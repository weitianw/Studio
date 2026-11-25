"""模拟 iPhone 上点开几个弹层截图（审界面用）：模型选择、增强、更多、图片详情、设置"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots_iphone')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'


def shot(pg, n):
    hide(pg); pg.wait_for_timeout(400); pg.screenshot(path=os.path.join(OUT, n + '.png')); print(n)


def tapsel(pg, sel):
    el = pg.query_selector(sel)
    if not el:
        print('没有', sel); return False
    b = el.bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(900); return True


with sync_playwright() as p:
    br, pg = open_iphone(p, PH)
    pg.evaluate("go('img')"); pg.wait_for_timeout(1800)
    if tapsel(pg, '#ig-model'): shot(pg, 'f_model')
    pg.keyboard.press('Escape'); pg.evaluate("document.querySelector('.igm-v[data-m=\"q21\"]')?.click()"); pg.wait_for_timeout(800); pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    ch = pg.query_selector_all('.ig-chips > .ig-chip')
    for c in ch:
        if '增强' in (c.text_content() or ''):
            b = c.bounding_box(); pg.touchscreen.tap(b['x'] + 10, b['y'] + 10); pg.wait_for_timeout(800); shot(pg, 'f_enh'); break
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    if tapsel(pg, '.ig-gal-card .vd-card, .ig-gal-card [data-i]'): shot(pg, 'f_view')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    pg.evaluate("go('img')"); pg.wait_for_timeout(1200)
    tabs = pg.query_selector_all('.sidebar button, .sidebar a, nav.tabbar button')
    if tabs:
        b = tabs[-1].bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(1000); shot(pg, 'f_more')
    pg.evaluate("go('settings')"); pg.wait_for_timeout(1500); shot(pg, 'f_settings')
    br.close()
