"""Recompute metadata-dependent metrics with the resolved train join."""
from core import *
from qa_v2 import B
from retrieval_v2 import operand_hit
from scoring import score,summarize,extract_json
def main():
 joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')};logs=json.loads((B/'revision_log_v2.json').read_text())
 for p in sorted(B.glob('summary_*.json')):
  s=json.loads(p.read_text())
  if 'label' not in s or 'A0' not in s:continue
  label=s['label'];raw=readl(B/('answers_'+label+'.jsonl'));ev={t['row']['item_id']:t for t in readl(B/('evidence_'+label+'.jsonl'))}
  scored=[score(r,ev[r['item_id']]['row'],ev[r['item_id']]['evidence'],joins[r['item_id']]) for r in raw]
  jsonl(B/('scores_'+label+'.jsonl'),scored)
  op=[operand_hit(t['evidence']['chunks'],joins[i]) for i,t in ev.items()];op=[x for x in op if x]
  for arm in ['A0','A1']:
   rs=[r for r in scored if r['arm']==arm];m=summarize(rs);n=len(rs);objs=[extract_json(r['response']['choices'][0]['message'].get('content')) for r in raw if r['arm']==arm]
   m.update(abstain_rate=m['abstain']/n,answered_conditional_accuracy=sum(r['NumMatch_1pct'] for r in rs)/m['answered'] if m['answered'] else None,JSON_validity=sum(isinstance(o,dict) for o in objs)/n,reasoning_over_80_words=sum(isinstance(o,dict) and len(o.get('reasoning','').split())>80 for o in objs),packed_operand_all_HR=sum(o['all_hit'] for o in op)/len(op) if op else None,operand_n=len(op),packed_snippet_any_HR=m['HR_at_5'],packed_snippet_all_HR=m['all_gold_HR_at_5'])
   s[arm]=m
  s['join_hash']=sha((MAN/'finqa_dev2_join.jsonl').read_bytes());s['metadata_rescore']='Resolved equivalent train join and existing reference-unit rule; no generation repeated or output used for join selection.'
  dump(p,s)
  for e in logs['entries']:
   if e['label']==label:e['metrics']=s
 dump(B/'revision_log_v2.json',logs)
if __name__=='__main__':main()

