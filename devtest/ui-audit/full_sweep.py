"""全量巡检（2026-11-18，docs/全量检查方法论.md 第 2 节 C / E / F）：所有页面 × 多种窗口 × 浏览器 / 应用窗口（body.in-app）。
每次切页查：
  - 切换后第一帧（0 ms）和 40 / 120 ms：#main 里有没有灰色占位（.shimmer）或“加载中”（第二次进同一页时必须直接是内容）
  - 切页过程中导航栏（logo、当前导航按钮）一帧都不能动
  - 版式：横向溢出、导航栏和主内容重叠、主内容里的按钮互相压住、按钮被别的东西盖住、文字被截成竖排
  - 页面报错
截图（SFW：藏起图片 / 视频 / 背景图）到 shots_sweep/<尺寸>_<模式>_<页面>.png。用法：python full_sweep.py [--shots] [--sizes 1440x900,800x600]"""
import os, sys, json, time
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_sweep'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
SHOTS = '--shots' in sys.argv
SIZES = [(800, 600), (1000, 630), (1280, 800), (1440, 900), (1920, 1080), (2560, 1440)]
if '--sizes' in sys.argv:
    SIZES = [tuple(int(v) for v in s.split('x')) for s in sys.argv[sys.argv.index('--sizes') + 1].split(',')]
PAGES = ['play', 'img', 'video', 'mats', 'prompt', 'tts', 'vc', 'audioedit', 'batch', 'works', 'voices', 'stt', 'settings', 'help']
HIDE = "img:not([src*=brand]):not([src$=svg]),video,canvas{visibility:hidden!important} *,*::before,*::after{background-image:none!important} #mini{display:none!important}"
INAPP = ("window.pywebview = { api: new Proxy({}, { get: () => () => Promise.resolve(null) }) };"
         "document.addEventListener('DOMContentLoaded', () => document.body.classList.add('in-app'));")
SFW = "document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = %s; document.head.append(s); });" % json.dumps(HIDE)
fails, passes = [], 0

# 切页并逐帧记录：导航栏位置、有没有占位
SWITCH = r"""(page) => new Promise(res => {
  const out = [], t0 = performance.now(); let n = 0;
  const pos = () => { const L = document.querySelector('.rail .brand'), A = document.querySelector('.rnav .active, .rnav [aria-current="page"]');
    const r = e => e ? Math.round(e.getBoundingClientRect().top * 2) / 2 : null; return [r(L), r(A && (A.querySelector('.ic') || A))]; };
  const ph = () => { const m = document.getElementById('main'); if (!m) return 'nomain';
    const sh = [...m.querySelectorAll('.shimmer')].filter(e => e.offsetParent && e.getBoundingClientRect().height > 20).length;
    const txt = /正在读取|加载中…|读取中…/.test((m.innerText || '').slice(0, 400)) ? 1 : 0; return sh + txt; };
  go(page);
  const f = () => { out.push({ t: Math.round(performance.now() - t0), pos: pos(), ph: ph() }); if (++n < 45) requestAnimationFrame(f); else res(out); };
  f();
})"""

LAYOUT = r"""() => {
  const P = [], vw = innerWidth, vh = innerHeight, R = e => e.getBoundingClientRect();
  const vis = e => { if (!e || !e.isConnected || !e.checkVisibility?.({ checkOpacity: true, checkVisibilityCSS: true })) return false; const r = R(e); return r.width > 1 && r.height > 1; };
  const nm = e => (e.id ? '#' + e.id : e.tagName.toLowerCase()) + (e.classList[0] ? '.' + e.classList[0] : '') + ' "' + (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 12) + '"';
  if (document.documentElement.scrollWidth > vw + 1) P.push('横向溢出 ' + document.documentElement.scrollWidth);
  const rail = document.querySelector('.rail'), main = document.getElementById('main');
  if (rail && main && vis(rail)) { const a = R(rail), b = R(main); if (b.left < a.right - 1 && getComputedStyle(rail).position !== 'fixed') P.push('主内容压到导航栏'); }
  // 主内容里看得见的按钮：互相压住、被盖住、出屏
  // 滚动容器（缩略图条等）里滚到边外的那部分不算：只查完全在它的滚动容器里面的
  const inScroller = e => { const r = R(e); for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const cs = getComputedStyle(x); if (/(auto|scroll|hidden)/.test(cs.overflowX + cs.overflowY)) { const c = R(x); if (r.left < c.left - 1 || r.right > c.right + 1 || r.top < c.top - 1 || r.bottom > c.bottom + 1) return false; } } return true; };
  const btns = [...document.querySelectorAll('#main button, #main a[href], #main [role=button], #main input:not([type=hidden]), #main select')].filter(vis).filter(e => { const r = R(e); return r.bottom > 0 && r.top < vh; }).filter(inScroller).slice(0, 220);
  const pb = document.querySelector('.pbar'), pbTop = pb && vis(pb) ? R(pb).top : vh;
  for (const e of btns) { const r = R(e);
    if (r.right > vw + 1 || r.left < -1) P.push('出屏 ' + nm(e));
    const cy = r.top + Math.min(r.height / 2, 14), cx = r.left + Math.min(r.width / 2, 14);
    if (cy > 2 && cy < Math.min(vh, pbTop) - 2 && cx > 0 && cx < vw) { const h = document.elementFromPoint(cx, cy);
      if (h && h !== e && !e.contains(h) && !h.contains(e) && !h.closest('.tb, .tb-strip, .pbar, #pb-fab, .toast, .tip, [role=tooltip], .dd-menu, .ctx') && !(e.closest('label') && e.closest('label').contains(h))) P.push('被盖住 ' + nm(e) + ' ← ' + nm(h)); } }
  for (let i = 0; i < btns.length; i++) for (let j = i + 1; j < btns.length; j++) { const a = btns[i], b = btns[j]; if (a.contains(b) || b.contains(a)) continue;
    const x = R(a), y = R(b), ox = Math.min(x.right, y.right) - Math.max(x.left, y.left), oy = Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top);
    if (a.matches('.prompt-peek') || b.matches('.prompt-peek')) continue;  // 输入框里故意放的小图标
    if (ox > 4 && oy > 4 && ox * oy > 0.3 * Math.min(x.width * x.height, y.width * y.height)) P.push('互相压住 ' + nm(a) + ' / ' + nm(b)); }
  // 短文字被挤成竖排（每个字一行）
  for (const e of [...document.querySelectorAll('#main button, #main .seg button, #main h1, #main h2, #main h3, #main .card-title')].filter(vis).slice(0, 200)) { const t = (e.textContent || '').trim(); if (t.length >= 2 && t.length <= 8) { const r = R(e), lh = parseFloat(getComputedStyle(e).lineHeight) || 18; if (r.height > lh * 2.6 && r.width < lh * 1.8) P.push('竖排 ' + nm(e)); } }
  return [...new Set(P)].slice(0, 12);
}"""


def check(name, ok, info=''):
    global passes
    if ok: passes += 1
    else: fails.append(f'{name} {info}'.strip())


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
        for (w, h) in SIZES:
            for mode in ('web', 'app'):
                ctx = b.new_context(viewport={'width': w, 'height': h}); ctx.add_init_script(SFW)
                if mode == 'app': ctx.add_init_script(INAPP)
                pg = ctx.new_page(); errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
                pg.goto(B + '/play'); pg.wait_for_timeout(2200)
                for pgname in PAGES:  # 先每页进一次（第一次进可以有占位）
                    pg.evaluate(f"go('{pgname}')"); pg.wait_for_timeout(700)
                pg.evaluate("go('play')"); pg.wait_for_timeout(1200)
                prev = 'play'
                for pgname in PAGES[1:] + ['play']:
                    tag = f'{w}x{h} {mode} {prev}→{pgname}'
                    frames = pg.evaluate(SWITCH, pgname)
                    navs = {tuple(f['pos']) for f in frames}
                    check(tag + ' 导航栏不动', len(navs) == 1, str(sorted(navs))[:120])
                    early = [f for f in frames if f['t'] <= 130 and f['ph']]
                    check(tag + ' 第一帧不是占位', not early, str(early[:3]))
                    pg.wait_for_timeout(900)
                    probs = pg.evaluate(LAYOUT)
                    check(tag + ' 版式', not probs, '；'.join(probs))
                    if SHOTS and mode == 'web' or (SHOTS and mode == 'app' and w in (1440, 1000)):
                        pg.screenshot(path=os.path.join(OUT, f'{w}x{h}_{mode}_{pgname}.png'))
                    prev = pgname
                check(f'{w}x{h} {mode} 页面报错', not errs, '；'.join(errs[:4]))
                ctx.close()
        b.close()


run()
for f in fails: print('✗', f)
print(f'通过 {passes}，失败 {len(fails)}')
