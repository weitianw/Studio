/* 修剪视频（2026-11-05 用户要求）：任何视频（成品、拼好的视频、改视频左边的原视频）都能去掉不要的帧或片段，存成一段新视频，原来的不动。
   黄色框选一段（最短一帧）→“删除这段”或“只保留这段”；可以删好几段、随时恢复；播放时自动跳过删掉的部分（就是修剪后的样子）。
   视频库里的视频：有对比用的原视频时一起裁，滑动对比照样对得上。用到 video.js 的 veTrack（选段条）、veFilm（胶片条） */
'use strict';
const vtFromItem = x => ({ id: x.id, url: vidPlay(x.file), name: x.file, dur: +x.duration || x.seconds || 0, fps: +x.fps || 24, w: x.width, h: x.height });
const vtFromSrc = () => VE_VID && ({ id: VE_VID.kind === 'gallery' ? VE_VID.id : null, file: VE_VID.kind === 'upload' ? VE_VID.file : null, url: VE_VID.url, name: VE_VID.name || '原视频', dur: +VE_VID.dur || 0,
  fps: +VE_VID.fps || (VE_VID.kind === 'gallery' ? +vidGal.find(g => g.id === VE_VID.id)?.fps : 0) || 0, w: VE_VID.w, h: VE_VID.h, asSource: true });  // fps 0 = 不知道：打开时自己量
function vtrimOpen(src) {
  if (!src?.url) return toast('没有可修剪的视频', true);
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">修剪视频${src.asSource ? '<span class="tiny" style="margin-left:8px;font-weight:400">改视频的原视频</span>' : ''}</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="vt-v"><video src="${esc(src.url)}" playsinline preload="auto"></video></div>
    <div class="vseg-track vtrim vt-track" tabindex="0" role="slider" aria-label="播放位置"><div class="vtrim-film"></div><div class="vt-cuts"></div><div class="vseg-rng"><span class="vtrim-h a" aria-hidden="true"></span><span class="vtrim-h b" aria-hidden="true"></span></div><div class="vseg-head"></div></div>
    <div class="row vt-ctl"><button type="button" class="btn small vt-play" aria-label="播放">${VID_IC.play}</button>
      <button type="button" class="btn small ghost" data-k="-1" title="后退 1 秒（Shift + ←）">−1 秒</button><button type="button" class="btn small ghost" data-k="-f" title="上一帧（←）">−1 帧</button>
      <button type="button" class="btn small ghost" data-k="f" title="下一帧（→）">+1 帧</button><button type="button" class="btn small ghost" data-k="1" title="前进 1 秒（Shift + →）">+1 秒</button>
      <span class="tiny vt-t"></span><span class="spacer"></span>
      <button type="button" class="btn small ghost" data-set="a" title="把选中范围的开始设到当前画面">设为开始</button><button type="button" class="btn small ghost" data-set="b" title="把选中范围的结束设到当前画面（含这一帧）">设为结束</button></div>
    <div class="row vt-sel"><span class="vt-sel-t"></span><span class="spacer"></span><button type="button" class="btn small" id="vt-del">${VSEG_IC.cut}删除这段</button><button type="button" class="btn small" id="vt-keep">只保留这段</button></div>
    <div class="vt-list"></div>
    <div class="row vt-foot"><span class="tiny vt-sum"></span><span class="spacer"></span><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary" id="vt-save" disabled>保存为新视频</button></div>`, null, true);
  box.classList.add('vt-m');
  const V = $('video', box), tr = $('.vt-track', box), rng = $('.vseg-rng', tr); let F = src.fps || 30; const fr = t => Math.round(t * F) / F;
  vidVolSync(V);
  const fit = () => { if (!box.isConnected) return removeEventListener('resize', fit);  // 窗口装不下时把画面缩小，整个修剪框不用滚动（2026-11-05 全面检查）
    V.style.maxHeight = ''; const over = box.scrollHeight - box.clientHeight; if (over > 0) V.style.maxHeight = Math.max(140, V.getBoundingClientRect().height - over - 2) + 'px'; };
  addEventListener('resize', fit);
  let a = 0, b = 0, cuts = []; const hist = [], redoH = [], rec = () => { hist.push(JSON.stringify(cuts)); if (hist.length > 100) hist.shift(); redoH.length = 0; };
  const D = () => V.duration || src.dur || 0;
  const merged = () => { const c = cuts.map(x => [...x]).sort((p, q) => p[0] - q[0]), m = []; c.forEach(x => { if (m.length && x[0] <= m[m.length - 1][1] + 0.5 / F) m[m.length - 1][1] = Math.max(m[m.length - 1][1], x[1]); else m.push(x); }); return m; };
  const paint = () => {
    const d = D(); if (!d) return;
    rng.style.cssText = `left:${a / d * 100}%;width:${(b - a) / d * 100}%`;
    const m = merged(), left = d - m.reduce((s, x) => s + (x[1] - x[0]), 0);
    $('.vt-cuts', tr).innerHTML = m.map(x => `<i style="left:${x[0] / d * 100}%;width:${(x[1] - x[0]) / d * 100}%"></i>`).join('');
    $('.vt-sel-t', box).innerHTML = `选中 <b>${a.toFixed(2)} – ${b.toFixed(2)} 秒</b>（${Math.round((b - a) * F)} 帧）`;
    $('.vt-list', box).innerHTML = m.length ? m.map((x, i) => `<span class="vt-cut">已删除 ${x[0].toFixed(2)} – ${x[1].toFixed(2)} 秒（${Math.round((x[1] - x[0]) * F)} 帧）<button type="button" class="pl-ib" data-un="${i}" title="恢复这段" aria-label="恢复这段">${ICON.x}</button></span>`).join('') : '';
    $$('[data-un]', box).forEach(x => x.onclick = () => { const r = merged()[+x.dataset.un]; rec(); cuts = cuts.filter(c => c[1] <= r[0] + 1e-6 || c[0] >= r[1] - 1e-6); paint(); fit(); });
    $('.vt-sum', box).textContent = m.length ? `修剪后 ${left.toFixed(2)} 秒（原来 ${d.toFixed(2)} 秒）` : `共 ${d.toFixed(2)} 秒 · ${Math.round(d * F)} 帧`;
    $('#vt-save', box).disabled = !m.length || left < 0.5 / F;
    tm();
  };
  const tm = () => { const t = V.currentTime; $('.vt-t', box).innerHTML = `<b>${t.toFixed(2)}</b> / ${D().toFixed(2)} 秒 · 第 ${Math.round(t * F) + 1} 帧`; };
  const set = (na, nb) => { const d = D(); a = Math.max(0, fr(na)); b = Math.min(d, Math.max(a + 1 / F, fr(nb))); paint(); };
  veTrack(tr, V, D, { onRange: (na, nb) => set(na, nb), getAB: () => [a, b], film: src.url, minLen: 1 / F });
  V.addEventListener('loadedmetadata', () => { const d = D(); a = fr(d * 0.4); b = fr(d * 0.6); paint(); fit(); if (!src.fps) (src.file ? vtFileFps(src.file) : Promise.resolve(0)).then(f => f || vtFps(V)).then(f => { if (!f || !box.isConnected) return; F = f; a = fr(a); b = fr(b); paint(); if (src.asSource && VE_VID?.url === src.url) VE_VID.fps = f; }); });
  V.addEventListener('timeupdate', tm); V.addEventListener('seeked', tm);
  vSmooth(V, () => { if (!box.isConnected) return false; tm(); const t = V.currentTime, c = merged().find(x => t >= x[0] && t < x[1] - 0.01); if (c) V.currentTime = Math.min(D() - 0.001, c[1]); });  // 播放时跳过删掉的部分
  const pb = $('.vt-play', box), pIc = () => { pb.innerHTML = V.paused ? VID_IC.play : VID_IC.pause; };
  V.onplay = V.onpause = V.onended = pIc;
  pb.onclick = () => (V.paused ? V.play().catch(() => { }) : V.pause());
  V.onclick = () => pb.click();
  const step = k => { V.pause(); vSeek(V, Math.max(0, Math.min(D() - 0.001, fr(V.currentTime) + (k === 'f' ? 1 / F : k === '-f' ? -1 / F : +k)))); };
  $$('[data-k]', box).forEach(x => x.onclick = () => step(x.dataset.k));
  $$('[data-set]', box).forEach(x => x.onclick = () => { const t = fr(V.currentTime); x.dataset.set === 'a' ? set(t, Math.max(b, t + 1 / F)) : set(Math.min(a, t), t + 1 / F); });
  $('#vt-del', box).onclick = () => { rec(); cuts.push([a, b]); paint(); fit(); };
  $('#vt-keep', box).onclick = () => { rec(); const d = D(); cuts = []; if (a > 0.5 / F) cuts.push([0, a]); if (d - b > 0.5 / F) cuts.push([b, d]); paint(); fit(); };
  box.addEventListener('keydown', e => { if (e.target.closest?.('input, textarea')) return;
    if ((e.ctrlKey || e.metaKey) && ['z', 'y'].includes(e.key.toLowerCase())) { e.preventDefault(); const re = e.key.toLowerCase() === 'y' || e.shiftKey, from = re ? redoH : hist, to = re ? hist : redoH;  // 撤销 / 重做
      const s = from.pop(); if (s == null) return toast(re ? '没有可重做的' : '没有可撤销的'); to.push(JSON.stringify(cuts)); cuts = JSON.parse(s); paint(); fit(); return; }
    if (e.key === ' ') { e.preventDefault(); pb.click(); } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); step(e.shiftKey ? (e.key === 'ArrowLeft' ? '-1' : '1') : (e.key === 'ArrowLeft' ? '-f' : 'f')); } });
  $('#vt-save', box).onclick = async () => {
    const btn = $('#vt-save', box); btn.disabled = true; btn.textContent = '正在保存…'; V.pause();
    try {
      const body = { cuts: merged(), name: src.name || '' };
      if (src.id) body.id = src.id;
      else { const bl = await fetch(src.url).then(r => r.blob()); body.data = await new Promise((res, rej) => { const fr2 = new FileReader(); fr2.onload = () => res(fr2.result); fr2.onerror = rej; fr2.readAsDataURL(bl); }); }
      const r = await api('/api/video/cut', { body });
      box.close(); toast('已保存为新视频（原来的视频没有改动）');
      await vidGallery();
      const n = vidGal.find(g => g.id === r.id) || r;
      if (src.asSource) { if (await confirmBox('用修剪后的视频作为原视频？', '改视频将使用修剪后的这段视频；修剪前的视频不受影响。', '使用')) vidEditThis(n); }
      else if (typeof vidStage === 'function' && $('#vd-stage')) vidStage(n, true, videoAutoplay());
    } catch (e) { toast('保存失败：' + e.message, true); btn.disabled = false; btn.textContent = '保存为新视频'; }
  };
  setTimeout(() => tr.focus(), 50);
}

/* 电脑上传的 MP4 / MOV：直接从文件头读帧率（视频轨道的时间刻度 ÷ 每帧时长；2026-11-06）。
   不靠播放时数帧（窗口在后台、看不见画面时那种办法测不出来）；读不出来（WebM 等）返回 0，再退回播放时测 */
async function vtFileFps(file) {
  try {
    if (!file?.slice) return 0;
    const rd = async (o, n) => new DataView(await file.slice(o, o + n).arrayBuffer());
    let off = 0, moov = null;
    for (let i = 0; i < 400 && off + 8 <= file.size; i++) {  // 文件最外层：找 moov
      const h = await rd(off, 16); let size = h.getUint32(0); const type = String.fromCharCode(h.getUint8(4), h.getUint8(5), h.getUint8(6), h.getUint8(7));
      if (size === 1) size = Number(h.getBigUint64(8)); else if (size === 0) size = file.size - off;
      if (size < 8) return 0;
      if (type === 'moov') { if (size > 64e6) return 0; moov = await rd(off, size); break; }
      off += size;
    }
    if (!moov) return 0;
    const kids = (dv, s, e) => { const out = []; for (let o = s; o + 8 <= e;) { const z = dv.getUint32(o); if (z < 8 || o + z > e) break; out.push([String.fromCharCode(dv.getUint8(o + 4), dv.getUint8(o + 5), dv.getUint8(o + 6), dv.getUint8(o + 7)), o, z]); o += z; } return out; };
    const find = (dv, s, e, path) => { let cur = [s, e]; for (const t of path) { const k = kids(dv, cur[0], cur[1]).find(x => x[0] === t); if (!k) return null; cur = [k[1] + 8, k[1] + k[2]]; } return cur; };
    for (const [t, o, z] of kids(moov, 8, moov.byteLength)) {
      if (t !== 'trak') continue;
      const hd = find(moov, o + 8, o + z, ['mdia', 'hdlr']); if (!hd) continue;
      const ht = String.fromCharCode(...[0, 1, 2, 3].map(i => moov.getUint8(hd[0] + 8 + i))); if (ht !== 'vide') continue;
      const md = find(moov, o + 8, o + z, ['mdia', 'mdhd']); const st = find(moov, o + 8, o + z, ['mdia', 'minf', 'stbl', 'stts']); if (!md || !st) continue;
      const scale = moov.getUint8(md[0]) === 1 ? moov.getUint32(md[0] + 20) : moov.getUint32(md[0] + 12);
      const n = moov.getUint32(st[0] + 4); let best = [0, 0];
      for (let i = 0; i < Math.min(n, 4096); i++) { const c = moov.getUint32(st[0] + 8 + i * 8), d = moov.getUint32(st[0] + 12 + i * 8); if (c > best[0]) best = [c, d]; }
      if (!scale || !best[1]) return 0;
      const f = scale / best[1], C = [23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 120];
      const c = C.find(x => Math.abs(x - f) / x < 0.003); return c ? (c % 1 ? Math.round(c) : c) : Math.round(f * 100) / 100;
    }
  } catch { }
  return 0;
}
/* 不知道帧率的视频（电脑上传的）：静音播几帧，看相邻两帧差多少时间，换算成帧率（常见的 23.976 / 29.97 归到 24 / 30），然后回到开头 */
function vtFps(V) {
  return new Promise(res => {
    if (!V.requestVideoFrameCallback) return res(0);
    const ts = [], m0 = V.muted, t0 = V.currentTime; let done = false;
    const end = f => { if (done) return; done = true; V.pause(); V.muted = m0; V.currentTime = t0; res(f); };
    const cb = (now, md) => { ts.push(md.mediaTime); if (ts.length >= 10) { const d = ts.slice(1).map((t, i) => t - ts[i]).filter(x => x > 0).sort((p, q) => p - q), m = d[d.length >> 1];
        const f = m ? 1 / m : 0, C = [24, 25, 30, 48, 50, 60, 120]; end(f ? (C.find(c => Math.abs(c - f) / c < 0.03) || Math.round(f)) : 0); } else V.requestVideoFrameCallback(cb); };
    V.muted = true; V.requestVideoFrameCallback(cb); V.play().catch(() => end(0)); setTimeout(() => end(0), 2500);
  });
}
