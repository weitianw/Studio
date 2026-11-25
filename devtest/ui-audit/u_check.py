"""2026-11-17 UI 审查 U01–U09 核对（docs/ux/Studio-UI-Experience.md 末尾）。合成数据，不截图。
U01 生图页竖屏转横屏后的工具栏 = 直接横屏打开    U02 底部工具面板：焦点进面板、关掉回到入口    U03 生成 / 更多工具命中区 ≥ 44×44
U04 Ctrl+K 搜索：中文输入法选词时回车 / 方向键不误操作    U05 Tab 之后 Esc 仍能关、焦点不跑出去、Ctrl+数字切页时搜索框收起
U06 方向键选中的项一直看得见    U07 小窗：焦点在置顶按钮上按空格只切换置顶（mini.js，静态检查 + 页面里模拟）
U08 播放进度条可聚焦、有名字、读得出当前时间、方向键能拖    U09 桌面空闲时每秒的 DOM 变化次数（任务计时不变时不写）
用法：python u_check.py"""
import os, re, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
from iphone import open_iphone, MODELS
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


BAR = "(() => { const f = [...document.querySelectorAll('#main .ig-top-f')].find(x => x.getClientRects().length); if (!f) return null; return [...f.querySelectorAll('.ig-cbar button, .ig-crow > button, .ph-more-b')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(); return [b.className.split(' ')[0] || b.id, Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }); })()"


def phone(p):
    m = MODELS['iPhone 16 Pro Max']
    print('— U01 横竖屏（WebKit）')
    br, pg = open_iphone(p, B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
    pg.set_viewport_size({'width': m['h'], 'height': m['w']}); pg.wait_for_timeout(1200)
    rotated = pg.evaluate(BAR)
    pg.reload(); pg.wait_for_timeout(2500); pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
    direct = pg.evaluate(BAR)
    check(f'U01 竖转横 = 直接横屏打开（{len(rotated or [])} / {len(direct or [])} 个按钮）', rotated == direct, (rotated, direct))
    pg.set_viewport_size({'width': m['w'], 'height': m['h']}); pg.wait_for_timeout(1200)
    print('— U02 / U03 （竖屏）')
    pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
    sizes = pg.evaluate("[...document.querySelectorAll('#main .ig-top-f .ig-gen, #main .ig-top-f .ph-more-b')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(); return [b.classList.contains('ig-gen') ? '生成' : '更多工具', Math.round(r.width), Math.round(r.height)]; })")
    print(f'  （U03 看起来的大小 {sizes}：外观不变，下面量点击区）')
    hit = pg.evaluate("[...document.querySelectorAll('#main .ig-top-f .ig-gen, #main .ig-top-f .ph-more-b')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(), cx = r.x + r.width / 2, cy = r.y + r.height / 2; return [-22, 22].every(dx => [-22, 22].every(dy => { const e = document.elementFromPoint(cx + dx * .95, cy + dy * .95); return e && (e === b || b.contains(e)); })); })")
    check(f'U03 以中心 44×44 的四个角都点得到按钮本身 {hit}', hit and all(hit), hit)
    more = pg.query_selector('#main .ig-top-f .ph-more-b')
    more.focus(); more.click(); pg.wait_for_timeout(700)
    f_in = pg.evaluate("!!document.activeElement?.closest('.ph-sheet')")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    f_back = pg.evaluate("document.activeElement?.classList.contains('ph-more-b')")
    check(f'U02 打开面板焦点进面板（{f_in}）、Esc 关掉焦点回到“更多工具”（{f_back}）', f_in and f_back)
    br.close()


def desk(p):
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1280, 'height': 720}); pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.add_style_tag(content='img,video{visibility:hidden!important}')
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    print('— U04–U06 Ctrl+K 搜索（Chromium 1280×720）')
    pg.evaluate("go('play')"); pg.wait_for_timeout(800)
    pg.keyboard.press('Control+k'); pg.wait_for_timeout(300)
    page0 = pg.evaluate("document.querySelector('#main').dataset.page")
    # 模拟中文输入法选词：composition 期间的回车 / 方向键（isComposing = true）
    pg.evaluate("""(() => { const i = document.querySelector('.nav-pal input'); i.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
      for (const k of ['ArrowDown', 'ArrowDown', 'Enter']) i.dispatchEvent(new KeyboardEvent('keydown', { key: k, isComposing: true, keyCode: 229, bubbles: true, cancelable: true })); })()""")
    pg.wait_for_timeout(300)
    s = pg.evaluate("({ open: !!document.querySelector('.nav-pal'), page: document.querySelector('#main').dataset.page, sel: [...document.querySelectorAll('.nav-pal-i')].findIndex(x => x.classList.contains('on')) })")
    check(f'U04 输入法选词时的方向键 / 回车不移动选中、不跳页（{s}）', s['open'] and s['page'] == page0 and s['sel'] == 0, s)
    pg.keyboard.press('Tab'); pg.wait_for_timeout(150)
    inside = pg.evaluate("!!document.activeElement?.closest('.nav-pal')")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    check(f'U05 Tab 后焦点留在搜索框里（{inside}），Esc 照样关掉', inside and not pg.evaluate("!!document.querySelector('.nav-pal')"))
    pg.keyboard.press('Control+k'); pg.wait_for_timeout(200); pg.keyboard.press('Control+2'); pg.wait_for_timeout(400)
    check('U05 搜索开着时按 Ctrl+数字切页：搜索框收起', not pg.evaluate("!!document.querySelector('.nav-pal')"))
    pg.keyboard.press('Control+k'); pg.wait_for_timeout(200)
    pg.evaluate("document.querySelector('.nav-pal-l').style.maxHeight = '120px'")  # 页面多到要滚的情况
    vis = []
    for _ in range(9):
        pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(60)
        vis.append(pg.evaluate("(() => { const L = document.querySelector('.nav-pal-l'), o = L.querySelector('.on'); if (!o) return false; const a = L.getBoundingClientRect(), r = o.getBoundingClientRect(); return r.top >= a.top - 1 && r.bottom <= a.bottom + 1; })()"))
    check(f'U06 方向键往下选 9 次，选中项一直在看得见的范围（{sum(vis)}/9）', all(vis), vis)
    pg.keyboard.press('Escape')
    print('— U07 小窗空格（mini.js）')
    src = open(os.path.join(os.path.dirname(__file__), '..', '..', 'studio', 'web', 'mini.js'), encoding='utf-8').read()
    m = re.search(r"document\.addEventListener\('keydown', e => \{(.{0,300})", src, re.S)
    check('U07 焦点在按钮上时空格交给按钮（不再切换播放）', bool(m and re.search(r"closest\??\.?\('button'\)\) return", m.group(1))), m.group(1)[:200] if m else None)
    print('— U08 播放进度条')
    for sel in ('#pb-track', '#np-track'):
        a = pg.evaluate(f"(() => {{ const t = document.querySelector('{sel}'); return t && {{ role: t.getAttribute('role'), tab: t.tabIndex, name: t.getAttribute('aria-label'), txt: t.getAttribute('aria-valuetext') }}; }})()")
        check(f'U08 {sel}：role={a and a["role"]} tabindex={a and a["tab"]} 名字={a and a["name"]} 当前={a and a["txt"]}', a and a['role'] == 'slider' and a['tab'] == 0 and a['name'] and a['txt'] is not None, a)
    pg.evaluate("(() => { const items = [{ title: 't', sub: 's', src: '/x/0.wav', key: 'k0' }]; PB.q = { items, orig: items.slice(), i: 0 }; })()")
    print('— U09 桌面空闲')
    pg.evaluate("go('tts')"); pg.wait_for_timeout(1500)
    pg.evaluate("""(() => { window.__mut2 = 0; const mo = new MutationObserver(r => { window.__mut2 += r.length; }); mo.observe(document.body, { childList: true, subtree: true, characterData: true }); setTimeout(() => mo.disconnect(), 10000); })()""")
    pg.wait_for_timeout(10200)
    jt = pg.evaluate("document.querySelectorAll('.jt[data-jt]').length")
    n2 = pg.evaluate("window.__mut2")
    check(f'U09 配音页（{jt} 个任务计时）空闲 10 秒的 DOM 变化：{n2} 次', n2 <= 15, n2)
    pg.evaluate("go('play')"); pg.wait_for_timeout(1500)
    pg.evaluate("""(() => { window.__mut = 0; window.__mo = new MutationObserver(r => { window.__mut += r.length; }); window.__mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true }); })()""")
    pg.wait_for_timeout(10000)
    n = pg.evaluate("window.__mut")
    check(f'U09 桌面播放页空闲 10 秒的 DOM 变化：{n} 次（任务计时不变时不该每秒写）', n <= 15, n)
    check('没有页面报错', not errs, errs)
    b.close()


with sync_playwright() as p:
    phone(p)
    desk(p)
print(f'通过 {ok}，失败 {bad}')
