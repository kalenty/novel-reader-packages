"""Verify a locally signed distribution bundle before Pages publication."""
import datetime,email.utils,gzip,hashlib,json,lzma,os,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
FINGERPRINT='4A5257DA36C1DD201DD5725A7D02DF8EE817027D'
FIXED={'index.html','audit.json','novel-reader.asc','novel-reader.gpg'}
SUITES={'testing','stable'}

def allowed(name):
    return name in FIXED or bool(re.fullmatch(r'dists/(?:testing|stable)/(?:Release|Release\.gpg|InRelease|audit.json|main/binary-aarch64/Packages(?:\.gz|\.xz)?|main/binary-aarch64/by-hash/SHA256/[0-9a-f]{64})',name)) or bool(re.fullmatch(r'pool/main/novel-reader_[0-9]+\.[0-9]+\.[0-9]+(?:~(?:rc|alpha|beta)[0-9]+)?_aarch64\.deb',name))

def validate_manifest(x):
    if x.get('primaryFingerprint')!=FINGERPRINT or x.get('channel') not in SUITES or not re.fullmatch(r'(?:testing|stable)-[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|alpha|beta)[0-9]+)?-[0-9a-f]{12}',x.get('tag','')) or not re.fullmatch('[0-9a-f]{64}',x.get('sha256','')):raise ValueError('Invalid release manifest')
    if not x['tag'].startswith(x['channel']+'-'+x['applicationVersion']+'-'):raise ValueError('Tag/version/channel mismatch')
    if x['channel']=='stable' and '-' in x['applicationVersion']:raise ValueError('Prerelease cannot enter stable')

def unpack(bundle,site):
    site.mkdir()
    with tarfile.open(bundle,'r:gz') as tar:
        seen=set();total=0
        for m in tar:
            if not m.isfile() or not allowed(m.name) or m.name in seen or PurePosixPath(m.name).is_absolute():raise ValueError('Unsafe bundle member')
            total+=m.size
            if total>150*1024*1024:raise ValueError('Bundle too large')
            seen.add(m.name);p=site/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
    if not FIXED.issubset(seen):raise ValueError('Incomplete bundle')

def verify_channel(site,channel,allow_expired=False):
    index="dists/"+channel+"/main/binary-aarch64/"
    dist="dists/"+channel+"/"
    keys=subprocess.check_output(['gpg','--batch','--show-keys','--with-colons',str(site/'novel-reader.gpg')],text=True,stderr=subprocess.DEVNULL)
    fingerprints=[line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:')]
    if sum(line.startswith('pub:') for line in keys.splitlines())!=1 or not fingerprints or fingerprints[0]!=FINGERPRINT:raise ValueError('Signing certificate mismatch')
    # Check both published encodings: clients may select the ASCII-armored key.
    asc=subprocess.check_output(['gpg','--batch','--show-keys','--with-colons',str(site/'novel-reader.asc')],text=True,stderr=subprocess.DEVNULL)
    if sum(line.startswith('pub:') for line in asc.splitlines())!=1 or next(x.split(':')[9] for x in asc.splitlines() if x.startswith('fpr:'))!=FINGERPRINT:raise ValueError('ASCII certificate mismatch')
    release=subprocess.check_output(['gpgv','--keyring',str((site/'novel-reader.gpg').resolve()),'--output','-',str(site/(dist+'InRelease'))],stderr=subprocess.DEVNULL)
    if release!=(site/(dist+'Release')).read_bytes():raise ValueError('Unsigned Release differs')
    subprocess.run(['gpgv','--keyring',str((site/'novel-reader.gpg').resolve()),str(site/(dist+'Release.gpg')),str(site/(dist+'Release'))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    text=release.decode();valid=email.utils.parsedate_to_datetime(re.search(r'^Valid-Until: (.+)$',text,re.M)[1]);now=datetime.datetime.now(datetime.timezone.utc)
    if valid>=now+datetime.timedelta(days=91) or (valid<=now and not allow_expired):raise ValueError('Expired or excessive metadata lifetime')
    for line in text.split('SHA256:\n',1)[1].splitlines():
        sha,size,name=line.split()
        if not allowed(dist+name):raise ValueError('Invalid index path')
        data=(site/dist/name).read_bytes()
        if len(data)!=int(size) or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Index checksum mismatch')
    raw=(site/(index+'Packages')).read_bytes()
    if gzip.decompress((site/(index+'Packages.gz')).read_bytes())!=raw or lzma.decompress((site/(index+'Packages.xz')).read_bytes())!=raw:raise ValueError('Compressed index content differs')
    packages=raw.decode();records=[x for x in packages.strip().split('\n\n') if x]
    if len(records)!=1:raise ValueError('Exactly one reviewed package expected')
    for record in records:
        fields=dict(line.split(': ',1) for line in record.splitlines() if line and not line.startswith(' '))
        if fields.get('Package')!='novel-reader' or fields.get('Architecture')!='aarch64' or not allowed(fields['Filename']):raise ValueError('Unexpected package')
        data=(site/fields['Filename']).read_bytes()
        if len(data)!=int(fields['Size']) or hashlib.sha256(data).hexdigest()!=fields['SHA256']:raise ValueError('Package checksum mismatch')
    for p in (site/(index+'by-hash/SHA256')).iterdir():
        if hashlib.sha256(p.read_bytes()).hexdigest()!=p.name:raise ValueError('By-hash index mismatch')
    if channel=='stable' and '~' in fields['Version']:raise ValueError('Prerelease package in stable')
    return {'version':fields['Version'],'sha256':fields['SHA256'],'filename':fields['Filename']}

def verify(site,allow_expired=False):
    channels=sorted(p.name for p in (site/'dists').iterdir() if p.is_dir())
    if not channels or not set(channels).issubset(SUITES):raise ValueError('Unexpected suite')
    result={c:verify_channel(site,c,allow_expired) for c in channels}
    actual={str(p.relative_to(site)) for p in (site/'pool/main').iterdir() if p.is_file()}
    if actual!={r['filename'] for r in result.values()}:raise ValueError('Unverified package in pool')
    print(json.dumps({'signature':'PASS','indexes':'PASS','package':'PASS','channels':channels,'primaryFingerprint':FINGERPRINT}))
    return result

if __name__=='__main__':
    x=json.loads(Path('release.json').read_text())
    validate_manifest(x)
    if os.environ.get('GITHUB_REPOSITORY')!='kalenty/novel-reader-packages':raise SystemExit('Unexpected repository')
    evidence=Path('.local');evidence.mkdir(exist_ok=True)
    subprocess.run(['gh','release','download',x['tag'],'--repo','kalenty/novel-reader-packages','--pattern','apt-site.tar.gz','--dir',str(evidence)],check=True)
    bundle=evidence/'apt-site.tar.gz'
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=x['sha256']:raise SystemExit('Bundle checksum mismatch')
    unpack(bundle,Path('site'));verify(Path('site'))
