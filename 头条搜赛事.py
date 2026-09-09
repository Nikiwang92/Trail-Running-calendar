#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用头条搜索多关键词, 提取2026越野赛事名
"""
import sys, time, re, json
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from bs4 import BeautifulSoup
opts = Options()
opts.add_argument('--headless'); opts.add_argument('--no-sandbox'); opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
d = webdriver.Edge(options=opts)

QUERIES = ['2026越野赛', '2026越野赛 报名', '越野赛 2026 赛程', '越野跑 赛事 2026', '2026马拉松 越野 报名', '山地越野赛 2026']
all_text = []
for q in QUERIES:
    try:
        url = 'https://www.toutiao.com/search/?keyword=' + __import__('urllib.parse', fromlist=['quote']).quote(q)
        d.get(url)
        time.sleep(8)
        body = d.find_element('css selector','body').text
        all_text.append(body)
        print(f'[{q}] 已抓取, 文本{len(body)}字')
    except Exception as e:
        print(f'[{q}] 失败 {str(e)[:50]}')
d.quit()

# 从所有文本提取赛事名: 匹配"2026...越野赛/跑山赛/挑战赛"等
full = '\n'.join(all_text)
# 赛事名模式
pat = re.compile(r'(?:2026|２０２６)?\s*([一-龥A-Za-z0-9·&]{2,30}?(?:越野赛|跑山赛|越野挑战赛|超级越野赛|山地越野|越野跑|越野马拉松|冰川极限挑战赛|越野大奖赛))')
matches = []
for m in pat.finditer(full):
    name = re.sub(r'\s+','',m.group(1))
    name = re.sub(r'^(2026|２０２６)','',name)
    if name and name not in matches:
        matches.append(name)

print('\n=== 提取到的赛事名 ===')
for i,n in enumerate(matches,1):
    print(f'{i}. {n}')
json.dump(matches, open('头条赛事清单.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'共 {len(matches)} 个')
