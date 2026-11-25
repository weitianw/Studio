"""常用状态的检查（规则和 audit2 一样）：python -I states.py <profile>
改视频放入原视频 + 有任务在跑、生视频有任务、导航展开、播放条展开、齿轮菜单、模式下拉、高级参数弹窗"""
import os, sys, json, time
SP = os.path.dirname(os.path.abspath(__file__))
prof = sys.argv[1]
src = open(os.path.join(SP, 'audit2.py'), encoding='utf-8').read().split("R = {'profile'")[0]
sys.argv = ['x', prof]; ns = {'__file__': os.path.join(SP, 'audit2.py')}; exec(compile(src, 'audit2', 'exec'), ns)
CHECK, MARKS, UNMARK, MUTE, B, EXE, INIT = ns['CHECK'], ns['MARKS'], ns['UNMARK'], ns['MUTE'], ns['B'], ns['EXE'], ns['INIT']
W, H, MOBI, APP, DPR, UA, THEME = ns['PROFILES'][prof]
from playwright.sync_api import sync_playwright
OUT = os.path.join(SP, 'st', prof); os.makedirs(OUT, exist_ok=True)
now = time.time()
JOBS = [{'id': 'j1', 'state': 'running', 'progress': 38, 'message': '正在生成 · 第 3/8 步', 'created': now - 200, 'started': now - 173, 'model': 'h3', 'model_name': 'MiniMax H3 · 官方', 'size': '720p', 'seconds': 3, 'seed': 1872853133, 'prompt': '', 'edit': {'task': 'outfit'}},
        {'id': 'j2', 'state': 'queued', 'progress': 0, 'message': '', 'created': now - 100, 'model': 'h3', 'model_name': 'MiniMax H3 · 官方', 'size': '720p', 'seconds': 5, 'seed': 210907434, 'prompt': '一个很长很长的提示词用来测试任务名字太长时的显示效果', 'edit': None}]
def route(r):
    u = r.request.url
    if not u.startswith(B): return r.abort()
    if r.request.method == 'POST' and any(k in u for k in ('/jobs', '/delete', '/clear', '/restart', '/quit', '/vault/lock')): return r.abort()
    if r.request.method == 'GET' and u.split('?')[0].endswith('/api/video/jobs'): return r.fulfill(status=200, content_type='application/json', body=json.dumps(JOBS))
    return r.continue_()
STATES = [
    ('edit_src_jobs', "() => { vidState().mode = 'edit'; go('video'); }", "() => new Promise(res => { try { matsVid({ rel: '测试/AI跳舞.mp4', name: 'AI跳舞.mp4' }, (v, done) => { VE_VID = v; if (done) { renderVideo.paintMode?.(); res(); } }); } catch (e) { res(); } setTimeout(res, 4000); })", "() => { try { vidWatch(); } catch (e) {} }"),
    ('edit_src_pc', "() => { vidState().mode = 'edit'; S.ui = { ...(S.ui || {}), pc: { ...(S.ui?.pc || {}), video: true } }; go('video'); }", "() => new Promise(res => { try { matsVid({ rel: '测试/AI跳舞.mp4', name: 'AI跳舞.mp4' }, (v, done) => { VE_VID = v; if (done) { renderVideo.paintMode?.(); res(); } }); } catch (e) { res(); } setTimeout(res, 4000); })", "() => { try { vidWatch(); } catch (e) {} }"),
    ('gen_jobs', "() => { vidState().mode = 'gen'; S.ui = { ...(S.ui || {}), pc: {} }; go('video'); }", "() => { try { vidWatch(); } catch (e) {} }", None),
    ('rail_wide', "() => { go('tts'); }", "() => { if (!document.documentElement.classList.contains('rail-wide')) document.getElementById('rail-tog')?.click(); }", None),
    ('player_open', "() => { document.documentElement.classList.remove('rail-wide'); go('img'); }", "() => { try { pbMin(false); } catch (e) {} }", None),
    ('gear_menu', "() => { try { pbMin(true); } catch (e) {} go('vc'); }", "() => document.getElementById('side-gear')?.click()", None),
    ('mode_menu', "() => { go('video'); }", "() => document.querySelector('#main > .page-head .b5-ctx')?.click()", None),
    ('adv_modal', "() => { go('video'); }", "() => { const b = document.querySelector('#vd-adv-open, [id$=adv-open]'); b && b.click(); }", None),
    ('img_adv', "() => { go('img'); }", "() => { const b = document.querySelector('#ig-adv-open'); b && b.click(); }", None),
]
R = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    kw = dict(viewport={'width': W, 'height': H}, color_scheme=THEME, device_scale_factor=1 if not MOBI else 2)
    if MOBI: kw.update(is_mobile=True, has_touch=True, user_agent=UA)
    ctx = b.new_context(**kw)
    if APP: ctx.add_init_script(INIT)
    if os.environ.get('AUD_SFW', '1') != '0':  # 截图只看 SFW（2026-11-18，和 audit2 一样）
        ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = 'img:not([src*=brand]):not([src$=svg]),video,canvas{visibility:hidden!important} *,*::before,*::after{background-image:none!important}'; document.head.append(s); });")
    ctx.route('**/*', route)
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:240])); pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errs.append('console: ' + m.text[:200]))
    pg.on('dialog', lambda d: d.dismiss())
    pg.goto(B + '/play'); pg.wait_for_timeout(1500)
    if APP: pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
    pg.evaluate("() => { try { pbMin(true); } catch (e) {} }")
    for name, js1, js2, js3 in STATES:
        try:
            pg.keyboard.press('Escape'); pg.evaluate("() => { document.querySelectorAll('.modal-bg').forEach(m => m.remove()); try { curPop && curPop.close(true); } catch (e) {} }")
            pg.evaluate(js1); pg.wait_for_timeout(1500)
            if js2: pg.evaluate(js2); pg.wait_for_timeout(1500)
            if js3: pg.evaluate(js3); pg.wait_for_timeout(2200)
            if name.startswith('edit'): pg.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === '剪辑' && x.offsetParent); b && b.click(); }"); pg.wait_for_timeout(800)
            pg.evaluate(MUTE); pg.evaluate(UNMARK)
            res = pg.evaluate(CHECK, {'W': W, 'H': H, 'mobile': MOBI, 'fixedPage': APP and not MOBI and W >= 1200 and name.startswith(('edit', 'gen')), 'atBottom': True})
            pg.screenshot(path=os.path.join(OUT, name + '.png'))
            if res['F']: pg.evaluate(MARKS); pg.screenshot(path=os.path.join(OUT, name + '_m.png')); pg.evaluate(UNMARK)
            R[name] = res
        except Exception as ex: R[name] = {'crash': str(ex)[:200]}
    R['_errs'] = errs; b.close()
json.dump(R, open(os.path.join(OUT, 'res.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
sys.stdout.reconfigure(encoding='utf-8')
for k, v in R.items():
    if k == '_errs': print('errs', v[:4]); continue
    fs = [f for f in v.get('F', []) if f['kind'] not in ('ellipsis', 'small')]
    print(prof, k, v.get('crash', ''), [f"{f['kind']} {f['el'][:36]}" for f in fs][:8])
