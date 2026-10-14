"""Verify and attach previously built Mac installers; no compilation or source upload."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,urllib.request,zipfile

REPO='Ebinaugustin/EA-RoomMatch-Image-to-Reverb'
RELEASE=412815657
TAG='v0.2.3-beta.1'
WINDOWS_SHA='81d1f9f0120f10b3fa8173aec434898638a59be8d1dde936e87802917e8d40fc'
SPECS=[('macos-arm64','ROOMMATCH_TRANSFER_ARM64_URL',1611696685,'a70de7b30fd1b7c8518a553f4d926f4fafc117eda7f6cab3aef6429e3940e517'),
       ('macos-x64','ROOMMATCH_TRANSFER_X64_URL',1812401112,'387a2036d3226916d827ca056bf3becc80bb014a0947e362dd0ddaa2889a5b1b')]

def gh(*args,capture=False):
    return subprocess.run(['gh',*map(str,args)],check=True,text=True,
        stdout=subprocess.PIPE if capture else None).stdout

def api(path): return json.loads(gh('api',path,capture=True))

def digest(file):
    with file.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def upload(file):
    checksum='sha256:'+digest(file)
    current=next((a for a in api(f'repos/{REPO}/releases/{RELEASE}/assets') if a['name']==file.name),None)
    if current:
        if current['state']=='uploaded' and current.get('digest')==checksum: return
        raise RuntimeError('An incomplete or different asset has this name: '+file.name)
    gh('release','upload',TAG,file,'--repo',REPO)
    uploaded=next(a for a in api(f'repos/{REPO}/releases/{RELEASE}/assets') if a['name']==file.name)
    if uploaded['state']!='uploaded' or uploaded.get('digest')!=checksum or uploaded['size']!=file.stat().st_size:
        raise RuntimeError('Uploaded asset did not match its verified source')
    print('Uploaded and checksum verified:',file.name,flush=True)

def main():
    release=api(f'repos/{REPO}/releases/{RELEASE}')
    if release['tag_name']!=TAG: raise RuntimeError('Release tag changed')
    windows=next((a for a in release['assets'] if a['name']=='EA-RoomMatch_Update-Full-Windows-x64.zip'),None)
    if not windows or windows['state']!='uploaded' or windows.get('digest')!='sha256:'+WINDOWS_SHA:
        raise RuntimeError('Verified Windows asset is missing')
    if not any(a['name']=='RoomMatch-Third-Party-Notices.zip' and a['state']=='uploaded' for a in release['assets']):
        raise RuntimeError('Third-party notices attachment is missing')
    downloads=[]
    for platform,secret,size,checksum in SPECS:
        archive=Path(platform+'.zip')
        request=urllib.request.Request(os.environ[secret],headers={'User-Agent':'EA-RoomMatch-Release-Transfer'})
        with urllib.request.urlopen(request,timeout=120) as source,archive.open('wb') as target:
            shutil.copyfileobj(source,target,1024*1024)
        if archive.stat().st_size!=size or digest(archive)!=checksum: raise RuntimeError('CI artifact checksum mismatch: '+platform)
        with zipfile.ZipFile(archive) as zipped:
            for name in (f'EA-RoomMatch-{platform}.pkg',f'EA-RoomMatch-{platform}-manifest.json'):
                with zipped.open(name) as source,Path(name).open('wb') as target: shutil.copyfileobj(source,target,1024*1024)
        manifest=Path(f'EA-RoomMatch-{platform}-manifest.json');report=json.loads(manifest.read_text())
        package=Path(f'EA-RoomMatch-{platform}.pkg')
        if digest(package)!=report['artifact']['sha256'] or package.stat().st_size!=report['artifact']['bytes']:
            raise RuntimeError('Native installer differs from build manifest')
        if any(test.get('status')!='passed' for test in report['tests'].values()): raise RuntimeError('Native validation failed')
        upload(package);upload(manifest)
        downloads.append(package.name)
        archive.unlink();package.unlink()
    gh('release','edit',TAG,'--repo',REPO,'--prerelease','--draft=false')
    result=api(f'repos/{REPO}/releases/{RELEASE}')
    if result['draft'] or not result['prerelease']: raise RuntimeError('Tester release was not published')
    names=['EA-RoomMatch_Update-Full-Windows-x64.zip',*downloads]
    if any(not any(a['name']==name and a['state']=='uploaded' for a in result['assets']) for name in names):
        raise RuntimeError('A platform installer is missing')
    with open(os.environ['GITHUB_STEP_SUMMARY'],'w') as summary:
        summary.write('## Verified RoomMatch download links\n\n')
        for asset in result['assets']:
            if asset['name'] in names: summary.write(f"- [{asset['name']}]({asset['browser_download_url']})\n")
    print('Published verified Windows and Mac tester release:',result['html_url'])

if __name__=='__main__': main()
