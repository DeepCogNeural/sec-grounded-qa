"""Deterministic selection using completed development files only."""
import argparse,datetime
from core import *
from qa_v2 import B
from scoring import rank_selection
def main(phase):
 summaries=[json.loads(p.read_text()) for p in B.glob('summary_*.json') if p.name.startswith(('summary_initial_','summary_candidate','summary_revision'))]
 if phase=='shared':
  candidates=[s for s in summaries if s['label'].startswith('candidate') and s['revision']=='r0' and all(s[a]['n']==200 for a in ['A0','A1'])]
  fallback=not candidates
  if fallback:candidates=[s for s in summaries if s['label']=='initial_bm25_4k']
  if not candidates:raise StopRun('no_complete_candidate')
  comparison=json.loads((B/'retrieval_comparison.json').read_text())['rows'] if (B/'retrieval_comparison.json').exists() else []
  for s in candidates:s['selection_operand_HR']=next((r['operand_all_HR'] for r in comparison if r['method']==s['retriever'] and r['k']==s['k']),s['A1']['packed_operand_all_HR'])
  order={'bm25':0,'dense':1,'hybrid':2,'hybrid_rerank':3}
  candidates.sort(key=lambda s:(-sum(s[a]['NumMatch_1pct'] for a in ['A0','A1']),-(s['selection_operand_HR'] or 0),s['k'],order[s['retriever']]))
  best=candidates[0]
  config=dict(label=best['label'],method=best['retriever'],k=best['k'],context_per_slot=best['context_per_slot'],concurrency=best['concurrency'],selected_revisions={'A0':'r0','A1':'r0'},selected_labels={a:best['label'] for a in ['A0','A1']},shared_selection=[dict(label=s['label'],combined_correct=sum(round(s[a]['NumMatch_1pct']*200) for a in ['A0','A1']),packed_operand_HR=s['A1']['packed_operand_all_HR']) for s in candidates],initial_fallback=fallback,common_schema_revisions_per_arm=1,total_revisions_after_initial_per_arm=1,selected_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
  dump(B/'selected_config.json',config)
 else:
  config=json.loads((B/'selected_config.json').read_text());ss=[s for s in summaries if s['label']==config['label'] or (s['label'].startswith('revision') and s['retriever']==config['method'] and s['k']==config['k'] and s['context_per_slot']==config['context_per_slot'])]
  assert all(s[a]['n']==200 for s in ss for a in ['A0','A1'])
  for a in ['A0','A1']:
   best=min(ss,key=lambda s:(-s[a]['NumMatch_1pct'],-s[a]['NumMatch_strict'],s[a]['abstain'],s['revision']))
   config['selected_revisions'][a]=best['revision'];config['selected_labels'][a]=best['label']
  config['additional_revision_count_per_arm']=len({s['revision'] for s in ss})-1;config['total_revisions_after_initial_per_arm']=1+config['additional_revision_count_per_arm'];dump(B/'selected_config.json',config)
 config=json.loads((B/'selected_config.json').read_text());a1=readl(B/('scores_'+config['selected_labels']['A1']+'.jsonl'))
 dump(B/'ranking_selection_v2.json',rank_selection([s for s in a1 if s['arm']=='A1']))
 print(json.dumps(config))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['shared','revisions'],required=True);main(p.parse_args().phase)

