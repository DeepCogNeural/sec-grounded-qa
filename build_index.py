import os,time,collections
from core import *
from retrieval import *
def main():
 if (RUNS/'STOP.json').exists():raise StopRun((RUNS/'STOP.json').read_text())
 start=time.time();rows=readl(MAN/'docfinqa_test.jsonl')+readl(MAN/'docfinqa_dev_sample.jsonl');groups=sorted(set(r['doc_group'] for r in rows));counts=[]
 with Client('secqa-stage1-index',float(os.environ['STAGE1_DEADLINE'])) as c:
  for i,g in enumerate(groups):
   chunks=build_group(g,(INDEX/'sources'/f'{g}.txt').read_text(),c);counts.append(dict(group=g,chunks=len(chunks),kind='docfinqa',tokens=[x['actual_tokens'] for x in chunks]))
   if i%10==0:print('docfinqa',i+1,'/',len(groups),flush=True)
  for i,d in enumerate(readl(MAN/'financebench_documents.jsonl')):
   pages=readl(INDEX/'financebench_pages'/f'{d["doc_name"]}.jsonl');chunks=build_group(d['doc_name'],'',c,pages)
   counts.append(dict(group=d['doc_name'],chunks=len(chunks),kind='financebench',tokens=[x['actual_tokens'] for x in chunks]));print('financebench',i+1,flush=True)
 jsonl(RUNS/'index_groups.jsonl',counts);lens=[t for r in counts for t in r['tokens']]
 dump(RUNS/'index_summary.json',dict(wall_seconds=time.time()-start,groups=len(counts),group_kinds=dict(collections.Counter(r['kind'] for r in counts)),chunks=len(lens),min_tokens=min(lens),max_tokens=max(lens),mean_tokens=sum(lens)/len(lens),window_tokens=450,stride=360,overlap=.2,tokenizer='running server /tokenize; every emitted chunk retokenized',retriever='bm25s.BM25 default lucene, k1=1.5, b=.75, english stopwords; no stemming',server_requests=c.n,server_errors=c.errors))
if __name__=='__main__':main()
