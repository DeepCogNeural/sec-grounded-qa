"""Explicit layout change with exact argv/environment rollback."""
import argparse,datetime,os,shlex,signal,subprocess,time,urllib.request
from core import *
from qa_v2 import B,DEADLINE
HEALTH_GENERATION_REQUESTS=0
def get(path,timeout=3):
 with urllib.request.urlopen(URL+path,timeout=timeout) as f:return json.load(f)
def capture():
 pids=subprocess.check_output(['pgrep','-f','^'+str(pathlib.Path('workspace') / 'shared-compute/llama/build/bin/llama-server')],text=True).split()
 if len(pids)!=1:raise StopRun('expected exactly one server')
 pid=int(pids[0]);root=pathlib.Path('/proc')/str(pid)
 rawenv=(root/'environ').read_bytes();rawargv=(root/'cmdline').read_bytes()
 private=B/'restart_environment';private.mkdir(mode=0o700,exist_ok=True);os.chmod(private,0o700)
 (private/'original.environ').write_bytes(rawenv);os.chmod(private/'original.environ',0o600)
 (private/'original.cmdline').write_bytes(rawargv);os.chmod(private/'original.cmdline',0o600)
 env=dict(x.split(b'=',1) for x in rawenv.split(b'\0') if x)
 argv=[os.fsdecode(x) for x in rawargv.split(b'\0') if x]
 cwd=os.readlink(root/'cwd')
 return pid,argv,env,cwd
def terminate(pid):
 try:os.kill(pid,signal.SIGTERM)
 except ProcessLookupError:return
 for _ in range(100):
  procpath=pathlib.Path('/proc',str(pid))
  if not procpath.exists():return
  try:
   if (procpath/'stat').read_text().split(') ',1)[1].startswith('Z '):return
  except FileNotFoundError:return
  time.sleep(.1)
 # Do not launch a competing server if the original has not exited.
 raise StopRun('server_did_not_exit_after_SIGTERM')
def launch(argv,env,cwd,label):
 f=open(ROOT/'logs'/('stage1b_'+label+'.log'),'ab')
 return subprocess.Popen(argv,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
def wait_health(proc,slots,ctx,end):
 global HEALTH_GENERATION_REQUESTS
 while time.time()<end:
  if proc.poll() is not None:return False,'process_exit_'+str(proc.returncode)
  try:
   h=get('/health');p=get('/props')
   if h.get('status')=='ok' and p['total_slots']==slots and p['default_generation_settings']['n_ctx']==ctx:
    payload=dict(messages=[{'role':'user','content':'Return the number 2 only.'}],temperature=0,max_tokens=8,cache_prompt=False,chat_template_kwargs={'enable_thinking':False})
    req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    HEALTH_GENERATION_REQUESTS+=1
    with urllib.request.urlopen(req,timeout=max(1,min(30,end-time.time()))) as f:r=json.load(f)
    text=(r['choices'][0]['message'].get('content') or '').strip()
    if text=='2':return True,dict(health=h,props=p,generation_response=r)
    return False,dict(reason='generation_health_mismatch',response=r)
  except Exception as e:last=repr(e)
  time.sleep(1)
 return False,locals().get('last','startup_timeout')
def main(args):
 with Client('secqa-stage1b-layout',DEADLINE) as c:
  c.guard(True)
  if any(x.get('is_processing') for x in get('/slots')):raise StopRun('active_slots')
  pid,old,env,cwd=capture();new=old.copy()
  for flag,val in [('--parallel',str(args.parallel)),('--ctx-size',str(args.ctx_size))]:
   new[new.index(flag)+1]=val
  allowed={old.index('--parallel')+1,old.index('--ctx-size')+1}
  assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(old,new))) and len(old)==len(new)
  check=subprocess.run(['ldd',old[0]],env=env,cwd=cwd,text=True,capture_output=True)
  (B/'restart_ldd.txt').write_text(check.stdout+check.stderr)
  if check.returncode or 'not found' in check.stdout+check.stderr:raise StopRun('ldd unresolved; old server untouched')
  oldslots=int(old[old.index('--parallel')+1]);oldctx=int(old[old.index('--ctx-size')+1])//oldslots
  record=dict(before_argv=old,before_command=shlex.join(old),requested_argv=new,requested_command=shlex.join(new),original_cwd=cwd,environment_saved_privately=True,environment_sha256=sha((B/'restart_environment/original.environ').read_bytes()),changed_flags=['--parallel','--ctx-size'],ldd_ok=True,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
  dump(B/'restart_v2.json',record);c.guard(True);terminate(pid);proc=launch(new,env,cwd,'layout_v2')
  ok,health=wait_health(proc,args.parallel,args.ctx_size//args.parallel,time.time()+180)
  record.update(requested_layout_success=ok,requested_health=health)
  if not ok:
   if proc.poll() is None:terminate(proc.pid)
   proc.wait(timeout=5)
   proc=launch(old,env,cwd,'layout_restore_v2');restored,health=wait_health(proc,oldslots,oldctx,time.time()+180)
   record.update(restored=restored,restore_health=health,chosen_argv=old,chosen_command=shlex.join(old))
   dump(B/'restart_v2.json',record)
   if not restored:raise StopRun('original_server_restore_failed')
  else:record.update(chosen_argv=new,chosen_command=shlex.join(new))
  actual=pathlib.Path('/proc',str(proc.pid),'cmdline').read_bytes()
  actualenv=pathlib.Path('/proc',str(proc.pid),'environ').read_bytes()
  record['argv_readback_match']=actual==b'\0'.join(os.fsencode(x) for x in record['chosen_argv'])+b'\0'
  record['environment_readback_match']=dict(x.split(b'=',1) for x in actualenv.split(b'\0') if x)==env
  record['final_props']=get('/props');record['final_slots']=get('/slots');record['health_generation_requests']=HEALTH_GENERATION_REQUESTS
  dump(B/'restart_v2.json',record)
  print(json.dumps({k:record[k] for k in ['requested_layout_success','chosen_command','argv_readback_match','environment_readback_match']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parallel',type=int,default=2);p.add_argument('--ctx-size',type=int,default=16384);main(p.parse_args())

