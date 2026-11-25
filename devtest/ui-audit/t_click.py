"""逐个点击每页上能点的东西（真实鼠标 / 手指）：python t_click.py tag [phone]
每点一下：是否点得到（中心点是不是被别的东西挡住）、报错、弹出了什么（弹窗 / 菜单 / 面板）、弹出的东西是否出了窗口、能不能用 Esc / 点空白关掉。弹出东西时截图。"""
import os, json, sys, re
from playwright.sync_api import sync_playwright
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897'); tag = sys.argv[1] if len(sys.argv) > 1 else 'c'; PHONE = 'phone' in sys.argv
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'click_' + tag); os.makedirs(OUT, exist_ok=True)
INIT = "window.pywebview = { api: new Proxy({}, { get: () => () => Promise.resolve(null) }) };"
PAGES = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2] not in ('phone', 'seq', 'hard') else ['play', 'tts', 'vc', 'img', 'video', 'voices', 'works', 'mats', 'prompt', 'stt', 'audioedit', 'settings']
SKIP = re.compile(r'删除|清空|移除|退出|重启|关机|释放|清除|退出私密|恢复默认|取消任务|全部清|卸载|下载|导出|开始生成|开始换声|开始修改|^生成$|^生成 →$|^×$|关闭窗口|最小化|最大化')
MARK = r"""(phone) => {
  const vis = e => { if (e.closest('details:not([open])') && !e.closest('summary')) return false; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' && +cs.opacity > .2 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && !e.closest('[aria-hidden=true], .tb-strip, .win-ctl, #rail .rnav'); };
  document.querySelectorAll('[data-tk]').forEach(e => e.removeAttribute('data-tk'));
  const els = [...document.querySelectorAll('#main button, #main [role=button], #main [role=tab], #main summary, #main label.switch, #main label.ig-check, #main select, #main a[href].btn, #main .chip, body > .ig-grid button, .ig-top-f button, .b5-tools > *, .b5-opt button, .b5-opt [role=button], .b5-opt label.switch')].filter(vis);
  const seen = new Set(), out = [];
  els.forEach(e => { if (seen.has(e)) return; seen.add(e); const i = out.length; e.setAttribute('data-tk', i);
    out.push({ i, t: (e.getAttribute('aria-label') || e.dataset.tip || e.title || e.textContent || e.id || e.className.toString()).replace(/\s+/g, ' ').trim().slice(0, 28), id: e.id }); });
  const cnt = {}; out.forEach(o => { const k = o.id || o.t; o.k = k; o.n = cnt[k] = (cnt[k] ?? -1) + 1; });
  return out.slice(0, 90);
}"""
STATE = r"""() => {
  const vis = e => { if (e.closest('details:not([open])') && !e.closest('summary')) return false; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 4 && r.height > 4 && cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > .2; };
  const pops = [...document.querySelectorAll('.modal-bg .modal, .pop, .dd-menu, .ctx-menu, .ig-panel:not([hidden]), .vg-pop, .b5-menu, .qpanel:not([hidden]), .tip-card-float, .np:not([hidden]), .lb, .viewer')].filter(vis);
  return { url: location.pathname, page: document.getElementById('main')?.dataset.page, pops: pops.map(p => { const r = p.getBoundingClientRect(); return { c: p.className.toString().slice(0, 30), r: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)], out: r.left < -1 || r.top < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1 }; }),
    ovx: document.scrollingElement.scrollWidth > innerWidth + 1 };
}"""
INNER = r"""() => {
  const vis = e => { if (e.closest('details:not([open])') && !e.closest('summary')) return false; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' && +cs.opacity > .2; };
  const P = [...document.querySelectorAll('.modal-bg .modal, .pop, .dd-menu, .ctx-menu, .ig-panel:not([hidden]), .vg-pop, .b5-menu, .qpanel:not([hidden])')].filter(vis).pop(); if (!P) return [];
  return [...P.querySelectorAll('button, [role=button], [role=menuitem], [role=menuitemradio], .dd-i, label.switch, summary, [role=tab], .seg button')].filter(vis).map((e, k) => { e.setAttribute('data-tk2', k); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, t = document.elementFromPoint(x, y);
    return { k, t: (e.getAttribute('aria-label') || e.textContent || e.title || e.className.toString()).replace(/\s+/g, ' ').trim().slice(0, 24), x, y, hit: t && (e === t || e.contains(t)) ? 'ok' : (t ? (t.id || t.className.toString()).slice(0, 24) : 'none') }; });
}"""
R = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    vp = {'width': 390, 'height': 844} if PHONE else {'width': 1920, 'height': 1080}
    ctx = b.new_context(viewport=vp, color_scheme='dark', **({'is_mobile': True, 'has_touch': True, 'device_scale_factor': 2} if PHONE else {}))
    if not PHONE: ctx.add_init_script(INIT)
    ctx.route('**/*', lambda r: r.abort() if not r.request.url.startswith(B) or (r.request.method == 'POST' and re.search(r'/jobs|/delete|/remove|/clear|/stop|/restart|/quit|/vault/lock', r.request.url)) else r.continue_())
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:200])); pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errs.append('console: ' + m.text[:160]))
    pg.on('dialog', lambda d: d.dismiss())
    pg.goto(B + '/play'); pg.wait_for_timeout(1500)
    if not PHONE: pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
    pg.evaluate("fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'testky' }) }).then(r => r.ok && vaultEnter())"); pg.wait_for_timeout(2500)
    LS = {}
    def home(name):
        if 'hard' in sys.argv and LS.get(name):  # 整页重新载入，并把本地存储恢复成这一页刚打开时的样子（页面自己记住的标签、模式都回到原样）
            pg.evaluate("(o) => { localStorage.clear(); Object.entries(o).forEach(([k, v]) => localStorage.setItem(k, v)); }", LS[name])
            pg.goto(B + '/play'); pg.wait_for_timeout(1200)
            if not PHONE: pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
            pg.evaluate("() => { try { vaultEnter(); } catch (e) {} }"); pg.wait_for_timeout(800)
        pg.keyboard.press('Escape'); pg.evaluate("() => { document.querySelectorAll('.modal-bg').forEach(m => m.remove()); try { ctxClose(true); } catch (e) {} }")
        pg.evaluate("() => { if (window.__S0) { const o = JSON.parse(window.__S0); Object.keys(S).forEach(k => delete S[k]); Object.assign(S, o); } }")
        pg.evaluate("() => { S.ui = { ...(S.ui || {}), pc: {}, ppos: 'bottom' }; S.galLay = 'col'; S.galFold = false; document.documentElement.classList.remove('rail-wide'); try { pbMin(true); } catch (e) {} }")
        pg.evaluate(f"go('{name}')"); pg.wait_for_timeout(1300); pg.evaluate("document.querySelectorAll('video,audio').forEach(v => { v.muted = true; v.pause(); })")
    def tap(x, y):
        if PHONE: pg.touchscreen.tap(x, y)
        else: pg.mouse.click(x, y)
    for name in PAGES:
        pg.evaluate("() => { window.__S0 = null; }"); home(name); pg.evaluate("() => { window.__S0 = JSON.stringify(S); }")
        LS[name] = pg.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        items = pg.evaluate(MARK, PHONE); res = []
        for it in items:
            if SKIP.search(it['t'] or ''): res.append({**it, 'skip': 1}); continue
            if 'seq' not in sys.argv or pg.evaluate("() => document.getElementById('main')?.dataset.page") != name or pg.evaluate(STATE)['pops']: home(name)
            m = []
            for _ in range(6):
                cur = pg.evaluate(MARK, PHONE); m = [c for c in cur if c['k'] == it['k'] and c['n'] == it['n']]
                if m: break
                pg.wait_for_timeout(500)
            if not m: res.append({**it, 'gone': 1}); continue
            it = {**it, 'i': m[0]['i']}
            el = pg.query_selector(f'[data-tk="{it["i"]}"]')
            if not el: res.append({**it, 'gone': 1}); continue
            try: el.scroll_into_view_if_needed(timeout=1500)
            except Exception: pass
            bx = el.bounding_box()
            if not bx: res.append({**it, 'nobox': 1}); continue
            cx, cy = bx['x'] + bx['width'] / 2, bx['y'] + bx['height'] / 2
            hit = pg.evaluate("([x, y, i]) => { const t = document.elementFromPoint(x, y), e = document.querySelector(`[data-tk=\"${i}\"]`); return !t ? 'none' : (e && (e === t || e.contains(t) || t.contains(e) || (e.tagName === 'INPUT' && t.closest('label')?.contains(e)))) ? 'ok' : (t.id || t.className.toString() || t.tagName).slice(0, 30); }", [cx, cy, it['i']])
            e0 = len(errs); s0 = pg.evaluate(STATE)
            try: tap(cx, cy)
            except Exception as ex: res.append({**it, 'clickerr': str(ex)[:80]}); continue
            pg.wait_for_timeout(650)
            pg.evaluate("document.querySelectorAll('video,audio').forEach(v => { v.muted = true; v.pause(); })")
            s1 = pg.evaluate(STATE); rec = {**it, 'hit': hit}
            if len(errs) > e0: rec['err'] = errs[e0:]
            if s1['pops']:
                rec['pops'] = s1['pops']; fn = f"{name}_{it['i']:02d}.png"; pg.screenshot(path=os.path.join(OUT, fn)); rec['shot'] = fn
                pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
                if pg.evaluate(STATE)['pops']:
                    tap(vp['width'] - 30 if not PHONE else 195, 70 if PHONE else vp['height'] // 2); pg.wait_for_timeout(300)
                    still = pg.evaluate(STATE)['pops']
                    if still: rec['stuck'] = [x['c'] for x in still]
            if s1['pops'] and not it.get('lv2'):  # 第二层：弹出来的菜单 / 面板里的按钮也逐个点（每次重新打开）
                home(name); pg.evaluate(MARK, PHONE); e2 = pg.query_selector(f'[data-tk="{it["i"]}"]')
                if e2:
                    b2 = e2.bounding_box(); tap(b2['x'] + b2['width'] / 2, b2['y'] + b2['height'] / 2); pg.wait_for_timeout(500)
                    inner = pg.evaluate(INNER)
                    sub = []
                    for j, q in enumerate(inner[:12]):
                        if SKIP.search(q['t'] or ''): continue
                        home(name); pg.evaluate(MARK, PHONE); e3 = pg.query_selector(f'[data-tk="{it["i"]}"]')
                        if not e3: break
                        b3 = e3.bounding_box(); tap(b3['x'] + b3['width'] / 2, b3['y'] + b3['height'] / 2); pg.wait_for_timeout(500)
                        cur = pg.evaluate(INNER); mm = [c for c in cur if c['t'] == q['t']]
                        if not mm: sub.append({'t': q['t'], 'gone': 1}); continue
                        h3 = pg.query_selector(f'[data-tk2="{mm[0]["k"]}"]')
                        try: h3.scroll_into_view_if_needed(timeout=1200)
                        except Exception: pass
                        bb = h3.bounding_box() if h3 else None
                        if not bb: sub.append({'t': q['t'], 'nobox': 1}); continue
                        px, py = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
                        mm[0]['hit'] = pg.evaluate("([x, y, k]) => { const t = document.elementFromPoint(x, y), e = document.querySelector(`[data-tk2=\"${k}\"]`); return t && e && (e === t || e.contains(t) || t.contains(e)) ? 'ok' : (t ? (t.id || t.className.toString()).slice(0, 24) : 'none'); }", [px, py, mm[0]['k']])
                        x0 = len(errs); tap(px, py); pg.wait_for_timeout(600)
                        pg.evaluate("document.querySelectorAll('video,audio').forEach(v => { v.muted = true; v.pause(); })")
                        s2 = pg.evaluate(STATE); r2 = {'t': q['t'], 'hit': mm[0]['hit']}
                        if len(errs) > x0: r2['err'] = errs[x0:]
                        if any(x['out'] for x in s2['pops']): r2['out'] = [x for x in s2['pops'] if x['out']]
                        if s2['pops']: fn = f"{name}_{it['i']:02d}_{j:02d}.png"; pg.screenshot(path=os.path.join(OUT, fn)); r2['shot'] = fn
                        sub.append(r2)
                    rec['sub'] = sub
            if s1['page'] != s0['page']: rec['nav'] = s1['page']
            if s1['ovx']: rec['ovx'] = 1
            res.append(rec)
        R[name] = res
        pg.screenshot(path=os.path.join(OUT, f'{name}_end.png'))
    R['_errs'] = errs; b.close()
open(os.path.join(OUT, 'res.json'), 'w', encoding='utf-8').write(json.dumps(R, ensure_ascii=False, indent=1)); print('done')
