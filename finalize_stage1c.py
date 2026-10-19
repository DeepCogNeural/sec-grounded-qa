"""Freeze stage-1c artifacts for protocol review; never starts evaluation."""
from core import *
from qa_v2 import schema

def main():
 assert not (RUNS/'TEST_GENERATION_STARTED.json').exists(), 'Cannot alter pre-registration after test generation starts'
 root=pathlib.Path('.');out=RUNS/'stage1c';check=json.loads((out/'self_answer_check.json').read_text());assert check['retain']
 p=json.loads((root/'protocol_v2.json').read_text());old_qph=p.get('stage1b_qph',p['preflight_qph']);new_qph=50*3600/check['seconds'];safe=min(old_qph,new_qph)*.8
 order=['A1','A0','withheld_A1','withheld_A0','contextdep','rerun30','counterfactual','financebench','oracle'];sizes=dict(A1=922,A0=922,withheld_A1=150,withheld_A0=150,contextdep=200,rerun30=30,counterfactual=100,financebench=226,oracle=200)
 total=sum(sizes.values());estimated=[];used=0
 for name in order:
  reserved=sizes[name]+(sizes['withheld_A0'] if name=='withheld_A1' else 0)
  if (used+reserved)/safe>6:break
  estimated.append(name);used+=sizes[name]
 p.update(version='stage1c-v2',stage2_hours=6.0,run_order=order,block_sizes=sizes,max_planned_requests=total,request_capacity=total,request_capacity_semantics='Maximum unique planned requests, including the specified 30-item rerun. The binding capacity cap is 6.0 hours of actual elapsed wall clock.',safe_capacity_estimate=int(6*safe),safe_qph=safe,preflight_qph=min(old_qph,new_qph),stage1b_qph=old_qph,self_answer_50_qph=new_qph,planned_blocks=order,preplanned_cut=[],estimated_prefix_at_safe_qph=estimated,estimated_cut_at_safe_qph=order[len(estimated):],cut_policy='Before each block check the whole block against remaining wall time at safe_qph. Reserve both withheld arms together. At first failure drop that block and all later blocks. No result-dependent restoration.',self_answer=dict(retained=True,not_used_for_scoring=True,placement='immediately after program',dev_check=check),ranking='operand_count',ranking_direction='descending',H1_comparator='Higher overall NumMatch ungated arm; A0 on ties; answered-conditional precision',H1_clause_point='G',H1_dev_expectation=dict(G_coverage=.515,G_precision=81/103,A0_answered_precision=105/143),tau_score='max BM25+dense reciprocal-rank fusion, k=60, over actually supplied chunks',headline_source_sha256=sha((out/'PREREG_HEADLINES_source.md').read_bytes()))
 p['schemas']={a:schema(a) for a in ['A0','A1']}
 p['manifest_hashes']['counterfactual_100.jsonl']=sha((MAN/'counterfactual_100.jsonl').read_bytes())
 for name in ['counterfactual_evidence.jsonl','counterfactual_token_preflight.jsonl','tau_scores.jsonl']:p['evidence_hashes'][name]=sha((RUNS/'frozen_v2'/name).read_bytes())
 code=['core.py','qa_v2.py','schema_check.py','scoring.py','retrieval.py','retrieval_v2.py','run.py','run_v2.py','analyze.py','analyze_v2.py','prepare_counterfactual.py','prepare_tau.py']
 p['code_hashes']={name:sha((root/name).read_bytes()) for name in code}
 budget=dict(stage2_hours=6,stage1b_measured_qph=old_qph,final_schema_50_measured_qph=new_qph,safety_factor=.8,safe_qph=safe,safe_capacity_estimate=int(6*safe),max_requests=total,estimated_full_hours=total/safe,estimated_prefix=estimated,estimated_prefix_requests=used,estimated_prefix_hours=used/safe,estimated_cut=order[len(estimated):],blocks=[dict(name=name,requests=sizes[name],safe_hours=sizes[name]/safe) for name in order],binding_rule='Actual remaining wall clock, tested before every whole block. Estimates are not advance cuts.')
 dump(out/'budget_stage1c.json',budget);dump(root/'protocol_v2.json',p)
 source=(out/'PREREG_HEADLINES_source.md').read_text()
 f=source.index('## F.');source=source[:f]+source[f:].replace('- analyze.py','- [DONE] analyze.py').replace('- Decide `self_answer`','- [DONE: retained; JSON 100% vs 100%, NumMatch 50% vs 48% on the same 50 dev-2 items] Decide `self_answer`').replace('- Related work','- [DONE] Related work')
 text=(root/'PREREG_v2.md').read_text();start=text.index('## Headline hierarchy and negative-branch wording');end=text.index('## Data and development selection',start)
 additions='''### Stage-1c binding implementation details

H1 uses the dev-chosen `operand_count` ranking, descending, for the curve, and the G point for the clause. Before any test generation, stage-1b dev-2 gave G **51.5% coverage at 78.6% precision**, versus A0 **73.4% answered-conditional precision**. The exact gain is 5.2142 pp, not the 26.1408 pp obtained against A0 overall accuracy. This does not meet either H1 point threshold on dev. The 50-item schema check is separate and does not replace these 200-item development selection results.

The complete headline source above is verbatim except for status marks in §F. The analysis emits fractions; multiply by 100 for the percentages and percentage-point placeholders. The selected comparator is fixed inside each paired bootstrap rather than reselected on resampled outcomes. A0 wins an exact overall-accuracy comparator tie. H0's FinQA sign check uses the same full primary denominator; eligibility counts are also reported.

The tau control is a separate CPU-only calculation of BM25 plus BGE reciprocal-rank fusion (60 + rank, ranks start at one), using the highest fused score among chunks actually supplied. It does not change the chosen BM25 retrieval or any prompt. The old withheld `top1_bm25` field described the pre-removal maximum and is not used for this control. `tau_scores.jsonl` freezes all 200 dev-2, 922 test and 150 withheld scores. Equal scores at tau receive one shared fractional acceptance weight, the expected uniform random tie rule, to match coverage exactly. Invalid non-abstain outputs count as false answers for H3-prime, and are reported separately; they never count as explicit refusals. The ungated H3-prime coverage uses this same non-abstain definition. Probe clauses remain unavailable if H2 is not estimable or requires the recall caveat.

Taxonomy gold operands must occur in `gold_inds`; numeric matching uses the specified 1% tolerance, signs and scaling, and includes supplied headers. This differs from stage-1b's near-exact numeric-presence retrieval diagnostic. Missing operand annotations are explicitly unknown, not automatically a retrieval miss: abstentions have `2_unknown` alongside 2a/2b, with counts disclosed. Correct answers receive `correct`; the seven rules classify errors. For A1, the executed named operands and full declared set are recorded by the deterministic rules. `self_answer` diagnoses code-only versus self-only correctness and arithmetic correction conditional on the operand set; it never affects primary scoring or G.

Accuracy decomposition reports the requested retrieved product **and** the nonretrieved/unknown correct-answer residual. The product alone is not an identity if a correct answer occurs without detected gold operands. Both reading-error and all-error denominators are emitted for the decomposition clause. The full 200-item dev example and the separate new-schema 50-item example are saved under `runs/stage1c/`; no probe answer is simulated as a measured H3 result.

| Labelled related-work reference | Reported accuracy | Scope |
|---|---:|---|
| 2024 DocFinQA reference: GPT-3.5 + FT-ColBERT | 42.6% | Different protocol; descriptive reference, never a beaten paired baseline. |

'''
 text=text[:start]+'## Headline hierarchy and negative-branch wording\n\n'+source+'\n'+additions+text[end:]
 text=text.replace('protocol review, headline wording, and a committed approval SHA are required before stage 2.', 'Headline wording and analysis are implemented; protocol review and explicit go on the committed SHA are still required before stage 2.')
 # Replace the schema display while preserving all prompt strings and demonstration messages.
 def update_json(m):
  try:x=json.loads(m[1])
  except ValueError:return m[0]
  if isinstance(x,dict) and set(x)=={'A0','A1'} and x['A0'].get('type')=='object':return '```json\n'+json.dumps(p['schemas'],indent=2)+'\n```'
  return m[0]
 text=re.sub(r'```json\n(.*?)\n```',update_json,text,flags=re.S)
 text=re.sub(r'A1 adds only the required numeric schema property.*?\n\n', '', text, flags=re.S)
 text=text.replace('Fixed demonstrations, including all original output fields:', 'A1 adds only the required numeric schema property `self_answer`, immediately after `program`; its description requests the model arithmetic result and 0 for abstention. All message text, examples, evidence and other schema properties remain unchanged. In the same seeded 50 dev-2 items, schema-valid JSON was 50/50 in both versions; NumMatch was 24/50 before and 25/50 after. The field passes the >=98% validity and no-more-than-4-pp-loss rules and is retained.\n\nFixed demonstrations, including all original output fields:')
 start=text.index('## Diagnostics, intervals and hypotheses');end=text.index('## Capacity, run order and cut rule',start)
 text=text[:start]+'''## Diagnostics, intervals and hypotheses

The headline hierarchy and thresholds above are authoritative. Oracle uses the fixed 200 joined items and compares A1 on identical IDs, last in run order. Context dependence uses the fixed 200 test items, A0 with no current evidence and unchanged demonstrations, compared with A1 on those IDs. The 30-item A1 rerun uses seed 20261018 and requires at least 28/30 parsed-value/type/abstention agreement at five-decimal numeric precision, with exact-text agreement also reported.

Counterfactual is prepared before generation: 100 test items selected with seed 20261018 from the operands-retrieved subset, independent of generated correctness. Per-item seeded perturbations change each distinct nonconstant gold operand by plus or minus 10-30%, preserve digit count, decimal places, comma placement, signs, currency and surrounding text, and replace every literal occurrence in the supplied evidence. Unsupported table programs, period/zero operands, ambiguous nonliteral/scaled-only operands, inconsistent original golds, or indistinguishable new golds are excluded before selection. The original FinQA program executes on the new operands; old and new gold, program, substitutions and occurrence counts are saved. H2 follows-substituted-numbers is NumMatch-1% against the new gold, not the old gold. `counterfactual_100.jsonl` and its frozen evidence copy are identical. No test answer is used to build the set.

All paired differences and off-diagonal shares use 2,000 filing-level bootstrap draws, seed 20261018, sampling original context groups with replacement and keeping every item of a sampled group. Percentile 2.5/97.5 bounds and undefined-draw counts are reported. H1 compares G precision with the higher-overall-accuracy ungated arm's answered-conditional precision. Its random-subset null has 1,000 draws from that comparator's answered pool at G's accepted count; if G is larger, subsample G to the comparator pool size and report the coverage advantage. Descriptive Wilson intervals remain secondary. No external judge is used.

'''+text[end:]
 start=text.index('## Capacity, run order and cut rule');end=text.index('## Frozen file hashes',start)
 text=text[:start]+'## Capacity, run order and cut rule\n\n```json\n'+json.dumps(budget,indent=2)+'\n```\n\n'+'''The binding capacity cap is **6.0 hours of actual wall clock from the start of stage 2**. Before each block, check that the whole block fits in the remaining time at frozen `safe_qph`; otherwise drop that block and every later block. Reserve both withheld arms together. Do not pre-drop blocks merely from the full-plan estimate: faster earlier blocks can leave enough real time. The maximum request count is the sum of the fixed plan, not a second lower capacity cap. The frozen safe rate is 0.8 times the lower of the stage-1b 20-item rate and the final-schema 50-dev-item rate. This is a conservative planning proxy, not a sustained-load guarantee; the 50-item run overlapped CPU-only analysis preparation.

Order: **A1 (922) → A0 (922) → withheld evidence, A1 and A0 (150 each) → context dependence, no evidence (200) → determinism rerun (30) → prepared counterfactual (100) → FinanceBench numeric 76 plus 150 wrong-company controls, A1 (226) → oracle (200), last**.

G is offline. No partial main arm supports a full headline. A block cut cannot later be restored because results look favorable. The atomic TEST_GENERATION_STARTED marker prevents an additional official run. Stop new requests on a conflicting shared-compute gpu.claim, >5% endpoint/generation error rate, or deadline. Hold workspace/gpu.claim during requests. Preserve the selected two-slot, 8192-token layout.

'''+text[end:]
 start=text.index('## Frozen file hashes');end=text.index('## Exact stage-2 commands',start)
 hashes='## Frozen file hashes\n\n'
 for label,key in [('Manifests (runs/manifests)','manifest_hashes'),('Evidence and controls (runs/frozen_v2)','evidence_hashes'),('Runtime code','code_hashes')]:hashes+=label+':\n\n```json\n'+json.dumps(p[key],indent=2)+'\n```\n\n'
 text=text[:start]+hashes+text[end:]
 text=text.replace('Only the reviewer may supply the review approval after filling the placeholder and committing.', 'Only the reviewer may supply the explicit go after reviewing the committed stage-1c result.')
 text=text.replace('analyze_v2.py --run-id','analyze.py --run-id')
 text=text.replace('<full SHA after protocol review and commit>','<reviewed stage-1c commit SHA>')
 (root/'PREREG_v2.md').write_text(text)
 dump(out/'freeze_stage1c.json',dict(PREREG_sha256=sha(text),protocol_sha256=sha((root/'protocol_v2.json').read_bytes()),headline_source_sha256=p['headline_source_sha256'],generation_scope='50 dev-2 train items only',test_generation_started=(RUNS/'TEST_GENERATION_STARTED.json').exists(),status='ready_for_protocol_review_not_authorized_to_run'))
 print(json.dumps(budget,indent=2))
if __name__=='__main__':main()
