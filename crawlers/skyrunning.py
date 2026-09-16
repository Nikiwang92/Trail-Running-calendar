# crawlers/skyrunning.py
# Skyrunning（ISF 国际天空跑联合会，skyrunning.com）——国际天空跑/越野系列
# 日历页(1 请求) 是 HTML 表格：名称 / 日期 dd/mm/yy / 国家 / 项目(Sky/Vertical/Ultra…) / 单场页链接
# 单场页含：距离、垂直爬升、官网域名（跨平台去重键）
#
# 去重策略：**中国境内的比赛直接跳过**。zuicool 是中国赛事的权威来源，
# 而本站在中国只列英文名（如 "Yading SkyRace®" ↔ zuicool「稻城亚丁天空跑」），
# 中英异名无法靠名称/日期去重，跳过是唯一可靠的防重复手段（不丢数据：zuicool 已有）。
import sys, json, re, time, math, html
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch

OUT_DIR = ROOT / 'crawl' / 'output'
CALENDAR = 'https://www.skyrunning.com/calendar/'

RE_SINGLE = re.compile(r'/single-race/([^/"?#]+)/')
RE_DDMMYY = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2})')
RE_DIST = re.compile(r'Distance:\s*([\d.,]+)\s*km', re.I)
RE_VERT = re.compile(r'Vertical climb:\s*([\d.,]+)\s*m', re.I)
RE_HREF = re.compile(r'href="(https?://[^"]+)"')

SKIP_COUNTRY = {'china', 'hong kong', 'hongkong', 'taiwan', 'macau', 'macao'}
BLOCK_HOSTS = ('skyrunning.com', 'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
               'youtube.com', 'docs.google.com', 'iubenda.com', 'googletagmanager.com',
               'google.com', 'gmpg.org', 'maxcdn', 'cloudflare', 'bunny.net')


def parse_calendar(page_html):
    """解析日历表 → [{slug, name, date, country, discipline, link}]（未过滤）"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_html, 'html.parser')
    out = []
    for tr in soup.select('tr'):
        a = tr.select_one('.rnk_list_name a')
        if not a:
            continue
        m = RE_SINGLE.search(a.get('href', ''))
        if not m:
            continue
        name = next((s.strip() for s in a.find_all(string=True) if s.strip()), '')
        cells = [td.get_text(' ', strip=True) for td in tr.find_all('td')]
        di = next((i for i, c in enumerate(cells) if RE_DDMMYY.fullmatch(c)), -1)
        if not name or di < 0 or di + 2 >= len(cells):
            continue
        d, mo, yy = (int(x) for x in RE_DDMMYY.fullmatch(cells[di]).groups())
        out.append({
            'slug': m.group(1),
            'name': name,
            'date': f'20{yy:02d}-{mo:02d}-{d:02d}',
            'country': cells[di + 1],
            'discipline': cells[di + 2],
            'link': f'https://www.skyrunning.com/single-race/{m.group(1)}/',
        })
    return out


def parse_race_page(page_html):
    """从单场页解析 距离 / 垂直爬升 / 官网域名"""
    txt = html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', '', page_html, flags=re.S)))
    out = {'distance_km': None, 'vertical_m': None, 'official': None}
    m = RE_DIST.search(txt)
    if m:
        out['distance_km'] = float(m.group(1).replace(',', '.').replace(' ', ''))
    m = RE_VERT.search(txt)
    if m:
        out['vertical_m'] = int(m.group(1).replace(',', '').replace('.', '').replace(' ', ''))
    for m in RE_HREF.finditer(page_html):
        host = urlparse(m.group(1)).netloc.lower()
        if host and not any(b in host for b in BLOCK_HOSTS):
            out['official'] = host
            break
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cal_html = fetch(CALENDAR, timeout=25)
    if not cal_html:
        print('[skyrunning] 日历页抓取失败')
        return
    rows = parse_calendar(cal_html)
    print(f'[skyrunning] 日历 {len(rows)} 场')

    races, skipped = [], []
    for r in rows:
        if r['country'].strip().lower() in SKIP_COUNTRY:
            skipped.append(f"{r['name']} ({r['country']})")
            continue
        page = fetch(r['link'], timeout=20)
        info = parse_race_page(page) if page else {}
        distances = []
        if info.get('distance_km'):
            km = math.floor(info['distance_km'] + 0.5)     # 20,5km → 21K（模型只存整数 K）
            item = {'d': f'{km}K'}
            if info.get('vertical_m'):
                item['climb'] = f"{info['vertical_m']}m"
            distances.append(item)
        races.append({
            'source_id': r['slug'],
            'name': f"{r['date'][:4]} {r['name']}",
            'date': r['date'],
            'end_date': None,
            'province': '海外',
            'city': r['country'],
            'distances': distances,
            'tags': ['skyrunning'],
            'link': r['link'],
            'wechat': None,
            'official': info.get('official'),
        })
    if skipped:
        print(f'[skyrunning] 跳过中国境内 {len(skipped)} 场（zuicool 权威）：{skipped}')
    print(f'[skyrunning] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'skyrunning.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'skyrunning',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[skyrunning] 写出: {out_path}')


def _selftest():
    """离线自检：日历表解析 + 单场页解析 + 中国过滤 + 小数距离取整"""
    cal = ('<table><tr><td><img></td><td></td>'
           '<td class="rnk_list_name"><a href="https://www.skyrunning.com/single-race/ibarra-skyrace-2026/">'
           'Ibarra SkyRace&reg;<br><span>Skyrunner&reg; World Series</span></a></td>'
           '<td>28/06/26</td><td>Ecuador</td><td class="isf_uppcase">Sky</td></tr>'
           '<tr class="odd"><td><img></td><td></td>'
           '<td class="rnk_list_name"><a href="https://www.skyrunning.com/single-race/yading-2026/">'
           'Yading SkyRace&reg;<br><span>Skyrunner&reg; World Series</span></a></td>'
           '<td>20/06/26</td><td>China</td><td>Sky</td></tr></table>')
    rows = parse_calendar(cal)
    assert len(rows) == 2, rows
    assert rows[0] == {'slug': 'ibarra-skyrace-2026', 'name': 'Ibarra SkyRace®',
                       'date': '2026-06-28', 'country': 'Ecuador', 'discipline': 'Sky',
                       'link': 'https://www.skyrunning.com/single-race/ibarra-skyrace-2026/'}, rows[0]
    page = ('<span class="elementor-icon-list-text">28/06/2026</span>'
            '<span class="elementor-icon-list-text">Distance: 20,5 km</span>'
            '<span class="elementor-icon-list-text">Vertical climb: 2,100m+</span>'
            '<a href="https://skyraceibarra.com/">site</a>'
            '<a href="https://www.facebook.com/x">fb</a>')
    info = parse_race_page(page)
    assert info == {'distance_km': 20.5, 'vertical_m': 2100, 'official': 'skyraceibarra.com'}, info
    assert math.floor(info['distance_km'] + 0.5) == 21
    print('[skyrunning] selftest OK')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        _selftest()
    else:
        main()
