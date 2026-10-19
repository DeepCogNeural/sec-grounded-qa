"""Frozen headline analysis. CPU only; consumes saved outputs, never generates."""
import argparse,ast,collections,math
import numpy as np
from core import *
from scoring import score,extract_json,summarize,gated_summary
from retrieval_v2 import operands
from schema_check import valid_schema
from qa_v2 import schema

SCALES=(1,.01,100,.001,1000,.000001,1000000)
READING=('unit_scale_sign','wrong_operand','wrong_arithmetic','other')
def numbers(text):return [float(m[0]) for m in NUMBER_SCAN.finditer(norm(text))]
def value_match(v,w,scaled=True):
 return any(abs(v-w*f)<=max(.005 if w==0 else 0,.01*abs(w*f)) for f in (SCALES if scaled else (1,)))
def present(v,vs):return any(value_match(v,w) for w in vs)
def gold_operands(join):
 if not join:return []
 vals=operands(join);goldnums=numbers(' '.join((join.get('qa.gold_inds') or {}).values()))
 return [v for v in vals if present(v,goldnums)]
def retrieved(chunks,vals):
 if not vals:return None
 nums=numbers(' '.join(c.get('header','')+' '+c['text'] for c in chunks))
 return all(present(v,nums) for v in vals)
def self_diagnostic(obj,gold,correct,operand_ok):
 if not isinstance(obj,dict) or type(obj.get('self_answer')) not in (int,float) or not math.isfinite(obj['self_answer']) or obj.get('abstain'):return dict(available=False)
 v=obj['self_answer'];p=parse(v)
 if obj.get('answer_type')=='percent':p['is_percent']=True
 if obj.get('answer_type')=='yes_no':p=parse('yes' if v==1 else 'no') if v in (0,1) else None
 own=match(p,gold)
 return dict(available=True,self_correct=own,executed_correct=correct,operand_set_correct=operand_ok,arithmetic_corrected=bool(operand_ok and correct and not own),arithmetic_harmed=bool(operand_ok and own and not correct),self_vs_execution='both_correct' if own and correct else 'execution_only' if correct else 'self_only' if own else 'both_wrong')
def categorize(result,row,evidence,join,system=None,allow_missing_self=False):
 s=result['score'];arm=result['arm'];system=system or arm;obj=extract_json(result['response']['choices'][0]['message'].get('content'));vals=gold_operands(join);hit=retrieved(evidence['chunks'],vals)
 sch=schema(arm)
 # Historical dev outputs predate the optional field; all other schema rules remain checked.
 if allow_missing_self and arm=='A1' and isinstance(obj,dict) and 'self_answer' not in obj:
  sch['properties'].pop('self_answer',None);sch['required']=[k for k in sch['required'] if k!='self_answer']
 invalid=not valid_schema(obj,sch) or s['truncated'] or s['unparseable']
 declared=[o['value'] for o in obj['operands'] if isinstance(o,dict) and type(o.get('value')) in (int,float)] if isinstance(obj,dict) and isinstance(obj.get('operands'),list) else []
 used=[]
 if arm=='A1' and isinstance(obj,dict) and not invalid and not s['abstain']:
  names={n.id for n in ast.walk(ast.parse(obj['program'],mode='eval')) if isinstance(n,ast.Name)}
  used=[o['value'] for o in obj['operands'] if o['name'] in names]
 operand_ok=bool(vals) and all(present(v,vals) for v in used) and all(present(v,declared) for v in vals)
 accepted=s['answered'] and (system!='A1+G' or s['G_accept']);correct=bool(accepted and s['NumMatch_1pct'])
 category='correct';sub=None
 if invalid:category='format'
 elif s['abstain'] or (system=='A1+G' and not s['G_accept']):
  category='abstain_filtered';sub='2a_justified' if hit is False else '2b_unjustified' if hit is True else '2_unknown'
 elif not correct:
  if hit is False:category='retrieval_miss'
  elif not vals or not row.get('gold') or row['gold']['is_yes_no'] or not s['prediction'] or s['prediction']['is_yes_no']:category='other'
  else:
   p=s['prediction'];g=row['gold'];pv=p['value'];gv=g['value']
   slip=(value_match(pv,-gv,False) or any(value_match(abs(pv),abs(gv)*f,False) for f in (10,100,1000,1000000,.1,.01,.001,.000001)))
   if slip:category='unit_scale_sign'
   elif arm=='A1':category='wrong_arithmetic' if operand_ok else 'wrong_operand'
   else:
    reasoning=numbers(obj.get('reasoning',''))
    if any(not present(v,vals) for v in reasoning):category='wrong_operand'
    elif all(present(v,reasoning) for v in vals):category='wrong_arithmetic'
    elif 'reasoning' not in obj and any(value_match(pv,v) and not present(v,vals) for v in numbers(' '.join(c['text'] for c in evidence['chunks']))):category='wrong_operand'
    else:category='other'
 return dict(item_id=row['item_id'],arm=system,doc_group=row['doc_group'],category=category,abstain_split=sub,gold_operands=vals,declared_operands=declared if arm=='A1' else None,executed_operands=used if arm=='A1' else None,operand_set_correct=operand_ok if arm=='A1' else None,operands_retrieved=hit,correct=correct,accepted=bool(accepted),G_reasons=(s.get('G') or {}).get('reasons',[]),self_answer=self_diagnostic(obj,row.get('gold'),s['NumMatch_1pct'],operand_ok) if arm=='A1' else None)
def wilson(k,n):
 if not n:return None
 z=1.959963984540054;p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;width=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return dict(k=k,n=n,point=p,lower=center-width,upper=center+width)
def interval(values):
 x=np.asarray([v for v in values if v is not None and math.isfinite(v)],dtype=float)
 return dict(lower=float(np.quantile(x,.025)),upper=float(np.quantile(x,.975)),valid_draws=len(x)) if len(x) else dict(lower=None,upper=None,valid_draws=0)
def bootstrap_indices(groups,draws=2000):
 keys=sorted(set(groups));by={k:np.flatnonzero(np.asarray(groups)==k) for k in keys};rng=np.random.default_rng(SEED)
 return [np.concatenate([by[k] for k in rng.choice(keys,len(keys),replace=True)]) for _ in range(draws)]
def rate(x,mask=None):
 x=np.asarray(x,dtype=float)
 if mask is not None:x=x[np.asarray(mask,dtype=bool)]
 return float(x.mean()) if len(x) else None
def diff_rate(a,b,ma=None,mb=None):
 x=rate(a,ma);y=rate(b,mb);return x-y if x is not None and y is not None else None
def paired(a,b,indices,ma=None,mb=None):
 a=np.asarray(a);b=np.asarray(b);ma=None if ma is None else np.asarray(ma);mb=None if mb is None else np.asarray(mb)
 return dict(point=diff_rate(a,b,ma,mb),**interval([diff_rate(a[ix],b[ix],None if ma is None else ma[ix],None if mb is None else mb[ix]) for ix in indices]),draws=len(indices),seed=SEED,unit='fraction')
def lambda_star(c,p,bc,bp):
 if p is None or bp is None:return dict(lambda_star=None,condition='undefined')
 intercept=c*p-bc*bp;slope=bc*(1-bp)-c*(1-p)
 if abs(intercept)<1e-15:intercept=0.
 if abs(slope)<1e-15:slope=0.
 root=-intercept/slope if slope else None
 if slope>0:condition='all_nonnegative' if intercept>0 else 'lambda_greater_than';star=max(0,root)
 elif slope<0:condition='lambda_less_than' if intercept>0 else 'never_nonnegative';star=root if intercept>0 else None
 else:condition='all_nonnegative' if intercept>0 else 'equal_all' if intercept==0 else 'never_nonnegative';star=0 if intercept>0 else None
 return dict(lambda_star=star,condition=condition,crossing=root,EV_difference_intercept=intercept,EV_difference_slope=slope)
def random_null(vbase,abase,v1,g):
 pool=np.asarray(vbase)[np.asarray(abase,dtype=bool)];gpool=np.asarray(v1)[np.asarray(g,dtype=bool)];k=min(len(pool),len(gpool));rng=np.random.default_rng(SEED)
 if not k:return dict(estimable=False)
 null=[];observed=[]
 for _ in range(1000):
  null.append(float(rng.choice(pool,k,replace=False).mean()));observed.append(float(rng.choice(gpool,k,replace=False).mean()) if len(gpool)>len(pool) else float(gpool.mean()))
 return dict(estimable=True,draws=1000,seed=SEED,subset_size=k,comparator_answered_n=len(pool),G_n=len(gpool),G_subsampled=len(gpool)>len(pool),G_coverage_advantage=max(0,len(gpool)-len(pool))/len(v1),mean_precision=rate(null),interval=interval(null),observed_precision=rate(observed),observed_interval=interval(observed),p_upper=(1+sum(a>=b for a,b in zip(null,observed)))/1001)
def threshold_gate(scores,coverage):
 ss=np.asarray(scores,dtype=float);target=coverage*len(ss)
 if target<=0:return dict(tau=None,boundary_accept=0,all_refuse=True,all_accept=False,matched_coverage=0)
 if target>=len(ss):return dict(tau=None,boundary_accept=1,all_refuse=False,all_accept=True,matched_coverage=1)
 tau=float(np.sort(ss)[::-1][math.ceil(target)-1]);above=int(sum(ss>tau));ties=int(sum(ss==tau));weight=(target-above)/ties
 return dict(tau=tau,boundary_accept=weight,all_refuse=False,all_accept=False,matched_coverage=(above+weight*ties)/len(ss))
def gate_weight(score,t):
 if t['all_refuse']:return 0.
 if t['all_accept']:return 1.
 return 1. if score>t['tau'] else t['boundary_accept'] if score==t['tau'] else 0.
def nonabstain(r):return not r['score']['abstain']
def probe_analysis(main,probes,taus,h1,headline,complete):
 out={}
 for system in ['A0','A1','A1+G']:
  arm=system.split('+')[0];rs=probes.get(arm,[]);ms=main[arm];coverage=rate([r['score']['G_accept'] if '+' in system else nonabstain(r) for r in ms])
  scores=[taus[r['item_id']] for r in ms];threshold=threshold_gate(scores,coverage)
  if not rs:out[system]=dict(estimable=False,n=0,calibration_n=len(ms),coverage=coverage,tau_gate=threshold,probe_false_answer_rate=None);continue
  false=[r['score']['G_accept'] if '+' in system else nonabstain(r) for r in rs];far=rate(false);control=rate([gate_weight(taus[r['item_id']],threshold) for r in rs]);advantage=control-far
  coverok=h1['branch'] in ['pass','partial'] if '+' in system else coverage>=.7
  validated=all(r['row'].get('probe',{}).get('validation',{}).get('valid') is True for r in rs)
  eligible=complete and len(rs)>=80 and validated and coverok
  branch='pass' if eligible and far<=.2 and advantage>=.1-1e-12 else 'partial' if eligible and .2<far<=.35 and advantage>=.1-1e-12 else 'fail'
  out[system]=dict(estimable=complete,branch=branch,n=len(rs),validated=validated,false_answer_rate=far,decline_rate=1-far,explicit_abstention_rate=rate([r['score']['abstain'] for r in rs]),invalid_rate=rate([not r['score']['answered'] and not r['score']['abstain'] for r in rs]),valid_false_answer_rate=rate([r['score']['answered'] for r in rs]),gold_match_memorisation_count=sum(match(r['score']['prediction'],r['row'].get('source_gold')) and bool(f) for r,f in zip(rs,false)),trivial_pass_n=sum(not r['row']['probe']['trivial_filter']['refuse'] for r in rs),trivial_pass_false_answer_rate=rate([f for r,f in zip(rs,false) if not r['row']['probe']['trivial_filter']['refuse']]),coverage=coverage,coverage_condition=coverok,tau_gate=threshold,tau_false_answer_rate=control,tau_decline_rate=1-control,beats_tau_pp=100*advantage,retrieval_score_equivalent=advantage<.1-1e-12,secondary_G_le_10pct=far<=.1 if '+' in system else None)
 return dict(systems=out,headline_system=headline,headline=out[headline],probe_clause_branch=('both_decline' if out['A0'].get('false_answer_rate',1)<=.2 and out[headline].get('false_answer_rate',1)<=.2 else 'headline_declines_more' if out[headline].get('false_answer_rate',1)<=.2 and out['A0'].get('false_answer_rate',1)>.2 else 'direct_declines_more' if out['A0'].get('false_answer_rate',1)<=.2 else 'both_answer_often' if out['A0'].get('false_answer_rate',0)>.35 and out[headline].get('false_answer_rate',0)>.35 else 'no_clause'),score_source='BM25+dense RRF(60), highest fused score among actually supplied chunks; expected uniform boundary tie handling')
def decomposition_clause(categories,branch):
 pool=[r for r in categories if r['arm'] in (['A0','A1'] if branch=='Tie' else ['A1']) and r['category']!='correct'];counts=collections.Counter(r['category'] for r in pool);reading=sum(counts[k] for k in READING);errors=len(pool)
 wo=counts['wrong_operand']/reading if reading else 0;wa=counts['wrong_arithmetic']/reading if reading else 0
 modal=counts.most_common(1)[0] if counts else (None,0)
 return dict(scope='pooled_A0_A1' if branch=='Tie' else 'A1',total_errors=errors,reading_errors=reading,wrong_operand_share_reading=wo,wrong_arithmetic_share_reading=wa,wrong_operand_share_all_errors=counts['wrong_operand']/errors if errors else 0,modal_category=modal[0],modal_share_all_errors=modal[1]/errors if errors else 0,clause_kind='operand_selection' if wo>=.5 and wa<=.15 else 'modal_category')
def determinism_equal(r,old):
 p=r['score']['prediction'];q=old['score']['prediction']
 if p is None or q is None:return p is None and q is None and r['score']['abstain']==old['score']['abstain'] and r['score']['truncated']==old['score']['truncated']
 return p['is_percent']==q['is_percent'] and p['is_yes_no']==q['is_yes_no'] and (p['value']==q['value'] if p['is_yes_no'] else round(p['value'],5)==round(q['value'],5))
def analyze(main,evidence,joins,probes=None,taus=None,diagnostics=None,dev=False):
 maps={a:{r['item_id']:r for r in main[a]} for a in ['A0','A1']};ids=sorted(maps['A0'].keys()&maps['A1'].keys())
 if not ids:raise ValueError('No paired items')
 if set(maps['A0'])!=set(maps['A1']):raise ValueError('Main arms must have identical IDs; incomplete run has no full headline')
 main={a:[maps[a][i] for i in ids] for a in maps};n=len(ids);complete=n==922 and not dev
 groups=[maps['A1'][i]['row']['doc_group'] for i in ids];ix=bootstrap_indices(groups)
 v={a:np.array([r['score']['NumMatch_1pct'] for r in main[a]]) for a in main};answered={a:np.array([r['score']['answered'] for r in main[a]]) for a in main};g=np.array([r['score']['G_accept'] for r in main['A1']])
 categories=[]
 for system in ['A0','A1','A1+G']:
  a=system.split('+')[0]
  for r in main[a]:categories.append(categorize(r,r['row'],evidence[r['item_id']],joins.get(r['item_id']),system,allow_missing_self=dev))
 hit=np.array([next(z for z in categories if z['item_id']==i and z['arm']=='A1')['operands_retrieved'] is True for i in ids]);known=np.array([next(z for z in categories if z['item_id']==i and z['arm']=='A1')['operands_retrieved'] is not None for i in ids])
 h0=paired(v['A1'],v['A0'],ix);branch='Win' if h0['lower']>0 else 'Lose' if h0['upper']<0 else 'Tie';fin=paired([r['score']['FinQA_agreement'] for r in main['A1']],[r['score']['FinQA_agreement'] for r in main['A0']],ix)
 scorer_dependent=h0['point']*fin['point']<0
 if scorer_dependent:branch='Tie'
 conditional=paired(v['A1'],v['A0'],ix,answered['A1'],answered['A0']);h0.update(branch=branch,win_word='beat' if h0['point']>=.05 else 'gave a small gain of',scorer_dependent=scorer_dependent,FinQA_delta=fin,answered_conditional_delta=conditional,append_abstention_clause=conditional['point'] is not None and h0['point']*conditional['point']<0)
 comparator='A0' if rate(v['A0'])>=rate(v['A1']) else 'A1';base=rate(v[comparator],answered[comparator]);precision=rate(v['A1'],g);gain=paired(v['A1'],v[comparator],ix,g,answered[comparator]);coverage=rate(g)
 h1branch='pass' if precision is not None and gain['point'] is not None and gain['lower'] is not None and gain['point']>=.15-1e-12 and gain['lower']>.05 and coverage>=.5 else 'partial' if precision is not None and gain['point'] is not None and gain['lower'] is not None and gain['point']>=.08-1e-12 and gain['lower']>0 and coverage>=.3 else 'fail'
 h1=dict(branch=h1branch,comparator=comparator,baseline_answered_precision=base,G_precision=precision,G_coverage=coverage,answered_conditional_gain=gain,overall_based_gain=precision-rate(v[comparator]) if precision is not None else None,random_subset_null=random_null(v[comparator],answered[comparator],v['A1'],g),ranking='operand_count',clause_operating_point='G',dev_expectation=dict(G_coverage=.515,G_precision=81/103,A0_answered_precision=105/143),lambda_star=lambda_star(coverage,precision,rate(answered[comparator]),base))
 headline='A1+G' if h1branch in ['pass','partial'] else 'A0' if branch=='Lose' else 'A1'
 curves=[];valid=answered['A1'];rank=np.array([r['score']['operand_count'] for r in main['A1']]);grid=sorted(set([k/20 for k in range(1,21) if k/20<=rate(valid)]+[rate(valid),coverage]))
 for cov in grid:
  if not cov:continue
  weights=np.zeros(n);left=cov*n
  for value in sorted(set(rank[valid]),reverse=True):
   group=valid&(rank==value);take=min(left,int(group.sum()));weights[group]=take/group.sum();left-=take
   if left<=1e-10:break
  p=float((v['A1']*weights).sum()/weights.sum());curves.append(dict(coverage=cov,precision=p,risk=1-p,random_gate_precision=base,lambda_star=lambda_star(cov,p,rate(answered[comparator]),base)))
 table={f'A0_{a}_A1_{b}':int(sum((v['A0']==bool(a))&(v['A1']==bool(b)))) for a in (0,1) for b in (0,1)}
 off={key:paired(mask,np.zeros(n),ix) for key,mask in [('A0_only',v['A0']&~v['A1']),('A1_only',~v['A0']&v['A1'])]}
 decomposition={}
 for a in main:
  contrib=float((v[a]&hit).mean());residual=float((v[a]&~hit).mean());decomposition[a]=dict(overall_accuracy=rate(v[a]),retrieved_fraction=rate(hit),correct_given_retrieved=rate(v[a],hit),retrieved_contribution=contrib,nonretrieved_or_unknown_contribution=residual,correct_given_not_retrieved=rate(v[a],~hit),identity_sum=contrib+residual,unknown_operand_n=int(sum(~known)),note='The product alone is not total accuracy when correct answers occur outside the retrieved subset; the residual is reported explicitly.')
 tax={a:dict(counts=dict(collections.Counter(r['category'] for r in categories if r['arm']==a)),abstain_split=dict(collections.Counter(r['abstain_split'] for r in categories if r['arm']==a and r['abstain_split'])),self_answer=dict(available=sum(bool(r['self_answer'] and r['self_answer']['available']) for r in categories if r['arm']==a),arithmetic_corrected=sum(bool(r['self_answer'] and r['self_answer'].get('arithmetic_corrected')) for r in categories if r['arm']==a))) for a in ['A0','A1','A1+G']}
 summary=dict(scope='dev_example' if dev else 'stage2',n=n,filings=len(set(groups)),complete_main=complete,headline_eligible=complete,arms={a:dict(**summarize([r['score'] for r in main[a]]),answered_conditional_accuracy=rate(v[a],answered[a]),abstain_rate=rate([r['score']['abstain'] for r in main[a]])) for a in main},A1_G=gated_summary([r['score'] for r in main['A1']]),H0=h0,H1=h1,headline_system=headline,conditional_delta_operands_retrieved=dict(n=int(sum(hit)),**paired(v['A1'],v['A0'],ix,hit,hit)),disagreement_share=rate(v['A0']!=v['A1']),paired_2x2=table,off_diagonal_bootstrap=off,accuracy_decomposition=decomposition,taxonomy=tax,decomposition_clause=decomposition_clause(categories,branch),risk_coverage=curves)
 best=max(main,key=lambda a:rate(v[a]));summary['accuracy_standalone']=dict(arm=best,accuracy=rate(v[best]),FinQA_agreement=rate([r['score']['FinQA_agreement'] for r in main[best]]),eligible_arms=[a for a in main if rate(v[a])>=.426 and rate([r['score']['FinQA_agreement'] for r in main[a]])>=.426],eligible=any(rate(v[a])>=.426 and rate([r['score']['FinQA_agreement'] for r in main[a]])>=.426 for a in main))
 summary['H3_prime']=probe_analysis(main,probes or {},taus or {},h1,headline,complete)
 diagnostics=diagnostics or {};ctx=diagnostics.get('contextdep',[]);cf=diagnostics.get('counterfactual',[]);oracle=diagnostics.get('oracle',[])
 h2=dict(estimable=False,status='not_run',drop_probe_clause=False,withheld_gold_match_memorisation_flags={name:result.get('gold_match_memorisation_count') for name,result in summary['H3_prime']['systems'].items()})
 if ctx:
  validctx=[r for r in ctx if r['item_id'] in maps['A1']];ctxacc=rate([r['score']['NumMatch_1pct'] for r in validctx]);ref=rate([maps['A1'][r['item_id']]['score']['NumMatch_1pct'] for r in validctx]);h2.update(contextdep_n=len(ctx),contextdep_accuracy=ctxacc,A1_same_items=ref,contextdep_ratio=ctxacc/ref if ref else None,drop_probe_clause=ctxacc>.5*ref)
 if cf:h2.update(counterfactual_n=len(cf),follows_new_gold=rate([r['score']['NumMatch_1pct'] for r in cf]),matches_old_gold=rate([match(r['score']['prediction'],r['row']['old_gold']) for r in cf]));h2['drop_probe_clause']|=h2['follows_new_gold']<.5
 if ctx and cf:
  h2['estimable']=len(ctx)==200 and len(cf)==100;h2['status']='fail' if h2['drop_probe_clause'] else 'pass' if h2['follows_new_gold']>=.7 else 'partial'
 summary['Wilson']={a:wilson(int(sum(v[a])),n) for a in main}
 summary['Wilson']['G_coverage']=wilson(int(sum(g)),n)
 summary['Wilson']['G_precision']=wilson(int(sum(v['A1']&g)),int(sum(g)))
 summary['H2']=h2
 summary['self_answer_vs_execution']={a:dict(collections.Counter(r['self_answer']['self_vs_execution'] for r in categories if r['arm']==a and r['self_answer'] and r['self_answer'].get('available'))) for a in ['A1','A1+G']}
 summary['H3_prime']['summary_clause_allowed']=bool(complete and summary['H3_prime']['headline'].get('branch')=='pass' and h2['estimable'] and not h2['drop_probe_clause'])
 if oracle:
  rs=[r for r in oracle if r['item_id'] in maps['A1']];summary['H4']=dict(n=len(rs),oracle_accuracy=rate([r['score']['NumMatch_1pct'] for r in rs]),gain_vs_A1=paired([r['score']['NumMatch_1pct'] for r in rs],[maps['A1'][r['item_id']]['score']['NumMatch_1pct'] for r in rs],bootstrap_indices([r['row']['doc_group'] for r in rs])),wrong_despite_gold_evidence=sum(not r['score']['NumMatch_1pct'] for r in rs),wrong_answered=sum(r['score']['answered'] and not r['score']['NumMatch_1pct'] for r in rs),wrong_with_all_gold_snippet_hits=sum(r['score']['answered'] and not r['score']['NumMatch_1pct'] and bool(r['score']['retrieval']) and r['score']['retrieval']['all_hit'] for r in rs))
 rerun=diagnostics.get('rerun30',[])
 if rerun:
  agree=sum(determinism_equal(r,maps['A1'][r['item_id']]) for r in rerun);summary['determinism']=dict(n=len(rerun),parsed_agreement=agree,exact_text_agreement=sum(r['response']['choices'][0]['message'].get('content')==maps['A1'][r['item_id']]['response']['choices'][0]['message'].get('content') for r in rerun),pass_28_of_30=len(rerun)==30 and agree>=28)
 fb=diagnostics.get('financebench',[])
 if fb:
  summary['financebench']={kind:dict(n=len(rs),false_answer_rate=rate([nonabstain(r) for r in rs]),G_accept_rate=rate([r['score']['G_accept'] for r in rs]),accuracy=rate([r['score']['NumMatch_1pct'] for r in rs]),trivial_decline_rate=rate([r['row']['probe']['trivial_filter']['refuse'] for r in rs])) for kind in ['answerable','easy'] if (rs:=[r for r in fb if r['row']['probe']['kind']==kind])}
 if fb:
  answerable=[r['score'] for r in fb if r['row']['probe']['kind']=='answerable']
  summary['financebench_answerable']=summarize(answerable) if answerable else None
  summary['financebench_answerable_G']=gated_summary(answerable) if answerable else None
 summary['headline_lead']='H0' if branch=='Win' else 'H1' if h1branch in ['pass','partial'] else 'H3_prime' if summary['H3_prime']['summary_clause_allowed'] else 'H0_null_with_decomposition'
 summary['G_point']=dict(coverage=coverage,precision=precision,lambda_star=h1['lambda_star'],probe_false_answer_rate=summary['H3_prime']['systems']['A1+G'].get('false_answer_rate'))
 summary['risk_coverage_G']=[]
 for point in curves:
  cov=point['coverage']
  if cov>coverage or cov<=0:continue
  need=cov*n;weights=np.zeros(n)
  for value in sorted(set(rank[g]),reverse=True):
   group=g&(rank==value);take=min(need,int(group.sum()));weights[group]=take/group.sum();need-=take
   if need<=1e-10:break
  p=float((v['A1']*weights).sum()/weights.sum());summary['risk_coverage_G'].append(dict(coverage=cov,precision=p,risk=1-p,lambda_star=lambda_star(cov,p,rate(answered[comparator]),base)))
 return summary,categories

def main():
 p=argparse.ArgumentParser();p.add_argument('--dev',action='store_true');p.add_argument('--run-id');args=p.parse_args()
 if args.dev:
  out=RUNS/'stage1c/dev_example';source=RUNS/'stage1b';inputs=readl(source/'evidence_candidate2_bm25_k10.jsonl');joins={r['item_id']:r for r in readl(MAN/'finqa_dev2_join.jsonl')};evidence={t['row']['item_id']:t['evidence'] for t in inputs};rows={t['row']['item_id']:t['row'] for t in inputs};raw=readl(source/'answers_candidate2_bm25_k10.jsonl');mainarms={a:[] for a in ['A0','A1']}
  for r in raw:
   r=dict(r,row=rows[r['item_id']]);r['score']=score(r,r['row'],evidence[r['item_id']],joins[r['item_id']]);mainarms[r['arm']].append(r)
  probes={};diag={}
 else:
  if not args.run_id:p.error('--run-id required unless --dev')
  out=RUNS/args.run_id;load=lambda name:readl(out/(name+'.jsonl')) if (out/(name+'.jsonl')).exists() else []
  mainarms={a:load(a) for a in ['A0','A1']};inputs=readl(RUNS/'frozen_v2/test_evidence.jsonl');evidence={t['row']['item_id']:t['evidence'] for t in inputs};joins={r['item_id']:r for r in readl(MAN/'finqa_join.jsonl')};probes={a:load('withheld_'+a) for a in mainarms};diag={a:load(a) for a in ['contextdep','counterfactual','oracle','rerun30','financebench']}
 taus={r['item_id']:r['top1_fused'] for r in readl(RUNS/'frozen_v2/tau_scores.jsonl')} if (RUNS/'frozen_v2/tau_scores.jsonl').exists() else {}
 summary,categories=analyze(mainarms,evidence,joins,probes,taus,diag,dev=args.dev);out.mkdir(exist_ok=True,parents=True);jsonl(out/'error_categories.jsonl',categories);dump(out/'analysis.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
