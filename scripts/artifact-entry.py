#!/usr/bin/env python3
"""Read a small diagnostic entry from a GitHub artifact without downloading its image."""
import argparse
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class RangeReader(io.RawIOBase):
    def __init__(self, size, fetch):
        self.size, self.fetch, self.position = size, fetch, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if whence not in (0, 1, 2) or position < 0:
            raise ValueError('invalid artifact seek')
        self.position = position
        return position

    def read(self, size=-1):
        size = min(self.size - self.position, size if size >= 0 else self.size - self.position)
        if size <= 0:
            return b''
        if size > 4 << 20:
            raise ValueError('diagnostic range exceeds 4 MiB; refusing a large artifact download')
        data = self.fetch(self.position, self.position + size - 1)
        if len(data) != size:
            raise ValueError('artifact range was truncated')
        self.position += size
        return data


def artifact_url(repository, artifact):
    token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/actions/artifacts/{artifact}/zip',
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'User-Agent': 'Omarchy-Aurora-diagnostics'})
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=30).close()
    except urllib.error.HTTPError as error:
        if error.code == 302:
            return error.headers['Location']
        raise RuntimeError(f'Artifact lookup failed: HTTP {error.code}') from None
    raise ValueError('expected an artifact download redirect')


def reader(url):
    # The API token is never forwarded to the artifact storage host.
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
        size = int(response.headers['Content-Length'])

    def fetch(start, end):
        request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
        with urllib.request.urlopen(request, timeout=60) as response:
            expected = f'bytes {start}-{end}/{size}'
            if response.status != 206 or response.headers.get('Content-Range') != expected:
                raise ValueError('artifact host did not honor the bounded byte range')
            return response.read(end - start + 2)
    return RangeReader(size, fetch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='aurora-silicon/omarchy-aurora')
    parser.add_argument('--artifact', type=int, required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository) or args.artifact <= 0:
        parser.error('expected a repository and positive artifact ID')
    if args.output.exists():
        parser.error('preserve existing evidence; choose a new output path')
    with zipfile.ZipFile(reader(artifact_url(args.repository, args.artifact))) as archive:
        entry = archive.getinfo(args.entry)
        if entry.file_size > 16 << 20 or entry.compress_size > 4 << 20:
            raise ValueError('this reader is limited to small diagnostic files')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(args.output.parent).free < (8 << 30) + entry.file_size:
            raise ValueError('writing this evidence would cross the 8 GiB free floor')
        data = archive.read(entry)
    args.output.write_bytes(data)
    print(json.dumps({'file': str(args.output), 'bytes': len(data)}))


if __name__ == '__main__':
    main()
