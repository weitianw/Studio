"""手机：电脑上开了「视频铺满」（S.ui.theater，几台设备共用）时，手机的视频全屏播放页照常排开、按钮不压进度条（2026-11-21 用户截图）。
用法：STUDIO_TEST_PORT=7897 ../.venv/Scripts/python.exe ip_np_theater.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from iphone import open_iphone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PORT = os.environ.get('STUDIO_TEST_PORT', '7897')
ok = fail = 0
def check(n, c, x=''):
    global ok, fail
    if c: ok += 1; print('  ✓', n)
    else: fail += 1; print('  ✗', n, str(x)[:300])
R = "(s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return [r.top, r.bottom]; })"
with sync_playwright() as p:
    br, pg = open_iphone(p, f'http://127.0.0.1:{PORT}/', sfw=False)
    pg.add_style_tag(content='img,video,canvas{opacity:0!important}')
    pg.evaluate("go('play')"); pg.wait_for_timeout(2000)
    pg.tap('#play-src .ps-item >> nth=0'); pg.wait_for_timeout(1500)
    pg.evaluate("[...document.querySelectorAll('button')].find(b => b.offsetParent && b.textContent.trim() === '视频')?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('#play-list .pl-row')?.click()"); pg.wait_for_timeout(2500)
    pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; })")
    pg.evaluate("S.ui = { ...(S.ui || {}), theater: true }"); pg.evaluate("npOpen()"); pg.wait_for_timeout(2000)
    pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
    cls = pg.evaluate("document.getElementById('np').className")
    prog, ctl, meta = (pg.evaluate(f"{R}('#np .np-{k}')") for k in ('prog', 'ctl', 'meta'))
    check('是视频全屏播放页', 'is-video' in cls, cls)
    check('手机上不用铺满的排法', 'theater' not in cls, cls)
    check('标题、进度条、按钮从上到下不重叠', prog and ctl and meta and meta[1] <= prog[0] + 1 and prog[1] <= ctl[0] + 1, (meta, prog, ctl))
    pg.evaluate("S.ui.theater = false")
    br.close()
print(f'{ok} 通过，{fail} 失败')
