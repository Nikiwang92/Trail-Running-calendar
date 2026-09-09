#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
越野赛事信息爬虫
爬取路跑中国等平台2026年越野赛事信息
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from datetime import datetime
import json
import re
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('越野赛事爬虫.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TrailRunningCrawler:
    """越野赛事爬虫类"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.runchina.com/'
        }
        self.session = requests.Session()

    def get_page(self, url, max_retries=3, delay=2):
        """获取页面内容"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()
                time.sleep(delay)
                return response.text
            except requests.RequestException as e:
                logger.warning(f"尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay * 2)
                continue
        return None

    def parse_runchina_events(self):
        """解析路跑中国赛事列表"""
        events = []

        # 路跑中国赛事列表页面
        base_url = "https://www.runchina.com/event/list"
        page = 1

        logger.info(f"开始爬取路跑中国赛事，第 {page} 页...")

        while True:
            url = f"{base_url}?page={page}&type=100"  # type=100 可能是越野赛类型
            logger.info(f"访问: {url}")

            html = self.get_page(url)
            if not html:
                logger.warning("无法获取页面内容，停止爬取")
                break

            soup = BeautifulSoup(html, 'html.parser')

            # 查找赛事列表元素 - 根据实际页面结构调整
            event_items = soup.find_all('div', class_='event-item') or \
                         soup.find_all('li', class_='event-item') or \
                         soup.select('div[class*="event"]')

            if not event_items:
                # 尝试其他选择器
                event_items = soup.find_all('a', href=re.compile(r'/event/\d+'))

            if not event_items:
                logger.warning("未找到赛事列表，可能需要调整选择器")
                break

            logger.info(f"找到 {len(event_items)} 个赛事")

            for item in event_items[:10]:  # 每页最多处理10个
                try:
                    event = self.parse_event_item(item)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.error(f"解析赛事失败: {e}")
                    continue

            # 检查是否还有下一页
            next_button = soup.find('a', text='下一页') or soup.find('a', class_='next-page')
            if not next_button or 'disabled' in next_button.get('class', []):
                logger.info("没有更多页面了")
                break

            page += 1
            time.sleep(3)

        return events

    def parse_event_item(self, item):
        """解析单个赛事项"""
        event = {}

        try:
            # 获取赛事链接
            link_tag = item.find('a')
            if link_tag:
                event['链接'] = "https://www.runchina.com" + link_tag.get('href', '')

            # 获取赛事名称
            name_tag = item.find('h3') or item.find('h2') or item.find('a')
            if name_tag:
                event['赛事名称'] = name_tag.get_text(strip=True)

            # 获取城市
            city_tag = item.find('span', class_='city') or item.find('span', text=re.compile(r'[一-龥]+'))
            if city_tag:
                event['城市'] = city_tag.get_text(strip=True)

            # 获取距离
            distance_tag = item.find('span', class_='distance') or item.find('span', text=re.compile(r'\d+公里'))
            if distance_tag:
                event['距离'] = distance_tag.get_text(strip=True)

            # 获取日期
            date_tag = item.find('span', class_='date') or item.find('time')
            if date_tag:
                event['日期'] = date_tag.get_text(strip=True)

            # 获取报名状态
            status_tag = item.find('span', class_='status') or item.find('span', text=re.compile(r'报名中|已结束|即将'))
            if status_tag:
                event['报名状态'] = status_tag.get_text(strip=True)

        except Exception as e:
            logger.error(f"解析赛事项失败: {e}")

        return event if event.get('赛事名称') else None

    def parse_runchina_event_detail(self, url):
        """解析赛事详情页"""
        detail = {}

        logger.info(f"解析详情页: {url}")

        html = self.get_page(url)
        if not html:
            return detail

        soup = BeautifulSoup(html, 'html.parser')

        # 获取赛事名称
        title = soup.find('h1') or soup.find('title')
        if title:
            detail['赛事名称'] = title.get_text(strip=True)

        # 获取详情信息
        detail_info = soup.find('div', class_='event-detail') or soup.find('div', class_='info')

        if detail_info:
            # 获取城市
            city = detail_info.find('span', text=re.compile(r'城市|地点'))
            if city:
                detail['城市'] = city.get_text(strip=True).replace('城市:', '').strip()

            # 获取时间
            time_info = detail_info.find('span', text=re.compile(r'时间|日期'))
            if time_info:
                detail['日期'] = time_info.get_text(strip=True).replace('时间:', '').strip()

            # 获取距离
            distance = detail_info.find('span', text=re.compile(r'距离|公里'))
            if distance:
                detail['距离'] = distance.get_text(strip=True).replace('距离:', '').strip()

            # 获取爬升
            elevation = detail_info.find('span', text=re.compile(r'爬升|米'))
            if elevation:
                detail['爬升'] = elevation.get_text(strip=True).replace('爬升:', '').strip()

            # 获取关门时间
            cutoff = detail_info.find('span', text=re.compile(r'关门|结束'))
            if cutoff:
                detail['关门时间'] = cutoff.get_text(strip=True).replace('关门:', '').strip()

            # 获取报名链接
            reg_link = detail_info.find('a', href=re.compile(r'register|报名|sign'))
            if reg_link:
                detail['报名链接'] = reg_link.get('href', '')
                if detail['报名链接'].startswith('/'):
                    detail['报名链接'] = "https://www.runchina.com" + detail['报名链接']

            # 获取报名开始时间
            reg_time = detail_info.find('span', text=re.compile(r'报名开始|开放时间'))
            if reg_time:
                detail['报名开始时间'] = reg_time.get_text(strip=True).replace('报名开始:', '').strip()

        return detail

    def save_to_csv(self, events, filename='越野赛事2026.csv'):
        """保存到CSV文件"""
        if not events:
            logger.warning("没有赛事数据可保存")
            return

        df = pd.DataFrame(events)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"已保存 {len(events)} 条赛事到 {filename}")

    def save_to_json(self, events, filename='越野赛事2026.json'):
        """保存到JSON文件"""
        if not events:
            logger.warning("没有赛事数据可保存")
            return

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 {len(events)} 条赛事到 {filename}")

    def save_to_excel(self, events, filename='越野赛事2026.xlsx'):
        """保存到Excel文件"""
        if not events:
            logger.warning("没有赛事数据可保存")
            return

        df = pd.DataFrame(events)
        df.to_excel(filename, index=False, engine='openpyxl')
        logger.info(f"已保存 {len(events)} 条赛事到 {filename}")

    def run(self):
        """运行爬虫"""
        logger.info("=" * 50)
        logger.info("开始爬取越野赛事信息")
        logger.info("=" * 50)

        try:
            # 爬取赛事列表
            events = self.parse_runchina_events()

            if events:
                logger.info(f"共找到 {len(events)} 个赛事")

                # 保存结果
                self.save_to_csv(events)
                self.save_to_json(events)
                self.save_to_excel(events)

                # 打印前5个赛事
                logger.info("\n前5个赛事:")
                for i, event in enumerate(events[:5], 1):
                    logger.info(f"{i}. {event.get('赛事名称', 'N/A')} - {event.get('城市', 'N/A')} - {event.get('距离', 'N/A')}")
            else:
                logger.warning("未找到任何赛事数据")

        except Exception as e:
            logger.error(f"爬取失败: {e}", exc_info=True)

        logger.info("=" * 50)
        logger.info("爬取完成")
        logger.info("=" * 50)


if __name__ == '__main__':
    crawler = TrailRunningCrawler()
    crawler.run()
