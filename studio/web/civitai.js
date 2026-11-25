/* Civitai LoRA 浏览：搜索、看示例、一键下载到对的文件夹（触发词、推荐强度一起记下来）。
   civitaiOpen(target, onDone, view)：target = h3 / zimage / krea / q21 / qedit / moss / h3img；下载完成后调 onDone() 刷新 LoRA 列表；view = 'mine' 直接打开“我的下载” */
'use strict';
const CV_T = [['h3', 'MiniMax H3 视频'], ['zimage', 'Z-Image'], ['krea', 'Krea 2'], ['q21', 'Qwen 2.1'], ['qedit', 'Qwen 改图'], ['moss', 'MOSS Image'], ['h3img', 'H3-Image']];
const CV_IC = {
  dl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
};
const CV_TR = new Map();  // 翻译过的：原文 → 中文（关掉商店再打开也不用重新翻）
const cvNum = n => n >= 1e4 ? (n / 1e4).toFixed(n >= 1e5 ? 0 : 1) + ' 万' : String(n || 0);
/* Civitai 的图片地址里能指定大小（2026-11-11 用户：商店往下滑越来越卡）：列表里用宽 450 的小图、视频用静态的第一帧（鼠标停上去才放小视频），
   详情里用宽 900 的，点开大图才用原图（data-full）。原图常是 2MB 的 PNG、视频 5MB，几十张一起解码就卡 */
const CV_SZ = /\/(?:[^/]*(?:original=true|width=\d+)[^/]*)\//;
const cvSized = (u, w) => CV_SZ.test(u) ? u.replace(CV_SZ, `/width=${w}/`) : u;
const cvStill = (u, w) => CV_SZ.test(u) ? u.replace(CV_SZ, `/anim=false,transcode=true,width=${w},optimized=true/`) : '';
const cvMedia = (m, cls = '', thumb = false) => {
  if (!m) return `<span class="cv-nom ${cls}">无预览</span>`;
  const r = '', full = ` data-full="${esc(m.url)}"`;  // 后台只给 PG / PG-13 的示例
  const still = m.type === 'video' && thumb ? cvStill(m.url, 450) : '';
  const el = still ? `<img class="cv-vth ${cls}"${r}${full} src="${esc(still)}" data-vsrc="${esc(cvSized(m.url, 450))}" alt="" loading="lazy" decoding="async">`
    : m.type === 'video' ? `<video class="${cls}"${r}${full} src="${esc(m.url)}" muted loop playsinline preload="metadata"></video>`
    : `<img class="${cls}"${r}${full} src="${esc(cvSized(m.url, thumb ? 450 : 900))}" alt="" loading="lazy" decoding="async">`;
  return el;
};
function cvHoverVid(card, on) {
  const th = card.querySelector('.cv-th'), im = th?.querySelector('img.cv-vth'); if (!im) return;
  let v = th.querySelector('video.cv-hv');
  if (!on) { if (v) { v.pause(); v.removeAttribute('src'); v.load(); v.remove(); } return; }
  if (!v) { v = document.createElement('video'); v.className = 'cv-hv'; v.muted = true; v.loop = true; v.playsInline = true; v.src = im.dataset.vsrc; th.append(v); }
  v.play().catch(() => { });
}
/* 点示例图：弹出完整的一张（列表里是裁成 3:4 的，2026-11-11 用户：想看作者放的完整的图）。← / → 换这一组里的上一张 / 下一张，点任意处或 Esc 关闭 */
function cvZoom(list, i) {
  if (!list.length) return; let k = Math.max(0, i);
  const ov = document.createElement('div'); ov.className = 'cv-zoom'; ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-label', '查看大图');
  const show = () => { const m = list[k]; ov.innerHTML = (m.tagName === 'VIDEO' ? `<video src="${esc(m.src)}" controls autoplay loop playsinline></video>` : `<img src="${esc(m.src)}" alt="">`)
    + (list.length > 1 ? `<span class="cv-zn">${k + 1} / ${list.length}</span>` : '') + `<button type="button" class="cv-zx" aria-label="关闭">${ICON.x}</button>`; const v = ov.querySelector('video'); if (v) v.muted = true; };
  const close = () => { removeEventListener('keydown', key, true); ov.remove(); };
  const key = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && list.length > 1) { e.preventDefault(); e.stopPropagation(); k = (k + (e.key === 'ArrowRight' ? 1 : list.length - 1)) % list.length; show(); } };
  ov.onclick = e => { if (e.target.closest('video')) return; close(); };
  addEventListener('keydown', key, true); show(); document.body.append(ov);
}
// 作者的说明（Civitai 给的是 HTML）：只留排版用的标签，去掉脚本、样式、事件和其他属性；链接在系统浏览器里打开；说明里的图片和示例一样走防窥遮罩
const CV_KEEP = new Set(['P', 'BR', 'UL', 'OL', 'LI', 'STRONG', 'B', 'EM', 'I', 'U', 'S', 'DEL', 'A', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'CODE', 'PRE', 'HR', 'SPAN', 'DIV', 'IMG', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH', 'SUP', 'SUB', 'MARK']);
const CV_DROP = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|NOSCRIPT|TEMPLATE|SVG|MATH|FORM|INPUT|BUTTON|TEXTAREA|SELECT|LINK|META|VIDEO|AUDIO|CANVAS)$/i;
const cvHtml = html => {
  const out = document.createElement('div');
  const walk = (src, dst) => { for (const n of src.childNodes) {
    if (n.nodeType === 3) { dst.append(n.textContent); continue; }
    if (n.nodeType !== 1 || CV_DROP.test(n.tagName)) continue;
    if (!CV_KEEP.has(n.tagName)) { walk(n, dst); continue; }  // 不认识的标签：去掉标签、留下文字
    if (n.tagName === 'IMG') {
      const u = n.getAttribute('src') || ''; if (!/^https:\/\//i.test(u)) continue;
      const w = document.createElement('span'); w.className = 'cv-dimg';
      w.innerHTML = cvMedia({ url: u, type: 'image' }); dst.append(w); continue;
    }
    const e = document.createElement(/^H[1-6]$/.test(n.tagName) ? 'H' + Math.min(6, +n.tagName[1] + 2) : n.tagName);  // 标题降几级，不比模型名还大
    if (n.tagName === 'A') { const u = n.getAttribute('href') || ''; if (/^https?:\/\//i.test(u)) { e.href = u; e.target = '_blank'; e.rel = 'noopener noreferrer'; } }
    walk(n, e); dst.append(e);
  } };
  walk(new DOMParser().parseFromString(String(html || ''), 'text/html').body, out);
  out.querySelectorAll('p, div').forEach(e => { if (!e.textContent.trim() && !e.querySelector('img, br, hr')) e.remove(); });  // 空段落去掉（段距由样式给）
  return out;
};
// 可翻译的段落：最里层的段落 / 列表项 / 标题（里面有图或代码的不翻）
const cvBlocks = root => { const sel = 'p, li, h3, h4, h5, h6, blockquote, td, th, div';
  const l = [...root.querySelectorAll(sel)].filter(e => !e.querySelector(sel) && !e.querySelector('img, pre, code') && /[A-Za-zÀ-￿]{2}/.test(e.textContent));
  return l.length || root.querySelector('img, pre, code') ? l : (/[A-Za-zÀ-￿]{2}/.test(root.textContent) ? [root] : []); };
/* po.pick(file)：选 LoRA 用（2026-11-11 用户：“添加 LoRA”的下拉框只有显示不全的名字）——打开“我的下载”，点一个进详情，点“使用”就加上；po.used：已经加了的文件名 */
function civitaiOpen(target, onDone, view, po = {}) {
  const st = { target: CV_T.some(t => t[0] === target) ? target : 'h3', q: '', sort: 'downloads', items: [], cursor: '', key: true, have: new Set(), busy: false, fit: '', tr: localStorage.getItem('cvTr') === '1',
    view: view === 'mine' ? 'mine' : 'store', mine: [] };
  const box = modal(`<div class="row cv-head"><h3 class="card-title" style="margin:0">${po.pick ? '选择 LoRA' : 'Civitai LoRA'}</h3><div class="seg cv-view" id="cv-view" role="group" aria-label="页面"><button type="button" data-v="store">商店</button><button type="button" data-v="mine">我的下载</button></div><span class="spacer"></span><button type="button" class="btn small ghost" id="cv-tr" title="使用 Google 翻译将名称和说明译为中文（触发词、文件名保持不变）">翻译成中文</button><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="cv-nav" id="cv-nav" hidden></div>
    <div class="cv-bar"><label class="cv-qw"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg><input class="input" id="cv-q" placeholder="搜索 LoRA（英文更准）" aria-label="搜索 LoRA"></label>
      <select class="select cv-tsel" id="cv-t" aria-label="用于哪个模型">${CV_T.map(([k, n]) => `<option value="${k}"${k === st.target ? ' selected' : ''}>${n}</option>`).join('')}</select>
      <select class="select" id="cv-sort"><option value="downloads">下载最多</option><option value="rating">评分最高</option><option value="new">最新</option></select>
</div>
    <div id="cv-key"></div><div id="cv-body" class="cv-body"><div class="shimmer"></div></div><div id="cv-dl" class="cv-dl"></div>`, null, true);
  box.classList.add('cv-modal');
  box.addEventListener('click', e => { const c = e.target.closest('.cv-w .chip.long'); if (c) c.classList.toggle('open'); });  // 很长的“触发词”（有的作者填了一整段提示词）：先显示 3 行，点一下展开
  box.addEventListener('click', e => {  // 详情里的示例图 / 说明里的图：点了弹出完整的大图
    const m = e.target.closest('.cv-mi > img, .cv-mi > video, .cv-dimg > img'); if (!m) return;
    const grp = [...m.closest('.cv-media, .cv-desc').querySelectorAll('.cv-mi > img, .cv-mi > video, .cv-dimg > img')];
    cvZoom(grp.map(x => ({ src: x.dataset.full || x.currentSrc || x.src, tagName: x.classList.contains('cv-vth') ? 'VIDEO' : x.tagName })), grp.indexOf(m));
  });
  const body = $('#cv-body', box);
  const paintKey = () => { $('#cv-key', box).innerHTML = st.key ? '' : `<div class="cv-keyrow"><span class="tiny">部分 LoRA 需要 API 密钥才能下载${window.hintHtml ? hintHtml('在 Civitai 网站 → 头像 → Settings → API Keys 生成密钥，粘贴到右边。只保存在本机。', 'sm') : ''}</span>
      <input class="input" id="cv-k" placeholder="粘贴 API 密钥" autocomplete="off"><button type="button" class="btn small" id="cv-ks">保存</button></div>`;
    const b = $('#cv-ks', box); if (b) b.onclick = async () => { try { await api('/api/civitai/key', { body: { key: $('#cv-k', box).value } }); st.key = true; paintKey(); toast('已保存 Civitai 密钥'); } catch (e) { toast(e.message, true); } }; };
  const load = async more => {
    if (more && st.busy) return; st.busy = true; const seq = st.seq = (st.seq || 0) + 1;  // 换了条件就重新查；旧的那次回来不再画（以前换条件被忽略、旧结果盖掉新的，2026-11-16 审查）
    if (!more) { st.items = []; st.cursor = ''; body.innerHTML = '<div class="shimmer"></div>'; }
    try {
      const [r, have] = await Promise.all([api(`/api/civitai/search?${new URLSearchParams({ q: st.q, target: st.target, sort: st.sort, cursor: more ? st.cursor : '' })}`), more ? null : api('/api/civitai/installed?target=' + st.target).catch(() => [])]);
      if (!box.isConnected || seq !== st.seq || st.view !== 'store') return;
      if (have) st.have = new Set(have);
      const from = st.items.length; st.items.push(...r.items); st.cursor = r.cursor; st.key = r.key; paintKey(); more ? gridAdd(from) : grid();
      if (st.tr) trItems(r.items);
    } catch (e) { if (box.isConnected && seq === st.seq && st.view === 'store') body.innerHTML = loadFail('无法读取 Civitai', e.message); }
    if (seq === st.seq) st.busy = false;
  };
  // 翻译：先翻名字（一次请求，约半秒），再在后台翻说明；网页上只换显示的字，不重画（视频不会重新开始）
  const trOf = t => (st.tr && CV_TR.get(t)) || t;
  const trSpan = t => `<span data-tr="${esc(t)}" data-trt="1"${st.tr && CV_TR.has(t) && CV_TR.get(t) !== t ? ` title="原文：${esc(t)}"` : ''}>${esc(trOf(t))}</span>`;
  const applyTr = () => {
    $$('[data-tr]', box).forEach(e => { const s = e.dataset.tr, t = trOf(s); e.textContent = t; if (e.dataset.trt) e.title = t !== s ? '原文：' + s : ''; });
    $$('.cv-desc', box).forEach(d => (d._blocks || []).forEach(e => {  // 说明里的段落：译文只换文字；回到原文时放回原来的节点（加粗、链接都还在）
      const t = st.tr && CV_TR.get(e._src);
      if (t && t !== e._src) { e._orig = e._orig || [...e.childNodes]; e.textContent = t; }
      else if (e._orig) { e.replaceChildren(...e._orig); e._orig = null; }
    }));
  };
  const trDesc = async () => {  // 只翻正在看的那篇说明，每次 30 段
    const d = $('.cv-desc', body); if (!d?._blocks) return;
    const l = d._blocks.map(e => e._src);
    for (let i = 0; i < l.length; i += 30) { await trFetch(l.slice(i, i + 30)); if (!d.isConnected) return; applyTr(); }
  };
  let trQ = Promise.resolve();
  const trFetch = list => (trQ = trQ.catch(() => { }).then(async () => {
    const need = [...new Set(list.filter(t => t && !CV_TR.has(t)))]; if (!need.length) return;
    const r = await api('/api/civitai/translate', { body: { texts: need } }); need.forEach((t, i) => CV_TR.set(t, r.texts[i] || t));
  }));
  const trItems = async items => {
    try { await trFetch(items.map(x => x.name)); applyTr(); }
    catch (e) { if (box.isConnected && st.tr) { toast(e.message, true); setTr(false); } }
  };
  const trBtn = $('#cv-tr', box);
  const setTr = on => { st.tr = on; localStorage.setItem('cvTr', on ? '1' : '0'); trBtn.textContent = on ? '显示原文' : '翻译成中文'; applyTr(); };
  trBtn.onclick = async () => {
    if (st.tr) return setTr(false);
    trBtn.disabled = true; trBtn.textContent = '翻译中…';
    try { await trFetch([...st.items.map(x => x.name), ...($('.cv-desc', body)?._blocks || []).slice(0, 30).map(e => e._src)]); setTr(true); trItems(st.items); trDesc().catch(() => { }); }
    catch (e) { toast(e.message, true); setTr(false); }
    trBtn.disabled = false;
  };
  if (st.tr) trBtn.textContent = '显示原文';
  const nav = $('#cv-nav', box);
  const usePick = f => { box.close(); po.pick(f); };
  const useBtn = (f, cls = '') => po.used?.has(f) || po.used?.has(loraStem(f)) ? `<span class="tiny cv-ok">${CV_IC.ok}已添加</span>` : `<button type="button" class="btn small primary ${cls}" data-use="${esc(f)}">使用</button>`;
  const navOn = (fn, y = 0, file = '') => { nav.innerHTML = `<button type="button" class="btn small ghost cv-back">${CV_IC.back}返回</button>${po.pick && file ? '<span class="spacer"></span>' + useBtn(file) : ''}`; nav.hidden = false; box.classList.add('cv-det');
    $('.cv-back', nav).onclick = () => { navOff(); fn(); body.scrollTop = y; requestAnimationFrame(() => { body.scrollTop = y; }); };  // 回到进来之前看到的地方（2026-11-11 用户：以前回到最上面）
    $$('[data-use]', nav).forEach(b => b.onclick = () => usePick(b.dataset.use)); body.scrollTop = 0; };
  const navOff = () => { nav.hidden = true; nav.innerHTML = ''; box.classList.remove('cv-det'); };
  const fitOk = () => true;
  const haveOf = x => x.versions.some(v => v.files.some(f => st.have.has(f.name)));
  const cardHtml = (x, i) => { const m = x.versions[0]?.media?.[0];
    return `<button type="button" class="cv-card" data-i="${i}"><div class="cv-th">${cvMedia(m, '', true)}${haveOf(x) ? `<span class="cv-have">${CV_IC.ok}已下载</span>` : ''}</div>
        <div class="cv-n">${trSpan(x.name)}</div><div class="tiny cv-s">${esc(x.creator || '')} · ↓ ${cvNum(x.downloads)}${x.likes ? ' · 赞 ' + cvNum(x.likes) : ''}</div></button>`; };
  const bindCards = cs => cs.forEach(c => { c.onclick = () => detail(st.items[+c.dataset.i], { y: body.scrollTop, keep: [...body.childNodes] });
    c.onmouseenter = () => cvHoverVid(c, true); c.onmouseleave = () => cvHoverVid(c, false); });
  const moreBtn = () => { const old = $('#cv-more', body)?.closest('.row'); if (old) old.remove();
    if (st.cursor) { body.insertAdjacentHTML('beforeend', '<div class="row" style="justify-content:center;margin:12px 0 4px"><button type="button" class="btn small" id="cv-more">加载更多</button></div>'); $('#cv-more', body).onclick = () => load(true); } };
  const gridAdd = from => {  // 加载更多：只把新的接在后面，前面已经加载好的图不动（2026-11-11 用户：以前整页重画，图全部重新加载）
    const g = $('.cv-grid', body); if (!g) return grid();
    const add = st.items.map((x, i) => [x, i]).slice(from).filter(([x]) => fitOk(x));
    g.insertAdjacentHTML('beforeend', add.map(([x, i]) => cardHtml(x, i)).join(''));
    bindCards([...g.querySelectorAll('.cv-card')].slice(-add.length || g.children.length)); moreBtn();
  };
  const grid = () => {
    const show = st.items.map((x, i) => [x, i]).filter(([x]) => fitOk(x));
    body.innerHTML = show.length ? `<div class="cv-grid">${show.map(([x, i]) => cardHtml(x, i)).join('')}</div>
      ${st.cursor ? '<div class="row" style="justify-content:center;margin:12px 0 4px"><button type="button" class="btn small" id="cv-more">加载更多</button></div>' : ''}`
      : `<div class="ig-empty"><b>${st.items.length ? '本页没有可用的' : '没有找到'}</b></div>${st.items.length && st.cursor ? '<div class="row" style="justify-content:center;margin:12px 0 4px"><button type="button" class="btn small" id="cv-more">加载更多</button></div>' : ''}`;
    bindCards($$('.cv-card', body));
    const mb = $('#cv-more', body); if (mb) mb.onclick = () => load(true);
  };
  // 从详情回到列表：把原来那一页原样放回去（图不用重新加载）；只更新“已下载”
  const backTo = (keep, fn) => () => { if (!keep?.length) return fn();
    body.replaceChildren(...keep);
    $$('.cv-card[data-i]', body).forEach(c => { const x = st.items[+c.dataset.i], b = c.querySelector('.cv-have'); if (!x) return; const h = haveOf(x);
      if (h && !b) c.querySelector('.cv-th')?.insertAdjacentHTML('beforeend', `<span class="cv-have">${CV_IC.ok}已下载</span>`); else if (!h && b) b.remove(); }); };
  const detail = (x, o = {}) => {
    const T = o.target || st.target;
    // 示例：只放选中的那个版本自己的一组（和模型页上这个版本的一样）；“模型页”链接带上版本号，打开的就是这个版本
    // （不带版本号时 Civitai 打开最新的版本，常是别的底模，比如同一个模型里的 H3 / LTX 版本，示例自然对不上）
    body.innerHTML = `<div class="cv-d"><div class="cv-left">${x.versions.length > 1 ? `<div class="cv-vsel">${x.versions.map((v, k) => `<button type="button" class="chip${k ? '' : ' on'}" data-sv="${k}">${esc(v.name)}</button>`).join('')}</div>` : ''}<div class="cv-media"></div></div>
        <div class="cv-info"><h3 class="card-title" style="margin:0 0 4px">${trSpan(x.name)}</h3><div class="tiny">${esc(x.creator || '')} · ↓ ${cvNum(x.downloads)} · <a class="cv-page" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">模型页</a>${x.weight ? ` · 推荐强度 ${x.weight}` : ''}</div>
          <div class="cv-vs">${x.versions.map((v, k) => `<div class="cv-v${k ? '' : ' sel'}" data-k="${k}"><div class="row" style="gap:8px"><b>${esc(v.name)}</b><span class="tiny">${esc(v.base)}</span></div>
            ${v.words.length ? `<div class="cv-w">${v.words.slice(0, 12).map(w => `${w.length > 60 ? `<span class="chip long" role="button" tabindex="0" title="点击展开 / 收起"><span class="cw-t">${esc(w)}</span></span>` : `<span class="chip">${esc(w)}</span>`}`).join('')}</div>` : '<div class="tiny">无触发词</div>'}
            ${v.files.map(f => `<div class="row cv-f"><span class="tiny cv-fn" title="${esc(f.name)}">${esc(f.name)}</span><span class="tiny">${f.kb ? Math.round(f.kb / 1024) + ' MB' : ''}</span>${st.have.has(f.name) ? (po.pick ? useBtn(f.name) : `<span class="tiny cv-ok">${CV_IC.ok}已下载</span>`) : `<button type="button" class="btn small" data-v="${k}" data-f="${esc(f.name)}">${CV_IC.dl}下载</button>`}</div>`).join('')}</div>`).join('')}</div>
          <div class="cv-dwrap"><div class="cv-desc"></div><button type="button" class="btn small ghost cv-dmore" hidden>展开全部</button></div></div></div>`;
    navOn(backTo(o.keep, o.back || grid), o.y || 0, o.file || '');
    const pick = k => {  // 换版本：示例、模型页链接、版本卡片的高亮一起换
      const v = x.versions[k]; if (!v) return;
      $$('.cv-vsel .chip', body).forEach(b => b.classList.toggle('on', +b.dataset.sv === k));
      $$('.cv-v', body).forEach(e => e.classList.toggle('sel', +e.dataset.k === k));
      $('.cv-page', body).href = x.url + '?modelVersionId=' + encodeURIComponent(v.id);
      const md = $('.cv-media', body); md.innerHTML = v.media.length ? v.media.map(m => `<div class="cv-mi">${cvMedia(m)}</div>`).join('') : '<div class="cv-mi">' + cvMedia(null) + '</div>';
      $$('video', md).forEach((e, i) => { e.controls = true; if (i < 4) videoPreviewPlay(e); });  // 只自动播前 4 个，其余点了再播
      md.scrollLeft = 0;
    };
    $$('.cv-vsel .chip', body).forEach(b => b.onclick = () => pick(+b.dataset.sv));
    pick(Math.max(0, x.versions.findIndex(v => v.id === o.version)));
    // 说明：作者原来的排版（段落、列表、加粗、链接）；很长时先收起，点“展开全部”看完整的
    const dsc = $('.cv-desc', body), dmore = $('.cv-dmore', body);
    dsc.append(...(x.html ? cvHtml(x.html) : Object.assign(document.createElement('p'), { textContent: x.desc || '' })).childNodes);
    dsc._blocks = cvBlocks(dsc); dsc._blocks.forEach(e => { e._src = e.textContent.replace(/\s+/g, ' ').trim().slice(0, 1600); });
    if (!dsc.textContent.trim() && !dsc.querySelector('img')) dsc.innerHTML = '<p class="tiny">无说明</p>';
    let opened = false;
    const fit = () => { if (!opened && dmore.hidden && dsc.scrollHeight > 340) { dsc.classList.add('clip'); dmore.hidden = false; } };
    fit(); dsc.querySelectorAll('img').forEach(i => i.addEventListener('load', fit, { once: true }));  // 说明里的图加载完会变高
    dmore.onclick = () => { opened = dsc.classList.contains('clip'); dsc.classList.toggle('clip', !opened); dmore.textContent = opened ? '收起' : '展开全部'; if (!opened) dsc.scrollIntoView({ block: 'nearest' }); };
    if (st.tr) { applyTr(); trDesc().catch(() => { }); }
    const get = async (v, f) => { try { await api('/api/civitai/download', { body: { version: v.id, target: T, file: f, model: x.name, weight: x.weight, creator: x.creator } }); toast('开始下载 ' + f); watchDl(); } catch (e) { toast(e.message, true); } };
    $$('[data-v][data-f]', body).forEach(b => b.onclick = () => { b.disabled = true; get(x.versions[+b.dataset.v], b.dataset.f); });
    $$('[data-use]', body).forEach(b => b.onclick = () => usePick(b.dataset.use));
  };
  let dlT = 0;
  const watchDl = async () => {
    clearTimeout(dlT); if (!box.isConnected) return;
    const l = await api('/api/civitai/downloads').catch(() => []); if (!box.isConnected) return;
    if (!watchDl.old) watchDl.old = new Set(l.filter(d => d.state !== 'running').map(d => d.id));
    const now = l.filter(d => d.state === 'running' || !watchDl.old.has(d.id)), run = now.filter(d => d.state === 'running');
    const top = run.length ? run[run.length - 1] : now[now.length - 1], rest = now.filter(d => d !== top);
    $('#cv-dl', box).innerHTML = (top ? [top] : []).map(d => `<div class="cv-dli ${d.state}"><span class="cv-fn" title="${esc(d.name)}">${esc(d.title || d.name)}</span><span class="tiny">${d.state === 'done' ? '完成' : d.state === 'error' ? esc(d.error) : d.total ? Math.round(d.got / d.total * 100) + '%' : Math.round(d.got / 1048576) + ' MB'}</span>${d.state === 'running' && d.total ? `<i style="width:${Math.round(d.got / d.total * 100)}%"></i>` : ''}</div>`).join('');
    if (top && rest.length) $('#cv-dl .cv-dli', box).insertAdjacentHTML('beforeend', `<span class="cv-dlmore" title="${esc(rest.map(d => (d.title || d.name) + '：' + (d.state === 'done' ? '完成' : d.state === 'error' ? '失败' : d.total ? Math.round(d.got / d.total * 100) + '%' : '下载中')).join('\n'))}">+${rest.length}</span>`);
    const doneNow = l.filter(d => d.state === 'done' && !watchDl.seen?.has(d.id)); watchDl.seen = new Set([...(watchDl.seen || []), ...doneNow.map(d => d.id)]);
    if (doneNow.length) { doneNow.forEach(d => st.have.add(d.name)); onDone?.(); if (st.view === 'mine') loadMine(); }
    if (l.some(d => d.state === 'running')) dlT = setTimeout(watchDl, 1000);
  };
  $('#cv-t', box).onchange = e => { st.target = e.target.value; navOff(); st.view === 'mine' ? loadMine() : load(); };
  // ---- 我的下载：这个模型的全部 LoRA
  const MINE_T = t => [t];
  const lbl = r => { const m = r.meta; if (m?.name) return { name: m.name, sub: m.version || '' };
    const L = typeof loraLabel === 'function' ? loraLabel(r.file, null) : null; return { name: L?.name || r.file.replace(/\.(safetensors|gguf)$/i, ''), sub: '' }; };
  const loadMine = async () => {
    body.innerHTML = '<div class="shimmer"></div>';
    try {
      const ts = MINE_T(st.target), ls = await Promise.all(ts.map(t => api('/api/civitai/mine?target=' + t).then(l => l.map(r => ({ ...r, t })))));
      if (!box.isConnected || st.view !== 'mine') return;
      const seen = new Set(); st.mine = ls.flat().filter(r => !seen.has(r.file) && seen.add(r.file)).sort((a, b) => b.mtime - a.mtime);
      st.have = new Set(st.mine.map(r => r.file)); mineGrid();
    } catch (e) { if (box.isConnected) body.innerHTML = loadFail('无法读取本机的 LoRA', e.message); }
  };
  const mineGrid = () => {
    const un = st.mine.filter(r => !r.meta).length;
    body.innerHTML = st.mine.length ? `<div class="row cv-mine-h"><span class="tiny">${CV_T.find(t => t[0] === st.target)?.[1] || ''} · 共 ${st.mine.length} 个${un ? ` · ${un} 个未识别` : ''}</span><span class="spacer"></span>${un ? '<button type="button" class="btn small" id="cv-idall" title="按文件指纹去 Civitai 查出这些 LoRA 是哪个模型（只读文件、不改动文件本身）">全部识别</button>' : ''}</div>
      ${(() => { const card = (r, i) => { const L = lbl(r), m = r.meta;
        return `<button type="button" class="cv-card${r.builtin ? ' cv-bi' : ''}" data-m="${i}"><div class="cv-th">${po.used?.has(r.file) ? `<span class="cv-have">${CV_IC.ok}已添加</span>` : ''}${m?.preview ? cvMedia({ url: m.preview, type: m.preview_type === 'video' ? 'video' : 'image' }, '', true) : `<span class="cv-nom">${m ? '无预览' : '未识别'}</span>`}</div>
          <div class="cv-n">${trSpan(L.name)}</div><div class="tiny cv-s" title="${esc(r.file)}">${esc([L.sub, Math.round(r.size / 1048576) + ' MB'].filter(Boolean).join(' · '))}</div><div class="tiny cv-s cv-file">${esc(r.file)}</div>${r.builtin ? `<div class="tiny cv-role">${esc(r.builtin)}</div>` : ''}</button>`; };
        // 软件自己在用的（默认用的、加速……）收在最下面，默认折叠（2026-11-06 用户要求）
        const own = st.mine.map((r, i) => [r, i]).filter(([r]) => !r.builtin), bi = st.mine.map((r, i) => [r, i]).filter(([r]) => r.builtin), open = !!S.ui?.cvBiOpen;
        return (own.length ? `<div class="cv-grid">${own.map(([r, i]) => card(r, i)).join('')}</div>` : `<div class="tiny cv-mine-none">没有自己下载的 LoRA，下面是软件内置使用的</div>`)
          + (bi.length ? `<button type="button" class="cv-bi-h${open ? ' open' : ''}" id="cv-bi-t" aria-expanded="${open}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg><b>软件内置使用</b><span class="tiny">${bi.length} 个 · 某些功能自动加载或开关控制的，一般不用管</span></button>`
            + `<div class="cv-grid cv-bi-g"${open ? '' : ' hidden'}>${bi.map(([r, i]) => card(r, i)).join('')}</div>` : ''); })()}`
      : `<div class="ig-empty"><b>还没有这个模型的 LoRA</b><span class="tiny">可在“商店”中下载</span></div>`;
    const bh = $('#cv-bi-t', body); if (bh) bh.onclick = () => { const o = !S.ui?.cvBiOpen; S.ui = { ...(S.ui || {}), cvBiOpen: o }; persist();
      bh.classList.toggle('open', o); bh.setAttribute('aria-expanded', String(o)); $('.cv-bi-g', body).hidden = !o; };
    $$('.cv-card', body).forEach(c => { c.onclick = () => mineDetail(st.mine[+c.dataset.m], body.scrollTop, [...body.childNodes]);
      c.onmouseenter = () => cvHoverVid(c, true); c.onmouseleave = () => cvHoverVid(c, false); });  // 视频预览：鼠标停上去才放小视频（和商店一样）
    const ia = $('#cv-idall', body); if (ia) ia.onclick = async () => {
      ia.disabled = true; let ok = 0, n = 0; const L = st.mine.filter(r => !r.meta);
      for (const r of L) { ia.textContent = `识别中 ${++n} / ${L.length}…`; try { await api('/api/civitai/identify', { body: { target: r.t, file: r.file } }); ok++; } catch { } if (!box.isConnected) return; }
      toast(ok ? `已识别 ${ok} 个${ok < L.length ? `，${L.length - ok} 个在 Civitai 上找不到` : ''}` : '这些 LoRA 在 Civitai 上都找不到', !ok); loadMine();
    };
    if (st.tr) trItems(st.mine.map(r => ({ name: lbl(r).name })));
  };
  const mineDetail = async (r, y = 0, keep = null) => {
    if (r.model_id) {  // 有记录：取 Civitai 上这个模型的详情，和商店里看到的一样
      body.innerHTML = '<div class="shimmer"></div>';
      try { const x = await api(`/api/civitai/model?${new URLSearchParams({ id: r.model_id, target: r.t, version: r.version_id || '' })}`); if (!box.isConnected || st.view !== 'mine') return;
        return detail(x, { back: mineGrid, version: r.version_id, target: r.t, y, file: r.file, keep }); }
      catch (e) { toast('无法读取 Civitai 上的详情：' + e.message, true); }
    }
    const L = lbl(r), m = r.meta;
    body.innerHTML = `<div class="cv-one">${m?.preview ? `<div class="cv-media cv-one-m"><div class="cv-mi">${cvMedia({ url: m.preview, type: m.preview_type === 'video' ? 'video' : 'image' })}</div></div>` : ''}<h3 class="card-title" style="margin:0 0 6px">${esc(L.name)}</h3>
        <div class="tiny">${esc(r.file)} · ${Math.round(r.size / 1048576)} MB</div>
        ${m?.url ? `<div class="tiny" style="margin-top:6px"><a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">模型页</a></div>` : ''}
        ${m?.words?.length ? `<div class="cv-w">${m.words.slice(0, 12).map(w => `${w.length > 60 ? `<span class="chip long" role="button" tabindex="0" title="点击展开 / 收起"><span class="cw-t">${esc(w)}</span></span>` : `<span class="chip">${esc(w)}</span>`}`).join('')}</div>` : ''}
        ${m ? '' : `<p class="tiny" style="margin:10px 0">未识别${window.hintHtml ? hintHtml('不是从商店下载的，本机没有它的记录。识别会按文件指纹去 Civitai 查是哪个模型，只读文件，不会改动它。', 'sm') : ''}</p><button type="button" class="btn small" id="cv-id">从 Civitai 识别</button>`}</div>`;
    navOn(backTo(keep, mineGrid), y, r.file);
    const ib = $('#cv-id', body); if (ib) ib.onclick = async () => {
      ib.disabled = true; ib.textContent = '识别中…';
      try { const mt = await api('/api/civitai/identify', { body: { target: r.t, file: r.file } }); toast('已识别：' + mt.name + (mt.version ? ' · ' + mt.version : '')); await loadMine(); const n = st.mine.find(z => z.file === r.file); if (n) mineDetail(n); }
      catch (e) { toast(e.message, true); ib.disabled = false; ib.textContent = '从 Civitai 识别'; }
    };
  };
  const setView = v => { st.view = v; navOff(); $$('#cv-view button', box).forEach(b => b.classList.toggle('on', b.dataset.v === v)); box.classList.toggle('cv-mine', v === 'mine'); v === 'mine' ? loadMine() : load(); };
  $$('#cv-view button', box).forEach(b => b.onclick = () => { if (b.dataset.v !== st.view) setView(b.dataset.v); });
  let qt = 0; $('#cv-q', box).oninput = e => { clearTimeout(qt); qt = setTimeout(() => { st.q = e.target.value.trim(); load(); }, 450); };
  $('#cv-sort', box).onchange = e => { st.sort = e.target.value; load(); };
  setView(st.view); watchDl();
}
