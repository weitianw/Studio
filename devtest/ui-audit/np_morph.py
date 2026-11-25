"""全屏播放页展开 / 收起动画（2026-11-17 用户：照 Apple Music 从播放条放大、缩回播放条）。
量：动画中途的 clip-path 和封面位置、结束后没有残留动画 / 样式、收起后播放条回来；连点打开 / 收起不卡住。用法：python np_morph.py [shot]"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
SH = tempfile.gettempdir()  # 截图放系统临时文件夹
ok = bad = 0
def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)
ST = "(() => { const np = document.querySelector('#np'), c = document.querySelector('#np-art > *'), r = c && c.getBoundingClientRect(); return { hidden: np.hidden, clip: getComputedStyle(np).clipPath, cov: r && [Math.round(r.left), Math.round(r.top), Math.round(r.width)], anims: np.getAnimations({ subtree: true }).filter(a => !(a instanceof CSSAnimation) && !(a instanceof CSSTransition) && !(a.effect.target.closest && a.effect.target.closest('[data-npb=play]'))).length, tr: np.style.transition, open: document.body.classList.contains('np-open') }; })()"
def run(p, pbmin):
    print('— 播放条' + ('收起成小圆钮' if pbmin else '展开'))
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(B + '/'); pg.wait_for_timeout(2200); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.evaluate("document.documentElement.dataset.theme = 'dark'; go('play')"); pg.wait_for_timeout(1500)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("(e => { e.click(); e.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('.pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1200); pg.evaluate("qAudio.muted = true")
    pg.evaluate("(m) => pbMin(m, false)", pbmin); pg.wait_for_timeout(500)
    art = pg.evaluate("(() => { const e = document.body.classList.contains('pb-min') ? document.querySelector('#pb-fab') : document.querySelector('#pb-art'), r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width)]; })()")
    pg.evaluate("npOpen()")
    mids = []
    for t in (40, 150, 300):
        pg.wait_for_timeout(t - (mids and [40, 150, 300][len(mids) - 1] or 0)); mids.append(pg.evaluate(ST))
        if 'shot' in sys.argv: pg.screenshot(path=os.path.join(SH, f'morph_open_{t}{"m" if pbmin else ""}.png'))
    pg.wait_for_timeout(500); end = pg.evaluate(ST)
    print('playbar art', art, 'mid', [m['cov'] for m in mids], [m['clip'][:40] for m in mids], 'end', end)
    check('展开中途：整页从播放条的范围展开（clip-path 是 inset）', 'inset' in mids[0]['clip'] and mids[0]['clip'] != 'none')
    check(f'展开起点：封面从播放条小封面附近飞出（{mids[0]["cov"]} ← {art}）', mids[0]['cov'] and abs(mids[0]['cov'][2] - art[2]) < mids[-1]['cov'][2] * .6 and mids[0]['cov'][2] < end['cov'][2])
    print('   end', end, pg.evaluate("document.querySelector('#np').getAnimations({ subtree: true }).filter(a => !(a instanceof CSSAnimation) && !(a instanceof CSSTransition)).map(a => [a.effect.target.className.toString().slice(0, 30), a.playState])"))
    check('展开结束：没有残留动画、样式还原、页面开着', end['anims'] == 0 and end['clip'] == 'none' and end['tr'] == '' and not end['hidden'])
    pg.evaluate("npClose()"); pg.wait_for_timeout(200)
    m2 = pg.evaluate(ST)
    if 'shot' in sys.argv: pg.screenshot(path=os.path.join(SH, 'morph_close_200.png'))
    pg.wait_for_timeout(600); e2 = pg.evaluate(ST)
    check(f'收起中途：封面往播放条缩（{m2["cov"]}）、页面还在', not m2['hidden'] and m2['cov'] and m2['cov'][2] < end['cov'][2])
    check('收起结束：页面藏起、播放条回来、没有残留', e2['hidden'] and not e2['open'] and e2['anims'] == 0 and e2['tr'] == '')
    pg.evaluate("npOpen()"); pg.wait_for_timeout(120); pg.evaluate("npClose()"); pg.wait_for_timeout(80); pg.evaluate("npOpen()"); pg.wait_for_timeout(1300)
    e3 = pg.evaluate(ST)
    print('   left:', pg.evaluate("document.querySelector('#np').getAnimations({ subtree: true }).filter(a => !(a instanceof CSSAnimation) && !(a instanceof CSSTransition)).map(a => [a.effect.target.id || a.effect.target.className.toString().slice(0, 30), a.playState, a.effect.getKeyframes().map(k => Object.keys(k).join('|')).join(';'), a.currentTime])"))
    check('快速 开→收→开：最后是打开、没有卡住的动画', not e3['hidden'] and e3['open'] and e3['anims'] == 0 and e3['clip'] == 'none', e3)
    pg.evaluate("npClose()"); pg.wait_for_timeout(900)
    pg.emulate_media(reduced_motion='reduce'); pg.wait_for_timeout(200)
    check('没有页面报错', not errs, errs)
    b.close()


with sync_playwright() as p:
    run(p, False); run(p, True)
print(f'通过 {ok}，失败 {bad}')
