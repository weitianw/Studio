"""页面能不能上下滑（2026-11-16，用户：图集 / 素材库 / 生视频页滑不动了）。模拟 iPhone 16 Pro Max：
量 html / body 的 overflow、手指下面是什么、手指下面一串祖先的 touch-action / overflow，和 window 能不能滚。
用法：python ip_scroll.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
PROBE = r"""() => { const x = innerWidth / 2, y = innerHeight / 2, e = document.elementFromPoint(x, y), chain = [];
  for (let n = e; n && n !== document.documentElement; n = n.parentElement) { const c = getComputedStyle(n);
    if (c.touchAction !== 'auto' || /auto|scroll|hidden/.test(c.overflowY) || c.position === 'fixed') chain.push(`${n.tagName.toLowerCase()}${n.id ? '#' + n.id : ''}.${String(n.className).split(' ').slice(0, 2).join('.')} ta=${c.touchAction} oy=${c.overflowY} pos=${c.position} sh=${n.scrollHeight} ch=${n.clientHeight}`); }
  const h = getComputedStyle(document.documentElement), b = getComputedStyle(document.body);
  const before = scrollY; scrollTo(0, before + 300); const after = scrollY; scrollTo(0, before);
  return { at: e ? e.tagName + '.' + e.className : null, html: h.overflow + ' ' + h.touchAction, body: b.overflow + ' ' + b.touchAction + ' pos=' + b.position, docH: document.documentElement.scrollHeight, ih: innerHeight, canScroll: after - before, chain,
    cls: document.documentElement.className + ' | ' + document.body.className }; }"""


FAIL = []
# 素材库：和电脑一样整页锁住，只有图片区（.gal-body）滚动，筛选栏一直在上面（11-16 用户）
MATS = r"""() => { const b = document.querySelector('#main .gal-body'), t = document.querySelector('#main .gal-t1'); if (!b || !t) return null;
  const y0 = t.getBoundingClientRect().top, s0 = scrollY; scrollTo(0, 400); const win = scrollY - s0; scrollTo(0, s0);
  const st0 = b.scrollTop; b.scrollTop = st0 + 300; const inner = b.scrollTop - st0, y1 = t.getBoundingClientRect().top; b.scrollTop = st0;
  const r = b.getBoundingClientRect();
  return { win, inner, bar: Math.round(y1 - y0), sh: b.scrollHeight, ch: b.clientHeight, bottom: Math.round(r.bottom), ih: innerHeight, pb: getComputedStyle(b).paddingBottom }; }"""


def mats(pg, name):
    r = pg.evaluate(MATS); print('  ', name, r)
    if not r or r['win'] != 0 or (r['sh'] > r['ch'] + 20 and r['inner'] <= 0) or r['bar'] != 0 or r['bottom'] > r['ih'] + 1:
        FAIL.append(name + '（素材库：整页锁住、图片区能滚、筛选栏不动、图片区不超出屏幕）')


def show(pg, name):
    r = pg.evaluate(PROBE); (FAIL.append(name) if r['docH'] > r['ih'] + 20 and r['canScroll'] <= 0 and '素材库' not in name else None); print('==', name); [print('  ', k, v) for k, v in r.items() if k != 'chain']; [print('     ', c) for c in r['chain']]


if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("S.muted = true")
        pg.evaluate("go('video')"); pg.wait_for_timeout(1800); hide(pg); show(pg, '生视频')
        pg.evaluate("go('mats')"); pg.wait_for_timeout(1800); hide(pg); show(pg, '素材库'); mats(pg, '素材库')
        pg.evaluate("[...document.querySelectorAll('.gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("[...document.querySelectorAll('.gal-body .gal-fd')].find(f => f.textContent.includes('测试文件夹'))?.click()"); pg.wait_for_timeout(2000); show(pg, '素材库-文件夹里面'); mats(pg, '素材库-文件夹里面')
        # 开关一次侧栏以后
        b = pg.query_selector('#main .ph-menu-b').bounding_box(); pg.touchscreen.tap(b['x'] + 20, b['y'] + 20); pg.wait_for_timeout(700)
        pg.touchscreen.tap(pg.viewport_size['width'] - 20, 500); pg.wait_for_timeout(700); show(pg, '素材库（开关过一次侧栏）')
        pg.evaluate("go('prompt')"); pg.wait_for_timeout(1500); pg.evaluate("go('video')"); pg.wait_for_timeout(1800); hide(pg); show(pg, '生视频（从 AI 助手过来）')
        pg.evaluate("go('mats')"); pg.wait_for_timeout(1500); pg.evaluate("go('video')"); pg.wait_for_timeout(1800); hide(pg); show(pg, '生视频（从素材库过来）')
        br.close()
    print('滑不动的：', FAIL or '没有')
