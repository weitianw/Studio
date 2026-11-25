"""往下拉关闭的面板（2026-11-16 用户：生图里打开素材库选素材，往上翻图片时面板被收起了；滑动操作的面板都要像侧栏一样有动画）。
模拟 iPhone 16 Pro Max：
- 选素材窗口：图片区往下滚过以后，在图片上往下划 → 不关（是在滚动）；在标题那一段往下拉 → 关
- 图片区在最上面时往下拉够远 → 关，松手后接着往下滑出去（不先弹回原位）；拉一点点 → 顺滑地弹回
- 底部面板（选模型）同样
用法：python ip_sheets.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


# 在 sel 这个元素上（从它顶上往下 dy0 的地方）用一根手指往下拉 dist，松手后过 after 毫秒量面板的位移
PULL = r"""async ([sel, panel, dy0, dist, steps, after]) => { const t = document.querySelector(sel); if (!t) return 'no ' + sel; const r = t.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + dy0;
  const tgt = document.elementFromPoint(x, y) || t;
  const TN = { pointerdown: 'touchstart', pointermove: 'touchmove', pointerup: 'touchend' };
  const ev = (n, yy) => { tgt.dispatchEvent(new PointerEvent(n, { pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: x, clientY: yy, bubbles: true, cancelable: true, buttons: n === 'pointerup' ? 0 : 1 }));
    const to = { identifier: 5, target: tgt, clientX: x, clientY: yy }, te = new Event(TN[n], { bubbles: true, cancelable: true });
    Object.defineProperty(te, 'touches', { value: n === 'pointerup' ? [] : [to] }); Object.defineProperty(te, 'changedTouches', { value: [to] }); tgt.dispatchEvent(te); };  // 真机上 pointer 和 touch 都有
  ev('pointerdown', y); for (let k = 1; k <= steps; k++) { ev('pointermove', y + dist * k / steps); await new Promise(r => setTimeout(r, 16)); }
  const p = () => { const e = document.querySelector(panel); if (!e) return null; const m = getComputedStyle(e).transform; return m === 'none' ? 0 : Math.round(new DOMMatrix(m).m42); };
  // 松手后每 30ms 记一次位置（无头模拟器大约 80ms 才更新一次算出来的样式，所以看整条路径，不只看一个时刻）
  const during = p(); ev('pointerup', y + dist); const path = []; for (let k = 0; k < 12; k++) { await new Promise(r => setTimeout(r, 30)); path.push(p()); } await new Promise(r => setTimeout(r, 400));
  const seen = path.filter(v => v !== null);
  return { during, path: path.join(','), down: seen.some(v => v > during + 5), back: seen.some(v => v < during - 5), mid: seen.some(v => v > 0 && v < during), end: p(), open: !!document.querySelector(panel) }; }"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        def picker():
            pg.evaluate("go('img')"); pg.wait_for_timeout(1500); hide(pg)
            pg.evaluate("document.querySelector('.ig-srct .ig-srct-x')?.click()")
            b = pg.query_selector('.ig-srct').bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(1500)
            pg.evaluate("[...document.querySelectorAll('.gal-m .gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1200)
            pg.evaluate("[...document.querySelectorAll('.gal-m .gal-body .gal-fd')].find(f => f.textContent.includes('测试文件夹'))?.click()"); pg.wait_for_timeout(2000)
        picker()
        st = pg.evaluate("(() => { const b = document.querySelector('.gal-m .gal-body'); b.scrollTop = 260; return [b.scrollTop, b.scrollHeight, b.clientHeight]; })()")
        check('选素材窗口：图片区能往下滚（测试前提）', st[0] > 0, st)
        r = pg.evaluate(PULL, ['.gal-m .gal-body', '.modal-bg > .modal.gal-m', 80, 240, 12, 100])
        check('选素材窗口：图片往下滚过以后，在图片上往下划 → 不关（是往上翻图片）', isinstance(r, dict) and r['open'] and r['during'] == 0, r)
        r = pg.evaluate(PULL, ['.modal-bg > .modal.gal-m', '.modal-bg > .modal.gal-m', 20, 240, 12, 100])
        check('选素材窗口：在最上面标题那段往下拉 → 关', isinstance(r, dict) and not r['open'], r)
        check('选素材窗口：松手后接着往下滑出去（不先弹回原位）', isinstance(r, dict) and r['down'] and not r['back'], r)
        picker()
        pg.evaluate("document.querySelector('.gal-m .gal-body').scrollTop = 0")
        r = pg.evaluate(PULL, ['.gal-m .gal-body', '.modal-bg > .modal.gal-m', 80, 50, 6, 90])
        check('选素材窗口：图片区在最上面、拉一点点 → 顺滑弹回（经过中间位置，最后回到 0）', isinstance(r, dict) and r['open'] and r['mid'] and r['end'] == 0, r)
        r = pg.evaluate(PULL, ['.gal-m .gal-body', '.modal-bg > .modal.gal-m', 80, 240, 12, 100])
        check('选素材窗口：图片区在最上面、往下拉够远 → 关', isinstance(r, dict) and not r['open'], r)
        # 底部面板：输入框的「⋯ 更多工具」（选模型 11-23 起改成贴着按钮的小菜单，不是底部面板了）
        pg.evaluate("go('img')"); pg.wait_for_timeout(1200)
        pg.evaluate("document.querySelector('#main .ig-top-f .ph-more-b, .ph-more-b')?.click()"); pg.wait_for_timeout(900)
        r = pg.evaluate(PULL, ['.ph-sheet .ph-sheet-h', '.ph-sheet', 10, 50, 6, 90])
        check('底部面板：拉一点点 → 顺滑弹回', isinstance(r, dict) and r['open'] and r['mid'] and r['end'] == 0, r)
        r = pg.evaluate(PULL, ['.ph-sheet .ph-sheet-h', '.ph-sheet', 10, 200, 10, 90])
        check('底部面板：往下拉够远 → 接着滑出去、关上', isinstance(r, dict) and not r['open'] and r['down'] and not r['back'], r)
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
