"""“提取衣服”放进输入框下面那排（2026-11-17 用户：右边选项栏平时关着）。电脑选项栏收起：放参考图前没有、放了出现、点一下开（变蓝、和选项栏开关同步）、
请求带 ref_extract；换成文生图（移除原图）后不出现。手机同样看一次。只用自己画的格子图。用法：python ip_xchip.py"""
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
HIDE = "document.querySelectorAll('.ig-gal img, .ig-gal video, #ig-live img').forEach(e => e.style.visibility = 'hidden')"
ST = "(() => { const c = document.querySelector('.ig-xchip'); const r = c?.getBoundingClientRect(); const sw = document.querySelector('#ig-xref');" \
     " return { shown: !!(c && !c.hidden && r.width), on: !!c?.classList.contains('on'), pressed: c?.getAttribute('aria-pressed'), sw: sw ? sw.checked : null, refX: !!S.img.refX," \
     " hit: !!(r && r.width && document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.closest('.ig-xchip')), h: r ? Math.round(r.height) : 0, color: c ? getComputedStyle(c).color : '' }; })()"
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
    pg.evaluate("document.querySelector('#ig-mode button[data-k=\"inpaint\"]')?.click()"); pg.wait_for_timeout(900)
    if tag == '电脑':
        pg.mouse.click(5, 450); pg.wait_for_timeout(400); pg.click('#ig-prompt'); pg.wait_for_timeout(800)
    s = pg.evaluate(ST); check(f'{tag}：没放参考图时没有“提取衣服”', not s['shown'], s)
    pg.query_selector('#ig-ref-file').set_input_files(GRID); pg.wait_for_timeout(1500)
    if tag == '电脑':
        pg.mouse.click(5, 450); pg.wait_for_timeout(400); pg.click('#ig-prompt'); pg.wait_for_timeout(800)
    pg.evaluate("document.querySelector('.ig-xchip')?.scrollIntoView({block: 'nearest', inline: 'center'})"); pg.wait_for_timeout(300)
    s = pg.evaluate(ST); check(f'{tag}：放了参考图出现在输入框下面那排、点得到', s['shown'] and s['hit'] and not s['on'], s)
    c = pg.query_selector('.ig-xchip'); bb = c.bounding_box()
    if tag == '手机':
        pg.touchscreen.tap(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
    else:
        c.click()
    pg.wait_for_timeout(500)
    s = pg.evaluate(ST); check(f'{tag}：点一下开（变蓝、aria-pressed、选项栏开关同步、记住）', s['on'] and s['pressed'] == 'true' and s['refX'] and s['sw'] in (True, None) and s['color'] != pg.evaluate("getComputedStyle(document.querySelector('.ig-chips .ig-chip:not(.ig-xchip)')).color"), s)
    pg.evaluate(HIDE)
    if tag == '手机':
        hide(pg)
    pg.screenshot(path=os.path.join(OUT, f'chip_{tag}.png'))
    got = {}
    pg.route('**/api/img/jobs', lambda r: r.continue_() if r.request.method != 'POST' else (got.update(json.loads(r.request.post_data or '{}')), r.fulfill(status=200, content_type='application/json', body='{"error":"测试拦截"}')))
    pg.evaluate("(() => { const g = IMG_MASK.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(100, 100, 300, 300); })()")
    pg.evaluate("(t => { t.value = '测试'; t.dispatchEvent(new Event('input', { bubbles: true })); })(document.querySelector('#ig-prompt'))"); pg.evaluate("document.querySelector('#ig-go').click()"); pg.wait_for_timeout(1500)
    check(f'{tag}：生成请求带 ref_extract', got.get('ref_extract') is True, {k: got.get(k) for k in ('ref_extract', 'mode')})
    pg.unroute('**/api/img/jobs')
    c = pg.query_selector('.ig-xchip'); bb = c.bounding_box()
    if tag == '手机':
        pg.touchscreen.tap(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
    else:
        c.click()
    pg.wait_for_timeout(400)
    s = pg.evaluate(ST); check(f'{tag}：再点一下关', not s['on'] and not s['refX'], s)
    pg.evaluate("document.querySelector('[data-rx=\"0\"]')?.click()"); pg.wait_for_timeout(900)
    s = pg.evaluate(ST); check(f'{tag}：移除参考图后不再显示', not s['shown'], s)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
    flow(pg, '电脑')
    check('电脑：没有页面报错', not errs, errs[:3])
    b.close()
    br, pg = open_iphone(p, PH); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    flow(pg, '手机')
    check('手机：没有页面报错', not errs, errs[:3])
    br.close()
print(f'{ok}/{ok + bad} 通过')
