"""Pre-freeze unit and saved-dev integration checks. No generation."""
import copy,unittest
import numpy as np
from core import *
import analyze as a
from qa_v2 import schema
from schema_check import valid_schema
from prepare_counterfactual import execute_finqa,format_like,token_digits,TOKEN

class AnalysisTests(unittest.TestCase):
 def fixture(self,arm='A1',correct=False,hit=True):
  obj=dict(reasoning='10 and 20',operands=[dict(name='a',value=10,quote='The amounts are 10 and 20 in 2020.',period='2020',unit='USD'),dict(name='b',value=20,quote='The amounts are 10 and 20 in 2020.',period='2020',unit='USD')],program='a+b',self_answer=30,answer_type='number',abstain=False)
  if arm=='A0':obj=dict(reasoning='10 and 20',answer=31,unit='USD',abstain=False)
  row=dict(item_id='x',doc_group='filing',gold=parse(30));join={'qa.program':'add(10, 20)','qa.gold_inds':{'text_0':'10 and 20'}};e={'chunks':[dict(header='2020',text='10 and 20' if hit else '17 and 42')]}
  s=dict(truncated=False,unparseable=False,abstain=False,answered=True,G_accept=True,G={'reasons':[]},NumMatch_1pct=correct,prediction=parse(30 if correct else 31))
  r=dict(arm=arm,score=s,response={'choices':[{'message':{'content':json.dumps(obj)}}]})
  return r,row,e,join,obj
 def category(self,**kwargs):
  r,row,e,j,o=self.fixture(**kwargs);return a.categorize(r,row,e,j)
 def test_wrong_arithmetic(self):self.assertEqual(self.category()['category'],'wrong_arithmetic')
 def test_retrieval_first(self):self.assertEqual(self.category(hit=False)['category'],'retrieval_miss')
 def test_correct(self):self.assertEqual(self.category(correct=True)['category'],'correct')
 def test_gold_constants(self):self.assertEqual(a.gold_operands({'qa.program':'divide(20, const_100)','qa.gold_inds':{'a':'20 100'}}),[20])
 def test_abstain_splits(self):
  for hit,expected in [(False,'2a_justified'),(True,'2b_unjustified')]:
   r,row,e,j,o=self.fixture(hit=hit);r['score'].update(abstain=True,answered=False);o.update(abstain=True,operands=[],program='');r['response']['choices'][0]['message']['content']=json.dumps(o)
   self.assertEqual(a.categorize(r,row,e,j)['abstain_split'],expected)
 def test_filter_splits(self):
  r,row,e,j,o=self.fixture();r['score']['G_accept']=False
  self.assertEqual(a.categorize(r,row,e,j,'A1+G')['abstain_split'],'2b_unjustified')
 def test_format_precedes_abstain(self):
  r,row,e,j,o=self.fixture();r['score'].update(abstain=True,truncated=True)
  self.assertEqual(a.categorize(r,row,e,j)['category'],'format')
 def test_wrong_operand(self):
  r,row,e,j,o=self.fixture();o['operands'][0]['value']=17;r['response']['choices'][0]['message']['content']=json.dumps(o)
  self.assertEqual(a.categorize(r,row,e,j)['category'],'wrong_operand')
 def test_sign_and_scale(self):
  for pred in (-30,300):
   r,row,e,j,o=self.fixture();r['score']['prediction']=parse(pred)
   self.assertEqual(a.categorize(r,row,e,j)['category'],'unit_scale_sign')
 def test_A0_rules(self):
  r,row,e,j,o=self.fixture(arm='A0');self.assertEqual(a.categorize(r,row,e,j)['category'],'wrong_arithmetic')
  o['reasoning']='17 and 20';r['response']['choices'][0]['message']['content']=json.dumps(o);self.assertEqual(a.categorize(r,row,e,j)['category'],'wrong_operand')
 def test_self_answer_never_changes_score(self):
  r,row,e,j,o=self.fixture(correct=True);o['self_answer']=31;r['response']['choices'][0]['message']['content']=json.dumps(o);out=a.categorize(r,row,e,j)
  self.assertEqual(out['category'],'correct');self.assertTrue(out['self_answer']['arithmetic_corrected'])
 def test_schema_boolean_not_number(self):self.assertFalse(valid_schema(True,{'type':'number'}))
 def test_cluster_draws(self):
  draws=a.bootstrap_indices(['f','f','g']);self.assertEqual(len(draws),2000)
  for ix in draws:self.assertEqual(sum(ix==0),sum(ix==1))
  np.testing.assert_array_equal(draws[0],a.bootstrap_indices(['f','f','g'])[0])
 def test_conditional_baseline(self):
  ix=a.bootstrap_indices(['f','g','h','i']);out=a.paired([1,0,0,0],[1,1,0,0],ix,[1,0,0,0],[1,1,0,0]);self.assertEqual(out['point'],0)
 def test_random_null_subsample_G(self):
  r=a.random_null([1,0,0,0],[1,0,0,0],[1,1,0,0],[1,1,1,0]);self.assertTrue(r['G_subsampled']);self.assertEqual(r['subset_size'],1);self.assertEqual(r['mean_precision'],1)
 def test_tau_ties(self):
  t=a.threshold_gate([3,2,2,1],.5);self.assertEqual(t['tau'],2);self.assertEqual(t['boundary_accept'],.5);self.assertEqual(sum(a.gate_weight(x,t) for x in [3,2,2,1])/4,.5)
 def test_tau_edges(self):
  self.assertEqual(a.gate_weight(2,a.threshold_gate([1,2],0)),0);self.assertEqual(a.gate_weight(2,a.threshold_gate([1,2],1)),1)
 def test_nonabstain_invalid_is_false_answer(self):self.assertTrue(a.nonabstain({'score':{'abstain':False,'answered':False}}))
 def test_lambda(self):
  r=a.lambda_star(.5,.8,1,.6);self.assertAlmostEqual(r['lambda_star'],2/3);self.assertEqual(r['condition'],'lambda_greater_than')
  self.assertEqual(a.lambda_star(1,.5,1,.6)['condition'],'never_nonnegative')
 def test_counterfactual_execute(self):
  self.assertEqual(execute_finqa('subtract(20, 10), divide(#0, const_10)',{20:24,10:8}),1.6)
  self.assertEqual(format_like(1200.5,'1,000.0'),'1,200.5');self.assertEqual(token_digits('1,000.0'),token_digits('1,200.5'))
 def test_probe_tau_and_coverage(self):
  def result(i,abstain,g=False):
   return dict(item_id=str(i),score=dict(abstain=abstain,answered=not abstain,G_accept=g,prediction=None),row=dict(probe=dict(validation=dict(valid=True),trivial_filter=dict(refuse=False)),source_gold=None))
  main={a:[result(i,i>=80,i<50) for i in range(100)] for a in ['A0','A1']}
  probes={a:[result(i,i>=10,i<5) for i in range(100)] for a in main};taus={str(i):100-i for i in range(100)}
  out=a.probe_analysis(main,probes,taus,{'branch':'partial'},'A1+G',True)
  self.assertEqual(out['systems']['A0']['branch'],'pass');self.assertEqual(out['systems']['A1+G']['branch'],'pass');self.assertEqual(out['systems']['A1+G']['coverage'],.5)
  out=a.probe_analysis(main,probes,taus,{'branch':'fail'},'A1',True);self.assertEqual(out['systems']['A1+G']['branch'],'fail')
 def test_probe_tau_equivalence(self):
  def result(i,abstain):return dict(item_id=str(i),score=dict(abstain=abstain,answered=not abstain,G_accept=not abstain,prediction=None),row=dict(probe=dict(validation=dict(valid=True),trivial_filter=dict(refuse=False)),source_gold=None))
  main={a:[result(i,i>=80) for i in range(100)] for a in ['A0','A1']};probes={a:[result(i,i>=80) for i in range(100)] for a in main};taus={str(i):100-i for i in range(100)}
  out=a.probe_analysis(main,probes,taus,{'branch':'partial'},'A1',True);self.assertTrue(out['headline']['retrieval_score_equivalent']);self.assertEqual(out['headline']['branch'],'fail')
 def test_no_probe_measurement_in_dev(self):
  s=json.loads((RUNS/'stage1c/dev_example/analysis.json').read_text())
  self.assertFalse(s['H3_prime']['headline']['estimable']);self.assertEqual(s['H3_prime']['headline']['calibration_n'],200);self.assertFalse(s['H3_prime']['summary_clause_allowed'])
 def test_self_answer_saved_outputs(self):
  s=json.loads((RUNS/'stage1c/dev_self_answer_50/analysis.json').read_text());self.assertEqual(s['n'],50);self.assertEqual(sum(s['self_answer_vs_execution']['A1'].values()),s['arms']['A1']['answered'])
 def test_finqa_sign_downgrade(self):
  s=json.loads((RUNS/'stage1c/dev_example/analysis.json').read_text());self.assertTrue(s['H0']['scorer_dependent']);self.assertEqual(s['H0']['branch'],'Tie')
 def test_determinism_five_decimal(self):
  r={'score':{'prediction':parse(1.000001),'abstain':False,'truncated':False}};old=copy.deepcopy(r);old['score']['prediction']=parse(1.000002);self.assertTrue(a.determinism_equal(r,old))
 def test_saved_dev(self):
  s=json.loads((RUNS/'stage1c/dev_example/analysis.json').read_text());self.assertEqual(s['n'],200);self.assertAlmostEqual(s['arms']['A0']['NumMatch_1pct'],.525);self.assertAlmostEqual(s['arms']['A1']['NumMatch_1pct'],.485);self.assertAlmostEqual(s['H1']['G_coverage'],.515);self.assertAlmostEqual(s['H1']['baseline_answered_precision'],105/143);self.assertEqual(sum(s['paired_2x2'].values()),200)
  for a0 in ['A0','A1']:self.assertAlmostEqual(s['accuracy_decomposition'][a0]['identity_sum'],s['arms'][a0]['NumMatch_1pct'])
  self.assertEqual(len(readl(RUNS/'stage1c/dev_example/error_categories.jsonl')),600)
 def test_saved_counterfactual(self):
  rows=readl(MAN/'counterfactual_100.jsonl');self.assertEqual(len(rows),100);self.assertEqual(len({r['row']['item_id'] for r in rows}),100)
  for r in rows:
   cf=r['row']['counterfactual'];self.assertFalse(match(r['row']['old_gold'],r['row']['new_gold']))
   for c in cf['changes']:self.assertTrue(.1-1e-12<=abs(c['relative_change'])<=.3+1e-12)
 def test_counterfactual_preserves_format_and_execution(self):
  originals={t['row']['item_id']:t for t in readl(RUNS/'frozen_v2/test_evidence.jsonl')};joins={j['item_id']:j for j in readl(MAN/'finqa_join.jsonl')}
  for t in readl(MAN/'counterfactual_100.jsonl'):
   item=t['row']['item_id'];old=originals[item];cf=t['row']['counterfactual'];changes={c['old']:c['new'] for c in cf['changes']}
   for c,d in zip(old['evidence']['chunks'],t['evidence']['chunks']):
    self.assertEqual(c['header'],d['header']);self.assertEqual(TOKEN.sub('<N>',c['text']),TOKEN.sub('<N>',d['text']))
    for m,z in zip(TOKEN.finditer(c['text']),TOKEN.finditer(d['text'])):
     v=float(m[0].replace(',',''));expected=format_like(changes[v],m[0]) if v in changes else m[0];self.assertEqual(z[0],expected);self.assertEqual(token_digits(m[0]),token_digits(z[0]))
   scale=joins[item].get('prediction_percent_to_finqa_scale',.01) if t['row']['gold']['is_percent'] else 1
   self.assertAlmostEqual(execute_finqa(cf['program'],changes)/scale,t['row']['gold']['value'])
 def test_only_schema_field_changed(self):
  # Historical check: private development commit dated 2026-10-18 19:23:27 EDT (UTC-04:00).
  # Requires the private development history; this single-commit snapshot does not contain it.
  old=json.loads(subprocess.check_output(['git','show','ed4fd38e16f6fb1f772347a0fc995cd07b9994ce:protocol_v2.json'],text=True));now=json.loads(pathlib.Path('protocol_v2.json').read_text());self.assertEqual(old['prompt'],now['prompt']);self.assertEqual(old['schemas']['A0'],schema('A0'))
  sch=schema('A1');sch['properties'].pop('self_answer');sch['required'].remove('self_answer');self.assertEqual(sch,old['schemas']['A1'])
 def test_self_answer_field_order(self):
  for r in readl(RUNS/'stage1c/answers_self_answer_50.jsonl'):
   obj=json.loads(r['response']['choices'][0]['message']['content']);keys=list(obj);self.assertEqual(keys.index('self_answer'),keys.index('program')+1);self.assertTrue(valid_schema(obj,schema('A1')))
 def test_frozen_hashes_and_headline_source(self):
  p=json.loads(pathlib.Path('protocol_v2.json').read_text())
  for key,root in [('manifest_hashes',MAN),('evidence_hashes',RUNS/'frozen_v2'),('code_hashes',pathlib.Path('.'))]:
   for name,h in p[key].items():self.assertEqual(sha((root/name).read_bytes()),h,name)
  self.assertEqual(p['stage2_hours'],6);self.assertEqual(p['run_order'],['A1','A0','withheld_A1','withheld_A0','contextdep','rerun30','counterfactual','financebench','oracle']);self.assertEqual(p['block_sizes']['counterfactual'],100)
  text=pathlib.Path('PREREG_v2.md').read_text();source=(RUNS/'stage1c/PREREG_HEADLINES_source.md').read_text();section=text[text.index('# PREREG_HEADLINES'):text.index('### Stage-1c binding implementation details')].strip();section=re.sub(r'- \[DONE[^\]]*\] ', '- ',section);self.assertEqual(section,source.strip());self.assertNotIn('REVIEW_PLACEHOLDER',text)
 def test_stage2_plan_and_capacity_without_generation(self):
  from run_v2 import build_plan,block_fits
  p=json.loads(pathlib.Path('protocol_v2.json').read_text());plan=build_plan(p);self.assertEqual([r[0] for r in plan],p['run_order']);self.assertEqual(sum(len(r[2]) for r in plan),2900);self.assertEqual(len(plan[6][2]),100)
  need=300*3600/p['safe_qph'];self.assertTrue(block_fits('withheld_A1',150,1844,need,p));self.assertFalse(block_fits('withheld_A1',150,1844,need-.01,p));self.assertFalse(block_fits('contextdep',200,2144,199*3600/p['safe_qph'],p))
 def test_invalid_operands_do_not_crash_taxonomy(self):
  r,row,e,j,o=self.fixture();o['operands']=None;o['self_answer']=float('nan');o['answer_type']='percent';r['response']['choices'][0]['message']['content']=json.dumps(o);self.assertEqual(a.categorize(r,row,e,j)['category'],'format')
 def test_yesno_prediction_for_numeric_gold(self):
  r,row,e,j,o=self.fixture(arm='A0');r['score']['prediction']=parse('yes');self.assertEqual(a.categorize(r,row,e,j)['category'],'other')
 def test_lambda_floating_equality(self):
  self.assertEqual(a.lambda_star(.5,.8,.5,.8+1e-16)['condition'],'equal_all')
if __name__=='__main__':unittest.main()
