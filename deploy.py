"""Verify a locally signed distribution bundle before Pages publication."""
import datetime,email.utils,gzip,hashlib,json,lzma,os,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
FINGERPRINT='4A5257DA36C1DD201DD5725A7D02DF8EE817027D'
FIXED={'index.html','audit.json','novel-reader.asc','novel-reader.gpg','dists/testing/Release','dists/testing/Release.gpg','dists/testing/InRelease'}
INDEX='dists/testing/main/binary-aarch64/'

def allowed(name):
    return name in FIXED or name in {INDEX+'Packages'+x for x in ['', '.gz','.xz']} or bool(re.fullmatch(re.escape(INDEX)+r'by-hash/SHA256/[0-9a-f]{64}',name)) or bool(re.fullmatch(r'pool/main/novel-reader_[0-9]+\.[0-9]+\.[0-9]+(?:~(?:rc|alpha|beta)[0-9]+)?_aarch64\.deb',name))

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

def verify(site):
    keys=subprocess.check_output(['gpg','--batch','--show-keys','--with-colons',str(site/'novel-reader.gpg')],text=True,stderr=subprocess.DEVNULL)
    fingerprints=[line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:')]
    if sum(line.startswith('pub:') for line in keys.splitlines())!=1 or not fingerprints or fingerprints[0]!=FINGERPRINT:raise ValueError('Signing certificate mismatch')
    # Check both published encodings: clients may select the ASCII-armored key.
    asc=subprocess.check_output(['gpg','--batch','--show-keys','--with-colons',str(site/'novel-reader.asc')],text=True,stderr=subprocess.DEVNULL)
    if sum(line.startswith('pub:') for line in asc.splitlines())!=1 or next(x.split(':')[9] for x in asc.splitlines() if x.startswith('fpr:'))!=FINGERPRINT:raise ValueError('ASCII certificate mismatch')
    release=subprocess.check_output(['gpgv','--keyring',str((site/'novel-reader.gpg').resolve()),'--output','-',str(site/'dists/testing/InRelease')],stderr=subprocess.DEVNULL)
    if release!=(site/'dists/testing/Release').read_bytes():raise ValueError('Unsigned Release differs')
    subprocess.run(['gpgv','--keyring',str((site/'novel-reader.gpg').resolve()),str(site/'dists/testing/Release.gpg'),str(site/'dists/testing/Release')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    text=release.decode();valid=email.utils.parsedate_to_datetime(re.search(r'^Valid-Until: (.+)$',text,re.M)[1]);now=datetime.datetime.now(datetime.timezone.utc)
    if not now<valid<now+datetime.timedelta(days=91):raise ValueError('Expired or excessive metadata lifetime')
    for line in text.split('SHA256:\n',1)[1].splitlines():
        sha,size,name=line.split()
        if not allowed('dists/testing/'+name):raise ValueError('Invalid index path')
        data=(site/'dists/testing'/name).read_bytes()
        if len(data)!=int(size) or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Index checksum mismatch')
    raw=(site/(INDEX+'Packages')).read_bytes()
    if gzip.decompress((site/(INDEX+'Packages.gz')).read_bytes())!=raw or lzma.decompress((site/(INDEX+'Packages.xz')).read_bytes())!=raw:raise ValueError('Compressed index content differs')
    packages=raw.decode();records=[x for x in packages.strip().split('\n\n') if x]
    if len(records)!=1:raise ValueError('Exactly one reviewed package expected')
    for record in records:
        fields=dict(line.split(': ',1) for line in record.splitlines() if line and not line.startswith(' '))
        if fields.get('Package')!='novel-reader' or fields.get('Architecture')!='aarch64' or not allowed(fields['Filename']):raise ValueError('Unexpected package')
        data=(site/fields['Filename']).read_bytes()
        if len(data)!=int(fields['Size']) or hashlib.sha256(data).hexdigest()!=fields['SHA256']:raise ValueError('Package checksum mismatch')
    for p in (site/(INDEX+'by-hash/SHA256')).iterdir():
        if hashlib.sha256(p.read_bytes()).hexdigest()!=p.name:raise ValueError('By-hash index mismatch')
    print(json.dumps({'signature':'PASS','indexes':'PASS','package':'PASS','channel':'testing','primaryFingerprint':FINGERPRINT}))

if __name__=='__main__':
    x=json.loads(Path('release.json').read_text())
    if x['primaryFingerprint']!=FINGERPRINT or not re.fullmatch(r'testing-[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|alpha|beta)[0-9]+)?-[0-9a-f]{12}',x['tag']):raise SystemExit('Invalid release manifest')
    if os.environ.get('GITHUB_REPOSITORY')!='kalenty/novel-reader-packages':raise SystemExit('Unexpected repository')
    evidence=Path('.local');evidence.mkdir(exist_ok=True)
    subprocess.run(['gh','release','download',x['tag'],'--repo','kalenty/novel-reader-packages','--pattern','apt-site.tar.gz','--dir',str(evidence)],check=True)
    bundle=evidence/'apt-site.tar.gz'
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=x['sha256']:raise SystemExit('Bundle checksum mismatch')
    unpack(bundle,Path('site'));verify(Path('site'))
