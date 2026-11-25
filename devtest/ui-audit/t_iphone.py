"""手机界面回归测试（模拟 iPhone，WebKit，见 iphone.py）：python t_iphone.py
- 生图输入框下面那排按钮只占一行
- 点一下“+”直接进素材库；其它来源在“···”里
- 涂抹大图：两指张开 / 捏合缩放
- 生成结果的缩略图都加载出来（加载失败会自己重试）
失败的项前面打 ✗，最后一行是通过数。截图前藏起图片和视频"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


def tap(pg, sel):
    b = pg.query_selector(sel).bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(700)


if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("go('img')"); pg.wait_for_timeout(2000); hide(pg)
        # 一排按钮
        h = pg.evaluate("document.querySelector('.ig-cbar > .bar-l').getBoundingClientRect().height")
        check('生图：按钮只占一行', h < 48, h)
        # 点一下进素材库
        pg.evaluate("document.querySelector('.ig-srct .ig-srct-x')?.click()"); pg.wait_for_timeout(400)
        tap(pg, '.ig-srct')
        check('点一下“+”：直接打开素材库', bool(pg.query_selector('.gal-m')), pg.evaluate("[...document.querySelectorAll('.ctx-menu, .ig-panel:not([hidden])')].length"))
        check('素材库窗口右上角有“其他来源”', bool(pg.query_selector('.gal-m .gal-alt-more')))
        if pg.query_selector('.gal-m .gal-alt-more'):
            tap(pg, '.gal-m .gal-alt-more')
            labs = pg.evaluate("[...document.querySelectorAll('.ctx-menu > *')].map(b => b.textContent.trim())")
            check('“其他来源”里有照片或文件、生图图库', any('照片或文件' in x for x in labs) and any('生图图库' in x for x in labs), labs)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
        pg.evaluate("document.querySelector('.gal-m [data-close]')?.click()"); pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(HERE, 'shots_iphone', 't_img.png'))
        # 缩略图第一次下载被打断（切后台 / 网络断一下）：自己重试，最后都加载出来
        seen = {}
        def flaky(route):
            u = route.request.url.split('&rt=')[0].split('?rt=')[0]
            seen[u] = seen.get(u, 0) + 1
            return route.abort() if seen[u] == 1 and len(seen) <= 6 else route.continue_()
        pg.context.route('**/media/img/**', flaky)
        pg.reload(); pg.wait_for_timeout(2500); hide(pg); pg.evaluate("go('img')"); pg.wait_for_timeout(8000)
        st = pg.evaluate("(() => { const ims = [...document.querySelectorAll('.ig-gal-card img')].slice(0, 6); return ims.map(i => [i.complete, i.naturalWidth, i.dataset.rt || '']); })()")
        check('缩略图第一次失败：自己重试后加载出来', st and all(w > 0 for _, w, _ in st), st)
        check('确实有缩略图被打断过', any(v > 1 for v in seen.values()), list(seen.values())[:8])
        pg.context.unroute('**/media/img/**')
        # 局部重画：两指缩放（合成两个触摸指针；格子图是测试自己画的）
        tap(pg, '#ig-model'); pg.evaluate("document.querySelector('.igm-v[data-m=\"q21\"]')?.click()"); pg.wait_for_timeout(900)
        pg.query_selector('#ig-file').set_input_files(os.path.join(HERE, 'aud_grid.png')); pg.wait_for_timeout(1500)
        pg.evaluate("document.querySelector('#ig-mode button[data-k=\"inpaint\"]')?.click()"); pg.wait_for_timeout(1200)
        if not pg.evaluate("!!document.querySelector('#ig-src canvas')?.offsetParent"):
            tap(pg, '.ig-srct'); pg.wait_for_timeout(800)
        PIN = """async ([dx0, dx1, steps]) => { const cv = document.querySelector('#ig-src canvas'); cv.setPointerCapture = () => {}; cv.releasePointerCapture = () => {};
          const r = cv.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2, H = IMG_MASK._h, u0 = H.u.length;
          const ev = (t, id, x) => cv.dispatchEvent(new PointerEvent(t, { pointerId: id, pointerType: 'touch', isPrimary: id === 1, clientX: x, clientY: cy, bubbles: true, cancelable: true, buttons: t === 'pointerup' ? 0 : 1 }));
          ev('pointerdown', 1, cx - dx0); ev('pointermove', 1, cx - dx0 - 2); ev('pointerdown', 2, cx + dx0);
          for (let i = 1; i <= steps; i++) { const d = dx0 + (dx1 - dx0) * i / steps; ev('pointermove', 1, cx - d); ev('pointermove', 2, cx + d); await new Promise(r => setTimeout(r, 16)); }
          ev('pointerup', 2, cx + dx1); ev('pointermove', 1, cx - dx1 + 30); ev('pointerup', 1, cx - dx1 + 30);
          const z = cv.closest('.ig-src')._zm; return { z: Math.round(z.z * 100) / 100, undo: H.u.length - u0, pill: document.querySelector('.ig-zoom-b')?.textContent || '' }; }"""
        if pg.evaluate("!!document.querySelector('#ig-src canvas')?.offsetParent"):
            r1 = pg.evaluate(PIN, [40, 120, 10])
            check('涂抹：两指张开放大（大约 3 倍），刚落下那一指没留下涂痕', 2.5 < r1['z'] < 3.5 and r1['undo'] == 0, r1)
            r2 = pg.evaluate(PIN, [120, 40, 10])
            check('涂抹：两指捏合缩回', r2['z'] < 1.2, r2)
        else:
            check('涂抹：找到画布', False, pg.evaluate("[document.querySelector('#ig-src canvas') ? 'hidden' : 'none', S.img.model, S.img.mode, !!document.querySelector('.ig-srct img'), !!document.querySelector('.ph-sheet')]"))
        # 长按作品格子：出菜单（iPhone 的 Safari 长按不会触发右键菜单，phone.js 补上）
        pg.evaluate("document.querySelector('.ph-sheet-done')?.click()"); pg.wait_for_timeout(500)
        LP = """async () => { const t = document.querySelector('.ig-gal .ig-tile'); if (!t) return 'no tile'; const r = t.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
          const tc = { identifier: 1, target: t, clientX: x, clientY: y };  // WebKit 桌面版不能 new Touch：用带 touches 的普通事件
          const ev = (n, ts) => { const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: ts }); Object.defineProperty(e, 'changedTouches', { value: [tc] }); t.dispatchEvent(e); };
          ev('touchstart', [tc]); await new Promise(r => setTimeout(r, 650)); ev('touchend', []);
          const m = document.querySelector('.ctx-menu'); return m ? [...m.children].map(c => c.textContent.trim()).filter(Boolean).slice(0, 4) : 'no menu'; }"""
        lp = pg.evaluate(LP)
        check('长按作品：出菜单（详情、全屏查看、复用……）', isinstance(lp, list) and any('详情' in x for x in lp), lp)
        pg.evaluate("ctxClose(true)"); pg.wait_for_timeout(300)  # 关掉菜单（菜单开着时，下一下点击只用来关菜单）
        # 空的输入框只有一行高（占位提示不把框撑高）
        pg.evaluate("(() => { const t = document.querySelector('#ig-prompt'); t.value = ''; t.dispatchEvent(new Event('input', { bubbles: true })); })()"); pg.wait_for_timeout(300)
        th = pg.evaluate("document.querySelector('#ig-prompt').offsetHeight")
        check('空输入框一行高', th <= 44, th)
        # ---- 11-16 用户看过第 2 步后的问题 ----
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        m = pg.evaluate("""() => { const f = document.querySelector('.ig-top-f'), comp = f.querySelector('.ig-composer').getBoundingClientRect(), bar = f.querySelector('.ig-cbar').getBoundingClientRect(), rail = document.getElementById('rail').getBoundingClientRect(), bl = f.querySelector('.ig-cbar > .bar-l');
          return { barToComp: comp.top - bar.bottom, compToBottom: innerHeight - comp.bottom, rail: getComputedStyle(document.getElementById('rail')).display, oy: getComputedStyle(bl).overflowY, ta: getComputedStyle(bl).touchAction }; }""")
        check('底部：选项和输入框之间至少 8px', m['barToComp'] >= 8, m)
        check('生图：不显示底栏（页面在左边侧栏）', m['rail'] == 'none', m)
        check('底部：输入框离屏幕底边留出底部横条 + 8px', m['compToBottom'] >= 34 + 8, m)
        # 侧栏：≡ 打开、当前页高亮、点外面关；从左边缘往右滑也能打开
        tap(pg, '.ph-menu-b'); pg.wait_for_timeout(300)  # 真的点按（有按下）：长按菜单那套会挡住“没有按下的点击”
        d = pg.evaluate("[document.body.classList.contains('ph-dw-open'), [...document.querySelectorAll('#ph-dw .ph-dw-nav a')].map(a => a.textContent.trim() + (a.classList.contains('on') ? '*' : ''))]")
        check('侧栏：≡ 打开，列出全部页面，生图高亮', d[0] and '生图*' in d[1] and len(d[1]) >= 10, d)
        pg.touchscreen.tap(pg.viewport_size['width'] - 20, 500); pg.wait_for_timeout(500)  # 点侧栏右边露出来的那块（遮罩正中被侧栏盖着）
        check('侧栏：点外面关上（还在生图页）', not pg.evaluate("document.body.classList.contains('ph-dw-open')") and pg.evaluate("document.getElementById('main').dataset.page") == 'img')
        pg.evaluate("""(() => { const ev = (n, x) => { const e = new Event(n, { bubbles: true }); const t = { clientX: x, clientY: 500 }; Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); document.body.dispatchEvent(e); };
          ev('touchstart', 6); for (let x = 20; x <= 200; x += 20) ev('touchmove', x); ev('touchend', 200); })()"""); pg.wait_for_timeout(700)  # 真的拖（11-16 起侧栏跟着手指走，要有移动）
        check('侧栏：从屏幕左边缘往右滑打开', pg.evaluate("document.body.classList.contains('ph-dw-open')"))
        pg.evaluate("document.querySelector('#ph-dw [data-ph-go=mats]').click()"); pg.wait_for_timeout(1500)
        r2 = pg.evaluate("[document.getElementById('main').dataset.page, getComputedStyle(document.getElementById('rail')).display, Math.round(innerHeight - document.getElementById('rail').getBoundingClientRect().bottom)]")
        check('侧栏：点素材库就过去；所有页面都不显示底栏', r2[0] == 'mats' and r2[1] == 'none', r2)
        pg.evaluate("go('prompt')"); pg.wait_for_timeout(1500)
        pg.evaluate("document.getElementById('pg-hist-m')?.click()"); pg.wait_for_timeout(600)
        n2 = pg.evaluate("[...document.querySelectorAll('#pg-hist > .ph-dw-nav > a')].map(a => a.textContent.trim())")
        check('AI 助手：抽屉最上面是常用页面，其余收进“更多页面”', 3 <= len(n2) <= 6 and pg.evaluate("!!document.querySelector('#pg-hist .ph-dw-more')"), n2)
        pg.evaluate("document.body.classList.remove('pg-hist-open')"); pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        check('选项那排只能左右滑', m['oy'] == 'hidden' and 'pan-x' in m['ta'], m)
        # “⋯”和胶囊在同一行（不管胶囊多少：放了图、局部重画时胶囊最多）
        for st_js in ("", 'document.querySelector("#ig-model").click(); setTimeout(() => document.querySelector(".igm-v[data-m=q21]")?.click(), 400)'):
            if st_js: pg.evaluate(st_js); pg.wait_for_timeout(1500)
            one = pg.evaluate("(() => { const m = document.querySelector('#main .ig-top-f .ph-more-b'), c = document.querySelector('#main .ig-top-f .ig-chips'); if (!m || !c) return null; const a = m.getBoundingClientRect(), b = c.getBoundingClientRect(); return Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2) < 4; })()")
            check('“⋯”和选项胶囊在同一行' + ('（换了模型）' if st_js else ''), one, one)
        hd = pg.evaluate("() => { scrollTo(0, 700); return new Promise(r => setTimeout(() => r(document.querySelector('#main > .page-head').getBoundingClientRect().bottom), 700)); }")
        check('标题栏收起后不超过 安全区 + 70', hd <= 62 + 70.5, hd)  # 11-17 用户要标题栏离状态栏远一点（按钮上沿在安全区下面 16pt），原来是 + 56
        pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(300)
        # 键盘：手指离开输入框那一下就先把输入框抬到键盘的高度（iOS 不再把整页推上去）；底栏、播放条藏起来
        pg.evaluate("window.__phNoKbCheck = true")  # 模拟器里没有键盘：关掉“键盘没出来就放回底部”的保险，只测抬起和聚焦
        b0 = pg.evaluate("document.querySelector('.ig-top-f').getBoundingClientRect().bottom")
        ta = pg.query_selector('#ig-prompt').bounding_box(); pg.touchscreen.tap(ta['x'] + 40, ta['y'] + ta['height'] / 2); pg.wait_for_timeout(900)  # 只点一下：要真的聚焦到输入框（11-16 键盘弹不出来的 bug：点击落空了）
        k = pg.evaluate("[document.documentElement.classList.contains('ph-kb'), document.querySelector('.ig-top-f').getBoundingClientRect().bottom, getComputedStyle(document.getElementById('rail')).display, document.activeElement && document.activeElement.id]")
        check('点输入框：输入框真的聚焦了（键盘会弹出来）', k[3] == 'ig-prompt', k)
        check('点输入框：先抬到键盘的高度、底栏藏起来', k[0] and k[1] < b0 - 200 and k[2] == 'none', [b0] + k)
        pg.wait_for_timeout(800)
        check('点输入框：过一会儿还停在键盘上面（不会自己掉回去）', pg.evaluate("document.documentElement.classList.contains('ph-kb') && document.activeElement.id === 'ig-prompt'"))
        pg.evaluate("window.__phNoKbCheck = false; document.activeElement.blur()"); pg.wait_for_timeout(500)
        # 保险：键盘没出来（模拟器里就是这样）→ 0.9 秒后放回底部，不悬在半空
        ta = pg.query_selector('#ig-prompt').bounding_box(); pg.touchscreen.tap(ta['x'] + 40, ta['y'] + ta['height'] / 2); pg.wait_for_timeout(1300)
        check('键盘没出来：输入框放回底部（不悬在半空）', not pg.evaluate("document.documentElement.classList.contains('ph-kb')") and abs(pg.evaluate("document.querySelector('.ig-top-f').getBoundingClientRect().bottom") - b0) < 2)
        pg.evaluate("document.activeElement.blur()"); pg.wait_for_timeout(500)
        check('收起键盘：输入框回到底栏上面', not pg.evaluate("document.documentElement.classList.contains('ph-kb')") and abs(pg.evaluate("document.querySelector('.ig-top-f').getBoundingClientRect().bottom") - b0) < 2)
        # 弹窗从底部升起、铺满宽度；往下拉关闭
        pg.evaluate("go('video')"); pg.wait_for_timeout(1800); hide(pg)
        pg.evaluate("document.querySelector('#vd-gal > .vd-tile')?.click()"); pg.wait_for_timeout(1200)
        pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
        r = pg.evaluate("(() => { const m = document.querySelector('.modal-bg > .modal'); if (!m) return null; const b = m.getBoundingClientRect(); return [b.width, innerWidth, Math.round(innerHeight - b.bottom)]; })()")
        check('视频详情：从底部升起、铺满宽度', r and r[0] >= r[1] - 12 and r[2] <= 1, r)  # 模拟器里滚动条锁定时会让出 10px，真机没有
        if r:
            pg.evaluate("""async () => { const m = document.querySelector('.modal-bg > .modal'), b = m.getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + 20;
              const ev = (t, yy) => (t === 'pointerdown' ? m : window).dispatchEvent(new PointerEvent(t, { pointerId: 9, pointerType: 'touch', isPrimary: true, clientX: x, clientY: yy, bubbles: true }));
              ev('pointerdown', y); for (let i = 1; i <= 10; i++) { ev('pointermove', y + i * 20); await new Promise(r => setTimeout(r, 16)); } ev('pointerup', y + 200); }""")
            pg.wait_for_timeout(600)
            check('视频详情：往下拉关闭', not pg.evaluate("!!document.querySelector('.modal-bg:not(.out) > .modal')"))
        # 看大图：底部工具栏、往下拉关闭
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        pg.evaluate("document.querySelector('.ig-gal .ig-tile').click()"); pg.wait_for_timeout(900)
        bar = pg.evaluate("[...document.querySelectorAll('.iv-bar button')].map(b => b.textContent.trim())")
        check('看大图：底部工具栏 复用 / 改图 / 下载 / 详情 / 删除', bar == ['复用', '改图', '下载', '详情', '删除'], bar)
        pg.evaluate("""async () => { const st = document.querySelector('.iv-stage'); st.setPointerCapture = () => {};
          const ev = (t, y) => st.dispatchEvent(new PointerEvent(t, { pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: 220, clientY: y, bubbles: true, button: 0, buttons: t === 'pointerup' ? 0 : 1 }));
          ev('pointerdown', 400); for (let y = 410; y <= 620; y += 20) { ev('pointermove', y); await new Promise(r => setTimeout(r, 16)); } ev('pointerup', 620); }""")
        pg.wait_for_timeout(500)
        check('看大图：往下拉关闭', not pg.evaluate("ImageViewer.isOpen()"))
        # 素材库：文件夹两列带名字；文件夹里面三列方格、不写文件名
        pg.evaluate("go('mats')"); pg.wait_for_timeout(1500); hide(pg)
        pg.evaluate("[...document.querySelectorAll('.gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500)
        c1 = pg.evaluate("(() => { const g = document.querySelector('.gal-body .gal-grid'); return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0; })()")
        pg.evaluate("document.querySelector('.gal-body .gal-fd')?.click()"); pg.wait_for_timeout(1500)
        c2 = pg.evaluate("(() => { const g = document.querySelector('.gal-body .gal-grid'); const cap = g && g.querySelector('.gal-cap'); return g ? [getComputedStyle(g).gridTemplateColumns.split(' ').length, cap ? getComputedStyle(cap).display : 'none'] : null; })()")
        check('素材库：文件夹两列', c1 == 2, c1)
        check('素材库：文件夹里面三列方格、不写文件名', c2 and c2[0] == 3 and c2[1] == 'none', c2)
        check('素材库：“组合”格子空着时不占标题栏', pg.evaluate("(() => { const t = document.querySelector('.page-head .gal-tray'); return !t || getComputedStyle(t).display === 'none'; })()"))
        # 图少的时候：最后一排也能滑到输入框上面（11-16 用户：底下几张被输入框和底栏挡住、滑不上来）
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        for n in (6, 9, 12):
            r = pg.evaluate(f"""async () => {{ const g = document.querySelector('.ig-gal'); [...g.children].slice({n}).forEach(e => e.remove()); window.phPad?.(); await new Promise(r => setTimeout(r, 300)); scrollTo(0, 99999); await new Promise(r => setTimeout(r, 400));
              const last = g.lastElementChild.getBoundingClientRect(), tops = [...document.querySelectorAll('#main .ig-top-f, #rail')].filter(e => getComputedStyle(e).display !== 'none' && e.getClientRects().length).map(e => e.getBoundingClientRect().top); return [Math.round(last.bottom), Math.round(Math.min(...tops))]; }}""")
            check(f'只有 {n} 张图：滑到底，最后一排在输入框上面', r[0] <= r[1], r)
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'通过 {ok} / {ok + bad}')
