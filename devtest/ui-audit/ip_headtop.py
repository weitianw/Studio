"""手机标题栏离状态栏多远（2026-11-17 用户：标题有点太高了，改成截图那样）。用户截图（iPhone，@3x）：≡ 按钮上沿在 77.7pt、44pt 高、
中心 99.7pt；“33 张”在 145pt 左右。安全区 62pt（模拟器）→ 按钮上沿在安全区下面约 16pt。逐页量 ≡ 按钮、标题、右上按钮的位置。
用法：python ip_headtop.py [--shot]"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'headtop'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
M = r"""() => { const r = s => { const e = [...document.querySelectorAll(s)].find(x => x.offsetParent && x.getBoundingClientRect().width); if (!e) return null; const b = e.getBoundingClientRect(); return [Math.round(b.top * 10) / 10, Math.round(b.height)]; };
  return { burger: r('#ph-menu, .ph-menu, .pg-menu, [data-ph-menu], #main .page-head .ph-burger, .ph-dw-btn'), title: r('#main > .page-head .page-title'), head: r('#main > .page-head') }; }"""
if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("S.muted = true")
        out = {}
        for page in ['img', 'play', 'video', 'mats', 'prompt', 'tts', 'settings']:
            pg.evaluate(f"go({page!r})"); pg.wait_for_timeout(1600); hide(pg)
            out[page] = pg.evaluate(M)
            print(page, out[page], flush=True)
            if '--shot' in sys.argv:
                pg.evaluate("document.querySelectorAll('#main img, #main video').forEach(e => e.style.visibility = 'hidden')")
                pg.screenshot(path=os.path.join(OUT, f'{page}.png'), clip={'x': 0, 'y': 0, 'width': 440, 'height': 180})
        print('safe-top', pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sat') || 'n/a'"))
        br.close()
