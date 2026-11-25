/* Prompt inspection is opt-in: no network or model work until the icon is clicked. */
window.PromptInspector = (() => {
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h10M4 11h8M4 16h5"/><circle cx="16" cy="15" r="4"/><path d="m19 18 3 3"/></svg>';
  const sources = new WeakMap(), uses = new WeakMap(), tpls = new WeakMap();  // tpls：这个输入框用到的模板（{ pages } 或返回它的函数）
  const sizes = new ResizeObserver(entries => entries.forEach(({ target, contentRect }) => target.closest('.has-prompt-peek')?.classList.toggle('pi-short', contentRect.height < 72)));
  let active = null;
  const rawTrace = (input, label = '输入内容') => ({ input, stages: [{ label, text: input }], notes: ['此处展示当前填写内容。'] });
  const printable = t => [t.input !== undefined ? '输入原文\n' + t.input : '', ...(t.stages || []).map(s => s.label + '\n' + s.text +
    (s.negative !== undefined ? '\n\n负面提示词\n' + s.negative : '')), ...(t.notes || [])].filter(Boolean).join('\n\n');
  /* 2026-11-09 模板套：和“完整提示词”同一个窗口，第二页“模板”。一套 = 全部页面的模板；这里只列出当前页面用到的那几份，
     正在用的那份（预览里用到的）默认选中。内置的两套只读，可以基于任意一套新建、改、定默认（tplstore.py） */
  /* 当前默认那套的全文：网页上自己拼指令的地方（改录音的“发给模型的指令”）照它拼；改了模板 / 换了默认 / 换了空间后重新取，发 tplchange */
  window.TPL = { cur: null, L: null, async load() { try { const L = TPL.L = await api('/api/templates'); TPL.cur = await api('/api/templates?id=' + encodeURIComponent(L.default)); } catch { } dispatchEvent(new Event('tplchange')); } };
  addEventListener('DOMContentLoaded', () => setTimeout(() => TPL.load(), 0), { once: true });
  function tplPanel(el, opts, onChange) {
    let L = null, sid = '', set = null, kind = '', lang = 'zh', drafts = {}, used = [], mode = 't';  // mode：t = 模板（套在用户文字外面的），s = 系统指令（发给 AI 模型的，2026-11-16 分开）
    const openG = new Set(), kindBy = {};  // 左边点开了哪几个功能（正在看的那个默认点开）；kindBy：模板 / 系统指令各自上次看的那份
    const kinds = () => (L?.kinds || []).filter(k => k.pages.some(p => opts.pages.includes(p)) && !!k.sys === (mode === 's'));
    let pic = false;  // 有参考图 / 无参考图（改视频的换衣可以不放图：两份分开的模板，2026-11-09）
    const fit = n => (n.lang === lang || !n.lang) && (n.pic === undefined || n.pic === pic);
    const name = () => { const ns = kinds().find(k => k.key === kind)?.names || []; return ns.find(fit) || ns.find(n => n.lang === lang || !n.lang) || ns[0]; };
    const dirty = () => Object.keys(drafts).some(n => drafts[n] !== set?.t[n]);
    const load = async id => { set = await api('/api/templates?id=' + encodeURIComponent(id)); sid = set.id; drafts = {}; };
    const ask = async () => !dirty() || confirmBox('放弃未保存的修改？', '', '放弃', true);
    const pickUsed = () => { const k = kinds().find(k => k.names.some(n => used.includes(n.name))) || kinds()[0]; kind = k?.key || '';
      const n = k?.names.find(n => used.includes(n.name)); if (n?.lang) lang = n.lang; if (n?.pic !== undefined) pic = n.pic; };
    const paint = () => {
      const K = kinds(), k = K.find(x => x.key === kind), n = name(), ro = !!set?.builtin, isDef = sid === L.default;
      const txt = n ? (drafts[n.name] ?? set.t[n.name] ?? '') : '';
      const slots = Object.entries(k?.slots || {});
      const isUsed = x => x.names.some(m => used.includes(m.name)), dot = '<i class="pt-dot" aria-label="正在使用"></i>';
      const G = [...new Set(K.map(x => x.group))], g = k?.group || G[0], inG = K.filter(x => x.group === g);  // 先选功能，再选这个功能里的那一份（2026-11-09 用户：一次全列出来太多）
      const top = `<div class="pt-top"><button type="button" class="pt-set" aria-haspopup="listbox" title="选择模板套"><span>${esc(set.name)}</span>${isDef ? '<em class="pt-def">默认</em>' : ''}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg></button>
          <span class="spacer"></span>${isDef ? '' : '<button type="button" class="btn small" data-pt-def>设为默认</button>'}${ro ? '' : `<button type="button" class="pl-ib" data-pt-more aria-label="更多操作" title="重命名 / 删除"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg></button>`}</div>`;
      if (opts.slot) opts.slot.innerHTML = top;
      el.innerHTML = (opts.slot ? '' : top) + `
        ${K.length > 1 ? `<nav class="pt-side" aria-label="模板">${G.map(x => { const its = K.filter(y => y.group === x), u = its.some(isUsed);  // 电脑：左边是功能（同一级），有几份的功能点开看下面的几份（2026-11-09 用户：原来看不出谁是哪一类）
            if (its.length === 1) return `<button type="button" class="pt-sg pt-sg1${its[0].key === kind ? ' on' : ''}" data-k="${esc(its[0].key)}" aria-current="${its[0].key === kind}"><i class="pt-chev"></i><span>${esc(x)}</span>${u ? dot : ''}</button>`;
            const op = openG.has(x) || (x === g && !openG.has('\0' + x));
            return `<button type="button" class="pt-sg" data-og="${esc(x)}" aria-expanded="${op}"><svg class="pt-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg><span>${esc(x)}</span>${u && !op ? dot : ''}</button>`
              + `<div class="pt-sc"${op ? '' : ' hidden'}>${its.map(y => `<button type="button" class="pt-si${y.key === kind ? ' on' : ''}" data-k="${esc(y.key)}" aria-current="${y.key === kind}">${esc(y.label)}${isUsed(y) ? dot : ''}</button>`).join('')}</div>`; }).join('')}</nav>` : ''}
        <div class="pt-mob">${G.length > 1 ? `<div class="pt-groups" role="tablist" aria-label="功能">${G.map(x => { const u = K.some(y => y.group === x && isUsed(y)); return `<button type="button" role="tab" class="pt-g${x === g ? ' on' : ''}" data-g="${esc(x)}" aria-selected="${x === g}">${esc(x)}${u ? dot : ''}</button>`; }).join('')}</div>` : ''}
          ${inG.length > 1 ? `<div class="pt-chips" role="tablist" aria-label="模板">${inG.map(x => `<button type="button" role="tab" class="pt-k${x.key === kind ? ' on' : ''}" data-k="${esc(x.key)}" aria-selected="${x.key === kind}">${esc(x.label)}${isUsed(x) ? dot : ''}</button>`).join('')}</div>` : ''}</div>
        <div class="pt-main"><div class="pt-mh"><b class="pt-title">${esc(g || '')}${inG.length > 1 ? ' · ' + esc(k?.label || '') : ''}</b><span class="spacer"></span>
          ${(k?.names || []).some(m => m.pic === false) ? `<div class="seg mini pt-pic">${[[true, '有参考图'], [false, '无参考图']].map(([v, t]) => `<button type="button" data-p="${v}" class="${v === pic ? 'on' : ''}">${t}${(k?.names || []).some(m => m.pic === v && used.includes(m.name)) ? dot : ''}</button>`).join('')}</div>` : ''}
          ${k?.versions ? (() => { const cv = set.vers?.[k.key] || {}, own = !!cv.own;  // 系统指令的几个版本（2026-11-16）：点一下就改用，不用保存；这套里自己改过这一份时用的是改过的文字
            return `<div class="seg mini pt-ver" role="radiogroup" aria-label="版本"${own ? ` title="这套模板里改过这一份，使用的是改过的文字"` : ''}>${k.versions.map(v => `<button type="button" role="radio" data-v="${esc(v.id)}" aria-checked="${!own && v.id === (cv.id || '')}" class="${!own && v.id === (cv.id || '') ? 'on' : ''}"${own ? ' disabled' : ''}>${esc(v.label)}</button>`).join('')}</div>`; })() : ''}
          ${new Set((k?.names || []).map(m => m.lang)).size > 1 ? `<div class="seg mini pt-lang">${[...new Set(k.names.map(m => m.lang))].map(l => `<button type="button" data-l="${l}" class="${l === lang ? 'on' : ''}">${l === 'en' ? '英文' : '中文'}</button>`).join('')}</div>` : ''}
          ${slots.length && window.hintHtml ? hintHtml('<b>会被替换的部分</b><br>' + slots.map(([a, b]) => `<code>{${esc(a)}}</code> ${esc(b)}`).join('<br>'), 'sm') : ''}</div>
        <textarea class="textarea pt-text" spellcheck="false" aria-label="模板内容"${ro ? ' readonly' : ''}>${esc(txt)}</textarea></div>
        <div class="row pi-foot"><span class="spacer"></span>${ro ? '<button type="button" class="btn small primary" data-pt-new>基于此套新建</button>'
          : `<button type="button" class="btn small" data-pt-undo${dirty() ? '' : ' disabled'}>还原</button><button type="button" class="btn small primary" data-pt-save${dirty() ? '' : ' disabled'}>保存</button>`}</div>`;
      const ta = el.querySelector('.pt-text'), q = s => el.querySelector(s) || opts.slot?.querySelector(s);
      ta.oninput = () => { if (n) drafts[n.name] = ta.value; const d = dirty(); q('[data-pt-save]') && (q('[data-pt-save]').disabled = !d); q('[data-pt-undo]') && (q('[data-pt-undo]').disabled = !d); };
      el.querySelectorAll('.pt-g').forEach(b => b.onclick = () => { const xs = kinds().filter(x => x.group === b.dataset.g); kind = (xs.find(x => x.names.some(m => used.includes(m.name))) || xs[0]).key;
        const m = kinds().find(x => x.key === kind)?.names || []; if (!m.some(x => x.lang === lang)) lang = m[0]?.lang || 'zh'; paint(); });
      el.querySelectorAll('[data-og]').forEach(b => b.onclick = () => { const x = b.dataset.og; if (openG.has(x) || x === kinds().find(y => y.key === kind)?.group) { openG.delete(x); if (x === kinds().find(y => y.key === kind)?.group) openG.add('\0' + x); } else { openG.add(x); openG.delete('\0' + x); } paint(); });
      el.querySelectorAll('.pt-k, .pt-si, .pt-sg1').forEach(b => b.onclick = () => { kind = b.dataset.k; const m = kinds().find(x => x.key === kind)?.names || []; if (!m.some(x => x.lang === lang)) lang = m[0]?.lang || 'zh'; paint(); });
      el.querySelectorAll('.pt-lang button').forEach(b => b.onclick = () => { lang = b.dataset.l; paint(); });
      el.querySelectorAll('.pt-pic button').forEach(b => b.onclick = () => { pic = b.dataset.p === 'true'; paint(); });
      el.querySelectorAll('.pt-ver button').forEach(b => b.onclick = async () => { if (b.classList.contains('on') || !await ask()) return; drafts = {};
        await run({ op: 'pick', key: kind, ver: b.dataset.v }, `已改用「${b.textContent}」`, sid); });
      q('.pt-set').onclick = () => popover(q('.pt-set'), `<div class="pp-pop pt-pop" role="listbox">${L.sets.map(x => `<button type="button" class="pp-it${x.id === sid ? ' on' : ''}" role="option" aria-selected="${x.id === sid}" data-id="${esc(x.id)}"><span>${esc(x.name)}${x.builtin ? '<em class="pt-ro">内置</em>' : ''}${x.id === L.default ? '<em class="pt-def">默认</em>' : ''}</span>${x.id === sid ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>' : ''}</button>`).join('')}
          <button type="button" class="pp-it pt-add" data-new><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg><span>基于「${esc(set.name)}」新建</span></button></div>`,
        pop => { pop.querySelectorAll('[data-id]').forEach(b => b.onclick = async () => { pop.close(); if (b.dataset.id === sid || !await ask()) return; await load(b.dataset.id); paint(); });
          pop.querySelector('[data-new]').onclick = () => { pop.close(); create(); }; }, { width: 300 });
      q('[data-pt-def]') && (q('[data-pt-def]').onclick = () => run({ op: 'default', id: sid }, `已将「${set.name}」设为默认`));
      q('[data-pt-new]') && (q('[data-pt-new]').onclick = create);
      q('[data-pt-undo]') && (q('[data-pt-undo]').onclick = () => { drafts = {}; paint(); });
      q('[data-pt-save]') && (q('[data-pt-save]').onclick = async () => { const t = {}; for (const m in drafts) if (drafts[m] !== set.t[m]) t[m] = drafts[m];
        await run({ op: 'save', id: sid, t }, sid === L.default ? '已保存' : `已保存。当前默认的仍是「${L.sets.find(x => x.id === L.default)?.name || ''}」`); });
      q('[data-pt-more]') && (q('[data-pt-more]').onclick = () => popover(q('[data-pt-more]'), `<div class="pp-pop"><button type="button" class="pp-it" data-rn><span>重命名</span></button><button type="button" class="pp-it danger" data-del><span>删除</span></button></div>`,
        pop => { pop.querySelector('[data-rn]').onclick = () => { pop.close(); nameBox('重命名模板套', set.name, v => run({ op: 'save', id: sid, name: v }, '已重命名')); };
          pop.querySelector('[data-del]').onclick = async () => { pop.close();
            if (!await confirmBox(`删除「${set.name}」？`, '删除后无法恢复' + (sid === L.default ? '，默认将改回「正向写法」。' : '。'), '删除', true)) return;
            drafts = {}; await run({ op: 'delete', id: sid }, '已删除', 'pos'); }; }, { width: 160 }));
    };
    const nameBox = (title, v, done) => modal(`<h3 class="card-title">${esc(title)}</h3><input class="input" id="pt-nm" value="${esc(v)}" maxlength="40" aria-label="名称" style="margin:12px 0">
      <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" data-close>取消</button><button class="btn primary" id="pt-ok">确定</button></div>`, m => {
      const i = m.querySelector('#pt-nm'), ok = () => { const t = i.value.trim(); if (!t) return toast('名称不能为空', true); m.close(); done(t); };
      m.querySelector('#pt-ok').onclick = ok; i.onkeydown = e => { if (e.key === 'Enter') ok(); }; setTimeout(() => i.select(), 30); });
    const create = async () => { if (!await ask()) return; nameBox('新建模板套', set.name + ' 副本', v => run({ op: 'create', base: sid, name: v }, `已新建「${v}」，可以修改后设为默认`, null, true)); };
    const run = async (body, msg, then, isNew) => {
      try { const r = await api('/api/templates', { body }); L = r; await load(then || (body.op === 'delete' ? r.default : r.id)); paint(); toast(msg); onChange?.(); if (isNew) el.querySelector('.pt-text')?.focus(); }
      catch (e) { toast(e.message, true); }
    };
    return {
      async open(u, m = 't') { if (m !== mode) { kindBy[mode] = kind; mode = m; kind = kindBy[m] || ''; }  // 模板 / 系统指令各记各的：切回来停在刚才看的那份
        const same = kind && String(u || []) === String(used); used = u || [];  // 第一次打开 / 设置变了：定位到正在用的那份；否则停在刚才看的那份
        try { L = await api('/api/templates'); if (!set) await load(L.default); if (!same) pickUsed(); paint(); } catch (e) { el.textContent = e.message; } },
      dirty, ask,
    };
  }
  function show(provider, options = {}) {
    active?.close();
    const gen = VGEN, source = options.source, T = options.tpl && !options.saved;
    const TK = (TPL.L?.kinds || []).filter(k => T && k.pages.some(p => options.tpl.pages.includes(p))), hasS = TK.some(k => k.sys), hasT = !TK.length || TK.some(k => !k.sys);  // 这一页有没有系统指令 / 模板（列表还没读到：先都给）
    const tabs = [['p', '完整提示词'], ...(hasT ? [['t', '模板']] : []), ...(hasS || !TPL.L ? [['s', '系统指令']] : [])];
    const box = modal(`<div class="row between pi-head">${T ? `<div class="seg pi-tabs" role="tablist" aria-label="提示词">${tabs.map(([k, n], i) => `<button type="button" role="tab" class="${i ? '' : 'on'}" aria-selected="${!i}" data-tab="${k}">${n}</button>`).join('')}</div><div class="pi-hx" hidden></div>`
      : `<h3 class="card-title">${options.saved ? '实际发送的提示词' : '提示词预览'}</h3>`}<button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div><div class="pi-pane" data-pane="p"><div class="pi-body" aria-live="polite">正在读取…</div><div class="row pi-foot"><span class="spacer"></span><button type="button" class="btn small" data-pi-use hidden>放到提示词框</button><button type="button" class="btn small" data-pi-copy disabled>复制全部</button></div></div>${T ? '<div class="pi-pane pi-tpl" data-pane="t" hidden></div>' : ''}`);
    box.classList.add('prompt-inspector'); box.setAttribute('aria-label', options.saved ? '实际发送的提示词' : '提示词预览'); active = box;
    const close = box.close;
    const watch = setInterval(() => { if (gen !== VGEN || source && !source.isConnected) box.close(); }, 200);
    let tp = null, stale = false, lastUsed = [];
    box.close = async () => { if (tp && !await tp.ask()) return false; clearInterval(watch); close(); if (active === box) active = null; source?.setAttribute('aria-expanded', 'false'); return true; };  // 模板有没保存的修改：先问
    box.querySelector('[data-close]').onclick = box.close;
    if (T) {
      tp = tplPanel(box.querySelector('.pi-tpl'), { ...options.tpl, slot: box.querySelector('.pi-hx') }, () => { stale = true; TPL.load(); });
      box.querySelectorAll('.pi-tabs button').forEach(b => b.onclick = () => {
        const t = b.dataset.tab; box.querySelectorAll('.pi-tabs button').forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-selected', x === b); });
        box.querySelectorAll('.pi-pane').forEach(p => p.hidden = p.dataset.pane !== (t === 's' ? 't' : t)); box.classList.toggle('pi-t', t !== 'p'); box.querySelector('.pi-hx').hidden = t === 'p';
        if (t !== 'p') tp.open(lastUsed, t); else if (stale) { stale = false; fill(); }  // 改过模板 / 换了默认：回到完整提示词时重新预览
      });
    }
    const fill = () => Promise.resolve().then(() => typeof provider === 'function' ? provider() : provider).then(t => {
      if (active !== box || gen !== VGEN) return;
      lastUsed = t.templates || [];
      const body = box.querySelector('.pi-body');
      const raw = t.input === undefined ? '' : `<details class="pi-original"${(t.stages || []).some(s => s.text !== t.input) ? ' open' : ''}><summary>输入原文</summary><pre>${esc(t.input || '（空）')}</pre></details>`;
      body.innerHTML = raw + (t.stages || []).map(s => `<section class="pi-stage"><h4>${esc(s.label)}</h4><pre>${esc(s.text || '（空）')}</pre>${s.negative !== undefined ? `<h5>负面提示词</h5><pre>${esc(s.negative || '（空）')}</pre>` : ''}</section>`).join('') +
        (t.notes?.length ? `<div class="tiny pi-notes">${t.notes.map(esc).join('<br>')}</div>` : '');
      const copy = box.querySelector('[data-pi-copy]'); copy.disabled = false;
      copy.onclick = () => copyText(printable(t)).then(() => toast('已复制完整提示词'), e => toast(e.message, true));
      const fn = options.use?.(t), ub = box.querySelector('[data-pi-use]');  // 把完整提示词放进提示词框（改视频：同时关掉“使用模板”）
      if (fn) { ub.hidden = false; ub.onclick = async () => { if (await box.close()) fn(); }; }
    }).catch(e => {
      if (active !== box) return;
      box.querySelector('.pi-body').textContent = /404|not found/i.test(e.message) ? '后台尚未载入预览接口，请在设置中重启 Studio 后再试。' : e.message;
    });
    fill();
    source?.setAttribute('aria-expanded', 'true'); box.querySelector('[data-close]').focus({ preventScroll: true });
    return box;
  }
  function fallback(el) {
    if (el.id === 'script' || el.id === 'extra') {
      const trace = rawTrace(el.id === 'script' ? el.value : ($('#script')?.value || ''), '配音文本');
      trace.stages.push({ label: '导演指令', text: instructText() });
      trace.notes = ['展示当前完整文本与导演指令；分段、停顿及模型支持范围以配音任务为准。'];
      return trace;
    }
    if (el.id === 'ae-a' || el.id === 'ae-b') {
      return { input: [$('#ae-a')?.value || '', $('#ae-b')?.value || ''].join('\n'), stages: [{ label: '发给模型的指令', text: aeInst() }], notes: [], templates: aeTplName() ? [aeTplName()] : [] };
    }
    if (el.id === 'ig-dt-p') {
      return { input: el.value, stages: [{ label: '局部细化提示词', text: el.value.trim().slice(0, 1000) || ($('#ig-prompt')?.value || '').trim().slice(0, 4000) }], notes: ['留空时使用主提示词；检测到相应区域后才会执行细化。'] };
    }
    const label = el.closest('.field')?.querySelector('.label');
    const title = label ? [...label.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : '';
    return rawTrace(el.value, title || '输入内容');
  }
  function bind(el, provider, opts) {
    if (!el) return;
    if (provider) sources.set(el, provider);
    if (opts?.use) uses.set(el, opts.use);
    if (opts?.tpl) tpls.set(el, opts.tpl);
    if (el._promptPeek) { if (el.tagName === 'TEXTAREA') sizes.observe(el); return; }
    if (el.tagName === 'TEXTAREA' && typeof clearable === 'function') clearable(el);
    let wrap = el.closest('.clr-wrap');
    if (!wrap) { wrap = document.createElement('span'); wrap.className = 'pi-wrap'; el.parentNode.insertBefore(wrap, el); wrap.append(el); }
    wrap.classList.add('has-prompt-peek');
    const b = document.createElement('button'); b.type = 'button'; b.className = 'prompt-peek'; b.innerHTML = icon;
    b.title = '查看完整提示词'; b.setAttribute('aria-label', '查看完整提示词'); b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false');
    b.onclick = e => { e.preventDefault(); e.stopPropagation(); const tp = tpls.get(el), tpl = typeof tp === 'function' ? tp() : tp;
      show(() => sources.has(el) ? sources.get(el)() : fallback(el), { source: b, use: uses.get(el), tpl: tpl?.pages?.length ? tpl : null }); };
    wrap.append(b); el._promptPeek = b;
    if (el.tagName === 'TEXTAREA') sizes.observe(el);
  }
  const selector = 'textarea.textarea:not([readonly]):not(#stt-text):not(#ev-tr):not(#rd-text):not(.pt-text), #ae-a, #ae-b, input#ig-dt-p, input#s-prompt, input#s-bg';
  const scan = node => { if (node.nodeType !== 1) return; if (node.matches(selector)) bind(node); node.querySelectorAll(selector).forEach(el => bind(el)); };
  new MutationObserver(ms => {
    for (const m of ms) {
      for (const n of m.removedNodes) if (n.nodeType === 1 && !n.isConnected) { if (n.matches(selector)) sizes.unobserve(n); n.querySelectorAll(selector).forEach(el => sizes.unobserve(el)); }
      for (const n of m.addedNodes) scan(n);
    }
  }).observe(document.documentElement, { subtree: true, childList: true });
  addEventListener('DOMContentLoaded', () => scan(document.documentElement), { once: true });
  function history(host, item) {
    if (!host) return;
    host.classList.add('pi-history');
    const b = document.createElement('button'); b.type = 'button'; b.className = 'prompt-peek'; b.innerHTML = icon;
    b.title = '查看生成时的完整提示词'; b.setAttribute('aria-label', b.title); b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false');
    b.onclick = e => { e.stopPropagation(); show(() => item.prompt_trace || { input: item.prompt || '', stages: [], notes: ['此作品没有保存完整的发送记录，仅能显示输入文字，无法还原当时实际发送的完整内容。'] }, { saved: !!item.prompt_trace, source: b }); };
    host.append(b);
  }
  return { bind, show, history };
})();
