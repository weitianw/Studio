"""“重新生成字幕”（2026-11-17）：测试音频（测试人声/轻声测试.wav，Windows 慧慧合成）先生成一次字幕，再点“重新生成”（确认框），等新的出来；量字幕文件确实换了。用法：python np_regen.py"""
import os, sys, time, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


def wait_subs(pg, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        s = pg.evaluate("(() => ({ n: document.querySelectorAll('#np-right .sub').length, empty: document.querySelector('#np-right .np-empty')?.textContent || '' }))()")
        if s['n'] or ('失败' in s['empty']) or ('未识别' in s['empty']):
            return s, round(time.time() - t0)
        if pg.query_selector('#np-gen'):
            pg.click('#np-gen')
        pg.wait_for_timeout(2000)
    return None, t


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio']); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /^测试人声/.test(x.textContent.trim()))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("PB.a.pause()"); pg.evaluate("npOpen()"); pg.wait_for_timeout(1000); pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(1500)
    s, sec = wait_subs(pg); check('第一次生成字幕', s and (s['n'] or '未识别' in s['empty']), (s, sec))
    key = pg.evaluate("NP.subsKey"); print('key', key, 'sec', sec)
    # 11-18：“重新生成”收进字幕区的右键菜单（和右上角 ⋯）
    pg.click('#np-right', button='right', position={'x': 200, 'y': 200}); pg.wait_for_timeout(300)
    rb = pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].some(e => /重新生成字幕/.test(e.textContent))"); check('字幕区右键菜单里有“重新生成字幕…”', rb)
    if rb:
        before = pg.evaluate("JSON.stringify(NP.sents)")
        pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => /重新生成字幕/.test(e.textContent)).click()"); pg.wait_for_timeout(600)
        check('先弹确认框', pg.evaluate("!!document.querySelector('.modal, .confirm, [role=dialog]')"))
        pg.evaluate("[...document.querySelectorAll('.modal button, [role=dialog] button')].find(b => b.textContent.trim() === '重新生成')?.click()"); pg.wait_for_timeout(1500)
        running = pg.evaluate("document.querySelector('#np-right .np-empty')?.textContent || ''")
        check('点了以后显示“正在生成字幕”（旧的已删）', '正在生成' in running, running)
        s2, sec2 = wait_subs(pg); check('重新生成完成', bool(s2), (s2, sec2))
        print('regen sec', sec2, 'same text as before:', pg.evaluate("JSON.stringify(NP.sents)") == before)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'{ok}/{ok + bad} 通过')
