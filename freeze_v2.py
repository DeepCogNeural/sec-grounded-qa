"""Freeze all stage-2 evidence using selected development settings; no generation."""
import argparse,time
from core import *
from qa_v2 import *
from retrieval_v2 import RetrieverV2
from scoring import distribution
def main(args):
 config=json.loads((B/'selected_config.json').read_text());method=config['method'];k=config['k'];out=RUNS/'frozen_v2';out.mkdir(exist_ok=True);demos=readl(MAN/'demos_train.jsonl');tokenrows=[];start=time.time()
 with Client('secqa-stage1b-freeze-no-generation',DEADLINE-120) as c:
  props=c.call('/props');ctx=props['default_generation_settings']['n_ctx'];assert ctx==config['context_per_slot']
  retr=RetrieverV2(c,dense=method!='bm25',rerank=method=='hybrid_rerank');lexical=RetrieverV2(c,dense=False)
  def record(kind,t):
   row=t['row'];e=pack_shared(c,row,t['evidence'],demos,ctx);t=dict(row=row,evidence=e)
   counts={a:len(c.tokens(c.render(messages_v2(row['question'],e['chunks'],demos,a,config['selected_revisions'][a])))) for a in ['A0','A1']}
   tokenrows.append(dict(kind=kind,item_id=row['item_id'],tokens=counts,output_reserve=MAX_TOKENS,over_budget=any(n+MAX_TOKENS>ctx for n in counts.values()),chunks=len(e['chunks']),dropped=len(e.get('dropped',[]))))
   return t
  test=[]
  for i,r in enumerate(readl(MAN/'docfinqa_test.jsonl')):
   c.guard();e=retr.evidence(r['doc_group'],r['question'],method,k);test.append(record('test',dict(row=r,evidence=e)))
   if (i+1)%100==0:print('FREEZE test',i+1,round(time.time()-start),flush=True)
  jsonl(out/'test_evidence.jsonl',test)
  withheld=[record('withheld',t) for t in readl(MAN/'withheld_evidence_probes.jsonl')]
  jsonl(out/'withheld_evidence.jsonl',withheld)
  fb=[]
  # FinanceBench remains the frozen, untuned lexical control; no dense index outside permitted DocFinQA groups.
  for t in readl(RUNS/'frozen/financebench_evidence.jsonl'):
   if t['row']['probe']['kind'] not in ['answerable','easy']:continue
   fb.append(record('financebench-'+t['row']['probe']['kind'],t))
  jsonl(out/'financebench_evidence.jsonl',fb)
  oracle=[]
  for r in readl(MAN/'oracle_200.jsonl'):
   e=lexical.evidence('oracle-'+r['item_id'],r['question'],'bm25',k)
   oracle.append(record('oracle',dict(row=r,evidence=e)))
  jsonl(out/'oracle_evidence.jsonl',oracle)
  context=[record('contextdep',dict(row=r,evidence=dict(chunks=[],dropped=[],top1_bm25=0.,evidence_tokens=0))) for r in readl(MAN/'contextdep_200.jsonl')]
  jsonl(out/'contextdep_evidence.jsonl',context)
  assert c.generation_n==0
 jsonl(out/'token_preflight.jsonl',tokenrows)
 summary={kind:{'n':sum(t['kind']==kind for t in tokenrows),'tokens':{a:distribution([t['tokens'][a] for t in tokenrows if t['kind']==kind]) for a in ['A0','A1']},'over_budget':sum(t['over_budget'] for t in tokenrows if t['kind']==kind)} for kind in sorted({t['kind'] for t in tokenrows})}
 dump(B/'frozen_summary_v2.json',dict(sets=summary,generation_requests=0,context_per_slot=ctx,wall_seconds=time.time()-start,evidence_hashes={p.name:sha(p.read_bytes()) for p in sorted(out.glob('*.jsonl'))},financebench_retrieval='Frozen stage-1 BM25 top-5, repacked to shared schema budget; no tuning or generations',oracle_retrieval='BM25 over FinQA supplied gold-page text only'))
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main(None)

