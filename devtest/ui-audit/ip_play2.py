"""播放页四件事（2026-11-16 用户）：标题栏下面没有多一层；文件很多的文件夹里重画列表不会回到最上面；“回到正在播放的文件”按钮；
按下高亮晚 0.12 秒（量样式）。模拟 iPhone 16 Pro Max，用测试数据里的“很多文件（400 个）”文件夹，声音静音、视频不加载。用法：python ip_play2.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'play'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


def folder(pg, nm):
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
    pg.evaluate(f"[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && x.textContent.includes({nm!r}))?.click()"); pg.wait_for_timeout(1800); hide(pg)


ROWTOP = "(i => { const r = document.querySelector(`#play-list .pl-row[data-i=\"${i}\"]`); return r ? Math.round(r.getBoundingClientRect().top) : null; })"

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        folder(pg, '很多文件')
        # 1 标题栏实色
        hb = pg.evaluate("getComputedStyle(document.querySelector('#main > .page-head')).backgroundImage + ' | ' + getComputedStyle(document.querySelector('#main > .page-head')).backgroundColor")
        check('标题栏是实色（下面不再有渐隐、透出后面的卡片）', hb.startswith('none'), hb)
        # 2 滚到下面，点一首播放（列表会重画），位置不能丢
        pg.evaluate("scrollTo(0, 9000)"); pg.wait_for_timeout(800)
        i = pg.evaluate("(() => { const rs = [...document.querySelectorAll('#play-list .pl-row[data-i]')].filter(r => { const b = r.getBoundingClientRect(); return b.top > 250 && b.bottom < innerHeight - 200; }); return rs.length ? +rs[0].dataset.i : null; })()")
        y0 = pg.evaluate("scrollY"); t0 = pg.evaluate(ROWTOP, i)
        pg.evaluate(f"document.querySelector('#play-list .pl-row[data-i=\"{i}\"] .pl-main')?.click()"); pg.wait_for_timeout(1500)
        y1 = pg.evaluate("scrollY"); t1 = pg.evaluate(ROWTOP, i)
        check(f'文件很多的文件夹：滚到下面点一首（列表重画），页面不跳（{y0}→{y1}）', i is not None and abs(y1 - y0) <= 2 and t1 is not None and abs(t1 - t0) <= 2, (i, y0, y1, t0, t1))
        pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })"); pg.wait_for_timeout(600)
        # 2b 后台有任务 / 音源库变了：整页自动重画（renderPlay(true)），位置不能丢（真正让用户“莫名回到最上面”的那个）
        pg.evaluate("scrollTo(0, 9000)"); pg.wait_for_timeout(600); y0 = pg.evaluate("scrollY")
        pg.evaluate("renderPlay(true)"); pg.wait_for_timeout(2500); y1 = pg.evaluate("scrollY")
        check(f'后台自动刷新整页：文件很多的文件夹里滚到的位置不丢（{y0}→{y1}）', abs(y1 - y0) <= 2, (y0, y1))
        # 3 回到正在播放的：按钮在，滚到最上面再点它 → 那一行回到屏幕里，还亮一下
        lb = pg.evaluate("(() => { const b = document.querySelector('#main > .page-head > .ph-locate'); return b ? [!b.hidden, Math.round(b.getBoundingClientRect().width), getComputedStyle(b).gridColumnStart] : null; })()")
        check('有播放栏时：标题栏右边有“回到正在播放的文件”', lb and lb[0] and lb[1] == 44, lb)
        pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(500)
        b = pg.query_selector('#main > .page-head > .ph-locate').bounding_box(); pg.touchscreen.tap(b['x'] + 22, b['y'] + 22); pg.wait_for_timeout(1300)
        t2 = pg.evaluate(ROWTOP, i); fl = pg.evaluate(f"!!document.querySelector('#play-list .pl-row[data-i=\"{i}\"].pl-flash')")
        check('点一下：滚回那一首（在屏幕中间附近）、那一行亮一下', t2 is not None and 150 < t2 < pg.viewport_size['height'] - 200 and fl, (t2, fl))
        pg.screenshot(path=os.path.join(OUT, 'locate.png'))
        # 4 在别的文件夹里点它：打开那首所在的文件夹再滚过去
        folder(pg, '很深')
        pg.wait_for_timeout(300); b = pg.query_selector('#main > .page-head > .ph-locate')
        if b and b.bounding_box():
            bb = b.bounding_box(); pg.touchscreen.tap(bb['x'] + 22, bb['y'] + 22); pg.wait_for_timeout(1800)
            t3 = pg.evaluate(ROWTOP, i)
            check('在别的文件夹里点：打开那首所在的文件夹、滚到那一首', pg.evaluate("document.querySelector('#play-list .card-title')?.textContent || ''").find('很多文件') >= 0 and t3 is not None and 0 < t3 < pg.viewport_size['height'], (pg.evaluate("document.querySelector('#play-list .card-title')?.textContent"), t3))
        else:
            check('在别的文件夹里也有这个按钮', False)
        # 5 按下高亮晚 0.12 秒：规则在
        d = pg.evaluate("""(() => { for (const sh of document.styleSheets) { try { for (const r of sh.cssRules) if (r.selectorText && r.selectorText.includes('.pl-row') && r.selectorText.includes(':active:not(.ph-press)') && r.style.transitionDelay) return r.style.transitionDelay; } catch {} } return null; })()""")
        check('列表行、格子：:active 的样子不出现，改由 phone.js 的 .ph-press（手指不动 0.2 秒才亮，ip_pltree 里量）', d == '600s', d)
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
