"""播放页左边的文件夹树（2026-11-16 用户：点展开 / 收起有时却进了文件夹；进一个有子文件夹的文件夹后不要自动展开，只有点展开按钮才展开）。
模拟 iPhone 16 Pro Max，用测试数据里的“很深”文件夹。用法：python ip_pltree.py"""
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


ST = "({ src: playSrc, folder: !!document.querySelector('#main .play-grid.m-list'), open: (S.ui?.openDirs || []).includes('很深') })"
TOG = "(() => { const t = document.querySelector('#play-src .ps-dir[data-src=\"d:很深\"] .ps-tog'); if (!t) return null; const r = t.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()"

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("go('play')"); pg.wait_for_timeout(1700); hide(pg)
        pg.evaluate("S.ui = { ...(S.ui || {}), openDirs: (S.ui?.openDirs || []).filter(d => d !== '很深') }; persist()")
        pg.evaluate("plmBack?.()") if pg.evaluate("!!document.querySelector('#main .play-grid.m-list')") else None
        pg.wait_for_timeout(1200); s0 = pg.evaluate(ST); t = pg.evaluate(TOG)
        check('测试前提：在文件夹列表、“很深”没展开、有展开箭头', not s0['folder'] and not s0['open'] and t, (s0, t))
        if t:
            print('   箭头大小', round(t[2]), '×', round(t[3]))
            # 点在箭头左边一点（以前 18×18 的范围外面）
            pg.touchscreen.tap(t[0] - 8, t[1] + t[3] / 2 + 6); pg.wait_for_timeout(900); s1 = pg.evaluate(ST)
            check('点箭头偏左一点：只展开，不进文件夹', s1['open'] and not s1['folder'] and s1['src'] == s0['src'], s1)
            t = pg.evaluate(TOG); pg.touchscreen.tap(t[0] + t[2] / 2, t[1] + t[3] / 2); pg.wait_for_timeout(900); s2 = pg.evaluate(ST)
            check('再点箭头：收起，不进文件夹', not s2['open'] and not s2['folder'], s2)
            # 点文件夹的名字：进去，但不展开
            nm = pg.evaluate("(() => { const n = document.querySelector('#play-src .ps-dir[data-src=\"d:很深\"] .ps-name'), r = n.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
            pg.touchscreen.tap(nm[0], nm[1]); pg.wait_for_timeout(1500); s3 = pg.evaluate(ST)
            check('点文件夹名字：进去了，但左边的树没有自动展开', s3['folder'] and s3['src'] == 'd:很深' and not s3['open'], s3)
        # 同一级的文件夹（有没有子文件夹都一样）：图标和名字对齐
        pg.evaluate("plmBack?.()"); pg.wait_for_timeout(1200)
        al = pg.evaluate("""(() => { const by = {}; document.querySelectorAll('#play-src .ps-dir').forEach(r => { const ic = r.querySelector('.ps-ic'), nm = r.querySelector('.ps-name'); if (!ic || !r.offsetParent) return;
          (by[r.dataset.depth] ||= []).push([Math.round(ic.getBoundingClientRect().left), Math.round(nm.getBoundingClientRect().left), r.querySelector('.ps-tog.none') ? 'none' : 'has']); }); return by; })()""")
        bad_al = {d: v for d, v in al.items() if len({x[0] for x in v}) > 1 or len({x[1] for x in v}) > 1}
        check(f'同一级的文件夹对齐（有子文件夹和没有的混在一起，{sum(len(v) for v in al.values())} 行）', al and not bad_al and any(len({x[2] for x in v}) > 1 for v in al.values()), bad_al or al)
        # 按下的样子：手指不动 0.2 秒才亮；一动就灭；点一下松手时亮一下
        PR = r"""async ([mode]) => { const r = document.querySelector('#play-src .ps-dir'), b = r.getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + b.height / 2;
          const ev = (n, xx, yy) => { const t = { identifier: 6, target: r, clientX: xx, clientY: yy }; const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: n === 'touchend' ? [] : [t] }); Object.defineProperty(e, 'changedTouches', { value: [t] }); r.dispatchEvent(e); };
          const lit = () => r.classList.contains('ph-press'), w = ms => new Promise(z => setTimeout(z, ms)), out = [];
          ev('touchstart', x, y);
          if (mode === 'hold') { await w(120); out.push(lit()); await w(150); out.push(lit()); ev('touchend', x, y); await w(150); out.push(lit()); }
          if (mode === 'slow') { for (let k = 1; k <= 20; k++) { ev('touchmove', x, y + k * 1.5); await w(20); if (k === 12) out.push(lit()); } out.push(lit()); r.dispatchEvent(Object.assign(new Event('touchcancel', { bubbles: true }))); await w(50); out.push(lit()); }
          if (mode === 'tap') { await w(60); ev('touchend', x, y); await w(20); out.push(lit()); await w(200); out.push(lit()); }
          return out; }"""
        check('按住不动：0.12 秒时还没亮，0.27 秒时亮了，松手后灭', pg.evaluate(PR, ['hold']) == [False, True, False], pg.evaluate(PR, ['hold']))
        check('按着慢慢往下滑（每 20ms 1.5px）：一直不亮', pg.evaluate(PR, ['slow']) == [False, False, False], pg.evaluate(PR, ['slow']))
        check('点一下：松手时亮一下，然后灭', pg.evaluate(PR, ['tap']) == [True, False], pg.evaluate(PR, ['tap']))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
