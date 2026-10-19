"""Render figures from compact aggregates only (no model or analysis rerun)."""
import json
import time
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
try:
    plt.style.use('nature-npg')
except OSError:
    plt.style.use(ROOT / 'nature-npg.mplstyle')
A = json.loads((ROOT / 'results/analysis.json').read_text())
S = json.loads((ROOT / 'results/supplemental.json').read_text())
W = S['descriptive_Wilson']
BLUE, RED, CYAN, GRAY = '#3C5488', '#E64B35', '#4DBBD5', '#4D4D4D'
COLORS = [BLUE, RED, CYAN]
OUT = ROOT / 'figures'

def save(fig, name, note):
    fig.text(.01, .01, note, fontsize=7, color=GRAY, va='bottom')
    fig.tight_layout(rect=(0, .11, 1, .94))
    for ext in ['png', 'svg']:
        fig.savefig(OUT / (name + '.' + ext), dpi=300, metadata={'Date': None} if ext == 'svg' else None)
    svg=OUT/(name+'.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)

def bars(ax, labels, values, colors, intervals=None):
    x = np.arange(len(values))
    ax.bar(x, values, color=colors, width=.55)
    if intervals:
        err = np.maximum(0, np.array([[v - 100*w['lower'], 100*w['upper'] - v] for v,w in zip(values,intervals)]).T)
        ax.errorbar(x, values, yerr=err, fmt='none', color=GRAY, capsize=3, lw=.8)
    for i,v in enumerate(values):
        upper = 100*intervals[i]['upper'] if intervals else v
        ax.text(i, upper+2, f'{v:.1f}%', ha='center', color=GRAY)
    ax.set_xticks(x, labels)
    ax.tick_params(axis='x', top=False)
    ax.set_ylim(0, 106)

def main():
    start=time.monotonic(); OUT.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), gridspec_kw={'width_ratios':[1,1.3]})
    fig.suptitle('a  Code execution did not give a scorer-stable accuracy gain', x=.01, ha='left', fontsize=10, fontweight='bold')
    bars(axes[0], ['A0: direct', 'A1: execute'], [100*A['arms'][a]['NumMatch_1pct'] for a in ['A0','A1']], COLORS[:2], [A['Wilson'][a] for a in ['A0','A1']])
    axes[0].set_ylim(0,65); axes[0].set_ylabel('All-item accuracy (%)')
    d=A['H0']; axes[1].axvline(0, color=GRAY, ls='--', lw=.5)
    for y,(label,r) in enumerate([('NumMatch-1%',d),('FinQA agreement',d['FinQA_delta'])]):
        point=100*r['point']; lo=100*r['lower']; hi=100*r['upper']
        axes[1].errorbar(point,y,xerr=[[point-lo],[hi-point]],fmt='o',color=GRAY,capsize=3)
        axes[1].text(point,y+.16,f'{point:+.2f} pp [{lo:+.2f}, {hi:+.2f}]',ha='center',color=GRAY)
    axes[1].set_yticks([0,1], ['NumMatch-1%', 'FinQA agreement']); axes[1].set_ylim(-.4,1.55); axes[1].set_xlim(-6.3,7.0)
    axes[1].set_xlabel('Paired difference: A1 − A0 (percentage points)')
    save(fig,'a_paired_accuracy','All 922 questions, 240 filing groups. Rate bars: 95% Wilson CI; differences: 2,000 filing-bootstrap draws.\nOpposite scorer signs force the preregistered Tie branch; this is not evidence of equivalence.')

    fig,ax=plt.subplots(figsize=(7.2,4.2))
    fig.suptitle('b  Refusals dominate errors; executing a wrong program still fails',x=.01,ha='left',fontsize=10,fontweight='bold')
    cats=['format','abstain_filtered','retrieval_miss','unit_scale_sign','wrong_operand','wrong_arithmetic','other']
    labels=['Format / invalid program','Abstain / filtered','Retrieval miss','Unit / scale / sign','Wrong operand','Wrong arithmetic','Other']
    y=np.arange(len(cats))
    for j,arm in enumerate(['A0','A1','A1+G']):
        values=[A['taxonomy'][arm]['counts'].get(c,0) for c in cats]
        ax.barh(y+(j-1)*.24, values, height=.21,color=COLORS[j],label=arm)
        for yy,v in zip(y+(j-1)*.24,values):ax.text(v+3,yy,str(v),va='center',fontsize=7,color=GRAY)
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(0,440);ax.set_xlabel('Errors / refusals (count; 922 questions per system)');ax.legend(loc='lower right',ncol=3)
    save(fig,'b_error_categories','Frozen first-match taxonomy. Format precedes filtering. Correct: A0 442; A1 416; A1+G 332.\nWrong arithmetic includes choosing an incorrect operation after matching operands; it is not an execution-engine error.')

    fig,ax=plt.subplots(figsize=(7.2,4.0))
    fig.suptitle('c  G exceeds direct answering when wrong:right cost > 1.62',x=.01,ha='left',fontsize=10,fontweight='bold')
    for key,label,color in [('risk_coverage','A1: operand-count ranking',RED),('risk_coverage_G','A1+G: same ranking',CYAN)]:
        rs=A[key];ax.plot([100*r['coverage'] for r in rs],[100*r['risk'] for r in rs],'-o',color=color,label=label)
    null=A['H1']['random_subset_null'];baseline=100*(1-A['H1']['baseline_answered_precision'])
    ax.plot([0,100*A['arms']['A0']['answered']/A['n']],[baseline,baseline],color=BLUE,ls='--',label=f'A0 random-gate expectation: {baseline:.1f}% risk')
    g=A['G_point'];x=100*g['coverage'];y=100*(1-g['precision'])
    ax.errorbar(x,100*(1-null['mean_precision']),yerr=[[100*(null['interval']['upper']-null['mean_precision'])],[100*(null['mean_precision']-null['interval']['lower'])]],fmt='D',color=BLUE,capsize=3,label='Random null: 95% subset interval at G coverage')
    ax.scatter([x],[y],s=35,color=CYAN,edgecolor=GRAY,zorder=5)
    ax.annotate(f'G: {x:.1f}% coverage\n{y:.1f}% risk; λ* = 1.62',(x,y),xytext=(56,26.5),arrowprops={'arrowstyle':'-','lw':.5},color=GRAY)
    for system,offset in [('A1',(5,28)),('A1+G',(-80,18))]:
        t=S['tau_main_points'][system];tx=100*t['actual_answered_coverage'];ty=100*t['actual_answered_risk']
        ax.scatter(tx,ty,marker='s',color=GRAY,s=20)
        label='A1 coverage' if system=='A1' else 'G coverage'
        ax.annotate(f'τ at {label}: {tx:.1f}%, {ty:.1f}%',(tx,ty),xytext=offset,textcoords='offset points',fontsize=7,color=GRAY)
    ax.set_xlabel('Valid-answer coverage (% of 922 questions)');ax.set_ylabel('Risk (% wrong among valid answers)');ax.set_xlim(0,88);ax.set_ylim(24,46)
    ax.legend(loc='upper right',fontsize=7)
    save(fig,'c_risk_coverage','Ranking and G were fixed on development data. τ squares use the frozen H3 thresholds, then the model’s valid answers.\nTheir actual answer coverage differs from nominal retrieval admission. Null interval describes random subsets, not sampling uncertainty.')

    fig,ax=plt.subplots(figsize=(7.2,3.5))
    fig.suptitle('d  Both ungated arms decline withheld-evidence probes beyond τ',x=.01,ha='left',fontsize=10,fontweight='bold')
    x=np.arange(3)
    for j,arm in enumerate(['A0','A1','A1+G']):
        r=A['H3_prime']['systems'][arm]
        ax.bar(j-.17,100*r['decline_rate'],width=.32,color=COLORS[j])
        ax.bar(j+.17,100*r['tau_decline_rate'],width=.32,facecolor='white',edgecolor=GRAY,hatch='///')
        w=W['withheld_A0_abstain' if arm=='A0' else 'withheld_A1_abstain' if arm=='A1' else 'withheld_A1_G_accept']
        lo,hi=(w['lower'],w['upper']) if arm!='A1+G' else (1-w['upper'],1-w['lower'])
        p=r['decline_rate'];ax.errorbar(j-.17,100*p,yerr=[[100*(p-lo)],[100*(hi-p)]],fmt='none',color=GRAY,capsize=3)
        ax.text(j-.17,100*hi+1.5,f'{100*p:.1f}%',ha='center',fontsize=7,color=GRAY)
        ax.text(j+.17,100*r['tau_decline_rate']+2,f"{100*r['tau_decline_rate']:.1f}%",ha='center',fontsize=7,color=GRAY)
    ax.set_xticks(x,['A0: direct','A1: execute','A1+G: filtered']);ax.set_ylim(0,108);ax.set_ylabel('Decline rate on 150 probes (%)');ax.tick_params(axis='x',top=False)
    ax.text(0,1.03,'Solid: measured system (95% Wilson CI); hatched: matched-coverage retrieval-score control',transform=ax.transAxes,fontsize=7,color=GRAY)
    save(fig,'d_withheld_declines','Decline = explicit refusal for A0/A1; refusal or filtering for A1+G. Invalid non-refusals count as false answers.\nA1+G improves on τ by 9.33 pp (<10 pp), so its probe result is retrieval-score-equivalent under the frozen rule.')

    fig,axes=plt.subplots(1,2,figsize=(7.2,3.4))
    fig.suptitle('e  Changed figures: 75% followed; no-evidence outputs all refused',x=.01,ha='left',fontsize=10,fontweight='bold')
    bars(axes[0],['New gold','Old gold'],[75,0],[RED,GRAY],[W['counterfactual_NumMatch_1pct'],W['counterfactual_old_gold']])
    axes[0].axhline(70,color=GRAY,ls='--',lw=.5);axes[0].text(.48,72,'Frozen follow threshold: 70%',fontsize=7,color=GRAY)
    axes[0].set_ylabel('Match rate on 100 counterfactuals (%)')
    bars(axes[1],['A0: no evidence','A1: same 200 items'],[0,48.5],[BLUE,RED],[W['contextdep_NumMatch_1pct'],W['contextdep_A1_same_items']])
    axes[1].set_ylabel('Accuracy on 200 questions (%)')
    axes[1].axhline(24.25,color=GRAY,ls='--',lw=.5);axes[1].text(-.25,26,'Half of A1: 24.25%',fontsize=7,color=GRAY)
    save(fig,'e_context_dependence','Bars: 95% Wilson intervals. Counterfactuals substitute gold operands by 10–30%; new gold is recomputed.\nContext comparison changes both evidence and arm, as preregistered; these probes cannot prove absence of memorisation.')
    print(f'Five PNG/SVG figures rendered in {time.monotonic()-start:.2f} seconds.')

if __name__=='__main__':
    main()
