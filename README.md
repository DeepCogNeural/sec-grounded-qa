# Grounded QA over SEC filings

**On 150 constructed figure-removal probes, A1 (extract-and-compute) declined 84.7%; A0 (direct answering) declined 87.3%. A1’s matched retrieval-score gate declined 67.3%.** Probe validation is a bounded numeric check, not proof of unanswerability. On the same 922 questions and evidence, A1 scored 45.1% versus A0’s 47.9%; the FinQA scorer reversed the ranking. These are the headline and null result selected by rules frozen before test generation.

Post hoc, descriptive scorer disagreement: NumMatch-1% vs FinQA flips on 91/922 A1 and 133/922 A0 items; 77/91 of the A1 flips are percent-type predictions.

Both arms were instructed to abstain only when a required number was missing, not merely because arithmetic or unit conversion was needed. On the main set, “unjustified” abstentions with all gold figures numerically present were A1 117/922 = 12.7% and A0 128/922 = 13.9% of all questions. The gate above matches A1’s main-set non-refusal coverage.

**Question:** Does extracting financial figures and computing in code improve on answering directly, and can evidence checks select reliable answers?

**System:** question + full filing → shared BM25 top-10 evidence → the same local 4-bit Qwen3.8-27B → **A0:** direct answer, or **A1:** extracted numbers + restricted arithmetic execution → optional **G:** quote, number, period and program validation.

**Data:** all 922 DocFinQA test questions from 240 filing groups; configuration selected on 100 DocFinQA dev-split questions in stage 1 (prompt revision, retrieval and ranking), then 200 separate training questions in stages 1b/1c (final configuration). The main A0/A1 comparison receives identical evidence. This was one frozen evaluation run, including the planned 30-item repeat. The full run completed all 2,900 requests in 4 h 50 min, with no generation errors or budget cuts.

| Frozen test result | Estimate |
|---|---|
| Primary accuracy, direct / execute | 47.94% / 45.12%; paired difference −2.82 pp, 95% CI [−4.76, −0.99] |
| Frozen H0 verdict | **Scorer-dependent Tie**: FinQA agreement reverses the sign (+3.25 pp); not statistical equivalence |
| G precision / coverage | 68.03% / 52.93%; gain over direct answers only +1.67 pp [−1.57, 4.93]; H1 fails |
| Counterfactual / no-evidence controls | A1 followed substituted figures in 75 of 100 edited-evidence cases (81 filings); A0 refused all 200 no-evidence questions; H2 passes |

[Full results and intervals](RESULTS.md) · [Frozen rules](PREREG_v2.md) · [Numeric evidence](results/) · [Figures](figures/)

## What did not work

- Extracting numbers and executing a program reduced primary accuracy. The alternative scorer reverses the direction, so the frozen rule prevents a winner claim.
- G retained 332 correct and 156 wrong answers. Its precision gain did not meet even the partial H1 threshold.
- G declined 92.0% of withheld probes, but its retrieval-score control already declined 82.7%. The 9.33 pp advantage misses the required 10 pp.
- A1 had 36 unparseable/invalid-program outputs and one truncation. Matching operand values did not guarantee the right operation.
- FinanceBench answerable accuracy was 17/76 (22.37%). All wrong-company controls were also rejected by a trivial metadata filter.

## Read the figures

![Paired accuracy and scorer dependence](figures/a_paired_accuracy.png)

The bars compare all-item accuracy. The right panel shows A1 minus A0 with filing-bootstrap intervals. Blue denotes A0, red A1, and cyan A1+G throughout. These are held-out test evaluations after development selection.

The remaining figures show [error counts](figures/b_error_categories.png), [risk versus valid-answer coverage](figures/c_risk_coverage.png), [withheld-probe declines](figures/d_withheld_declines.png), and [counterfactual and no-evidence controls](figures/e_context_dependence.png). Values are labelled; SVG copies accompany the PNGs.

## Limitations and protocol-labelled related work

This experiment uses one **4-bit local model**, one selected retriever and one fixed prompt pair. It does not identify effects across models, quantization levels or independent prompt searches. A1 includes a self-answer field and longer structured output, so this tests an extract-and-execute pipeline, not an isolated arithmetic-engine switch. There is no same-protocol stronger-model or API-model reference; no paid API was a design rule.

DocFinQA questions are **FinQA-derived**. Training-set exposure or memorisation cannot be ruled out. A0 refused all 200 no-evidence questions; that could reflect the instruction to refuse, not inability to recall. The no-evidence arm is A0 while the comparison arm is A1, as frozen. Counterfactual follow rate supports sensitivity to supplied numbers but does not prove semantic understanding.

On the same 200 questions, supplying gold-page evidence increased A1 accuracy from 48.5% to 67.5% (+19.0 pp), with 65 errors remaining. This shows substantial room to improve evidence retrieval; it does not establish retrieval as the dominant source of error. A1 was wrong on 341/752 main-set questions with all gold figures numerically present. Oracle prompts averaged 2,253.695 tokens (200 questions), versus 5,819.009 for main A1 prompts (922 questions), a 3,565.314-token difference. These are different-sized sets, not a paired token-length comparison; the oracle also changes context length. See [oracle details and sources](RESULTS.md#context-counterfactual-oracle-and-determinism).

Numeric operand presence does not prove that the right entity, period or unit was retrieved. G does not validate the operation or semantic association. One unparseable gold remains wrong in the 922-item denominator; seven items lack usable operand annotations. Bootstrap intervals cluster by 240 original-context groups; descriptive Wilson intervals do not model those dependencies.

| Reference / protocol label | Reported result | Why it is not a paired baseline |
|---|---:|---|
| [DocFinQA (arXiv:2401.06915v2), Table 2](https://huggingface.co/papers/2401.06915), GPT-3.5 + FT-ColBERT | 42.6% | Full test set; retrieved filing chunks, few-shot Python-program generation, with context/shot configuration selected on dev (Section 4 and Appendix L, Table 4). Historical answer accuracy under that protocol, not this run’s NumMatch-1% scorer or a paired baseline. |
| FinanceBench historical GPT-4-1106-preview singleStore, human labels on the fixed 76 IDs | 37/76 = 48.68% | Different model, generation and human scoring |
| Same saved GPT-4 outputs, current numeric parser on the same IDs | 10/76 = 13.16%; 57 parse failures | Same parser, different output format and generation protocol |
| FinanceBench historical Llama2 singleStore, human labels on the fixed 76 IDs | 26/76 = 34.21% | Different model, generation and human scoring |
| Same saved Llama2 outputs, current numeric parser on the same IDs | 9/76 = 11.84%; 60 parse failures | Parser failure dominates this retrospective comparison |
| This run, A1, untuned FinanceBench BM25 top-5, numeric parser | 17/76 = 22.37% | Local numeric subset, not the published full benchmark |

The historical DocFinQA reference is not a beaten baseline. A0 reaches 47.94% with this protocol, and 43.28% under FinQA agreement; neither supports cross-protocol superiority.

**Constructed probes and validation.** Both arms were instructed to abstain when a required number was missing; probe declines measure instruction-following under constructed omission. The matched retrieval-score control supplies the comparison. On the ordinary main set, refusals despite all gold figures being numerically present were A1 117/922 = 12.7% and A0 128/922 = 13.9% of all questions. Numeric presence does not certify semantic sufficiency.

The 150 withheld probes remove chunks containing gold operands and scaled variants. Validation checks the question, headers and supplied evidence for operands, direct gold and finite pairwise arithmetic derivations. It cannot exclude arbitrary multi-step or semantic derivations. These are omission controls, not certified unanswerable filings. Removal lowers retrieval scores, making the τ control essential.

Counterfactuals replace operands by seeded ±10–30% changes, preserve numeric formatting, replace literal occurrences, and recompute gold through the original program. All 100 selected items passed format, program and token-budget checks before answer generation; exclusions were fixed then. All 150 wrong-company FinanceBench controls are rejected by the trivial metadata filter.

## Reproduce

The repository contains code, figures and numeric-only score tables. It excludes full DocFinQA contexts, raw responses, test prompts containing filing text, and FinanceBench PDF text. The fixed three training demonstrations in `PREREG_v2.md` and `make_demos.py` retain short FinQA training questions and SEC filing excerpts. Raw outputs and licensed source data are required for the full frozen analysis. No paid API is used.

For the available evidence and figures:

```sh
cd results
shasum -a 256 -c checksums.sha256
cd ..
python3 plot_results.py
```

Plotting needs NumPy and Matplotlib. The bundled `nature-npg.mplstyle` is the fallback for the installed `nature-npg` style. It uses Arial with Helvetica/DejaVu Sans fallbacks. The five figures take seconds on the Mac and read aggregates only.

For the frozen CPU analysis on the server, with the original inputs present:

```sh
cd workspace/sec-grounded-qa
workspace/venv/bin/python analyze.py --run-id stage2-v2-20261018
workspace/venv/bin/python export_results.py
```

`analyze.py` preserves the preregistered analysis; the publication copy renames one presentation-only field from the original. `results/analysis.json` preserves all numeric outputs with the matching field name. `supplemental.json` adds descriptive Wilson intervals and display coordinates for already-frozen τ thresholds; it does not select thresholds or verdicts. `results/README.md` specifies numeric encodings. Server dependencies are in `requirements-lock.txt`.

The original generation snapshot is private development commit `749248eb40aeb33bfaf8ae8a3cd42be55bca47e0` (2026-10-18 19:41:20 EDT, UTC−04:00). Source hashes in frozen metadata describe the original inputs; cleaned source bytes can differ.

The delivered results require no new generation. The server was restored to 4 × 4,096 after this run; the experiment used 2 × 8,192.

## Pre-registration timeline

Times are EDT (UTC−04:00). Commit and server file times are local evidence, not external registration.

| Local time | Event | Commit / record |
|---|---|---|
| 2026-10-18 17:00:07 | Stage-one draft and initial selection on 100 DocFinQA dev-split questions | `ba64c9979ab8d6c9ee0a58d42e3a3f88e3dc9848` |
| 2026-10-18 19:23:27 | Measured stage-1b protocol and evidence budget | `ed4fd38e16f6fb1f772347a0fc995cd07b9994ce` |
| 2026-10-18 19:41:20 | Final hierarchy, self-answer decision and frozen analysis | `749248eb40aeb33bfaf8ae8a3cd42be55bca47e0` |
| 2026-10-18 21:02:56 | Test marker created, referencing final SHA | Server file time; original private preregistration SHA-256 `5b1ad4dfedbdbe26bbc137737121c0a6e97f68d26f8d8b83e5457eb75f291fdc`; original private commit `749248e` (2026-10-18 19:41:20 EDT) |
| 2026-10-19 01:53:10 | All planned blocks complete | Server status file time; 17,413.20 seconds; no cuts |

These commits are in a private development repository; their order is attested by commit times and server file times on 2026-10-18–19 and can be shown on request. This public repository is a single-commit snapshot of the final state.

Next-day completion is listed separately. Earlier development scripts remain for provenance; their superseded budgets are not the final protocol. The final budget was six hours.

## Licence

The code is licensed under the [MIT License](LICENSE). DocFinQA (MIT) and FinanceBench (CC BY-NC 4.0) keep their own licences. For benchmark data, this repository contains only question IDs, numeric predictions, scores and three short DocFinQA training demonstrations, and no FinanceBench document text.
