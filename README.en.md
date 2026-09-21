<div align="center">

# 🏃‍♂️⛰️ Trail Running Calendar

A **daily auto-updating** calendar of trail running races — crawled from multiple platforms and aggregated into one searchable, filterable web page

[![Auto-update](https://img.shields.io/badge/auto--update-daily%2003%3A00%20CST-2ea44f?style=flat-square)](https://github.com/Nikiwang92/Trail-Running-calendar/actions)
[![Sources](https://img.shields.io/badge/sources-zuicool%20%7C%20UTMB%20%7C%20TORX%20%7C%20Skyrunning-1f6feb?style=flat-square)](#-data-sources)
[![Frontend](https://img.shields.io/badge/frontend-zero%20deps%20%7C%20zero%20build-orange?style=flat-square)](#-tech-stack)
[![Races](https://img.shields.io/badge/races-1100%2B-d02020?style=flat-square)](#-scale)

[**🌐 Live site**](https://nikiwang92.github.io/Trail-Running-calendar/) &nbsp;·&nbsp;
[**📖 Project docs**](./project/project.md) &nbsp;·&nbsp;
[**📝 Changelog**](./version/version.md) &nbsp;·&nbsp;
[**中文说明 →**](./README.md)

</div>

![Preview](docs/preview.png)

---

## ✨ Features

| | |
|---|---|
| 🔍 **Search** | Filter instantly by race name, location or category (try `100K`, `Beijing`) |
| 🏷️ **Tag filters** | UTMB / TORX / Skyrunning / Golden League / ITRA / Youth / Training / 100K+ — combinable |
| 📅 **Status · year · month · province** | Upcoming · **Ongoing** · Finished; 2026 / 2027; Jan–Dec; every province |
| 📊 **Race details** | Every official category with its **elevation gain**, **cut-off time**, registration deadline, WeChat account and official link |
| 📱 **Responsive** | Adapts to phone / tablet / desktop |

---

## 🌐 Live site

**<https://nikiwang92.github.io/Trail-Running-calendar/>**

> Page blank or 404? See the Pages setup in the [Fork guide](#-fork-your-own-calendar).

---

## 📈 Scale

| Metric | Value |
|---|---|
| Races | **1,124** (2026: 1,085 / 2027: 39) |
| Regions | 33 provinces & regions (6 in HK/Macau/Taiwan, 233 overseas) |
| Categories | 2,779 (1,449 with elevation gain, 876 with cut-off time) |

> Numbers refresh daily — shown here for reference only.

---

## 🔌 Data sources

| Platform | Races | Notes |
|---|---|---|
| [Zuicool](https://zuicool.com) | 841 | Primary source, mainland China |
| [Skyrunning / ISF](https://www.skyrunning.com/calendar/) | 136 | Official calendar of the International Skyrunning Federation |
| [UTMB World Series](https://live.utmb.world/zh-Hans/calendar) | 93 | Official API, both 2026 & 2027 editions, 33 countries |
| [TORX®](https://www.torxtrail.com/) | 5 | Aosta Valley series, Italy (Tor des Géants etc.) |

All data comes from public pages and is for reference only — **always check the official race announcement**.

---

## 🤖 Daily updates (automatic)

No maintenance needed — it runs every day at **03:00 Beijing time**:

```
① Crawl    python crawlers/run_all.py     ~7 min
           ├─ scans the full race list daily; only fetches detail pages for new/changed races
           └─ a full refresh runs every 15 days
② Merge    python scripts/merge_all.py    dedupe / fill categories / recalc status
                                          (auto-backup before every update)
③ Render   node daily_update.js           refresh "today" and the page
④ Publish  commit → GitHub Pages redeploys
```

To check it's healthy: **your repo → Actions → Daily Update** (a green check means all good).

---

## 🚀 Local preview

**No dependencies** — just double-click `index.html`
(data is loaded via `<script src>`, which works under `file://`).

To modify data or run the crawlers, see the [debugging guide](#-debugging-guide).

---

## 🍴 Fork your own calendar

### 1. Fork the repository
Click **Fork** at the top-right to get `your-username/Trail-Running-calendar`.

### 2. Enable auto-updates (Actions)
- Go to `your repo → Actions`
- If you see *"Workflows aren't being run on this forked repository"*, click **I understand my workflows, go ahead and enable them**
- It then crawls and commits daily at UTC 19:00 (Beijing 03:00)

### 3. Enable web hosting (Pages)
- `Settings → Pages`
- Set **Source** to `Deploy from a branch`
- Set **Branch** to `main` + `/ (root)` → Save
- In a few minutes visit `https://your-username.github.io/Trail-Running-calendar/`

> The repo ships with `.nojekyll` — without it, Pages' Jekyll would ignore `_race_data.js` (leading underscore) and the page would render blank.

### 4. Allow Actions to push (if you hit a permission error)
`Settings → Actions → General → Workflow permissions` → select **Read and write permissions**.

### 5. Want only one region / type?
- **One province only**: add a filter in `scripts/merge_all.py`, or narrow the scope in `crawlers/zuicool.py`
- **Change the year**: search for `2026` and replace with your target year
- **Change the colors**: edit the CSS variables at the top of `index.html`

---

## 🛠 Debugging guide

<details>
<summary><b>Data isn't updating?</b></summary>

1. Check whether the latest run in `your repo → Actions → Daily Update` succeeded
2. Common causes:
   - Actions write permission not enabled → see [Fork step 4](#4-allow-actions-to-push-if-you-hit-a-permission-error)
   - Target site rate-limiting or redesign → check the crawler output in the logs
3. **Trigger a run manually**: `Actions → Daily Update → Run workflow`

</details>

<details>
<summary><b>Run the whole pipeline locally</b></summary>

```bash
# 1) Crawl (incremental, ~1–2 min; full incl. Skyrunning ~7 min)
python crawlers/run_all.py
#    Or the primary crawler only, forcing a full detail refresh (800+ pages, 15–40 min)
python crawlers/zuicool.py --full

# 2) Merge crawl results → _race_data.js
python scripts/merge_all.py

# 3) Recalculate status + refresh index.html
node daily_update.js

# 4) Open index.html in a browser to preview
```

> **Windows:** set `PYTHONIOENCODING=utf-8` before running Python, or the console's GBK encoding raises errors.

</details>

<details>
<summary><b>A platform returns no data?</b></summary>

- Check the `count` in `crawl/output/{platform}.json`
- Check the merge report `crawl/REPORT_<date>.md`
- Inspect a single race:

```bash
python -c "import sys; sys.path.insert(0,'crawlers'); import zuicool as z; \
print(z.parse_detail(z.fetch('https://zuicool.com/event/98816')))"
```

</details>

<details>
<summary><b>Search / filters not responding?</b></summary>

1. Press `F12` and check the Console for red errors
2. Common cause: a race in `_race_data.js` is missing a field (e.g. empty `city`), which makes the script throw
3. Validate the data file:

```bash
node -e "require('./_race_data.js'); console.log('data OK')"
```

4. Validate the page script: `node daily_update.js` (prints whether index.html JS syntax is OK)

</details>

---

## 🧱 Tech stack

- **Scraping**: Python 3 + requests + BeautifulSoup
- **Storage**: a single CommonJS file, `_race_data.js` (single source of truth)
- **Frontend**: vanilla HTML / CSS / JavaScript — zero dependencies, zero build
- **Automation**: GitHub Actions + GitHub Pages

> For the **detailed project structure and internal flow**, see [`project/project.md`](./project/project.md);
> for the dated changelog, see [`version/version.md`](./version/version.md).

---

## 📄 License & credits

Data copyright belongs to the respective race organizers and platforms; this project only aggregates and displays it. Issues and PRs are [welcome](https://github.com/Nikiwang92/Trail-Running-calendar/issues).

If this tool helped you, a ⭐ is appreciated.
