"""Score existing dev outputs with the final frozen primitives; never generate."""
from core import *
from scoring import *
def main():
 rows={r['item_id']:r for r in readl(MAN/'docfinqa_dev_sample.jsonl')};ev={r['item_id']:r for r in readl(RUNS/'dev_evidence.jsonl')};joins={r['item_id']:r for r in readl(MAN/'finqa_dev_join.jsonl')};raw=readl(RUNS/'dev_answers_r0.jsonl');scored=[score(r,rows[r['item_id']],ev[r['item_id']],joins.get(r['item_id'])) for r in raw]
 assert len(raw)==200 and len({(r['item_id'],r['arm']) for r in raw})==200
 jsonl(RUNS/'dev_scores_r0.jsonl',scored);summary=json.loads((RUNS/'dev_summary_r0.json').read_text())
 for a in ['A0','A1']:summary[a]=summarize([r for r in scored if r['arm']==a])
 dump(RUNS/'dev_summary_r0.json',summary);dump(RUNS/'ranking_selection.json',rank_selection([r for r in scored if r['arm']=='A1']))
 for f in ['docfinqa_test.jsonl','docfinqa_dev_sample.jsonl']:
  for r in readl(MAN/f):assert parse(r['answer_raw'])==r['gold'],(f,r['item_id'])
 qs=readl(DATA/'financebench/data/financebench_open_source.jsonl');ids=[q['financebench_id'] for q in qs if parse(q['answer']) and not parse(q['answer'])['is_yes_no']]
 assert ids==json.loads((MAN/'financebench_numeric_ids.json').read_text())['ids']
 dump(RUNS/'final_parser_consistency.json',dict(docfinqa_test=922,dev=100,financebench_numeric=len(ids),consistent=True))
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
