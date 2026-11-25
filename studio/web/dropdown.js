/* 下拉框：把系统自带的 <select> 换成和整个界面一致的样式（圆角按钮 + 浮出的圆角菜单，选中项打勾）。
   原来的 <select> 还在（只是看不见），选中时照常触发 change / input，所以各处原来的代码不用改；
   代码里直接改 select.value 时，按钮上的文字也会跟着变。加了 class="native" 的保持系统样式。 */
'use strict';
(() => {
  const CHEV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10l5 5 5-5"/></svg>';
  const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  let menu = null, cur = null, hi = -1;

  function label(sel) { const o = sel.options[sel.selectedIndex]; return o ? o.textContent : ''; }
  function sync(sel) {
    const b = sel._dd; if (!b) return;
    const t = label(sel); if (b._t !== t) { b._t = t; b.querySelector('.dd-t').textContent = t; }
    b.disabled = sel.disabled; b.title = sel.title || ''; b.hidden = sel.hidden;  // 原来的 select 藏起来时按钮也藏（以前插帧关着时“RIFE 4.26”还显示，2026-11-06 修）
  }
  function enhance(sel) {
    if (sel._dd || sel.classList.contains('native') || sel.multiple || sel.size > 1) return;
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'dd ' + [...sel.classList].filter(c => c !== 'select').join(' ');
    b.style.cssText = sel.style.cssText;
    b.innerHTML = `<span class="dd-t"></span><span class="dd-c">${CHEV}</span>`;
    b.setAttribute('aria-haspopup', 'listbox');
    sel.after(b); sel.classList.add('dd-src'); sel._dd = b; b._sel = sel;
    b.onclick = e => { e.preventDefault(); e.stopPropagation(); cur === sel ? close() : open(sel); };
    b.onkeydown = e => { if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key) && cur !== sel) { e.preventDefault(); open(sel); } };
    sel.addEventListener('change', () => sync(sel));
    new MutationObserver(() => sync(sel)).observe(sel, { childList: true, subtree: true, attributes: true, characterData: true });
    sync(sel);
  }
  // 代码里改 select.value / selectedIndex 时同步按钮
  for (const k of ['value', 'selectedIndex']) {
    const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, k);
    Object.defineProperty(HTMLSelectElement.prototype, k, { ...d, set(v) { d.set.call(this, v); if (this._dd) sync(this); } });
  }

  function open(sel) {
    close();
    cur = sel; const b = sel._dd; b.classList.add('open');
    menu = document.createElement('div'); menu.className = 'dd-menu'; menu.setAttribute('role', 'listbox');
    let html = '';
    [...sel.children].forEach(ch => {
      if (ch.tagName === 'OPTGROUP') { html += `<div class="dd-g">${escH(ch.label)}</div>`; [...ch.children].forEach(o => html += item(o)); }
      else html += item(ch);
    });
    menu.innerHTML = html;
    document.body.append(menu);
    const r = b.getBoundingClientRect();
    menu.style.minWidth = Math.min(r.width, innerWidth - 20) + 'px'; menu.style.maxWidth = (innerWidth - 20) + 'px';  // 选项名字很长时（手机上）不伸出屏幕：在框里换行
    const h = menu.offsetHeight, w = menu.offsetWidth;
    let y = r.bottom + 6; if (y + h > innerHeight - 10 && r.top - h - 6 > 10) { y = r.top - h - 6; menu.classList.add('up'); }
    menu.style.top = y + 'px'; menu.style.left = Math.max(10, Math.min(innerWidth - w - 10, r.left)) + 'px';
    const items = [...menu.querySelectorAll('.dd-i')];
    hi = items.findIndex(i => i.classList.contains('on')); paintHi(); items[hi]?.scrollIntoView({ block: 'nearest' });
    menu.addEventListener('mousemove', e => { const i = e.target.closest('.dd-i'); if (i) { hi = items.indexOf(i); paintHi(); } });
    menu.addEventListener('click', e => { const i = e.target.closest('.dd-i'); if (i && !i.classList.contains('dis')) pick(+i.dataset.i); });
    requestAnimationFrame(() => menu && menu.classList.add('show'));
  }
  const item = o => `<div class="dd-i${o.selected ? ' on' : ''}${o.disabled ? ' dis' : ''}" role="option" data-i="${o.index}"><span class="dd-k">${CHECK}</span><span>${escH(o.textContent)}</span></div>`;
  function escH(t) { return String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]); }
  function paintHi() { menu?.querySelectorAll('.dd-i').forEach((x, k) => x.classList.toggle('hi', k === hi)); }
  function pick(idx) {
    const sel = cur; close(); if (!sel || sel.selectedIndex === idx) return sel?._dd.focus();
    sel.selectedIndex = idx;
    sel.dispatchEvent(new Event('input', { bubbles: true })); sel.dispatchEvent(new Event('change', { bubbles: true }));
    sel._dd.focus();
  }
  function close() {
    if (!menu) return;
    const m = menu; menu = null; m.classList.remove('show'); setTimeout(() => m.remove(), 140);
    cur?._dd.classList.remove('open'); cur = null;
  }
  document.addEventListener('pointerdown', e => { if (menu && !e.target.closest('.dd-menu, .dd')) close(); }, true);
  document.addEventListener('keydown', e => {
    if (!menu) return;
    const items = [...menu.querySelectorAll('.dd-i')];
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); const s = cur; close(); s?._dd.focus(); }  // 只关菜单，不连带关掉外面的浮层 / 播放页
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); hi = (hi + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; paintHi(); items[hi]?.scrollIntoView({ block: 'nearest' }); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (items[hi]) pick(+items[hi].dataset.i); }
  }, true);
  addEventListener('resize', close);
  addEventListener('scroll', e => { if (menu && !menu.contains(e.target)) close(); }, { passive: true, capture: true });

  const scan = root => (root.matches?.('select') ? [root] : [...(root.querySelectorAll?.('select') || [])]).forEach(enhance);
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => n.nodeType === 1 && scan(n)))).observe(document.documentElement, { childList: true, subtree: true });
  const start = () => scan(document.body);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
