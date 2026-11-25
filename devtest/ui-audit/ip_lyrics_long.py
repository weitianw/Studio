"""长字幕找粉色条（2026-11-17 用户：快结尾的地方密集出现，前面偶尔有）。400 句测试字幕，逐行，从头滚到尾分段截图，
在截图里数粉紫色像素（R>170、G<90、B>170）。用法：python ip_lyrics_long.py 标签"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__)); tag = sys.argv[1] if len(sys.argv) > 1 else 'x'
OUT = os.path.join(HERE, 'shots_iphone', 'lyrics_long', tag); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
W = ['那时候', '是不是觉得很爽很刺激啊', '可是你看进去的东西啊', '可是下了车以后呢', '你还记得那天晚上吗', '想知道', '我一直在这里等你', '慢慢来，不着急']
SENTS = [{'s': i * 3.0, 'e': i * 3.0 + 2.4, 'text': W[i % len(W)] + ('，' + W[(i * 3) % len(W)] if i % 3 == 0 else '') + ('？' if i % 4 == 0 else '。')} for i in range(400)]
with sync_playwright() as p:
    br, pg = open_iphone(p, PH)
    pg.route('**/api/play/subs?**', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'state': 'done', 'sents': SENTS, 'language': 'zh'}, ensure_ascii=False)))
    pg.evaluate("S.muted = true")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("document.querySelector('#play-list .pl-row[data-i] .pl-main')?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("npOpen()"); pg.wait_for_timeout(1000); pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('#np-right [data-mode] [data-m=\"line\"]')?.click()"); pg.wait_for_timeout(800)
    total = 0
    for k, t in enumerate([20, 300, 600, 900, 1100, 1150, 1180, 1195]):
        pg.evaluate(f"(() => {{ const a = PB.a; a.pause(); Object.defineProperty(a, 'currentTime', {{ get: () => {t}, set: () => {{}}, configurable: true }}); a.dispatchEvent(new Event('timeupdate')); }})()"); pg.wait_for_timeout(1400)
        f = os.path.join(OUT, f'{k}_{t}.png'); pg.screenshot(path=f)
        print(t, flush=True)
    br.close()
