/* 手机上的外壳行为（2026-11-07）：
   1) 状态栏下面一条实色的窄条：iOS 26 主屏幕 App 会把最上面一段页面糊掉，顶上有一条整宽、实色、固定的条时就不糊了
   2) 打字时（键盘弹起）把底部标签栏和播放小圆钮收起来，不再被键盘顶到半空
   3) 换声 / 语音转文字 / 改录音：下面的“记录”收进左边抽屉（标题左边一个圆钮，带条数），页面只留输入；正在处理的那条仍在页面上 */
(() => {
  const mq = matchMedia('(max-width: 760px)'), html = document.documentElement, $ = s => document.querySelector(s);
  // 1) 状态栏实色条
  const strip = Object.assign(document.createElement('div'), { id: 'sb-strip' }); strip.setAttribute('aria-hidden', 'true'); document.body.append(strip);
  // 2) 键盘：可视区域比窗口矮一大截、焦点在输入框里 = 键盘开着
  const vv = window.visualViewport;
  const kb = () => {
    const a = document.activeElement, typing = !!a && (a.matches?.('textarea, input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=button]), [contenteditable="true"]'));
    const open = mq.matches && typing && !!vv && innerHeight - vv.height > 140;
    html.classList.toggle('kb-open', open);
    if (vv) html.style.setProperty('--vvh', Math.round(vv.height) + 'px');
  };
  vv?.addEventListener('resize', kb); document.addEventListener('focusin', () => setTimeout(kb, 60)); document.addEventListener('focusout', () => setTimeout(kb, 120));
  // 3) 记录抽屉
  const SRC = {
    vc: () => $('#main #vc-rec-list')?.closest('.vc-out'),
    stt: () => $('#main #stt-list')?.closest('.card'),
    audioedit: () => $('#main #ae-list')?.closest('.card'),
  };
  const HIST_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h10M4 15h16"/></svg>';
  const dw = Object.assign(document.createElement('aside'), { id: 'm-dw', className: 'm-dw' }); dw.setAttribute('aria-label', '记录');
  const scrim = Object.assign(document.createElement('div'), { className: 'm-dw-scrim' });
  document.body.append(dw, scrim);
  const setOpen = on => document.body.classList.toggle('mdw-open', on);
  scrim.onclick = () => setOpen(false);
  { let x0 = null; const ts = e => { x0 = e.touches[0].clientX; }, te = e => { if (x0 != null && e.changedTouches[0].clientX - x0 < -50) setOpen(false); x0 = null; };
    [dw, scrim].forEach(el => { el.addEventListener('touchstart', ts, { passive: true }); el.addEventListener('touchend', te, { passive: true }); }); }
  dw.addEventListener('click', e => { if (e.target.closest('a[href], [data-page]')) setOpen(false); });
  let btn = null, cnt = null;
  const count = () => { if (!btn) return; const n = [...dw.querySelectorAll('#stt-list > *, #ae-list > *, #vc-rec-list > *')].filter(e => !e.matches('.tiny, .empty, .shimmer, .muted')).length; const b = btn.querySelector('.m-dw-n'); b.textContent = n ? (n > 99 ? '99+' : n) : ''; };
  const clear = () => { setOpen(false); dw.replaceChildren(); btn?.remove(); btn = null; cnt?.disconnect(); cnt = null; document.body.classList.remove('mdw-on'); };
  const sync = () => {
    const main = document.getElementById('main'), page = main?.dataset.page, get = SRC[page];
    if (!mq.matches || !get) return clear();
    const card = get(); if (!card) { if (!dw.firstChild || !main.contains(btn)) clear(); return; }
    if (card.parentElement === dw) return;
    clear();
    if (page === 'vc') { const job = card.querySelector('#vc-job-area'); if (job) card.before(job); }  // 正在换的那条留在页面上
    dw.append(card); document.body.classList.add('mdw-on');
    const head = main.querySelector(':scope > .page-head');
    btn = document.createElement('button'); btn.type = 'button'; btn.className = 'm-dw-b lg'; btn.setAttribute('aria-label', '记录');
    btn.innerHTML = HIST_IC + '<span class="m-dw-n"></span>';
    btn.onclick = () => setOpen(!document.body.classList.contains('mdw-open'));
    head?.prepend(btn);
    cnt = new MutationObserver(count); cnt.observe(dw, { childList: true, subtree: true }); count();
  };
  let rq = 0; const soon = () => { cancelAnimationFrame(rq); rq = requestAnimationFrame(sync); };
  const main = document.getElementById('main');
  if (main) new MutationObserver(soon).observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-page'] });
  mq.addEventListener?.('change', () => { if (!mq.matches && dw.firstChild) { clear(); const p = main?.dataset.page; if (p && window.go) go(p); } else soon(); });
  soon();
})();
