# crawlers/utmb.py
# UTMB World Series（全球）—— 官方 API utmblive-api.utmb.world
#   /event-future?locale=zh-Hans             在售/未来（含 2027）
#   /event-utmbworld/history?locale=zh-Hans  本年度已办/进行中
# 每条含 tenant / title / url(= https://<tenant>.utmb.world) / country(cityCode)
#        / startDateIso|dateStart / endDateIso|dateEnd / raceCategories / placeName
#
# **去重**：url 的 host（<tenant>.utmb.world）就是跨平台主键——
#   ① 中文条目若带同域 `official` → 本条目被 `drop_claimed_duplicates` / `detect_new` 跳过；
#   ② 已有条目 link 就是该 utmb 子域 → `detect_new` 的 `utmb:<slug>` 判定拦下。
#   故中国站（大境门/厦门/莫干山/云丘山/蜀道）不会与最酷网重复。
import sys, json, re, time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch

OUT_DIR = ROOT / 'crawl' / 'output'
DATA_FILE = ROOT / '_race_data.js'
API = 'https://utmblive-api.utmb.world'
ENDPOINTS = ['/event-future?locale=zh-Hans', '/event-utmbworld/history?locale=zh-Hans']

REGION = {'HK': '香港', 'MO': '澳门', 'TW': '台湾'}     # 其余境外 → 海外
RE_CAT = re.compile(r'^(\d+)\s*([km])$', re.I)
RE_UTMB_HOST = re.compile(r'https?://((?:[a-z0-9-]+\.)*utmb\.world)')


def _dist(cat):
    """'100k' → '100K'；'100m'（英里）→ '100M'"""
    m = RE_CAT.match((cat or '').strip())
    return f'{int(m.group(1))}{m.group(2).upper()}' if m else None


def build_alias_map():
    """已有 utmb 子域条目的 <完整 host> → 中文名（保留中文名，避免被英文名覆盖）。
    用完整 host 做键：API 的 tenant（mountyun）与子域 slug（mount-yun）拼写并不一致。"""
    alias = {}
    if not DATA_FILE.exists():
        return alias
    for line in DATA_FILE.read_text(encoding='utf-8').split('\n'):
        m = re.search(r'name:\s*"((?:[^"\\]|\\.)*)"', line)
        h = RE_UTMB_HOST.search(line)
        if m and h:
            try:
                alias[h.group(1)] = json.loads('"' + m.group(1) + '"')
            except Exception:
                pass
    return alias


def _norm(e):
    """API 条目 → 本项目 race dict"""
    tenant = e.get('tenant') or ''
    year = e.get('year')
    url = e.get('url') or f'https://{tenant}.utmb.world'
    host = urlparse(url).netloc.lower() or f'{tenant}.utmb.world'
    cc = (e.get('countryCode') or '').upper()
    country = (e.get('country') or '').strip()
    place = (e.get('placeName') or '').strip()
    city = f'{country}·{place}' if place and place.lower() not in country.lower() else country
    dists = [_dist(c) for c in (e.get('raceCategories') or [])]
    return {
        'source_id': f'{tenant}-{year}',
        'name': e.get('title') or '',
        'date': e.get('startDateIso') or e.get('dateStart'),
        'end_date': e.get('endDateIso') or e.get('dateEnd'),
        'province': REGION.get(cc, '海外'),
        'city': city,
        'country_code': cc,
        'distances': [{'d': d} for d in dists if d],
        'tags': ['utmb'],
        # link 必须带届次：<tenant>.utmb.world 是年无关的赛事官网，同一赛事 2026/2027 两届
        # 若共用同一个 link，会被合并层的 link 去重合成一条。加 ?year= 只是给去重用的区分符，
        # 站点会忽略该参数（host/slug 不受影响，认领与 `utmb:<slug>` 判定照常工作）。
        'link': f'{url}?year={year}' if year else url,
        'wechat': None,
        'official': None,   # 不设：设了会让 drop_claimed_duplicates 把自己判成重复
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    alias = build_alias_map()
    print(f'[utmb] 已有中文别名: {len(alias)} 个')
    raw, seen = [], set()
    for path in ENDPOINTS:
        body = fetch(API + path, timeout=25)
        if not body:
            print(f'[utmb] {path} 抓取失败')
            continue
        try:
            data = json.loads(body)
        except Exception as ex:
            print(f'[utmb] {path} 解析失败: {ex}')
            continue
        print(f'[utmb] {path} → {len(data)} 条')
        for e in data:
            k = (e.get('tenant'), e.get('year'))
            if k in seen:
                continue
            seen.add(k)
            raw.append(e)

    races = []
    for e in raw:
        r = _norm(e)
        if not r['name'] or not r['date']:
            print(f"  {e.get('tenant')}: 缺名称/日期，跳过")
            continue
        # 已有同 utmb 子域的中文条目 → 用它（本项目以中文为准）
        zh = alias.get(urlparse(r['link']).netloc.lower())
        if zh:
            r['name'] = zh
        races.append(r)
    print(f'[utmb] 总计 {len(races)} 场（{sum(1 for r in races if r["province"] != "海外")} 场港澳台）')
    out_path = OUT_DIR / 'utmb.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'utmb',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[utmb] 写出: {out_path}')


def _selftest():
    """离线自检：组别映射 / 港澳台归属 / 城市拼接 / 去重键"""
    assert _dist('100k') == '100K' and _dist('100m') == '100M' and _dist('20k') == '20K'
    assert _dist('xx') is None
    r = _norm({'tenant': 'translantau', 'year': 2026, 'title': 'Translantau™ by UTMB®',
               'url': 'https://translantau.utmb.world', 'countryCode': 'HK',
               'country': 'Hong Kong, China', 'placeName': 'Lantau Island',
               'startDateIso': '2026-11-13', 'endDateIso': '2026-11-15',
               'raceCategories': ['50k', '100k']})
    assert r['province'] == '香港' and r['city'] == 'Hong Kong, China·Lantau Island', r
    assert r['link'] == 'https://translantau.utmb.world?year=2026' and r['date'] == '2026-11-13'
    assert [d['d'] for d in r['distances']] == ['50K', '100K'], r['distances']
    r = _norm({'tenant': 'paraty', 'year': 2026, 'title': 'Paraty Brazil by UTMB',
               'url': 'https://paraty.utmb.world', 'countryCode': 'BR',
               'country': 'Brazil', 'placeName': 'Paraty', 'startDateIso': '2026-09-17'})
    assert r['province'] == '海外' and r['city'] == 'Brazil·Paraty', r
    print('[utmb] selftest OK')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        _selftest()
    else:
        main()
