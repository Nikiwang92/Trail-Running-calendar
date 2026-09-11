# crawlers/runninginchina.py
# 跑 IN 中国 — runninginchina.org
# 列表：https://www.runninginchina.org/event/index.html?type_id=3&page=N
# 详情：https://www.runninginchina.org/event/extra_view/{id}.html
import sys, json, re, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.parse import parse_cn_date, parse_distance_km
from _lib.province import split_province_city
from _lib.tags import infer_tags

BASE = 'https://www.runninginchina.org'
LIST_URL = BASE + '/event/index.html?type_id=3&page={page}'
OUT_DIR = ROOT / 'crawl' / 'output'

RE_RE_EVENT = re.compile(r'href="(/event/(?:event_view|extra_view|view)/\d+\.html)"[^>]*>([^<]+)<')
RE_DATE_LIST = re.compile(r'(?:比赛时间[：:]\s*)?(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})')
RE_STATUS_WORDS = re.compile(r'(报名已经截止|报名正在进行|报名中[：:]?|报名中|已截止|已结束|报名即将开始|下届比赛|上届比赛|官方网址|赛事官网|报名未开始)')


def list_page(page, session):
    """列表行含 名称/日期/地点，直接解析，无需详情页。
    行文本示例："长白山林海雪原穿越赛 2026.12.06 报名已经截止 太湖" """
    html = fetch(LIST_URL.format(page=page), session=session, timeout=15)
    if not html:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    for a in soup.find_all('a', href=re.compile(r'/event/(?:event_view|extra_view|view)/\d+\.html')):
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        eid = re.search(r'/(\d+)\.html', a['href']).group(1)
        # 从锚点向上找第一个含日期的容器行
        row_text = title
        node = a
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            t = node.get_text(' ', strip=True)
            row_text = t
            if RE_DATE_LIST.search(t):
                break
        date = None
        dm = RE_DATE_LIST.search(row_text)
        if dm:
            date = f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
        # 地点 = 行文本去掉名称/日期/状态词后的残留
        rest = row_text.replace(title, '', 1)
        rest = RE_DATE_LIST.sub('', rest, count=1)
        rest = RE_STATUS_WORDS.sub('', rest)
        rest = re.sub(r'(?:比赛地点|赛事地点|举办地点|地点)[：:]\s*', '', rest)
        city = rest.strip(' ·,，。')[:24]
        items.append({'id': eid, 'title': title, 'url': BASE + a['href'],
                      'date': date, 'city': city})
    seen, uniq = set(), []
    for it in items:
        if it['id'] not in seen:
            seen.add(it['id']); uniq.append(it)
    return uniq


def parse_detail(html):
    if not html:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n', strip=True)
    h1 = soup.find('h1')
    name = h1.get_text(strip=True) if h1 else None
    # 日期
    date = None
    end_date = None
    m = re.search(r'(?:比赛时间|赛事时间|活动时间|比赛日期)[:：\s]*(\d{4}[-/]\d{1,2}[-/]\d{1,2}[^\n]{0,30})', text)
    if m:
        seg = m.group(1)
        date = parse_cn_date(seg)
        if date:
            end_seg = re.search(r'(?:至|到|—|-|~)\s*(\d{1,2}[-/]\d{1,2})', seg)
            if end_seg:
                y = seg[:4]
                ed = parse_cn_date(y + end_seg.group(1).replace('-', '-'))
                end_date = ed
    # 距离
    distances = []
    for d in parse_distance_km(text):
        distances.append({'d': d})
    # 地点
    city = None
    m = re.search(r'(?:赛事地点|比赛地点|举办地点|地点)[:：\s]+([一-龥A-Za-z\s,，·省市区县]{3,30})', text)
    if m:
        city = m.group(1).strip().split('\n')[0][:30]
    province = ''
    if city:
        province, _ = split_province_city(city)
    return {
        'name': name,
        'date': date,
        'end_date': end_date,
        'province': province,
        'city': city or '',
        'distances': distances,
        'raw_text': text[:500],
    }


def get_selenium():
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        return webdriver.Edge(options=opts)
    except Exception:
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


def crawl(start_page=1, max_pages=12, year_filter='2026'):
    s = get_session()
    races = []
    seen = set()
    miss = 0
    for p in range(start_page, start_page + max_pages):
        items = list_page(p, s)
        matched = [it for it in items if (it.get('date') or '').startswith(year_filter)]
        print(f'[runninginchina] 第{p}页: {len(items)} 条, {year_filter} 年 {len(matched)} 条')
        if not matched:
            miss += 1
            if miss >= 2:
                print(f'[runninginchina] 连续 {miss} 页无 {year_filter}，停止')
                break
            continue
        miss = 0
        for it in matched:
            if it['id'] in seen:
                continue
            seen.add(it['id'])
            # 只取列表行的名称/日期/地点；详情页解析质量差（组别噪声大），不取 distances
            city = it.get('city') or ''
            province = split_province_city(city)[0] if city else ''
            races.append({
                'source_id': it['id'],
                'name': it['title'],
                'date': it['date'],
                'end_date': None,
                'province': province,
                'city': city,
                'distances': [],
                'tags': infer_tags(it['title']),
                'link': it['url'],
                'wechat': None,
            })
    return races


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = crawl()
    print(f'[runninginchina] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'runninginchina.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'runninginchina',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[runninginchina] 写出: {out_path}')


if __name__ == '__main__':
    main()