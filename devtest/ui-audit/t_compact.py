"""精简模式（迷你播放器，2026-11-18 用户：UX 优化一下）：模拟应用窗口，340 宽。
播放键没有白色大圆；字幕抽屉是歌词式（没有时间、没有“逐行 / 段落 / 全文”、当前句没有底块）；进度条能点着跳；
播放列表行矮一点；浅色主题下歌词是深色字。截图前藏起图片 / 视频，静音。用法：python t_compact.py"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots_np_desk')


def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)


APP = """(() => { const p = () => Promise.resolve({}); window.pywebview = { api: { win_drag: p, win_state: p, win_min: p, win_max: p, win_close: p, compact: p, compact_hide: p, compact_pin: p, compact_size: p, compact_drag: p } }; appChrome(); })()"""
SENTS = json.dumps([{'s': i * 3, 'e': i * 3 + 2.6, 'text': f'第 {i + 1} 句歌词'} for i in range(12)], ensure_ascii=False)
VIS = "s => [...document.querySelectorAll(s)].filter(e => e.getClientRects().length && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden').length"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1200, 'height': 800}, color_scheme='dark'); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    pg.evaluate(APP)
    pg.evaluate("S.theme = 'dark'; applyTheme(false); go('play')"); pg.wait_for_timeout(1500)
    pg.locator('#play-src button', has_text='很多文件').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='片段 004').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause()")
    pg.set_viewport_size({'width': 340, 'height': 60}); pg.evaluate("compactOpen()"); pg.wait_for_timeout(800)
    check('进了精简模式', pg.evaluate("!!CP && document.body.classList.contains('compact')"))
    pg.mouse.move(170, 30); pg.wait_for_timeout(400)
    bg = pg.evaluate("getComputedStyle(document.querySelector('[data-cp=\"play\"]')).backgroundColor")
    check(f'播放键没有白色大圆（{bg}）', bg in ('rgba(0, 0, 0, 0)', 'transparent'), bg)
    # 进度条：点中间跳到一半
    d = pg.evaluate("qAudio.duration")
    r = pg.evaluate("(() => { const r = document.querySelector('.cp-prog').getBoundingClientRect(); return [r.left, r.top, r.width]; })()")
    pg.mouse.click(r[0] + r[2] / 2, r[1] + 1); pg.wait_for_timeout(300)
    t = pg.evaluate("qAudio.currentTime")
    check(f'点进度条中间：跳到一半（{t:.1f} / {d:.1f}）', d and abs(t - d / 2) < d * 0.06, (t, d))
    # 字幕
    pg.set_viewport_size({'width': 340, 'height': 340})
    pg.evaluate(f"(() => {{ CP.key = PB.meta.subsKey || 'x'; PB.meta.subsKey = CP.key; CP.state = 'done'; CP.sents = {SENTS}; qAudio.currentTime = 10; cpDrawer('subs'); cpLine(); setTimeout(() => qAudio.dispatchEvent(new Event('timeupdate')), 200); }})()")
    pg.wait_for_timeout(1200)
    check('字幕抽屉是歌词式', pg.evaluate("!!document.querySelector('.cp-drawer .subs-host.lyrics')"))
    check('没有 逐行 / 段落 / 全文', pg.evaluate(VIS, '.cp-drawer [data-mode]') == 0)
    check('没有时间', pg.evaluate(VIS, '.cp-drawer .sub .st') == 0)
    on = pg.evaluate("(() => { const o = document.querySelector('.cp-drawer .sub.on'); return o && [getComputedStyle(o).backgroundColor, o.textContent.trim()]; })()")
    check(f'当前那句没有底块（{on}）', on and on[0] in ('rgba(0, 0, 0, 0)', 'transparent'), on)
    pos = pg.evaluate("(() => { const o = document.querySelector('.cp-drawer .sub.on').getBoundingClientRect(), l = document.querySelector('.cp-drawer .subs').getBoundingClientRect(); return (o.top + o.height / 2 - l.top) / l.height; })()")
    check(f'当前那句滚到抽屉偏上的位置（{pos:.2f}）', 0.25 < pos < 0.6, pos)
    pg.mouse.move(170, 200); pg.wait_for_timeout(300)
    check('鼠标移上去：有查找小图标', pg.evaluate("getComputedStyle(document.querySelector('.cp-drawer .find-btn')).opacity") == '1')
    pg.screenshot(path=os.path.join(OUT, 'cp_subs_dark.png'))
    pg.evaluate("S.theme = 'light'; applyTheme(false)"); pg.wait_for_timeout(500)
    col = pg.evaluate("getComputedStyle(document.querySelector('.cp-drawer .sub.on')).color")
    check(f'浅色：当前那句是深色字（{col}）', col.startswith('rgb(29, 29, 31'), col)
    pg.screenshot(path=os.path.join(OUT, 'cp_subs_light.png'))
    pg.evaluate("S.theme = 'dark'; applyTheme(false)")
    pg.evaluate("cpDrawer('queue')"); pg.wait_for_timeout(700)
    h = pg.evaluate("Math.round(document.querySelector('.cp-drawer .ql-row').getBoundingClientRect().height)")
    check(f'播放列表一行不高（{h}px）', h <= 44, h)
    pg.screenshot(path=os.path.join(OUT, 'cp_queue.png'))
    pg.evaluate("compactClose()"); pg.wait_for_timeout(500)
    check('退出精简模式', pg.evaluate("!CP && !document.body.classList.contains('compact')"))
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
