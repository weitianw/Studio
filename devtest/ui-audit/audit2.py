"""全面 UI 检查（2026-11-08）：python -I audit2.py <profile> [pages]
- 像用户一样点导航进每一页（返回键、标题栏的真实状态才会出现）
- 每页跑版面规则：横向溢出 / 整页多余滚动 / 没用的小滚动条 / 元素被挡住 / 文字互相压住 / 标题被挤走 / 文字被挤成竖排 / 文字被截掉 /
  小组件独占一行 / 点按区域太小（手机）/ 空白框 / 图片坏了；可疑处画红框截图，另存一张干净截图给人看
- 手机：真实触摸滑动（上下左右），看页面 / 弹窗有没有横着动
- 记录报错（页面异常、控制台错误、失败的请求）"""
import os, json, sys, re, time
from playwright.sync_api import sync_playwright
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897'); SP = os.path.dirname(os.path.abspath(__file__))
IPH = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
IPAD = 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
PROFILES = {  # 名字: (宽, 高, 手机/触屏, 应用窗口(pywebview), dpr, UA, 主题)
    'app1920': (1920, 1080, False, True, 1, None, 'dark'), 'app1920t': (1920, 1032, False, True, 1, None, 'dark'),  # 4K 200% 全屏 / 最大化带任务栏
    'app2560': (2560, 1440, False, True, 1, None, 'dark'), 'app1600': (1600, 900, False, True, 1, None, 'dark'),
    'app1440': (1440, 900, False, True, 1, None, 'dark'), 'app1366': (1366, 768, False, True, 1, None, 'dark'), 'app1280': (1280, 720, False, True, 1, None, 'dark'),
    'win1200': (1200, 800, False, True, 1, None, 'dark'), 'win1199': (1199, 800, False, True, 1, None, 'dark'), 'win1024': (1024, 768, False, True, 1, None, 'dark'),
    'win900': (900, 700, False, True, 1, None, 'dark'), 'win761': (761, 900, False, True, 1, None, 'dark'), 'win1920s': (1920, 600, False, True, 1, None, 'dark'),
    'app3840': (3840, 2160, False, True, 1, None, 'dark'),
    'web1920': (1920, 1080, False, False, 1, None, 'dark'), 'light1920': (1920, 1080, False, True, 1, None, 'light'),
    'ph440': (440, 956, True, False, 3, IPH, 'dark'), 'ph393': (393, 852, True, False, 3, IPH, 'dark'), 'ph390': (390, 844, True, False, 3, IPH, 'dark'),
    'ph375': (375, 667, True, False, 2, IPH, 'dark'), 'ph440l': (440, 956, True, False, 3, IPH, 'light'), 'phland': (956, 440, True, False, 3, IPH, 'dark'),
    'pad768': (768, 1024, True, False, 2, IPAD, 'dark'), 'pad1024': (1024, 1366, True, False, 2, IPAD, 'dark'),
}
prof = sys.argv[1]; W, H, MOBI, APP, DPR, UA, THEME = PROFILES[prof]
PAGES = sys.argv[2].split(',') if len(sys.argv) > 2 else ['play', 'tts', 'vc', 'img', 'video', 'audioedit', 'works', 'voices', 'mats', 'prompt', 'stt', 'settings', 'batch']
OUT = os.path.join(SP, 'aud', prof); os.makedirs(OUT, exist_ok=True)
INIT = "window.pywebview = { api: new Proxy({}, { get: () => () => Promise.resolve(null) }) };"

CHECK = r"""(o) => {
  const W = o.W || innerWidth, H = o.H || innerHeight, F = [];
  const add = (kind, el, msg, sev = 2) => { const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : null; F.push({ kind, sev, msg, el: el ? desc(el) : '', r: r ? [r.left, r.top, r.right, r.bottom].map(Math.round) : null }); if (el && el.setAttribute) el.setAttribute('data-aud', (el.getAttribute('data-aud') || '') + kind + ' '); };
  const desc = e => { const t = (e.getAttribute?.('aria-label') || e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 24); return `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${e.classList?.length ? '.' + [...e.classList].slice(0, 3).join('.') : ''}${t ? ' “' + t + '”' : ''}`; };
  const cs = e => getComputedStyle(e);
  const effVis = e => { { const d = e.closest('details:not([open])'); if (d && !e.closest('summary')) return 0; } let o = 1; for (let x = e; x && x.nodeType === 1; x = x.parentElement) { const s = cs(x); if (s.display === 'none' || s.visibility === 'hidden' || s.contentVisibility === 'hidden') return 0; o *= +s.opacity; if (o < .05) return 0; } return o; };
  const clipRect = e => { let r = e.getBoundingClientRect(), L = r.left, T = r.top, R = r.right, Bm = r.bottom;
    for (let x = e.parentElement; x && x !== document.documentElement; x = x.parentElement) { const s = cs(x); if (s.overflowX !== 'visible' || s.overflowY !== 'visible' || s.clipPath !== 'none') { const q = x.getBoundingClientRect(); if (s.overflowX !== 'visible') { L = Math.max(L, q.left); R = Math.min(R, q.right); } if (s.overflowY !== 'visible') { T = Math.max(T, q.top); Bm = Math.min(Bm, q.bottom); } }
      if (s.position === 'fixed') break; }
    L = Math.max(L, 0); T = Math.max(T, 0); R = Math.min(R, W); Bm = Math.min(Bm, H); return { L, T, R, B: Bm, w: R - L, h: Bm - T }; };
  const ownText = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const INTER = 'button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=menuitem], [role=option], summary, label.switch, .chip';
  const all = [...document.querySelectorAll('body *')].filter(e => !['SCRIPT', 'STYLE', 'LINK', 'META', 'TEMPLATE', 'BR'].includes(e.tagName) && !e.closest('svg:not(:root) *'));
  const V = new Map();
  for (const e of all) { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue; if (r.bottom <= 0 || r.top >= H || r.right <= 0 || r.left >= W) { V.set(e, null); continue; } const op = effVis(e); if (!op) continue; const c = clipRect(e); if (c.w < 1 || c.h < 1) continue; V.set(e, { r, c, op }); }
  const vis = e => !!V.get(e);
  // 1 横向：整页能横着滚 / 有东西伸出屏幕左右（没被裁掉）
  const se = document.scrollingElement;
  if (se.scrollWidth > W + 0.5) add('hscroll', null, `整页可横向滚动 ${se.scrollWidth - W}px`, 3);
  if (innerWidth > W + 0.5 || (visualViewport && visualViewport.scale < 0.99)) add('zoomout', null, `整页被缩小了（内容比屏幕宽，浏览器自动缩放到 ${innerWidth}px）`, 3);
  for (const [e, v] of V) { if (!v) continue; const r = v.r; if ((r.right > W + 1 || r.left < -1) && cs(e).position !== 'fixed') {
    // 横着滚的一排（overflow auto/scroll）里伸出去是正常的；被一个比屏幕窄的框裁掉也正常；被整页 / 整屏宽的框裁掉 = 内容在屏幕边上被截断
    let clipped = false; for (let x = e.parentElement; x && x !== document.documentElement; x = x.parentElement) { const s = cs(x); if (s.overflowX !== 'visible') { const q = x.getBoundingClientRect(); if (/(auto|scroll)/.test(s.overflowX) || (q.right < W - 1 && q.left > 1)) { clipped = true; break; } } }
    if (!clipped && !e.closest('[data-aud-ok]')) add('offscreen', e, `伸出屏幕 ${Math.round(r.left)}..${Math.round(r.right)}`, 3); } }
  // 2 整页多余竖向滚动（应用里固定高度的页面）
  if (o.fixedPage && se.scrollHeight > H + 1) add('vscroll', null, `整页可上下滚 ${se.scrollHeight - H}px`, 3);
  // 3 没用的小滚动条（内容只多出一点点）
  for (const [e, v] of V) { if (!v) continue; const s = cs(e); if (/(auto|scroll)/.test(s.overflowY) && e.clientHeight > 40) { const d = e.scrollHeight - e.clientHeight; if (d > 1 && d < 48 && !e.matches('textarea')) add('tinyscroll', e, `只多出 ${d}px 也能滚`, 2); }
    if (/(auto|scroll)/.test(s.overflowX) && e.clientWidth > 40) { const d = e.scrollWidth - e.clientWidth; if (d > 0 && d < 3) add('tinyhscroll', e, `横向只多出 ${d}px（iOS 上可能横着晃）`, 2); } }
  // 4 能点的东西 / 文字被别的东西挡住（取中心点看最上面是谁）
  // 所在的“层”：最外面那个固定在屏幕上的（标签栏、浮钮、弹出层…）；没有的话最近的吸顶 / 浮起来的；都没有 = 页面本身
  const layer = x => { let fx = null, other = null; for (let y = x; y && y !== document.body; y = y.parentElement) { const s = cs(y); if (s.position === 'fixed') fx = y; else if (!other && (s.position === 'sticky' || (s.position === 'absolute' && +s.zIndex >= 10))) other = y; } return fx || other || document.body; };
  const isOverlay = x => !!x.closest('.modal-bg, .toast, .tip-card-float, [role=tooltip], .rail-dim, .m-dw-scrim, #sb-strip, .b5-menu, .pop, .dd-menu, .ctx-menu, .fly, .side-pop, .gear-pop, .tb-strip, .tb, .tb-edge, .iv, .viewer, .lb, .np');
  const atoms = []; for (const [e, v] of V) { if (!v) continue; if (e.matches(INTER) && !e.parentElement.closest(INTER)) atoms.push(e); else if (ownText(e) && !e.closest(INTER) && !['OPTION'].includes(e.tagName)) atoms.push(e); }
  const topModal = [...document.querySelectorAll('.modal-bg')].filter(vis).pop();
  for (const e of atoms) { const { c } = V.get(e); if (c.w < 4 || c.h < 4) continue; if (topModal && !topModal.contains(e)) continue; if (cs(e).pointerEvents === 'none') continue;
    const x = c.L + c.w / 2, y = c.T + c.h / 2, t = document.elementFromPoint(x, y); if (!t || t === e || e.contains(t) || t.contains(e)) continue;
    if (e.tagName === 'INPUT' && t.closest('label')?.contains(e)) continue; if (e.closest('label') && e.closest('label').contains(t)) continue;
    if (isOverlay(t) && !isOverlay(e)) continue;  // 菜单 / 提示 / 弹窗盖在上面是正常的
    const ta = t.closest(INTER) || t; if (ta.contains(e)) continue;
    const s = cs(t); if (+s.opacity < .1 || s.pointerEvents === 'none') continue;
    const lt = layer(ta), le = layer(e);
    if (lt !== le && lt !== document.body && le !== document.body && /fixed|sticky/.test(cs(lt).position) && /fixed|sticky/.test(cs(le).position) && (cs(lt).position === 'fixed' || cs(le).position === 'fixed') && !lt.contains(le) && !le.contains(lt) && !isOverlay(ta)) { add('fixedclash', e, '两个固定的控件叠在一起：' + desc(ta), 3); continue; }
    if (lt !== le && (le === document.body || !le.contains(lt))) { if (lt !== document.body && cs(lt).position === 'fixed' && o.atBottom && !e.closest('[data-aud-scroll]')) { let inner = false; for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const q = cs(x); if (/(auto|scroll)/.test(q.overflowY) && x.scrollHeight - x.clientHeight - x.scrollTop > 4) { inner = true; break; } } if (!inner) add('hiddenunder', e, '滚到底也被盖住：' + desc(ta), 3); } continue; }
    add(e.matches(INTER) ? 'covered' : 'textcovered', e, '被挡住：' + desc(ta), e.matches(INTER) ? 3 : 2); }
  // 5 文字压文字
  const tx = atoms.filter(e => ownText(e) || e.matches('button, .chip'));
  for (let i = 0; i < tx.length; i++) for (let j = i + 1; j < tx.length; j++) { const a = tx[i], b = tx[j]; if (a.contains(b) || b.contains(a)) continue; const A = V.get(a).c, Bc = V.get(b).c;
    if (layer(a) !== layer(b)) continue;
    const ix = Math.min(A.R, Bc.R) - Math.max(A.L, Bc.L), iy = Math.min(A.B, Bc.B) - Math.max(A.T, Bc.T); if (ix > 3 && iy > 3) { const ar = ix * iy / Math.min(A.w * A.h, Bc.w * Bc.h); if (ar > .25) add('overlap', a, '和 ' + desc(b) + ' 重叠 ' + Math.round(ar * 100) + '%', 3); } }
  // 6 标题被挤走 / 被截
  const head = document.querySelector('#main > .page-head'); const ttl = head && head.querySelector('.page-title, .b5-ctx');
  if (head && ttl && vis(ttl)) { const hr = head.getBoundingClientRect(), tr = ttl.getBoundingClientRect(); const centered = document.documentElement.classList.contains('ph') && Math.abs((tr.left + tr.right) / 2 - (hr.left + hr.right) / 2) < 24;  /* 11-17：手机标题栏 11-16 起标题居中（Claude / iOS 那样），居中不算被挤走 */
    if (!centered && tr.left - hr.left > hr.width * .4) add('title', ttl, `标题被挤到右边（离左边 ${Math.round(tr.left - hr.left)}px）`, 3); }
  // 7 文字被挤成竖排 / 被截掉 / 溢出按钮
  for (const [e, v] of V) { if (!v || !ownText(e)) continue; const s = cs(e), fs = parseFloat(s.fontSize) || 14, lh = parseFloat(s.lineHeight) || fs * 1.4, txt = e.textContent.trim();
    if (txt.length >= 2 && v.r.width < fs * 2.3 && v.r.height > lh * 2.5 && !/^[\d\s:.%+-]+$/.test(txt)) add('vertical', e, `文字被挤成竖排（宽 ${Math.round(v.r.width)}px）`, 3);
    if (s.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) add('ellipsis', e, `文字被省略：“${txt.slice(0, 30)}”`, 1);
    else if (e.scrollWidth > e.clientWidth + 2 && s.overflowX === 'visible' && e.matches('button, .chip, .btn, .pill, [role=tab]')) add('spill', e, '文字溢出按钮', 2);
    if (s.webkitLineClamp && s.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 2) add('ellipsis', e, `多行文字被截：“${txt.slice(0, 30)}”`, 1);
    const area = v.r.width * v.r.height; if (area > 0 && v.c.w * v.c.h < area * .82 && !e.closest('[data-aud-scroll]')) { let sc = false; for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const q = cs(x); if (/(auto|scroll)/.test(q.overflowY + q.overflowX)) { sc = true; break; } } if (!sc && v.c.T > 0 && v.c.B < H) add('cut', e, '文字被裁掉一部分', 2); } }
  // 7b 短按钮 / 选项的字折成了两行；横向一排里有一项只露出一半（被裁 / 被渐隐遮罩截掉）
  for (const [e, v] of V) { if (!v || !e.matches('button, .chip, [role=tab], .seg > *, .ig-chip, .pill')) continue; const s = cs(e), txt = (e.innerText || '').trim(); if (!txt || txt.length > 12) continue;
    const fs = parseFloat(s.fontSize) || 13, lh = parseFloat(s.lineHeight) || fs * 1.35; const tops = []; const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); let n; while ((n = tw.nextNode())) { if (!n.textContent.trim() || !vis(n.parentElement)) continue; const g = document.createRange(); g.selectNodeContents(n); for (const q of g.getClientRects()) if (q.width > 1) tops.push(q.top); }
    // 同一段文字分在了好几行（一个字一行 / 一个词拆开）：只看文字本身，不看图标
    const per = new Map(); { const tw2 = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); let m; while ((m = tw2.nextNode())) { if (!m.textContent.trim()) continue; const g = document.createRange(); g.selectNodeContents(m); const ls = [...g.getClientRects()].filter(q => q.width > 1).map(q => q.top); const u = []; ls.forEach(t => { if (!u.some(x => Math.abs(x - t) < lh * .6)) u.push(t); }); if (u.length > 1) per.set(m, u.length); } }
    if (per.size) add('wrap', e, `短文字折成了 ${Math.max(...per.values())} 行：“${txt}”`, 3); }
  for (const [e, v] of V) { if (!v) continue; const s = cs(e); if (!/(auto|hidden|clip)/.test(s.overflowX) || e.scrollWidth <= e.clientWidth + 2) continue; const er = e.getBoundingClientRect(), mask = s.maskImage !== 'none' || s.webkitMaskImage !== 'none';
    for (const k of e.querySelectorAll(':scope > *, :scope > * > .ig-chip')) { const q = k.getBoundingClientRect(); if (q.width < 8) continue; const shown = Math.min(q.right, er.right - (mask ? er.width * .06 : 0)) - Math.max(q.left, er.left); if (shown > 4 && shown < q.width * .8 && (k.innerText || '').trim()) { add('halfcut', k, `只露出 ${Math.round(shown / q.width * 100)}%（${(k.innerText || '').trim().slice(0, 12)}）`, 2); break; } } }
  // 8 小组件独占一行（左右都空着）
  const WID = 'button, .chip, .pill, .btn, [role=button], label.switch, label.ig-check, .vd-jp, .seg, select';
  for (const [e, v] of V) { if (!v || !e.matches(WID) || e.parentElement.closest(WID) || (topModal && !topModal.contains(e))) continue;
    if (document.documentElement.classList.contains('ph') && e.closest('#main > .page-head')) continue;  // 11-17：手机标题栏是左 ≡ / 中标题 / 右按钮三栏，右边只有一个按钮是设计如此 const s = cs(e); if (['fixed', 'absolute'].includes(s.position) || v.r.height > 56) continue;
    // 往上找“这一行”：只包着它的那几层
    let row = e; while (row.parentElement && row.parentElement !== document.body) { const p = row.parentElement, kids = [...p.children].filter(k => vis(k) && !['fixed', 'absolute'].includes(cs(k).position)); if (kids.length === 1 && p.getBoundingClientRect().height < v.r.height + 30) row = p; else break; }
    const p = row.parentElement; if (!p) continue; const pr = p.getBoundingClientRect(); if (pr.width < v.r.width * 3.2 || pr.width < 260) continue;
    const rr = row.getBoundingClientRect(); const band = q => q.bottom > rr.top + 2 && q.top < rr.bottom - 2 && q.width > 2;
    let sib = false; { const y = (rr.top + rr.bottom) / 2; for (let x = pr.left + 6; x < pr.right - 4 && !sib; x += 12) { if (x > rr.left - 4 && x < rr.right + 4) continue; const t = document.elementFromPoint(x, y); if (!t || row.contains(t) || t.contains(row)) continue;
      const tr = t.getBoundingClientRect(); if (tr.width < pr.width * .9 && (ownText(t) || t.closest(INTER) || ['IMG', 'VIDEO', 'svg', 'CANVAS', 'INPUT', 'TEXTAREA'].includes(t.tagName) || t.closest('svg'))) sib = true; } }
    if (!sib) for (const n of p.childNodes) if (n.nodeType === 3 && n.textContent.trim()) { const g = document.createRange(); g.selectNodeContents(n); if ([...g.getClientRects()].some(band)) { sib = true; break; } }
    if (!sib && v.r.width < pr.width * .3 && (p.children.length > 1 || p !== row.parentElement)) add('lonerow', e, `小组件独占一行（宽 ${Math.round(v.r.width)} / 行宽 ${Math.round(pr.width)}）`, 1); }
  // 9 手机：点按区域太小
  if (o.mobile) for (const e of atoms) { if (!e.matches(INTER)) continue; const { r } = V.get(e); if (Math.min(r.width, r.height) < 28 && !e.closest('p, .hint-body, .tip-card-float') && !(e.tagName === 'A' && cs(e).display === 'inline')) add('small', e, `点按区域 ${Math.round(r.width)}×${Math.round(r.height)}`, 1); }
  // 10 空白框、坏图
  for (const [e, v] of V) { if (!v) continue; if (e.matches('.card') && v.r.height > 60 && !e.innerText.trim() && !e.querySelector('img, video, canvas, svg, input, textarea')) add('empty', e, '空白的框', 2);
    if (e.tagName === 'IMG' && e.complete && e.naturalWidth === 0 && e.getAttribute('src')) add('brokenimg', e, '图片加载失败', 3); }
  return { F, scrollH: se.scrollHeight, scrollW: se.scrollWidth, page: document.getElementById('main')?.dataset.page, depth: window.go?.depth ?? null, back: !!document.querySelector('#main .pg-back:not([hidden])') };
}"""
MARKS = r"""() => { document.querySelectorAll('.aud-box').forEach(b => b.remove()); const col = { 3: '#ff2d55', 2: '#ff9f0a', 1: '#64d2ff' };
  document.querySelectorAll('[data-aud]').forEach(e => { const r = e.getBoundingClientRect(); const k = e.getAttribute('data-aud'), sev = /hscroll|offscreen|covered|overlap|title|vertical|brokenimg|vscroll|hiddenunder|wrap|fixedclash/.test(k) ? 3 : /tinyscroll|spill|cut|empty|textcovered|tinyh|halfcut/.test(k) ? 2 : 1;
    const b = document.createElement('div'); b.className = 'aud-box'; b.style.cssText = `position:fixed;z-index:2147483647;pointer-events:none;left:${r.left - 2}px;top:${r.top - 2}px;width:${r.width + 4}px;height:${r.height + 4}px;outline:2px solid ${col[sev]};font:10px/1 sans-serif;color:#fff`;
    const l = document.createElement('span'); l.textContent = k.trim(); l.style.cssText = `position:absolute;left:0;top:-11px;background:${col[sev]};padding:1px 2px;white-space:nowrap`; b.append(l); document.body.append(b); }); }"""
UNMARK = "() => { document.querySelectorAll('.aud-box').forEach(b => b.remove()); document.querySelectorAll('[data-aud]').forEach(e => e.removeAttribute('data-aud')); }"
MUTE = "document.querySelectorAll('video,audio').forEach(v => { v.muted = true; v.pause(); })"
FIXED = {'img', 'video', 'mats'}  # 电脑应用里应当一屏放下、不整页滚动的页面
R = {'profile': prof, 'pages': {}}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=user-gesture-required'])
    kw = dict(viewport={'width': W, 'height': H}, color_scheme=THEME, device_scale_factor=1 if not MOBI else min(DPR, 2))
    if MOBI: kw.update(is_mobile=True, has_touch=True, user_agent=UA)
    ctx = b.new_context(**kw)
    if APP: ctx.add_init_script(INIT)
    if os.environ.get('AUD_SFW', '1') != '0':  # 截图只看 SFW（2026-11-18）：图片 / 视频 / 画布 / 背景图都藏起来；AUD_SFW=0 关掉
        ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = 'img:not([src*=brand]):not([src$=svg]),video,canvas{visibility:hidden!important} *,*::before,*::after{background-image:none!important}'; document.head.append(s); });")
    ctx.route('**/*', lambda r: r.abort() if not r.request.url.startswith(B) or (r.request.method == 'POST' and re.search(r'/jobs|/delete|/remove|/clear|/stop|/restart|/quit|/vault/lock|/generate|/synth|/convert', r.request.url)) else r.continue_())
    pg = ctx.new_page(); errs = []; bad = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:240]))
    pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errs.append('console: ' + m.text[:200]))
    pg.on('response', lambda r: r.status >= 400 and r.url.startswith(B) and bad.append(f'{r.status} {r.request.method} {r.url[len(B):][:90]}'))
    pg.on('dialog', lambda d: d.dismiss())
    cdp = ctx.new_cdp_session(pg)
    pg.goto(B + '/play'); pg.wait_for_timeout(1800)
    if APP: pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
    pg.evaluate(f"() => {{ try {{ S.theme = '{THEME}'; document.documentElement.dataset.theme = '{THEME}'; persist(); }} catch (e) {{}} }}")
    pg.wait_for_timeout(400)

    def nav(name):
        """像用户一样点导航：电脑上点导航栏（分类弹出菜单里的那一项），手机上点底部标签再点弹出的那一项；设置点齿轮"""
        how = pg.evaluate(r"""(n) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(e).visibility !== 'hidden'; };
          if (n === 'settings') { const g = document.querySelector('#side-gear, [data-page=settings]'); if (g && vis(g)) { const r = g.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, step: 'gear' }; } return null; }
          const a = [...document.querySelectorAll(`#rail a[data-page="${n}"]`)].find(vis); if (a) { const r = a.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, step: 'link' }; }
          const any = document.querySelector(`#rail a[data-page="${n}"]`); const c = any?.closest('.cat')?.querySelector('.cat-b'); if (c && vis(c)) { const r = c.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, step: 'cat' }; } return null; }""", name)
        steps = []
        for _ in range(3):
            if not how: break
            steps.append(how['step'])
            if MOBI: pg.touchscreen.tap(how['x'], how['y'])
            else: pg.mouse.click(how['x'], how['y'])
            pg.wait_for_timeout(700)
            if how['step'] != 'cat': break
            how = pg.evaluate(r"""(n) => { const a = [...document.querySelectorAll(`#rail a[data-page="${n}"], .fly a[data-page="${n}"]`)].find(e => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(e).visibility !== 'hidden' && +getComputedStyle(e).opacity > .3; }); if (!a) return null; const r = a.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, step: 'link' }; }""", name)
        if name == 'settings':
            q = pg.evaluate(r"""() => { const a = [...document.querySelectorAll('button, a')].find(e => e.textContent.trim() === '全部设置' && e.getBoundingClientRect().width > 2); if (!a) return null; const r = a.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }""")
            if q:
                steps.append('全部设置')
                if MOBI: pg.touchscreen.tap(q['x'], q['y'])
                else: pg.mouse.click(q['x'], q['y'])
                pg.wait_for_timeout(900)
        if not MOBI: pg.mouse.move(W - 5, H // 2)
        pg.wait_for_timeout(1500); pg.evaluate(MUTE)
        cur = pg.evaluate("() => document.getElementById('main')?.dataset.page")
        if cur != name:
            pg.evaluate(f"go('{name}')"); pg.wait_for_timeout(1500); pg.evaluate(MUTE); steps.append('go()')
        return steps

    def check(key, extra=None):
        pg.evaluate(MUTE); pg.evaluate(UNMARK)
        res = pg.evaluate(CHECK, {'W': W, 'H': H, 'atBottom': pg.evaluate("() => scrollY + innerHeight >= document.scrollingElement.scrollHeight - 2"), 'mobile': MOBI, 'fixedPage': APP and not MOBI and W >= 1200 and pg.evaluate("() => document.getElementById('main')?.dataset.page") in FIXED})
        pg.screenshot(path=os.path.join(OUT, key + '.png'))
        if res['F']:
            pg.evaluate(MARKS); pg.screenshot(path=os.path.join(OUT, key + '_m.png')); pg.evaluate(UNMARK)
        if extra: res.update(extra)
        return res

    def swipe(x, y, dx, dy):
        """真实触摸滑动（Chrome 的手势合成，和手指一样会滚动页面 / 框）；返回滑动前后各个滚动位置、#main 和弹窗的位置有没有变"""
        snap = r"""() => { const o = { win: [scrollX, scrollY], vv: [visualViewport.offsetLeft, visualViewport.pageLeft, +visualViewport.scale.toFixed(3)], iw: innerWidth }; const m = document.querySelector('#main'), md = [...document.querySelectorAll('.modal')].pop();
          o.main = m && Math.round(m.getBoundingClientRect().left); o.modal = md && Math.round(md.getBoundingClientRect().left);
          o.sx = [...document.querySelectorAll('*')].filter(e => e.scrollLeft > 0).map(e => (e.id || e.className.toString()).slice(0, 30) + ':' + e.scrollLeft); return o; }"""
        a = pg.evaluate(snap)
        # 逐个发真实的触摸事件（synthesizeScrollGesture 在这里不生效，2026-11-08 验证过）
        try:
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
            for i in range(1, 13):
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x + dx * i / 12, 'y': y + dy * i / 12}]}); pg.wait_for_timeout(16)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        except Exception as ex: return {'err': str(ex)[:80]}
        pg.wait_for_timeout(350); z = pg.evaluate(snap)
        moved = z['win'][0] != a['win'][0] or z['vv'] != a['vv'] or z['main'] != a['main'] or z['modal'] != a['modal'] or z['sx'] != a['sx'] or z['iw'] > W + 0.5
        return {'moved': moved, 'before': a, 'after': z} if (moved or dy) else {'moved': False}

    for name in PAGES:
        rec = {}
        try:
            steps = nav(name); rec['nav'] = steps
            rec['top'] = check(f'{name}_top', {'steps': steps})
            # 能滚的：滚到底再查一次（底部固定的东西会不会盖住最后的内容）
            sh = pg.evaluate("() => { const se = document.scrollingElement; return se.scrollHeight - innerHeight; }")
            if sh > 40:
                pg.evaluate("() => window.scrollTo(0, document.scrollingElement.scrollHeight)"); pg.wait_for_timeout(500)
                rec['bottom'] = check(f'{name}_bottom')
                last = pg.evaluate(r"""() => { const m = document.querySelector('#main'); const els = [...m.querySelectorAll('*')].filter(e => e.getBoundingClientRect().height > 0 && e.children.length === 0); const lastEl = els.sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0]; if (!lastEl) return null; const r = lastEl.getBoundingClientRect(); const t = document.elementFromPoint(Math.min(innerWidth - 2, r.left + r.width / 2), Math.min(innerHeight - 2, r.bottom - 3)); return { bottom: Math.round(r.bottom), H: innerHeight, coveredBy: t && !lastEl.contains(t) && !t.contains(lastEl) ? (t.id || t.className.toString()).slice(0, 40) : null }; }""")
                rec['lastEl'] = last
                pg.evaluate("() => window.scrollTo(0, 0)"); pg.wait_for_timeout(300)
            if MOBI:
                rec['swipe'] = {k: swipe(*a) for k, a in {'L_mid': (int(W * .85), H // 2, -int(W * .7), 0), 'R_mid': (int(W * .15), H // 2, int(W * .7), 0), 'L_top': (int(W * .85), 160, -int(W * .7), 0), 'L_low': (int(W * .85), H - 200, -int(W * .7), 0), 'U_mid': (W // 2, int(H * .7), 0, -int(H * .4))}.items()}
                pg.evaluate("() => window.scrollTo(0, 0)")
        except Exception as ex:
            rec['crash'] = str(ex)[:300]
        R['pages'][name] = rec
    # 手机：像用户一样从生视频 / 作品 / 生图点开一个（弹窗 / 大图）再左右滑
    if MOBI:
        R['modal'] = {}
        for pn, sel in (('video', '#vd-gal .vd-tile, #vd-gal .vd-ju'), ('works', '#main .work'), ('img', '#main .ig-tile, #main .ig-ju')):
            try:
                if pn not in PAGES: continue
                nav(pn); pg.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /全部视频|全部图片/.test(x.textContent) && x.offsetParent); }")
                t = pg.query_selector(sel)
                if not t: R['modal'][pn] = {'crash': 'no tile'}; continue
                t.scroll_into_view_if_needed(); bb = t.bounding_box(); pg.touchscreen.tap(bb['x'] + bb['width'] / 2, bb['y'] + min(40, bb['height'] / 2)); pg.wait_for_timeout(1600); pg.evaluate(MUTE)
                pg.touchscreen.tap(bb['x'] + bb['width'] / 2, bb['y'] + min(40, bb['height'] / 2)) if not pg.evaluate("() => !!document.querySelector('.modal-bg, .iv, .viewer, .lb')") else None
                pg.wait_for_timeout(1200); pg.evaluate(MUTE)
                R['modal'][pn] = {'open': pg.evaluate("() => [...document.querySelectorAll('.modal-bg, .iv, .viewer, .lb')].map(e => e.className.toString().slice(0, 30))"), 'check': check(f'{pn}_modal'),
                                  'swipe': {k: swipe(*a) for k, a in {'L': (int(W * .85), H // 2, -int(W * .7), 0), 'R': (int(W * .15), H // 2, int(W * .7), 0), 'L_top': (int(W * .85), 220, -int(W * .7), 0), 'L_low': (int(W * .85), H - 160, -int(W * .7), 0)}.items()}}
                pg.keyboard.press('Escape'); pg.evaluate("() => document.querySelectorAll('.modal-bg').forEach(m => m.remove())")
            except Exception as ex: R['modal'][pn] = {'crash': str(ex)[:200]}
    R['errs'] = errs; R['bad'] = sorted(set(bad)); b.close()
json.dump(R, open(os.path.join(OUT, 'res.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
# 简表
cnt = {}
for n, rec in R['pages'].items():
    for part in ('top', 'bottom'):
        for f in (rec.get(part) or {}).get('F', []): cnt[f['kind']] = cnt.get(f['kind'], 0) + 1
sw = {n: [k for k, v in (rec.get('swipe') or {}).items() if v.get('moved') and k[0] in 'LR'] for n, rec in R['pages'].items()}
print(prof, json.dumps(cnt, ensure_ascii=False), 'hswipe:', {k: v for k, v in sw.items() if v}, 'errs:', len(errs), 'bad:', len(R['bad']), 'crash:', [n for n, r in R['pages'].items() if r.get('crash')])
