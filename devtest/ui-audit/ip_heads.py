"""每个页面的标题栏长什么样（2026-11-16，准备把手机标题栏改成 Claude 那种居中的窄条）：模拟 iPhone 16 Pro Max，
打印每页 #main > .page-head 里直接的子元素（标签、class、大小、文字），以及能横着滚动的格子区。用法：python ip_heads.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
DUMP = r"""() => { const h = document.querySelector('#main > .page-head'); if (!h) return null;
  const d = (e, lv) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); if (s.display === 'none' || !r.width) return null;
    const o = { t: e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).join('.') : ''), r: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] };
    const txt = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim(); if (txt) o.x = txt.slice(0, 20);
    if (lv < 3 && e.children.length && !e.matches('svg, .seg, .gal-root')) o.c = [...e.children].map(c => d(c, lv + 1)).filter(Boolean); return o; };
  const hs = getComputedStyle(h);
  return { head: [Math.round(h.getBoundingClientRect().height), hs.position, hs.top], kids: [...h.children].map(c => d(c, 0)).filter(Boolean) }; }"""
HSCROLL = r"""() => [...document.querySelectorAll('#main *')].filter(e => { const s = getComputedStyle(e); return /auto|scroll/.test(s.overflowX) && e.scrollWidth > e.clientWidth + 1 && e.clientHeight > 150; }).map(e => e.className + ' ' + e.scrollWidth + '>' + e.clientWidth + ' ta=' + getComputedStyle(e).touchAction)"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("S.muted = true")
        for page in ['play', 'img', 'video', 'mats', 'prompt', 'tts', 'vc', 'audioedit', 'batch', 'works', 'voices', 'stt', 'settings']:
            pg.evaluate(f"go({page!r})"); pg.wait_for_timeout(1700); hide(pg)
            if page == 'mats':
                pg.evaluate("[...document.querySelectorAll('#main .gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1200)
                pg.evaluate("[...document.querySelectorAll('#main .gal-body .gal-fd')].find(f => f.textContent.includes('测试文件夹'))?.click()"); pg.wait_for_timeout(1500)
            print('=====', page, json.dumps(pg.evaluate(DUMP), ensure_ascii=False))
            print('   横着能滚的大块：', pg.evaluate(HSCROLL))
        br.close()
