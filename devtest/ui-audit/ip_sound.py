"""手机端“音效与声道”（主音轨 + 叠加音轨）（2026-11-17 用户：手机端的音轨有问题）。打开全屏播放 → 中间的音效按钮 → 截图；
再点“叠加音轨”进选择页截图；量有没有超出屏幕、点不到的。用法：python ip_sound.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'sound'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
OVER = """(() => { const W = innerWidth, out = []; document.querySelectorAll('body *').forEach(e => { if (!e.offsetParent && getComputedStyle(e).position !== 'fixed') return; const r = e.getBoundingClientRect();
  if (r.width && r.height && (r.right > W + 1 || r.left < -1) && getComputedStyle(e).visibility !== 'hidden') out.push((e.id || e.className || e.tagName).toString().slice(0, 40) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); }); return out.slice(0, 15); })()"""
with sync_playwright() as p:
    br, pg = open_iphone(p, PH); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("document.querySelector('#play-list .pl-row[data-i] .pl-main')?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("npOpen()"); pg.wait_for_timeout(1200)
    btns = pg.evaluate("[...document.querySelectorAll('#np button')].filter(b => b.offsetParent).map(b => (b.id || b.className) + '|' + (b.title || b.getAttribute('aria-label') || b.textContent.trim()).slice(0, 20))")
    print('np buttons', btns)
    pg.evaluate("[...document.querySelectorAll('#np .np-dock button, #np button')].find(b => /音效|声道/.test((b.title || '') + (b.getAttribute('aria-label') || '') + (b.dataset.np || '')) || b.dataset.np === 'sound')?.click()"); pg.wait_for_timeout(1200)
    hide(pg); pg.screenshot(path=os.path.join(OUT, '1_panel.png'))
    print('超出屏幕', pg.evaluate(OVER))
    pg.evaluate("document.querySelector('[data-sp=\"add\"]')?.click()"); pg.wait_for_timeout(1200)
    hide(pg); pg.screenshot(path=os.path.join(OUT, '2_add.png'))
    print('超出屏幕(选择页)', pg.evaluate(OVER))
    print('errors', errs[:3])
    br.close()
