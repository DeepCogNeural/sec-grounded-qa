"""Test execution is available only after explicit pre-registration review."""
import argparse,concurrent.futures,copy,datetime,math,random,subprocess,time
from core import *
from scoring import *

def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
def verify(args):
 if not args.prereg_approved:raise SystemExit('Stage 2 requires protocol pre-registration review and commit.')
 if git('rev-parse','HEAD')!=args.reviewed_commit:raise SystemExit('Reviewed commit does not match HEAD.')
 if git('status','--porcelain'):raise SystemExit('Working tree must be clean.')
 if not git('ls-files','PREREG_draft.md'):raise SystemExit('Pre-registration must be committed.')
 p=json.loads(pathlib.Path('protocol.json').read_text())
 for filename,expected in p['manifest_hashes'].items():
  if sha((MAN/filename).read_bytes())!=expected:raise SystemExit('Manifest changed: '+filename)
 for filename,expected in p['evidence_hashes'].items():
  if sha((RUNS/'frozen'/filename).read_bytes())!=expected:raise SystemExit('Frozen evidence changed: '+filename)
 return p

def append(path,row):
 with pathlib.Path(path).open('a') as f:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush()

def batch_run(name,arm,inputs,c,demos,out,joins):
 destination=out/(name+'.jsonl')
 if destination.exists():raise StopRun('Refusing to regenerate existing test output '+name)
 results=[]
 def one(t):
  row=t['row'];e=t['evidence'];ms=messages(row['question'],e['chunks'],demos,arm);n=len(c.tokens(c.render(ms)))
  if n+650>4096:
   response=dict(choices=[dict(message=dict(content=''),finish_reason='length')],usage=dict(prompt_tokens=n,completion_tokens=0));not_sent='context_budget'
  else:
   not_sent=None
   try:response=c.generate(ms)
   except ServerRequestError as exc:response=dict(choices=[dict(message=dict(content=''),finish_reason='server_error')],usage=dict(prompt_tokens=n,completion_tokens=0),error=str(exc))
  result=dict(item_id=row['item_id'],arm=arm,response=response,not_sent=not_sent,doc_group=row['doc_group'])
  result['score']=score(result,row,e,joins.get(row['item_id']) if name!='counterfactual' else None);result['row']=row
  return result
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
  for pos in range(0,len(inputs),4):
   c.guard(True);futures=[ex.submit(one,t) for t in inputs[pos:pos+4]]
   for f in futures:
    r=f.result();append(destination,r);results.append(r)
   print(name,len(results),'/',len(inputs),flush=True)
 dump(out/(name+'_summary.json'),summarize([r['score'] for r in results]) if results else dict(n=0))
 return results

def substitute_counterfactual(base_results,inputs):
 evidence={t['row']['item_id']:t for t in inputs};pool=sorted(base_results,key=lambda r:r['item_id']);random.Random(SEED).shuffle(pool);selected=[];excluded=[]
 for r in pool:
  if not r['score']['NumMatch_1pct']:continue
  obj=extract_json(r['response']['choices'][0]['message'].get('content'));ops=obj.get('operands',[]) if isinstance(obj,dict) else []
  if not ops or obj.get('answer_type')=='yes_no':continue
  t=copy.deepcopy(evidence[r['item_id']]);changes={};bad=None
  for o in ops:
   v=o.get('value')
   if type(v) not in (int,float) or not any(has_value(ch['text'],v) for ch in t['evidence']['chunks']):bad='operand_absent';break
   if str(int(v)) in re.findall(r'(?:19|20)\d\d',str(o.get('period',''))) and float(v).is_integer():bad='operand_is_period_year';break
   if v not in changes:changes[v]=v*(1.3 if len(changes)%2==0 else .7)
  if bad:excluded.append(dict(item_id=r['item_id'],reason=bad));continue
  newops=[dict(o,value=changes[o['value']]) for o in ops]
  try:value=evaluate(obj['program'],newops)
  except ProgramError:continue
  gold=dict(value=value,is_percent=obj['answer_type']=='percent',is_yes_no=False)
  if match(r['score']['prediction'],gold):excluded.append(dict(item_id=r['item_id'],reason='new_gold_not_distinguishable_under_NumMatch_1pct'));continue
  replacements=collections.Counter()
  def repl(m):
   val=float(m[0])
   if val in changes:replacements[val]+=1;return format(changes[val],'.12g')
   return m[0]
  for ch in t['evidence']['chunks']:ch['text']=NUMBER_SCAN.sub(repl,norm(ch['text']))
  if any(replacements[v]==0 for v in changes):continue
  t['row']['old_gold']=t['row']['gold'];t['row']['gold']=gold;t['row']['counterfactual']=dict(original_program=obj['program'],changes=[dict(old=k,new=v,occurrences=replacements[k]) for k,v in changes.items()],new_operands=newops,synthetic=True)
  selected.append(t)
  if len(selected)==150:break
 return selected,excluded

def main(args):
 protocol=verify(args);out=RUNS/args.run_id
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):raise SystemExit('Invalid run id')
 out.mkdir(exist_ok=False)
 with (RUNS/'TEST_GENERATION_STARTED.json').open('x') as marker:json.dump(dict(run_id=args.run_id,reviewed_commit=args.reviewed_commit),marker)
 start=time.time();deadline=start+protocol['stage2_hours']*3600;demos=readl(MAN/'demos_train.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_join.jsonl')};frozen=RUNS/'frozen';test=readl(frozen/'test_evidence.jsonl');a1=None;completed=[];cut=[]
 capacity=protocol['request_capacity'];used=0
 dump(out/'run_config.json',dict(reviewed_commit=args.reviewed_commit,protocol=protocol,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 try:
  with Client('secqa-stage2-'+args.run_id,deadline) as c:
   props=c.call('/props')
   if props['total_slots']!=4 or props['default_generation_settings']['n_ctx']!=4096 or props['model_alias']!=protocol['model_alias']:raise StopRun('server_configuration_changed')
   plan=[('A1','A1',test),('A0','A0',test),('financebench','A1',readl(frozen/'financebench_evidence.jsonl')),('oracle','A1',readl(frozen/'oracle_evidence.jsonl')),('contextdep','A0',readl(frozen/'contextdep_evidence.jsonl')),('counterfactual','A1',None),('rerun30','A1',None)]
   for index,(name,arm,inputs) in enumerate(plan):
    if name=='counterfactual':
     inputs,excluded=substitute_counterfactual(a1,test);jsonl(out/'counterfactual_inputs.jsonl',inputs);jsonl(out/'counterfactual_excluded.jsonl',excluded)
    if name=='rerun30':inputs=random.Random(SEED).sample(test,30)
    n=len(inputs);remaining_seconds=deadline-time.time();needed=n*3600/(protocol['preflight_qph']*.8)
    if used+n>capacity or remaining_seconds<needed:
     cut=[x[0] for x in plan[index:]];break
    results=batch_run(name,arm,inputs,c,demos,out,joins);used+=n;completed.append(name)
    if name=='A1':a1=results
    if name=='financebench':
     ans=[r['score'] for r in results if r['row']['probe']['kind']=='answerable'];dump(out/'financebench_answerable_summary.json',summarize(ans))
   dump(out/'status.json',dict(status='complete' if not cut else 'cut',completed=completed,cut=cut,attempted_items=used,generation_requests=c.generation_n,generation_errors=c.generation_errors,wall_seconds=time.time()-start))
 except StopRun as exc:
  dump(out/'status.json',dict(status='stopped',reason=str(exc),completed=completed,wall_seconds=time.time()-start));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--reviewed-commit',required=True);p.add_argument('--prereg-approved',action='store_true');p.add_argument('--run-id',required=True);main(p.parse_args())
