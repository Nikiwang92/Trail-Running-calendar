#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛会通越野赛事爬虫 v2
从静态"竞赛规程"页提取: 报名时间 / 全组别表(距离,爬升,下降,关门时长,起终点,比赛时间,关门时间,ITRA,名额) / 城市 / 比赛日期
无需小程序、无需抓包、无需登录。支持每日定时更新。
"""

import requests
import sys
import re
import json
import glob
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
    """清理多余空白"""
    return re.sub(r'\s+', ' ', s or '').strip()


class SaiHuiTongCrawler:
    def __init__(self, domain, event_name=None):
        self.domain = domain.rstrip('/')
        self.base = f'https://{self.domain}'
        self.event_name = event_name
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def discover(self):
        """发现页面，返回 {名称: mid}"""
        pages = {}
        r = self.session.get(f'{self.base}/m/', timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True)
            m = re.search(r'/m/text\?mid=(\d+)', a.get('href', ''))
            if m:
                pages[txt] = m.group(1)
        if not self.event_name and soup.title:
            self.event_name = clean(soup.title.get_text(strip=True))
        return pages

    def get_text(self, mid):
        r = self.session.get(f'{self.base}/m/text?mid={mid}', timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        return soup.get_text(' ', strip=True)

    def parse(self):
        result = {'域名': self.domain, '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M')}
        pages = self.discover()

        # 找竞赛规程页（优先含"规程"）
        comp_mid = None
        for name, mid in pages.items():
            if '规程' in name:
                comp_mid = mid
                break
        if not comp_mid:
            comp_mid = next(iter(pages.values()), None)

        text = self.get_text(comp_mid) if comp_mid else ''
        if not text:
            result['错误'] = '未找到竞赛规程页'
            return result

        self.event_name = self.event_name or self.domain
        result['赛事名称'] = self.event_name

        # --- 报名时间 ---
        reg = re.search(r'报名时间[:：]\s*(.*?)(?:；|。|$)', text)
        if reg:
            # 清理多余空格，如 "202 5年" -> "2025年"
            rt = clean(reg.group(1))
            rt = re.sub(r'(\d)\s+(\d{1,4})\s*年', r'\1\2年', rt)
            result['报名时间'] = rt

        # --- 城市 ---
        city = re.search(r'(?:比赛地点|赛事地点|举办地点)[:：]\s*([一-龥]{2,25}?)（', text) or \
               re.search(r'(?:比赛地点|赛事地点|举办地点)[:：]\s*([一-龥省市区]{3,20})', text)
        if city:
            result['城市'] = clean(city.group(1))

        # --- 比赛日期 ---
        date = re.search(r'比赛时间[:：]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}[^\d]*\d{0,2}日?)', text)
        if date:
            result['比赛日期'] = clean(date.group(1))

        # --- 组别表 ---
        groups = []
        # 定位组别信息表格起始
        start = text.find('组别信息')
        region = text[start:] if start != -1 else text
        # 行模式: 代码 距离km 爬升D+ 下降D- 关门h 起终点 比赛时间 关门时间 ITRA 名额
        for m in re.finditer(
            r'([A-Z]{1,4})\s+(\d{1,3})\s*k?m?\s*(\d+)\s*D\+\s*(\d+)\s*D-\s*([\d.]+)h\s*'
            r'([一-龥A-Za-z0-9\- ]+?)\s*-\s*([一-龥A-Za-z0-9\- ]+?)\s+'
            r'(20\d{2}/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})\s+'
            r'(20\d{2}/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})\s+(\d+)\s+(\d+)人',
            region
        ):
            groups.append({
                '组别': m.group(1),
                '距离': m.group(2),
                '爬升(m)': m.group(3),
                '下降(m)': m.group(4),
                '关门时长(h)': m.group(5),
                '起点': clean(m.group(6)),
                '终点': clean(m.group(7)),
                '开始时间': f"{m.group(8)} {m.group(9)}",
                '关门时间': f"{m.group(10)} {m.group(11)}",
                'ITRA': m.group(12),
                '名额(人)': m.group(13),
            })
        result['组别'] = groups
        return result

    def save(self, result, dirname='赛事数据'):
        """保存当日快照 + 追加到总清单"""
        os.makedirs(dirname, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M')
        safe = re.sub(r'[\\/:*?"<>|]', '_', self.event_name or self.domain)
        f = os.path.join(dirname, f'{safe}_{stamp}.json')
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
        return f


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description='赛会通越野赛事爬虫 v2')
    p.add_argument('domain', nargs='?', help='赛事子域名, 如 mgucn.saihuitong.com')
    p.add_argument('--name', help='赛事名称')
    p.add_argument('--domain-list', help='批量: 每行一个子域名的文件')
    return p.parse_args()


def main():
    args = parse_args()
    crawler = SaiHuiTongCrawler(args.domain, args.name) if args.domain else None
    if crawler:
        result = crawler.parse()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        crawler.save(result)
    elif args.domain_list:
        with open(args.domain_list, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                domain, _, name = line.partition(',')
                print('=' * 50)
                c = SaiHuiTongCrawler(domain.strip(), name.strip() or None)
                r = c.parse()
                c.save(r)
                print(f"{r.get('赛事名称','?')} | {r.get('报名时间','?')} | 组别{len(r.get('组别',[]))}个")
    else:
        print('请提供 domain 或 --domain-list')


if __name__ == '__main__':
    main()
