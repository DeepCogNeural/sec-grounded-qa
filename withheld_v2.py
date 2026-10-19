"""Evidence-withheld construction; never generates an answer."""
import argparse,random,time
import numpy as np
from core import *
from retrieval_v2 import RetrieverV2,operands,numeric_values,scales,approx_present,B,DEADLINE
from qa_v2 import pack_shared
def derived_check(chunks,gold,question):
 # Conservative numeric presence, then an explicit finite arithmetic search.
 # This cannot establish absence of every possible semantic derivation.
 nums=sorted(numeric_values(question+' '+' '.join(c['header']+' '+c['text'] for c in chunks)))
 targets=sorted(scales(gold['value']))
 if approx_present(nums,targets):return dict(pass_check=False,reason='gold_or_scaled_gold_present',numeric_count=len(nums))
 a=np.asarray(nums,dtype=np.float64)
 if not len(a):return dict(pass_check=True,reason='no_numeric_tokens',numeric_count=0,checked='single-value scaling and pairwise arithmetic')
 # abs sign is conservative. Include subtraction in both directions implicitly.
 x=a[:,None];y=a[None,:]
 with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
  for name,arr in [('sum',x+y),('difference',np.abs(x-y)),('product',x*y),('ratio',x/y)]:
   for target in targets:
    z=np.isclose(np.abs(arr),target,rtol=1e-9,atol=1e-9)&np.isfinite(arr)
    if np.any(z):
     i,j=np.argwhere(z)[0];return dict(pass_check=False,reason='pairwise_'+name,numbers=[nums[i],nums[j]],target=target,numeric_count=len(nums))
 return dict(pass_check=True,reason='no_match_in_finite_arithmetic_check',numeric_count=len(nums),checked='single values with 1e-6,1e-3,1e-2,1,1e2,1e3,1e6 scaling; pair +,-,*,/ with those target scales',limitation='Does not prove absence of arbitrary multi-step or semantic derivations.')
def main(args):
 rows=readl(MAN/'docfinqa_test.jsonl');joins={j['item_id']:j for j in readl(MAN/'finqa_join.jsonl')};random.Random(SEED).shuffle(rows)
 demos=readl(MAN/'demos_train.jsonl');checks=[];out=[];start=time.time()
 with Client('secqa-stage1b-withheld-no-generation',DEADLINE-180) as c:
  retr=RetrieverV2(c,dense=args.method!='bm25',rerank=args.method=='hybrid_rerank')
  ctx=c.call('/props')['default_generation_settings']['n_ctx']
  for row in rows:
   c.guard();j=joins[row['item_id']];vals=operands(j);gold=row['gold']
   v=dict(item_id=row['item_id'],join_status=j['join_status'],operands=vals)
   if j['join_status']=='unresolved' or not vals or not gold or gold['is_yes_no'] or gold['value']==0:
    v.update(valid=False,reason='unresolved_no_operands_or_nonzero_numeric_gold_missing');checks.append(v);continue
   bans=set().union(*(scales(value) for value in vals))
   question_absence=not approx_present(numeric_values(row['question']),bans)
   v['question_operand_absence']=question_absence
   if not question_absence:
    v.update(valid=False,reason='gold_operand_or_scaled_variant_in_question');checks.append(v);continue
   ranks,scores,chunks=retr.ranks(row['doc_group'],row['question'])
   allowed=[];excluded=[]
   for i in ranks[args.method]:
    nums=numeric_values(chunks[i]['header']+' '+chunks[i]['text'])
    if approx_present(nums,bans):excluded.append(chunks[i]['chunk_id'])
    else:allowed.append(i)
   e=dict(chunks=[dict(chunks[i],bm25_score=scores[i]) for i in allowed[:args.k]],dropped=[],top1_bm25=max(scores.values()),retriever=args.method,k=args.k)
   e=pack_shared(c,row,e,demos,ctx)
   supplied='\n\n'.join(ch['header']+'\n'+ch['text'] for ch in e['chunks'])
   absence=not approx_present(numeric_values(supplied),bans);deriv=derived_check(e['chunks'],gold,row['question'])
   # Require nonempty evidence and at least one non-period number; avoids vacuous text-only controls.
   nums=numeric_values(' '.join(ch['text'] for ch in e['chunks']));has_financial_number=any(n<1900 or n>2099 for n in nums)
   parts=j['filename'].split('/');company=parts[0];year=int(parts[1]);baseline=trivial(company,sorted(set(int(y) for y in re.findall(r'(?<!\d)((?:19|20)\d\d)(?!\d)',row['question']))),dict(company=company,doc_period=year,doc_type='10k'))
   valid=bool(e['chunks']) and absence and deriv['pass_check'] and has_financial_number
   v.update(valid=valid,reason='accepted' if valid else 'numeric_derivation_or_empty_or_no_nonperiod_numbers',banned_variants=sorted(bans),excluded_chunk_count=len(excluded),all_excluded_chunk_ids=excluded,selected_chunk_ids=[ch['chunk_id'] for ch in e['chunks']],gold_operand_absence=absence,gold_derivation_check=deriv,evidence_sha256=sha(supplied),gold=gold,has_nonperiod_number=has_financial_number,trivial_filter=baseline)
   checks.append(v)
   if valid:
    r=dict(row,source_item_id=row['item_id'],item_id='withheld-'+row['item_id'],source_gold=gold,gold=None,answer_raw=None,probe=dict(kind='withheld',gold='abstain',validation=v,trivial_filter=v['trivial_filter']))
    out.append(dict(row=r,evidence=e))
   if len(checks)%25==0:
    jsonl(B/'withheld_candidate_checks.jsonl',checks);jsonl(MAN/'withheld_evidence_probes.jsonl',out)
    print('WITHHELD',len(checks),len(out),round(time.time()-start),flush=True)
   if len(out)>=150:break
  assert c.generation_n==0
 jsonl(B/'withheld_candidate_checks.jsonl',checks);jsonl(MAN/'withheld_evidence_probes.jsonl',out)
 dump(B/'withheld_summary.json',dict(validated=len(out),target=150,candidates_checked=len(checks),trivial_pass=sum(not x['row']['probe']['trivial_filter']['refuse'] for x in out),seed=SEED,method=args.method,k=args.k,context_per_slot=ctx,manifest_sha256=sha((MAN/'withheld_evidence_probes.jsonl').read_bytes()),generation_requests=0,wall_seconds=time.time()-start,scope='Synthetic omission of all chunks containing any program operand value, including scaled equivalents. Question operands are excluded; finite derivability checks include question numbers. Arbitrary derivability is not certified.',same_company_different_period_dropped=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--method',required=True);p.add_argument('--k',type=int,required=True);main(p.parse_args())

