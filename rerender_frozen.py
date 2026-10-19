"""Recount frozen evidence with the selected prompt. Never generate answers."""
import os
from core import *
from scoring import distribution

def main():
 if (RUNS/'STOP.json').exists():raise StopRun('Existing stop')
 tokenrows=[];demos=readl(MAN/'demos_train.jsonl');out=RUNS/'frozen'
 with Client('secqa-stage1-final-token-preflight',float(os.environ['STAGE1_DEADLINE'])) as c:
  for name,arms in [('test',['A0','A1']),('financebench',['A1']),('oracle',['A1']),('contextdep',['A0'])]:
   for t in readl(out/(name+'_evidence.jsonl')):
    row=t['row'];e=t['evidence'];kind=name+'-'+row['probe']['kind'] if name=='financebench' else name
    tokenrows.append(dict(kind=kind,item_id=row['item_id'],tokens={a:len(c.tokens(c.render(messages(row['question'],e['chunks'],demos,a)))) for a in arms}))
   print(name,'rendered',flush=True)
 jsonl(out/'token_preflight.jsonl',tokenrows);summary={}
 for kind in sorted(set(r['kind'] for r in tokenrows)):
  summary[kind]={a:distribution([r['tokens'][a] for r in tokenrows if r['kind']==kind and a in r['tokens']]) for a in ['A0','A1']}
  summary[kind]['over_4096_with_650_output']=sum(any(v+650>4096 for v in r['tokens'].values()) for r in tokenrows if r['kind']==kind)
  summary[kind]['over_budget_by_arm']={a:sum(r['tokens'].get(a,0)+650>4096 for r in tokenrows if r['kind']==kind) for a in ['A0','A1']}
 summary.update(generation_requests=c.generation_n,server_requests=c.n,server_errors=c.errors,selected_revision=json.loads((RUNS/'revision_selection.json').read_text())['chosen'])
 dump(RUNS/'frozen_token_summary.json',summary);dump(RUNS/'frozen_evidence_hashes.json',{p.name:sha(p.read_bytes()) for p in sorted(out.glob('*.jsonl'))});print(json.dumps(summary),flush=True)
if __name__=='__main__':
 try:main()
 except StopRun as e:dump(RUNS/'STOP.json',dict(reason=str(e)));raise
