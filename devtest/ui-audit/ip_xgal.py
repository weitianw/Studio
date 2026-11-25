"""提取出来的衣服进生图图库（2026-11-17）：图上角标“衣服”、悬停写“提取的衣服”；右键有“放进「提取的衣服」”，点了提示已放进素材库。
只看文字，不截图（图库里有别的成品）。用法：python ip_xgal.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.evaluate("go('img')"); pg.wait_for_selector('#ig-gal .ig-tile', timeout=60000); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelectorAll('img, video').forEach(e => e.style.visibility = 'hidden')")
    t = pg.evaluate("(() => { const t = [...document.querySelectorAll('#ig-gal .ig-tile')].find(x => x.querySelector('.ig-badge')?.textContent === '衣服'); if (!t) return null; t.scrollIntoView(); return { i: t.dataset.i, tip: t.title }; })()")
    check('图库里提取的衣服角标是“衣服”', bool(t), t)
    if t:
        check('悬停说明写“提取的衣服”', '提取的衣服' in t['tip'], t['tip'][:80])
        pg.click(f'#ig-gal .ig-tile[data-i="{t["i"]}"]', button='right'); pg.wait_for_timeout(600)
        items = pg.evaluate("[...document.querySelectorAll('.ctx-menu button, .ctx button, [role=menu] button, [role=menuitem]')].map(b => b.textContent.trim()).filter(Boolean)")
        check('右键菜单有“放进「提取的衣服」”', any('放进「提取的衣服」' in x for x in items), items[:14])
        pg.evaluate("[...document.querySelectorAll('.ctx-menu button, .ctx button, [role=menu] button, [role=menuitem]')].find(b => b.textContent.includes('放进「提取的衣服」'))?.click()"); pg.wait_for_timeout(1200)
        toast = pg.evaluate("[...document.querySelectorAll('.toast')].map(x => x.textContent).join(' | ')")
        check('点了提示已放进 / 已有', '素材库' in toast, toast)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'{ok}/{ok + bad} 通过')
