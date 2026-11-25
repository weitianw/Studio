/* 看图：播放页点一张图片，铺满窗口看大图。
   - ← / → 或两边的按钮、底下的缩略图条：上一张 / 下一张（手机上左右滑）
   - 滚轮 / + − 缩放（以鼠标位置为中心），放大后按住拖动；双击在“适应窗口”和“放大”之间切换；0 = 适应窗口
   - R 旋转、空格 / ▶ 自动播放（每 4 秒一张）、F 全屏、I 文件信息（尺寸、大小、拍摄时间、相机……）、Esc 关闭
   - 一段时间不动鼠标，上下的工具条自动淡出 */
'use strict';
window.ImageViewer = (() => {
  const IC = {
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
    r: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
    zin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6M11 8v6"/></svg>',
    zout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6"/></svg>',
    fit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/><rect x="8" y="9" width="6" height="4" rx=".8" stroke-width="1.6"/></svg>',  // 适应窗口：放大镜里一个画框，和旁边的放大 / 缩小一组（2026-11-15 用户：原来和全屏是同一个四角图标；画框样式又像画中画）
    rot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="10" width="10.5" height="10.5" rx="1.5"/><path d="M8 6h5.5a5.5 5.5 0 0 1 5.5 5.5V14"/><path d="M16.5 11.5 19 14l2.5-2.5"/></svg>',  // 旋转：方块 + 绕过去的箭头（Apple rotate.right；圆形箭头在别处是“重新生成”）
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6.5" y="5" width="4" height="14" rx="1"/><rect x="13.5" y="5" width="4" height="14" rx="1"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.1"/></svg>',
    cmp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M12 3v18"/></svg>',
    live: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="9.2" stroke-dasharray="1.6 2.2"/></svg>',
    fs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
    fsx: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>',  // 退出全屏
    more: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="12" r="9"/><circle cx="7.6" cy="12" r="1.15" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.15" fill="currentColor" stroke="none"/><circle cx="16.4" cy="12" r="1.15" fill="currentColor" stroke="none"/></svg>',
  };
  let alt = false, hideT = 0, el = null, list = [], i = 0, z = 1, tx = 0, ty = 0, rot = 0, show = null, idle = 0, drag = null, onClose = null, actions = null, info = localStorage.getItem('ivinfo') === '1';
  const $ = s => el.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function build() {
    el = document.createElement('div'); el.className = 'iv'; el.tabIndex = -1;
    el.innerHTML = `<div class="iv-stage"><img class="iv-ph" alt="" draggable="false" hidden><img class="iv-img" alt="" draggable="false"><video class="iv-lv" playsinline preload="none" hidden></video></div>
      <div class="iv-top"><button type="button" class="iv-livebtn" data-a="live" hidden data-tip="实况：按住照片播放">${IC.live}<span>实况</span></button><div class="iv-title"><b></b><span class="iv-idx"></span></div>
        <div class="iv-tools"><button data-a="zout" title="缩小（−）">${IC.zout}</button><span class="iv-z">100%</span><button data-a="zin" title="放大（+）">${IC.zin}</button>
          <button data-a="fit" title="适应窗口（0）">${IC.fit}</button><button data-a="rot" title="旋转（R）">${IC.rot}</button>
          <button data-a="show" title="自动播放（空格）">${IC.play}</button><button data-a="alt" class="iv-alt" title="对比细化前的原图（按住 C）" hidden>${IC.cmp}</button><button data-a="info" title="文件信息（I）">${IC.info}</button><button data-a="fs" title="全屏（F）">${IC.fs}</button><button data-a="more" class="iv-more" title="更多" aria-label="更多" hidden>${IC.more}</button><button data-a="close" title="关闭（Esc）">${IC.x}</button></div></div>
      <button class="iv-nav prev" data-a="prev" title="上一张（←）">${IC.l}</button><button class="iv-nav next" data-a="next" title="下一张（→）">${IC.r}</button>
      <div class="iv-strip"></div><div class="iv-info"></div><div class="iv-bar" hidden></div>`;
    document.body.append(el);
    if (!el.requestFullscreen && !el.webkitRequestFullscreen) el.querySelector('[data-a="fs"]').hidden = true;
    const fsMark = () => { const b = el.querySelector('[data-a="fs"]'), on = (document.fullscreenElement || document.webkitFullscreenElement) === el; b.innerHTML = on ? IC.fsx : IC.fs; b.title = on ? '退出全屏（F）' : '全屏（F）'; };
    document.addEventListener('fullscreenchange', fsMark); document.addEventListener('webkitfullscreenchange', fsMark);  // iPhone：不支持网页全屏，按了也没用
    el.addEventListener('click', e => {
      const b = e.target.closest('[data-a]'); if (b) { e.stopPropagation(); act(b.dataset.a); return; }
      const t = e.target.closest('.iv-th'); if (t) { jump(+t.dataset.i); return; }
      const bb = e.target.closest('.iv-bar [data-k]'); if (bb) { e.stopPropagation(); const it = (actions?.(i) || []).filter(x => x && x.short)[+bb.dataset.k]; it?.on(); return; }
      if (e.target.classList.contains('iv-stage') && z <= 1.001 && Date.now() - (stage._moved || 0) > 350) setTimeout(() => { if (z <= 1.001 && Date.now() - (stage._moved || 0) > 350) close(); }, 330);  // 等一下：手机上可能是双击  // 点空白处关闭（放大时、刚拖动 / 滑动过时不关）
    });
    const stage = $('.iv-stage');
    stage.addEventListener('wheel', e => { e.preventDefault(); zoomAt(z * (e.deltaY < 0 ? 1.18 : 1 / 1.18), e.clientX, e.clientY); }, { passive: false });
    let lastType = 'mouse';
    stage.addEventListener('dblclick', e => { if (lastType === 'touch') return; if (z > 1.01) fit(); else zoomAt(2.5, e.clientX, e.clientY); });
    // 手机：双指捏合缩放（以两指中间为中心，捏的同时可以挪）、双击放大 / 还原、放大后单指拖动、没放大时左右滑换图
    const pts = new Map(); let pinch = null, lastTap = null;
    const two = () => { const [a, b] = [...pts.values()]; return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
    stage.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      lastType = e.pointerType;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      try { stage.setPointerCapture(e.pointerId); } catch { }
      if (pts.size === 2) { const t = two(); pinch = { d: t.d, x: t.x, y: t.y, z, tx, ty }; drag = null; stage._moved = Date.now(); return; }
      drag = { x: e.clientX, y: e.clientY, tx, ty, moved: false, touch: e.pointerType === 'touch', t: Date.now() };
      clearTimeout(liveT); if (list[i]?.live && z <= 1.001) liveT = setTimeout(() => { if (drag && !drag.moved && pts.size === 1) { drag.live = true; live(true); } }, 260);  // 实况：按住照片播放（和 iPhone 相册一样）
    });
    stage.addEventListener('pointermove', e => {
      if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && pts.size >= 2) {
        const t = two(), nz = Math.max(1, Math.min(12, pinch.z * t.d / pinch.d)), k = nz / pinch.z;
        const ox = pinch.x - (innerWidth - side0()) / 2 - pinch.tx, oy = pinch.y - innerHeight / 2 - pinch.ty;
        z = nz; tx = pinch.tx - ox * (k - 1) + (t.x - pinch.x); ty = pinch.ty - oy * (k - 1) + (t.y - pinch.y);
        if (z <= 1.001) { tx = 0; ty = 0; }
        paint(false); wake(); return;
      }
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.hypot(dx, dy) > 4) { drag.moved = true; if (!drag.live) clearTimeout(liveT); }
      if (z > 1.001) { tx = drag.tx + dx; ty = drag.ty + dy; paint(false); stage.classList.add('grab'); }
      else if (drag.touch && !drag.down && list.length > 1 && (drag.side || (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) * 1.2))) {  // 横着滑：图跟着手指走（照片 App），松手再决定换不换（2026-11-16 用户：换图要有动画）
        drag.side = true; stage.style.transition = 'none'; stage.style.transform = `translateX(${dx}px)`; }
      else if (drag.touch && !drag.side && (drag.down || (dy > 12 && dy > Math.abs(dx) * 1.3))) {  // 往下拉：图跟着手往下走、背景变淡，松手够远就关（照片 App）
        drag.down = true; const k = Math.max(0, dy); stage.style.transform = `translateY(${k}px) scale(${Math.max(.82, 1 - k / 1600)})`; el.style.setProperty('--iv-bg', String(Math.max(.2, 1 - k / 420))); el.classList.add('iv-pull'); }
    });
    const up = e => {
      pts.delete(e.pointerId); clearTimeout(liveT);
      if (e.type === 'pointercancel' && drag?.side) { drag = null; stage.style.transition = 'transform .22s cubic-bezier(.2, .8, .2, 1)'; stage.style.transform = ''; return; }
      if (drag?.live) { live(false); stage._moved = Date.now(); drag = null; return; }
      if (pinch) {  // 松开一根手指：剩下那根接着拖
        if (pts.size < 2) { pinch = null; const r = [...pts.values()][0]; drag = r ? { x: r.x, y: r.y, tx, ty, moved: true, touch: true, t: 0 } : null; stage._moved = Date.now(); }
        return;
      }
      if (!drag) return;
      const dx = e.clientX - drag.x;
      if (drag.down) { const dy = e.clientY - drag.y; el.classList.remove('iv-pull'); stage.style.transform = ''; el.style.removeProperty('--iv-bg'); stage._moved = Date.now(); drag = null; if (dy > 110) close(); return; }
      if (drag.touch && !drag.moved && Date.now() - drag.t < 300) {  // 手机上双击：放大到点的位置 / 还原
        if (lastTap && Date.now() - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
          if (z > 1.01) fit(); else zoomAt(2.5, e.clientX, e.clientY);
          lastTap = null; stage._moved = Date.now();
        } else lastTap = { t: Date.now(), x: e.clientX, y: e.clientY };
      }
      if (drag.side) { const v = Math.abs(dx) / Math.max(1, Date.now() - drag.t); stage._moved = Date.now(); drag = null;
        if (Math.abs(dx) > innerWidth * .22 || (Math.abs(dx) > 30 && v > .45)) slide(dx < 0 ? 1 : -1, dx); else { stage.style.transition = 'transform .22s cubic-bezier(.2, .8, .2, 1)'; stage.style.transform = ''; }
        return; }
      if (drag.moved) stage._moved = Date.now();
      stage.classList.remove('grab'); drag = null;
    };
    stage.addEventListener('pointerup', up); stage.addEventListener('pointercancel', up);
    el.addEventListener('contextmenu', e => { e.preventDefault(); if (lastType === 'touch' || pts.size || pinch) return; close(); });  // 右键：退出看图（手机长按不算）
    stage.addEventListener('lostpointercapture', e => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; });
    resetTouch = () => { pts.clear(); pinch = null; drag = null; lastTap = null; };
    // 底下的缩略图条：按住左右拖动（像拖一卷胶片），滚轮也能左右滚；拖过了松手不算点了某张
    const strip = $('.iv-strip');
    let sd = null;
    strip.addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.pointerType === 'touch') return;  // 手机本来就能用手指滑
      sd = { x: e.clientX, left: strip.scrollLeft, moved: false, id: e.pointerId };
    });
    strip.addEventListener('pointermove', e => {
      if (!sd) return;
      const dx = e.clientX - sd.x;
      if (!sd.moved && Math.abs(dx) > 4) { sd.moved = true; try { strip.setPointerCapture(sd.id); } catch { } strip.classList.add('grab'); }
      if (sd.moved) strip.scrollLeft = sd.left - dx;
      wake();
    });
    const sup = () => { if (!sd) return; strip.classList.remove('grab'); if (sd.moved) strip._dragged = Date.now(); sd = null; };
    strip.addEventListener('pointerup', sup); strip.addEventListener('pointercancel', sup);
    strip.addEventListener('click', e => { if (Date.now() - (strip._dragged || 0) < 250) { e.stopPropagation(); e.preventDefault(); } }, true);
    strip.addEventListener('wheel', e => { if (strip.scrollWidth <= strip.clientWidth) return; e.preventDefault(); strip.scrollLeft += Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY; wake(); }, { passive: false });
    el.addEventListener('mousemove', wake);
    const lb = $('.iv-livebtn');
    lb.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') live(true); });
    lb.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') live(false); });
    $('.iv-img').addEventListener('load', () => { paint(false); el.classList.remove('loading'); idx(); if (list[i] && $('.iv-img').getAttribute('src') === list[i].src) $('.iv-ph').hidden = true; });
    $('.iv-img').addEventListener('error', () => { el.classList.remove('loading'); $('.iv-idx').textContent += '  · 无法打开此图片'; });
  }
  // 实况：图后面那一小段视频，放在图的位置上（同样的大小和变换），放完或松手就回到图
  let liveT = 0;
  function live(on) {
    const v = $('.iv-lv'), img = $('.iv-img'), it = list[i];
    if (!on || !it?.live) { v.pause(); v.hidden = true; img.style.visibility = ''; $('.iv-livebtn').classList.remove('on'); return; }
    if (v.dataset.src !== it.live) { v.src = it.live; v.dataset.src = it.live; }
    v.style.cssText = `width:${img.style.width};height:${img.style.height};transform:${img.style.transform}`;
    v.currentTime = 0; v.hidden = false; $('.iv-livebtn').classList.add('on');
    v.onplaying = () => { img.style.visibility = 'hidden'; };
    v.onended = () => live(false);
    v.play().catch(() => live(false));
  }
  function wake() { el.classList.remove('idle'); clearTimeout(idle); idle = setTimeout(() => { if (!drag) el.classList.add('idle'); }, 2600); }
  function base() {  // 适应窗口时的缩放比例（不放大超过原尺寸）
    const img = $('.iv-img'), w = img.naturalWidth || 1, h = img.naturalHeight || 1, side = rot % 180 !== 0;
    const vw = innerWidth - 40 - side0(), vh = innerHeight - 150;
    return Math.min(1, vw / (side ? h : w), vh / (side ? w : h));
  }
  const side0 = () => info && innerWidth > 640 ? 290 : 0;  // 开着文件信息面板时，图片往左让出面板的位置
  function paint(anim = true) {
    const img = $('.iv-img'), b = base();
    img.style.transition = anim ? 'transform .28s cubic-bezier(.2, .8, .2, 1)' : 'none';
    img.style.width = (img.naturalWidth || 0) + 'px'; img.style.height = (img.naturalHeight || 0) + 'px';
    img.style.transform = `translate(-50%, -50%) translate(${tx - side0() / 2}px, ${ty}px) scale(${b * z}) rotate(${rot}deg)`;
    $('.iv-z').textContent = Math.round(b * z * 100) + '%';
  }
  function zoomAt(nz, cx, cy) {
    nz = Math.max(1, Math.min(12, nz));
    // 以鼠标位置为中心缩放：鼠标下面那一点缩放前后不动
    const ox = cx - (innerWidth - side0()) / 2 - tx, oy = cy - (innerHeight / 2 - 0) - ty, k = nz / z;
    tx -= ox * (k - 1); ty -= oy * (k - 1); z = nz;
    if (z <= 1.001) { tx = 0; ty = 0; }
    paint(); wake();
  }
  function fit() { z = 1; tx = 0; ty = 0; paint(); }
  // 换图带滑动（手机：手指甩出去 / 底栏的上一张、下一张）：当前这张往一边滑出，下一张从另一边滑进来
  // 2026-11-17 UI 审查 #1：目标图号（pend）和滑动动画分开记——滑到一半又按“下一张”，从目标图再往后算（以前第二下把第一下的换图取消了，连按两次只走一张）；
  // 关掉 / 重开 / 直接跳图时收掉没跑完的定时器和舞台位移（以前关掉马上重开，旧定时器又把新打开的切走；减少动态效果时拖完舞台停在半路）
  let sliding = 0, pend = null;
  function settle(apply = true) {  // 把没滑完的那次立刻做完（apply = false：直接作废）
    clearTimeout(sliding); sliding = 0;
    const st = el && $('.iv-stage'); if (st) { st.style.transition = 'none'; st.style.transform = ''; }
    const n = pend; pend = null;
    if (apply && n != null) go(n);
  }
  function slide(dir, from = 0) {
    const st = $('.iv-stage'), W = innerWidth + 24, n = (pend ?? i) + dir;
    settle();
    if (!st || matchMedia('(prefers-reduced-motion: reduce)').matches) return go(n);
    st.style.transform = `translateX(${from}px)`; st.getBoundingClientRect();
    st.style.transition = 'transform .2s cubic-bezier(.3, .6, .4, 1)'; st.style.transform = `translateX(${-dir * W}px)`;
    pend = n;
    sliding = setTimeout(() => {
      pend = null;
      st.style.transition = 'none'; st.style.transform = `translateX(${dir * W}px)`; go(n); st.getBoundingClientRect();
      st.style.transition = 'transform .28s cubic-bezier(.2, .8, .2, 1)'; st.style.transform = '';
      sliding = setTimeout(() => { sliding = 0; st.style.transition = ''; }, 300);
    }, 190);
  }
  function jump(n) { settle(false); go(n); }  // 缩略图、键盘、自动播放直接跳：先收掉没滑完的
  function go(n) {
    queueMicrotask(() => { try { bar(); } catch { } });
    if (!list.length) return;
    i = (n + list.length) % list.length;
    const it = list[i], img = $('.iv-img');
    z = 1; tx = 0; ty = 0; rot = 0;
    el.classList.add('loading');
    img.style.opacity = '0';
    const src = it.src; alt = false;
    // 2026-11-17 UI 审查 #4：原图还没到手时，先在主图位置放这张的缩略图（缩略图条里多半已经载过），原图解码好原位换上；
    // 原图打不开时缩略图留着。以前这段时间主图是透明的、标题却已换了
    const ph = $('.iv-ph'), th = it.thumb && it.thumb !== src ? it.thumb : null;
    ph.hidden = true; ph.removeAttribute('src');
    if (th) { ph.style.width = `calc(100vw - ${40 + side0()}px)`; ph.style.transform = `translate(-50%, -50%) translateX(${-side0() / 2}px)`; ph.src = th; }
    const ab = $('.iv-alt'); ab.hidden = !it.alt; ab.classList.remove('on'); ab.title = `对比${it.altName || '细化前的原图'}（按住 C）`;
    live(false); $('.iv-livebtn').hidden = !it.live;
    const pre = new Image();
    pre.onload = () => { if (list[i] !== it) return; img.src = src; img.style.opacity = ''; };
    pre.onerror = () => { if (list[i] !== it) return; img.src = src; img.style.opacity = ''; if (th) img.style.visibility = 'hidden'; };  // 打不开：留着缩略图（图片的 error 里写“无法打开”）
    pre.src = src;
    img.style.visibility = '';
    if (th && !pre.complete) ph.hidden = false;  // 原图在缓存里就不必闪一下缩略图
    $('.iv-title b').textContent = it.name; idx(true); if (info) infoPaint(); bar();  // 底部工具栏每张图重算（有没有可对比的不一样）
    [1, -1].forEach(d => { const nx = list[(i + d + list.length) % list.length]; if (nx) new Image().src = nx.src; });  // 预先加载前后两张
    $$('.iv-th').forEach(t => t.classList.toggle('on', +t.dataset.i === i));
    $(`.iv-th[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    el.classList.toggle('single', list.length < 2);
    wake();
  }
  const $$ = s => [...el.querySelectorAll(s)];
  function idx(noSize) {  // 标题下面：第几张 · 尺寸 · 所在文件夹
    const it = list[i], img = $('.iv-img'), wh = !noSize && img.naturalWidth ? `${img.naturalWidth} × ${img.naturalHeight}` : '';
    $('.iv-idx').textContent = [`${i + 1} / ${list.length}`, wh, it.sub].filter(Boolean).join('  ·  ');
  }
  const size = b => b >= 1 << 20 ? (b / (1 << 20)).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
  const when = t => { const d = new Date(t * 1000), p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };
  async function infoPaint() {  // 文件信息面板：每张图第一次看时去问服务器，记住结果
    const it = list[i], box = $('.iv-info');
    el.classList.toggle('info', info);
    if (!info) return;
    if (!it._info) { box.innerHTML = `<div class="iv-ih">${esc(it.name)}</div><div class="iv-ir"><span>读取中…</span></div>`; it._info = it.info ? await it.info().catch(() => ({})) : {}; }
    if (list[i] !== it || !info) return;
    const f = it._info, rows = [
      ['尺寸', f.w ? `${f.w} × ${f.h}${f.frames ? `（${f.frames} 帧动图）` : ''}` : ''], ['大小', f.size ? size(f.size) : ''], ['格式', f.ext],
      ['拍摄时间', f.taken ? f.taken.replace(/^(\d{4}):(\d\d):(\d\d)/, '$1-$2-$3') : ''], ['相机', f.camera], ['镜头', f.lens], ['参数', f.shot],
      [f.prompt ? '生成时间' : '修改时间', f.mtime ? when(f.mtime) : ''], ['位置', f.prompt ? '' : it.sub],
      ['模型', f.model], ['方式', f.mode], ['参数', f.sample], ['种子', f.seed], ['用时', f.took], ['提示词', f.prompt], ['实际生成用的', f.used], ['负面提示词', f.negative], ['说明', f.note]];
    box.innerHTML = `<div class="iv-ih">${esc(it.name)}</div>` + rows.filter(r => r[1]).map(([k, v]) => `<div class="iv-ir"><span>${k}</span><b>${esc(v)}</b></div>`).join('')
      + (f.prompt ? '<div class="iv-icp"><button type="button" data-a="copyp">复制提示词</button></div>' : '');  // 2026-11-23：详情页去掉了，它的“复制提示词”和实际用的提示词放到这里
  }
  function act(a) {
    if (a === 'close') return close();
    if (a === 'more') { const b = $('.iv-more'), items = actions?.(i); if (items?.length && window.ctxMenu) window.ctxMenu({ anchor: b }, items); return; }  // 调用方给的操作菜单（素材库：作为姿势 / 衣服 / 脸……）
    if (a === 'live') return live(true);
    if (a === 'copyp') { const p = list[i]?._info?.prompt || ''; (window.copyText ? window.copyText(p) : navigator.clipboard.writeText(p)).then(() => window.toast?.('已复制提示词'), er => window.toast?.(er.message, true)); return; }
    const ph = document.documentElement.classList.contains('ph');  // 手机：上一张 / 下一张也是滑过去的
    if (a === 'prev') return ph ? slide(-1) : jump(i - 1);
    if (a === 'next') return ph ? slide(1) : jump(i + 1);
    if (a === 'zin') return zoomAt(z * 1.4, innerWidth / 2, innerHeight / 2);
    if (a === 'zout') return zoomAt(z / 1.4, innerWidth / 2, innerHeight / 2);
    if (a === 'fit') return fit();
    if (a === 'rot') { rot = (rot + 90) % 360; z = 1; tx = ty = 0; return paint(); }
    if (a === 'show') return slideshow(!show);
    if (a === 'alt') {  // 细化前 / 后来回切（位置和缩放不变）
      const it = list[i]; if (!it?.alt) return;
      alt = !alt; $('.iv-img').src = alt ? it.alt : it.src; $('.iv-alt').classList.toggle('on', alt);
      $('.iv-title b').textContent = alt ? (it.altName || '细化前的原图') : it.name; return;
    }
    if (a === 'info') { info = !info; localStorage.setItem('ivinfo', info ? '1' : '0'); $('[data-a="info"]').classList.toggle('on', info); paint(); return infoPaint(); }
    if (a === 'fs') {  // iPad 只有带 webkit 前缀的；iPhone 不支持网页全屏（看图本来就铺满屏幕，按钮已藏起来）
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement, req = el.requestFullscreen || el.webkitRequestFullscreen;
      if (fsEl) Promise.resolve((document.exitFullscreen || document.webkitExitFullscreen).call(document)).catch(() => { });
      else if (req) Promise.resolve(req.call(el)).catch(() => { });
    }
  }
  function slideshow(on) {
    clearInterval(show); show = on ? setInterval(() => jump(i + 1), 4000) : null;
    const b = $('[data-a="show"]'); b.innerHTML = on ? IC.pause : IC.play; b.classList.toggle('on', !!on);
  }
  function key(e) {
    if (!el || el.hidden) return;
    if (document.querySelector('.ctx-menu')) return;  // ··· 菜单开着：键盘（Esc、方向键）交给菜单
    const k = e.key, map = { ArrowLeft: 'prev', ArrowRight: 'next', Escape: 'close', '+': 'zin', '=': 'zin', '-': 'zout', '0': 'fit', r: 'rot', R: 'rot', f: 'fs', F: 'fs', i: 'info', I: 'info', ' ': 'show', c: 'alt', C: 'alt' };
    if (!map[k]) return;
    if (k === 'Escape' && document.fullscreenElement) return;  // 先退出全屏
    e.preventDefault(); e.stopImmediatePropagation(); act(map[k]);
  }
  addEventListener('resize', () => { if (el && !el.hidden) paint(false); });
  let opener = null, resetTouch = () => { };
  function open(items, start = 0, opts = {}) {
    if (!items.length) return;
    if (!el) { build(); document.addEventListener('keydown', key, true); }
    if (!document.body.classList.contains('iv-open')) opener = document.activeElement;  // 记下是谁打开的，关掉后焦点回到那里
    list = items; onClose = opts.onClose || null; actions = opts.actions || null;
    if (opts.info) info = true;  // 从“详情和提示词”打开：直接开着信息面板（不改记住的开关）
    $('.iv-more').hidden = !actions;
    bar();
    $('.iv-strip').innerHTML = items.length > 1 ? items.map((it, k) => `<button class="iv-th" data-i="${k}" title="${esc(it.name)}"><img loading="lazy" src="${esc(it.thumb || it.src)}" alt=""></button>`).join('') : '';
    clearTimeout(hideT); el.hidden = false; el.classList.remove('out'); document.body.classList.add('iv-open');  // 刚关上又马上打开：取消还没执行的“藏起来”
    $('[data-a="info"]').classList.toggle('on', info); el.classList.toggle('info', info);
    settle(false); go(start); el.focus();
  }
  function bar() {  // 手机：常用操作放到底部工具栏（带 short 的那几项）；电脑照旧在右上角“···”
    const b = $('.iv-bar'); if (!b) return; const ph = document.documentElement.classList.contains('ph'), its = ph ? (actions?.(i) || []).filter(x => x && x.short) : [];
    b.hidden = !its.length; el.classList.toggle('iv-hasbar', its.length > 0);
    b.innerHTML = its.map((x, k) => `<button type="button" data-k="${k}" class="${x.danger ? 'dg' : ''}" aria-label="${esc(x.label)}">${x.icon || ''}<span>${esc(x.short)}</span></button>`).join('');
  }
  function close() {
    if (!el || el.hidden) return;
    resetTouch(); settle(false);
    slideshow(false); live(false);
    if (document.fullscreenElement === el) document.exitFullscreen().catch(() => { });
    el.classList.add('out'); document.body.classList.remove('iv-open');
    clearTimeout(hideT); hideT = setTimeout(() => { el.hidden = true; el.classList.remove('out'); $('.iv-img').removeAttribute('src'); }, 180);
    onClose?.(i);
    if (opener?.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }
  return { open, close, isOpen: () => !!el && !el.hidden };
})();
