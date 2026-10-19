import datetime,os,random,shlex,signal,subprocess,time,urllib.request
from core import *
from manifests import join_one,QN
from prepare_dev import clean
B=RUNS/'stage1b'
rule=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),dev2_seed=20261019,shared_selection='First rank retriever/k candidates by all-program-operands HR, then gold-snippet all-hit HR. Evaluate the best two distinct candidates with identical r0 prompts on all 200 dev-2 items in both arms. Choose higher combined A0+A1 NumMatch-1%; ties higher operand HR, then smaller k, then BM25,dense,hybrid,hybrid_rerank. Slot layout is 2x8192 if restart succeeds; selected for capacity before results. No test outputs used.',revision_selection='After shared config selection, evaluate at most 4 further prompt revisions per arm on the same 200 dev-2 items. Equal revision count for both arms. Select each arm separately by its own NumMatch-1%, tie strict, tie fewer abstentions, tie earlier version. Stop after one further paired revision unless time allows more. Revisions must be logged with reason before generation.',time_fallback='If the second shared candidate cannot finish both arms before 23:15 UTC, retain the first fully measured candidate; partial candidates cannot win. Stop new revision batches at 23:15 UTC. Hard stop 23:45 UTC.',retrieval_metrics='Primary HR@k = all nonconstant numeric operands of FinQA train program occur somewhere in top-k; absolute numeric equivalence with comma/accounting normalization, includes percent conversions and 1e3/1e6 units. Also report any/all gold snippet lexical proxy (>=80% unique tokens and all numeric tokens in a chunk), and literal operand HR without scalings. No claim that value presence proves semantic evidence.',deadline_utc='2026-10-18T23:45:00Z')
dump(B/'selection_rules_v2.json',rule)
train=json.load(open(DATA/'docfinqa/train.json'));demos=readl(MAN/'demos_train.jsonl');exclude={d['context_sha256'] for d in demos};ids={d['item_id'] for d in demos}
pool=[i for i,x in enumerate(train) if x.get('Program') and sha(x['Context']) not in exclude and f'train-{i:04d}' not in ids]
chosen=random.Random(20261019).sample(pool,200);by=collections.defaultdict(list)
for x in json.load(open(DATA/'FinQA/dataset/train.json')):by[QN(x['qa']['question'])].append(('train',x))
rows=[];joins=[]
for i in chosen:
 x=train[i];h=sha(x['Context']);r=dict(item_id=f'train-{i:04d}',source_index=i,context_sha256=h,doc_group=h,question=x['Question'],answer_raw=x['Answer'],gold=parse(x['Answer']),program_raw=x['Program'],split='train',development_role='dev-2');rows.append(r);joins.append(join_one(r,x['Context'],by));p=INDEX/'sources'/f'{h}.txt'
 if not p.exists():p.write_text(clean(x['Context']))
jsonl(MAN/'docfinqa_dev2.jsonl',rows);jsonl(MAN/'finqa_dev2_join.jsonl',joins)
dump(B/'dev2_manifest_summary.json',dict(n=len(rows),eligible_pool=len(pool),groups=len(set(r['doc_group'] for r in rows)),seed=20261019,excluded_demo_documents=sorted(exclude),join_status=dict(collections.Counter(r['join_status'] for r in joins)),hashes={n:sha((MAN/n).read_bytes()) for n in ['docfinqa_dev2.jsonl','finqa_dev2_join.jsonl','docfinqa_dev_sample.jsonl']}))
# Layout changes are exclusively in restart_layout_v2.py.
