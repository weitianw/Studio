"""生图高级参数（ComfyUI 模型）：步数 / CFG / 采样器 / 调度器 / 像素默认推荐、能改、数字对、生成时带上、恢复推荐（2026-11-23）。用法：devtest/.venv/Scripts/python.exe t_qset.py"""
import sys, json, os
sys.path.insert(0, 'D:/AI-TTS/devtest/ui-audit')
from playwright.sync_api import sync_playwright
from np_desk import EXE
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = fail = 0; errs = []; sent = []
def check(n, c, x=''):
    global ok, fail
    if c: ok += 1; print('  ✓', n)
    else: fail += 1; print('  ✗', n, str(x)[:300])
HIDE = 'img:not([src*="/brand/"]):not([src$=".svg"]),video,canvas{visibility:hidden!important} *,*::before,*::after{background-image:none!important}'
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    for theme, w, h in (('dark', 1440, 900), ('light', 1024, 700)):
        pg = b.new_page(viewport={'width': w, 'height': h}, color_scheme=theme); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.route('**/api/img/jobs', lambda r: (sent.append(json.loads(r.request.post_data or '{}')), r.fulfill(status=400, content_type='application/json', body='{"error":"测试拦下"}')) if r.request.method == 'POST' else r.fallback())
        pg.goto('http://127.0.0.1:7897/'); pg.wait_for_timeout(2500); pg.add_style_tag(content=HIDE)
        pg.evaluate(f"S.theme = '{theme}'; applyTheme(false)")
        pg.evaluate("go('img')"); pg.wait_for_timeout(2500)
        pg.evaluate("(() => { const st = S.img; Object.assign(st, { model: 'moss-photo', mode: 'txt', refine2: false, seed: -1, loras: [], qOver: {} }); persist(); go('img'); })()"); pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('ig-adv-open').click()"); pg.wait_for_timeout(900)
        ph = pg.evaluate("[document.getElementById('ig-qsteps')?.placeholder, document.querySelector('#ig-qsamp option')?.textContent, document.querySelector('#ig-qmp option')?.textContent]")
        check(f'{theme}：推荐值显示成默认（MOSS 写真 30 步 / er_sde / 2 百万像素）', ph == ['推荐 30', '推荐 er_sde', '推荐 2 百万像素'], ph)
        pg.fill('#ig-qsteps', '20'); pg.evaluate("(() => { const e = document.getElementById('ig-qmp'); e.value = '1'; e.dispatchEvent(new Event('change', { bubbles: true })); })()"); pg.wait_for_timeout(500)
        n = pg.evaluate("document.getElementById('ig-adv-n').textContent")
        check(f'{theme}：改了两项，数字是 2，「恢复推荐」出现', n == '2' and pg.evaluate("!document.getElementById('ig-qreset').hidden"), n)
        geo = pg.evaluate("""(() => { const m = document.querySelector('.modal'), r = m.getBoundingClientRect(); const out = [...m.querySelectorAll('#ig-qsteps, #ig-qcfg, .ig-q2 .dd, .ig-q2 button, #ig-qmp + *, .ig-q2 > .field > *:last-child')].filter(e => e.offsetParent).map(e => { const q = e.getBoundingClientRect(); return [Math.round(q.left), Math.round(q.right), Math.round(q.width)]; });
          return { overflow: m.scrollWidth > m.clientWidth + 1, out, inside: out.every(([l, rr]) => l >= r.left && rr <= r.right) }; })()""")
        check(f'{theme}：新字段在弹窗里、不横向溢出', geo['inside'] and not geo['overflow'], geo)
        pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', f'qset_{theme}.png'))
        pg.click('.modal [data-close]'); pg.wait_for_timeout(1500)
        check(f'{theme}：关了弹窗数字还在', pg.evaluate("document.getElementById('ig-adv-n').textContent") == '2')
        pg.evaluate("(() => { const ta = document.querySelector('#ig-prompt, textarea'); ta.value = 'test'; ta.dispatchEvent(new Event('input')); })()")
        pg.evaluate("document.querySelector('#ig-go, #ig-gen, .ig-go, [data-gen]')?.click()"); pg.wait_for_timeout(1200)
        q = (sent[-1] if sent else {}).get('q_over')
        check(f'{theme}：生成时带上改过的设置', q == {'steps': 20, 'mp': '1'} or q == {'steps': 20, 'mp': 1}, sent[-1:] )
        pg.evaluate("document.getElementById('ig-adv-open').click()"); pg.wait_for_timeout(800)
        pg.click('#ig-qreset'); pg.wait_for_timeout(500)
        check(f'{theme}：恢复推荐后清空', pg.evaluate("document.getElementById('ig-qsteps').value") == '' and pg.evaluate("document.getElementById('ig-adv-n').textContent") in ('', '0'))
        pg.close()
    b.close()
check('没有页面报错', not errs, errs[:3])
print(f'{ok} 通过，{fail} 失败')
