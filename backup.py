#!/usr/bin/env python3
import argparse
import os
import sys
import json
import time
import pathlib
import ssl
from datetime import datetime
from typing import Optional, Tuple

import requests
from truenas_api_client import Client


def read_api_key(explicit_key: Optional[str], api_key_file: Optional[str]) -> Optional[str]:
    if explicit_key:
        return explicit_key.strip()
    if api_key_file:
        with open(api_key_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    env_key = os.environ.get('TRUENAS_API_KEY')
    if env_key:
        return env_key.strip()
    return None


def ensure_output_dir(path: str) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def build_ws_base(host: str) -> str:
    # Accept inputs like 127.0.0.1, http(s)://host, ws(s)://host/api/current
    h = host.strip()
    if h.startswith('ws://') or h.startswith('wss://'):
        return h.rstrip('/')
    if h.startswith('http://'):
        return 'ws://' + h[len('http://'):].rstrip('/')
    if h.startswith('https://'):
        return 'wss://' + h[len('https://'):].rstrip('/')
    # Bare host/IP defaults to https → wss
    return 'wss://' + h


def build_http_base(host: str) -> str:
    h = host.strip()
    if h.startswith('http://') or h.startswith('https://'):
        return h.rstrip('/')
    if h.startswith('ws://'):
        return 'http://' + h[len('ws://'):].rstrip('/')
    if h.startswith('wss://'):
        return 'https://' + h[len('wss://'):].rstrip('/')
    return 'https://' + h


def ws_api_url(host: str) -> str:
    base = build_ws_base(host)
    if base.endswith('/api/current'):
        return base
    return base + '/api/current'


def http_api_base(host: str) -> str:
    return build_http_base(host)


def call_ws_jsonrpc(uri: str, method: str, params=None, headers=None, verify_tls: bool = True):
    # Use requests to POST to REST shim if available; otherwise prefer core.download with token
    # Many TrueNAS installs support POST /api/v2.0/core/download
    raise NotImplementedError


def start_download_session(host: str, api_key: str, include_secrets: bool, verify_tls: bool) -> Tuple[str, str]:
    """Use WebSocket JSON-RPC (core.download -> config.save) to receive a URL and token.

    Returns (download_url, token)
    """
    uri = ws_api_url(host)
    ssl_ctx = None
    if uri.startswith('wss://'):
        if not verify_tls:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
    # Authenticate with API key and request download URL via core.download
    with Client(uri=uri, ssl=ssl_ctx) as client:
        client.call('auth.login_with_api_key', api_key)
        args = {'secretseed': include_secrets}
        result = client.call('core.download', 'config.save', [args], 'config.tar')
        if isinstance(result, dict):
            dl_url = result.get('url') or result.get('result') or result.get('job_url')
            token = result.get('token') or result.get('auth_token')
        elif isinstance(result, list) and len(result) >= 2:
            dl_url = result[1]
            token = result[2] if len(result) >= 3 else None
        else:
            raise RuntimeError(f'Unexpected response from core.download: {result!r}')
        if not dl_url:
            raise RuntimeError('No download URL returned by core.download')
        return dl_url, (token or '')


def download_file(host: str, download_url: str, token: str, verify_tls: bool) -> bytes:
    base = http_api_base(host)
    # download_url may already be absolute; if relative, prefix base
    if download_url.startswith('http://') or download_url.startswith('https://'):
        full_url = download_url
    else:
        full_url = base + download_url
    params = {}
    if token:
        params['auth_token'] = token
    resp = requests.get(full_url, params=params, verify=verify_tls, timeout=300)
    resp.raise_for_status()
    return resp.content


def enforce_retention(directory: str, retention: int) -> None:
    if retention <= 0:
        return
    files = sorted(
        [f for f in pathlib.Path(directory).glob('truenas_config_*.tar') if f.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[retention:]:
        try:
            old.unlink()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description='Download TrueNAS configuration backup via API')
    parser.add_argument('--host', required=True, help='TrueNAS host/IP or URL (e.g., 127.0.0.1 or https://truenas.local)')
    parser.add_argument('--out-dir', required=True, help='Directory to store backups')
    parser.add_argument('--api-key', help='API key; falls back to TRUENAS_API_KEY env')
    parser.add_argument('--api-key-file', help='Path to file containing API key')
    parser.add_argument('--include-secrets', action='store_true', help='Include secretseed in backup')
    parser.add_argument('--no-verify-tls', action='store_true', help='Disable TLS verification')
    parser.add_argument('--retention', type=int, default=14, help='Keep last N backups (default: 14)')

    args = parser.parse_args()
    verify_tls = not args.no_verify_tls

    api_key = read_api_key(args.api_key, args.api_key_file)
    if not api_key:
        print('Error: API key not provided. Use --api-key, --api-key-file, or TRUENAS_API_KEY env.', file=sys.stderr)
        return 2

    ensure_output_dir(args.out_dir)

    try:
        download_url, token = start_download_session(args.host, api_key, args.include_secrets, verify_tls)
        content = download_file(args.host, download_url, token, verify_tls)
    except requests.HTTPError as e:
        print(f'HTTP error: {e.response.status_code} {e.response.text}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = os.path.join(args.out_dir, f'truenas_config_{timestamp}.tar')
    with open(out_path, 'wb') as f:
        f.write(content)
    print(f'Wrote {out_path}')

    enforce_retention(args.out_dir, args.retention)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


