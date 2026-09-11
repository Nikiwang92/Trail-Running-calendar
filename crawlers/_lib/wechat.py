# crawlers/_lib/wechat.py
# 从详情页抽取公众号名称
import re

# 匹配 "公众号：XXX" / "官方微信：XXX" / "微信公众号：XXX" / 关注 "XXX"
WECHAT_PATTERNS = [
    re.compile(r'(?:官方微信公众号|微信公众号|公众号|官方微信|微信号|官方订阅号)[:：]\s*([一-龥A-Za-z0-9·&_-]{2,30})'),
    re.compile(r'关注\s*([一-龥][一-龥A-Za-z·&_-]{1,29})'),
    re.compile(r'(?:官方|品牌)?公众号[\s"「:：]+([一-龥A-Za-z·&_-]{2,30})'),
]


def extract_wechat(text):
    """从文本中抽取公众号名称"""
    if not text:
        return None
    for pat in WECHAT_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            # 过滤明显是动词的尾巴
            if any(name.endswith(suf) for suf in ['报名', '扫码', '点击', '关注', '查看', '了解', '获取']):
                continue
            return name
    return None


def is_valid_wechat(name):
    """验证公众号名称是否合理"""
    if not name or len(name) < 2 or len(name) > 30:
        return False
    # 必须含中文
    if not re.search(r'[一-龥]', name):
        return False
    # 排除纯标签词
    blacklist = ['报名', '扫码', '点击', '关注', '查看', '了解更多', '官方', '微信', '公众号']
    return name not in blacklist