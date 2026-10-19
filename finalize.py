"""Produce the reviewable draft and frozen protocol from written artifacts."""
import datetime,subprocess
from core import *
from scoring import distribution
from manifests import hashes

def main():
 ms=json.loads((RUNS/'manifest_summary.json').read_text());pre=json.loads((RUNS/'preflight_summary.json').read_text());dev=json.loads((RUNS/'dev_summary_r0.json').read_text());rank=json.loads((RUNS/'ranking_selection.json').read_text());idx=json.loads((RUNS/'index_summary.json').read_text());tokens=json.loads((RUNS/'frozen_token_summary.json').read_text());evhash=json.loads((RUNS/'frozen_evidence_hashes.json').read_text());demos=readl(MAN/'demos_train.jsonl');props=json.loads((RUNS/'server_props.json').read_text())
 selection=json.loads((RUNS/'revision_selection.json').read_text());devs={v:json.loads((RUNS/f'dev_summary_{v}.json').read_text()) for v in ['r0','r1']};dev=devs[selection['chosen']];pre1=json.loads((RUNS/'preflight_r1_summary.json').read_text());cut_qph=selection['cut_qph']
 capacity=int(cut_qph*.8*4.5);planned=922+922+ms['financebench_numeric']+ms['hard_probes']+150+200+200+150+30
 protocol=dict(seed=SEED,model_alias=props['model_alias'],model_build=props['build_info'],total_slots=4,context_per_slot=4096,temperature=0,cache_prompt=False,enable_thinking=False,max_tokens=650,concurrency=4,stage2_hours=4.5,preflight_qph=cut_qph,selected_revision=selection['chosen'],throughput_safety_factor=.8,request_capacity=capacity,max_planned_requests=planned,ranking=rank['chosen'],ranking_direction='descending',run_order=['A1','A0','financebench','oracle','contextdep','counterfactual','rerun30'],manifest_hashes={k:v['sha256'] for k,v in hashes().items()},evidence_hashes=evhash,prompt=dict(system=SYSTEM,A0=A0,A1=A1),parser_rule=PARSER_RULE,chunk_tokens=450,stride=360,evidence_budget=2600,top_k=5)
 dump('protocol.json',protocol)
 table='\n'.join('| '+name+' | '+str(v['rows'] if v['rows'] is not None else ms['financebench_numeric'])+' | `'+v['sha256']+'` |' for name,v in hashes().items())
 commands='''ssh compute-host
cd workspace/sec-grounded-qa
export HF_HOME=workspace/cache/huggingface
REVIEWED_COMMIT='<full SHA committed and approved by the reviewer>'
workspace/venv/bin/python run.py --reviewed-commit "$REVIEWED_COMMIT" --prereg-approved --run-id stage2-20261018
workspace/venv/bin/python analyze.py --run-id stage2-20261018 > workspace/logs/stage2-analysis.log'''
 text=f'''# Grounded SEC filing QA — pre-registration draft

Draft for protocol review. Stage 1 is finished. No test or FinanceBench generation is authorized by this draft. The reviewer must review and commit this document before stage 2. Nothing below may change after that commit. All evaluation and diagnostic outputs, including null results, will be retained. No LLM-as-judge is used.

## Scope and immutable design

Model: `{props['model_alias']}`; build `{props['build_info']}`. The existing server is unchanged: four slots, 4,096 tokens each. Generation is temperature 0, seed 20261018, `cache_prompt=false`, `chat_template_kwargs={{"enable_thinking": false}}`, concurrency 4, and at most 650 output tokens. No resize, restart, paid API, second model, test-time prompt tuning, or FinanceBench tuning is permitted.

DocFinQA test is the full 922-row evaluation set. Dev is the fixed 100-row sample drawn by Python `random.Random(20261018).sample` from source order. Two prompt versions were evaluated: r0 on 100 paired items, then one shared-system revision r1 on the first 50 of that same seeded sample. The 20-request r0 A1 preflight is reused; total unique generation requests are 300 over 100 unique dev items. Before r1 generation, the selection rule was written: compare combined A0+A1 NumMatch-1% correct counts on the same 50 items; ties favor fewer unparseable outputs, then retain r0. The selected version is {selection["chosen"]}; ranking uses its {selection["final_sample_n"]} paired dev items. The only prompt edit requires valid JSON escaping and replaces literal tabs/newlines inside strings with spaces. The r0 failure counts remain visible. Full prompts and revision reasons are retained in prompt_revision_log.json; no other prompt revision was used. Three fixed train items are `train-2200`, `train-3534`, and `train-0700`, sampled with the same seed from nonempty Python programs having 2–4 numeric literal occurrences. This counts arithmetic constants, and the rendered A1 examples bind financial operands separately.

The first demonstration has unavailable financial operands in its paired context and therefore demonstrates abstention. Its source program and answer are retained. The second retains a source annotation inconsistency: the question says prior to 2019, while its program includes 2019. No alternative train examples were selected after inspecting dev results.

One malformed DocFinQA gold, `test-0040`, has no unambiguous parsed number. It remains in the 922-item denominator and is wrong under NumMatch for every output. Its raw label remains available; FinQA execution agreement is separate and never substitutes a new DocFinQA gold. Empty source Program fields never indicate unanswerability.

## Frozen manifests

Files reside in `workspace/runs/manifests/`; `MANIFEST.sha256` records their exact byte hashes. Test IDs are original source positions `test-0000` through `test-0921`. Context hashes use exact original UTF-8 Context bytes; `doc_group` is that hash. Test has 240 groups. All frozen item lists are the complete contents of the following files, identified by these hashes.

| File | Rows or numeric IDs | SHA-256 |
|---|---:|---|
{table}

FinQA matching uses lowercase and collapsed whitespace, searching `dataset/test.json` first and consulting dev/train only for missing questions. The resulting 915 unique matches and seven duplicated annotations cover all 922 rows. For each duplicate, execution answer, document company/year, program, gold spans, and pre_text/table/post_text are checked. The two payloads are identical; the lexicographically smallest FinQA ID is the canonical representative, and both candidates plus agreement evidence are retained. This is equivalence resolution, not unchecked first-match selection.

Oracle and context-dependence each use their fixed 200-item seeded lists. The deterministic rerun samples 30 rows from the complete test list with the same seed. It compares parsed values rounded to five decimals, percent/yes-no flags, and abstention/truncation states; exact text agreement is also reported. At least 28/30 agreement is required, or nondeterminism is disclosed.

## Retrieval and evidence

DocFinQA contexts are deduplicated by original context hash. Literal backslash-n/backslash-t sequences are restored to whitespace before indexing. Each context is tokenized with the running Qwen `/tokenize` endpoint, split into 450-token windows with stride 360 (20% overlap), and every emitted chunk is retokenized to record its actual length. The original token start/end positions and chunk ID are retained.

FinanceBench uses PyMuPDF page text from its 84 question documents, with zero-based page numbers preserved and no window crossing a page boundary. Extraction is deterministic; no OCR is added. Each original document has a separate BM25 index. The index uses `bm25s` Lucene defaults, k1=1.5, b=0.75, English stopwords, no stemming. Dense retrieval is not built or selected; its improvement is not measured.

Retrieve top five chunks within the document only. Sort returned ties by chunk index, then append complete chunks in score order until the total rendered evidence is at most 2,600 Qwen tokens. Log every dropped chunk. Chunk headers identify document/chunk/page and enumerate year tokens present in that chunk. Header years indicate local occurrence, not a semantic link between a specific number and year. A0 and A1 use exactly the same packed evidence bytes, order, question, system instruction, and three demonstration inputs. Only output schema/instructions and demonstration outputs differ.

Frozen evidence files and all rendered token counts live in `workspace/runs/frozen/`. Their hashes are embedded in `protocol.json`. Stage 1 retrieved and rendered test/FinanceBench/oracle prompts without calling completion endpoints. Evidence-page hit rate is an exact page-number comparison for answerable FinanceBench items.

Dev HR@5 is operationalized for FinQA's paraphrased/table-linearized gold snippets: at least one gold snippet has at least 80% unique token recall and all its numeric tokens in one retrieved chunk. Report all-snippet hit rate and literal normalized-substring hit rate beside it. This is a retrieval diagnostic, not a proof that the question is answerable.

The oracle arm indexes only each joined FinQA example's pre_text, table, and post_text, with the same chunking and top-five packing. It estimates gain from supplied gold-page evidence. Packing may omit some gold spans; all-gold snippet hits and errors despite those hits are reported. It is not a causal decomposition or an assumption of perfect oracle packing. Context-dependence uses A0 with no current-question evidence, while retaining the same demonstrations.

## Exact prompts

System message, shared by both arms:

```text
{SYSTEM}
```

Final user message for A0 is this instruction, followed by `Evidence:\\n`, the frozen packed chunks, and `Question: ` plus the source question:

```text
{A0}
```

Final user message for A1 follows the identical arrangement:

```text
{A1}
```

Demonstrations appear as three user/assistant pairs. Each user message is exactly `Evidence:\\n{{evidence}}\\nQuestion: {{question}}`. Each assistant message is compact JSON (`ensure_ascii=False`, separators comma/colon). Exact demonstration data:

```json
{json.dumps([{k:d[k] for k in ['item_id','question','evidence','A0','A1']} for d in demos],ensure_ascii=False,indent=2)}
```

The current chat template is rendered by `/apply-template`; token counts use `/tokenize`. No chain-of-thought or explanation is requested. Non-JSON prose/markdown is unparseable. The server's `finish_reason=length` is a failure even if a usable JSON prefix exists; no silent retries are allowed.

## Parser, safe evaluator, and scorers

Frozen parser rule: {PARSER_RULE}

A0 predictions use `answer` plus the percent flag in `unit`. A1 predictions execute `program` over the declared numeric operands; `answer_type=percent` marks percentage points. Yes/no execution must yield exactly 1/0. The evaluator permits numeric literals, declared operand names, parentheses, unary +/- and binary +, -, *, /. It forbids calls, attributes, subscripts, comparisons, booleans, powers, undeclared names, duplicate names, nonfinite values, division by zero, expressions longer than 2,000 characters, and ASTs exceeding 100 nodes.

- **NumMatch-1%** (primary, ours): compare parsed prediction p to gold g. Candidate scales are p only, or p, 100p, p/100 when either carries a percent flag. Correct iff absolute difference is at most 0.01 times abs(g), or abs(candidate) <= 0.005 when g=0. Yes/no is exact. No other unit-scale forgiveness is used.
- **NumMatch-strict**: identical tolerance and yes/no rule, with no scale candidates.
- **FinQA execution agreement**: prediction rounded to five decimals equals `qa.exe_ans`, on the resolved joined set. Percentage-point predictions are converted using the per-item `prediction_percent_to_finqa_scale`, fixed before generation. This is 0.01 or 1 according to the reference FinQA percent answer/execution-unit relationship; the choice never depends on a model prediction. Nonpercent predictions receive no conversion. The official numeric equality rule is retained; source rounding and unit heterogeneity remain visible.

Abstain, filtered, unparseable, context-over-budget, and truncated outputs are not answered: wrong for accuracy, excluded from precision. Every test row remains in primary accuracy, including the malformed gold. Filtered rows are excluded only from gated precision, never silently removed from accuracy denominators.

## Evidence-validation gate G and ranking

Accept an A1 result only if it parses, executes, does not abstain/truncate, and every operand has a normalized quote of at least 20 characters that occurs verbatim in a retrieved chunk. Normalization collapses whitespace, removes numeric thousands commas, and maps accounting parentheses to negative numbers, including optional currency signs. Matching remains case sensitive. The quote must contain the operand's numeric value (numeric equality tolerance 1e-9), and its declared year/quarter token must appear in that quote or its chunk header. Units must be nonempty strings, but unit correctness is not semantically verified. All program names must be declared operands.

Failure categories include not_found, too_short, value_absent, period_absent, undeclared_name, missing_operands, invalid_operand, invalid_program, arithmetic_error, unit_missing, invalid_json, and abstain. G verifies evidence-form constraints; it does not prove the chosen operation, entity, year association, unit conversion, or answer is correct. No claim that the model knows when it does not know will be made.

Dev selected ranking: **{rank['chosen']}**, descending. Candidates were mean logprob of tokens overlapping the JSON program string, top-1 BM25 score, and number of operands. Selection minimizes dev AURC among candidates available for all answered A1 cases. Equal AURC ties use that candidate order. Equal scores form one threshold group; fractional weights at a boundary produce expected uniform tie ordering. Curves compare both pipelines at common coverage in 5-percentage-point steps, plus the largest shared coverage. Abstentions/unparseable outputs do not enter ranked answered pools. G's unthresholded coverage is c*, not an optimized test threshold.

## FinanceBench and probes

The numeric answerable subset has {ms['financebench_numeric']} IDs under the frozen parser, independent of question type. This parser-based subset is not a semantic certification that every question requests a number; prose references with one explicit quantity can be included. Historical GPT-4-Turbo single-store and Llama2 single-store human-label accuracies use exactly these IDs and are labelled different scoring protocol. Same-parser `model_answer` rescoring and parse failures are reported separately; these numbers are not an apples-to-apples generated-model comparison.

Hard replacement documents must have the same metadata company and doc_type but a different doc_period. Validation scans normalized replacement text for the gold numeric value in equivalent comma/decimal/parentheses formatting and scales 1, 1e-3, 1e-6, 1e3, 1e6 (also 0.01 and 100 for percent gold). Absolute values are checked conservatively, so a sign difference cannot certify absence. Every asked four-digit year must be absent within 300 characters of every occurrence of the question's financial metric nouns. Metric nouns are the exact deterministic financial lexicon intersection recorded per candidate; items with no metric noun, no year, or no numeric gold are excluded. Every retained probe records text hash, variants, token counts, year/metric occurrences and minimum distances. This validation is an explicit heuristic for synthetic probes, not a proof that no arithmetic answer can exist.

The fixed set contains {ms['hard_probes']} validated hard probes; **{ms['hard_trivial_pass']} survive the trivial filter**. Thus the key H3 denominator is empty and H3 is not estimable with this frozen set. No zero-denominator rate will be reported as 0% or as success. The 150 easy probes use a seed-20261018 question permutation with every replacement from a different company.

Trivial filter: refuse iff normalized company differs or any asked year is outside [doc_period-2, doc_period] for 10-K, [doc_period-1, doc_period] otherwise. Its verdict is recorded for all 150 answerable questions, every hard probe, and every easy probe. Model generations cover numeric answerable items only; the metadata baseline covers all 150. Hard/easy false-answer rate is the fraction accepted by A1+G; underlying A1 answer rate is also reported. Answerable coverage uses the numeric subset.

## Counterfactual diagnostic

After the fixed primary/auxiliary runs, consider A1-correct numerical test items whose declared operand values occur in the supplied evidence. Shuffle candidate IDs with seed 20261018. Exclude yes/no items, missing operands, operands equal to their declared period year, and interventions whose recomputed gold cannot be distinguished from the old prediction under NumMatch-1%. Retain at most 150.

Assign factors 1.3, 0.7, 1.3, 0.7 to distinct operand values in declaration order. Equal repeated values share one factor. Replace all matching numeric-token occurrences in the supplied evidence, normalize numeric formatting, retain the original question and program for recomputing gold, and rerun the same A1 prompt. Explicit arithmetic constants in the program are unchanged. Record every replaced value/count, new operands, new gold, and exclusion reason before generation. Report shares matching new and old gold. This is a synthetic intervention on an outcome-selected eligible subset, not all-test causal accuracy.

## Statistics and hypotheses

Question-level Wilson 95% intervals (z=1.959963984540054) are descriptive. Paired differences use 2,000 filing-level bootstrap draws, NumPy default_rng seed 20261018: sample the original number of distinct context hashes with replacement, retain all questions in each sampled group, and recompute the question-weighted statistic. Report percentile 2.5/97.5 bounds. For gated precision draws with no accepted answers, omit undefined draws and disclose the valid-draw count. All headline/auxiliary differences and precision gains use filing-level intervals; no independent-question bootstrap replaces them.

The random-gate null uses 1,000 draws, seed 20261018, sampling without replacement from valid A1 answers at exactly G's accepted count. Report its precision distribution and one-sided `(1 + count(null >= observed))/1001`. Risk-coverage curve points are descriptive at matched coverage; no unsupported difference claim is inferred from unmatched coverage.

| ID | Metric and pass rule | Failure/limit wording |
|---|---|---|
| H0 | NumMatch-1% A1 minus A0 on all 922; point >= +5 pp and lower 95% filing bound > 0 | Point <= 0: no gain from code execution; otherwise report threshold/uncertainty honestly |
| H1 | G precision minus A1 accuracy at c*; gain >=15 pp, lower bound >5 pp, coverage >=50%; matched-count random-gate null reported | Report point/coverage; no knows-when-it-does-not-know wording |
| H2 | Counterfactual new-gold match >=70% and context-dependence accuracy <=0.5 times A1 on the same fixed 200 IDs | New-gold match <50% requires a recall/memorisation caveat; empty diagnostic is not estimable |
| H3 | False-answer rate <=10% on validated hard probes passed by trivial filter, with numeric answerable coverage >=70% | >25% permits no abstention claim; current informative n=0 means not estimable |
| H4 | Oracle 200 minus A1 on identical IDs, with wrong answered and parse-failure counts | Descriptive gain from supplied gold-page evidence, not causal decomposition |

The historical 42.6% DocFinQA result (GPT-3.5 plus FT-ColBERT, generated programs) is a historical reference under another protocol, never a beaten baseline. Any comparison in a headline must identify identical items and scorer on both sides. Nulls, truncation, parser failures, wrong-year/unit/operation/entity audits, and limits of probe eligibility must remain visible.

## Measured capacity, cut, order and execution

Real 20-dev A1 preflight: {pre['questions_per_hour']:.6f} questions/hour over {pre['wall_seconds']:.6f} seconds, concurrency 4. All finish reasons were stop, no server errors. This exceeds the historical synthetic 732/hour by a factor of {pre['ratio_to_reference']:.6f}; outputs are shorter, so it is not a sustained-load guarantee or a pure hardware speed comparison.

The first 20 r1 A1 requests measured {pre1["questions_per_hour"]:.6f} questions/hour over {pre1["wall_seconds"]:.6f} seconds, without extra requests. The capacity estimate uses the predeclared conservative minimum of both measured rates: {cut_qph:.6f} questions/hour.

Stage-2 capacity is floor(preflight_qph * 0.8 * 4.5 hours) = **{capacity} requests**. Maximum planned requests are **{planned}**. {"No arm is cut initially." if capacity>=planned else "The request cap may cut trailing arms; preserve the fixed order and whole-arm cut rule."} Before each arm, require both remaining request capacity and remaining wall time at 80% of measured throughput to fit the complete arm. Otherwise cut that arm and all later arms. No partial arm is relabelled complete; no full 922-item headline exists unless both primary arms finish. Final token preflight has {tokens["test"]["over_budget_by_arm"]["A1"]} test A1 prompts and {tokens["financebench-easy"]["over_budget_by_arm"]["A1"]} easy-probe A1 prompts above 4,096 when reserving 650 output tokens; all dev prompts fit. An over-budget individual prompt is recorded as not sent/wrong without truncating evidence or silently changing the prompt.

Run exactly once in this order: A1 922, A0 922, FinanceBench numeric answerable then hard then easy probes, oracle 200, context-dependence 200, counterfactual <=150, and 30-item A1 rerun. G is computed offline on A1; it is not an extra generation arm. `TEST_GENERATION_STARTED.json` is atomically created at run start to prevent another official test run under a different output directory. The deliberate final rerun is the only repeat.

Before load and during requests, check `workspace/**/gpu.claim`. Hold `workspace/gpu.claim` while requesting, remove it on exit. Stop on any conflicting claim, generation or total endpoint error rate greater than 5%, or the stage deadline. In-flight responses may finish, but no new request is issued after a stop. Dev token-budget failure in more than 5% of items is an immediate stage-1 stop. Server process/configuration stays read-only.

Commands below are exact except for the future protocol review SHA, which cannot be filled by the draft author. The `--prereg-approved` flag is supplied only after that review and commit. These commands have **not** been executed during stage 1.

```sh
{commands}
```

The runner checks a clean tree, exact reviewed HEAD, committed pre-registration, all manifest/evidence hashes, model alias, slot count and context size. Raw outputs and derived analyses stay in `workspace/runs/stage2-20261018/`.
'''
 pathlib.Path('PREREG_draft.md').write_text(text)
 summary=dict(status='stage1_complete',manifests=ms,preflight=pre,dev=dev,dev_revisions=devs,revision_selection=selection,preflight_r1=pre1,ranking=rank,index=idx,frozen_token_summary=tokens,protocol=protocol,unit_tests_log=str(ROOT/'logs/unit_tests.log'),prereg_path=str(pathlib.Path.cwd()/'PREREG_draft.md'),stage2_commands=commands,stage1_elapsed_seconds=time.time()-json.loads((RUNS/'stage1_timing.json').read_text())['start_epoch'])
 dump(RUNS/'stage1_summary.json',summary)
 print('DRAFT_READY',planned,capacity,rank['chosen'])
if __name__=='__main__':main()
