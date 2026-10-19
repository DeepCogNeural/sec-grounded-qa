"""Export numeric-only evidence from saved results; never requests generation."""
import csv
import hashlib
import json
from pathlib import Path

from analyze import gate_weight, threshold_gate, wilson

SOURCE = Path('workspace') / './runs/stage2-v2-20261018'
DEST = Path(__file__).resolve().parent / 'results'
BLOCKS = ['A0', 'A1', 'withheld_A0', 'withheld_A1', 'contextdep',
          'rerun30', 'counterfactual', 'financebench', 'oracle']
CATEGORIES = ['correct', 'format', 'abstain_filtered', 'retrieval_miss',
              'unit_scale_sign', 'wrong_operand', 'wrong_arithmetic', 'other']

def main():
    DEST.mkdir(exist_ok=True)
    analysis = json.loads((SOURCE / 'analysis.json').read_text())
    (DEST / 'analysis.json').write_text(json.dumps(analysis, indent=2) + '\n')
    cats = {(r['item_id'], r['arm']): r for r in map(json.loads,
            (SOURCE / 'error_categories.jsonl').read_text().splitlines())}
    mainrows = {}
    supplemental = {'descriptive_Wilson': {}, 'tau_main_points': {}}
    fields = ['question_id', 'prediction', 'prediction_type', 'answered', 'abstain',
              'unparseable', 'truncated', 'NumMatch_1pct', 'NumMatch_strict',
              'FinQA_agreement', 'finqa_eligible', 'G_accept', 'operand_count',
              'category', 'operands_retrieved', 'abstain_split', 'filing_index']
    groups = {g: i for i, g in enumerate(sorted({r['doc_group'] for r in cats.values()}))}
    for block in BLOCKS:
        rows = [json.loads(line) for line in (SOURCE / (block + '.jsonl')).open()]
        if block in ['A0', 'A1']:
            mainrows[block] = rows
        for system in ([block, 'A1_G'] if block == 'A1' else [block]):
            with (DEST / (system + '.csv')).open('w') as f:
                writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
                writer.writeheader()
                for r in rows:
                    s = r['score']; p = s['prediction']
                    t = 0 if p is None else 3 if p['is_yes_no'] else 2 if p['is_percent'] else 1
                    pred = '' if p is None else int(p['value'] == 'yes') if t == 3 else p['value']
                    c = cats.get((r['item_id'], 'A1+G' if system == 'A1_G' else block))
                    out = {k: int(s[k]) for k in fields[3:13]}
                    if system == 'A1_G':
                        out['answered'] = int(s['G_accept'])
                        for k in ['NumMatch_1pct', 'NumMatch_strict', 'FinQA_agreement']:
                            out[k] = int(s[k] and s['G_accept'])
                    out.update(question_id=r['item_id'], prediction=pred, prediction_type=t,
                               filing_index=groups.get(r['row']['doc_group'], ''),
                               category=CATEGORIES.index(c['category']) if c else '',
                               operands_retrieved=2 if c and c['operands_retrieved'] is None else int(c['operands_retrieved']) if c else '',
                               abstain_split={'2a_justified': 1, '2b_unjustified': 2, '2_unknown': 3}.get(c['abstain_split'], 0) if c else '')
                    writer.writerow(out)
        for metric in ['NumMatch_1pct', 'answered', 'abstain', 'G_accept']:
            supplemental['descriptive_Wilson'][block + '_' + metric] = wilson(sum(r['score'][metric] for r in rows), len(rows))
        supplemental['descriptive_Wilson'][block + '_nonabstain'] = wilson(sum(not r['score']['abstain'] for r in rows), len(rows))
        if block == 'financebench':
            for kind in ['answerable', 'easy']:
                subset = [r for r in rows if r['row']['probe']['kind'] == kind]
                for metric in ['NumMatch_1pct', 'answered', 'abstain', 'G_accept']:
                    supplemental['descriptive_Wilson']['financebench_' + kind + '_' + metric] = wilson(sum(r['score'][metric] for r in subset), len(subset))
    taus = {r['item_id']: r['top1_fused'] for r in map(json.loads,
            (SOURCE.parent / 'frozen_v2/tau_scores.jsonl').read_text().splitlines())}
    for system, probe in analysis['H3_prime']['systems'].items():
        rows = mainrows[system.split('+')[0]]
        weights = [gate_weight(taus[r['item_id']], probe['tau_gate']) for r in rows]
        # Retrieval-only gate; correctness includes the underlying model's refusals.
        precision = sum(w * r['score']['NumMatch_1pct'] for w, r in zip(weights, rows)) / sum(weights)
        actual_answered = sum(w * r['score']['answered'] for w, r in zip(weights, rows))
        actual_precision = sum(w * r['score']['NumMatch_1pct'] for w, r in zip(weights, rows)) / actual_answered
        supplemental['tau_main_points'][system] = dict(coverage=sum(weights)/len(rows), precision=precision, risk=1-precision,
            actual_answered_coverage=actual_answered/len(rows), actual_answered_precision=actual_precision, actual_answered_risk=1-actual_precision)
    h2=analysis['H2']; det=analysis['determinism']; fb=analysis['financebench_answerable_G']
    for name, k, n in [('contextdep_A1_same_items', round(h2['A1_same_items']*h2['contextdep_n']), h2['contextdep_n']),
                       ('determinism_parsed', det['parsed_agreement'], det['n']),
                       ('determinism_text', det['exact_text_agreement'], det['n']),
                       ('financebench_G_precision', round(fb['precision']*fb['answered']), fb['answered']),
                       ('counterfactual_old_gold', round(h2['matches_old_gold']*h2['counterfactual_n']), h2['counterfactual_n'])]:
        supplemental['descriptive_Wilson'][name] = wilson(k, n)
    hist = json.loads((SOURCE.parent / 'manifests/financebench_numeric_ids.json').read_text())['historical']
    supplemental['financebench_historical'] = [{k: v for k, v in r.items() if k in ['source', 'n', 'human_correct', 'human_accuracy', 'same_parser_correct', 'same_parser_accuracy', 'parse_failures']} for r in hist]
    (DEST / 'supplemental.json').write_text(json.dumps(supplemental, indent=2) + '\n')
    (DEST / 'run_status.json').write_bytes((SOURCE / 'status.json').read_bytes())
    (DEST / 'checksums.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in sorted(DEST.iterdir()) if p.is_file() and p.name != 'checksums.sha256'))
    print('Exported numeric score tables and aggregate results.')

if __name__ == '__main__':
    main()
