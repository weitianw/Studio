"""键盘弹起时输入框贴着键盘（2026-11-16，用户截图：AI 助手页输入框停在屏幕上半截）。模拟 iPhone 16 Pro Max，
模拟两种 iOS 行为：A 只有可视区域变矮（窗口不变，可能还往上卷了一点）；B 整个窗口一起变矮。另外先存一个记错的键盘高度。
量输入框底边是不是在键盘上沿上面 8px 左右。用法：python ip_kb.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'kb'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0
KB = 400


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


TA = {'img': '#main .ig-top-f textarea', 'video': '#main .ig-top-f textarea', 'prompt': '#main .pg-composer textarea'}
BOX = "(() => { const t = document.activeElement; const b = t && (t.closest('.ig-top-f') || t.closest('.pg-in') || t.closest('.pg-composer')); return b ? Math.round(b.getBoundingClientRect().bottom) : null; })()"
FAKE = r"""([h, top]) => { const vv = visualViewport; Object.defineProperty(vv, 'height', { get: () => h, configurable: true }); Object.defineProperty(vv, 'offsetTop', { get: () => top, configurable: true }); vv.dispatchEvent(new Event('resize')); }"""
UNFAKE = "(() => { const vv = visualViewport; delete vv.height; delete vv.offsetTop; document.activeElement?.blur?.(); vv.dispatchEvent(new Event('resize')); })()"


def focus(pg, page):
    b = pg.query_selector(TA[page]).bounding_box(); pg.touchscreen.tap(b['x'] + 30, b['y'] + b['height'] / 2); pg.wait_for_timeout(250)
    return pg.evaluate("document.activeElement?.tagName")


if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)) if 'ResizeObserver loop' not in str(e) else None)  # 改窗口大小时浏览器的提示，不算错（旧版也有）
        vw, vh = pg.viewport_size['width'], pg.viewport_size['height']
        for page in ['prompt', 'img', 'video']:
            for bad_kb in (None, 700, 900):
                tag = page + (f'（记错的键盘高度 {bad_kb}）' if bad_kb else '')
                pg.evaluate(f"go({page!r})"); pg.wait_for_timeout(1500); hide(pg)
                pg.evaluate(f"localStorage.setItem('phKb', {bad_kb})" if bad_kb else "localStorage.removeItem('phKb')")
                # A：窗口不变，可视区域变矮
                check(f'{tag}：点一下输入框就聚焦', focus(pg, page) == 'TEXTAREA')
                pg.evaluate(FAKE, [vh - KB, 0]); pg.wait_for_timeout(400); y = pg.evaluate(BOX)
                check(f'{tag} A：输入框贴着键盘（底边 ≈ 可视区域底 − 8）', y is not None and abs(y - (vh - KB - 8)) <= 3, (y, vh - KB - 8))
                pg.screenshot(path=os.path.join(OUT, f'{page}_A{"_bad" if bad_kb else ""}.png'))
                # A'：iOS 又把可视区域往上卷了 90
                pg.evaluate(FAKE, [vh - KB, 90]); pg.wait_for_timeout(400); y = pg.evaluate(BOX)
                check(f'{tag} A（往上卷了 90）：还是贴着键盘', y is not None and abs(y - (90 + vh - KB - 8)) <= 3, (y, 90 + vh - KB - 8))
                # 用键盘上的“⌄”收起：键盘没了，输入框还聚焦着（第三方输入法常这样）→ 输入框回到底部
                pg.evaluate("(() => { const vv = visualViewport; delete vv.height; delete vv.offsetTop; vv.dispatchEvent(new Event('resize')); })()"); pg.wait_for_timeout(500)
                y = pg.evaluate("Math.round(document.querySelector('%s').closest('.ig-top-f, .pg-in, .pg-composer').getBoundingClientRect().bottom)" % TA[page])
                check(f'{tag} A：用“⌄”收起键盘（没失去焦点）→ 输入框回到底部', y > vh - 140 and not pg.evaluate("document.documentElement.classList.contains('ph-kb')"), (y, vh))
                pg.evaluate(UNFAKE); pg.wait_for_timeout(500)
                # B：整个窗口一起变矮（键盘外面才是窗口）
                check(f'{tag} B：点一下输入框就聚焦', focus(pg, page) == 'TEXTAREA')
                pg.set_viewport_size({'width': vw, 'height': vh - KB}); pg.wait_for_timeout(700); y = pg.evaluate(BOX)
                check(f'{tag} B：输入框贴着键盘（底边 ≈ 窗口底 − 8）', y is not None and abs(y - (vh - KB - 8)) <= 3, (y, vh - KB - 8))
                pg.screenshot(path=os.path.join(OUT, f'{page}_B{"_bad" if bad_kb else ""}.png'))
                pg.set_viewport_size({'width': vw, 'height': vh}); pg.wait_for_timeout(700)  # 先不失去焦点：像“⌄”收起
                y = pg.evaluate("Math.round(document.querySelector('%s').closest('.ig-top-f, .pg-in, .pg-composer').getBoundingClientRect().bottom)" % TA[page])
                check(f'{tag} B：用“⌄”收起键盘（没失去焦点）→ 输入框回到底部', y > vh - 140, (y, vh))
                pg.evaluate("document.activeElement?.blur?.()"); pg.wait_for_timeout(300)
                y = pg.evaluate("Math.round(document.querySelector('%s').closest('.ig-top-f, .pg-in, .pg-composer').getBoundingClientRect().bottom)" % TA[page])
                check(f'{tag}：键盘收起后输入框回到底部', y > vh - 140, (y, vh))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
