# 版本记录

按**日期倒序**，每次**重大改动**记一条（新增/停用数据源、改数据模型或流程、UI 功能、批量数据修复等）。**单纯的文件位置调整不计入。** 改流程/结构时同步更新 [`project/project.md`](../project/project.md) 与根目录 `CLAUDE.md`（两份逐字一致）。

---

## 2026-09-20

- **状态判定改为「赛程区间包含今天即进行中」**：以前单日赛在比赛当天仍显示「未开始」。现在统一按区间 `[date, endDate]` 判：包含今天 → 进行中；完全在未来 → 未开始；完全在过去 → 已结束。
- **修复「今天」整体晚一天**：GitHub Actions runner 默认 UTC 时区，cron `0 19 * * *` 在北京次日 03:00 触发时，UTC 还停在前一天——脚本用 `new Date()` / `datetime.now()` 取本地日期，就把「今天」记成了昨天。后果：`const today` 落后一天、赛事 `status` 全线偏移（9 月 19 日的赛事在 20 日仍显示「未开始」）。
  - 修法：`.github/workflows/daily.yml` 的 job env 加 `TZ: Asia/Shanghai`；提交信息也从 `date -u` 改为本地 `date +%F`。
  - 一次性纠正：本次本地重跑 merge，**27 场** `status` 从 upcoming/hold 修正为 past。

## 2026-09-18

- **跨天赛事显示「进行中」**：以前只看结束日，导致 9/11–9/19 这种正在跑的赛事显示「未开始」。现在 `getStatusFromRace()` 增加 `open` 状态——**有 `endDate` 的赛事**，已开赛（`date <= today`）且未结束（`endDate >= today`）→ 显示「进行中」（**绿色**徽章，样式早就有，一直没接上）。状态筛选行相应加了「进行中」按钮（否则这类赛事在两个筛选项里都看不到）。
- 单日赛不受影响：当天仍显示「未开始」。（**此规则已于 09-20 调整**，见上）

## 2026-09-17

- 建立本文件（`version/version.md`），回溯记录 09-11 以来的改动。
- 定下记录规则：**只记重大改动**；单纯的文件位置调整不计入。
- 更新 Claude 记忆：记录项目当前范围（已从中国扩展到全球）与文档约定；修正一条过时的「预览文件放 `preview/`」记忆（该目录已废弃，README 预览图在 `docs/preview.png`）。

## 2026-09-16

- **接入三个国际数据源**，数据 1014 → **1100 场**：
  - `crawlers/torx.py` 意大利 TORX® 系列（torxtrail.com，og:meta 解析）5 场
  - `crawlers/skyrunning.py` ISF 天空跑（skyrunning.com）136 场；**中国境内场次跳过**（中英异名靠名称/日期判不出来，跳过是唯一可靠的防重复手段，数据不丢——最酷网已有）
  - `crawlers/utmb.py` 重写为官方 API（`utmblive-api.utmb.world`），5 → 95 场（含 2027 届、33 国）
- **跨平台去重**（国际源必须与最酷网合并、不得重复）：
  - `link` 去重**保持不带日期**——最酷的 link 是具体赛事实例，改期必须算同一条
  - `utmb:<slug>` 判定**带日期**，且 UTMB 的 link 加 `?year=`：同一子域是年无关的系列官网，2026/2027 两届要各留一条
  - UTMB 全球站的中国/港澳台场次：同日已有「… by UTMB」条目则跳过（最酷条目常缺 `official` 域名，认领机制兜不住，如「大蜀道100」）
  - 模糊去重**只在跨来源生效**：同源同日同场地的相似名多是不同组别（Skyrunning 的 Mourne SkyUltra / Mourne SkyTrail 曾被误合）
  - `_names_similar`：规范化后**完全相同**也算相似（修「云丘山」历史重复）
  - `host_of` 剥离 `?query`；`drop_claimed_duplicates` 加「自我认领」保护
- 其他修复：`parse_races_text` 从未解析 `tags` 字段（导致同步标签时会把 `itra` 覆盖掉）；`insert_new_races` 无条件补逗号会产生 **JS 数组空洞**（`Array.join` 把空洞当空串保留，永不"自愈"）；前端 `getStatusFromRace` 忽略 `endDate`，进行中的多日赛显示「已结束」。
- UI：标签行加 TORX / Skyrunning + 卡片徽章；页脚加 **GitHub 仓库链接**（内联 SVG 图标）；平台列表补 TORX / Skyrunning；重截 `docs/preview.png`。

## 2026-09-15

- **修正 29 场赛事的省份/城市错配**（如「九寨沟神境之旅」标成浙江、「青海同德」标成浙江建德）。根因：`province/city` 只在新增时写入、`merge` 之后从不更新，历史错值永久留存；叠加增量抓取沿用旧缓存。
  - `crawlers/zuicool.py`：列表卡片的省份与详情/缓存冲突时**以卡片为准**
  - `scripts/merge_all.py`：新增 `sync_city_province` 每日自愈步骤
  - 新增 `scripts/audit_location.py`：比对 `_race_data.js` 与最酷网列表卡片的 province
- 手机端：修复**搜索框被撑到 320px 高**（`flex: 0 1 320px` 在 `flex-direction: column` 下变成了高度）；整体字号缩小到 `87.5%`。
- 页面标题去掉「— Bauhaus」。

## 2026-09-14

- 品牌去掉「中国 / China」→ 更名「越野赛事日历 / Trail Running Calendar」（保留平台专有名词：跑IN中国、UTMB 世界系列赛中国站）。
- `hero` 表头缩短（padding 70/50 → 28/20，h1 2.4 → 1.9rem，统计块整体缩小）。
- 筛选折叠按钮移到搜索框右侧、搜索框收窄、恢复省份横向滚动条。

## 2026-09-13

- 每日自动更新（当日无人工改动）。

## 2026-09-11

- 显示「报名截止」时间——信息本来就在列表卡片上（"报名截止：02-28 23:59"），**无需进详情页**。
- 压缩置顶筛选栏（6 行标签按钮整体变小、行距更紧）。
- 修复 GitHub Pages 页面空白：加 `.nojekyll`——Pages 默认用 Jekyll，会忽略以 `_` 开头的 `_race_data.js`。
- CI：每日任务结束时输出网页地址（Actions notice + Job Summary）；cron 改为北京时间 03:00；全量日日志醒目化；修复增量模式重复抓取 60 场/天的问题。
