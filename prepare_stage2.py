"""Freeze evidence and render prompts. No completion endpoint is called."""
import os,random,time
from core import *
from retrieval import *
from scoring import distribution

def main():
 if (RUNS/'STOP.json').exists():raise StopRun((RUNS/'STOP.json').read_text())
 out=RUNS/'frozen';out.mkdir(exist_ok=True)
 demos=readl(MAN/'demos_train.jsonl');tokenrows=[]
 with Client('secqa-stage1-freeze-evidence',float(os.environ['STAGE1_DEADLINE'])) as c:
  retr=Retriever(c);rows=[]
  for i,row in enumerate(readl(MAN/'docfinqa_test.jsonl')):
   e=retr.get(row['doc_group'],row['question']);rows.append(dict(row=row,evidence=e))
   tokenrows.append(dict(kind='test',item_id=row['item_id'],tokens={a:len(c.tokens(c.render(messages(row['question'],e['chunks'],demos,a)))) for a in ['A0','A1']}))
   if i%100==0:print('test evidence',i+1,flush=True)
  jsonl(out/'test_evidence.jsonl',rows)
  qs={q['financebench_id']:q for q in readl(DATA/'financebench/data/financebench_open_source.jsonl')};numeric=set(json.loads((MAN/'financebench_numeric_ids.json').read_text())['ids']);fb=[]
  probes=readl(MAN/'financebench_probes.jsonl')
  for kind in ['answerable','hard','easy']:
   for p in probes:
    if p['kind']!=kind or (kind=='answerable' and p['financebench_id'] not in numeric):continue
    q=qs[p['financebench_id']];e=retr.get(p['replacement_doc'],p['question']);gold=parse(q['answer']) if kind=='answerable' else None
    row=dict(item_id=p['probe_id'],doc_group=p['replacement_doc'],question=p['question'],gold=gold,answer_raw=q['answer'] if kind=='answerable' else None,probe=p)
    goldpages=[int(z['evidence_page_num']) for z in q['evidence']]
    row['evidence_page_hit']=any(ch['page'] in goldpages for ch in e['chunks']) if kind=='answerable' else None
    fb.append(dict(row=row,evidence=e));tokenrows.append(dict(kind='financebench-'+kind,item_id=row['item_id'],tokens={'A1':len(c.tokens(c.render(messages(row['question'],e['chunks'],demos,'A1'))))}))
  jsonl(out/'financebench_evidence.jsonl',fb)
  oracle=[]
  for i,j in enumerate(readl(MAN/'oracle_200.jsonl')):
   text='\n'.join(j['pre_text'])+'\n'+'\n'.join(' | '.join(r) for r in j['table'])+'\n'+'\n'.join(j['post_text'])
   group='oracle-'+j['item_id'];build_group(group,text,c);e=retr.get(group,j['question']);oracle.append(dict(row=j,evidence=e))
   tokenrows.append(dict(kind='oracle',item_id=j['item_id'],tokens={'A1':len(c.tokens(c.render(messages(j['question'],e['chunks'],demos,'A1'))))}))
   if i%25==0:print('oracle evidence',i+1,flush=True)
  jsonl(out/'oracle_evidence.jsonl',oracle)
  context=[]
  for r in readl(MAN/'contextdep_200.jsonl'):
   e=dict(chunks=[],dropped=[],top1_bm25=0.,evidence_tokens=0);context.append(dict(row=r,evidence=e))
   tokenrows.append(dict(kind='contextdep',item_id=r['item_id'],tokens={'A0':len(c.tokens(c.render(messages(r['question'],[],demos,'A0'))))}))
  jsonl(out/'contextdep_evidence.jsonl',context)
 jsonl(out/'token_preflight.jsonl',tokenrows)
 summary={}
 for kind in sorted(set(r['kind'] for r in tokenrows)):
  summary[kind]={a:distribution([r['tokens'][a] for r in tokenrows if r['kind']==kind and a in r['tokens']]) for a in ['A0','A1']}
  summary[kind]['over_4096_with_650_output']=sum(any(v+650>4096 for v in r['tokens'].values()) for r in tokenrows if r['kind']==kind)
 summary['generation_requests']=c.generation_n;summary['server_requests']=c.n;summary['server_errors']=c.errors;dump(RUNS/'frozen_token_summary.json',summary)
 files=sorted(out.glob('*.jsonl'));dump(RUNS/'frozen_evidence_hashes.json',{p.name:sha(p.read_bytes()) for p in files})
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
