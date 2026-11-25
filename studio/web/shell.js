/* 外壳（2026-11-07 改版）：左边分类导航栏
   - 电脑：鼠标停在一类上，右边弹出这一类的页面；点一下也能打开（触屏 / 键盘）；底部按钮展开成完整列表（记住）
   - 手机：底部 播放 · 创作 · 素材 · 工具 · 更多；点一类从下面弹出这一类的页面
   - 播放器：电脑上收成导航栏底部的小圆钮，点一下展开 / 收起播放条 */
'use strict';
(() => {
  const rail = document.getElementById('rail'); if (!rail) return;
  // 导航（2026-11-11 用户选方案 C + D）：一级放常用的（默认 播放 · 生图 · 生视频 · 素材库 · AI 助手，可以自己改），其余按 创作 / 素材 / 工具 收进“更多”；
  // “更多”里鼠标停在一页上点 ☆ 固定到一级；一级上右键：上移 / 下移 / 从导航栏移除。（“最近”那一格 2026-11-11 用户说不需要，去掉了）
  // Ctrl+1 ~ Ctrl+9 = 一级的第几个；Ctrl+K = 搜索页面。页面的图标和名字取自 index.html 里原来的那几项
  const nav = rail.querySelector('.rnav'), PG = {};
  nav.querySelectorAll('a[data-page]').forEach(a => { const s = a.querySelector('svg'); PG[a.dataset.page] = { n: a.querySelector('span')?.textContent.trim() || a.dataset.page, svg: s ? s.outerHTML : '' }; });
  const GR = [['创作', ['tts', 'vc', 'img', 'video', 'audioedit', 'batch']], ['素材', ['works', 'voices', 'mats']], ['工具', ['prompt', 'stt']], ['', ['play']]];
  const NAV0 = ['play', 'img', 'video', 'mats', 'prompt'], NAV_MAX = 7;
  const SV = d => `<svg class="ri" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const DOTS = SV('<circle cx="5.5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="18.5" cy="12" r="1.2"/>');
  const STAR = SV('<path d="M12 4.5l2.3 4.7 5.2.8-3.8 3.6.9 5.1L12 16.3l-4.6 2.4.9-5.1-3.8-3.6 5.2-.8z"/>');
  const h = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pins = () => { const p = (Array.isArray(S.ui?.navPins) ? S.ui.navPins : NAV0).filter((x, i, a) => PG[x] && a.indexOf(x) === i).slice(0, NAV_MAX); return p.length ? p : NAV0.filter(x => PG[x]); };
  const curPage = () => window.__railPage || document.getElementById('main')?.dataset.page || location.pathname.slice(1);
  const SHORT = { stt: '转文字' };  // 收起的导航栏 / 手机底栏地方小：五个字挤成很小的字（2026-11-15 界面检查）；展开的导航栏、“更多”菜单里仍写全名
  const nmH = p => SHORT[p] ? `<span class="rn-s" aria-hidden="true">${h(SHORT[p])}</span><span class="rn-f">${h(PG[p].n)}</span>` : `<span>${h(PG[p].n)}</span>`;
  const pinA = p => `<a href="/${p}" data-page="${p}" class="cat-b"${SHORT[p] ? ` aria-label="${h(PG[p].n)}"` : ''}><i class="ic">${PG[p].svg}</i>${nmH(p)}</a>`;
  const build = () => {
    const P = pins(), more = GR.map(([t, ps]) => { const r = ps.filter(p => PG[p] && !P.includes(p)); return r.length ? (t ? `<div class="fly-h">${t}</div>` : '')
      + r.map(p => `<a href="/${p}" data-page="${p}" role="menuitem">${PG[p].svg}<span>${h(PG[p].n)}</span>${P.length < NAV_MAX ? `<span class="fly-pin" role="button" data-pin="${p}" aria-label="固定到导航栏" data-tip="固定到导航栏">${STAR}</span>` : ''}</a>`).join('') : ''; }).join('');
    nav.innerHTML = P.map(p => `<div class="cat cat-pin" data-cat="pin">${pinA(p)}</div>`).join('')
      + (more ? `<div class="cat cat-more" data-cat="more"><button type="button" class="cat-b" aria-haspopup="menu" aria-expanded="false"><i class="ic">${DOTS}</i><span>更多</span></button><div class="fly" role="menu" aria-label="更多">${more}</div></div>` : '');
  };
  const setPins = P => { S.ui = { ...(S.ui || {}), navPins: P }; persist(); build(); window.railMark?.(curPage()); };
  window.navPinned = () => pins();
  window.navPages = () => Object.entries(PG).map(([p, x]) => ({ p, n: x.n, svg: x.svg }));
  build();
  const cats = () => [...rail.querySelectorAll('.rnav > .cat')];
  const dim = Object.assign(document.createElement('div'), { className: 'rail-dim' }); document.body.append(dim);
  const closeAll = except => cats().forEach(c => { if (c !== except && c.classList.contains('open')) { c.classList.remove('open'); c.querySelector('button.cat-b')?.setAttribute('aria-expanded', 'false'); } });
  const syncDim = () => dim.classList.toggle('on', matchMedia('(max-width: 760px)').matches && cats().some(c => c.classList.contains('open')));
  // 导航收起时：所在那一类的图标和名字换成当前页面的（进了生视频，“创作”就显示生视频），换到别的类就恢复（2026-11-07 用户：页面不再放标题）
  const catFace = page => cats().forEach(c => { const b = c.querySelector(':scope > .cat-b'); if (!b || !c.querySelector('.fly')) return;
    if (b._orig === undefined) b._orig = b.innerHTML;
    const a = !document.documentElement.classList.contains('rail-wide') && matchMedia('(min-width: 761px)').matches && c.querySelector(`.fly a[data-page="${page}"]`);
    const want = a ? `<i class="ic">${a.querySelector('svg')?.outerHTML || ''}</i>${PG[page] ? nmH(page) : `<span>${a.querySelector('span')?.textContent || ''}</span>`}` : b._orig;
    if (b.innerHTML !== want) { b.innerHTML = want; b.classList.toggle('cur-page', !!a); if (a && !matchMedia('(prefers-reduced-motion: reduce)').matches) b.querySelector('.ic')?.animate([{ transform: 'scale(.7)', opacity: .3 }, { transform: 'none', opacity: 1 }], { duration: 260, easing: 'cubic-bezier(.32, .72, 0, 1)' }); } });
  window.railMark = page => {
    window.__railPage = page; catFace(page);
    nav.querySelectorAll('a[data-page]').forEach(a => a.classList.toggle('active', a.dataset.page === page));
    cats().forEach(c => c.classList.toggle('on', !!c.querySelector(`a[data-page="${page}"]`)));
    closeAll(); syncDim();
  };
  rail.addEventListener('click', e => {  // ☆：固定到一级（在链接里面：拦下，不跳页面）
    const pn = e.target.closest('[data-pin]'); if (!pn) return;
    e.preventDefault(); e.stopPropagation(); const P = pins(); if (!P.includes(pn.dataset.pin) && P.length < NAV_MAX) { setPins([...P, pn.dataset.pin]); toast?.('已固定到导航栏：' + PG[pn.dataset.pin].n); }
  }, true);
  rail.addEventListener('contextmenu', e => {  // 一级上右键：上移 / 下移 / 从导航栏移除
    const a = e.target.closest('.cat-pin > a[data-page]'); if (!a || typeof ctxMenu !== 'function') return;
    const P = pins(), p = a.dataset.page, i = P.indexOf(p), mv = d => { const q = [...P]; [q[i], q[i + d]] = [q[i + d], q[i]]; setPins(q); };
    ctxMenu(e, [i > 0 && { label: '上移', on: () => mv(-1) }, i < P.length - 1 && { label: '下移', on: () => mv(1) }, P.length > 1 && { label: '从导航栏移除', on: () => setPins(P.filter(x => x !== p)) },
      JSON.stringify(P) !== JSON.stringify(NAV0) && { label: '恢复默认', on: () => setPins([...NAV0]) }].filter(Boolean));
  });
  rail.addEventListener('click', e => {
    const b = e.target.closest('button.cat-b'); if (!b) return;
    const c = b.closest('.cat'), open = !c.classList.contains('open');
    closeAll(c); c.classList.toggle('open', open); b.setAttribute('aria-expanded', String(open)); syncDim();
    if (open && e.detail === 0) c.querySelector('.fly a')?.focus();  // 键盘打开：焦点进菜单
  });
  /* 电脑上弹出的分类菜单不超出窗口底边（2026-11-15 界面检查：窗口矮的时候“更多”的菜单伸出窗口 50px，
     藏着的时候也把整页撑得能上下滚，导航栏跟着滚上去、播放器圆钮就盖住了显卡占用）：菜单太靠下就往上挪，正好贴着底边 */
  const fitFly = () => {
    if (!matchMedia('(min-width: 761px)').matches || document.documentElement.classList.contains('rail-wide')) { rail.querySelectorAll('.fly').forEach(f => { f.style.top = ''; }); return; }
    rail.querySelectorAll('.rnav > .cat > .fly').forEach(f => {
      const c = f.parentElement, ct = c.getBoundingClientRect().top, h = f.offsetHeight;
      const over = ct - 4 + h - (innerHeight - 8);
      f.style.top = over > 0 ? Math.round(-4 - Math.min(over, ct - 8)) + 'px' : '';
    });
  };
  addEventListener('resize', fitFly); rail.addEventListener('pointerover', e => { const c = e.target.closest('.rnav > .cat'); if (c && c !== rail._fitC) { rail._fitC = c; fitFly(); } });  // 进入新的一类才量（以前每次 pointerover 都量） rail.addEventListener('click', fitFly, true);
  requestAnimationFrame(fitFly); setTimeout(fitFly, 600);
  document.addEventListener('pointerdown', e => { if (!e.target.closest('#rail .cat')) { closeAll(); syncDim(); } }, true);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && cats().some(c => c.classList.contains('open'))) { const c = cats().find(x => x.classList.contains('open')); closeAll(); syncDim(); c?.querySelector('.cat-b')?.focus(); } });
  // 点开一类后鼠标又移到另一类：先关掉点开的那个，同一时间只弹一个菜单（2026-11-07 用户：会叠在一起）
  rail.addEventListener('mouseover', e => { const c = e.target.closest('.rnav > .cat'); if (!c || c === rail._hov) return; rail._hov = c;  // 导航会重画：用委托，不给每一类单独挂
    if (matchMedia('(hover: hover) and (pointer: fine)').matches && cats().some(x => x !== c && x.classList.contains('open'))) closeAll(c); });
  // 快捷键：Ctrl+1 ~ 9 = 一级的第几个；Ctrl+K = 搜索页面（2026-11-11 用户选的方案 D）
  let palClose = null;
  const palOpen = () => {
    if (document.querySelector('.nav-pal')) return;
    const ov = document.createElement('div'); ov.className = 'nav-pal-bg';
    ov.innerHTML = `<div class="nav-pal" role="dialog" aria-label="搜索页面"><input class="input" placeholder="搜索页面" aria-label="搜索页面" autocomplete="off"><div class="nav-pal-l" role="listbox"></div></div>`;
    document.body.append(ov); const inp = ov.querySelector('input'), L = ov.querySelector('.nav-pal-l'); let sel = 0, list = [];
    const all = () => { const P = pins(), ps = Object.keys(PG); return [...P, ...ps.filter(p => !P.includes(p))]; };
    const draw = () => { const q = inp.value.trim().toLowerCase(), P = pins(); list = all().filter(p => !q || PG[p].n.toLowerCase().includes(q) || p.includes(q)); sel = Math.min(sel, Math.max(0, list.length - 1));
      L.innerHTML = list.map((p, i) => `<div class="nav-pal-i${i === sel ? ' on' : ''}" role="option" id="nav-pal-${i}" aria-selected="${i === sel}" data-p="${p}">${PG[p].svg}<span>${h(PG[p].n)}</span>${P.includes(p) && P.indexOf(p) < 9 ? `<kbd>Ctrl ${P.indexOf(p) + 1}</kbd>` : ''}</div>`).join('') || '<div class="nav-pal-e">没有这个页面</div>';
      const o = L.querySelector('.on'); inp.setAttribute('aria-activedescendant', o ? o.id : ''); o?.scrollIntoView({ block: 'nearest' }); };  // U06：键盘选中的那项一直看得见
    const close = () => { ov.remove(); palClose = null; if (back?.isConnected) back.focus({ preventScroll: true }); };
    const back = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
    palClose = close;
    const pick = p => { close(); if (p) window.go?.(p); };
    inp.oninput = () => { sel = 0; draw(); };
    // 2026-11-17 UI 审查 U04 / U05：中文输入法选词时的回车 / 方向键交给输入法；Esc 在搜索框里哪儿都能关，Tab 不让焦点跑到背后的页面
    ov.addEventListener('keydown', ev => { if (ev.isComposing || ev.keyCode === 229) return; if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); close(); } else if (ev.key === 'Tab') { ev.preventDefault(); inp.focus(); } });
    inp.onkeydown = ev => { if (ev.isComposing || ev.keyCode === 229) return; if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { ev.preventDefault(); sel = (sel + (ev.key === 'ArrowDown' ? 1 : list.length - 1)) % Math.max(1, list.length); draw(); }
      else if (ev.key === 'Enter') { ev.preventDefault(); pick(list[sel]); } };
    ov.onclick = ev => { const it = ev.target.closest('[data-p]'); if (it) return pick(it.dataset.p); if (!ev.target.closest('.nav-pal')) close(); };
    draw(); inp.focus();
  };
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || document.querySelector('.modal-bg')) return;
    if (/^[1-9]$/.test(e.key)) { const p = pins()[+e.key - 1]; if (p) { e.preventDefault(); palClose?.(); window.go?.(p); } }  // 搜索开着时用 Ctrl+数字切页：搜索框一起收起（U05）
    else if (e.key.toLowerCase() === 'k') { e.preventDefault(); palOpen(); }
  });
  rail.addEventListener('mouseleave', () => { if (matchMedia('(hover: hover) and (pointer: fine)').matches) { closeAll(); } });
  // 返回上一页（2026-11-07 用户）：标题左边一个“‹”，和大多数应用一样；没有上一页时不显示
  const BACK_IC = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>';
  const backPlace = () => {
    const h = document.querySelector('#main > .page-head'); if (!h) return;
    let b = h.querySelector('.pg-back');
    if (!b) { b = document.createElement('button'); b.type = 'button'; b.className = 'pg-back'; b.setAttribute('aria-label', '返回'); b.dataset.tip = '返回上一页'; b.innerHTML = BACK_IC; b.onclick = () => history.back();
      const ctx = h.querySelector(':scope > .b5-l, :scope > .b5-ctx');
      if (h.classList.contains('b5-head') && ctx) { if (ctx.classList.contains('b5-l')) ctx.prepend(b); else { const w = document.createElement('div'); w.className = 'b5-l'; ctx.before(w); w.append(b, ctx); } }
      else { const t = h.querySelector('.page-title'); let host = t?.parentElement || h;
        // 标题直接在标题栏里（配音、作品…）：标题栏两端对齐，返回键插进去会把标题挤到最右边（2026-11-08 用户）——返回键和标题包成一组
        if (t && host === h) { host = document.createElement('div'); t.before(host); host.append(t); }
        host.prepend(b); host.classList.add('pg-titlew'); } }
    // 手机：底栏上的几个页面是最上一级，不显示返回（2026-11-16 手机改版：iOS 的标签页没有返回）
    const tabRoot = document.documentElement.classList.contains('ph') && pins().slice(0, 4).includes(curPage());
    b.hidden = !(window.go?.depth > 0) || tabRoot;
    h.classList.toggle('has-back', !b.hidden);
  };
  { const m = document.getElementById('main'); if (m) { let q = 0; new MutationObserver(() => { cancelAnimationFrame(q); q = requestAnimationFrame(backPlace); }).observe(m, { childList: true, subtree: false }); backPlace(); } }
  // 展开 / 收起导航（记住）
  const tog = document.getElementById('rail-tog');
  const wide = on => {
    document.documentElement.classList.toggle('rail-wide', on);
    const t = on ? '收起导航' : '展开导航'; tog?.setAttribute('aria-label', t); tog?.setAttribute('data-tip', t);
  };
  wide(document.documentElement.classList.contains('rail-wide'));
  // 2026-11-17 用户：这个按钮基本不用——导航栏上不再放，开关挪到设置页（railWideSet）
  window.railWideSet = on => { if (on === document.documentElement.classList.contains('rail-wide')) return; tog?.onclick?.(); };
  if (tog) tog.onclick = () => {
    const on = !document.documentElement.classList.contains('rail-wide'), H = document.documentElement;
    H.classList.add('rail-anim'); clearTimeout(tog._t); tog._t = setTimeout(() => { H.classList.remove('rail-anim'); dispatchEvent(new Event('resize')); }, 360);  // 宽度动画只在点按钮时有（打开页面时不动）
    wide(on); catFace(window.__railPage || document.getElementById('main')?.dataset.page);
    try { S.ui = { ...(S.ui || {}), railWide: on }; persist(); } catch { }
    requestAnimationFrame(() => { try { pbLayout(); } catch { } dispatchEvent(new Event('resize')); });
  };
  // 播放器小圆钮：电脑上一直在导航栏底部，点一下展开 / 收起播放条
  const fab = document.getElementById('pb-fab');
  // 点音符：转一下，播放器从这里往上展开（导航栏上）；再点转回去收起（2026-11-07 用户）。播放页、配音、换声、改录音还是底部那条（2026-11-10 用户）
  const railMode = () => matchMedia('(min-width: 761px)').matches && !['play', 'tts', 'vc', 'audioedit'].includes(document.getElementById('main')?.dataset.page) && !document.body.classList.contains('compact');
  if (fab) fab.onclick = () => {
    const minNow = document.body.classList.contains('pb-min');
    fab.classList.remove('spin'); void fab.offsetWidth; fab.classList.add('spin'); setTimeout(() => fab.classList.remove('spin'), 520);
    if (!minNow && railMode() && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.body.classList.add('pb-closing'); setTimeout(() => { document.body.classList.remove('pb-closing'); try { pbMin(true); } catch { } }, 230); return; }
    try { pbMin(!minNow); } catch { } };
  try {  // 改版后第一次打开：电脑上播放条先收起（底部留给输入框），以后按用户上次的选择
    if (!S.ui?.b5) { S.ui = { ...(S.ui || {}), b5: 1 }; persist(); pbMin(true); }
  } catch { }
  // 顶部（logo 下面）：展开 / 收起导航、精简模式（浏览器里才有）；底部从上到下：播放器小圆钮、显卡、私密空间、设置（2026-11-07 用户）
  const top = document.createElement('div'); top.className = 'rail-top'; rail.querySelector('.brand')?.after(top);
  const tg = document.getElementById('rail-tog'); if (tg) top.append(tg);
  const cp = document.getElementById('cp-open'); if (cp) { top.append(cp); cp.dataset.tip = cp.title || '精简模式'; cp.removeAttribute('title'); }
  try {  // 第 2 轮改版（2026-11-07）：缩略图默认在左边一列（贴着导航栏，像可灵）；以后按用户的选择
    if (!S.ui?.b5v2) { S.ui = { ...(S.ui || {}), b5v2: 1 }; S.galLay = 'col'; persist(); }
    if (!S.ui?.b5v3) { S.ui = { ...(S.ui || {}), b5v3: 1 }; S.galLay = 'col'; persist(); }  // 2026-11-07 用户选方案 A：缩略图放回左边（两列大缩略图）
  } catch { }
  // 小圆钮放在导航栏底部那几个按钮上面（按钮多少不一样：浏览器里多一个精简模式、私密空间多一个标记）
  const foot = rail.querySelector('.rail-foot');
  // --fab-b：圆钮离底边多高。导航栏上展开的播放器跟着它摆（私密空间里底部多一个按钮、圆钮往上挪时，播放器以前不动，圆钮正好盖住里面的音量键，2026-11-08）
  const fitFab = () => { if (!fab) return; if (matchMedia('(max-width: 760px)').matches) { fab.style.bottom = ''; return; } const fb = Math.round(innerHeight - foot.getBoundingClientRect().top + 10); fab.style.bottom = fb + 'px'; document.documentElement.style.setProperty('--fab-b', fb + 'px'); };
  addEventListener('resize', fitFab); if (window.ResizeObserver && foot) new ResizeObserver(fitFab).observe(foot); fitFab();
  { let q = 0; addEventListener('scroll', () => { if (!q) q = requestAnimationFrame(() => { q = 0; fitFab(); }); }, { passive: true }); }  // 整页滚动时导航栏会跟着动：圆钮跟着它（不然会盖住底部的按钮）
  // 开关：点了以后那一块常被整块重画（比如“使用模板”），新开关直接是开好的样子、没有滑动。重画后给新开关补一次滑动动画
  document.addEventListener('change', e => {
    const i = e.target; if (!i.matches?.('.switch input[type=checkbox]') || !i.id) return;
    const id = i.id, old = i;
    const fix = () => { const n = document.getElementById(id); if (!n || n === old) return; const sp = n.nextElementSibling; if (!sp || sp._swIn) return;
      sp._swIn = 1; sp.classList.add(n.checked ? 'sw-on' : 'sw-off'); setTimeout(() => sp.classList.remove('sw-on', 'sw-off'), 450); };
    [0, 30, 120, 300].forEach(t => setTimeout(fix, t));
  }, true);
  // 缩略图的宽高比给样式用（下面一排固定高度、按比例排宽度）
  const arMark = root => root.querySelectorAll?.('.ig-ju[data-ar]:not([data-arv])').forEach(e => { e.style.setProperty('--ar', e.dataset.ar); e.dataset.arv = '1'; });
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) { if (n.matches?.('.ig-ju[data-ar]')) arMark(n.parentElement || n); arMark(n); } }))).observe(document.body, { childList: true, subtree: true });
  arMark(document);
  try { window.railMark(document.getElementById('main')?.dataset.page || location.pathname.slice(1)); } catch { }
})();
