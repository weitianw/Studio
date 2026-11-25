/* 说明文字收进小问号：
   - window.hintHtml(内容)：生成一个“?”，鼠标停留 0.6 秒（或键盘聚焦）后在旁边浮出说明卡片。
   - 页面里所有 class="help" 的说明段落（高级参数下面那些长解释），自动收成它所属标题 / 参数名旁边的“?”；
     加了 class="keep" 的（当前状态提示，比如“最终发给模型的指令”）照常显示。
   - 带 data-tip="说明 HTML" 的元素（比如分段按钮）：鼠标停上去也浮出同样的卡片；只在有鼠标的设备上（手机点一下就是选中，不弹说明）。
   说明卡片浮在最上层（挂在 body 上），不会被滚动区域裁掉；靠近屏幕边缘时自动换方向。 */
'use strict';
(() => {
  window.hintHtml = (html, cls = '') => `<span class="tip-q ${cls}" tabindex="0" aria-label="说明">?<span class="tip-card">${html}</span></span>`;
  let card = null, owner = null;
  const float = () => card || (card = Object.assign(document.createElement('div'), { className: 'tip-float' }), document.body.append(card), card);
  /* 2026-11-07 用户：说明太长。每一行只留第一句（到“。”“；”为止，太长就在逗号处截断），去掉长括号，最多 4 行；
     写了 data-tip-full 的（真要讲清楚的）原样显示 */
  const brief = html => {
    const strip = t => t.replace(/<[^>]+>/g, '');
    const lines = html.split(/(?:<br\s*\/?>\s*)+/i).map(l => l.trim()).filter(l => strip(l).trim());
    return lines.slice(0, 4).map(l => {
      l = l.replace(/（[^（）]{7,}）/g, '').replace(/\([^()]{12,}\)/g, '');
      const t = strip(l), m = t.search(/[。；]/); let cut = m > 0 ? m + 1 : t.length;
      if (cut > 46) { const k = t.slice(0, 46).lastIndexOf('，'); cut = k > 10 ? k : 46; }
      if (cut >= t.length) return l;
      // 按纯文字的位置截断，保留开头的 <b>…</b>
      let n = 0, out = '';
      for (const part of l.split(/(<[^>]+>)/)) { if (part.startsWith('<')) { out += part; continue; } if (n >= cut) continue; out += part.slice(0, cut - n); n += part.length; }
      return out.replace(/[，、：；]$/, '').replace(/<b>([^<]*)$/, '<b>$1</b>');
    }).join('<br>');
  };
  function show(q) {
    const html = q.dataset.tip || q.querySelector('.tip-card')?.innerHTML; if (!html) return;
    const c = float(); owner = q;
    c.innerHTML = q.hasAttribute('data-tip-full') ? html : brief(html); c.classList.add('show');
    const r = q.getBoundingClientRect(), w = c.offsetWidth, h = c.offsetHeight;
    let x = r.left + r.width / 2 - 24, y = r.bottom + 10;
    if (x + w > innerWidth - 12) x = Math.max(12, r.right - w + 12);
    if (y + h > innerHeight - 12) y = Math.max(12, r.top - h - 10);
    c.style.left = Math.max(12, x) + 'px'; c.style.top = y + 'px';
  }
  function hide(q) { if (card && (!q || q === owner)) { card.classList.remove('show'); owner = null; } }
  const hover = matchMedia('(hover: hover) and (pointer: fine)');
  // 浏览器自带的 title 提示（样子和网站不一样）：鼠标停上去时换成同一种浮层
  const esc = t => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const target = el => { const q = el.closest?.('.tip-q') || (hover.matches ? el.closest?.('[data-tip], button[title], a[title], [role=button][title], label[title], .vd-tile[title], .ig-ju[title], .ig-tile[title]') : null);
    if (q && q.hasAttribute('title') && !q.classList.contains('tip-q')) { const t = q.getAttribute('title'); if (t) q.dataset.tip = esc(t).replace(/\n/g, '<br>'); q.removeAttribute('title'); }
    return q && (q.dataset.tip || q.classList.contains('tip-q')) ? q : null; };
  // 点了带 data-tip 的按钮：说明收起来，不挡住选好的结果。按钮点完常会重画、鼠标下面又来一次 mouseover：鼠标真的移开（超过几像素）之前都不再弹
  let muted = null;
  // 鼠标停一会儿（0.6 秒）再显示（2026-11-04 用户要求：一放上去就弹太打扰）；已经有说明开着时，移到旁边的按钮上立刻换过去
  const DELAY = 600;
  let timer = 0, pend = null;
  const cancel = () => { clearTimeout(timer); timer = 0; pend = null; };
  document.addEventListener('mouseover', e => {
    if (muted || document.body.classList.contains('tip-hold')) return;
    const q = target(e.target);
    if (q && q !== owner) {
      if (owner) { cancel(); show(q); return; }
      if (q === pend) return;
      cancel(); pend = q; timer = setTimeout(() => { const p = pend; cancel(); if (p && p.isConnected && p.matches(':hover')) show(p); }, DELAY);
    } else if (!q) { cancel(); if (owner && !e.target.closest('.tip-float')) hide(); }
  });
  document.addEventListener('pointerdown', e => { cancel(); if (owner?.dataset.tip && owner.contains(e.target)) { muted = { x: e.clientX, y: e.clientY }; hide(); } }, true);
  document.addEventListener('mousemove', e => { if (muted && Math.hypot(e.clientX - muted.x, e.clientY - muted.y) > 6) muted = null; }, { passive: true });
  document.addEventListener('focusin', e => { const q = e.target.closest?.('.tip-q'); if (q) show(q); });
  document.addEventListener('focusout', e => { const q = e.target.closest?.('.tip-q'); if (q) hide(q); });
  addEventListener('scroll', () => { cancel(); hide(); }, { passive: true, capture: true });

  // 把 .help 段落收成“?”：挂在同一个参数块里它前面的那个名字上，没有就挂在前面最近的小标题 / 卡片标题上
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  function hostFor(h) {
    const opt = h.closest('.opt, .field');
    if (opt) { const ls = [...opt.querySelectorAll('.label')].filter(l => before(l, h) && !l.contains(h)); if (ls.length) return ls[ls.length - 1]; }
    for (let p = h.previousElementSibling; p; p = p.previousElementSibling) {
      if (p.matches('.sec-label, .card-title, .label, h3')) return p;
      const l = p.querySelectorAll?.('.sec-label, .card-title, .label'); if (l?.length) return l[l.length - 1];
    }
    return h.closest('.card, .modal')?.querySelector('.card-title, h3') || null;
  }
  function fold(root) {
    const list = root.matches?.('.help') ? [root] : [...(root.querySelectorAll?.('.help') || [])];
    list.forEach(h => {
      if (h.classList.contains('keep') || h.closest('.help-doc') || h._folded) return;
      const txt = h.innerHTML.trim(); h._folded = true;
      if (!txt) { h.remove(); return; }
      const host = hostFor(h); if (!host) return;
      const old = host.querySelector(':scope > .tip-q.auto');
      if (old) old.querySelector('.tip-card').innerHTML += '<br><br>' + txt;
      else host.insertAdjacentHTML('beforeend', hintHtml(txt, 'sm auto'));
      h.remove();
    });
  }
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => n.nodeType === 1 && fold(n)))).observe(document.documentElement, { childList: true, subtree: true });
  const start = () => fold(document.body);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
