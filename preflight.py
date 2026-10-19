import concurrent.futures,collections,os,time
from core import *
from retrieval import *
REV='r0'
def run():
 if (RUNS/'preflight_answers.jsonl').exists():raise StopRun('Refusing to overwrite existing development generations')
 rows=readl(MAN/'docfinqa_dev_sample.jsonl')[:20];demos=readl(MAN/'demos_train.jsonl')
 deadline=float(os.environ['STAGE1_DEADLINE'])
 with Client('secqa-stage1-preflight',deadline) as c:
  for i,row in enumerate(rows):
   h=row['doc_group'];build_group(h,(INDEX/'sources'/f'{h}.txt').read_text(),c)
   print('indexed',i+1,flush=True)
  retr=Retriever(c);tasks=[];pre=[]
  for row in rows:
   e=retr.get(row['doc_group'],row['question']);allmsgs={a:messages(row['question'],e['chunks'],demos,a) for a in ['A0','A1']}
   counts={a:len(c.tokens(c.render(m))) for a,m in allmsgs.items()}
   pre.append(dict(item_id=row['item_id'],prompt_tokens=counts,completion_budget=650,over_budget=any(n+650>4096 for n in counts.values()),**e))
   tasks.append(dict(row=row,messages=allmsgs['A1'],prompt_tokens=counts['A1']))
  jsonl(RUNS/'preflight_prompts.jsonl',pre)
  if sum(p['over_budget'] for p in pre)/len(pre)>.05:
   dump(RUNS/'STOP.json',dict(reason='evidence_budget_gt_4096_for_gt5pct',items=len(pre),over_budget=sum(p['over_budget'] for p in pre)));return
  if any(p['over_budget'] for p in pre):raise StopRun('Cannot send any over-budget prompt; investigate before generation')
  results=[];start=time.monotonic()
  def one(t):
   st=time.monotonic();r=c.generate(t['messages']);ch=r['choices'][0]
   return dict(item_id=t['row']['item_id'],arm='A1',revision=REV,elapsed_seconds=time.monotonic()-st,prompt_tokens_preflight=t['prompt_tokens'],response=r,finish_reason=ch['finish_reason'],answer=ch['message']['content'])
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    for batch in range(0,20,4):
     c.guard(True)
     fut=[ex.submit(one,t) for t in tasks[batch:batch+4]]
     for f in fut:
      r=f.result();results.append(r);jsonl(RUNS/'preflight_answers.jsonl',results)
     print('generated',len(results),flush=True)
  except StopRun as e:
   dump(RUNS/'STOP.json',dict(reason=str(e),completed=len(results)));raise
  wall=time.monotonic()-start
  summary=dict(requests=len(results),unique_dev_items=len(results),wall_seconds=wall,questions_per_hour=len(results)*3600/wall,reference_qph=732,ratio_to_reference=(len(results)*3600/wall)/732,concurrency=4,temperature=0,cache_prompt=False,enable_thinking=False,finish_reasons=dict(collections.Counter(r['finish_reason'] for r in results)),prompt_tokens=[r['response']['usage']['prompt_tokens'] for r in results],completion_tokens=[r['response']['usage']['completion_tokens'] for r in results],prompt_token_counts=[p['prompt_tokens'] for p in pre],server_requests=c.n,server_errors=c.errors)
  dump(RUNS/'preflight_summary.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':run()
