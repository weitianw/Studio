/* 视频小窗的界面：应用 / 网页里的悬浮小窗、拖到应用外的独立小窗、网页的画中画窗口，用的都是这一套。
   按钮都浮在画面上（鼠标移上去才出现，画面不变暗）：上面一排是弹出 / 打开 / 收起 / 关闭，下方中间一小组是后退 / 播放 / 前进，最底下是细进度条。 */
'use strict';
/* 播放时每一帧刷新一次（2026-11-05 用户要求）：浏览器的 timeupdate 大约 0.25 秒才来一次，秒数和进度条一跳一跳的。
   只在播放时跑，暂停 / 放完就停；fn 返回 false 时也停（界面没了） */
window.vSmooth = (m, fn) => {
  if (!m) return; if (m._vsm) { m._vsm.push(fn); return; } const fns = m._vsm = [fn]; let r = 0;  // 一个元素可以挂好几个（小窗 + 底栏）；返回 false 的那个就摘掉
  const tick = () => { r = 0; if (m.paused || m.ended) return; for (let i = fns.length - 1; i >= 0; i--) if (fns[i]() === false) fns.splice(i, 1); if (!fns.length) { m._vsm = null; return; } r = requestAnimationFrame(tick); };
  const go = () => { if (!r && !m.paused) r = requestAnimationFrame(tick); };
  m.addEventListener('play', go); m.addEventListener('playing', go); go();
};
window.MiniUI = (() => {
  const st = 'fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"';
  const SVG = {
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>',
    b15: `<svg viewBox="0 0 24 24" ${st}><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.6"/><path d="M4 4v4.6h4.6"/><text x="12.4" y="15.6" text-anchor="middle" font-size="7.2" font-weight="700" fill="currentColor" stroke="none" font-family="system-ui">10</text></svg>`,
    f15: `<svg viewBox="0 0 24 24" ${st}><path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.6"/><path d="M20 4v4.6h-4.6"/><text x="11.6" y="15.6" text-anchor="middle" font-size="7.2" font-weight="700" fill="currentColor" stroke="none" font-family="system-ui">10</text></svg>`,
    pop: `<svg viewBox="0 0 24 24" ${st}><path d="M14 4h6v6M20 4l-7.5 7.5"/><path d="M11 5H6.5A2.5 2.5 0 0 0 4 7.5v10A2.5 2.5 0 0 0 6.5 20h10a2.5 2.5 0 0 0 2.5-2.5V13"/></svg>`,
    back: `<svg viewBox="0 0 24 24" ${st}><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M15.5 9.5L11 14M11 10.2V14h3.8"/></svg>`,
    open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
    fold: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    pin: `<svg viewBox="0 0 24 24" ${st}><path d="M9 3.5h6M10 3.5v5.2L6.8 12.4h10.4L14 8.7V3.5M12 12.4V20.5"/></svg>`,
  };
  const TITLE = {
    pop: '弹出到窗口外（可拖动到任意位置）', back: '放回页面', open: '打开全屏播放', fold: '收起画面（声音继续）', x: '关闭并暂停', pin: '始终在最前面',
  };
  const fmt = s => { s = Math.max(0, s || 0); const m = Math.floor(s / 60), x = Math.floor(s % 60); return `${m}:${String(x).padStart(2, '0')}`; };
  const icon = (b, name) => { if (b && b.dataset.icon !== name) { b.dataset.icon = name; b.innerHTML = SVG[name]; } };

  /* left / right：上面一排左边、右边各放哪些按钮 */
  function html(left, right) {
    const btn = b => `<button type="button" data-mini="${b}" title="${TITLE[b]}">${SVG[b]}</button>`;
    return `<div class="mini-v"></div>
      ${['nw', 'ne', 'sw', 'se'].map(c => `<i class="mini-rz" data-rz="${c}"></i>`).join('')}
      <div class="mini-top">${left.map(btn).join('')}<span class="mini-gap"></span>${right.map(btn).join('')}</div>
      <div class="mini-bot"><div class="mini-mid">
        <button type="button" data-mini="b15" title="后退 10 秒">${SVG.b15}</button><button type="button" data-mini="play" title="播放 / 暂停"></button><button type="button" data-mini="f15" title="前进 10 秒">${SVG.f15}</button>
      </div></div>
      <span class="mini-time"></span>
      <div class="mini-track"><div class="mini-rail"></div><div class="mini-fill"></div><div class="mini-hover"></div><div class="mini-knob"></div><span class="mini-tip"></span></div>`;
  }

  /* 绑定控制栏。video 是要控制的那个视频；hooks：
     cmd(name, e)          右边那些按钮、双击画面（name = 'dbl'）
     drag(phase, e)        在画面上按住拖动（phase = start / move / end）
     resize(corner, phase, e)  拖四个角 */
  function bind(root, video, hooks = {}) {
    const $ = s => root.querySelector(s);
    const tr = $('.mini-track'), PAD = 12;
    const frac = e => { const r = tr.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - r.left - PAD) / (r.width - PAD * 2))); };
    function paint() {
      const d = isFinite(video.duration) ? video.duration : 0, c = video.currentTime || 0, w = tr.clientWidth - PAD * 2, px = d ? Math.min(1, c / d) * w : 0;
      $('.mini-fill').style.width = px + 'px'; $('.mini-knob').style.left = (PAD + px) + 'px';
      $('.mini-time').textContent = `${fmt(c)} / ${fmt(d)}`;
      icon($('[data-mini="play"]'), video.paused ? 'play' : 'pause');
    }
    function aspect() {  // 小窗的比例跟着视频走（竖屏视频也不会有大黑边）
      if (video.videoWidth && video.videoHeight) root.style.setProperty('--ar', Math.min(2.4, Math.max(.5, video.videoWidth / video.videoHeight)));
    }
    ['timeupdate', 'play', 'pause', 'loadedmetadata', 'durationchange', 'seeked', 'emptied'].forEach(ev => video.addEventListener(ev, paint));
    window.vSmooth(video, () => root.isConnected ? paint() : false);  // 进度条、时间连续走
    video.addEventListener('loadedmetadata', aspect);
    aspect();
    const stop = e => e.stopPropagation();
    $('[data-mini="play"]').onclick = e => { stop(e); video.paused ? video.play().catch(() => { }) : video.pause(); };
    $('[data-mini="b15"]').onclick = e => { stop(e); video.currentTime = Math.max(0, video.currentTime - 10); paint(); };
    $('[data-mini="f15"]').onclick = e => { stop(e); video.currentTime = Math.min((video.duration || 1e9) - .05, video.currentTime + 10); paint(); };
    root.querySelectorAll('.mini-top [data-mini]').forEach(b => { if (!['play', 'b15', 'f15'].includes(b.dataset.mini)) b.onclick = e => { stop(e); hooks.cmd?.(b.dataset.mini, e); }; });
    // 进度条：鼠标移上去变粗、出现圆点和时间；可以按住拖
    let seeking = false;
    const seek = e => { const d = video.duration; if (d) video.currentTime = frac(e) * d; paint(); };
    tr.addEventListener('pointerdown', e => { stop(e); seeking = true; tr.setPointerCapture(e.pointerId); root.classList.add('seeking'); seek(e); });
    tr.addEventListener('pointermove', e => {
      const p = frac(e), r = tr.getBoundingClientRect(), x = PAD + p * (r.width - PAD * 2);
      $('.mini-hover').style.left = x + 'px';
      const tip = $('.mini-tip'); tip.style.left = Math.min(r.width - 28, Math.max(28, x)) + 'px'; tip.textContent = fmt(p * (video.duration || 0));
      if (seeking) { stop(e); seek(e); }
    });
    const send = () => { seeking = false; root.classList.remove('seeking'); };
    tr.addEventListener('pointerup', send); tr.addEventListener('pointercancel', send);
    // 拖四个角改大小
    root.querySelectorAll('.mini-rz').forEach(g => {
      let on = false;
      g.addEventListener('pointerdown', e => { stop(e); e.preventDefault(); on = true; g.setPointerCapture(e.pointerId); root.classList.add('sizing'); hooks.resize?.(g.dataset.rz, 'start', e); });
      g.addEventListener('pointermove', e => { if (on) { stop(e); hooks.resize?.(g.dataset.rz, 'move', e); } });
      const end = e => { if (!on) return; on = false; root.classList.remove('sizing'); hooks.resize?.(g.dataset.rz, 'end', e); };
      g.addEventListener('pointerup', end); g.addEventListener('pointercancel', end);
    });
    // 在画面（或控制栏空白处）按住拖动
    let dragging = false;
    root.addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target.closest('button, .mini-track, .mini-rz')) return;
      dragging = true; root.setPointerCapture(e.pointerId); hooks.drag?.('start', e);
    });
    root.addEventListener('pointermove', e => { if (dragging) hooks.drag?.('move', e); });
    const dend = e => { if (!dragging) return; dragging = false; hooks.drag?.('end', e); };
    root.addEventListener('pointerup', dend); root.addEventListener('pointercancel', dend);
    root.addEventListener('lostpointercapture', dend);  // 拖动被系统接管（拖到窗口外）时也算松手
    root.addEventListener('dblclick', e => { if (!e.target.closest('button, .mini-track, .mini-rz')) hooks.cmd?.('dbl', e); });
    paint();
    return { paint, aspect, icon: (name, which) => icon($(`[data-mini="${name}"]`), which) };
  }
  return { html, bind, SVG, fmt };
})();
