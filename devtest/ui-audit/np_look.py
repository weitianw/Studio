"""全屏播放页的“外观”（npstyle.js，2026-11-17）：⋯ → 外观 → 选样式 / 背景颜色 / 封面。
电脑 1440 和 2000 宽、iPhone 模拟；每种样式截图（图片和视频藏起来、静音），量版面、点弹窗、看有没有报错。用法：python np_look.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import open_np, B, EXE
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_np_look'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0
STY = ['mist', 'orig', 'solid']


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


RECT = "s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), vis: getComputedStyle(e).display !== 'none' && r.width > 0 }; }"
SET = "([s, color, art]) => { S.ui = { ...(S.ui || {}), npLook: { s, color, art } }; NP.key = null; npPaint(true); }"


def desktop(p, W, H):
    import np_desk
    np_desk.W, np_desk.H = W, H
    b, pg = open_np(p)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    HIDE = "document.querySelectorAll('.np img, .np video').forEach(e => e.style.visibility = 'hidden')"
    pg.evaluate("S.theme = 'dark'; applyTheme(false); NP.key = null; npPaint(true)"); pg.wait_for_timeout(500)  # 无头浏览器默认浅色；先测深色
    check(f'{W}: 播放页铺满整个窗口（右边不留一条）', pg.evaluate("Math.round(document.querySelector('#np').getBoundingClientRect().width) === innerWidth"))
    check(f'{W}: 默认样式是封面雾色', pg.evaluate("NPL._L().s === 'mist' && document.querySelector('#np').classList.contains('look-mist')"))
    check(f'{W}: 没有前进 / 后退 10 秒', not pg.evaluate(RECT, '[data-npb="back"]')['vis'] and not pg.evaluate(RECT, '[data-npb="fwd"]')['vis'])
    # ⋯ → 外观（从右边滑出）
    pg.click('#np-more2'); pg.wait_for_timeout(300)  # 11-18：电脑上放音频时用右上角的 ⋯
    check(f'{W}: 右上角 ⋯ 菜单里有“外观…”', pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].some(e => e.textContent.includes('外观'))"))
    pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => e.textContent.includes('外观')).click()"); pg.wait_for_timeout(500)
    sh = pg.evaluate(RECT, '.npl-sheet')
    check(f'{W}: 外观从右边滑出，左边不挡', sh and sh['vis'] and sh['x'] + sh['w'] > W - 30 and sh['w'] < 420, sh)
    check(f'{W}: 4 个样式 + 3 种播放栏（11-18 加了流动渐变、底部通栏）', pg.evaluate("document.querySelectorAll('.npl-st .npl-card').length === 4 && document.querySelectorAll('.npl-bars .npl-card').length === 3"))
    pg.evaluate("document.querySelectorAll('.npl-sheet .mini i').forEach(e => e.style.backgroundImage = 'none')")
    pg.screenshot(path=os.path.join(OUT, f'd{W}_sheet.png'))
    hit = pg.evaluate("(() => { const r = document.querySelector('#np-stage').getBoundingClientRect(); return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.closest('#np') ? 1 : 0; })()")
    check(f'{W}: 外观开着时左边的播放页还能点', hit == 1 and bool(pg.evaluate(RECT, '.npl-sheet')))
    pg.click('.npl-sw [data-col="dusk"]'); pg.wait_for_timeout(300)
    check(f'{W}: 选“暮紫”', pg.evaluate("S.ui.npLook.color === 'dusk' && getComputedStyle(document.querySelector('#np')).getPropertyValue('--tone').trim() === '#4d4463'"))
    st0 = pg.evaluate("document.querySelector('#np-right .subs')?.scrollTop")
    pg.click('.npl-card[data-st="solid"]'); pg.wait_for_timeout(500)
    st1 = pg.evaluate("document.querySelector('#np-right .subs')?.scrollTop")
    check(f'{W}: 换样式时字幕不从头滚', st0 is not None and abs(st1 - st0) < 4, (st0, st1))
    fs0 = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#np-right .sub')).fontSize)")
    pg.click('.npl-fs [data-fs="xl"]'); pg.wait_for_timeout(700)
    fs1 = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#np-right .sub')).fontSize)")
    on = pg.evaluate("(() => { const l = document.querySelector('#np-right .subs'), o = l.querySelector('.sub.on'); return (o.offsetTop + o.offsetHeight / 2 - l.scrollTop) / l.clientHeight; })()")
    check(f'{W}: 字幕“特大”（{fs0:.0f} → {fs1:.0f}px），当前句在 30% 左右（{on:.2f}）', fs1 > fs0 * 1.3 and .22 < on < .38, (fs0, fs1, on))
    pg.click('.npl-fs [data-fs="m"]'); pg.wait_for_timeout(300)
    pg.click('.npl-art [data-art="none"]'); pg.wait_for_timeout(300)
    check(f'{W}: 封面“不显示” → 通用图案', pg.evaluate("S.ui.npLook.art === 'none' && !!document.querySelector('#np-art .npl-cov.gen')"))
    pg.click('.npl-bars [data-bar="dock"]'); pg.wait_for_timeout(400)
    check(f'{W}: 播放栏“底部一条”', pg.evaluate("document.querySelector('#np').classList.contains('bar-dock')"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    check(f'{W}: Esc 只关弹窗，不关播放页', not pg.evaluate(RECT, '.npl-sheet') and not pg.evaluate("document.querySelector('#np').hidden"))
    # 底部一条：进度条能拖
    pr = pg.evaluate(RECT, '#np-track'); y = pr['y'] + pr['h'] / 2
    pg.mouse.move(pr['x'] + pr['w'] * .2, y); pg.mouse.down(); pg.mouse.move(pr['x'] + pr['w'] * .5, y, steps=6); pg.mouse.up(); pg.wait_for_timeout(200)
    hit = pg.evaluate("([x, y]) => document.elementFromPoint(x, y)?.closest('#np-track') ? 1 : 0", [pr['x'] + pr['w'] * .5, y])
    t = pg.evaluate("window.__t")
    check(f'{W}: 底部一条：进度条点得到、能拖（拖到 {t}）', hit == 1 and t is not None and abs(t - pg.evaluate("PB.a.duration") * .5) < pg.evaluate("PB.a.duration") * .06, (hit, t))
    rt, ctl = pg.evaluate(RECT, '#np-right'), pg.evaluate(RECT, '.np-ctl')
    check(f'{W}: 底部一条：字幕那栏不伸到玻璃条后面', rt['y'] + rt['h'] < ctl['y'] - 8, (rt, ctl))
    pg.evaluate(HIDE); pg.screenshot(path=os.path.join(OUT, f'd{W}_dock_subs.png'))
    # 收起字幕 → 居中（所有样式）
    for s in ('mist', 'orig', 'solid'):
        for bar in ('under', 'dock'):
            pg.evaluate("([s, bar]) => { S.ui = { ...(S.ui || {}), npPanel: true, npLook: { s, bar, color: 'cover', art: 'show' } }; npPaint(true); }", [s, bar]); pg.wait_for_timeout(700)
            pg.click('.np-tabs button[data-np="subs"]'); pg.wait_for_timeout(600)
            st = pg.evaluate(RECT, '#np-stage')
            ok1 = not pg.evaluate(RECT, '#np-right')['vis'] and abs(st['x'] + st['w'] / 2 - W / 2) < 30
            pg.evaluate(HIDE); pg.screenshot(path=os.path.join(OUT, f'd{W}_{s}_{bar}_solo.png'))
            pg.click('.np-tabs button[data-np="subs"]'); pg.wait_for_timeout(700)
            ok2 = pg.evaluate(RECT, '#np-right')['vis']
            check(f'{W}: {s} / {bar}：点选中的“字幕”收起 → 封面居中；再点 → 打开', ok1 and ok2, st)
            pg.evaluate(HIDE); pg.screenshot(path=os.path.join(OUT, f'd{W}_{s}_{bar}.png'))
    # 应用浅色
    pg.evaluate("S.theme = 'light'; applyTheme(false)"); pg.wait_for_timeout(600)
    check(f'{W}: 应用浅色 → 播放页也浅', pg.evaluate("document.querySelector('#np').classList.contains('npl-light')"))
    pg.evaluate("([s]) => { S.ui = { ...(S.ui || {}), npLook: { s, bar: 'under', color: 'cover', art: 'show' } }; npPaint(true); }", ['mist']); pg.wait_for_timeout(700)
    pg.evaluate(HIDE); pg.screenshot(path=os.path.join(OUT, f'd{W}_light_mist.png'))
    pg.click('.np-tabs button[data-np="queue"]'); pg.wait_for_timeout(900); pg.evaluate(HIDE)
    pg.screenshot(path=os.path.join(OUT, f'd{W}_light_queue.png'))
    pg.click('.np-tabs button[data-np="subs"]'); pg.wait_for_timeout(500)
    pg.evaluate("S.theme = 'dark'; applyTheme(false)"); pg.wait_for_timeout(300)
    # 版面：左右两栏整体居中
    pg.evaluate("S.ui = { ...(S.ui || {}), npPanel: true, npLook: { s: 'orig', color: 'cover', art: 'show' } }; npPaint(true);"); pg.wait_for_timeout(600)
    st, rt = pg.evaluate(RECT, '#np-stage'), pg.evaluate(RECT, '#np-right')
    lm, rm = st['x'], W - (rt['x'] + rt['w'])
    check(f'{W}: 左右两栏整体居中（左边距 {lm}，右边距 {rm}）', abs(lm - rm) < 60, (st, rt))
    check(f'{W}: 没有页面报错', not errs, errs)
    b.close()


def phone(p):
    br, pg = open_iphone(p, PH)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("PB.a.pause(); npOpen(); npSetView('cover')"); pg.wait_for_timeout(1200)
    for s in STY:
        pg.evaluate(SET, [s, 'cover' if s in ('orig', 'mist') else 'pine', 'show']); pg.wait_for_timeout(900); hide(pg)
        pg.evaluate("document.querySelectorAll('#npl-flow i').forEach(e => e.style.visibility = 'hidden')")
        st, dock = pg.evaluate(RECT, '#np-stage'), pg.evaluate(RECT, '#np-dock')
        check(f'手机 {s}：封面和底部一排都在屏幕里', st and dock and st['w'] > 200 and dock['y'] + dock['h'] <= pg.evaluate('innerHeight'), (st, dock))
        pg.screenshot(path=os.path.join(OUT, f'ph_{s}.png'))
    pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(900); hide(pg); pg.screenshot(path=os.path.join(OUT, 'ph_light_subs.png'))
    pg.evaluate("npSetView('cover')"); pg.wait_for_timeout(600)
    pg.tap('#np-more'); pg.wait_for_timeout(600)
    pg.tap('.npm-look'); pg.wait_for_timeout(700)
    sh = pg.evaluate(RECT, '.npl-sheet')
    check('手机：外观从底部升起', sh and sh['vis'] and sh['y'] + sh['h'] >= pg.evaluate('innerHeight') - 2, sh)
    pg.evaluate("document.querySelectorAll('.npl-sheet .mini i').forEach(e => e.style.backgroundImage = 'none')")
    pg.screenshot(path=os.path.join(OUT, 'ph_sheet.png'))
    pg.tap('.npl-card[data-st="solid"]'); pg.wait_for_timeout(300)
    check('手机：点一下就生效', pg.evaluate("S.ui.npLook.s === 'solid'"))
    check('手机 没有页面报错', not errs, errs)
    br.close()


if __name__ == '__main__':
    with sync_playwright() as p:
        desktop(p, 1440, 900); desktop(p, 2000, 1000); phone(p)
    print(f'通过 {ok}，失败 {bad}')
