"""AI 助手页：输入框始终在这一页最下面（2026-11-18 用户：退出迷你播放器 / 最大化后输入框没在底下，下面空一截）。
各窗口尺寸量输入框离底边多远；再模拟“算高度那一刻窗口还小”（innerHeight 临时假装成 640），恢复后输入框也要贴底；
换声页的结果区同一套算法，顺带看不出错。用法：python t_pg_fill.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)


MSG = """(() => { const m = document.querySelector('#pg-msgs'); m.innerHTML = '<div class="pg-u">哈喽</div><div class="pg-a"><div class="pg-txt">哈喽！有什么可以帮你的吗？</div></div>'; document.querySelector('.pg-card').classList.remove('is-empty'); })()"""
GAP = "(() => { const r = document.querySelector('.pg-in').getBoundingClientRect(), g = document.querySelector('.pg-grid').getBoundingClientRect(); return [Math.round(innerHeight - r.bottom), Math.round(innerHeight - g.bottom), document.documentElement.scrollHeight - innerHeight]; })()"
STALE = """(() => { const d = Object.getOwnPropertyDescriptor(window, 'innerHeight'); Object.defineProperty(window, 'innerHeight', { get: () => 640, configurable: true }); try { fitPages(); } finally { Object.defineProperty(window, 'innerHeight', d); } })()"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1600, 'height': 1000}, color_scheme='dark'); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('prompt')"); pg.wait_for_timeout(1500); pg.evaluate(MSG); pg.wait_for_timeout(300)
    for w, h in ((1280, 800), (1440, 900), (1600, 1000), (1920, 1080), (2560, 1440), (1100, 700)):
        pg.set_viewport_size({'width': w, 'height': h}); pg.wait_for_timeout(500)
        ib, gb, ov = pg.evaluate(GAP)
        check(f'{w}×{h}：输入框离底边 {ib}px、整页不滚（{ov}）', 0 <= ib <= 40 and ov <= 0, (ib, gb, ov))
    pg.set_viewport_size({'width': 1600, 'height': 1000}); pg.wait_for_timeout(400)
    pg.evaluate(STALE); pg.wait_for_timeout(300)
    ib, gb, ov = pg.evaluate(GAP)
    check(f'算高度时窗口还小（640）→ 恢复后输入框仍贴底（离底边 {ib}px）', 0 <= ib <= 40 and ov <= 0, (ib, gb, ov))
    # 窗口变大但这一刻不重算：高度也跟着变（不靠 resize 事件）
    pg.evaluate("window.__fp = fitPages; fitPages = () => {}"); pg.set_viewport_size({'width': 1600, 'height': 1200}); pg.wait_for_timeout(400)
    ib, gb, ov = pg.evaluate(GAP); pg.evaluate("fitPages = window.__fp")
    check(f'窗口变高、没重算也贴底（离底边 {ib}px）', 0 <= ib <= 40 and ov <= 0, (ib, gb, ov))
    pg.set_viewport_size({'width': 1600, 'height': 1000}); pg.wait_for_timeout(400)
    # 播放条收起 / 展开：这页播放条在左边导航栏里，输入框都贴底
    for v in ('false', 'true'):
        pg.evaluate(f"pbMin({v})"); pg.wait_for_timeout(600)
        ib, gb, ov = pg.evaluate(GAP); check(f'pbMin({v})：输入框离底边 {ib}px', 0 <= ib <= 40 and ov <= 0, (ib, gb, ov))
    # 矮窗口（≤820）正在播放：导航栏里的播放器变成圆钮旁边的小胶囊，对话区不该给它让位
    pg.evaluate("go('play')"); pg.wait_for_timeout(1200)
    pg.locator('#play-src button', has_text='很多文件').first.click(); pg.wait_for_timeout(1200)
    pg.locator('#play-list .pl-row[data-i]', has_text='片段 004').first.dblclick(); pg.wait_for_timeout(1200)
    pg.evaluate("pbMin(false); go('prompt')"); pg.wait_for_timeout(1200); pg.evaluate(MSG)
    for w, h in ((1000, 630), (900, 600), (1280, 800), (1600, 1000)):
        pg.set_viewport_size({'width': w, 'height': h}); pg.wait_for_timeout(600)
        ib, gb, ov = pg.evaluate(GAP)
        check(f'正在播放、{w}×{h}：输入框离底边 {ib}px', 0 <= ib <= 40 and ov <= 0, (ib, gb, ov))
    pg.evaluate("qAudio.pause()"); pg.set_viewport_size({'width': 1600, 'height': 1000}); pg.wait_for_timeout(400)
    # 空对话：输入框在中间（不是这次要改的），只看不报错、不出滚动条
    pg.evaluate("go('prompt')"); pg.wait_for_timeout(1200)
    ov = pg.evaluate("document.documentElement.scrollHeight - innerHeight"); check(f'空对话：整页不滚（{ov}）', ov <= 0)
    # 换声页结果区同一个函数
    pg.evaluate("go('vc')"); pg.wait_for_timeout(1500)
    vh = pg.evaluate("(() => { const e = document.querySelector('.vc-out'); return e ? [e.style.height, Math.round(e.getBoundingClientRect().height)] : null; })()")
    check(f'换声页结果区高度正常（{vh}）', vh is None or vh[1] >= 120, vh)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
