"""播放页：左边缘往右滑 = 退回上个文件夹（2026-11-16 用户：只有播放页这样；播放页最上面那层、别的页面照样打开侧栏）。
模拟 iPhone 16 Pro Max，测试数据里的“很深”文件夹（有子文件夹）。用法：python ip_plback.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'play'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


FINGER = r"""async ([x0, x1, steps, ms, hold]) => { const y = 500, tgt = document.elementFromPoint(x0, y) || document.body;
  const ev = (n, x) => { const t = { identifier: 3, target: tgt, clientX: x, clientY: y }; const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); tgt.dispatchEvent(e); };
  ev('touchstart', x0); for (let i = 1; i <= steps; i++) { ev('touchmove', x0 + (x1 - x0) * i / steps); await new Promise(r => setTimeout(r, ms)); }
  window.__fup = () => ev('touchend', x1); if (!hold) ev('touchend', x1); }"""
ST = "({ src: playSrc, folder: !!document.querySelector('#main .play-grid.m-list'), dw: document.body.classList.contains('ph-dw-open'), tx: (() => { const e = document.getElementById('play-list'); const m = e && getComputedStyle(e).transform; return !m || m === 'none' ? 0 : Math.round(new DOMMatrix(m).m41); })() })"

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("go('play')"); pg.wait_for_timeout(1700); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很深/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("document.querySelector('#play-list .pl-dirhit')?.click()"); pg.wait_for_timeout(1800); hide(pg)
        s0 = pg.evaluate(ST); print('   进到：', s0['src'])
        check('测试前提：在“很深”的子文件夹里', s0['folder'] and s0['src'].startswith('d:很深/'), s0)
        # 拖到一半停住：列表跟着手指往右
        pg.evaluate(FINGER, [6, 160, 10, 16, True]); pg.wait_for_timeout(80); m = pg.evaluate(ST)
        check('子文件夹里从左边缘往右拖：列表跟着手指走、不开侧栏', abs(m['tx'] - 154) <= 4 and not m['dw'], m)
        pg.screenshot(path=os.path.join(OUT, 'back_mid.png'))
        pg.wait_for_timeout(200); pg.evaluate("window.__fup()"); pg.wait_for_timeout(700); m = pg.evaluate(ST)
        check('只拖了 35% 以内、停住再松手 → 弹回，还在这个子文件夹', m['src'] == s0['src'] and m['tx'] == 0 and not m['dw'], m)
        # 拖够远：退回上一层
        # 量一下多快：从松手到上一层的列表出来、滑到位（11-16 用户：退回有点慢）
        ms = pg.evaluate(r"""async ([x0, x1]) => { const src0 = playSrc, y = 500, tgt = document.elementFromPoint(x0, y) || document.body;
          const ev = (n, x) => { const t = { identifier: 4, target: tgt, clientX: x, clientY: y }; const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); tgt.dispatchEvent(e); };
          ev('touchstart', x0); for (let i = 1; i <= 12; i++) { ev('touchmove', x0 + (x1 - x0) * i / 12); await new Promise(r => setTimeout(r, 16)); }
          const t0 = performance.now(); ev('touchend', x1);
          while (performance.now() - t0 < 4000) { await new Promise(r => setTimeout(r, 15)); const g = document.querySelector('#main .play-grid'), tr = g && getComputedStyle(g).transform;
            const tt = document.querySelector('#play-list .card-title')?.textContent || ''; if (playSrc !== src0 && tt.includes('很深') && !tt.includes('/') && (!tr || tr === 'none') && +getComputedStyle(g).opacity === 1) return Math.round(performance.now() - t0); }  // 新的一层（标题只剩“很深”）出来、滑到位
          return -1; }""", [6, 300])
        print('   退回用时（松手到滑到位）ms：', ms)
        check(f'退回上一层快（松手到新的一层滑到位 ≤ 600ms，这次 {ms}ms）', 0 < ms <= 600, ms)
        pg.wait_for_timeout(600); m = pg.evaluate(ST)
        check('拖够远松手 → 退回上一层文件夹（“很深”）', m['src'] == 'd:很深' and m['folder'] and not m['dw'] and m['tx'] == 0, m)
        # 在第一层文件夹里快甩：回到文件夹列表
        pg.evaluate(FINGER, [6, 110, 4, 12, False]); pg.wait_for_timeout(1800); m = pg.evaluate(ST)
        check('第一层文件夹里往右快甩 → 回到文件夹列表（最上面那层）', not m['folder'] and not m['dw'], m)
        # 最上面那层：左边缘往右滑 = 打开侧栏
        pg.evaluate(FINGER, [6, 300, 12, 16, False]); pg.wait_for_timeout(800); m = pg.evaluate(ST)
        check('播放页最上面那层：左边缘往右滑 → 打开侧栏', m['dw'], m)
        pg.evaluate("document.body.classList.remove('ph-dw-open')"); pg.wait_for_timeout(600)
        # 文件夹里 ≡ 照样能开侧栏
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很深/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        b = pg.query_selector('#main .ph-menu-b').bounding_box(); pg.touchscreen.tap(b['x'] + 22, b['y'] + 22); pg.wait_for_timeout(800)
        check('文件夹里点 ≡ → 打开侧栏', pg.evaluate("document.body.classList.contains('ph-dw-open')"))
        pg.evaluate("document.body.classList.remove('ph-dw-open')"); pg.wait_for_timeout(600)
        # 别的页面：左边缘往右滑照样打开侧栏
        pg.evaluate("go('img')"); pg.wait_for_timeout(1600)
        pg.evaluate(FINGER, [6, 300, 12, 16, False]); pg.wait_for_timeout(800)
        check('生图页：左边缘往右滑 → 打开侧栏（不变）', pg.evaluate("document.body.classList.contains('ph-dw-open')"))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
