"""Validator for the frozen schemas, using only their JSON-schema keywords."""
import math

def valid_schema(obj,s):
 if 'anyOf' in s:return any(valid_schema(obj,x) for x in s['anyOf'])
 t=s.get('type')
 if t=='object':
  if not isinstance(obj,dict) or not all(k in obj for k in s.get('required',[])):return False
  if s.get('additionalProperties') is False and set(obj)-set(s['properties']):return False
  return all(valid_schema(v,s['properties'][k]) for k,v in obj.items() if k in s['properties'])
 if t=='array':return isinstance(obj,list) and len(obj)<=s.get('maxItems',float('inf')) and all(valid_schema(x,s['items']) for x in obj)
 if t=='number':return type(obj) in (int,float) and math.isfinite(obj)
 if t=='boolean':return type(obj) is bool
 if t=='null':return obj is None
 if t=='string':return isinstance(obj,str) and len(obj)<=s.get('maxLength',float('inf')) and ('enum' not in s or obj in s['enum'])
 raise ValueError('Unsupported schema type '+str(t))
