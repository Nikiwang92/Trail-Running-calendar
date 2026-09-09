#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026年中国越野赛事批量抓取
从赛会通承载的赛事（朗途体育系列 + 高黎贡）抓取真实规程数据
支持两种规程格式: 组别表格型 / "实际距离+累计爬升"型
"""

import requests
import sys
import re
import json
import os
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    return soup.get_text(' ', strip=True)


def parse_common(text, title=None):
    """解析赛事通用信息: 名称/地点/时间/报名时间"""
    d = {}
    # 优先用页面标题（已清洗"【】_运营方"部分）
    if title:
        t = re.sub(r'【[^】]*】\s*[-—]?\s*', '', title)
        t = re.sub(r'(体育赛事官网|赛事官网|_朗途.*|_赛会通.*)', '', t)
        t = re.sub(r'[_-].*?(朗途|赛会通|官网)', '', t).strip(' -_')
        d['赛事名称'] = t or None
    if '赛事名称' not in d or not d.get('赛事名称'):
        m = re.search(r'赛事名称[:：]\s*(.{4,40}?)(?=\s{2,}|\n|$)', text)
        if not m:
            m = re.search(r'([^。]{3,30}?跑山赛|越野赛|跑山赛|越野挑战赛|冰川极限挑战赛)', text)
        if m:
            d['赛事名称'] = clean(m.group(1))

    m = re.search(r'(?:赛事地点|比赛地点|举办地点|地点)[:：]\s*([一-龥省市区]{2,25}?)（', text) or \
        re.search(r'(?:赛事地点|比赛地点|举办地点|地点)[:：]\s*([一-龥省市区]{2,25})', text)
    if m:
        d['城市'] = clean(m.group(1))

    m = re.search(r'(?:比赛时间|赛事时间)[:：]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}日?[^\s。；]{0,15})', text)
    if m:
        d['比赛日期'] = clean(m.group(1))

    m = re.search(r'报名时间[:：]?\s*(.*?)(?:；|。|$)', text)
    if m:
        rt = clean(m.group(1))
        rt = re.sub(r'(\d)\s+(\d{1,4})\s*年', r'\1\2年', rt)
        d['报名时间'] = rt
    return d


def parse_groups_table(text):
    """格式A: 表格型  'MGU 168km 8540D+ 8550 D- 47h 起终点 时间 时间 ITRA 名额人'"""
    groups = []
    region = text[text.find('组别信息'):] if '组别信息' in text else text
    for m in re.finditer(
        r'([A-Z]{1,4})\s+(\d{1,3})\s*k?m?\s*(\d+)\s*D\+\s*(\d+)\s*D-\s*([\d.]+)h\s*'
        r'([一-龥A-Za-z0-9\- ]+?)\s*-\s*([一-龥A-Za-z0-9\- ]+?)\s+'
        r'(20\d{2}/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})\s+'
        r'(20\d{2}/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})\s+(\d+)\s+(\d+)人',
        region
    ):
        groups.append({
            '组别': m.group(1), '距离km': m.group(2), '爬升m': m.group(3),
            '下降m': m.group(4), '关门时长h': m.group(5),
            '起点': clean(m.group(6)), '终点': clean(m.group(7)),
            '开始': f"{m.group(8)} {m.group(9)}", '关门': f"{m.group(10)} {m.group(11)}",
            'ITRA': m.group(12), '名额': m.group(13),
        })
    return groups


def parse_groups_desc(text):
    """格式B: 'XXkm组 实际距离:xxkm 累计爬升:xx米 出发时间:... 关门时间:...'"""
    groups = []
    # 1. 找到所有 'XXkm 组' 出现位置作为组别边界
    matches = list(re.finditer(r'(\d{1,3})\s*km\s*组', text))
    seen_pos = {}
    for m in matches:
        d = m.group(1)
        if d not in seen_pos:
            seen_pos[d] = m.start()

    for d, pos in sorted(seen_pos.items(), key=lambda x: x[1]):
        # 组别文本块：从当前位置到下一个组别
        ends = [p for p in seen_pos.values() if p > pos]
        end = min(ends) if ends else pos + 2000
        seg = text[pos:end]
        g = {'组别': f'{d}km', '距离km': d, '爬升m': '', '下降m': '', '关门时长h': '',
             '起点': '', '终点': '', '开始': '', '关门': '', 'ITRA': '', '名额': ''}
        # 距离
        m2 = re.search(r'实际距离[:：]\s*([\d.]+)\s*km', seg)
        if m2:
            g['距离km'] = m2.group(1)
        # 爬升
        m3 = re.search(r'累计爬升[:：]\s*([\d]+)\s*米', seg)
        if m3:
            g['爬升m'] = m3.group(1)
        # 下降
        m4 = re.search(r'累计下降[:：]\s*([\d]+)\s*米', seg)
        if m4:
            g['下降m'] = m4.group(1)
        # 出发/关门
        m5 = re.search(r'出发时间[:：]\s*([\d\s年月日.:：\-]{6,30})', seg)
        if m5:
            g['开始'] = clean(m5.group(1))
        m6 = re.search(r'关门时间[:：]\s*([\d\s年月日.:：\-]{6,40})', seg)
        if m6:
            g['关门'] = clean(m6.group(1))
        # 关门时长（括号内小时）
        m7 = re.search(r'（\s*([\d.]+)\s*小时\s*）', seg)
        if m7:
            g['关门时长h'] = m7.group(1)
        groups.append(g)
    return groups


def crawl_event(domain, article_id=None, name=None):
    """抓取单个赛事"""
    base = f'https://{domain}'
    result = {'域名': domain, '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M')}

    if article_id:
        text = fetch_text(f'{base}/m/article?id={article_id}&mid=57201')
    else:
        # 高黎贡模式: 从首页发现竞赛规程text页
        r = requests.get(f'{base}/m/', headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        comp_mid = None
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True)
            if '规程' in txt:
                m = re.search(r'/m/text\?mid=(\d+)', a.get('href', ''))
                if m:
                    comp_mid = m.group(1)
                    break
        if not comp_mid:
            return {**result, '错误': '未找到规程页'}
        text = fetch_text(f'{base}/m/text?mid={comp_mid}')

    # 记录页面标题（用于名称）
    page_url = f'{base}/m/article?id={article_id}&mid=57201' if article_id else f'{base}/m/'
    r0 = requests.get(page_url, headers=HEADERS, timeout=15)
    title = BeautifulSoup(r0.text, 'html.parser').title.get_text(strip=True) if BeautifulSoup(r0.text, 'html.parser').title else ''

    result.update(parse_common(text, title))
    groups = parse_groups_table(text) or parse_groups_desc(text) or parse_groups_dets(text)
    result['组别'] = groups
    return result


def parse_groups_dets(text):
    """格式C: 表格型变体 'XXkm 规模 报到 检录 出发 关门 颁奖 关门时长 ITRA' (如白云50)"""
    groups = []
    start = text.find('赛事项目')
    region = text[start:] if start != -1 else text
    # 匹配: '22 km 600 人 ... 6 hrs 1' 这类行
    for m in re.finditer(
        r'(\d{1,3})\s*km\s+(\d+)\s*人.*?'
        r'([\d.]+)\s*hrs?\s+(\d+)',
        region
    ):
        groups.append({
            '组别': f'{m.group(1)}km', '距离km': m.group(1), '爬升m': '', '下降m': '',
            '关门时长h': m.group(3), '起点': '', '终点': '',
            '开始': '', '关门': '', 'ITRA': m.group(4), '名额': m.group(2),
        })
    return groups


def main():
    # 真实2026赛事: 域名 + 规程文章ID (朗途体育系列)
    events = [
        ('moganshan.saihuitong.com', 69954, None),      # 2026凯乐石莫干山跑山赛
        ('moganshan.saihuitong.com', 71201, None),      # 2026 FUGA深圳100
        ('moganshan.saihuitong.com', 70868, None),      # 2026凯乐石贡嘎100
        ('moganshan.saihuitong.com', 70533, None),      # 2026凯乐石松花湖东北100
        ('moganshan.saihuitong.com', 71112, None),      # 2026白云山日落跑
        ('moganshan.saihuitong.com', 70531, None),      # 2026天河50越野赛
        ('moganshan.saihuitong.com', 70493, None),      # 2026百里少年越野赛 广州站
        ('moganshan.saihuitong.com', 70634, None),      # 2026白云50跑山赛
        ('mgucn.saihuitong.com', None, '高黎贡超级山径赛'),  # 高黎贡
    ]

    all_rows = []
    summary = []
    for domain, aid, name in events:
        print('=' * 60)
        print(f'抓取: {domain} article={aid}')
        try:
            r = crawl_event(domain, aid, name)
            title = r.get('赛事名称', domain)
            print(f'  赛事: {title}')
            print(f'  报名: {r.get("报名时间","?")}')
            print(f'  地点: {r.get("城市","?")}  日期: {r.get("比赛日期","?")}')
            print(f'  组别: {len(r.get("组别",[]))}个')
            for g in r.get('组别', []):
                print(f'    {g["组别"]} {g["距离km"]}km 爬升{g["爬升m"]}m 关门{g["关门时长h"]}h')
                all_rows.append({**{'赛事': title, '城市': r.get('城市',''),
                                    '报名时间': r.get('报名时间',''), '比赛日期': r.get('比赛日期','')}, **g})
            summary.append({'赛事': title, '城市': r.get('城市',''), '报名时间': r.get('报名时间',''),
                            '比赛日期': r.get('比赛日期',''), '组别数': len(r.get('组别',[]))})
        except Exception as e:
            print(f'  失败: {str(e)[:60]}')
            summary.append({'赛事': f'{domain}（失败）', '错误': str(e)[:40]})

    # 保存
    os.makedirs('2026赛事数据', exist_ok=True)
    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv('2026赛事数据/2026中国越野赛事.csv', index=False, encoding='utf-8-sig')
        df.to_excel('2026赛事数据/2026中国越野赛事.xlsx', index=False, engine='openpyxl')
        print(f'\n已保存 {len(all_rows)} 条组别记录 → 2026赛事数据/')

    sdf = pd.DataFrame(summary)
    sdf.to_csv('2026赛事数据/赛事汇总.csv', index=False, encoding='utf-8-sig')
    print('\n=== 汇总 ===')
    for s in summary:
        print(f"  {s.get('赛事','?')} | {s.get('城市','?')} | {s.get('报名时间','?')} | {s.get('组别数','?')}组")


if __name__ == '__main__':
    main()
