"""P07 测量：400 首的播放列表，全屏播放页右侧打开“播放列表”。不放真实音频，只模拟“换到下一首”（改 PB.q.i 再 qPanelPaint）。
看：每次换歌的主线程耗时、样式重算 / 布局次数（CDP Performance 指标）、换歌后平滑滚动期间的掉帧（>25 ms 的帧）；
另外空闲 10 秒（列表开着、不操作）时 resizefx 定时测量带来的布局次数。
用法：python bench_p07.py（修复前的数字：在 17349db 上跑同一个脚本）"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SETUP = """(() => {
  const items = Array.from({ length: 400 }, (_, k) => ({ title: '测试曲目 ' + k, sub: '合成 · ' + (k % 7), src: '/x/' + k + '.wav', key: 'k' + k }));
  PB.q = { items, orig: items.slice(), i: 0 };
  npOpen ? npOpen() : null;
})()"""


def metrics(cdp):
    return {m['name']: m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("document.querySelectorAll('img, video').forEach(e => e.style.visibility = 'hidden')")
    pg.evaluate(SETUP); pg.wait_for_timeout(300)
    pg.evaluate("(() => { if ($('#np').hidden) npOpen(); NP.tab = 'queue'; npPaint(true); qPanelPaint(); })()"); pg.wait_for_timeout(1200)
    assert pg.evaluate("document.querySelectorAll('#np-right .ql-row').length") == 400, '列表没有画出来'
    cdp = pg.context.new_cdp_session(pg); cdp.send('Performance.enable')
    # 换歌 30 次，每次之间等平滑滚动结束；同时记帧间隔
    pg.evaluate("window.__gaps = []; (function f(t0) { requestAnimationFrame(t => { if (window.__gaps) { window.__gaps.push(t - t0); f(t); } }); })(performance.now())")
    m0 = metrics(cdp)
    ts = []
    for k in range(1, 31):
        ts.append(pg.evaluate("(k) => { const t = performance.now(); PB.q.i = k * 3; qPanelPaint(); document.body.offsetHeight; return performance.now() - t; }", k))
        pg.wait_for_timeout(750)
    m1 = metrics(cdp)
    gaps = pg.evaluate("(() => { const g = window.__gaps; window.__gaps = null; return g; })()")
    on = pg.evaluate("document.querySelector('#np-right .ql-row.on')?.dataset.k")
    vis = pg.evaluate("(() => { const r = document.querySelector('#np-right .ql-rows').getBoundingClientRect(), o = document.querySelector('#np-right .ql-row.on').getBoundingClientRect(); return o.top >= r.top && o.bottom <= r.bottom; })()")
    # 空闲 10 秒
    i0 = metrics(cdp); pg.wait_for_timeout(10000); i1 = metrics(cdp)
    ts.sort()
    print(f'当前代码：换歌 30 次  每次耗时 p50 {ts[15]:.1f} ms / p95 {ts[28]:.1f} ms / 最大 {ts[-1]:.1f} ms')
    print(f'  样式重算 {m1["RecalcStyleCount"] - m0["RecalcStyleCount"]:.0f} 次，布局 {m1["LayoutCount"] - m0["LayoutCount"]:.0f} 次，脚本 {1000 * (m1["ScriptDuration"] - m0["ScriptDuration"]):.0f} ms，主线程任务 {1000 * (m1["TaskDuration"] - m0["TaskDuration"]):.0f} ms')
    print(f'  帧 {len(gaps)} 个，>25 ms 的 {sum(g > 25 for g in gaps)} 个，最长 {max(gaps):.1f} ms；最后正在放第 {on} 首，在可见范围内 {vis}')
    print(f'  空闲 10 秒：样式重算 {i1["RecalcStyleCount"] - i0["RecalcStyleCount"]:.0f} 次，布局 {i1["LayoutCount"] - i0["LayoutCount"]:.0f} 次，主线程任务 {1000 * (i1["TaskDuration"] - i0["TaskDuration"]):.0f} ms')
    print('  页面报错', errs or '无')
    b.close()
