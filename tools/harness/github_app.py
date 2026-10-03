"""Minimal GitHub App client. Tokens stay in memory, never argv/logs or workers."""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PERMISSIONS = {'checks': 'write', 'contents': 'read', 'pull_requests': 'read',
               'metadata': 'read'}


def private_file(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError('configuration/key/admission must be an owner-only regular file')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('GitHub API redirects are forbidden')


def api(method: str, path: str, token: str, body: Any = None) -> Any:
    if not path.startswith('/') or path.startswith('//') or '?' in path:
        raise ValueError('invalid GitHub API path')
    request = urllib.request.Request('https://api.github.com' + path,
        data=None if body is None else json.dumps(body).encode(), method=method,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'KineticLoop-local-gate',
                 'Content-Type': 'application/json'})
    try:
        # Do not inherit proxy settings or forward credentials through redirects.
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(
                request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f'GitHub API {method} failed with HTTP {error.code}') from None


def jwt(app_id: int, key: Path) -> str:
    private_file(key)
    def encode(value: bytes) -> bytes:
        return base64.urlsafe_b64encode(value).rstrip(b'=')
    now = int(time.time())
    message = encode(b'{"alg":"RS256","typ":"JWT"}') + b'.' + encode(json.dumps(
        {'iat': now - 60, 'exp': now + 480, 'iss': str(app_id)}).encode())
    signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key)],
        input=message, capture_output=True, check=True, timeout=15).stdout
    return (message + b'.' + encode(signature)).decode()


class App:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.token = ''
        self.deadline = 0.0

    def refresh(self) -> None:
        config = self.config
        token = jwt(config['app_id'], Path(config['key_path']))
        install = api('GET', '/app/installations/' + str(config['installation_id']), token)
        if (install['app_id'] != config['app_id'] or install['suspended_at'] is not None
                or install['repository_selection'] != 'selected'
                or install['permissions'] != PERMISSIONS
                or install['account']['login'] != config['repository'].split('/')[0]):
            raise ValueError('App installation identity, scope or permissions differ')
        result = api('POST', '/app/installations/' + str(config['installation_id'])
                     + '/access_tokens', token,
                     {'repository_ids': [config['repository_id']], 'permissions': PERMISSIONS})
        self.token = result['token']
        self.deadline = time.monotonic() + 3000

    def request(self, method: str, path: str, body: Any = None) -> Any:
        if time.monotonic() >= self.deadline:
            self.refresh()
        return api(method, path, self.token, body)
