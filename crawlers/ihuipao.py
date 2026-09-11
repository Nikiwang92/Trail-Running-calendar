# crawlers/ihuipao.py
# 爱汇跑 — ihuipao.com / v6.ihuipao.com
# 列表：https://www.ihuipao.com/race?page=N
# 详情：https://www.ihuipao.com/race/{slug}
import sys, json, re, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.parse import parse_cn_date, parse_distance_km
from _lib.province import split_province_city
from _lib.tags import infer_tags

BASE = 'https://www.ihuipao.com'
LIST_URL = BASE + '/race?page={page}&racesort=time'
OUT_DIR = ROOT / 'crawl' / 'output'

# 列表 HTML 中的赛事 link
RE_RE_EVENT = re.compile(r'href="(/race/[A-Za-z0-9]+)"[^>]*>([^<]+)<')


TRAIL_KW = ['越野', '跑山', '超马', '超级', '山地', 'trail', 'ultra', '山径', '户外越野', 'by UTMB', '黄金联赛']

def is_trail(title):
    return any(kw.lower() in title.lower() for kw in TRAIL_KW)


def list_page(page, session):
    html = fetch(LIST_URL.format(page=page), session=session, timeout=15)
    if not html:
        return []
    items = []
    for m in RE_RE_EVENT.finditer(html):
        slug = m.group(1).split('/')[-1]
        title = m.group(2).strip()
        if not title or len(title) < 4:
            continue
        if not is_trail(title):
            continue
        items.append({'slug': slug, 'title': title, 'url': BASE + m.group(1)})
    seen, uniq = set(), []
    for it in items:
        if it['slug'] not in seen:
            seen.add(it['slug']); uniq.append(it)
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
    m = re.search(r'(?:比赛时间|赛事时间|活动时间|比赛日期)[:：\s]+(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[^\n]{0,30})', text)
    if m:
        seg = m.group(1)
        date = parse_cn_date(seg)
        if date:
            end_seg = re.search(r'(?:至|到|—|-|~)\s*(\d{1,2}[-/月]\d{1,2})', seg)
            if end_seg:
                y = seg[:4]
                ed = parse_cn_date(y + end_seg.group(1).replace('-', '-').replace('/', '月') + '日')
                end_date = ed
    # 兜底：从全文找首个 YYYY年MM月DD日
    if not date:
        from _lib.parse import CN_DATE_RE
        mm = CN_DATE_RE.search(text)
        if mm:
            date = f"{mm.group(1)}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
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
    # wechat
    from _lib.wechat import extract_wechat, is_valid_wechat
    wechat = extract_wechat(text)
    if wechat and not is_valid_wechat(wechat):
        wechat = None
    return {
        'name': name,
        'date': date,
        'end_date': end_date,
        'province': province,
        'city': city or '',
        'distances': distances,
        'wechat': wechat,
        'raw_text': text[:500],
    }


def crawl(start_page=1, max_pages=5):
    s = get_session()
    races = []
    seen = set()
    empty_count = 0
    for p in range(start_page, start_page + max_pages):
        items = list_page(p, s)
        if not items:
            empty_count += 1
            if empty_count >= 2:
                break
            continue
        empty_count = 0
        print(f'[ihuipao] 第{p}页: {len(items)} 条')
        for it in items:
            if it['slug'] in seen:
                continue
            seen.add(it['slug'])
            html = fetch(it['url'], session=s, timeout=15)
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
                'wechat': info.get('wechat'),
            })
    return races


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = crawl()
    print(f'[ihuipao] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'ihuipao.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'ihuipao',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[ihuipao] 写出: {out_path}')


if __name__ == '__main__':
    main()