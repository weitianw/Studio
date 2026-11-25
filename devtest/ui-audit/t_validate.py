"""检查规则自己的测试：把以前漏掉的那几类 bug 故意放回页面，看 audit2 的规则能不能抓到（抓不到 = 规则没用）"""
import os, sys, json
SP = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(SP, 'audit2.py'), encoding='utf-8').read().split("R = {'profile'")[0]
sys.argv = ['x', 'ph440']; ns = {'__file__': os.path.join(SP, 'audit2.py')}; exec(compile(src, 'audit2', 'exec'), ns)
CHECK, B, EXE, INIT = ns['CHECK'], ns['B'], ns['EXE'], ns['INIT']
from playwright.sync_api import sync_playwright
IPH = ns['IPH']
CASES = [  # (名字, 视口, 手机, 页面, 注入的 bug, 应该出现的规则)
    ('标题被返回键挤到右边', (440, 956), True, 'tts', "() => { const h = document.querySelector('#main > .page-head'), w = h.querySelector('.pg-titlew'); h.style.setProperty('display', 'flex', 'important'); h.style.setProperty('justify-content', 'space-between', 'important');  /* 11-17：新标题栏用 !important 排成三栏，注入也要 important 才真的把标题挤偏 */ const t = h.querySelector('.page-title'); if (t) t.style.setProperty('margin-left', 'auto', 'important'); [...w.childNodes].forEach(n => h.insertBefore(n, w)); w.remove(); }", 'title'),
    ('短按钮文字折两行', (900, 700), False, 'audioedit', "() => { const s = document.createElement('style'); s.textContent = '#ae-kind { width: 250px !important; } #ae-kind > button { white-space: normal !important; flex: 1 1 0 !important; padding: 0 2px !important; }'; document.head.append(s); }", 'wrap'),
    ('小组件独占一行', (900, 700), False, 'video', "() => { vidState().mode = 'gen'; const r = document.createElement('div'); r.style.cssText = 'display:flex;margin:8px 0'; const b = document.createElement('button'); b.className = 'btn small'; b.textContent = '中文'; r.append(b); document.querySelector('.ig-top-f').prepend(r); }", 'lonerow'),
    ('两个固定控件叠在一起', (956, 440), True, 'tts', "() => { const s = document.createElement('style'); s.textContent = '.rnav { margin-bottom: 0 !important; } html:not(.rail-wide) .rnav .cat-b > span { display: inline !important; } .rnav .cat-b { min-height: 64px !important; }'; document.head.append(s); }", 'fixedclash'),
    ('没用的小滚动条', (1920, 1080), False, 'vc', "() => { const d = document.createElement('div'); d.style.cssText = 'height:120px;overflow:auto;background:#333'; d.innerHTML = '<div style=\"height:140px\">x</div>'; document.querySelector('#main').prepend(d); }", 'tinyscroll'),
    ('伸出屏幕', (440, 956), True, 'vc', "() => { const d = document.createElement('div'); d.textContent = '很宽的一行'; d.style.cssText = 'width:520px;background:#333'; document.querySelector('#main').prepend(d); }", 'offscreen'),
    ('内容比屏幕宽（整页被缩小）', (440, 956), True, 'tts', "() => { const s = document.createElement('style'); s.textContent = 'html, body, #main { overflow: visible !important; }'; document.head.append(s); const d = document.createElement('div'); d.style.cssText = 'width:700px;height:40px;background:#444'; document.querySelector('#main').prepend(d); }", 'zoomout'),
    ('文字压文字', (1920, 1080), False, 'tts', "() => { const t = [...document.querySelectorAll('#main .card *')].find(e => e.children.length === 0 && e.textContent.trim() === '文本'); const d = document.createElement('span'); d.textContent = '重叠的文字'; d.style.cssText = 'margin-left:-26px;position:relative'; t.after(d); }", 'overlap'),
    ('选项只露出一半', (900, 700), False, 'img', "() => { const s = document.createElement('style'); s.textContent = '.ig-top-f > .ig-cbar > .bar-l .ig-chip > span, .ig-top-f > .ig-cbar > .bar-l .ig-cb > span { display: inline !important; } .ig-top-f > .ig-cbar > .bar-l, .ig-top-f > .ig-cbar > .bar-l.wr { flex-wrap: nowrap !important; overflow: hidden !important; }'; document.head.append(s); }", 'halfcut'),
]
out = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    for name, (w, h), mob, page, js, want in CASES:
        kw = dict(viewport={'width': w, 'height': h}, color_scheme='dark')
        if mob: kw.update(is_mobile=True, has_touch=True, user_agent=IPH)
        ctx = b.new_context(**kw)
        if not mob: ctx.add_init_script(INIT)
        pg = ctx.new_page(); pg.route('**/*', lambda r: r.abort() if not r.request.url.startswith(B) else r.continue_())
        pg.goto(B + '/play'); pg.wait_for_timeout(1200)
        if not mob: pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
        pg.evaluate(f"go('{page}')"); pg.wait_for_timeout(1300); pg.evaluate(f"go('{page}')"); pg.wait_for_timeout(300)  # 第二次：返回键出现
        before = {f['kind'] for f in pg.evaluate(CHECK, {'W': w, 'H': h, 'mobile': mob, 'fixedPage': False, 'atBottom': True})['F']}
        pg.evaluate(js); pg.wait_for_timeout(500)
        after = pg.evaluate(CHECK, {'W': w, 'H': h, 'mobile': mob, 'fixedPage': False, 'atBottom': True})['F']
        got = want in {f['kind'] for f in after}
        out.append((name, want, '抓到了' if got else '没抓到 !!!', '（注入前就有）' if want in before else '', [f['kind'] + ' ' + f['el'][:40] for f in after if f['kind'] not in ('ellipsis', 'small')][:6] if (not got or want in before) else ''))
        pg.screenshot(path=os.path.join(SP, 'sheets', 'val_' + want + '.png'))
        ctx.close()
    b.close()
sys.stdout.reconfigure(encoding='utf-8')
for o in out: print(*o)
