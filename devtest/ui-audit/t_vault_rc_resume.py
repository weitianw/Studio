"""遥控播放：全程在电脑上点 A → 点 B → 再点回 A，手机接着 A 上次的位置放（手机在私密空间 / 刚退出私密空间各一遍）。
2026-11-17 用户发现手机刚退出私密空间时不续播：退出前挂着的等命令请求把私密原地址发给了已经退出的手机，放不出来。
用法（先起测试 Studio：python -I run.py --profile chk --port 7941 --state states/rc，并先跑过一次 t_vault_rc.py 做好测试音）：
  .venv\\Scripts\\python.exe -I ui-audit\\t_vault_rc_resume.py"""
import os, sys, time
fails = []
from playwright.sync_api import sync_playwright
EXE = os.path.join(os.environ['LOCALAPPDATA'], 'ms-playwright', 'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe')
IOS = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1'
PC, PH = 'http://127.0.0.1:7941', 'http://127.0.0.1:7942'
INIT = "sessionStorage.getItem('sessT0') || sessionStorage.setItem('sessT0', String(Date.now())); sessionStorage.setItem('vaultTab', '1'); document.addEventListener('play', e => { e.target.muted = true; }, true);"
def until(fn, secs=8):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.2)
    return False
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pc = b.new_context(viewport={'width': 1440, 'height': 900}); ph = b.new_context(viewport={'width': 402, 'height': 874}, user_agent=IOS, has_touch=True, is_mobile=True)
    code = pc.request.post(PC + '/api/remote/code').json()['code']
    ph.request.post(PH + '/api/remote/pair', data={'code': code, 'name': 't'})
    for c, base in ((pc, PC), (ph, PH)): c.request.post(base + '/api/vault/unlock', data={'key': 'testky'})
    P, M = pc.new_page(), ph.new_page()
    for pg in (P, M): pg.add_init_script(INIT)
    P.goto(PC + '/play'); M.goto(PH + '/play'); P.wait_for_timeout(3000)
    if P.evaluate('document.body.classList.contains("pb-min")'): P.click('#pb-fab')
    for space in ('vault', 'normal'):
        if space == 'normal':
            M.evaluate('vaultLock()'); M.wait_for_timeout(2500)
        # 手机先随便放一下（手机得在放，电脑才会自动连上）
        if space == 'vault':
            M.click('.ps-item[data-src="d:遥控测试"]'); M.wait_for_selector('.pl-row'); M.locator('.pl-row').nth(1).click()
        else:
            M.evaluate("go('play')"); M.wait_for_selector('#play-q'); M.wait_for_timeout(1200); M.fill('#play-q', '空白音频'); M.wait_for_timeout(800)
            M.evaluate("S.qmode.repeat = 'one'"); M.locator('.pl-row', has_text='空白音频').first.click()
        if not until(lambda: P.evaluate('RC.ctl'), 10): P.click('#pb-rc'); until(lambda: P.evaluate('RC.ctl'), 5)
        P.evaluate("document.querySelector('.ps-item[data-src=\"d:遥控测试\"]')?.click()"); P.wait_for_selector('.pl-row')
        rows = P.locator('.pl-row')
        P.evaluate('savePos({})')  # 先清掉电脑记着的进度
        rows.nth(0).dblclick()   # A（电脑上双击播放）
        until(lambda: P.locator('#pb-title').inner_text() == '测试音 1' and M.evaluate('!qAudio.paused'), 8)
        until(lambda: M.evaluate('qAudio.currentTime') > 1, 8); M.evaluate('qAudio.currentTime = 25'); time.sleep(7)  # A 放到 30 秒左右
        ta = M.evaluate('qAudio.currentTime')
        rows.nth(1).dblclick()   # B
        until(lambda: P.locator('#pb-title').inner_text() == '测试音 2', 8); time.sleep(3)
        rows.nth(0).dblclick()   # 再点回 A
        until(lambda: P.locator('#pb-title').inner_text() == '测试音 1', 8); time.sleep(2.5)
        tb = M.evaluate('qAudio.currentTime')
        print(f'{space}: A 放到 {ta:.1f} 秒 → 切 B → 再点 A 从 {tb:.1f} 秒  {"通过" if tb > 20 else "失败"}', flush=True)
        if tb <= 20: fails.append(space)
    M.evaluate('pbReset(true); rcBye()'); M.wait_for_timeout(800)  # 手机正常停下：下一个测试不会看到这台旧手机
    P.evaluate('rcStop(true, true)'); P.wait_for_timeout(300)
    b.close()
print('结果：' + ('全部通过' if not fails else '失败：' + '、'.join(fails)))
sys.exit(1 if fails else 0)
