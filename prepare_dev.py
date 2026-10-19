import ast,collections,json,pathlib,random,re
from core import *
def clean(s):return s.replace('\\n','\n').replace('\\t','\t')
def main():
 dev=json.load(open(DATA/'docfinqa/dev.json'))
 ids=random.Random(SEED).sample(range(len(dev)),100)
 rows=[]
 for i in ids:
  x=dev[i];h=sha(x['Context'])
  rows.append(dict(item_id=f'dev-{i:04d}',source_index=i,context_sha256=h,doc_group=h,question=x['Question'],answer_raw=x['Answer'],gold=parse(x['Answer'])))
  d=INDEX/'sources'/f'{h}.txt';d.parent.mkdir(parents=True,exist_ok=True)
  if not d.exists():d.write_text(clean(x['Context']))
 jsonl(MAN/'docfinqa_dev_sample.jsonl',rows)
 del dev
 train=json.load(open(DATA/'docfinqa/train.json'));pool=[]
 for i,x in enumerate(train):
  if not x['Program']:continue
  try:
   constants=[n.value for n in ast.walk(ast.parse(x['Program'])) if isinstance(n,ast.Constant) and type(n.value) in (int,float)]
   if 2<=len(constants)<=4:pool.append((i,x))
  except SyntaxError:pass
 selected=random.Random(SEED).sample(pool,3)
 out=[]
 for i,x in selected:
  ctx=norm(x['Context']); nums=sorted(set(n.value for n in ast.walk(ast.parse(x['Program'])) if isinstance(n,ast.Constant) and type(n.value) in (int,float) and n.value not in (0,1,100)))
  excerpts={}
  for n in nums:
   matches=[m for m in re.finditer(r'(?<![\d.])'+re.escape(str(n))+r'(?![\d.])',ctx)]
   excerpts[str(n)]=[ctx[max(0,m.start()-200):m.end()+200] for m in matches][:30]
  out.append(dict(item_id=f'train-{i:04d}',question=x['Question'],program_raw=x['Program'],answer_raw=x['Answer'],context_sha256=sha(x['Context']),context_header=ctx[:1200],excerpts=excerpts))
 dump(RUNS/'demo_candidates.json',out)
 print('READY',len(rows),[x['item_id'] for x in out],flush=True)
if __name__=='__main__':main()
