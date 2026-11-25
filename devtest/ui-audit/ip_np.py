"""全屏播放（2026-11-16 用户：顶上那根拉条太靠下；拖进度条到 3 分钟松手却到了 5 分钟）。模拟 iPhone 16 Pro Max：
放一首测试音频（静音）、打开全屏播放，打印顶上那一段的元素和进度条的结构 / 事件。截图在 shots_iphone/np。用法：python ip_np.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'np'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
TOP = r"""() => { const np = document.getElementById('np'); if (!np || np.hidden) return null; const out = [];
  const w = (e, lv) => { if (lv > 4) return; const r = e.getBoundingClientRect(), s = getComputedStyle(e); if (s.display === 'none' || !r.width || r.top > 420) return;
    out.push('  '.repeat(lv) + e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ').slice(0, 3).join('.') + ' ' + [r.left, r.top, r.width, r.height].map(Math.round) + (e.children.length ? '' : ' “' + (e.textContent || '').trim().slice(0, 12) + '”'));
    [...e.children].forEach(c => w(c, lv + 1)); };
  w(np, 0); const pb = (sel) => { const e = np.querySelector(sel); return e ? getComputedStyle(e, '::before').content + ' ' + getComputedStyle(e, '::before').top + ' ' + getComputedStyle(e, '::before').width : null; };
  return { tree: out.slice(0, 40), before: [pb('.np-top'), getComputedStyle(np, '::before').content + ' top=' + getComputedStyle(np, '::before').top + ' w=' + getComputedStyle(np, '::before').width] }; }"""
PROG = r"""() => { const np = document.getElementById('np'), t = np.querySelector('.np-track, .np-prog input, .np-prog'); if (!t) return null; const r = t.getBoundingClientRect();
  return { tag: t.tagName + '.' + t.className, html: (np.querySelector('.np-prog') || t).outerHTML.slice(0, 600), rect: [r.left, r.top, r.width, r.height].map(Math.round) }; }"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("document.querySelector('#play-list .pl-row[data-i] .pl-main')?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; })")
        pg.evaluate("npOpen()"); pg.wait_for_timeout(1200)
        print(json.dumps(pg.evaluate(TOP), ensure_ascii=False, indent=1))
        print(json.dumps(pg.evaluate(PROG), ensure_ascii=False, indent=1))
        print(pg.evaluate("""(() => { const t = document.querySelector('#np .np-top'), c = getComputedStyle(t), x = document.getElementById('np-close'), cx = getComputedStyle(x);
          return { pt: c.paddingTop, h: c.height, pos: c.position, top: c.top, xmt: cx.marginTop, xh: cx.height, xpos: cx.position, xtop: cx.top, xtr: cx.transform }; })()"""))
        hide(pg); pg.screenshot(path=os.path.join(OUT, 'np.png'))
        br.close()
