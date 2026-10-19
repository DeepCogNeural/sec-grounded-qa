"""Development only; never accepts evaluation manifests."""
import argparse,concurrent.futures,datetime,time
from core import *
from qa_v2 import *
from retrieval import Retriever,build_group,hitrate
from retrieval_v2 import operand_hit
from scoring import score,summarize,extract_json,distribution
def register(label,revision,method,k):
 p=B/'revision_log_v2.json';log=json.loads(p.read_text()) if p.exists() else {'entries':[]}
 if any(x['label']==label for x in log['entries']):raise StopRun('label_already_registered')
 log['entries'].append(dict(label=label,revision=revision,reason='Constrained JSON and missing-number-only abstention; reasoning capped at 160 characters to enforce at most 80 whitespace words, after initial baseline exceeded the instruction on 8 outputs.' if revision=='r0' else 'Clarify arithmetic, period-column alignment, extrema without forbidden functions, and missing evidence; same revision allowance for both arms.',retriever=method,k=k,arms=['A0','A1'],created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),system=SYSTEM_V2,extra=REVISION_EXTRA[revision],A0=A0_V2,A1=A1_V2,schema={a:schema(a) for a in ['A0','A1']},status='registered_before_generation'))
 dump(p,log)
def main(args):
 assert args.revision in REVISION_EXTRA
 path=B/('answers_'+args.label+'.jsonl')
 if path.exists():raise StopRun('refuse_overwrite')
 rows=readl(MAN/'docfinqa_dev2.jsonl');assert len(rows)==200 and all(r['split']=='train' for r in rows)
 joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')};demos=readl(MAN/'demos_train.jsonl');evidence={};results=[]
 register(args.label,args.revision,args.method,args.k)
 start=time.time()
 with Client('secqa-stage1b-dev-'+args.label,min(DEADLINE-600,args.stop_at)) as c:
  props=c.call('/props');ctx=props['default_generation_settings']['n_ctx'];concurrency=props['total_slots']
  if args.evidence:
   source={x['row']['item_id']:x['evidence'] for x in readl(B/args.evidence)}
  else:
   for n,g in enumerate(sorted(set(r['doc_group'] for r in rows))):
    c.guard();build_group(g,(INDEX/'sources'/f'{g}.txt').read_text(),c)
    if n%10==0:print('INDEX',n,flush=True)
   retr=Retriever(c);source={r['item_id']:retr.get(r['doc_group'],r['question']) for r in rows}
  for r in rows:
   e=pack_shared(c,r,source[r['item_id']],demos,ctx);evidence[r['item_id']]=e
  jsonl(B/('evidence_'+args.label+'.jsonl'),[dict(row=r,evidence=evidence[r['item_id']]) for r in rows])
  generation_start=time.time()
  def one(r,arm):
   c.guard();e=evidence[r['item_id']];ms=messages_v2(r['question'],e['chunks'],demos,arm,args.revision);st=time.time()
   response=generate_v2(c,ms,arm)
   return dict(item_id=r['item_id'],arm=arm,revision=args.revision,label=args.label,response=response,elapsed_seconds=time.time()-st)
  with path.open('x') as f,concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
   for arm in ['A1','A0']:
    armstart=time.time()
    for pos in range(0,200,concurrency):
     fs=[ex.submit(one,r,arm) for r in rows[pos:pos+concurrency]]
     for fu in fs:
      x=fu.result();results.append(x);f.write(json.dumps(x,ensure_ascii=False)+'\n');f.flush()
     if (pos+concurrency)%20==0:print(arm,pos+concurrency,'seconds',round(time.time()-armstart),flush=True)
    if arm=='A1':dump(B/('first_arm_'+args.label+'.json'),dict(seconds=time.time()-armstart,n=200))
  generation_seconds=time.time()-generation_start
 joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')}
 rowmap={r['item_id']:r for r in rows};scored=[score(x,rowmap[x['item_id']],evidence[x['item_id']],joins[x['item_id']]) for x in results]
 jsonl(B/('scores_'+args.label+'.jsonl'),scored);summary={}
 for a in ['A0','A1']:
  ss=[x for x in scored if x['arm']==a];s=summarize(ss)
  objs=[extract_json(x['response']['choices'][0]['message'].get('content')) for x in results if x['arm']==a]
  op=[operand_hit(evidence[r['item_id']]['chunks'],joins[r['item_id']]) for r in rows];op=[x for x in op if x]
  s.update(packed_snippet_any_HR=s['HR_at_5'],packed_snippet_all_HR=s['all_gold_HR_at_5'],abstain_rate=s['abstain']/200,answered_conditional_accuracy=sum(x['NumMatch_1pct'] for x in ss)/s['answered'] if s['answered'] else None,JSON_validity=sum(isinstance(x,dict) for x in objs)/200,reasoning_over_80_words=sum(isinstance(x,dict) and len(x.get('reasoning','').split())>80 for x in objs),packed_operand_all_HR=sum(x['all_hit'] for x in op)/len(op) if op else None,operand_n=len(op))
  summary[a]=s
 summary.update(label=args.label,revision=args.revision,retriever=args.method,k=args.k,context_per_slot=ctx,concurrency=concurrency,generation_seconds=generation_seconds,questions_per_hour=400*3600/generation_seconds,wall_seconds=time.time()-start,server_errors=c.errors,request_count=c.generation_n,evidence_hash=sha((B/('evidence_'+args.label+'.jsonl')).read_bytes()),generation_scope='200 fixed dev-2 train items, both arms; no test or FinanceBench')
 dump(B/('summary_'+args.label+'.json'),summary)
 log=json.loads((B/'revision_log_v2.json').read_text())
 for x in log['entries']:
  if x['label']==args.label:x.update(status='complete',summary_file='summary_'+args.label+'.json',metrics=summary)
 dump(B/'revision_log_v2.json',log)
 print(json.dumps(summary),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--revision',default='r0');p.add_argument('--method',default='bm25');p.add_argument('--k',type=int,default=5);p.add_argument('--evidence');p.add_argument('--stop-at',type=float,default=DEADLINE-600);main(p.parse_args())

