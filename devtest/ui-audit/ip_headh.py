"""标题栏高度从哪来（2026-11-16 标题栏改成一行后）：打印 page-head 的位置、内外边距、每个子元素。用法：python ip_headh.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
JS = r"""() => { const h = document.querySelector('#main > .page-head'), s = getComputedStyle(h), r = h.getBoundingClientRect(), m = h.querySelector('.ph-menu-b')?.getBoundingClientRect();
  return { top: Math.round(r.top), bottom: Math.round(r.bottom), pt: s.paddingTop, pb: s.paddingBottom, mt: s.marginTop, mb: s.marginBottom, minH: s.minHeight, rows: s.gridTemplateRows, menu: m && [Math.round(m.top), Math.round(m.bottom)],
    kids: [...h.children].map(c => c.className + ':' + getComputedStyle(c).display + ':' + Math.round(c.getBoundingClientRect().height)) }; }"""
if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        for page in ['img', 'works']:
            pg.evaluate(f"go({page!r})"); pg.wait_for_timeout(1800)
            print(page, pg.evaluate(JS))
            pg.evaluate("scrollTo(0, 700)"); pg.wait_for_timeout(700); print('  滚动后', pg.evaluate(JS))
        br.close()
