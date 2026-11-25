"""遥控播放（私密空间里用电脑控制手机播放；手机在哪个空间都行）的端到端检查：一个浏览器里开两个页面，一个当电脑、一个当手机（测试 Studio 的手机端口）。

用法（在 D:\\AI-TTS\\devtest 里，先起测试 Studio：python -I run.py --profile chk --port 7941 --state states/rc；--state 要一样，脚本往它的库里放测试音）：
  .venv\\Scripts\\python.exe -I ui-audit\\t_vault_rc.py [--port 7941] [--shot 截图.png]
全部静音；截图前把图片 / 视频藏起来。只看测试数据。"""
import argparse, os, subprocess, sys, time
from playwright.sync_api import sync_playwright

EXE = os.path.join(os.environ['LOCALAPPDATA'], 'ms-playwright', 'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe')  # 和 tools/iphone.py 用同一个
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--port', type=int, default=7941)
ap.add_argument('--shot')
ap.add_argument('--state', default=os.path.join(os.path.dirname(HERE), 'states', 'rc'))
a = ap.parse_args()
# 测试数据里的录音只有 2 秒：在测试 Studio 的私密库里现做两段 1 分钟的测试音，普通库里放一段 5 秒的空白音频（只做一次）
FF = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
VD = os.path.join(a.state, 'data', 'library', '遥控测试'); os.makedirs(VD, exist_ok=True)
for n in (1, 2):
    f = os.path.join(VD, f'测试音 {n}.mp3')
    if not os.path.isfile(f):
        subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f"aevalsrc='0.1*sin(2*PI*{330 * n}*t)*lt(mod(t,1),0.2)':s=44100:d=60", '-c:a', 'libmp3lame', '-b:a', '64k', f], check=True)
BLANK = os.path.join(a.state, 'pub', '空白音频.mp3')
if not os.path.isfile(BLANK):
    subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono', '-t', '5', '-c:a', 'libmp3lame', '-b:a', '32k', BLANK], check=True)
PC, PH = f'http://127.0.0.1:{a.port}', f'http://127.0.0.1:{a.port + 1}'
IOS = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1'
fails, errs = [], []


def check(name, ok, info=''):
    print(('通过 ' if ok else '失败 ') + name + (f'  {info}' if info else ''), flush=True)
    if not ok:
        fails.append(name)


def until(fn, secs=6, step=0.2):
    end = time.time() + secs
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return fn()


def open_folder(pg, src):
    pg.evaluate("document.querySelector('.ps-back, .pl-back')?.click()") if pg.locator(f'.ps-item[data-src="{src}"]').count() == 0 else None
    pg.click(f'.ps-item[data-src="{src}"]')
    pg.wait_for_selector('.pl-row', timeout=10000)


def unlock(ctx, base):
    r = ctx.request.post(base + '/api/vault/unlock', data={'key': 'testky'})
    assert r.ok, r.text()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pc = b.new_context(viewport={'width': 1440, 'height': 900})
    ph = b.new_context(viewport={'width': 402, 'height': 874}, user_agent=IOS, has_touch=True, is_mobile=True, device_scale_factor=3)
    code = pc.request.post(PC + '/api/remote/code').json()['code']
    assert ph.request.post(PH + '/api/remote/pair', data={'code': code, 'name': '测试手机'}).ok
    unlock(pc, PC); unlock(ph, PH)
    P, M = pc.new_page(), ph.new_page()
    for pg, who in ((P, '电脑'), (M, '手机')):
        pg.on('pageerror', lambda e, w=who: errs.append(f'{w}: {e}'))
        pg.on('response', lambda r, w=who: r.status >= 400 and '/api/rc/' in r.url and '/api/rc/cmd' not in r.url and errs.append(f'{w} {r.status} {r.request.method} {r.url}'))  # 只看遥控的接口（刚打开时别的接口的 409、没封面的 404 是原来就有的）
        pg.add_init_script("document.addEventListener('play', e => { e.target.muted = true; }, true);")
        pg.add_init_script("sessionStorage.getItem('sessT0') || sessionStorage.setItem('sessT0', String(Date.now())); sessionStorage.setItem('vaultTab', '1');")  # 新标签页默认不沿用私密空间：当成是在这个标签页里进的
    P.goto(PC + '/play'); M.goto(PH + '/play')
    until(lambda: P.evaluate('VAULT') and M.evaluate('VAULT && REMOTE'), 10)
    check('两边都在私密空间、手机端被认成手机', P.evaluate('VAULT && !REMOTE') and M.evaluate('VAULT && REMOTE'))
    if P.evaluate('document.body.classList.contains("pb-min")'): P.click('#pb-fab')  # 测试数据里播放条是收起的：先展开
    check('电脑在私密空间里：手机图标一直在（手机还没播放）', until(lambda: P.evaluate('!document.getElementById("pb-rc").hidden'), 4))

    # ---- 一：电脑先开启控制，手机（私密空间）再播放
    P.click('#pb-rc')
    check('开启控制：播放条显示“等待手机播放”', until(lambda: P.locator('#pb-sub').inner_text() == '等待手机播放' and 'rc' in P.get_attribute('#pbar', 'class'), 4), P.locator('#pb-sub').inner_text())
    open_folder(M, 'd:遥控测试')
    M.locator('.pl-row').nth(0).click()
    check('手机开始播放', until(lambda: M.evaluate('!!qCur() && !qAudio.paused && qAudio.currentTime > 0.2'), 8))
    check('点播放的那一下：无声播放器已经启动过一次', M.evaluate('RC.primed && !!RC.kel && RC.kel.paused'))
    M.evaluate('window._k1 = RC.kel')
    title = M.evaluate('qCur().title')
    check('电脑上显示手机在放的', until(lambda: P.locator('#pb-title').inner_text() == title, 6), P.locator('#pb-title').inner_text() + ' / ' + P.locator('#pb-sub').inner_text())
    t1 = P.evaluate('PB.ext.t'); time.sleep(1.2); t2 = P.evaluate('PB.ext.t')
    check('电脑上的进度跟着走', t2 > t1 + 0.6, f'{t1:.1f} → {t2:.1f}')
    check('控制时音量藏起来、播放列表在', P.locator('#vol-ctl').is_hidden() and P.locator('#pb-queue').is_visible())
    P.click('[data-pb="play"]')
    check('暂停：手机停了、在放无声音频', until(lambda: M.evaluate('qAudio.paused && !!RC.keep && !RC.keep.paused'), 4))
    check('暂停：用的是点播放时启动过的那一个', M.evaluate('RC.keep === window._k1'))
    P.click('[data-pb="play"]')
    check('继续：手机接着放、无声音频停掉', until(lambda: M.evaluate('!qAudio.paused && !RC.keep'), 4))
    c0 = M.evaluate('qAudio.currentTime'); P.evaluate("document.querySelector('[data-pb=fwd]').click()")  # 11-17 播放条改版后“前进 10 秒”按钮不显示了（功能还在）
    check('快进：手机前进约 10 秒', until(lambda: M.evaluate('qAudio.currentTime') > c0 + 7, 4))
    d = M.evaluate('pbDur(qAudio)'); box = P.locator('#pb-track').bounding_box()
    P.mouse.click(box['x'] + box['width'] * 0.3, box['y'] + box['height'] / 2)
    check('拖进度：手机跳到 30% 左右', until(lambda: abs(M.evaluate('qAudio.currentTime') - d * 0.3) < max(3, d * 0.05), 4))
    P.click('[data-pb="next"]')
    check('下一首：手机换了一首、电脑标题跟着换', until(lambda: M.evaluate('PB.q.i') == 1 and P.locator('#pb-title').inner_text() == M.evaluate('qCur().title'), 5))
    open_folder(P, 'd:遥控测试')
    P.locator('.pl-row').nth(0).dblclick()
    check('在电脑上点一首：交给手机放，电脑不出声', until(lambda: M.evaluate('qCur().title') == title and not M.evaluate('qAudio.paused'), 5) and P.evaluate('qAudio.paused'))
    P.evaluate("qAudio.play().catch(()=>{})")
    check('电脑播放器被直接放：转成手机暂停', until(lambda: M.evaluate('qAudio.paused') and P.evaluate('qAudio.paused'), 4))
    P.click('[data-pb="play"]'); until(lambda: not M.evaluate('qAudio.paused'), 4)

    # 全屏播放页 + 字幕 + 播放列表（控制手机时）
    P.click('#pb-now')
    check('控制手机时能打开全屏播放页', until(lambda: P.evaluate("!document.getElementById('np').hidden && document.getElementById('np-title').textContent") == title, 4))
    a0 = P.evaluate("document.getElementById('np-t0').textContent"); time.sleep(1.6)
    check('全屏页的进度跟着手机走', P.evaluate("document.getElementById('np-t0').textContent") != a0, a0)
    P.evaluate("document.querySelector('.np-tabs [data-np=\"subs\"]')?.click()")
    check('全屏页有字幕入口（这首还没字幕：转换字幕）', until(lambda: P.evaluate("!!document.getElementById('np-gen')"), 5), P.evaluate("document.getElementById('np-right').innerText.slice(0, 60)"))
    check('全屏页的音效按钮藏起来', P.locator('#np-fxm').is_hidden())
    check('全屏页能收藏手机正在放的那首', P.evaluate("!document.getElementById('np-fav').hidden"))
    P.evaluate('RCA.currentTime = 20')  # 点字幕里的一句 = 这样让手机跳过去
    check('字幕跳转：手机跳到 20 秒', until(lambda: abs(M.evaluate('qAudio.currentTime') - 20) < 2.5, 4), f"{M.evaluate('qAudio.currentTime'):.1f}")
    qt = "[...document.querySelectorAll('%s .ql-row .ql-t')].map(x => x.textContent.trim())"
    P.evaluate("document.querySelector('.np-tabs [data-np=\"queue\"]')?.click()")
    check('全屏页的播放列表是手机的', until(lambda: P.evaluate(qt % '#np-right') == ['测试音 1', '测试音 2'], 5), repr(P.evaluate(qt % '#np-right')))
    P.locator('#np-right .ql-row').nth(1).click()
    check('在全屏页的播放列表里点第二首 → 手机跳过去', until(lambda: M.evaluate('PB.q.i') == 1 and P.evaluate("document.getElementById('np-title').textContent") == '测试音 2', 5))
    P.evaluate("document.querySelector('.np-tabs [data-np=\"subs\"]')?.click()")
    if a.shot:
        P.add_style_tag(content='img, video { visibility: hidden !important; }'); P.wait_for_timeout(300)
        P.screenshot(path=a.shot.replace('.png', '_np.png'))
    P.click('#np-close'); P.wait_for_timeout(400)
    P.click('#pb-queue')
    check('播放条上的播放列表也是手机的', until(lambda: P.evaluate(qt % '#qpanel') == ['测试音 1', '测试音 2'], 4))
    P.locator('#qpanel .ql-row').nth(0).click()
    check('在播放条的播放列表里点第一首 → 手机跳回去', until(lambda: M.evaluate('PB.q.i') == 0 and not M.evaluate('qAudio.paused'), 5))
    P.evaluate('qPanelClose()')

    # ---- 二：手机在私密空间里放着，主动退出私密空间 → 接着放（换成一次性地址），电脑照样能控制
    tb = M.evaluate('qAudio.currentTime')
    M.evaluate('vaultLock()')
    check('手机退出私密空间：接着放', until(lambda: M.evaluate('!VAULT && qCur()?.rc === true && !qAudio.paused && qAudio.currentTime > 0.2'), 8))
    check('手机退出私密空间：从原来的位置接着放', abs(M.evaluate('qAudio.currentTime') - tb) < 4, f"{tb:.1f} → {M.evaluate('qAudio.currentTime'):.1f}")
    check('手机上放的是一次性地址', M.evaluate("qAudio.currentSrc.includes('/api/rc/m/')"))
    ptxt = M.evaluate("document.getElementById('pb-title').textContent + '|' + document.getElementById('pb-sub').textContent + '|' + (navigator.mediaSession?.metadata?.title || '')")
    check('手机上不露出私密内容的名字', '测试音' not in ptxt and '遥控测试' not in ptxt and '电脑控制播放' in ptxt, ptxt)
    check('电脑上照样显示真名', until(lambda: P.locator('#pb-title').inner_text() == title and P.locator('#pb-sub').inner_text().startswith('手机'), 5), P.locator('#pb-title').inner_text())
    P.click('[data-pb="play"]')
    check('手机不在私密空间：电脑暂停 → 手机停了、在放无声音频', until(lambda: M.evaluate('qAudio.paused && !!RC.keep'), 4))
    check('再次暂停：还是同一个无声播放器（不重建）', M.evaluate('RC.keep === window._k1 && !RC.keep.paused'))
    P.click('[data-pb="play"]')
    check('手机不在私密空间：电脑继续 → 手机接着放', until(lambda: M.evaluate('!qAudio.paused && !RC.keep'), 4))
    P.click('#pb-queue')
    check('手机不在私密空间：电脑上的播放列表是真名', until(lambda: P.evaluate(qt % '#qpanel') == ['测试音 1', '测试音 2'], 5), repr(P.evaluate(qt % '#qpanel')))
    P.evaluate('qPanelClose()')
    P.click('#pb-now')
    check('手机不在私密空间：电脑的全屏页有字幕入口', until(lambda: P.evaluate("!!document.getElementById('np-gen')"), 5))
    P.click('#np-close'); P.wait_for_timeout(400)
    check('手机不在私密空间：手机的播放列表里没有真名', '测试音' not in M.evaluate("qListHtml()"))
    P.click('[data-pb="next"]')
    check('手机不在私密空间：下一首', until(lambda: M.evaluate('PB.q.i') == 1 and P.locator('#pb-title').inner_text() == '测试音 2', 5), P.locator('#pb-title').inner_text())
    open_folder(P, 'd:遥控测试')
    P.locator('.pl-row').nth(0).dblclick()
    check('手机不在私密空间：在电脑上点一首 → 手机放', until(lambda: M.evaluate("qCur()?.rc && PB.q.i === 0 && !qAudio.paused") and P.locator('#pb-title').inner_text() == title, 6))
    check('换一首再点回来：手机接着上次的位置放（不从头）', until(lambda: M.evaluate('qAudio.currentTime') > 15, 5), f"{M.evaluate('qAudio.currentTime'):.1f}")
    url = M.evaluate('qAudio.currentSrc').replace(PH, '')
    check('一次性地址：别的设备拿不到', b.new_context().request.get(PH + url).status in (401, 404) and pc.request.get(PC + url).status == 404)
    check('手机普通空间的播放页没有私密内容', '测试音' not in M.evaluate('document.body.innerText'))

    # ---- 三：电脑关掉控制 → 手机上电脑发去的私密内容停掉、清掉
    P.click('#pb-rc')
    check('电脑关掉控制：手机上的私密内容停掉', until(lambda: M.evaluate('!qCur() && qAudio.paused && !RC.keep'), 8))
    check('电脑关掉控制：一次性地址作废', ph.request.get(PH + url).status == 404)
    check('电脑关掉控制：播放条回到自己的', not P.evaluate('RC.ctl') and 'rc' not in P.get_attribute('#pbar', 'class'))

    # ---- 四：手机在普通空间先放空白音频，电脑再开启控制，电脑点私密内容 → 手机放
    M.evaluate("go('play')"); M.wait_for_selector('#play-q', timeout=8000); M.wait_for_timeout(1200)  # 退出私密空间后在配音页；等播放页画完再搜
    M.fill('#play-q', '空白音频'); M.wait_for_timeout(600)
    M.locator('.pl-row', has_text='空白音频').first.click()
    check('手机（普通空间）放空白音频', until(lambda: M.evaluate("qCur()?.title === '空白音频' && !qAudio.paused"), 6))
    P.click('#pb-rc')
    check('电脑开启控制：看到手机在放空白音频', until(lambda: P.locator('#pb-title').inner_text() == '空白音频', 6), P.locator('#pb-title').inner_text())
    open_folder(P, 'd:遥控测试')
    P.locator('.pl-row').nth(1).dblclick()
    check('电脑点私密内容 → 普通空间的手机放', until(lambda: M.evaluate("qCur()?.rc && !qAudio.paused") and P.locator('#pb-title').inner_text() == '测试音 2', 8), P.locator('#pb-title').inner_text())
    # 控制手机时电脑自己放了别的：手机先暂停、控制保持开着；再点手机图标接着放
    until(lambda: M.evaluate('qAudio.currentTime') > 3, 6)
    P.evaluate("window._pa = new Audio(); _pa.src = '/media/lib/' + encodeURIComponent('遥控测试') + '/' + encodeURIComponent('测试音 1.mp3'); pbRegister(_pa, () => ({ title: '电脑本机' })); _pa.play()")
    check('电脑放别的：手机先暂停', until(lambda: M.evaluate('qAudio.paused'), 5))
    tp = M.evaluate('qAudio.currentTime')
    check('电脑放别的：播放条回到电脑自己的、控制保持开着', not P.evaluate('RC.ctl') and P.evaluate('RC.parked > 0') and pc.request.get(PC + '/api/rc/view').json()['armed'])
    check('电脑放别的：手机上的内容还在（没被清掉）', M.evaluate('qCur()?.rc === true'))
    P.evaluate('_pa.pause()')
    P.click('#pb-rc')
    check('再点手机图标：接着控制，手机还停在原来的位置', until(lambda: P.evaluate('RC.ctl') and P.evaluate('PB.ext && PB.ext.paused'), 5) and abs(M.evaluate('qAudio.currentTime') - tp) < 1)
    P.click('[data-pb="play"]')
    check('继续：手机从原来的位置接着放', until(lambda: not M.evaluate('qAudio.paused'), 5) and M.evaluate('qAudio.currentTime') >= tp - 0.5, f"{tp:.1f} → {M.evaluate('qAudio.currentTime'):.1f}")
    check('播放进度、最近播放都没记', M.evaluate("!Object.keys(JSON.parse(localStorage.getItem('playpos') || '{}')).some(k => k.includes('遥控测试'))"))

    # 齿轮：手机（普通空间）有“允许电脑控制”，电脑没有
    for pg, who, want in ((M, '手机', True), (P, '电脑', False)):
        pg.evaluate('document.getElementById("side-gear").click()')
        has = until(lambda: pg.evaluate('!!document.getElementById("gear-rc")'), 2)
        check(f'{who}齿轮里{"有" if want else "没有"}“允许电脑控制”', bool(has) == want and (not want or pg.evaluate('document.getElementById("gear-rc").checked')))
        pg.keyboard.press('Escape'); pg.evaluate('curPop && curPop.close(true)')
    if a.shot:
        P.add_style_tag(content='img, video, .pl-card .pc-art { visibility: hidden !important; }')
        P.locator('#pbar').screenshot(path=a.shot)
        M.add_style_tag(content='img, video { visibility: hidden !important; }')
        M.screenshot(path=a.shot.replace('.png', '_phone.png'))

    # ---- 五：电脑退出私密空间 → 手机上的私密内容停掉
    P.evaluate('vaultLock()')
    check('电脑退出私密空间：手机上的私密内容停掉', until(lambda: M.evaluate('!qCur() && !RC.keep'), 8))
    check('电脑退出私密空间：没有手机图标', until(lambda: P.evaluate('document.getElementById("pb-rc").hidden'), 3))
    nr = b.new_context().request.get(PC + '/api/rc/view')
    check('不在私密空间：电脑的接口不存在', nr.status == 404, str(nr.status))

    # ---- 六：自动开启（手机在放，电脑在私密空间里就自动打开控制）
    unlock(pc, PC); P.evaluate("sessionStorage.setItem('vaultTab', '1'); vaultEnter()")
    until(lambda: P.evaluate('VAULT'), 5)
    if P.evaluate('document.body.classList.contains("pb-min")'): P.click('#pb-fab')
    M.fill('#play-q', ''); M.wait_for_timeout(300); M.fill('#play-q', '空白音频'); M.wait_for_timeout(800)
    M.evaluate("S.qmode.repeat = 'one'")  # 空白音频只有 5 秒：单曲循环，一直算“在放”
    M.locator('.pl-row', has_text='空白音频').first.click()
    check('自动开启：手机（普通空间）一放，电脑自动打开控制', until(lambda: P.evaluate('RC.ctl && RC.auto'), 10) and until(lambda: P.locator('#pb-title').inner_text() == '空白音频', 6),
          P.locator('#pb-title').inner_text())
    P.click('#pb-rc')
    time.sleep(7)
    check('手动关掉以后：手机还在放也不再自动打开', not P.evaluate('RC.ctl'))
    P.evaluate('RC.noAuto = false')  # 当成手机停过一阵、新的一轮
    check('新的一轮：又自动打开', until(lambda: P.evaluate('RC.ctl && RC.auto'), 8))
    P.click('[data-pb="play"]')  # 让手机暂停：后台过一阵就不再算“有手机在放”
    until(lambda: M.evaluate('qAudio.paused'), 4)
    time.sleep(27)
    P.evaluate('RC.act = Date.now() - 61000')  # 当成已经停了 1 分钟
    check('自动打开的：手机停下 1 分钟后自动关掉', until(lambda: not P.evaluate('RC.ctl'), 5))
    check('自动关掉后：播放条回到电脑自己的', 'rc' not in P.get_attribute('#pbar', 'class'))
    M.evaluate('pbReset(true); rcBye()'); M.wait_for_timeout(800)  # 手机正常停下（告诉后台），下一轮测试不会看到这台旧手机
    b.close()

print('页面错误：' + ('；'.join(errs) if errs else '无'))
print('结果：' + ('全部通过' if not fails and not errs else f'{len(fails)} 项失败：' + '、'.join(fails)))
sys.exit(1 if fails or errs else 0)
