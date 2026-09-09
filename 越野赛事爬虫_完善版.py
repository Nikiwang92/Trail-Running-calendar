#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
越野赛事信息爬虫 - 完善版
支持多平台、自动更新、错误处理
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
import re
from datetime import datetime
import logging
from urllib.parse import urljoin

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('越野赛事爬虫_完善版.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TrailRunningCrawlerV2:
    """越野赛事爬虫类 V2"""

    # 爬虫平台配置
    PLATFORMS = {
        'runchina': {
            'name': '路跑中国',
            'base_url': 'https://www.runchina.com',
            'event_url': 'https://www.runchina.com/event/list',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        },
        '170617': {
            'name': '170617跑吧',
            'base_url': 'https://www.170617.com',
            'event_url': 'https://www.170617.com/events',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        },
        'nfgs': {
            'name': '南太行越野',
            'base_url': 'https://www.nfgs.com',
            'event_url': 'https://www.nfgs.com/events',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.PLATFORMS['runchina']['headers'])
        self.all_events = []

    def get_page(self, url, platform='runchina', max_retries=3, delay=2):
        """获取页面内容"""
        platform_config = self.PLATFORMS.get(platform, self.PLATFORMS['runchina'])

        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url,
                    headers=platform_config['headers'],
                    timeout=10,
                    allow_redirects=True
                )
                response.raise_for_status()
                time.sleep(delay + (attempt * 0.5))  # 递增延迟
                return response.text
            except requests.RequestException as e:
                logger.warning(f"[{platform}] 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay * 2)
                continue
        return None

    def parse_runchina_events(self):
        """解析路跑中国赛事列表"""
        events = []
        base_url = "https://www.runchina.com"

        logger.info(f"开始爬取路跑中国赛事...")

        # 尝试不同的URL
        urls = [
            f"{base_url}/event/list?type=100",  # 越野赛类型
            f"{base_url}/event/list",
            f"{base_url}/event",
        ]

        for url in urls:
            logger.info(f"访问: {url}")

            html = self.get_page(url, 'runchina')
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # 尝试多种选择器
            selectors = [
                ('div.event-item', 'item'),
                ('li.event-item', 'item'),
                ('div[class*="event"]', 'item'),
                ('a[href*="/event/"]', 'link'),
            ]

            for selector, name in selectors:
                event_items = soup.select(selector)
                if event_items:
                    logger.info(f"找到 {len(event_items)} 个赛事 (使用选择器: {selector})")
                    break

            if not event_items:
                logger.warning("未找到赛事列表，尝试解析详情页...")
                return []

            for idx, item in enumerate(event_items[:50], 1):  # 限制50个
                try:
                    event = self.parse_event_item(item, base_url)
                    if event and event.get('赛事名称'):
                        events.append(event)
                except Exception as e:
                    logger.error(f"解析赛事 {idx} 失败: {e}")
                    continue

            if events:
                logger.info(f"成功解析 {len(events)} 个赛事")
                break

        return events

    def parse_event_item(self, item, base_url):
        """解析单个赛事项"""
        event = {}

        try:
            # 获取赛事名称
            name_tag = item.find('h3') or item.find('h2') or item.find('a')
            if name_tag:
                event['赛事名称'] = name_tag.get_text(strip=True)

            # 获取链接
            link_tag = item.find('a')
            if link_tag:
                href = link_tag.get('href', '')
                event['链接'] = urljoin(base_url, href)

            # 获取城市
            city_tag = item.find('span', class_='city') or item.find('span', class_='location')
            if city_tag:
                event['城市'] = city_tag.get_text(strip=True)

            # 获取距离
            distance_tag = item.find('span', class_='distance') or item.find('span', text=re.compile(r'\d+公里'))
            if distance_tag:
                event['距离'] = distance_tag.get_text(strip=True)

            # 获取日期
            date_tag = item.find('time') or item.find('span', class_='date')
            if date_tag:
                event['日期'] = date_tag.get_text(strip=True)

            # 获取爬升
            elevation_tag = item.find('span', text=re.compile(r'爬升|米'))
            if elevation_tag:
                event['爬升'] = elevation_tag.get_text(strip=True)

            # 获取关门时间
            cutoff_tag = item.find('span', text=re.compile(r'关门|结束'))
            if cutoff_tag:
                event['关门时间'] = cutoff_tag.get_text(strip=True)

            # 获取报名状态
            status_tag = item.find('span', class_='status') or item.find('span', text=re.compile(r'报名中|即将'))
            if status_tag:
                event['报名状态'] = status_tag.get_text(strip=True)

            # 获取报名链接
            reg_link_tag = item.find('a', text=re.compile(r'报名|立即报名'))
            if reg_link_tag:
                event['报名链接'] = urljoin(base_url, reg_link_tag.get('href', ''))

        except Exception as e:
            logger.error(f"解析赛事项失败: {e}")

        return event if event.get('赛事名称') else None

    def parse_event_detail(self, url, platform='runchina'):
        """解析赛事详情页"""
        detail = {}

        logger.info(f"解析详情页: {url}")

        html = self.get_page(url, platform)
        if not html:
            return detail

        soup = BeautifulSoup(html, 'html.parser')

        # 获取赛事名称
        title = soup.find('h1') or soup.find('title')
        if title:
            detail['赛事名称'] = title.get_text(strip=True)

        # 查找详情区域
        detail_area = soup.find('div', class_='event-detail') or \
                     soup.find('div', class_='info') or \
                     soup.find('div', class_='content') or \
                     soup.find('article')

        if detail_area:
            # 提取所有文本，按标点分割
            text = detail_area.get_text('\n', strip=True)

            # 使用正则提取关键信息
            patterns = {
                '城市': r'城市[:：]\s*([一-龥]+)',
                '地点': r'地点[:：]\s*([一-龥]+)',
                '日期': r'日期[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}/\d{2,4})',
                '时间': r'时间[:：]\s*(\d{1,2}:\d{2}|\d{1,2}-\d{2}:\d{2})',
                '距离': r'距离[:：]\s*(\d+(?:\.\d+)?公里)',
                '爬升': r'爬升[:：]\s*(\d+(?:\.\d+)?米)',
                '关门时间': r'关门[:：]\s*(\d+(?:\.\d+)?)',
                '报名开始时间': r'报名开始[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}/\d{2,4})',
                '报名结束时间': r'报名结束[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}/\d{2,4})',
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, text)
                if match:
                    detail[key] = match.group(1).strip()

            # 查找报名链接
            reg_tag = soup.find('a', href=re.compile(r'register|sign-up|报名'))
            if reg_tag:
                detail['报名链接'] = urljoin(self.PLATFORMS[platform]['base_url'], reg_tag.get('href', ''))

        return detail

    def run(self, platforms=None):
        """运行爬虫"""
        if platforms is None:
            platforms = ['runchina']

        logger.info("=" * 60)
        logger.info("开始爬取越野赛事信息")
        logger.info(f"平台: {', '.join([self.PLATFORMS[p]['name'] for p in platforms])}")
        logger.info("=" * 60)

        try:
            for platform in platforms:
                if platform not in self.PLATFORMS:
                    logger.warning(f"未知的平台: {platform}")
                    continue

                logger.info(f"\n{'=' * 60}")
                logger.info(f"爬取: {self.PLATFORMS[platform]['name']}")
                logger.info(f"{'=' * 60}")

                events = self.parse_runchina_events()

                if events:
                    self.all_events.extend(events)
                    logger.info(f"{self.PLATFORMS[platform]['name']} - 共找到 {len(events)} 个赛事")

                    # 解析前5个赛事的详情
                    for i, event in enumerate(events[:5], 1):
                        logger.info(f"\n解析第 {i} 个赛事详情:")
                        detail = self.parse_event_detail(event['链接'], platform)
                        if detail:
                            logger.info(f"  {detail}")

        except Exception as e:
            logger.error(f"爬取失败: {e}", exc_info=True)

        # 保存结果
        self.save_results()

        logger.info("\n" + "=" * 60)
        logger.info("爬取完成")
        logger.info(f"共找到 {len(self.all_events)} 个赛事")
        logger.info("=" * 60)

    def save_results(self, filename='越野赛事2026_爬取.csv'):
        """保存结果到多个格式"""
        if not self.all_events:
            logger.warning("没有赛事数据可保存")
            return

        # 保存CSV
        df = pd.DataFrame(self.all_events)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"已保存 CSV: {filename}")

        # 保存Excel
        excel_file = filename.replace('.csv', '.xlsx')
        df.to_excel(excel_file, index=False, engine='openpyxl')
        logger.info(f"已保存 Excel: {excel_file}")

        # 保存JSON
        json_file = filename.replace('.csv', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_events, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 JSON: {json_file}")

        # 打印统计
        logger.info("\n数据统计:")
        logger.info(f"  总赛事数: {len(self.all_events)}")

        # 统计报名状态
        status_count = {}
        for event in self.all_events:
            status = event.get('报名状态', '未知')
            status_count[status] = status_count.get(status, 0) + 1

        logger.info(f"  报名状态:")
        for status, count in status_count.items():
            logger.info(f"    {status}: {count} 个")

        # 统计城市分布
        city_count = {}
        for event in self.all_events:
            city = event.get('城市', '未知')
            city_count[city] = city_count.get(city, 0) + 1

        logger.info(f"\n  城市分布(前10):")
        sorted_cities = sorted(city_count.items(), key=lambda x: x[1], reverse=True)[:10]
        for city, count in sorted_cities:
            logger.info(f"    {city}: {count} 个")


def main():
    """主函数"""
    crawler = TrailRunningCrawlerV2()

    # 选择要爬取的平台
    print("\n请选择要爬取的平台:")
    print("1. 路跑中国 (runchina) - 推荐")
    print("2. 170617跑吧")
    print("3. 南太行越野")
    print("4. 全部平台")

    choice = input("\n请输入选项(1-4): ").strip()

    platforms = []
    if choice == '1':
        platforms = ['runchina']
    elif choice == '2':
        platforms = ['170617']
    elif choice == '3':
        platforms = ['nfgs']
    elif choice == '4':
        platforms = ['runchina', '170617', 'nfgs']
    else:
        print("默认使用路跑中国")
        platforms = ['runchina']

    crawler.run(platforms)


if __name__ == '__main__':
    main()
