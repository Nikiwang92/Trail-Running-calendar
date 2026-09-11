# crawlers/utmb.py
# UTMB World Series：从 _race_data.js 抽已知子域名列表 + 解析 RSC payload
# 中文名优先：如果 _race_data.js 里有同 link 的中文名，用中文名
import sys, json, re, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.tags import infer_tags
from _lib.province import split_province_city

OUT_DIR = ROOT / 'crawl' / 'output'

RE_NAME = re.compile(r'"name":"([^"]+)"')
RE_START = re.compile(r'"startDate":"(\d{4}-\d{2}-\d{2})"')
RE_END = re.compile(r'"endDate":"(\d{4}-\d{2}-\d{2})"')
RE_DIST = re.compile(r'"distance(?:Km|Distance)":(\d+(?:\.\d+)?)')
RE_ELEV = re.compile(r'"(?:positiveElevation|elevation(?:Gain)?)":(\d+(?:[, ]\d{3})*)')
RE_CITY = re.compile(r'"city":"([^"]+)"')
RE_COUNTRY = re.compile(r'"country":"([^"]+)"')


def get_subdomains_from_race_data():
    """从 _race_data.js + 内置默认清单抽所有 utmb.world 子域名"""
    src_path = ROOT / '_race_data.js'
    sub = set()
    if src_path.exists():
        src = src_path.read_text(encoding='utf-8')
        for m in re.finditer(r'https?://([a-z0-9-]+)\.utmb\.world', src):
            sub.add(m.group(1))
    # 内置默认清单（首次部署 _race_data.js 为空时使用）
    for default in ('dajingmen', 'mogan', 'mount-yun', 'shudao', 'xiamen'):
        sub.add(default)
    return sorted(sub)


def build_alias_map():
    """从 _race_data.js 抽 link -> 中文名（用于英文名去重）
    例如 { 'dajingmen.utmb.world/zh-Hans': '2026京东大境门古长城越野赛byUTMB®' }
    """
    src_path = ROOT / '_race_data.js'
    src = src_path.read_text(encoding='utf-8')
    alias = {}
    for m in re.finditer(r'name:\s*"([^"]+)"[^{}]*?link:\s*"(https?://[a-z0-9-]+\.utmb\.world/[^"]+)"', src):
        name = m.group(1)
        link = m.group(2).rstrip('/')
        alias[link] = name
    return alias


def parse_subdomain(slug):
    """访问 {slug}.utmb.world/zh-Hans/ 解析 RSC payload"""
    url = f'https://{slug}.utmb.world/zh-Hans/'
    html = fetch(url, timeout=20)
    if not html:
        return None
    name_m = RE_NAME.search(html)
    if not name_m:
        return None
    name = name_m.group(1)
    if name.lower() in ('facebook', 'instagram', 'hoka', 'suunto', 'tudor'):
        return None
    start = RE_START.search(html)
    end = RE_END.search(html)
    dist = RE_DIST.search(html)
    elev = RE_ELEV.search(html)
    city_m = RE_CITY.search(html)
    country_m = RE_COUNTRY.search(html)
    return {
        'name': name,
        'date': start.group(1) if start else None,
        'end_date': end.group(1) if end else None,
        'distance_km': float(dist.group(1)) if dist else None,
        'elevation_m': int(elev.group(1).replace(',', '').replace(' ', '')) if elev else None,
        'city': city_m.group(1) if city_m else None,
        'country': country_m.group(1) if country_m else None,
        'slug': slug,
        'link': url,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subs = get_subdomains_from_race_data()
    alias = build_alias_map()
    print(f'[utmb] 已知子域名: {len(subs)} 个, 中文别名: {len(alias)} 个')
    races = []
    for slug in subs:
        try:
            info = parse_subdomain(slug)
            if not info:
                print(f'  {slug}: 解析失败')
                continue
            link_key = info['link'].rstrip('/')
            # 如果 RSC name 是英文（含非中文）且有中文别名，用中文名
            if link_key in alias and not any('一' <= c <= '鿿' for c in info['name']):
                info['name'] = alias[link_key]
            # 城市 → province/city
            province, city = split_province_city(info.get('city') or '')
            distances = []
            if info.get('distance_km'):
                km = info['distance_km']
                d = f'{int(km) if km == int(km) else km}K'
                item = {'d': d}
                if info.get('elevation_m'):
                    item['climb'] = f"{info['elevation_m']}m"
                distances.append(item)
            races.append({
                'source_id': slug,
                'name': info['name'],
                'date': info.get('date'),
                'end_date': info.get('end_date'),
                'province': province,
                'city': city,
                'distances': distances,
                'tags': ['utmb', 'itra'],
                'link': info['link'],
                'wechat': None,
            })
            print(f'  {slug}: {info["name"][:30]} ({info.get("date", "?")})')
        except Exception as e:
            print(f'  {slug}: 异常 {e}')
    print(f'[utmb] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'utmb.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'utmb',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[utmb] 写出: {out_path}')


if __name__ == '__main__':
    main()