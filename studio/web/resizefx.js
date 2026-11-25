/* 改窗口大小时的过渡：只处理“到某个宽度会重新排列”的东西（音色卡片、工具栏按钮、两栏 / 上下排的卡片）。
   - 连续的小变化：实时跟手，不加动画。
   - 一下子挪了一大截（换行、换列）：从原来的位置滑到新位置。
   - 滑的途中位置又变了（慢慢拖的时候常有）：从“现在看得到的位置”接着滑向新目标，不会先跳到旧终点再重来。
   - 位置按“相对上一层”来算：卡片挪了，里面的音色跟着卡片走，不会自己再滑一次（以前两层一起动，看起来乱）。
   - 最大化 / 还原 / 贴边分屏（一下子变几百像素）：直接换布局，不加动画。 */
'use strict';
(() => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const SEL = '.grid-tts > *, .play-grid > .card, .side-col > .card, .voice-pick > .vp, .toolbar > .grp, .toolbar > .chip';
  const JUMP = 36, DUR = 320, EASE = 'cubic-bezier(.25, .8, .25, 1)';
  let last = new Map(), raf = 0, lastW = innerWidth, lastH = innerHeight;
  const parentOf = el => el.parentElement?.closest(SEL);
  // 元素现在“排版上”的位置（去掉正在播放的滑动动画），相对上一层被跟踪的元素
  function layoutPos(el) {
    const r = el.getBoundingClientRect();
    let x = r.left, y = r.top;
    const m = getComputedStyle(el).transform;
    if (m && m !== 'none') { const v = new DOMMatrixReadOnly(m); x -= v.e; y -= v.f; }
    const p = parentOf(el);
    if (p) { const q = layoutPos(p); x -= q.x; y -= q.y; }
    return { x, y, w: r.width, vis: r.width > 0 && r.bottom > -80 && r.top < innerHeight + 80 };
  }
  function offsetNow(el) {  // 正在滑：现在相对排版位置偏了多少
    const m = getComputedStyle(el).transform;
    if (!m || m === 'none') return { dx: 0, dy: 0 };
    const v = new DOMMatrixReadOnly(m); return { dx: v.e, dy: v.f };
  }
  function snap() {
    const m = new Map();
    document.querySelectorAll(SEL).forEach(el => { const p = layoutPos(el); if (p.vis) m.set(el, p); });
    return m;
  }
  function frame() {
    raf = 0;
    if (window.fsHold?.()) return;  // 视频全屏 / 刚退出全屏：窗口大小是应用自己改的，背后的卡片不滑动（app.js）
    const big = Math.abs(innerWidth - lastW) > 200 || Math.abs(innerHeight - lastH) > 200;
    lastW = innerWidth; lastH = innerHeight;
    if (big) { document.querySelectorAll(SEL).forEach(el => el.getAnimations().forEach(a => a.id === 'rflip' && a.cancel())); last = snap(); return; }
    const now = new Map();
    document.querySelectorAll(SEL).forEach(el => {
      const n = layoutPos(el); if (!n.vis) return;
      now.set(el, n);
      const o = last.get(el); if (!o) return;
      const dx = o.x - n.x, dy = o.y - n.y;
      if (Math.hypot(dx, dy) < JUMP) return;  // 连续的小变化：跟手
      const cur = offsetNow(el);  // 正在滑的话，从现在看得到的位置接着滑
      el.getAnimations().forEach(a => a.id === 'rflip' && a.cancel());
      const a = el.animate([{ transform: `translate(${dx + cur.dx}px, ${dy + cur.dy}px)` }, { transform: 'none' }], { duration: DUR, easing: EASE });
      a.id = 'rflip';
    });
    last = now;
  }
  addEventListener('resize', () => { if (!raf) raf = requestAnimationFrame(frame); });
  // 平时更新位置记录（页面内容变了、滚动了，都以最新的为准）；改窗口大小时由上面逐帧更新。
  // 2026-11-17 审查 P07：以前每 700 毫秒不管有没有变化都量一遍（播放页每次都要重新排版）；现在只在页面真的变了之后才量：
  // DOM 变化（浮在上面的播放页 / 播放列表 / 底栏 / 提示不算，它们不影响下面卡片的位置）、图片载入、滚动、改窗口大小
  let busy = 0, dirty = true;
  const FLOAT = '#np, #qpanel, #pbar, .toast';
  new MutationObserver(recs => {
    if (dirty) return;
    for (const r of recs) { const t = r.target.nodeType === 1 ? r.target : r.target.parentElement; if (t && !t.closest(FLOAT)) { dirty = true; return; } }
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'style'] });
  addEventListener('resize', () => { dirty = true; clearTimeout(busy); busy = setTimeout(() => { busy = 0; }, 500); });
  setInterval(() => { if (dirty && !busy && !raf && !document.hidden && !window.fsHold?.()) { dirty = false; last = snap(); } }, 700);
  addEventListener('scroll', () => { dirty = true; if (!busy) last = new Map(); }, { passive: true, capture: true });
  addEventListener('load', () => { dirty = true; }, true);  // 图片等载入完（捕获阶段才收得到）也会挪位置
  addEventListener('load', () => { last = snap(); });
})();
