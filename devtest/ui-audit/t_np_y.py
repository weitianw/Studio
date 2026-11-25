"""全屏播放页方案 Y（2026-11-18 用户选的，设计稿 docs/设计稿/视频播放页方案_1118_第三轮.html）：
音频：右上角 迷你播放器 · 全屏 │ 窗口按钮一排（应用里一直显示，没有第二个迷你播放器）；底部通栏右边 音量 · 字幕 · 播放列表 · ⋯（音效收进 ⋯）。
视频：整条进度条（两头时间）；下面一排 左 标题 · ♡ ｜ 中 上一个 · 播放 · 下一个 ｜ 右 音量 · 画面字幕 · 全屏 · ⋯；右上角 侧栏开关 · 迷你播放器；
⋯ 里有音效、画中画、随机 / 循环；侧栏打开时画面不被控制条压住；窄窗口（≤760）按钮放回原处。
截图前藏起图片 / 视频，静音。用法：python t_np_y.py"""
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


Q = """s => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); if (!r.width) return null; return { x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom, r: r.right, cy: r.top + r.height / 2, cx: r.left + r.width / 2 }; }"""
KIDS = "s => [...document.querySelectorAll(s + ' > *')].filter(e => e.getClientRects().length && getComputedStyle(e).display !== 'none' && !e.hidden).map(e => e.id || e.dataset.mv || e.className)"
APP = """(() => { const p = () => Promise.resolve({}); window.pywebview = { api: { win_drag: p, win_state: p, win_min: p, win_max: p, win_close: p, compact: p, compact_hide: p, compact_pin: p } }; appChrome(); })()"""
MENU = "[...document.querySelectorAll('.ctx-menu:not(.ctx-subm) .ctx-i')].map(e => e.textContent.trim())"


def look(pg, bar):
    pg.evaluate(f"(() => {{ const l = JSON.parse(localStorage.getItem('npLook') || '{{}}'); l.bar = '{bar}'; localStorage.setItem('npLook', JSON.stringify(l)); }})()")
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(400); pg.click(f'[data-bar="{bar}"]'); pg.wait_for_timeout(400); pg.mouse.click(300, 300); pg.wait_for_timeout(500)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}, color_scheme='dark'); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video,.np-amb canvas{visibility:hidden!important}')  # 环境光是视频画面模糊出来的：截图里也藏起来
    pg.evaluate(APP); pg.wait_for_timeout(300)
    check('模拟应用窗口：有窗口按钮', pg.evaluate("!!document.querySelector('.tb') && document.body.classList.contains('in-app')"))
    pg.evaluate("S.theme = 'dark'; applyTheme(false); go('play')"); pg.wait_for_timeout(1500)
    pg.locator('#play-src button', has_text='很多文件').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='片段 004').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); npOpen()"); pg.wait_for_timeout(1300)
    look(pg, 'full')
    # ---- 音频：底部通栏 ----
    wg = pg.evaluate(KIDS, '#np-wg'); dock = pg.evaluate(KIDS, '#np-dock')
    check(f'音频右上角：迷你播放器 · 全屏（{wg}）', wg == ['np-mini', 'np-fs'], wg)
    check(f'音频右下角：音量 · 字幕 · 播放列表 · ⋯，没有音效（{dock}）', dock == ['np-vol', 'subs', 'queue', 'np-more2'], dock)
    tb = pg.evaluate(Q, '.tb'); w2 = pg.evaluate(Q, '#np-wg'); cl = pg.evaluate(Q, '#np-close')
    check(f'窗口按钮一直显示（不用悬停）', pg.evaluate("getComputedStyle(document.querySelector('.tb')).opacity") == '1')
    check('窗口按钮里没有第二个迷你播放器', not pg.evaluate(Q, '.tb [data-tb="cp"]'))
    check(f'右上角那组和窗口按钮一排、不重叠（{w2 and round(w2["cy"])} / {tb and round(tb["cy"])}，间距 {w2 and tb and round(tb["x"] - w2["r"])}）', w2 and tb and abs(w2['cy'] - tb['cy']) < 3 and 0 <= tb['x'] - w2['r'] < 40, (w2, tb))
    check(f'和左上角 ⌄ 一样高（{cl and round(cl["cy"])}）', cl and w2 and abs(cl['cy'] - w2['cy']) < 4, (cl, w2))
    mv, sb, mo = pg.evaluate(Q, '#np-dock .np-vol'), pg.evaluate(Q, '#np-dock [data-mv="subs"]'), pg.evaluate(Q, '#np-dock #np-more2')
    check('⋯ 在右下角最右边、和那一排对齐', mo and sb and abs(mo['cy'] - sb['cy']) < 3 and mo['x'] > sb['r'] and mo['r'] < 1440, (mo, sb))
    pg.click('#np-dock #np-more2'); pg.wait_for_timeout(400); m = pg.evaluate(MENU)
    check(f'音频 ⋯ 里有 外观、音效与声道（{m}）', any('外观' in x for x in m) and any('音效' in x for x in m), m)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(OUT, 'y_audio_full.png'))
    # 浅色背景：窗口按钮跟着变深
    # 其它样式（封面下方）：⋯ 回到右上角那组
    look(pg, 'under'); wg = pg.evaluate(KIDS, '#np-wg')
    check(f'封面下方样式：右上角 迷你播放器 · ⋯ · 全屏（{wg}）', wg == ['np-mini', 'np-more2', 'np-fs'], wg)
    ov = pg.evaluate("(() => { const a = document.querySelector('#np-wg').getBoundingClientRect(), t = document.querySelector('.np-tabs').getBoundingClientRect(); return t.width > 0 && a.left < t.right + 4 && t.left < a.right && a.top < t.bottom && t.top < a.bottom; })()")
    check('封面下方样式：字幕 / 播放列表页签不被右上角那组盖住', not ov)
    pg.screenshot(path=os.path.join(OUT, 'y_audio_under.png'))
    look(pg, 'full')
    # 窄窗口：放回原处
    pg.set_viewport_size({'width': 700, 'height': 900}); pg.wait_for_timeout(800)
    check(f'窄窗口：右上角那组空了、按钮回原处（{pg.evaluate(KIDS, "#np-wg")}）', pg.evaluate("!document.querySelector('#np-wg').children.length && document.querySelector('#np-fs').parentElement.classList.contains('np-tools') && document.querySelector('#np-vol').parentElement.classList.contains('np-ctl')"))
    pg.set_viewport_size({'width': 1440, 'height': 900}); pg.wait_for_timeout(800)
    check('变回宽窗口：又摆好', pg.evaluate(KIDS, '#np-wg') == ['np-mini', 'np-fs'])
    pg.evaluate("npClose()"); pg.wait_for_timeout(600)
    # ---- 视频 ----
    pg.evaluate("go('play')"); pg.wait_for_timeout(1200)
    pg.locator('#play-src button', has_text='视频').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='H264 720p').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); npOpen()"); pg.wait_for_timeout(1500)
    for th in (True, False):
        pg.evaluate(f"S.ui = {{ ...(S.ui || {{}}), theater: {'true' if th else 'false'} }}; npTheater()"); pg.wait_for_timeout(1200)
        tag = '视频铺满' if th else '侧栏打开'
        wg, vr = pg.evaluate(KIDS, '#np-wg'), pg.evaluate(KIDS, '#np-vr')
        check(f'{tag}：右上角只有 迷你播放器（{wg}）', wg == ['np-mini'], wg)
        check(f'{tag}：右下角 音量 · 音轨 · 设置 · 侧栏 · 全屏，全屏在最右边（{vr}）', vr == ['np-vol', 'np-fx', 'np-more2', 'np-theater', 'np-fs'], vr)
        if th:
            sv = pg.evaluate("(() => { const s = getComputedStyle(document.querySelector('#np-stage')), v = getComputedStyle(qAudio); return [s.paddingTop, v.borderTopLeftRadius, v.boxShadow]; })()")
            check(f'视频铺满：画面没有内边距 / 圆角 / 阴影（{sv}）', sv[0] == '0px' and sv[1] == '0px' and sv[2] == 'none', sv)
            pg.wait_for_timeout(500)
            amb = pg.evaluate("(() => { const a = document.querySelector('.np-amb'); if (!a || a.hidden || getComputedStyle(a).display === 'none') return 'hidden'; const c = a.querySelector('canvas.on'); if (!c) return 'no-canvas'; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let s = 0; for (let i = 0; i < d.length; i += 4) s += d[i] + d[i + 1] + d[i + 2]; return [c.width, c.height, Math.round(s / (d.length / 4))]; })()")
            check(f'视频铺满：环境光在、画上了画面的颜色（{amb}）', isinstance(amb, list) and amb[0] == 48 and amb[2] > 0, amb)
        else:
            check('开侧栏：没有环境光', pg.evaluate("(() => { const a = document.querySelector('.np-amb'); return !a || a.hidden || getComputedStyle(a).display === 'none'; })()"))
            vr2 = pg.evaluate("(() => { const v = qAudio.getBoundingClientRect(), l = document.querySelector('#np .np-left').getBoundingClientRect(); return [Math.round(v.width), Math.round(l.width), getComputedStyle(qAudio).borderTopLeftRadius]; })()")
            check(f'开侧栏：画面是圆角卡片、几乎占满左栏（{vr2}）', vr2[2] != '0px' and vr2[0] >= vr2[1] - 12, vr2)
        check(f'{tag}：⋯ 换成齿轮“设置”', pg.evaluate("document.querySelector('#np-more2').classList.contains('as-gear') && document.querySelector('#np-more2').getAttribute('aria-label') === '设置'"))
        th_b, vr_b = pg.evaluate(Q, '#np-vr #np-theater'), pg.evaluate(Q, '#np-vr')
        check(f'{tag}：侧栏开关真的在右下角那一排里（{th_b and round(th_b["cy"])} / {vr_b and round(vr_b["cy"])}）', th_b and vr_b and abs(th_b['cy'] - vr_b['cy']) < 4 and th_b['x'] >= vr_b['x'] - 1, (th_b, vr_b))
        ctl = pg.evaluate("[...document.querySelectorAll('#np .np-ctl > *')].filter(e => e.getClientRects().length && getComputedStyle(e).display !== 'none').map(e => e.dataset.npb || e.id)")
        check(f'{tag}：中间只有 上一个 · 播放 · 下一个（{ctl}）', [x for x in ctl if x not in ('back', 'fwd')] == ['prev', 'play', 'next'], ctl)
        gone = pg.evaluate("['#np-hide', '#np-ext', '#np-pip', '#np-capbtn', '#np-fs2', '#np-more'].filter(s => { const e = document.querySelector(s); return e && e.getClientRects().length && getComputedStyle(e).display !== 'none'; })")
        check(f'{tag}：隐藏控制条 / PotPlayer / 画中画 / 画面字幕 / 第二个全屏键 / 标题旁 ⋯ 都不单独占位（{gone}）', not gone, gone)
        pr, t0, t1, me, ct, v2, left = (pg.evaluate(Q, s) for s in ('#np .np-track', '#np-t0', '#np-t1', '#np .np-meta', '#np .np-ctl', '#np-vr', '#np .np-left'))
        check(f'{tag}：进度条横跨整栏、两头写时间', pr and t0 and t1 and left and t0['r'] <= pr['x'] + 2 and t1['x'] >= pr['r'] - 2 and abs(t0['cy'] - pr['cy']) < 4 and pr['w'] > left['w'] - 160, (pr, t0, t1, left))
        check(f'{tag}：标题 / 播放键 / 右边按钮同一排（{me and round(me["cy"])} / {ct and round(ct["cy"])} / {v2 and round(v2["cy"])}）', me and ct and v2 and abs(me['cy'] - ct['cy']) < 6 and abs(v2['cy'] - ct['cy']) < 6, (me, ct, v2))
        check(f'{tag}：三块左右不重叠', me and ct and v2 and me['r'] <= ct['x'] and ct['r'] <= v2['x'], (me, ct, v2))
        check(f'{tag}：播放键在那一栏中间', ct and left and abs(ct['cx'] - left['cx']) < 30, (ct, left))
        if not th:
            vd = pg.evaluate(Q, '#np-stage')
            check(f'侧栏打开：控制条在画面下面、不压画面', vd and pr and vd['b'] <= pr['y'] + 2, (vd, pr))
            side = pg.evaluate(Q, '#np-right'); w2 = pg.evaluate(Q, '#np-wg')
            check('侧栏打开：右上角那组在侧栏上方、不压住页签', w2 and side and w2['x'] >= side['x'] - 4 and not pg.evaluate("(() => { const a = document.querySelector('#np-wg').getBoundingClientRect(), t = document.querySelector('.np-tabs').getBoundingClientRect(); return a.left < t.right && t.left < a.right && a.top < t.bottom && t.top < a.bottom; })()"), (w2, side))
        pg.screenshot(path=os.path.join(OUT, f'y_video_{"theater" if th else "split"}.png'))
        pg.click('#np-vr #np-more2'); pg.wait_for_timeout(400); m = pg.evaluate(MENU)
        check(f'{tag}：设置里有 画面字幕、画中画，没有音效（已经是按钮）（{m}）', any('画面字幕' in x for x in m) and any('画中画' in x for x in m) and not any('音效' in x for x in m), m)
        if th: check('视频铺满：⋯ 里有 隐藏控制条', any('隐藏控制条' in x for x in m), m)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # 侧栏开关、迷你播放器按钮能点
    pg.click('#np-vr #np-theater'); pg.wait_for_timeout(1000)
    check('点右下角侧栏开关：切成视频铺满', pg.evaluate("document.querySelector('#np').classList.contains('theater')"))
    pg.click('#np-wg #np-mini'); pg.wait_for_timeout(600)
    check('点迷你播放器：进精简模式', pg.evaluate("document.body.classList.contains('compact') && !!document.querySelector('#cp-host:not([hidden])')"))
    pg.evaluate("compactClose()"); pg.wait_for_timeout(600)
    check('退出精简模式：回到全屏播放页', pg.evaluate("!document.body.classList.contains('compact') && !document.querySelector('#np').hidden"))
    # 鼠标不动：右上角那组和窗口按钮一起隐藏
    pg.evaluate("document.querySelector('#np').classList.add('idle')"); pg.wait_for_timeout(500)
    check('视频铺满、鼠标不动：右上角那组和窗口按钮一起隐藏', pg.evaluate("getComputedStyle(document.querySelector('#np-wg')).opacity === '0' && getComputedStyle(document.querySelector('.tb')).opacity === '0'"))
    pg.evaluate("document.querySelector('#np').classList.remove('idle')")
    pg.evaluate("npClose()"); pg.wait_for_timeout(600)
    check('关了全屏播放页：窗口按钮恢复成平时的样子（有迷你播放器）', pg.evaluate("!!document.querySelector('.tb [data-tb=\"cp\"]').getClientRects().length"))
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
