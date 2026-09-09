# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

2026年中国越野赛赛事日历 (2026 China Trail Running Event Calendar)。核心是一个单页 HTML 赛事日历应用，支持按月份/省份/标签筛选、搜索、状态展示（已结束/未开始）。同一份赛事数据被渲染成多种视觉风格版本，每版对应一种设计系统模板。

## Data & File Architecture

**数据单一来源**：`_race_data.js`（CommonJS module）是所有赛事的权威数据源。每条赛事字段结构：

- `name`, `date`（必填 YYYY-MM-DD）, `endDate`（可选，多日赛事）
- `province`, `city`（location）
- `distances`: `[{d:"100K", climb:"4712m", time:"28h"}]`，climb/time 未知则省略
- `tags`: `["utmb"] | ["golden"] | ["itra"]`（可组合）
- `status`: `"past"`(已结束) 或 `"upcoming"`(未开始)
- `link`（报名链接）, `wechat`（公众号，可选）

**数据注入 HTML**：每个 preview HTML 内嵌 `const races = [...]` 数组（与 `_race_data.js` 内容相同但转为 JS 字面量）。`_merge.js` 负责从 `_race_data.js` 重新生成 HTML 中的 races 数组。

**状态判定**：`status` 字段与实际日期联动。`check_status.js` 以硬编码 `today` 日期（当前 `2026-08-19`）对比 `endDate || date` 计算应然状态，并报告与实际 `status` 字段不匹配的赛事。更新数据时需：改 `_race_data.js` 的 status → 重新生成 HTML → 若基准日期变更还要同步改 `check_status.js` 和 HTML 内 `const today`。

## Design System Templates (`prompt/`)

`prompt/prompt_*.txt` 是设计系统规范，各定义一种完整视觉风格（Bauhaus、Cyberpunk、Industrial、Neo-brutalism、Neumorphism、Playful Geometric、Sketch、Vaporwave）。每个文件包含 role 指令 + `<design-system>` 完整 token 体系（颜色、字体、阴影、圆角、组件样式、响应式、动效）。

**模板约定**：用户说"按某个 txt 模板生成新 html"时，仅替换界面风格（CSS/视觉），保持数据结构和功能完全不变。新文件命名 `2026_trail_races_<Style>.html`，输出到 `preview/` 目录。

## Helper Scripts（`_` 前缀）

- `_race_data.js` — 权威赛事数据源
- `_merge.js` — 从 `_race_data.js` 重新生成 HTML 内 races 数组
- `_update_links.js` — 按赛事名批量更新/插入报名链接
- `_add_itra.js` — 批量添加 ITRA 标签
- `check_status.js` — 校验并报告 status 字段与实际日期是否一致

运行方式：`node <script>.js`（Node.js，无依赖）。

## Crawlers（Python）

- `越野赛事爬虫.py` / `越野赛事爬虫_完善版.py` — 通用越野赛事爬虫
- `批量抓取2026越野赛.py` — 批量抓取
- `赛会通越野赛爬虫.py` — 赛会通平台专用
- `头条搜赛事.py` — 头条搜索赛事

数据抓取后用 `_merge.js` 等脚本回填到 HTML。

## Key Conventions

- **预览文件一律放 `preview/` 目录**，不散落到项目根目录或 Desktop。
- 修改赛事数据：先改 `_race_data.js`，再同步更新目标 HTML 内的内嵌数组；涉及状态重算时用 `check_status.js` 验证。
- 修改设计风格时，只动 CSS/视觉层，不改变数据结构和交互逻辑。
- 当前基准日期为 2026-09-01（用户指定今天日期），早于此日期的赛事应标记为 "past"。

## Working Directory Notes

- 主工作目录 `F:\RUN`，Windows 环境，bash shell。
- 助手脚本和历史 HTML 的绝对路径常硬编码指向 `C:/Users/admin/Desktop/...`，更新文件路径时需同步检查这些硬编码。
