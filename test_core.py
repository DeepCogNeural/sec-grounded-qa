import unittest
from core import *
class ParserTests(unittest.TestCase):
 def test_parser(self):
  for s,v,pct in [('14%',14,True),('-4.4%',-4.4,True),('(1,234.50)',-1234.5,False),('3298',3298,False),('$1,577.00',1577,False),('-35',-35,False),('-$1,561',-1561,False),('($1,234)',-1234,False),('2.3 billion',2.3,False)]:
   with self.subTest(s=s):self.assertEqual(parse(s),dict(value=v,is_percent=pct,is_yes_no=False))
  for s in ['3 and 4','nan','inf','1,23',True,None]:self.assertIsNone(parse(s))
 def test_scores(self):
  self.assertTrue(match(parse('.14'),parse('14%')));self.assertFalse(match(parse('.14'),parse('14%'),True))
  self.assertEqual(parse('the total in 2018 was $ 56.7 million .')['value'],56.7);self.assertEqual(parse('the interest decreased 25.7% from year 1 to years 3-5')['value'],25.7);self.assertEqual(parse('170 grants')['value'],170);self.assertEqual(parse('1.371:1')['value'],1.371);self.assertEqual(parse('$ 27.8 per share')['value'],27.8);self.assertFalse(match(parse('1'),parse('100')));self.assertTrue(match(parse('.005'),parse('0')))
  self.assertFalse(match(parse('.0051'),parse('0')));self.assertTrue(match(parse('yes'),parse('yes')))
  self.assertTrue(finqa_agreement(parse('14%'),.14));self.assertFalse(finqa_agreement(parse('14'),.14));self.assertTrue(finqa_agreement(parse('940%'),940,1))
class EvalTests(unittest.TestCase):
 def test_arithmetic(self):self.assertEqual(evaluate('(a-b)/b*100',[dict(name='a',value=120),dict(name='b',value=100)]),20)
 def test_reject(self):
  for p in ['__import__("os")','a.__class__','a[0]','sum([1,2])','2**1000000','a+b','1/0','True','1<2']:
   with self.subTest(p=p),self.assertRaises(ProgramError):evaluate(p,[dict(name='a',value=2)])
class GateTests(unittest.TestCase):
 def base(self):return dict(operands=[dict(name='a',value=-1234,quote='Operating costs were (1,234) million in 2020.',period='2020',unit='USD millions')],program='a',answer_type='number',abstain=False)
 def test_normalization(self):self.assertTrue(gate(self.base(),[dict(text='Operating  costs were -1234 million in 2020.',header='')])['accept'])
 def test_failures(self):
  b=self.base();cs=[dict(text=b['operands'][0]['quote'],header='')]
  for key,value,reason in [('quote','wrong quote with sufficient length','not_found'),('quote','-1234','too_short'),('value',99,'value_absent'),('period','2019','period_absent')]:
   b=self.base();b['operands'][0][key]=value;self.assertIn(reason,gate(b,cs)['reasons'])
  b=self.base();b['program']='z';self.assertIn('undeclared_name',gate(b,cs)['reasons'])
 def test_sentence_final_number(self):
  self.assertTrue(has_value('The value in 2020 was 3298.',3298))
  self.assertEqual(parse('The answer is 3298.')['value'],3298)
 def test_header(self):
  b=self.base();b['operands'][0]['quote']='Operating costs were (1,234) million.'
  self.assertTrue(gate(b,[dict(text=b['operands'][0]['quote'],header='filing 2020')])['accept'])
 def test_trivial(self):
  d=dict(company='A',doc_period=2020,doc_type='10k')
  self.assertFalse(trivial('A',[2018],d)['refuse']);self.assertTrue(trivial('B',[2020],d)['refuse']);self.assertTrue(trivial('A',[2017],d)['refuse'])
if __name__=='__main__':unittest.main()
