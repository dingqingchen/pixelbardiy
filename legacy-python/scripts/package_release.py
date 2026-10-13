"""Make clean Windows/MCU ZIPs and SHA256 manifests; exclude personal runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def copy_tree(source,target):
    for file in source.rglob('*'):
        relative=file.relative_to(source)
        if any(part in ('runtime','__pycache__','backups') for part in relative.parts): continue
        if file.is_file():
            out=target/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,out)


def manifest(directory,version):
    rows=[]
    for file in sorted(directory.rglob('*')):
        if file.is_file() and file.name!='manifest.json':
            rows.append(dict(path=file.relative_to(directory).as_posix(),bytes=file.stat().st_size,
                             sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    (directory/'manifest.json').write_text(json.dumps(dict(version=version,files=rows),indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='v1.0.0')
    args=parser.parse_args()
    if not args.version.replace('.','').replace('-','').isalnum():raise ValueError('Invalid version')
    staging=ROOT/'release-staging'/args.version
    staging.mkdir(parents=True,exist_ok=False)
    packages=ROOT/'packages';packages.mkdir(exist_ok=True)
    outputs=[]
    for product in ('HaloStudio','HaloFirmware'):
        destination=staging/product;destination.mkdir()
        copy_tree(ROOT/'dist'/product,destination)
        if not (destination/(product+'.exe')).is_file():raise FileNotFoundError('Build '+product+' first')
        for name in ('README.md','LICENSE','THIRD_PARTY_LICENSE.txt'):
            shutil.copy2(ROOT/name,destination/name)
        copy_tree(ROOT/'docs',destination/'docs')
        script_names=['Verify-Package.ps1']+(['Set-Autostart.ps1'] if product=='HaloStudio' else ['Update-MCU.ps1'])
        (destination/'scripts').mkdir()
        for name in script_names:shutil.copy2(ROOT/'scripts'/name,destination/'scripts'/name)
        if product=='HaloFirmware':copy_tree(ROOT/'firmware',destination/'firmware')
        manifest(destination,args.version)
        archive=packages/f'{product}-{args.version}-win64.zip'
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as zipped:
            for file in sorted(destination.rglob('*')):
                if file.is_file():zipped.write(file,file.relative_to(staging).as_posix())
        outputs.append(archive)
    sums=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in outputs)
    (packages/'SHA256SUMS.txt').write_text(sums,encoding='ascii')
    print(sums,end='')


if __name__=='__main__':main()
