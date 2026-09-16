# crawlers/torx.py
# TORX®（意大利 Valle d'Aosta，VDA Trailers 运营）——国际越野赛系列
# 赛事页 og:description 含结构化信息：<日期> <类型> Distance: / Elevation gain: / Maximum time: / Starting point:
# 用 og:title/og:description 解析，避免扫 700KB 页面正文（正文是 Brizy 拖拽生成，结构不稳定）
import sys, json, re, time, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch

OUT_DIR = ROOT / 'crawl' / 'output'
HOME = 'https://torxtrail.com/'

RE_RACE_LINK = re.compile(r'https://torxtrail\.com/(tor\d+-[a-z0-9-]+)/')
RE_OG = lambda key: re.compile(r'<meta (?:property|name)="og:%s" content="(.*?)"\s*/>' % key, re.S)
RE_TITLE_SUFFIX = re.compile(r'\s*-\s*TORX® with Kailas Endurance Trail\s*$')

MONTHS = 'January February March April May June July August September October November December'.split()
MONTH_RE = '|'.join(MONTHS)
RE_DATE_RANGE = re.compile(r'(\d{1,2})\s*/\s*(\d{1,2})\s+(%s)\s+(\d{4})' % MONTH_RE)
RE_DATE_ONE = re.compile(r'(\d{1,2})\s+(%s)\s+(\d{4})' % MONTH_RE)
RE_DIST = re.compile(r'Distance:\s*([\d.,]+)\s*k', re.I)
RE_ELEV = re.compile(r'Elevation gain:\s*([\d.,]+)\s*D\+', re.I)
RE_TIME = re.compile(r'Maximum time:\s*(\d+)\s*hours?', re.I)
RE_START = re.compile(r'Starting point:\s*(.+?)\s*(?:Finishing point|Date\s*:|Award)', re.S)


def _num(s):
    """'32.000' → 32000（欧式千分位）；'24000' → 24000"""
    return int(re.sub(r'[.,\s]', '', s))


def parse_race(page_html, link):
    """从赛事页 HTML 解析一场 TORX 赛事，返回 race dict 或 None"""
    m_title = RE_OG('title').search(page_html)
    m_desc = RE_OG('description').search(page_html)
    if not m_title or not m_desc:
        return None
    title = RE_TITLE_SUFFIX.sub('', html.unescape(m_title.group(1))).replace('–', '-')
    title = re.sub(r'\s+', ' ', title).strip()
    desc = html.unescape(m_desc.group(1))

    # 日期：赛事页开头紧跟名称，先试范围（"13 / 19 September 2026"）再试单日（"19 September 2026"）
    date = end_date = None
    rng = RE_DATE_RANGE.search(desc)
    if rng:
        d1, d2, mo, yr = int(rng.group(1)), int(rng.group(2)), rng.group(3), int(rng.group(4))
        mi = MONTHS.index(mo) + 1
        date = f'{yr}-{mi:02d}-{d1:02d}'
        if (mi, d2) != (mi, d1):
            end_date = f'{yr}-{mi:02d}-{d2:02d}'
    else:
        one = RE_DATE_ONE.search(desc)
        if one:
            mi = MONTHS.index(one.group(2)) + 1
            date = f'{int(one.group(3))}-{mi:02d}-{int(one.group(1)):02d}'
    if not date:
        return None

    dist = RE_DIST.search(desc)
    elev = RE_ELEV.search(desc)
    tlim = RE_TIME.search(desc)
    start = RE_START.search(desc)

    d_item = {'d': f'{_num(dist.group(1))}K'} if dist else None
    if d_item and elev:
        d_item['climb'] = f'{_num(elev.group(1))}m'
    if d_item and tlim:
        d_item['time'] = f'{tlim.group(1)}h'

    return {
        'source_id': link.rstrip('/').rsplit('/', 1)[-1],
        # 名称前缀系列品牌，否则页面搜索 "TORX" 匹配不到（站内标题只写 TOR330 等编号）
        'name': f'{date[:4]} TORX® {title}',
        'date': date,
        'end_date': end_date,
        'province': '海外',
        'city': re.sub(r'\s+', ' ', start.group(1)).strip() if start else 'Italy',
        'distances': [d_item] if d_item else [],
        'tags': ['itra', 'torx'],   # VDA Trailers 自 2014 年起为 ITRA 成员
        'link': link,
        'wechat': None,
        'official': None,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    home = fetch(HOME, timeout=20)
    if not home:
        print('[torx] 首页抓取失败')
        return
    slugs = sorted(set(RE_RACE_LINK.findall(home)))
    print(f'[torx] 首页找到 {len(slugs)} 场: {slugs}')
    races = []
    for slug in slugs:
        link = f'https://torxtrail.com/{slug}/'
        try:
            page = fetch(link, timeout=20)
            r = parse_race(page, link) if page else None
            if not r:
                print(f'  {slug}: 解析失败')
                continue
            races.append(r)
            print(f'  {slug}: {r["name"]} ({r["date"]}~{r["end_date"] or r["date"]}) {r["distances"]}')
        except Exception as e:
            print(f'  {slug}: 异常 {e}')
    print(f'[torx] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'torx.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'torx',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[torx] 写出: {out_path}')


def _selftest():
    """离线自检：og:meta 解析（含范围日期/单日/欧式千分位/名称后缀）"""
    def page(title, desc):
        return (f'<meta property="og:title" content="{title}" />'
                f'<meta property="og:description" content="{desc}" />')
    r = parse_race(page('TOR330 – TOR DES GÉANTS - TORX® with Kailas Endurance Trail',
                        'TOR330 - TOR DES GÉANTS®13 / 19 September 2026 Endurance trail '
                        'Distance: 330kmElevation gain: 24000 D+Maximum time: 150 hours'
                        'Starting point: Courmayeur - Valle d\'Aosta - ItalyFinishing point: x'),
                   'https://torxtrail.com/tor330-tor-des-geants/')
    assert r['name'] == '2026 TORX® TOR330 - TOR DES GÉANTS', r['name']
    assert (r['date'], r['end_date']) == ('2026-09-13', '2026-09-19'), r
    assert r['distances'] == [{'d': '330K', 'climb': '24000m', 'time': '150h'}], r['distances']
    r = parse_race(page('TOR30 – PASSAGE AU MALATRÀ - TORX® with Kailas Endurance Trail',
                        'TOR30 - PASSAGE AU MALATRÀ19 September 2026 Trail running competition '
                        'Distance: 30kElevation gain: 2.000 D+Maximum time: 8 hours'
                        'Starting point: Saint-Rhémy-en-Bosses - ItalyFinishing point: y'),
                   'https://torxtrail.com/tor30-passage-au-malatra/')
    assert (r['date'], r['end_date']) == ('2026-09-19', None), r
    assert r['distances'] == [{'d': '30K', 'climb': '2000m', 'time': '8h'}], r['distances']
    print('[torx] selftest OK')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        _selftest()
    else:
        main()
