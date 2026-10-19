"""CPU-only fused score control on frozen supplied chunks; no answer generation."""
import os
os.environ['HF_HOME']=str(__import__('pathlib').Path('workspace') / './cache/huggingface')
os.environ['CUDA_VISIBLE_DEVICES']=''
import numpy as np,torch
from sentence_transformers import SentenceTransformer
from core import *
from retrieval_v2 import RetrieverV2

def main():
 torch.set_num_threads(4)
 dev=readl(RUNS/'stage1b/evidence_candidate2_bm25_k10.jsonl');test=readl(RUNS/'frozen_v2/test_evidence.jsonl');wh=readl(RUNS/'frozen_v2/withheld_evidence.jsonl')
 rows=dev+test;model=SentenceTransformer('BAAI/bge-base-en-v1.5',device='cpu');model.max_seq_length=512
 vec=model.encode(['Represent this sentence for searching relevant passages: '+t['row']['question'] for t in rows],normalize_embeddings=True,convert_to_numpy=True,batch_size=32,show_progress_bar=False)
 retr=RetrieverV2(dense=False);withheld={t['row']['source_item_id']:t for t in wh};out=[]
 for pos,t in enumerate(rows):
  r=t['row'];ranks,_,chunks=retr.ranks(r['doc_group'],r['question']);mat=np.load(INDEX/'dense_v2'/f"{r['doc_group']}.npy");sim=mat.astype(np.float32)@vec[pos];dr=np.lexsort((np.arange(len(sim)),-sim));rrf=np.zeros(len(chunks))
  for ranking in [ranks['bm25'],dr]:
   for k,i in enumerate(ranking):rrf[i]+=1/(61+k)
  by={c['chunk_id']:float(rrf[i]) for i,c in enumerate(chunks)}
  for record in [t]+([withheld[r['item_id']]] if r['item_id'] in withheld else []):
   values=[by[c['chunk_id']] for c in record['evidence']['chunks']]
   out.append(dict(item_id=record['row']['item_id'],top1_fused=max(values) if values else 0,source='max BM25+dense RRF(60) among actually supplied chunks',chunk_scores=[dict(chunk_id=c['chunk_id'],score=by[c['chunk_id']]) for c in record['evidence']['chunks']]))
  if pos%100==0:print('TAU',pos,flush=True)
 jsonl(RUNS/'frozen_v2/tau_scores.jsonl',out)
 print('DONE',len(out),flush=True)
if __name__=='__main__':main()
