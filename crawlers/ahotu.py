# crawlers/ahotu.py
# ahotu.com 国际赛事聚合 — 中国越野赛
# 列表：https://www.ahotu.com/zh/calendar/trail-running/china
# 详情：https://www.ahotu.com/zh/event/{slug}
import sys, json, re, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.parse import parse_cn_date, parse_distance_km, parse_climb
from _lib.province import split_province_city
from _lib.tags import infer_tags

BASE = 'https://www.ahotu.com'
LIST_URL = BASE + '/zh/calendar/trail-running/china?page={page}'
OUT_DIR = ROOT / 'crawl' / 'output'

# 列表里赛事是 <a href="/zh/event/{slug}"> {title} <span>...</span> </a>
RE_EVENT_LINK = re.compile(r'href="(/zh/event/[a-z0-9-]+)"[^>]*>([^<]+?)(?:<span|$)', re.MULTILINE)
RE_EVENT_DATE = re.compile(r'(\d{4}\.\d{1,2}\.\d{1,2})')


def list_page(page, session):
    """拉一页中国越野赛列表"""
    html = fetch(LIST_URL.format(page=page), session=session, timeout=15)
    if not html:
        return []
    items = []
    for m in RE_EVENT_LINK.finditer(html):
        url_path = m.group(1)
        title = m.group(2).strip()
        if not title or len(title) < 4:
            continue
        slug = url_path.split('/')[-1]
        items.append({'slug': slug, 'title': title, 'url': BASE + url_path})
    # 去重
    seen, uniq = set(), []
    for it in items:
        if it['slug'] not in seen:
            seen.add(it['slug']); uniq.append(it)
    return uniq


def parse_detail(html):
    """解析详情页 HTML"""
    if not html:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n', strip=True)
    # 名称
    h1 = soup.find('h1')
    name = h1.get_text(strip=True) if h1 else None
    # 日期
    date = None
    end_date = None
    # 形如 "2026.11.08" 或 "2026.11.08-2026.11.10"
    m = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})(?:\s*[-—至]\s*(\d{4}\.\d{1,2}\.\d{1,2}))?', text)
    if m:
        date = m.group(1).replace('.', '-')
        if m.group(2):
            end_date = m.group(2).replace('.', '-')
    # 组别距离 / 爬升
    distances = []
    for d in parse_distance_km(text):
        distances.append({'d': d})
    climb = parse_climb(text)
    if climb and distances:
        distances[0]['climb'] = climb
    # 地点（"城市: xxx" / "Location: xxx"）
    city = None
    m = re.search(r'(?:城市|地点|Location|City)[:：\s]+([一-龥A-Za-z\s,，·]{3,40})', text)
    if m:
        city = m.group(1).strip().split('\n')[0][:30]
    if city:
        province, _ = split_province_city(city)
    else:
        province = ''
    # wechat: 不在 ahotu 上，跳过
    return {
        'name': name,
        'date': date,
        'end_date': end_date,
        'province': province,
        'city': city or '',
        'distances': distances,
        'raw_text': text[:500],
    }


"""如果 Cloudflare 拦截，尝试 Selenium 渲染"""
USE_SELENIUM = True


def get_selenium():
    """用 Edge 浏览器绕过 Cloudflare"""
    if not USE_SELENIUM:
        return None
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        opts.add_argument('--user-agent=M=M=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        return webdriver.Edge(options=opts)
    except Exception as e:
        print(f'[ahotu] Selenium 初始化失败: {e}')
        return None


def fetch_with_selenium(url, wait=8):
    d = get_selenium()
    if not d:
        return None
    try:
        d.get(url)
        import time as t
        t.sleep(wait)
        html = d.page_source
        d.quit()
        return html
    except Exception:
        try:
            d.quit()
        except Exception:
            pass
        return None


def crawl(start_page=1, max_pages=20):
    s = get_session()
    races = []
    seen = set()
    empty_count = 0
    for p in range(start_page, start_page + max_pages):
        items = list_page(p, s)
        if not items:
            # Selenium 兜底
            list_html = fetch_with_selenium(LIST_URL.format(page=p))
            if list_html:
                items = []
                for mm in RE_EVENT_LINK.finditer(list_html):
                    url_path = mm.group(1)
                    title = mm.group(2).strip()
                    if not title or len(title) < 4:
                        continue
                    slug = url_path.split('/')[-1]
                    items.append({'slug': slug, 'title': title, 'url': BASE + url_path})
                seen_items = set()
                items = [i for i in items if i['slug'] not in seen_items and not seen_items.add(i['slug'])]
        if not items:
            empty_count += 1
            if empty_count >= 2:
                break
            continue
        empty_count = 0
        print(f'[ahotu] 第{p}页: {len(items)} 条')
        for it in items:
            if it['slug'] in seen:
                continue
            seen.add(it['slug'])
            html = fetch(it['url'], session=s, timeout=15)
            if not html:
                html = fetch_with_selenium(it['url'])
            if not html:
                continue
            info = parse_detail(html)
            if not info or not info.get('name') or not info.get('date'):
                continue
            if not info['date'].startswith('2026'):
                continue
            races.append({
                'source_id': it['slug'],
                'name': info['name'],
                'date': info['date'],
                'end_date': info.get('end_date'),
                'province': info.get('province', ''),
                'city': info.get('city', ''),
                'distances': info.get('distances', []),
                'tags': infer_tags(info['name']),
            'link': it['url'],
                'wechat': None,
            })
    return races


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = crawl()
    print(f'[ahotu] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'ahotu.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'ahotu',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[ahotu] 写出: {out_path}')


if __name__ == '__main__':
    main()