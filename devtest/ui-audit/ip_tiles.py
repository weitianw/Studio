"""素材库格子里的图怎么放（2026-11-16 用户：不是居中，是从上往下放、只裁掉下面）。规矩（galVthMark）：
铺满时每边最多裁掉约 6%（总共 12%）就铺满、居中裁；差得更多就完整显示，空出来的地方用同一张图放大模糊的光晕补满。
模拟 iPhone 16 Pro Max，量每个格子：图的框是不是正好等于格子（不是更高被裁掉下面）、铺满时是不是居中、完整显示时有没有光晕。
测试图是 iphone.py 换上的假图（比例各不相同）。用法：python ip_tiles.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'tiles'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


MEASURE = r"""(root) => [...document.querySelectorAll(root + ' .gal-fim')].filter(im => !im.closest('.gal-fd') && im.querySelector(':scope > img')?.naturalWidth).slice(0, 24).map(im => {
  const t = im.querySelector(':scope > img'), a = im.getBoundingClientRect(), b = t.getBoundingClientRect(), c = getComputedStyle(t);
  const R = a.width / a.height, r = t.naturalWidth / t.naturalHeight, crop = 1 - Math.min(r / R, R / r);
  return { box: [Math.round(b.width - a.width), Math.round(b.height - a.height), Math.round(b.top - a.top), Math.round(b.left - a.left)], fit: c.objectFit, pos: c.objectPosition, crop: Math.round(crop * 100), glow: im.classList.contains('gal-glow') };
})"""


def judge(tag, rows):
    if not rows:
        check(f'{tag}：有格子', False); return
    off = [r for r in rows if any(abs(v) > 1 for v in r['box'])]
    check(f'{tag}：图的框正好等于格子（{len(rows)} 格）', not off, off[:3])
    covs = [r for r in rows if r['crop'] <= 12]
    bad_c = [r for r in covs if r['fit'] != 'cover' or r['pos'] not in ('50% 50%', 'center center', 'center')]
    check(f'{tag}：差得少（≤12%）的铺满、居中裁（{len(covs)} 格）', not bad_c, bad_c[:3])
    fits = [r for r in rows if r['crop'] > 12]
    bad_f = [r for r in fits if r['fit'] != 'contain' or not r['glow']]
    check(f'{tag}：差得多的完整显示 + 光晕（{len(fits)} 格）', not bad_f, bad_f[:3])


if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true")
        pg.evaluate("go('mats')"); pg.wait_for_timeout(1800)
        pg.evaluate("[...document.querySelectorAll('#main .gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500)
        for nm in ['测试文件夹']:
            pg.evaluate("document.querySelector('#main .gal-path [data-d=\"\"]')?.click()"); pg.wait_for_timeout(1200)
            pg.evaluate(f"[...document.querySelectorAll('#main .gal-body .gal-fd')].find(f => f.textContent.includes({nm!r}))?.click()"); pg.wait_for_timeout(1500)
            pg.wait_for_timeout(1500)
            judge(f'素材库 · {nm}', pg.evaluate(MEASURE, '#main'))
            hide(pg); pg.screenshot(path=os.path.join(OUT, f'{nm}.png'))
        # 生图里点“+”打开的选素材窗口
        pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
        pg.evaluate("document.querySelector('.ig-srct .ig-srct-x')?.click()")
        b = pg.query_selector('.ig-srct').bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(1500)
        pg.evaluate("[...document.querySelectorAll('.gal-m .gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("[...document.querySelectorAll('.gal-m .gal-body .gal-fd')].find(f => f.textContent.includes('测试文件夹'))?.click()"); pg.wait_for_timeout(3000)
        judge('选素材窗口 · 测试文件夹', pg.evaluate(MEASURE, '.gal-m'))
        hide(pg); pg.screenshot(path=os.path.join(OUT, 'picker.png'))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
