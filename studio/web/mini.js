/* 应用外的视频小窗（studio/app.py 打开的独立窗口）。和主窗口的通信都经过 app.py：
   这边 → 主窗口：进度（底栏跟着走）、放完了、放回页面 / 关闭；主窗口 → 这边：miniCmd（底栏的播放、拖动、换下一个视频…） */
'use strict';
const S0 = (() => { try { return JSON.parse(decodeURIComponent(location.hash.slice(1))); } catch { return {}; } })();
const BAR = 0;  // 按钮都浮在画面上，窗口大小 = 画面大小
const root = document.getElementById('mini');
root.innerHTML = MiniUI.html(['back'], ['pin', 'x']);
const v = document.createElement('video');
v.className = 'np-video'; v.playsInline = true; v.preload = 'auto';
root.querySelector('.mini-v').append(v);
const API = () => window.pywebview?.api;
let pin = S0.top !== false, rate = S0.rate || 1;
if (S0.ar) root.style.setProperty('--ar', S0.ar);

function paintPin() {
  const b = root.querySelector('[data-mini="pin"]');
  b.classList.toggle('on', pin); b.title = pin ? '始终在最前面：开（点击关闭）' : '始终在最前面：关（点击开启）';
}
let loadN = 0;
function load(src, t, play) {
  v.src = src; v.volume = S0.vol ?? 1; v.playbackRate = rate;
  const n = ++loadN;  // 连着按“下一个”：只有最后一次的起点 / 播放生效
  v.addEventListener('loadedmetadata', () => { if (n !== loadN) return; if (t) v.currentTime = t; v.playbackRate = rate; if (play) v.play().catch(e => { window._perr = e.name + ': ' + e.message; }); }, { once: true });
}
const state = () => ({ t: v.currentTime || 0, d: isFinite(v.duration) ? v.duration : 0, paused: v.paused, w: innerWidth, ar: ar(), top: pin });
window.miniState = state;
let last = 0;
const report = force => { const n = Date.now(); if (!force && n - last < 250) return; last = n; API()?.state(state()).catch(() => { }); };
v.addEventListener('timeupdate', () => report());
['play', 'pause', 'seeked', 'loadedmetadata'].forEach(ev => v.addEventListener(ev, () => report(true)));
v.addEventListener('ended', () => API()?.ended().catch(() => { }));
window.miniCmd = c => {
  if (c.load) { load(c.load.src, c.load.t || 0, true); document.title = c.load.title || 'Studio 小窗'; }
  if (c.toggle) v.paused ? v.play().catch(() => { }) : v.pause();
  if (c.seek != null) v.currentTime = c.seek;
  if (c.seekBy) v.currentTime = Math.min((v.duration || 1e9) - .05, Math.max(0, v.currentTime + c.seekBy));
  if (c.play) v.play().catch(() => { });
  if (c.pause) v.pause();
  if (c.vol != null) v.volume = c.vol;
  if (c.rate) { rate = c.rate; v.playbackRate = rate; }
};
const done = mode => { if (mode === 'close') v.pause(); API()?.done({ ...state(), mode }).catch(() => { }); };

/* 拖动窗口 / 拖四个角改大小：每一帧最多挪一次 */
let pend = null, raf = 0;
const flush = () => { raf = 0; const p = pend; pend = null; if (!p) return; p.move ? API()?.move(p.x, p.y) : API()?.resize(p.w, p.h, p.c); };
const queue = p => { pend = p; if (!raf) raf = requestAnimationFrame(flush); };
let dg = null, rz = null;
const ar = () => (v.videoWidth && v.videoHeight ? Math.min(2.4, Math.max(.5, v.videoWidth / v.videoHeight)) : S0.ar || 16 / 9);
MiniUI.bind(root, v, {
  cmd: name => {
    if (name === 'pin') { pin = !pin; paintPin(); API()?.pin(pin); }
    else if (name === 'back' || name === 'dbl') done('back');
    else if (name === 'x') done('close');
  },
  drag: (ph, e) => {  // 按住拖动超过几个像素：交给系统拖动窗口（单击、双击不受影响）
    if (ph === 'start') dg = { x: e.clientX, y: e.clientY };
    else if (ph === 'move' && dg && Math.hypot(e.clientX - dg.x, e.clientY - dg.y) > 4) { dg = null; API()?.start_drag(); }
    else if (ph !== 'move') dg = null;
  },
  resize: (c, ph, e) => {
    if (ph === 'start') { rz = { w: innerWidth, sx: e.screenX, sy: e.screenY, ar: ar() }; return; }
    if (!rz) return;
    if (ph === 'end') { rz = null; return; }
    const dx = (e.screenX - rz.sx) * (c.includes('w') ? -1 : 1), dy = (e.screenY - rz.sy) * (c.includes('n') ? -1 : 1);
    const dw = Math.abs(dx) > Math.abs(dy * rz.ar) ? dx : dy * rz.ar;
    const w = Math.round(Math.min(screen.availWidth * .95, (screen.availHeight * .95 - BAR) * rz.ar, Math.max(rz.ar >= 1 ? 240 : 170, rz.w + dw)));
    queue({ w, h: Math.round(w / rz.ar + BAR), c });
  },
});
/* 视频比例和打开时估计的不一样：把窗口高度调成刚好 */
v.addEventListener('loadedmetadata', () => {
  const a = ar(); root.style.setProperty('--ar', a);
  const L = Math.max(innerWidth, innerHeight - BAR);  // 保持画面长边不变（横屏换竖屏也一样大）
  let w = a >= 1 ? L : L * a; w = Math.min(w, (screen.availHeight * .9 - BAR) * a);
  w = Math.round(Math.max(a >= 1 ? 240 : 170, w)); const h = Math.round(w / a + BAR);
  if (Math.abs(w - innerWidth) > 2 || Math.abs(h - innerHeight) > 2) API()?.resize(w, h, 'se');  // 左上角不动
});
document.addEventListener('keydown', e => {
  if (e.target.closest?.('button')) return;  // 2026-11-17 UI 审查 U07：焦点在按钮上（比如置顶）时空格 / 方向键交给按钮，只做按钮自己的事
  if (e.key === ' ') { e.preventDefault(); if (!e.repeat) v.paused ? v.play().catch(() => { }) : v.pause(); }
  else if (e.key === 'ArrowLeft') v.currentTime = Math.max(0, v.currentTime - 5);
  else if (e.key === 'ArrowRight') v.currentTime = Math.min((v.duration || 1e9) - .05, v.currentTime + 5);
});
document.addEventListener('contextmenu', e => e.preventDefault());
paintPin();
document.title = S0.title || 'Studio 小窗';
if (S0.src) load(S0.src, S0.t || 0, false);
/* 开始播放由 app.py 在页面加载完后调用：新窗口自己调 play() 会被浏览器的“自动播放”限制挡掉（没有点过这个窗口） */
window.miniStart = () => { if (S0.src && !S0.paused) v.play().catch(e => { window._perr = e.name + ': ' + e.message; }); };
