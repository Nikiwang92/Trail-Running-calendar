# 中国越野赛事日历 🏃⛰️

一个**每天自动更新**的全国越野跑赛事日历。自动从多个平台抓取赛事，汇总成一张可搜索、可筛选的网页。

> 数据每日 00:00（北京时间）自动刷新，无需人工维护。

📁 想看**详细项目结构 / 内部流程**？ → [`project/project.md`](./project/project.md)

![预览](docs/preview.png)

*[English →](./README.en.md)*

---

## 这是什么

把散落在最酷、UTMB、赛会通等平台的越野赛事，聚合成**一份**带日期、地点、组别、爬升、关门时间、认证标签（UTMB / 黄金联赛 / ITRA / 青少年 / 训练赛）的清单，并按月份排成日历。

目前收录 **840+ 场** 2026 年赛事，覆盖 29 个省份。

---

## 在线访问

🌐 **https://nikiwang92.github.io/Trail-Running-calendar/**

> 首次使用需在仓库 `Settings → Pages` 里把 Source 设为 `main` 分支根目录（见下方 [Fork 指南](#fork-成你自己的日历)）。

---

## 功能

- 🔍 **搜索**：按赛事名称、地点、组别搜索（如输入 `100K`、`灵鹫山`、`北京`）
- 🏷️ **标签筛选**：UTMB / 黄金联赛 / ITRA / 青少年 / 训练赛 / 100K+ （可多选叠加）
- 📅 **状态 & 月份 & 省份筛选**：未开始 / 已结束、按月、按省
- 📊 **赛事详情**：每场显示所有官方组别及对应爬升、关门时长、公众号、报名链接
- 📱 **响应式**：手机 / 平板 / 桌面自适应

---

## 数据来源

| 平台 | 说明 |
|---|---|
| [最酷 zuicool](https://zuicool.com) | 主力来源，覆盖约 95% |
| [UTMB World Series](https://www.utmb.world) | UTMB 世界系列赛中国站 |

数据来自各平台公开页面，仅供参考，**请以赛事官方公告为准**。

---

## 每日更新（自动）

不需要你操作，每天北京时间 03:00 自动跑一遍：

1. **抓取**（约 1.5 分钟）—— 先扫一遍全部赛事列表，只对**新增**和**有变动**的赛事抓详情页；每 15 天做一次全量兜底
2. **合并** —— 去重、补全组别、重算状态；更新前自动备份
3. **发布** —— 提交并重新部署网页

想看是否正常：`你的仓库 → Actions → Daily Update`（绿勾即正常）。

---

## 本地预览

无需安装任何依赖，直接双击打开 `index.html` 即可（数据通过 `<script src>` 加载，`file://` 下可用）。

想改数据或跑爬虫，见下方调试章节。

---

## Fork 成你自己的日历

想要一个属于自己（或自己地区）的版本？按以下步骤：

### 1. Fork 仓库
点本页右上角 **Fork**，得到 `你的用户名/Trail-Running-calendar`。

### 2. 开启自动更新（GitHub Actions）
- 进入 `你的仓库 → Actions`
- 若提示 "Workflows aren't being run on this forked repository"，点 **I understand my workflows, go ahead and enable them**
- 之后每天 UTC 19:00（北京 03:00）会自动抓取并提交

### 3. 开启网页托管（GitHub Pages）
- `Settings → Pages`
- **Source** 选 `Deploy from a branch`
- **Branch** 选 `main` + `/ (root)` → Save
- 几分钟后访问 `https://你的用户名.github.io/Trail-Running-calendar/`

> 仓库自带 `.nojekyll`——否则 Pages 的 Jekyll 会忽略以 `_` 开头的 `_race_data.js`，页面会一片空白。

### 4. 授权 Actions 提交（如遇权限报错）
- `Settings → Actions → General → Workflow permissions`
- 选 **Read and write permissions** → Save

### 5. 想改成只保留某个地区 / 某个类型？
- **只留某个省份**：改 `crawlers/zuicool.py` 的 `crawl(year_filter=...)` 附近，或在 `scripts/merge_all.py` 里加过滤
- **换年份**：全局搜 `2026`，改成目标年份
- **换配色**：改 `index.html` 顶部的 CSS 变量 `--red / --blue / --yellow` 等

---

## 调试指南

### 数据没更新？
1. 打开 `你的仓库 → Actions → Daily Update`，看最近一次是否成功
2. 失败常见原因：
   - 没开 Actions 写权限 → 见上方 Fork 第 4 步
   - 爬虫被目标站点限流 / 改版 → 看日志里 `[zuicool]` 的翻页输出
3. **手动触发一次**：`Actions → Daily Update → Run workflow`

### 本地跑整条链路
```bash
# 1) 抓取（增量：只抓新增/有变动的，约 1–2 分钟）
python crawlers/zuicool.py
#    想强制全量详情（800+ 页，15–40 分钟）：
python crawlers/zuicool.py --full

# 2) 合并爬虫结果 → _race_data.js
python scripts/merge_all.py

# 3) 重算状态 + 刷新 index.html
node daily_update.js

# 4) 浏览器打开 index.html 预览
```
> Windows 本地跑 Python 前先设 `PYTHONIOENCODING=utf-8`，否则控制台 GBK 编码会报错。

### 某平台抓不到数据？
- 看爬虫产出的 `crawl/output/{平台}.json` 的 `count`
- 看 `crawl/REPORT_<日期>.md`（合并报告）
- 想精确排查某场赛事：
  ```bash
  python -c "import sys; sys.path.insert(0,'crawlers'); import zuicool as z; \
  print(z.parse_detail(z.fetch('https://zuicool.com/event/98816')))"
  ```

### 页面搜索 / 筛选没反应？
1. 浏览器按 `F12` 打开 Console 看有没有红色报错
2. 常见原因：`_race_data.js` 里某条数据字段缺失（如 `city` 为空），导致脚本抛错
3. 校验数据文件语法：
   ```bash
   node -e "require('./_race_data.js'); console.log('数据 OK')"
   ```
4. 校验页面脚本：
   ```bash
   node daily_update.js    # 末尾会打印 index.html JS 语法是否 OK
   ```

### 想改完立即看效果
本地双击 `index.html` 刷新即可，无需构建、无需起服务。

---

## 技术栈

- **数据抓取**：Python 3 + requests + BeautifulSoup
- **数据存储**：单个 CommonJS 文件 `_race_data.js`
- **前端**：原生 HTML / CSS / JavaScript（零依赖、零构建）
- **自动化**：GitHub Actions + GitHub Pages

想看**详细的项目结构与内部流程**，见 [`project/project.md`](./project/project.md)。

---

## 许可与致谢

数据版权归各赛事主办方与发布平台所有，本项目仅做聚合展示。发现问题欢迎提 Issue。

如果这个小工具帮到了你，欢迎点个 ⭐。
