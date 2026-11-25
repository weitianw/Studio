"""“参考图先提取衣服”开关（2026-11-16）：Qwen 2.1 + 局部重画 + 放一张参考图 → 参考图那一栏出现开关；点了记住、生成请求带 ref_extract。
电脑 1440 宽（选项栏展开）和 iPhone 16 Pro Max 各看一次。只用自己画的格子图，截图前藏起图库。用法：python ip_xref.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_xref'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
GRID = os.path.join(HERE, 'aud_grid.png')
HIDE = "document.querySelectorAll('.ig-gal img, .ig-gal video, #ig-live img, .b5-stage img:not(#ig-src img)').forEach(e => e.style.visibility = 'hidden')"
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


def flow(pg, tag):
    pg.evaluate("go('img')"); pg.wait_for_selector('#ig-model', state='attached', timeout=60000); pg.wait_for_timeout(1500)
    pg.evaluate("S.img.refX = false")
    pg.evaluate("document.querySelector('#ig-model').click()"); pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('.igm-v[data-m=\"q21\"]').click()"); pg.wait_for_timeout(1200)
    pg.query_selector('input[type=file]').set_input_files(GRID); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('#ig-mode button[data-k=\"inpaint\"]')?.click()"); pg.wait_for_timeout(1000)
    check(f'{tag}：没放参考图时没有开关', not pg.query_selector('#ig-xref'))
    pg.query_selector('#ig-ref-file').set_input_files(GRID); pg.wait_for_timeout(1500)
    x = pg.query_selector('#ig-xref')
    check(f'{tag}：放了参考图出现“先提取衣服”开关', bool(x))
    if not x:
        return
    if tag == '手机':  # 手机：参考图在原图那一格的面板里（从底部升起）
        pg.evaluate("document.querySelector('.ig-srct')?.click()"); pg.wait_for_timeout(900)
    pg.evaluate("document.querySelector('#ig-xref').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(300)
    lab = pg.query_selector('label.ig-xref'); bb = lab.bounding_box()
    need = 32 if tag == '手机' else 20
    check(f'{tag}：开关看得见、能点到（≥ {need} 高）', bb and bb['height'] >= need and pg.evaluate("(() => { const r = document.querySelector('label.ig-xref .switch').getBoundingClientRect(); const e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return !!e?.closest('label.ig-xref'); })()"), bb)
    if tag == '手机':
        pg.touchscreen.tap(bb['x'] + bb['width'] - 20, bb['y'] + bb['height'] / 2)
    else:
        pg.click('label.ig-xref .switch')
    pg.wait_for_timeout(500)
    check(f'{tag}：点了打开、记住（S.img.refX）', pg.evaluate("document.querySelector('#ig-xref').checked && S.img.refX === true"))
    check(f'{tag}：悬停说明写了用途', '肤色' in (lab.get_attribute('data-tip') or ''))
    pg.evaluate(HIDE); hide(pg) if tag == '手机' else None
    pg.screenshot(path=os.path.join(OUT, f'{tag}.png'))
    # 生成请求里带 ref_extract（拦下请求，不真的生成）
    got = {}
    pg.route('**/api/img/jobs', lambda r: r.continue_() if r.request.method != 'POST' else (got.update(json.loads(r.request.post_data or '{}')), r.fulfill(status=200, content_type='application/json', body='{"error":"测试拦截"}')))
    if tag == '手机':
        pg.evaluate("window.phSheet?.close?.()"); pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
    pg.evaluate("(() => { const g = IMG_MASK.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(100, 100, 300, 300); })()")  # 局部重画要先涂抹，否则网页不发请求
    pg.evaluate("(t => { t.value = '测试'; t.dispatchEvent(new Event('input', { bubbles: true })); })(document.querySelector('#ig-prompt'))"); pg.evaluate("document.querySelector('#ig-go').click()"); pg.wait_for_timeout(1500)
    check(f'{tag}：生成请求带 ref_extract、不带 inp_edge（后台用默认）', got.get('ref_extract') is True and 'inp_edge' not in got, {k: got.get(k) for k in ('ref_extract', 'inp_edge', 'mode')})
    pg.unroute('**/api/img/jobs')


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("S.ui = { ...(S.ui || {}), ppos: 'side' }")  # 2026-11-19：右栏没了；电脑上开关摊开着的是创作栏版（输入框版收在弹框里）
    flow(pg, '电脑')
    pg.evaluate("S.ui = { ...(S.ui || {}), ppos: 'bottom' }; persist()")
    check('电脑：没有页面报错', not errs, errs[:3])
    b.close()
    br, pg = open_iphone(p, PH); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    flow(pg, '手机')
    check('手机：没有页面报错', not errs, errs[:3])
    br.close()
print(f'{ok}/{ok + bad} 通过')
