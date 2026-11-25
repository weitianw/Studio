"""手机播放页：点文件夹跳到文件列表（文件夹列表藏起来），返回键回来；点子文件夹同样（2026-11-21 用户：在文件列表下面展开了）。
用法：STUDIO_TEST_PORT=7897 ../.venv/Scripts/python.exe ip_play_drill.py"""
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
D = "[getComputedStyle(document.querySelector('.play-side')).display, getComputedStyle(document.querySelector('#play-list')).display]"
with sync_playwright() as p:
    br, pg = open_iphone(p, f'http://127.0.0.1:{PORT}/', sfw=False)
    pg.add_style_tag(content='img,video,canvas{opacity:0!important}')
    pg.evaluate("go('play')"); pg.wait_for_timeout(2000)
    check('一开始只有文件夹列表', pg.evaluate(D) == ['block', 'none'], pg.evaluate(D))
    pg.tap('#play-src .ps-item >> nth=0'); pg.wait_for_timeout(1500)
    check('点「作品」：只剩文件列表', pg.evaluate(D) == ['none', 'flex'], pg.evaluate(D))
    pg.tap('.pl-back'); pg.wait_for_timeout(1200)
    check('返回键：回到文件夹列表', pg.evaluate(D) == ['block', 'none'], pg.evaluate(D))
    pg.tap('#play-src .ps-dir >> nth=1'); pg.wait_for_timeout(1500)
    check('点一个文件夹：只剩文件列表', pg.evaluate(D) == ['none', 'flex'], pg.evaluate(D))
    br.close()
print(f'{ok} 通过，{fail} 失败')
