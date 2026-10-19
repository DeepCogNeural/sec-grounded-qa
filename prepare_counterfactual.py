"""CPU-only 100-item pre-freeze substitution set, independent of generated answers."""
import copy,decimal,operator,random
from core import *
from analyze import gold_operands,retrieved

TOKEN=re.compile(r'(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)')
OPS={'add':operator.add,'subtract':operator.sub,'multiply':operator.mul,'divide':operator.truediv,'exp':operator.pow,'greater':lambda a,b:float(a>b)}
def execute_finqa(program,changes=None):
 changes=changes or {};calls=re.findall(r'(\w+)\(\s*([^,]+),\s*([^\)]+)\)',program or '');out=[]
 if not calls:raise ValueError('empty_program')
 def val(t):
  t=t.strip()
  if t.startswith('#'):return out[int(t[1:])]
  if t.startswith('const_'):return float(t[6:].replace('m','-').replace('_','.'))
  p=parse(t)
  if not p or p['is_yes_no']:raise ValueError('nonnumeric_operand')
  v=p['value'];return math.copysign(changes.get(abs(v),abs(v)),v)
 for op,a,b in calls:
  if op not in OPS:raise ValueError('unsupported_operation_'+op)
  result=OPS[op](val(a),val(b))
  if not math.isfinite(result):raise ValueError('nonfinite')
  out.append(result)
 return out[-1]
def token_digits(s):return sum(c.isdigit() for c in s)
def format_like(value,token):
 places=len(token.split('.')[1]) if '.' in token else 0
 fmt=f'{value:,.{places}f}' if ',' in token else f'{value:.{places}f}'
 return fmt

def transform(t,join):
 row=t['row'];gold=row['gold'];vals=gold_operands(join)
 if not vals or retrieved(t['evidence']['chunks'],vals) is not True:raise ValueError('operands_not_retrieved')
 if not gold or gold['is_yes_no']:raise ValueError('nonnumeric_gold')
 if any(v==0 or 1900<=abs(v)<=2099 and float(v).is_integer() for v in vals):raise ValueError('zero_or_period_operand')
 # Strict literal eligibility avoids ambiguous scaling, signs, and unsupported table programs.
 progvals=[]
 for op,a,b in re.findall(r'(\w+)\(\s*([^,]+),\s*([^\)]+)\)',join.get('qa.program') or ''):
  if op not in OPS:raise ValueError('unsupported_operation_'+op)
  for term in (a,b):
   term=term.strip()
   if not term.startswith(('#','const_')):progvals.append(parse(term)['value'])
 if set(progvals)!=set(vals):raise ValueError('program_gold_operand_mismatch')
 scale=join.get('prediction_percent_to_finqa_scale',.01) if gold['is_percent'] else 1
 original=execute_finqa(join['qa.program'])/scale
 if not match(dict(gold,value=original),gold):raise ValueError('original_program_gold_mismatch')
 alltext='\n'.join(c['text'] for c in t['evidence']['chunks']);tokens=collections.defaultdict(list)
 for m in TOKEN.finditer(alltext):tokens[float(m[0].replace(',',''))].append(m[0])
 rng=random.Random(int(sha(str(SEED)+':'+row['item_id'])[:16],16));changes={};details=[]
 for value in sorted(set(abs(v) for v in vals)):
  forms=tokens[value]
  if not forms:raise ValueError('literal_operand_absent')
  places=min(len(s.split('.')[1]) if '.' in s else 0 for s in forms);quantum=10**(-places)
  candidates=[]
  for _ in range(500):
   factor=1+rng.choice([-1,1])*rng.uniform(.1,.3);new=round(value*factor,places)
   relative=abs(new/value-1)
   if .1-1e-12<=relative<=.3+1e-12 and new>0 and all(token_digits(format_like(new,s))==token_digits(s) and format_like(new,s).count(',')==s.count(',') for s in forms):candidates.append(new)
  if not candidates:raise ValueError('no_same_digit_perturbation')
  new=candidates[0];changes[value]=new;details.append(dict(old=value,new=new,relative_change=new/value-1,forms=sorted(set(forms)),occurrences=len(forms)))
 if len(set(changes.values()))!=len(changes):raise ValueError('colliding_substitutions')
 newgold=dict(gold,value=execute_finqa(join['qa.program'],changes)/scale)
 if match(newgold,gold):raise ValueError('new_gold_not_distinguishable')
 new=copy.deepcopy(t);counts=collections.Counter()
 def sub(m):
  v=float(m[0].replace(',',''))
  if v not in changes:return m[0]
  counts[v]+=1;return format_like(changes[v],m[0])
 for c in new['evidence']['chunks']:c['text']=TOKEN.sub(sub,c['text'])
 assert all(counts[v]>0 for v in changes)
 new['row'].update(old_gold=gold,new_gold=newgold,gold=newgold,counterfactual=dict(program=join['qa.program'],old_program_execution=original,new_program_execution=newgold['value'],changes=details,seed=SEED,selection='pre-generation operands-retrieved; unsupported or ambiguous substitutions excluded',synthetic=True))
 return new

def main():
 inputs=readl(RUNS/'frozen_v2/test_evidence.jsonl');joins={j['item_id']:j for j in readl(MAN/'finqa_join.jsonl')};random.Random(SEED).shuffle(inputs);out=[];excluded=[]
 for t in inputs:
  try:out.append(transform(t,joins[t['row']['item_id']]))
  except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError) as e:excluded.append(dict(item_id=t['row']['item_id'],reason=str(e)))
  if len(out)==100:break
 if len(out)!=100:raise ValueError(f'Only {len(out)} eligible substitutions')
 jsonl(MAN/'counterfactual_100.jsonl',out);jsonl(RUNS/'frozen_v2/counterfactual_evidence.jsonl',out);jsonl(RUNS/'stage1c/counterfactual_excluded.jsonl',excluded)
 summary=dict(n=len(out),seed=SEED,generation_requests=0,selection_independent_of_model_answers=True,checked_candidates=len(out)+len(excluded),excluded_reasons=dict(collections.Counter(x['reason'] for x in excluded)),manifest_sha256=sha((MAN/'counterfactual_100.jsonl').read_bytes()))
 dump(RUNS/'stage1c/counterfactual_summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
