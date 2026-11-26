"""英文模式下每个页面还剩哪些中文（文字节点 + 属性），列出唯一的片段（开源泛化 ④）。
测试 Studio（STUDIO_TEST_PORT，默认 7897），静音，不截图。页面按 studio.lang = en 打开（不管测试 Studio 的默认语言）。
用法：STUDIO_TEST_PORT=7897 ../.venv/Scripts/python.exe t_i18n.py    （要指定浏览器时设 STUDIO_CHROMIUM）"""
import json, os, re, sys
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
EXE = os.environ.get('STUDIO_CHROMIUM')
PORT = os.environ.get('STUDIO_TEST_PORT', '7897')
PAGES = ['play', 'tts', 'vc', 'voices', 'stt', 'img', 'video', 'mats', 'prompt', 'batch', 'audioedit', 'works', 'settings', 'models']
JS = """() => { const out = new Set(), H = /[\\u4e00-\\u9fff]/;
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) { const p = n.parentElement; if (!p || p.closest('script,style,textarea,.no-i18n')) continue; if (H.test(n.nodeValue)) out.add(n.nodeValue.trim()); }
  document.querySelectorAll('[title],[placeholder],[aria-label],[data-tip]').forEach(e => { if (e.closest('.no-i18n')) return; for (const a of ['title','placeholder','aria-label','data-tip']) { const v = e.getAttribute(a); if (v && H.test(v)) out.add('@' + a + ': ' + v); } });
  return [...out]; }"""
res = {}
allx = set()
with sync_playwright() as p:
    br = p.chromium.launch(**({'executable_path': EXE} if EXE else {}), args=['--mute-audio'])
    ctx = br.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_init_script("try { localStorage.setItem('studio.lang', 'en'); } catch (e) {}")
    ctx.route('**/*', lambda r: r.abort() if r.request.resource_type in ('image', 'media') or (r.request.method == 'POST' and re.search(r'/jobs|/delete|/generate|/restart|/quit', r.request.url)) else r.continue_())
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
    pg.goto(f'http://127.0.0.1:{PORT}/', wait_until='domcontentloaded')
    pg.wait_for_timeout(3500)
    print('lang', pg.evaluate('window.STUDIO_LANG'), 'dict', pg.evaluate('Object.keys(window.I18N_EN || {}).length'))
    for pid in PAGES:
        pg.evaluate(f"go({pid!r})")
        pg.wait_for_timeout(2200)
        if pid == 'video':
            left = pg.evaluate(JS)
            pg.evaluate("document.querySelector('[data-v=edit]')?.click()")
            pg.wait_for_timeout(1500)
            left += pg.evaluate(JS)
        elif pid == 'img':
            pg.click('#ig-prompt')
            pg.wait_for_timeout(600)
            left = pg.evaluate(JS)
            pg.evaluate("[...document.querySelectorAll('#main .ig-chips > *')].filter(e => e.offsetParent)[0]?.click()")
            pg.wait_for_timeout(800)
            left += pg.evaluate(JS)
            pg.keyboard.press('Escape')
            pg.evaluate("document.getElementById('ig-adv-open')?.click()")
            pg.wait_for_timeout(900)
            left += pg.evaluate(JS)
            pg.keyboard.press('Escape')
        elif pid == 'models':
            left = pg.evaluate(JS)
            pg.evaluate("document.querySelector('[data-add=image]')?.click()")
            pg.wait_for_timeout(1200)
            left += pg.evaluate(JS)
            pg.keyboard.press('Escape')
        else:
            left = pg.evaluate(JS)
        res[pid] = sorted(set(left))
        allx |= set(left)
    br.close()
for k, v in res.items():
    print(f'== {k} ({len(v)})')
    for x in v[:40]:
        print('   ', x)
print('TOTAL unique', len(allx), 'errors', errs)
