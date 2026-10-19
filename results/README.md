# Numeric evidence packet

`analysis.json` is the unmodified frozen analysis output. `supplemental.json` contains secondary Wilson intervals, FinanceBench historical aggregates, and plotting coordinates for frozen retrieval-score thresholds. `run_status.json` records completed/cut blocks and request counts. `checksums.sha256` covers every packet file except itself.

Each CSV contains question IDs and numeric fields only. No questions, filing contexts, evidence quotes, raw responses or PDF text are included. Empty fields mean unavailable, not zero. A1_G is the offline view of the same A1 outputs, not another generation.

| Column | Meaning |
|---|---|
| question_id | Original manifest ID; repeated across paired arms |
| prediction | Parsed numeric prediction before G; yes/no encoded 1/0; blank when unavailable |
| prediction_type | 0 unavailable; 1 number; 2 percent; 3 yes/no |
| answered | Valid answer; for A1_G, valid and accepted by G |
| abstain | Explicit model refusal, including in A1_G; filtering is not an explicit refusal |
| unparseable / truncated | Frozen scorer flags |
| NumMatch_1pct / NumMatch_strict / FinQA_agreement | Correctness flags; A1_G additionally requires G acceptance |
| finqa_eligible | Whether the FinQA agreement score has a resolved join |
| G_accept | Offline gate accepts the A1 output; zero for A0 where the gate is not applicable |
| operand_count | Count of declared operands |
| category | Main arms only: 0 correct; 1 format; 2 abstain/filtered; 3 retrieval miss; 4 unit/scale/sign; 5 wrong operand; 6 wrong arithmetic; 7 other |
| operands_retrieved | Main arms only: 0 absent; 1 all present; 2 unknown annotations |
| abstain_split | Main arms only: 0 not applicable; 1 justified; 2 unjustified; 3 unknown |
| filing_index | Numeric index of sorted original-context group hashes from the main set; blank for groups outside it |

Main A0/A1/A1_G each contain 922 rows. Withheld_A0/A1 each contain 150, contextdep 200, rerun30 30, counterfactual 100, financebench 226 and oracle 200. FinanceBench retains manifest IDs; its aggregate answerable/easy split is 76/150. Every field other than IDs is numeric or blank.

The packet permits per-item score audits and clustered main-arm resampling without redistributing text. It cannot reproduce extraction, evidence validation or semantic judgements without the licensed inputs outside Git. Supplemental Wilson intervals are descriptive; frozen decisions come only from `analysis.json`.
