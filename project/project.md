# 项目结构与流程 — 中国越野赛事日历

本文件是这个项目的**详细上手文档**（结构 / 流程 / 改动约定），给 Claude Code 和人类协作者共用。改动项目结构/流程时，请同步更新本文件。简介与用法见 [`README.md`](../README.md)。

---

## 一、项目目标

每天自动抓取**全量**中国越野赛事（含 2027+）→ 存到唯一数据源 `_race_data.js` → 渲染成 `index.html`（Bauhaus 风格）→ 部署到 GitHub Pages。

**三条铁律**：
1. **全量**：每天重抓所有能抓的平台，不做人工筛选。
2. **不硬编码**：赛事数据只来自爬虫，绝不手写进代码。
3. **单一数据源**：所有赛事只在 `_race_data.js` 存一份，HTML 不含数据。

---

## 二、总览与数据流

```
[触发] GitHub Actions cron '0 16 * * *'(UTC=北京00:00)  或手动 Run workflow
   │
   ▼
① 抓取  python crawlers/run_all.py
   ├── zuicool.py     主力（增量：每天全量抓列表，只对变化的抓详情）
   └── utmb.py        次级（utmb.world 中国子站）
   各爬虫只写 crawl/output/{platform}.json
   │
   ▼
② 合并  python scripts/merge_all.py     ← 唯一写 _race_data.js 的地方
   更新前先备份 → backup/race_data/(本地7份) + data_backup/(入库3份)
   去重 / 修正归属 / 补组别 / 新增 / 重算 status / 标 cancelled / 排序 / 清洗
   → 写 _race_data.js → node 校验语法（失败回滚）
   │
   ▼
③ 渲染  node daily_update.js
   重算 past/upcoming（保留 cancelled）+ 改 index.html 的 const today / 页脚
   index.html 通过 <script src> 读 _race_data.js（shim 模式，HTML 不含数据）
   │
   ▼
④ 提交  git add -A && commit && push → GitHub Pages
```

**三层严格分离，职责边界（务必遵守）**：
- 爬虫**只**产出 JSON，**禁止**直接改 `_race_data.js`。
- `merge_all.py` 和 `daily_update.js` 是**仅有的两个**写 `_race_data.js` 的地方。
- `index.html` 不写数据，只做 UI。

**前端筛选栏**（`index.html`，行间叠加=与）：
```
搜索框（名称/省/市/组别，输入即筛 + 回车）
[状态行]  全部 / 未开始 / 已结束                              单选
[标签行]  全部 / UTMB / 黄金联赛 / ITRA / 青少年 / 训练赛 / 100K+   多选
[年份行]  全部 / 2026 / 2027…                                单选
[月份行]  全部 / 1–12月                                      单选
[省份行]  全部省份 / 各省（港澳台/海外 排最后）                  单选
```

**当前规模**：851 场（2026:848 / 2027:3）· 海外 2 · 港澳台 3 · 重复 0。

---

## 三、目录结构

```
F:\RUN\
├── _race_data.js              # ★ 唯一权威数据源（CommonJS module.exports=[...]）
├── index.html                 # ★ 展示页（Bauhaus，shim 模式读数据）
├── daily_update.js            # ★ 重算 status + 同步 HTML
├── crawlers/
│   ├── run_all.py             # 编排器：顺序跑启用爬虫
│   ├── zuicool.py             # 主力爬虫
│   ├── saihuitong.py          # 赛会通运营方子站（已停用）
│   ├── utmb.py                # utmb.world 子站
│   ├── ahotu.py / ihuipao.py / runninginchina.py  # 已停用（见「已知限制」）
│   └── _lib/                  # 公共工具
│       ├── http.py            # Session + 每 host 限速 1 QPS + retry + UA 池
│       ├── parse.py           # normalize_name / 中文日期归一 / 距离正则
│       ├── province.py        # 省-市-县 映射（split_province_city）
│       ├── tags.py            # tags 推断（infer_tags / tags_from_page）
│       └── wechat.py          # 公众号抽取
├── scripts/
│   ├── merge_all.py           # ★ 合并层（核心，~720 行）
│   ├── fix_tags.py            # 一次性：重算历史条目的 tags
│   └── dedup_by_link.py       # 历史一次性脚本
├── crawl/
│   ├── output/*.json          # 每日爬虫产物（gitignore）
│   ├── state.json             # 增量抓取状态：{last_full, races:{id:{fp,fetched}}}（**要提交**）
│   ├── MISSING_LOG.json       # "连续未抓到"计数（14 天 → cancelled）
│   └── REPORT_YYYYMMDD.md     # 每日合并报告
├── data_backup/               # ★ 每日 _race_data.js 备份，随 git 提交，保留 3 份
├── backup/race_data/          # 本地滚动备份（时间戳命名，保留 7，.gitignore 忽略）
├── domains.json               # saihuitong 爬虫的域名清单（103 个运营方）
├── requirements.txt           # requests / bs4 / pandas / lxml / openpyxl
├── template/index_Bauhaus.html # 设计模板（备用，不参与构建）
├── prompt/*.txt               # 各设计风格提示词（gitignore）
└── .github/workflows/daily.yml # 每日自动化
```

---

## 四、数据模型（`_race_data.js` 每条）

```javascript
{ name:"2026京东大境门古长城越野赛byUTMB®",
  date:"2026-09-11",              // YYYY-MM-DD
  endDate:"2026-09-13",           // 可选，多日赛
  province:"河北",
  city:"河北省张家口市桥西区大境门景区",
  distances:[ {d:"100K", climb:"3959m", time:"25h"}, ... ],  // 官方组别，降序
  tags:["utmb"],                  // ∈ {utmb,golden,itra,youth,training}
  status:"past"|"upcoming"|"cancelled",
  link:"https://zuicool.com/event/98816",   // 可选
  wechat:"大境门古长城越野赛",               // 可选
  official:"dajingmen.utmb.world" }          // 可选，官网域名（跨平台去重键）
```

文件格式：`module.exports = [\n  { ... },\n  { ... }\n];`，每条**一行**，2 空格缩进。

**当前规模**（会变，仅供参照）：851 场，组别 2224 个（带爬升 1227 / 带关门 813），31 省（含港澳台/海外）。

---

## 五、采集层

### 编排器 `crawlers/run_all.py`
顺序跑（不并行，避免互踩），逐个 `import` 并调 `main()`，失败不阻塞。
```python
CRAWLERS = [('zuicool','zuicool'), ('utmb','utmb')]
```

### 主力爬虫 `crawlers/zuicool.py`（增量抓取）

每天**全量抓列表页**（~0.4 MB / 10 秒，很便宜），但**只对"有变化"的赛事抓详情页**。

**① 列表页** `list_page(page, where='')` — `https://zuicool.com/events?type=trail-run[&where=X]&page=N`
- 每页 100 条，解析 `div.event-body` 卡片 → `{id, url, name, date, city, raw}`
- `raw` = 卡片完整文本，用作**变更指纹**（含副标题如"改档九月，新增70KM组"、报名截止、报名状态）
- 地区：`REGIONS = [('', 大陆), ('hkgmac', 港澳台), ('overseas', 海外)]`
  - 同一赛事可能同时出现在多个列表 → 按 id 去重，**港澳台/海外优先于大陆**（修正归类）
  - 海外赛事的 province 统一置为 `海外`

**② 列表收集** `_list_all(session, where, ...)` — 翻页收敛
- 匹配 `date >= MIN_DATE`（`MIN_YEAR='2026'`，即**含 2027/2028…**）
- **连续 2 页无 >= 目标年份的赛事即停**

**③ 增量决策**（核心，见 `crawl()`）
```
state 里没见过该 id（新赛事）且尚未开赛  → 抓详情
state 里见过、但列表指纹变了            → 抓详情
到全量周期(FULL_REFRESH_DAYS=15)且尚未开赛 → 抓详情（兜底"详情页独有变化"）
其余 / 已开赛结束                       → 跳过
```
- 已开赛/结束的赛事（`date < today`）**永不重抓**（现 851 场里 past 629 场，占 7 成，直接砍掉）
- 跳过的条目**沿用上一次 `zuicool.json` 的详情字段**（`_load_prev_output()`），保证输出是**完整快照**——否则 `official`/`wechat`/`distances` 会丢，导致合并层去重与 missing 判定失效
- 状态存 `crawl/state.json`：`{last_full, races:{id:{fp, fetched}}}`
- `--full` 参数可强制全量

**④ 详情页** `parse_detail(html)` — 优先解析结构化块 `div.event-desc_lead`：
```
定于2026年9月11日-13日在河北…开赛，设DGW100、CGW70…   ← 首行：日期范围+地点
DGW100：实际距离100km，累计爬升3959米，总关门时长25小时   ← 每组一行
```
- `_parse_lead_block()`：逐行按第一个冒号拆，`_dist_from_label()` 取**官方距离**
  （`DGW100`→100，`八荒六合168K`→168，`100公里组`→100），抽累计爬升/关门时长
- 日期范围、地点也从首行抽；其余字段有兜底
- **注意**：绝不全文扫 `km`（曾把"实际距离162.09km""200组名额"当组别）
- **tags**：`tags_from_page(html, name)` — **先删掉侧栏 `.events-list` + nav/header/footer**再扫关键词，否则会误采"相关赛事"里别的赛事名
- **港澳台**：卡片地点写"中国香港 …"，但详情页常写成大陆报名点 → 优先用**卡片地点**定省市（`crawl()` 里判断 `card_city.startswith('香港'/'澳门'/'台湾')`）

**⑤ 输出**：`crawl/output/zuicool.json`，**覆盖列表里见到的全部赛事**（未抓详情的用卡片+上次数据占位）

> 效果：首次全量 ~815 请求 / 14–20 min；之后每天增量 ~12 列表 + 5–60 详情 ≈ 1–2 min。


### 次级爬虫
- **`utmb.py`**：从 `_race_data.js` 抽已知 `*.utmb.world` 子域名（+内置 5 个），抓 Next.js RSC payload；用 `build_alias_map()` 把英文名换成中文名。

### 停用平台（已评估，别再加回来）
| 平台 | 原因 |
|---|---|
| `saihuitong` | 扫 102 个运营方域名但产出 **0 场**（站点结构变化，与 zuicool 高度重叠，纯耗时）|
| `runninginchina` | 赛事 100% 与 zuicool 重复（赞助商前缀致名称不一致），且无组别数据 |
| `ahotu` | Cloudflare 拦截，返回 0 字节 |
| `ihuipao` | 列表为 JS 渲染，静态 HTML 无赛事链接 |

---

## 六、合并层 `scripts/merge_all.py`（核心）

`main()` 按序执行（顺序有依赖，别乱调）：

| # | 步骤 | 函数 | 作用 |
|---|---|---|---|
| -1 | **备份** | `backup_data` | 更新前把 `_race_data.js` 复制到 `backup/race_data/`（本地，保留 7）+ `data_backup/`（入库，保留 3）|
| 0 | 跨平台去重 | `drop_claimed_duplicates` | `official` 域名"认领"（来自 zuicool 输出 **∪ 现有 `_race_data`**）后，独立的 utmb 英文条目删除 |
| 1 | 重算 status | `auto_recalc_status` | 只改 status 字段 |
| 1.2 | 修正港澳台归属 | `sync_region_province` | 已有条目若被识别为港澳台（爬虫 province 为港澳台、现有不是）→ 改 province/city |
| 1.5 | 补全组别 | `merge_existing_distances` | 用官方组别覆盖脏数据；**只有 zuicool 平台允许覆盖**，其余平台仅在空时补 |
| 2 | 检测取消 | `detect_missing` + `mark_cancelled` | 连续 **14 天**所有平台没抓到 → `status:"cancelled"`（不删条目），进度存 `crawl/MISSING_LOG.json`。**按"天"累加**（同日多次运行算 1 天）；**已过去的赛事**和**非 zuicool 来源**的赛事不参与统计 |
| 3 | 新增赛事 | `detect_new` + `insert_new_races` | 追加到 `];` 之前；`serialize_new()` 序列化 |
| 3.5 | 最终去重 | `dedupe_final` | 见下 |
| 3.6 | 组别降序 | `sort_all_distances` | 100K→50K→30K… |
| 3.7 | 清洗 city | `sanitize_cities` | 去 `\n关注` / `地点` 前缀 |
| 4 | 写+校验 | `node -e require()` | 语法错就回滚 |
| 5 | 报告 | 写 `crawl/REPORT_*.md` | |

**去重的四道防线**（缺一不可）：
1. `link_key`：zuicool 域名统一取 event id（`reg.zuicool.com/123` == `zuicool.com/event/123`）
2. 同 `name_norm + date`
3. **同日 + 同省 + 名称相似度 ≥0.85 或一方包含另一方**（`_names_similar`，处理赞助商前缀/标点差异）
4. `official` 域名 ↔ utmb 子站 hostname

**配置常量**：
```python
ENABLED_PLATFORMS = {'zuicool', 'utmb'}   # 只合并这些
PLATFORM_PRIORITY = ['zuicool', 'utmb']   # 冲突时的优先级
CANCEL_THRESHOLD_DAYS = 14
```

**⚠️ 解析 `_race_data.js` 时**：字符串字段必须用 `((?:[^"\\]|\\.)*)` + `json.loads`
（名称可能含转义引号 `\"`，用 `[^"]+` 会解析错，历史上导致过误标 cancelled）。

---

## 七、展示层 `daily_update.js`

```
1. 取当天 today
2. require('_race_data.js')
3. 重算 status：endDate||date < today ? 'past' : 'upcoming'
   ⚠️ status==='cancelled' 的条目【跳过】，由 merge 负责，别覆盖
4. serializeRace() 规范化写回 _race_data.js
5. 改 index.html：const today（5a）、races 数组（5b shim 模式跳过）、页脚更新时间（5c）
6. new Function() 校验 HTML 内嵌脚本语法
```

**shim 模式**（关键架构）：`index.html` 不内嵌数据，而是
```html
<script>var module = {exports:{}};</script>
<script src="./_race_data.js"></script>
<script>const races = module.exports;</script>
```
好处：HTML 从 750KB 降到 ~37KB，数据只存一份；`file://` 下可用（不受 CORS 限制）。
`daily_update.js` 的 5b 检测到 `const races = module` 就跳过数组替换。

---

## 八、前端 `index.html`

- 纯 UI，无构建步骤，直接打开即可
- 筛选栏：
  - 搜索框（名称/省/市/组别，输入即筛 + 回车确认）
  - **状态行**：全部 / 未开始 / 已结束 —— **单选**
  - **标签行**：全部 / UTMB / 黄金联赛 / ITRA / 青少年 / 训练赛 / 100K+ —— **多选**
  - **年份行**：全部 / 2026 / 2027… —— 单选（从数据动态生成）
  - **月份行**：全部 / 1–12月 —— 单选
  - **省份行**：全部省份 / 各省 —— 单选，大陆按赛事数降序，**港澳台/海外排最后**
  - 规则：每行都有「全部」；**行内**状态单选、标签多选；**行间**叠加（与）
- `getStatusFromRace()` 前端也判一次状态，并优先返回 `cancelled`
- 卡片按月份分组，组别降序展示

---

## 九、每日日常流程（无人值守）

### 触发
```
cron '0 16 * * *' (UTC) = 北京 00:00 自动   或   Actions 页手动 Run workflow
```

### 时间线
```
北京 00:00
   ├─ ① 抓取 run_all.py        ~1.5 分钟
   ├─ ② 合并 merge_all.py        ~5 秒
   ├─ ③ 渲染 daily_update.js     ~2 秒
   └─ ④ git commit + push
   ▼
GitHub Pages 重新部署 → 用户看到最新日历
```

### 每天固定发生的事

| 环节 | 做什么 | 频率/条件 |
|---|---|---|
| **抓列表** | zuicool 大陆 12 页 + 港澳台 1 页 + 海外 1 页（~0.5 MB / 15 秒）| 每天全量 |
| **抓详情** | 只抓**新赛事**和**列表指纹变了**的 | 每天，通常 5–60 场 |
| **兜底全量** | 未开赛赛事的详情全抓一遍 | **每 15 天**（`FULL_REFRESH_DAYS`，防详情页独有变化）|
| **备份** | `_race_data.js` 复制一份 | 每次合并前（本地 7 / 仓库 3）|
| **合并** | 去重 / 修正归属 / 补组别 / 新增 / 排序 / 清洗 | 每天 |
| **状态重算** | `endDate < today → past`，否则 `upcoming`（`cancelled` 不动）| 每天 |
| **取消检测** | 连续 14 天没抓到的 zuicool 赛事 → `cancelled` | 累计制，按天 |
| **发布** | 提交 + 推送 → GitHub Pages | 每天 |

> 关键：**每天不必全量抓详情**。列表是"新赛事/变化"的唯一来源（很便宜），详情只为"有变化"的抓。

### `.github/workflows/daily.yml` 步骤
```
Checkout → Node20 → Python3.11 → pip install -r requirements.txt
→ python crawlers/run_all.py    (continue-on-error)
→ python scripts/merge_all.py   (continue-on-error)
→ node daily_update.js
→ git add -A && commit && push
→ 提示网页地址（把 Pages URL 写进 Actions 的 notice + Job Summary，方便知道去哪看）
```
`continue-on-error` 保证单平台失败不阻塞整条流水线；`timeout-minutes: 90`；`concurrency: daily-update` 防并发互踩。

### 每天不需要人工做的事
- 不用手动触发 / 不用手填数据 / 不用手动改日期（`const today` 自动）

### 人工只需偶尔确认（可选）
1. 看 Actions 是否绿：`仓库 → Actions → Daily Update`
2. 看合并报告 `crawl/REPORT_YYYYMMDD.md`（新增几场 / 有无 cancelled）
3. 失败时重跑一次 `Run workflow` 即可

### 出问题时回滚
```bash
cp data_backup/_race_data_YYYYMMDD.js _race_data.js          # 仓库备份（近 3 天）
cp backup/race_data/_race_data_<时间戳>.js _race_data.js      # 本地备份（近 7 次）
```

### 频率分层一览
```
每天    ：列表全量 + 变化详情 + 合并 + 发布    ≈ 1.5 分钟
每 15 天：额外一次"未开赛赛事"详情全量         ≈ 3–4 分钟
每 14 天：cancelled 判定复查
```

---

## 十、常用命令

```bash
# 抓取（增量：只抓新赛事/列表有变化的，约 1–2 分钟）
python crawlers/zuicool.py

# 强制全量详情（约 15–40 分钟，zuicool 800+ 详情页）
python crawlers/zuicool.py --full

# 跑全部爬虫
python crawlers/run_all.py

# 合并爬虫产物 → _race_data.js
python scripts/merge_all.py

# 重算 status + 刷新 index.html
node daily_update.js

# 本地预览
# 直接用浏览器打开 index.html（无需起服务）

# 从备份回滚（merge_all 每次更新前会自动备份）
cp data_backup/_race_data_20260911.js _race_data.js          # 仓库备份（14 天内）
cp backup/race_data/_race_data_20260911_100226.js _race_data.js   # 本地细粒度备份（7 份内）
```
> 增量状态存在 `crawl/state.json`。想重来一次全量：删掉它再跑即可。
> 备份策略：`backup/race_data/`（本地，保留 7，不入库）+ `data_backup/`（入库，保留 3）。

**Windows 本地注意**：设 `PYTHONIOENCODING=utf-8`（控制台默认 GBK 会报编码错）。

---

## 十一、关键约定（改代码前必读）

1. **不要硬编码赛事数据**。任何赛事信息都应来自爬虫，绝不手写进 `_race_data.js` 或 HTML。
2. **改结构先改本文件**。新增/删除爬虫、改变数据模型、调整流程，同步更新本文件（`project/project.md`）。
3. **tags 只从"赛事自身内容"推断**（名称 + 详情页自身区块），绝不扫整页——侧栏有别的赛事。
4. **组别只取官方整数 K**（`100K/70K`），丢弃小数实际距离（`102.85km`）。
5. **距离排序统一降序**；status 只有 `past/upcoming/cancelled` 三个值。
6. **改 `_race_data.js` 前先想清楚谁在写**——只有 `merge_all.py` 和 `daily_update.js` 可以写。
7. 提交前跑一遍 `merge_all.py` + `daily_update.js`，确认两者都无报错、`node -e require()` 通过。

---

## 十二、已知限制与坑

- **`MISSING_LOG` 必须按"天"累加**：曾按"每次运行"累加，一天内反复跑 merge 把 days 刷到 14 → 36 场被误标 `cancelled`（靠 `data_backup/` 一键回滚救回）。改 `detect_missing` 时务必保留 `last_missing != today` 的判断。
- **missing 统计只覆盖"未过去 + zuicool 来源"的赛事**：① 已结束的赛事会从 zuicool 列表自然下架，统计它们会导致 14 天后被误标 cancelled；② 非 zuicool 来源（官网/tsaigu/ninghai100 等）永远不会出现在 zuicool 列表里，统计它们会被永久误判为 missing。
- **每次更新前会自动备份**：`backup/race_data/`（本地 7 份）+ `data_backup/`（入库 3 份）；出问题直接 `cp` 回滚。
- **`_race_data.js` 是唯一数据源**：历史备份 `_race_data_v1.js` 已删除；现在以线上数据为准增量更新。当前 851 场。
- **增量抓取依赖 `crawl/state.json`**：它必须随仓库提交，否则 CI 每次都会当成"首次"全量抓。若 state 丢失，删掉它重跑一次全量即可。
- **增量跳过的条目必须沿用上次详情字段**（`_load_prev_output()`）：否则 `official` 丢失 → 合并层判不出"已认领官方站点" → utmb 英文重复会重新冒出来（踩过）。
- **港澳台赛事**：zuicool 的**大陆列表里本来就有**（如香港100、香港狂野），但详情页地点常写成大陆报名点，导致 `province` 被误判。修正靠：① 卡片地点"中国香港…"优先；② `split_province_city` 仅当**以**港澳台开头才算（避免"炮台湾"误判）。
- **海外赛事**已接入（`REGIONS` 含 `('overseas','海外')`）：zuicool 海外越野赛 2026/2027 各仅 1 场，量少。
- **zui 详情页无 `ETag`/`Last-Modified`**（且 `Cache-Control: no-store`），无法用 HTTP 304 做增量，只能靠"列表指纹 + 定期全量"。
- **12 条无组别**：多为"拟定…敬请期待"的未定档赛事，页面本身没组别，后续抓取会自动补。
- **saihuitong 已停用**：扫 102 个运营方域名产出 0 场，从 `run_all.py` 移除。`domains.json` 保留备用。
- **MISSING_LOG 的 key 是 `normalize_name` 结果**：曾出现含转义引号的赛事名被解析成 `\` 等脏 key，已清理，但改解析逻辑时需回归验证。
- **`crawl/output/` 是 gitignore**：CI 每次重新生成；本地调试时注意别把旧 JSON 当新数据。
- **首次全量抓取较慢**（zuicool 800+ 详情页，1 QPS 限速 + 站点限流），CI 里 `continue-on-error` 保证单平台失败不阻塞。
