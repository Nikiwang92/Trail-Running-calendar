# crawlers/saihuitong.py
# 赛会通 saihuitong.com 平台 — 从 backup/赛会通运营方目录.json 100 域名全扫
import sys, json, os, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.parse import parse_cn_date, parse_distance_km
from _lib.province import split_province_city
from _lib.tags import infer_tags

OUT_DIR = ROOT / 'crawl' / 'output'
DIR_JSON_CANDIDATES = [
    ROOT / 'domains.json',
    ROOT / 'crawl' / 'domains_full.json',
    ROOT / '赛会通运营方目录.json',
    ROOT / 'backup' / '赛会通运营方目录.json',
]


def load_domains():
    for p in DIR_JSON_CANDIDATES:
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            out = []
            for k in ('saihui', 'jlb', 'other'):
                for d in data.get(k, []):
                    if d and d != 'www.saihuitong.com':
                        out.append(d)
            # 去重保序
            seen, uniq = set(), []
            for d in out:
                if d not in seen:
                    seen.add(d); uniq.append(d)
            return uniq
    return []


HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148', 'Accept-Language': 'zh-CN,zh;q=0.9'}

# 导航/说明类标题，非赛事，直接丢弃
JUNK_TITLE_KW = ['须知', '规程', '声明', '隐私', '协议', '联系', '关于', '常见问题',
                 '成绩查询', '照片查询', '报名指南', '退费', '保险', '免责', '首页',
                 '个人中心', '登录', '注册', '说明', '公告', '客服']


def is_junk_title(title):
    t = (title or '').strip()
    if len(t) < 4:
        return True
    return any(kw in t for kw in JUNK_TITLE_KW)


def scan_operator(domain, session):
    """扫描单个赛会通运营方，返回其承载的赛事列表"""
    events = []
    for path in ['/m/', '/m/events']:
        try:
            r = session.get(f'https://{domain}{path}', headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            from bs4 import BeautifulSoup
            r.encoding = 'utf-8'
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                txt = a.get_text(strip=True)
                m = re.search(r'/m/text\?mid=(\d+)', href)
                if m and not is_junk_title(txt):
                    events.append({'mid': m.group(1), 'name': txt})
        except Exception:
            continue
    seen, uniq = set(), []
    for e in events:
        if e['mid'] not in seen:
            seen.add(e['mid']); uniq.append(e)
    return uniq


def fetch_text(domain, mid, session):
    """抓规程页 text"""
    try:
        r = session.get(f'https://{domain}/m/text?mid={mid}', headers=HEADERS, timeout=12)
        r.encoding = 'utf-8'
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def parse_text(text, title=''):
    """从规程页 text 提取字段"""
    if not text:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, 'html.parser')
    text_only = soup.get_text(' ', strip=True)
    # 名称
    name = None
    if title:
        t = re.sub(r'【[^】]*】\s*[-—]?\s*', '', title)
        t = re.sub(r'(体育赛事官网|赛事官网|_朗途.*|_赛会通.*)', '', t).strip(' -_')
        name = t or None
    if not name:
        m = re.search(r'(?:赛事名称|比赛名称)[:：\s]+([一-龥A-Za-z0-9·&]{4,40})', text_only)
        if m:
            name = m.group(1).strip()
    # 日期
    date = None
    end_date = None
    m = re.search(r'(?:比赛时间|赛事时间|活动时间|比赛日期)[:：\s]+(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日[^\s。；]{0,15})', text_only)
    if m:
        seg = m.group(1)
        date = parse_cn_date(seg)
        if date:
            end_seg = re.search(r'(?:至|到|—|-|~)\s*(\d{1,2}\s*月\s*\d{1,2}\s*日)', seg)
            if end_seg:
                y = seg[:4]
                ed = parse_cn_date(y + '年' + end_seg.group(1))
                end_date = ed
    if not date:
        # 兜底：找首个 YYYY年MM月DD日
        m2 = re.search(r'(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', text_only)
        if m2:
            date = parse_cn_date(m2.group(1))
    # 距离 / 爬升
    distances = []
    for d in parse_distance_km(text_only):
        distances.append({'d': d})
    # 地点
    city = None
    m = re.search(r'(?:比赛地点|赛事地点|举办地点|地点)[:：\s]+([一-龥省市区县镇村路街道·]{3,30}?)（', text_only)
    if not m:
        m = re.search(r'(?:比赛地点|赛事地点|举办地点|地点)[:：\s]+([一-龥省市区县镇村路街道·]{3,30})', text_only)
    if m:
        city = m.group(1).strip()
    province = ''
    if city:
        province, _ = split_province_city(city)
    # 拒绝：导航标题 / 明显假日期（页脚版权年 2004 等）
    if is_junk_title(name):
        return None
    if not date or int(date[:4]) < 2020:
        return None
    return {
        'name': name,
        'date': date,
        'end_date': end_date,
        'province': province,
        'city': city or '',
        'distances': distances,
        'raw_text': text_only[:500],
    }


def crawl(max_domains=102):
    """扫所有运营方域名"""
    s = get_session()
    domains = load_domains()
    print(f'[saihuitong] 域名总数: {len(domains)}')
    races = []
    seen = set()
    domain_count = 0
    for d in domains[:max_domains]:
        domain_count += 1
        events = scan_operator(d, s)
        if not events:
            continue
        for ev in events:
            key = f"{d}/{ev['mid']}"
            if key in seen:
                continue
            seen.add(key)
            html = fetch_text(d, ev['mid'], s)
            if not html:
                continue
            info = parse_text(html, ev['name'])
            if not info or not info.get('name') or not info.get('date'):
                continue
            races.append({
                'source_id': key,
                'name': info['name'],
                'date': info['date'],
                'end_date': info.get('end_date'),
                'province': info.get('province', ''),
                'city': info.get('city', ''),
                'distances': info.get('distances', []),
                'tags': infer_tags(info['name']),
                'link': f'https://{d}/m/text?mid={ev["mid"]}',
                'wechat': None,
            })
        if domain_count % 10 == 0:
            print(f'  进度: {domain_count}/{len(domains[:max_domains])}, 当前{len(races)}场')
    print(f'[saihuitong] 扫了 {domain_count} 个域名')
    return races


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 全量扫 102 个 saihuitong 运营方域名，约 1 分钟
    races = crawl(max_domains=102)
    print(f'[saihuitong] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'saihuitong.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'saihuitong',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[saihuitong] 写出: {out_path}')


if __name__ == '__main__':
    main()