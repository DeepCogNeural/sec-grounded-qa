import json,pathlib,re,time
import bm25s,numpy as np
from core import *
def words(s):return re.findall(r'[a-z]+|\d+(?:\.\d+)?',norm(s).lower())
def build_group(group,text,client,pages=None):
 target=INDEX/'bm25'/group
 if (target/'chunks.jsonl').exists():return readl(target/'chunks.jsonl')
 target.mkdir(parents=True,exist_ok=True)
 sections=[(None,text)] if pages is None else [(p['page'],p['text']) for p in pages]
 chunks=[]
 for page,section in sections:
  tok=client.call('/tokenize',dict(content=section,add_special=False,with_pieces=True))['tokens']
  for start in range(0,len(tok),360):
   ts=tok[start:start+450]
   raw=b''.join(t['piece'].encode() if isinstance(t['piece'],str) else bytes(t['piece']) for t in ts)
   chunk=raw.decode('utf-8',errors='replace')
   actual=len(client.tokens(chunk))
   years=sorted(set(re.findall(r'\b(?:19|20)\d\d\b',chunk)))
   header=f'[doc {group[:12]} chunk {len(chunks)}'+(f' page {page}' if page is not None else '')+('; years '+','.join(years) if years else '')+']'
   chunks.append(dict(chunk_id=f'{group}:{len(chunks)}',text=chunk,header=header,page=page,token_start=start,token_end=start+len(ts),actual_tokens=actual))
   if start+450>=len(tok):break
 if not chunks:raise ValueError('empty_document '+group)
 corpus=bm25s.tokenize([c['text'] for c in chunks],stopwords='en',show_progress=False)
 model=bm25s.BM25();model.index(corpus,show_progress=False);model.save(str(target),corpus=None)
 jsonl(target/'chunks.jsonl',chunks)
 return chunks
class Retriever:
 def __init__(self,client):self.client=client;self.cache={}
 def get(self,group,question):
  if group not in self.cache:
   p=INDEX/'bm25'/group
   self.cache[group]=(bm25s.BM25.load(str(p),load_corpus=False),readl(p/'chunks.jsonl'))
  model,chunks=self.cache[group]
  qt=bm25s.tokenize([question],stopwords='en',show_progress=False)
  ids,scores=model.retrieve(qt,k=min(5,len(chunks)),show_progress=False)
  ordered=sorted(zip(ids[0].tolist(),scores[0].tolist()),key=lambda x:(-x[1],x[0]))
  packed=[];dropped=[]
  for idx,score in ordered:
   c=dict(chunks[idx],bm25_score=float(score))
   txt='\n\n'.join(x['header']+'\n'+x['text'] for x in packed+[c])
   if len(self.client.tokens(txt))<=2600:packed.append(c)
   else:dropped.append(c['chunk_id'])
  return dict(chunks=packed,dropped=dropped,top1_bm25=float(ordered[0][1]),evidence_tokens=len(self.client.tokens('\n\n'.join(x['header']+'\n'+x['text'] for x in packed))))
def hitrate(chunks,join):
 if not join or join['join_status']=='unresolved':return None
 snippets=list((join.get('qa.gold_inds') or {}).values())
 if not snippets:return None
 hits=[];verbatim=[]
 for s in snippets:
  sw=set(words(s));nums={w for w in sw if re.fullmatch(r'\d+(?:\.\d+)?',w)}
  hit=False
  for c in chunks:
   cw=set(words(c['text']))
   if sw and len(sw&cw)/len(sw)>=.8 and nums<=cw:hit=True
  hits.append(hit);verbatim.append(any(norm(s).lower() in norm(c['text']).lower() for c in chunks))
 return dict(any_hit=any(hits),all_hit=all(hits),snippet_hits=hits,verbatim_any=any(verbatim))
