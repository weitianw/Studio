"""书签（2026-11-18 用户：音视频都能记住某个进度，不要太显眼）。
音频（音乐/长音频）：30 秒处按 B → 进度条（底栏、全屏播放页）上出现小点、位置对；跳到别处后点小点回到 30 秒；
右上角 ⋯ 里有“添加书签”和“书签（1）”二级菜单；刷新后还在；右键小点 → 删除。视频（视频/H264 720p）也能加。用法：python t_marks.py"""
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


def play(pg, folder, name):
    pg.evaluate("go('play')"); pg.wait_for_timeout(1200)
    pg.locator('#play-src button', has_text=folder).first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text=name).first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("document.body.classList.contains('pb-min') && pbMin(false)"); pg.wait_for_timeout(500)  # 播放条收成小圆钮时看不到进度条


DOTS = """sel => [...document.querySelectorAll(sel + ' .mk-box .mk')].map(m => { const r = m.getBoundingClientRect(), t = m.closest(sel).getBoundingClientRect(); return { t: +m.dataset.mk, x: (r.left + r.width / 2 - t.left) / t.width, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }; })"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    pg.evaluate("S.ui = { ...(S.ui || {}), marks: {} }; persist()")
    play(pg, '音乐', '长音频')
    pg.evaluate("qAudio.pause(); qAudio.currentTime = 30"); pg.wait_for_timeout(500)
    pg.mouse.click(1000, 300); pg.keyboard.press('b'); pg.wait_for_timeout(500)
    toast = pg.evaluate("[...document.querySelectorAll('.toast')].map(t => t.textContent).join('|')")
    check(f'按 B：提示“已添加书签 0:30”（{toast}）', '已添加书签 0:30' in toast)
    d = pg.evaluate(DOTS, '#pb-track'); dur = pg.evaluate("qAudio.duration")
    check(f'底栏进度条上有一个小点、位置对（{d}）', len(d) == 1 and abs(d[0]['x'] - 30 / dur) < .01, d)
    pg.evaluate("qAudio.currentTime = 80"); pg.wait_for_timeout(400)
    pg.mouse.click(d[0]['cx'], d[0]['cy']); pg.wait_for_timeout(500)
    t = pg.evaluate("qAudio.currentTime"); check(f'点小点：跳回 30 秒（{t:.1f}）', abs(t - 30) < .3)
    pg.evaluate("npOpen()"); pg.wait_for_timeout(1200)
    d2 = pg.evaluate(DOTS, '#np-track'); check(f'全屏播放页的进度条上也有（{len(d2)}）', len(d2) == 1 and abs(d2[0]['x'] - 30 / dur) < .01, d2)
    pg.evaluate("qAudio.currentTime = 60"); pg.wait_for_timeout(300)
    pg.click('#np-more2'); pg.wait_for_timeout(400)
    top = pg.evaluate("[...document.querySelectorAll('.ctx-menu:not(.ctx-subm) .ctx-i')].map(e => e.textContent.trim())")
    check(f'右上角 ⋯：有“添加书签”和“书签（1）”（{top}）', any('添加书签' in x for x in top) and any('书签（1）' in x for x in top))
    pg.hover("xpath=//div[contains(@class,'ctx-menu') and not(contains(@class,'ctx-subm'))]//div[contains(@class,'ctx-i')][contains(normalize-space(.),'书签（1）')]"); pg.wait_for_timeout(300)
    sub = pg.evaluate("[...document.querySelectorAll('.ctx-subm .ctx-i')].map(e => e.textContent.trim())")
    check(f'“书签（1）”展开：0:30 和“全部删除”（{sub}）', '0:30' in sub and '全部删除' in sub)
    pg.screenshot(path=os.path.join(OUT, 'marks_menu.png'))
    pg.evaluate("[...document.querySelectorAll('.ctx-subm .ctx-i')].find(e => e.textContent.trim() === '0:30').click()"); pg.wait_for_timeout(400)
    t = pg.evaluate("qAudio.currentTime"); check(f'点 0:30：跳过去（{t:.1f}）', abs(t - 30) < .3)
    pg.evaluate("persistFlush?.()"); pg.reload(); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    play(pg, '音乐', '长音频'); pg.evaluate("qAudio.pause()"); pg.wait_for_timeout(600)
    d = pg.evaluate(DOTS, '#pb-track'); check('刷新后书签还在', len(d) == 1 and d[0]['t'] == 30, d)
    pg.mouse.click(d[0]['cx'], d[0]['cy'], button='right'); pg.wait_for_timeout(300)
    pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => e.textContent.includes('删除书签')).click()"); pg.wait_for_timeout(400)
    check('右键 → 删除书签：小点没了', not pg.evaluate(DOTS, '#pb-track'))
    # 视频
    play(pg, '视频', 'H264 720p'); pg.evaluate("qAudio.pause(); qAudio.currentTime = 2"); pg.wait_for_timeout(500)
    pg.mouse.click(1000, 300); pg.keyboard.press('b'); pg.wait_for_timeout(500)
    d = pg.evaluate(DOTS, '#pb-track'); check(f'视频也能加书签（{d}）', len(d) == 1 and d[0]['t'] == 2, d)
    check('在输入框里按 B 不加书签', pg.evaluate("""(() => { const i = document.querySelector('#play-q, .page-head input, input[type=search]'); if (!i) return true; i.focus();
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', bubbles: true })); return true; })()""") and len(pg.evaluate(DOTS, '#pb-track')) == 1)
    pg.evaluate("S.ui = { ...(S.ui || {}), marks: {} }; persist()")
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
