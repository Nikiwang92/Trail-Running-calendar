#!/usr/bin/env python3
# scripts/fix_tags.py
# 一次性修正 _race_data.js 里因"整页扫关键词"而误标/漏标的 tags：
#   - 只对 link 指向 zuicool 的条目重新抓取详情页
#   - tags 改为只从"赛事自身内容"推断（名称 + event-desc_lead 块），忽略侧栏推荐
# 用法: python scripts/fix_tags.py
import sys, re, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))
from _lib.http import fetch, get_session
from _lib.tags import tags_from_page

DATA_FILE = ROOT / '_race_data.js'


def main():
    src = DATA_FILE.read_text(encoding='utf-8')
    lines = src.split('\n')
    s = get_session()
    changed = 0
    checked = 0
    for i, line in enumerate(lines):
        st = line.strip()
        if not (st.startswith('{ name:') or st.startswith('{name:')):
            continue
        # 注意：所有正则都在未 strip 的 line 上匹配，避免缩进导致的偏移
        tag_m = re.search(r'tags:\[([^\]]*)\]', line)
        if not tag_m:
            continue
        cur = [t.strip().strip('"') for t in tag_m.group(1).split(',') if t.strip()]
        if not (set(cur) & {'youth', 'training'}):
            continue  # 只重算带 youth/training 的条目（侧栏误标的影响面）
        link_m = re.search(r'link:"([^"]+)"', line)
        if not link_m or 'zuicool.com/event/' not in link_m.group(1):
            continue  # 非 zuicool 来源，无页面可核，保持原样
        name_m = re.search(r'name:"([^"]+)"', line)
        name = name_m.group(1) if name_m else ''
        html = fetch(link_m.group(1), session=s, timeout=15)
        checked += 1
        if not html:
            continue
        new_tags = tags_from_page(html, name)
        if new_tags != cur:
            new_field = 'tags:[' + ','.join(json.dumps(t, ensure_ascii=False) for t in new_tags) + ']'
            lines[i] = line[:tag_m.start()] + new_field + line[tag_m.end():]
            changed += 1
            print(f'  {name[:30]}: {cur} -> {new_tags}')
    DATA_FILE.write_text('\n'.join(lines), encoding='utf-8')
    print(f'[fix_tags] 检查 {checked} 条, 修改 {changed} 条')

    # 校验语法；失败则回滚
    import subprocess, os
    env = os.environ.copy(); env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(['node', '-e', f'module.exports = require({json.dumps(str(DATA_FILE))});'],
                       capture_output=True, env=env, encoding='utf-8', errors='ignore')
    if r.returncode == 0:
        print('[fix_tags] 语法 OK')
    else:
        DATA_FILE.write_text(src, encoding='utf-8')
        print('[fix_tags] ✗ 语法错误，已回滚: ' + r.stderr[:200])


if __name__ == '__main__':
    main()
