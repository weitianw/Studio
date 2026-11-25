"""正在播放（方案 D + E，2026-11-17）：播放卡片 = 圆形封面 / 没封面时中性底 + 音符，不动；侧栏 = 音柱，只在播放卡片收起来且在播放时跳。不截图用户内容（图片藏起）。"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0
def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)
ST = """(() => { const c = document.querySelector('#pb-art > .now-cov'), d = document.querySelector('#pb-fab-art > .now-bars'), i = d && d.querySelector('.eq i'); const r = c && c.getBoundingClientRect(), q = d && d.getBoundingClientRect();
  return { card: !!c, round: c && getComputedStyle(c).borderRadius, cw: r && Math.round(r.width), bars: !!d, bw: q && Math.round(q.width), run: i && getComputedStyle(i).animationPlayState, orbs: document.querySelectorAll('#pbar .sorb, #pb-fab .sorb').length }; })()"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    for theme in ('dark', 'light'):
        pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(B + '/'); pg.wait_for_timeout(2200); pg.add_style_tag(content='img,video{visibility:hidden!important}')
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate(f"document.documentElement.dataset.theme = '{theme}'; go('play')"); pg.wait_for_timeout(1500)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("(e => { e.click(); e.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelectorAll('.pl-row[data-i] .pl-main')[5])"); pg.wait_for_timeout(1500); pg.evaluate("qAudio.muted = true; qAudio.loop = true; qAudio.play()"); pg.wait_for_timeout(600)
        pg.evaluate("pbMin(false, false)"); pg.wait_for_timeout(600); a = pg.evaluate(ST)
        pg.screenshot(path=os.path.join(tempfile.gettempdir(), f'now_{theme}_bar.png'))
        pg.evaluate("pbMin(true, false)"); pg.wait_for_timeout(600); m = pg.evaluate(ST)
        pg.screenshot(path=os.path.join(tempfile.gettempdir(), f'now_{theme}_min.png'))
        pg.evaluate("qAudio.pause()"); pg.wait_for_timeout(500); z = pg.evaluate(ST)
        print(theme, a, m, z)
        check(f'{theme}：卡片是圆形封面 / 音符（{a["round"]}，{a["cw"]}px），没有 Siri 球了', a['card'] and a['round'] in ('50%', '9999px') or (a['round'] or '').endswith('px') and a['orbs'] == 0, a)
        check(f'{theme}：卡片开着时侧栏音柱不动（{a["run"]}）', a['bars'] and a['run'] == 'paused')
        check(f'{theme}：卡片收起、在播放：侧栏音柱跳（{m["run"]}）', m['run'] == 'running')
        check(f'{theme}：暂停后音柱停（{z["run"]}）', z['run'] == 'paused')
        check(f'{theme}：没有页面报错', not errs, errs)
        pg.evaluate("pbMin(false, false)"); pg.close()
    b.close()
print(f'通过 {ok}，失败 {bad}')
