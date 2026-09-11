# crawlers/run_all.py
# 编排器：顺序跑 6 个爬虫，timeout 控制，失败标记不阻塞
import sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawlers'))

CRAWLERS = [
    ('zuicool', 'zuicool'),        # 主力：覆盖 800+ 场
    ('utmb', 'utmb'),              # 次级：utmb.world 中国子站
]
# 停用：
#   saihuitong     —— 扫 102 个运营方域名但产出 0 场（站点结构变化，与 zuicool 高度重叠）
#   runninginchina —— 赛事全部与 zuicool 重复（赞助商前缀导致名称不一致），且无组别数据
#   ahotu          —— 返回 0（Cloudflare 拦截）
#   ihuipao        —— 列表为 JS 渲染，静态 HTML 无赛事链接

results = []


def run_one(name, module_name):
    print(f'\n=== [{name}] 开始 ===')
    t0 = time.time()
    try:
        mod = __import__(module_name)
        mod.main()
        dt = time.time() - t0
        out_path = ROOT / 'crawl' / 'output' / f'{name}.json'
        count = 0
        if out_path.exists():
            import json
            count = json.loads(out_path.read_text(encoding='utf-8')).get('count', 0)
        results.append((name, 'ok', count, dt))
        print(f'=== [{name}] OK ({count} 场, {dt:.1f}s) ===')
    except Exception as e:
        dt = time.time() - t0
        traceback.print_exc()
        results.append((name, 'fail', 0, dt))
        print(f'=== [{name}] FAIL ({dt:.1f}s): {e} ===')


def main():
    print('=== 编排器启动 ===')
    for name, module in CRAWLERS:
        run_one(name, module)
    print('\n=== 汇总 ===')
    for name, status, count, dt in results:
        print(f'  [{status:4s}] {name}: {count} 场, {dt:.1f}s')


if __name__ == '__main__':
    main()