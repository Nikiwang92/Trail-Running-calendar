<div align="center">

# 🏃‍♂️⛰️ 越野赛事日历

**每天自动更新**的越野跑赛事日历 —— 从多个平台抓取，汇总成一张可搜索、可筛选的网页

[![自动更新](https://img.shields.io/badge/自动更新-每日%2003%3A00-2ea44f?style=flat-square)](https://github.com/Nikiwang92/Trail-Running-calendar/actions)
[![数据源](https://img.shields.io/badge/数据源-最酷%20%7C%20UTMB%20%7C%20TORX%20%7C%20Skyrunning-1f6feb?style=flat-square)](#-数据来源)
[![前端](https://img.shields.io/badge/前端-零依赖%20零构建-orange?style=flat-square)](#-技术栈)
[![赛事](https://img.shields.io/badge/收录-1100%2B%20场-d02020?style=flat-square)](#-数据规模)

[**🌐 在线访问**](https://nikiwang92.github.io/Trail-Running-calendar/) &nbsp;·&nbsp;
[**📖 项目文档**](./project/project.md) &nbsp;·&nbsp;
[**📝 版本记录**](./version/version.md) &nbsp;·&nbsp;
[**English →**](./README.en.md)

</div>

![预览](docs/preview.png)

---

## ✨ 功能

| | |
|---|---|
| 🔍 **搜索** | 按赛事名称、地点、组别即时筛选（试试 `100K`、`灵鹫山`、`北京`）|
| 🏷️ **标签筛选** | UTMB / TORX / Skyrunning / 黄金联赛 / ITRA / 青少年 / 训练赛 / 100K+ —— 可多选叠加 |
| 📅 **状态 / 年份 / 月份 / 省份** | 未开始 · **进行中** · 已结束；2026 / 2027；1–12 月；各省份 |
| 📊 **赛事详情** | 每场列出全部官方组别及对应**累计爬升**、**关门时长**、报名截止、微信公众号、官方链接 |
| 📱 **响应式** | 手机 / 平板 / 桌面自适应 |

---

## 🌐 在线访问

**<https://nikiwang92.github.io/Trail-Running-calendar/>**

> 打不开或页面空白？见下方 [Fork 指南](#-fork-成你自己的日历) 里的 Pages 设置。

---

## 📈 数据规模

| 指标 | 数值 |
|---|---|
| 赛事总数 | **1124 场**（2026: 1085 / 2027: 39）|
| 覆盖地区 | 33 个省市自治区（含港澳台 6 场、海外 233 场）|
| 官方组别 | 2779 个（其中 1449 个带累计爬升、876 个带关门时长）|

> 数字每日自动刷新，这里仅作参考。

---

## 🔌 数据来源

| 平台 | 覆盖 | 说明 |
|---|---|---|
| [最酷 zuicool](https://zuicool.com) | 841 场 | 主力来源，中国大陆赛事 |
| [Skyrunning / ISF](https://www.skyrunning.com/calendar/) | 136 场 | 国际天空跑联合会官方日历 |
| [UTMB World Series](https://live.utmb.world/zh-Hans/calendar) | 93 场 | 官方 API，含 2026 / 2027 两届、33 国 |
| [TORX®](https://www.torxtrail.com/) | 5 场 | 意大利奥斯塔谷系列（巨人之旅等）|

数据均来自各平台公开页面，仅供参考，**请以赛事官方公告为准**。

---

## 🤖 每日自动更新

无需人工维护，每天**北京时间 03:00** 自动跑一遍：

```
① 抓取   python crawlers/run_all.py     约 7 分钟
         ├─ 每天扫全部赛事列表，只对【新增】和【有变动】的抓详情页
         └─ 每 15 天做一次全量兜底
② 合并   python scripts/merge_all.py    去重 / 补组别 / 重算状态（更新前自动备份）
③ 渲染   node daily_update.js           刷新「今天」与页面
④ 发布   提交 → GitHub Pages 自动重新部署
```

想确认是否正常：**仓库 → Actions → Daily Update**（绿勾即正常）。
人工只需偶尔看一眼，或失败时手动 `Run workflow` 重跑一次。

---

## 🚀 本地预览

**无需安装任何依赖**，直接双击打开 `index.html` 即可
（数据通过 `<script src>` 加载，`file://` 下也能用）。

想改数据或跑爬虫，见下方[调试指南](#-调试指南)。

---

## 🍴 Fork 成你自己的日历

### 1. Fork 仓库
点右上角 **Fork**，得到 `你的用户名/Trail-Running-calendar`。

### 2. 开启自动更新（Actions）
- 进入 `你的仓库 → Actions`
- 若提示 *"Workflows aren't being run on this forked repository"*，点 **I understand my workflows, go ahead and enable them**
- 之后每天 UTC 19:00（北京 03:00）自动抓取并提交

### 3. 开启网页托管（Pages）
- `Settings → Pages`
- **Source** 选 `Deploy from a branch`
- **Branch** 选 `main` + `/ (root)` → Save
- 几分钟后访问 `https://你的用户名.github.io/Trail-Running-calendar/`

> 仓库自带 `.nojekyll` —— 否则 Pages 的 Jekyll 会忽略以 `_` 开头的 `_race_data.js`，页面一片空白。

### 4. 授权 Actions 提交（如遇权限报错）
`Settings → Actions → General → Workflow permissions` → 选 **Read and write permissions**。

### 5. 想只保留某个地区 / 类型？
- **只留某个省份**：在 `scripts/merge_all.py` 里加一道过滤，或改 `crawlers/zuicool.py` 的抓取范围
- **换年份**：全局搜 `2026` 改成目标年份
- **换配色**：改 `index.html` 顶部的 CSS 变量

---

## 🛠 调试指南

<details>
<summary><b>数据没更新？</b></summary>

1. 看 `你的仓库 → Actions → Daily Update` 最近一次是否成功
2. 常见失败原因：
   - 没开 Actions 写权限 → 见 [Fork 第 4 步](#4-授权-actions-提交如遇权限报错)
   - 目标站点限流 / 改版 → 看日志里各爬虫的输出
3. **手动触发**：`Actions → Daily Update → Run workflow`

</details>

<details>
<summary><b>本地跑整条链路</b></summary>

```bash
# 1) 抓取（增量：只抓新增/有变动的，约 1–2 分钟；全量含 Skyrunning 约 7 分钟）
python crawlers/run_all.py
#    或只跑主力爬虫、强制全量详情（800+ 页，15–40 分钟）
python crawlers/zuicool.py --full

# 2) 合并爬虫结果 → _race_data.js
python scripts/merge_all.py

# 3) 重算状态 + 刷新 index.html
node daily_update.js

# 4) 浏览器打开 index.html 预览
```

> **Windows 注意**：跑 Python 前先设 `PYTHONIOENCODING=utf-8`，否则控制台 GBK 编码会报错。

</details>

<details>
<summary><b>某平台抓不到数据？</b></summary>

- 看爬虫产出的 `crawl/output/{平台}.json` 里的 `count`
- 看合并报告 `crawl/REPORT_<日期>.md`
- 精确排查某一场赛事：

```bash
python -c "import sys; sys.path.insert(0,'crawlers'); import zuicool as z; \
print(z.parse_detail(z.fetch('https://zuicool.com/event/98816')))"
```

</details>

<details>
<summary><b>页面搜索 / 筛选没反应？</b></summary>

1. 浏览器按 `F12` 看 Console 有没有红色报错
2. 常见原因：`_race_data.js` 某条数据字段缺失（如 `city` 为空）导致脚本抛错
3. 校验数据文件：

```bash
node -e "require('./_race_data.js'); console.log('数据 OK')"
```

4. 校验页面脚本：`node daily_update.js`（末尾会打印 index.html JS 语法是否 OK）

</details>

---

## 🧱 技术栈

- **数据抓取**：Python 3 + requests + BeautifulSoup
- **数据存储**：单个 CommonJS 文件 `_race_data.js`（唯一数据源）
- **前端**：原生 HTML / CSS / JavaScript —— 零依赖、零构建
- **自动化**：GitHub Actions + GitHub Pages

> 想看**详细的项目结构与内部流程**，见 [`project/project.md`](./project/project.md)；
> 按日期的改动记录见 [`version/version.md`](./version/version.md)。

---

## 📄 许可与致谢

数据版权归各赛事主办方与发布平台所有，本项目仅做聚合展示。发现问题欢迎提 [Issue](https://github.com/Nikiwang92/Trail-Running-calendar/issues)。

如果这个小工具帮到了你，欢迎点个 ⭐
