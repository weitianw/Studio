"""播放列表换歌时的滚动（2026-11-17 用户：换了之后回到最上面；应该从当前的平滑滚到新的）。
电脑全屏播放页的播放列表 + 底栏的播放列表面板；手机的播放列表视图。用法：python np_queue_glide.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import np_desk
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


# 换到第 k 首，每 40ms 记一次滚动位置；最后量正在播那行在列表里的位置（0 = 顶，1 = 底）
TRACE = r"""async ([sel, k]) => {
  const box = () => document.querySelector(sel + ' .ql-rows');
  const s0 = box().scrollTop; const tr = [];
  PB.q.i = k; qLoad();
  for (let i = 0; i < 25; i++) { tr.push(Math.round(box().scrollTop)); await new Promise(r => setTimeout(r, 40)); }
  const rows = box(), on = rows.querySelector('.ql-row.on'), r = rows.getBoundingClientRect(), o = on.getBoundingClientRect();
  return { s0: Math.round(s0), first: tr[0], tr, end: tr[tr.length - 1], pos: +((o.top + o.height / 2 - r.top) / r.height).toFixed(2), k: +on.dataset.k };
}"""


def judge(name, r, k):
    # 测试数据里有坏文件，播放器会自动跳到下一首：只看滚动本身（不倒退、分几步滚过去、最后停在 30% 左右），不要求正好是 k
    steps, tr = len(set(r['tr'])), r['tr']
    back = [(a, b) for a, b in zip(tr, tr[1:]) if (b - a) * (tr[-1] - tr[0]) < -2]
    check(f'{name}：不跳回最上面（换前 {r["s0"]}，换后第一帧 {r["first"]}）', r['first'] == r['s0'] or abs(r['first'] - r['s0']) < abs(r['end'] - r['s0']) * .5, r)
    check(f'{name}：平滑滚过去、中途不倒退（{steps} 个不同位置），正在播的那首停在 {r["pos"]}', not back and steps >= 4 and .15 < r['pos'] < .5, (back, r))


if __name__ == '__main__':
    with sync_playwright() as p:
        b, pg = np_desk.open_np(p)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.ui = { ...(S.ui || {}), npPanel: true }; NPL.paint()")
        pg.click('.np-tabs button[data-np="queue"]'); pg.wait_for_timeout(900)
        r0 = pg.evaluate("(() => { const rows = document.querySelector('#np-right .ql-rows'), on = rows.querySelector('.ql-row.on'), r = rows.getBoundingClientRect(), o = on.getBoundingClientRect(); return +((o.top + o.height / 2 - r.top) / r.height).toFixed(2); })()")
        check(f'打开播放列表：直接停在正在播的那首（{r0}）', .1 < r0 < .6, r0)
        judge('全屏播放页 下一首', pg.evaluate(TRACE, ['#np-right', pg.evaluate("PB.q.i") + 1]), pg.evaluate("PB.q.i") + 1)
        judge('全屏播放页 跳到第 120 首', pg.evaluate(TRACE, ['#np-right', 120]), 120)
        pg.evaluate("document.querySelector('#np-right .ql-rows').dispatchEvent(new WheelEvent('wheel', { deltaY: 100 }))")
        # 看的是“屏幕上的位置”：换歌时分组标题（正在播放 / 接下来播放）会移位，列表会补偿滚动距离让看到的行不动（2026-11-17），所以不比 scrollTop
        A = "(() => { const rows = document.querySelector('#np-right .ql-rows'), R = rows.getBoundingClientRect(); const e = [...rows.querySelectorAll('.ql-row[data-k]')].find(x => x.getBoundingClientRect().top >= R.top + 60); return e ? [e.dataset.k, Math.round(e.getBoundingClientRect().top)] : null; })()"
        a0 = pg.evaluate(A)
        r = pg.evaluate(TRACE, ['#np-right', 40])
        k1 = pg.evaluate("k => { const e = document.querySelector(`#np-right .ql-row[data-k=\"${k}\"]`); return e ? Math.round(e.getBoundingClientRect().top) : null; }", a0[0]) if a0 else None
        check(f'刚自己滚过列表：不抢位置（看到的行 {a0} → {k1}）', len(set(r['tr'])) <= 2 and a0 and k1 is not None and abs(k1 - a0[1]) <= 2, r)
        check('没有页面报错', not errs, errs)
        b.close()
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
        pg.evaluate("PB.a.pause(); npOpen(); npSetView('queue')"); pg.wait_for_timeout(1200)
        judge('手机 跳到第 60 首', pg.evaluate(TRACE, ['#np-right', 60]), 60)
        check('手机 没有页面报错', not errs, errs)
        br.close()
    print(f'通过 {ok}，失败 {bad}')
