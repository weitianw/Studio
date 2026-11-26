/* 模型页（2026-11-26 开源泛化 ⑤）：这台电脑的显卡和内存；每类模型（生图 / AI 助手 / 生视频 / 配音）的文件在不在、多大、放不放得下；
   自己加模型（选类型、从文件夹里选文件）、藏起不用的、删掉自己加的。后台 /api/catalog（modelsinfo.py）。
   排版沿用设置页的分区和行（st-sec / st-row），说明放在悬停提示里 */
'use strict';
const MD_KIND = [['image', '生图'], ['llm', 'AI 助手'], ['video', '生视频'], ['tts', '配音 · 换声 · 识别']];
const MD_FIT = {
  ok: ['放得下', '整个模型能放进显存'],
  tight: ['偏紧', '显存放不下全部，运行时会把一部分放在内存里，速度较慢'],
  no: ['放不下', '这台电脑的显存和内存都不够运行这个模型'],
};
const MD_TASK = { tts: '配音', vc: '换声', asr: '识别', clon: '配音', vdes: '配音' };
let MD = null;

async function renderModels() {
  const main = $('#main');
  main.innerHTML = `<div class="page-head"><div><h1 class="page-title">模型</h1></div></div><div class="st-wrap md-wrap"><div class="md-wait tiny">正在读取…</div></div>`;
  try { MD = await api('/api/catalog'); } catch (e) { const w = $('.md-wrap', main); if (w) w.innerHTML = `<div class="md-wait tiny">${esc(e.message)}</div>`; return; }
  if ($('#main')?.dataset.page === 'models' || $('#main .md-wrap')) mdPaint();
}

function mdRow(kind, x) {
  const fit = x.have ? MD_FIT[x.fit] : ['缺少文件', (x.missing || []).filter(Boolean).join('\n')];
  const sub = [x.family_name || (kind === 'tts' ? (MD_TASK[x.task] || '') : ''), x.source === 'user' ? '自己添加' : String(x.source || '').startsWith('pack:') ? '功能包' : x.source === 'folder' ? 'models/llm 文件夹' : ''].filter(Boolean).join(' · ');
  const act = x.source === 'user' ? `<button type="button" class="btn small ghost" data-del="${esc(x.id)}">删除</button>`
    : kind !== 'video' && x.source !== 'folder' ? `<button type="button" class="btn small ghost md-hide" data-hide="${esc(x.id)}">隐藏</button>` : '';
  return `<div class="st-row md-row" data-kind="${kind}"><div class="st-l"><b>${esc(x.name)}</b>${sub ? `<span class="md-sub">${esc(sub)}</span>` : ''}</div>
    <div class="st-r">${x.gb ? `<span class="md-gb">${x.gb} GB</span>` : ''}${fit && fit[0] ? `<span class="md-fit md-${x.have ? x.fit : 'miss'}" data-tip="${esc(fit[1] + (x.need_gb && x.have ? `\n约需 ${x.need_gb} GB` : ''))}">${fit[0]}</span>` : ''}${act}</div></div>`;
}

function mdPaint() {
  const w = $('#main .md-wrap'); if (!w || !MD) return;
  const g = (MD.hardware.gpu || [])[0], r = MD.hardware.ram || {};
  const hw = g ? `${g.name} · 显存 ${Math.round(g.total_gb)} GB · 内存 ${Math.round(r.total_gb || 0)} GB` : `未检测到 NVIDIA 显卡 · 内存 ${Math.round(r.total_gb || 0)} GB`;
  const hidden = MD_KIND.flatMap(([k]) => (MD.user[k] || []).filter(e => e.hidden).map(e => ({ k, id: e.id })));
  w.innerHTML = `<div class="md-hw tiny">${esc(hw)}</div>` + MD_KIND.map(([k, n]) => {
    const rows = MD.kinds[k] || [];
    return `<section class="st-sec md-sec"><div class="row between md-h"><h2 class="st-h">${n}</h2>${k !== 'video' ? `<button type="button" class="btn small" data-add="${k}">添加模型</button>` : ''}</div>
      <div class="card st-card">${rows.length ? rows.map(x => mdRow(k, x)).join('') : '<div class="st-row"><div class="st-l tiny">还没有模型</div></div>'}</div></section>`;
  }).join('') + (hidden.length ? `<details class="md-hid"><summary class="tiny">已隐藏 ${hidden.length} 个模型</summary><div class="card st-card">${hidden.map(x =>
    `<div class="st-row"><div class="st-l">${esc(x.id)}</div><div class="st-r"><button type="button" class="btn small ghost" data-unhide="${esc(x.id)}" data-kind="${x.k}">恢复</button></div></div>`).join('')}</div></details>` : '');
  $$('[data-add]', w).forEach(b => b.onclick = () => mdAdd(b.dataset.add));
  $$('[data-del]', w).forEach(b => b.onclick = () => mdDel(b.closest('[data-kind]').dataset.kind, b.dataset.del, '已删除'));
  $$('[data-unhide]', w).forEach(b => b.onclick = () => mdDel(b.dataset.kind, b.dataset.unhide, '已恢复'));
  $$('[data-hide]', w).forEach(b => b.onclick = async () => {
    try { await api('/api/catalog/user', { body: { kind: b.closest('[data-kind]').dataset.kind, entry: { id: b.dataset.hide, hidden: true } } }); toast('已隐藏'); renderModels(); } catch (e) { toast(e.message, true); }
  });
}

async function mdDel(kind, id, msg) {
  try { await api(`/api/catalog/user?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}`, { method: 'DELETE' }); toast(msg); renderModels(); } catch (e) { toast(e.message, true); }
}

async function mdAdd(kind) {
  const kn = (MD_KIND.find(x => x[0] === kind) || [, ''])[1];
  const fams = kind === 'image' ? MD.families.image : kind === 'tts' ? MD.families.tts : null;
  const box = modal(`<div class="row between" style="margin-bottom:12px"><h3 class="card-title" style="margin:0">添加${esc(kn)}模型</h3><button type="button" class="btn small" data-close>取消</button></div>
    ${fams ? `<label class="field"><span class="label">类型</span><select class="select" id="md-fam">${fams.map(f => `<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('')}</select></label>` : ''}
    <label class="field"><span class="label">模型文件</span><select class="select" id="md-file"><option value="">正在读取…</option></select></label>
    ${kind === 'tts' ? `<label class="field"><span class="label">用途</span><select class="select" id="md-task"><option value="tts">配音</option><option value="vc">换声</option><option value="asr">识别</option></select></label>` : ''}
    ${kind === 'image' ? `<details class="md-adv"><summary class="tiny">文本编码器和 VAE</summary>
      <label class="field"><span class="label">文本编码器</span><select class="select" id="md-te"><option value="">按类型默认</option></select></label>
      <label class="field"><span class="label">VAE</span><select class="select" id="md-vae"><option value="">按类型默认</option></select></label></details>` : ''}
    <label class="field"><span class="label">名称</span><input class="input" id="md-name" placeholder="默认用文件名" autocomplete="off"></label>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button type="button" class="btn primary" id="md-save" disabled>添加</button></div>`);
  const fam = () => (fams || []).find(f => f.id === $('#md-fam', box)?.value) || {};
  const folder = () => kind === 'image' ? (fam().folder || 'diffusion_models') : 'llm';
  const opts = (L, none) => L.length ? L.map(f => `<option value="${esc(f.file)}">${esc(f.file)}${f.gb ? ` · ${f.gb} GB` : ''}</option>`).join('') : `<option value="">${esc(none)}</option>`;
  const load = async () => {
    const sel = $('#md-file', box); sel.innerHTML = '<option value="">正在读取…</option>';
    try {
      const L = await api('/api/catalog/files?folder=' + folder());
      sel.innerHTML = opts(L, '这个文件夹里还没有模型文件');
      sel.dataset.tip = (kind === 'image' ? 'ComfyUI/models/' : 'models/') + (folder() === 'llm' ? '' : folder());
    } catch (e) { sel.innerHTML = `<option value="">${esc(e.message)}</option>`; }
    $('#md-save', box).disabled = !sel.value;
  };
  if (kind === 'image') {
    const fill = async (id, f) => { try { const L = await api('/api/catalog/files?folder=' + f); $(id, box).insertAdjacentHTML('beforeend', L.map(x => `<option value="${esc(x.file)}">${esc(x.file)}</option>`).join('')); } catch { } };
    fill('#md-te', 'text_encoders'); fill('#md-vae', 'vae');
  }
  const fs = $('#md-fam', box); if (fs) fs.onchange = load;
  $('#md-file', box).onchange = e => { $('#md-save', box).disabled = !e.target.value; };
  load();
  $('#md-save', box).onclick = async () => {
    const f = $('#md-file', box).value, name = $('#md-name', box).value.trim();
    const entry = kind === 'image' ? { family: fam().id, unet: f, name, te: $('#md-te', box).value, vae: $('#md-vae', box).value }
      : kind === 'llm' ? { file: f, name } : { family: fam().id, path: 'models/' + f.replace(/\\/g, '/'), name, task: $('#md-task', box).value };
    $('#md-save', box).disabled = true;
    try { await api('/api/catalog/user', { body: { kind, entry } }); box.close(); toast(kind === 'tts' ? '已添加，配音引擎正在重新载入' : '已添加'); renderModels(); }
    catch (e) { toast(e.message, true); $('#md-save', box).disabled = false; }
  };
}
PAGES.models = renderModels;
