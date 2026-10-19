"""One predeclared shared-format revision on 50 existing dev items."""
import concurrent.futures,os,time
import core
from core import *
from scoring import *
def main():
 if (RUNS/'dev_answers_r1.jsonl').exists():raise StopRun('Existing r1 outputs')
 if (RUNS/'STOP.json').exists():raise StopRun('Existing stop')
 rows=readl(MAN/'docfinqa_dev_sample.jsonl');selected=rows[:50]
 rule=dict(ids=[r['item_id'] for r in selected],selection='Higher combined A0+A1 NumMatch-1% correct count on the same 50 items; tie fewer unparseable outputs; final tie retain r0',throughput_cut='Minimum of r0 and r1 20-item A1 throughput',written_before_generation=True)
 dump(RUNS/'revision_selection_rule.json',rule)
 log=json.loads((RUNS/'prompt_revision_log.json').read_text())
 assert len(log['revisions'])==1
 core.SYSTEM=log['revisions'][0]['system']+' Use valid JSON: escape quotes; replace tabs and newlines inside strings with spaces.'
 log['revisions'].append(dict(revision='r1',reason='25 r0 A1 outputs contained literal control characters inside JSON strings; shared system instruction requests whitespace replacement and escaping',system=core.SYSTEM,A0=A0,A1=A1,demos_sha256=sha((MAN/'demos_train.jsonl').read_bytes())))
 log['prompt_revisions_after_initial']=1;dump(RUNS/'prompt_revision_log.json',log)
 ev={r['item_id']:r for r in readl(RUNS/'dev_evidence.jsonl')};demos=readl(MAN/'demos_train.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_dev_join.jsonl')};tokens=[];out=[];start=time.monotonic()
 with Client('secqa-stage1-dev-r1',float(os.environ['STAGE1_DEADLINE'])) as c:
  for r in rows:
   counts={a:len(c.tokens(c.render(messages(r['question'],ev[r['item_id']]['chunks'],demos,a)))) for a in ['A0','A1']}
   tokens.append(dict(item_id=r['item_id'],prompt_tokens=counts,over_budget=any(v+650>4096 for v in counts.values())))
  jsonl(RUNS/'dev_token_preflight_r1.jsonl',tokens)
  over=sum(r['over_budget'] for r in tokens)
  if over/100>.05:raise StopRun('evidence_budget_gt_4096_for_gt5pct')
  tokenmap={r['item_id']:r for r in tokens}
  def one(row,arm):
   st=time.monotonic();cnt=tokenmap[row['item_id']]['prompt_tokens'][arm]
   if cnt+650>4096:raise StopRun('Selected r1 item exceeds budget')
   response=c.generate(messages(row['question'],ev[row['item_id']]['chunks'],demos,arm))
   return dict(item_id=row['item_id'],arm=arm,revision='r1',elapsed_seconds=time.monotonic()-st,response=response)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
   for arm in ['A1','A0']:
    st=time.monotonic()
    for i in range(0,50,4):
     c.guard(True);fs=[ex.submit(one,r,arm) for r in selected[i:i+4]]
     out.extend(f.result() for f in fs);jsonl(RUNS/'dev_answers_r1.jsonl',out)
     if arm=='A1' and i==16:
      wall=time.monotonic()-st;rr=out[:20]
      dump(RUNS/'preflight_r1_summary.json',dict(n=20,wall_seconds=wall,questions_per_hour=72000/wall,concurrency=4,prompt_tokens=distribution([r['response']['usage']['prompt_tokens'] for r in rr]),completion_tokens=distribution([r['response']['usage']['completion_tokens'] for r in rr]),finish_reasons=dict(collections.Counter(r['response']['choices'][0]['finish_reason'] for r in rr))))
     print(arm,min(i+4,50),flush=True)
 scored=[score(r,next(z for z in rows if z['item_id']==r['item_id']),ev[r['item_id']],joins.get(r['item_id'])) for r in out]
 jsonl(RUNS/'dev_scores_r1.jsonl',scored)
 summary={a:summarize([r for r in scored if r['arm']==a]) for a in ['A0','A1']}
 summary.update(revision='r1',unique_dev_items=50,generations_total=100,new_generation_requests=c.generation_n,wall_seconds=time.monotonic()-start,server_errors=c.errors,token_preflight={a:distribution([r['prompt_tokens'][a] for r in tokens]) for a in ['A0','A1']},over_budget=over)
 dump(RUNS/'dev_summary_r1.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':
 try:main()
 except StopRun as e:dump(RUNS/'STOP.json',dict(reason=str(e)));raise
