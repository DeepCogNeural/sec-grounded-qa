"""Twenty dev-2 A1 requests at selected layout; no evaluation generation."""
import concurrent.futures,time
from core import *
from qa_v2 import *
from scoring import distribution
def main():
 config=json.loads((B/'selected_config.json').read_text());inputs=readl(B/('evidence_'+config['label']+'.jsonl'))[:20];demos=readl(MAN/'demos_train.jsonl');out=[];p=B/'throughput_v2_answers.jsonl'
 if p.exists():raise StopRun('throughput_already_measured')
 assert all(t['row'].get('split')=='train' for t in inputs)
 with Client('secqa-stage1b-throughput20',DEADLINE-120) as c:
  props=c.call('/props');workers=props['total_slots'];ctx=props['default_generation_settings']['n_ctx'];assert ctx==config['context_per_slot']
  jobs=[(t,messages_v2(t['row']['question'],t['evidence']['chunks'],demos,'A1',config['selected_revisions']['A1'])) for t in inputs]
  start=time.monotonic()
  def one(job):
   t,ms=job;st=time.monotonic();r=generate_v2(c,ms,'A1');return dict(item_id=t['row']['item_id'],arm='A1',response=r,elapsed_seconds=time.monotonic()-st)
  with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
   for i in range(0,20,workers):
    out.extend(f.result() for f in [ex.submit(one,j) for j in jobs[i:i+workers]])
  seconds=time.monotonic()-start
 jsonl(p,out)
 dump(B/'throughput_v2.json',dict(n=20,arm='A1',context_per_slot=ctx,concurrency=workers,wall_seconds=seconds,questions_per_hour=20*3600/seconds,server_errors=c.errors,prompt_tokens=distribution([x['response']['usage']['prompt_tokens'] for x in out]),answer_tokens=distribution([x['response']['usage']['completion_tokens'] for x in out]),finish_reasons=dict(collections.Counter(x['response']['choices'][0]['finish_reason'] for x in out)),cached_tokens=sorted({x['response']['usage'].get('prompt_tokens_details',{}).get('cached_tokens') for x in out}),scope='20 fixed dev-2 prompts, selected A1 revision, conservative proxy for all stage-2 blocks; short-run extrapolation'))
if __name__=='__main__':main()

