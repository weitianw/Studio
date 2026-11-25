"""叠加音轨（2026-11-17 用户：iPhone 上叠加音轨以后两个都没声音）。电脑 Chromium（声音不出喇叭，Web Audio 照样算）：
放一首测试音频 → 叠加另一首 → 音效链在跑、左右都有电平；模拟系统把音频暂停（ctx.suspend）→ 正在放时自己恢复；
iPhone 模拟器：叠加不报错、声明成媒体播放（navigator.audioSession 有的话）。用法：python t_layer.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required']); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && x.textContent.trim().startsWith('测试人声'))?.click()"); pg.wait_for_timeout(1500)
    pg.mouse.click(5, 450)  # 用户点过页面（音效链要这样才能启动）
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(2500)
    url = pg.evaluate("PB.a?.currentSrc || PB.a?.src")
    check('主音轨在放', pg.evaluate("!!PB.a && !PB.a.paused"), url)
    pg.evaluate(f"Sound.addLayer({{ url: {json.dumps(url)}, title: '测试叠加' }})"); pg.wait_for_timeout(2500)
    PEAK = "(async () => { Sound.meter(); let mx = 0; for (let i = 0; i < 20; i++) { await new Promise(r => setTimeout(r, 100)); mx = Math.max(mx, ...(Sound.meter() || [0])); } return mx; })()"
    st = pg.evaluate("({ hooked: Sound.hooked(), state: Sound._ctx()?.state, layers: Sound.layers.map(l => l.playing) })"); st['m'] = [pg.evaluate(PEAK)]
    print('叠加后', st)
    check('叠加后：主音轨接进音效链、音效链在跑', st['hooked'] and st['state'] == 'running', st)
    check('叠加后：叠加的音轨也在放', st['layers'] and all(st['layers']), st)
    check('叠加后：有电平（有声音出来）', st['m'] and max(st['m']) > 0.001, st['m'])
    pg.evaluate("Sound._ctx().suspend()"); pg.wait_for_timeout(1500)
    st2 = pg.evaluate("({ state: Sound._ctx()?.state, m: Sound.meter() })")
    check('模拟系统暂停音效链：正在放时自己恢复', st2['state'] == 'running', st2)
    pg.wait_for_timeout(500)
    check('恢复后有电平', pg.evaluate(PEAK) > 0.001)
    pg.evaluate("Sound.clearLayers(); PB.a.pause()")
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'{ok}/{ok + bad} 通过')


if __name__ == '__main__':  # iPhone 模拟器（WebKit）：叠加不报错；有 navigator.audioSession 时声明成 playback
    from iphone import open_iphone
    PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("go('play')"); pg.wait_for_timeout(1500)
        pg.touchscreen.tap(200, 400); pg.wait_for_timeout(300)
        pg.evaluate("Sound.addLayer({ url: '/media/lib/x.mp3', title: '测试叠加' })"); pg.wait_for_timeout(1500)
        r = pg.evaluate("({ has: !!navigator.audioSession, type: navigator.audioSession?.type, state: Sound._ctx()?.state })")
        print('iPhone', r)
        check('iPhone：有 audioSession 时声明成 playback', (not r['has']) or r['type'] == 'playback', r)
        check('iPhone：叠加不报错', not errs, errs[:3])
        pg.evaluate("Sound.clearLayers()")
        br.close()
    print(f'{ok}/{ok + bad} 通过（含 iPhone）')
