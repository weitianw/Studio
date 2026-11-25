/* 设置页（2026-11-05 用户要求）：左下角齿轮弹窗只留常用的几项，其余都在这里；外加“存储”——按多久没用清掉缓存。
   用 app.js 里已有的选项（GEAR_OPTS）和操作（主题、视频小窗、自动播放、防窥、显存、手机访问、重启……），这里只负责排版 */
'use strict';
const ST_AGES = [['0', '全部'], ['30', '1 个月'], ['90', '3 个月'], ['180', '6 个月'], ['365', '1 年']];  // 2026-11-08：手机上“1 个月前”被折成两行；这一行的标题已经写了“多久没有用过”，不用再写“前”
const stBytes = n => { n = +n || 0; if (n < 1024) return n + ' B'; const u = ['KB', 'MB', 'GB', 'TB']; let i = -1; do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1); return (n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2)) + ' ' + u[i]; };
const stSeg = (id, o) => `<div class="seg gp-seg" id="st-${id}" role="group">${o.items.map(([v, name, ic]) => `<button type="button" data-v="${v}" title="${name}" aria-label="${name}" class="${o.get() === v ? 'on' : ''}">${ic}</button>`).join('')}</div>`;
const stInApp = () => document.body.classList.contains('in-app') && !!window.pywebview?.api?.set_close_mode;  // 电脑上的 Studio 应用（不是浏览器 / 手机）
const ST_CHEV ='<svg class="st-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>';

// 设置页左边的目录（2026-11-18 用户：设置页分区，方便分类设置）：只在电脑上够宽时显示；点一下平滑滚到那个分区，滚动时亮着现在看到的那个
function stNav(R) {
  const nav = $('.st-nav', R), secs = $$('.st-sec[id]', R); if (!nav) return;
  nav.innerHTML = secs.map(s => `<button type="button" data-s="${s.id}">${esc($('.st-h', s).textContent)}</button>`).join('');
  // 滚动的是哪一层：往上找第一个能滚的，找不到就是整个窗口
  let sc = R; while (sc && !/(auto|scroll)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
  const win = !sc || sc === document.body || sc === document.documentElement; if (win) sc = document.scrollingElement;
  const tgt = win ? window : sc, top0 = () => win ? 0 : sc.getBoundingClientRect().top;
  const spy = () => {
    if (!nav.isConnected) return tgt.removeEventListener('scroll', spy);
    const top = top0() + 90, end = sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 4;
    let cur = secs[0]; for (const s of secs) if (s.getBoundingClientRect().top <= top) cur = s;
    if (end) cur = secs[secs.length - 1];
    $$('button', nav).forEach(b => b.classList.toggle('on', b.dataset.s === cur?.id));
  };
  $$('button', nav).forEach(b => b.onclick = () => { const s = $('#' + b.dataset.s, R); if (!s) return; (win ? window : sc).scrollTo({ top: sc.scrollTop + s.getBoundingClientRect().top - top0() - 16, behavior: 'smooth' }); });
  tgt.addEventListener('scroll', spy, { passive: true }); spy();
}
function renderSettings() {
  const row = (id, label, desc = '') => `<div class="st-row"><div class="st-l"><b>${label}${desc ? hintHtml(desc) : ''}</b></div><div class="st-r"><em class="st-cur" id="st-${id}-n">${gearName(GEAR_OPTS[id])}</em>${stSeg(id, GEAR_OPTS[id])}</div></div>`;
  const sw = (id, label, desc, on) => `<label class="st-row st-sw" data-tip="${esc(desc)}"><div class="st-l"><b>${label}</b></div><div class="st-r"><span class="switch"><input type="checkbox" id="st-${id}"${on ? ' checked' : ''}><span></span></span></div></label>`;
  const stSec = (id, title, body) => body.trim() ? `<section class="st-sec" id="sts-${id}"><h2 class="st-h">${title}</h2><div class="card st-card">${body}</div></section>` : '';
  const link = (id, label, desc, extra = '') => `<a class="st-row st-link" href="#" id="st-${id}"${extra}${desc ? ` data-tip="${esc(desc)}"` : ''}><div class="st-l"><b>${label}</b></div><div class="st-r">${ST_CHEV}</div></a>`;
  $('#main').innerHTML = `<div class="page-head"><div><h1 class="page-title">设置</h1></div></div>
  <div class="st-layout"><nav class="st-nav" aria-label="设置分区"></nav>
  <div class="st-wrap">
    ${stSec('look', '外观', `
      ${row('theme', '主题')}
      <div class="st-row"><div class="st-l"><b>语言</b></div><div class="st-r no-i18n"><div class="seg" id="st-lang" role="group" aria-label="Language">${[['en', 'English'], ['zh', '中文']].map(([v, n]) => `<button type="button" data-v="${v}" class="${(window.STUDIO_LANG || 'en') === v ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>
      ${MOB() ? '' : sw('railwide', '展开导航栏', '开启：左边导航栏变宽，图标旁边显示页面名称。关闭（默认）：窄导航栏', document.documentElement.classList.contains('rail-wide'))}
      ${MOB() ? '' : sw('galstk', '缩略图叠放', '开启：左边的缩略图放不下时叠在一起（像一叠文件），鼠标移上去抽出来。关闭（默认）：平铺，可以上下滚动', !!S.ui?.galStack)}
    `)}
    ${stSec('play', '播放', `
      ${row('vid', '视频小窗', '播放页以外的地方播放视频时，画面显示在哪里')}
      ${row('cover', '播放时的封面')}
      ${sw('autoplay', '自动播放视频预览', '关闭后，打开视频只显示画面，点播放按钮或缩略图上的 ▶ 才播放；播放页和连续预览不受影响', videoAutoplay())}
      ${MOB() ? '' : sw('plauthor', '播放列表显示作者', '开启：播放页的歌曲表多一列“作者”（读自文件里的作者标签）。关闭（默认）：不显示', !!S.ui?.plAuthor)}
    `)}
    ${stSec('gen', '生图与生视频', `
      ${MOB() ? '' : `<div class="st-row"><div class="st-l"><b>生图、生视频的选项</b></div><div class="st-r"><div class="seg" id="st-ppos" role="group" aria-label="选项放在哪" data-tip="输入框（默认）：选项在底部输入框里，点开输入框再选。创作栏：选项和提示词都在左边一整栏，点一下就改，缩略图在视频下面">${[['bottom', '输入框'], ['side', '创作栏']].map(([v, n]) => `<button type="button" data-v="${v}" class="${(S.ui?.ppos || 'bottom') === v ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>`}
      ${sw('pcs', '视频组平铺显示', '关闭（默认）：同一个原视频的片段、版本和拼接视频叠成一格，点开查看。开启：全部平铺显示', !!S.vdPcs)}
      ${sw('qc', '自动质检（生视频）', '开启后，每生成一段视频，在后台用 CPU 自动检查一遍（约 10～20 秒，不占显卡、不影响排队）：人物不见了、动作和原视频差得多、改衣后长相和原视频差别大。有问题的视频在缩略图上标出，点开可跳到对应的秒数。注意：很小的脸上嘴、鼻子那种变形查不出来。关闭（默认）时不做任何检查。', false)}
    `)}
    ${stSec('priv', stInApp() ? '窗口与隐私' : '隐私', `
      ${stInApp() ? `<div class="st-row"><div class="st-l"><b>点 × 时${hintHtml('<b>收进托盘</b>（默认）：窗口藏到右下角的托盘图标里，Studio 和正在播放的声音都还在，点托盘图标就回来；右键托盘图标可以退出。<br><b>退出软件</b>：直接关掉 Studio')}</b></div><div class="st-r"><div class="seg" id="st-close" role="group" aria-label="点 × 时"><button type="button" data-v="tray">收进托盘</button><button type="button" data-v="quit">退出软件</button></div></div></div>` : ''}
      ${sw('guard', '防窥模式', '页面上的图片和视频封面先显示为黑底，鼠标停留约 1 秒后才显示', !!S.ui?.guard)}
      ${VAULT ? row('lock', '自动退出私密空间', '多久没有操作（也没有在播放）后自动退出') : ''}
    `)}
    <section class="st-sec" id="sts-store"><h2 class="st-h">存储</h2><div class="card st-card st-store" id="st-store">
      <div class="st-row st-sum"><div class="st-l"><b>可清除的缓存${hintHtml((VAULT ? '只清除私密空间的缓存' : '只清除普通空间的缓存') + '。缓存都能自动重新生成，清除后第一次打开相应内容时会稍慢')}</b></div><div class="st-r"><em class="st-total" id="st-total">${ST_CATS && ST_CATS.g === VGEN ? '共 ' + stBytes(ST_CATS.reduce((a, c) => a + c.size, 0)) : '读取中…'}</em></div></div>
      <div id="st-cats"><div class="shimmer" style="height:120px;margin:10px 16px"></div></div>
      <div class="st-row st-act"><div class="st-l"><b>清除多久没有用过的${hintHtml('按最近一次使用的时间计算；最近 1 小时内用过的不会删除')}</b></div>
        <div class="st-r st-act-r"><div class="seg st-age" id="st-age" role="group" aria-label="清除范围">${ST_AGES.map(([v, n]) => `<button type="button" data-d="${v}" class="${v === (S.stAge ?? '90') ? 'on' : ''}">${n}</button>`).join('')}</div>
        <button type="button" class="btn danger st-clean" id="st-clean" disabled>清除</button></div></div>
      <div class="tiny st-note">只删缓存；作品、原视频、音色、字幕和设置不受影响</div>
    </div></section>
    <section class="st-sec" id="sts-gpu"><h2 class="st-h">显卡</h2><div class="card st-card st-vram"><div class="gp-list gp-vram" id="gear-vram"><div class="vr-head"><span>显存</span><em>读取中…</em></div><div class="vr-bar"><i></i></div></div></div></section>
    <section class="st-sec" id="sts-link"><h2 class="st-h">连接与工具</h2><div class="card st-card">
      ${REMOTE ? '' : link('remote', '手机访问', '通过 Tailscale 在 iPhone 上使用 Studio')}
      ${REMOTE && !STANDALONE ? link('a2hs', '添加到主屏幕', '像 App 一样从主屏幕打开') : ''}
      ${REMOTE && window.isSecureContext ? sw('push', '生成完成时通知', '生成完成或失败时，在这台手机上弹出通知（手机这会儿正开着 Studio 时不弹）。需要从主屏幕打开的 Studio（iOS 16.4 以上）。私密空间的任务只显示“有任务已完成”，不显示名字。', false) : ''}
      ${VAULT && REMOTE && window.isSecureContext && window.PublicKeyCredential ? sw('pk', '面容 ID 解锁（本机）', '开启后，在这台手机上按住页面标题（例如“播放”）约 1 秒再松开，验证面容 ID 就能进入私密空间，不用再输密钥。不会显示任何按钮；别的设备上按住标题没有反应。', false) : ''}
      ${REMOTE ? '' : link('comfy', 'ComfyUI', '打开生视频引擎自己的界面（未启动时会先启动）')}
      ${REMOTE ? '' : `<a class="st-row st-link" href="http://127.0.0.1:8080" target="_blank" data-tip="配音引擎自己的界面"><div class="st-l"><b>audio.cpp</b></div><div class="st-r">${ST_CHEV}</div></a>`}
    </div></section>
    <section class="st-sec" id="sts-about"><h2 class="st-h">关于</h2><div class="card st-card">
      <div class="st-row"><div class="st-l"><b>引擎状态</b></div><div class="st-r"><span class="gp-status st-eng" id="gear-eng">${engText()}</span></div></div>
      ${link('help', '使用说明', '')}
      ${link('origtpl', '原始提示词模板', 'laowang 用的工作流里自带的提示词原文')}
      ${link('restart', '重启 Studio', '重新启动后台程序（页面会自动重新连接）')}
      ${VAULT ? link('exit', '退出私密空间', '') : ''}
    </div></section>
  </div></div>`;
  const R = $('#main');
  stNav(R);
  const pick = (id, b) => { $$(`#st-${id} button`, R).forEach(y => y.classList.toggle('on', y === b)); $(`#st-${id}-n`, R).textContent = b.title; };
  $$('#st-theme button', R).forEach(b => b.onclick = () => { S.theme = b.dataset.v; persist(); applyTheme(true); pick('theme', b); });
  $$('#st-lang button', R).forEach(b => b.onclick = () => { if (b.dataset.v !== (window.STUDIO_LANG || 'en')) window.setStudioLang?.(b.dataset.v); });  // 界面语言：英文（默认）/ 中文，切换后重新载入页面
  $$('#st-vid button', R).forEach(b => b.onclick = () => { S.vidMode = b.dataset.v; persist(); pick('vid', b); const m = MINI; if (m && !m.hidden && !MINI_OUT) { m.hidden = true; m.classList.remove('show'); } miniSync(); });
  $$('#st-cover button', R).forEach(b => b.onclick = () => { S.coverMode = b.dataset.v; persist(); pick('cover', b); if (PB.a) pbPaint(true); qPanelPaint(); });
  $$('#st-lock button', R).forEach(b => b.onclick = () => { S.lockMin = +b.dataset.v; persist(); pick('lock', b); idleT = Date.now(); });
  $('#st-autoplay', R).onchange = e => setVideoAutoplay(e.target.checked);
  $$('#st-ppos button', R).forEach(b => b.onclick = () => { S.ui = { ...(S.ui || {}), ppos: b.dataset.v }; persist(); $$('#st-ppos button', R).forEach(y => y.classList.toggle('on', y === b)); });  // 2026-11-19：输入框版 / 创作栏版（右下角齿轮里也能换）
  $('#st-pcs', R).onchange = e => { S.vdPcs = e.target.checked; persist(); };
  const cl = $('#st-close', R);  // 点 × 时：收进托盘 / 退出软件（电脑应用里才有；设置存在 app.py 那边）
  if (cl) { const A = window.pywebview.api, mark = m => $$('[data-v]', cl).forEach(b => b.classList.toggle('on', b.dataset.v === m));
    mark('tray'); Promise.resolve(A.get_close_mode?.()).then(m => mark(m === 'quit' ? 'quit' : 'tray')).catch(() => { });
    $$('[data-v]', cl).forEach(b => b.onclick = async () => { try { mark(await A.set_close_mode(b.dataset.v)); toast(b.dataset.v === 'quit' ? '点 × 时将直接退出 Studio' : '点 × 时将收进右下角的托盘'); } catch (e) { toast('设置失败：' + e.message, true); } }); }
  if ($('#st-plauthor', R)) $('#st-plauthor', R).onchange = e => { S.ui = { ...(S.ui || {}), plAuthor: e.target.checked }; persist(); };
  if ($('#st-railwide', R)) $('#st-railwide', R).onchange = e => window.railWideSet?.(e.target.checked);
  if ($('#st-galstk', R)) $('#st-galstk', R).onchange = e => { S.ui = { ...(S.ui || {}), galStack: e.target.checked }; persist(); };
  $('#st-guard', R).onchange = e => { S.ui = S.ui || {}; S.ui.guard = e.target.checked; persist(); applyGuard(); };
  { const q = $('#st-qc', R); api('/api/video/qc').then(r => { q.checked = !!r.on; }).catch(() => { });  // 自动质检：存在电脑上（手机、电脑提交的都按它）
    q.onchange = async () => { try { const r = await api('/api/video/qc', { body: { on: q.checked } }); q.checked = !!r.on; toast(r.on ? '已开启自动质检：之后生成的每一段都会自动检查' : '已关闭自动质检'); } catch (e) { q.checked = !q.checked; toast(e.message, true); } }; }
  const on = (id, fn) => { const a = $('#st-' + id, R); if (a) a.onclick = e => { e.preventDefault(); fn(); }; };
  on('origtpl', stOrigTpl);
  on('remote', remotePanel); on('a2hs', addToHome); on('help', () => go('help')); on('restart', studioRestart); on('exit', () => vaultLock());
  on('comfy', async () => { toast('正在打开 ComfyUI（如视频引擎未启动，需先启动，约半分钟）…'); try { const r = await api('/api/video/comfy', { body: {} }); window.open(r.url, '_blank'); } catch (er) { toast(er.message, true); } });
  vramPaint(R);
  stStore();
  stPushBind(R); stPkBind(R);
}

/* 原始提示词模板（2026-11-08 用户要求）：laowang 用的两个工作流里自带的提示词、对比测试时用的那几段，原文只读（studio/orig_prompts.json） */
async function stOrigTpl() {
  let items = [];
  try { items = (await api('/api/video/orig-templates')).items || []; } catch (e) { return toast(/not found|404/i.test(e.message) ? '后台版本过旧，请重启 Studio' : e.message, true); }
  if (!items.length) return toast('没有找到原始模板文件', true);
  const box = modal(`<div class="row between pi-head"><h3 class="card-title">原始提示词模板</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="seg full st-ot-seg" role="tablist">${items.map((x, i) => `<button type="button" role="tab" data-i="${i}" data-tip="${esc(x.from || '')}" class="${i ? '' : 'on'}">${esc(x.name)}</button>`).join('')}</div>
    <div class="pi-body"><pre></pre></div>
    <div class="row pi-foot"><span class="spacer"></span><button type="button" class="btn small" data-copy>复制</button></div>`);
  box.classList.add('prompt-inspector', 'st-ot');
  let cur = 0; const pre = $('pre', box), show = i => { cur = i; pre.textContent = items[i].text; $('.pi-body', box).scrollTop = 0; $$('.st-ot-seg button', box).forEach(b => b.classList.toggle('on', +b.dataset.i === i)); };
  $$('.st-ot-seg button', box).forEach(b => b.onclick = () => show(+b.dataset.i));
  $('[data-close]', box).onclick = () => box.close();
  $('[data-copy]', box).onclick = () => copyText(items[cur].text).then(() => toast('已复制'), e => toast(e.message, true));
  show(0);
}

/* 生成完成时通知（2026-11-06）：注册 sw.js → 订阅推送 → 告诉电脑。iPhone 要求“请求通知权限”直接在点按里调用，所以它放在第一步 */
const b64uBytes = s => { s = String(s).replace(/-/g, '+').replace(/_/g, '/'); const b = atob(s + '='.repeat((4 - s.length % 4) % 4)); return Uint8Array.from(b, c => c.charCodeAt(0)); };
const bytesB64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
function stPushBind(R) {
  const cb = $('#st-push', R); if (!cb) return;
  api('/api/push/status').then(r => { cb.checked = !!r.on && Notification.permission === 'granted'; }).catch(() => { });
  cb.onchange = async () => {
    if (!cb.checked) {
      try { const reg = await navigator.serviceWorker?.getRegistration('/'); const sub = await reg?.pushManager?.getSubscription(); await sub?.unsubscribe(); } catch { }
      await api('/api/push/unsubscribe', { body: {} }).catch(() => { }); return toast('已关闭通知');
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !window.Notification) { cb.checked = false; return toast('请从主屏幕打开 Studio 后再开启（iOS 16.4 以上）', true); }
    try {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') { cb.checked = false; return toast('没有获得通知权限：可在 iPhone 设置 → 通知 → Studio 中打开', true); }
      const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' }); await navigator.serviceWorker.ready;
      const { key } = await api('/api/push/key');
      const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64uBytes(key) });
      await api('/api/push/subscribe', { body: { sub: sub.toJSON() } });
      await api('/api/push/test', { body: {} }).catch(() => { });
      toast('已开启：生成完成时会通知这台手机（稍后会收到一条测试通知）');
    } catch (e) { cb.checked = false; toast('开启通知失败：' + e.message, true); }
  };
}

/* 面容 ID 解锁（本机）。iPhone 要求 navigator.credentials.create/get 直接在点按里调用：挑战先取好，点的时候直接用 */
const PK_FLAG = 'ui.lp';  // 这台手机开启过（按住标题时才去要挑战；没开启的设备上按住标题什么也不做）
const pkPub = o => ({ ...o, challenge: b64uBytes(o.challenge), ...(o.user ? { user: { ...o.user, id: b64uBytes(o.user.id) } } : {}),
  ...(o.excludeCredentials ? { excludeCredentials: o.excludeCredentials.map(c => ({ ...c, id: b64uBytes(c.id) })) } : {}),
  ...(o.allowCredentials ? { allowCredentials: o.allowCredentials.map(c => ({ ...c, id: b64uBytes(c.id) })) } : {}) });
function stPkBind(R) {
  const cb = $('#st-pk', R); if (!cb) return;
  let opts = null; const prep = () => api('/api/vault/passkey/reg', { body: {} }).then(o => { opts = o; }).catch(() => { opts = null; });
  api('/api/vault/passkey/status').then(r => { cb.checked = !!r.on; if (r.on) localStorage.setItem(PK_FLAG, '1'); else localStorage.removeItem(PK_FLAG); }).catch(() => { });
  prep();
  cb.onchange = async () => {
    if (!cb.checked) { await api('/api/vault/passkey/remove', { body: {} }).catch(() => { }); localStorage.removeItem(PK_FLAG); return toast('已关闭面容 ID 解锁'); }
    if (!opts) { cb.checked = false; prep(); return toast('请稍等一下再试', true); }
    try {
      const c = await navigator.credentials.create({ publicKey: pkPub(opts) }); opts = null; prep();
      await api('/api/vault/passkey/save', { body: { id: c.id, clientDataJSON: bytesB64u(c.response.clientDataJSON), attestationObject: bytesB64u(c.response.attestationObject) } });
      localStorage.setItem(PK_FLAG, '1');
      toast('已开启：以后在这台手机上按住页面标题约 1 秒再松开，验证面容 ID 即可进入');
    } catch (e) { cb.checked = false; prep(); toast(e.name === 'NotAllowedError' ? '已取消' : e.name === 'InvalidStateError' ? '这台手机已开启过面容 ID 解锁，请关掉设置页重新打开' : '开启失败：' + e.message, true); }
  };
}

/* 存储：每一类缓存占多少、选的时间范围里能清掉多少；勾选要清的几类，点“清除” */
let ST_CATS = null;
async function stStore(data) {
  const box = $('#st-cats'); if (!box) return;
  const d = data || await api('/api/cache').catch(e => ({ error: e.message }));
  if (!box.isConnected) return;
  if (d.error) { box.innerHTML = `<div class="tiny st-err">无法读取缓存信息：${esc(d.error)}</div>`; $('#st-total').textContent = ''; return; }
  ST_CATS = d.cats || []; ST_CATS.g = VGEN;  // 记下是哪个空间的：下次进设置页先显示上次的总大小（不闪“读取中…”）
  S.stKeys = S.stKeys || { scrub: true, covers: true, conv: true, tmp: true };
  box.innerHTML = ST_CATS.map(c => `<label class="st-row st-cat"><span class="st-ck"><input type="checkbox" data-k="${esc(c.key)}"${S.stKeys[c.key] !== false ? ' checked' : ''}></span>
    <div class="st-l"><b>${esc(c.name)}${hintHtml(esc(c.desc))}</b></div><div class="st-r st-size"><b data-free="${esc(c.key)}"></b>${c.size ? `<em>共 ${stBytes(c.size)}${c.files ? ` · ${c.files} 个文件` : ''}</em>` : ''}</div></label>`).join('');
  $$('[data-k]', box).forEach(i => i.onchange = () => { S.stKeys[i.dataset.k] = i.checked; persist(); stCalc(); });
  $$('#st-age button').forEach(b => b.onclick = () => { S.stAge = b.dataset.d; persist(); $$('#st-age button').forEach(x => x.classList.toggle('on', x === b)); stCalc(); });
  $('#st-total').textContent = '共 ' + stBytes(ST_CATS.reduce((a, c) => a + c.size, 0));
  $('#st-clean').onclick = stClean;
  stCalc();
}
const stAge = () => S.stAge ?? '90';
const stFree = c => stAge() === '0' ? c.size : (c.old?.[stAge()] || 0);  // 选的范围里能清掉多少（“全部”时最近 1 小时 / 1 天内的其实也会留着）
function stCalc() {
  if (!ST_CATS) return;
  let sum = 0;
  ST_CATS.forEach(c => { const f = stFree(c), el = $(`[data-free="${c.key}"]`); const on = S.stKeys[c.key] !== false; if (on) sum += f;
    if (el) { el.textContent = f ? '可清除 ' + stBytes(f) : '没有可清除的'; el.classList.toggle('none', !f); el.closest('.st-cat')?.classList.toggle('off', !on); } });
  const b = $('#st-clean'); if (b) { b.disabled = !sum; b.textContent = sum ? '清除 ' + stBytes(sum) : '清除'; }
}
async function stClean() {
  const keys = ST_CATS.filter(c => S.stKeys[c.key] !== false && stFree(c)).map(c => c.key); if (!keys.length) return;
  const names = ST_CATS.filter(c => keys.includes(c.key)).map(c => c.name).join('、'), age = ST_AGES.find(a => a[0] === stAge())[1];
  if (!await confirmBox('清除缓存？', `将删除${age === '全部' ? '' : ' ' + age + '以上没有用过的'}${names}（约 ${stBytes(ST_CATS.filter(c => keys.includes(c.key)).reduce((a, c) => a + stFree(c), 0))}）。这些都能自动重新生成，作品和原视频不受影响。`, '清除', true)) return;
  const b = $('#st-clean'); b.disabled = true; b.textContent = '正在清除…';
  try { const r = await api('/api/cache/clean', { body: { keys, days: +stAge() } }); toast(r.files ? `已清除 ${r.files} 个文件，释放 ${stBytes(r.freed)}` : '没有需要清除的文件'); stStore(r); }
  catch (e) { toast('清除失败：' + e.message, true); stStore(); }
}
PAGES.settings = renderSettings;
