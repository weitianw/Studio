"""全屏播放页的音量条（2026-11-17 用户：播放页加入可以调节音量的功能）。
电脑（Chromium）：点 / 拖 / 滚轮 / 方向键 / 静音键，底栏音量跟着变；视频时在按钮那一排右边。
iPhone（WebKit 模拟）：位置不挡底部一排按钮，点一下就生效。
不认 audio.volume 的 iPhone：页面载入前把 volume 改成只读，看音量是不是改走音效链的增益。
测试音频不播放（暂停）+ 静音浏览器。截图到 shots_np_vol。用法：python np_vol.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import open_np, EXE, B
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_np_vol'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


RECT = "s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, vis: getComputedStyle(e).display !== 'none' && r.width > 0 }; }"
ST = "() => ({ v: S.volume, m: !!S.muted, a: PB.a.volume, bar: +document.querySelector('#vol').value, fill: parseFloat(document.querySelector('#np-vfill').style.width), t: PB.a.currentTime, now: document.querySelector('#np-vtrack').getAttribute('aria-valuenow') })"


def click_at(pg, frac, sel='#np-vtrack'):
    r = pg.evaluate(RECT, sel)
    pg.mouse.click(r['x'] + r['w'] * frac, r['y'] + r['h'] / 2)
    return r


def desktop(p):
    b, pg = open_np(p)
    pg.evaluate("npSetView('cover')"); pg.wait_for_timeout(700)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    v, play = pg.evaluate(RECT, '#np-vol'), pg.evaluate(RECT, '[data-npb="play"]')
    check('电脑 音频：音量条在播放键下面', v and v['vis'] and v['y'] > play['y'] + play['h'] - 2 and v['w'] > 200, (v, play))
    click_at(pg, .25); s = pg.evaluate(ST)
    check('点 25% 的位置 → 音量 25%，底栏和播放器跟着变', abs(s['v'] - .25) < .03 and abs(s['a'] - .25) < .03 and abs(s['bar'] - .25) < .03 and abs(s['fill'] - 25) < 3 and not s['m'], s)
    r = pg.evaluate(RECT, '#np-vtrack'); y = r['y'] + r['h'] / 2
    pg.mouse.move(r['x'] + r['w'] * .3, y); pg.mouse.down(); pg.mouse.move(r['x'] + r['w'] * .6, y, steps=5); pg.mouse.move(r['x'] + r['w'] * .8, y, steps=5); pg.mouse.up()
    s = pg.evaluate(ST); check('拖到 80%', abs(s['v'] - .8) < .03 and abs(s['a'] - .8) < .03, s)
    pg.mouse.move(r['x'] + r['w'] * .5, y); pg.mouse.wheel(0, -100); pg.wait_for_timeout(100)
    s = pg.evaluate(ST); check('滚轮向上 +5%', abs(s['v'] - .85) < .011, s)
    t0 = s['t']; pg.focus('#np-vtrack'); pg.keyboard.press('ArrowLeft'); pg.keyboard.press('ArrowLeft')
    s = pg.evaluate(ST); check('方向键调音量、不跳进度', abs(s['v'] - .75) < .011 and abs(s['t'] - t0) < .01, s)
    pg.click('#np-vmute'); s = pg.evaluate(ST)
    check('左边小喇叭 = 静音（播放器音量 0，条为空）', s['m'] and s['a'] == 0 and s['fill'] == 0 and pg.evaluate("document.querySelector('#np-vmute').classList.contains('on')"), s)
    pg.screenshot(path=os.path.join(OUT, 'desk_audio_muted.png'))
    pg.click('#np-vmute'); s = pg.evaluate(ST); check('再点取消静音，回到 75%', not s['m'] and abs(s['a'] - .75) < .011, s)
    pg.screenshot(path=os.path.join(OUT, 'desk_audio.png'))
    pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(700)
    v = pg.evaluate(RECT, '#np-vol'); check('字幕视图下也有音量条', v and v['vis'], v)
    pg.screenshot(path=os.path.join(OUT, 'desk_subs.png'))
    # 视频的排版：把播放页当成视频（只看位置）
    pg.evaluate("document.querySelector('#np').classList.add('is-video')"); pg.wait_for_timeout(400)
    v, ctl, nx = pg.evaluate(RECT, '#np-vol'), pg.evaluate(RECT, '.np-ctl'), pg.evaluate(RECT, '#np-repeat')
    check('电脑 视频：音量在按钮那一排右边，不挡按钮', v and v['vis'] and abs((v['y'] + v['h'] / 2) - (ctl['y'] + ctl['h'] / 2)) < 4 and v['x'] > nx['x'] + nx['w'], (v, ctl, nx))
    pg.screenshot(path=os.path.join(OUT, 'desk_video_layout.png'))
    pg.evaluate("document.querySelector('#np').classList.remove('is-video'); document.body.classList.add('rc-ctl')")
    check('控制手机播放时不显示', not pg.evaluate(RECT, '#np-vol')['vis'])
    pg.evaluate("document.body.classList.remove('rc-ctl')")
    check('没有页面报错', not errs, errs)
    b.close()


def novol(p):
    """模拟 iPhone 不认 audio.volume：音量调低以后接进音效链，总增益 = 音量；静音 = 0"""
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    pg.add_init_script("(() => { const d = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'volume'); Object.defineProperty(HTMLMediaElement.prototype, 'volume', { get() { return 1; }, set(v) { }, configurable: true }); })()")
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("PB.a.pause(); npOpen(); npSetView('cover')"); pg.wait_for_timeout(900)
    check('检测到不认 audio.volume', pg.evaluate("Sound._novol()"))
    was = pg.evaluate("Sound.hooked()")
    click_at(pg, .4); pg.wait_for_timeout(400)
    g = pg.evaluate("(() => { const c = Sound._ctx(); return { hooked: Sound.hooked(), state: c && c.state }; })()")
    check('音量 40%：接进音效链', g['hooked'], (was, g))
    pg.click('#np-vmute'); pg.wait_for_timeout(200)
    check('静音以后仍然接着（增益 0）', pg.evaluate("Sound.hooked() && S.muted"))
    b.close()


def phone(p):
    br, pg = open_iphone(p, PH)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("PB.a.pause(); npOpen()"); pg.wait_for_timeout(1200); hide(pg)
    H = pg.evaluate("innerHeight")
    for view in ('cover', 'subs', 'queue'):
        pg.evaluate(f"npSetView('{view}')"); pg.wait_for_timeout(900); hide(pg)
        v, play, dock, st = pg.evaluate(RECT, '#np-vol'), pg.evaluate(RECT, '[data-npb="play"]'), pg.evaluate(RECT, '#np-dock'), pg.evaluate(RECT, '#np-stage')
        check(f'手机 {view}：音量条在播放键和底部一排之间、都在屏幕里', v and v['vis'] and v['y'] >= play['y'] + play['h'] - 2 and v['y'] + v['h'] <= dock['y'] + 2 and dock['y'] + dock['h'] <= H, (v, play, dock, H))
        if view == 'cover': check('手机 封面没被挤小（≥ 240）', st['w'] >= 240, st)
        pg.screenshot(path=os.path.join(OUT, f'phone_{view}.png'))
    pg.evaluate("npSetView('cover')"); pg.wait_for_timeout(600)
    r = pg.evaluate(RECT, '#np-vtrack'); pg.touchscreen.tap(r['x'] + r['w'] * .5, r['y'] + r['h'] / 2); pg.wait_for_timeout(200)
    s = pg.evaluate("({ v: S.volume, m: S.muted })")
    check('手机 点一下 50% → 音量 50%', abs(s['v'] - .5) < .03 and not s['m'], s)
    check('音量条够高好点（≥ 30）', r['h'] >= 30, r)
    check('手机 没有页面报错', not errs, errs)
    br.close()


if __name__ == '__main__':
    with sync_playwright() as p:
        desktop(p); novol(p); phone(p)
    print(f'通过 {ok}，失败 {bad}')
