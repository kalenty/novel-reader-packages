"""Trusted-main promotion: data-only inbox, signed verification, immutable release, Pages."""
import argparse,gzip,hashlib,io,json,os,re,shutil,subprocess,tarfile
from pathlib import Path
from deploy import unpack,verify,validate_manifest
PUBLIC='kalenty/novel-reader-packages'

def run(*args,**kw):return subprocess.check_output(args,**kw)
def download(manifest,directory):
    validate_manifest(manifest);directory.mkdir(parents=True)
    run('gh','release','download',manifest['tag'],'--repo',PUBLIC,'--pattern','apt-site.tar.gz','--dir',str(directory))
    bundle=directory/'apt-site.tar.gz'
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Previous bundle checksum mismatch')
    site=directory/'site';unpack(bundle,site);verify(site,allow_expired=True);return site

def deterministic_bundle(site,target):
    with target.open('wb') as file:
        with gzip.GzipFile(fileobj=file,mode='wb',filename='',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as tar:
                for p in sorted(site.rglob('*')):
                    if not p.is_file():continue
                    data=p.read_bytes();entry=tarfile.TarInfo(str(p.relative_to(site)));entry.size=len(data);entry.mode=0o644;tar.addfile(entry,io.BytesIO(data))

def prepare():
    if os.environ.get('GITHUB_REPOSITORY')!=PUBLIC:raise ValueError('Unexpected repository')
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text());source=event.get('workflow_run',{}).get('head_sha') or event.get('inputs',{}).get('inbox_sha')
    if not source:source=run('git','ls-remote','origin','refs/heads/apt-incoming',text=True).split()[0]
    if not re.fullmatch('[0-9a-f]{40}',source):raise ValueError('Invalid inbox commit')
    run('git','fetch','--depth','1','origin',source,stderr=subprocess.DEVNULL)
    root=Path('.local/promotion');root.mkdir(parents=True)
    manifest=json.loads(run('git','show',source+':release.json'));validate_manifest(manifest)
    bundle=root/'incoming.tar.gz';bundle.write_bytes(run('git','show',source+':apt-site.tar.gz'))
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Inbox bundle checksum mismatch')
    fresh=root/'fresh';unpack(bundle,fresh);new=verify(fresh);channel=manifest['channel']
    if set(new)!={channel} or new[channel]['version']!=manifest['applicationVersion'].replace('-','~',1):raise ValueError('Manifest differs from signed package')
    if manifest.get('packageSha256')!=new[channel]['sha256']:raise ValueError('Signed candidate checksum mismatch')
    previous=json.loads(Path('release.json').read_text());oldsite=download(previous,root/'previous');old=verify(oldsite,allow_expired=True)
    if channel in old:
        result=subprocess.run(['dpkg','--compare-versions',new[channel]['version'],'lt',old[channel]['version']])
        if result.returncode==0:raise ValueError('Refusing downgrade publication')
        if new[channel]['version']==old[channel]['version'] and new[channel]['sha256']!=old[channel]['sha256']:raise ValueError('Same version with different contents; bump VERSION')
    site=Path('site');shutil.copytree(oldsite,site)
    target=site/'dists'/channel
    if target.exists():shutil.rmtree(target)
    shutil.copytree(fresh/'dists'/channel,target)
    for p in fresh.iterdir():
        if p.is_file():shutil.copyfile(p,site/p.name)
    for p in (fresh/'pool/main').iterdir():shutil.copyfile(p,site/'pool/main'/p.name)
    needed=set()
    for suite in (site/'dists').iterdir():
        packages=(suite/'main/binary-aarch64/Packages').read_text();needed.update(re.findall(r'^Filename: (.+)$',packages,re.M))
    for p in (site/'pool/main').iterdir():
        if str(p.relative_to(site)) not in needed:p.unlink()
    verify(site,allow_expired=True)
    out=root/'prepared';out.mkdir();deterministic_bundle(site,out/'apt-site.tar.gz')
    published=dict(manifest,sourceBundleSha256=manifest['sha256'],inboxCommit=source);published['sha256']=hashlib.sha256((out/'apt-site.tar.gz').read_bytes()).hexdigest();(out/'release.json').write_text(json.dumps(published,indent=2)+'\n')
    print(json.dumps({'verified':True,'tag':manifest['tag'],'channel':channel,'version':new[channel]['version']}))

def publish():
    out=Path('.local/promotion/prepared');manifest=json.loads((out/'release.json').read_text());validate_manifest(manifest);bundle=out/'apt-site.tar.gz'
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Prepared bundle mismatch')
    probe=subprocess.run(['gh','release','view',manifest['tag'],'--repo',PUBLIC,'--json','tagName'],capture_output=True,text=True)
    if probe.returncode==0:
        existing=Path('.local/existing');existing.mkdir();run('gh','release','download',manifest['tag'],'--repo',PUBLIC,'--pattern','apt-site.tar.gz','--dir',str(existing))
        if hashlib.sha256((existing/'apt-site.tar.gz').read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Existing immutable release differs')
    else:
        if 'not found' not in probe.stderr.lower() and '404' not in probe.stderr:raise ValueError('Cannot check existing release safely')
        args=['gh','release','create',manifest['tag'],str(bundle),str(out/'release.json'),'--repo',PUBLIC,'--target','main','--title','Novel Reader '+manifest['applicationVersion']+' ('+manifest['channel']+')','--notes','Automatically built, audited and signed. See README for scoped APT setup. Device acceptance remains required for testing candidates.']
        args+=['--prerelease','--latest=false'] if manifest['channel']=='testing' else ['--latest']
        run(*args)
    destination=Path('release.json');text=(out/'release.json').read_text()
    if destination.read_text()!=text:
        destination.write_text(text)
        for key,value in [('user.name','Novel Reader Contributors'),('user.email','contributors@users.noreply.github.com')]:run('git','config',key,value)
        run('git','add','release.json');run('git','-c','commit.gpgsign=false','commit','-m','Publish '+manifest['tag'])
        run('git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','origin','HEAD:main',stderr=subprocess.STDOUT)
    print(json.dumps({'published':manifest['tag'],'channel':manifest['channel']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','publish']);args=parser.parse_args()
    prepare() if args.action=='prepare' else publish()
