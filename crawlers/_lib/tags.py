# crawlers/_lib/tags.py
# tags 推断：utmb / golden / itra（赛事认证）+ youth（青少年/亲子/少儿）+ training（训练赛/训练营）
import re

UTMB_KW = ['utmb', 'by utmb', '黄金联赛', 'golden league', '黄金系列']
GOLDEN_KW = ['黄金联赛', '黄金系列赛', 'golden league']
ITRA_KW = ['itra', '国际越野跑协会']
YOUTH_KW = ['青少年', '少年', '亲子', '少儿', 'kidstrail', '少年越野', '儿童越野', 'kids trail', '少年组', '亲子组']
TRAINING_KW = ['训练赛', '训练营', '训练', 'practice race', 'training camp']


def infer_tags(*sources):
    """从多个源（详情页文本/链接/API 字段）推断 tags
    返回 list，元素 ∈ {utmb, golden, itra, youth, training}
    """
    text = ' '.join(str(s or '') for s in sources).lower()
    tags = []
    if any(kw in text for kw in UTMB_KW):
        tags.append('utmb')
    if any(kw in text for kw in GOLDEN_KW):
        tags.append('golden')
    if any(kw in text for kw in ITRA_KW):
        tags.append('itra')
    if any(kw in text for kw in YOUTH_KW):
        tags.append('youth')
    if any(kw in text for kw in TRAINING_KW):
        tags.append('training')
    return tags


def merge_tags(existing, crawled):
    """合并已有 tags 和新推断的 tags
    - 保留人工标注的
    - 去重保序
    """
    out = list(existing or [])
    for t in (crawled or []):
        if t not in out:
            out.append(t)
    return out


def tags_from_page(html, name=''):
    """从详情页 HTML 推断 tags。
    关键：剔除"相关赛事/推荐"侧栏（.events-list）与页眉页脚，
    否则会把侧栏里**别的**赛事名（如"XX训练赛"）当成关键词误标。
    """
    if not html:
        return infer_tags(name)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    for sel in ('.events-list', 'nav', 'header', 'footer'):
        for el in soup.select(sel):
            el.decompose()
    return infer_tags(name, soup.get_text(' ', strip=True))