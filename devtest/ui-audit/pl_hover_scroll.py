"""滚动时文件行不亮（2026-11-17 用户：滚动时鼠标下面的文件不停高亮；参照 Google）。
电脑播放页的大文件夹：鼠标停在一行上 → 亮；滚轮滚动 → 滚动中鼠标下面的行不亮、列表照常滚；停手后鼠标下面那行亮；
鼠标快速划过：刚进入 30 毫秒时还没亮。用法：python pl_hover_scroll.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


BG = "([x, y]) => { const e = document.elementFromPoint(x, y)?.closest('.pl-row'); const h = document.querySelector('.pl-row:hover'); return { under: !!e, hover: h ? h.dataset.i : null, bg: h ? getComputedStyle(h).backgroundColor : null, scrolling: document.documentElement.classList.contains('is-scrolling'), top: Math.round(document.querySelector('.pl-rows').scrollTop) }; }"

if __name__ == '__main__':
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/'); pg.wait_for_timeout(2500)
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("document.querySelectorAll('img, video').forEach(e => e.style.visibility = 'hidden')")
        r = pg.evaluate("(() => { const e = document.querySelectorAll('.pl-row[data-i]')[4].getBoundingClientRect(); return [e.x + e.width / 2, e.y + e.height / 2]; })()")
        x, y = r
        pg.mouse.move(x, y - 60); pg.wait_for_timeout(300); pg.mouse.move(x, y); pg.wait_for_timeout(30)
        early = pg.evaluate(BG, [x, y])
        pg.wait_for_timeout(400)
        late = pg.evaluate(BG, [x, y])
        check(f'快速划过时不闪：进入 30 毫秒还没亮（{early["bg"]}），停住后亮（{late["bg"]}）', early['hover'] is not None and early['bg'] != late['bg'], (early, late))
        pg.mouse.wheel(0, 300); pg.wait_for_timeout(60)
        mid = pg.evaluate(BG, [x, y])
        check(f'滚动中：鼠标下面的行不亮（{mid["bg"]}），列表照常滚（{late["top"]} → {mid["top"]}）', mid['scrolling'] and mid['bg'] in (None, 'rgba(0, 0, 0, 0)') and mid['top'] > late['top'], mid)
        for _ in range(4):
            pg.mouse.wheel(0, 200); pg.wait_for_timeout(80)
        mid2 = pg.evaluate(BG, [x, y])
        check('连续滚动中一直不亮', mid2['scrolling'] and mid2['bg'] in (None, 'rgba(0, 0, 0, 0)'), mid2)
        pg.wait_for_timeout(500); pg.mouse.move(x + 3, y)
        pg.wait_for_timeout(400)
        end = pg.evaluate(BG, [x, y])
        check(f'停手后：鼠标下面那行亮（{end["hover"]}）', not end['scrolling'] and end['hover'] is not None, end)
        pg.mouse.dblclick(x, y); pg.wait_for_timeout(300)  # 电脑上双击播放（2026-11-17）
        check('停手后点文件照常能点', pg.evaluate("!!document.querySelector('.pl-row.on, .pl-row.cur, .pl-row[aria-current]') || !!PB.a"))
        # F22：滚完立刻点（220 毫秒内）：播放、选中文件夹、从播放列表移除都要生效
        pg.mouse.wheel(0, 200); pg.wait_for_timeout(40)
        r2 = pg.evaluate("(() => { const e = [...document.querySelectorAll('.pl-row[data-i] .pl-main')].find(x => { const r = x.getBoundingClientRect(); return r.top > 120 && r.bottom < innerHeight - 120; }); const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2, e.closest('.pl-row').dataset.i]; })()")
        pg.evaluate("window.__k = PB.q ? PB.q.i : -1")
        pg.mouse.dblclick(r2[0], r2[1]); pg.wait_for_timeout(400)
        check('滚完立刻点文件：开始播放这一首', pg.evaluate("document.documentElement.classList.contains('is-scrolling')") is False and pg.evaluate("!!PB.q && PB.q.items[PB.q.i] && document.querySelector('.pl-row.on')?.dataset.i === arguments[0]".replace('arguments[0]', repr(str(r2[2])))))
        pg.evaluate("qPanelToggle()"); pg.wait_for_timeout(500)
        n0 = pg.evaluate("PB.q.items.length")
        x = pg.evaluate("(() => { const box = document.querySelector('#qpanel .ql-rows').getBoundingClientRect(); const e = [...document.querySelectorAll('#qpanel .ql-row:not(.on)')].find(r => { const q = r.getBoundingClientRect(); return q.top > box.top + 4 && q.bottom < box.bottom - 4; }); e.querySelector('.ql-x').style.opacity = 1; const r = e.querySelector('.ql-x').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")  # 看得见的一行（列表已经滚到正在播的那首）
        pg.mouse.move(300, 500); pg.mouse.wheel(0, 120); pg.wait_for_timeout(30)  # 在别处滚一下，马上去点（还在“滚动中”）
        on = pg.evaluate("document.documentElement.classList.contains('is-scrolling')")
        pg.mouse.click(x[0], x[1]); pg.wait_for_timeout(400)
        check('点的时候还在“滚动中”', on)
        check(f'滚完立刻点播放列表的“移除”：少了一首（{n0} → {pg.evaluate("PB.q.items.length")}）', pg.evaluate("PB.q.items.length") == n0 - 1)
        pg.evaluate("qPanelClose()"); pg.wait_for_timeout(300)
        t = pg.evaluate("(() => { const e = [...document.querySelectorAll('#play-src .ps-item')].find(x => !x.classList.contains('on')); if (!e) return null; const r = e.getBoundingClientRect(); return [r.x + 30, r.y + r.height / 2]; })()")
        if t:
            pg.mouse.move(t[0], t[1]); pg.mouse.wheel(0, 60); pg.wait_for_timeout(30)
            pg.mouse.click(t[0], t[1]); pg.wait_for_timeout(600)
            check('滚完立刻点左边的文件夹：选中了', pg.evaluate("(() => { const e = document.elementFromPoint(%s, %s)?.closest('.ps-item'); return !!e && e.classList.contains('on'); })()" % (t[0], t[1])))
        check('没有页面报错', not errs, errs)
        b.close()
    print(f'通过 {ok}，失败 {bad}')
