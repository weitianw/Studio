"""侧栏跟着手指走（2026-11-16）：模拟 iPhone 16 Pro Max，用一串 touchstart / touchmove / touchend 拖侧栏，
量拖到一半时侧栏、页面、输入框是不是都跟着手指，松手后按位置 + 速度开或关，关上后页面回到原位。截图在 shots_iphone/drag。
用法：python ip_drag.py [--light]"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'drag'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
LIGHT = '--light' in sys.argv
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


# 手指：从 x0 拖到 x1，steps 步，每步 ms 毫秒；hold = 停在最后不松手（量中间状态）
FINGER = r"""async ([x0, x1, y, steps, ms, hold]) => {
  const tgt = document.elementFromPoint(x0, y) || document.body;
  const ev = (n, x) => { const t = { identifier: 7, target: tgt, clientX: x, clientY: y, pageX: x, pageY: y + scrollY };
    const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); tgt.dispatchEvent(e); return e; };
  ev('touchstart', x0); let prevented = false;
  for (let i = 1; i <= steps; i++) { const e = ev('touchmove', x0 + (x1 - x0) * i / steps); prevented = prevented || e.defaultPrevented; await new Promise(r => setTimeout(r, ms)); }
  window.__finger = () => ev('touchend', x1);
  if (!hold) ev('touchend', x1);
  return prevented; }"""
VERT = """async ([x, y0, y1]) => { const tgt = document.elementFromPoint(x, y0);
  const ev = (n, y) => { const t = { identifier: 8, target: tgt, clientX: x, clientY: y }; const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); tgt.dispatchEvent(e); };
  ev('touchstart', y0); for (let i = 1; i <= 10; i++) { ev('touchmove', y0 + (y1 - y0) * i / 10); await new Promise(r => setTimeout(r, 16)); } ev('touchend', y1); }"""
STATE = r"""() => { const page = document.getElementById('main').dataset.page, d = page === 'prompt' ? document.getElementById('pg-hist') : document.getElementById('ph-dw');
  const r = e => e ? Math.round(e.getBoundingClientRect().left) : null, comp = document.querySelector('#main .ig-top-f, #main .pg-composer'), head = [...document.querySelectorAll('#main > .page-head')].find(h => h.offsetWidth);
  const fr = document.querySelector('.ph-dw-frame'), sc = document.querySelector('.ph-dw-scrim');
  return { page, open: document.body.classList.contains(page === 'prompt' ? 'pg-hist-open' : 'ph-dw-open'), dw: d ? Math.round(d.getBoundingClientRect().right - (parseFloat((d.style.clipPath.match(/inset\(0(?:px)? ([\d.]+)px/) || [0, 0])[1]) || 0)) : null, dwW: d ? d.offsetWidth : 0,
    comp: r(comp), head: r(head), frame: fr && getComputedStyle(fr).display !== 'none' ? r(fr) : null, radius: fr ? fr.style.borderRadius : '', scrim: sc ? +getComputedStyle(sc).opacity : null,
    sy: Math.round(scrollY), left: [...document.querySelectorAll('[style*="translate"]')].filter(e => !e.closest('#ph-dw, #pg-hist') && e.style.translate).length }; }"""


def st(pg):
    return pg.evaluate(STATE)


def settle(pg, ms=650):
    pg.wait_for_timeout(ms)


def run(pg, page):
    tag = page
    pg.evaluate(f"go({page!r})"); pg.wait_for_timeout(1600); hide(pg)
    if page == 'img':
        pg.evaluate("scrollTo(0, 400)"); pg.wait_for_timeout(500)
    s0 = st(pg); y = 420
    # 1 慢慢拖到一半停住：侧栏右边 = 手指的位置；页面、输入框、标题栏跟着往右
    half = s0['dwW'] * .5
    prev = pg.evaluate(FINGER, [6, 6 + half, y, 14, 18, True]); pg.wait_for_timeout(120); s1 = st(pg)
    check(f'{tag}：拖动时不让页面跟着滚 / 不触发点击', prev, prev)
    check(f'{tag}：拖到一半，侧栏右边跟着手指（±3px）', s1['dw'] is not None and abs(s1['dw'] - half) <= 3, (s1['dw'], half))
    if s0['comp'] is not None:
        check(f'{tag}：输入框跟着一起往右', abs((s1['comp'] - s0['comp']) - half) <= 3, (s0['comp'], s1['comp']))
    if s0['head'] is not None:
        check(f'{tag}：标题栏跟着一起往右', abs((s1['head'] - s0['head']) - half) <= 3, (s0['head'], s1['head']))
    check(f'{tag}：页面变成圆角卡片、变暗一点', s1['frame'] is not None and abs(s1['frame'] - half) <= 3 and s1['radius'] not in ('', '0px') and 0.3 < s1['scrim'] < 0.7, s1)
    check(f'{tag}：拖动时页面没有上下跳', s1['sy'] == s0['sy'], (s0['sy'], s1['sy']))
    if page not in ('prompt', 'settings'):  # 设置不在页面列表里（在侧栏最下面的“设置”）
        on = pg.evaluate("document.querySelector('#ph-dw .ph-dw-nav a.on')?.dataset.phGo")
        check(f'{tag}：拖开时侧栏高亮的是当前页', on == page, on)
    pg.screenshot(path=os.path.join(OUT, f'{page}_half{"_l" if LIGHT else ""}.png'))
    # 停在一半慢慢松手（停了一会儿，速度 ≈ 0）→ 刚好一半算没过半：关上
    pg.wait_for_timeout(200); pg.evaluate("window.__finger()"); settle(pg); s2 = st(pg)
    check(f'{tag}：停在一半松手 → 收回去，页面回到原位、没有残留位移', not s2['open'] and s2['comp'] == s0['comp'] and s2['head'] == s0['head'] and s2['frame'] is None and s2['left'] == 0, s2)
    # 2 慢慢拖过 60% 松手 → 打开
    pg.evaluate(FINGER, [6, 6 + s0['dwW'] * .65, y, 16, 20, False]); settle(pg); s3 = st(pg)
    check(f'{tag}：拖过一半松手 → 打开到底', s3['open'] and abs(s3['dw'] - s0['dwW']) <= 2, s3)
    pg.screenshot(path=os.path.join(OUT, f'{page}_open{"_l" if LIGHT else ""}.png'))
    sb = pg.evaluate("(() => { const e = document.getElementById('sb-strip'); if (!e || getComputedStyle(e).display === 'none') return null; const r = e.getBoundingClientRect(), d = document.querySelector('#ph-dw, #pg-hist'); return { l: Math.round(r.left), w: Math.round(r.width), z: +getComputedStyle(e).zIndex, dz: Math.max(+getComputedStyle(document.getElementById('ph-dw')).zIndex || 0, +(document.getElementById('pg-hist') && getComputedStyle(document.getElementById('pg-hist')).zIndex) || 0), tr: e.style.translate || '' }; })()")
    check(f'{tag}：开着时状态栏那条实色条不动、整宽、盖在侧栏上面（iOS 26 不糊顶部）', sb is None or (sb['l'] == 0 and sb['w'] >= pg.viewport_size['width'] - 1 and sb['z'] > sb['dz'] and not sb['tr']), sb)
    # 3 开着时往左拖一点点、停住 → 侧栏跟着往左
    pg.evaluate(FINGER, [s0['dwW'] - 20, s0['dwW'] - 120, y, 10, 18, True]); pg.wait_for_timeout(100); s4 = st(pg)
    check(f'{tag}：开着往左拖，侧栏跟着手指往回收', abs(s4['dw'] - (s0['dwW'] - 100)) <= 4, (s4['dw'], s0['dwW'] - 100))
    pg.wait_for_timeout(200); pg.evaluate("window.__finger()"); settle(pg); s5 = st(pg)
    check(f'{tag}：只收了一点就松手 → 弹回打开', s5['open'] and abs(s5['dw'] - s0['dwW']) <= 2, s5)
    # 4 往左快速一甩（只拖了 25%）→ 关上
    pg.evaluate(FINGER, [s0['dwW'] - 10, s0['dwW'] * .75 - 10, y, 4, 12, False]); settle(pg); s6 = st(pg)
    check(f'{tag}：往左快甩一下 → 关上', not s6['open'] and s6['left'] == 0 and s6['comp'] == s0['comp'], s6)
    # 5 从边缘往右快甩（只拖了 25%）→ 打开
    pg.evaluate(FINGER, [6, 6 + s0['dwW'] * .25, y, 4, 12, False]); settle(pg); s7 = st(pg)
    check(f'{tag}：从边缘往右快甩一下 → 打开', s7['open'], s7)
    # 6 点 ≡ / 点外面：也是滑出来的（中途量一下，侧栏在半路）
    pg.evaluate("document.body.classList.remove('ph-dw-open', 'pg-hist-open')"); settle(pg)
    btn = '#pg-hist-m' if page == 'prompt' else '#main .ph-menu-b'
    b = pg.query_selector(btn).bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(110); s8 = st(pg)
    check(f'{tag}：点 ≡ 侧栏是滑出来的（中途在半路）', 20 < s8['dw'] < s0['dwW'] - 10, s8)
    settle(pg); s9 = st(pg)
    check(f'{tag}：点 ≡ 打开到底', s9['open'] and abs(s9['dw'] - s0['dwW']) <= 2, s9)
    pg.touchscreen.tap(pg.viewport_size['width'] - 20, 500); settle(pg); s10 = st(pg)
    check(f'{tag}：点右边露出来的页面 → 关上、回原位', not s10['open'] and s10['left'] == 0 and s10['comp'] == s0['comp'], s10)
    # 7 从边缘竖着滑：不开侧栏
    pg.evaluate(VERT, [10, 600, 300]); settle(pg, 400)
    check(f'{tag}：从边缘竖着滑不开侧栏', not st(pg)['open'])
    # 8 不在边缘往右滑：不开（选项胶囊那排要能左右滑）
    pg.evaluate(FINGER, [120, 300, y, 10, 16, False]); settle(pg, 400)
    check(f'{tag}：不在左边缘往右滑不开侧栏', not st(pg)['open'])


if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH, dark=not LIGHT)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true")
        for page in ['img', 'video', 'play', 'mats', 'prompt', 'tts', 'settings']:
            run(pg, page)
        # 侧栏里点页面：先收侧栏、再换页，换完没有残留位移
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        pg.evaluate(FINGER, [6, 300, 420, 12, 16, False]); settle(pg)
        pg.evaluate("document.querySelector('#ph-dw [data-ph-go=video]').click()"); pg.wait_for_timeout(1800)
        s = st(pg); check('侧栏里点生视频：换过去、侧栏收好、没有残留位移', s['page'] == 'video' and not s['open'] and s['left'] == 0 and s['frame'] is None, s)
        t = pg.evaluate("(() => { const t0 = performance.now(); for (let i = 0; i < 5; i++) window.__phCollect?.(); return (performance.now() - t0) / 5; })()")
        print('  找要移动的层平均用时 ms：', t)
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
