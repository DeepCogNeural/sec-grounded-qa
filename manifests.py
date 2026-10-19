"""Read-only source processing; never issues generation requests."""
import ast,collections,json,math,pathlib,random,re
import fitz
from core import *
from prepare_dev import clean
QN=lambda s:' '.join(s.lower().split())
def load_finqa():
 by=collections.defaultdict(list)
 for split in ['test','dev','train']:
  current=collections.defaultdict(list)
  for x in json.load(open(DATA/'FinQA/dataset'/f'{split}.json')):current[QN(x['qa']['question'])].append((split,x))
  for q,candidates in current.items():
   if q not in by:by[q]=candidates
 return by
def join_one(row,ctx,by):
 candidates=by[QN(row['question'])];proof=[]
 header=norm(ctx)[:6000].lower()
 # The reported fiscal year nearest the filing heading, not all years mentioned.
 fy=re.search(r'fiscal\s+year\s+ended.{0,65}?((?:19|20)\d\d)',header)
 fy=fy or re.search(r'((?:19|20)\d\d)\s+FORM\s+10-K',header,re.I)
 header_year=fy[1] if fy else None
 for split,x in candidates:
  exe=x['qa'].get('exe_ans');p=parse(exe)
  agree=match(p,row['gold'])
  parts=x.get('filename',x['id']).split('/');doc_year=parts[1] if len(parts)>1 else None
  aliases={'GPN':'global payments','MRO':'marathon oil','DVN':'devon energy','PNC':'pnc financial','WRK':'westrock'}
  company=aliases.get(parts[0]);company_match=company in header if company else None
  doc_match=bool(header_year and header_year==doc_year and company_match is not False)
  snippets=x['qa'].get('gold_inds',{})
  overlap=sum(norm(v).lower() in norm(ctx).lower() for v in snippets.values())
  proof.append(dict(finqa_id=x['id'],split=split,filename=x.get('filename'),exe_ans=exe,exe_agrees=agree,context_fiscal_year=header_year,filename_year=doc_year,document_year_agrees=bool(header_year and header_year==doc_year),document_company_alias=company,document_company_agrees=company_match,document_name_agrees=doc_match,context_header_evidence=header[:3500] if len(candidates)>1 else None,verbatim_gold_snippets=overlap))
 if len(candidates)==1:chosen=0;status='unique'
 else:
  joint=[i for i,p in enumerate(proof) if p['exe_agrees'] and p['document_name_agrees']]
  if len(joint)==1:chosen=joint[0];status='resolved'
  else:
   # Equivalent duplicate annotations are not distinct document choices.
   payloads=[json.dumps({k:x.get(k) for k in ['filename','pre_text','post_text','table']} | {'exe_ans':x['qa'].get('exe_ans'),'program':x['qa'].get('program'),'gold_inds':x['qa'].get('gold_inds')},sort_keys=True) for _,x in candidates]
   if candidates and len(set(payloads))==1 and all(p['exe_agrees'] and p['document_name_agrees'] for p in proof):
    chosen=min(range(len(candidates)),key=lambda i:candidates[i][1]['id']);status='resolved'
    for p in proof:p['resolution']='identical document, execution answer, program, gold spans and evidence payload; canonical smallest ID'
   else:chosen=None;status='unresolved'
 out=dict(item_id=row['item_id'],doc_group=row['doc_group'],question=row['question'],answer_raw=row['answer_raw'],gold=row['gold'],join_status=status,candidates=proof)
 if chosen is not None:
  split,x=candidates[chosen];out.update(finqa_id=x['id'],finqa_split=split,filename=x.get('filename'),**{'qa.exe_ans':x['qa'].get('exe_ans'),'qa.program':x['qa'].get('program'),'qa.gold_inds':x['qa'].get('gold_inds'),'pre_text':x.get('pre_text'),'post_text':x.get('post_text'),'table':x.get('table')})
 return out

def docfinqa_manifests():
 by=load_finqa();test=json.load(open(DATA/'docfinqa/test.json'));rows=[];joins=[]
 for i,x in enumerate(test):
  h=sha(x['Context']);row=dict(item_id=f'test-{i:04d}',source_index=i,context_sha256=h,doc_group=h,question=x['Question'],answer_raw=x['Answer'],gold=parse(x['Answer']))
  rows.append(row);joins.append(join_one(row,x['Context'],by))
  p=INDEX/'sources'/f'{h}.txt'
  if not p.exists():p.write_text(clean(x['Context']))
 jsonl(MAN/'docfinqa_test.jsonl',rows);jsonl(MAN/'finqa_join.jsonl',joins)
 joined=[j for j in joins if j['join_status']!='unresolved']
 jsonl(MAN/'oracle_200.jsonl',random.Random(SEED).sample(joined,200))
 jsonl(MAN/'contextdep_200.jsonl',random.Random(SEED).sample(rows,200))
 dump(RUNS/'ambiguous_join_evidence.json',[j for j in joins if len(j['candidates'])!=1])
 del test
 dev=json.load(open(DATA/'docfinqa/dev.json'))
 jsonl(MAN/'finqa_dev_join.jsonl',[join_one(r,dev[r['source_index']]['Context'],by) for r in readl(MAN/'docfinqa_dev_sample.jsonl')])
 return dict(test_rows=len(rows),test_contexts=len(set(r['doc_group'] for r in rows)),test_parse_failures=sum(r['gold'] is None for r in rows),join_status=dict(collections.Counter(j['join_status'] for j in joins)))
METRIC_WORDS=set('revenue revenues sales income earnings profit profits margin margins ebit ebitda ebitdar expense expenses costs cost expenditure expenditures capex capital ppne property plant equipment asset assets liabilities liability debt borrowings cash cashflow flow flows operations operating balance inventory inventories turnover receivable receivables tax taxes rate ratio equity shares stock dividend dividends interest maturity maturities pension benefit benefits restructuring growth investment investments securities liquidity depreciation amortization volume payment payments return returns working net total gross'.split())
def asked_years(question):return sorted(set(int(y) for y in re.findall(r'(?<!\d)((?:19|20)\d\d)(?!\d)',question)))
def probe_validation(q,doc,text):
 gold=parse(q['answer']);years=asked_years(q['question'])
 if not gold or gold['is_yes_no'] or not years:return dict(valid=False,reason='no_numeric_gold_or_year')
 normalized=norm(text).lower();v=gold['value'];factors=[1,.001,.000001,1000,1000000]
 if gold['is_percent']:factors += [.01,100]
 variants=sorted(set(abs(v*f) for f in factors))
 nums=[];matches=[]
 for m in NUMBER_SCAN.finditer(normalized):
  n=abs(float(m[0]));nums.append(n)
  if any(math.isclose(n,z,rel_tol=1e-9,abs_tol=1e-9) for z in variants):matches.append(dict(token=m[0],offset=m.start()))
 metrics=sorted(set(re.findall('[a-z]+',q['question'].lower()))&METRIC_WORDS)
 near=[];min_dist={str(y):None for y in years};yearpos={y:[m.start() for m in re.finditer(r'(?<!\d)'+str(y)+r'(?!\d)',normalized)] for y in years}
 metricpos=[]
 for metric in metrics:
  for m in re.finditer(r'\b'+re.escape(metric)+r'\b',normalized):
   metricpos.append((metric,m.start()))
   for y,positions in yearpos.items():
    if positions:
     distance=min(abs(p-m.start()) for p in positions)
     if min_dist[str(y)] is None or distance<min_dist[str(y)]:min_dist[str(y)]=distance
     if distance<=300:near.append(dict(year=y,metric=metric,offset=m.start(),distance=distance))
 return dict(valid=not matches and not near and bool(metrics),replacement_text_sha256=sha(text),normalization='core.norm then lowercase; numeric-token exact equivalence, abs sign conservatively treated alike',gold=gold,scale_factors=factors,absolute_numeric_variants=variants,numeric_tokens_scanned=len(nums),value_matches=matches[:10],asked_years=years,metric_nouns=metrics,metric_lexicon=sorted(METRIC_WORDS),metric_occurrences=len(metricpos),year_occurrences={str(y):len(p) for y,p in yearpos.items()},minimum_year_metric_distance=min_dist,year_near_metric=near[:10],window_chars=300)
def finance_manifests():
 root=DATA/'financebench';questions=readl(root/'data/financebench_open_source.jsonl');rawmeta=readl(root/'data/financebench_document_information.jsonl');meta={x['doc_name']:x for x in rawmeta}
 names=sorted(set(q['doc_name'] for q in questions));texts={};pdfmeta=[]
 for name in names:
  path=root/'pdfs'/f'{name}.pdf';pages=[]
  with fitz.open(path) as doc:
   for i,page in enumerate(doc):pages.append(dict(page=i,text=page.get_text()))
  jsonl(INDEX/'financebench_pages'/f'{name}.jsonl',pages);texts[name]='\n\f\n'.join(p['text'] for p in pages)
  pdfmeta.append(dict(doc_name=name,pdf_sha256=sha(path.read_bytes()),pages=len(pages),text_sha256=sha(texts[name]),metadata=meta[name]))
 jsonl(MAN/'financebench_documents.jsonl',pdfmeta)
 numeric=[q for q in questions if parse(q['answer']) and not parse(q['answer'])['is_yes_no']];ids=[q['financebench_id'] for q in numeric];gold={q['financebench_id']:parse(q['answer']) for q in numeric}
 historical=[]
 for filename in ['gpt-4-1106-preview_singleStore.jsonl','llama2_singleStore.jsonl']:
  selected=[r for r in readl(root/'results'/filename) if r['financebench_id'] in ids];assert len(selected)==len(ids)
  scored=[dict(financebench_id=r['financebench_id'],label=r['label'],parsed=parse(r['model_answer']),NumMatch_1pct=match(parse(r['model_answer']),gold[r['financebench_id']]),NumMatch_strict=match(parse(r['model_answer']),gold[r['financebench_id']],True)) for r in selected]
  historical.append(dict(source=filename,source_sha256=sha((root/'results'/filename).read_bytes()),n=len(selected),human_correct=sum(r['label']=='Correct Answer' for r in selected),human_accuracy=sum(r['label']=='Correct Answer' for r in selected)/len(selected),same_parser_correct=sum(r['NumMatch_1pct'] for r in scored),same_parser_accuracy=sum(r['NumMatch_1pct'] for r in scored)/len(selected),parse_failures=sum(r['parsed'] is None for r in scored),rows=scored,protocol='Historical human labels use a different scoring protocol; same-parser rescore is deliberately strict about answer strings.'))
 dump(MAN/'financebench_numeric_ids.json',dict(parser_rule=PARSER_RULE,ids=ids,items=[dict(financebench_id=q['financebench_id'],gold=parse(q['answer'])) for q in numeric],historical=historical))
 probes=[];validation=[]
 for q in questions:
  original=meta[q['doc_name']];yrs=asked_years(q['question'])
  probes.append(dict(probe_id=q['financebench_id']+'-answerable',kind='answerable',financebench_id=q['financebench_id'],question=q['question'],question_company=q['company'],source_doc=q['doc_name'],replacement_doc=q['doc_name'],gold=parse(q['answer']),trivial_filter=trivial(q['company'],yrs,original)))
  for name in names:
   m=meta[name]
   if name==q['doc_name'] or m['company']!=original['company'] or m['doc_type']!=original['doc_type'] or m['doc_period']==original['doc_period']:continue
   v=probe_validation(q,m,texts[name]);validation.append(dict(financebench_id=q['financebench_id'],replacement_doc=name,**v))
   if v['valid']:probes.append(dict(probe_id=q['financebench_id']+'-hard-'+name,kind='hard',financebench_id=q['financebench_id'],question=q['question'],question_company=q['company'],source_doc=q['doc_name'],replacement_doc=name,validation=v,trivial_filter=trivial(q['company'],yrs,m)))
 rng=random.Random(SEED);perm=list(range(len(questions)))
 while True:
  rng.shuffle(perm)
  if all(questions[i]['company']!=questions[j]['company'] for i,j in enumerate(perm)):break
 for i,j in enumerate(perm):
  q=questions[i];replacement=questions[j]['doc_name'];probes.append(dict(probe_id=q['financebench_id']+'-easy',kind='easy',financebench_id=q['financebench_id'],question=q['question'],question_company=q['company'],source_doc=q['doc_name'],replacement_doc=replacement,replacement_question_id=questions[j]['financebench_id'],validation=dict(wrong_company=True,derangement_seed=SEED),trivial_filter=trivial(q['company'],asked_years(q['question']),meta[replacement])))
 jsonl(MAN/'financebench_probes.jsonl',probes);jsonl(RUNS/'financebench_hard_candidates.jsonl',validation)
 return dict(financebench_documents=len(names),financebench_numeric=len(ids),hard_probes=sum(p['kind']=='hard' for p in probes),hard_trivial_pass=sum(p['kind']=='hard' and not p['trivial_filter']['refuse'] for p in probes),easy_probes=sum(p['kind']=='easy' for p in probes),answerable=sum(p['kind']=='answerable' for p in probes),hard_candidates=len(validation))
def hashes():
 files=sorted(p for p in MAN.iterdir() if p.suffix in ('.json','.jsonl'))
 (MAN/'MANIFEST.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in files))
 return {p.name:dict(sha256=sha(p.read_bytes()),rows=len(readl(p)) if p.suffix=='.jsonl' else None) for p in files}
if __name__=='__main__':
 summary=docfinqa_manifests();print('DOCFINQA',summary,flush=True)
 summary.update(finance_manifests());summary['manifests']=hashes();dump(RUNS/'manifest_summary.json',summary);print(json.dumps(summary),flush=True)
