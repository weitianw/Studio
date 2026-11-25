"""全屏播放页（2026-11-18 用户）：
1) 从播放列表在音频和视频之间切换：有过渡动画（View Transitions，html.vt-np），切完样子对、没有卡住；
2) 视频页背景跟着外观走（两边设置互通）：纯色 → 视频页也是那个颜色；封面雾色 / 流动渐变 → 视频页有那层背景、放视频时不流动；
3) 视频页的外观只显示能用的：样式、背景颜色（没有 播放栏 / 字幕大小 / 封面）；视频的设置菜单里有“外观…”。
截图前藏起图片 / 视频，静音。用法：python t_np_vt.py"""
import os, sys
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


SPY = """(() => { window.__vt = 0; const R = document.documentElement; new MutationObserver(() => { if (R.classList.contains('vt-np')) window.__vt++; }).observe(R, { attributes: true, attributeFilter: ['class'] }); })()"""
MENU = "[...document.querySelectorAll('.ctx-menu:not(.ctx-subm) .ctx-i')].map(e => e.textContent.trim())"
SECS = "[...document.querySelectorAll('.npl-sheet .npl-sec')].map(e => e.firstChild.textContent.trim())"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}, color_scheme='dark'); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video,.np-amb canvas{visibility:hidden!important}')
    pg.evaluate("S.theme = 'dark'; applyTheme(false); go('play')"); pg.wait_for_timeout(1500)
    # 播放列表里放一首音频、一个视频
    pg.locator('#play-src button', has_text='视频').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='H264 720p').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); window.__vid = { ...PB.q.items[PB.q.i] }")
    pg.locator('#play-src button', has_text='很多文件').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='片段 004').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); qAdd(window.__vid, true)"); pg.wait_for_timeout(300)
    vi = pg.evaluate("(PB.q?.items || []).findIndex(x => x.video)")
    ai = pg.evaluate("PB.q.i")
    check(f'播放列表里音频、视频都有（音频 {ai}，视频 {vi}）', vi >= 0 and ai >= 0 and vi != ai, (vi, ai))
    pg.evaluate("qAudio.pause(); npOpen()"); pg.wait_for_timeout(1300)
    pg.evaluate("(() => { const l = JSON.parse(JSON.stringify(S.ui?.npLook || {})); window.__look0 = l; })()")
    pg.evaluate(SPY)
    pg.evaluate("qAudio.addEventListener('playing', () => qAudio.pause())")  # 测试音频只有 1 秒：一开始放就停，免得放完自己跳到下一首
    for k, (idx, want) in enumerate(((vi, True), (ai, False), (vi, True))):
        pg.evaluate(f"PB.q.i = {idx}; qLoad()")
        pg.wait_for_timeout(1400); pg.evaluate("qAudio.pause()")
        isv = pg.evaluate("document.querySelector('#np').classList.contains('is-video')")
        check(f'第 {k + 1} 次切换：切成{"视频" if want else "音频"}', isv == want, isv)
    check(f'切换时有过渡动画（{pg.evaluate("window.__vt")} 次）', pg.evaluate("window.__vt") >= 3)
    check('动画结束后不残留', not pg.evaluate("document.documentElement.classList.contains('vt-np')"))
    # 现在是视频：外观
    pg.evaluate("S.ui = { ...(S.ui || {}), theater: false }; npTheater()"); pg.wait_for_timeout(1000)  # 外观背景在开侧栏时看得见（不开侧栏是环境光）
    pg.click('#np-vr #np-more2'); pg.wait_for_timeout(400); m = pg.evaluate(MENU)
    check(f'视频设置菜单里有“外观…”（{m}）', any('外观' in x for x in m), m)
    pg.locator('.ctx-menu .ctx-i', has_text='外观').first.click(); pg.wait_for_timeout(500)
    secs = pg.evaluate(SECS)
    check(f'视频页的外观只有 样式、背景颜色（{secs}）', secs == ['样式', '背景颜色'], secs)
    pg.click('.npl-sheet [data-st="solid"]'); pg.wait_for_timeout(300); pg.click('.npl-sheet [data-col="wine"]'); pg.wait_for_timeout(600)
    bgi = pg.evaluate("getComputedStyle(document.querySelector('#np')).backgroundImage")
    check(f'选纯色 · 酒红：视频页背景是那个颜色（{bgi[:60]}）', 'gradient' in bgi and pg.evaluate("getComputedStyle(document.querySelector('#np-bg')).display") == 'none', bgi)
    pg.screenshot(path=os.path.join(OUT, 'vt_video_solid.png'))
    pg.click('.npl-sheet [data-st="mist"]'); pg.wait_for_timeout(800)
    check('选封面雾色：视频页有那层雾色背景', pg.evaluate("(() => { const f = document.querySelector('#np .npl-flow'); return !!f && getComputedStyle(f).display !== 'none'; })()"))
    pg.mouse.click(300, 300); pg.wait_for_timeout(400)
    pg.evaluate("S.ui = { ...(S.ui || {}), theater: true }; npTheater()"); pg.wait_for_timeout(1000)
    check('不开侧栏：环境光盖在外观背景上（还没取到画面时露出外观背景，不会一片黑）', pg.evaluate("(() => { const a = document.querySelector('.np-amb'); return !!a && !a.hidden && getComputedStyle(a).display !== 'none' && getComputedStyle(a).backgroundColor === 'rgba(0, 0, 0, 0)'; })()"))
    pg.evaluate("S.ui = { ...(S.ui || {}), theater: false }; npTheater()"); pg.wait_for_timeout(800)
    # 回到音频：音频也是封面雾色（同一份设置），外观里 播放栏 / 字幕大小 / 封面 都在
    pg.evaluate(f"PB.q.i = {ai}; qLoad()"); pg.wait_for_timeout(1500); pg.evaluate("qAudio.pause()")
    check('回到音频：样式也是封面雾色（同一份设置）', pg.evaluate("document.querySelector('#np').classList.contains('look-mist')"))
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(500); secs = pg.evaluate(SECS)
    check(f'音频页的外观还是全的（{secs}）', all(x in secs for x in ('样式', '背景颜色', '字幕大小', '封面')), secs)
    pg.mouse.click(300, 300); pg.wait_for_timeout(400)
    # 右边播放列表：上面已经有“播放列表”页签，列表里不再重复这个标题（首数还在）
    pg.evaluate("NP.tab = 'queue'; npPaint(true)"); pg.wait_for_timeout(800)
    hd = pg.evaluate("(() => { const b = document.querySelector('#np-right .ql-head b'), t = document.querySelector('#np-right .ql-head .tiny'); return [b ? getComputedStyle(b).display : 'none', t ? t.textContent : '']; })()")
    check(f'侧栏播放列表：不重复“播放列表”标题、首数还在（{hd}）', hd[0] == 'none' and '首' in hd[1], hd)
    pg.evaluate("npClose()"); pg.wait_for_timeout(600)
    # 底部播放条：标题和目录一行，和进度条之间空开
    pg.evaluate("go('play'); pbMin(false)"); pg.wait_for_timeout(1200)
    g = pg.evaluate("(() => { const q = s => document.querySelector(s).getBoundingClientRect(); const t = q('.pbar .pb-title'), u = q('.pbar .pb-sub'), p = q('.pbar .pb-track'); return [Math.round(Math.abs(t.top + t.height / 2 - (u.top + u.height / 2))), Math.round(p.top - Math.max(t.bottom, u.bottom))]; })()")
    check(f'底部播放条：标题和目录一行、和进度条空开（错开 {g[0]}px，间距 {g[1]}px）', g[0] <= 3 and g[1] >= 6, g)
    # 还原外观设置
    pg.evaluate("S.ui = { ...(S.ui || {}), npLook: window.__look0 }; persist(); NPL.paint()")
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
