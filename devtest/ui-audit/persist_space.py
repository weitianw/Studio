"""P09 回归：打字后 0.6 秒内（写入还排着）就进 / 出私密空间：普通空间的草稿照样写进本地存储、不会带进私密空间；
私密空间里打的字不会写进本地存储；出来后普通空间的草稿还在。测试 Studio 的私密空间密钥是 testky（测试数据）。不截图。"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


LS = "JSON.parse(localStorage.getItem('studio')).text"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('tts')"); pg.wait_for_timeout(800)
    pg.evaluate("(() => { const ta = document.querySelector('#script'); ta.value = '普通草稿'; ta.oninput(); ta.blur(); })()")
    pg.click('#script'); pg.keyboard.press('Control+End'); pg.keyboard.type('甲乙')
    pg.evaluate("fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'testky' }) }).then(() => vaultEnter())")
    pg.wait_for_timeout(1500)
    check('进私密空间前排着的写入按普通空间写掉', pg.evaluate(LS) == '普通草稿甲乙', pg.evaluate(LS))
    check('私密空间里配音框是空的', pg.evaluate("VAULT && S.text === ''"), pg.evaluate("[VAULT, S.text]"))
    pg.evaluate("go('tts')"); pg.wait_for_timeout(800)
    pg.click('#script'); pg.keyboard.type('私密内容'); pg.wait_for_timeout(900)
    check('私密空间里打的字不进本地存储', pg.evaluate(LS) == '普通草稿甲乙' and '私密' not in pg.evaluate("localStorage.getItem('studio')"))
    pg.keyboard.type('再打'); pg.evaluate("vaultLock()"); pg.wait_for_timeout(1500)
    check('出私密空间：普通空间的草稿回来了', pg.evaluate("!VAULT && S.text === '普通草稿甲乙'"), pg.evaluate("[VAULT, S.text]"))
    check('出来后本地存储里没有私密空间的字', '私密' not in pg.evaluate("localStorage.getItem('studio')") and '再打' not in pg.evaluate("localStorage.getItem('studio')"))
    pg.reload(); pg.wait_for_timeout(2500); pg.evaluate("go('tts')"); pg.wait_for_timeout(800)
    check('刷新后普通草稿还在', pg.evaluate("document.querySelector('#script').value") == '普通草稿甲乙')
    pg.evaluate("fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'testky' }) }).then(() => vaultEnter())"); pg.wait_for_timeout(2000)
    check('再进私密空间：退出前最后打的字也存住了', pg.evaluate("VAULT && S.text") == '私密内容再打', pg.evaluate("S.text"))
    pg.evaluate("go('tts')"); pg.wait_for_timeout(600)
    pg.evaluate("(() => { const ta = document.querySelector('#script'); ta.value = ''; ta.oninput(); ta.blur(); })()"); pg.wait_for_timeout(300)
    pg.evaluate("vaultLock()"); pg.wait_for_timeout(1200); pg.evaluate("go('tts')"); pg.wait_for_timeout(600)
    pg.evaluate("(() => { const ta = document.querySelector('#script'); ta.value = ''; ta.oninput(); ta.blur(); })()")
    check('没有页面报错', not errs, errs)
    b.close()
print(f'通过 {ok}，失败 {bad}')
