"""比对 _race_data.js 的 province 与 zuicool 列表卡片，报告不一致的赛事。
（province/city 只在新增时写入，除非 merge 的 sync_city_province 生效，否则错值会长期留存。）

用法：python scripts/audit_location.py
"""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'crawlers'))
sys.path.insert(0, str(ROOT / 'scripts'))

import merge_all as M
import zuicool as Z
from _lib.province import split_province_city


def main():
    existing, _src = M.load_existing_races()
    session = Z.get_session()
    cards = {}
    for where, _label in Z.REGIONS:
        for it in Z._list_all(session, where=where):
            cards[it['id']] = it

    by_key = {}
    for r in existing:
        k = M.link_key(r.get('link', ''))
        if k.startswith('zuicool:'):
            by_key[k] = r

    bad = []
    for rid, it in cards.items():
        e = by_key.get('zuicool:' + rid)
        if not e or not it.get('city'):
            continue
        card_prov = '海外' if it.get('_region') == '海外' else (split_province_city(it['city'])[0] or '')
        if card_prov and e.get('province') != card_prov:
            bad.append((rid, e.get('date'), e.get('province'), e.get('city'), card_prov, it['city'], e.get('name')))

    print(f'比对 {len(by_key)} 条 vs 列表卡片 {len(cards)} 张 → 省份不一致 {len(bad)} 条\n')
    for b in sorted(bad, key=lambda x: x[1] or ''):
        print(f'[{b[0]}] {b[1]} {b[6]}')
        print(f'    库里: {b[2]} / {b[3]}')
        print(f'    卡片: {b[4]} / {b[5]}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
