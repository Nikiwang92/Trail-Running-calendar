#!/usr/bin/env python3
# scripts/merge_all.py
# 自动合并爬虫输出到 _race_data.js：
#   1. 重算 status (past/upcoming/cancelled)
#   2. 加入新赛事（直接 append 到 _race_data.js）
#   3. 连续 14 天未抓到 → status="cancelled"
import sys, json, re, os, shutil, subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.parse import normalize_name

OUT_DIR = ROOT / 'crawl' / 'output'
DATA_FILE = ROOT / '_race_data.js'
MISSING_LOG = ROOT / 'crawl' / 'MISSING_LOG.json'
REPORT_FILE = ROOT / 'crawl' / f'REPORT_{datetime.now().strftime("%Y%m%d")}.md'
LOCAL_BACKUP_DIR = ROOT / 'backup' / 'race_data'   # 本地滚动备份（.gitignore 忽略）
REPO_BACKUP_DIR = ROOT / 'data_backup'             # 入库滚动备份（会提交）
LOCAL_BACKUP_KEEP = 7
REPO_BACKUP_KEEP = 3
CANCEL_THRESHOLD_DAYS = 14
# 仅合并这些平台的爬虫输出（与 crawlers/run_all.py 的 CRAWLERS 一致）
# 已停用：saihuitong（扫 102 域名产 0 场）、runninginchina（与 zuicool 重复）、
#         ahotu（Cloudflare 拦截）、ihuipao（JS 渲染）
ENABLED_PLATFORMS = {'zuicool', 'utmb'}
PLATFORM_PRIORITY = ['zuicool', 'utmb']


def parse_races_text(src):
    """把 _race_data.js 源文本解析为赛事列表（每行 = 1 条），_raw 保留原行用于精确 replace"""
    import re as _re
    races = []
    for line in src.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('{ name:') and not stripped.startswith('{name:'):
            continue
        r = {'_raw': line, '_stripped': stripped, 'name': '', 'date': '', 'status': 'upcoming'}
        # 字符串字段：正确处理转义引号（名称可能含 "，序列化为 \"）
        def _str_field(key):
            m = _re.search(rf'{key}:\s*"((?:[^"\\]|\\.)*)"', stripped)
            if not m:
                return None
            try:
                return json.loads('"' + m.group(1) + '"')
            except Exception:
                return m.group(1)
        nm = _str_field('name')
        if nm:
            r['name'] = nm
        for key in ('date', 'endDate', 'province', 'city', 'status', 'link', 'wechat', 'official', 'regDeadline'):
            v = _str_field(key)
            if v is not None:
                r[key] = v
        # 解析 distances 数组（嵌套 {}，按 {d:"..."} 匹配每组）
        dm = _re.search(r'distances:\[([^\]]*)\]', stripped)
        if dm:
            dists = []
            for gm in _re.finditer(r'\{d:"([^"]+)"(?:,climb:"([^"]*)")?(?:,time:"([^"]*)")?\}', dm.group(1)):
                item = {'d': gm.group(1)}
                if gm.group(2):
                    item['climb'] = gm.group(2)
                if gm.group(3):
                    item['time'] = gm.group(3)
                dists.append(item)
            r['distances'] = dists
        races.append(r)
    return races


def load_existing_races():
    """从 _race_data.js 读所有赛事，返回 (races, src)"""
    src = DATA_FILE.read_text(encoding='utf-8')
    return parse_races_text(src), src


def link_key(url):
    """归一化 link 用于去重：zuicool 域名统一取 event id，其余取完整 URL。"""
    if not url:
        return ''
    m = re.match(r'https?://(?:reg\.)?zuicool\.com/(?:event/)?(\d+)', url)
    if m:
        return 'zuicool:' + m.group(1)
    return url.rstrip('/').lower()


def dist_str(dists):
    """把 distances 列表序列化为 JS 字面量（d/climb/time）。"""
    out = []
    for d in dists:
        o = f'd:"{d.get("d", "")}"'
        if d.get('climb'):
            o += f',climb:"{d["climb"]}"'
        if d.get('time'):
            o += f',time:"{d["time"]}"'
        out.append('{' + o + '}')
    return '[' + ','.join(out) + ']'


def sort_all_distances(src):
    """将所有赛事的组别按距离降序排列（页面展示统一从多到少）。"""
    entries = parse_races_text(src)
    new_src = src
    changed = 0
    for e in entries:
        dists = e.get('distances')
        if not dists or len(dists) < 2:
            continue
        nums = []
        for d in dists:
            m = re.match(r'\d+', str(d.get('d', '')))
            nums.append(int(m.group(0)) if m else 0)
        if nums == sorted(nums, reverse=True):
            continue
        ordered = [d for _, d in sorted(zip(nums, dists), key=lambda x: -x[0])]
        dm = re.search(r'distances:\[([^\]]*)\]', e['_raw'])
        if not dm:
            continue
        old = dm.group(0)
        new = 'distances:' + dist_str(ordered)
        if old in e['_raw']:
            new_src = new_src.replace(e['_raw'], e['_raw'].replace(old, new, 1), 1)
            changed += 1
    return new_src, changed


def _richness(e):
    """信息量排序键（越大越全，用于去重时保留）。"""
    return (len(e.get('distances', [])) * 10
            + (2 if e.get('city') else 0)
            + (1 if e.get('wechat') else 0)
            + (1 if e.get('endDate') else 0)
            + (1 if e.get('link') else 0))


def _names_similar(a, b):
    """同一赛事的不同写法（去重）：标点/前缀差异。谨慎——需同日 + 同省。"""
    if a.get('date') != b.get('date') or not a.get('date'):
        return False
    pa, pb = a.get('province'), b.get('province')
    if pa and pb and pa != pb:
        return False
    na, nb = normalize_name(a.get('name', '')), normalize_name(b.get('name', ''))
    if not na or not nb or na == nb:
        return False
    if (na in nb or nb in na) and min(len(na), len(nb)) >= 6:
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, na, nb).ratio() >= 0.85


def dedupe_final(src):
    """最终去重：同 link_key / 同 (name_norm,date) / 同日近似名 只保留信息最全的一条。"""
    entries = parse_races_text(src)
    from collections import defaultdict
    groups = defaultdict(list)
    for e in entries:
        k = link_key(e.get('link', '')) or ('nd:' + normalize_name(e['name']) + '|' + e.get('date', ''))
        groups[k].append(e)
    drop = []
    for k, es in groups.items():
        if len(es) < 2:
            continue
        es.sort(key=_richness, reverse=True)
        drop += es[1:]
    # 模糊去重：同一天、名称高度相似（或一方包含另一方）→ 视为重复
    drop_ids = {id(x) for x in drop}
    kept = [e for e in entries if id(e) not in drop_ids]
    by_date = defaultdict(list)
    for e in kept:
        by_date[e.get('date', '')].append(e)
    for dt, es in by_date.items():
        if not dt or len(es) < 2:
            continue
        es.sort(key=_richness, reverse=True)
        chosen = []
        for e in es:
            if any(_names_similar(e, k) for k in chosen):
                drop.append(e)
            else:
                chosen.append(e)
    new_src = src
    dropped = []
    for e in drop:
        raw = e['_raw']
        if (raw + '\n') in new_src:
            new_src = new_src.replace(raw + '\n', '', 1)
        elif raw in new_src:
            new_src = new_src.replace(raw, '', 1)
        else:
            continue
        dropped.append(e['name'])
    return new_src, dropped


JUNK_NAMES = {
    '领物须知', '竞赛规程', '常见问题', '报名须知', '赛事规程', '参赛须知',
    '免责声明', '联系我们', '关于我们', '隐私政策', '用户协议', '赛事信息',
    '比赛规程', '活动规程', '报名信息', '成绩查询', '照片查询',
}


def is_junk_race(r):
    """过滤爬虫误抓的导航/说明页（非赛事）。"""
    name = (r.get('name') or '').strip()
    if len(name) < 6 or name in JUNK_NAMES:
        return True
    date = r.get('date') or ''
    m = re.match(r'(\d{4})', date)
    if m and int(m.group(1)) < 2020:
        return True
    return False


def load_crawled():
    crawled = {}
    for f in OUT_DIR.glob('*.json'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            plat = data.get('platform', f.stem)
            if plat not in ENABLED_PLATFORMS:
                continue
            races = [r for r in data.get('races', []) if not is_junk_race(r)]
            crawled[plat] = races
        except Exception:
            pass
    return crawled


def host_of(url):
    """从 URL 取 hostname（小写），失败返回 ''。"""
    m = re.match(r'https?://([^/]+)', url or '')
    return m.group(1).lower() if m else ''


def claimed_official_hosts(crawled):
    """爬虫数据里声明的官方站点域名集合。
    例如 zuicool 抓到京东大境门，其 official=dajingmen.utmb.world，
    则 dajingmen.utmb.world 被"认领"，独立的 utmb 条目应合并进来而非重复。"""
    hosts = set()
    for plat, races in crawled.items():
        for r in races:
            o = r.get('official')
            if o:
                hosts.add(o.lower())
    return hosts


def load_missing_log():
    if MISSING_LOG.exists():
        return json.loads(MISSING_LOG.read_text(encoding='utf-8'))
    return {}


def save_missing_log(log):
    MISSING_LOG.parent.mkdir(parents=True, exist_ok=True)
    MISSING_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')


def normalize_race(r):
    """规范化一条赛事：丢弃带小数的距离（实际距离），只保留整数 K 官方组别"""
    import re as _re
    distances = r.get('distances') or []
    if not distances:
        return r
    from collections import OrderedDict
    seen = OrderedDict()
    for d in distances:
        d_str = d.get('d', '')
        climb = d.get('climb', '')
        time_v = d.get('time', '')
        km_m = _re.match(r'^(\d+(?:\.\d+)?)(K?)(.*)$', d_str)
        if not km_m or '.' in km_m.group(1):
            # 实际距离（小数 K）或非数字距离 → 直接丢弃
            continue
        km_int = int(km_m.group(1))
        suffix = km_m.group(2) or 'K'
        extra = km_m.group(3)
        key = (km_int, suffix, extra if extra else '')
        existing = seen.get(key)
        score_now = (1 if climb else 0) + (1 if time_v else 0)
        if existing is None or score_now > existing['_score']:
            seen[key] = {'d': d_str, 'climb': climb, 'time': time_v, '_score': score_now}
    sorted_keys = sorted(seen.keys(), key=lambda k: -k[0])
    new_distances = []
    for key in sorted_keys:
        v = seen[key]
        item = {'d': v['d']}
        if v['climb']:
            item['climb'] = v['climb']
        if v['time']:
            item['time'] = v['time']
        new_distances.append(item)
    r['distances'] = new_distances
    return r


def clean_city(city):
    """清洗地点串：去掉换行、"关注"按钮文字、误带的"地点/改至"前缀与尾部标点。"""
    if not city:
        return ''
    s = str(city).replace('\n', ' ').replace('\r', ' ')
    s = s.replace('关注', '')
    s = re.sub(r'^地点[:：]?\s*', '', s)
    s = re.sub(r'^(改至|迁至)\s*', '', s)
    s = s.strip(' ,，。·、;；')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def sanitize_cities(src):
    """把 _race_data.js 里已有的脏 city（含换行/"关注"/"地点"前缀）清洗干净。"""
    entries = parse_races_text(src)
    new_src = src
    changed = 0
    for e in entries:
        old = e.get('city', '')
        new = clean_city(old)
        if new == old:
            continue
        m = re.search(r'city:"((?:[^"\\]|\\.)*)"', e['_raw'])
        if not m:
            continue
        new_raw = e['_raw'][:m.start()] + 'city:' + json.dumps(new, ensure_ascii=False) + e['_raw'][m.end():]
        new_src = new_src.replace(e['_raw'], new_raw, 1)
        changed += 1
    return new_src, changed


def prune_missing_log(existing, log):
    """丢弃 MISSING_LOG 里已不存在的赛事 / 垃圾 key（如 '\\'、空名）。"""
    valid = {normalize_name(e['name']) for e in existing}
    dropped = [k for k in list(log.keys()) if k not in valid]
    for k in dropped:
        del log[k]
    return dropped


def serialize_new(r):
    """生成新赛事的 JS 字面量（带 2 空格缩进，匹配 src 标准格式）"""
    r = normalize_race(r)
    parts = [f"name:{json.dumps(r.get('name') or '', ensure_ascii=False)}",
             f"date:{json.dumps(r.get('date') or '', ensure_ascii=False)}"]
    if r.get('end_date'):
        parts.append(f"endDate:{json.dumps(r['end_date'], ensure_ascii=False)}")
    parts.append(f"province:{json.dumps(r.get('province') or '', ensure_ascii=False)}")
    parts.append(f"city:{json.dumps(clean_city(r.get('city')) or '', ensure_ascii=False)}")
    dist_arr = []
    for d in r.get('distances', []):
        o = [f"d:{json.dumps(d['d'], ensure_ascii=False)}"]
        if d.get('climb'):
            o.append(f"climb:{json.dumps(d['climb'], ensure_ascii=False)}")
        if d.get('time'):
            o.append(f"time:{json.dumps(d['time'], ensure_ascii=False)}")
        dist_arr.append('{' + ','.join(o) + '}')
    parts.append(f"distances:[{','.join(dist_arr)}]")
    tags = r.get('tags', [])
    parts.append(f"tags:[{','.join(json.dumps(t, ensure_ascii=False) for t in tags)}]")
    parts.append(f'status:"upcoming"')
    if r.get('link'):
        parts.append(f"link:{json.dumps(r['link'], ensure_ascii=False)}")
    if r.get('wechat'):
        parts.append(f"wechat:{json.dumps(r['wechat'], ensure_ascii=False)}")
    if r.get('official'):
        parts.append(f"official:{json.dumps(r['official'], ensure_ascii=False)}")
    if r.get('reg_deadline'):
        parts.append(f"regDeadline:{json.dumps(r['reg_deadline'], ensure_ascii=False)}")
    return '  { ' + ', '.join(parts) + ' }'


def find_insert_pos(s):
    """找到 module.exports = [ 之后的位置（用于在数组里插入新项）"""
    m = re.search(r'module\.exports\s*=\s*\[', s)
    if not m:
        return -1
    return m.end()


def auto_recalc_status(existing, src):
    today = datetime.now().strftime('%Y-%m-%d')
    new_src = src
    changed = 0
    for e in existing:
        if not e.get('date') or e.get('status') == 'cancelled':
            continue
        end_date = e.get('endDate') or e['date']
        try:
            d = datetime.strptime(end_date, '%Y-%m-%d')
            new_status = 'past' if d < datetime.now() else 'upcoming'
        except Exception:
            continue
        if e.get('status') != new_status:
            stripped = e['_stripped']
            new_stripped = re.sub(r'status:"[^"]*"', f'status:"{new_status}"', stripped)
            if new_stripped != stripped:
                new_src = new_src.replace(e['_raw'], e['_raw'].replace(stripped, new_stripped), 1)
                changed += 1
    return new_src, changed


def detect_missing(existing, crawled):
    today_str = datetime.now().strftime('%Y-%m-%d')
    found = set()
    for plat, races in crawled.items():
        for r in races:
            found.add(normalize_name(r.get('name', '')))
    missing_log = load_missing_log()
    for e in existing:
        if e.get('status') == 'cancelled':
            continue
        # 已过去的赛事不必再"被抓到"（列表会自然下架）→ 不参与 missing 统计
        if (e.get('endDate') or e.get('date') or '') < today_str:
            missing_log.pop(normalize_name(e['name']), None)
            continue
        # 只对 zuicool 来源的赛事做 missing 统计：其它来源（官网/tsaigu 等）
        # 永远不会出现在 zuicool 列表里，否则会被永久误判为 missing
        if 'zuicool.com' not in (e.get('link') or ''):
            missing_log.pop(normalize_name(e['name']), None)
            continue
        n = normalize_name(e['name'])
        if n in found:
            missing_log.pop(n, None)
            continue
        if n not in missing_log:
            missing_log[n] = {'name': e['name'], 'first_missing': today_str, 'last_missing': today_str, 'days': 1}
        elif missing_log[n].get('last_missing') != today_str:
            # 按"天"累加：同一天多次运行只算 1 天（否则一天内跑 N 次会被误判为 N 天）
            missing_log[n]['days'] = missing_log[n].get('days', 1) + 1
            missing_log[n]['last_missing'] = today_str
    return missing_log


def mark_cancelled(existing, missing_log, src):
    cancelled = []
    new_src = src
    for e in existing:
        if e.get('status') == 'cancelled':
            continue
        n = normalize_name(e['name'])
        log = missing_log.get(n, {})
        if log.get('days', 0) >= CANCEL_THRESHOLD_DAYS:
            stripped = e['_stripped']
            new_stripped = re.sub(r'status:"[^"]*"', 'status:"cancelled"', stripped)
            if new_stripped != stripped:
                new_src = new_src.replace(e['_raw'], e['_raw'].replace(stripped, new_stripped), 1)
                cancelled.append(e['name'])
                log['cancelled'] = True
    return new_src, cancelled


def detect_new(existing, crawled, claimed=None):
    """检测新赛事：name+date 匹配 OR link hostname 匹配（同 utmb 子站统一 dedup）。
    claimed: 已被其他平台条目录入的官方站点域名集合 —— 命中则跳过（避免中英重复）。"""
    import re as _re
    claimed = claimed or set()
    existing_keys = set()
    existing_links = set()  # 完整 link 用于精确去重
    existing_link_hosts = set()  # hostname 用于 link dedup
    existing_by_date = {}
    for e in existing:
        existing_keys.add((normalize_name(e['name']), e.get('date', '')))
        if e.get('date'):
            existing_by_date.setdefault(e['date'], []).append(e)
        if e.get('link'):
            existing_links.add(e['link'].rstrip('/').lower())
        if e.get('link'):
            host_m = _re.match(r'https?://([^/]+)', e['link'])
            if host_m:
                host = host_m.group(1)
                if '.utmb.world' in host:
                    # utmb 子站只取 slug 作为 key
                    existing_link_hosts.add('utmb:' + host.split('.')[0])
                else:
                    existing_link_hosts.add(host)
    new_by_plat = {}
    new_link_hosts_used = set()
    new_links_used = set()
    for plat in PLATFORM_PRIORITY:
        for r in crawled.get(plat, []):
            name = r.get('name', '')
            date = r.get('date', '')
            if not name or not date:
                continue
            key = (normalize_name(name), date)
            if key in existing_keys or key in new_by_plat:
                continue
            # 同日近似名（标点/赞助商前缀差异）也与现有重复 → 不新增
            cand = {'name': name, 'date': date, 'province': r.get('province', '')}
            if any(_names_similar(cand, e) for e in existing_by_date.get(date, [])):
                continue
            link = r.get('link', '')
            # 同 link 必为同一赛事（名称标点/后缀差异也算重复）
            nlink = link.rstrip('/').lower()
            if nlink and (nlink in existing_links or nlink in new_links_used):
                continue
            if nlink:
                new_links_used.add(nlink)
            host = host_of(link)
            # 该条目的官方站点已被别的平台条目认领（如 zuicool 已有中文条目）→ 跳过
            if host and host in claimed:
                continue
            host_m = _re.match(r'https?://([^/]+)', link)
            host_key = ''
            if host_m and '.utmb.world' in host_m.group(1):
                host_key = 'utmb:' + host_m.group(1).split('.')[0]
                if host_key in existing_link_hosts or host_key in new_link_hosts_used:
                    continue
            if host_key:
                new_link_hosts_used.add(host_key)
            new_by_plat[key] = (plat, r)
    return new_by_plat


def drop_claimed_duplicates(existing, claimed, src):
    """删除 utmb 英文重复条目：link host 为 *.<slug>.utmb.world，
    而该官方站点已被别的条目（中文名、数据更全）认领。
    仅针对 utmb.world —— 其他官网（utms/cd100k 等）是独立赛事，不能删。"""
    if not claimed:
        return src, []
    dropped = []
    new_src = src
    for e in existing:
        h = host_of(e.get('link', ''))
        if h and '.utmb.world' in h and h in claimed:
            raw = e['_raw']
            if (raw + '\n') in new_src:
                new_src = new_src.replace(raw + '\n', '', 1)
            elif raw in new_src:
                new_src = new_src.replace(raw, '', 1)
            else:
                continue
            dropped.append(e['name'])
    return new_src, dropped


def insert_new_races(src, new_by_plat):
    """在 module.exports 数组的 ]; 之前追加新赛事行（保持合法逗号）"""
    if not new_by_plat:
        return src, 0
    items = [serialize_new(r) for k, (p, r) in new_by_plat.items()]
    body = ',\n  '.join(items)
    # 定位数组结束 ]; （最后一个）
    close = src.rindex('];')
    # 判断数组是否为空：module.exports = [ 之后紧接 ]
    pos = find_insert_pos(src)
    empty = bool(re.match(r'\s*\]', src[pos:pos + 10])) if pos >= 0 else False
    head = src[:close].rstrip()          # 去掉尾部空白
    tail = src[close + 2:]               # '];' 之后的内容
    if empty:
        new_src = head + '\n  ' + body + '\n];' + tail
    else:
        # head 以最后一个对象的 } 结尾 → 追加 ,\n  <新项>\n];
        new_src = head + ',\n  ' + body + '\n];' + tail
    return new_src, len(items)


def sync_region_province(existing, crawled, src):
    """已有条目若被识别为港澳台/海外（爬虫省份为港澳台/海外、而现有不是）→ 修正 province/city。
    例：香港100 原来被详情页地点误标成"浙江"，这里按卡片地点纠正为"香港"。"""
    HKMT = {'香港', '澳门', '台湾', '海外'}
    by_key = {}
    for plat, races in crawled.items():
        for r in races:
            k = link_key(r.get('link', ''))
            if k:
                by_key[k] = r
    new_src = src
    changed = 0
    for e in existing:
        cr = by_key.get(link_key(e.get('link', '')))
        if not cr or cr.get('province') not in HKMT:
            continue
        if e.get('province') == cr.get('province'):
            continue
        raw = e['_raw']
        new_raw = re.sub(r'province:"((?:[^"\\]|\\.)*)"',
                         'province:' + json.dumps(cr['province'], ensure_ascii=False), raw, count=1)
        if cr.get('city'):
            new_raw = re.sub(r'city:"((?:[^"\\]|\\.)*)"',
                             'city:' + json.dumps(clean_city(cr['city']), ensure_ascii=False), new_raw, count=1)
        if new_raw != raw:
            new_src = new_src.replace(raw, new_raw, 1)
            changed += 1
    return new_src, changed


def sync_reg_deadline(existing, crawled, src):
    """把列表卡片上的"报名截止"同步到已有条目（新增/更新/删除）。
    该字段来自列表卡片，不依赖详情页，因此每天都能拿到最新值。"""
    by_key = {}
    for plat, races in crawled.items():
        for r in races:
            k = link_key(r.get('link', ''))
            if k:
                by_key[k] = r
    new_src = src
    changed = 0
    for e in existing:
        cr = by_key.get(link_key(e.get('link', '')))
        if cr is None:
            continue
        newval = cr.get('reg_deadline') or ''
        if newval == (e.get('regDeadline') or ''):
            continue
        raw = e['_raw']
        if 'regDeadline:"' in raw:
            new_raw = re.sub(r'regDeadline:"((?:[^"\\]|\\.)*)"',
                             'regDeadline:' + json.dumps(newval, ensure_ascii=False), raw, count=1)
        elif newval:
            new_raw = re.sub(r'status:"', 'regDeadline:' + json.dumps(newval, ensure_ascii=False) + ', status:"', raw, count=1)
        else:
            continue
        if new_raw != raw:
            new_src = new_src.replace(raw, new_raw, 1)
            changed += 1
    return new_src, changed


def merge_existing_distances(existing, crawled, src):
    """对每条 existing race，如果 crawled 找到匹配（同 link 或 同 name_norm+date），
    把 crawled 的 distances 字段（特别是 climb/time）补全到 existing。
    保留 existing 的人工字段（wechat、tags），distances 用 crawled 的（含 climb/time）。"""
    import re as _re
    from _lib.parse import normalize_name
    # 建 crawled 索引（存 (平台, race)，平台决定 distances 是否可信）
    by_link = {}
    by_key = {}
    for plat, races in crawled.items():
        for r in races:
            if r.get('link'):
                m = _re.match(r'https?://([^/]+)', r['link'])
                if m:
                    by_link.setdefault(m.group(1), []).append((plat, r))
            k = (normalize_name(r.get('name', '')), r.get('date', ''))
            if k[0] and k[1]:
                by_key.setdefault(k, []).append((plat, r))
    new_src = src
    updated = 0
    for e in existing:
        # 找 matched（返回 (平台, race)）
        matched = None
        if e.get('link'):
            m = _re.match(r'https?://([^/]+)', e['link'])
            if m:
                cands = by_link.get(m.group(1), [])
                for cplat, c in cands:
                    if normalize_name(c.get('name', '')) == normalize_name(e['name']):
                        matched = (cplat, c)
                        break
        if not matched:
            k = (normalize_name(e['name']), e.get('date', ''))
            cands = by_key.get(k, [])
            if cands:
                matched = cands[0]
        if not matched:
            continue
        matched_plat, matched_race = matched
        crawled_dists = matched_race.get('distances', [])
        if not crawled_dists:
            continue
        # 只有结构化解析的平台（zuicool 的"场次组别"块）才允许覆盖现有组别；
        # 其他平台（runninginchina 等）解析噪声大，仅在现有为空时补。
        if matched_plat != 'zuicool':
            if e.get('distances'):
                continue
        # crawled 现为官方"场次组别"块解析，作为 distances 权威来源：
        # 只要解析出组别就整体替换（旧的全文扫 km 数据常有错组别/错爬升）。
        existing_dists = e.get('distances', [])
        if existing_dists and len(crawled_dists) < len(existing_dists):
            # 现有组别更多：仅当 crawled 组别基本都带爬升（更可信）时才替换，
            # 否则保留现有的多组别（避免爬到不完整时反而丢组别）。
            crawled_rich = sum(1 for d in crawled_dists if d.get('climb')) >= max(1, len(crawled_dists) // 2 + 1)
            if not crawled_rich:
                continue
        # 替换整行：保留 e 的缩进/字段，但 distances 用 crawled 的
        raw = e['_raw']
        dm = _re.search(r'distances:\[([^\]]*)\]', e['_stripped'])
        if not dm:
            continue
        crawled_dists_str = ','.join(
            '{d:"' + d.get('d', '') + ('",climb:"' + d['climb'] + '"' if d.get('climb') else '"') + (',time:"' + d['time'] + '"' if d.get('time') else '') + '}'
            for d in crawled_dists if d.get('d')
        )
        # 替换 raw 中的 distances 部分
        old_pattern = _re.escape(dm.group(0))
        new_pattern = f'distances:[{crawled_dists_str}]'
        # 找 raw 中匹配的位置（避免 dm 在 stripped 中的 prefix 不在 raw 中）
        if dm.group(0) in raw:
            new_raw = raw.replace(dm.group(0), new_pattern, 1)
        else:
            # raw 中格式可能不同
            continue
        if new_raw != raw:
            new_src = new_src.replace(raw, new_raw, 1)
            updated += 1
    return new_src, updated


def backup_data():
    """每次更新前备份 _race_data.js：
      - 本地 backup/race_data/_race_data_<时间戳>.js（保留最近 30，不入库）
      - 仓库 data_backup/_race_data_<日期>.js（保留最近 14，随 git 提交）
    目的：更新出问题时能一键回滚到上一版。
    """
    if not DATA_FILE.exists():
        return
    now = datetime.now()
    # 本地（细粒度：时间戳）
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA_FILE, LOCAL_BACKUP_DIR / f'_race_data_{now.strftime("%Y%m%d_%H%M%S")}.js')
    for old in sorted(LOCAL_BACKUP_DIR.glob('_race_data_*.js'))[:-LOCAL_BACKUP_KEEP]:
        old.unlink()
    # 仓库（每天一份，随提交保留）
    REPO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA_FILE, REPO_BACKUP_DIR / f'_race_data_{now.strftime("%Y%m%d")}.js')
    for old in sorted(REPO_BACKUP_DIR.glob('_race_data_*.js'))[:-REPO_BACKUP_KEEP]:
        old.unlink()


def main():
    print(f'[merge] 基准日期: {datetime.now().isoformat(timespec="seconds")}')
    backup_data()
    print('[merge] 已备份 _race_data.js（本地 + data_backup/）')
    existing, src = load_existing_races()
    crawled = load_crawled()
    print(f'[merge] 现有 {len(existing)} 场, 爬虫平台 {list(crawled.keys())}')
    claimed = claimed_official_hosts(crawled)
    # 已入库条目的 official 也算"认领"（增量抓取时 zuicool.json 可能没覆盖到全部）
    claimed |= {e['official'].lower() for e in existing if e.get('official')}
    if claimed:
        print(f'[merge] 已认领官方站点 {len(claimed)} 个')

    # 0. 跨平台去重：删除被其他条目认领官方站点的独立条目（如 utmb 英文重复）
    src, dropped = drop_claimed_duplicates(existing, claimed, src)
    if dropped:
        dropped_set = set(dropped)
        existing = [e for e in existing if e['name'] not in dropped_set]
        print(f'[merge] 去重删除 {len(dropped)} 场: {dropped[:5]}')

    # 1. 重算 status
    new_src, status_changed = auto_recalc_status(existing, src)
    print(f'[merge] 重算 status: {status_changed} 场')

    # 1.2 修正已有条目的港澳台省份（详情页地点常误写为大陆）
    new_src, region_fixed = sync_region_province(existing, crawled, new_src)
    if region_fixed:
        print(f'[merge] 修正港澳台归属 {region_fixed} 场')

    # 1.3 同步"报名截止"（来自列表卡片）
    new_src, dl_fixed = sync_reg_deadline(existing, crawled, new_src)
    if dl_fixed:
        print(f'[merge] 同步报名截止 {dl_fixed} 场')

    # 1.5 补全已有赛事的 distances（climb/time）— 用 crawled 匹配更新
    new_src, fields_updated = merge_existing_distances(existing, crawled, new_src)
    print(f'[merge] 补全 distances: {fields_updated} 场')

    # 2. 检测 missing + 标 cancelled
    missing_log = detect_missing(existing, crawled)
    new_src, cancelled = mark_cancelled(existing, missing_log, new_src)
    print(f'[merge] 标 cancelled: {len(cancelled)} 场')

    # 3. 检测 + 插入新赛事
    new_by_plat = detect_new(existing, crawled, claimed)
    if new_by_plat:
        new_src, added = insert_new_races(new_src, new_by_plat)
        print(f'[merge] 新增 {added} 场')

    # 3.5 最终去重（同 link_key / 同 name+date 只留信息最全的）
    new_src, deduped = dedupe_final(new_src)
    if deduped:
        print(f'[merge] 最终去重 {len(deduped)} 场')

    # 3.6 组别距离降序排序
    new_src, reordered = sort_all_distances(new_src)
    print(f'[merge] 组别排序 {reordered} 场')

    # 3.7 清洗已有的脏 city（换行/"关注"/"地点"前缀）
    new_src, city_fixed = sanitize_cities(new_src)
    if city_fixed:
        print(f'[merge] 清洗 city {city_fixed} 场')

    # 4. 写文件 + node 校验语法
    DATA_FILE.write_text(new_src, encoding='utf-8')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(
        ['node', '-e', f'module.exports = require({json.dumps(str(DATA_FILE))});'],
        capture_output=True, env=env, encoding='utf-8', errors='ignore'
    )
    if r.returncode != 0:
        print(f'[merge] ✗ 语法错误，回滚: {r.stderr[:300]}')
        DATA_FILE.write_text(src, encoding='utf-8')
        return
    print(f'[merge] ✓ _race_data.js 已更新（status_changed={status_changed}, cancelled={len(cancelled)}, added={len(new_by_plat)}）')
    pruned = prune_missing_log(existing, missing_log)
    if pruned:
        print(f'[merge] 清理 MISSING_LOG 陈旧/垃圾 key {len(pruned)} 个: {pruned[:5]}')
    save_missing_log(missing_log)

    # 5. 主报告
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f'# 合并报告 — {datetime.now().strftime("%Y-%m-%d")}\n\n')
        f.write(f'- 现有: {len(existing)} 场\n')
        f.write(f'- 各平台抓取:\n')
        for plat, races in crawled.items():
            f.write(f'  - {plat}: {len(races)} 场\n')
        f.write(f'\n- **重算 status**: {status_changed} 场\n')
        f.write(f'- **标 cancelled**: {len(cancelled)} 场\n')
        f.write(f'- **新增**: {len(new_by_plat)} 场\n\n')
        if new_by_plat:
            f.write('## 新增赛事（已自动写入）\n\n')
            for k, (p, r) in sorted(new_by_plat.items(), key=lambda x: x[1][1].get('date', ''))[:50]:
                dists = '/'.join(d['d'] for d in r.get('distances', [])) or '-'
                f.write(f"- [{p}] {r.get('name','')[:40]} ({r.get('date','')})\n")
            if len(new_by_plat) > 50:
                f.write(f"\n*（共 {len(new_by_plat)} 场，仅展示前 50）*\n")
        if cancelled:
            f.write('\n## 本轮标 cancelled\n\n')
            for c in cancelled:
                f.write(f'- {c}\n')
        miss_now = [(n, v) for n, v in missing_log.items() if not v.get('cancelled') and v.get('days', 0) > 0]
        if miss_now:
            f.write(f'\n## 当前 missing (连续未抓到) — {len(miss_now)} 场\n\n')
            for n, v in sorted(miss_now, key=lambda x: -x[1].get('days', 0))[:30]:
                f.write(f'- {v.get("name","")}: {v.get("days",0)} 天\n')
    print(f'[merge] 报告: {REPORT_FILE}')


if __name__ == '__main__':
    main()