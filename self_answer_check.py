"""Paired 50-item dev-2 schema-only addition check. Never loads test data."""
import concurrent.futures,random,time
from schema_check import valid_schema
from core import *
from qa_v2 import *
from scoring import score,extract_json

def main():
 out=RUNS/'stage1c';out.mkdir(exist_ok=True)
 rows=readl(MAN/'docfinqa_dev2.jsonl');assert len(rows)==200 and all(r['split']=='train' for r in rows)
 rows=random.Random(SEED).sample(sorted(rows,key=lambda r:r['item_id']),50)
 evidence={x['row']['item_id']:x['evidence'] for x in readl(B/'evidence_candidate2_bm25_k10.jsonl')}
 old={x['item_id']:x for x in readl(B/'answers_candidate2_bm25_k10.jsonl') if x['arm']=='A1'}
 joins={x['item_id']:x for x in readl(MAN/'finqa_dev2_join.jsonl')};demos=readl(MAN/'demos_train.jsonl')
 jsonl(out/'self_answer_50_manifest.jsonl',rows);dump(out/'self_answer_schema.json',schema('A1'))
 start=time.time();results=[]
 with Client('secqa-stage1c-self-answer',start+900) as c:
  assert c.owns and (ROOT/'gpu.claim').exists()
  props=c.call('/props');assert props['total_slots']==2 and props['default_generation_settings']['n_ctx']==8192
  def one(row):
   ms=messages_v2(row['question'],evidence[row['item_id']]['chunks'],demos,'A1')
   return dict(item_id=row['item_id'],arm='A1',response=generate_v2(c,ms,'A1'))
  with (out/'answers_self_answer_50.jsonl').open('x') as f,concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
   for pos in range(0,50,2):
    fs=[ex.submit(one,row) for row in rows[pos:pos+2]]
    for fu in fs:
     r=fu.result();results.append(r);f.write(json.dumps(r)+'\n');f.flush()
    print('DEV',len(results),round(time.time()-start),flush=True)
 rowmap={r['item_id']:r for r in rows};metrics={};scores=[]
 for label,answers in [('stage1b',[old[r['item_id']] for r in rows]),('self_answer',results)]:
  valid=0;correct=0
  for r in answers:
   obj=extract_json(r['response']['choices'][0]['message'].get('content'));s=score(r,rowmap[r['item_id']],evidence[r['item_id']],joins[r['item_id']]);correct+=s['NumMatch_1pct']
   sch=schema('A1')
   if label=='stage1b':sch['properties'].pop('self_answer');sch['required'].remove('self_answer')
   ok=valid_schema(obj,sch) and r['response']['choices'][0]['finish_reason']=='stop'
   valid+=ok;scores.append(dict(label=label,**s))
  metrics[label]=dict(n=50,JSON_validity=valid/50,valid=valid,NumMatch_1pct=correct/50,correct=correct)
 delta=metrics['self_answer']['NumMatch_1pct']-metrics['stage1b']['NumMatch_1pct']
 metrics.update(delta_pp=100*delta,retain=metrics['self_answer']['JSON_validity']>=.98 and delta>=-.040000000001,seconds=time.time()-start,generation_requests=50,prompt_change='schema property only; all messages and evidence unchanged',seed=SEED)
 jsonl(out/'scores_self_answer_50.jsonl',scores);dump(out/'self_answer_check.json',metrics);print(json.dumps(metrics),flush=True)
if __name__=='__main__':main()
