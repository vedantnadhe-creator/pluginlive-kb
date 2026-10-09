#!/usr/bin/env python3
"""Deploy task-routing code over the exact running dependencies, with rollback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

service, branch, environment = sys.argv[1:]
if (environment,branch) not in [('DEV','Development'),('UAT','UAT')]:
    raise SystemExit('Unsupported environment/branch')
containers={'fast-api':['fastapi' if environment=='DEV' else 'fastapiai'],
            'form-data-normalization':['datanormalization','datanormalization-worker','datanormalization-cron'],
            'pg-vector-api-service':['vectorsearch']}
repos={'fast-api':'fastapi-ai-engine','form-data-normalization':'form-data-normalization',
       'pg-vector-api-service':'pg-vector-api-service','corporate-node-v2':'corporate-node-v2'}
repo=repos[service]
source=Path('/home/ubuntu/api')/repo

def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def output(args):return subprocess.check_output(args,text=True).strip()
run(['git','-C',str(source),'fetch','origin',branch])
sha=output(['git','-C',str(source),'rev-parse','origin/'+branch])
stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
release=Path('/home/ubuntu/releases')/repo/(environment+'-'+sha[:12]+'-'+stamp)
release.mkdir(parents=True)
if service=='corporate-node-v2':
    archive=subprocess.Popen(['git','-C',str(source),'archive',sha],stdout=subprocess.PIPE)
    run(['tar','-x','-C',str(release)],stdin=archive.stdout)
    if archive.wait():raise SystemExit('Archive failed')
    shutil.copy2(source/'.env',release/'.env')
    (release/'node_modules').symlink_to(source/'node_modules',target_is_directory=True)
    node='/home/ubuntu/.nvm/versions/node/v20.20.2/bin/node'
    run([node,str(source/'node_modules/typescript/bin/tsc'),'-p',str(release/'tsconfig.json')])
    unit='corporate-node-v2.service'
    override=Path('/etc/systemd/system')/(unit+'.d')/'zz-central-llm.conf'
    previous=None
    if override.exists():previous=override.read_text()
    text='[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart='+node+' '+str(release/'dist/index.js')+'\n'
    (release/'service-override.conf').write_text(text)
    run(['sudo','mkdir','-p',str(override.parent)])
    run(['sudo','cp',str(release/'service-override.conf'),str(override)])
    run(['sudo','systemctl','daemon-reload'])
    run(['sudo','systemctl','restart',unit])
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://localhost:4001/v2/health',timeout=3) as r:
                    if r.status==200:break
            except Exception:time.sleep(1)
        else:raise RuntimeError('Service health did not recover')
        if output(['systemctl','show',unit,'-p','ActiveState','--value'])!='active':raise RuntimeError('Service inactive')
    except Exception:
        if previous is None:run(['sudo','rm','-f',str(override)])
        else:
            (release/'previous-override.conf').write_text(previous)
            run(['sudo','cp',str(release/'previous-override.conf'),str(override)])
        run(['sudo','systemctl','daemon-reload']);run(['sudo','systemctl','restart',unit]);raise
    print('DEPLOYED',environment,repo,sha,release,flush=True)
    raise SystemExit(0)

files=output(['git','-C',str(source),'diff',sha+'^',sha,'--name-only']).splitlines()
files=[f for f in files if f.endswith('.py') and not f.startswith('tests/')]
if not files:raise SystemExit('No Python task-routing change in target commit')
for f in files:
    target=release/f;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(subprocess.check_output(['git','-C',str(source),'show',sha+':'+f]))
configs=[]
for name in containers[service]:
    inspected=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
    if inspected.returncode:continue
    configs.append(json.loads(inspected.stdout)[0])
if not configs:raise SystemExit('No running service to update')
for cfg in configs:
    name=cfg['Name'].lstrip('/')
    (release/(name+'-inspect.json')).write_text(json.dumps(cfg,indent=2))
    os.chmod(release/(name+'-inspect.json'),0o600)
    old=cfg['Image'];rollback='central-llm-rollback/'+name+':'+stamp
    run(['docker','tag',old,rollback])
    build=release/name;build.mkdir()
    for f in files:
        dest=build/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(release/f,dest)
    dockerfile='FROM '+rollback+'\n'
    for f in files:dockerfile+='COPY '+json.dumps([f,'/app/'+f])+'\n'
    dockerfile+='LABEL pluginlive.central-llm.revision="'+sha+'"\n'
    (build/'Dockerfile').write_text(dockerfile)
    tag='central-llm/'+name+':'+sha[:12]
    run(['docker','build','-t',tag,str(build)])
    # Parse the actual shipped code before interrupting the existing container.
    run(['docker','run','--rm','--entrypoint','python',tag,'-m','py_compile',*['/app/'+f for f in files]])
    cfg['_new_image']=tag

def recreate(cfg,image):
    name=cfg['Name'].lstrip('/');host=cfg['HostConfig'];conf=cfg['Config']
    env_file=release/(name+'.env')
    if any('\n' in item for item in conf['Env']):raise RuntimeError('Multiline env needs a different deployment method')
    env_file.write_text('\n'.join(conf['Env'])+'\n');os.chmod(env_file,0o600)
    cmd=['docker','run','-d','--name',name,'--env-file',str(env_file)]
    restart=host['RestartPolicy']['Name']
    if restart and restart!='no':cmd+=['--restart',restart]
    network=host.get('NetworkMode')
    if network and network!='default':cmd+=['--network',network]
    for port,bindings in (host.get('PortBindings') or {}).items():
        for binding in bindings:
            prefix=(binding['HostIp']+':') if binding.get('HostIp') else ''
            cmd+=['-p',prefix+binding['HostPort']+':'+port]
    for binding in host.get('Binds') or []:cmd+=['-v',binding]
    for mount in host.get('Mounts') or []:
        if mount.get('Type')!='bind':raise RuntimeError('Unsupported mount type')
        spec='type=bind,src='+mount['Source']+',dst='+mount['Target']
        if mount.get('ReadOnly'):spec+=',readonly'
        cmd+=['--mount',spec]
    logs=host.get('LogConfig') or {}
    if logs.get('Type'):cmd+=['--log-driver',logs['Type']]
    for k,v in (logs.get('Config') or {}).items():cmd+=['--log-opt',k+'='+v]
    for k,v in (conf.get('Labels') or {}).items():cmd+=['--label',k+'='+v]
    if conf.get('User'):cmd+=['--user',conf['User']]
    if conf.get('WorkingDir'):cmd+=['--workdir',conf['WorkingDir']]
    if host.get('Memory'):cmd+=['--memory',str(host['Memory'])]
    if host.get('NanoCpus'):cmd+=['--cpus',str(host['NanoCpus']/1e9)]
    if host.get('Privileged'):cmd+=['--privileged']
    if host.get('ReadonlyRootfs'):cmd+=['--read-only']
    if conf.get('Tty'):cmd+=['-t']
    if conf.get('OpenStdin'):cmd+=['-i']
    cmd+=[image,*(conf.get('Cmd') or [])]
    run(['docker','stop','-t','30',name],stdout=subprocess.DEVNULL)
    run(['docker','rm',name],stdout=subprocess.DEVNULL)
    run(cmd,stdout=subprocess.DEVNULL)

for cfg in configs:
    name=cfg['Name'].lstrip('/')
    recreate(cfg,cfg['_new_image'])
    try:
        ports={'fastapi':8011,'fastapiai':8011,'datanormalization':5013,'vectorsearch':5014}
        for _ in range(120):
            running=output(['docker','inspect',name,'-f','{{.State.Running}}'])=='true'
            if running:
                if name not in ports:
                    time.sleep(5)
                    if output(['docker','inspect',name,'-f','{{.State.Restarting}}'])=='false':break
                else:
                    try:
                        with urllib.request.urlopen('http://localhost:'+str(ports[name])+'/openapi.json',timeout=3) as r:
                            if r.status==200:break
                    except Exception:pass
            time.sleep(1)
        else:raise RuntimeError('Startup health failed for '+name)
    except Exception:
        recreate(cfg,cfg['Image']);raise
    conventional={'fastapi':'fastapi:api','fastapiai':'fastapi-ai-engine:api','datanormalization':'datanormalization:api','vectorsearch':'vectorsearch:api'}
    if name in conventional:run(['docker','tag',cfg['_new_image'],conventional[name]])
    print('DEPLOYED',environment,name,sha,'rollback='+cfg['Image'],flush=True)
print('Release artifacts:',release,flush=True)
