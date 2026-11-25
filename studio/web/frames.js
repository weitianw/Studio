/* ================= 视频截一帧 → 素材库（2026-11-19 用户） =================
   放大看视频的地方（素材库里打开的视频、生视频 / 改视频的成品、详情、改视频的原视频放大）：按 S 截当前这一帧，, . 逐帧；
   截下的图存进素材库，同一个视频的默认归进一个图集（放在成对的图片文件夹里：clips → clips image），视频下面一排蓝色小方块标出截过的位置，
   图片上能“回到视频”停在那一帧。播放页不截（用户：播放页有书签就够了）。
   生图 / 生视频 / AI 助手 / 选素材窗口里的“从视频截取…”打开选帧窗口（逐帧、缩略图条、推荐帧 = 找换装点的动作分析），挑好直接用。
   后台见 studio/frames.py（ffmpeg 从原文件按准确时间取，对齐到帧，PNG）。参考：PotPlayer / mpv / VLC 单键截图、逐帧；DaVinci Resolve 的 Grab Still。 */
const FR_PRIV = ['视频截图/私密空间'];  // 和 server.py 的 MATS_PRIVATE 一样
const frPriv = d => { const r = String(d || '').toLowerCase(); return FR_PRIV.some(p => r === p.toLowerCase() || r.startsWith(p.toLowerCase() + '/')); };
const FR_SV = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const FR_IC = {
  cam: FR_SV('<path d="M4 8h3l2-2.5h6L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>'),
  vid: FR_SV('<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9.5 4.5 2.5-4.5 2.5z"/>'),
  folder: FR_SV('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  prev: FR_SV('<path d="M15 6l-6 6 6 6"/>'), next: FR_SV('<path d="M9 6l6 6-6 6"/>'),
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>',
  stack: FR_SV('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'),
  lock: FR_SV('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
};
window.FR_IC = FR_IC;
const frT = t => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`; };
const frQs = src => src.mats ? 'mats=' + encodeURIComponent(src.mats) : 'gallery=' + encodeURIComponent(src.gallery);
const frKey = src => src.mats ? 'm:' + src.mats : src.gallery ? 'g:' + src.gallery : 'l:' + (src.local || '');
const frSrv = src => !!(src && (src.mats || src.gallery));  // 后台能读到原文件（素材库 / 视频库）；local = 电脑上选的文件，只能在网页里取
const frTol = info => info?.fps > 0 ? 0.5 / info.fps : 0.02;  // 算“同一帧”的范围：半帧（以前固定 0.1 秒，30 fps 时相邻帧也被当成重复，审查 11）
const FR_INFO = new Map();
function frInfo(src, fresh) {
  const k = frKey(src);
  if (!frSrv(src)) return Promise.resolve({ fps: 0, dur: src.dur || 0, items: [], name: src.name || '视频', private: !!VAULT, dest: VAULT ? '视频截图/私密空间' : '视频截图', local: true });
  if (fresh || !FR_INFO.has(k)) { const p = api('/api/frames/info?' + frQs(src)); FR_INFO.set(k, p); p.then(x => { p.v = x; }, () => FR_INFO.delete(k)); }
  return FR_INFO.get(k);
}
const frFolderKey = src => src.mats ? (src.mats.includes('/') ? src.mats.slice(0, src.mats.lastIndexOf('/')) : '/') : src.gallery ? '#gen' + (VAULT ? 'v' : '') : '#local' + (VAULT ? 'v' : '');
const frDestGet = src => (S.ui?.frDest || {})[frFolderKey(src)] || null;
function frDestSet(src, d) { S.ui = { ...(S.ui || {}), frDest: { ...(S.ui?.frDest || {}), [frFolderKey(src)]: d } }; persist(); }
const frFolderName = src => src.mats ? (frFolderKey(src) === '/' ? '素材库根目录' : frFolderKey(src).split('/').pop()) : src.gallery ? '生成的视频' : '电脑上的视频';

/* ---------- 存到哪里 ---------- */
async function frDest(src, info, force) {
  const cur = frDestGet(src);
  if (cur && !force && (!info.private || frPriv(cur.dir))) return cur;
  const r = await frDestDlg(src, info, cur);
  if (!r) return null;
  if (r.remember) frDestSet(src, { dir: r.dir, album: r.album });
  return { dir: r.dir, album: r.album };
}
function frDestDlg(src, info, cur) {
  return new Promise(res => {
    let dir = cur?.dir || info.dest || '视频截图', album = cur ? cur.album !== false : true, done = false;
    const box = modal(`<div class="row gal-head fr-dh"><h3 class="card-title" style="margin:0">截图存到哪里</h3><span class="spacer"></span><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
      <button type="button" class="fr-destb" data-chg>${FR_IC.folder}<b class="fr-dn"></b><span class="fr-dl"></span><span class="fr-chg">更改</span></button>
      <label class="fr-opt"><span>每个视频建一个图集</span><span class="switch"><input type="checkbox" data-al${album ? ' checked' : ''}><span></span></span></label>
      <label class="fr-opt"><span>以后从「${esc(frFolderName(src))}」截图都这样，不再问</span><span class="switch"><input type="checkbox" data-rm checked><span></span></span></label>
      <div class="row fr-dacts"><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary" data-ok>存好</button></div>`, null);
    box.classList.add('fr-dlg');
    const paint = () => { $('.fr-dn', box).textContent = dir; $('.fr-dl', box).textContent = frPriv(dir) ? '私密' : ''; };
    paint();
    const c0 = box.close; box.close = () => { c0(); if (!done) { done = true; res(null); } };
    $$('[data-close]', box).forEach(b => b.onclick = box.close);
    $('[data-chg]', box).onclick = async () => { const d = await frFolderPick(info, dir); if (d) { dir = d; paint(); } };
    $('[data-ok]', box).onclick = () => { done = true; const r = { dir, album: $('[data-al]', box).checked, remember: $('[data-rm]', box).checked }; c0(); res(r); };
  });
}
function frFolderPick(info, cur) {
  return new Promise(async res => {
    let dirs = []; try { dirs = (await api('/api/mats/dirs')).dirs || []; } catch (e) { toast(e.message, true); return res(null); }
    if (cur && !dirs.includes(cur)) dirs = [cur, ...dirs];
    let sel = cur, done = false;
    const box = modal(`<div class="row gal-head"><h3 class="card-title" style="margin:0">选择文件夹</h3><span class="spacer"></span><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
      ${info.private ? '<div class="tiny fr-pn">这是私密的视频：截图只能存进私密文件夹</div>' : ''}<div class="fr-tree"></div>
      <div class="row fr-newr"><input class="input" placeholder="新文件夹的名字" aria-label="新文件夹的名字"><button type="button" class="btn small" data-new>新建到所选文件夹里</button></div>
      <div class="row fr-dacts"><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary" data-ok>选这里</button></div>`, null);
    box.classList.add('fr-dlg', 'fr-fdlg');
    const tree = $('.fr-tree', box);
    const paint = () => {
      tree.innerHTML = `<button type="button" class="fr-ti${sel === '' ? ' on' : ''}" data-d=""${info.private ? ' disabled' : ''}>${FR_IC.folder}<span>素材库</span></button>` + dirs.map(d => {
        const dep = d.split('/').length, off = info.private && !frPriv(d);
        return `<button type="button" class="fr-ti${d === sel ? ' on' : ''}" data-d="${esc(d)}" style="padding-left:${10 + dep * 16}px"${off ? ' disabled' : ''}>${FR_IC.folder}<span>${esc(d.split('/').pop())}</span>${frPriv(d) ? '<em>私密</em>' : ''}</button>`; }).join('');
      $$('[data-d]', tree).forEach(b => b.onclick = () => { sel = b.dataset.d; paint(); });
      tree.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
    };
    paint();
    const c0 = box.close; box.close = () => { c0(); if (!done) { done = true; res(null); } };
    $$('[data-close]', box).forEach(b => b.onclick = box.close);
    $('[data-new]', box).onclick = () => { const n = $('.fr-newr input', box).value.trim().replace(/[\\/:*?"<>|]/g, ''); if (!n) return toast('请输入文件夹的名字', true);
      const d = (sel ? sel + '/' : '') + n; if (info.private && !frPriv(d)) return toast('私密的视频：请先选一个私密文件夹，再在里面新建', true);
      if (!dirs.includes(d)) dirs.splice(sel ? dirs.indexOf(sel) + 1 : 0, 0, d); sel = d; $('.fr-newr input', box).value = ''; paint(); };
    $('[data-ok]', box).onclick = () => { if (sel == null) return toast('请先选一个文件夹', true); if (info.private && !frPriv(sel)) return toast('私密的视频：截图只能存进私密文件夹', true); done = true; c0(); res(sel); };
  });
}

/* ---------- 截一帧 ---------- */
function frLocalShot(v, t) {  // 后台读不到原文件（电脑上选的视频）：在网页里取，原尺寸 PNG
  return new Promise((ok, no) => {
    const draw = el => { try { const c = document.createElement('canvas'); c.width = el.videoWidth; c.height = el.videoHeight; c.getContext('2d').drawImage(el, 0, 0); ok(c.toDataURL('image/png')); } catch (e) { no(new Error('无法读取这一帧')); } };
    if (v && Math.abs(v.currentTime - t) < 0.02 && v.readyState >= 2) return draw(v);
    const el = document.createElement('video'); el.muted = true; el.playsInline = true; el.preload = 'auto'; el.onerror = () => no(new Error('无法读取这一帧'));
    el.onloadeddata = () => { el.onseeked = () => { draw(el); el.removeAttribute('src'); el.load(); }; el.currentTime = t; };
    el.src = v?.currentSrc || v?.src;
  });
}
async function frGrab(src, t, o = {}) {  // 存进素材库：{ rel, t, album, n } / { dup: true, rel }；o.quiet：不弹提示（选帧窗口里）
  let info; try { info = await frInfo(src); } catch (e) { toast(e.message, true); return null; }
  const dest = o.dest || await frDest(src, info); if (!dest) return null;
  let r;
  try {
    if (frSrv(src)) r = await api('/api/frames/grab', { body: { src, t, save: dest, force: !!o.force } });
    else r = await api('/api/frames/save', { body: { data: await frLocalShot(o.video, t), name: (src.name || '视频').replace(/\.[^.]+$/, ''), t, dir: dest.dir, album: dest.album, private: info.private } });
  } catch (e) { toast(e.message, true); return null; }
  frRefresh(src);
  if (r.dup) { if (!o.quiet) toast('这一帧已经截过'); frFlash(src, r.t); return r; }
  if (!o.quiet) frToast(r, src, dest, t, o.video);
  return r;
}
function frToast(r, src, dest, t, video) {
  const tt = document.createElement('div'); tt.className = 'toast act fr-toast';
  const where = (r.album || dest.dir || '').split('/').slice(-2).join(' / ');
  tt.innerHTML = `<img src="${esc(matsUrl(r.rel) + '?thumb=1')}" alt=""><span>已存入 <b>${esc(where)}</b>${r.n ? `（第 ${r.n} 张）` : ''}</span><button type="button" data-u>撤销</button><button type="button" data-m>换位置</button>`;
  const bye = () => { if (tt.classList.contains('out')) return; tt.classList.add('out'); setTimeout(() => { tt.remove(); toastStack(); }, 260); };
  $('[data-u]', tt).onclick = async () => { bye(); if (await frUndo(r.rel, src)) toast('已撤销'); };  // 没撤成（接口报错）就不说已撤销（审查 13）
  $('[data-m]', tt).onclick = async () => { bye(); let info; try { info = await frInfo(src); } catch { return; }
    const d = await frDest(src, info, true); if (!d) return;
    const n = await frGrab(src, t, { dest: d, video, force: true }); if (n && !n.dup && n.rel !== r.rel) await frUndo(r.rel, src); };  // 先存到新位置，存好了再撤掉原来那张（以前先删再截，新位置失败就只能去回收站找，审查 13）
  document.body.appendChild(tt); toastStack(); setTimeout(bye, 5000);
}
async function frUndo(rel, src) { let ok = false; try { await api('/api/frames/undo', { body: { rel } }); ok = true; } catch (e) { toast(e.message, true); } if (src) frRefresh(src); return ok; }
function frRefresh(src) {
  if (src) FR_INFO.delete(frKey(src));
  document.querySelectorAll('video').forEach(v => { if (v._frBar && (!src || frKey(v._frSrc) === frKey(src))) frMarksPaint(v); });
  document.querySelectorAll('.gal-root').forEach(r => r._galRefresh?.());  // 素材库那一页开着：新截的图直接出现
}
function frFlash(src, t) {
  document.querySelectorAll('video').forEach(v => { if (!v._frBar || frKey(v._frSrc) !== frKey(src)) return;
    const m = [...v._frBar.querySelectorAll('.fr-mk')].find(x => Math.abs(+x.dataset.t - t) < 0.15); if (m) { m.classList.remove('flash'); void m.offsetWidth; m.classList.add('flash'); } });
}

/* ---------- 放大看的视频：截图标记（视频下面一排蓝色小方块） ---------- */
function frAttach(v, src) {
  if (!v || !src) return;
  v._frSrc = src; v.dataset.fr = '1';
  if (!frSrv(src)) return;  // 电脑上的视频没有记录：只能截，不标
  const host = v.parentElement; if (!host) return;
  if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
  let bar = v._frBar;
  if (!bar) {
    bar = v._frBar = document.createElement('div'); bar.className = 'fr-marks'; host.append(bar);
    const place = () => { if (!v.isConnected) { ro.disconnect(); bar.remove(); return; } bar.style.left = v.offsetLeft + 'px'; bar.style.width = v.offsetWidth + 'px'; bar.style.top = (v.offsetTop + v.offsetHeight + 3) + 'px'; };
    const ro = new ResizeObserver(place); ro.observe(v); ro.observe(host); place();
    v.addEventListener('loadedmetadata', () => frMarksPaint(v));
    bar.addEventListener('click', e => { const m = e.target.closest('.fr-mk'); if (!m) return; e.stopPropagation(); v.pause(); frOpenImages(v._frSrc, +m.dataset.i); });
    bar.addEventListener('contextmenu', e => { const m = e.target.closest('.fr-mk'); if (!m) return; e.preventDefault(); e.stopPropagation(); const rel = m.dataset.rel, s = v._frSrc;
      ctxMenu(e, [{ label: '打开图片', icon: CTX_IC.open, on: () => { v.pause(); frOpenImages(s, +m.dataset.i); } }, { label: '跳到 ' + frT(+m.dataset.t), on: () => { v.pause(); v.currentTime = +m.dataset.t + 0.001; } },
        { label: '在素材库中显示', icon: FR_IC.folder, on: () => frShowInMats(rel) }, '-', { label: '删除这张截图', icon: CTX_IC.del, danger: true, on: async () => {
          try { await api('/api/mats/delete', { body: { items: [rel] } }); toast('已移到回收站'); } catch (er) { toast(er.message, true); } frRefresh(s); } }]); });
    bar.addEventListener('mouseover', e => { const m = e.target.closest('.fr-mk'); if (!m) return; let hv = bar.querySelector('.fr-hv');
      if (!hv) { hv = document.createElement('div'); hv.className = 'fr-hv'; hv.innerHTML = '<img alt=""><span></span>'; bar.append(hv); }
      $('img', hv).src = matsUrl(m.dataset.rel) + '?thumb=1'; $('span', hv).textContent = '截图 · ' + frT(+m.dataset.t); hv.style.left = m.style.left; hv.hidden = false; });
    bar.addEventListener('mouseout', e => { if (!e.relatedTarget?.closest?.('.fr-mk')) { const hv = bar.querySelector('.fr-hv'); if (hv) hv.hidden = true; } });
  }
  frMarksPaint(v);
}
function frMarksPaint(v) {
  const bar = v._frBar, src = v._frSrc; if (!bar || !src) return;
  frInfo(src).then(info => {
    const d = v.duration || info.dur || 0, L = (info.items || []);
    bar.dataset.n = L.length;
    bar.querySelectorAll('.fr-mk').forEach(x => x.remove());
    if (!d) return;
    bar.insertAdjacentHTML('afterbegin', L.map((x, i) => `<i class="fr-mk" data-i="${i}" data-t="${x.t}" data-rel="${esc(x.rel)}" role="button" aria-label="截图 ${frT(x.t)}" style="left:calc(10px + (100% - 20px) * ${Math.min(1, x.t / d).toFixed(4)})"></i>`).join(''));
  }).catch(() => { });
}
async function frOpenImages(src, k = 0) {
  let info; try { info = await frInfo(src); } catch (e) { return toast(e.message, true); }
  const files = (info.items || []).map(x => ({ rel: x.rel, name: x.rel.split('/').pop(), kind: 'image', ft: x.t, fsrc: src }));
  if (!files.length) return toast('这个视频还没有截图');
  galView(files, Math.min(k, files.length - 1));
}
function frShowInMats(rel) {
  ImageViewer?.close?.(); $$('.modal-bg [data-close]').forEach(b => b.click());
  GAL.lastLib = '文件夹'; GAL.fold = { dir: rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : '', q: '' }; go('mats');
}
/* 图片 → 回到视频里的那一刻：素材库的视频在放大窗口里打开、停在那一帧；生成的视频去生视频页 */
async function frBackToVideo(fsrc, t) {
  if (!fsrc) return;
  if (fsrc.mats) {
    let ok = true; try { ok = (await api('/api/frames/info?' + frQs(fsrc))) && true; } catch { ok = false; }
    if (!ok) return toast('原视频已不在了', true);
    ImageViewer?.close?.();
    const box = galMedia({ rel: fsrc.mats, name: fsrc.mats.split('/').pop(), kind: 'video' }), v = box && $('video', box); if (!v) return;
    const seek = () => { v.pause(); v.currentTime = t + 0.001; };
    v.addEventListener('play', () => v.pause(), { once: true });
    if (v.readyState >= 1) seek(); else v.addEventListener('loadedmetadata', seek, { once: true });
    return;
  }
  if (fsrc.gallery) {
    let x = (typeof vidGal !== 'undefined' ? vidGal : []).find(y => y.id === fsrc.gallery);
    if (!x) { try { const all = await api('/api/video/gallery'); x = all.find(y => y.id === fsrc.gallery); } catch { } }
    if (!x) return toast('原视频已不在了', true);
    ImageViewer?.close?.();
    if (typeof vidView === 'function') { vidView(x, false); const v = $$('.modal-bg .vd-player').pop(); if (v) { const seek = () => { v.pause(); v.currentTime = t + 0.001; }; if (v.readyState >= 1) seek(); else v.addEventListener('loadedmetadata', seek, { once: true }); } }
  }
}

/* ---------- 键盘：S 截图、, . 逐帧（只在放大看的视频上；播放页、输入框里、别的弹窗开着时不管） ---------- */
function frActive() {
  if (document.body.classList.contains('np-open')) return null;
  const tops = [...document.querySelectorAll('.modal-bg')].filter(m => m.offsetParent || getComputedStyle(m).display !== 'none');
  if (tops.length) { const v = tops[tops.length - 1].querySelector('video[data-fr]'); return v && !tops[tops.length - 1].querySelector('.fr-pick') ? v : null; }
  const v = [...document.querySelectorAll('#vd-stage video[data-fr]')].find(x => x.offsetParent);
  return v || null;
}
document.addEventListener('keydown', e => {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key; if (k !== 's' && k !== 'S' && k !== ',' && k !== '.') return;
  if (e.target.closest?.('input, textarea, select, [contenteditable]') || document.querySelector('.fr-pick')) return;
  const v = frActive(); if (!v) return;
  e.preventDefault();
  if (k === ',' || k === '.') { v.pause(); const fps = FR_INFO.get(frKey(v._frSrc))?.v?.fps || 30; v.currentTime = Math.max(0, Math.min((v.duration || 1e9) - 0.01, v.currentTime + (k === '.' ? 1 : -1) / fps)); return; }
  if (e.repeat) return;
  frGrab(v._frSrc, v.currentTime, { video: v });
});
function frShotBtn(v) {  // 放大窗口里的“截取这一帧”按钮
  const b = document.createElement('button'); b.type = 'button'; b.className = 'btn small fr-shotb'; b.innerHTML = `${FR_IC.cam}<span>截取这一帧</span>`; b.dataset.tip = '截取当前画面，存进素材库（S；, . 逐帧）';
  b.onclick = () => frGrab(v._frSrc, v.currentTime, { video: v }); return b;
}

/* ---------- 选帧窗口 ---------- */
async function frVidUrl(src) {
  if (src.mats) return matsUrl(src.mats) + '?scrub=1';
  if (src.local) return src.local;
  let x = (typeof vidGal !== 'undefined' ? vidGal : []).find(y => y.id === src.gallery);
  if (!x) { try { x = (await api('/api/video/gallery')).find(y => y.id === src.gallery); } catch { } }
  return x && typeof vidPlay === 'function' ? vidPlay(x.file) : '';
}
/* o：title、primary 主按钮的字、mode 'use'（拿去用：截到的先放这里，主按钮交出去）/ 'save'（每截一张就存进素材库）、multi 能截几张、
   max 最多几张、onDone(files: File[])、change 有“换一个视频”、again 换视频时怎么重新打开 */
async function framePick(src, o = {}) {
  let info; try { info = await frInfo(src, true); } catch (e) { return toast(e.message, true); }
  const url = await frVidUrl(src); if (!url) return toast('找不到这个视频', true);
  const save = o.mode === 'save', max = o.multi ? (o.max || 12) : 1;
  let fps = info.fps || 30, dur = info.dur || 0, keep = save || !!(S.ui?.frKeep), dest = frDestGet(src), recs = [], closed = false;
  const tray = [];  // { t, url, rel }
  const box = modal(`<div class="row gal-head fr-head">${FR_IC.cam}<h3 class="card-title">从视频截取<span class="fr-vn">${esc(info.name || src.name || '')}</span></h3>${o.change ? '<button type="button" class="btn small" data-chg>换一个视频</button>' : ''}<span class="spacer"></span><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="fr-body"><div class="fr-l">
      <div class="fr-vw"><video src="${esc(url)}" muted playsinline preload="auto"></video></div>
      <div class="row fr-ctl"><button type="button" class="pl-ib fr-pp" aria-label="播放">${FR_IC.play}</button><span class="fr-tm">0:00.0</span>
        <div class="fr-track" role="slider" aria-label="播放位置" tabindex="0"><div class="fr-rail"></div><div class="fr-fill"></div><div class="fr-mks"></div><div class="fr-hv" hidden><img alt=""><span></span></div></div><span class="fr-du">${frT(dur)}</span></div>
      <div class="row fr-ctl2"><button type="button" class="btn small fr-ic" data-st="-1" data-tip="上一帧（,）" aria-label="上一帧">${FR_IC.prev}</button><button type="button" class="btn small fr-ic" data-st="1" data-tip="下一帧（.）" aria-label="下一帧">${FR_IC.next}</button>
        <button type="button" class="btn small" data-sk="-1">−1 秒</button><button type="button" class="btn small" data-sk="1">+1 秒</button><span class="fr-rst tiny"></span><span class="spacer"></span>
        <button type="button" class="btn primary fr-shot">${FR_IC.cam}<span>截这一帧</span><kbd>S</kbd></button></div>
      <div class="fr-strip"></div></div>
      <div class="fr-r"><div class="fr-rh">${save ? '这次截的（已存进素材库）' : '这次截的'}<span class="fr-n"></span></div><div class="fr-tray"></div>
        ${save ? '' : `<label class="fr-opt fr-kp"><span>同时存进素材库</span><span class="switch"><input type="checkbox" data-kp${keep ? ' checked' : ''}><span></span></span></label>`}
        <button type="button" class="fr-destb fr-dsm" data-dest>${FR_IC.folder}<b class="fr-dn"></b><span class="fr-chg">更改</span></button>
        <div class="fr-acts"><button type="button" class="btn primary fr-go">${esc(o.primary || (save ? '完成' : '用这一帧'))}</button></div></div></div>`, null, true);
  box.classList.add('fr-pick');
  const v = $('video', box), track = $('.fr-track', box), fill = $('.fr-fill', box), mks = $('.fr-mks', box), hv = $('.fr-hv', box), tm = $('.fr-tm', box), pp = $('.fr-pp', box);
  v.addEventListener('loadedmetadata', () => { if (!dur) { dur = v.duration || 0; $('.fr-du', box).textContent = frT(dur); paintMarks(); paintStrip(); } });
  const pct = t => dur ? Math.min(1, Math.max(0, t / dur)) * 100 : 0;
  const paintT = () => { tm.textContent = frT(v.currentTime); fill.style.width = pct(v.currentTime) + '%'; pp.innerHTML = v.paused ? FR_IC.play : FR_IC.pause; pp.setAttribute('aria-label', v.paused ? '播放' : '暂停'); };
  ['timeupdate', 'seeked', 'play', 'pause'].forEach(ev => v.addEventListener(ev, paintT));
  const raf = () => { if (closed) return; if (!v.paused) paintT(); requestAnimationFrame(raf); }; raf();
  const seek = t => { v.currentTime = Math.max(0, Math.min((dur || v.duration || 0) - 0.01, t)); };
  const step = d => { v.pause(); seek(v.currentTime + d / fps); };
  pp.onclick = () => v.paused ? v.play().catch(() => { }) : v.pause();
  $$('[data-st]', box).forEach(b => b.onclick = () => step(+b.dataset.st));
  $$('[data-sk]', box).forEach(b => b.onclick = () => { v.pause(); seek(v.currentTime + +b.dataset.sk); });
  // 进度条：拖动 / 点一下跳过去；悬停出小图
  const tAt = e => { const r = track.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (dur || 0); };
  track.addEventListener('pointerdown', e => { if (e.target.closest('.fr-mk')) return; e.preventDefault(); v.pause(); track.setPointerCapture(e.pointerId); seek(tAt(e));
    const mv = ev => seek(tAt(ev)), up = () => { track.removeEventListener('pointermove', mv); track.removeEventListener('pointerup', up); }; track.addEventListener('pointermove', mv); track.addEventListener('pointerup', up); });
  track.addEventListener('mousemove', e => { if (!frSrv(src) || !dur) return; const t = Math.round(tAt(e) * 2) / 2, m = e.target.closest('.fr-mk');
    hv.hidden = false; hv.style.left = pct(m ? +m.dataset.t : t) + '%'; $('img', hv).src = m?.dataset.rel ? matsUrl(m.dataset.rel) + '?thumb=1' : `/api/frames/thumb?${frQs(src)}&t=${t.toFixed(1)}`; $('span', hv).textContent = (m?.dataset.why ? m.dataset.why + ' · ' : m?.dataset.rel ? '截过 · ' : '') + frT(m ? +m.dataset.t : t); });
  track.addEventListener('mouseleave', () => { hv.hidden = true; });
  track.addEventListener('keydown', e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); v.pause(); seek(v.currentTime + (e.key === 'ArrowRight' ? 1 : -1)); } });
  mks.addEventListener('click', e => { const m = e.target.closest('.fr-mk'); if (m) { v.pause(); seek(+m.dataset.t + 0.001); } });
  const paintMarks = () => {
    mks.innerHTML = (info.items || []).map(x => `<i class="fr-mk" data-t="${x.t}" data-rel="${esc(x.rel)}" style="left:${pct(x.t)}%"></i>`).join('')
      + recs.map(p => `<i class="fr-mk rec" data-t="${p.t}" data-why="${esc(p.why)}" style="left:${pct(p.t)}%"></i>`).join(''); };
  const paintStrip = () => {
    const s = $('.fr-strip', box); if (!dur) return;
    const n = Math.max(6, Math.min(40, Math.ceil(dur))), w = dur / n;
    const ts = Array.from({ length: n }, (_, i) => Math.min(dur - 0.05, w * (i + 0.5)));
    s.innerHTML = ts.map(t => { const r = recs.find(p => Math.abs(p.t - t) <= w / 2);
      return `<button type="button" class="fr-th${r ? ' rec' : ''}" data-t="${r ? r.t : t}" aria-label="${frT(t)}" title="${r ? esc(r.why) + ' · ' : ''}${frT(r ? r.t : t)}">${frSrv(src) ? `<img loading="lazy" decoding="async" src="/api/frames/thumb?${frQs(src)}&t=${(r ? r.t : t).toFixed(1)}" alt="">` : `<span>${frT(t)}</span>`}${r ? `<em>${esc(r.tag)}</em>` : ''}</button>`; }).join('');
    $$('.fr-th', s).forEach(b => b.onclick = () => { v.pause(); seek(+b.dataset.t + 0.001); });
  };
  // 推荐帧：找换装点的动作分析（只用 CPU，按视频内容缓存）；打开就在后台找（2026-11-19 用户：自动）
  const rst = $('.fr-rst', box);
  if (frSrv(src)) { rst.textContent = '正在找推荐帧…';
    api('/api/video/cutpoints', { body: { video: src.mats ? { mats: src.mats } : { gallery: src.gallery }, bg: true } }).then(r => {
      if (closed) return; const TAG = { hit: '定格', swing: '大动作', turn: '转身' };
      recs = (r.points || []).filter(p => TAG[p.kind]).sort((a, b) => b.score - a.score).slice(0, 12).sort((a, b) => a.t - b.t).map(p => ({ t: p.t, tag: TAG[p.kind], why: TAG[p.kind] + ((p.why || [])[0] && (p.why || [])[0] !== TAG[p.kind] ? '：' + p.why[0] : '') }));
      rst.textContent = recs.length ? `推荐帧 ${recs.length} 个` : '没有找到推荐帧'; paintMarks(); paintStrip();
    }).catch(() => { if (!closed) rst.textContent = ''; }); }
  // 这次截的
  const paintTray = () => {
    const t = $('.fr-tray', box);
    t.innerHTML = tray.length ? tray.map((x, i) => `<div class="fr-ti2"><img src="${esc(x.rel ? matsUrl(x.rel) + '?thumb=1' : x.url)}" alt=""><span>${frT(x.t)}</span><button type="button" class="fr-x" data-x="${i}" aria-label="去掉">${ICON.x}</button></div>`).join('')
      : `<div class="fr-empty tiny">${MOB() ? '点「截这一帧」' : '按 S 或「截这一帧」'}${max > 1 ? `（最多 ${max} 张）` : ''}</div>`;
    $('.fr-n', box).textContent = tray.length ? `（${tray.length}）` : '';
    $$('[data-x]', t).forEach(b => b.onclick = async () => { const [x] = tray.splice(+b.dataset.x, 1); if (save && x?.rel && !x.dup) await frUndo(x.rel, src); paintTray(); });  // 以前截过的（dup）只从这里拿掉，不删素材库里的原图（审查 1）
    $$('.fr-ti2 img', t).forEach((im, i) => im.onclick = () => { v.pause(); seek(tray[i].t + 0.001); });
    $('.fr-go', box).disabled = !save && !tray.length;
  };
  const paintDest = () => { const b = $('[data-dest]', box); b.hidden = !keep; $('.fr-dn', box).textContent = dest ? dest.dir + (dest.album ? ' / 视频名' : '') : (info.dest || '视频截图') + ' / 视频名'; };
  const kp = $('[data-kp]', box); if (kp) kp.onchange = () => { keep = kp.checked; S.ui = { ...(S.ui || {}), frKeep: keep }; persist(); paintDest(); };
  $('[data-dest]', box).onclick = async () => { const d = await frDest(src, info, true); if (d) { dest = d; paintDest(); } };
  const shot = async () => {
    const t = v.currentTime; v.pause();
    if (tray.some(x => Math.abs(x.t - t) < frTol(info))) return toast('这一帧已经截过');
    if (tray.length >= max) { if (max === 1) tray.length = 0; else return toast(`最多 ${max} 张`, true); }
    const btn = $('.fr-shot', box); btn.disabled = true;
    try {
      if (save) { const r = await frGrab(src, t, { quiet: true, video: v, dest: dest || undefined }); if (r) { if (!dest) dest = frDestGet(src) || dest; tray.push({ t: r.t, rel: r.rel, dup: !!r.dup }); info = await frInfo(src, true); paintMarks(); } }
      else if (frSrv(src)) { const r = await api('/api/frames/grab', { body: { src, t } }); tray.push({ t: r.t, url: r.url, name: r.name }); }
      else tray.push({ t, url: await frLocalShot(v, t), name: `${(src.name || '视频').replace(/\.[^.]+$/, '')}_${t.toFixed(2)}s.png` });
    } catch (e) { toast(e.message, true); }
    btn.disabled = false; paintTray(); paintDest();
  };
  $('.fr-shot', box).onclick = shot;
  const onKey = e => {
    if (!box.isConnected) return document.removeEventListener('keydown', onKey, true);
    if ((box.contains(e.target) && e.target.closest?.('input, textarea')) || e.ctrlKey || e.metaKey || e.altKey) return;  // 焦点可能还留在上一个窗口（选视频）的搜索框里：只管这个窗口自己的输入框
    if (e.key === 's' || e.key === 'S') { e.preventDefault(); e.stopPropagation(); if (!e.repeat) shot(); }
    else if (e.key === ',' || e.key === '.') { e.preventDefault(); e.stopPropagation(); step(e.key === '.' ? 1 : -1); }
    else if (e.key === ' ' && e.target === document.body) { e.preventDefault(); pp.click(); }
  };
  document.addEventListener('keydown', onKey, true);
  requestAnimationFrame(() => { if (document.activeElement && !box.contains(document.activeElement)) document.activeElement.blur?.(); });
  const c0 = box.close; box.close = () => { closed = true; v.pause(); document.removeEventListener('keydown', onKey, true); c0(); };
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
  if ($('[data-chg]', box)) $('[data-chg]', box).onclick = () => { box.close(); o.again?.(); };
  $('.fr-go', box).onclick = async () => {
    if (save) { box.close(); return o.onDone?.([]); }
    if (!tray.length) return;
    const go = $('.fr-go', box); go.disabled = true;
    try {
      if (keep) { const d = dest || await frDest(src, info); if (!d) { go.disabled = false; return; } dest = d;
        var saved = 0; for (const x of tray) { if (await frGrab(src, x.t, { quiet: true, dest: d, video: v })) saved++; } }
      const files = await Promise.all(tray.map(async x => { const r = await fetch(x.url); if (!r.ok) throw new Error('无法读取截下的图'); const b = await r.blob(); return new File([b], x.name || `截图_${x.t.toFixed(2)}s.png`, { type: b.type || 'image/png' }); }));
      box.close(); o.onDone?.(files);
      const one = files.length > 1 ? ' ' + files.length + ' 张' : '一帧';  // 存没存进素材库照实说（第二轮审查 7：以前存失败也说“也存进了素材库”）
      if (keep) toast(saved === tray.length ? `已用这${one}，也存进了素材库` : saved ? `已用这${one}，其中 ${saved} 张存进了素材库` : `已用这${one}，没能存进素材库`, saved < tray.length);
    } catch (e) { go.disabled = false; toast(e.message, true); }
  };
  paintTray(); paintDest(); paintMarks(); paintStrip(); paintT();
  return box;
}
/* 先选视频（素材库的视频；右上角“从视频库选择”= 生成的视频），再打开选帧窗口 */
function frFromVideo(o = {}) {
  const open = src => framePick(src, { ...o, change: true, again: () => frFromVideo(o) });
  galPick(f => f && open({ mats: f.rel, name: f.name }), { kind: 'video', title: '选一个视频来截取画面', alt: [{ label: '从视频库选择', icon: FR_IC.vid, on: () => frPickGen(open) }] });
}
async function frPickGen(cb) {
  let list = typeof vidGal !== 'undefined' && vidGal.length ? vidGal : await api('/api/video/gallery').catch(() => []);
  list = (list || []).slice(0, 200); if (!list.length) return toast('视频库中尚无视频', true);
  modal(`<h3 class="card-title" style="margin:0 0 10px">从视频库选择一段</h3><div class="ig-pick">${list.map((x, i) => `<button type="button" class="ig-pick-t ve-pick-t" data-i="${i}" title="${esc(x.prompt || '')}">${x.thumb && typeof vidUrl === 'function' ? `<img loading="lazy" src="${esc(vidUrl(x.thumb))}" alt="">` : ''}</button>`).join('')}</div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>取消</button></div>`, box => {
    $$('.ve-pick-t', box).forEach(b => b.onclick = () => { box.close(); const x = list[+b.dataset.i]; cb({ gallery: x.id, name: (x.prompt || '').slice(0, 30) }); });
  }, true);
}
/* 选图片的菜单里加的一项：“从视频截取…” */
const frUseItem = (primary, onDone, multi) => ({ label: '从视频截取…', icon: FR_IC.cam, on: () => frFromVideo({ primary, onDone, multi }) });
/* 素材库页面右键：视频 → 截取画面… / 查看截图；视频截图的图集 → 打开来源视频 */
function frCardMenu(x) {
  if (x.kind === 'video' && !x.set && !x.dir) return [{ label: '截取画面…', icon: FR_IC.cam, on: () => framePick({ mats: x.rel, name: x.name }, { mode: 'save', primary: '完成' }) },
    ...(x.nframes ? [{ label: `查看截图（${x.nframes} 张）`, icon: FR_IC.stack, on: () => frOpenImages({ mats: x.rel }) }] : [])];
  if (x.set && x.video) return [{ label: '打开来源视频', icon: FR_IC.vid, on: () => frBackToVideo(x.video, 0) }];
  if (x.ft != null && x.fsrc) return [{ label: `回到视频 ${frT(x.ft)}`, icon: FR_IC.vid, on: () => frBackToVideo(x.fsrc, x.ft) }];
  return [];
}
/* 生视频的详情弹窗（vidView）：视频带 data-frg = 视频库 id，出现时接上截图（S 键、标记） */
new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) { if (n.nodeType !== 1) continue;
  const vs = n.matches?.('video[data-frg]') ? [n] : n.querySelectorAll ? n.querySelectorAll('video[data-frg]') : [];
  vs.forEach(v => { if (!v._frSrc) frAttach(v, { gallery: v.dataset.frg }); }); } }).observe(document.body, { childList: true, subtree: true });
