"""Establish FinQA reference units from gold metadata before predictions."""
import math
from core import *
def reference_scale(answer,exe):
 p=parse(answer)
 if not p or p['is_yes_no'] or not p['is_percent']:return .01,'default: percentage points to ratio'
 try:
  v=abs(float(exe)/p['value'])
  if v==0:return .01,'zero reference; ratio convention'
  scale=min([.01,1.],key=lambda s:abs(math.log(v/s)))
  return scale,'nearest unit scale of reference exe_ans / reference percent answer, independent of model prediction'
 except (ValueError,TypeError,ZeroDivisionError):return .01,'zero reference; ratio convention'
def main():
 allqa={}
 for split in ['test','dev','train']:
  for r in json.load(open(DATA/'FinQA/dataset'/f'{split}.json')):allqa[r['id']]=r['qa']
 for filename in ['finqa_join.jsonl','finqa_dev_join.jsonl','oracle_200.jsonl']:
  rows=readl(MAN/filename)
  for r in rows:
   if r['join_status']=='unresolved':continue
   q=allqa[r['finqa_id']];r['qa.answer']=q.get('answer');scale,rule=reference_scale(q.get('answer'),q.get('exe_ans'));r['prediction_percent_to_finqa_scale']=scale;r['finqa_unit_rule']=rule
  jsonl(MAN/filename,rows)
 from manifests import hashes
 summary=json.loads((RUNS/'manifest_summary.json').read_text());summary['manifests']=hashes();dump(RUNS/'manifest_summary.json',summary)
if __name__=='__main__':main()
