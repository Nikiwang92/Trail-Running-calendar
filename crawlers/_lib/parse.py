# crawlers/_lib/parse.py
# 距离/爬升/关门/日期 正则匹配 + 中文日期归一
import re

DISTANCE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:KM|K|公里|kilometers?)', re.IGNORECASE)
CLIMB_RE = re.compile(r'[+＋]\s*(\d+(?:[,，]\d{3})*)\s*M?\b')
CLIMB_ALT_RE = re.compile(r'累计爬升[：:]\s*(\d+(?:[,，]\d{3})*)\s*米?')
CUTOFF_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:小时|h|hrs|hour)', re.IGNORECASE)
CN_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
ISO_DATE_RE = re.compile(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})')
SLASH_DATE_RE = re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})')
DOT_DATE_RE = re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})')


def parse_distance_km(text):
    """从文本提取距离（KM），返回列表（一场赛事可能有多个组别）"""
    matches = DISTANCE_RE.findall(text)
    out = []
    for m in matches:
        try:
            v = float(m)
            if 5 <= v <= 500:  # 越野赛合理距离范围
                out.append(f"{int(v) if v == int(v) else v}K")
        except ValueError:
            pass
    # 去重保序
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d); uniq.append(d)
    return uniq


def parse_climb(text):
    """从文本提取爬升（米）"""
    m = CLIMB_RE.search(text) or CLIMB_ALT_RE.search(text)
    if m:
        return m.group(1).replace(',', '').replace('，', '') + 'm'
    return None


def parse_cutoff_hours(text):
    """从文本提取关门时长（小时）"""
    m = CUTOFF_RE.search(text)
    if m:
        return m.group(1) + 'h'
    return None


def parse_cn_date(s):
    """'2026年9月15日' / '2026/9/15' / '2026.9.15' → '2026-09-15'"""
    if not s:
        return None
    m = CN_DATE_RE.search(s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = DOT_DATE_RE.search(s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = ISO_DATE_RE.search(s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = SLASH_DATE_RE.search(s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def parse_end_date(s):
    """从 '至 2026年9月17日' 或 '至 9月17日' 提取结束日期"""
    m = re.search(r'至\s*(\d{1,2}\s*月\s*\d{1,2}\s*日)', s)
    if m:
        sub = m.group(1)
        # 取前 4 位年（从开头）
        y = re.search(r'(\d{4})', s)
        if y:
            date_str = y.group(1) + '年' + sub
            return parse_cn_date(date_str)
    return None


def normalize_name(name):
    """去空白/括号/常见后缀，用于 fuzzy match"""
    if not name:
        return ''
    s = re.sub(r'[\s　]+', '', str(name))
    s = re.sub(r'[【】()（）\[\]「」『』《》!！?？,，。·:：・•"' + '“”‘’' + r']', '', s)
    s = s.lower()
    # 去掉开头的年份（"2026宁海越野挑战赛" == "宁海越野挑战赛"）
    s = re.sub(r'^20\d{2}年?', '', s)
    # 优先按从长到短的顺序去后缀
    for suf in [
        'byutmb®', 'byutmb', 'by utmb®', 'by utmb',
        '国际越野跑协会',
        '超级越野赛', '山地越野赛', '极限挑战赛', '越野马拉松',
        '越野赛', '跑山赛', '挑战赛', '跑山大赛', '大奖赛',
        '越野跑', 'utmb®', 'ultra-trail',
    ]:
        if s.endswith(suf):
            s = s[:-len(suf)]
    return s