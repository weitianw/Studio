"""P07 回归（2026-11-17 审查）：播放列表改成“只重画两行 + 事件委托 + 看不见的行不排版”之后，
全屏播放页右侧和底栏弹出的播放列表：点一首播放、移除、拖动排序、随机 / 循环按钮、手动滚动后 3 秒内不抢位置、换歌自动跟随、
列表内容变了（移除、排序）照样整表更新。不放真实音频（qLoad 换成只重画）。用法：python queue_regress.py"""
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


SETUP = """(() => {
  const items = Array.from({ length: 400 }, (_, k) => ({ title: '测试曲目 ' + k, sub: '合成', src: '/x/' + k + '.wav', key: 'k' + k }));
  PB.q = { items, orig: items.slice(), i: 0 }; window.qLoad = () => qPanelPaint();
})()"""
ROWS = lambda box: f"document.querySelector('{box} .ql-rows')"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("document.querySelectorAll('img, video').forEach(e => e.style.visibility = 'hidden')")
    pg.evaluate(SETUP)
    for box, open_js in (('#np-right', "if ($('#np').hidden) npOpen(); NP.tab = 'queue'; npPaint(true); qPanelPaint();"), ('#qpanel', "npClose && npClose(true); qPanelToggle();")):
        print(box)
        pg.evaluate(SETUP); pg.evaluate(f"(() => {{ {open_js} }})()"); pg.wait_for_timeout(900)
        R = ROWS(box)
        check('400 行都在', pg.evaluate(f"{R}.children.length") == 400)
        # 点第 3 行：开始放这一首
        pg.click(f'{box} .ql-row[data-k="3"] .ql-main'); pg.wait_for_timeout(300)
        check('点一行 → 播放这一首（正在放的那行跟着换）', pg.evaluate(f"PB.q.i === 3 && {R}.querySelector('.ql-row.on').dataset.k === '3' && {R}.querySelectorAll('.ql-row.on').length === 1"))
        same = pg.evaluate(f"(() => {{ window.__rows = {R}; PB.q.i = 4; qPanelPaint(); return window.__rows === {R} && {R}.querySelectorAll('.ql-row.on').length === 1 && !!{R}.querySelector('.ql-row[data-k=\"4\"] .eq'); }})()")
        check('换歌只换行：列表本身不重建，音柱跟着走', same)
        # 移除第 5 行
        pg.hover(f'{box} .ql-row[data-k="5"]'); pg.wait_for_timeout(150)
        t5 = pg.evaluate("PB.q.items[5].title")
        pg.click(f'{box} .ql-row[data-k="5"] .ql-x', force=True); pg.wait_for_timeout(300)
        check(f'移除一首：399 首，列表里也没了', pg.evaluate("PB.q.items.length") == 399 and pg.evaluate(f"{R}.children.length") == 399 and t5 not in pg.evaluate(f"[...{R}.querySelectorAll('.ql-t')].slice(0, 12).map(e => e.textContent).join('|')"))
        # 拖动：把第 1 行拖到第 7 行下面
        t1 = pg.evaluate("PB.q.items[1].title")
        src = pg.locator(f'{box} .ql-row[data-k="1"]'); dst = pg.locator(f'{box} .ql-row[data-k="7"]')
        bb = dst.bounding_box()
        src.drag_to(dst, target_position={'x': 40, 'y': bb['height'] - 6}); pg.wait_for_timeout(400)
        pos = pg.evaluate(f"PB.q.items.findIndex(x => x.title === {t1!r})")
        check(f'拖动排序：第 1 首拖到第 7 首后面（现在在第 {pos} 位），列表跟着更新', pos == 7 and pg.evaluate(f"{R}.children[7].querySelector('.ql-t').textContent.includes({t1!r})"))
        # 随机 / 循环按钮（委托）
        r0 = pg.evaluate("S.qmode.repeat"); pg.click(f'{box} [data-qm="repeat"]'); pg.wait_for_timeout(250)
        check('循环按钮能点', pg.evaluate("S.qmode.repeat") != r0)
        pg.click(f'{box} [data-qm="repeat"]'); pg.click(f'{box} [data-qm="repeat"]'); pg.wait_for_timeout(250)
        # 手动滚动后 3 秒内不抢位置；之后换歌自动跟随到正在放的那首
        pg.hover(f'{box} .ql-row[data-k="2"]'); pg.mouse.wheel(0, 900); pg.wait_for_timeout(400)
        VIS = f"(() => {{ const R = {R}, b = R.getBoundingClientRect().top; const r = [...R.children].find(x => x.getBoundingClientRect().bottom > b + 60); return [r.dataset.k, Math.round(r.getBoundingClientRect().top)]; }})()"
        v0 = pg.evaluate(VIS)
        pg.evaluate("PB.q.i = 300; qPanelPaint()"); pg.wait_for_timeout(900)
        v1 = pg.evaluate(f"(() => {{ const r = {R}.querySelector('.ql-row[data-k=\"' + {v0[0]!r} + '\"]'); return [r.dataset.k, Math.round(r.getBoundingClientRect().top)]; }})()")
        check(f'刚手动滚过：换歌不抢位置（看得见的那行 {v0} → {v1}）', abs(v1[1] - v0[1]) < 2)
        pg.wait_for_timeout(2600)
        pg.evaluate("PB.q.i = 320; qPanelPaint()"); pg.wait_for_timeout(1000)
        vis = pg.evaluate(f"(() => {{ const r = {R}.getBoundingClientRect(), o = {R}.querySelector('.ql-row.on').getBoundingClientRect(); return [o.top >= r.top && o.bottom <= r.bottom, Math.round((o.top - r.top) / r.height * 100)]; }})()")
        check(f'3 秒后换歌：平滑跟到正在放的那首（在列表 {vis[1]}% 高度）', vis[0], vis)
        # 内容变了（随机）→ 整表更新
        pg.click(f'{box} [data-qm="shuffle"]'); pg.wait_for_timeout(400)
        check('随机播放：列表按新顺序整表更新', pg.evaluate(f"[...{R}.querySelectorAll('.ql-t')].slice(0, 400).every((e, k) => e.textContent.includes(PB.q.items[k].title))"))
        pg.click(f'{box} [data-qm="shuffle"]'); pg.wait_for_timeout(300)
        if box == '#np-right':  # 从字幕切回播放列表：直接停在正在放的那首（约 30% 高度）
            pcts = []
            for k in (200, 350, 30):
                pg.click('#np .np-tabs button[data-np="subs"]'); pg.wait_for_timeout(700)
                pg.evaluate(f"PB.q.i = {k}"); pg.click('#np .np-tabs button[data-np="queue"]'); pg.wait_for_timeout(1000)
                pcts.append(pg.evaluate(f"(() => {{ const r = {R}.getBoundingClientRect(), o = {R}.querySelector('.ql-row.on').getBoundingClientRect(); return Math.round((o.top - r.top) / r.height * 100); }})()"))
            check(f'切回播放列表：正在放的那首停在约 30% 高度（{pcts}）', all(15 <= x <= 40 for x in pcts[:2]) and 0 <= pcts[2] <= 40, pcts)
        if box == '#qpanel':
            pg.evaluate("qPanelClose()")
    check('没有页面报错', not errs, errs)
    b.close()
print(f'通过 {ok}，失败 {bad}')
