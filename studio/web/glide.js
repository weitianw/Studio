/* 液态高亮：分段控件、左侧导航、播放页音源列表里“选中的那一块”是同一个滑块，切换时从旧位置流动到新位置
   （移动途中先拉长、再收回，像一滴液体），不再是一格消失、另一格突然亮起。
   各处的代码照旧只切换按钮的 on / active 类名，这里自动跟上，不用改那些代码。 */
'use strict';
(() => {
  const GROUPS = [
    // 导航改成分类栏（2026-11-07）：不再用滑块  // 导航：短距离平移、不拉伸，连点时直接到位（快速切页不晕）
    { sel: '.seg', item: 'button', on: 'on' },
    { sel: '#play-src', item: '.ps-item', on: 'on' },
  ];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const memo = new Map();  // 按 id 记住上一次的位置：整组被重新渲染时也能从旧位置滑过来
  const groupOf = el => { for (const g of GROUPS) if (el.matches(g.sel)) return g; return null; };
  const boxOf = it => ({ x: it.offsetLeft, y: it.offsetTop, w: it.offsetWidth, h: it.offsetHeight });
  const mix = (a, b, k) => a + (b - a) * k;
  const css = b => ({ transform: `translate(${b.x}px, ${b.y}px)`, width: b.w + 'px', height: b.h + 'px' });
  const EASE = 'cubic-bezier(.32, .72, .16, 1)';
  // 选中的是“哪一个”（重画后元素换了新的，也能认出是不是同一个）
  const idOf = it => it.dataset.src || it.dataset.kind || it.dataset.page || it.getAttribute('href') || Object.entries(it.dataset).map(e => e.join('=')).join('&') || it.textContent.trim();

  function place(el, animate = true) {
    const g = el._glide || groupOf(el); if (!g) return;
    el._glide = g;
    let ind = el.querySelector(':scope > .glide');
    if (!ind) { ind = document.createElement('i'); ind.className = 'glide'; ind.setAttribute('aria-hidden', 'true'); el.prepend(ind); el.classList.add('glide-on'); }
    const on = [...el.children].find(x => x.matches(g.item) && x.classList.contains(g.on));
    el.querySelectorAll(':scope > .glided').forEach(x => { if (x !== on) x.classList.remove('glided'); });
    if (!on || !on.offsetWidth) { ind.style.opacity = '0'; ind._box = null; return; }
    // 滑块的颜色 / 阴影 / 圆角取选中项自己的样式（深浅色、私密空间各自不同），然后把选中项本身的底色去掉
    on.classList.add('glide-read'); on.classList.remove('glided');  // glide-read：读的时候关掉过渡，拿到的是最终颜色而不是过渡中途的颜色
    const cs = getComputedStyle(on);
    Object.assign(ind.style, { background: cs.backgroundColor, boxShadow: cs.boxShadow, borderRadius: cs.borderRadius, opacity: '1' });
    on.classList.add('glided'); on.classList.remove('glide-read');
    const next = boxOf(on), key = el.id ? '#' + el.id : null, who = idOf(on);
    const fresh = !ind._box, m = fresh && key ? memo.get(key) : null;  // fresh：整组刚被重新画过（滑块是新建的）
    const last = fresh ? m : { box: ind._box, who: ind._who, run: ind._run };
    const same = b => b && b.x === next.x && b.y === next.y && b.w === next.w && b.h === next.h;
    let prev = last?.box || null, resume = null;
    const running = last?.run && performance.now() - last.run.t0 < last.run.dur;
    if (last && last.who === who) {
      // 选中的还是同一个：只是列表重新排了（展开 / 收起文件夹、换类型筛选、重画）——直接放到新位置，不滑。
      // 正好在滑的途中被重画：接着把这一段滑完，不从头再来
      prev = null;
      if (running && same(last.run.to)) resume = last.run;
    } else if (fresh && last) {
      // 整组重画过、选中的换了一个（比如换了类型筛选后，选中项是跟着变的，不是你点的）：直接放到新位置，不滑——滑一下没有意义
      prev = null;
    } else if (running) {  // 上一次还没滑完又点了别的：从现在所在的位置接着滑，不会跳
      const r = ind.getBoundingClientRect(), pr = el.getBoundingClientRect();
      prev = { x: r.left - pr.left - el.clientLeft + el.scrollLeft, y: r.top - pr.top - el.clientTop + el.scrollTop, w: r.width, h: r.height };  // 列表滚动过：加上滚动的距离
    }
    ind.getAnimations().forEach(a => a.cancel());
    Object.assign(ind.style, css(next));
    ind._box = next; ind._who = who;
    const save = run => { ind._run = run; if (key) memo.set(key, { box: next, who, run }); };
    if (resume && !reduce) {  // （大小变化触发的重新定位也一样：正在滑就让它滑完）
      const a = ind.animate(resume.kf, { duration: resume.dur, easing: EASE });
      a.currentTime = performance.now() - resume.t0;
      return save(resume);
    }
    save(null);
    if (!animate || reduce || !prev || same(prev)) return;
    if (g.calm) {
      const now = performance.now(), quick = window.__navQuick === true;  // 连续快速切页的第三次起不滑
      if (quick) return;  // 0.4 秒内又切了一次：不滑，直接停在新位置
      const kf = [{ ...css(prev) }, { ...css(next) }], dur = 200;
      ind.animate(kf, { duration: dur, easing: 'cubic-bezier(.2, .8, .2, 1)' });
      return save({ kf, dur, t0: now, to: next });
    }
    // 中间那一帧：在“两块的平均”和“两块合起来”之间，横着走时略微压扁，竖着走时略微变窄
    const ux = Math.min(prev.x, next.x), uy = Math.min(prev.y, next.y);
    const uw = Math.max(prev.x + prev.w, next.x + next.w) - ux, uh = Math.max(prev.y + prev.h, next.y + next.h) - uy;
    const ax = mix(prev.x, next.x, .5), ay = mix(prev.y, next.y, .5), aw = mix(prev.w, next.w, .5), ah = mix(prev.h, next.h, .5);
    const horiz = Math.abs(next.x - prev.x) >= Math.abs(next.y - prev.y);
    const k = .55, mw = mix(aw, uw, k), mh = mix(ah, uh, k);
    const mid = horiz ? { x: mix(ax, ux, k), y: ay + ah * .04, w: mw, h: ah * .92 }
      : { x: ax + aw * .03, y: mix(ay, uy, k), w: aw * .94, h: mh };
    const dist = Math.hypot(next.x - prev.x, next.y - prev.y);
    const kf = [{ ...css(prev) }, { ...css(mid), offset: .42 }, { ...css(next) }], dur = Math.min(560, 340 + dist * .5);
    ind.animate(kf, { duration: dur, easing: EASE });
    save({ kf, dur, t0: performance.now(), to: next });
  }

  // 找出所有分组，选中项变了就滑过去；新渲染出来的分组也自动接上。
  // MutationObserver 的回调在浏览器画下一帧之前执行：底色的交接和动画的起点都在同一帧里完成，不会闪一下
  // 被移出页面的分组：不再盯着它（不然整页旧内容一直留在内存里，听一晚上越占越多）
  const ro = new ResizeObserver(es => es.forEach(e => { const el = e.target; if (!el.isConnected) { ro.unobserve(el); el._glideSeen = false; return; } if (el._glide && !window.fsHold?.()) place(el, false); }));  // 视频全屏期间不动（app.js fsHold）
  function scan(root, out) {
    for (const g of GROUPS) {
      const els = root.matches?.(g.sel) ? [root] : [];
      els.push(...root.querySelectorAll(g.sel));
      els.forEach(el => { if (!el._glideSeen) { el._glideSeen = true; ro.observe(el); } out.add(el); });
    }
  }
  const mo = new MutationObserver(ms => {
    const todo = new Set();
    for (const m of ms) {
      if (m.type === 'attributes') {
        const it = m.target, el = it.parentElement;
        if (el && el._glide && it.matches(el._glide.item) && it.classList.contains(el._glide.on) !== it.classList.contains('glided')) todo.add(el);
      } else {
        m.addedNodes.forEach(n => { if (n.nodeType !== 1) return; scan(n, todo); const el = n.parentElement; if (el?._glide) todo.add(el); });
      }
    }
    todo.forEach(el => el.isConnected && place(el));
  });
  window.Glide = { refresh: () => document.querySelectorAll('.glide-on').forEach(el => place(el, false)) };
  const start = () => { const s = new Set(); scan(document.body, s); s.forEach(el => place(el, false)); mo.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] }); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
