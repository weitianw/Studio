"""进度条和全屏播放顶上（2026-11-16 用户：拖到 3 分钟松手却到了 5 分钟；全屏播放顶上的拉条往上放到状态栏下面）。
模拟 iPhone 16 Pro Max：放测试数据里一首音频（静音），把它的时长假装成 45 分钟（转码 / 流式时 a.duration 是 Infinity，用文件记下的时长），
用 touch 指针拖全屏播放的进度条：拖的时候进度条跟手指、边拖边跳但最多 0.15 秒一次；松手准确跳到手指的位置。鼠标拖照旧边拖边跳。用法：python ip_seek.py"""
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


# 把正在放的这首假装成 45 分钟、a.duration = Infinity（流式）；记下每次设 currentTime
FAKE = r"""() => { const a = PB.a; if (!a) return 'no audio'; a.pause(); a._dur = 2700; window.__sets = [];
  Object.defineProperty(a, 'duration', { get: () => Infinity, configurable: true });
  let cur = 1200; Object.defineProperty(a, 'currentTime', { get: () => cur, set: v => { window.__sets.push(Math.round(v)); cur = v; setTimeout(() => a.dispatchEvent(new Event('seeked')), 60); }, configurable: true });
  pbPaint(); return 'ok'; }"""
DRAG = r"""async ([kind, p1]) => { const tr = document.getElementById('np-track'); tr.setPointerCapture = () => {}; const r = tr.getBoundingClientRect(), y = r.top + r.height / 2, x0 = r.left + r.width * .5, x1 = r.left + r.width * p1;
  const ev = (n, x) => tr.dispatchEvent(new PointerEvent(n, { pointerId: 11, pointerType: kind, isPrimary: true, clientX: x, clientY: y, bubbles: true, cancelable: true, buttons: n === 'pointerup' ? 0 : 1 }));
  window.__sets = []; ev('pointerdown', x0); for (let k = 1; k <= 15; k++) { ev('pointermove', x0 + (x1 - x0) * k / 15); await new Promise(z => setTimeout(z, 16)); }
  const during = { sets: window.__sets.slice(), t0: document.getElementById('np-t0').textContent, fill: document.getElementById('np-fill').style.width };
  ev('pointerup', x1); await new Promise(z => setTimeout(z, 30)); const right = document.getElementById('np-t0').textContent; await new Promise(z => setTimeout(z, 300));
  return { during, sets: window.__sets, right, after: document.getElementById('np-t0').textContent, want: Math.round(2700 * p1) }; }"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("document.querySelector('#play-list .pl-row[data-i] .pl-main')?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("npOpen()"); pg.wait_for_timeout(1200)
        # 顶上的拉条：紧贴状态栏下面
        top = pg.evaluate("(() => { const b = document.getElementById('np-close').getBoundingClientRect(), s = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sat')) || 0; return [Math.round(b.top), Math.round(b.bottom)]; })()")
        safe = pg.evaluate("Math.round(parseFloat(getComputedStyle(document.querySelector('#np .np-top')).paddingTop))")  # 模拟器只在样式表里换 env()：用顶栏的上边距当安全区
        check(f'全屏播放顶上的拉条在状态栏下面（安全区 {safe}px，拉条 {top}）', top[0] <= safe + 2 and top[1] - top[0] >= 28, (safe, top))
        print('  ', pg.evaluate(FAKE))
        r = pg.evaluate(DRAG, ['touch', 3 / 45])
        n = len(r['during']['sets'])
        check(f'手指拖：边拖边跳（听着找位置），但不是每动一下都跳（15 次移动跳了 {n} 次），进度条和时间跟着手指', 1 <= n <= 4 and r['during']['t0'] in ('2:59', '3:00'), r)
        check('手指拖：松手再准确跳一次，正好 3:00（以前按 Infinity 算会跑掉）', r['sets'] and r['sets'][-1] == 180 and all(v != float('inf') for v in r['sets']), r)
        check('手指拖：松手后时间一直是 3:00 左右（不闪回原来的位置）', r['right'] in ('2:59', '3:00') and r['after'] in ('2:59', '3:00'), r)
        r = pg.evaluate(DRAG, ['mouse', 10 / 45])
        check('鼠标拖：照旧边拖边跳，最后停在 10:00', len(r['sets']) > 3 and r['sets'][-1] == 600 and r['after'] in ('9:59', '10:00'), r)
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
