"""手机界面全面检查（模拟 iPhone，WebKit）：每一页、几种机型、深浅色，自动查这些（2026-11-16 用户：组件固定不住、太挤、太宽都不能有）：
- 页面不能左右晃（整页宽度 > 屏幕）
- 固定 / 贴边的东西（标题栏、输入框、播放条、浮动按钮…）不能和底栏叠在一起；底部几层之间至少 8px
- 滚到最底：最后的内容要露在底栏 / 输入框上面，不被挡住
- 标题栏收起后不超过 安全区 + 70px（11-17 起；原来 56）
- 能点的东西至少 30×30（iOS 建议 44，这里查明显太小的）
- 没有页面报错
用法：python t_iphone_all.py [机型 ...] [--light]   默认只测 iPhone 16 Pro Max（用户 11-16：够了）；截图在 shots_iphone/all/
失败的项前面打 ✗，最后一行是通过数"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide, MODELS
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'all'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
PAGES = ['play', 'img', 'video', 'mats', 'prompt', 'tts', 'vc', 'audioedit', 'batch', 'works', 'voices', 'stt', 'settings']
ok = bad = 0
fails = []


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1
    else:
        bad += 1; fails.append(f'{name} {info}'); print('✗ ' + name, info)


PROBE = r"""() => {
  const R = e => { const b = e.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; };
  const vis = e => { if (!e || !e.isConnected) return false; const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false; const b = e.getBoundingClientRect(); return b.width > 2 && b.height > 2; };
  const rail = document.getElementById('rail'), rr = vis(rail) ? R(rail) : null;
  const skip = e => e.closest('#rail, #__ios, #sb-strip, .ph-sheet, .ph-sheet-bg, .iv, .modal-bg, .toast, .toasts, #pg-hist, .m-dw, .m-dw-scrim, .rail-dim, .fly, #np, .tip, [data-tip-pop]');
  const fixed = [...document.querySelectorAll('body *')].filter(e => { const p = getComputedStyle(e).position; return (p === 'fixed' || p === 'sticky') && vis(e) && !skip(e) && !e.parentElement.closest('[style*=fixed]'); });
  const top = fixed.filter(e => !fixed.some(f => f !== e && f.contains(e)));
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const over = [];
  if (rr) for (const e of top) { const b = R(e); if (getComputedStyle(e).position === 'sticky' && b.t < rr.t - 40) continue; if (b.b > rr.t + 1 && b.t < rr.b - 1 && b.r > rr.l && b.l < rr.r) over.push(name(e) + ' ' + Math.round(b.t) + '-' + Math.round(b.b)); }
  const bottoms = top.filter(e => { const b = R(e); return b.t > innerHeight * .5 && getComputedStyle(e).position === 'fixed'; }).map(e => ({ n: name(e), ...R(e) }));
  const hx = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth;
  const small = [...document.querySelectorAll('#main button, #main a[href], #main [role=button], #main input[type=checkbox], #main .seg button')].filter(e => vis(e) && !e.closest('.ig-gal, .vd-gal, .gal-grid, .pl-list, .tiny, p, li') ).map(e => ({ n: name(e) + ' ' + (e.getAttribute('aria-label') || e.title || e.textContent || '').trim().slice(0, 10), w: Math.round(R(e).w), h: Math.round(R(e).h) })).filter(x => /^input/.test(x.n) ? (x.w < 24 || x.h < 24) : (x.w < 30 || x.h < 28));
  // 11-16 用户：要像人看一样。再量四样：同一行没对齐、按钮挤在一起、字被截断、能点的东西互相盖住
  const TAP = 'button, a[href], [role=button], input:not([type=hidden]), select, textarea, .ig-chip, .seg > *';
  const taps = [...document.querySelectorAll('#main ' + TAP.split(', ').join(', #main ') + ', #main .ig-top-f ' + TAP.split(', ').join(', #main .ig-top-f '))]
    .filter((e, i, a) => a.indexOf(e) === i && vis(e) && !e.closest('.ig-gal, .vd-gal, .gal-grid, .pl-list, #play-list, .tiny') && !e.disabled);
  const inView = r => r.b > 0 && r.t < innerHeight && r.r > 0 && r.l < innerWidth;
  // 标题栏：同一行的按钮 / 标题竖着的中线差不超过 3px
  const head = document.querySelector('#main > .page-head'), misalign = [];
  if (head && vis(head)) { const hs = [...head.querySelectorAll('button, .page-title, .b5-ctx, a.btn, .btn')].filter(e => vis(e) && !e.closest('.ph-sheet')).filter((e, i, a) => !a.some(f => f !== e && f.contains(e)));
    for (const x of hs) for (const y of hs) { if (x === y) continue; const a = R(x), b = R(y); if (a.b < b.t || b.b < a.t) continue; const d = Math.abs((a.t + a.b) / 2 - (b.t + b.b) / 2); if (d > 3) misalign.push(name(x) + ' / ' + name(y) + ' 差 ' + Math.round(d)); } }
  // 太挤：横着挨着的两个能点的东西间隔不到 6px（分段控件里面的不算），或者竖着叠的不到 4px
  const dense = [], overlap = [];
  for (let i = 0; i < taps.length; i++) for (let j = i + 1; j < taps.length; j++) {
    const x = taps[i], y = taps[j]; if (x.contains(y) || y.contains(x)) continue; if (x.parentElement === y.parentElement && x.parentElement.matches('.seg, .pt-chips, .ig-mode')) continue; if (x.closest('.gal-qk') && x.closest('.gal-qk') === y.closest('.gal-qk')) continue;  // 快捷位置是一组分段控件
    const grp = x.parentElement === y.parentElement && (c => c.backgroundColor !== 'rgba(0, 0, 0, 0)' && parseFloat(c.borderRadius) > 10)(getComputedStyle(x.parentElement)); if (grp) continue;  // 合成一个胶囊的一组按钮（AI 助手标题栏那种）
    if ([x, y].some(e => e.matches('.prompt-peek')) && [x, y].some(e => e.matches('textarea, input'))) continue;  // 输入框角上的“查看完整提示词”本来就在框里面
    const a = R(x), b = R(y); if (!inView(a) || !inView(b)) continue;
    const ix = Math.min(a.r, b.r) - Math.max(a.l, b.l), iy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    if (ix > 2 && iy > 2) { overlap.push(name(x) + ' × ' + name(y)); continue; }
    if (iy > Math.min(a.h, b.h) * .5) { const gap = Math.max(a.l, b.l) - Math.min(a.r, b.r); if (gap >= 0 && gap < 6) dense.push(name(x) + ' | ' + name(y) + ' ' + Math.round(gap) + 'px'); }
  }
  // 字被截断：没有省略号却被裁掉（字比框宽）
  const clip = [...document.querySelectorAll('#main *, .ig-top-f *')].filter(e => vis(e) && e.children.length === 0 && (e.textContent || '').trim().length > 1 && !e.closest('.ig-gal, .vd-gal, .gal-grid, input, textarea'))
    .filter(e => { const c = getComputedStyle(e); return e.scrollWidth > e.clientWidth + 1 && c.overflow !== 'visible' && c.textOverflow !== 'ellipsis' && c.whiteSpace !== 'normal'; }).map(e => name(e) + ' “' + e.textContent.trim().slice(0, 10) + '”');
  return { over, bottoms, hx, small: small.slice(0, 6), rail: rr, ih: innerHeight, misalign: [...new Set(misalign)].slice(0, 5), dense: dense.slice(0, 5), overlap: overlap.slice(0, 5), clip: clip.slice(0, 5) };
}"""
END = r"""async () => {
  // 11-16：图片还在加载时页面会继续变高，滚一次就量会量到“没滚到底”（偶尔失败）。等高度连续两次不变（最多 3 秒），再滚到底量
  let h0 = -1; for (let k = 0; k < 15; k++) { scrollTo(0, document.scrollingElement.scrollHeight); await new Promise(r => setTimeout(r, 200)); const h1 = document.scrollingElement.scrollHeight; if (h1 === h0) break; h0 = h1; }
  scrollTo(0, document.scrollingElement.scrollHeight); return new Promise(res => setTimeout(() => {
    const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false; const b = e.getBoundingClientRect(); return b.width > 2 && b.height > 2; };
    const m = document.getElementById('main'); if (!m) return res(null);
    // 正文里最靠下的能看见的东西（不算固定在屏幕上的）
    let low = null; for (const e of m.querySelectorAll('*')) { if (!vis(e) || e.children.length > 0 && e.textContent.trim() === '' && !e.matches('img, canvas, video, button, input, textarea')) continue;
      const p = getComputedStyle(e).position; if (p === 'fixed' || p === 'sticky' || e.id === 'ph-spacer' || e.closest('.ig-top-f, .gal-tray, [style*=fixed]')) continue;  // ph-spacer：垫底的空白，不是内容
      const b = e.getBoundingClientRect(); if (!low || b.bottom > low.b) low = { b: b.bottom, n: e.tagName.toLowerCase() + '.' + String(e.className).split(' ')[0] }; }
    // 挡在底部的：底栏、播放条、输入框、组合条
    const cov = ['#rail', '#pbar', '#main .ig-top-f', '#main .gal-tray'].map(s => document.querySelector(s)).filter(e => e && vis(e) && getComputedStyle(e).position === 'fixed').map(e => e.getBoundingClientRect().top);
    res({ low, cover: cov.length ? Math.min(...cov) : innerHeight });
  }, 500)); }"""
HEAD = r"""() => { scrollTo(0, 600); return new Promise(res => setTimeout(() => { const h = document.querySelector('#main > .page-head'); if (!h) return res(null);
  res({ bottom: h.getBoundingClientRect().bottom, scrolled: document.documentElement.classList.contains('ph-scrolled'), tall: document.scrollingElement.scrollHeight > innerHeight + 700 }); }, 700)); }"""


ROOT = r"""(sel) => {
  const root = document.querySelector(sel); if (!root) return null;
  const R = e => { const b = e.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; };
  const vis = e => { if (!e || !e.isConnected) return false; const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false; const b = e.getBoundingClientRect(); return b.width > 2 && b.height > 2; };
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const rr = R(root), inView = r => r.b > 0 && r.t < innerHeight && r.r > 0 && r.l < innerWidth;
  const taps = [...root.querySelectorAll('button, a[href], [role=button], input:not([type=hidden]), select, textarea, .seg > *')].filter((e, i, a) => a.indexOf(e) === i && vis(e) && !e.disabled && !e.closest('details:not([open]) > :not(summary)'));  // 折起来的 details 里面看不见
  const dense = [], overlap = [], out = [];
  for (const x of taps) { const a = R(x); if (inView(a) && (a.l < rr.l - 1 || a.r > rr.r + 1) && !x.closest('[style*="overflow"], .gal-host, .ph-sheet-b')) out.push(name(x)); }
  for (let i = 0; i < taps.length; i++) for (let j = i + 1; j < taps.length; j++) {
    const x = taps[i], y = taps[j]; if (x.contains(y) || y.contains(x)) continue; if (x.parentElement === y.parentElement && x.parentElement.matches('.seg, .pt-chips')) continue;
    if (x.parentElement === y.parentElement && (c => c.backgroundColor !== 'rgba(0, 0, 0, 0)' && parseFloat(c.borderRadius) > 10)(getComputedStyle(x.parentElement))) continue;
    if ([x, y].some(e => e.matches('.prompt-peek, .ig-srct-x, .ig-src-x, [class*="-x"]'))) continue;
    const a = R(x), b = R(y); if (!inView(a) || !inView(b)) continue;
    const ix = Math.min(a.r, b.r) - Math.max(a.l, b.l), iy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    if (ix > 2 && iy > 2) { overlap.push(name(x) + ' × ' + name(y)); continue; }
    if (iy > Math.min(a.h, b.h) * .5) { const gap = Math.max(a.l, b.l) - Math.min(a.r, b.r); if (gap >= 0 && gap < 6) dense.push(name(x) + ' | ' + name(y) + ' ' + Math.round(gap) + 'px'); }
  }
  const clip = [...root.querySelectorAll('*')].filter(e => vis(e) && e.children.length === 0 && (e.textContent || '').trim().length > 1 && !e.closest('input, textarea'))
    .filter(e => { const c = getComputedStyle(e); return e.scrollWidth > e.clientWidth + 1 && c.overflow !== 'visible' && c.textOverflow !== 'ellipsis' && c.whiteSpace !== 'normal'; }).map(e => name(e) + ' “' + e.textContent.trim().slice(0, 10) + '”');
  const small = taps.filter(e => { const b = R(e); const w = e.matches('input') && e.parentElement && R(e.parentElement).h >= 40; return inView(b) && !w && !e.matches('input[type=range]') && (e.matches('input[type=checkbox], input[type=radio]') ? (b.w < 22 || b.h < 22) : (b.w < 30 || b.h < 28)); }).map(e => name(e) + ' ' + Math.round(R(e).w) + '×' + Math.round(R(e).h));
  return { dense: dense.slice(0, 4), overlap: overlap.slice(0, 4), clip: clip.slice(0, 4), small: small.slice(0, 4), out: out.slice(0, 4) };
}"""
# 打开的面板 / 弹窗 / 侧栏 / 看大图里面也量一遍（页面, 怎么打开, 量哪一块）
STATES = [
    ('img', "document.querySelector('#ig-prompt').click(); document.querySelector('#ig-model').click()", 'body > .pop'),  # 11-23 起贴着按钮弹出小菜单（不再是底部面板）
    ('img', "document.querySelector('#ig-prompt').click(); [...document.querySelectorAll('.ig-chips > .ig-chip')].filter(c => !c.hidden && c.offsetParent).pop().click()", '.ig-panel:not([hidden])'),
    ('img', "document.querySelector('#main .ig-top-f .ph-more-b').click()", '.ph-sheet'),
    ('img', "document.querySelector('.ig-gal .ig-tile').click()", '.iv'),
    ('video', "document.querySelector('#main .ig-top-f .ph-more-b').click()", '.ph-sheet'),
    ('video', "document.querySelector('#vd-gal > .vd-tile').click()", '.modal-bg > .modal'),
    ('video', "document.querySelector('#main > .page-head .b5-ctx').click()", '.ph-sheet'),
    ('play', "document.querySelector('.ph-menu-b').click()", '#ph-dw'),
    ('play', "document.querySelector('.ph-menu-b').click(); setTimeout(() => document.querySelector('#ph-dw [data-ph-more]').click(), 500)", '.ph-sheet'),
    ('prompt', "document.getElementById('pg-hist-m').click()", '#pg-hist'),
]


def run(model, light=False):
    print(f'--- {model}{" 浅色" if light else ""}')
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH, model, dark=not light)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true")
        for pid in PAGES:
            pg.evaluate(f"go({pid!r})"); pg.wait_for_timeout(1700); hide(pg); pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(300)
            tag = f'{model} {pid}{" 浅色" if light else ""}'
            r = pg.evaluate(PROBE)
            check(f'{tag}：不左右晃', r['hx'] <= 1, r['hx'])
            check(f'{tag}：没有东西压在底栏上', not r['over'], r['over'])
            bs = sorted(r['bottoms'] + ([{'n': 'rail', **r['rail']}] if r['rail'] else []), key=lambda x: x['t'])
            for a, b in zip(bs, bs[1:]):
                if a['r'] > b['l'] and a['l'] < b['r']:  # 横向有重合的才算一上一下
                    check(f'{tag}：{a["n"]} 和 {b["n"]} 之间至少 8px', b['t'] - a['b'] >= 7.5, round(b['t'] - a['b']))
            check(f'{tag}：能点的东西不太小', not r['small'], r['small'])
            check(f'{tag}：标题栏同一行对齐', not r['misalign'], r['misalign'])
            check(f'{tag}：按钮之间不挤（至少 6px）', not r['dense'], r['dense'])
            check(f'{tag}：能点的东西不互相盖住', not r['overlap'], r['overlap'])
            check(f'{tag}：字没有被截断', not r['clip'], r['clip'])
            pg.screenshot(path=os.path.join(OUT, f'{model.replace(" ", "")}_{pid}{"_l" if light else ""}.png'))
            e = pg.evaluate(END)
            if e and e['low']:
                check(f'{tag}：滚到底，最后的内容不被底部挡住', e['low']['b'] <= e['cover'] + 1, (round(e['low']['b']), round(e['cover']), e['low']['n']))
            h = pg.evaluate(HEAD)
            if h and h['scrolled'] and h['tall']:  # 安全区按机型的真值（模拟器里页面上量不到 env()）
                sat = MODELS[model]['top']
                check(f'{tag}：标题栏收起后不超过安全区 + 70', h['bottom'] <= sat + 70.5, round(h['bottom'] - sat))  # 11-17：标题栏下移 14pt（用户要离状态栏远一点）
            pg.evaluate("scrollTo(0, 0)")
        for pid, how, sel in STATES:
            pg.evaluate("document.querySelector('.ph-sheet-done')?.click(); document.querySelectorAll('.modal-bg .x, .modal-bg [data-close]').forEach(b => b.click()); ImageViewer?.close?.(); document.body.classList.remove('ph-dw-open', 'pg-hist-open')"); pg.wait_for_timeout(500)
            pg.evaluate(f"go({pid!r})"); pg.wait_for_timeout(1500); hide(pg)
            try:
                pg.evaluate(how)
            except Exception as e:
                check(f'{model} {pid} 打开 {sel}', False, str(e)[:80]); continue
            pg.wait_for_timeout(1300); pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
            r = pg.evaluate(ROOT, sel); tag = f'{model} {pid} · {sel}{" 浅色" if light else ""}'
            if not r:
                check(f'{tag}：打开了', False); continue
            for k, nm in (('dense', '按钮之间不挤'), ('overlap', '不互相盖住'), ('clip', '字没有被截断'), ('small', '能点的东西不太小'), ('out', '没有伸出框外')):
                check(f'{tag}：{nm}', not r[k], r[k])
            pg.screenshot(path=os.path.join(OUT, f'{model.replace(" ", "")}_{pid}_{sel.strip(".#").split(" ")[0]}{"_l" if light else ""}.png'))
        check(f'{model}：没有页面报错', not errs, errs[:3])
        br.close()


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    ms = [m for m in MODELS if any(a.replace(' ', '').lower() in m.replace(' ', '').lower() for a in args)] if args else ['iPhone 16 Pro Max']  # 11-16 用户：只看 16 Pro Max 就够了
    for m in ms:
        run(m, '--light' in sys.argv)
    print(f'通过 {ok} / {ok + bad}')
