"""Pre-freeze counterfactual input-budget and dev-output validation; no generation."""
from core import *
from qa_v2 import *
from scoring import score
from analyze import analyze

def main():
 out=RUNS/'stage1c';demos=readl(MAN/'demos_train.jsonl');checks=readl(RUNS/'frozen_v2/counterfactual_token_preflight.jsonl') if (RUNS/'frozen_v2/counterfactual_token_preflight.jsonl').exists() else []
 with Client('secqa-stage1c-input-budget-no-generation',time.time()+180) as c:
  assert c.owns and (ROOT/'gpu.claim').exists()
  props=c.call('/props');assert props['total_slots']==2 and props['default_generation_settings']['n_ctx']==8192
  for t in ([] if checks else readl(RUNS/'frozen_v2/counterfactual_evidence.jsonl')):
   counts={a:len(c.tokens(c.render(messages_v2(t['row']['question'],t['evidence']['chunks'],demos,a)))) for a in ['A0','A1']}
   checks.append(dict(item_id=t['row']['item_id'],tokens=counts,over_budget=max(counts.values())+MAX_TOKENS>8192))
  assert c.generation_n==0 and not any(r['over_budget'] for r in checks)
 jsonl(RUNS/'frozen_v2/counterfactual_token_preflight.jsonl',checks)
 inputs=readl(B/'evidence_candidate2_bm25_k10.jsonl');rows={t['row']['item_id']:t['row'] for t in inputs};ev={t['row']['item_id']:t['evidence'] for t in inputs};joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')}
 ids={r['item_id'] for r in readl(out/'self_answer_50_manifest.jsonl')};old=[r for r in readl(B/'answers_candidate2_bm25_k10.jsonl') if r['arm']=='A0' and r['item_id'] in ids];new=readl(out/'answers_self_answer_50.jsonl');mainarms={a:[] for a in ['A0','A1']}
 for r in old+new:
  r=dict(r,row=rows[r['item_id']]);r['score']=score(r,r['row'],ev[r['item_id']],joins[r['item_id']]);mainarms[r['arm']].append(r)
 taus={r['item_id']:r['top1_fused'] for r in readl(RUNS/'frozen_v2/tau_scores.jsonl')};summary,categories=analyze(mainarms,ev,joins,taus=taus,dev=True)
 dump(out/'dev_self_answer_50/analysis.json',summary);jsonl(out/'dev_self_answer_50/error_categories.jsonl',categories)
 dump(out/'validation.json',dict(counterfactual_n=len(checks),counterfactual_over_budget=0,counterfactual_max_tokens=max(max(x['tokens'].values()) for x in checks),generation_requests=0,self_answer_dev_analysis_n=50,server_slots=props['total_slots'],server_context=props['default_generation_settings']['n_ctx']))
 print(json.dumps(summary['self_answer_vs_execution']))
if __name__=='__main__':main()
