"""看大图 / 放大视频（2026-11-16 用户：左右滑换图要有动画；放大视频要和放大图片一样，不要从下面升起的面板）。
模拟 iPhone 16 Pro Max：看大图里用 touch 指针左右拖，量拖到一半图跟着手指、松手后滑走换到下一张 / 不够远弹回；
生视频点一段：全屏黑底、播放器占满第一屏、在画面上往下拉能关。图片都是测试假图，视频不加载。截图在 shots_iphone/viewer。用法：python ip_viewer.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'viewer'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


# 在看大图的画面上用一根手指（touch 指针）从 x0 拖到 x1；hold = 停住不松手
SWIPE = r"""async ([x0, x1, steps, ms, hold]) => { const st = document.querySelector('.iv-stage'); st.setPointerCapture = () => {}; st.releasePointerCapture = () => {};
  const y = innerHeight / 2, ev = (t, x) => st.dispatchEvent(new PointerEvent(t, { pointerId: 9, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y, bubbles: true, cancelable: true, buttons: t === 'pointerup' ? 0 : 1 }));
  ev('pointerdown', x0); for (let i = 1; i <= steps; i++) { ev('pointermove', x0 + (x1 - x0) * i / steps); await new Promise(r => setTimeout(r, ms)); }
  window.__up = () => ev('pointerup', x1); if (!hold) ev('pointerup', x1); }"""
IDX = "document.querySelector('.iv-idx')?.textContent.split('/')[0].trim()"
TX = "(() => { const m = getComputedStyle(document.querySelector('.iv-stage')).transform; return m === 'none' ? 0 : Math.round(new DOMMatrix(m).m41); })()"

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true")
        pg.evaluate("go('img')"); pg.wait_for_timeout(1800); hide(pg)
        b = pg.query_selector('.ig-gal .ig-tile').bounding_box(); pg.touchscreen.tap(b['x'] + 30, b['y'] + 30); pg.wait_for_timeout(1200)
        i0 = pg.evaluate(IDX); W = pg.viewport_size['width']
        pg.evaluate(SWIPE, [300, 160, 10, 16, True]); pg.wait_for_timeout(80); mid = pg.evaluate(TX)
        check('看大图：横着拖，图跟着手指走（拖了 −140）', abs(mid + 140) <= 4, mid)
        pg.screenshot(path=os.path.join(OUT, 'iv_mid.png'))
        pg.wait_for_timeout(150); pg.evaluate("window.__up()"); pg.wait_for_timeout(100); out = pg.evaluate(TX)
        check('看大图：松手后继续往左滑出去（有动画，不是一下跳）', out < mid - 20, (mid, out))
        pg.wait_for_timeout(700)
        i1 = pg.evaluate(IDX); check('看大图：滑完换到下一张、图回到正中', i1 == str(int(i0) + 1) and pg.evaluate(TX) == 0, (i0, i1, pg.evaluate(TX)))
        # 慢慢拖一小段：弹回，不换
        pg.evaluate(SWIPE, [200, 160, 10, 30, True]); pg.wait_for_timeout(300); pg.evaluate("window.__up()"); pg.wait_for_timeout(500)
        check('看大图：只拖了一小段、慢慢松手 → 弹回、不换图', pg.evaluate(IDX) == i1 and pg.evaluate(TX) == 0, (pg.evaluate(IDX), pg.evaluate(TX)))
        # 快速一甩（只拖 60）：换
        pg.evaluate(SWIPE, [200, 260, 3, 12, False]); pg.wait_for_timeout(800)
        check('看大图：往右快甩一下 → 回到上一张', pg.evaluate(IDX) == i0, pg.evaluate(IDX))
        # 底栏下一张按钮也滑
        has_next = pg.evaluate("!!document.querySelector('.iv-bar [data-a=next], .iv [data-a=next]')")
        pg.evaluate("ImageViewer?.close?.()"); pg.wait_for_timeout(500)
        # 放大视频
        pg.evaluate("go('video')"); pg.wait_for_timeout(1800); hide(pg)
        b = pg.query_selector('#vd-gal > .vd-tile').bounding_box(); pg.touchscreen.tap(b['x'] + 40, b['y'] + 40); pg.wait_for_timeout(1200)
        pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
        r = pg.evaluate("""(() => { const m = document.querySelector('.modal-bg > .modal.vd-view'), bg = m?.parentElement, v = m?.querySelector('.vd-player'); if (!m) return null; const a = m.getBoundingClientRect(), c = v.getBoundingClientRect();
          return { m: [a.left, a.top, a.width, a.height].map(Math.round), bg: getComputedStyle(bg).backgroundColor, mbg: getComputedStyle(m).backgroundColor, rad: getComputedStyle(m).borderTopLeftRadius, v: [c.left, c.top, c.width, c.height].map(Math.round),
            grab: getComputedStyle(m, '::before').display, first: [...m.children].filter(e => !e.classList.contains('fr-marks')).sort((x, y) => x.getBoundingClientRect().top - y.getBoundingClientRect().top).map(e => e.className.split(' ')[0]).slice(0, 4) }; })()""")
        vw, vh = pg.viewport_size['width'], pg.viewport_size['height']
        check('放大视频：全屏（不是下面升起的面板）', r and r['m'] == [0, 0, vw, vh] and r['rad'] == '0px' and r['grab'] == 'none', r)
        check('放大视频：黑底', r and r['mbg'] in ('rgb(0, 0, 0)',) and r['bg'] in ('rgb(0, 0, 0)',), r and (r['bg'], r['mbg']))
        check('放大视频：画面贴满屏宽、占第一屏大半', r and r['v'][0] == 0 and r['v'][2] == vw and r['v'][3] > vh * .65, r and r['v'])
        check('放大视频：画面下面先是操作按钮', r and len(r['first']) > 2 and r['first'][2] == 'row', r and r['first'])
        pg.screenshot(path=os.path.join(OUT, 'vd_full.png'))
        # 在画面中间往下拉：关
        pg.evaluate("""(async () => { const v = document.querySelector('.modal.vd-view .vd-player'), r = v.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + 120;
          const TN = { pointerdown: 'touchstart', pointermove: 'touchmove', pointerup: 'touchend' };
          const ev = (n, yy) => { v.dispatchEvent(new PointerEvent(n, { pointerId: 3, pointerType: 'touch', isPrimary: true, clientX: x, clientY: yy, bubbles: true, cancelable: true }));
    const to = { identifier: 5, target: v, clientX: x, clientY: yy }, te = new Event(TN[n], { bubbles: true, cancelable: true });
    Object.defineProperty(te, 'touches', { value: n === 'pointerup' ? [] : [to] }); Object.defineProperty(te, 'changedTouches', { value: [to] }); v.dispatchEvent(te); };  // 真机上 pointer 和 touch 都有
          ev('pointerdown', y); for (let k = 1; k <= 10; k++) { ev('pointermove', y + k * 22); await new Promise(r => setTimeout(r, 16)); } ev('pointerup', y + 220); })()"""); pg.wait_for_timeout(700)
        check('放大视频：在画面上往下拉 → 关上', not pg.evaluate("!!document.querySelector('.modal-bg > .modal.vd-view')"))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
