# crawlers/_lib/http.py
# 共享 requests Session，每 host 限速 1 QPS，retry 3 次指数退避，UA 池
import time
import threading
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

_last_request_per_host = {}
_lock = threading.Lock()


def _wait_for_quota(host):
    """每 host 1 QPS"""
    with _lock:
        last = _last_request_per_host.get(host, 0)
        now = time.time()
        if now - last < 1.0:
            time.sleep(1.0 - (now - last))
        _last_request_per_host[host] = time.time()


def get_session():
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST']),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


def fetch(url, session=None, timeout=15, headers=None, method='GET', data=None, retries=2):
    """GET/POST URL，自动限速 + UA 轮换 + retry"""
    s = session or get_session()
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    _wait_for_quota(host)
    ua = random.choice(USER_AGENTS)
    h = {'User-Agent': ua, 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'}
    if headers:
        h.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            if method.upper() == 'POST':
                r = s.post(url, headers=h, data=data, timeout=timeout)
            else:
                r = s.get(url, headers=h, timeout=timeout)
            r.raise_for_status()
            r.encoding = 'utf-8'
            return r.text
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 ** attempt)
    return None