"""手机（2026-11-23 用户三条）：
1. 输入框上的选项（模型、尺寸……）贴着按钮弹出小面板，不从底下升起整页；点外面关
2. 看大图：底部工具栏有「对比」（有可比的图时）、没有「详情」；信息面板里有「复制提示词」；「详情和提示词」打开看大图 + 信息面板
3. 底部面板 / 弹窗：往下拉能关（标题那段、内容滚到顶时内容区也行），内容没到顶时往下拉是滚内容、不关；拉的时候背后的页面不动；点露出来的那一截能关
用一串 touchstart / touchmove / touchend（和 ip_drag 一样）。截图前藏起图片视频。用法：STUDIO_TEST_PORT=7897 ../.venv/Scripts/python.exe ip_sheets_pull.py"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from iphone import open_iphone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = fail = 0; errs = []
def check(n, c, x=''):
    global ok, fail
    if c: ok += 1; print('  ✓', n)
    else: fail += 1; print('  ✗', n, str(x)[:300])
PULL = """async ([sel, fy, dy]) => { const root = document.querySelector(sel); if (!root) return 'none'; const r = root.getBoundingClientRect(), x = r.left + r.width / 2, y0 = r.top + fy;
  const tgt = document.elementFromPoint(x, y0) || root; let prevented = false;
  const ev = (n, y) => { const t = { identifier: 9, target: tgt, clientX: x, clientY: y }; const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); tgt.dispatchEvent(e); return e; };
  const sy = document.scrollingElement.scrollTop; ev('touchstart', y0);
  for (let i = 1; i <= 10; i++) { const e = ev('touchmove', y0 + dy * i / 10); prevented = prevented || e.defaultPrevented; await new Promise(r => setTimeout(r, 16)); }
  ev('touchend', y0 + dy); return { prevented, pageMoved: document.scrollingElement.scrollTop !== sy }; }"""
OPEN = "!!document.querySelector('.ph-sheet.on, .modal-bg:not(.out) > .modal')"
with sync_playwright() as p:
    br, pg = open_iphone(p, PH); pg.on('pageerror', lambda e: errs.append(str(e)))
    # 1 输入框上的选项
    pg.evaluate("go('img')"); pg.wait_for_timeout(2500); pg.click('#ig-prompt'); pg.wait_for_timeout(700)
    chips = pg.evaluate("[...document.querySelectorAll('#main .ig-chips > *')].filter(e => e.offsetParent).length")
    for k in range(chips):
        pg.evaluate(f"[...document.querySelectorAll('#main .ig-chips > *')].filter(e => e.offsetParent)[{k}].click()"); pg.wait_for_timeout(600)
        r = pg.evaluate(f"""(() => {{ const c = [...document.querySelectorAll('#main .ig-chips > *')].filter(e => e.offsetParent)[{k}].getBoundingClientRect(), p = document.querySelector('.ig-panel:not([hidden]), body > .pop:not(.ph-pop)'); if (!p) return null; const q = p.getBoundingClientRect();
          return {{ sheet: !!document.querySelector('.ph-sheet.on'), bottomGap: Math.round(c.top - q.bottom), h: Math.round(q.height), top: Math.round(q.top), fullW: q.width >= innerWidth - 2 }}; }})()""")
        check(f'选项 {k + 1}：贴着按钮弹出（不是底部整页）', r and not r['sheet'] and 0 <= r['bottomGap'] <= 24 and r['top'] > 40, r)
        pg.touchscreen.tap(220, 120); pg.wait_for_timeout(600)
        check(f'选项 {k + 1}：点外面关', not pg.evaluate("!!document.querySelector('.ig-panel:not([hidden]), body > .pop:not(.ph-pop)')"))
    # 2 看大图
    pg.evaluate("document.querySelector('.ig-tile, .img-tile')?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(500)
    idx = pg.evaluate("imgGal.findIndex(x => imgCmpSrc(x))")
    if idx >= 0:
        pg.evaluate(f"imgView({idx})"); pg.wait_for_timeout(1500)
        bar = pg.evaluate("[...document.querySelectorAll('.iv-bar button span')].map(s => s.textContent)")
        check('看大图：底部工具栏有「对比」、没有「详情」', '对比' in bar and '详情' not in bar, bar)
        pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(500)
    else:
        print('   （测试数据里没有能对比的图，跳过对比按钮那一项）')
    pg.evaluate("imgView(0, { info: true })"); pg.wait_for_timeout(1500)
    check('「详情和提示词」：看大图开着信息面板，有「复制提示词」', pg.evaluate("document.querySelector('.iv')?.classList.contains('info') && !!document.querySelector('.iv-info [data-a=copyp]')"))
    check('详情页没有了', not pg.evaluate("!!document.querySelector('.ig-dview')") and pg.evaluate("typeof imgDetail") == 'undefined')
    pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(600)
    # 3 底部面板：输入框“⋯ 更多工具”（phSheet）
    pg.evaluate("document.querySelector('.ph-more-b')?.click()"); pg.wait_for_timeout(800)
    if pg.evaluate("!!document.querySelector('.ph-sheet.on')"):
        r = pg.evaluate(PULL, ['.ph-sheet.on', 20, 200]); pg.wait_for_timeout(600)
        check('底部面板：从标题往下拉关掉，背后页面不动', not pg.evaluate("!!document.querySelector('.ph-sheet.on')") and r['prevented'] and not r['pageMoved'], r)
        pg.evaluate("document.querySelector('.ph-more-b')?.click()"); pg.wait_for_timeout(800)
        r = pg.evaluate(PULL, ['.ph-sheet.on', 120, 200]); pg.wait_for_timeout(600)
        check('底部面板：从内容区往下拉也能关', not pg.evaluate("!!document.querySelector('.ph-sheet.on')"), r)
        pg.evaluate("document.querySelector('.ph-more-b')?.click()"); pg.wait_for_timeout(800)
        pg.touchscreen.tap(220, 150); pg.wait_for_timeout(600)
        check('底部面板：点外面关', not pg.evaluate("!!document.querySelector('.ph-sheet.on')"))
    else:
        check('打开了「更多工具」', False)
    # 弹窗（modal）：设置 → 存储里的长列表不好找，用高级参数（内容长、能滚）
    pg.evaluate("document.getElementById('ig-adv-open').click()"); pg.wait_for_timeout(1000)
    if pg.evaluate("!!document.querySelector('.modal-bg:not(.out) > .modal')"):
        sc = pg.evaluate("(() => { const m = document.querySelector('.modal-bg:not(.out) > .modal'); m.scrollTop = 200; return m.scrollTop; })()")
        if sc > 0:
            r = pg.evaluate(PULL, ['.modal-bg:not(.out) > .modal', 200, 160]); pg.wait_for_timeout(600)
            check('弹窗：内容没滚到顶时，在内容区往下拉不关（交给滚动）', pg.evaluate(OPEN) and not r['prevented'], r)
            pg.evaluate("document.querySelector('.modal-bg:not(.out) > .modal').scrollTop = 0"); pg.wait_for_timeout(200)
        r = pg.evaluate(PULL, ['.modal-bg:not(.out) > .modal', 160, 220]); pg.wait_for_timeout(900)
        check('弹窗：滚到顶后往下拉关掉，背后页面不动', not pg.evaluate("!!document.querySelector('.modal-bg:not(.out) > .modal')") and r['prevented'] and not r['pageMoved'], r)
        pg.evaluate("document.getElementById('ig-adv-open').click()"); pg.wait_for_timeout(1000)
        gap = pg.evaluate("Math.round(document.querySelector('.modal-bg:not(.out) > .modal').getBoundingClientRect().top)")
        check('弹窗：上面留着能点的一截（≥ 40）', gap >= 40, gap)
        pg.touchscreen.tap(220, max(10, gap // 2)); pg.wait_for_timeout(700)
        check('弹窗：点上面露出来的那一截关掉', not pg.evaluate("!!document.querySelector('.modal-bg:not(.out) > .modal')"))
    else:
        check('打开了高级参数', False)
    br.close()
check('没有页面报错', not errs, errs[:3])
print(f'{ok} 通过，{fail} 失败')
