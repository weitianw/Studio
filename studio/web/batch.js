/* 批量（2026-11-14 用户要求）：选一批视频 + 一个配方（一整套设置）→ 后台自己跑完（分段 → 生成 → 质检 → 不过就换种子重做 → 挑最好的 → 拼回原视频 → 推送到手机）。
   后台 batch.py；网页只负责：挑视频（这里一个个加，或在素材库多选后“加入批量”）、选 / 改配方、看记录（每段最终那一版、重做、换一版）。
   两个空间各一份草稿（只在内存里，私密空间的不存到浏览器）。 */
'use strict';
const BT_D = { n: { items: [], rid: 'default', r: null }, v: { items: [], rid: 'default', r: null } };
const btD = () => BT_D[VAULT ? 'v' : 'n'];
let BT_RECIPES = null, BT_PASS = null;
const BT_ST = { wait: '排队', run: '生成中', done: '完成', partial: '不完整', fail: '失败', cancelled: '已停下', running: '进行中' };
const btFmt = s => (Math.round(s * 100) / 100).toFixed(2).replace(/\.?0+$/, '');
const btRecipe = () => { const d = btD(); return d.r || (BT_RECIPES || []).find(x => x.id === d.rid) || (BT_RECIPES || [])[0]; };
const btViggle = r => !!r.viggle;

/* 素材库多选后“加入批量”（gallery.js）：[{rel, name}] */
window.batchAdd = list => { const d = btD(); let n = 0;
  (list || []).forEach(f => { if (!d.items.some(x => x.rel === f.rel)) { d.items.push({ rel: f.rel, name: f.name || f.rel.split('/').pop(), dur: 0, segs: null, busy: false }); n++; } });
  if ($('#main')?.dataset.page === 'batch') renderBatch(); else go('batch');
  if (n) toast(`已加入 ${n} 个视频`); };

async function renderBatch() {
  $('#main').innerHTML = `
  <div class="page-head"><div><h1 class="page-title">批量</h1></div></div>
  <div class="grid-tts bt-grid">
    <div class="stack"><div class="card bt-new">
      <div class="field"><div class="row bt-vh"><span class="label" data-tip="${esc('一次放几个视频：每个视频按配方分段、生成、质检，不过就换种子重做，最后拼回原视频。<br>也可以在素材库里点“多选”，选好后点“加入批量”。')}">视频</span><span class="spacer"></span>
          <button type="button" class="btn small ghost" id="bt-clear" hidden>清空</button><button type="button" class="btn small" id="bt-add">${ICON.plus}<span>添加视频</span></button></div>
        <div id="bt-items" class="bt-items"></div></div>
      <div class="field" id="bt-rsf" hidden><span class="label">配方</span><div class="seg full bt-rs" id="bt-rs"></div></div>
      <div id="bt-form"></div>
      <div class="row bt-go"><button type="button" class="btn small" id="bt-save">另存为配方</button><button type="button" class="btn small ghost" id="bt-del" hidden>删除此配方</button><span class="spacer"></span><button class="btn primary" id="bt-start">开始批量</button></div>
    </div></div>
    <div class="side-col"><div class="card"><h3 class="card-title">记录</h3><div id="bt-list" class="bt-list"><div class="shimmer"></div></div></div></div>
  </div>`;
  try { const r = await api('/api/batch/recipes'); BT_RECIPES = r.recipes; BT_PASS = r.pass; } catch (e) { BT_RECIPES = BT_RECIPES || []; toast(e.message, true); }
  if ($('#main')?.dataset.page !== 'batch') return;
  btPaintRecipes(); btPaintItems(); btPaintForm();
  $('#bt-add').onclick = () => matsPick('video', f => { if (f) window.batchAdd([f]); });
  $('#bt-clear').onclick = () => { btD().items = []; btPaintItems(); };
  $('#bt-start').onclick = btStart;
  $('#bt-save').onclick = btSaveRecipe;
  $('#bt-del').onclick = async () => { const r = btRecipe(); if (!r || r.builtin) return;
    try { await api('/api/batch/recipes/' + encodeURIComponent(r.id), { method: 'DELETE' }); BT_RECIPES = BT_RECIPES.filter(x => x.id !== r.id); Object.assign(btD(), { rid: BT_RECIPES[0]?.id, r: null }); btPaintRecipes(); btPaintForm(); btPaintItems(); toast('已删除配方'); } catch (e) { toast(e.message, true); } };
  btList();
}

function btPaintRecipes() {
  const d = btD(), box = $('#bt-rs'); if (!box) return;
  $('#bt-rsf').hidden = (BT_RECIPES || []).length < 2;  // 只有内置的那一套时不显示（改法就在下面选）
  box.innerHTML = (BT_RECIPES || []).map(r => `<button type="button" data-r="${esc(r.id)}" class="${r.id === d.rid ? 'on' : ''}">${esc(r.name)}</button>`).join('');
  $$('[data-r]', box).forEach(b => b.onclick = () => { Object.assign(d, { rid: b.dataset.r, r: null }); btPaintRecipes(); btPaintForm(); btPaintItems(); });
  const r = btRecipe(); $('#bt-del') && ($('#bt-del').hidden = !r || !!r.builtin);
}

/* 配方的设置：改了就是这次用的（不会改掉存着的配方；要留着就“另存为配方”） */
function btPaintForm() {
  const box = $('#bt-form'); if (!box) return; const r = btRecipe(); if (!r) { box.innerHTML = ''; return; }
  const set = (k, v) => { const d = btD(); d.r = { ...btRecipe(), [k]: v }; btPaintForm(); if (k === 'segs') { d.items.forEach(x => { x.segs = null; }); btPaintItems(); } };
  const seg = (id, cur, opts) => `<div class="seg full" id="${id}">${opts.map(([v, n, tip]) => `<button type="button" data-v="${esc(String(v))}" class="${String(cur) === String(v) ? 'on' : ''}"${tip ? ` data-tip="${esc(tip)}"` : ''}>${n}</button>`).join('')}</div>`;
  const sw = (id, on, txt, tip) => `<label class="vd-sw ve-sw"><span data-tip="${esc(tip)}">${txt}</span><span class="switch"><input type="checkbox" id="${id}"${on ? ' checked' : ''}><span></span></span></label>`;
  box.innerHTML = `
    <label class="field"><span class="label">换成什么衣服</span><textarea class="input bt-ins" id="bt-ins" rows="2" placeholder="例如：白色连衣裙">${esc(r.instruction || '')}</textarea></label>
    <div class="bt-two">
      <div class="field"><span class="label" data-tip="${esc('<b>推荐分段</b>：按音乐和动作挑出几段（够多记录后按你自己的选段习惯）。<br><b>整段</b>：整个视频一起做（Viggle 每段最长 14 秒）。')}">分段</span>${seg('bt-segs', r.segs, [['recommend', '推荐分段'], ['whole', '整段']])}</div>
      <div class="field"><span class="label">分辨率</span>${seg('bt-size', r.size, [['480p', '480p'], ['720p', '720p']])}</div>
    </div>
    <div class="field"><span class="label" data-tip="${esc(`质检：脸和原视频的相似度 ≥ ${BT_PASS?.face_sim ?? 0.75}，脸 / 背景亮度差在 ±${BT_PASS?.face_dL ?? 6} 以内，动作差 ≤ ${BT_PASS?.drift ?? 0.06}，没有“人物不见了”等问题。<br>不过就换种子重做；次数用完就留分数最高的那一版。`)}">质检不过时重做</span>${seg('bt-retry', r.retry, [[0, '不重做'], [1, '1 次'], [2, '2 次'], [3, '3 次']])}</div>
    <div class="field ve-sws">${sw('bt-vg', btViggle(r), 'Viggle 重拍', '光照和脸最接近原视频。每段最长 14 秒')}${sw('bt-splice', r.splice !== false, '拼回原视频', '每个视频做完后，把各段的最终版拼回原视频，得到完整的视频')}</div>`;
  $('#bt-ins', box).oninput = e => { const d = btD(); d.r = { ...btRecipe(), instruction: e.target.value }; };
  [['bt-segs', 'segs'], ['bt-size', 'size']].forEach(([id, k]) => $$(`#${id} [data-v]`, box).forEach(b => b.onclick = () => set(k, b.dataset.v)));
  $$('#bt-retry [data-v]', box).forEach(b => b.onclick = () => set('retry', +b.dataset.v));
  $('#bt-vg', box).onchange = e => set('viggle', e.target.checked);
  $('#bt-splice', box).onchange = e => set('splice', e.target.checked);
  btPaintGo();
}

function btPaintItems() {
  const d = btD(), box = $('#bt-items'); if (!box) return; const r = btRecipe() || {};
  $('#bt-clear').hidden = !d.items.length;
  box.innerHTML = d.items.length ? d.items.map((x, i) => `<div class="bt-it" data-i="${i}">
      <img class="bt-th" decoding="async" src="${esc(matsUrl(x.rel) + '?thumb=1')}" alt="">
      <div class="bt-mid"><div class="bt-n" title="${esc(x.name)}">${esc(x.name)}</div>
        <div class="bt-segs">${r.segs === 'whole' ? `<span class="chip">整段${x.dur ? ' · ' + btFmt(x.dur) + ' 秒' : ''}</span>`
          : x.busy ? '<span class="tiny">正在找换装点…</span>' : x.segs ? (x.segs.length ? x.segs.map(([a, b], k) => `<span class="chip bt-sg">${btFmt(a)}–${btFmt(b)} 秒<button type="button" class="bt-sx" data-k="${k}" aria-label="去掉这一段">${ICON.x}</button></span>`).join('') : '<span class="tiny">没有找到合适的段落：整段做</span>')
          : '<span class="tiny">分段会在开始时自动找</span>'}</div></div>
      <button type="button" class="pl-ib" data-rm aria-label="移出这个视频" title="移出">${ICON.x}</button></div>`).join('')
    : '<div class="tiny bt-empty">还没有视频</div>';
  $$('.bt-it', box).forEach(row => { const x = d.items[+row.dataset.i];
    $('[data-rm]', row).onclick = () => { d.items.splice(+row.dataset.i, 1); btPaintItems(); };
    $$('.bt-sx', row).forEach(b => b.onclick = () => { x.segs.splice(+b.dataset.k, 1); btPaintItems(); }); });
  if (r.segs === 'recommend') d.items.forEach(x => { if (!x.segs && !x.busy && !x.fail) btFindSegs(x); });  // 失败过的不再自动重试（以前无限循环请求，2026-11-15 审查）
  btPaintGo();
}

/* 推荐分段：和生视频页“推荐分段”同一套（后台 segpref；记录够了按你自己的习惯） */
async function btFindSegs(x) {
  x.busy = true; const video = { mats: x.rel };
  try {
    const cp = await api('/api/video/cutpoints', { body: { video } });
    x.dur = cp.dur || 0;
    const r = await api('/api/video/cutpoints/split', { body: { video, dur: x.dur } });
    x.segs = r.segs || [];
  } catch { x.segs = null; x.fail = true; }
  x.busy = false; if ($('#main')?.dataset.page === 'batch') btPaintItems();
}

function btPaintGo() {
  const b = $('#bt-start'); if (!b) return; const d = btD(), n = d.items.length;
  b.textContent = n ? `开始批量（${n} 个视频）` : '开始批量'; b.disabled = !n || d.items.some(x => x.busy);
}

async function btStart() {
  const d = btD(), r = btRecipe(); if (!d.items.length || !r) return;
  if (!String(r.instruction || '').trim()) { $('#bt-ins')?.focus(); return toast('请写明要换成什么衣服', true); }
  const b = $('#bt-start'); b.disabled = true;
  try {
    const items = d.items.map(x => ({ video: { mats: x.rel }, label: x.name, dur: x.dur || undefined, segs: r.segs === 'recommend' && x.segs && x.segs.length ? x.segs : undefined }));
    await api('/api/batch', { body: { recipe: d.r ? { ...r } : r.id, items } });
    d.items = []; btPaintItems(); toast('已开始：做完会推送到手机'); btList();
  } catch (e) { toast(e.message, true); }
  btPaintGo();
}

function btSaveRecipe() {
  const r = btRecipe(); if (!r) return;
  modal(`<h3 class="card-title">另存为配方</h3><label class="field"><span class="label">名字</span><input class="input" id="bt-rn" maxlength="40" value="${esc(r.builtin ? r.name + ' · 我的' : r.name)}"></label>
    <div class="row" style="margin-top:12px"><span class="spacer"></span><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary" id="bt-rok">保存</button></div>`, box => {
    const inp = $('#bt-rn', box); inp.focus(); inp.select();
    $('#bt-rok', box).onclick = async () => {
      try { const x = await api('/api/batch/recipes', { body: { recipe: { ...r, id: r.builtin ? '' : r.id, name: inp.value } } });
        BT_RECIPES = [...BT_RECIPES.filter(y => y.id !== x.id), x]; Object.assign(btD(), { rid: x.id, r: null }); box.close(); btPaintRecipes(); btPaintForm(); toast('已保存配方'); } catch (e) { toast(e.message, true); } };
  });
}

/* ---------------- 记录 ---------------- */
function btList() {
  pollStart(async stop => {
    const box = $('#bt-list'); if (!box) return stop();
    let r; try { r = await api('/api/batch'); } catch { return; }
    const sig = JSON.stringify(r.batches.map(b => [b.id, b.updated, b.state]));
    if (box.dataset.sig !== sig) { box.dataset.sig = sig; btPaintList(box, r.batches); }
  }, 5000);
}

function btPaintList(box, list) {
  const open = new Set($$('.bt-b[open]', box).map(x => x.dataset.id));
  box.innerHTML = list.length ? list.map((b, n) => btCard(b, open.has(b.id) || (!open.size && n === 0))).join('') : '<div class="tiny bt-empty rec-empty">暂无记录</div>';
  $$('.bt-b', box).forEach(el => { const b = list.find(x => x.id === el.dataset.id); if (!b) return;
    const act = async (path, body, msg) => { try { await api(`/api/batch/${encodeURIComponent(b.id)}${path}`, { body }); delete box.dataset.sig; btList(); if (msg) toast(msg); } catch (e) { toast(e.message, true); } };
    $('[data-stop]', el) && ($('[data-stop]', el).onclick = e => { e.preventDefault(); act('/cancel', {}, '已停下（已经做好的保留）'); });  // 按钮在标题行（summary）里：不要顺带展开 / 收起
    $('[data-del]', el) && ($('[data-del]', el).onclick = async e => { e.preventDefault(); try { await api('/api/batch/' + encodeURIComponent(b.id), { method: 'DELETE' }); delete box.dataset.sig; btList(); } catch (e) { toast(e.message, true); } });
    $$('[data-redo]', el).forEach(x => x.onclick = () => { const [i, k] = x.dataset.redo.split(':').map(Number); act('/redo', { item: i, seg: k }, '这一段再做一次'); });
    $$('[data-pick]', el).forEach(x => x.onchange = () => { const [i, k] = x.dataset.pick.split(':').map(Number); act('/pick', { item: i, seg: k, try: +x.value }, '已换成这一版，重新拼接'); });
  });
}

// 缺了哪几段（生成失败）：做好的部分已保留，缺的段可以单独重做（2026-11-17 审查 F02）
const miss = it => { const m = (it.segs || []).filter(s => s.state === 'fail'); return m.length && ['partial', 'fail'].includes(it.state) ? `<div class="tiny" style="color:var(--red)">缺 ${m.map(s => `${btFmt(s.a)}–${btFmt(s.b)} 秒`).join('、')}（生成失败，可点该段的“重做”）</div>` : ''; };
function btCard(b, open) {
  const r = b.recipe || {}, segsAll = b.items.flatMap(it => it.segs || []), doneN = segsAll.filter(s => ['done', 'fail', 'cancelled'].includes(s.state)).length;
  const head = `<summary><b>${esc(r.name || '批量')}</b><span class="tiny">${fmtTime(b.created)} · ${b.items.length} 个视频${segsAll.length ? ` · ${doneN}/${segsAll.length} 段` : ''}</span>
    <span class="chip bt-st st-${esc(b.state)}">${BT_ST[b.state] || esc(b.state)}</span>${b.state === 'running' ? '<button type="button" class="btn small ghost" data-stop>停下</button>' : '<button type="button" class="btn small ghost" data-del>删除记录</button>'}</summary>`;
  const items = b.items.map((it, i) => {
    const segs = (it.segs || []).map((s, k) => {
      const best = s.best !== null && s.best !== undefined ? s.tries[s.best] : null, run = s.tries[s.tries.length - 1];
      const m = best?.qc || {}, why = best?.why || [];
      const tip = best ? `${best.ok ? '质检通过' : '质检未通过：' + why.join('；')}<br>脸相似 ${m.face_sim ?? '—'} · 脸亮度差 ${m.face_dL ?? '—'} · 背景 ${m.bg_dL ?? '—'} · 动作差 ${m.drift ?? '—'}<br>共做了 ${s.tries.length} 次` : run?.error ? esc(run.error) : '';
      const opts = s.tries.map((t, n) => t.result ? `<option value="${n}"${n === s.best ? ' selected' : ''}>第 ${n + 1} 次${t.ok ? '（通过）' : t.score !== undefined ? `（${t.score}）` : ''}</option>` : '').join('');
      return `<div class="bt-sr"><div class="row"><span class="bt-dot st-${esc(s.state)}${best && !best.ok ? ' warn' : ''}"></span><span>${btFmt(s.a)}–${btFmt(s.b)} 秒</span>
          <span class="tiny" data-tip="${esc(tip)}">${s.state === 'run' ? '生成中' + (s.tries.length > 1 ? ` · 第 ${s.tries.length} 次` : '') : s.state === 'done' ? (best?.ok ? '通过' : '未通过，用了分数最高的一版') : BT_ST[s.state] || s.state}</span>
          <span class="spacer"></span>${opts && s.tries.filter(t => t.result).length > 1 ? `<select class="input bt-pick" data-pick="${i}:${k}" aria-label="换一版">${opts}</select>` : ''}
          ${['done', 'fail'].includes(s.state) && b.state !== 'cancelled' ? `<button type="button" class="btn small ghost" data-redo="${i}:${k}">重做</button>` : ''}</div>
        ${best?.file ? `<video class="bt-v" src="${esc(vidUrl(best.file))}" muted playsinline controls preload="none"></video>` : ''}</div>`; }).join('');
    const sp = it.splice?.file ? `<div class="bt-sr"><div class="row"><b>拼接结果</b></div><video class="bt-v" src="${esc(vidUrl(it.splice.file))}" muted playsinline controls preload="none"></video></div>`
      : it.splice?.state === 'error' ? `<div class="tiny" style="color:var(--red)">拼接失败：${esc(it.splice.error)}</div>` : '';
    return `<div class="bt-bi"><div class="row bt-bn"><span class="bt-n" title="${esc(it.label)}">${esc(it.label || '视频 ' + (i + 1))}</span><span class="spacer"></span><span class="tiny">${it.state === 'run' && !it.segs ? '正在找换装点…' : ['done', 'partial', 'fail', 'cancelled'].includes(it.state) ? BT_ST[it.state] : ''}</span></div>
      ${it.error ? `<div class="tiny" style="color:var(--red)">${esc(it.error)}</div>` : ''}${miss(it)}${segs}${sp}</div>`; }).join('');
  return `<details class="bt-b" data-id="${esc(b.id)}"${open ? ' open' : ''}>${head}<div class="bt-bd">${b.note ? `<div class="tiny bt-note">${esc(b.note)}</div>` : ''}${items}
    </div></details>`;
}

PAGES.batch = renderBatch;
