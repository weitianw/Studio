"""P09 测量：配音页长稿（2 万字）里连续打 200 个字，看每次按键的输入处理耗时、写本地存储次数和写入总量；
再验证：停手后写进去了、刷新后草稿还在、失焦立刻写、换页立刻写。
用法：python bench_p09.py [--old] [--big]
  --old：配音框换回修复前的处理函数（每次按键同步 persist()，和 17349db 的代码一样）
  --big：状态里再放 1.5 MB 的 AI 对话记录（长期用下来的规模）"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
OLD, BIG = '--old' in sys.argv, '--big' in sys.argv
INIT = """(() => {
  const set = Storage.prototype.setItem; window.__w = { n: 0, bytes: 0 };
  Storage.prototype.setItem = function (k, v) { if (this === localStorage && k === 'studio') { __w.n++; __w.bytes += String(v).length; } return set.call(this, k, v); };
  window.__ev = []; let t0 = 0;
  addEventListener('input', () => { t0 = performance.now(); }, true);
  addEventListener('input', () => { __ev.push(performance.now() - t0); }, false);
})()"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}, service_workers='block')
    pg = ctx.new_page(); pg.add_init_script(INIT)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('tts')"); pg.wait_for_timeout(1200)
    if BIG:
        pg.evaluate("S.pgHist = Array.from({ length: 300 }, (_, k) => ({ id: 'h' + k, title: '测试对话 ' + k, msgs: [{ role: 'user', content: '测'.repeat(2500) }] })); persist()")
    if OLD:
        pg.evaluate("(() => { const ta = document.querySelector('#script'); ta.oninput = () => { S.text = ta.value; persist(); updateStat(); }; })()")
    long = ('这是一段用来测试的长稿，句子不断重复以模拟真实的长篇配音文本。' * 1100)[:20000]
    pg.evaluate("t => { const ta = document.querySelector('#script'); ta.value = t; ta.oninput(); }", long)
    pg.evaluate("document.querySelector('#script').blur()"); pg.wait_for_timeout(800)
    size = pg.evaluate("localStorage.getItem('studio').length")
    pg.evaluate("__w.n = 0; __w.bytes = 0; __ev.length = 0")
    pg.click('#script'); pg.keyboard.press('Control+End')
    pg.keyboard.type('a' * 200, delay=15)
    typed = pg.evaluate("[__w.n, __w.bytes, __ev.slice()]")
    pg.wait_for_timeout(900)
    after_idle = pg.evaluate("[__w.n, JSON.parse(localStorage.getItem('studio')).text.endsWith('a'.repeat(200))]")
    ev = sorted(typed[2])
    print(f'{"修复前（同步写）" if OLD else "修复后"}：状态 {size / 1024:.0f} KB，打 200 个字')
    print(f'  每次按键输入处理 p50 {ev[len(ev) // 2]:.2f} ms / p95 {ev[int(len(ev) * .95)]:.2f} ms / 最大 {ev[-1]:.2f} ms')
    print(f'  打字过程中写本地存储 {typed[0]} 次，共 {typed[1] / 2**20:.1f} MiB；停手 0.9 秒后共 {after_idle[0]} 次，内容已是最新 {after_idle[1]}')
    # 失焦立刻写
    pg.keyboard.type('b'); n0 = pg.evaluate("__w.n"); pg.evaluate("document.querySelector('#script').blur()")
    blur_ok = pg.evaluate("JSON.parse(localStorage.getItem('studio')).text.endsWith('b')")
    # 换页立刻写
    pg.click('#script'); pg.keyboard.press('Control+End'); pg.keyboard.type('c'); pg.evaluate("go('play')")
    go_ok = pg.evaluate("JSON.parse(localStorage.getItem('studio')).text.endsWith('c')")
    # 打完马上刷新：草稿还在
    pg.evaluate("go('tts')"); pg.wait_for_timeout(600); pg.click('#script'); pg.keyboard.press('Control+End'); pg.keyboard.type('d')
    pg.reload(); pg.wait_for_timeout(2500); pg.evaluate("go('tts')"); pg.wait_for_timeout(800)
    reload_ok = pg.evaluate("document.querySelector('#script').value.endsWith('d')")
    print(f'  失焦立刻写 {blur_ok}，换页立刻写 {go_ok}，打完马上刷新草稿还在 {reload_ok}')
    # 恢复：清掉测试稿
    pg.evaluate("(() => { const ta = document.querySelector('#script'); ta.value = ''; ta.oninput(); S.pgHist = []; persist(); ta.blur(); })()")
    print('  页面报错', errs or '无')
    b.close()
