"""音效与声道的“全部还原”（2026-11-17 用户：音轨改了之后点还原，也变不回来）。
放测试人声 → 声道改成“左”、叠加一条、选“沉浸空间” → 点“全部还原” → 看设置、左右电平、叠加的是否都回到原样。用法：python t_sound_reset.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


LR = "(async () => { Sound.meter(); let l = 0, r = 0; for (let i = 0; i < 20; i++) { await new Promise(z => setTimeout(z, 100)); const m = Sound.meter() || [0, 0]; l = Math.max(l, m[0]); r = Math.max(r, m[1]); } return [+l.toFixed(4), +r.toFixed(4)]; })()"
STATE = "({ main: Sound.main, fx: Sound.fx, layers: Sound.layers.length, active: Sound.active(), fxActive: Sound.fxActive(), hooked: Sound.hooked(), vol: PB.a.volume, muted: PB.a.muted, rate: PB.a.playbackRate, saved: localStorage.getItem('sound') })"

if __name__ == '__main__':
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required']); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/'); pg.wait_for_timeout(2500)
        pg.evaluate("localStorage.removeItem('sound')")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && x.textContent.trim().startsWith('测试人声'))?.click()"); pg.wait_for_timeout(1500)
        pg.mouse.click(5, 450)
        pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(2500)
        pg.evaluate("PB.a.loop = true")
        url = pg.evaluate("PB.a?.currentSrc || PB.a?.src")
        print('原样', pg.evaluate(STATE))
        # 改：声道 → 左；叠加一条；选“沉浸空间”（都通过面板点）
        pg.evaluate('spOpen()'); pg.wait_for_timeout(500)
        pg.click('.sp-track[data-t="main"] [data-pos="l"]'); pg.wait_for_timeout(600)
        pg.evaluate(f"Sound.addLayer({{ url: {json.dumps(url)}, title: '测试叠加' }}); spPaint()"); pg.wait_for_timeout(1500)
        pg.click('.sp-presets [data-preset="space"]'); pg.wait_for_timeout(1200)
        changed = pg.evaluate(STATE); lr1 = pg.evaluate(LR)
        print('改了以后', changed, lr1)
        check('改了以后：声道是左、有叠加、有音效', changed['main']['pos'] == 'l' and changed['layers'] == 1 and changed['fxActive'], changed)
        pg.click('[data-sp="reset"]'); pg.wait_for_timeout(1500)
        after = pg.evaluate(STATE); lr2 = pg.evaluate(LR)
        print('还原以后', after, lr2)
        check('还原：声道回到“中”、音量 100%', after['main'] == {'pos': 'c', 'vol': 1}, after['main'])
        check('还原：叠加的音轨没了', after['layers'] == 0, after)
        check('还原：音效全关', not after['fxActive'] and after['fx']['preset'] == 'off', after['fx'])
        check(f'还原：左右电平一样（{lr2}）', lr2[0] > .001 and abs(lr2[0] - lr2[1]) / max(lr2) < .1, lr2)
        check('还原：面板上显示的也回到原样', pg.evaluate("document.querySelector('.sp-track[data-t=main] [data-pos=c]')?.classList.contains('on') && document.querySelector('.sp-presets [data-preset=off]')?.classList.contains('on') && !document.querySelector('.sp-track:not([data-t=main])')"))
        check('还原：记住的设置也是原样', json.loads(after['saved'] or '{}').get('main', {}).get('pos') == 'c')
        check('没有页面报错', not errs, errs[:3])
        b.close()
    print(f'{ok}/{ok + bad} 通过')
