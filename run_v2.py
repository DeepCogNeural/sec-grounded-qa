"""Frozen stage-2 runner. No stage-2 generation during development."""
import argparse,concurrent.futures,datetime,random,subprocess,time
from core import *
from qa_v2 import messages_v2,generate_v2,MAX_TOKENS
from scoring import score,summarize
from run import append,git
def verify(args):
 if not args.prereg_approved:raise SystemExit('protocol approval is required.')
 if git('rev-parse','HEAD')!=args.reviewed_commit or git('status','--porcelain'):raise SystemExit('Reviewed HEAD must match and be clean.')
 if not git('ls-files','PREREG_v2.md'):raise SystemExit('PREREG_v2 must be committed.')
 text=pathlib.Path('PREREG_v2.md').read_text()
 if 'REVIEW_PLACEHOLDER' in text:raise SystemExit('reviewer must fill headline hierarchy before approval.')
 p=json.loads(pathlib.Path('protocol_v2.json').read_text())
 if p.get('freeze_status')!='ready_for_protocol_review':raise SystemExit('Protocol is incomplete.')
 for key,root in [('manifest_hashes',MAN),('evidence_hashes',RUNS/'frozen_v2')]:
  for name,h in p[key].items():
   if sha((root/name).read_bytes())!=h:raise SystemExit('Frozen file changed: '+name)
 for name,h in p['code_hashes'].items():
  if sha(pathlib.Path(name).read_bytes())!=h:raise SystemExit('Frozen code changed: '+name)
 return p
def batch(name,arm,inputs,c,demos,out,joins,p):
 dest=out/(name+'.jsonl')
 if dest.exists():raise StopRun('refuse_regenerate_'+name)
 results=[];workers=p['concurrency'];ctx=p['context_per_slot'];rev=p['selected_revisions'][arm]
 def one(t):
  row=t['row'];e=t['evidence'];ms=messages_v2(row['question'],e['chunks'],demos,arm,rev);n=len(c.tokens(c.render(ms)))
  if n+MAX_TOKENS>ctx:
   response=dict(choices=[dict(message=dict(content=''),finish_reason='length')],usage=dict(prompt_tokens=n,completion_tokens=0));not_sent='context_budget'
  else:
   not_sent=None
   try:response=generate_v2(c,ms,arm)
   except ServerRequestError as exc:response=dict(choices=[dict(message=dict(content=''),finish_reason='server_error')],usage=dict(prompt_tokens=n,completion_tokens=0),error=str(exc))
  result=dict(item_id=row['item_id'],arm=arm,response=response,not_sent=not_sent,doc_group=row['doc_group'],row=row)
  result['score']=score(result,row,e,joins.get(row.get('source_item_id',row['item_id'])) if name not in ['counterfactual'] else None)
  if row.get('probe',{}).get('kind') in ['withheld','easy']:
   result['probe_false_answer']=not result['score']['abstain'];result['probe_refusal']=result['score']['abstain']
   result['invalid_response']=not result['score']['answered'] and not result['probe_refusal']
  return result
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  for pos in range(0,len(inputs),workers):
   c.guard(True);fs=[ex.submit(one,t) for t in inputs[pos:pos+workers]]
   for f in fs:
    r=f.result();append(dest,r);results.append(r)
   print(name,len(results),'/',len(inputs),flush=True)
 summary=summarize([r['score'] for r in results]) if results else dict(n=0)
 probes=[r for r in results if 'probe_false_answer' in r]
 if probes:summary['probe_metrics']=dict(n=len(probes),false_answer_rate=sum(r['probe_false_answer'] for r in probes)/len(probes),explicit_abstention_rate=sum(r['probe_refusal'] for r in probes)/len(probes),invalid_response_rate=sum(r['invalid_response'] for r in probes)/len(probes))
 dump(out/(name+'_summary.json'),summary)
 return results
def build_plan(p):
 frozen=RUNS/'frozen_v2';test=readl(frozen/'test_evidence.jsonl');withheld=readl(frozen/'withheld_evidence.jsonl')
 inputs={'A1':('A1',test),'A0':('A0',test),'withheld_A1':('A1',withheld),'withheld_A0':('A0',withheld),'contextdep':('A0',readl(frozen/'contextdep_evidence.jsonl')),'rerun30':('A1',random.Random(SEED).sample(test,30)),'counterfactual':('A1',readl(frozen/'counterfactual_evidence.jsonl')),'financebench':('A1',readl(frozen/'financebench_evidence.jsonl')),'oracle':('A1',readl(frozen/'oracle_evidence.jsonl'))}
 plan=[(name,*inputs[name]) for name in p['run_order']]
 assert all(len(z[2])==p['block_sizes'][z[0]] for z in plan)
 return plan

def block_fits(name,n,used,remaining_seconds,p):
 reserved=2*n if name=='withheld_A1' else n
 return used+reserved<=p['request_capacity'] and remaining_seconds>=reserved*3600/p['safe_qph']

def main(args):
 p=verify(args)
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):raise SystemExit('Invalid run id')
 out=RUNS/args.run_id;out.mkdir(exist_ok=False)
 # Exclusive global marker prevents a second test run, including partial reruns.
 with (RUNS/'TEST_GENERATION_STARTED.json').open('x') as f:json.dump(dict(run_id=args.run_id,reviewed_commit=args.reviewed_commit),f)
 start=time.time();deadline=start+p['stage2_hours']*3600;demos=readl(MAN/'demos_train.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_join.jsonl')}
 plan=build_plan(p)
 completed=[];used=0;a1=None;cut=[]
 dump(out/'run_config.json',dict(reviewed_commit=args.reviewed_commit,protocol=p,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 try:
  with Client('secqa-stage2-'+args.run_id,deadline) as c:
   props=c.call('/props')
   if props['total_slots']!=p['total_slots'] or props['default_generation_settings']['n_ctx']!=p['context_per_slot'] or props['model_alias']!=p['model_alias']:raise StopRun('server_configuration_changed')
   for index,(name,arm,inputs) in enumerate(plan):
    if name not in p['planned_blocks']:cut=[z[0] for z in plan[index:]];break
    n=len(inputs)
    if not block_fits(name,n,used,deadline-time.time(),p):
     cut=[z[0] for z in plan[index:]];break
    results=batch(name,arm,inputs,c,demos,out,joins,p);completed.append(name);used+=n
    if name=='A1':a1=results
    if name=='financebench':
     ans=[r['score'] for r in results if r['row']['probe']['kind']=='answerable'];dump(out/'financebench_answerable_summary.json',summarize(ans))
   dump(out/'status.json',dict(status='complete' if not cut else 'cut',completed=completed,cut=cut,attempted_items=used,generation_requests=c.generation_n,generation_errors=c.generation_errors,wall_seconds=time.time()-start))
 except StopRun as exc:
  dump(out/'status.json',dict(status='stopped',reason=str(exc),completed=completed,attempted_items=used,wall_seconds=time.time()-start));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--reviewed-commit',required=True);p.add_argument('--prereg-approved',action='store_true');p.add_argument('--run-id',required=True);main(p.parse_args())

