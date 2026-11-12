# crawlers/zuicool.py
# 最酷 zuicool.com/reg.zuicool.com 越野赛
# 列表页：https://reg.zuicool.com/?race_type_id=10 翻页
# 详情页：https://reg.zuicool.com/{id}
import sys, re, json, os, time, hashlib
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT /'crawlers'))
from _lib.http import fetch, get_session
from _lib.parse import parse_cn_date, parse_distance_km, parse_climb, parse_cutoff_hours
from _lib.province import split_province_city
from _lib.tags import infer_tags, tags_from_page
from _lib.wechat import extract_wechat, is_valid_wechat

BASE = 'https://zuicool.com'
LIST_URL = BASE + '/events?type=trail-run&page={page}'
LIST_URL_WHERE = BASE + '/events?type=trail-run&where={where}&page={page}'
OUT_DIR = ROOT / 'crawl' / 'output'
DATA_FILE = ROOT / '_race_data.js'
STATE_FILE = ROOT / 'crawl' / 'state.json'

# 抓取地区：(where 参数, 地区标签)。'' = 大陆（默认）
REGIONS = [
    ('', None),
    ('hkgmac', '港澳台'),
    ('overseas', '海外'),
]

FULL_REFRESH_DAYS = 15   # 每 N 天做一次全量详情抓取（兜底"详情页独有变化"）
STALE_DAYS = 3           # 开赛后仍继续刷详情 N 天：赛前/赛中的页面还在改（组别、关门）
MIN_YEAR = '2026'        # 抓取 >= 该年份的赛事（含 2027/2028…）
MIN_DATE = MIN_YEAR + '-01-01'
MAX_PAGES = 30

RE_LINK = re.compile(r'href="(https?://(?:www\.)?zuicool\.com/event/(\d+))"[^>]*>([^<]+)<')
RE_DATE_RANGE = re.compile(r'(\d{4}年\d{1,2}月\d{1,2}日)(?:\s*[—\-到至~]+\s*(\d{1,2}月\d{1,2}日))?')
RE_DATE_ISO = re.compile(r'(\d{4}-\d{1,2}-\d{1,2})')
RE_CARD_DATE = re.compile(r'(20\d{2})\.(\d{1,2})\.(\d{1,2})')


def list_page(page, session, where=''):
    """拉一页列表，解析每个赛事卡片，返回
    [{id, url, name, date, city, raw}, ...]
    raw 是卡片的完整文本，用作"变更指纹"（含副标题/报名状态等）。
    """
    url = (LIST_URL_WHERE.format(where=where, page=page) if where
           else LIST_URL.format(page=page))
    html = fetch(url, session=session, timeout=15)
    if not html:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    for body in soup.find_all('div', class_='event-body'):
        a = body.find('a', class_='event-a') or body.find('a', href=re.compile(r'/event/\d+'))
        if not a:
            continue
        href = a.get('href', '')
        idm = re.search(r'/event/(\d+)', href)
        if not idm:
            continue
        rid = idm.group(1)
        name = a.get_text(strip=True)
        if not name or len(name) < 4 or len(name) > 90:
            continue
        date, city = None, ''
        info = body.find('div', class_='info')
        if info:
            itext = info.get_text(' ', strip=True)
            dm = RE_CARD_DATE.search(itext)
            if dm:
                date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
            # "2026.09.11 · 河北 张家口市 ..." → 取 · 之后
            if '·' in itext:
                tail = itext.split('·', 1)[1].strip()
                tail = re.sub(r'报名截止.*$', '', tail).strip()
                city = tail.split('报名')[0].strip()
        raw = body.get_text(' ', strip=True)
        # 报名截止：卡片上就有（"报名截止：02-28 23:59"），无需进详情页
        # 只给到"月-日 时:分"，按赛事日期推断年份（早于赛事的截止一般在去年）
        deadline = None
        dm2 = re.search(r'报名截止[：:]\s*(\d{1,2})-(\d{1,2})\s*(\d{1,2}):(\d{2})', raw)
        if dm2:
            mo, dd, hh, mi = (int(x) for x in dm2.groups())
            if date:
                ry, rmo, rdd = int(date[:4]), int(date[5:7]), int(date[8:10])
                y = ry if (mo, dd) <= (rmo, rdd) else ry - 1
            else:
                y = datetime.now().year
            deadline = f'{y}-{mo:02d}-{dd:02d} {hh:02d}:{mi:02d}'
        items.append({'id': rid, 'url': f'https://zuicool.com/event/{rid}',
                      'name': name, 'date': date, 'city': city, 'raw': raw,
                      'reg_deadline': deadline})
    seen, uniq = set(), []
    for it in items:
        if it['id'] not in seen:
            seen.add(it['id']); uniq.append(it)
    return uniq


def _fingerprint(item):
    """列表卡片的变更指纹（名称/日期/地点/副标题/报名状态任一变化都会变）。"""
    return hashlib.md5((item.get('raw') or '').encode('utf-8')).hexdigest()[:16]


def _list_all(session, where, max_pages=MAX_PAGES, min_date=MIN_DATE):
    """翻页收敛：连续 2 页无 >= min_date 的赛事即停。返回该地区的所有卡片。"""
    out, miss = [], 0
    label = where or '大陆'
    for p in range(1, max_pages + 1):
        items = list_page(p, session, where=where)
        if not items:
            miss += 1
            if miss >= 3:
                break
            continue
        matched = [it for it in items if (it.get('date') or '') >= min_date]
        print(f'[zuicool][{label}] 第{p}页: {len(items)} 条, 其中 >= {min_date[:4]} 年 {len(matched)} 条')
        if not matched:
            miss += 1
            if miss >= 2:
                print(f'[zuicool][{label}] 连续 {miss} 页无 >= {min_date[:4]} 年赛事，停止翻页')
                break
            continue
        miss = 0
        out += matched
    return out


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'last_full': None, 'races': {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def _load_prev_output():
    """读上一次的 zuicool.json（增量跳过时沿用其详情字段，保证快照完整）。"""
    p = OUT_DIR / 'zuicool.json'
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8')).get('races', [])
    except Exception:
        return []


def _existing_zuicool_ids():
    """从 _race_data.js 抽已入库的 zuicool event id（用于判断"新赛事"）。"""
    ids = set()
    if not DATA_FILE.exists():
        return ids
    src = DATA_FILE.read_text(encoding='utf-8')
    for m in re.finditer(r'zuicool\.com/(?:event/)?(\d+)', src):
        ids.add(m.group(1))
    return ids


def _full_reason(state, today, forced=False):
    """返回触发全量的理由字符串；空串表示走增量。"""
    if forced:
        return '手动 --full'
    last = state.get('last_full')
    if not last:
        return '首次运行（无历史全量记录）'
    try:
        days = (date.fromisoformat(today) - date.fromisoformat(last)).days
        if days >= FULL_REFRESH_DAYS:
            return f'距上次全量 {days} 天（阈值 {FULL_REFRESH_DAYS}）'
    except Exception:
        return '上次全量日期异常'
    return ''



RE_LEAD_RANGE = re.compile(
    r'定于\s*(?:(\d{4})\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    r'(?:\s*[-—~～到至]+\s*(?:(\d{1,2})\s*月)?\s*(\d{1,2})\s*日?)?'
)
RE_LEAD_LOC = re.compile(r'(?:在\s*)+([一-龥]{2,12}(?:省|自治区)?[一-龥A-Za-z0-9·]{0,20}(?:市|州|盟|区)?[一-龥0-9A-Za-z·号]{0,24}?)\s*(?:开赛|开跑|举办|举行|启动|拉开|正式)')
RE_LABEL_DIST = re.compile(r'(\d{1,3})\s*(?:KM|公里|K)', re.IGNORECASE)
RE_LABEL_TAIL = re.compile(r'(\d{1,3})\s*K?\s*$')
RE_DEC = re.compile(r'(\d{1,3}(?:\.\d+)?)\s*(?:KM|公里|K|km)', re.I)
# 正文距离：'实际距离34公里'、'徒步距离17KM'，或行首无标签的 '26公里'
RE_BODY_DIST = re.compile(
    r'(?:实际距离|赛道(?:总)?长|赛程|活动距离|徒步距离|比赛距离|赛事距离|路线距离|里程|距离)'
    r'\s*(?:约)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:km|KM|Km|公里)'
    r'|^\s*(\d{1,3}(?:\.\d+)?)\s*(?:km|KM|Km|公里)', re.I)
RE_GROUP_CLIMB = re.compile(r'(?:累计爬升|累计上升|爬升|上升)\s*[:：]?\s*(?:约)?\s*(\d+(?:[,，]\d{3})*)\s*(?:米|m|M)')
# 时刻：小时/分钟都要合法，且两侧不能再接数字（否则 'UTNH-100：11月' 里的 '00：11' 会被当时刻）
# 秒也要一起吃掉：'23:59:59' 只遮前两段会漏下 ':59' 被当成 59K 组别（踩过：香港跨年越野赛）
RE_CLOCK = re.compile(r'(?<!\d)((?:[01]?\d|2[0-3]))\s*[:：]\s*([0-5]\d)(?:\s*[:：]\s*[0-5]\d)?(?!\d)')
_HOUR = r'(?:小时|h|H|个小时)'
RE_CUT_HMIN = re.compile(r'(\d+)\s*' + _HOUR + r'\s*(\d+)\s*(?:分钟|min)', re.I)
RE_CUT_DUR = re.compile(r'(?:总)?关门(?:时长|时限|时间)?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*' + _HOUR
                        + r'\s*(?:(\d+)\s*(?:min|分钟))?', re.I)
RE_CUT_AFTER = re.compile(r'(\d+(?:\.\d+)?)\s*' + _HOUR + r'\s*关门')
RE_CUT_PAREN = re.compile(r'[（(]\s*(\d+(?:\.\d+)?)\s*(?:个)?小时\s*[)）]')
RE_CUT_XIAN = re.compile(r'限\s*(?:时\s*)?(\d+(?:\.\d+)?)\s*' + _HOUR, re.I)
RE_CUT_DT = re.compile(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*(?:上午|下午|晚上|凌晨)?\s*(\d{1,2})\s*[:：]\s*(\d{2})')
RE_CUT_START = re.compile(r'出发时间')
RE_CUT_CLOSE = re.compile(r'关门时间\s*(?!\d+(?:\.\d+)?\s*' + _HOUR + r')')
# 官方站点：优先"官网：xxx"；裸域名仅接受已知赛事平台
RE_OFFICIAL = re.compile(r'(?:官方网站?|赛事官网|官网|网站)\s*[:：]?\s*(?:https?://)?([a-z0-9][a-z0-9.\-]+\.[a-z]{2,})', re.IGNORECASE)
RE_OFFICIAL_BARE = re.compile(r'\b([a-z0-9][a-z0-9\-]+\.(?:utmb\.world|saihuitong\.com|ihuipao\.com|xempower\.cn))\b', re.IGNORECASE)


def extract_official(text):
    """提取赛事官网域名（用于跨平台去重键）。返回小写 hostname 或 None。
    排除 zuicool 自身（页脚常出现"最酷官网zuicool.com"）。"""
    for m in RE_OFFICIAL.finditer(text):
        host = m.group(1).lower()
        if 'zuicool.com' in host:
            continue
        return host
    m2 = RE_OFFICIAL_BARE.search(text)
    if m2 and 'zuicool.com' not in m2.group(1).lower():
        return m2.group(1).lower()
    return None


MIN_KM, MAX_KM = 2, 200


def _round_km(x):
    """小数距离四舍五入（半向上）。不能用 round()：Python 是银行家舍入，
    4.5 会被舍成 4、30.5 舍成 30，与"官方整数 K"的直觉相反。"""
    return int(float(x) + 0.5)


def _dist_from_label(label):
    """从组别标签提取官方距离（数字）。'DGW100'→100，'八荒六合168K'→168，'100公里组'→100，'3K禅村拾趣'→3。
    小数优先取整（'MSA30.5K'→31，'15.2km'→15），否则 '30.5K' 会被截成 5。
    只接受 2-200 的合理距离（含少儿组短距离）。"""
    m = RE_DEC.search(label)
    if m:
        v = _round_km(m.group(1))
        if MIN_KM <= v <= MAX_KM:
            return v
    vals = [int(m.group(1)) for m in RE_LABEL_DIST.finditer(label) if MIN_KM <= int(m.group(1)) <= MAX_KM]
    if vals:
        return vals[0]
    m2 = RE_LABEL_TAIL.search(label)
    if m2 and MIN_KM <= int(m2.group(1)) <= MAX_KM:
        return int(m2.group(1))
    return None


def _body_dist(detail):
    """标签里没距离时（'揽胜组'、'The Third组'），从该行正文取距离。
    '30公里，累计爬升1860米' / '实际距离34公里' 均可；不合理的不要。"""
    for m in RE_BODY_DIST.finditer(detail):
        v = _round_km(m.group(1) or m.group(2))
        if MIN_KM <= v <= MAX_KM:
            return v
    return None


_RE_LAP_PAREN = re.compile(r'[（(][^）)]*(?:\d+\s*圈|[xX×]\s*\d+)[^）)]*[）)]')
_RE_ENUM_STOP = re.compile(r'(实际距离|累计爬升|累计上升|关门|限时|组别人数|名额|规模)')
_RE_FIRST_DIST_PHRASE = re.compile(
    r'(?:赛道(?:总)?长|赛道距离|实际距离|比赛距离|赛事距离|路线距离|徒步距离|活动距离|赛程|里程|全程|距离)'
    r'\s*(?:约)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:km|KM|Km|公里)', re.I)
_RE_DIST_BEFORE_GROUP = re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:km|KM|Km|公里)\s*[^\d，。；、]{0,8}?组')


def _dist_from_first_line(first):
    """首行兜底：只在"设A组、B组"这类组别枚举里取距离，绝不整行扫描。
    首行常写赛道分段（'共计6.7公里，其中1.5公里…5.2公里'）、实际距离、名额，
    整行扫会把它们当成组别（踩过：6.7/1.5/5.2 变成 7K/5K）。
        '设5公里单人组、…、10公里单人组等组别'            → [10, 5]
        '设长距离组(80公里)、短距离组(40公里)…三个组别'   → [80, 40, 15]
        '设逐光50KM一个项目，实际距离47.2公里'            → [50]（遇"实际距离"即止）
        '比赛线路共计6.7公里，其中1.5公里…'               → []
    """
    line = _RE_LAP_PAREN.sub(' ', first)          # 圈数/倍数说明（'（6K赛道x3圈）'）不是组别
    i = line.find('设')
    if i >= 0 and re.search(r'(组|项目|赛)', line[i:]):
        tail = line[i:]
        m = _RE_ENUM_STOP.search(tail)
        if m:
            tail = tail[:m.start()]
        tail = re.split(r'[。；;]', tail)[0]
        vals = []
        for seg in re.split(r'[、，,/]', tail):
            # 标记（组/项目/赛）常只出现在枚举末尾（'设10KM、18KM两个项目'），
            # 此时枚举内的纯距离段（'10KM'）也是组别 —— 已在"设"锚点内，可放心取距离。
            dm = RE_DEC.search(seg) if (re.search(r'(组|项目|赛)', seg) or re.search(r'(组|项目|赛)', tail)) else None
            if dm:
                v = _round_km(dm.group(1))
                if MIN_KM <= v <= MAX_KM:
                    vals.append(v)
        if vals:
            return vals
    m = _RE_FIRST_DIST_PHRASE.search(line)
    if m:
        v = _round_km(m.group(1))
        if MIN_KM <= v <= MAX_KM:
            return [v]
    m = re.search(r'[一-龥]{0,6}环线\s*(?:约)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:km|KM|Km|公里)', line)
    if m:
        v = _round_km(m.group(1))
        if MIN_KM <= v <= MAX_KM:
            return [v]
    vals = []
    for dm in _RE_DIST_BEFORE_GROUP.finditer(line):
        v = _round_km(dm.group(1))
        if MIN_KM <= v <= MAX_KM:
            vals.append(v)
    return vals


def _plausible(km, h):
    """关门时长合理性闸门：0.4-40 小时，且配速落在 0.15-1.6 h/km。不满足一律丢弃。"""
    if h is None or not (0.4 <= h <= 40):
        return False
    if not km or km <= 0:
        return False
    return 0.15 <= h / km <= 1.6


def _cut_from_detail(detail):
    """从一个组别行正文抽关门时长（小时，float）。认六种写法，缺失返回 None：
        关门时长25小时 / 关门时间6小时 / 7.5小时关门 / 关门时间14:00（7小时）
        限时6小时 / 出发时间10月11日8:00…关门时间10月11日14:30
    """
    m = RE_CUT_HMIN.search(detail)                    # 1小时35分钟
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    m = RE_CUT_DUR.search(detail)                     # 关门时长25小时 / 关门时间6小时
    if m:
        return float(m.group(1)) + (int(m.group(2)) / 60.0 if m.group(2) else 0)
    ms = RE_CUT_AFTER.findall(detail)                 # 7.5小时关门：取最后一个（CP 在前、终点在后）
    if ms:
        return float(ms[-1])
    m = RE_CUT_PAREN.search(detail)                   # 关门时间14:00（7小时）
    if m:
        return float(m.group(1))
    m = RE_CUT_XIAN.search(detail)                    # 限时6小时
    if m:
        return float(m.group(1))
    sm, cm = RE_CUT_START.search(detail), RE_CUT_CLOSE.search(detail)
    if sm and cm and cm.start() > sm.end():
        a = RE_CUT_DT.search(detail[sm.end():cm.start()])
        b = RE_CUT_DT.search(detail[cm.end():])
        if a and b:
            m1 = int(a.group(2)) * 1440 + int(a.group(3)) * 60 + int(a.group(4))
            m2 = int(b.group(2)) * 1440 + int(b.group(3)) * 60 + int(b.group(4))
            d = m2 - m1
            if 0 < d <= 72 * 60:
                return d / 60.0
        ca, cb = RE_CLOCK.search(detail[sm.end():cm.start()]), RE_CLOCK.search(detail[cm.end():])
        if ca and cb:
            d = (int(cb.group(1)) * 60 + int(cb.group(2))) - (int(ca.group(1)) * 60 + int(ca.group(2)))
            if d <= 0:
                d += 24 * 60
            if 0 < d <= 72 * 60:
                return d / 60.0
    return None


_re_split_line = re.compile(r'[：:]')


def _split_label(line):
    """按第一个冒号拆成 标签|正文。先屏蔽时刻里的 ASCII 冒号（'8:00'），
    否则 re.split 会切在时钟上，标签与正文双双错位。"""
    masked = RE_CLOCK.sub(lambda m: m.group(0).replace(':', '\x00').replace('：', '\x00'), line)
    parts = _re_split_line.split(masked, maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[0].replace('\x00', ':'), parts[1].replace('\x00', ':')


def _parse_lead_block(lead_text):
    """解析 event-desc_lead 结构化块（最可靠的来源）
    返回 dict: distances / date / end_date / city。
    组别行形如（格式多样）：
        DGW100：实际距离100km，累计爬升3959米，总关门时长25小时
        天空之镜100KM组（TKZJ100）：...实际距离约102.85KM，累计爬升3775米，限时28小时
        100公里组：...总关门时长30h，实际距离98.68km，累计上升6304m
        3K禅村拾趣（亲子组1大1小）：实际距离3.1KM，累计爬升136m，关门时长2h45min
    """
    out = {'distances': [], 'date': None, 'end_date': None, 'city': None}
    lines = [l.strip() for l in lead_text.split('\n') if l.strip()]
    if not lines:
        return out
    # 首行常是"延期提示/调整提醒"公告，真正的赛事导语在下一行（含"定于…"）
    first = next((l for l in lines if '定于' in l), lines[0])
    # 日期范围
    m = RE_LEAD_RANGE.search(first)
    if m:
        year = m.group(1)
        if not year:
            y2 = re.search(r'(20\d{2})', first)
            year = y2.group(1) if y2 else '2026'
        mo1, d1 = int(m.group(2)), int(m.group(3))
        out['date'] = f'{year}-{mo1:02d}-{d1:02d}'
        if m.group(5):
            mo2 = int(m.group(4)) if m.group(4) else mo1
            d2 = int(m.group(5))
            if (mo1, d1) != (mo2, d2):
                out['end_date'] = f'{year}-{mo2:02d}-{d2:02d}'
    # 地点
    ml = RE_LEAD_LOC.search(first)
    if ml:
        out['city'] = ml.group(1).strip()

    # 组别（逐行）：按第一个冒号拆成 标签|详情
    seen = {}
    for line in lines:
        sp = _split_label(line)
        if not sp:
            continue
        label, detail = sp
        km = _dist_from_label(label)
        # 组别行正文一般写着距离/爬升/关门；但"两日赛/组合组"这类
        # （'卓越组36KM（两日赛）：同时参加…12公里组+…24公里组'）正文只有赛制说明，
        # 距离只写在标签里 —— 标签自身带「组/项目 + 距离」也算组别行，否则整组被丢掉。
        if not re.search(r'(实际距离|累计爬升|累计上升|关门|限时|组别人数)', detail) \
                and not (km is not None and re.search(r'(组|项目)', label)):
            continue
        if km is None:
            km = _body_dist(detail)          # 标签无距离（'揽胜组'）→ 用正文距离
        if km is None:
            continue
        item = {'d': f'{km}K'}
        cm = RE_GROUP_CLIMB.search(detail)
        if cm:
            item['climb'] = cm.group(1).replace(',', '').replace('，', '') + 'm'
        h = _cut_from_detail(detail)
        if _plausible(km, h):
            item['time'] = f'{round(h, 2):g}h'
        # 同距离去重：保留信息更多的
        score = (1 if item.get('climb') else 0) + (1 if item.get('time') else 0)
        prev = seen.get(km)
        if prev is None or score > prev[0]:
            seen[km] = (score, item)
    # 兜底：详情页没有逐行组别时，只从首行的"设A、B、C组"枚举里取，
    # 绝不整行扫 km —— 首行常写赛道分段（'6.7公里，其中1.5公里…5.2公里'）、
    # 实际距离与名额，整行扫会把它们当组别。
    if not seen:
        for v in _dist_from_first_line(first):
            seen.setdefault(v, (0, {'d': f'{v}K'}))
    out['distances'] = [v[1] for _, v in sorted(seen.items(), key=lambda x: -x[0])]
    # 单组别赛事：爬升/关门常直接写在导语首行
    if len(out['distances']) == 1:
        item = out['distances'][0]
        if 'climb' not in item:
            cm = RE_GROUP_CLIMB.search(first)
            if cm:
                item['climb'] = cm.group(1).replace(',', '').replace('，', '') + 'm'
        if 'time' not in item:
            km = int(re.match(r'(\d+)', item['d']).group(1))
            h = _cut_from_detail(first)
            if _plausible(km, h):
                item['time'] = f'{round(h, 2):g}h'
    return out


def _parse_pkg_block(soup):
    """解析 div.event-pkgs 报名包块（详情页 lead 块没写组别时的兜底）。
    每组一个 .pkg2：h4.name = 组别名（常带距离，'男子组（6.7公里）'），
    small.highlight_short = '100公里组：累计爬升5458m，…，关门时长30h，规模200人'。
    返回 (distances, has_block)。**无包块返回 ([], False)** —— 绝不把"缺块"当"空组别"。"""
    box = soup.select_one('div.event-pkgs')
    if not box:
        return [], False
    pkgs = box.select('.pkg2')
    if not pkgs:
        return [], False
    seen = {}
    for p in pkgs:
        h = p.select_one('h4.name')
        label = h.get_text(' ', strip=True) if h else ''
        if not label:
            continue
        detail = ' '.join(sm.get_text(' ', strip=True) for sm in p.select('small.highlight_short'))
        km = _dist_from_label(label)
        if km is None:
            km = _body_dist(detail)
        if km is None:
            continue
        item = {'d': f'{km}K'}
        cm = RE_GROUP_CLIMB.search(detail)
        if cm:
            item['climb'] = cm.group(1).replace(',', '').replace('，', '') + 'm'
        hh = _cut_from_detail(detail)
        if _plausible(km, hh):
            item['time'] = f'{round(hh, 2):g}h'
        # 同距离去重（'100公里组'/'100公里双人同行组'）：保留字段更全的
        score = (1 if item.get('climb') else 0) + (1 if item.get('time') else 0)
        prev = seen.get(km)
        if prev is None or score > prev[0]:
            seen[km] = (score, item)
    if not seen:
        return [], True
    return [v[1] for _, v in sorted(seen.items(), key=lambda x: -x[0])], True


def parse_detail(html):
    """解析详情页 HTML，返回字段 dict"""
    if not html:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    # 侧栏"相关赛事/推荐"是**别的**赛事的内容，整块剔除，否则日期/地点/距离都会被污染
    for el in soup.select('.events-list'):
        el.decompose()
    text = soup.get_text('\n', strip=True)
    # 名称
    name = ''
    h1 = soup.find('h1') or soup.find('h2')
    if h1:
        name = h1.get_text(strip=True)

    # 优先：结构化 event-desc_lead 块
    lead = soup.find('div', class_=re.compile(r'event-desc_lead'))
    lead_out = {'distances': [], 'date': None, 'end_date': None, 'city': None}
    lead_text = ''
    if lead:
        lead_text = lead.get_text('\n', strip=True)
        lead_out = _parse_lead_block(lead_text)

    # 日期
    # —— 日期兜底（仅当 lead 块未给出时）——
    date = lead_out['date']
    end_date = lead_out['end_date']
    if not date:
        # 形如 "比赛时间：2026年11月8日 至 11月10日"
        m = re.search(r'(?:比赛时间|赛事时间|活动时间|活动日期|比赛日期)[:：\s]*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日[^\n]{0,30})', text)
        if m:
            seg = m.group(1)
            date = parse_cn_date(seg)
            if date:
                end_seg = re.search(r'(?:至|到|—|-|~)\s*(\d{1,2}\s*月\s*\d{1,2}\s*日)', seg)
                if end_seg:
                    y = seg[:4]
                    ed = parse_cn_date(y + '年' + end_seg.group(1))
                    end_date = ed
        # 直接抓首个 YYYY年M月D日
        if not date:
            m2 = re.search(r'(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*[-—到至~]?\s*(\d{1,2}\s*月\s*\d{1,2}\s*日)?', text)
            if m2:
                date = parse_cn_date(m2.group(1))
                if m2.group(2):
                    y = m2.group(1)[:4]
                    end_date = parse_cn_date(y + '年' + m2.group(2))
        # YYYY.M.D 格式
        if not date:
            m3 = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})\s*[-—]?\s*(?:至\s*)?(\d{1,2})\.(\d{1,2})?', text)
            if m3:
                y, mo, d = m3.group(1), int(m3.group(2)), int(m3.group(3))
                date = f"{y}-{mo:02d}-{d:02d}"
                if m3.group(4):
                    end_date = f"{y}-{int(m3.group(4)):02d}-{int(m3.group(5)):02d}"
        # 从标题分离年份，抓 M月D日[-M月D日]
        if not date:
            year_m = re.search(r'(20\d{2})', name or text)
            year = year_m.group(1) if year_m else '2026'
            m4 = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[-—到至~]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
            if m4:
                mo1, d1, mo2, d2 = m4.group(1), m4.group(2), m4.group(3), m4.group(4)
                date = f"{year}-{int(mo1):02d}-{int(d1):02d}"
                end_date = f"{year}-{int(mo2):02d}-{int(d2):02d}"
            else:
                m5 = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
                if m5:
                    date = f"{year}-{int(m5.group(1)):02d}-{int(m5.group(2)):02d}"

    # —— 组别：优先 lead 块，其次报名包块，最后正文兜底 ——
    distances = lead_out['distances']
    # 组别是否"权威"（可据此删掉库里页面上没有的旧 key）：解析出了组别，
    # 或页面压根没有"设…组/项目/赛"的枚举（=这赛事不分组，旧值必是脏数据）。
    # 页面有枚举但我们一个都没解析出来 → 判为解析失败，保留旧值，不删。
    lead_has_enum = bool(re.search(r'设[^。；]{0,200}?(组|项目|赛)', lead_text))
    # 兜底 ①：详情页右上角的"报名组别"包块（div.event-pkgs）。lead 块只写了赛道分段
    # 与名额、没写组别时（狼牙山：'比赛线路共计6.7公里，其中1.5公里…'），组别只在这里。
    pkg_dists, has_pkg_block = ([], False)
    if not distances:
        pkg_dists, has_pkg_block = _parse_pkg_block(soup)
    if not distances and pkg_dists:
        distances = pkg_dists
    # 页面有 lead 块却一句组别都没有（包块也没有）、且导语写着"拟定/敬请期待"
    # → 选手册尚未公布，合并层据此清掉库里的旧组别（旧值多来自历史整页扫 km，是脏数据）
    pending_groups = not distances and bool(lead_text) and bool(
        re.search(r'(拟定|敬请期待|即将启动报名|尚未|未定|待定)', lead_text))
    # 包块本身是官方枚举 → 有数据即可作权威；但不能在"lead 写了设…组却解析失败"时
    # 逆转判定，那种情况仍按解析失败处理，保留旧值。
    pkg_auth = has_pkg_block and bool(pkg_dists) and not lead_has_enum
    authoritative = (bool(lead_text) and (bool(distances) or not lead_has_enum)) or pkg_auth
    if not distances and not lead:
        # 兜底：**仅当页面没有结构化 lead 块**（老页面）时才全文扫 km。
        # 有 lead 块却没解析出组别 = 页面确实没写组别（"敬请期待"），此时整页扫会把
        # 赛道分段/名额/侧栏内容当成组别（踩过：狼牙山 6.7/5.2 公里变成 7K/5K）。
        km_positions = []
        for km_m in re.finditer(r'(?<!\.\d)\D(\d{1,3})(?:\s*)(?:km|KM|公里)(?!\d)', text):
            try:
                v = int(km_m.group(1))
                if 5 <= v <= 500:
                    km_positions.append((km_m.start(), v))
            except ValueError:
                pass
        seen_d, dedup_positions = set(), []
        for pos, v in km_positions:
            if v not in seen_d:
                seen_d.add(v)
                dedup_positions.append((pos, v))
        for pos, v in dedup_positions:
            seg_end = min(pos + 400, len(text))
            seg = text[pos:seg_end]
            item = {'d': f'{v}K'}
            cm = re.search(r'累计爬升[:：]?\s*(\d+(?:[,，]\d{3})*)\s*米?', seg)
            if not cm:
                cm = re.search(r'[+＋]\s*(\d+(?:[,，]\d{3})*)\s*[Mm]', seg)
            if cm:
                item['climb'] = cm.group(1) + 'm'
            h = _cut_from_detail(seg)
            if _plausible(v, h):
                item['time'] = f'{round(h, 2):g}h'
            distances.append(item)

    # —— 地点：优先 lead 块 ——
    city = lead_out['city']
    if not city:
        m = re.search(r'(?:赛事地点|比赛地点|举办地点|地点)[:：\s]*([一-龥省市区县镇村路街道·]{3,30}?)[\s，。,.]', text)
        if not m:
            m = re.search(r'(?:^|\n)\s*([一-龥]{2,3})\s+([一-龥]{2,5}市|[一-龥]{2,3}州|[一-龥]{2,4}区)\s+(?:[一-龥]{2,4}\s+)?([一-龥]{2,8})', text)
        if m:
            city = m.group(0).strip()
    province = split_province_city(city)[0] if city else ''

    wechat = extract_wechat(text)
    if wechat and not is_valid_wechat(wechat):
        wechat = None
    official = extract_official(text)
    return {
        'name': name or None,
        'date': date,
        'end_date': end_date,
        'province': province,
        'city': city or '',
        'distances': distances,
        # lead 块 = 官方组别枚举，页面上没有的旧 key 即为脏数据 → 合并层可删
        'dists_authoritative': authoritative,
        'dists_pending': pending_groups,
        'tags': tags_from_page(html, name),
        'wechat': wechat,
        'official': official,
        'page_title': _page_title(html),
        'raw_text': text[:500],
    }


def _page_title(html):
    """详情页标题（用于校验 link 是否指向了别的赛事）。最酷的标题就是赛事名，
    偶尔带 " - 最酷" 之类后缀，统一截掉。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    t = ''
    for attrs in ({'property': 'og:title'}, {'name': 'og:title'}):
        meta = soup.find('meta', attrs=attrs)
        if meta and meta.get('content'):
            t = meta['content']
            break
    if not t and soup.title and soup.title.string:
        t = soup.title.string
    t = re.sub(r'\s+', ' ', (t or '')).strip()
    for sep in (' - ', ' | ', ' – ', '_'):
        if sep in t:
            t = t.split(sep)[0].strip()
    return t


def _title_matches(page_title, race_name):
    """页面标题与赛事名是否指同一场（防 link 串库：35355 的页面标题其实是另一个赛事）。
    规范化后互相包含或相似度 >=0.7 才算通过；页面没标题时放行（不误伤）。"""
    if not page_title:
        return True
    from difflib import SequenceMatcher
    a, b = _hardnorm(page_title), _hardnorm(race_name)
    if not a or not b:
        return True
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.7


def _hardnorm(s):
    """只留中英文数字，去掉标点/空格，用于标题比对。"""
    return re.sub(r'[^0-9a-zA-Z一-鿿]', '', s or '').lower()


def _pick_city(cached, card):
    """未抓详情的条目该用哪个地点：列表卡片是"当天在售"的权威地点，详情页缓存可能早已
    失效（改址 / event id 复用 / 正则截断，曾出现「延边100」缓存成长春伊通河）。
    卡片本身写成「主会场…，分会场…」这类长句时不适合当 city，退回缓存。"""
    card = (card or '').strip()
    if not card or len(card) > 40 or '，' in card:
        return cached or card
    return card


def crawl(full=False, today=None, max_pages=MAX_PAGES, min_date=MIN_DATE):
    """增量抓取：
      1) 抓全部地区的列表页（~0.4MB，很便宜）
      2) 决定哪些需要抓详情：
         新赛事 / 列表指纹变化 / 到全量周期且尚未开赛
      3) 抓详情 + 更新 state.json
    输出的 races 覆盖"列表里见到的全部赛事"——未抓详情的用列表卡片的最低信息占位，
    这样合并层的 detect_missing / detect_new 语义不变（不会把跳过误判为 missing）。
    """
    session = get_session()
    today = today or date.today().isoformat()
    state = load_state()
    full_reason = _full_reason(state, today, forced=full)
    full_due = bool(full_reason)
    existing_ids = _existing_zuicool_ids()
    if full_due:
        print('=' * 60)
        print(f'[zuicool] ★★★ 全量模式 『{full_reason}』')
        print('[zuicool]   将对所有【未开赛】赛事重抓详情（已办完的仍跳过）')
        print('=' * 60)
    else:
        print('-' * 60)
        print(f'[zuicool] 增量模式  上次全量={state.get("last_full")}  今日={today}  已入库id={len(existing_ids)}')
        print('-' * 60)

    # 1) 收集所有地区的列表卡片（同一赛事可能同时出现在大陆/港澳台/海外列表）
    all_items = {}
    region_of = {}
    for where, label in REGIONS:
        for it in _list_all(session, where, max_pages, min_date):
            all_items.setdefault(it['id'], it)
            if label:
                region_of[it['id']] = label   # 港澳台/海外优先于大陆
    for rid, label in region_of.items():
        if rid in all_items:
            all_items[rid]['_region'] = label
    print(f'[zuicool] 列表共 {len(all_items)} 场')

    # 2) 决定抓哪些详情（"是否见过"以 state 为准，见过的就不重复抓）
    need = []
    for rid, it in all_items.items():
        fp = _fingerprint(it)
        it['_fp'] = fp
        prev = state['races'].get(rid)
        # 开赛后头 3 天仍继续刷新：赛事页在赛前/赛中还会改（组别、关门时间），
        # 一开赛就停抓会导致库里停在旧值（历史"组别/爬升不对"多由此而来）
        _d = it.get('date') or ''
        too_old = bool(_d) and _d < (date.fromisoformat(today) - timedelta(days=STALE_DAYS)).isoformat()
        if prev is None:
            if not too_old:
                need.append((rid, it, 'new'))      # 从没见过的新赛事
        elif prev.get('fp') != fp:
            need.append((rid, it, 'changed'))      # 列表有变化
        elif full_due and not too_old:
            need.append((rid, it, 'full'))         # 全量兜底（跳过已开赛）
    from collections import Counter
    reasons = Counter(x[2] for x in need)
    label = {'new': '新增', 'init': '首次建指纹', 'changed': '列表变动', 'full': '全量兜底'}
    detail = '  '.join(f'{label.get(k, k)}={v}' for k, v in reasons.items()) or '无'
    print(f'[zuicool] 本次需抓详情 {len(need)} / 共 {len(all_items)} 场   （{detail}）')

    # 3) 抓详情 + 组装输出（覆盖全部列表项）
    fetched = {}
    for rid, it, reason in need:
        html = fetch(it['url'], session=session, timeout=15)
        if not html:
            continue
        fetched[rid] = parse_detail(html) or {}

    # 跳过未抓详情的条目：沿用上一次输出里的详情字段，保证 zuicool.json 是完整快照
    # （否则 official/wechat/distances 会丢，导致合并层去重与 missing 判定失效）
    prev_map = {r.get('source_id'): r for r in _load_prev_output()}

    races = []
    for rid, it in all_items.items():
        info = fetched.get(rid)
        if info is None:
            info = prev_map.get(rid) or {}
        name = it['name'] or info.get('name')
        date_ = it['date'] or info.get('date')
        if not name or not date_:
            continue
        card_city = it.get('city') or ''
        if rid in fetched:
            city = info.get('city') or card_city
        else:
            # 未抓详情：缓存可能已失效，卡片是当天在售状态的权威地点
            city = _pick_city(info.get('city'), card_city)
        # 列表卡片是"当前在售状态"的权威来源：卡片省份与详情/缓存冲突时以卡片为准
        # （详情页地点常写成报名点/相关赛事；增量跳过的条目还会沿用旧缓存，历史上造成过省份错配）
        card_core = card_city[2:] if card_city.startswith('中国') else card_city
        card_prov = split_province_city(card_city)[0] if card_city else ''
        city_prov = split_province_city(city)[0] if city else ''
        if any(card_core.startswith(k) for k in ('香港', '澳门', '台湾')):
            city, city_prov = card_city, card_prov
        elif card_prov and city_prov and card_prov != city_prov:
            city, city_prov = card_city, card_prov
        province = card_prov or city_prov
        # 海外赛事统一归为"海外"（个别城市名可能误命中，但整体更清晰）
        if it.get('_region') == '海外' and province not in ('香港', '澳门', '台湾'):
            province = '海外'
        races.append({
            'source_id': rid,
            'name': name,
            'date': date_,
            'end_date': info.get('end_date'),
            'province': province,
            'city': city,
            'distances': info.get('distances', []),
            # lead 块 = 官方组别枚举 → 合并层可删掉库里页面上没有的旧组别（脏 key）
            'dists_authoritative': bool(info.get('dists_authoritative')),
            # 详情页明确写着"拟定/敬请期待"且无组别 → 合并层可清掉库里的旧组别
            'dists_pending': bool(info.get('dists_pending')),
            'tags': info.get('tags') or (infer_tags(name) if rid in fetched else []),
            'link': it['url'],
            'wechat': info.get('wechat'),
            'official': info.get('official'),
            'reg_deadline': it.get('reg_deadline'),
            'title_ok': _title_matches(info.get('page_title'), name),
            'raw': {'fetched': rid in fetched},
        })

    # 4) 更新 state
    for rid, it in all_items.items():
        prev = state['races'].get(rid, {})
        state['races'][rid] = {
            'fp': it['_fp'],
            'fetched': today if rid in fetched else prev.get('fetched'),
        }
    if full_due:
        state['last_full'] = today
    save_state(state)
    print(f'[zuicool] 实抓详情 {len(fetched)} 场, 输出 {len(races)} 场')
    return races


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', action='store_true', help='强制全量详情抓取')
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = crawl(full=args.full, max_pages=MAX_PAGES)
    print(f'[zuicool] 总计 {len(races)} 场')
    out_path = OUT_DIR / 'zuicool.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'platform': 'zuicool',
            'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'count': len(races),
            'races': races,
        }, f, ensure_ascii=False, indent=2)
    print(f'[zuicool] 写出: {out_path}')


if __name__ == '__main__':
    main()