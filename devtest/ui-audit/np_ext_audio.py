"""音频也能“用 PotPlayer 打开”（2026-11-17 用户：网页播放器到不了 192 kHz → PotPlayer 可以独占输出）。
全屏播放页的 ⋯ 里有这一项；点了以后发出请求（文件、当前位置）、网页这边暂停。
请求被测试拦下来，不会真的打开 PotPlayer。用法：python np_ext_audio.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import np_desk
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


if __name__ == '__main__':
    sent = []

    def ext(route):
        if route.request.method == 'GET':
            return route.fulfill(status=200, content_type='application/json', body='{"potplayer": true}')
        sent.append(json.loads(route.request.post_data or '{}'))
        route.fulfill(status=200, content_type='application/json', body='{"ok": true}')

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=np_desk.EXE, args=['--mute-audio'])
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        ctx.route('**/api/play/external', ext)  # 一律拦下：测试里不打开 PotPlayer
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(np_desk.B + '/'); pg.wait_for_timeout(2500)
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
        pg.evaluate("npOpen()"); pg.wait_for_timeout(800)
        pg.evaluate("(() => { const a = PB.a; Object.defineProperty(a, 'currentTime', { get: () => 83.4, set: () => { }, configurable: true }); })()")
        pg.click('#np-more2'); pg.wait_for_timeout(400)  # 11-18：右上角的 ⋯
        r = pg.evaluate("(() => { const e = [...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => e.textContent.includes('PotPlayer')); return e ? { text: e.textContent.trim() } : null; })()")
        check('音频：右上角 ⋯ 里有“用 PotPlayer 打开”', r and '用 PotPlayer 打开' in r['text'], r)
        pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => e.textContent.includes('PotPlayer')).click()"); pg.wait_for_timeout(600)
        check(f'点了：发出打开请求（文件 + 当前位置 {sent[0]["t"] if sent else None} 秒）', len(sent) == 1 and sent[0].get('key') and abs(sent[0]['t'] - 83.4) < .01, sent)
        check('网页这边暂停了', pg.evaluate("PB.a.paused"))
        check('提示“已在 PotPlayer 中打开”', pg.evaluate("[...document.querySelectorAll('.toast, .tst, [class*=toast]')].some(e => e.textContent.includes('PotPlayer'))"))
        pg.evaluate("VAULT = true"); pg.click('#np-more2'); pg.wait_for_timeout(400)
        check('私密空间里不出现', not pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].some(e => e.textContent.includes('PotPlayer'))"))
        pg.keyboard.press('Escape'); pg.evaluate("VAULT = false")
        check('没有页面报错', not errs, errs)
        b.close()
    print(f'通过 {ok}，失败 {bad}')
