import os
import time
import json
from typing import List, Dict
import requests


def get_base_url() -> str:
    return os.environ.get('MMCOE_BASE_URL', 'http://localhost:5000')


def bearer() -> Dict[str, str]:
    token = os.environ.get('MMCOE_AUTH_TOKEN', '').strip()
    return {'Authorization': f'Bearer {token}'} if token else {}


def fetch_routes(base: str) -> List[Dict]:
    try:
        r = requests.get(f'{base}/health/routes', timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'[monitor] Failed to fetch routes: {e}')
        return []


def probe(url: str, method: str = 'GET', headers: Dict[str, str] = None) -> int:
    try:
        h = headers or {}
        resp = requests.request(method, url, headers=h, timeout=10)
        return resp.status_code
    except Exception:
        return 0


def main():
    base = get_base_url()
    interval = float(os.environ.get('MMCOE_MONITOR_INTERVAL', '15'))
    print(f'[monitor] Starting route monitor against {base} every {interval}s')
    while True:
        routes = fetch_routes(base)
        summary = {
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'ok': 0,
            'fail': 0,
            'checked': 0,
            'details': []
        }
        for r in routes:
            rule = r.get('rule', '')
            methods = r.get('methods', [])
            # Only GET probes by default
            if 'GET' not in methods:
                continue
            url = f'{base}{rule}'
            # Skip dynamic or unsafe endpoints
            if any(seg.startswith('<') and seg.endswith('>') for seg in rule.split('/')):
                continue
            code = probe(url, 'GET', bearer())
            summary['checked'] += 1
            if 200 <= code < 400:
                summary['ok'] += 1
            else:
                summary['fail'] += 1
                summary['details'].append({'url': url, 'status': code})
        print('[monitor]', json.dumps(summary))
        time.sleep(interval)


if __name__ == '__main__':
    main()


