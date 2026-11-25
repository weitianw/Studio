"""播放页（2026-11-16 用户：搜索框下面有一层东西；滑动时手指按住的那个文件会高亮；很多文件的文件夹滑到下面有时会退回最上面；要一键回到正在播的文件）。
模拟 iPhone 16 Pro Max，进测试数据里“很多文件”的文件夹，打印：标题栏 / 搜索框下面那一带是什么、列表行的 class 和按下样式、滚动容器。
用法：python ip_play.py [--shot]"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'play'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
PROBE = r"""() => { const h = document.querySelector('#main > .page-head'), hr = h.getBoundingClientRect(), s = document.querySelector('.play-search'), sr = s.getBoundingClientRect();
  const y = Math.round(sr.bottom + 6), at = document.elementsFromPoint(innerWidth / 2, y).slice(0, 6).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ').slice(0, 2).join('.') + ' bg=' + getComputedStyle(e).backgroundColor);
  const sc = [...document.querySelectorAll('#main *')].filter(e => /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 4).map(e => e.className + ' ' + e.scrollHeight + '/' + e.clientHeight);
  const row = document.querySelector('#play-list > *, .pl-list > *, #main .pl-row');
  return { head: [Math.round(hr.top), Math.round(hr.bottom)], search: [Math.round(sr.top), Math.round(sr.bottom)], under: at, scrollers: sc, docH: document.scrollingElement.scrollHeight, row: row && (row.tagName + '.' + row.className + ' :: ' + row.outerHTML.slice(0, 300)) }; }"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("S.muted = true")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1800); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(2000); hide(pg)
        pg.evaluate("scrollTo(0, 300)"); pg.wait_for_timeout(600)
        print(json.dumps(pg.evaluate(PROBE), ensure_ascii=False, indent=1))
        pg.screenshot(path=os.path.join(OUT, 'scrolled.png'))
        br.close()
