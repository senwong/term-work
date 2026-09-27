#!/usr/bin/env python3
"""Build an architecture-independent installer archive from a committed tag."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import re
import subprocess

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tag', help='Existing version tag, e.g. v0.1.0')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', args.tag):
        parser.error('Expected vMAJOR.MINOR.PATCH')
    root = Path(__file__).resolve().parent
    version = subprocess.check_output(['git', 'show', args.tag + ':VERSION'], cwd=root, text=True).strip()
    if args.tag != 'v' + version:
        parser.error('Tag does not match committed VERSION')
    prefix = 'term-work-' + version
    archive = subprocess.check_output(['git', 'archive', '--format=tar', '--prefix=' + prefix + '/', args.tag], cwd=root)
    output = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as compressed:
        compressed.write(archive)
    dist = root / 'dist'
    dist.mkdir(exist_ok=True)
    name = prefix + '-macos.tar.gz'
    content = output.getvalue()
    (dist / name).write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest() + '  ' + name + '\n'
    (dist / 'SHA256SUMS').write_text(checksum)
    print(checksum, end='')

if __name__ == '__main__':
    main()
