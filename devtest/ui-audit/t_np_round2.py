"""全屏播放页第二轮（2026-11-18 用户）：截图 + 量位置。深色、1440×900。
封面下方：封面和标题之间不再空一大截；底部通栏：音量和右边按钮一排、垂直居中，左下角退出按钮和歌名一块居中，歌词区收窄、当前句在 42% 左右；
外观点外面就关；按钮没有底色；视频页播放键没有白色大圆；左下角退出按钮能退出。用法：python t_np_round2.py"""
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


Q = """s => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom, r: r.right, cy: r.top + r.height / 2 }; }"""
FAKE = """(() => { NP.tab = 'subs'; NP.sents = Array.from({ length: 40 }, (_, i) => ({ s: i * 2, e: i * 2 + 1.8, text: '测试歌词第 ' + (i + 1) + ' 句' })); npSubsDraw(qAudio);
  Object.defineProperty(qAudio, 'currentTime', { get: () => 30.5, set: () => {}, configurable: true }); qAudio.dispatchEvent(new Event('timeupdate')); })()"""


def bar(pg, v):
    pg.evaluate(f"(() => {{ const l = JSON.parse(localStorage.getItem('npLook') || '{{}}'); }})()")
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(400); pg.click(f'[data-bar="{v}"]'); pg.wait_for_timeout(500)
    pg.mouse.click(300, 300); pg.wait_for_timeout(500)  # 点外面关掉外观


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}, color_scheme='dark'); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    pg.evaluate("S.theme = 'dark'; applyTheme(false); go('play')"); pg.wait_for_timeout(1500)
    pg.locator('#play-src button', has_text='很多文件').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='片段 004').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); npOpen()"); pg.wait_for_timeout(1300)
    # 外观：点外面关
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(500)
    check('外观打开了', pg.evaluate("!!document.querySelector('.npl-bg .npl-sheet')"))
    pg.mouse.click(300, 300); pg.wait_for_timeout(500)
    check('点外观外面：外观关了', not pg.evaluate("!!document.querySelector('.npl-bg')"))
    check('这一下没有顺带点到底下（没开始播放）', pg.evaluate("qAudio.paused"))
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(400); pg.click('.npl-sheet', position={'x': 200, 'y': 20}); pg.wait_for_timeout(300)
    check('点外观里面：不关', pg.evaluate("!!document.querySelector('.npl-bg')"))
    pg.mouse.click(300, 300); pg.wait_for_timeout(500)
    # 封面下方
    bar(pg, 'under'); pg.evaluate(FAKE); pg.wait_for_timeout(800)
    st, mt, cv = pg.evaluate(Q, '#np-stage'), pg.evaluate(Q, '#np .np-meta'), pg.evaluate(Q, '#np .npl-cov')
    check(f'封面下方：封面那块是正方形（{st["w"]:.0f}×{st["h"]:.0f}）', abs(st['w'] - st['h']) < 2, st)
    check(f'封面到标题不空一大截（{mt["y"] - cv["b"]:.0f}px）', 0 < mt['y'] - cv['b'] < 50, (cv, mt))
    bg = pg.evaluate("[...document.querySelectorAll('#np .np-x, #np .np-fav, #np .np-more, #np .np-b, #np .np-tabs, #np .np-tabs button')].filter(e => e.getClientRects().length && !e.classList.contains('play')).map(e => [e.id || e.className, getComputedStyle(e).backgroundColor]).filter(x => !/rgba\\(0, 0, 0, 0\\)|transparent/.test(x[1]))")
    check(f'按钮都没有底色（{bg}）', not bg, bg)
    pg.screenshot(path=os.path.join(OUT, 'r2_under.png'))
    # 底部通栏
    bar(pg, 'full'); pg.evaluate(FAKE); pg.wait_for_timeout(1200)
    v, d, mn, me, rt, on = (pg.evaluate(Q, s) for s in ('#np-vol', '#np-dock [data-mv="subs"]', '#np-min', '#np .np-meta', '#np-right', '#np-right .sub.on'))
    check(f'底部通栏：音量和右边按钮垂直居中对齐（{v and v["cy"]:.0f} / {d and d["cy"]:.0f}）', v and d and abs(v['cy'] - d['cy']) < 3, (v, d))
    check('音量在右边那组按钮的左边、不重叠', v and d and v['r'] <= d['x'] + 1)
    check(f'左下角退出按钮和歌名那一块上下居中（{mn and mn["cy"]:.0f} / {me and me["cy"]:.0f}）', mn and me and abs(mn['cy'] - me['cy']) < 6 and mn['r'] < me['x'], (mn, me))
    check(f'歌词区收窄（{rt and rt["h"]:.0f}px，以前 648）', rt and rt['h'] <= 565, rt)
    pg.screenshot(path=os.path.join(OUT, 'r2_full.png'))
    pg.evaluate("document.querySelector('#np-right .subs').scrollTop = 0; NP.key = null"); pg.evaluate("npSubsDraw(qAudio)"); pg.wait_for_timeout(1500)
    on = pg.evaluate(Q, '#np-right .sub.on'); rt = pg.evaluate(Q, '#np-right')
    if on and rt: print('当前句位置', round((on['cy'] - rt['y']) / rt['h'], 3))
    pg.click('#np-min'); pg.wait_for_timeout(900)
    check('点左下角：退出全屏播放', pg.evaluate("document.querySelector('#np').hidden"))
    bar_back = pg.evaluate("NPL._L().bar"); print('bar', bar_back)
    # 视频页
    pg.evaluate("go('play')"); pg.wait_for_timeout(1200)
    pg.locator('#play-src button', has_text='视频').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='H264 720p').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.pause(); npOpen()"); pg.wait_for_timeout(1300)
    pb = pg.evaluate("(() => { const e = document.querySelector('#np .np-b.play'); return e && getComputedStyle(e).backgroundColor; })()")
    check(f'视频页：播放键没有白色大圆（{pb}）', pb in ('rgba(0, 0, 0, 0)', 'transparent'), pb)
    check('视频页：没有左下角的退出按钮（有自己的控制条）', not pg.evaluate(Q, '#np-min'))
    vv = pg.evaluate(Q, '#np-vol'); check(f'视频页：音量在右下角那组（11-18 方案 Y；{vv}）', vv and vv['w'] > 60 and pg.evaluate("document.querySelector('#np-vol').parentElement.id === 'np-vr'"), vv)
    pg.screenshot(path=os.path.join(OUT, 'r2_video.png'))
    pg.evaluate("npClose()"); pg.wait_for_timeout(600)
    pg.evaluate("NPL.open()"); pg.wait_for_timeout(300)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
