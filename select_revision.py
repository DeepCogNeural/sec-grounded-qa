"""Select the prompt using the rule saved before r1 outputs."""
from core import *
from scoring import *
def main():
 rule=json.loads((RUNS/'revision_selection_rule.json').read_text());ids=set(rule['ids']);metrics={};scores={};summaries={}
 for version in ['r0','r1']:
  scores[version]=readl(RUNS/f'dev_scores_{version}.jsonl');ss=[r for r in scores[version] if r['item_id'] in ids]
  assert len(ss)==100
  metrics[version]=dict(correct=sum(r['NumMatch_1pct'] for r in ss),unparseable=sum(r['unparseable'] for r in ss),by_arm={a:summarize([r for r in ss if r['arm']==a]) for a in ['A0','A1']})
  summaries[version]=json.loads((RUNS/f'dev_summary_{version}.json').read_text())
 winner=max(['r0','r1'],key=lambda v:(metrics[v]['correct'],-metrics[v]['unparseable'],v=='r0'))
 log=json.loads((RUNS/'prompt_revision_log.json').read_text());chosen=next(r for r in log['revisions'] if r['revision']==winner)
 path=pathlib.Path('core.py');lines=path.read_text().splitlines();path.write_text('\n'.join('SYSTEM='+repr(chosen['system']) if l.startswith('SYSTEM=') else l for l in lines)+'\n')
 log['selected_revision']=winner;log['matched_comparison']=metrics;dump(RUNS/'prompt_revision_log.json',log)
 pre0=json.loads((RUNS/'preflight_summary.json').read_text());pre1=json.loads((RUNS/'preflight_r1_summary.json').read_text())
 result=dict(chosen=winner,selection_rule=rule,matched_comparison=metrics,unique_dev_items=100,generation_requests=300,prompt_versions=2,prompt_revisions_after_initial=1,final_sample_n=summaries[winner]['unique_dev_items'],cut_qph=min(pre0['questions_per_hour'],pre1['questions_per_hour']))
 dump(RUNS/'revision_selection.json',result);dump(RUNS/'ranking_selection.json',rank_selection([r for r in scores[winner] if r['arm']=='A1']))
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
