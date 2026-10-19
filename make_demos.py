from core import *
x=json.loads((RUNS/'demo_candidates.json').read_text())
out=[]
for d in x:
 if d['item_id']=='train-2200':
  evidence='[train-2200]\n'+d['context_header'][:240]
  a0=dict(answer=None,unit='',abstain=True);a1=dict(operands=[],program='',answer_type='number',abstain=True)
  note='Seed-selected train program operands 627444 and 635092 absent from normalized supplied context; demonstrates abstention. Context header is fiscal 2013, question asks 2014.'
 elif d['item_id']=='train-3534':
  q='Debt borrowings-principal payments | $41029 | $2717 | $4743 | $5147 | $28422'
  assert q in d['excerpts']['41029'][0]
  evidence='[train-3534; filing year 2014; amounts in millions]\n'+q
  a1=dict(operands=[dict(name='a',value=41029,quote=q,period='2014',unit='USD millions'),dict(name='b',value=28422,quote=q,period='2014',unit='USD millions')],program='(a-b)/a*100',answer_type='percent',abstain=False)
  a0=dict(answer=(41029-28422)/41029*100,unit='%',abstain=False)
  note='Uses supplied train program verbatim in arithmetic meaning; source question says prior to 2019, while supplied program includes 2019. Demonstration preserves dataset convention.'
 else:
  qa='Investing &amp; Lending | Equity securities | $ 3930 | $ 2800 | $ 603'
  qb='Total net revenues | 7018 | 5891 | 2142'
  assert qa in d['excerpts']['3930'][0] and qb in d['excerpts']['3930'][0]
  evidence='[train-0700; fiscal year 2013; amounts in millions]\n'+qa+'\n'+qb
  a1=dict(operands=[dict(name='a',value=3930,quote=qa,period='2013',unit='USD millions'),dict(name='b',value=7018,quote=qb,period='2013',unit='USD millions')],program='a/b*100',answer_type='percent',abstain=False)
  a0=dict(answer=3930/7018*100,unit='%',abstain=False);note='First table column is 2013, per source filing.'
 out.append({k:d[k] for k in ('item_id','question','program_raw','answer_raw','context_sha256')}|dict(evidence=evidence,A0=a0,A1=a1,selection_rule='Python random.Random(20261018).sample over train order with 2-4 numeric literal occurrences in AST of nonempty Program',note=note,A0_text='Evidence:\n'+evidence+'\nQuestion: '+d['question']+'\n'+json.dumps(a0),A1_text='Evidence:\n'+evidence+'\nQuestion: '+d['question']+'\n'+json.dumps(a1)))
jsonl(MAN/'demos_train.jsonl',out)
