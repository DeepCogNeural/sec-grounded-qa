import collections,json,math,re,statistics
from core import *
from retrieval import hitrate

def extract_json(text):
 # JSON only: surrounding whitespace allowed, markdown fences and prose fail.
 try:return json.loads(text.strip())
 except (ValueError,AttributeError):return None

def program_logprob(response):
 ch=response['choices'][0];text=ch['message'].get('content') or '';m=re.search(r'"program"\s*:\s*"((?:[^"\\]|\\.)*)"',text)
 if not m or not m[1]:return None
 logs=(ch.get('logprobs') or {}).get('content') or [];offset=0;selected=[]
 for x in logs:
  token=x.get('token','');end=offset+len(token)
  if end>m.start(1) and offset<m.end(1) and math.isfinite(x.get('logprob',float('nan'))):selected.append(x['logprob'])
  offset=end
 return sum(selected)/len(selected) if selected else None

def score(result,row,evidence,join=None):
 response=result['response'];ch=response['choices'][0];obj=extract_json(ch['message'].get('content'));arm=result['arm'];truncated=ch['finish_reason']=='length'
 abstain=not truncated and isinstance(obj,dict) and obj.get('abstain') is True
 p=prediction(obj,arm) if not truncated else None
 g=gate(obj,evidence['chunks']) if arm=='A1' else None
 answered=p is not None and not abstain and not truncated
 valid_g=bool(answered and g and g['accept'])
 operands=obj.get('operands',[]) if isinstance(obj,dict) and isinstance(obj.get('operands',[]),list) else []
 return dict(item_id=row['item_id'],arm=arm,prediction=p,answered=answered,abstain=abstain,unparseable=not answered and not abstain and not truncated,truncated=truncated,NumMatch_1pct=bool(answered and match(p,row['gold'])),NumMatch_strict=bool(answered and match(p,row['gold'],True)),FinQA_agreement=finqa_agreement(p,join.get('qa.exe_ans'),join.get('prediction_percent_to_finqa_scale',.01)) if answered and join and join['join_status']!='unresolved' else False,finqa_eligible=bool(join and join['join_status']!='unresolved'),G=g,G_accept=valid_g,operand_count=len(operands),mean_program_token_logprob=program_logprob(response) if arm=='A1' else None,top1_bm25=evidence['top1_bm25'],retrieval=hitrate(evidence['chunks'],join),usage=response.get('usage'),finish_reason=ch['finish_reason'])
def distribution(v):
 v=sorted(v)
 if not v:return None
 def q(p):return v[round((len(v)-1)*p)]
 return dict(n=len(v),min=v[0],p05=q(.05),median=q(.5),p95=q(.95),max=v[-1],mean=sum(v)/len(v))
def summarize(rows):
 n=len(rows);accepted=[r for r in rows if r['G_accept']];quotes=[q for r in rows if r['G'] for q in r['G']['quotes']];hits=[r['retrieval'] for r in rows if r['retrieval'] is not None];fj=[r for r in rows if r['finqa_eligible']]
 return dict(n=n,NumMatch_1pct=sum(r['NumMatch_1pct'] for r in rows)/n,NumMatch_strict=sum(r['NumMatch_strict'] for r in rows)/n,FinQA_agreement=sum(r['FinQA_agreement'] for r in fj)/len(fj) if fj else None,finqa_n=len(fj),answered=sum(r['answered'] for r in rows),abstain=sum(r['abstain'] for r in rows),unparseable=sum(r['unparseable'] for r in rows),truncated=sum(r['truncated'] for r in rows),HR_at_5=sum(h['any_hit'] for h in hits)/len(hits) if hits else None,all_gold_HR_at_5=sum(h['all_hit'] for h in hits)/len(hits) if hits else None,verbatim_HR_at_5=sum(h['verbatim_any'] for h in hits)/len(hits) if hits else None,HR_denominator=len(hits),G_coverage=len(accepted)/n,G_precision=sum(r['NumMatch_1pct'] for r in accepted)/len(accepted) if accepted else None,G_accepted=len(accepted),G_failure_reasons=dict(collections.Counter(reason for r in rows if r['G'] for reason in r['G']['reasons'])),quote_fidelity=sum(quotes)/len(quotes) if quotes else None,operand_quotes=len(quotes),prompt_tokens=distribution([r['usage']['prompt_tokens'] for r in rows]),completion_tokens=distribution([r['usage']['completion_tokens'] for r in rows]))
def rank_selection(rows):
 eligible=[r for r in rows if r['answered']];out=[]
 for name in ['mean_program_token_logprob','top1_bm25','operand_count']:
  groups=collections.defaultdict(list)
  for r in eligible:groups[r[name] if r[name] is not None else -1e300].append(r)
  n=0;err=0.;risk_area=0.;curve=[]
  for value,rs in sorted(groups.items(),reverse=True):
   # Expected error under uniform random tie ordering, integrated over each rank.
   fraction_wrong=sum(not r['NumMatch_1pct'] for r in rs)/len(rs)
   for k in range(1,len(rs)+1):risk_area+=(err+k*fraction_wrong)/(n+k)
   n+=len(rs);err+=len(rs)*fraction_wrong;curve.append(dict(score=value,n=n,coverage=n/len(rows),risk=err/n))
  out.append(dict(name=name,AURC=risk_area/n if n else None,available=sum(r[name] is not None for r in eligible),curve=curve))
 valid=[r for r in out if r['AURC'] is not None and r['available']==len(eligible)]
 chosen=min(valid,key=lambda r:r['AURC'])['name'] if valid else 'top1_bm25'
 return dict(chosen=chosen,direction='descending',candidates=out,selection='minimum dev AURC among fully available candidates; equal AURC priority program logprob, BM25, operand count',tie_handling='equal scores form one threshold group; risk curves compare common coverage by fractional weighting within boundary group (expected uniform tie order), never item-id favorable ordering',eligible=len(eligible))

def curve_at_common_coverage(rows,ranking):
 """Fractional boundary-group weights give the expected uniform tie result."""
 n=len(rows);valid=[r for r in rows if r['answered']];gated=[r for r in valid if r['G_accept']]
 maxcov=min(len(valid),len(gated))/n if n else 0
 grid=sorted(set([j/20 for j in range(1,21) if j/20<=maxcov]+([maxcov] if maxcov else [])))
 def precision_at(pool,coverage):
  groups=collections.defaultdict(list)
  for r in pool:groups[r[ranking] if r[ranking] is not None else -1e300].append(r)
  need=coverage*n;correct=0.;den=0.
  for _,rs in sorted(groups.items(),reverse=True):
   take=min(len(rs),need-den)
   if take<=0:break
   correct+=take*sum(r['NumMatch_1pct'] for r in rs)/len(rs);den+=take
  return correct/den if den else None
 return [dict(coverage=c,A1_precision=precision_at(valid,c),A1_G_precision=precision_at(gated,c)) for c in grid]


def gated_summary(rows):
 """Report all three scorers for the offline arm without another generation."""
 n=len(rows);accepted=[r for r in rows if r['G_accept']];fj=[r for r in rows if r['finqa_eligible']]
 return dict(n=n,answered=len(accepted),coverage=len(accepted)/n if n else None,NumMatch_1pct=sum(r['NumMatch_1pct'] for r in accepted)/n if n else None,NumMatch_strict=sum(r['NumMatch_strict'] for r in accepted)/n if n else None,FinQA_agreement=sum(r['G_accept'] and r['FinQA_agreement'] for r in fj)/len(fj) if fj else None,precision=sum(r['NumMatch_1pct'] for r in accepted)/len(accepted) if accepted else None)
