import concurrent.futures,os,time
from core import *
from retrieval import *
from scoring import *
def main():
 if (RUNS/'dev_answers_r0.jsonl').exists():raise StopRun('Refusing to overwrite existing development generations')
 if (RUNS/'STOP.json').exists():raise StopRun((RUNS/'STOP.json').read_text())
 rows=readl(MAN/'docfinqa_dev_sample.jsonl');demos=readl(MAN/'demos_train.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_dev_join.jsonl')}
 existing={(r['item_id'],r['arm']):r for r in readl(RUNS/'preflight_answers.jsonl')}
 preexisting={r['item_id']:r for r in readl(RUNS/'preflight_prompts.jsonl')};evidence={};tokenrows=[];results=[]
 dump(RUNS/'prompt_revision_log.json',dict(revisions=[dict(revision='r0',reason='Initial shared-evidence direct vs extract-compute specification; three seed-selected demonstrations including an evidence-missing abstention example',system=SYSTEM,A0=A0,A1=A1,demos_sha256=sha((MAN/'demos_train.jsonl').read_bytes()))],prompt_revisions_after_initial=0,parser_note='Parser expanded before final dev scoring to handle explicit amounts/percents in prose, per-share/grant units, and x:1; no generation regenerated.'))
 start=time.time()
 with Client('secqa-stage1-dev-pilot',float(os.environ['STAGE1_DEADLINE'])) as c:
  retr=Retriever(c)
  for row in rows:
   e=preexisting.get(row['item_id']) or retr.get(row['doc_group'],row['question']);evidence[row['item_id']]=e
   counts={a:len(c.tokens(c.render(messages(row['question'],e['chunks'],demos,a)))) for a in ['A0','A1']}
   tokenrows.append(dict(item_id=row['item_id'],prompt_tokens=counts,completion_budget=650,over_budget=any(t+650>4096 for t in counts.values())))
  jsonl(RUNS/'dev_evidence.jsonl',[dict(item_id=i,**{k:v for k,v in e.items() if k!='item_id'}) for i,e in evidence.items()]);jsonl(RUNS/'dev_token_preflight.jsonl',tokenrows)
  over=sum(r['over_budget'] for r in tokenrows)
  if over/len(rows)>.05:
   dump(RUNS/'STOP.json',dict(reason='evidence_budget_gt_4096_for_gt5pct',over=over,n=len(rows)));raise StopRun('evidence_budget_gt_4096_for_gt5pct')
  def one(row,arm):
   key=(row['item_id'],arm)
   if key in existing:return dict(existing[key],reused_preflight=True)
   st=time.monotonic();e=evidence[row['item_id']]
   tokenrow=next(r for r in tokenrows if r['item_id']==row['item_id'])
   if tokenrow['prompt_tokens'][arm]+650>4096:
    return dict(item_id=row['item_id'],arm=arm,revision='r0',not_sent='context_budget',response=dict(choices=[dict(message=dict(content=''),finish_reason='length')],usage=dict(prompt_tokens=tokenrow['prompt_tokens'][arm],completion_tokens=0)))
   try:r=c.generate(messages(row['question'],e['chunks'],demos,arm))
   except ServerRequestError as exc:
    r=dict(choices=[dict(message=dict(content=''),finish_reason='server_error')],usage=dict(prompt_tokens=tokenrow['prompt_tokens'][arm],completion_tokens=0),error=str(exc))
   return dict(item_id=row['item_id'],arm=arm,revision='r0',elapsed_seconds=time.monotonic()-st,response=r)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
   for arm in ['A1','A0']:
    for batch in range(0,len(rows),4):
     c.guard(True);futures=[ex.submit(one,r,arm) for r in rows[batch:batch+4]]
     for f in futures:results.append(f.result())
     jsonl(RUNS/'dev_answers_r0.jsonl',results)
     print(arm,batch+len(futures),flush=True)
 scored=[];rowmap={r['item_id']:r for r in rows}
 for r in results:scored.append(score(r,rowmap[r['item_id']],evidence[r['item_id']],joins.get(r['item_id'])))
 jsonl(RUNS/'dev_scores_r0.jsonl',scored)
 summary={a:summarize([r for r in scored if r['arm']==a]) for a in ['A0','A1']};summary.update(revision='r0',unique_dev_items=len(rows),generations_total=len(results),reused_preflight=len(existing),new_generation_requests=c.generation_n,wall_seconds=time.time()-start,server_errors=c.errors,token_preflight={a:distribution([r['prompt_tokens'][a] for r in tokenrows]) for a in ['A0','A1']},over_budget=over)
 dump(RUNS/'dev_summary_r0.json',summary);dump(RUNS/'ranking_selection.json',rank_selection([r for r in scored if r['arm']=='A1']));print(json.dumps(summary),flush=True)
if __name__=='__main__':
 try:main()
 except StopRun as e:dump(RUNS/'STOP.json',dict(reason=str(e)));raise
