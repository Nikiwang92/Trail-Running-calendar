#!/usr/bin/env python3
# scripts/dedup_by_link.py
# 按 link 去重，保留字段最全的
import sys, re, subprocess, os, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.parse import normalize_name

DATA_FILE = ROOT / '_race_data.js'


def load_races(src):
    """返回 [{_raw, _stripped, name, link, ...}]"""
    races = []
    for line in src.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('{ name:'):
            continue
        name_m = re.search(r'name:\s*"([^"]+)"', stripped)
        if not name_m:
            continue
        r = {'_raw': line, '_stripped': stripped, 'name': name_m.group(1)}
        link_m = re.search(r'link:\s*"([^"]+)"', stripped)
        r['link'] = link_m.group(1) if link_m else ''
        for key in ('date', 'endDate', 'province', 'city', 'status', 'wechat'):
            v = re.search(rf'{key}:\s*"([^"]+)"', stripped)
            if v:
                r[key] = v.group(1)
        d_m = re.search(r'distances:\[([^\]]*)\]', stripped)
        if d_m:
            r['distances_str'] = d_m.group(1)
            r['distances_count'] = len(re.findall(r'\{d:"', d_m.group(1)))
        else:
            r['distances_str'] = ''
            r['distances_count'] = 0
        t_m = re.search(r'tags:\[([^\]]*)\]', stripped)
        r['tags'] = [t for t in re.findall(r'"([^"]+)"', t_m.group(1))] if t_m else []
        races.append(r)
    return races


def completeness_score(r):
    score = 0
    if r.get('endDate'): score += 5
    if r.get('wechat'): score += 3
    if r.get('province'): score += 2
    if r.get('city'): score += 2
    score += r.get('distances_count', 0) * 2
    score += len(r.get('tags', []))
    if any('一' <= c <= '鿿' for c in r['name']):
        score += 2
    return score


def name_similarity(a, b):
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0
    shared = sum(1 for c in na if c in nb)
    return shared / max(len(na), len(nb))


def find_groups(races):
    """按 link 分组 dedup：
    - utmb 子站：同 hostname (slug.utmb.world) 视为同一赛事
    - 其他平台：完整 link 相同时才视为同一赛事（再用 name 相似度二次过滤）
    """
    by_key = defaultdict(list)  # key: utmb_slug 或 full_link
    no_link = []
    for r in races:
        if r['link']:
            m = re.match(r'https?://([^/]+)(/.*)?', r['link'])
            if m and '.utmb.world' in m.group(1):
                # utmb 子站：只取 hostname 的 slug
                host = m.group(1)
                slug = host.split('.')[0]  # e.g. 'dajingmen'
                key = f'utmb:{slug}'
            else:
                key = r['link'].rstrip('/')
            by_key[key].append(r)
        else:
            no_link.append(r)
    groups = []
    for key, items in by_key.items():
        if len(items) < 2:
            continue
        is_utmb = key.startswith('utmb:')
        if is_utmb:
            # utmb 子站强制 dedup（slug 相同即视为同一赛事）
            groups.append((items[0]['link'], items))
            continue
        # 其他平台：name 相似度聚类
        item_groups = []
        for r in items:
            placed = False
            for g in item_groups:
                if any(name_similarity(r['name'], x['name']) >= 0.4 for x in g):
                    g.append(r)
                    placed = True
                    break
            if not placed:
                item_groups.append([r])
        for g in item_groups:
            if len(g) >= 2:
                groups.append((key, g))
    # 兜底：没 link 的按 name+date 在现有赛事中找匹配（相似度 >= 0.5）
    for r in no_link:
        d = r.get('date', '')
        for ex in races:
            if ex is r or not ex['link'] or ex.get('date') != d:
                continue
            if name_similarity(r['name'], ex['name']) >= 0.5:
                for _, items in groups:
                    if ex in items:
                        items.append(r)
                        break
                else:
                    if ex['link']:
                        groups.append((ex['link'].rstrip('/'), [ex, r]))
                break
    return groups


def merge_group(group):
    """合并一组：保留最全字段的代表；同时合并同赛事同整数 K 的距离重复"""
    rep = max(group, key=completeness_score)
    others = [r for r in group if r is not rep]
    # 合并 tags
    all_tags = list(rep['tags'])
    for o in others:
        for t in o['tags']:
            if t not in all_tags:
                all_tags.append(t)
    # 合并 distances 并集，同整数 K 去重（保留 climb/time 信息更全的）
    def parse_d(s):
        """'100K' → (100, 'K', '') 等"""
        m = re.match(r'^(\d+(?:\.\d+)?)(K?)(.*)$', s)
        if m:
            return (int(round(float(m.group(1)))), m.group(2) or 'K', m.group(3))
        return (None, None, s)

    seen_k = {}  # km_int → best {d, climb, time}
    def add(s):
        nonlocal seen_k
        for m in re.finditer(r'\{d:"([^"]+)"(?:,climb:"([^"]*)")?(?:,time:"([^"]*)")?\}', s):
            d_str = m.group(1)
            climb = m.group(2) or ''
            time_v = m.group(3) or ''
            km_int, suffix, extra = parse_d(d_str)
            if km_int is None:
                continue
            key = (km_int, suffix)
            existing = seen_k.get(key)
            score_now = (1 if climb else 0) + (1 if time_v else 0)
            if not existing or score_now > existing[3]:
                seen_k[key] = (d_str, climb, time_v, score_now)
    add(rep.get('distances_str', ''))
    for o in others:
        add(o.get('distances_str', ''))
    # 输出
    sorted_d = sorted(seen_k.items(), key=lambda x: -x[0][0])
    merged_d = []
    for (km_int, suffix), (d_str, climb, time_v, _) in sorted_d:
        if climb and time_v:
            merged_d.append(f'{{d:"{d_str}",climb:"{climb}",time:"{time_v}"}}')
        elif climb:
            merged_d.append(f'{{d:"{d_str}",climb:"{climb}"}}')
        elif time_v:
            merged_d.append(f'{{d:"{d_str}",time:"{time_v}"}}')
        else:
            merged_d.append(f'{{d:"{d_str}"}}')
    final_wechat = rep.get('wechat') or ''
    for o in others:
        if o.get('wechat') and not final_wechat:
            final_wechat = o['wechat']
    final_enddate = rep.get('endDate') or ''
    for o in others:
        if o.get('endDate') and not final_enddate:
            final_enddate = o['endDate']
    parts = [f"name:{json.dumps(rep['name'], ensure_ascii=False)}",
             f"date:{json.dumps(rep['date'], ensure_ascii=False)}"]
    if final_enddate:
        parts.append(f"endDate:{json.dumps(final_enddate, ensure_ascii=False)}")
    if rep.get('province'):
        parts.append(f"province:{json.dumps(rep['province'], ensure_ascii=False)}")
    if rep.get('city'):
        parts.append(f"city:{json.dumps(rep['city'], ensure_ascii=False)}")
    parts.append(f"distances:[{','.join(merged_d)}]")
    parts.append(f"tags:[{','.join(json.dumps(t, ensure_ascii=False) for t in all_tags)}]")
    parts.append(f"status:{json.dumps(rep.get('status', 'upcoming'), ensure_ascii=False)}")
    parts.append(f"link:{json.dumps(rep['link'], ensure_ascii=False)}")
    if final_wechat:
        parts.append(f"wechat:{json.dumps(final_wechat, ensure_ascii=False)}")
    return '  { ' + ', '.join(parts) + ' },'


def dedup(src):
    races = load_races(src)
    groups = find_groups(races)
    new_src = src
    removed = []
    for link, group in groups:
        rep_line = merge_group(group)
        first_raw = group[0]['_raw']
        # 删除组内所有行（按 _raw 完整匹配）
        for r in group:
            if r['_raw'] in new_src:
                new_src = new_src.replace(r['_raw'] + '\n', '', 1)
                if not r['_raw'] in new_src:
                    removed.append(r['name'])
        # 在第一行原位置插入合并行
        # 找 first_raw 原来的换行位置（已经删掉），改为合并行
        # 简化：找到 first_raw 后面的换行符 + 第一个相邻行的开头，插合并行
        # 但 first_raw 已被替换为空，所以用空字符串位置插
        # 更简单：在 ]; 之前追加合并行
        m = list(re.finditer(r'\n\];', new_src))
        if m:
            pos = m[-1].start()
            new_src = new_src[:pos] + ',\n' + rep_line + new_src[pos:]
    return new_src, removed


def main():
    src = DATA_FILE.read_text(encoding='utf-8')
    new_src, removed = dedup(src)
    if not removed:
        print('✓ 无 link 重复需清理')
        return
    DATA_FILE.write_text(new_src, encoding='utf-8')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(
        ['node', '-e', f'module.exports = require({str(DATA_FILE)!r});'],
        capture_output=True, env=env, encoding='utf-8', errors='ignore'
    )
    if r.returncode != 0:
        print(f'✗ 语法错误，回滚: {r.stderr[:300]}')
        DATA_FILE.write_text(src, encoding='utf-8')
        return
    print(f'✓ 合并了 {len(removed)} 场：')
    for n in removed:
        print(f'  - {n}')


if __name__ == '__main__':
    main()