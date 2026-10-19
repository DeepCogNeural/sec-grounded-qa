"""Write the measured protocol and review draft; does not run stage 2."""
import datetime,math,subprocess
from core import *
from qa_v2 import *
def main():
 config=json.loads((B/'selected_config.json').read_text());through=json.loads((B/'throughput_v2.json').read_text());frozen=json.loads((B/'frozen_summary_v2.json').read_text());probe=json.loads((B/'withheld_summary.json').read_text());ranking=json.loads((B/'ranking_selection_v2.json').read_text())
 summaries=[json.loads(p.read_text()) for p in sorted(B.glob('summary_*.json')) if p.name.startswith(('summary_initial_','summary_candidate','summary_revision'))]
 p=json.loads(pathlib.Path('protocol.json').read_text())
 measured=through['questions_per_hour'];capacity=math.floor(measured*.8*5.5);nprobe=probe['validated']
 plan=[('A1',922),('A0',922),('withheld_A1',nprobe),('withheld_A0',nprobe),('financebench',226),('oracle',200),('contextdep',200),('counterfactual',150),('rerun30',30)]
 included=[];cut=[];used=0
 for i,(name,n) in enumerate(plan):
  reserved=2*n if name=='withheld_A1' else n
  if used+reserved>capacity:cut=[x[0] for x in plan[i:]];break
  included.append(name);used+=n
 launches=json.loads((B/'restart_v2.json').read_text()) if (B/'restart_v2.json').exists() else None
 if launches:argv=launches['chosen_argv'];command=launches['chosen_command'];envnote='Exact original /proc environment restored; only --parallel and --ctx-size may differ.'
 else:
  ids=subprocess.check_output(['pgrep','-f','^'+str(pathlib.Path('workspace') / 'shared-compute/llama/build/bin/llama-server')],text=True).split();assert len(ids)==1
  argv=pathlib.Path('/proc',ids[0],'cmdline').read_bytes().decode().rstrip('\0').split('\0');command=__import__('shlex').join(argv);envnote='Original live process; no layout change.'
 manifests={x.name:sha(x.read_bytes()) for x in sorted(MAN.iterdir()) if x.suffix in ['.json','.jsonl']}
 (MAN/'MANIFEST.sha256').write_text(''.join(h+'  '+n+'\n' for n,h in manifests.items()))
 hashes={name:sha(pathlib.Path(name).read_bytes()) for name in ['core.py','qa_v2.py','scoring.py','retrieval.py','run.py','run_v2.py','analyze_v2.py']}
 p.update(version='stage1b-v2',freeze_status='ready_for_protocol_review',total_slots=config['concurrency'],context_per_slot=config['context_per_slot'],concurrency=config['concurrency'],max_tokens=MAX_TOKENS,stage2_hours=5.5,preflight_qph=measured,safe_qph=measured*.8,throughput_safety_factor=.8,request_capacity=capacity,max_planned_requests=sum(n for _,n in plan),planned_blocks=included,preplanned_cut=cut,run_order=[x[0] for x in plan],block_sizes=dict(plan),selected_revisions=config['selected_revisions'],retriever=config['method'],top_k=config['k'],evidence_budget='Whole-chunk shared packing until both arms, with both revision reserves, fit context minus 800 output tokens',manifest_hashes=manifests,evidence_hashes=frozen['evidence_hashes'],code_hashes=hashes,ranking=ranking['chosen'],launch_command=command,launch_argv=argv,launch_environment=envnote,withheld_summary=probe,prompt=dict(system=SYSTEM_V2,extra_by_arm={a:REVISION_EXTRA[config['selected_revisions'][a]] for a in ['A0','A1']},A0=A0_V2,A1=A1_V2),schemas={a:schema(a) for a in ['A0','A1']},evidence_directory='frozen_v2',financebench_retrieval=frozen['financebench_retrieval'],oracle_retrieval=frozen['oracle_retrieval'])
 p.pop('selected_revision',None)
 dump('protocol_v2.json',p)
 budget=dict(measured_qph=measured,safety_factor=.8,safe_qph=measured*.8,stage2_hours=5.5,capacity=capacity,max_requests=sum(n for _,n in plan),estimated_full_hours=sum(n for _,n in plan)/(measured*.8),planned_blocks=included,cut_from_tail=cut,planned_requests=used,blocks=[dict(name=n,requests=k,safe_hours=k/(measured*.8)) for n,k in plan])
 dump(B/'budget_v2.json',budget)
 def block(x,lang='json'):return '\n```'+lang+'\n'+(json.dumps(x,ensure_ascii=False,indent=2) if not isinstance(x,str) else x)+'\n```\n'
 lines=['# Grounded SEC filing QA — pre-registration v2','',
 'Development configuration is selected. This review draft supersedes PREREG_draft.md. No DocFinQA test, FinanceBench, or derived-probe generation has occurred during this stage. protocol review, headline wording, and a committed approval SHA are required before stage 2. No test-time tuning, silent reruns, or external judge is allowed. Null and incomplete outcomes remain reportable.',
 '',
 '## Headline hierarchy and negative-branch wording',
 '',
 'REVIEW_PLACEHOLDER — the reviewer must fill this section before the final pre-registration commit. The stage-2 runner refuses this placeholder.',
 '',
 '## Data and development selection',
 '',
 'Evaluation is all 922 DocFinQA test rows in 240 original-context groups. The original 100-item dev-1 manifest is unchanged. Primary development uses 200 nonempty-Program train items, seed 20261019, excluding all three fixed demonstration items and their two documents. Dev-2 has 161 document groups. FinQA train joins are 196 unique and four resolved duplicates. The previously unresolved JPM question is resolved by identical annotation payloads and its matching 2013 mortgage-loan rows in the source context. No development item is dropped.',
 '',
 'Test row test-0040 has an unparseable gold and remains wrong in the full primary denominator. Test programs and golds are used only to build manifests, retrieval diagnostics, and evidence-withheld controls, never to tune on generated test answers. The three fixed demonstrations are unchanged; one has missing evidence and demonstrates abstention, and one retains a disclosed prior-to-2019 annotation inconsistency.',
 '',
 'Selection rules were written before result selection, with the resumption amendment recorded before the first generation: initial constrained/calibrated BM25 baseline on 4 x 4096; rank retrieval/k candidates by all-operand HR, then all-gold-snippet HR; compare the top two with identical r0 prompts on all 200 items and both arms when time permits. Choose highest combined NumMatch-1%, then higher operand HR, smaller k, and BM25/dense/hybrid/rerank order. A partially measured candidate cannot win. Both arms received one common schema correction. No extra text revision was run because of the deadline. At most four revisions per arm were allowed, with equal counts; selection uses its own NumMatch-1%, then strict, fewer abstentions, earlier revision. No new revision batch starts after 23:15 UTC; hard stop 23:45 UTC.',
 block(config),
 'The complete revision log is runs/stage1b/revision_log_v2.json. Development rates are not test estimates. Initial JSON constraints and abstention instructions were introduced together; their separate causal gains are not identified.',
 '',
 '## Model, layout, and generation',
 '',
 f"Model: {p['model_alias']}; build {p['model_build']}. Chosen layout: {p['total_slots']} slots x {p['context_per_slot']} tokens. Temperature 0, seed 20261018, cache_prompt false, thinking false, max output 800 tokens; concurrency equals slots. Both arms request the same short reasoning field, at most 40 words and never over 80; the final schema caps it at 160 characters, which guarantees at most 80 whitespace-separated words. The initial 480-character baseline had 8 instruction violations, retained in raw outputs; the correction preceded shared-candidate generation. JSON schema constrains structure; truncation still counts as failure, not a valid answer. No retry after truncation or schema failure.",
 block(command,'sh'),
 'Required library search path: LD_LIBRARY_PATH=workspace/llama/build/bin:workspace/cuda-12.4/lib64. A restart preserves the full original environment and exact argv, changing only --parallel and --ctx-size. The environment is stored privately outside Git, not printed. ldd must resolve before stopping the old process. Health and one non-benchmark generation must pass within three minutes, otherwise restore the original argv/environment and keep developing with its context budget. The selected layout remains for stage 2.',
 '',
 '## Retrieval and shared evidence',
 '',
 f"Chosen DocFinQA retriever: {config['method']}, top-{config['k']}. Original-context hashes define document groups. Windows are 450 Qwen tokens, stride 360, with actual emitted lengths recorded. Lexical indexing uses bm25s Lucene defaults, English stopwords, no stemming. Dense is BAAI/bge-base-en-v1.5, CUDA float16, max sequence 512, L2-normalized document and instruction-prefixed query vectors. Hybrid reciprocal-rank fusion uses sum(1/(60+rank)), with ranks starting at one. Optional BAAI/bge-reranker-base scores the hybrid top 30 query/chunk pairs, max sequence 512, then orders that prefix before the remainder. Ties use chunk index.",
 '',
 'Only test + dev-1 + dev-2 document groups receive dense embeddings. FinanceBench remains the frozen, untuned BM25 top-5 control. The oracle uses BM25 over its FinQA gold-page pre_text/table/post_text only; it measures gain from supplied gold-page evidence and may omit gold spans due to packing.',
 '',
 'Both arms receive identical chunk bytes, ordering, question, demonstration inputs, and reasoning-length rule. Pack whole chunks until every arm with either prepared prompt variant plus 800 output tokens fits the chosen context. The unused r1 variant was reserved in packing but never evaluated or selected. Remove chunks from the end, log every removal, and retain the same evidence across revisions. Headers list locally occurring years, not semantic associations. All rendered frozen prompts are checked before stage 2. Evidence hashes appear below.',
 '',
 'Retrieval HR@5 and HR@10 are measured on all 200 dev-2 items: every nonconstant FinQA program operand (including all numeric cells of a table_* source row) appears numerically in the retrieved chunks, with comma/accounting normalization, conservative absolute signs, percent and 1e3/1e6 scalings. Also report literal operands without scaling, any/all snippet hits (at least 80% unique words and every numeric token in one chunk), denominators, and packed-evidence HR. Numeric presence and lexical overlap do not certify semantic evidence.',
 '',
 '## Exact prompts and schemas',
 '',
 'The shared system is followed by the selected extra for each arm, then the three fixed user/JSON demonstration pairs. Demonstration JSON gains reasoning: "A required number is absent." for abstention and "Use the quoted values in the requested arithmetic." otherwise. The last user message contains the arm instruction, Evidence, packed chunks separated by blank lines, then Question. The exact renderer is qa_v2.messages_v2.',
 block(p['prompt']),
 block(p['schemas']),
 'Fixed demonstrations, including all original output fields:',
 block([{k:d[k] for k in ['item_id','question','evidence','A0','A1']} for d in readl(MAN/'demos_train.jsonl')]),
 '',
 '## Scorers and gate G',
 '',
 PARSER_RULE,
 '',
 'A0 supplies its own arithmetic answer. A1 executes an AST restricted to numeric literals, declared operand names, unary signs, parentheses, +,-,*,/. Calls, attributes, comparisons, powers, duplicate names, booleans, undeclared names, nonfinite values, division by zero, expressions over 2000 characters, and ASTs over 100 nodes fail. Percent type means percentage points; yes/no execution must equal 1/0.',
 '',
 'NumMatch-1%: p or, only if p/g has a percent flag, p,100p,p/100 must differ from g by <=1% of abs(g); zero uses absolute tolerance .005. Yes/no is exact. NumMatch-strict removes scale candidates. FinQA agreement uses five-decimal execution equality with the pre-existing reference-only percent-unit rule; this never replaces DocFinQA gold. Every abstention, invalid program, invalid JSON, truncation, unsent-over-budget output, or filtered output is wrong for overall accuracy and excluded from its corresponding answered precision.',
 '',
 'G accepts only an answered A1 output whose every operand quote, after whitespace, thousands-comma and accounting-negative normalization, is an exact case-sensitive substring of a supplied chunk, at least 20 characters long, contains the numeric value, and has its year/quarter in the quote or chunk header. Units must be nonempty; declared names must execute. Report every failure category. G does not verify operation, entity, semantic period association or unit correctness. No knows-when-it-does-not-know claim is permitted.',
 '',
 f"Ranking is {ranking['chosen']}, descending, chosen on selected A1 dev-2 by minimum AURC among fully available program-token mean logprob, top-1 BM25 score, and operand count. Equal values remain a threshold group; fractional weighting at a coverage boundary equals expected uniform tie ordering. Compare risk/precision at common coverage, never split a tie using correctness.",
 '',
 '## Withheld evidence and FinanceBench controls',
 '',
 f"Withheld set: {nprobe} of target 150; seed 20261018. Same test question and document, no answer generation. Remove every ranked chunk containing any nonconstant gold program operand under normalized numeric forms and factors 1, .01, 100, .001, 1000, .000001, 1000000; signs are conservatively ignored. Take the top remaining k and apply shared packing. Verify operand absence in supplied text and headers. Reject any question that itself contains a gold operand or scaled variant, empty/text-only controls, nonnumeric/zero golds, unresolved joins, direct scaled gold presence, and gold derivable by the explicit finite numeric check.",
 '',
 'The finite derivability check includes question text, evidence text, and headers. It enumerates all present numeric values and pairwise +, -, *, /, comparing absolute results against gold at the same scales, tolerance 1e-9. It is deliberately stronger than direct gold absence, but does not prove absence of arbitrary multi-step arithmetic or semantic derivations. These are validated-under-the-stated-check synthetic omission controls, not certified universally unanswerable filings. Full per-item checks and excluded chunk IDs are retained; this limitation applies to H3.',
 '',
 'Gold is abstain. Evaluate both arms; report explicit abstention, valid false answers, invalid responses, and A1+G false acceptance separately. Invalid JSON/programs are not counted as explicit refusals. The trivial baseline uses matched company and FinQA filing year: refuse any asked year outside [year-2,year] for 10-K; same-document controls can still fail this period baseline. Report the subset it passes, with its actual denominator.',
 '',
 'Keep 76 parser-selected FinanceBench answerable IDs and 150 wrong-company easy probes, with frozen metadata baseline and historical comparisons. Drop the six old same-company/different-period probes: none passes the trivial filter, below the required 50 informative items. No FinanceBench tuning or generation occurred. Historical human-label accuracies and same-parser re-scores use exactly the 76 IDs and remain different protocols.',
 '',
 '## Diagnostics, intervals and hypotheses',
 '',
 'Oracle: fixed 200 joined items, compare to A1 on identical IDs; disclose packing and errors despite gold evidence. Context dependence: fixed 200 test items, A0 without current evidence and unchanged demonstrations; compare to A1 on identical IDs.',
 '',
 'Counterfactual: at most 150 shuffled eligible A1-correct numeric test items (seed 20261018), with all extracted operand values present. Exclude period-year operands, yes/no, and indistinguishable new gold. Alternate factors 1.3/0.7 over distinct values in declaration order; replace every occurrence, recompute gold with the original program, and report new/old-gold matching. This is a synthetic intervention on an outcome-selected subset. The 30-item A1 rerun is the only planned direct repeat; require >=28/30 parsed-value/type/abstention agreement or disclose nondeterminism.',
 '',
 'Report descriptive Wilson 95% question intervals. All paired accuracy and precision differences use 2000 filing-level bootstrap draws, seed 20261018, sampling original context groups with replacement, retaining all questions, and percentile 2.5/97.5 bounds. Disclose omitted undefined precision draws. Random-gate null: 1000 draws from answered A1 at exactly G accepted count; report null distribution and (1+count(null>=observed))/1001. No LLM judge.',
 '',
 '| ID | Threshold | Failure or scope |',
 '|---|---|---|',
 '| H0 | A1−A0 NumMatch-1% on all 922: point >=5 pp and lower filing CI >0 | Point <=0: no gain from code execution; otherwise report uncertainty. Both complete arms required. |',
 '| H1 | G precision−A1 accuracy >=15 pp, lower CI >5 pp, G coverage >=50%, random-gate null reported | Report point and coverage; no knowledge-of-uncertainty claim. |',
 '| H2 | Counterfactual new-gold match >=70%; no-evidence accuracy <=0.5 x A1 on same 200 | New-gold match <50% requires recall caveat. Cut, empty, or incomplete diagnostics are not estimable. |',
 '| H3 | A1+G false acceptance <=10% on withheld probes passed by trivial baseline, with full-test answerable G coverage >=70% | >25% permits no abstention claim. Both probe arms must be complete. Report raw A0/A1, invalid responses and finite-validation limits alongside. |',
 '| H4 | Oracle minus A1 on identical 200 IDs, descriptive | Gain from supplied gold-page evidence, not causal decomposition. |',
 '',
 'The historical 42.6% GPT-3.5 plus FT-ColBERT result is a protocol-different reference, never a beaten baseline. Preserve nulls, parse/truncation failures and error audits.',
 '',
 '## Capacity, run order and cut rule',
 block(budget),
 'Use the measured 20-dev A1 throughput at the frozen layout with an 0.8 safety factor, not a sustained-load guarantee. Stage 2 is capped at 5.5 hours. Drop complete blocks from the bottom until the plan fits. Reserve both withheld arms together before starting either. Before each block, require both request capacity and remaining time at safe_qph; otherwise drop it and every later block. No partial main arm supports a full headline. A block cut cannot later be restored because earlier results look favorable.',
 '',
 'Order: A1 922 → A0 922 → withheld A1 then A0 → FinanceBench numeric 76 then easy 150 (A1) → oracle 200 → context-dependence 200 → counterfactual <=150 → rerun30. G is offline. The atomic TEST_GENERATION_STARTED marker prevents an additional official run. Stop new requests on a conflicting shared-compute gpu.claim, >5% endpoint/generation error rate, or deadline. Hold workspace/gpu.claim during load. Do not restore the selected layout until after stage 2.',
 '',
 '## Frozen file hashes',
 '',
 'Manifests (runs/manifests):',
 block(manifests),
 'Evidence (runs/frozen_v2):',
 block(frozen['evidence_hashes']),
 'Runtime code:',
 block(hashes),
 '',
 '## Exact stage-2 commands',
 '',
 'Not executed. Only the reviewer may supply the review approval after filling the placeholder and committing. The runner checks the exact clean HEAD, committed PREREG_v2, missing placeholder, code/manifest/evidence hashes, model, slot count, and context.',
 block("ssh compute-host\ncd workspace/sec-grounded-qa\nexport HF_HOME=workspace/cache/huggingface\nREVIEWED_COMMIT='<full SHA after protocol review and commit>'\nworkspace/venv/bin/python run_v2.py --reviewed-commit \"$REVIEWED_COMMIT\" --prereg-approved --run-id stage2-v2-20261018\nworkspace/venv/bin/python analyze_v2.py --run-id stage2-v2-20261018 > workspace/logs/stage2-v2-analysis.log",'sh'),
 ]
 pathlib.Path('PREREG_v2.md').write_text('\n'.join(lines)+'\n')
 dump(B/'freeze_completion.json',dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_sha256=sha(pathlib.Path('protocol_v2.json').read_bytes()),prereg_sha256=sha(pathlib.Path('PREREG_v2.md').read_bytes()),status='development_frozen_pending_main_headline_and_commit',test_generation_marker_exists=(RUNS/'TEST_GENERATION_STARTED.json').exists(),stage2_started=False))
 print(json.dumps(budget),flush=True)
if __name__=='__main__':main()

