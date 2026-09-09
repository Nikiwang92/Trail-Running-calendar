# 2026 中国山地越野赛事日历

2026 年中国越野跑赛事清单，按月份/省份/标签筛选，支持搜索与"已结束/未开始"状态展示。

👉 **公开页面**：https://<your-username>.github.io/<repo-name>/

数据源：最酷、搜狐赛事日历、Ahotu、UTMB 官方、跑IN 中国等平台。

## 项目结构

```
├── index.html              # GitHub Pages 部署的主页面（Bauhaus 风格）
├── _race_data.js           # 权威赛事数据源（CommonJS module）
├── check_status.js         # 状态校验脚本（已结束/未开始）
├── scripts/
│   └── daily_update.js     # 每日自动跑：刷新 today 日期 + 重算 status + 同步 HTML
├── .github/workflows/
│   └── daily.yml           # 每天北京时间 00:00 跑一次 daily_update.js
├── preview/                # 其他设计风格版本（Industrial/Cyberpunk/Vaporwave 等）
├── prompt/                 # 各设计系统模板（prompt_*.txt）
├── 越野赛事爬虫.py 等        # Python 爬虫（手动运行）
└── CLAUDE.md               # 项目说明
```

## 每日自动更新

`.github/workflows/daily.yml` 配置 GitHub Actions：

- 触发时间：每天 **UTC 16:00**（北京时间 00:00）
- 任务流程：
  1. 跑 `scripts/daily_update.js`：
     - 取当天日期
     - 重算 `_race_data.js` 中所有赛事状态（`endDate||date < today` → `past`）
     - 同步刷新 `index.html`：`const today`、`const races = [...]`、页脚"更新时间"
     - 校验 HTML 内嵌脚本语法
  2. 自动 commit 并 push 到 main 分支
  3. GitHub Pages 自动重新部署

也可在 GitHub Actions 页面手动点 **Run workflow** 立即触发。

## 本地运行

```bash
# 校验赛事状态
node check_status.js

# 手动跑一次每日更新（用今天日期）
node scripts/daily_update.js

# 浏览器打开
start index.html   # Windows
open index.html    # macOS
```

## 发布到 GitHub Pages（一次性配置）

1. 在 GitHub 新建 public 仓库
2. 推送代码：
   ```bash
   git init
   git add .
   git commit -m "init: 2026 越野赛日历"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
3. 仓库 → **Settings** → **Pages**：
   - Source: **Deploy from a branch**
   - Branch: **main** / **/ (root)**
   - 保存
4. 等 1-2 分钟，访问 `https://<your-username>.github.io/<repo-name>/`

## 数据字段说明

每条赛事：

```js
{
  name: "赛事名称",
  date: "2026-09-15",          // 必填，开始日期
  endDate: "2026-09-17",       // 可选，多日赛事结束日期
  province: "省份",
  city: "城市·具体地点",
  distances: [
    { d: "100K", climb: "5500m", time: "30h" },  // 距离/爬升/关门时间，未知则省略
  ],
  tags: ["utmb" | "golden" | "itra"],   // 可组合
  status: "past" | "upcoming",          // 每日自动重算
  link: "https://...",                  // 报名链接
  wechat: "公众号名",                    // 可选
}
```

## 手动添加新赛事

1. 编辑 `_race_data.js`，在合适月份下加一条赛事（注意 `status` 默认 `"upcoming"`）
2. 跑 `node scripts/daily_update.js` 同步到 `index.html`
3. `git add -A && git commit -m "data: 添加 XXX 赛事" && git push`

新赛事推送到 main 后，GitHub Pages 会自动重新部署。
