"""全屏播放页改动后的检查（2026-11-17）：电脑 音频（测试人声，真识别出的字幕）——字幕工具栏有“重新生成”、高亮两边圆角不被截、页签在右上；
电脑 视频（剧集/第1季/第1集）——顶栏位置和改之前一样（页签在字幕栏左边、收起在左上）；手机的部分见 ip_lyrics.py。
画面里的视频截图前藏起来。用法：python np_check2.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_np_desk'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0
R = """(() => { const q = s => { const e = document.querySelector(s); if (!e || !e.offsetParent) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
  const on = document.querySelector('#np-right .sub.on'), list = document.querySelector('#np-right .subs');
  return { close: q('#np-close'), tabs: q('.np-tabs'), tools: q('.np-tools'), regen: q('#np-right [data-regen]'), on: on && q('#np-right .sub.on'), list: list && q('#np-right .subs'),
    onBg: on ? getComputedStyle(on).backgroundColor : null, video: document.querySelector('#np')?.classList.contains('is-video') }; })()"""


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


def open_item(pg, folder, sub=None):
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
    pg.evaluate(f"[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && x.textContent.trim().startsWith('{folder}'))?.click()"); pg.wait_for_timeout(1800)
    if sub:
        pg.evaluate(f"[...document.querySelectorAll('#play-src *, #play-list *')].find(x => x.children.length < 4 && x.textContent.trim().startsWith('{sub}'))?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(2000)
    pg.evaluate("PB.a?.pause()"); pg.evaluate("npOpen()"); pg.wait_for_timeout(1200); pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(2500)
    pg.evaluate("(() => { const a = PB.a; if (!a) return; Object.defineProperty(a, 'currentTime', { get: () => 8.5, set: () => {}, configurable: true }); a.dispatchEvent(new Event('timeupdate')); })()"); pg.wait_for_timeout(1200)
    pg.evaluate("document.querySelectorAll('.np video, .np img').forEach(e => e.style.visibility = 'hidden')")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio']); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    open_item(pg, '测试人声'); r = pg.evaluate(R); print('音频', r)
    check('电脑 音频：字幕上面那排平时不显示（11-18 收进右键菜单）', not r['regen'], r)
    pg.click('#np-right', button='right', position={'x': 200, 'y': 200}); pg.wait_for_timeout(300)
    mi = pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].map(e => e.textContent.trim())"); pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    check(f'电脑 音频：右键菜单里有 重新生成 / 翻译 / 查找 / 逐行·段落·全文 / 提前·推后（{mi}）', all(any(k in x for x in mi) for k in ['重新生成字幕', '翻译', '查找', '逐行', '段落', '全文', '提前', '推后']), mi)
    check('电脑 音频：正在播那句不超出字幕框（不被截）', r['on'] and r['list'] and r['on'][0] + r['on'][2] <= r['list'][0] + r['list'][2] + 1, r)
    check('电脑 音频：页签在右上、和收起按钮分开', r['tabs'] and r['close'] and r['tabs'][0] > 700 and r['tabs'][0] + r['tabs'][2] < r['tools'][0], r)
    pg.screenshot(path=os.path.join(OUT, 'check_audio.png'))
    pg.evaluate("npClose?.()"); pg.wait_for_timeout(800)
    open_item(pg, '剧集', '第1季'); r = pg.evaluate(R); print('视频', r)
    check('电脑 视频：还是视频布局（is-video）', r['video'], r)
    check('电脑 视频：页签不跑到右上（保持在字幕栏那边）', r['tabs'] is None or r['tabs'][1] < 120, r)
    pg.screenshot(path=os.path.join(OUT, 'check_video.png'))
    check('电脑：没有页面报错', not errs, errs[:3])
    b.close()
    # 手机：模拟器拦掉了音频请求（静音），全屏播放打不开字幕；手机的字幕和“重新生成”由 ip_lyrics.py（模拟字幕）检查
print(f'{ok}/{ok + bad} 通过')
