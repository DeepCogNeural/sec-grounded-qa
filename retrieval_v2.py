"""Per-document dense and lexical retrieval, no generation."""
import os,time,collections,ast,bisect
for key,folder in [('HF_HOME','huggingface'),('TORCH_HOME','torch'),('CUDA_CACHE_PATH','cuda'),('XDG_CACHE_HOME','xdg')]:
 os.environ[key]=str(__import__('pathlib').Path('workspace') / './cache'/folder)
import numpy as np,bm25s
from core import *
from retrieval import build_group,hitrate
B=RUNS/'stage1b';DEADLINE=1792367100

def operands(join):
 # Explicit const_* and intermediate #* are not document operands.
 vals=[]
 calls=re.findall(r'(\w+)\(\s*([^,]+),\s*([^\)]+)\)',join.get('qa.program') or '')
 clean=lambda x:re.sub(r'[^a-z0-9]','',norm(x).lower())
 for op,a,b in calls:
  if op.startswith('table_'):
   table=join.get('table') or []
   rows=[row for row in table[1:] if clean(row[0])==clean(a)]
   if not rows and sum(c[0].startswith('table_') for c in calls)==1:
    indices=[int(key.split('_')[1]) for key in (join.get('qa.gold_inds') or {}) if re.fullmatch(r'table_\d+',key)]
    rows=[table[i] for i in indices if i<len(table)]
   if not rows:return []
   nums=[]
   for row in rows:
    for cell in row[1:]:
     parsed=parse(cell)
     if parsed and not parsed['is_yes_no']:nums.append(parsed['value'])
     else:
      repeated=numeric_values(cell)
      if len(repeated)>1:return []
      if repeated:nums.append(next(iter(repeated)))
   if not nums:return []
   vals.extend(nums)
   continue
  for t in [a,b]:
   t=t.strip()
   if t.startswith(('const_','#')):continue
   p=parse(t)
   if p and not p['is_yes_no']:vals.append(p['value'])
 return sorted(set(vals))
VALUE_SCAN=re.compile(r'(?<![\w.])[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?(?=$|[^\w]|(?:million|billion|thousand|percent|mn|bn|k|m|b)\b)',re.I)
def numeric_values(text):
 return {abs(float(m[0])) for m in VALUE_SCAN.finditer(norm(text))}
def scales(v):return {abs(v*f) for f in [1,.01,100,.001,1000,.000001,1000000]}
def approx_present(nums,variants):
 ordered=sorted(nums)
 for v in variants:
  i=bisect.bisect_left(ordered,v)
  if any(math.isclose(n,v,rel_tol=1e-9,abs_tol=1e-9) for n in ordered[max(0,i-1):i+1]):return True
 return False
def operand_hit(chunks,join,scaled=True):
 vals=operands(join)
 if not vals:return None
 nums=numeric_values(' '.join(c['text'] for c in chunks))
 hits=[approx_present(nums,scales(v) if scaled else {abs(v)}) for v in vals]
 return dict(all_hit=all(hits),any_hit=any(hits),hits=hits,values=vals)
class RetrieverV2:
 def __init__(self,client=None,dense=True,rerank=False):
  self.client=client;self.cache={};self.encoder=None;self.reranker=None
  if dense:
   import torch
   from sentence_transformers import SentenceTransformer
   torch.set_num_threads(8)
   self.encoder=SentenceTransformer('BAAI/bge-base-en-v1.5',device='cuda',model_kwargs={'torch_dtype':torch.float16});self.encoder.max_seq_length=512
  if rerank:
   import torch
   from sentence_transformers import CrossEncoder
   self.reranker=CrossEncoder('BAAI/bge-reranker-base',device='cuda',max_length=512,model_kwargs={'torch_dtype':torch.float16})
 def group(self,g):
  if g not in self.cache:
   p=INDEX/'bm25'/g
   self.cache[g]=(bm25s.BM25.load(str(p),load_corpus=False),readl(p/'chunks.jsonl'))
  return self.cache[g]
 def ranks(self,g,q,rerank=True):
  model,chunks=self.group(g);qt=bm25s.tokenize([q],stopwords='en',show_progress=False);ids,ss=model.retrieve(qt,k=len(chunks),show_progress=False)
  bm=sorted(zip(ids[0].tolist(),ss[0].tolist()),key=lambda z:(-z[1],z[0]));out={'bm25':[z[0] for z in bm]};scores={i:float(s) for i,s in bm}
  if self.encoder:
   vec=self.encoder.encode(['Represent this sentence for searching relevant passages: '+q],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0]
   mat=np.load(INDEX/'dense_v2'/f'{g}.npy');ds=mat.astype(np.float32)@vec.astype(np.float32);dense=np.lexsort((np.arange(len(ds)),-ds)).tolist();out['dense']=dense
   rrf=np.zeros(len(chunks),dtype=np.float64)
   for ranking in [out['bm25'],dense]:
    for rank,i in enumerate(ranking):rrf[i]+=1/(60+rank+1)
   hybrid=np.lexsort((np.arange(len(rrf)),-rrf)).tolist();out['hybrid']=hybrid
   if self.reranker and rerank:
    top=hybrid[:30];rr=self.reranker.predict([(q,chunks[i]['text']) for i in top],batch_size=16,show_progress_bar=False);out['hybrid_rerank']=[i for i,s in sorted(zip(top,rr),key=lambda z:(-float(z[1]),z[0]))]+hybrid[30:]
  return out,scores,chunks
 def evidence(self,g,q,method,k,budget=5700,ranked=None):
  ranks,scores,chunks=ranked or self.ranks(g,q);chosen=ranks[method][:k];packed=[];dropped=[]
  for i in chosen:
   c=dict(chunks[i],bm25_score=scores[i]);text='\n\n'.join(x['header']+'\n'+x['text'] for x in packed+[c])
   count=len(self.client.tokens(text)) if self.client else sum(x['actual_tokens']+45 for x in packed+[c])
   if count<=budget:packed.append(c)
   else:dropped.append(c['chunk_id'])
  return dict(chunks=packed,dropped=dropped,top1_bm25=max(scores.values()),evidence_tokens=len(self.client.tokens('\n\n'.join(c['header']+'\n'+c['text'] for c in packed))) if self.client else None,retriever=method,k=k)

def build():
 start=time.time();client=Client('stage1b-index',DEADLINE);rows=readl(MAN/'docfinqa_test.jsonl')+readl(MAN/'docfinqa_dev_sample.jsonl')+readl(MAN/'docfinqa_dev2.jsonl');groups=sorted(set(r['doc_group'] for r in rows));counts=[]
 for i,g in enumerate(groups):
  chunks=build_group(g,(INDEX/'sources'/f'{g}.txt').read_text(),client);counts.append(dict(group=g,chunks=len(chunks)))
  if i%20==0:print('BM25',i+1,len(groups),flush=True)
 dump(B/'index_v2_summary.json',dict(groups=len(groups),chunks=sum(x['chunks'] for x in counts),groups_detail=counts,bm25_seconds=time.time()-start,generation_requests=client.generation_n))
 retr=RetrieverV2();target=INDEX/'dense_v2';target.mkdir(exist_ok=True);total=0
 for i,g in enumerate(groups):
  client.guard();p=target/f'{g}.npy';chunks=readl(INDEX/'bm25'/g/'chunks.jsonl')
  if not p.exists():
   vec=retr.encoder.encode([c['text'] for c in chunks],batch_size=48,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False);np.save(p,vec.astype(np.float16))
  total+=len(chunks)
  if i%10==0:print('DENSE',i+1,len(groups),total,round(time.time()-start),flush=True)
 dump(B/'dense_index_summary.json',dict(groups=len(groups),chunks=total,model='BAAI/bge-base-en-v1.5',max_seq_length=512,dtype='float16',normalization='L2',device='cuda',wall_seconds=time.time()-start,generation_requests=client.generation_n))

def measure():
 rows=readl(MAN/'docfinqa_dev2.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')};client=Client('stage1b-retrieval',DEADLINE)
 try:retr=RetrieverV2(client,rerank=True);rerank_error=None
 except Exception as exc:
  dump(B/'reranker_load_error.json',dict(error=repr(exc)));retr=RetrieverV2(client,rerank=False);rerank_error=repr(exc)
 metrics=[];evidence={};start=time.time()
 for pos,r in enumerate(rows):
  client.guard();ranked=retr.ranks(r['doc_group'],r['question']);rankings,ss,ch=ranked
  for method,rank in rankings.items():
   for k in [5,10]:
    selected=[ch[i] for i in rank[:k]];j=joins[r['item_id']];h=operand_hit(selected,j);literal=operand_hit(selected,j,False);snip=hitrate(selected,j)
    metrics.append(dict(item_id=r['item_id'],method=method,k=k,operand=h,literal=literal,snippet=snip))
    e=retr.evidence(r['doc_group'],r['question'],method,k,ranked=ranked);evidence.setdefault(f'{method}_k{k}',[]).append(dict(row=r,evidence=e))
  if pos%20==0:print('RETRIEVAL',pos+1,round(time.time()-start),flush=True)
 jsonl(B/'retrieval_metrics.jsonl',metrics);summary=[]
 for key,ev in evidence.items():
  method,k=key.rsplit('_k',1);m=[z for z in metrics if z['method']==method and z['k']==int(k)];op=[z['operand'] for z in m if z['operand']];lit=[z['literal'] for z in m if z['literal']];snip=[z['snippet'] for z in m if z['snippet']]
  summary.append(dict(method=method,k=int(k),n=len(m),operand_n=len(op),operand_all_HR=sum(z['all_hit'] for z in op)/len(op) if op else None,operand_any_HR=sum(z['any_hit'] for z in op)/len(op) if op else None,literal_all_HR=sum(z['all_hit'] for z in lit)/len(lit) if lit else None,snippet_any_HR=sum(z['any_hit'] for z in snip)/len(snip) if snip else None,snippet_all_HR=sum(z['all_hit'] for z in snip)/len(snip) if snip else None))
  jsonl(B/f'dev2_evidence_{key}.jsonl',ev)
 dump(B/'retrieval_comparison.json',dict(rows=summary,wall_seconds=time.time()-start,rerank_error=rerank_error,generation_requests=0))
 order={'bm25':0,'dense':1,'hybrid':2,'hybrid_rerank':3};ranked=sorted(summary,key=lambda z:(-(z['operand_all_HR'] or 0),-(z['snippet_all_HR'] or 0),z['k'],order[z['method']]))
 dump(B/'shared_candidates.json',dict(candidates=ranked[:2],selection_rules_sha256=sha((B/'selection_rules_v2.json').read_bytes())));print(json.dumps(ranked[:2]),flush=True)
if __name__=='__main__':
 import sys
 with Client('secqa-stage1b-retrieval-'+sys.argv[1],DEADLINE) as owner:
  assert owner.owns and (ROOT/'gpu.claim').exists()
  if sys.argv[1]=='build':build()
  elif sys.argv[1]=='measure':measure()
