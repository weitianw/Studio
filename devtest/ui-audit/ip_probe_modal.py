"""选素材窗口（弹窗）的 transition / animation 实际是什么（2026-11-16 查往下拉松手没有动画）。用法：python ip_probe_modal.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
        pg.evaluate("document.querySelector('.ig-srct .ig-srct-x')?.click()")
        b = pg.query_selector('.ig-srct').bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(1500)
        print(pg.evaluate(r"""(async () => { const m = document.querySelector('.modal-bg > .modal'), r = m.querySelector('.gal-body').getBoundingClientRect(), x = r.left + 100, y = r.top + 80, tgt = document.elementFromPoint(x, y);
          const ev = (n, yy) => tgt.dispatchEvent(new PointerEvent(n, { pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: x, clientY: yy, bubbles: true, cancelable: true }));
          ev('pointerdown', y); for (let k = 1; k <= 6; k++) { ev('pointermove', y + 50 * k / 6); await new Promise(r => setTimeout(r, 16)); }
          ev('pointerup', y + 50); const out = [m.style.transition, m.style.transform]; const ys = []; for (let k = 0; k < 8; k++) { await new Promise(r => setTimeout(r, 40)); ys.push(Math.round(new DOMMatrix(getComputedStyle(m).transform === 'none' ? undefined : getComputedStyle(m).transform).m42)); } out.push(ys.join(','));
          return { right_after: out, at60: [m.style.transition, m.style.transform, getComputedStyle(m).transform, getComputedStyle(m).transitionProperty, getComputedStyle(m).transitionDuration], anims: m.getAnimations().map(a => (a.transitionProperty || a.animationName) + ':' + a.playState) }; })()"""))
        print(pg.evaluate("""(() => { const m = document.querySelector('.modal-bg > .modal'); const c = getComputedStyle(m);
          m.style.transition = 'transform .26s ease'; m.style.transform = 'translateY(200px)'; const c2 = getComputedStyle(m);
          return { cls: m.className, transition: c.transition, animation: c.animationName + ' ' + c.animationDuration + ' ' + c.animationFillMode, afterSet: c2.transition, anims: m.getAnimations().map(a => a.animationName || a.transitionProperty || a.constructor.name + ':' + a.playState) }; })()"""))
        br.close()
