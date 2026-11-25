/* AI 配音工作室 前端。纯原生 JS，无需构建。 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
/* 转圈（.spinner，0.7 秒一圈）：列表每次轮询都整段重画，新的转圈从 0° 开始，看起来每秒抽一下。
   新加进页面的转圈一律按全局时间对齐动画（animation-delay 为负），接着原来的角度转，看起来是连续的（2026-11-04） */
new MutationObserver(ms => { const d = `-${(performance.now() % 700) / 1000}s`;
  for (const m of ms) for (const n of m.addedNodes) { if (n.nodeType !== 1) continue; if (n.classList.contains('spinner')) n.style.animationDelay = d; n.querySelectorAll?.('.spinner').forEach(x => { x.style.animationDelay = d; }); } })
  .observe(document.documentElement, { childList: true, subtree: true });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// LoRA 的名称和一句话用途（选择框里只显示文件名，用户分不清是什么，2026-11-04）：认得的按文件名写好；Civitai 下载的用它的模型名；都没有就把文件名整理一下
const LORA_KNOWN = [
  [/head[_ -]?swap/i, '换头', '仅替换头部，身体与动作保持原视频'],
  [/character[_ -]?swap/i, '换人', '将视频中的人物替换为人物图中的人物'],
  [/vfx[_ -]?edit/i, '特效编辑（VFX）', '用一句话修改视频：添加特效、更换天气或背景'],
];
const loraLabel = (f, meta) => {  // → { name, use }
  const tm = /(fl2v|ref2v)_turbo_(\d+)step/i.exec(f || '');  // 官方加速 LoRA：在高级参数的“加速 LoRA”里选
  if (tm) return { name: `加速 LoRA（${/fl2v/i.test(tm[1]) ? 'FL2VA' : 'Ref2VA'} ${tm[2]} 步）`, use: /fl2v/i.test(tm[1]) ? '生视频首帧用' : '参考模式用' };
  const k = LORA_KNOWN.find(([re]) => re.test(f || ''));
  if (k) return { name: k[1], use: k[2] };
  if (meta?.name) return { name: meta.name, use: meta.base ? `Civitai · ${meta.base}` : 'Civitai 下载' };
  return { name: String(f || '').replace(/\.(safetensors|pt|ckpt|gguf)$/i, '').replace(/[_]+/g, ' ').trim(), use: '' };
};
const loraOpt = (f, meta) => { const L = loraLabel(f, meta); return L.name + (L.use ? ' — ' + L.use : ''); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const MINI = document.getElementById('mini');  // 视频小窗（弹到画中画窗口时它会被搬到另一个文档里，所以先记住它）
const ICON = {
  sparkle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5l1.9 4.9 4.9 1.9-4.9 1.9L12 17.1l-1.9-4.9-4.9-1.9 4.9-1.9z"/><path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>',
  playNext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4.5v11l8.5-5.5z"/><path d="M19.5 9v4.5a4 4 0 0 1-4 4H10"/><path d="M12.5 14.8 9.8 17.5l2.7 2.7"/></svg>',
  addList: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="17" height="17" rx="3.5"/><path d="M12 8v8M8 12h8"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 3.5 8 12 12.5 20.5 8z"/><path d="M3.5 12 12 16.5 20.5 12"/><path d="M3.5 16 12 20.5 20.5 16"/></svg>',
  sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/></svg>',
  tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.4 1.4 0 0 1 0 2l-6.2 6.2a1.4 1.4 0 0 1-2 0z"/><circle cx="8" cy="8" r="1.5"/></svg>',
  recent: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 4v4h4"/><path d="M12 7.5V12l3 2"/></svg>',
  translate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h9M8.5 3v2M6 5c.6 3.4 2.8 6 6 7.5M11 5c-.8 3.6-3.2 6.6-6.5 8"/><path d="M13 21l4-9 4 9M14.6 17.6h4.8"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/></svg>',
  wand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/></svg>',  // 2026-11-07 用户不喜欢魔法棒：换成“笔”
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>',
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  dl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12M7 11l5 5 5-5M5 20h14"/></svg>',
  redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.2h7a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/></svg>',
  note: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 3.2 9.6 5c-.5.1-.8.5-.8 1v8.5a3 3 0 1 0 1.4 2.5V8.5l6.4-1.4v5.4a3 3 0 1 0 1.4 2.5V4c0-.6-.5-.9-.8-.8z"/></svg>',
  film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.2-2.5z" fill="currentColor" stroke="none"/></svg>',
  expandAll: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9l5 5 5-5M7 4l5 5 5-5M5 20h14"/></svg>',
  collapseAll: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 15l5-5 5 5M7 20l5-5 5 5M5 4h14"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  wave: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 10v4M8 6v12M12 9v6M16 4v16M20 10v4"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>',
  up2: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l6-6 6 6"/></svg>',
  down2: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
  fs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  fsExit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>',
  heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-9-9.1C1.7 7.6 4 4.5 7.2 4.5c2 0 3.4 1.1 4.8 2.8 1.4-1.7 2.8-2.8 4.8-2.8 3.2 0 5.5 3.1 4.2 6.4C19 15.6 12 20 12 20z"/></svg>',
  heartFill: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 20s-7-4.4-9-9.1C1.7 7.6 4 4.5 7.2 4.5c2 0 3.4 1.1 4.8 2.8 1.4-1.7 2.8-2.8 4.8-2.8 3.2 0 5.5 3.1 4.2 6.4C19 15.6 12 20 12 20z"/></svg>',
  chev: '<svg class="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>',
};

/* ================= 状态（自动保存在浏览器里） ================= */
// 2026-11-14 审查：本地存储里有一项坏了（不是合法 JSON）时以前整页白屏；读不出就当没有
function lsJSON(k, d, st = localStorage) { try { const v = JSON.parse(st.getItem(k)); return v ?? d; } catch { return d; } }
const saved = lsJSON('studio', {});
const S = Object.assign({
  model: 'breeze', voice: null, text: '', seed: 123,
  dir: { emotion: '', level: 1, styles: [], pace: '', extra: '' },
  adv: {}, job: { maxlen: 200, pause: 0.35, pause_para: 0.8, check: true, retries: 2 },
  jobId: null, videoAutoplay: true,
}, saved);
S.dir = Object.assign({ emotion: '', level: 1, styles: [], pace: '', extra: '', useVector: false, vector: [0, 0, 0, 0, 0, 0, 0, 0] }, S.dir);
/* 这次是新打开的应用（不是切换页面 / 刷新）：生图的提示词和原图、AI 助手正在看的对话都不带过来（历史在作品页 / 对话历史里）
   桌面应用每次打开带 ?launch=编号（WebView2 关掉重开后 sessionStorage 还在，靠它判断不准）；浏览器 / 手机仍看 sessionStorage。 */
const LAUNCH = new URLSearchParams(location.search).get('launch');
if (LAUNCH) { const u = new URL(location.href); u.searchParams.delete('launch'); history.replaceState(history.state, '', u.pathname + u.search + u.hash); }
const NEW_SESSION = LAUNCH ? LAUNCH !== localStorage.getItem('appLaunch') : !sessionStorage.getItem('sessT0');
if (LAUNCH) localStorage.setItem('appLaunch', LAUNCH);
if (NEW_SESSION) {
  sessionStorage.clear();  // 上次打开时的标签页记录（这次打开的时间、私密空间标记、草稿……）都不沿用
  if (S.img) { S.img.prompt = ''; S.img.srcId = null; }
  if (S.pg) { S.pg.msgs = []; S.pg.draft = ''; S.pg.cur = null; }
  if (S.vidg) { S.vidg.prompt = ''; S.vidg.srcId = null; S.vidg.eprompt = ''; }
  sessionStorage.removeItem('igDraft'); sessionStorage.removeItem('vdDraft'); sessionStorage.removeItem('veDraft');
}
let models = [], voices = [], pollTimer = null, player = new Audio(), playingKey = null;
/* 两个空间各是各的：配音的文字 / 音色 / 任务、换声的录音、生图的提示词、播放页文件夹的展开和排序……
   在私密空间里时，普通空间的这些先放在 NSTASH 里（写进本地存储的始终是普通空间的）；
   私密空间的存在服务器上隐藏的 .data 里（见 vprefsSave），不进浏览器的本地存储，下次进私密空间还在。 */
let NSTASH = null;
const NKEYS = ['text', 'img', 'voice', 'jobId', 'ui', 'vc', 'dir', 'byModel', 'pg', 'ttsRec', 'pgHist', 'vidg'];
let persistT = 0;  // persistSoon 排着的写入（见下面）
const persist = () => {
  if (persistT) { clearTimeout(persistT); persistT = 0; }  // 这次就把排着的一起写了
  const o = { model: S.model, voice: S.voice, text: S.text, seed: S.seed, dir: S.dir, adv: S.adv, job: S.job, jobId: S.jobId, byModel: S.byModel, ui: S.ui, vc: S.vc, pg: S.pg, ttsRec: S.ttsRec, pgHist: S.pgHist, vidg: S.vidg, volume: S.volume, muted: S.muted, coverMode: S.coverMode, npBg: S.npBg, qmode: S.qmode, img: S.img, theme: S.theme, lockMin: S.lockMin, vidMode: S.vidMode, miniW: S.miniW, miniTop: S.miniTop, galLay: S.galLay, galFold: S.galFold, vsegFree: S.vsegFree, vdDual: S.vdDual, vdPcs: S.vdPcs, vdSnap: S.vdSnap, vdJobFold: S.vdJobFold, stAge: S.stAge, stKeys: S.stKeys, abSndBy: S.abSndBy, tr: S.tr, dock: S.dock, cpTop: S.cpTop, cpW: S.cpW, cpDrawerH: S.cpDrawerH, abModeV: S.abModeV, abModeI: S.abModeI, v38: 1 };  // abMode：对比方式（并排 / 滑动），以前没存、刷新就丢
  if (NSTASH) NKEYS.forEach(k => { o[k] = NSTASH[k]; });
  o.videoAutoplay = S.videoAutoplay;
  localStorage.setItem('studio', JSON.stringify(o));
  if (NSTASH) vprefsSave();
};
/* 打字、拖滑块这类高频改动：先改内存里的 S，写本地存储合并成一次（停手 0.6 秒、失焦、换页、切到后台、关页面、进出私密空间时立刻写）。
   2026-11-17 审查 P09：以前每按一个键都把整份页面状态 JSON 序列化后同步写进 localStorage，长稿时按键会卡。存的格式不变，旧草稿照常读 */
const persistSoon = () => { if (!persistT) persistT = setTimeout(() => { persistT = 0; persist(); }, 600); };
const persistFlush = () => { if (persistT) persist(); };
document.addEventListener('focusout', persistFlush, true);
document.addEventListener('visibilitychange', () => { if (document.hidden) persistFlush(); });
addEventListener('pagehide', persistFlush);
addEventListener('beforeunload', persistFlush);
const VMEM = {};  // 私密空间里的播放进度等：只在内存里
const playPos = () => JSON.parse((VAULT ? VMEM.playpos : localStorage.getItem('playpos')) || '{}');
const savePos = m => { if (VAULT) { VMEM.playpos = JSON.stringify(m); vprefsSave(); } else localStorage.setItem('playpos', JSON.stringify(m)); };
/* 私密空间自己的界面设置：改了 0.8 秒后存一次，退出私密空间前、关窗口时立刻存。
   进来时先读出来；读到之前（或者读失败）一律不存，免得把存着的设置覆盖成空的。 */
let VPREFS_OK = false, vpT = 0;
function vprefsSave(now) {
  if (!VAULT || !VPREFS_OK) return;
  clearTimeout(vpT); vpT = 0;
  const send = () => {
    vpT = 0; if (!VAULT || !VPREFS_OK) return;
    const studio = {}; NKEYS.forEach(k => { studio[k] = S[k]; });
    const body = JSON.stringify({ studio, playpos: JSON.parse(VMEM.playpos || '{}'), plscroll: PLSC.v, playSrc });
    return fetch('/api/vault/prefs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: !!now && body.length < 60000 }).catch(() => { });
  };
  if (now) return send();
  vpT = setTimeout(send, 800);
}
async function vprefsLoad() {
  VPREFS_OK = false;
  const gen = VGEN, d = await api('/api/vault/prefs').catch(() => null);
  if (gen !== VGEN || !VAULT || !d) return;
  if (d.studio) {
    NKEYS.forEach(k => { if (d.studio[k] !== undefined) S[k] = d.studio[k]; });
    // 叉掉应用 / 重启电脑后第一次进私密空间：和普通空间一样，生图 / 生视频的草稿和 AI 助手正在看的对话不带过来（对话历史还在）；
    // 同一次打开里进进出出、刷新、重启 Studio 都保留
    if (!sessionStorage.getItem('vaultSeen')) {
      if (S.img) { S.img.prompt = ''; S.img.srcId = null; }
      if (S.vidg) { S.vidg.prompt = ''; S.vidg.srcId = null; S.vidg.eprompt = ''; }
      if (S.pg) { S.pg.msgs = []; S.pg.draft = ''; S.pg.cur = null; }
      sessionStorage.removeItem('igDraft'); sessionStorage.removeItem('vdDraft'); sessionStorage.removeItem('veDraft');
    }
    if (S.vc) Object.assign(S.vc, { src: null, jobSrc: null });  // 私密空间上传的录音是临时文件，退出时已经删掉了
  }
  VMEM.playpos = JSON.stringify(d.playpos || {}); PLSC.v = d.plscroll || {};
  if (typeof d.playSrc === 'string' && d.playSrc && !PLAY_FRESH) playSrc = d.playSrc;  // 刚打开应用：不恢复上次的文件夹
  PLAY_FRESH = false;
  VPREFS_OK = true;
  sessionStorage.setItem('vaultSeen', '1');
  spaceUI();  // 读进来的是这一边的界面设置：页面马上按它显示
}
addEventListener('pagehide', () => { if (vpT) vprefsSave(true); });  // 关窗口时还有没存的：马上存
if (!saved.v38) { S.jobId = null; if (S.vc) Object.assign(S.vc, { jobId: null, jobSrc: null, src: null }); }  // 旧版本可能把私密空间的任务 / 录音记在这里：清一次

/* ================= 通用 ================= */
async function copyText(t) {  // 手机通过 http 打开时没有 navigator.clipboard：退回老办法
  if (navigator.clipboard && window.isSecureContext) { try { return await navigator.clipboard.writeText(t); } catch { } }  // 被拒绝（没有权限 / 窗口不在前台）：退回老办法，不把英文报错弹给用户
  const ta = document.createElement('textarea'); ta.value = t; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;left:-9999px;top:0';
  document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, t.length);
  const ok = document.execCommand('copy'); ta.remove();
  if (!ok) throw new Error('复制失败，请手动选中文字复制');
}
const MIC_HTTP = '通过此地址无法在手机上直接录音（浏览器仅允许 HTTPS 网页使用麦克风）。可先用手机自带的“语音备忘录”录制，再点击“上传文件”';
/* Studio 重启过（后台换了新代码）：页面还是旧的——手机上从主屏幕打开的 App 会一直留着旧页面（2026-11-08：选视频还是旧的格子）。
   发现启动编号变了，就在下次回到前台时自动刷新一次（正在用的时候不打断；草稿本来就会存着） */
let BOOT0 = null, BOOT_STALE = false;
function bootSeen(b) { if (!b) return; if (!BOOT0) BOOT0 = b; else if (b !== BOOT0) BOOT_STALE = true; }
document.addEventListener('visibilitychange', async () => {
  if (document.hidden) return;
  if (!BOOT_STALE) { try { const r = await fetch('/api/boot', { cache: 'no-store' }); bootSeen(r.headers.get('X-Studio-Boot')); } catch { return; } }
  if (BOOT_STALE && !document.hidden && sessionStorage.getItem('bootReload') !== BOOT0 + '>') { sessionStorage.setItem('bootReload', BOOT0 + '>'); location.reload(); }
});
// 2026-11-10 用户：桌面版（WebView2）里按 F5 / Ctrl+R 刷新不了页面——自己接住这两个键刷新（浏览器里效果一样）
addEventListener('keydown', e => { if (e.key === 'F5' || ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key === 'r' || e.key === 'R'))) { e.preventDefault(); location.reload(); } });
let VGEN = 0;  // 每进出一次私密空间加 1：在这之前发出、之后才回来的结果（比如音源库扫描）作废
async function api(path, opt = {}) {
  const gen = VGEN;  // 发请求时在哪个空间：结果回来时已经进出过私密空间的话，这个结果作废（永远不返回），不会显示到另一边
  const init = { method: opt.method || (opt.body !== undefined || opt.raw ? 'POST' : 'GET'), headers: { 'X-Space': VAULT ? 'v' : 'n' } };  // 服务器据此发现“页面以为在私密空间、凭证却失效了”
  if (opt.raw) { Object.assign(init.headers, opt.headers || {}); if (opt.raw.libPath) { init.body = ''; init.headers['X-Lib-Path'] = encodeURIComponent(opt.raw.libPath); } else init.body = opt.raw; }
  else if (opt.body !== undefined) { init.body = JSON.stringify(opt.body); init.headers['Content-Type'] = 'application/json'; }
  let r;
  try { r = await fetch(path, init); } catch { throw new Error('无法连接 Studio 后台（可能正在重启，请稍后再试）'); }
  bootSeen(r.headers.get('X-Studio-Boot'));
  const data = await r.json().catch(() => ({}));
  if (gen !== VGEN && !opt.anySpace) return new Promise(() => { });
  if (r.status === 409 && data.error === 'space mismatch' && !window.BOOTED) return new Promise(() => { });  // 刚打开、还没决定用哪个空间：这次不算
  if (r.status === 409 && (data.error === 'vault expired' || data.error === 'space mismatch')) { vaultCheck(); return new Promise(() => { }); }  // 私密空间已经失效：马上退出界面，这次的操作不执行
  if (!r.ok) throw new Error(data.error || ('请求失败 ' + r.status));
  return data;
}
function toast(msg, err) {
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  toastStack();
  setTimeout(() => { t.classList.add('out'); setTimeout(() => { t.remove(); toastStack(); }, 260); }, err ? 5200 : 2600);
}
function toastAct(msg, label, fn) {  // 带一个按钮的提示（比如“已清空 · 撤销”），5 秒后自己消失
  const t = document.createElement('div'); t.className = 'toast act';
  t.innerHTML = `<span>${esc(msg)}</span><button type="button">${esc(label)}</button>`;
  const bye = () => { if (t.classList.contains('out')) return; t.classList.add('out'); setTimeout(() => { t.remove(); toastStack(); }, 260); };
  t.querySelector('button').onclick = () => { fn(); bye(); };
  document.body.appendChild(t); toastStack(); setTimeout(bye, 5000);
}
/* 文本框右上角的 ×：一键清空（清错了可以撤销）。所有多行文本框和播放页的搜索框都有，手机上尤其方便 */
function clearable(el) {
  if (!el || el._clr || !el.parentNode) return; el._clr = true;
  const wrap = document.createElement('span'); wrap.className = 'clr-wrap' + (el.tagName === 'TEXTAREA' ? ' ta' : '');
  el.parentNode.insertBefore(wrap, el); wrap.appendChild(el);
  const b = document.createElement('button'); b.type = 'button'; b.className = 'clr-x'; b.title = '清空'; b.setAttribute('aria-label', '清空'); b.innerHTML = ICON.x; b.tabIndex = -1;
  wrap.appendChild(b);
  const sync = () => wrap.classList.toggle('has', !!el.value);
  ['input', 'change', 'focus', 'blur'].forEach(t => el.addEventListener(t, sync)); sync();
  b.onpointerdown = e => e.preventDefault();  // 不抢走输入框的焦点（手机上键盘不会收起来再弹出）
  b.onclick = () => {
    const old = el.value; if (!old) return;
    el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); sync(); el.focus();
    toastAct('已清空', '撤销', () => { if (!el.isConnected) return; el.value = old; el.dispatchEvent(new Event('input', { bubbles: true })); sync(); });
  };
}
new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) (n.matches?.('textarea.textarea:not(#stt-text):not(.pt-text), #play-q') ? [n] : n.querySelectorAll?.('textarea.textarea:not(#stt-text):not(.pt-text), #play-q') || []).forEach(clearable); })
  .observe(document.documentElement, { childList: true, subtree: true });
function toastStack() {  // 同时有好几条提示：从上往下依次排开（“新增文件”那条也算在内）
  const sat = toastStack.sat ??= (() => { const d = document.createElement('div'); d.style.cssText = 'position:fixed;padding-top:env(safe-area-inset-top);visibility:hidden'; document.body.appendChild(d); const v = parseFloat(getComputedStyle(d).paddingTop) || 0; d.remove(); return v; })();  // iPhone 顶部状态栏的高度
  let y = 22 + sat;
  document.querySelectorAll('.toast:not(.out)').forEach(t => { t.style.top = y + 'px'; y += t.offsetHeight + 8; });
}
/* ---------- 运行日志：实时显示后台每一步 ---------- */
const newOp = () => 'op' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const logLine = (e, still) => `<div class="ln ${e.level}${still ? ' still' : ''}"><span class="tm">${new Date(e.t * 1000).toLocaleTimeString('zh-CN', { hour12: false })}</span>${esc(e.msg)}</div>`;
function liveLog(el, tag, title = '') {
  let since = 0, stopped = false;
  const t0 = Date.now();
  el.innerHTML = `<div class="live"><div class="row between tiny"><span><span class="spinner dark" style="width:11px;height:11px;margin-right:6px;vertical-align:-1px"></span>${esc(title)}</span><span>已运行 <b class="el">0.0 秒</b></span></div><div class="console"><div class="lines"></div><span class="cursor"></span></div></div>`;
  const lines = $('.lines', el), con = $('.console', el), elT = $('.el', el);
  const timer = setInterval(() => { if (!el.isConnected) { stopped = true; return clearInterval(timer); } elT.textContent = ((Date.now() - t0) / 1000).toFixed(1) + ' 秒'; }, 100);  // 页面换掉了（离开、进出私密空间）就不再刷新
  const pull = async () => {
    const list = await api(`/api/activity?since=${since}&tag=${encodeURIComponent(tag)}`).catch(() => []);
    for (const e of list) { since = e.seq; lines.insertAdjacentHTML('beforeend', logLine(e)); }
    if (list.length) con.scrollTop = con.scrollHeight;
  };
  (async function loop() { while (!stopped && el.isConnected) { await pull(); await sleep(350); } })();
  return async (keep = true) => {
    stopped = true; clearInterval(timer); await pull();
    $('.spinner', el)?.remove(); $('.cursor', el)?.remove();
    if (!keep) el.innerHTML = '';
  };
}

function hash(s) { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
/* ================= Siri 风格音色球（移植自 SmoothUI SiriOrb，MIT，见 siri-orb.css 顶部版权说明） ================= */
const SORB_COLORS = { bg: 'oklch(92% 0.03 300)', c1: 'oklch(68% 0.21 350)', c2: 'oklch(70% 0.18 210)', c3: 'oklch(66% 0.2 285)', c4: 'oklch(72% 0.19 325)' };
const SORB_HUES = [0, 10, 20, 30, -10, 5, 15, 25];  // 每个音色在 Siri 的粉/蓝/紫范围内轻微偏移，便于区分
const SORB_SIZES = { sm: 24, '': 44, xl: 56, lg: 76 };
function sorbVars(px) {
  const small = px < 50;
  const blur = small ? Math.max(px * .008, 1) : Math.max(px * .015, 4);
  const contrast = small ? Math.max(px * .004, 1.2) : Math.max(px * .008, 1.5);
  const dot = small ? Math.max(px * .004, .05) : Math.max(px * .008, .1);
  const shadow = small ? Math.max(px * .004, .5) : Math.max(px * .008, 2);
  const mask = px < 30 ? '0%' : px < 50 ? '5%' : px < 100 ? '15%' : '25%';
  const finalContrast = px < 30 ? 1.1 : small ? Math.max(contrast * 1.2, 1.3) : contrast;
  return `--blur-amount:${blur}px;--contrast-amount:${finalContrast};--dot-size:${dot}px;--shadow-spread:${shadow}px;--mask-radius:${mask};--rim:${Math.max(px * .06, 1.5)}px`;
}
const orbVars = id => ({ hue: SORB_HUES[hash(id) % SORB_HUES.length] });
/* 静态的音色头像：首字 + 柔和的渐变底色。Siri 球只在播放条和正在播放页出现，别处都用这个（一页里不会有好几个球在动） */
const vav = (id, cls = '', key = '', label = '') => {
  // 参考 ElevenLabs 的音色球：每个音色一对柔和的渐变色，不在球上写字
  const size = cls.split(' ').find(c => c in SORB_SIZES) || '', px = SORB_SIZES[size];
  if (!id) return `<span class="vav none ${cls}" data-orbkey="${esc(key)}" style="--s:${px}px" aria-hidden="true"></span>`;
  const [c1, c2] = VAV_PAIRS[hash(id) % VAV_PAIRS.length];
  return `<span class="vav ${cls}" data-orbkey="${esc(key)}" title="${esc(label)}" style="--s:${px}px;--c1:${c1};--c2:${c2}" aria-hidden="true"></span>`;
};
const VAV_PAIRS = [['#CADCFC', '#A0B9D1'], ['#F4D9E6', '#D7A9C4'], ['#D9F2E6', '#9DD3BA'], ['#FBE7C6', '#E8B98A'], ['#E3DCFB', '#B5A6EC'],
  ['#D6EEFB', '#8EC5E6'], ['#F9D8D2', '#E3A296'], ['#E6F0C8', '#B5CF7E'], ['#DCE3EA', '#A3B1C2'], ['#F7E3F9', '#CDA2D9'], ['#CFF4F1', '#86D3CB'], ['#FCE9B6', '#E7C65F']];
/* 与之前的接口一致：orb(音色id, 尺寸类, 播放键, 名字) */
const orb = (id, cls = '', key = '', label = '') => {
  const size = cls.split(' ').find(c => c in SORB_SIZES) || '', px = SORB_SIZES[size];
  if (!id) return `<span class="sorb none ${cls}" data-orbkey="${esc(key)}" style="--orb-size:${px}px"><span class="sorb-disc">${esc(label === '无' ? '' : label)}</span></span>`;
  const { hue } = orbVars(id), c = SORB_COLORS;
  const live = key === 'now' ? ' sorb-live' : '';
  return `<span class="sorb ${cls}${live}" data-orbkey="${esc(key)}" title="${esc(label)}" style="--orb-size:${px}px;--bg:${c.bg};--c1:${c.c1};--c2:${c.c2};--c3:${c.c3};--c4:${c.c4};${sorbVars(px)};--animation-duration:${18 + hash(id) % 6}s">
    <span class="sorb-glow" style="filter:blur(calc(var(--orb-size) * .28)) hue-rotate(${hue}deg)"></span>
    <span class="sorb-disc" style="filter:hue-rotate(${hue}deg)"><span class="sorb-layer sorb-sheen"></span><span class="sorb-layer sorb-rim"></span></span></span>`;
};

const VZ = { key: null, audio: null, an: null, fbuf: null, level: 0 };
let actx = null;
const vizNodes = new WeakMap();
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* 只在有声音播放时才运行：把实时音量交给对应的音色球（放大 + 收紧模糊 + 光晕变亮） */
let vizRaf = 0;
function vizLoop() {
  vizRaf = 0;
  const on = VZ.key && VZ.audio && !VZ.audio.paused && !VZ.audio.ended;
  $$('.sorb.playing, .vav.playing').forEach(o => { if (!on || o.dataset.orbkey !== VZ.key) { o.classList.remove('playing'); o.style.setProperty('--amp', 0); } });
  if (!on) { VZ.key = null; VZ.level = 0; return; }
  if (VZ.an) {
    VZ.an.getByteFrequencyData(VZ.fbuf);
    let sum = 0; const n = Math.min(48, VZ.fbuf.length);
    for (let k = 1; k < n; k++) sum += VZ.fbuf[k];
    const lvl = Math.min(1, Math.pow(sum / (n - 1) / 255 * 2.2, 1.2));
    VZ.level = VZ.level * .7 + lvl * .3;
  }
  $$('.sorb, .vav').filter(o => o.dataset.orbkey === VZ.key).forEach(o => { o.classList.add('playing'); o.style.setProperty('--amp', VZ.level.toFixed(3)); });
  vizRaf = requestAnimationFrame(vizLoop);
}

/* ================= 播放器：替换浏览器自带的 <audio controls>（窄卡片里进度条会被挤得很小） ================= */
const fmtT = s => { s = Math.max(0, s || 0); const m = Math.floor(s / 60), x = Math.floor(s % 60); return `${m}:${String(x).padStart(2, '0')}`; };
const apHtml = (url, key = '', opts = {}) =>
  `<div class="ap${opts.mini ? ' mini' : ''}" ${opts.id ? `id="${opts.id}"` : ''} data-src="${esc(url)}" data-orbkey="${esc(key)}"${opts.autoplay ? ' data-autoplay="1"' : ''}${opts.lazy ? ` data-lazy="1" data-dur="${opts.dur || 0}"` : ''}${opts.title ? ` data-title="${esc(opts.title)}"` : ''}${opts.sub ? ` data-sub="${esc(opts.sub)}"` : ''}${opts.orb ? ` data-orb="${esc(opts.orb)}"` : ''}${opts.subs ? ` data-subs="${esc(opts.subs)}"` : ''}>
    <button class="ap-btn" type="button" aria-label="播放">${ICON.play}</button>
    <div class="ap-track"><div class="ap-fill"></div><div class="ap-knob"></div></div>
    <span class="ap-time">${opts.lazy && opts.dur ? fmtT(opts.dur) : '0:00'}</span></div>`;
/* 全站音量：左下角一个滑杆，所有播放器（成品、试听、分段、对比）都跟着它 */
const vol = () => S.volume ?? 1;
function applyVolume() {
  const v = S.muted ? 0 : vol();
  if (player) player.volume = v;
  $$('.ap').forEach(el => { if (el._a) el._a.volume = v; });
  (window._extraAudios || []).forEach(a => { a.volume = v; });
  qAudio.volume = v;  // 播放列表（底栏）正在放的那个
  window.Sound?.volume(v);  // 叠加音轨
  $$('video.vsync').forEach(x => vsApply(x));  // 生视频的预览 / 详情：跟着播放栏
  $$('video:not(.vsync), audio').forEach(mediaVol);  // 其余页面里的视频 / 声音（见 mediaVol）
}
/* 页面里带控制条的视频：一打开就用播放栏的音量和静音；在视频上调音量 / 点静音，播放栏也跟着变（反过来也一样）。
   auto = 预览自动播放：播放栏正在放东西时先静音，免得两边的声音叠在一起（自己点开视频的声音就不再管） */
function vsApply(v) {
  const m = !!S.muted || !!v._vsAuto;
  if (v._vsSet && v._vsSet[0] === vol() && v._vsSet[1] === m) return;
  v._vsSet = [vol(), m]; v.volume = vol(); v.muted = m;
}
function vidVolSync(v, auto) {
  if (!v) return;
  v._vsAuto = !!auto && !!PB.a && !PB.a.paused; v.classList.add('vsync'); vsApply(v);
  if (v._vs) return; v._vs = 1;
  v.addEventListener('volumechange', () => {
    const [sv, sm] = v._vsSet || [];
    if (Math.abs(v.volume - sv) < .005 && v.muted === sm) return;  // 是我们自己设的
    if (!v.muted) v._vsAuto = false;  // 自己打开了声音
    const nv = Math.round(v.volume * 100) / 100;
    if (Math.abs(nv - vol()) >= .005) S.volume = nv;
    if (v.muted !== !!S.muted) { S.muted = v.muted; if (!S.muted && vol() === 0) S.volume = .8; }
    v._vsSet = [vol(), v.muted]; persist(); applyVolume(); window.volPaint?.();
  });
}
/* 兜底（2026-11-09 用户：全部视频里格子上直接播放时不跟应用音量，是系统最大音量）：页面里任何视频 / 声音一开始播放就用应用的音量和静音。
   带控制条的视频接上双向同步（在视频上调音量，左边也跟着变）；本来就静音的预览（悬停预览、对比里没选中的那格）不去打开声音，
   只是应用静音时一起静音，取消静音时把这里静音的那些还原 */
function mediaVol(m) {
  if (!(m instanceof HTMLMediaElement) || m === qAudio || m === player) return;
  if (m.classList.contains('vsync')) return vsApply(m);
  if (m.controls && !m.muted) return vidVolSync(m);  // 本来静音的（比如先静音再自己点开声音的预览）不在这里打开声音
  if (Math.abs(m.volume - vol()) > .005) m.volume = vol();
  if (S.muted && !m.muted) { m.muted = true; m._gm = 1; } else if (!S.muted && m._gm) { m.muted = false; m._gm = 0; }
}
document.addEventListener('play', e => mediaVol(e.target), true);

/* 自动视频预览统一走这里；点击播放、连续播放和小窗接续保持各自的播放行为。
   标记只保留到用户操作视频为止，关闭自动播放时仅暂停仍由程序自动播放的预览。 */
const videoAutoplay = () => S.videoAutoplay !== false;
function videoPreviewPlay(v, manual = false) {
  if (!v) return;
  if (!v._previewBound) {
    v._previewBound = true;
    const takeOver = () => { delete v.dataset.autoPreview; v.autoplay = false; };
    v.addEventListener('pointerdown', takeOver);
    v.addEventListener('keydown', takeOver);
  }
  v.autoplay = false;
  if (!manual && !videoAutoplay()) return;
  if (manual) delete v.dataset.autoPreview; else v.dataset.autoPreview = '1';
  v.play().catch(() => { });
}
function setVideoAutoplay(on) {
  S.videoAutoplay = !!on; persist();
  if (!on) $$('video[data-auto-preview]').forEach(v => { v.autoplay = false; v.pause(); delete v.dataset.autoPreview; });
}

/* 只在图标真的变了才替换：进度每 0.2 秒刷新一次，如果每次都重画按钮里的图标，按下鼠标的瞬间图标被换掉，这次点击就会丢 */
const setIcon = (btn, name) => { if (btn && btn.dataset.icon !== name) { btn.dataset.icon = name; btn.innerHTML = ICON[name]; } };
const playErr = e => {
  if (!e || e.name === 'AbortError') return;
  const why = e.name === 'NotAllowedError' ? '浏览器要求先点击页面才能播放声音' : e.name === 'NotSupportedError' ? '无法播放此格式（或仍在转换中）' : e.message;
  toast('无法播放：' + why, true);
};
/* ================= 全站播放控制条（参考 Apple Music 底栏）=================
   所有音频都登记到这里：同一时间只放一个，开始播放新的就自动暂停旧的；底栏显示正在放的是什么，可以暂停、拖动、快退快进、调速度和音量。 */
const PB = { a: null, all: new Set(), rate: 1 };
const RC = { ctl: false, st: null, stAt: 0, mk: '', loop: false, gone: true, keep: null, keepT: 0, pollT: 0, lastRep: 0, armed: false, qsig: '', qv: 0, queue: null, qvSeen: null, auto: false, act: 0, noAuto: false, quiet: 0, kel: null, primed: false, kerr: '', rpos: {}, parked: 0 };  // 私密空间里用电脑控制手机播放：见“遥控播放”那一节
/* 封面：默认用 Siri 球；设置里切到“文件自带封面”后，有封面的音频显示自己的封面，没有的仍用 Siri 球 */
const coverUrl = path => '/media/cover/' + path.split('/').map(encodeURIComponent).join('/');
function vinylHtml(m, key = '') {
  return `<span class="vinyl"><span class="vinyl-disc"></span><span class="vinyl-label">${orb(m.orb || m.title || 'pb', '', key, m.title || '♪')}</span><span class="vinyl-hole"></span></span>`;
}
function npArtHtml(m, key = '') {  // 全屏播放页：文件封面模式且有封面 → 封面；否则 → 黑胶
  { const x = window.NPL?.art(m, key); if (x != null) return x; }  // 选了别的外观（npstyle.js）：由那里画
  if (S.coverMode === 'file' && hasCov(m)) return `<span class="art np-cover"><img src="${esc(m.cover)}" alt="" onerror="${COV_ERR};this.closest('#np-art').innerHTML=this.closest('#np-art').dataset.vinyl"></span>`;
  return vinylHtml(m, key);
}
/* 列表行的封面：文件封面模式 → 封面；Siri 球模式 → 只有正在播放的那一行是球，其他行是很淡的音频 / 视频小图标 */
/* 没有封面的文件：第一次取不到就记住，之后列表重画、换行高亮时不再一遍遍去要（以前每次重画都请求一次、每次都 404） */
const NOCOV = new Set();
const hasCov = m => !!m.cover && !NOCOV.has(m.cover);
const COV_ERR = `NOCOV.add(this.getAttribute('src'))`;
function rowArt(x, isCur, px) {
  const blank = `<span class="art-ic">${x.video ? ICON.film : ICON.note}</span>`;
  const img = hasCov(x) ? `<img src="${esc(x.cover)}" alt="" loading="lazy" decoding="async" onerror="${COV_ERR};this.remove()">` : '';
  return `<span class="art art-blank${isCur ? ' cur' : ''}" style="--s:${px}px">${blank}${img}${isCur ? '<span class="art-eq"><span class="eq"><i></i><i></i><i></i></span></span>' : ''}</span>`;
}
/* 播放条和侧栏里“正在播放”的那个（2026-11-17 用户：Siri 球太炫彩 → 选了方案 D + E，docs/设计稿/播放球方案_1117.html）：
   播放卡片 = 圆形封面（没有封面：中性底 + 音符），不动；侧栏 = 深色玻璃圆里三根音柱，只在播放卡片收起来、并且在播放时跳（两边不同时动） */
const NOW_NOTE = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8.6 5.5 19.6 3v12.4h-1.7V7.1l-7.6 1.75V18H8.6z"/><ellipse cx="6.75" cy="18" rx="3.15" ry="2.35" transform="rotate(-22 6.75 18)"/><ellipse cx="16.05" cy="15.45" rx="3.15" ry="2.35" transform="rotate(-22 16.05 15.45)"/></svg>';
function nowCardArt(m, px) {
  const img = S.coverMode === 'file' && hasCov(m);
  return `<span class="now-cov${img ? '' : ' none'}" style="--s:${px}px">${img ? `<img src="${esc(m.cover)}" alt="" loading="lazy" onerror="${COV_ERR};this.parentElement.classList.add('none');this.remove()">` : ''}${NOW_NOTE}</span>`;
}
const nowBarsArt = px => `<span class="now-bars" style="--s:${px}px"><span class="eq"><i></i><i></i><i></i></span></span>`;
function artHtml(m, px, key = '') {
  const o = `<span class="art-orb">${orb(m.orb || m.title || 'pb', '', key, m.title || '♪')}</span>`;
  const useImg = S.coverMode === 'file' && hasCov(m);
  return `<span class="art${useImg ? '' : ' noimg'}" style="--s:${px}px">${useImg ? `<img src="${esc(m.cover)}" alt="" loading="lazy" onerror="${COV_ERR};this.parentElement.classList.add('noimg')">` : ''}${o}</span>`;
}
const RATES = [1, 1.25, 1.5, 2, 0.75];
// 键盘快进快退（2026-11-18 用户）：只动主音轨，叠加的音轨留在原来的位置——它们的“错开”加上这次跳的秒数
function keySeek(a, t) {
  const t0 = a.currentTime; a.currentTime = t;
  try { if (a === sndMain()) Sound.shiftLayers(a.currentTime - t0); } catch { }
}
function pbRegister(a, meta) {
  a._pbMeta = meta;
  if (PB.all.has(a)) return;
  PB.all.add(a);
  a.addEventListener('play', () => pbTake(a));
  ['timeupdate', 'pause', 'ended', 'loadedmetadata', 'durationchange', 'seeked'].forEach(ev => a.addEventListener(ev, () => { if (PB.a === a) pbPaint(); }));
  vSmooth(a, () => { if (PB.a === a && !extOn()) pbLite(); });  // 播放时底栏的进度条、时间每一帧都走（不再 0.25 秒跳一下）
}
// 2026-11-16 用户（手机）：40 多分钟的音频，进度条拖到 3 分钟，松手却到了 5 分钟。
// 1) 拖的时候用 a.duration 算位置，进度条显示用的是“有限的 duration，否则文件记下的时长”：转码 / 流式的文件 a.duration 是 Infinity 或者估的，两边差得很多
// 2) 手指每动一下就跳一次（currentTime），几十次跳转叠在一起，最后停在哪要看哪一次最后完成
// 现在：时长和显示用同一个；手指拖的时候进度条和时间跟着手指，也边拖边跳（听着找位置，用户 11-16 第二次），但最多 0.15 秒跳一次、上一次跳完才跳下一次；
// 松手再准确跳一次到松手的位置，跳到之前进度条停在那里。鼠标拖照旧每动一下就跳
const pbDur = a => a.duration && isFinite(a.duration) ? a.duration : +(a._dur || 0);
const pbCur = a => PB.scrub ? PB.scrub.t : (a.currentTime || 0);
/* 2026-11-17 UI 审查 U08：进度条能用键盘、读屏能读——slider 角色、名字、“当前 / 总时长”；←→ 5 秒、PageUp / PageDown 30 秒、Home / End */
function scrubAria(tr, c, d) {
  if (!tr) return; const v = `${fmtT(c)} / ${fmtT(d || 0)}`;
  if (tr.getAttribute('aria-valuetext') !== v) { tr.setAttribute('aria-valuetext', v); tr.setAttribute('aria-valuenow', String(Math.round(c))); tr.setAttribute('aria-valuemax', String(Math.round(d || 0))); }
}
function bindScrub(tr, host) {
  if (!tr) return; let drag = false, live = false, last = 0;
  tr.setAttribute('role', 'slider'); tr.tabIndex = 0; tr.setAttribute('aria-label', '播放进度'); tr.setAttribute('aria-valuemin', '0'); scrubAria(tr, 0, 0);
  const at = e => { const a = PB.a; if (!a) return null; const r = tr.getBoundingClientRect(), p = Math.min(1, Math.max(0, (e.clientX - r.left) / (r.width || 1))), d = extOn() ? PB.ext.d : pbDur(a); return d ? p * d : null; };
  const go = t => { const a = PB.a; if (t == null || !a) return; if (extOn()) { PB.ext.t = t; extCmd({ seek: t }); } else a.currentTime = t; };
  const show = t => { if (t == null) return; if (live) { go(t); PB.scrub = null; } else { PB.scrub = { t }; const a = PB.a, now = performance.now(); if (a && (extOn() || !a.seeking) && now - last > 150) { last = now; go(t); } } pbPaint(); };
  tr.addEventListener('pointerdown', e => { drag = true; live = e.pointerType !== 'touch'; last = 0; tr.setPointerCapture(e.pointerId); host?.classList.add('drag'); show(at(e)); });
  tr.addEventListener('pointermove', e => { if (drag) show(at(e)); });
  const end = e => { if (!drag) return; drag = false; host?.classList.remove('drag'); if (live) return;
    const t = (e.type === 'pointerup' ? at(e) : null) ?? PB.scrub?.t, a = PB.a; if (t == null || !a) { PB.scrub = null; return pbPaint(); }
    go(t); if (extOn()) { PB.scrub = null; return pbPaint(); }
    PB.scrub = { t }; const done = () => { if (PB.scrub?.t === t) { PB.scrub = null; pbPaint(); } }; a.addEventListener('seeked', done, { once: true }); setTimeout(done, 1500); pbPaint(); };
  tr.addEventListener('pointerup', end); tr.addEventListener('pointercancel', end);
  tr.addEventListener('keydown', e => {
    const a = PB.a; if (!a) return; const d = extOn() ? PB.ext.d : pbDur(a), c = extOn() ? PB.ext.t || 0 : pbCur(a);
    const st = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5, PageUp: 30, PageDown: -30 }[e.key];
    const t = st != null ? c + st : e.key === 'Home' ? 0 : e.key === 'End' && d ? d - .5 : null; if (t == null) return;
    e.preventDefault(); e.stopPropagation(); const to = Math.max(0, d ? Math.min(d - .05, t) : t); if (extOn()) go(to); else keySeek(a, to); pbPaint();
  });
}
function pbLite() {  // 只刷进度条和时间（每一帧都调，别的不动）
  const a = PB.a; if (!a) return;
  const d = pbDur(a), c = pbCur(a), pct = d ? Math.min(100, c / d * 100) : 0;
  const f = $('#pb-fill'), k = $('#pb-knob'); if (f) f.style.width = pct + '%'; if (k) k.style.left = pct + '%';
  { const bar = $('#pbar'), p2 = Math.round(pct * 2) / 2; if (bar && bar._p !== p2) { bar._p = p2; bar.style.setProperty('--pbp', p2 + '%'); } }  // 手机：封面外圈的进度环（只在变了 0.5% 时写）
  const t0 = $('#pb-t0'), t1 = $('#pb-t1'), s0 = fmtT(c), s1 = d ? '-' + fmtT(Math.max(0, d - c)) : '0:00';
  if (t0 && t0.textContent !== s0) { t0.textContent = s0; scrubAria($('#pb-track'), c, d); } if (t1 && t1.textContent !== s1) t1.textContent = s1;
}
function pbTake(a) {
  if (RC.ctl && a !== qAudio) rcPark();  // 正在控制手机时在电脑上放了别的：手机先暂停，播放条回到电脑自己的（控制保持开着，再点手机图标接着放）
  if (MINI_OUT === 'win' && a !== qAudio) appReturn('close');
  for (const x of PB.all) {
    if (x === a) continue;
    if (!x.paused) x.pause();
    if (x._el && !x._el.isConnected) PB.all.delete(x);  // 页面上已经没有的播放器不再记着
  }
  a.playbackRate = PB.rate; pbLayout();
  const changed = PB.a !== a; PB.a = a; pbPaint(changed);
  try { Sound.setMainEl(sndMain()); } catch { }  // 叠加的音轨跟着现在放的这个走
  clearInterval(PB.iv); PB.iv = setInterval(() => { if (!PB.a || PB.a.paused) return clearInterval(PB.iv); pbPaint(); }, 200);
}
function pbPaint(withMeta) {
  const a = PB.a, bar = $('#pbar'); if (!bar) return;
  try { mkPaint(); } catch { }  // 书签的小点（只在换了文件 / 时长 / 书签时重画）
  bar.classList.toggle('idle', !a);
  $('#pb-fab')?.classList.toggle('on', !!a && !(extOn() ? PB.ext?.paused : a.paused));
  $$('.pb-q', bar).forEach(b => b.hidden = !(a && a === qAudio && (PB.q || RC.ctl)));
  { const sh = $('#pb-shuffle'), rp = $('#pb-repeat');  // 随机 / 循环（2026-11-17 播放条照 Apple Music 重排）
    if (sh) { sh.classList.toggle('on', !!S.qmode.shuffle); sh.disabled = RC.ctl; }
    if (rp) { if (rp.dataset.m !== S.qmode.repeat) { rp.dataset.m = S.qmode.repeat; rp.innerHTML = repeatIcon(S.qmode.repeat); rp.title = REPEAT[S.qmode.repeat][0]; } rp.classList.toggle('on', S.qmode.repeat !== 'off'); rp.disabled = RC.ctl; } }
  bar.classList.toggle('rc', RC.ctl); document.body.classList.toggle('rc-ctl', RC.ctl);  // 控制手机时：全屏页的音效按钮也藏起来
  const vb = $('#pb-video'); if (vb) { vb.hidden = RC.ctl || !(a === qAudio && PB.meta?.video); vb.classList.toggle('on', !!MINI_OUT || !MINI.hidden); }
  const ex = extOn() ? PB.ext : null, paused = ex ? ex.paused : a?.paused;  // 视频在应用外的小窗口里放：显示它的进度
  { const pp = $('[data-pb="play"]', bar), st = a && !paused ? 'pause' : 'play'; if (pp.dataset.ap !== st) { pp.dataset.ap = st; pp.innerHTML = NP_GLYPH[st]; } }  // 实心圆角图标，和全屏播放页一样
  if (!a) {
    document.body.classList.remove('is-playing', 'vid-playing'); bar.classList.remove('playing');
    const f = $('#pb-fill'), k = $('#pb-knob'); if (f) f.style.width = '0%'; if (k) k.style.left = '0%';
    $('#pb-t0') && ($('#pb-t0').textContent = '0:00'); $('#pb-t1') && ($('#pb-t1').textContent = '0:00');
    if (CP) cpPaint(true); tbSync(false, false); return;
  }
  if (withMeta) {
    let m = {}; try { m = a._pbMeta ? a._pbMeta() : {}; } catch { }
    $('#pb-title').textContent = m.title || '音频';
    $('#pb-sub').textContent = m.sub || '';
    $('#pb-art').innerHTML = nowCardArt(m, 40);
    const fa = $('#pb-fab-art'); if (fa) fa.innerHTML = nowBarsArt(28);
    PB.meta = m; npPaint(true); mediaMeta(m);
  }
  bar.classList.toggle('playing', !paused); document.body.classList.toggle('is-playing', !paused);
  document.body.classList.toggle('vid-playing', !paused && a === qAudio && !!PB.meta?.video);  // 放视频时 Siri 球暂停流动（见 app.css）
  const d = ex ? ex.d || a.duration || 0 : pbDur(a), c = (PB.scrub ? PB.scrub.t : ex ? ex.t : a.currentTime) || 0, pct = d ? Math.min(100, c / d * 100) : 0;
  $('#pb-fill').style.width = pct + '%'; $('#pb-knob').style.left = pct + '%';
  $('#pb-t0').textContent = fmtT(c); $('#pb-t1').textContent = d ? '-' + fmtT(Math.max(0, d - c)) : '0:00';
  npPaint(); mediaState(a, paused, c, d);
  if (CP) cpPaint(withMeta);
  tbSync(true, !paused);
}
let tbKey = '';
function tbSync(has, playing) {  // 任务栏缩略图上的 上一首 / 播放 / 下一首（桌面应用里才有）：状态变了才告诉窗口
  const k = (has ? 1 : 0) + ':' + (playing ? 1 : 0);
  if (k === tbKey || !window.pywebview?.api?.tb_state) return;
  tbKey = k; window.pywebview.api.tb_state(!!playing, !!has).catch(() => { });
}
window.tbCmd = c => { if (c === 'prev') qPrev(); else if (c === 'next') qNext(false); else $('[data-pb="play"]')?.click(); };
/* 系统媒体控制：键盘上的 播放/暂停、上一首、下一首 键；Windows 音量浮窗 / 锁屏上显示正在播放的内容和封面 */
const MS = 'mediaSession' in navigator ? navigator.mediaSession : null;
function mediaMeta(m) {
  if (!MS || !window.MediaMetadata) return;
  try {
    if (VAULT) { MS.metadata = new MediaMetadata({ title: 'Studio', artist: '', album: '', artwork: [{ src: '/static/app-icon-512.png', sizes: '512x512', type: 'image/png' }] }); return; }
    const art = m.cover && S.coverMode === 'file' ? [{ src: new URL(m.cover, location.href).href, sizes: '512x512' }] : [{ src: '/static/app-icon-512.png', sizes: '512x512', type: 'image/png' }];
    MS.metadata = new MediaMetadata({ title: m.title || '音频', artist: m.sub || 'Studio', album: 'Studio', artwork: art });
  } catch { }
}
let msLast = 0;
function mediaState(a, paused, c, d) {
  if (!MS) return;
  MS.playbackState = paused ? 'paused' : 'playing';
  if (Date.now() - msLast < 1000 || !d || !isFinite(d)) return;
  msLast = Date.now();
  try { MS.setPositionState({ duration: d, position: Math.min(d, Math.max(0, c)), playbackRate: PB.rate || 1 }); } catch { }
}
if (MS) {
  const h = (k, f) => { try { MS.setActionHandler(k, f); } catch { } };
  const btn = n => $(`[data-pb="${n}"]`)?.click();
  h('play', () => { if (!PB.a || PB.a.paused) btn('play'); }); h('pause', () => { if (PB.a && !PB.a.paused) btn('play'); });
  h('previoustrack', () => btn('prev')); h('nexttrack', () => btn('next'));
  h('seekbackward', () => btn('back')); h('seekforward', () => btn('fwd'));
  h('seekto', e => { if (extOn()) return extCmd({ seek: e.seekTime }); if (PB.a) PB.a.currentTime = e.seekTime; });
  h('stop', () => { if (PB.a && !PB.a.paused) btn('play'); });
}
function pbLayout() {
  const bar = $('#pbar'), main = $('#main'); if (!bar || !main) return;
  const ref = main.querySelector(':scope > .page-head') || main;
  const r = ref.getBoundingClientRect(), cs = getComputedStyle(ref);
  const left = r.left + (ref === main ? parseFloat(cs.paddingLeft) : 0), right = r.right - (ref === main ? parseFloat(cs.paddingRight) : 0);
  if (right - left < 300) return;
  // 窗口宽、播放条只占内容区一部分时：按整个窗口居中（看着在屏幕正中）；窗口窄、播放条快占满内容区时：按内容区居中（两边留白一样）
  const w = Math.min(880, right - left), k = Math.min(1, Math.max(0, (w / (right - left) - .6) / .3));
  const xWin = Math.min(Math.max(innerWidth / 2 - w / 2, left), right - w), xMain = left + (right - left - w) / 2;
  const x = xWin + (xMain - xWin) * k;
  bar.style.left = x + 'px'; bar.style.width = w + 'px'; bar.style.right = 'auto';
  const qp = $('#qpanel'); if (qp) { qp.style.right = Math.max(16, innerWidth - (x + w)) + 'px'; }
  const sp = $('#spanel'); if (sp) { sp.style.right = Math.max(16, innerWidth - (x + w)) + 'px'; }
  miniLayout();  // 播放条挪了位置（窗口变大变小）：贴在它上面的视频跟着走
  // 2026-11-18 用户：播放条会遮住一部分文件。列表滚到底时要能露出最后一行：播放条盖住了底下多高，就给列表留多高（收起时 0）
  const br = bar.getBoundingClientRect(), shown = !document.body.classList.contains('pb-min') && br.height > 0 && getComputedStyle(bar).display !== 'none';
  // 播放页列表被播放条盖住的那一截（列表底边 - 播放条顶边）：列表底部留出这么多，滚到底最后一行不被挡；没盖住就不留
  { const rl = document.querySelector('.main[data-page="play"] .pl-rows'), lb = rl?.getBoundingClientRect().bottom || 0;
    document.documentElement.style.setProperty('--pb-cover', shown && lb > br.top ? Math.round(lb - br.top + 12) + 'px' : '0px'); }
}
/* 收起播放条：缩成右下角的小圆按钮（手机上在底部导航上面），正在放的时候外圈转；点一下展开。记住上次的状态 */
function pbMin(on, save = true) {
  document.body.classList.toggle('pb-min', !!on);
  const fab = $('#pb-fab'); if (fab) fab.hidden = !on;
  if (save) { S.ui = { ...(S.ui || {}), pbMin: !!on }; persist(); }
  if (on) { qPanelClose?.(); try { spClose(); } catch { } }
  requestAnimationFrame(() => { try { fitScript(); fitPages(); if (!mdrag && !mrz) miniSync(); miniLayout(); pbLayout(); } catch { } });  // 收起 / 展开播放条：视频在“从播放条展开”和悬浮小窗之间切换
}
function bindPlayerBar() {
  $('#pb-hide').onclick = e => { e.stopPropagation(); pbMin(true); };
  $('#pb-fab').onclick = () => pbMin(false);
  pbMin(!!S.ui?.pbMin, false);
  const bar = $('#pbar'); if (!bar) return;
  pbLayout(); addEventListener('resize', pbLayout);
  if (window.ResizeObserver) new ResizeObserver(() => { if (!window.fsHold?.()) pbLayout(); }).observe($('#main'));
  $('[data-pb="play"]', bar).onclick = () => { const a = PB.a; if (!a) return; if (extOn()) return extCmd({ toggle: true }); rcPrime(); a.paused ? a.play().catch(playErr) : a.pause(); };
  $('[data-pb="prev"]', bar).onclick = () => qPrev();
  $('[data-pb="next"]', bar).onclick = () => qNext(false);
  $('#pb-shuffle').onclick = () => { qSetShuffle(!S.qmode.shuffle); pbPaint(); };
  $('#pb-repeat').onclick = () => { qCycleRepeat(); pbPaint(); };
  $('#pb-more').onclick = e => {  // ⋯：播放速度（以前是一直显示的“1×”）、打开全屏播放
    e.stopPropagation();
    ctxMenu({ anchor: e.currentTarget }, [{ group: '播放速度' }, ...[...RATES].sort((x, y) => x - y).map(r => ({ label: r + '×', checked: PB.rate === r, on: () => pbSetRate(r) })), '-', { label: '打开全屏播放', on: () => npOpen() }]);
  };
  $('#pb-now').onclick = () => { if (PB.a) npOpen(); };  // 控制手机时也能打开：进度、字幕跟着手机
  $('#pb-now').onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && PB.a) { e.preventDefault(); npOpen(); } };  // 键盘也能打开
  $('#pb-rc').onclick = () => RC.ctl ? rcStop(true, true) : rcStart();
  $('#pb-queue').onclick = () => qPanelToggle();
  $('#pb-fx').onclick = () => spToggle();
  $('#np-fx').onclick = () => spToggle();
  spBtnPaint();
  $('#pb-video').onclick = () => { if (MINI_OUT === 'win') return appReturn('fold'); if (MINI_OUT === 'pip') { pipRestore(); MINI._dismissed = true; return miniSync(); } MINI._dismissed = !MINI.hidden; miniSync(); };
  $('[data-pb="back"]', bar).onclick = () => { if (extOn()) return extCmd({ seekBy: -10 }); if (PB.a) { PB.a.currentTime = Math.max(0, PB.a.currentTime - 10); pbPaint(); } };
  $('[data-pb="fwd"]', bar).onclick = () => { if (extOn()) return extCmd({ seekBy: 10 }); const a = PB.a; if (a) { a.currentTime = Math.min((a.duration || 1e9) - 0.05, a.currentTime + 10); pbPaint(); } };
  bindScrub($('#pb-track'), bar);
  $('#pb-rate').onclick = () => pbSetRate(RATES[(RATES.indexOf(PB.rate) + 1) % RATES.length]);
  window.pbSetRate = r => {
    PB.rate = r;
    $('#pb-rate').textContent = PB.rate + '×'; $('#pb-rate').classList.toggle('on', PB.rate !== 1);
    if (PB.a) PB.a.playbackRate = PB.rate;
    if (extOn()) extCmd({ rate: PB.rate });
  };
  pbPaint();
}
function apInit(root = document) {
  $$('.ap', root).forEach(el => {
    if (el._a) return;
    // 分段列表里的小播放器先不加载，点播放才去取音频，避免一次请求上百个文件
    const a = new Audio(); a.preload = el.dataset.lazy ? 'none' : 'metadata'; a.src = el.dataset.src; el._a = a;
    a.volume = S.muted ? 0 : vol(); a._el = el; a._dur = el.dataset.dur; a.dataset.orbkey = el.dataset.orbkey || '';
    pbRegister(a, () => ({ title: el.dataset.title || (el.closest('.card, .modal')?.querySelector('.card-title, .tt, b')?.textContent || $('.page-title')?.textContent || '音频').trim(),
      sub: el.dataset.sub || $('.page-title')?.textContent || '', orb: el.dataset.orb, subsKey: el.dataset.subs }));
    const btn = $('.ap-btn', el), fill = $('.ap-fill', el), knob = $('.ap-knob', el), time = $('.ap-time', el), track = $('.ap-track', el);
    let raf = 0, dragging = false;
    const paint = () => {
      const d = a.duration || +el.dataset.dur || 0, p = d ? Math.min(1, a.currentTime / d) : 0;
      fill.style.width = p * 100 + '%'; knob.style.left = p * 100 + '%';
      time.textContent = d ? `${fmtT(a.currentTime)} / ${fmtT(d)}` : fmtT(a.currentTime);
    };
    const loop = () => { paint(); if (!a.paused) raf = requestAnimationFrame(loop); };
    a.addEventListener('loadedmetadata', paint);
    a.addEventListener('play', () => {
      $$('.ap').forEach(o => { if (o !== el && o._a && !o._a.paused) o._a.pause(); });
      if (player && !player.paused) player.pause();
      btn.innerHTML = ICON.pause; el.classList.add('on'); attachViz(a, el.dataset.orbkey);
      cancelAnimationFrame(raf); raf = requestAnimationFrame(loop);
    });
    const stop = () => { btn.innerHTML = ICON.play; el.classList.remove('on'); paint(); };
    a.addEventListener('pause', stop); a.addEventListener('ended', stop);
    btn.onclick = () => (a.paused ? a.play().catch(playErr) : a.pause());
    const seekTo = e => {
      const r = track.getBoundingClientRect(), p = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      const d = a.duration || +el.dataset.dur;
      if (d) { a.currentTime = p * d; paint(); }
    };
    track.addEventListener('pointerdown', e => { dragging = true; track.setPointerCapture(e.pointerId); el.classList.add('drag'); seekTo(e); });
    track.addEventListener('pointermove', e => { if (dragging) seekTo(e); });
    const end = () => { dragging = false; el.classList.remove('drag'); };
    track.addEventListener('pointerup', end); track.addEventListener('pointercancel', end);
    if (el.dataset.autoplay) a.play().catch(() => {});
  });
}
new MutationObserver(() => { clearTimeout(apInit._t); apInit._t = setTimeout(() => apInit(), 20); }).observe(document.documentElement, { childList: true, subtree: true });

/* ================= 过渡动画：所有展开 / 收起都平滑进行 ================= */
const EASE = 'cubic-bezier(.2,.7,.2,1)';
function toggleDetails(d, open) {
  if (!d) return;
  const sum = d.querySelector(':scope > summary');
  d._target = open;
  if (reduceMotion || !sum || !d.isConnected) { d.open = open; return; }
  const from = d.getBoundingClientRect().height;
  if (d._anim) { d._anim.onfinish = null; d._anim.cancel(); d._anim = null; }
  d.open = true;
  const to = open ? d.scrollHeight : sum.getBoundingClientRect().height;
  d.style.overflow = 'hidden';
  const anim = d.animate({ height: [from + 'px', to + 'px'] }, { duration: Math.min(380, 200 + Math.abs(to - from) * .2), easing: EASE });
  if (open) [...d.children].filter(x => x !== sum).forEach(x => x.animate({ opacity: [0, 1], transform: ['translateY(-6px)', 'none'] }, { duration: 260, easing: EASE }));
  d._anim = anim;
  const done = () => { if (d._anim !== anim) return; d._anim = null; anim.cancel(); d.style.overflow = ''; d.open = d._target; };
  anim.onfinish = done;
  setTimeout(done, 450);  // 页面在后台时浏览器不派发动画事件，定时兜底保证一定能结束
}
document.addEventListener('click', e => {
  const sum = e.target.closest('summary');
  if (!sum || e.target.closest('button, a, input, select, textarea')) return;
  const d = sum.parentElement;
  if (d?.tagName !== 'DETAILS') return;
  e.preventDefault();
  toggleDetails(d, !(d._target ?? d.open));
});

/* 浏览器只允许在用户点击后启动音频分析；在那之前绝不接管音频，避免出现“没声音” */
const unlockAudio = () => {
  try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); if (actx.state !== 'running') actx.resume(); else { document.removeEventListener('pointerdown', unlockAudio, true); document.removeEventListener('keydown', unlockAudio, true); } } catch { /* 不支持就不做声波 */ }  // 开好了就不再每次点击都来（2026-11-11）
};
document.addEventListener('pointerdown', unlockAudio, true);
document.addEventListener('keydown', unlockAudio, true);
function attachViz(audio, key) {
  if (!key || reduceMotion || !actx || actx.state !== 'running') return;
  try {
    if (!vizNodes.has(audio)) {
      const src = actx.createMediaElementSource(audio), an = actx.createAnalyser();
      an.fftSize = 256; an.smoothingTimeConstant = .7; src.connect(an); an.connect(actx.destination); vizNodes.set(audio, an);
    }
  } catch { return; }
  VZ.an = vizNodes.get(audio); VZ.fbuf = new Uint8Array(VZ.an.frequencyBinCount); VZ.audio = audio; VZ.key = key;
  if (!vizRaf) vizRaf = requestAnimationFrame(vizLoop);
}
document.addEventListener('play', e => { if (e.target.tagName === 'AUDIO') attachViz(e.target, e.target.dataset.orbkey); }, true);


function fmtDur(sec) { if (sec == null) return '—'; sec = Math.round(sec); const m = Math.floor(sec / 60), s = sec % 60; return m ? `${m} 分 ${s} 秒` : `${s} 秒`; }
function fmtTime(t) { const d = new Date(t * 1000); return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
function togglePlay(key, url, onState, meta) {
  if (playingKey === key && !player.paused) { player.pause(); return; }
  player.pause(); PB.all.delete(player); player = new Audio(url);  // 旧的从播放器表里拿掉（以前每试听一次多留一个，2026-11-15 审查） player.dataset.orbkey = key; playingKey = key; player.volume = S.muted ? 0 : vol();
  pbRegister(player, () => meta || keyMeta(key));
  const upd = () => { $$('[data-play]').forEach(b => { const on = b.dataset.play === playingKey && !player.paused; b.classList.toggle('on', on); b.innerHTML = on ? ICON.pause : ICON.play; }); onState && onState(); };
  const p = player;
  player.onplay = () => { upd(); attachViz(p, key); }; player.onpause = upd; player.onended = () => { playingKey = null; upd(); };
  player.play().catch(playErr);
}
function keyMeta(key) {
  const k = String(key || '');
  if (k.startsWith('v:')) { const v = voices.find(x => x.id === k.slice(2)); return { title: v?.name || '音色', sub: '音色试听', orb: v?.id }; }
  if (k.startsWith('c:')) return { title: '候选音色', sub: '音色库 · 试听' };
  return { title: $('.page-title')?.textContent || '音频', sub: '' };
}
const curModel = () => models.find(m => m.key === S.model || (m.ids || []).includes(S.model)) || models[0];
const curPreset = () => (S.voice || '').startsWith('preset:') ? S.voice.slice(7) : null;
const curVoice = () => curPreset() ? null : (voices.find(v => v.id === S.voice) || null);
const profile = () => curModel()?.profile || {};
const roles = () => curModel()?.roles || {};
const dirKind = () => profile().director?.kind || 'none';

/* 导演面板 → 发给模型的指令文字（Breeze/Qwen：一句话指令；IndexTTS：情绪描述） */
function instructText() {
  const p = profile().director || {}, d = S.dir, parts = [];
  const emo = (p.emotions || []).find(e => e.key === d.emotion);
  if (p.kind === 'emotion') {
    if (emo && !emotionVector()) parts.push(emo.text);  // 滑杆全为 0 时仍用所选情绪
  } else {
    if (emo) parts.push(emo.levels[Math.max(0, Math.min(2, d.level))]);
    parts.push(...d.styles.filter(s => (p.styles || []).includes(s)));
    if (d.pace && (p.paces || []).some(x => x.text === d.pace)) parts.push(d.pace);
  }
  if (d.extra.trim()) parts.push(d.extra.trim());
  return parts.filter(Boolean).join('，');
}
function emotionVector() {
  const d = S.dir;
  return dirKind() === 'emotion' && d.useVector && (d.vector || []).some(x => x > 0) ? d.vector : null;
}
/* IndexTTS「情绪跟随正文」：没写情绪、没用向量时，按每段正文自动推断情绪 */
function emotionAuto() {
  return dirKind() === 'emotion' && !!S.dir.autoEmo && !emotionVector() && !instructText();
}
/* 与后端 pick_mode 一致 */
function mode() {
  const r = roles(), ins = instructText();
  if (curPreset()) return r.preset ? 'preset' : 'none';
  if (curVoice()) return r.direct && (ins || emotionVector() || emotionAuto()) ? 'direct' : (r.clone ? 'clone' : 'none');
  return r.design && ins ? 'design' : 'none';
}
const MODE_NAME = { clone: '纯克隆', direct: '导演模式', design: '音色设计', preset: '预设音色', none: '未选择音色', vc: '换声' };

/* 与后端一致的简化切段，用于实时预估 */
function splitPreview(text, maxlen) {
  let n = 0;
  for (let para of text.split(/\n+/)) {
    para = para.replace(/^\s*[{｛][^}｝\n]{1,120}[}｝]\s*/, '').replace(/[\[［]\s*(?:停顿|停|pause)[^\]］]*[\]］]/gi, '。').trim();  // 停顿标记也会切段
    if (!para.replace(/[\[(（][^\])）\n]{1,12}[\])）]/g, '').replace(/[^一-鿿0-9A-Za-z]/g, '')) continue;
    const sents = para.match(/[^。！？!?；;…]+[。！？!?；;…]*[”’」』"）)\]]?/g) || [para];
    let cur = 0;
    for (const s of sents) { if (cur && cur + s.length > maxlen) { n++; cur = 0; } cur += s.length; while (cur > maxlen) { n++; cur -= maxlen; } }
    if (cur) n++;
  }
  return n;
}

/* ================= 页面上的定时刷新 =================
   同一时间只有一个。pollStart(tick, 毫秒)：先跑一次 tick，再每隔一段时间跑；tick(stop) 里调 stop() 停下。
   切换页面（pollStop）或开始新的轮询后，旧的立刻作废：还在等第一次结果的不会再开定时器，也不会误停新页面的。 */
let pollGen = 0;
function pollStop() { clearInterval(pollTimer); pollTimer = null; pollGen++; }
function pollStart(tick, ms) {
  pollStop();
  const gen = pollGen;
  let me = null, stopped = false;
  const stop = () => { stopped = true; if (me) clearInterval(me); if (me && pollTimer === me) pollTimer = null; };
  let busy = false;
  const run = async () => { if (gen !== pollGen) return stop(); if (busy) return; busy = true; try { await tick(stop); } finally { busy = false; } };
  return (async () => { await run(); if (!stopped && gen === pollGen) me = pollTimer = setInterval(run, ms); })();
}

/* ================= 路由 ================= */
const PAGES = { tts: renderTTS, vc: renderVC, voices: renderVoices, works: renderWorks, stt: renderSTT, help: renderHelp, play: renderPlay, img: renderImg, prompt: renderPrompt, audioedit: (...a) => renderAudioEdit(...a) };
/* 切页不闪占位（2026-11-18 全量检查：素材库 / 改录音 / 批量 / 设置切进去头一两帧是“正在读取…”或灰色占位条）：
   这些列表画好后在内存里记下样子，下次进这页先直接放上次的样子，接口回来照常整块重画成最新的（新元素上没有 data-sig，第一次一定重画、事件也会绑上）。
   只存在内存里；进出私密空间（VGEN 变了）就清空 */
const SNAP = { g: null, m: new Map() };
const SNAP_SEL = ['#ae-list', '#bt-list', '#st-cats', '.gal-body', '#pg-side', '#lp-list'];
function snapKeep() {
  if (SNAP.g !== VGEN) { SNAP.m.clear(); SNAP.g = VGEN; }
  const pg = $('#main')?.dataset.page;
  SNAP_SEL.forEach(sel => { const el = $('#main ' + sel); if (!el || el._snap) return; el._snap = 1; const key = pg + sel;
    const ph = () => !!el.querySelector(':scope > .shimmer') || /^(正在读取|读取中)/.test(el.textContent.trim());
    const last = SNAP.m.get(key); if (last && ph()) el.innerHTML = last;
    new MutationObserver(() => { if (el.isConnected && SNAP.g === VGEN && !ph()) SNAP.m.set(key, el.innerHTML); }).observe(el, { childList: true }); });
}
function go(page, push = true) {
  persistFlush();
  if (push && PAGES[page] && $('#main')?.dataset.page && $('#main').dataset.page !== page) go.depth = (go.depth || 0) + 1;  // 返回键：前面还有页面可以回去
  document.getElementById('ig-mask-ov')?.remove();  // 放大涂抹的层：换页 / 进出私密空间时收掉
  const asked = page;
  if (!PAGES[page]) page = 'play';  // 打开时（地址里没有页面）默认是播放页
  if (push && document.documentElement.classList.contains('ph')) history.replaceState({}, '', '/' + page);  // 手机（2026-11-16）：换页不新增历史，左边缘往右滑 = 打开侧栏，不是返回
  else if (push) history.pushState({}, '', '/' + page);
  else if (asked !== page) history.replaceState({}, '', '/' + page);  // 被改到别的页面时地址栏也跟着改
  pollStop(); PAGE_REFRESH = null;
  $('#side-gear')?.classList.toggle('m-on', ['help', 'settings'].includes(page));  // “更多”里只剩设置和使用说明（页面都在分类里，2026-11-07）
  const main = $('#main');
  const render = () => {
    $$('.rnav a').forEach(a => a.classList.toggle('active', a.dataset.page === page)); window.railMark?.(page);
    if (page === 'img' && main.dataset.page !== 'img') { imgStage.off = false; imgStage.closed = true; imgStage.srcOn = false; imgStage.srcInit = true; }  // 2026-11-10 用户：进入生图页先是空画面
    main.dataset.page = page; const r = PAGES[page](); snapKeep(); window.scrollTo(0, 0); return r;
  };
  const after = () => { requestAnimationFrame(() => pbLayout()); setTimeout(pbLayout, 300); };
  // 页面切换：只让内容区淡入一下（很快、不位移、不变形），侧栏和底部播放条完全不参与，一直是实时画面。
  // 以前用浏览器的“页面过渡”，过渡期间侧栏和播放条会变成一张截图：播放条的磨砂背景没了（看着变淡）、
  // 侧栏截图被裁掉一角、进度条停住又跳一下；快速连点时卡片飞来飞去也容易晕。
  const samePage = main.dataset.page === page;  // 同一页里前进后退（手机上进出文件夹）：不淡入，不然像闪了一下
  render(); after();
  const now = performance.now(); go._streak = now - (go._t || 0) < 1500 ? (go._streak || 0) + 1 : 0; go._t = now;
  const quick = go._streak >= 2; window.__navQuick = quick;  // 左侧导航的滑块也看这个
  main.classList.toggle('no-anim', quick);  // 区块的“上浮出现”动画也不放  // 连着快速切页：不淡入，直接显示（不会一直闪）
  if (go._first === false && !reduceMotion && !samePage && !quick) {
    go._fade?.cancel();
    go._fade = main.animate([{ opacity: .35 }, { opacity: 1 }], { duration: 120, easing: 'cubic-bezier(0, 0, .2, 1)' });  // 从 35% 开始淡入，不是从全黑闪出来
  } else go._fade?.cancel();
  go._first = false;
  // 切页后强制整块重画一次：WebView2 在双显卡笔记本上偶尔有一块区域不刷新（还显示上一页），动画被中途取消时最容易出现
  clearTimeout(go._rp); go._rp = setTimeout(() => { main.style.willChange = 'transform'; requestAnimationFrame(() => requestAnimationFrame(() => { main.style.willChange = ''; })); }, 140);
}
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-page]');
  if (!a) return;
  e.preventDefault();
  go(a.dataset.page);
});
window.onpopstate = () => { go.depth = Math.max(0, (go.depth || 0) - 1); go(location.pathname.slice(1), false); };

/* 外观：跟随系统时随 Windows 的深浅色自动切换；切换时整页颜色平滑过渡 */
const darkMQ = matchMedia('(prefers-color-scheme: dark)');
function applyTheme(animate) {
  const t = S.theme === 'dark' || (S.theme !== 'light' && darkMQ.matches) ? 'dark' : 'light';
  const root = document.documentElement;
  root.style.background = ''; root.style.colorScheme = '';  // index.html 第一帧临时设的颜色：交给样式表
  { const m = document.querySelector('meta[name="theme-color"]'); if (m) { m.dataset.page = t === 'dark' ? '#0b0b0c' : '#f5f5f7'; if (!document.body?.classList.contains('np-open')) m.content = m.dataset.page; } }  // 手机状态栏 / 浏览器顶栏跟着浅色、深色（以前一直是深色）
  if (root.dataset.theme === t) return;
  if (animate && !reduceMotion) { root.classList.add('theme-anim'); setTimeout(() => root.classList.remove('theme-anim'), 500); }
  root.dataset.theme = t;
  window.Glide?.refresh();  // 滑块的颜色跟着换
}
darkMQ.addEventListener('change', () => applyTheme(true));
let ENGINE = null;  // null 连接中 / true 运行中 / false 未运行 / 'off' 工作室未连接
async function vaultCheck() {
  const gen = VGEN, v = await api('/api/vault/status').catch(() => null);
  if (!v || gen !== VGEN) return;  // 这期间自己进出过私密空间：这次的结果作废
  // 别的标签页进了私密空间（Cookie 共用）：这个标签页照旧留在普通空间，不跟着进去（2026-11-17 审查 F20：以前切回来就自动进私密空间，不用密钥）
  if (v.vault && !VAULT) return;
  if (!v.vault && VAULT) {
    sessionStorage.removeItem('vaultTab'); if (curPop) curPop.close(true); ImageViewer.close();
    vaultSwitchUI(false); await vaultReloadData(); toast('私密空间已退出（已在其他窗口退出，或因长时间未使用而失效）'); go('play');
  }
}
addEventListener('focus', vaultCheck);
/* 播放副本（?scrub=1 → 302 到带版本的地址）放到一半副本没了 / 换过：后台对中途的请求回 410（不再改从原片取字节，第二轮审查 10），
   这里重新加载同一个地址（后台跳到现在的版本），接着原来的位置放 */
document.addEventListener('error', e => {
  const v = e.target; if (!v || v.tagName !== 'VIDEO' || !/[?&]scrub=1/.test(v.getAttribute('src') || '')) return;
  if ((v._srTry = (v._srTry || 0) + 1) > 2) return;
  const t = v.currentTime, pl = !v.paused; v.load();
  v.addEventListener('loadedmetadata', () => { try { v.currentTime = t; } catch { } if (pl) v.play().catch(() => { }); }, { once: true });
}, true);
/* 手机和电脑之间的同步：服务器给每一类内容一个“版本”，变了就让当前页面刷新自己的那部分（PAGE_REFRESH 由各页面设置） */
let REV = null, PAGE_REFRESH = null;
function revCheck(rev) {
  if (!rev) return;
  const old = REV;
  if (old && document.hidden) return;  // 在后台：先不记，切回来时再比（不会漏掉这期间的变化）
  REV = rev; if (!old) return;
  const changed = Object.keys(rev).filter(k => rev[k] !== old[k]);
  if (!changed.length) return;
  if (changed.includes('voices')) loadVoices().then(() => { if ($('#vlist')) renderVoiceList(); }).catch(() => { });
  if (PAGE_REFRESH && changed.some(k => PAGE_REFRESH.on.includes(k))) PAGE_REFRESH.fn();
}
const pageRefresh = (on, fn) => { PAGE_REFRESH = { on, fn }; };
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshStatus(); });  // 切回来马上看一眼
let STATUS_P = null;  // 正在查的那一次：后台慢时不叠着再发（审查 28）
function refreshStatus() { return STATUS_P || (STATUS_P = refreshStatus1().finally(() => { STATUS_P = null; })); }
async function refreshStatus1() {
  vaultCheck();
  try { const st = await api('/api/status'); ENGINE = st.engine; revCheck(st.rev); } catch { ENGINE = 'off'; }
  const d = $('#eng-dot'); if (d) d.className = 'dot ' + (ENGINE === true ? 'ok' : ENGINE === null ? '' : 'bad');
  const s = $('#gear-eng'); if (s) s.innerHTML = engText();
}
const engText = () => ENGINE === true ? '<span class="dot ok"></span>引擎运行中 · CUDA' : ENGINE === null ? '<span class="dot"></span>正在连接引擎…' : ENGINE === 'off' ? '<span class="dot bad"></span>工作室未连接' : '<span class="dot bad"></span>引擎未运行';
/* 左下角齿轮：引擎状态、外观、视频小窗、封面、帮助。选项用图标表示（鼠标停留显示名称），右边小字显示当前选的是哪个 */
const GI = (d, fill) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const GEAR_OPTS = {
  theme: { key: 't', get: () => S.theme || 'system', items: [
    ['system', '跟随系统', GI('<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/>')],
    ['light', '浅色', GI('<circle cx="12" cy="12" r="3.6"/><path d="M12 2.8v2.2M12 19v2.2M2.8 12H5M19 12h2.2M5.5 5.5l1.6 1.6M16.9 16.9l1.6 1.6M5.5 18.5l1.6-1.6M16.9 7.1l1.6-1.6"/>')],
    ['dark', '深色', GI('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>')]] },
  vid: { key: 'v', get: () => S.vidMode || 'float', items: [
    ['float', '悬浮小窗', GI('<rect x="3" y="5" width="18" height="14" rx="3"/><rect x="12" y="11.5" width="6.5" height="5" rx="1.2" fill="currentColor" stroke="none"/>')],
    ['dock', '从播放条展开', GI('<rect x="4" y="3.5" width="16" height="11" rx="2.5"/><rect x="3" y="17" width="18" height="3.5" rx="1.75" fill="currentColor" stroke="none"/>')]] },
  // 缩略图放在哪（2026-11-08：从左上角挪到这里——标题旁边两个长方形图标长得几乎一样，分不清）
  lay: { key: 'g', get: () => S.galLay === 'col' ? 'col' : 'row', items: [
    ['col', '在左边', GI('<rect x="3" y="4" width="18" height="16" rx="2.5"/><rect x="3" y="4" width="6" height="16" rx="2" fill="currentColor" opacity=".35" stroke="none"/><path d="M9 4v16"/>')],
    ['row', '在下面', GI('<rect x="3" y="4" width="18" height="16" rx="2.5"/><rect x="3" y="14" width="18" height="6" rx="2" fill="currentColor" opacity=".35" stroke="none"/><path d="M3 14h18"/>')]] },
  // 生图、生视频的选项放在哪（2026-11-19 用户：两版并存，默认输入框，在右下角设置里换）
  opt: { key: 'o', get: () => S.ui?.ppos === 'side' ? 'side' : 'bottom', items: [
    ['bottom', '输入框', GI('<rect x="3" y="4" width="18" height="16" rx="2.5"/><rect x="7" y="14" width="10" height="3.5" rx="1.5" fill="currentColor" opacity=".35" stroke="none"/>')],
    ['side', '创作栏', GI('<rect x="3" y="4" width="18" height="16" rx="2.5"/><rect x="3" y="4" width="7" height="16" rx="2" fill="currentColor" opacity=".35" stroke="none"/><path d="M10 4v16"/>')]] },
  lock: { key: 'l', get: () => String(S.lockMin ?? 15), items: [  // 私密空间里多久没操作（也没在播放）自动退出
    ['0', '关闭', '<b class="gp-tx">关</b>'], ['5', '5 分钟', '<b class="gp-tx">5′</b>'],
    ['15', '15 分钟', '<b class="gp-tx">15′</b>'], ['30', '30 分钟', '<b class="gp-tx">30′</b>']] },
  cover: { key: 'c', get: () => S.coverMode === 'file' ? 'file' : 'orb', items: [
    ['orb', 'Siri 球', GI('<circle cx="12" cy="12" r="8"/><path d="M6.5 13.5c2-3 5-3.6 8.2-2M8 16.6c2.4-2.3 5.6-2.8 8.6-1.4" opacity=".75"/>')],
    ['file', '文件自带的封面', GI('<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l4.6-4.4 3.4 3 3-2.6L20 17.5"/>')]] },
};
const gearSeg = (id, o) => `<div class="seg gp-seg" id="gear-${id}">${o.items.map(([v, name, ic]) => `<button type="button" data-${o.key}="${v}" title="${name}" aria-label="${name}" class="${o.get() === v ? 'on' : ''}">${ic}</button>`).join('')}</div>`;
/* ================= 手机访问（Tailscale） =================
   电脑和手机都装 Tailscale 并登录同一个账号，Studio 只在 Tailscale 的加密通道上对手机开放（不对公寓 Wi-Fi 开放）。
   手机第一次打开要输入这里显示的 6 位配对码；配对过的设备列在下面，可以随时移除。手机配对后可以正常使用全部功能（包括私密空间）；只有在资源管理器中打开、改远程访问设置这些只能在电脑上做。 */
let REMOTE = false;  // 这个页面是不是在手机上（通过 Tailscale）打开的
async function remotePanel() {
  const box = document.createElement('div'); box.className = 'modal-bg';
  box.innerHTML = `<div class="modal rp"><button class="x" title="关闭">×</button><h3 class="card-title" style="margin:0 0 4px">手机访问</h3><div class="rp-body"><div class="tiny">读取中…</div></div></div>`;
  document.body.append(box);
  const escK = e => { if (e.key === 'Escape' && box.isConnected && [...document.querySelectorAll('.modal-bg')].pop() === box) { e.preventDefault(); e.stopImmediatePropagation(); close(); } };
  const close = () => { box.remove(); document.removeEventListener('keydown', escK, true); };
  document.addEventListener('keydown', escK, true);  // Esc 也能关
  box.querySelector('.modal').setAttribute('role', 'dialog');
  box.onclick = e => { if (e.target === box || e.target.closest('.x')) close(); };
  const ago = t => { if (!t) return '尚未使用'; const d = (Date.now() / 1000 - t) / 60; return d < 2 ? '刚刚' : d < 60 ? Math.round(d) + ' 分钟前' : d < 1440 ? Math.round(d / 60) + ' 小时前' : Math.round(d / 1440) + ' 天前'; };
  let code = null, codeT = 0;
  const draw = async st => {
    st = st || await api('/api/remote').catch(e => ({ error: e.message }));
    if (!box.isConnected) return;
    if (st.error) { $('.rp-body', box).innerHTML = `<div class="tiny" style="color:var(--red)">无法读取手机访问状态：${esc(st.error)}</div>`; return; }
    const b = $('.rp-body', box), ts = st.tailscale || {};
    const step = !ts.installed ? 'install' : !ts.running ? 'login' : !st.enabled ? 'off' : !st.listening ? 'wait' : 'on';
    b.innerHTML = `
      <div class="gp-row rp-sw"><span class="gp-l">允许手机访问<em>${{ install: '需要先安装 Tailscale', login: 'Tailscale 尚未登录 / 未连接', off: '已关闭', wait: '正在开启…', on: '已开启' }[step]}</em></span>
        <label class="switch"><input type="checkbox" id="rp-on" ${st.enabled ? 'checked' : ''}><span></span></label></div>
      ${step === 'install' || step === 'login' ? `<ol class="rp-steps">
        <li>在电脑上安装 Tailscale：<a href="https://tailscale.com/download/windows" target="_blank">tailscale.com/download</a>，安装后登录（可使用 Apple / Google 账号）。</li>
        <li>iPhone 在 App Store 安装 <b>Tailscale</b>，使用<b>同一账号</b>登录并开启连接。</li>
        <li>返回此处开启“允许手机访问”。</li></ol>` : ''}
      ${step === 'on' ? `<div class="rp-addr"><div class="tiny">在 iPhone 的 Safari 中打开：</div><div class="rp-url">${esc(st.url)}</div>${st.ip_url && st.ip_url !== st.url ? `<div class="tiny">无法打开时请使用：${esc(st.ip_url)}</div>` : ''}
        <div class="tiny">打开后在 Safari 中点击“分享”→“添加到主屏幕”，之后即可像 App 一样打开。</div></div>
        <div class="rp-pair">${code && Date.now() < codeT ? `<div class="tiny">在手机上输入配对码（5 分钟内有效）：</div><div class="rp-code">${code.slice(0, 3)} ${code.slice(3)}</div>` : `<button class="btn primary" id="rp-new">${ICON.plus || ''}配对新设备</button>`}</div>` : ''}
      ${st.devices?.length ? `<div class="sec-label">已配对的设备</div><div class="rp-devs">${st.devices.map(d => `<div class="rp-dev"><span>${esc(d.name)}</span><em>最近使用 ${ago(d.last)}</em><button class="btn small" data-rm="${esc(d.id)}">移除</button></div>`).join('')}</div>` : ''}
      <div class="tiny rp-note">仅通过 Tailscale 加密通道访问，公寓 Wi-Fi 中的其他人无法连接；已配对的手机可使用全部功能（包括私密空间）；“在资源管理器中打开”及修改此处设置仅能在电脑上操作。</div>`;
    $('#rp-on', b).onchange = async e => { await api('/api/remote', { body: { enabled: e.target.checked } }).catch(() => { }); draw(); if (e.target.checked) setTimeout(() => draw(), 22000); };
    const nb = $('#rp-new', b); if (nb) nb.onclick = async () => { const r = await api('/api/remote/code', { body: {} }).catch(e => { toast(e.message, true); }); if (!r) return; code = r.code; codeT = Date.now() + r.ttl * 1000; draw(st); setTimeout(() => { code = null; if (box.isConnected) draw(); }, r.ttl * 1000); poll(); };
    $$('[data-rm]', b).forEach(x => x.onclick = async () => { const r = await api('/api/remote/device/' + encodeURIComponent(x.dataset.rm), { method: 'DELETE' }).catch(e => { toast(e.message, true); }); if (r) draw(r); });
  };
  const poll = async () => {  // 显示配对码期间：手机一配对成功就刷新设备列表
    const n0 = (await api('/api/remote').catch(() => ({}))).devices?.length || 0;
    const t = setInterval(async () => {
      if (!box.isConnected || !code) return clearInterval(t);
      const st = await api('/api/remote').catch(() => null);
      if (st && (st.devices?.length || 0) > n0) { clearInterval(t); code = null; toast('新设备配对成功'); draw(st); }
    }, 2000);
  };
  draw();
}
/* 显存：显卡总用量 + 本程序加载了哪些模型（各约多大），可以单独释放；释放后下次用到时会自动重新加载 */
async function vramPaint(pop, data) {
  const box = $('#gear-vram', pop); if (!box) return;
  if (!data && vramPaint.last && /读取中/.test(box.textContent)) vramPaint(pop, vramPaint.last);  // 先画上次读到的（2026-11-18：设置页切进去不再闪“读取中…”），再读最新的
  const d = data || await api('/api/vram').catch(() => null);
  if (!box.isConnected) return;
  vramPaint.last = d || { total: null };  // 读不到也记下（下次先显示“无法读取”，不闪“读取中…”）
  if (!d || d.total == null) { box.innerHTML = '<div class="vr-head"><span>显存</span><em>无法读取显卡信息</em></div>'; return; }
  const gb = mb => (mb / 1024).toFixed(1);
  const ours = d.items.reduce((a, x) => a + x.mb, 0), other = Math.max(0, d.used - ours);
  const seg = (mb, cls) => `<i class="${cls}" style="width:${Math.min(100, mb / d.total * 100)}%"></i>`;
  box.innerHTML = `<div class="vr-head"><span>显存</span><em>${gb(d.used)} / ${gb(d.total)} GB</em></div>
    <div class="vr-bar">${seg(ours, 'ours')}${seg(other, 'other')}</div>
    ${d.items.map(x => `<div class="vr-row"><span class="vr-dot ours"></span><span class="vr-n">${esc(x.name)}</span><span class="vr-mb">${gb(x.mb)} GB</span><button type="button" class="vr-x" data-vr="${esc(x.id)}" title="释放（下次使用时自动重新加载）">释放</button></div>`).join('')
      || '<div class="vr-row vr-none">当前没有加载模型</div>'}
    <div class="vr-row"><span class="vr-dot other"></span><span class="vr-n">其他程序</span><span class="vr-mb">${gb(other)} GB</span>${d.items.length > 1 ? '<button type="button" class="vr-x" data-vr="all">全部释放</button>' : '<span class="vr-x-sp"></span>'}</div>`;
  $$('[data-vr]', box).forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = '释放中';
    const r = await api('/api/vram', { body: { id: b.dataset.vr } }).catch(e => { toast('释放失败：' + e.message, true); return null; });
    vramPaint(pop, r || undefined);
  });
}
const gearName = o => (o.items.find(x => x[0] === o.get()) || o.items[0])[1];
/* 侧栏底部：显卡占用（一眼看到用了多少、哪个模型在显存里）+ 任务队列（配音 / 换声 / 生图 / 生视频的所有任务都在这里看进度、取消） */
const Q_SRC = [
  { kind: 'tts', url: '/api/jobs', cancel: id => `/api/jobs/${id}/cancel` },
  { kind: 'img', url: '/api/img/jobs', cancel: id => `/api/img/jobs/${id}/cancel` },
  { kind: 'video', url: '/api/video/jobs', cancel: id => `/api/video/jobs/${id}/cancel` },
];
const Q_ACTIVE = ['queued', 'running'];
async function qFetch() {
  const r = await Promise.all(Q_SRC.map(src => api(src.url).then(l => (Array.isArray(l) ? l : l?.jobs || []).map(j => ({ ...j, _src: src })), () => [])));
  return r.flat();
}
const qKind = j => j._src.kind === 'tts' ? (j.kind === 'vc' ? ['换声', 'vc'] : ['配音', 'tts']) : j._src.kind === 'img' ? ['生图', 'img'] : ['生视频', 'video'];
const qPct = j => j.progress != null ? +j.progress || 0 : j.count ? Math.round(((j.done || 0) + (j.total ? (j.step || 0) / j.total : 0)) / j.count * 100) : j.total ? Math.round((j.done || 0) / j.total * 100) : 0;
function qRow(j) {
  const [k, page] = qKind(j), act = Q_ACTIVE.includes(j.state), pct = Math.max(0, Math.min(100, qPct(j)));
  const sub = [j.model_name, act ? (j.message || (j.state === 'queued' ? '排队中' : '')) : j.state === 'done' ? (j.warn && typeof j.warn === 'string' ? '完成 · ' + j.warn : '完成') : j.state === 'error' ? '失败' : '已取消'].filter(Boolean).join(' · ');  // warn：比如二采失败、只存了一采（审查 16）
  return `<div class="qp-row ${esc(j.state)}" data-page="${page}" role="button" tabindex="0"><span class="qp-k qp-${page}">${k}</span>
    <div class="qp-main"><div class="qp-t" title="${esc(j.title || j.prompt || '')}">${esc(j.title || j.prompt || '任务')}</div><div class="qp-sub">${esc(sub)}${jobTimer(j, 'sm')}</div>
      ${act ? `<div class="qp-bar${j.state === 'queued' ? ' wait' : ''}"><i style="width:${j.state === 'queued' ? 0 : pct}%"></i></div>` : ''}</div>
    ${act ? `<button type="button" class="qp-x" data-qc="${esc(j.id)}" data-qk="${j._src.kind}" title="取消" aria-label="取消">${ICON.x}</button>` : ''}</div>`;
}
async function qPaint(pop) {
  const box = $('#qp-list', pop); if (!box) return;
  const all = await qFetch(); if (!box.isConnected) return;
  const now = Date.now() / 1000, act = all.filter(j => Q_ACTIVE.includes(j.state)).sort((a, b) => (a.state === 'running' ? 0 : 1) - (b.state === 'running' ? 0 : 1) || (a.created || 0) - (b.created || 0));
  const rec = all.filter(j => !Q_ACTIVE.includes(j.state) && j.finished && now - j.finished < 1800).sort((a, b) => b.finished - a.finished).slice(0, 5);
  $('#qp-n', pop).textContent = act.length ? `${act.length} 个进行中` : '';
  box.innerHTML = (act.length ? act.map(qRow).join('') : '<div class="qp-empty">没有进行中的任务</div>')
    + (rec.length ? `<div class="qp-sec">最近完成</div>${rec.map(qRow).join('')}` : '');
  $$('[data-qc]', box).forEach(b => b.onclick = async e => {
    e.stopPropagation(); b.disabled = true;
    const src = Q_SRC.find(x => x.kind === b.dataset.qk);
    await api(src.cancel(b.dataset.qc), { body: {} }).catch(er => toast(er.message, true)); qPaint(pop); dockPaint();
  });
  $$('.qp-row', box).forEach(r => r.onclick = () => { pop.close(); go(r.dataset.page); });
}
function qOpen(anchor) {
  popover(anchor, `<div class="qp"><div class="gp-list gp-vram" id="gear-vram"><div class="vr-head"><span>显存</span><em>读取中…</em></div><div class="vr-bar"><i></i></div></div>
    <div class="qp-h"><b>任务</b><span class="tiny" id="qp-n"></span></div><div class="qp-list" id="qp-list"><div class="shimmer"></div></div></div>`, pop => {
    vramPaint(pop); qPaint(pop);
    const t = setInterval(() => { if (!pop.isConnected) return clearInterval(t); qPaint(pop); }, 2000);
  }, { width: 380 });
}
async function dockPaint() {  // 侧栏底部的两个小按钮：显存条 + 进行中的任务数
  const d = $('#side-dock'); if (!d || document.hidden) return;
  const [v, all] = await Promise.all([api('/api/vram').catch(() => null), qFetch()]);
  if (v && v.total) {
    const p = Math.min(100, v.used / v.total * 100);
    $('.sd-gpu i', d).style.width = p + '%'; $('.sd-gpu i', d).className = p > 90 ? 'hot' : p > 70 ? 'warm' : '';
    $('.sd-gpu em', d).textContent = (v.used / 1024).toFixed(1) + ' GB';
    $('.sd-gpu', d).title = `显存 ${(v.used / 1024).toFixed(1)} / ${(v.total / 1024).toFixed(1)} GB` + (v.items?.length ? '\n' + v.items.map(x => `${x.name}：${(x.mb / 1024).toFixed(1)} GB`).join('\n') : '\n当前没有加载模型');
  }
  const act = all.filter(j => Q_ACTIVE.includes(j.state)), run = act.some(j => j.state === 'running');
  const n = $('.sd-n', d); n.textContent = act.length || ''; $('.sd-gpu', d).classList.toggle('run', run);
  if (act.length) $('.sd-gpu', d).title += `\n${act.length} 个任务进行中`;
}
function dockInit() {
  const foot = $('.rail-foot'), g = $('#side-gear'); if (!foot || !g || $('#side-dock')) return;
  const d = document.createElement('div'); d.className = 'side-dock'; d.id = 'side-dock';
  d.innerHTML = `<button type="button" class="sd-gpu" aria-label="显卡占用"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="5" width="14" height="14" rx="2.5"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></svg><span class="sd-bar"><i></i></span><em>—</em><b class="sd-n"></b></button><button type="button" class="sd-q" hidden aria-label="任务队列"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/></svg><b></b></button>`;
  g.after(d);
  $('.sd-gpu', d).onclick = e => qOpen(e.currentTarget); $('.sd-q', d).onclick = e => qOpen(e.currentTarget);
  dockPaint(); setInterval(dockPaint, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) dockPaint(); });
}
function applyGuard() { document.body.classList.toggle('guard', !!S.ui?.guard); }
function bindGear() {
  applyGuard(); dockInit();
  const g = $('#side-gear'); if (!g) return;
  const row = (id, label) => `<div class="gp-row"><span class="gp-l">${label}<em id="gear-${id}-n">${gearName(GEAR_OPTS[id])}</em></span>${gearSeg(id, GEAR_OPTS[id])}</div>`;
  const chev = '<svg class="gp-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>';
  const PI = { video: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.2-2.5z" fill="currentColor" stroke="none"/>', works: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M10 9l5 3-5 3z"/>', prompt: '<path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z"/><path d="M18.5 14.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>', vc: '<path d="M3 9h13l-3-3M21 15H8l3 3"/>', voices: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    stt: '<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/>', audioedit: '<path d="M3 12h2l2-5 3 10 3-12 3 9 2-4h3"/>', mats: '<rect x="3.5" y="3.5" width="7" height="9" rx="2"/><rect x="13.5" y="3.5" width="7" height="6" rx="2"/><rect x="3.5" y="15.5" width="7" height="5" rx="2"/><rect x="13.5" y="12.5" width="7" height="8" rx="2"/>' };
  const rcRow = () => `<label class="gp-row" data-tip="开启（默认）：电脑在播放条上开启控制后，可以从电脑控制这台设备的播放，锁屏后也可以。为了暂停后还能被电脑继续，暂停时会播放无声音频，最长 30 分钟。"><span class="gp-l">允许电脑控制</span><span class="switch"><input type="checkbox" id="gear-rc" aria-label="允许电脑控制播放"${localStorage.getItem('rcAllow') !== '0' ? ' checked' : ''}><span></span></span></label>`;
  g.onclick = () => popover(g, `<div class="gear-pop">
      ${MOB() && window.navPages ? `<div class="gp-list gp-pages">${(() => { const P = (window.navPinned?.() || []).slice(0, 4); return window.navPages().filter(x => !P.includes(x.p)); })().map(x => `<a class="gp-link${location.pathname === '/' + x.p ? ' on' : ''}" href="/${x.p}" data-gp="${x.p}"><span class="gp-pic">${x.svg}</span><span>${esc(x.n)}</span>${chev}</a>`).join('')}</div>` : ''}
      <div class="gp-list">${row('vid', '视频小窗')}${MOB() ? '' : (S.ui?.ppos === 'side' ? '' : row('lay', '缩略图')) + row('opt', '选项')}
        <label class="gp-row" data-tip="开启：打开视频（点缩略图、详情、放大原视频、素材库里的视频）就开始播放，生成完成后也自动播放。关闭：打开视频只显示画面，点播放按钮或缩略图上的 ▶ 才播放。播放页和连续预览不受影响。"><span class="gp-l">自动播放<em>视频预览</em></span><span class="switch"><input type="checkbox" id="gear-autoplay" aria-label="自动播放视频预览"${videoAutoplay() ? ' checked' : ''}><span></span></span></label>
        <label class="gp-row" data-tip="关闭（默认）：同一个原视频的片段、版本和拼接视频叠成一格，点开查看。开启：全部平铺显示"><span class="gp-l">视频组<em>平铺</em></span><span class="switch"><input type="checkbox" id="gear-pcs" aria-label="视频组平铺显示"${S.vdPcs ? ' checked' : ''}><span></span></span></label></div>
      ${VAULT ? `<div class="gp-list">${row('lock', '自动退出')}${REMOTE ? rcRow() : ''}</div>` : REMOTE ? `<div class="gp-list">${rcRow()}</div>` : ''}
      <div class="gp-list gp-links">
        ${MOB() ? `<a class="gp-link" href="#" id="gear-queue"><svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M8 6h12M8 12h12M8 18h12\"/><circle cx=\"4\" cy=\"6\" r=\"1\" fill=\"currentColor\"/><circle cx=\"4\" cy=\"12\" r=\"1\" fill=\"currentColor\"/><circle cx=\"4\" cy=\"18\" r=\"1\" fill=\"currentColor\"/></svg><span>任务与显卡</span></a>` : ''}
        <a class="gp-link" href="#" id="gear-guard">${GI('<path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A9.8 9.8 0 0 1 12 5c5 0 9 5 9 7a10.6 10.6 0 0 1-2.4 3.3M6.5 6.6C4.4 8 3 10.3 3 12c0 2 4 7 9 7 1.6 0 3.1-.4 4.4-1.1"/>')}<span>防窥模式</span><em class="gp-sw" id="gear-guard-v">${S.ui?.guard ? '开' : '关'}</em></a>
        <a class="gp-link" href="#" id="gear-restart">${GI('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>')}<span>重启 Studio</span>${chev}</a>
        ${VAULT ? `<a class="gp-link" href="#" id="gear-exit">${GI('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>')}<span>退出私密空间</span>${chev}</a>` : ''}
      </div>
      <div class="gp-list gp-links"><a class="gp-link gp-all" href="/settings" id="gear-all">${GI('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>')}<span>全部设置</span>${chev}</a></div></div>`,
    pop => {
      $('#gear-all', pop).onclick = e => { e.preventDefault(); pop.close(); go('settings'); };  // 其余的设置、存储（清缓存）、显卡、手机访问……都在设置页
      $('#gear-autoplay', pop).onchange = e => setVideoAutoplay(e.target.checked);
      const grc = $('#gear-rc', pop); if (grc) grc.onchange = e => { localStorage.setItem('rcAllow', e.target.checked ? '1' : '0'); if (e.target.checked) rcReport(true); else rcBye(); };
      $('#gear-pcs', pop).onchange = e => { S.vdPcs = e.target.checked; persist(); if (typeof vidGallery === 'function' && ($('#vd-gal') || $('#w-vgal'))) vidGallery(); };
      const x = $('#gear-exit', pop); if (x) x.onclick = e => { e.preventDefault(); pop.close(); vaultLock(); };
      const pick = (id, b) => { $$(`#gear-${id} button`, pop).forEach(y => y.classList.toggle('on', y === b)); $(`#gear-${id}-n`, pop).textContent = b.title; };
      $$('#gear-theme button', pop).forEach(b => b.onclick = () => { S.theme = b.dataset.t; persist(); applyTheme(true); pick('theme', b); });
      $$('#gear-lock button', pop).forEach(b => b.onclick = () => { S.lockMin = +b.dataset.l; persist(); pick('lock', b); idleT = Date.now(); });
      $$('#gear-lay button', pop).forEach(b => b.onclick = () => { pick('lay', b); if ((S.galLay === 'col' ? 'col' : 'row') === b.dataset.g) return;
        const t = $('.gal-lay:not(.gal-fb)'); if (t) t.click(); else { S.galLay = b.dataset.g; persist(); } });  // 当前页有缩略图：用原来那个（藏起来的）按钮切换，页面跟着重排
      $$('#gear-opt button', pop).forEach(b => b.onclick = () => { pick('opt', b); if ((S.ui?.ppos === 'side' ? 'side' : 'bottom') === b.dataset.o) return; S.ui = { ...(S.ui || {}), ppos: b.dataset.o }; persist(); b5Relayout(); });
      $$('#gear-vid button', pop).forEach(b => b.onclick = () => {
        S.vidMode = b.dataset.v; persist(); pick('vid', b);
        const mini = MINI; if (mini && !mini.hidden && !MINI_OUT) { mini.hidden = true; mini.classList.remove('show'); } miniSync();
      });

      $$('[data-gp]', pop).forEach(a => a.onclick = e => { e.preventDefault(); pop.close(); go(a.dataset.gp); });

      $('#gear-restart', pop).onclick = e => { e.preventDefault(); pop.close(); studioRestart(); };
      if ($('#gear-queue', pop)) $('#gear-queue', pop).onclick = e => { e.preventDefault(); const a = $('#side-gear'); pop.close(true); setTimeout(() => qOpen(a), 0); };
      $('#gear-guard', pop).onclick = e => {  // 防窥模式：页面上的图片 / 视频封面都换成黑底图标，鼠标停在上面一会儿才显示；弹窗里看大图不受影响
        e.preventDefault(); S.ui = S.ui || {}; S.ui.guard = !S.ui.guard; persist(); applyGuard();
        $('#gear-guard-v', pop).textContent = S.ui.guard ? '开' : '关'; toast(S.ui.guard ? '防窥模式已开启：鼠标在图片上停留约 1 秒后才显示' : '防窥模式已关闭');
      };

      $$('#gear-cover button', pop).forEach(b => b.onclick = () => {
        S.coverMode = b.dataset.c; persist(); pick('cover', b);
        if (PB.a) pbPaint(true); qPanelPaint();
      });
    }, { width: 248, title: MOB() ? '更多' : '' });
}

/* 手机：添加到主屏幕（像 App 一样全屏打开）。iPhone 主屏幕应用可能拿不到 Safari 里的登录信息，
   所以先要一个只属于这台手机的安装令牌，写进启动地址：第一次从主屏幕打开时自动登录，不用再配对 */
const STANDALONE = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
async function addToHome() {
  let tok = '';
  try { tok = (await api('/api/remote/install', { body: {} })).token || ''; } catch (e) { return toast(e.message, true); }
  $('link[rel=manifest]')?.setAttribute('href', '/manifest.webmanifest?it=' + encodeURIComponent(tok));
  history.replaceState(history.state, '', location.pathname + '?it=' + encodeURIComponent(tok));  // iPhone 用当前地址当启动地址
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent), safari = ios && !/CriOS|FxiOS|EdgiOS/.test(navigator.userAgent);
  const shareIc = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M12 3v12M8 7l4-4 4 4"/><path d="M6 11v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8"/></svg>';
  modal(`<h3 class="card-title" style="margin:0 0 10px">添加到主屏幕</h3>
    ${ios && !safari ? '<div class="a2hs-warn">iPhone 上仅 Safari 可添加到主屏幕：请使用 Safari 打开此页面后再操作。</div>' : ''}
    <ol class="a2hs-steps">${ios ? `<li>点击 Safari 底部（或地址栏右侧）的 <b>分享</b> 按钮 ${shareIc}</li><li>向下滑动，点击 <b>添加到主屏幕</b></li><li>名称保持“Studio”，点击右上角的 <b>添加</b></li>`
      : '<li>点击浏览器右上角的 <b>⋮</b> 菜单</li><li>点击 <b>添加到主屏幕</b> 或 <b>安装应用</b></li><li>确认添加</li>'}</ol>
    <div class="tiny" style="line-height:1.7">之后从主屏幕的 Studio 图标打开：全屏显示、无地址栏、自动登录，无需再输入配对码。电脑需保持开机，Tailscale 需保持连接。</div>
    <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn primary" data-close>知道了</button></div>`, null);
}

/* 一键重启 Studio：换上新代码（关掉应用窗口不会重启后台）。有任务在进行时先问；重启期间盖一层“正在重启”，好了自动刷新页面 */
async function studioRestart() {
  if (!await confirmBox('重启 Studio？', '后台将重新启动，约需 10~30 秒，完成后页面将自动刷新。配音引擎不会重新载入。' + (VAULT ? '私密空间将退出，重启后需重新输入密钥。' : ''), '重启')) return;
  let r;
  try { r = await api('/api/restart', { body: {} }); } catch (e) { return toast('重启失败：' + e.message, true); }
  if (r.busy) {
    if (!await confirmBox('当前有任务正在进行', `${r.busy.join('、')}。重启将中断这些任务（已生成的部分不会丢失）。`, '仍然重启', true)) return;
    try { r = await api('/api/restart', { body: { force: true } }); } catch (e) { return toast('重启失败：' + e.message, true); }
  }
  if (!r.ok) return toast('未能重启：' + (r.error || '后台无响应'), true);
  const ov = document.createElement('div'); ov.className = 'restart-ov';
  ov.innerHTML = '<div class="restart-card"><span class="spinner dark"></span><b>正在重启 Studio…</b><div class="tiny" id="rs-t">等待旧后台退出</div></div>';
  document.body.appendChild(ov);
  const t0 = Date.now(); let down = false;
  for (;;) {
    await sleep(1000);
    const sec = Math.round((Date.now() - t0) / 1000);
    let ok = false;
    try { ok = (await fetch('/api/status', { cache: 'no-store' })).ok; } catch { }
    if (!ok) down = true;
    if (ok && (down || sec > 25)) { $('#rs-t', ov).textContent = '已完成，正在刷新页面'; await sleep(300); location.reload(); return; }  // 重启 Studio 只是换上新代码：草稿、正在看的对话都保留（叉掉应用 / 重启电脑后再打开才清空）
    $('#rs-t', ov).textContent = down ? `正在启动新的后台… ${sec} 秒` : `等待旧后台退出… ${sec} 秒`;
    if (sec > 120) { ov.querySelector('.restart-card').innerHTML = '<b>重启超时</b><div class="tiny">新后台未能启动。请查看 studio/app-server.log，或双击“打开 Studio 应用”。</div><button type="button" class="btn small" onclick="location.reload()">刷新页面</button>'; return; }
  }
}

/* ================= 私密空间 =================
   在任何页面依次按下密钥的 6 个键即可进入（输入框里也可以，进入后会把这几个字删掉）。
   进入后作品、历史记录、语音转文字、新建的音色都存在另一处，和普通界面互相看不到；还会多出“播放”页。 */
let VAULT = false;
const VAULT_KEYS_LEN = 6;
/* 私密空间：切到后台时（iPhone 上滑看后台、切到别的 App、电脑最小化）先用一块黑色盖住画面，后台预览里看不到内容（2026-11-06 用户）。
   回到前台再拿掉。手机上失去焦点（开始上滑）时也先盖上；电脑上失去焦点很常见（点到别的窗口），不盖 */
/* iPhone 主屏 App：慢慢上滑时 App 还没进后台（document.hidden 还是 false、常常也没有 blur），系统却已经拍下了后台预览图，
   等到那些事件再临时建一块黑色往往来不及画出来。所以：①黑色那块提前建好、平时只是隐藏，盖上时只切一个 class；
   ②从屏幕最下面（主屏条那里）按下、随后被系统取消（touchcancel = 系统接管了上滑手势）时立刻盖上，不等进后台。
   这样盖上之后不一定会有 focus 回来，所以点一下黑色那块也能拿掉（2026-11-06 用户：后台预览没实现） */
const VC_TOUCH = matchMedia('(hover: none) and (pointer: coarse)');
function vaultCoverEl() {
  let c = document.getElementById('vault-cover');
  if (!c && document.body) { c = document.createElement('div'); c.id = 'vault-cover'; c.setAttribute('aria-hidden', 'true');
    c.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
    c.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); vaultCover(false); });  // 回到 App 后点一下就拿掉
    document.body.append(c); }
  return c;
}
/* 回到 App 自动拿掉黑色（2026-11-06 用户：不要再点一下）。iPhone 上滑看后台时常常一个事件都不给（没有 blur / focus / visibilitychange），
   所以盖着的时候自己看“页面还在不在画”：后台列表里 App 不画画面（requestAnimationFrame 停了、计时器也停了），回到 App 又接着画 ——
   停过一阵又画出下一帧 = 回来了，马上拿掉。
   上滑一点又松手、根本没离开时，画面一直在画、没有停顿可以判断：只有这台手机已经证明过“离开时会停画”（记在 localStorage），
   才把“连续画了 3 秒都没停”当成没离开、拿掉；没证明过就还是点一下拿掉（宁可多点一下，也不在后台列表里露出内容） */
const VC = { on: false, why: '', t0: 0, last: 0, gap: false, away: false, raf: 0, iv: 0 };
function vcStop() { cancelAnimationFrame(VC.raf); clearInterval(VC.iv); VC.raf = VC.iv = 0; }
function vcWatch() {
  vcStop(); const now = performance.now(); Object.assign(VC, { t0: now, last: now, gap: false, fast: 0 });
  const back = () => { if (document.hidden) return; try { localStorage.setItem('vcPause', '1'); } catch { } vaultCover(false); };
  const step = t => {
    if (!VC.on) return;
    const d = t - VC.last; VC.last = t;
    if (d > 450) { VC.gap = true; VC.fast = 0; }  // 停过一阵（离开过）
    else if (VC.gap) { VC.fast = d < 50 ? VC.fast + 1 : 0; if (VC.fast >= 3) return back(); }  // 停过之后又按正常速度连续画了几帧：回来了（后台列表里偶尔慢慢画一帧不算）
    if (!VC.gap && !VC.away && VC.why === 'swipe' && t - VC.t0 > 3000 && localStorage.getItem('vcPause') === '1' && !document.hidden) return vaultCover(false);  // 没离开过（只是上滑一点又松手）
    VC.raf = requestAnimationFrame(step);
  };
  VC.raf = requestAnimationFrame(step);
  let tick = Date.now();  // 有的系统停画时 requestAnimationFrame 会一下子补上，计时器停顿再看一遍
  VC.iv = setInterval(() => { const n = Date.now(); if (n - tick > 1200) { VC.gap = true; VC.fast = 0; } tick = n; }, 250);  // 只记“停过”，回没回来还是看画面是否恢复正常速度
}
function vaultCover(on, why = '') {
  if (on && !VAULT) return;
  const c = on ? vaultCoverEl() : document.getElementById('vault-cover'); if (!c) return;
  if (on) { if (!VC.on) { VC.on = true; VC.why = why; VC.away = false; c.classList.add('on'); void c.offsetHeight; vcWatch(); } else if (why !== 'swipe') VC.away = true; }  // 已经盖着又收到离开的消息：确实离开了
  else { VC.on = false; vcStop(); c.classList.remove('on'); }
}
document.addEventListener('visibilitychange', () => { if (document.hidden) { vaultCover(true, 'hide'); VC.away = true; } else vaultCover(false); });
addEventListener('pagehide', () => { vaultCover(true, 'hide'); VC.away = true; });
addEventListener('pageshow', () => vaultCover(false));
addEventListener('freeze', () => { VC.away = true; });
addEventListener('resume', () => { if (!document.hidden) vaultCover(false); });
/* 键盘（2026-11-09 用户 iPad：私密空间里收起键盘时也会盖上黑色）：iPad 收键盘时窗口会收到一次 blur；主屏 App 收键盘后页面高度有时恢复不了
   （WebKit 254861），“屏幕最下面那一窄条”就跑到屏幕中间。所以：正在打字 / 刚收起键盘 0.8 秒内的 blur 不当成离开（真上滑时系统比 blur 先拍预览，
   这次 blur 本来也盖不住）；键盘开着、或页面比这个宽度下见过的最高还矮一截时，不按主屏条上滑算 */
const VC_KB = { t: 0, fullH: {} }, VC_VV = window.visualViewport;
const vcEd = a => !!a?.matches?.('textarea, input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=button]):not([type=submit]), [contenteditable="true"], [contenteditable=""]');
const vcKbNow = () => vcEd(document.activeElement) || performance.now() - VC_KB.t < 800 || !!VC_VV && innerHeight - VC_VV.height * (VC_VV.scale || 1) > 80;  // 双指放大时可视区域也变矮：按缩放还原再比
document.addEventListener('focusout', e => { if (vcEd(e.target)) VC_KB.t = performance.now(); }, true);  // 离开输入框 = 键盘在收起
VC_VV?.addEventListener('resize', () => { VC_KB.t = performance.now(); });
const vcFull = () => { const k = innerWidth, h = innerHeight; if (!vcKbNow()) VC_KB.fullH[k] = Math.max(VC_KB.fullH[k] || 0, h); return h >= (VC_KB.fullH[k] || h) - 40; };
addEventListener('resize', () => setTimeout(vcFull, 900));
addEventListener('blur', () => { if (VC_TOUCH.matches && !vcKbNow()) { vaultCover(true, 'blur'); VC.away = true; } });
addEventListener('focus', () => { if (!document.hidden) vaultCover(false); });
let vcArm = false;
addEventListener('touchstart', e => {
  if (!VAULT || !VC_TOUCH.matches) return;
  vaultCoverEl();  // 私密空间里第一次碰屏幕就把黑色那块建好
  const t = e.touches[0]; vcArm = e.touches.length === 1 && t && t.clientY > innerHeight - 34 && !vcKbNow() && vcFull();  // 主屏条那一窄条（键盘开着 / 页面高度没恢复时不算）
}, { capture: true, passive: true });
addEventListener('touchend', () => { vcArm = false; }, { capture: true, passive: true });
addEventListener('touchcancel', () => { if (vcArm && VAULT) vaultCover(true, 'swipe'); vcArm = false; }, { capture: true, passive: true });
/* 面容 ID 进私密空间（2026-11-06，设置 → 面容 ID 解锁（本机））：按住页面标题约 0.8 秒再松开 → 系统弹出面容 ID → 通过就进入。
   只在这台设备开启过（localStorage 'ui.lp'）时才有反应，不显示任何按钮。按下时先去要挑战；iPhone 要求在松手（点按）里直接调用验证 */
/* 11-19 用户：手机上这个入口没了——生视频、AI 助手（电脑上全部页面）的标题位置换成了“生成视频 ⌄”这类切换按钮，.page-title 藏起来了，
   而且标题字只有两三个字宽，手指不好按中。现在：标题、标题位置的切换按钮、标题栏的空白处都算；按住够久、去验证了，松手后的那一下点击不再打开切换菜单 */
let pkHold = null, pkSup = 0;
const PK_AT = t => !!t?.closest?.('.page-title, #main > .page-head .b5-ctx, #main .pg-top .pg-cap') || !!t?.matches?.('#main > .page-head, #main > .page-head > div:not([class]), #main > .page-head > .b5-l, #main .pg-top');
addEventListener('click', e => { if (pkSup && performance.now() - pkSup < 900) { pkSup = 0; e.preventDefault(); e.stopPropagation(); } }, true);
addEventListener('pointerdown', e => {
  if (VAULT || localStorage.getItem('ui.lp') !== '1' || !window.PublicKeyCredential || !PK_AT(e.target)) return;
  const h = pkHold = { t: Date.now(), x: e.clientX, y: e.clientY, o: null };
  fetch('/api/vault/passkey/begin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => r.ok ? r.json() : (r.status === 404 && localStorage.removeItem('ui.lp'), null)).then(o => { h.o = o; }).catch(() => { });
}, true);
addEventListener('pointermove', e => { if (pkHold && Math.hypot(e.clientX - pkHold.x, e.clientY - pkHold.y) > 12) pkHold = null; }, true);
addEventListener('pointercancel', () => { pkHold = null; }, true);
addEventListener('pointerup', async e => {
  const h = pkHold; pkHold = null;
  if (!h || VAULT || Date.now() - h.t < 800 || !h.o) return;
  e.preventDefault(); pkSup = performance.now();
  const b = s => { s = String(s).replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(s + '='.repeat((4 - s.length % 4) % 4)), c => c.charCodeAt(0)); };
  const u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  try {
    const c = await navigator.credentials.get({ publicKey: { ...h.o, challenge: b(h.o.challenge), allowCredentials: (h.o.allowCredentials || []).map(x => ({ ...x, id: b(x.id) })) } });
    const r = await fetch('/api/vault/passkey/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: c.id, clientDataJSON: u(c.response.clientDataJSON), authenticatorData: u(c.response.authenticatorData), signature: u(c.response.signature) }) });
    if (r.status === 429) return toast('尝试次数过多，请 10 分钟后再试', true);
    if (r.ok && !VAULT) vaultEnter();
  } catch { }  // 取消了 / 没通过：什么也不提示（和没有这个入口一样）
}, true);
let keyBuf = '', keyT = 0, VK = null, VKS = '';  // VK：服务器给的 2 位提示，VKS：提示盐（真正的校验值只在服务器，2026-11-17 F08）
function sha256js(str) {  // 手机通过 http 打开时浏览器不给 crypto.subtle：用这个
  const K = [], H = [], b = new TextEncoder().encode(str), n = ((b.length + 9 + 63) >> 6) << 6, m = new Uint8Array(n), w = new Uint32Array(64);
  let p = 2;
  for (let c = 0; c < 64;) { let ok = true; for (let d = 2; d * d <= p; d++) if (p % d === 0) { ok = false; break; } if (ok) { if (c < 8) H[c] = (Math.pow(p, 1 / 2) % 1) * 2 ** 32 | 0; K[c++] = (Math.pow(p, 1 / 3) % 1) * 2 ** 32 | 0; } p++; }
  m.set(b); m[b.length] = 0x80; const dv = new DataView(m.buffer); dv.setUint32(n - 4, b.length * 8); dv.setUint32(n - 8, Math.floor(b.length / 2 ** 29));
  const r = (x, k) => (x >>> k) | (x << (32 - k));
  for (let o = 0; o < n; o += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + i * 4);
    for (let i = 16; i < 64; i++) w[i] = (w[i - 16] + (r(w[i - 15], 7) ^ r(w[i - 15], 18) ^ (w[i - 15] >>> 3)) + w[i - 7] + (r(w[i - 2], 17) ^ r(w[i - 2], 19) ^ (w[i - 2] >>> 10))) | 0;
    let [a, bb, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (r(e, 6) ^ r(e, 11) ^ r(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0, t2 = ((r(a, 2) ^ r(a, 13) ^ r(a, 22)) + ((a & bb) ^ (a & c) ^ (bb & c))) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = bb; bb = a; a = (t1 + t2) | 0;
    }
    [a, bb, c, d, e, f, g, h].forEach((x, i) => { H[i] = (H[i] + x) | 0; });
  }
  return H.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
}
const sha256hex = async s => crypto.subtle ? [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(x => x.toString(16).padStart(2, '0')).join('') : sha256js(s);
/* 最近打的 6 个字是不是密钥：先在本地比哈希的前两位（大部分直接排除，不用每打一个字都问服务器），对上了再让服务器核对。
   服务器那边 10 分钟里错 20 次就暂停，不能被一个个试出来。 */
async function vaultTry(guess, el) {
  if (VAULT || !VK || guess.length < VAULT_KEYS_LEN) return;
  if ((await sha256hex(VKS + guess)).slice(0, 2) !== VK) return;
  let r = null;
  try { r = await fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: guess }) }); } catch { }
  if (r?.status === 429) return toast('尝试次数过多，请 10 分钟后再试', true);
  if (!r?.ok || VAULT) return;
  // 在输入框里打的密钥：从文字里删掉
  if (el && ('value' in el) && typeof el.value === 'string') {
    const pos = el.selectionStart ?? el.value.length, before = el.value.slice(0, pos);
    if (before.toLowerCase().endsWith(guess)) { el.value = before.slice(0, -guess.length) + el.value.slice(pos); el.dispatchEvent(new Event('input')); }
  }
  keyBuf = '';
  vaultEnter();
}
document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
  keyT = Date.now();
  keyBuf = (keyBuf + e.key.toLowerCase()).slice(-VAULT_KEYS_LEN);
  if (VAULT || keyBuf.length < VAULT_KEYS_LEN) return;
  const guess = keyBuf, el = e.target;
  setTimeout(() => vaultTry(guess, el), 0);  // 等这个字先进了输入框
}, true);
// 手机键盘打字不一定有按键事件：在输入框里打字时看光标前面的 6 个字
document.addEventListener('input', e => {
  const el = e.target;
  if (VAULT || Date.now() - keyT < 100 || !el || typeof el.value !== 'string' || el.type === 'password') return;
  const pos = el.selectionStart ?? el.value.length, guess = el.value.slice(Math.max(0, pos - VAULT_KEYS_LEN), pos).toLowerCase();
  if (guess.length === VAULT_KEYS_LEN) vaultTry(guess, el);
}, true);
function vaultSwitchUI(on) {
  VAULT = on; document.body.classList.toggle('vault', on);
  RC.ac?.abort();  // 手机：挂着的等命令请求是那一边的，取消，按这一边重新等
  if (!on) { rcStop(false); RC.parked = 0; }  // 电脑退出私密空间：不再控制手机（后台那边退出时已关掉）。手机退出时照常（电脑开着控制的话接着放，见 vaultLock2）
  else { RC.noAuto = false; clearTimeout(RC.pollT); RC.pollT = setTimeout(rcPoll, 1000); }  // 电脑进私密空间：开始看有没有手机在放
  rcBtn();
  if (on) vaultCoverEl(); else vaultCover(false);  // 进私密空间就把后台预览用的黑色那块建好（隐藏着）；退出时拿掉
  $$('.vault-only').forEach(x => x.hidden = !on);
  const ex = $('#vault-chip'); if (ex) { ex.hidden = !on; ex.onclick = () => vaultLock(); ex.title = '点击退出私密空间'; }  // 整个标签都能点
  window.Glide?.refresh();  // 私密空间里选中色不同
}
function spaceSwap() {  // 进出私密空间：见 NSTASH
  persistFlush();  // 排着的写入先按换空间之前的状态写掉
  document.getElementById('ig-mask-ov')?.remove();  // 放大涂抹的层：换页 / 进出私密空间时收掉
  pgAbort();
  const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  // 生图 / 生视频输入框另存在 sessionStorage 的草稿：两个空间共用一份，进出时都清掉（提示词本身随 S.img / S.vidg 换回来）
  sessionStorage.removeItem('igDraft'); sessionStorage.removeItem('vdDraft'); sessionStorage.removeItem('veDraft');
  if (VAULT && !NSTASH) {
    NSTASH = {}; NKEYS.forEach(k => { NSTASH[k] = clone(S[k]); });
    S.text = ''; S.img = Object.assign({}, S.img, { prompt: '', seed: -1, srcId: null });
    S.pg = { preset: S.pg?.preset, params: S.pg?.params, msgs: [], draft: '' }; S.ttsRec = []; S.pgHist = []; S.vidg = { model: S.vidg?.model };
    S.jobId = null; Object.assign(V(), { jobId: null, view: 'new', jobSrc: null, src: null, voice: null });
  } else if (!VAULT && NSTASH) {
    clearTimeout(vpT); vpT = 0; VPREFS_OK = false;
    NKEYS.forEach(k => { S[k] = NSTASH[k]; }); NSTASH = null;
    PLSC.v = {}; delete VMEM.playpos;
  }
  imgGal = []; IMG_SRC = null; IMG_MASK = null; if (typeof VID_SRC !== 'undefined') { VID_SRC = null; VID_END = null; vidGal = []; vidStage.cur = null; vidStage.last = null; vidStage.top = undefined; renderVideo.entered = false; if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = null; VE_REF = null; }  // 改视频的原视频 / 人物图也是那一边的
  // 2026-11-08：换了空间也算第一次进生视频页（成品页空着）；“看过的最新一段”换成这边的，不然这边最新那段会被当成新生成的自动打开
  PG_IMG = null; PG_AUTO = false; imgStage.cur = null; IMG_CTL = null; IMG_REFS = []; PG_ORIG.clear();  // AI 助手待发的图、反推自动发送、右边大图选中的那张：都是那一边的，不带过来
  createDesign.state = null; sttCur = null; PGST = null;  // 提示词预设两个空间各一份
  Object.assign(AE, { a: '', b: '', secs: '', src: null });  // 改录音的原文 / 新文 / 选的录音也是那一边的（2026-11-14 审查：以前进出私密空间还留着上一边的文件）
  spaceUI();
}
/* 两个空间各一份的界面设置（S.ui）里，会直接改变页面样子的那几项：每次换了 S.ui（进出私密空间、读进私密空间的设置）都按当前这一边重新套上。
   2026-11-09 用户：私密空间里防窥模式自己开了、开关却显示“关”——在私密空间里刷新页面时，启动先按普通空间的设置套上防窥，换成私密空间的设置后没再套；
   收起播放条也一样。以后 S.ui 里再加会改页面样子的项，也加在这里 */
function spaceUI() { window.TPL?.load();  // 换了空间：模板套跟着换（各空间各自的默认）

  applyGuard();
  if (document.body.classList.contains('pb-min') !== !!S.ui?.pbMin) pbMin(!!S.ui?.pbMin, false);
  try { capPaint(); if (!$('#np')?.hidden) npTheater(); } catch { }  // 画面字幕、播放页铺满：播放页开着时
}
async function vaultReloadData() {
  spaceSwap();
  VGEN++; try { Sound.clearLayers(); } catch { }  // 叠加在上面的音轨也是那一边的
  // 开着的弹窗、右键菜单、叠加面板、提示都是那一边的内容：一起关掉
  if (curPop) curPop.close(true);
  ImageViewer.close(); ctxClose(true); spClose();
  $$('.modal-bg').forEach(b => { $('.modal', b)?.close?.(); b.remove(); });
  $$('.toast.new-files').forEach(t => t.remove());
  playQ = ''; playSrc = ''; playAll = false;  // 搜索框里的字、选中的文件夹不带到另一边
  pbReset(true); libCache = null; FAVS = new Set(); LIBNEW = []; LIBFLASH = new Set(); TAGS = {};  // 两个空间互相看不到：新增列表、标签也清掉
  if (VAULT) await vprefsLoad();  // 私密空间上次的设置
  persist();
  spaceUI();  // 2026-11-08：两个空间的界面设置各一份（S.ui），防窥也在里面——换完要按这一边的重新套上（以前留着另一边的，开关显示“关”、页面却是开着的）
  await loadVoices();
}
async function vaultEnter(msg = '已进入私密空间') {
  if (VAULT) return;
  sessionStorage.setItem('vaultTab', '1');
  vaultSwitchUI(true); await vaultReloadData();
  toast(msg);
  go('play');
}
async function vaultLock(msg = '已退出私密空间') {
  if (typeof msg !== 'string') msg = '已退出私密空间';
  if (!VAULT || vaultLock._busy) return;
  vaultLock._busy = true; try { await vaultLock2(msg); } finally { vaultLock._busy = false; }
}
async function vaultLock2(msg) {
  sessionStorage.removeItem('vaultTab');
  if (curPop) curPop.close(true);
  ImageViewer.close();
  if (vpT) await vprefsSave(true);  // 还没存的设置先存好（退出后就存不进私密空间了）
  const hand = await rcHandoff();  // 手机：电脑开着控制、正在放 → 退出后接着放（换成一次性地址）
  RC.lock = true;  // 退出的这一下不报状态（凭证已经退掉、空间还没切过来，会被拒）
  await fetch('/api/vault/lock', { method: 'POST' }).catch(() => { });
  vaultSwitchUI(false); RC.lock = false; await vaultReloadData();
  if (hand) rcResume(hand);
  toast(msg);
  go('tts');
}
/* 自动退出：私密空间里一段时间没动鼠标键盘、也没在播放，就自动退出（时间在齿轮里设，默认 15 分钟）。
   一直在播放不算“没操作”：播完以后再开始计时，比如听着睡着了，播完 15 分钟后自动退出。 */
let idleT = Date.now();
['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'].forEach(t => addEventListener(t, () => { idleT = Date.now(); }, { capture: true, passive: true }));
setInterval(() => {
  const m = S.lockMin ?? 15;
  if (!VAULT || !m) return;
  if ((PB.a && !PB.a.paused) || (extOn() && !PB.ext?.paused)) { idleT = Date.now(); return; }
  if (Date.now() - idleT > m * 60000) vaultLock(`${m} 分钟无操作，已自动退出私密空间`);
}, 15000);
/* 一键隐藏（老板键）Ctrl + Alt + H：暂停、关掉应用外的小窗、退出私密空间。在桌面应用里任何时候按都有效（不用先切到这个窗口），
   窗口同时收进右下角托盘；再按一次窗口回来（回来的是普通界面）。 */
window.bossKey = async () => {
  if (MINI_OUT === 'win') await appReturn('close').catch(() => { });
  try { if (PB.a && !PB.a.paused) PB.a.pause(); } catch { }
  try { if (!qAudio.paused) qAudio.pause(); } catch { }
  ImageViewer.close();
  if (VAULT) await vaultLock();
};
/* 点 ×（或 Alt + F4、任务栏“关闭窗口”）收进托盘时（app.py hide_to_tray 通知过来）：正在私密空间就退出（2026-11-08 用户）；
   放着的私密空间的视频 / 声音一起停（退出时本来就会停），普通空间的音乐照常接着放 */
window.trayHidden = async () => {
  if (!VAULT) return;  // 普通空间：什么都不动
  ImageViewer.close(); if (MINI_OUT === 'win') await appReturn('close').catch(() => { });
  await vaultLock('已收进托盘，并退出了私密空间');
};
document.addEventListener('keydown', e => {  // 桌面应用里已经注册成全局快捷键，这里是网页 / 注册失败时的后备
  if (!(e.ctrlKey && e.altKey && !e.shiftKey && e.key.toLowerCase() === 'h')) return;
  e.preventDefault(); e.stopPropagation();
  if (window.pywebview?.api?.boss) window.pywebview.api.boss(); else bossKey();
}, true);

/* ================= 播放页（私密空间）：音源库 + 这里的作品 / 历史记录 ================= */
let playSrc = '', playQ = '', playAll = false, libCache = null, SRC_ORDER = {}, PLAY_FRESH = NEW_SESSION;
/* 我的收藏：只记住是哪几个文件，不移动文件本身；存在私密空间里，退出后看不到 */
let FAVS = new Set(), TAGS = {};
/* 新文件自动出现：每 20 秒看一眼音源库（服务器那边 10 秒内的扫描结果直接复用）；从别的窗口（比如资源管理器）切回来时马上重新扫一遍。
   有新文件就弹出“新增 N 个 · 查看”，点一下跳到“最近新增”，新文件会闪一下。删掉的文件也会自动从列表里消失。
   列表右上角菜单里的“刷新音源库” = 立刻重新扫一遍。返回 true 有变化 / false 没变化 / null 没扫成 */
let LIBNEW = [], LIBFLASH = new Set(), IMGCACHE = null;
async function libWatch(fresh) {
  if (document.hidden || !libCache) return null;
  const gen = VGEN;
  // 带上次的指纹：没变化时服务器只回 same（不再每 20 秒把整个列表传一遍，手机上尤其省）
  const q = k => (fresh ? '&fresh=1' : '') + '&sig=' + encodeURIComponent(libWatch[k] || '0');  // 空的参数服务器会当成没带：第一次也带一个
  const [lr, ir] = await Promise.all([api('/api/play/library?' + q('ls').slice(1)).catch(() => null), api('/api/play/images?' + q('is').slice(1)).catch(() => null)]);
  const pick = (r, old) => !r ? null : Array.isArray(r) ? r : r.same ? old : r.items;  // 旧版服务器直接回列表
  if (gen !== VGEN || !libCache) return null;  // 扫描期间进出了私密空间：这份结果是另一边的，不用（签名也不能记）
  const lib = pick(lr, libCache), imgs = pick(ir, IMGCACHE);
  if (!lib) return null;
  // 2026-11-17 审查 F12：签名和对应的列表一起更新。以前先记下新签名，路径一样（同名替换）就不换列表，
  // 之后服务器一直回 same，客户端永远拿着旧的时长 / 修改时间
  if (lr?.sig && !lr.same) libWatch.ls = lr.sig; if (ir?.sig && !ir.same) libWatch.is = ir.sig;
  const meta = x => [x.path, x.mtime, x.size, x.dur].join('|');
  const was = new Map(libCache.map(x => [x.path, meta(x)])), now = new Set(lib.map(x => x.path));
  const added = lib.filter(x => !was.has(x.path)), gone = libCache.some(x => !now.has(x.path));
  const changed = lib !== libCache && lib.some(x => was.has(x.path) && was.get(x.path) !== meta(x));  // 同名替换：路径没变，内容变了
  const imgDiff = !!imgs && !!IMGCACHE && (imgs.length !== IMGCACHE.length || imgs.some((x, k) => meta(x) !== meta(IMGCACHE[k])));
  if (imgs) IMGCACHE = imgs;
  if (!added.length && !gone && !imgDiff && !changed) return false;
  libCache = lib;
  LIBNEW = [...added.sort((a, b) => b.mtime - a.mtime).map(x => x.path), ...LIBNEW.filter(pth => now.has(pth))];
  if (location.pathname === '/play' && !playQ && !$('#play-src')?.classList.contains('ps-sorting')) renderPlay(true);  // 正在拖文件夹排序时不重画
  if (added.length) newFilesToast(added);
  return true;
}
setInterval(libWatch, 20000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) libWatch(); });
let libFocusT = 0;
addEventListener('focus', () => { if (Date.now() - libFocusT < 4000) return; libFocusT = Date.now(); libWatch(location.pathname === '/play'); });
function newFilesToast(added) {
  $$('.toast.new-files').forEach(t => t.remove());
  const t = document.createElement('button'); t.type = 'button'; t.className = 'toast new-files';
  t.innerHTML = `${ICON.sparkle}<span>音源库新增 ${added.length} 个文件</span><b>查看</b>`;
  t.onclick = () => {
    t.remove();
    LIBFLASH = new Set(added.map(x => 'lib:' + x.path)); setTimeout(() => { LIBFLASH = new Set(); }, 4000);
    playSrc = 'new'; playQ = '';
    if (location.pathname === '/play') renderPlay(); else go('play');
  };
  document.body.appendChild(t); toastStack();
  setTimeout(() => { if (t.isConnected) { t.classList.add('out'); setTimeout(() => { t.remove(); toastStack(); }, 260); } }, 9000);
}
/* 标签：给音源加几个自己的分类（比如“睡前”“学习”），左侧会出现按标签筛选的列表 */
function tagPopover(anchor, key, all, after) {
  let cur = [...(TAGS[key] || [])];
  const draw = pop => {
    $('.tag-chips', pop).innerHTML = [...new Set([...all, ...cur])].map(t => `<button type="button" class="chip${cur.includes(t) ? ' on' : ''}" data-t="${esc(t)}">${esc(t)}</button>`).join('') || '<span class="tiny">暂无标签</span>';
    $$('[data-t]', pop).forEach(b => b.onclick = () => { const t = b.dataset.t; cur = cur.includes(t) ? cur.filter(x => x !== t) : [...cur, t]; save(pop); });
  };
  const save = async pop => { TAGS = await api('/api/play/tags', { body: { key, tags: cur } }).catch(() => TAGS); draw(pop); after?.(); };
  popover(anchor, `<div class="tag-pop"><div class="sec-label" style="margin-top:0">标签</div><div class="tag-chips"></div>
      <div class="row" style="gap:6px;margin-top:10px"><input class="input" id="tag-new" placeholder="新标签" maxlength="24" style="flex:1;min-width:0"><button class="btn small" id="tag-add">添加</button></div></div>`,
    pop => {
      draw(pop);
      const add = () => { const v = $('#tag-new', pop).value.trim(); if (!v) return; $('#tag-new', pop).value = ''; if (!cur.includes(v)) cur = [...cur, v]; all = [...new Set([...all, v])]; save(pop); };
      $('#tag-add', pop).onclick = add; $('#tag-new', pop).onkeydown = e => { if (e.key === 'Enter') add(); };
      setTimeout(() => $('#tag-new', pop)?.focus(), 30);
    }, { width: 260 });
}
async function loadFavs() { FAVS = new Set((await api('/api/play/favs').catch(() => [])).map(f => f.key)); }
async function toggleFav(key, on = !FAVS.has(key)) {
  on ? FAVS.add(key) : FAVS.delete(key);
  try { await api('/api/play/favs', { body: { key, on } }); }
  catch (e) { on ? FAVS.delete(key) : FAVS.add(key); return toast('收藏失败：' + e.message, true); }
  $$(`[data-fav="${CSS.escape(key)}"]`).forEach(b => { b.classList.toggle('on', on); setIcon(b, on ? 'heartFill' : 'heart'); });
  favPaintNow(); PB.onFav?.();
  toast(on ? '已收藏' : '已取消收藏');
}
const favBtn = (key, cls = '') => `<button class="fav-btn ${cls} ${FAVS.has(key) ? 'on' : ''}" data-fav="${esc(key)}" data-icon="${FAVS.has(key) ? 'heartFill' : 'heart'}" title="收藏">${FAVS.has(key) ? ICON.heartFill : ICON.heart}</button>`;
function favPaintNow() {  // 全屏播放页标题旁的收藏按钮
  const b = $('#np-fav'), k = RC.ctl ? RC.st?.key : qCur()?.key;  // 控制手机时：手机正在放的那首（私密空间里的）
  if (!b) return; b.hidden = !(k && (RC.ctl || PB.a === qAudio));
  if (k) { b.dataset.fav = k; b.classList.toggle('on', FAVS.has(k)); setIcon(b, FAVS.has(k) ? 'heartFill' : 'heart'); }
}
const fmtSize = b => b > 1 << 30 ? (b / (1 << 30)).toFixed(1) + ' GB' : b > 1 << 20 ? (b / (1 << 20)).toFixed(0) + ' MB' : Math.max(1, b >> 10) + ' KB';
const libUrl = path => '/media/lib/' + path.split('/').map(encodeURIComponent).join('/');
const thumbUrl = path => '/media/thumb/' + path.split('/').map(encodeURIComponent).join('/');
const dirLabel = d => d === '未分类' ? '根目录' : d;  // 直接放在音源库里、没放进文件夹的文件
const KINDS = [['all', '全部'], ['video', '视频'], ['audio', '音频'], ['image', '图片']];
const PL_CHEV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>', PL_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const SI = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const SORTS = [  // 播放页的排序方式（名称、菜单里的图标）
  ['default', '默认', SI('<path d="M7 5v14M4 8l3-3 3 3M17 19V5M14 16l3 3 3-3"/>')],
  ['new', '最新', SI('<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>')],
  ['size', '最大', SI('<path d="M4 20h16M6.5 20v-6M12 20V8M17.5 20V4"/>')],
  ['name', '名称', SI('<path d="M4 17l3.5-10L11 17M5.2 13.5h4.6M14 7h6l-6 10h6"/>')]];
async function plRefresh() {  // 马上找出刚放进音源库的文件（切回窗口时、每 20 秒也会自动找）
  const r = await libWatch(true);
  toast(r === null ? '刷新失败' : r === false ? '已刷新，无新文件' : '已刷新', r === null);
}
const VIEWS = [  // 播放页列表的显示方式（像访达里的“列表 / 图标”）
  ['list', '列表', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01"/></svg>'],
  ['grid', '封面网格', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/></svg>']];
/* 右键菜单：items = [{ label, icon, on, danger }] 或 '-'（分隔线）。点外面、Esc、滚动、切到别的窗口都会关掉 */
let CTX = null;
const CI = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const CTX_IC = {
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.1"/></svg>',  // 详情（2026-11-16：以前用的是文件夹图标）
  expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
  open: CI('<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>'),
  reveal: CI('<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/><path d="M14 13.5h-5M11.5 11l2.5 2.5-2.5 2.5"/>'),
  del: CI('<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5M10 11v5.5M14 11v5.5"/>'),
};
/* 手机上没有右键：长按 0.5 秒（手指没怎么动）就当成右键，弹出同一个菜单；松手后的那一下点击不再算 */
(() => {
  let t = 0, x0 = 0, y0 = 0, fired = false;
  const LP = '.pl-row, .img-tile, .ps-dir, .pl-dirhit, .ig-tile';  // 有右键菜单的那些
  addEventListener('touchstart', e => {
    fired = false; clearTimeout(t);
    const el = e.target.closest?.(LP); if (!el || e.touches.length !== 1) return;
    const p = e.touches[0]; x0 = p.clientX; y0 = p.clientY;
    t = setTimeout(() => { fired = true; e.target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: x0, clientY: y0 })); }, 500);
  }, { passive: true });
  addEventListener('touchmove', e => { const p = e.touches[0]; if (p && Math.hypot(p.clientX - x0, p.clientY - y0) > 10) clearTimeout(t); }, { passive: true });
  addEventListener('touchend', () => clearTimeout(t), { passive: true });
  addEventListener('click', e => { if (fired) { fired = false; e.preventDefault(); e.stopPropagation(); } }, true);
})();
function ctxMenu(e, items) {  // e：右键事件；或 { anchor: 按钮, onClose } —— 贴着按钮下方、右边对齐弹出
  e.preventDefault?.(); ctxClose(true);
  if (e.anchor && window.ctxAnchorFor && !e.anchor.getClientRects().length) e = { ...e, anchor: window.ctxAnchorFor };  // 右栏收起时点输入框上的素材格：菜单贴着那一格
  const m = document.createElement('div'); m.className = 'dd-menu ctx-menu' + (e.anchor ? ' anchored' : ''); m.setAttribute('role', 'menu');
  const html = list => list.map((it, i) => it === '-' ? '<div class="ctx-sep"></div>' : it.group ? `<div class="dd-g">${esc(it.group)}</div>`
    : `<div class="dd-i ctx-i${it.danger ? ' danger' : ''}${it.checked ? ' on' : ''}" data-i="${i}" role="menuitem"><span class="ctx-ic">${it.icon || ''}</span><span>${esc(it.label)}</span>${it.checked !== undefined ? `<span class="ctx-k">${it.checked ? PL_CHECK : ''}</span>` : it.hint ? `<span class="ctx-k ctx-hint">${esc(it.hint)}</span>` : ''}${it.sub ? `<span class="ctx-k ctx-subk">${CTX_SUBK}</span>` : ''}</div>`).join('');
  m.innerHTML = html(items);
  document.body.append(m);
  const w = m.offsetWidth, h = m.offsetHeight, r = e.anchor?.getBoundingClientRect();
  const x = r ? r.right - w : e.clientX, y = r ? r.bottom + 6 : e.clientY, up = y + h > innerHeight - 8;
  m.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + 'px';
  m.style.top = (up ? Math.max(8, (r ? r.top - 6 : y) - h) : y) + 'px';
  if (up) m.classList.add('up');
  m._close = e.onClose;
  void m.offsetWidth; m.classList.add('show');  // 先排版一次再加 show，淡入动画才会播放
  // 二级菜单（2026-11-18 用户：右上角 ⋯ 里字幕那些收成一个“字幕”，移上去再展开）
  let subM = null;
  const subClose = () => { subM?.remove(); subM = null; m.querySelector('.sub-open')?.classList.remove('sub-open'); };
  const subOpen = d => {
    const it = items[+d.dataset.i]; if (subM && subM._d === d) return; subClose(); if (!it?.sub) return;
    const sm = document.createElement('div'); sm.className = 'dd-menu ctx-menu ctx-subm'; sm.setAttribute('role', 'menu'); sm._d = d; sm.innerHTML = html(it.sub);
    document.body.append(sm); d.classList.add('sub-open');
    const mr = m.getBoundingClientRect(), dr = d.getBoundingClientRect(), sw = sm.offsetWidth, sh = sm.offsetHeight;
    let x = mr.right - 4; if (x + sw > innerWidth - 8) x = mr.left - sw + 4;
    sm.style.left = Math.max(8, x) + 'px'; sm.style.top = Math.max(8, Math.min(dr.top - 6, innerHeight - sh - 8)) + 'px';
    void sm.offsetWidth; sm.classList.add('show');
    sm.onclick = ev => { const q = ev.target.closest('[data-i]'); if (!q) return; const f = it.sub[+q.dataset.i]; ctxClose(); f.on(); };
    subM = sm;
  };
  m._subClose = subClose;
  m.addEventListener('pointerover', ev => { const d = ev.target.closest('.ctx-i'); if (d) subOpen(d); });
  m.onclick = ev => { const d = ev.target.closest('[data-i]'); if (!d) return; if (items[+d.dataset.i].sub) return subOpen(d); ctxClose(); items[+d.dataset.i].on(); };
  CTX = m;
}
const CTX_SUBK = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>';
/* 2026-11-10 用户：基本都从素材库选——空的素材格（原视频 / 首帧 / 原图 / 参考图 / 尾帧）电脑上点一下直接打开素材库，
   其余来源（电脑、视频库、粘贴…）放在素材库窗口右上角（galPick 读 MATS_ALT）；手机上、右键照旧弹菜单。items[0] 是“从素材库选” */
function slotPick(anchor, items) {
  if (!/素材库/.test(items[0]?.label || '')) return ctxMenu({ anchor }, items);  // 2026-11-16 用户：手机上也是点一下就进素材库（其余来源在素材库窗口的“···”里）
  window.MATS_ALT = items.slice(1).filter(it => it && it !== '-' && !it.group && !it.danger);
  try { items[0].on(); } finally { window.MATS_ALT = null; }
}
function ctxClose(instant) {
  const m = CTX; if (!m) return; CTX = null; m._close?.(); m._subClose?.();
  if (instant) return m.remove();
  m.classList.remove('show'); setTimeout(() => m.remove(), 140);
}
addEventListener('pointerdown', e => {
  if (!CTX || e.target.closest('.ctx-menu')) return;
  const a = e.target.closest('.pl-opts, .pl-kind'); if (a?.classList.contains('open')) { a._skip = true; setTimeout(() => { a._skip = false; }, 400); }
  ctxClose();
}, true);
addEventListener('keydown', e => { if (CTX && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); ctxClose(); } }, true);
addEventListener('scroll', e => { if (!(e.target instanceof Element && e.target.closest('.ctx-menu'))) ctxClose(); }, true);  // 菜单自己里面滚动（项目多时）不关（2026-11-10 用户：往下滑就消失，选不到下面的）
 addEventListener('blur', () => ctxClose()); addEventListener('resize', () => ctxClose());
/* 音源库里的文件 / 文件夹：在资源管理器里打开、移到回收站（只在电脑上；手机访问时没有这两项） */
const libReveal = (path, dir) => api('/api/play/reveal', { body: { path, dir } }).catch(e => toast(e.message, true));
function libDelete(path, dir, name, count) {
  const perm = VAULT;  // 私密空间里：永久删除（回收站里谁都能看到、还原）
  modal(`<h3 class="card-title" style="margin:0 0 8px">${perm ? '永久删除' : '将'}${dir ? '文件夹' : ''}「${esc(name)}」${perm ? '' : '移到回收站'}？</h3>
    <div class="tiny" style="line-height:1.7">${dir ? `文件夹中的 ${count} 个文件将一并${perm ? '删除' : '移走'}。` : ''}${perm ? '私密空间中的文件不会放入回收站（以免他人在回收站中看到），<b>删除后无法恢复</b>。' : '如有需要，可从 Windows 回收站中还原。'}</div>
    <div class="row" style="justify-content:flex-end;gap:8px;margin-top:18px"><button class="btn" data-close>取消</button><button class="btn del-solid" id="del-ok">${CTX_IC.del}${perm ? '永久删除' : '移到回收站'}</button></div>`, box => {
    const ok = $('#del-ok', box); setTimeout(() => ok.focus(), 30);
    ok.onclick = async () => {
      ok.disabled = true;
      const k = qCur()?.key || '';  // 正在放的就是它（或在这个文件夹里）：先停下，不然文件被占用删不掉
      const hit = x => !!x && (x.key === 'lib:' + path || (dir && (path === '未分类' ? /^lib:[^/]*$/.test(x.key) : x.key.startsWith('lib:' + path + '/'))));
      if (PB.q?.items.some(hit)) { qDrop(hit); await sleep(350); }  // 先放开文件（被占用就删不掉）
      const r = await api('/api/play/delete', { body: { path, dir } }).catch(e => { toast(e.message, true); return null; });
      box.close();
      if (!r) return;
      toast(perm ? '已永久删除' : '已移到回收站');
      if (location.pathname === '/play') { libCache = null; renderPlay(); }
    };
  });
}
let PLAYNAV = null, PLAYCTX = null;
const PLAYKB = { sk: null, key: null };  // 播放页键盘选中的是哪个文件夹里的哪个文件（页面重画后接着用）
document.addEventListener('keydown', e => {
  if (location.pathname !== '/play' || !PLAYNAV || !$('#play-list') || e.defaultPrevented) return;
  if (!$('#np')?.hidden || ImageViewer.isOpen() || curPop || CTX || $('.modal-bg') || $('.dd-menu.show')) return;
  const k = e.key, q = $('#play-q'), inField = e.target.closest?.('input, textarea, select, [contenteditable]');
  if (inField) {
    if (e.target === q && k === 'Escape') { e.preventDefault(); if (q.value) { q.value = ''; q.dispatchEvent(new Event('input')); } q.blur(); }
    else if (e.target === q && (k === 'ArrowDown' || k === 'Enter') && PLAYNAV.items.length) { e.preventDefault(); q.blur(); PLAYNAV.kbSet(0); }
    return;
  }
  const N = PLAYNAV.items.length, step = PLAYNAV.grid ? PLAYNAV.cols : 1, cur = PLAYNAV.kb;
  const to = i => { e.preventDefault(); if (N) PLAYNAV.kbSet(Math.max(0, Math.min(N - 1, i))); };
  if ((k === 'f' && (e.ctrlKey || e.metaKey)) || (k === '/' && !e.ctrlKey)) { e.preventDefault(); q?.focus(); q?.select(); return; }
  if (e.ctrlKey && (k === 'ArrowLeft' || k === 'ArrowRight')) { e.preventDefault(); return k === 'ArrowLeft' ? qPrev() : qNext(false); }
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (k === 'ArrowDown') return to(cur < 0 ? 0 : cur + step);
  if (k === 'ArrowUp') return to(cur < 0 ? 0 : cur - step);
  if (PLAYNAV.grid && (k === 'ArrowLeft' || k === 'ArrowRight')) return to(cur < 0 ? 0 : cur + (k === 'ArrowLeft' ? -1 : 1));
  if (k === 'Home') return to(0);
  if (k === 'End') return to(N - 1);
  if (k === 'PageDown' || k === 'PageUp') { const rows = Math.max(1, Math.floor(($('.pl-rows')?.clientHeight || 400) / (PLAYNAV.grid ? 230 : 58)) - 1); return to((cur < 0 ? 0 : cur) + (k === 'PageDown' ? 1 : -1) * rows * step); }
  if (k === 'Enter' && cur >= 0) { if (e.target.closest?.('button, a, [role=menuitem], .ps-item, [tabindex]:not(body)')) return; e.preventDefault(); return PLAYNAV.play(cur); }
  if (k === ' ') { e.preventDefault(); return $('[data-pb="play"]')?.click(); }
  if ((k === 'ArrowLeft' || k === 'ArrowRight') && extOn()) { e.preventDefault(); return extCmd({ seekBy: k === 'ArrowLeft' ? -5 : 5 }); }
  if ((k === 'ArrowLeft' || k === 'ArrowRight') && PB.a) { e.preventDefault(); keySeek(PB.a, k === 'ArrowLeft' ? Math.max(0, PB.a.currentTime - 5) : Math.min((PB.a.duration || 1e9) - .05, PB.a.currentTime + 5)); }
});
const PLSC = { n: lsJSON('plscroll', {}), v: {} };  // 每个文件夹的列表滚到哪里了，切回来接着看（私密空间的只在内存里）
const PLSCROLL = () => PLSC[VAULT ? 'v' : 'n'];
/* 旧版本在私密空间里也把播放进度、列表位置、文件夹展开 / 排序写进了本地存储：进私密空间读到音源库后，把属于它的那些删掉（每次打开只做一次） */
function scrubPrivate(lib, tags) {
  if (scrubPrivate.done || !VAULT) return; scrubPrivate.done = true;
  const paths = new Set(lib.map(x => x.path)), dirs = new Set();
  lib.forEach(x => { const ps = (x.dir || x.folder || '').split('/'); for (let k = 1; k <= ps.length; k++) { const d = ps.slice(0, k).join('/'); if (d && d !== '未分类') dirs.add(d); } });
  const keys = new Set([...[...dirs].map(d => 'd:' + d), ...Object.values(tags || {}).flat().map(t => 't:' + t)]);
  const pp = lsJSON('playpos', {}), pk = Object.keys(pp).filter(k => paths.has(k));
  if (pk.length) { pk.forEach(k => delete pp[k]); localStorage.setItem('playpos', JSON.stringify(pp)); }
  const sk = Object.keys(PLSC.n).filter(k => keys.has(k));
  if (sk.length) { sk.forEach(k => delete PLSC.n[k]); localStorage.setItem('plscroll', JSON.stringify(PLSC.n)); }
  const u = NSTASH?.ui;
  if (u) { if (u.openDirs) u.openDirs = u.openDirs.filter(d => !dirs.has(d)); [u.sorts, u.views].forEach(m => m && Object.keys(m).forEach(k => { if (keys.has(k)) delete m[k]; })); persist(); }
}
/* 手机上的播放页：一次只显示一层——文件夹列表，或者点进去后的文件列表（顶上有返回键，iPhone 左滑也能回来） */
const MOB = () => matchMedia('(max-width: 760px)').matches;
let PLM = false;
function plmPaint() {
  const g = $('.play-grid'); if (!g) return;
  g.classList.toggle('m-list', MOB() && (PLM || !!playQ));
}
function plmEnter() {
  if (!MOB()) return;
  if (!PLM) { if (!document.documentElement.classList.contains('ph')) history.pushState({ pl: 1 }, '', '/play'); PLM = true; }  // 手机上不记历史（左边缘右滑是打开侧栏），返回用页面里的“‹”
  plmPaint(); window.scrollTo(0, 0);
}
let plRedraw = null;  // 播放页就地重画（左边文件夹 + 右边列表，不重新取数据）；renderPlay 画好后设上
const PLREDRAW = () => !!(document.documentElement.classList.contains('ph') && plRedraw?.());  // 只在手机外壳上用（电脑照旧）
function plmBack() {
  if (playQ) { playQ = ''; playAll = false; const q = $('#play-q'); if (q) q.value = ''; }
  else if (playSrc.startsWith('d:') && playSrc.slice(2).includes('/')) {  // 在子文件夹里：先回到上一层文件夹
    playSrc = 'd:' + playSrc.slice(2).split('/').slice(0, -1).join('/'); vprefsSave();
    if (PLREDRAW()) { window.scrollTo(0, 0); return true; }  // 2026-11-16 用户：手机上滑动退回上个文件夹有点慢——以前整页重画、重新问服务器要十来样数据；现在用手上已有的数据就地重画（和进文件夹一样快）
    return renderPlay(true);
  }
  if (history.state?.pl) return history.back();  // 回到文件夹列表（会重画一次）
  PLM = false; if (PLREDRAW()) { plmPaint(); window.scrollTo(0, 0); return true; } renderPlay(true);
}
/* 导航栏和播放页左栏对齐（2026-11-18 用户：没按方案 B 对齐——应用窗口顶上有 34px 的拖动条、窗口矮时导航间距会变，写死的数对不上）：
   在播放页里实际量：logo 和左栏“播放”标题同一行（调导航栏的上边距 --rail-pt），第一个导航按钮和“资料库”同一高度（--rnav-top）；
   量到的数记下来，其它页面也用同一个位置（不会换页就跳） */
const RAIL_AL = lsJSON('railAlign', null);
function railApply(v) { const h = document.documentElement.style; if (v) { h.setProperty('--rail-pt', v.pt + 'px'); h.setProperty('--rnav-top', v.nt + 'px'); } }
railApply(RAIL_AL);
function railAlign() {
  if (document.documentElement.classList.contains('ph') || innerWidth < 761 || innerHeight <= 620) return;  // 很矮的窗口导航栏挨紧排（b5.css），不量也不记
  const logo = $('.rail .brand'), nav = $('.rnav a.active') || $('.rnav a'), t = $('#main .ps-title'), lib = $('#play-src .ps-lib'), rail = $('.rail'), rn = $('.rnav');
  if (!logo || !nav || !t || !lib || !rail || !rn || !t.offsetParent) return;
  // 切页时内容有一小段上浮的进场动画：动画放完再量（以前边放边量，先量偏、过一会儿再改，导航栏就上下动一下，2026-11-18 用户）
  const busy = ($('#main')?.getAnimations?.({ subtree: true }) || []).filter(x => x.playState === 'running' && x.effect?.getTiming?.().iterations !== Infinity);
  if (busy.length) { clearTimeout(railAlign._w); railAlign._w = setTimeout(() => Promise.all(busy.map(x => x.finished.catch(() => { }))).then(() => railAlign()), 0); return; }
  const mid = e => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; };
  if (scrollY > 0) return;  // 页面往下滚过了：不量
  const pt0 = parseFloat(getComputedStyle(rail).paddingTop), pt = Math.max(8, Math.min(140, Math.round(pt0 + mid(t) - mid(logo))));
  if (pt !== Math.round(pt0)) document.documentElement.style.setProperty('--rail-pt', pt + 'px');
  const ic = $('.ic', nav) || nav;  // 按图标那一块对齐（图标下面还有一行字）
  const nt0 = parseFloat(getComputedStyle(rn).marginTop), nt = Math.max(0, Math.min(260, Math.round(nt0 + mid(lib) - mid(ic))));
  if (nt !== Math.round(nt0)) document.documentElement.style.setProperty('--rnav-top', nt + 'px');
  if (!RAIL_AL || RAIL_AL.pt !== pt || RAIL_AL.nt !== nt) { try { localStorage.setItem('railAlign', JSON.stringify({ pt, nt })); } catch { } }
}
addEventListener('resize', () => { clearTimeout(railAlign._t); railAlign._t = setTimeout(railAlign, 150); });
document.fonts?.ready.then(() => setTimeout(railAlign, 50));  // 字体载入后行高可能变一点：再量一次
if (window.ResizeObserver) { const ro = new ResizeObserver(() => { clearTimeout(railAlign._r); railAlign._r = setTimeout(railAlign, 60); }); const watch = () => { const br = $('.rail .brand'); if (br) { ro.observe(br); ro.observe($('.rail')); } else setTimeout(watch, 300); }; watch(); }  // 导航栏里的东西大小变了（矮窗口时 logo 变小等）：再量一次
// 打开的文件夹（Lucide folder-open，ISC）：电脑上左栏用“合上 / 打开的文件夹”表示收起 / 展开，不再单独放一列小箭头（2026-11-18 用户参考 ChatGPT 侧栏）
const PL_FOPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"/></svg>';
const PL_FILT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M7 12h10M10 17h4"/></svg>';
const PL_CSEP = '<span class="crumb-sep" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="m9 6 6 6-6 6"/></svg></span>';
const PL_SHUF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>';
async function renderPlay(keep) {
  const gen = renderPlay.n = (renderPlay.n || 0) + 1, vg = VGEN;
  // 手机上：现在是在“文件夹里面”还是在文件夹列表。手机外壳（html.ph）换页不记历史（左边缘右滑是打开侧栏），history.state 里没有这个：
  // 2026-11-16 用户“文件很多的文件夹滑到下面，有时莫名回到最上面”——后台自动刷新（keep）每次都把它读成“不在文件夹里”，退回文件夹列表。自动刷新时保持原样
  PLM = document.documentElement.classList.contains('ph') ? (keep ? PLM : false) : !!history.state?.pl;
  const stale = () => gen !== renderPlay.n || vg !== VGEN;  // 已经重画过 / 进出过私密空间：这一次的数据过期了，晚到的刷新（比如搜索框的防抖）不能再画上去
  const srcTop = keep ? $('#play-src')?.scrollTop || 0 : 0;  // 自动刷新：左边文件夹列表滚到哪里，重画后还在那里
  // 2026-11-17 用户：电脑上搜索框放在左栏最上面（照 docs/设计稿/播放页A_子文件夹方案_1117.html）；手机照旧在标题下面
  const sbox = `<div class="play-search"><span>${ICON.search}</span><input class="input" id="play-q" placeholder="搜索音源、作品和文件夹…" value="${esc(playQ)}"></div>`, sideQ = !MOB();
  const shell = `<div class="page-head${sideQ ? ' pl-nohead' : ''}"><h1 class="page-title">播放</h1>${sideQ ? '' : `<div class="play-tools">${sbox}</div>`}</div>
    <div class="play-grid"><div class="play-side">${sideQ ? `<h1 class="ps-title">播放</h1><div class="play-tools ps-search">${sbox}</div>` : ''}<div class="card play-src" id="play-src"><div class="shimmer"></div></div></div><div class="card play-list" id="play-list"><div class="shimmer"></div></div></div>`;
  // 已经在播放页上（进出文件夹、自动刷新）：先留着现在的画面，数据到了再一次换掉 —— 不会先变成占位条再出来（看着像闪一下）
  const same = !!$('#play-src') && $('#main').dataset.page === 'play';
  if (!same) $('#main').innerHTML = shell;
  const fetchAll = () => Promise.all([libCache ? Promise.resolve(libCache) : api('/api/play/library').catch(() => []), api('/api/jobs').catch(() => []), loadFavs(),
    api('/api/play/recent').catch(() => []), api('/api/play/tags').catch(() => ({})), api('/api/play/order').catch(() => ({})), api('/api/play/images').catch(() => []),
    api('/api/img/gallery').catch(() => []), api('/api/video/gallery').catch(() => [])]);  // 生图 / 生视频的成品：放进“作品”（2026-11-06 用户）
  // 2026-11-17 用户：切页时闪一下空框——换到播放页时先用上次读到的数据马上画（不等接口），后台再读一遍，有变化才按“自动刷新”重画一次
  const PD = renderPlay.data, warm = !keep && PD && PD.vg === VGEN;
  let data;
  if (warm) { data = PD.v; fetchAll().then(v => { if (VGEN !== PD.vg) return; renderPlay.data = { vg: PD.vg, v }; if (JSON.stringify(v) !== JSON.stringify(PD.v) && gen === renderPlay.n && $('#main').dataset.page === 'play' && $('#play-src') && !playQ) renderPlay(true); }); }
  else { data = await fetchAll(); renderPlay.data = { vg, v: data }; }
  const [lib, jobsAll, , recent, tags, order, imgs, gImgs, gVids] = data;
  if (gen !== renderPlay.n || !$('#play-src') || $('#main').dataset.page !== 'play') return;  // 这期间又重画过 / 已经离开播放页：这一次作废
  // 2026-11-16 用户：文件很多的文件夹滑到下面，有时莫名回到最上面。后台有任务 / 音源库变了时这里会整页自动重画（pageRefresh），
  // 换掉的那一下页面只剩空架子那么高，浏览器把滚动位置夹到最上面。同一页重画：先撑住原来的高度，画完回到原来的位置
  const keepPY = same && keep ? scrollY : null;
  if (keepPY != null) $('#main').style.minHeight = $('#main').offsetHeight + 'px';
  if (same) {
    const ae = document.activeElement?.id === 'play-q' ? { s: document.activeElement.selectionStart } : null;  // 正在搜索框里打字：换完以后光标还在
    $('#main').innerHTML = shell;
    [...$('#main').children].forEach(c => { c.style.animation = 'none'; });  // 同一页重画：不再播放进场动画
    if (ae) { const q = $('#play-q'); q.focus({ preventScroll: true }); try { q.setSelectionRange(ae.s, ae.s); } catch { } }
  }
  libCache = lib; IMGCACHE = imgs; TAGS = tags || {}; const ORDER = order || {}; SRC_ORDER = ORDER;
  scrubPrivate(lib, TAGS);
  plmPaint();
  pageRefresh(['jobs', 'play'], () => { if (!playQ && !$('#play-src')?.classList.contains('ps-sorting')) renderPlay(true); });
  // 类型筛选：只看视频 / 音频 / 图片时，左边只列出有这种文件的文件夹，右边也只列这种文件
  const KIND = () => S.ui?.kind || 'all';
  const okMedia = x => { const k = KIND(); return k === 'all' || (k === 'video' ? !!x.video : k === 'audio' ? !x.video : false); };
  const okTrack = x => okMedia({ video: x.video });
  const imgsOn = () => KIND() === 'all' || KIND() === 'image';
  const WKS = [['all', '全部作品', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/></svg>'],
    ['video', '只看视频', ICON.film], ['image', '只看图片', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="9" cy="10" r="1.7" fill="currentColor" stroke="none"/><path d="m4 17 5-4.5 3.5 3 3-2.5 4.5 4"/></svg>'], ['audio', '只看配音', ICON.note]];
  const WK = () => { const k = S.ui?.wkind || 'all'; return KIND() === 'all' || KIND() === k ? k : 'all'; };  // “作品”里自己的筛选：全部 / 视频 / 图片 / 音频（只管作品这一页，不动左边的总筛选）
  // 自己拖出来的顺序优先；没排过的（比如新加的文件夹）按名字排在后面
  const byOrder = (grp, list, name) => { const o = ORDER[grp] || []; const ix = x => { const i = o.indexOf(name(x)); return i < 0 ? 1e9 : i; }; return list.slice().sort((a, b) => ix(a) - ix(b) || name(a).localeCompare(name(b), 'zh', { numeric: true })); };
  if (!$('#play-src')) { if (keepPY != null) $('#main').style.minHeight = ''; return; }  // 已经离开：撑住的高度也放掉
  const done = jobsAll.filter(j => j.state === 'done' && j.has_output);
  const jobTrack = j => ({ key: 'job:' + j.id, url: `/media/job/${j.id}/output.mp3?t=${j.finished}`, title: j.title, sub: (j.kind === 'vc' ? '换声' : '配音') + (j.voice_name ? ' · ' + j.voice_name : ''), meta: fmtDur(j.duration), dur: j.duration, artist: j.voice_name || '', orb: j.voice, subsKey: 'job:' + j.id, at: j.finished || 0, big: j.duration || 0 });
  const libTrack = x => ({ key: 'lib:' + x.path, url: libUrl(x.path), title: x.name, sub: dirLabel(x.dir || x.folder).split('/').join(' / '), meta: fmtSize(x.size), dur: x.dur, artist: x.artist || '', video: x.video, ext: x.ext, orb: x.folder, pos: x.path, cover: coverUrl(x.path), subsKey: 'lib:' + x.path, at: x.mtime || 0, big: x.size || 0, conv: x.conv });
  // 生视频的成品当作“作品”里的视频（已经拼回原视频的那几小段不放，和生视频页默认一样）；生图的成品当作“作品”里的图片
  const genShort = (s, d) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s ? (s.length > 40 ? s.slice(0, 40) + '…' : s) : d; };
  const spliced = new Set((gVids || []).filter(x => x.spliced_of).flatMap(x => [x.spliced_of, ...(x.spliced_ids || [])]));
  const vidTrack = x => ({ key: 'vid:' + x.id, url: '/media/video/' + encodeURIComponent(x.file), title: genShort(x.prompt_input ?? x.prompt, x.model_name || '生成的视频'),
    sub: (x.edit ? (x.spliced_of ? '改视频 · 完整版' : '改视频') : '生视频') + (x.model_name ? ' · ' + x.model_name : '') + (typeof vidPostS === 'function' && vidPostS(x) ? ' · ' + vidPostS(x) : ''), meta: fmtDur(x.duration || x.seconds), video: true,
    cover: x.thumb ? '/media/video/' + encodeURIComponent(x.thumb) : '', subsKey: 'vid:' + x.id, at: x.created || 0, big: x.duration || 0 });
  // 2026-11-11 用户：同一条的不同调色（超分、插帧）只显示一个——按 upscaled_of 找到最初那条，一家只放最新做的那个；拼进完整视频的片段整家都不放
  const vById = new Map((gVids || []).map(x => [x.id, x]));
  const vRoot = x => { let r = x, n = 0; while (r.upscaled_of && vById.has(r.upscaled_of) && n++ < 20) r = vById.get(r.upscaled_of); return r.id; };
  const splicedRoot = new Set([...spliced].map(id => vById.has(id) ? vRoot(vById.get(id)) : id));
  const vNewest = new Map();
  for (const x of gVids || []) { if (!x.file || spliced.has(x.id) || splicedRoot.has(vRoot(x))) continue; const k = vRoot(x), o = vNewest.get(k); if (!o || (x.created || 0) > (o.created || 0)) vNewest.set(k, x); }
  const genVids = [...vNewest.values()].map(vidTrack);
  const genPics = (gImgs || []).filter(x => x.file).map(x => ({ name: genShort(x.prompt_used || x.prompt, x.file), gsrc: '/media/img/' + encodeURIComponent(x.file), gthumb: '/media/img/' + encodeURIComponent(x.file) + '?thumb=1',
    gsub: '生图' + (x.model_name ? ' · ' + x.model_name : ''), mtime: x.created || 0, size: 0, dir: '' }));
  const allTracks = () => new Map([...done.map(jobTrack), ...genVids, ...lib.map(libTrack)].map(x => [x.key, x]));
  /* 文件夹树：按每个文件的完整文件夹路径（dir）建，任意层级都能展开；选中一个文件夹 = 它和它所有子文件夹里的文件 */
  let dirs = new Set(), kbI = -1, kbVis = false;  // kbVis：选中框只在用键盘上下移动时显示；鼠标点（点了就播放）只记起点、不画框（2026-11-17 用户：高亮逻辑有问题）
  const buildDirs = () => {  // 当前类型下有文件的文件夹（含它们的上层文件夹）
    dirs = new Set();
    [...lib.filter(okMedia), ...(imgsOn() ? imgs : [])].forEach(x => { const parts = (x.dir || x.folder).split('/'); for (let k = 1; k <= parts.length; k++) dirs.add(parts.slice(0, k).join('/')); });
  };
  buildDirs();
  const kids = pre => {
    const out = byOrder('d:' + pre, [...dirs].filter(d => pre ? d.startsWith(pre + '/') && !d.slice(pre.length + 1).includes('/') : !d.includes('/')), d => d.split('/').pop());
    if (!pre && !(ORDER['d:'] || []).includes('未分类') && out.includes('未分类')) { out.splice(out.indexOf('未分类'), 1); out.unshift('未分类'); }  // 根目录默认排第一
    return out;
  };
  const under = (x, d) => { const xd = x.dir || x.folder; return xd === d || xd.startsWith(d + '/'); };
  const inDir = d => lib.filter(x => okMedia(x) && under(x, d));
  const imgsIn = d => imgsOn() ? imgs.filter(x => under(x, d)) : [];
  const openDirs = () => new Set(S.ui?.openDirs || []);
  const dirSource = d => ({ id: 'd:' + d, name: dirLabel(d.split('/').pop()), path: d, folder: true, items: () => inDir(d).map(libTrack), imgs: () => imgsIn(d) });
  const fixed = [
    { id: 'works', name: '作品', icon: ICON.star, works: true, items: () => WK() === 'image' ? [] : [...done.filter(j => j.saved).map(jobTrack), ...genVids].filter(x => WK() === 'all' || (WK() === 'video') === !!x.video).sort((a, b) => b.at - a.at),
      imgs: () => imgsOn() && ['all', 'image'].includes(WK()) ? genPics : [] },
    ...(LIBNEW.length ? [{ id: 'new', name: '最近新增', icon: ICON.sparkle, items: () => LIBNEW.map(pth => lib.find(x => x.path === pth)).filter(Boolean).map(libTrack) }] : []),
    { id: 'recent', name: '最近播放', icon: ICON.recent, keepOrder: true, items: () => { const all = allTracks(); return recent.map(r => all.get(r.key)).filter(Boolean); } },
    { id: 'favs', name: '我的收藏', icon: ICON.heart, items: () => { const all = allTracks(); return [...FAVS].map(k => all.get(k)).filter(Boolean); } },
  ];
  fixed.forEach(f => { const raw = f.items; f.items = () => raw().filter(okTrack); });
  const fixedShown = () => KIND() === 'image' ? fixed.filter(f => f.imgs?.().length) : KIND() === 'all' ? fixed : fixed.filter(f => f.items().length || f.imgs?.().length);  // 只看图片：“作品”里有生成的图片时也列出来
  const tagList = () => KIND() === 'image' ? [] : byOrder('tags', [...new Set(Object.values(TAGS).flat())], t => t);
  const tagSource = t => ({ id: 't:' + t, name: t, tag: true, items: () => { const all = allTracks(); return Object.entries(TAGS).filter(([, v]) => v.includes(t)).map(([k]) => all.get(k)).filter(Boolean).filter(okTrack); } });
  const treeRows = () => {  // 当前展开状态下看得见的文件夹（深度优先）
    const out = [], open = openDirs();
    const walk = (pre, depth) => kids(pre).forEach(d => { const has = kids(d).length > 0; out.push({ ...dirSource(d), depth, has, open: open.has(d) }); if (has && open.has(d)) walk(d, depth + 1); });
    walk('', 0); return out;
  };
  if (playSrc.startsWith('f:')) playSrc = 'd:' + playSrc.slice(2);  // 旧版本存的“第一层文件夹”
  const getSource = id => fixedShown().find(s => s.id === id) || (id.startsWith('d:') && dirs.has(id.slice(2)) ? dirSource(id.slice(2)) : null)
    || (id.startsWith('t:') && tagList().includes(id.slice(2)) ? tagSource(id.slice(2)) : null);
  const fallbackSrc = () => { if (playSrc && !getSource(playSrc)) playSrc = ''; };  // 选中的文件夹没了（删了 / 换了类型筛选）：回到什么都没选，不自动进别的文件夹
  fallbackSrc();
  if (MOB() && PLM && !playQ && !getSource(playSrc)) { PLM = false; history.replaceState(null, '', '/play'); plmPaint(); }  // 手机上停在“文件夹里面”但那个文件夹没了：回到文件夹列表
  // 搜索范围：选着一个文件夹（或作品、收藏、标签……）时只在它里面找；点了“全部” / 什么都没选 / 手机上在文件夹列表那一层时在全部里找
  const scopeSrc = () => playAll || (MOB() && !PLM) ? null : getSource(playSrc);
  const srcName = sc => sc.path ? dirLabel(sc.path.split('/').pop()) : sc.name;
  const qPh = () => { const q = $('#play-q'), sc = scopeSrc(); if (q) q.placeholder = sc ? `在“${srcName(sc)}”中搜索…` : '搜索音源、作品和文件夹…'; };
  const inherit = (m, id, dflt) => {
    if (m[id]) return m[id];
    for (let d = id.startsWith('d:') ? id.slice(2) : ''; d.includes('/');) { d = d.slice(0, d.lastIndexOf('/')); if (m['d:' + d]) return m['d:' + d]; }
    return dflt;
  };
  const sortOf = id => inherit(S.ui?.sorts || {}, id, S.ui?.sort || 'default');
  const viewOf = id => inherit(S.ui?.views || {}, id, 'list');
  const toggleDir = (d, on) => { const o = openDirs(); (on ?? !o.has(d)) ? o.add(d) : o.delete(d); S.ui = { ...(S.ui || {}), openDirs: [...o] }; persist(); };
  const drawSrc = () => {
    if (stale()) return;
    const rows = treeRows();
    // 类型筛选：手机照旧在左栏最上面一排；电脑上（2026-11-17 用户：和搜索框挤在一起太重）收成“资料库”那行右边的一个小图标（#pl-kind），筛了某类时前面写类型名
    $('#play-src').innerHTML = (MOB() ? `<div class="seg mini full ps-kind" id="ps-kind">${KINDS.map(([k, n]) => `<button data-kind="${k}" class="${KIND() === k ? 'on' : ''}">${n}</button>`).join('')}</div>` : '')
      + `<div class="ps-head ps-lib"><span class="sec-label" style="margin:0">资料库</span><span class="spacer"></span>${MOB() ? '' : `<button type="button" class="pl-kind${KIND() !== 'all' ? ' on' : ''}" id="pl-kind" data-tip="按类型筛选：只看视频、音频或图片" aria-label="按类型筛选" aria-haspopup="menu">${KIND() === 'all' ? '' : `<span>${KINDS.find(k => k[0] === KIND())[1]}</span>`}${PL_FILT}</button>`}</div>`
      + fixedShown().map(s => `<button class="ps-item ${s.id === playSrc && (!playQ || scopeSrc()) ? 'on' : ''}" data-src="${esc(s.id)}"><span class="ps-ic">${s.icon}</span><span class="ps-name">${esc(s.name)}</span><span class="ps-n">${s.items().length + (s.works ? s.imgs().length : 0)}</span></button>`).join('')
      + (tagList().length ? `<div class="ps-head"><span class="sec-label" style="margin:0">标签</span></div>` + tagList().map(t => { const s = tagSource(t);
          return `<button class="ps-item ${s.id === playSrc && (!playQ || scopeSrc()) ? 'on' : ''}" data-src="${esc(s.id)}" data-grp="tags" data-name="${esc(t)}"><span class="ps-ic">${ICON.tag}</span><span class="ps-name">${esc(t)}</span><span class="ps-n">${s.items().length}</span></button>`; }).join('') : '')
      + (dirs.size ? `<div class="ps-head"><span class="sec-label" style="margin:0">音源库</span><span class="spacer"></span>
          <button class="ps-allbtn" data-all="open" title="全部展开">${ICON.expandAll}</button><button class="ps-allbtn" data-all="close" title="全部收起">${ICON.collapseAll}</button></div>`
        : `<div class="ps-empty">${KIND() !== 'all' ? '音源库中尚无' + KINDS.find(k => k[0] === KIND())[1] : VAULT ? '私密音源库为空' : '将音频、视频或图片放入<br><b>D:\\AI-TTS\\音源库</b><br>文件夹，数十秒内将自动显示在此处'}</div>`)
      + rows.map(s => `<button class="ps-item ps-dir ${s.id === playSrc && (!playQ || scopeSrc()) ? 'on' : ''}" data-src="${esc(s.id)}" data-grp="${esc('d:' + s.path.split('/').slice(0, -1).join('/'))}" data-name="${esc(s.path.split('/').pop())}" data-depth="${s.depth}" style="--depth:${s.depth}"${s.path === '未分类' ? ' title="直接位于音源库根目录、未放入文件夹的文件"' : ''}>
          ${MOB() ? `<span class="ps-tog ${s.has ? '' : 'none'} ${s.open ? 'open' : ''}" data-tog="${esc(s.path)}">${s.has ? ICON.chev : ''}</span><span class="ps-ic">${ICON.folder}</span>`
            : `<span class="ps-ic">${s.has && s.open ? PL_FOPEN : ICON.folder}</span>`}<span class="ps-name">${esc(s.name)}</span>${!MOB() && s.has ? `<span class="ps-chv${s.open ? ' open' : ''}" data-tog="${esc(s.path)}" title="${s.open ? '收起' : '展开'}" aria-label="${s.open ? '收起' : '展开'}">${ICON.chev}</span>` : ''}<span class="ps-n">${inDir(s.path).length + imgsIn(s.path).length}</span></button>`).join('');
    const kb = $('#pl-kind', $('#play-src')); if (kb) kb.onclick = e => {  // 类型筛选（电脑）：和排序一样点开一个小菜单
      const b = e.currentTarget; if (b._skip) return void (b._skip = false); b.classList.add('open');
      ctxMenu({ anchor: b, onClose: () => b.classList.remove('open') }, KINDS.map(([k, n]) => ({ label: n, checked: KIND() === k, on: () => { if (k === KIND()) return; S.ui = { ...(S.ui || {}), kind: k }; persist(); buildDirs(); fallbackSrc(); drawSrc(); drawList(); } })));
    };
    $$('[data-kind]', $('#play-src')).forEach(b => b.onclick = () => {
      if (b.dataset.kind === KIND()) return;
      S.ui = { ...(S.ui || {}), kind: b.dataset.kind }; persist(); buildDirs(); fallbackSrc(); drawSrc(); drawList();
    });
    $$('[data-all]', $('#play-src')).forEach(b => b.onclick = () => {
      S.ui = { ...(S.ui || {}), openDirs: b.dataset.all === 'open' ? [...dirs].filter(d => kids(d).length) : [] }; persist(); drawSrc();
    });
    $$('.ps-item', $('#play-src')).forEach(b => b.onclick = e => {
      if ($('#play-src')?._noClick) return;  // 刚拖完排序，松手那一下不算点击
      const tog = e.target.closest('[data-tog]');
      if (tog && !tog.classList.contains('none')) { toggleDir(tog.dataset.tog); return drawSrc(); }  // 小箭头：只展开 / 收起，不切换列表
      const id = b.dataset.src, d = id.startsWith('d:') ? id.slice(2) : null;
      // 点文件夹本身：选中它。2026-11-16 用户（手机）：进去以后不要展开，只有点展开按钮才展开。
      // 2026-11-17 用户（电脑）：点开时展开，再点不要收起——只有左边的箭头收起
      if (d && kids(d).length && !document.documentElement.classList.contains('ph')) toggleDir(d, true);
      const changed = id !== playSrc || playQ;
      playSrc = id; playQ = ''; playAll = false; $('#play-q').value = ''; vprefsSave(); plmEnter();
      drawSrc(); if (changed) drawList();
    });
    railAlign();
  };
  const drawList = () => {
    if (stale()) return;
    qPh();
    if (!playQ && !getSource(playSrc)) {  // 什么都没选（刚进播放页）：右边空着
      $('#play-list').innerHTML = `<div class="vd-ab-empty vd-empty vd-closed pl-none"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg><span>选择一个列表</span></div>`;  // 2026-11-16 检查：原来是一个什么都没有的空框
      PLAYNAV = { items: [], grid: false, cols: 1, kbSet() { }, play() { }, kb: -1 }; return;
    }
    const pos = playPos();
    let title, items, pics = [], dhits = [], groups = null, subAll = null, sgroups = null, crumbs = '';
    const sc = playQ ? scopeSrc() : null;
    if (playQ) {
      const q = playQ.toLowerCase(), hit = x => (x.title + ' ' + x.sub).toLowerCase().includes(q), pHit = x => (x.name + ' ' + (x.dir || '') + ' ' + (x.gsub || '')).toLowerCase().includes(q);
      if (sc?.folder) {  // 只在这个文件夹（含子文件夹）里找
        dhits = [...dirs].filter(d => d.startsWith(sc.path + '/') && d.split('/').pop().toLowerCase().includes(q)).slice(0, 30);
        const all = inDir(sc.path).map(libTrack); subAll = new Map(all.map(x => [x.key, x]));
        items = all.filter(hit); pics = imgsIn(sc.path).filter(pHit);
      } else if (sc) {  // 作品 / 最近 / 收藏 / 标签：只在这一列里找
        const all = sc.items(); subAll = new Map(all.map(x => [x.key, x]));
        items = all.filter(hit); pics = (sc.imgs ? sc.imgs() : []).filter(pHit);
      } else {
        dhits = [...dirs].filter(d => d.split('/').pop().toLowerCase().includes(q)).slice(0, 30);
        items = [...done.map(jobTrack), ...lib.map(libTrack)].filter(x => okTrack(x) && hit(x));
        items = items.filter((x, i) => items.findIndex(y => y.key === x.key) === i);
        pics = imgsOn() ? imgs.filter(pHit) : [];
      }
      title = `搜索“${esc(playQ)}”`;
    } else {
      const s = getSource(playSrc) || fixed[0]; items = s.items(); pics = s.imgs ? s.imgs() : [];
      const segs = s.path ? dirLabel(s.path).split('/') : [], raw = s.path ? s.path.split('/') : [];  // 文件夹标题：上面几层都能点，回到那一层
      title = s.path ? esc(segs[segs.length - 1]) : esc(s.name);
      crumbs = s.path && segs.length > 1 ? segs.slice(0, -1).map((n, j) => `<button type="button" class="crumb" data-dir="${esc(raw.slice(0, j + 1).join('/'))}">${esc(n)}</button>`).join(PL_CSEP) + PL_CSEP + `<b>${esc(segs[segs.length - 1])}</b>` : '';
      // 有子文件夹的文件夹（2026-11-17 用户选方案 1 + 4，docs/设计稿/播放页A_子文件夹方案_1117.html）：右边按子文件夹分组列出全部文件——
      // 直接放在这一层的在最前面（不带小标题），后面每个子文件夹一段，小标题写相对路径（多层用“ › ”连起来），小标题上可以只播这一段；
      // “播放”就是整个文件夹。左边的树照旧能展开、直接点到某个子文件夹
      if (s.folder && kids(s.path).length && MOB()) {  // 手机照旧：子文件夹列出来点进去，文件只列直接放在这一层的（2026-11-18 全量检查：分组改动误伤了手机的逐层进出 / 右滑返回）
        dhits = kids(s.path);
        items = lib.filter(x => okMedia(x) && (x.dir || x.folder) === s.path).map(libTrack);
        pics = imgsOn() ? imgs.filter(x => x.dir === s.path) : [];
      } else if (s.folder && kids(s.path).length) {
        const order = [], walkD = pre => kids(pre).forEach(d => { order.push(d); walkD(d); }); walkD(s.path);
        const byDir = new Map(); inDir(s.path).forEach(x => { const d = x.dir || x.folder; if (!byDir.has(d)) byDir.set(d, []); byDir.get(d).push(libTrack(x)); });
        sgroups = [[null, byDir.get(s.path) || []], ...order.map(d => [d, byDir.get(d) || []])].filter(g => g[1].length);
        items = sgroups.flatMap(g => g[1]);
        dhits = [];
        pics = imgsOn() ? imgs.filter(x => x.dir === s.path) : [];
      }
    }
    // 排序：默认（文件夹顺序 / 最近播放的先后）、最新、最大（文件大小 / 配音时长）、名称
    const sk = playQ ? '' : playSrc, sort = sortOf(sk || 'search'), view = viewOf(sk || 'search');
    const sortFn = sort === 'new' ? (a, b) => b.at - a.at : sort === 'size' ? (a, b) => b.big - a.big : sort === 'name' ? (a, b) => a.title.localeCompare(b.title, 'zh', { numeric: true }) : null;
    const natural = (a, b) => a.title.localeCompare(b.title, 'zh', { numeric: true });  // 分组时默认按名字的自然顺序（第2集在第10集前面）
    if (sgroups) { sgroups = sgroups.map(([d, g]) => [d, g.slice().sort(sortFn || natural)]); items = sgroups.flatMap(g => g[1]); }  // 分组时每一段里各自排
    else if (sortFn) items = items.slice().sort(sortFn);
    else if (!playQ && getSource(playSrc)?.folder) items = items.slice().sort(natural);  // 文件夹里默认也按名字的自然顺序
    if (sort === 'new') pics = pics.slice().sort((a, b) => b.mtime - a.mtime);
    else if (sort === 'size') pics = pics.slice().sort((a, b) => b.size - a.size);
    else if (sort === 'name') pics = pics.slice().sort((a, b) => a.name.localeCompare(b.name, 'zh', { numeric: true }));
    if (playQ) {  // 搜索结果按类型分开：作品 / 视频 / 音频（图片、文件夹、字幕另外各一块）
      groups = [['作品', x => !x.pos], ['视频', x => x.pos && x.video], ['音频', x => x.pos && !x.video]].map(([n, f]) => [n, items.filter(f)]).filter(g => g[1].length);
      items = groups.flatMap(g => g[1]);
    }
    const picHtml = pics.length ? `<div class="img-sec">${items.length || playQ ? `<div class="sec-label">图片 · ${pics.length} 张</div>` : ''}<div class="img-grid">${pics.map((g, i) => `<button class="img-tile" data-g="${i}" title="${esc(g.name)}"><img loading="lazy" decoding="async" src="${esc(g.gthumb || thumbUrl(g.path))}" alt=""><span class="img-n">${esc(g.name)}</span></button>`).join('')}</div></div>` : '';
    const box = $('#play-list');
    const counts = groups ? [dhits.length ? '文件夹 ' + dhits.length : '', ...groups.map(([n, g]) => n + ' ' + g.length), pics.length ? '图片 ' + pics.length : ''].filter(Boolean).join(' · ') || '0 个'
      : [dhits.length ? dhits.length + ' 个文件夹' : sgroups ? sgroups.filter(g => g[0]).length + ' 个文件夹' : '', items.length || (!pics.length && !dhits.length) ? items.length + ' 个' : '', pics.length ? pics.length + ' 张图片' : ''].filter(Boolean).join(' · ');
    const inFolder = !playQ && !!getSource(playSrc)?.folder;  // 在某个文件夹里：每行不再重复写文件夹名（分组时小标题已经写了），只留“上次听到”
    const rowHtml = (x, i) => {
        const p = x.pos && pos[x.pos];
        return `<div class="pl-row ${qCur()?.key === x.key ? 'on' : ''}${LIBFLASH.has(x.key) ? ' is-new' : ''}${i === kbI && kbVis ? ' kb' : ''}" data-i="${i}"><span class="pl-n"><em>${i + 1}</em><span class="eq pl-eq" aria-hidden="true"><i></i><i></i><i></i></span></span>${rowArt(x, qCur()?.key === x.key, 40)}
          <div class="pl-main"><div class="pl-t"><span class="pl-tt">${esc(x.title)}</span>${x.video ? ' <span class="pill">视频</span>' : ''}${x.conv ? ` <span class="pill conv-pill" title="浏览器无法直接播放此格式：首次播放时将自动转换（仅转换一次）">${esc((x.ext || '').toUpperCase())}</span>` : ''}${(TAGS[x.key] || []).map(t => ` <span class="pill tag-pill">${esc(t)}</span>`).join('')}</div><div class="pl-a">${esc(x.artist || '')}</div><div class="pl-s">${inFolder ? (p ? `上次${x.video ? '看' : '听'}到 ${fmtT(p)}` : '') : esc(x.sub) + (p ? ` · 上次${x.video ? '看' : '听'}到 ${fmtT(p)}` : '')}</div></div>
          <span class="pl-acts"><button class="pl-ib" data-layer title="叠加到当前播放内容（同时播放，可分配到左右声道）" aria-label="叠加播放">${ICON.layers}</button><button class="pl-ib" data-qnext title="下一首播放" aria-label="下一首播放">${ICON.playNext}</button><button class="pl-ib" data-qadd title="加入播放列表" aria-label="加入播放列表">${ICON.addList}</button><button class="pl-ib" data-tagbtn title="标签" aria-label="标签">${ICON.tag}</button></span>${favBtn(x.key)}
          <span class="pl-d">${x.dur ? fmtT(x.dur) : ''}</span><span class="pl-m">${esc(MOB() || x.pos ? x.meta || '' : '')}</span></div>`; };  // 电脑上作品的时长在“时长”那一列，大小列空着
    const cardHtml = (x, i) => {
      const cur = qCur()?.key === x.key, p = x.pos && pos[x.pos];
      return `<div class="pl-card${cur ? ' on' : ''}${LIBFLASH.has(x.key) ? ' is-new' : ''}${i === kbI ? ' kb' : ''}" data-i="${i}" title="${esc(x.title)}">
          <div class="pc-art${wide ? ' wide' : ''}"><span class="pc-ic">${x.video ? ICON.film : ICON.note}</span>${hasCov(x) ? (wide ? `<img class="pc-bg" src="${esc(x.cover)}" alt="" loading="lazy" decoding="async" aria-hidden="true" onerror="this.remove()">` : '') + `<img class="pc-fg" src="${esc(x.cover)}" alt="" loading="lazy" decoding="async" onerror="${COV_ERR};this.remove()">` : ''}
            ${cur ? '<span class="art-eq"><span class="eq"><i></i><i></i><i></i></span></span>' : ''}${x.conv ? `<span class="pc-badge">${esc((x.ext || '').toUpperCase())}</span>` : x.video ? '<span class="pc-badge">视频</span>' : ''}
            <span class="pc-acts"><button class="pl-ib" data-qnext title="下一首播放" aria-label="下一首播放">${ICON.playNext}</button><button class="pl-ib" data-qadd title="加入播放列表" aria-label="加入播放列表">${ICON.addList}</button>${favBtn(x.key)}</span></div>
          <div class="pc-t">${esc(x.title)}</div><div class="pc-s">${esc(x.meta || '')}${p ? ` · ${x.video ? '看' : '听'}到 ${fmtT(p)}` : ''}</div></div>`;
    };
    // 网格：一排放几张，按列表的宽度算（窗口变宽变窄时重新排）
    const grid = view === 'grid', nv = grid ? items.filter(x => x.video).length : 0, wide = nv > 0 && nv * 2 >= items.length;
    const colsAt = wd => Math.max(2, Math.floor((wd - 40 + 14) / ((wide ? 176 : 150) + 14)));
    const cols = grid ? colsAt(box.clientWidth) : 1;
    // 列表里的每一行（分组标题也算一行；网格里一排卡片算一行），先只记下怎么画；行数多时只画看得见的那一段，几千个文件也一样流畅
    const ents = [], hdr = t => ents.push({ h: 'h', html: () => `<div class="sec-label pl-grp">${t}</div>` });
    const addItems = list => {  // list：[[项目, 序号], …]
      if (!grid) return list.forEach(([x, i]) => ents.push({ it: [i], html: () => rowHtml(x, i) }));
      for (let n = 0; n < list.length; n += cols) { const part = list.slice(n, n + cols); ents.push({ h: 'g', it: part.map(p => p[1]), html: () => `<div class="pl-grow" style="--cols:${cols}">${part.map(([x, i]) => cardHtml(x, i)).join('')}</div>` }); }
    };
    if (dhits.length) {
      hdr(`文件夹 · ${dhits.length}`);
      dhits.forEach(d => ents.push({ html: () => `<div class="pl-row pl-dirhit" data-dir="${esc(d)}"><span class="pl-n"></span><span class="pl-dic">${ICON.folder}</span>
          <div class="pl-main"><div class="pl-t">${esc(dirLabel(d.split('/').pop()))}</div><div class="pl-s">${playQ ? esc(d.includes('/') ? d.split('/').slice(0, -1).join(' / ') : '音源库') : `${kids(d).length ? kids(d).length + ' 个文件夹 · ' : ''}文件夹`}</div></div><span class="pl-m">${inDir(d).length + imgsIn(d).length} 个</span></div>` }));
      if (!playQ && items.length) hdr(`文件 · ${items.length}`);
    }
    let k = 0;
    if (groups) groups.forEach(([n, g]) => { hdr(`${n} · ${g.length}`); addItems(g.map(x => [x, k++])); });
    else if (sgroups) {
      const base = getSource(playSrc)?.path || '';
      // 每一段可以折叠（2026-11-17 用户：分组折叠必须要做）：点小标题收起 / 展开，记在 S.ui.grpFold（按子文件夹路径）；折叠的那段不画行，“播放”照样是整个文件夹
      const fold = new Set(S.ui?.grpFold || []);
      sgroups.forEach(([d, g]) => {
        const at = k;
        if (d) { const rel = d.slice(base.length + 1).split('/').map(dirLabel).join(' › '), shut = fold.has(d);
          hdr(`<button type="button" class="pl-gtog${shut ? '' : ' open'}" data-gfold="${esc(d)}" aria-expanded="${!shut}"><span class="pl-gch">${ICON.chev}</span><span class="pl-gt">${esc(rel)}</span><span class="pl-gc">· ${g.length} 个</span></button><button type="button" class="pl-gplay" data-gplay="${at}" data-gn="${g.length}" title="播放这一段" aria-label="播放这一段">${ICON.play}</button>`);
          if (shut) { k += g.length; return; } }
        addItems(g.map(x => [x, k++]));
      });
    } else addItems(items.map((x, i) => [x, i]));
    const virt = ents.length > 300 || (grid && ents.length > 40);
    const entOf = []; ents.forEach((e, j) => e.it?.forEach(i => { entOf[i] = j; }));
    kbI = sk === PLAYKB.sk && PLAYKB.key ? items.findIndex(x => x.key === PLAYKB.key) : -1;
    PLAYKB.sk = sk;
    const rowsHtml = virt ? '<div class="pl-vtop"></div><div class="pl-vwin"></div><div class="pl-vbot"></div>' : ents.map(e => e.html()).join('');
    // 2026-11-16 用户：文件很多的文件夹滑到下面，有时莫名回到最上面。手机上整页一起滚；同一个列表重画（换歌、刷新音源库、收藏……）时
    // 先清空再量行高，这一下页面只剩标题那么高，浏览器把滚动位置夹到顶上。现在同一个列表重画时先撑住原来的高度，画完回到原来的位置
    const keepY = MOB() && sk && box._sk === sk ? scrollY : null; box._sk = sk;
    if (keepY != null) box.style.minHeight = box.offsetHeight + 'px';
    // 表头（电脑、列表显示）：# · 标题 · 文件夹（在某个文件夹里时不显示这一列）· 大小
    box.classList.toggle('pl-noauthor', !S.ui?.plAuthor);  // 2026-11-18 用户：作者列放进设置里的开关，默认不显示
    const thead = !grid && !MOB() && (items.length || dhits.length) ? `<div class="pl-thead"><span class="pl-n">#</span><span></span><span class="pl-th2"><span>标题</span><span>作者</span><span>${inFolder ? '' : '文件夹'}</span></span><span></span><span class="pl-d">时长</span><span class="pl-m">${playSrc === 'works' ? '' : '大小'}</span></div>` : '';
    // 分组的“全部收起 / 全部展开”（2026-11-18 用户）：标题那排、排序左边一个图标；有一段开着就是全部收起，全收起了就是全部展开
    const gDirs = sgroups && !grid ? sgroups.filter(g => g[0]).map(g => g[0]) : [], gFold = new Set(S.ui?.grpFold || []), gAnyOpen = gDirs.some(d => !gFold.has(d));
    const grpAll = gDirs.length > 1 ? `<button type="button" class="pl-opts pl-gall" id="pl-gall" data-tip="${gAnyOpen ? '全部收起' : '全部展开'}" aria-label="${gAnyOpen ? '全部收起' : '全部展开'}">${gAnyOpen ? ICON.collapseAll : ICON.expandAll}</button>` : '';
    // 只是收起 / 展开分组时安静地重画：不再播放每一行的进场动画（以前整个右边像刷新了一次）
    box.classList.toggle('pl-quiet', !!drawList.quiet); drawList.quiet = false;
    box.innerHTML = `${crumbs ? `<div class="pl-crumbs">${crumbs}</div>` : ''}<div class="row between pl-head"><button type="button" class="pl-back" id="pl-back" title="返回" aria-label="返回">${ICON.chev}</button><div style="min-width:0"><h3 class="card-title" style="margin:0">${title}</h3><div class="tiny">${counts}</div></div>
        <span class="spacer"></span>${playQ && getSource(playSrc) && !(MOB() && !PLM) ? `<div class="seg mini pl-scope" id="pl-scope" role="group" aria-label="搜索范围">${[[0, srcName(getSource(playSrc))], [1, '全部']].map(([a, n]) => `<button type="button" data-all="${a}" class="${+playAll === a ? 'on' : ''}" aria-pressed="${+playAll === a}">${esc(n)}</button>`).join('')}</div>` : ''}${!playQ && playSrc === 'works' ? `<div class="seg mini pl-wk" id="pl-wk" role="group" aria-label="作品类型">${WKS.filter(([k]) => k === 'all' || KIND() === 'all' || KIND() === k).map(([k, n, ic]) => `<button type="button" data-wk="${k}" class="${WK() === k ? 'on' : ''}" title="${n}" aria-label="${n}" aria-pressed="${WK() === k}">${ic}</button>`).join('')}</div>` : ''}${grpAll}<button type="button" class="pl-opts" id="pl-opts" title="排序与显示方式（按文件夹分别记忆）" aria-haspopup="menu">${(VIEWS.find(v => v[0] === view) || VIEWS[0])[2]}<span>${SORTS.find(o => o[0] === sort)?.[1] || '默认'}</span>${PL_CHEV}</button>
        ${items.length ? `<button class="btn primary" id="pl-all">${ICON.play}播放</button><button class="btn" id="pl-shuf" title="随机播放">${PL_SHUF}随机播放</button>` : ''}</div>
      ${thead}<div class="pl-rows${virt ? ' pl-virt' : ''}${grid ? ' pl-gridv' : ''}">${rowsHtml}${picHtml}${items.length || pics.length || dhits.length ? '' : `<div class="empty tiny pl-empty">${playQ ? '没有找到' : playSrc === 'works' ? (WK() === 'all' ? '暂无作品' : '这一类暂无作品') : '此处暂无内容'}</div>`}</div>`;
    const bk = $('#pl-back', box); if (bk) bk.onclick = plmBack;
    $$('.img-tile', box).forEach(t => t.onclick = () => ImageViewer.open(pics.map(g => g.gsrc ? { src: g.gsrc, thumb: g.gthumb, name: g.name, sub: g.gsub } : ({ src: libUrl(g.path), thumb: thumbUrl(g.path), name: g.name, sub: dirLabel(g.dir).split('/').join(' / '),
      info: () => api('/api/play/imginfo?path=' + encodeURIComponent(g.path)) })), +t.dataset.g));
    $$('#pl-wk button', box).forEach(b => b.onclick = () => { S.ui = { ...(S.ui || {}), wkind: b.dataset.wk }; persist(); drawList(); });
    $$('#pl-scope button', box).forEach(b => b.onclick = () => { const a = b.dataset.all === '1'; if (a === playAll) return; playAll = a; drawSrc(); drawList(); });
    const openHit = r => {  // 搜到的文件夹：点一下打开它（左边的树也展开到那里）
      const d = r.dataset.dir, o = openDirs(), parts = d.split('/');
      for (let n = 1; n < parts.length; n++) o.add(parts.slice(0, n).join('/'));
      S.ui = { ...(S.ui || {}), openDirs: [...o] }; persist();
      playSrc = 'd:' + d; playQ = ''; playAll = false; $('#play-q').value = ''; vprefsSave(); plmEnter();
      drawSrc(); drawList(); $('#play-src .ps-item.on')?.scrollIntoView({ block: 'nearest' });
    };
    $$('.crumb', box).forEach(b => b.onclick = () => openHit(b));  // 标题上面那行路径：点上面几层回到那一层
    const rowsEl = $('.pl-rows', box);
    { const sb = () => box.style.setProperty('--sbw', Math.max(0, rowsEl.offsetWidth - rowsEl.clientWidth) + 'px'); sb(); requestAnimationFrame(sb); if (!box._sbRO && window.ResizeObserver) { box._sbRO = new ResizeObserver(() => { const r = $('.pl-rows', box); if (r) box.style.setProperty('--sbw', Math.max(0, r.offsetWidth - r.clientWidth) + 'px'); }); } box._sbRO?.disconnect(); box._sbRO?.observe(rowsEl); requestAnimationFrame(pbLayout); }  // 表头右边补上滚动条的宽度，和行对齐
    let vpaint = null, voff = null;
    if (virt) {
      // 先画几行量出行高和标题高，算出每一行的位置；之后滚动时只换中间那一段
      const top = $('.pl-vtop', rowsEl), win = $('.pl-vwin', rowsEl), bot = $('.pl-vbot', rowsEl);
      // 每种行（标题 / 普通一行 / 一排卡片）各画两个，量出高度
      const kinds = [...new Set(ents.map(e => e.h || 'r'))], sample = kinds.map(t => ents.find(e => (e.h || 'r') === t));
      win.innerHTML = sample.map(e => e.html() + e.html()).join('');
      const c = win.children, H = {};
      kinds.forEach((t, j) => { H[t] = c[2 * j + 1].offsetTop - c[2 * j].offsetTop || 58; });
      const off = [0]; ents.forEach(e => off.push(off[off.length - 1] + H[e.h || 'r'])); voff = off;
      const total = off[ents.length];
      const find = y => { let lo = 0, hi = ents.length; while (lo < hi) { const m = (lo + hi) >> 1; if (off[m + 1] <= y) lo = m + 1; else hi = m; } return lo; };
      let a0 = -1, b0 = -1;
      vpaint = () => {
        const pageScroll = MOB();  // 手机上整页一起滚（不在页面里再套一个小滚动框）
        const y = pageScroll ? Math.max(0, -rowsEl.getBoundingClientRect().top) : rowsEl.scrollTop, h = pageScroll ? innerHeight : (rowsEl.clientHeight || 800);
        const a = Math.max(0, find(y - 600)), b = Math.min(ents.length, find(y + h + 600) + 1);
        if (a === a0 && b === b0) return;
        a0 = a; b0 = b;
        top.style.height = off[a] + 'px'; bot.style.height = (total - off[b]) + 'px';
        win.innerHTML = ents.slice(a, b).map(e => e.html()).join('');
      };
      top.style.height = '0px'; win.innerHTML = ''; bot.style.height = total + 'px';
      const ro = new ResizeObserver(() => { if (!rowsEl.isConnected) return ro.disconnect(); a0 = -1; vpaint(); }); ro.observe(rowsEl);
    }
    if (grid) {  // 宽度变了、一排能放的张数跟着变：重新排一遍
      let w0 = box.clientWidth;
      const ro2 = new ResizeObserver(() => {
        if (!rowsEl.isConnected) return ro2.disconnect();
        if (Math.abs(box.clientWidth - w0) < 4) return; w0 = box.clientWidth;
        if (colsAt(box.clientWidth) !== cols) { if (sk) PLSCROLL()[sk] = rowsEl.scrollTop; drawList(); }
      });
      ro2.observe(box);
    }
    if (sk && PLSCROLL()[sk] && !MOB()) rowsEl.scrollTop = PLSCROLL()[sk];
    vpaint?.();
    if (keepY != null) { box.style.minHeight = ''; if (Math.abs(scrollY - keepY) > 1) scrollTo(0, keepY); vpaint?.(); }
    // 2026-11-16 用户：在播放栏里有一个（播放中或暂停）时，一键回到这个文件在列表里的位置（手机标题栏右边的按钮，phone.js）
    window.plLocate = key => {
      const i = items.findIndex(x => x.key === key); if (i < 0) return false;
      const j = entOf[i] ?? i, rowAt = () => rowsEl.querySelector(`[data-i="${i}"]`);
      let y; if (virt && voff) y = voff[j]; else { const r = rowAt(); if (!r) return false; y = r.offsetTop - rowsEl.offsetTop; }
      if (MOB()) scrollTo({ top: Math.max(0, rowsEl.getBoundingClientRect().top + scrollY + y - innerHeight * .4), behavior: 'smooth' });
      else rowsEl.scrollTo({ top: Math.max(0, y - rowsEl.clientHeight * .4), behavior: 'smooth' });
      setTimeout(() => { const r = rowAt(); if (!r) return; r.classList.remove('pl-flash'); void r.offsetWidth; r.classList.add('pl-flash'); setTimeout(() => r.classList.remove('pl-flash'), 1600); }, 650);
      return true;
    };
    window.plGoCur = () => {  // 不在现在这个列表里：打开它所在的文件夹（左边的树也展开到那里），再滚过去
      const c = qCur(); if (!c) return false; if (window.plLocate(c.key)) return true;
      const m = /^lib:(.*)$/.exec(c.key || ''); if (!m) return false; const d = m[1].includes('/') ? m[1].slice(0, m[1].lastIndexOf('/')) : '';
      if (!getSource('d:' + d)) return false;
      const o = openDirs(), parts = d.split('/'); for (let n = 1; n < parts.length; n++) o.add(parts.slice(0, n).join('/'));
      S.ui = { ...(S.ui || {}), openDirs: [...o] }; persist();
      playSrc = 'd:' + d; playQ = ''; playAll = false; const q = $('#play-q'); if (q) q.value = ''; vprefsSave(); plmEnter(); drawSrc(); drawList();
      setTimeout(() => window.plLocate?.(c.key), 120); return true;
    };
    if (window._plWs) { removeEventListener('scroll', window._plWs); window._plWs = null; }  // 每次重画列表只留一个（以前搜索每打一个字就多一个）
    if (vpaint) { const ws = () => { if (!rowsEl.isConnected) { removeEventListener('scroll', ws); if (window._plWs === ws) window._plWs = null; return; } if (MOB()) vpaint(); }; window._plWs = ws; addEventListener('scroll', ws, { passive: true }); }
    let tsc; rowsEl.onscroll = () => {
      vpaint?.();
      if (!sk) return; clearTimeout(tsc); tsc = setTimeout(() => { PLSCROLL()[sk] = Math.round(rowsEl.scrollTop); if (!VAULT) localStorage.setItem('plscroll', JSON.stringify(PLSC.n)); else vprefsSave(); }, 200);
    };
    rowsEl.oncontextmenu = e => {  // 右键：文件夹 / 文件 / 图片
      const hit = e.target.closest('.pl-dirhit'); if (hit) return PLAYCTX.dirMenu(e, hit.dataset.dir);
      const gh = e.target.closest('[data-gfold]'); if (gh) return PLAYCTX.dirMenu(e, gh.dataset.gfold);  // 分组小标题（子文件夹）：文件夹的右键菜单
      const g = e.target.closest('.img-tile');
      if (g) {
        const pic = pics[+g.dataset.g]; if (!pic || !pic.path) return;  // 生图的成品不在音源库里：用自带的右键菜单
        return ctxMenu(e, [...(REMOTE || VAULT ? [] : [{ label: '在资源管理器中显示', icon: CTX_IC.reveal, on: () => libReveal(pic.path, false) }, '-']),
          { label: '删除图片…', icon: CTX_IC.del, danger: true, on: () => libDelete(pic.path, false, pic.name) }]);
      }
      const r = e.target.closest('.pl-row[data-i], .pl-card[data-i]'); if (!r) return;
      const i = +r.dataset.i, x = items[i]; kbSet(i, false);
      const menu = [{ label: '播放', icon: ICON.play, on: () => playQueue(items, i) }, { label: '下一首播放', icon: ICON.playNext, on: () => qAdd(x, true) },
        { label: '加入播放列表', icon: ICON.addList, on: () => qAdd(x, false) }];
      if (x.pos) menu.push('-', ...(REMOTE || VAULT ? [] : [{ label: '在资源管理器中显示', icon: CTX_IC.reveal, on: () => libReveal(x.pos, false) }]),
        { label: '删除文件…', icon: CTX_IC.del, danger: true, on: () => libDelete(x.pos, false, x.title) });
      ctxMenu(e, menu);
    };
    rowsEl.onclick = e => {  // 每一行的点击都在这里统一处理（滚动时行会换掉，不在每行上单独绑）
      const hit = e.target.closest('.pl-dirhit'); if (hit) return openHit(hit);
      const gp = e.target.closest('[data-gplay]'); if (gp) { const a = +gp.dataset.gplay; return playQueue(items.slice(a, a + +gp.dataset.gn), 0); }  // 子文件夹那一段
      const gf = e.target.closest('[data-gfold]'); if (gf) { const f = new Set(S.ui?.grpFold || []), d = gf.dataset.gfold; f.has(d) ? f.delete(d) : f.add(d); S.ui = { ...(S.ui || {}), grpFold: [...f] }; persist(); if (sk) PLSCROLL()[sk] = rowsEl.scrollTop; drawList.quiet = true; return drawList(); }
      const r = e.target.closest('.pl-row[data-i], .pl-card[data-i]'); if (!r) return;
      const x = items[+r.dataset.i];
      // 2026-11-17 用户：电脑上的歌曲表改成单击选中、双击播放（照 Spotify / Apple Music）；悬停时序号位置的 ▶ 单击就播放；手机、网格照旧点一下就播放
      const selOnly = !MOB() && r.classList.contains('pl-row') && !e.target.closest('.pl-n, button, a, [data-fav]');
      kbSet(+r.dataset.i, false, selOnly);  // 点过的那一行就是键盘的起点
      if (selOnly) return;
      if (e.target.closest('[data-fav]')) return toggleFav(x.key);
      if (e.target.closest('[data-layer]')) {
        if (!PB.a || (PB.a === qAudio && !qCur())) return toast('请先播放一项内容，再叠加此项');
        if (PB.a === qAudio && qCur().key === x.key) return toast('此项正在播放');
        Sound.addLayer({ url: x.url, title: x.title }); spOpen(); return toast('已叠加：' + x.title);
      }
      if (e.target.closest('[data-qnext]')) return qAdd(x, true);
      if (e.target.closest('[data-qadd]')) return qAdd(x, false);
      if (e.target.closest('[data-tagbtn]')) return tagPopover(e.target.closest('[data-tagbtn]'), x.key, tagList(), () => { drawSrc(); drawList(); });
      playQueue(items, +r.dataset.i);
    };
    rowsEl.ondblclick = e => {  // 双击一行：播放（电脑上的列表）
      if (MOB()) return; const r = e.target.closest('.pl-row[data-i]'); if (!r || e.target.closest('.pl-n, button, a, [data-fav]')) return;
      window.getSelection?.()?.removeAllRanges(); playQueue(items, +r.dataset.i);
    };
    const ga = $('#pl-gall', box); if (ga) ga.onclick = () => { const f = new Set(S.ui?.grpFold || []); gDirs.forEach(d => gAnyOpen ? f.add(d) : f.delete(d)); S.ui = { ...(S.ui || {}), grpFold: [...f] }; persist(); if (sk) PLSCROLL()[sk] = rowsEl.scrollTop; drawList.quiet = true; drawList(); };
    const all = $('#pl-all', box); if (all) all.onclick = () => playQueue(items, 0);
    const shf = $('#pl-shuf', box); if (shf) shf.onclick = () => { if (!S.qmode.shuffle) { S.qmode.shuffle = true; persist(); } playQueue(items, Math.floor(Math.random() * items.length)); qPanelPaint(); npPaint(true); };
    const setOpt = (k, v) => { S.ui = { ...(S.ui || {}), [k]: { ...(S.ui?.[k] || {}), [sk || 'search']: v } }; if (sk) PLSCROLL()[sk] = 0; persist(); drawList(); };
    $('#pl-opts', box).onclick = e => {  // 一个按钮打开菜单：排序 / 显示方式 / 刷新
      const b = e.currentTarget; if (b._skip) return void (b._skip = false); b.classList.add('open');
      ctxMenu({ anchor: b, onClose: () => b.classList.remove('open') }, [{ group: '排序' },
        ...SORTS.map(([k, n, ic]) => ({ label: n, icon: ic, checked: sort === k, on: () => sort !== k && setOpt('sorts', k) })),
        ...(items.length ? [{ group: '显示方式' }, ...VIEWS.map(([v, n, ic]) => ({ label: n, icon: ic, checked: view === v, on: () => view !== v && setOpt('views', v) }))] : []),
        '-', { label: '刷新音源库', icon: ICON.redo, on: () => plRefresh() }]);
    };
    box._items = items;
    // 键盘选中：移到第 i 个，滚到看得见的地方（只画看得见的行时，先按位置滚过去再画）
    const kbSet = (i, scroll = true, vis = scroll) => {
      kbI = i; PLAYKB.key = items[i]?.key || null; kbVis = vis;
      $$('.kb', rowsEl).forEach(x => x.classList.remove('kb'));
      if (i < 0 || !kbVis) return;
      if (scroll) {
        if (voff) {
          const j = entOf[i], y0 = voff[j], y1 = voff[j + 1], st = rowsEl.scrollTop, ch = rowsEl.clientHeight;
          if (y0 < st) rowsEl.scrollTop = Math.max(0, y0 - 8); else if (y1 > st + ch) rowsEl.scrollTop = y1 - ch + 8;
          vpaint();
        }
        $(`[data-i="${i}"]`, rowsEl)?.scrollIntoView({ block: 'nearest' });
      }
      $(`[data-i="${i}"]`, rowsEl)?.classList.add('kb');
    };
    PLAYNAV = { items, grid, cols, kbSet, play: i => playQueue(items, i), get kb() { return kbI; } };
    if (playQ) subSearch(playQ, subAll || allTracks());
  };
  // 搜索时也在已有的字幕里找：列出是哪个文件、第几秒说的，点一下从那里开始播放
  const subSearch = async (q, all) => {
    const hits = await api('/api/play/subsearch?q=' + encodeURIComponent(q)).catch(() => []);
    const box = $('#play-list'); if (!box || playQ !== q || !hits.length) return;
    const rows = hits.map(h => ({ h, x: all.get(h.key) })).filter(r => r.x);
    if (!rows.length) return;
    const ql = q.toLowerCase(), mark = t => { const i = t.toLowerCase().indexOf(ql); return i < 0 ? esc(t) : esc(t.slice(0, i)) + `<mark>${esc(t.slice(i, i + q.length))}</mark>` + esc(t.slice(i + q.length)); };
    const sec = document.createElement('div'); sec.className = 'sub-hits';
    sec.innerHTML = `<div class="sec-label">字幕中找到 ${rows.length} 处</div>` + rows.map((r, i) => `<div class="pl-row sub-hit" data-h="${i}"><span class="pl-n">${fmtT(r.h.s)}</span>
        <div class="pl-main"><div class="pl-t">${mark(r.h.text)}</div><div class="pl-s">${esc(r.x.title)}</div></div></div>`).join('');
    $('.pl-rows', box).append(sec);
    $$('.sub-hit', sec).forEach(el => el.onclick = () => { const r = rows[+el.dataset.h]; playQueue([{ ...r.x, startAt: r.h.s }], 0); });
  };

  /* 拖动文件夹 / 标签排序：按住拖到同一层的别的位置，松手就记住（下次打开还是这个顺序）。只能在同一层里挪，子文件夹跟着一起走 */
  const bindSrcDrag = box => {
    let d = null;
    const rowsOf = grp => [...box.querySelectorAll('.ps-item[data-grp]')].filter(r => r.dataset.grp === grp);
    const subtreeEnd = r => { let e = r; const dp = +(r.dataset.depth || 0); for (let n = r.nextElementSibling; n && n.matches('.ps-dir') && +n.dataset.depth > dp; n = n.nextElementSibling) e = n; return e; };
    const cleanup = () => { d?.ghost?.remove(); d?.line?.remove(); d?.row.classList.remove('ps-dragging'); box.classList.remove('ps-sorting'); cancelAnimationFrame(d?.raf); d = null; };
    box.addEventListener('pointerdown', e => {
      const row = e.target.closest('.ps-item[data-grp]');
      if (!row || e.button !== 0 || e.pointerType === 'touch' || e.target.closest('[data-tog]') || playQ) return;
      d = { row, y0: e.clientY, id: e.pointerId, on: false };
    });
    const place = () => {
      const br = box.getBoundingClientRect(), y = Math.min(br.bottom - 4, Math.max(br.top + 4, d.y));
      d.ghost.style.top = (y - d.dy) + 'px';
      const others = d.sibs.filter(x => x !== d.row);
      d.k = others.filter(x => { const r = x.getBoundingClientRect(); return r.top + r.height / 2 < y; }).length;
      const ref = d.k < others.length ? others[d.k] : others.length ? subtreeEnd(others[others.length - 1]) : d.row;
      const rr = ref.getBoundingClientRect(), top = (d.k < others.length ? rr.top : rr.bottom) - br.top + box.scrollTop;
      Object.assign(d.line.style, { top: top - 1 + 'px', left: (ref.offsetLeft + 10 + (+(d.row.dataset.depth || 0)) * 14) + 'px', width: Math.max(40, d.row.offsetWidth - 20 - (+(d.row.dataset.depth || 0)) * 14) + 'px' });
      // 拖到上下边缘时自动滚动
      const edge = d.y < br.top + 36 ? -1 : d.y > br.bottom - 36 ? 1 : 0;
      cancelAnimationFrame(d.raf);
      if (edge) d.raf = requestAnimationFrame(() => { if (!d) return; box.scrollTop += edge * 9; place(); });
    };
    box.addEventListener('pointermove', e => {
      if (!d || e.pointerId !== d.id) return;
      d.y = e.clientY;
      if (!d.on) {
        if (Math.abs(e.clientY - d.y0) < 5) return;
        d.on = true; try { box.setPointerCapture(d.id); } catch { } box.classList.add('ps-sorting');
        d.sibs = rowsOf(d.row.dataset.grp); d.from = d.sibs.indexOf(d.row);
        const r = d.row.getBoundingClientRect(); d.dy = d.y0 - r.top;
        d.ghost = d.row.cloneNode(true); d.ghost.classList.add('ps-ghost'); d.ghost.classList.remove('glided', 'on');
        Object.assign(d.ghost.style, { left: r.left + 'px', width: r.width + 'px', height: r.height + 'px' });
        document.body.append(d.ghost);
        d.line = document.createElement('div'); d.line.className = 'ps-drop'; box.append(d.line);
        d.row.classList.add('ps-dragging');
      }
      place();
    });
    const end = e => {
      if (!d || e.pointerId !== d.id) return;
      if (!d.on) { d = null; return; }
      const { row, sibs, from, k } = d; cleanup();
      box._noClick = true; setTimeout(() => { box._noClick = false; }, 0);
      if (k == null || k === from) return;
      const names = sibs.map(x => x.dataset.name); const [n] = names.splice(from, 1); names.splice(k, 0, n);
      const grp = row.dataset.grp, prev = ORDER[grp] || [], shown = new Set(names);
      if (prev.some(x => !shown.has(x))) {  // 把看得到的这几个按新顺序填回它们原来占的位置
        let q = 0; const merged = prev.map(x => shown.has(x) ? null : x);  // null = 看得到的文件夹原来的位置
        names.filter(x => !prev.includes(x)).forEach(() => merged.push(null));  // 以前没排过的放最后
        names.splice(0, names.length, ...merged.map(x => x === null ? names[q++] : x));
      }
      ORDER[grp] = names;
      api('/api/play/order', { body: { group: grp, names } }).catch(err => toast(err.message, true));
      // 松手后各行从原来的位置滑到新位置
      const before = new Map([...box.querySelectorAll('.ps-item[data-src]')].map(r => [r.dataset.src, r.getBoundingClientRect().top]));
      drawSrc();
      box.querySelectorAll('.ps-item[data-src]').forEach(r => { const t = before.get(r.dataset.src); if (t == null) return; const dy = t - r.getBoundingClientRect().top; if (Math.abs(dy) > 1) r.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 340, easing: 'cubic-bezier(.2, .8, .2, 1)' }); });
    };
    box.addEventListener('pointerup', end); box.addEventListener('pointercancel', e => { if (d && e.pointerId === d.id) cleanup(); });
    box.addEventListener('click', e => { if (box._noClick) { e.stopPropagation(); e.preventDefault(); box._noClick = false; } }, true);
  };
  drawSrc(); drawList(); bindSrcDrag($('#play-src'));
  plRedraw = () => { if (stale() || !$('#play-src') || $('#main').dataset.page !== 'play') return false; drawSrc(); drawList(); return true; };
  if (srcTop) $('#play-src').scrollTop = srcTop;
  if (keepPY != null) { $('#main').style.minHeight = ''; if (Math.abs(scrollY - keepPY) > 1) scrollTo(0, keepPY); }
  const dirMenu = (e, d) => {  // 文件夹的右键菜单
    const all = lib.filter(x => under(x, d)).length + imgs.filter(x => under(x, d)).length;
    const items = [{ label: '播放全部', icon: ICON.play, on: () => { const t = inDir(d).map(libTrack); if (t.length) playQueue(t, 0); else toast('此文件夹中没有可播放的文件'); } }];
    if (!REMOTE && !VAULT) items.push({ label: '在资源管理器中打开', icon: CTX_IC.open, on: () => libReveal(d, true) });  // 私密空间里不用（资源管理器会记下文件夹名）
    if (d !== '未分类') items.push('-', { label: '删除文件夹…', icon: CTX_IC.del, danger: true, on: () => libDelete(d, true, dirLabel(d.split('/').pop()), all) });
    ctxMenu(e, items);
  };
  $('#play-src').oncontextmenu = e => { const b = e.target.closest('.ps-dir'); if (b) dirMenu(e, b.dataset.src.slice(2)); };
  PLAYCTX = { dirMenu };
  let tq; $('#play-q').oninput = e => { clearTimeout(tq); tq = setTimeout(() => { playQ = e.target.value.trim(); if (!playQ) playAll = false; drawSrc(); drawList(); plmPaint(); }, 180); };
  PB.onFav = () => { if (!$('#play-src')) return; if (playSrc === 'favs' && !playQ) { drawSrc(); drawList(); } else drawSrc(); };  // 在别的页面的全屏播放里点收藏：这里没东西可画
  PB.onTrack = () => {
    const box = $('#play-list'); if (!box) return;
    $$('.pl-row', box).forEach(r => {
      const x = box._items?.[+r.dataset.i], cur = x?.key === qCur()?.key;
      r.classList.toggle('on', cur);
      const a = $('.art', r); if (x && a && a.classList.contains('cur') !== cur) a.outerHTML = rowArt(x, cur, 40);  // 正在播放的音柱跟着走
    });
    $$('.pl-card', box).forEach(c => {  // 网格：正在播放的那张卡片
      const cur = box._items?.[+c.dataset.i]?.key === qCur()?.key, eq = $('.art-eq', c);
      c.classList.toggle('on', cur);
      if (cur && !eq) $('.pc-art', c).insertAdjacentHTML('beforeend', '<span class="art-eq"><span class="eq"><i></i><i></i><i></i></span></span>');
      if (!cur && eq) eq.remove();
    });
  };
}

/* ================= 播放队列 =================
   播放页点一首 / 全部播放：当前列表就是播放列表。可以拖动调整顺序、删除、随机、顺序 / 列表循环 / 单曲循环；
   长音频记住听到哪里。用一个 <video> 元素播放：音频、视频都能放，视频画面显示在全屏播放页里。 */
const qAudio = document.createElement('video');
// 音效与声道的主音轨：播放页的播放器；底栏在放别处的视频（生视频、素材库……）时就是那个视频（2026-11-18 用户：放视频时叠加没用）
const sndMain = () => PB.a && (PB.a === qAudio || PB.a.tagName === 'VIDEO') ? PB.a : qAudio;
qAudio.preload = 'metadata'; qAudio.playsInline = true; qAudio.className = 'np-video';
Sound.init(qAudio, {
  clock: () => { if (extOn()) return { t: PB.ext.t, paused: PB.ext.paused, rate: PB.rate, src: true };
    const a = sndMain(); return { t: a.currentTime, paused: a.paused || PB.a !== a, rate: a.playbackRate, src: !!a.currentSrc }; },
  onChange: () => spBtnPaint(),
});
S.qmode = Object.assign({ shuffle: false, repeat: 'off' }, S.qmode || {});
const qCur = () => PB.q?.items[PB.q.i];
function playQueue(items, i, keepOrder) {
  if (RC.ctl) return rcQueue(items, i);  // 正在控制手机：点的这一首交给手机放
  rcPrime();  // 手机：在点按里顺手启动一次无声播放器（见 rcKeepEl）
  const list = items.slice();
  PB.q = { items: list, orig: keepOrder && PB.q ? PB.q.orig : list.slice(), i };
  if (S.qmode.shuffle && !keepOrder) qShuffle(true);
  qLoad();
}
function qLoad() {
  const x = qCur(); if (!x) return;
  if (MINI_OUT === 'win' && !x.video) { appReturn('close').then(qLoad); return; }  // 下一个是音频：小窗口关掉，回到这边放
  if (MINI_OUT === 'pip' && !x.video) pipRestore();
  if (x.conv && !x.convUrl) return qConvert(x);
  qAudio.src = x.convUrl || x.url; qAudio.dataset.orbkey = 'q:' + x.key; qAudio.volume = S.muted ? 0 : vol();
  qAudio.classList.toggle('is-video', !!x.video);
  pbRegister(qAudio, () => ({ title: x.title, sub: x.sub, orb: x.orb, cover: x.cover, subsKey: x.subsKey, video: x.video }));
  const start = x.startAt; delete x.startAt;  // 从字幕搜索结果点进来：从那一句开始
  const resume = start != null ? start : x.resume || (x.pos ? playPos()[x.pos] : x.rc ? RC.rpos[x.key] : undefined);  // x.resume：电脑控制时电脑记着的进度；x.rc：普通空间里电脑发来的，只在内存里记
  const tok = qLoad.n = (qLoad.n || 0) + 1;
  qAudio.addEventListener('loadedmetadata', () => {
    if (qLoad.n !== tok) return;  // 等它加载期间又换了一首：这是上一首的，不管
    if (start != null) qAudio.currentTime = start;
    else if (resume && qAudio.duration && resume < qAudio.duration - 15) { qAudio.currentTime = resume; toast('从上次的 ' + fmtT(resume) + ' 继续'); }
  }, { once: true });
  if (/^(lib|job):/.test(x.key || '')) api('/api/play/recent', { body: { key: x.key } }).catch(() => { });  // 最近播放
  if (MINI_OUT === 'win') {  // 下一个也是视频：在应用外的小窗口里接着放
    PB.ext = { t: resume || 0, d: 0, paused: false };
    extCmd({ load: { src: new URL(x.convUrl || x.url, location.href).href, t: resume || 0, title: x.title } });  // 转换过的格式：给小窗口转好的那份
  } else qAudio.play().catch(e => { if (e?.name === 'NotSupportedError' && /^lib:/.test(x.key || '')) return; playErr(e); });  // 放不了的格式交给下面的自动转换
  pbTake(qAudio); pbPaint(true); PB.onTrack?.(); qPanelPaint(); spPaint();
  const mini = MINI; if (mini) mini._dismissed = false; miniSync();
}
/* 浏览器放不了的格式（avi、wmv、rmvb、ape、部分 H.265 视频……）：服务器用 ffmpeg 转一份能放的（只转一次，以后直接用），转好自动开始播放 */
async function qConvert(x) {
  const me = qConvert.n = (qConvert.n || 0) + 1, rel = x.pos;
  qAudio.pause(); qAudio.removeAttribute('src'); qAudio.load();
  pbRegister(qAudio, () => ({ title: x.title, sub: x.sub, orb: x.orb, cover: x.cover, video: x.video }));
  pbTake(qAudio); pbPaint(true); PB.onTrack?.(); qPanelPaint();
  const sub = t => { if (qCur() === x && $('#pb-sub')) $('#pb-sub').textContent = t; };
  let st = await api('/api/play/convert', { body: { path: rel } }).catch(e => ({ state: 'error', err: e.message }));
  if (st.state === 'error') { sub(x.sub); return toast(`「${x.title}」无法播放：${convWhy(st.err)}`, true); }  // 一开始就失败：只说一次原因
  if (st.state !== 'done') { toast('此格式需先转换才能播放，转换完成后将自动开始（仅转换一次）'); sub('正在转换… 0%'); }
  while (st.state === 'running' || st.state === 'none') {
    await sleep(800);
    if (qConvert.n !== me || qCur() !== x) return;  // 换了别的：不再等
    st = await api('/api/play/convert?path=' + encodeURIComponent(rel)).catch(e => ({ state: 'error', err: e.message }));  // 文件中途没了：别一直等
    if (st.state === 'running') sub(`正在转换… ${st.p || 0}%`);
  }
  if (qCur() !== x) return;
  if (st.state === 'done') { x.convUrl = st.url; qLoad(); }
  else { sub(x.sub); toast(`「${x.title}」无法播放：${convWhy(st.err)}`, true); }
}
const convWhy = e => /invalid data|error opening|no such file|moov atom|could not find|end of file|does not contain any stream|output file is empty/i.test(e || '') ? '文件已损坏，或并非音频 / 视频' : (e || '未知原因');  // ffmpeg 的英文报错换成看得懂的
qAudio.addEventListener('error', () => {  // 看着是能放的格式，实际解码不了（比如 H.265）：也自动转换
  const x = qCur(), err = qAudio.error;
  if (!x || !/^lib:/.test(x.key || '') || !err || err.code < 3 || PB.a !== qAudio) return;
  if (x.convUrl || x._convTried) { if (!x._badTold) { x._badTold = true; toast(`「${x.title}」无法播放：文件已损坏，或并非音频 / 视频`, true); } return; }  // 转过了还是放不了：说一声，别没反应
  x._convTried = true;
  fetch(x.url, { headers: { Range: 'bytes=0-0' } }).then(r => {
    if (r.status !== 404) {
      if (REMOTE && x.video && !x.conv) { toast(`「${x.title}」无法在手机上播放（通常因分辨率或帧率过高，例如 4K 120 帧），请在电脑上观看`, true); try { qAudio.pause(); } catch { } return pbPaint(true); }
      return qConvert(x);
    }
    if (qCur() !== x) return;
    toast(`找不到「${x.title}」（可能已被删除或移动），已跳到下一首`, true);
    if (PB.q && PB.q.i < PB.q.items.length - 1) qNext(false); else pbPaint(true);
  }, () => qConvert(x));
});
function qNext(auto) {
  if (RC.ctl) return void rcCmd({ c: 'next' });
  const q = PB.q; if (!q) return;
  if (auto && S.qmode.repeat === 'one') { qAudio.currentTime = 0; qAudio.play().catch(playErr); return; }
  if (q.i < q.items.length - 1) { q.i++; qLoad(); }
  else if (S.qmode.repeat === 'all' && q.items.length) { q.i = 0; qLoad(); }
  else if (!auto) toast('已是最后一首');
}
function qPrev() {
  if (RC.ctl) return void rcCmd({ c: 'prev' });
  const q = PB.q; if (!q || PB.a !== qAudio) { if (PB.a) PB.a.currentTime = 0; return; }
  if ((extOn() ? PB.ext.t : qAudio.currentTime) > 3 || q.i === 0) { if (extOn()) extCmd({ seek: 0 }); else qAudio.currentTime = 0; return; }
  q.i--; qLoad();
}
function qShuffle(on) {
  const q = PB.q; if (!q) return;
  const cur = qCur();
  if (on) {
    const rest = q.items.filter((_, k) => k !== q.i);
    for (let k = rest.length - 1; k > 0; k--) { const r = Math.floor(Math.random() * (k + 1)); [rest[k], rest[r]] = [rest[r], rest[k]]; }
    q.items = cur ? [cur, ...rest] : rest; q.i = 0;
  } else {
    const extra = q.items.filter(x => !q.orig.some(y => y.key === x.key));
    q.items = [...q.orig.filter(x => q.items.some(y => y.key === x.key)), ...extra];
    q.i = Math.max(0, q.items.findIndex(x => x.key === cur?.key));
  }
}
function qAdd(x, next) {
  if (!PB.q || !qCur()) { playQueue([x], 0); return toast('开始播放'); }
  const q = PB.q, at = next ? q.i + 1 : q.items.length;
  q.items = q.items.filter(y => y.key !== x.key || y === qCur());
  q.i = q.items.indexOf(qCur());
  q.items.splice(next ? q.i + 1 : q.items.length, 0, x);
  if (!q.orig.some(y => y.key === x.key)) q.orig.push(x);
  toast(next ? '下一首播放：' + x.title : '已加入播放列表'); qPanelPaint();
}
function qRemove(k) {
  const q = PB.q; if (!q) return;
  const wasCur = k === q.i;
  const [x] = q.items.splice(k, 1);
  q.orig = q.orig.filter(y => y.key !== x.key);
  if (k < q.i) q.i--;
  if (wasCur) { if (q.items.length) { q.i = Math.min(q.i, q.items.length - 1); qLoad(); } else { pbReset(); } }
  qPanelPaint();
}
function qDrop(pred) {  // 从播放列表拿掉一批（比如刚被删掉的文件）；正在放的也在里面：接着放剩下的下一首（原来是暂停的就停在那里）
  const q = PB.q; if (!q) return;
  const cur = qCur(), gone = pred(cur), wasPaused = !PB.a || PB.a.paused;
  const before = q.items.slice(0, q.i).filter(x => !pred(x)).length;
  q.items = q.items.filter(x => !pred(x)); q.orig = q.orig.filter(x => !pred(x));
  if (!q.items.length) return pbReset();
  if (!gone) { q.i = q.items.indexOf(cur); return qPanelPaint(); }
  q.i = Math.min(before, q.items.length - 1);
  qAudio.removeAttribute('src'); qAudio.load();
  qLoad(); if (wasPaused) qAudio.pause();
  qPanelPaint();
}
function qMove(from, to) {
  const q = PB.q; if (!q || from === to) return;
  const cur = qCur(); const [x] = q.items.splice(from, 1); q.items.splice(to, 0, x);
  q.i = q.items.indexOf(cur); qPanelPaint();
}
qAudio.addEventListener('ended', () => {
  const x = qCur();
  if (x?.pos) { const m = playPos(); delete m[x.pos]; savePos(m); }
  if (x?.rc) delete RC.rpos[x.key];
  qNext(true);
});
let lastSave = 0;
qAudio.addEventListener('timeupdate', () => {
  const x = qCur(); if (x?.rc && qAudio.currentTime >= 15) RC.rpos[x.key] = Math.round(qAudio.currentTime);  // 普通空间里电脑发来的：只在内存里记放到哪（切回来接着放，不写进手机的存储）
  if (!x?.pos || Date.now() - lastSave < 5000 || qAudio.currentTime < 15) return;
  lastSave = Date.now(); const m = playPos(); m[x.pos] = Math.round(qAudio.currentTime); savePos(m);
});
/* 进入 / 退出私密空间时：停掉并清空，底栏不再显示另一边的内容 */
function pbReset(unload) {  // unload：进出私密空间时，所有播放器连文件一起卸掉（iPhone 的“正在播放”会一直显示最后一个播放器的时长、进度）
  pipRestore(); if (MINI_OUT === 'win') appReturn('close');
  for (const x of [...PB.all, ...(unload && player ? [player] : [])]) { try { x.pause(); if (unload && x !== qAudio) { x.removeAttribute('src'); x.load(); } } catch { } }
  PB.a = null; PB.q = null; PB.meta = null;
  qAudio.removeAttribute('src'); qAudio.load();
  $('#pb-title') && ($('#pb-title').textContent = '未在播放'); $('#pb-sub') && ($('#pb-sub').textContent = ''); $('#pb-art') && ($('#pb-art').innerHTML = ''); $('#pb-fab-art') && ($('#pb-fab-art').innerHTML = '');
  npClose(true); qPanelClose(); miniSync();
  if (MS) { try { MS.metadata = null; MS.playbackState = 'none'; MS.setPositionState?.(); } catch { } }  // 系统音量浮窗 / 媒体键 / iPhone 的“正在播放”里不再显示刚才的标题、封面、时长
  pbPaint();
}
const REPEAT = { off: ['顺序播放', 'M17 2l4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3'], all: ['列表循环', 'M17 2l4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3'], one: ['单曲循环', 'M17 2l4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3'] };
const repeatIcon = m => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${REPEAT[m][1]}"/>${m === 'one' ? '<text x="12" y="15" text-anchor="middle" font-size="7" font-weight="800" fill="currentColor" stroke="none" font-family="system-ui">1</text>' : ''}</svg>`;
function qSetShuffle(on) { S.qmode.shuffle = on; persist(); qShuffle(on); qPanelPaint(); npPaint(true); toast(on ? '随机播放' : '按列表顺序播放'); }
function qCycleRepeat() { const order = ['off', 'all', 'one']; S.qmode.repeat = order[(order.indexOf(S.qmode.repeat) + 1) % 3]; persist(); qPanelPaint(); npPaint(true); toast(REPEAT[S.qmode.repeat][0]); }

/* 播放列表（底栏右侧弹出的面板 / 全屏播放页右侧共用一个渲染） */
function qListHtml() {
  if (RC.ctl) return rcQListHtml();  // 控制手机时：手机的播放列表
  const q = PB.q;
  const head = `<div class="ql-head"><div><b>播放列表</b><span class="tiny">${q ? q.items.length + ' 首' : ''}</span></div>
    <div class="row" style="gap:4px"><button class="ql-mode ${S.qmode.shuffle ? 'on' : ''}" data-qm="shuffle" title="随机播放"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg></button>
      <button class="ql-mode ${S.qmode.repeat !== 'off' ? 'on' : ''}" data-qm="repeat" title="${REPEAT[S.qmode.repeat][0]}">${repeatIcon(S.qmode.repeat)}</button>
      ${q ? '<button class="ql-mode" data-qm="clear" title="清空播放列表" aria-label="清空播放列表"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg></button>' : ''}</div></div>`;
  if (!q || !q.items.length) return head + `<div class="ql-empty">播放列表为空。请在“播放”页点击一首，或点击“全部播放”。</div>`;
  return head + `<div class="ql-rows">${q.items.map((x, k) => qRowHtml(x, k, k === q.i)).join('')}</div>`;
}
const qRowHtml = (x, k, cur) => `<div class="ql-row ${cur ? 'on' : ''}" draggable="true" data-k="${k}">
      <span class="ql-grip" title="拖动调整顺序">⋮⋮</span>${rowArt(x, cur, 36)}<div class="ql-main"><div class="ql-t">${cur ? '<span class="eq"><i></i><i></i><i></i></span>' : ''}${esc(x.title)}</div><div class="ql-s">${esc(x.sub)}</div></div>
      <button class="ql-x" data-qx="${k}" title="从播放列表移除">${ICON.x}</button></div>`;
/* 列表内容的指纹（不含“正在放第几首”）：没变就是只换了歌，只重画旧的和新的那两行（2026-11-17 审查 P07） */
function qSig() {
  const q = PB.q; if (RC.ctl || !q) return null;
  return q.items.map(x => (x.key || x.src || '') + '\u0001' + x.title + '\u0001' + x.sub + '\u0001' + (x.cover || '') + (x.video ? 'v' : '')).join('\u0002') + '|' + S.qmode.shuffle + S.qmode.repeat;
}
/* 事件挂在外面的框上（委托）：重画行不用重新绑定，400 首也只有一组监听 */
function qDelegate(box) {
  if (box._qDel) return; box._qDel = true;
  const row = e => !RC.ctl && e.target.closest?.('.ql-row[draggable]');
  box.addEventListener('click', e => {
    if (RC.ctl) return;
    const m = e.target.closest('[data-qm]'); if (m && box.contains(m)) return m.dataset.qm === 'shuffle' ? qSetShuffle(!S.qmode.shuffle) : m.dataset.qm === 'repeat' ? qCycleRepeat() : pbReset();
    const r = row(e); if (!r || !PB.q) return;
    const x = e.target.closest('[data-qx]'); if (x) return qRemove(+x.dataset.qx);
    const k = +r.dataset.k; if (k !== PB.q.i) { PB.q.i = k; qLoad(); }
  });
  box.addEventListener('dragstart', e => { const r = row(e); if (!r) return; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('application/x-studio-q', r.dataset.k); r.classList.add('dragging'); });
  box.addEventListener('dragend', e => row(e)?.classList.remove('dragging'));
  box.addEventListener('dragover', e => { const r = row(e); if (!r) return; e.preventDefault(); const rc = r.getBoundingClientRect(); r.classList.toggle('drop-before', e.clientY < rc.top + rc.height / 2); r.classList.toggle('drop-after', e.clientY >= rc.top + rc.height / 2); });
  box.addEventListener('dragleave', e => row(e)?.classList.remove('drop-before', 'drop-after'));
  box.addEventListener('drop', e => {
    const r = row(e); if (!r) return; e.preventDefault();
    const raw = e.dataTransfer.getData('application/x-studio-q'), after = r.classList.contains('drop-after'); r.classList.remove('drop-before', 'drop-after'); if (raw === '') return;
    const from = +raw; let to = +r.dataset.k + (after ? 1 : 0); if (from < to) to--; qMove(from, to);
  });
}
function qBind(box) {
  if (RC.ctl) return rcQBind(box);
  qDelegate(box);
  const on = $('.ql-row.on', box); if (on && !box._scrolled) { on.scrollIntoView({ block: 'nearest' }); box._scrolled = true; }
}
/* 播放列表重画（换了一首等）：留在原来的滚动位置，换了正在播的那首时平滑滚到新的那首（2026-11-17 用户：以前每次都跳回最上面）。
   你刚自己滚过列表（3 秒内）就不抢位置 */
function qRepaint(box, wrap) {
  const old = $('.ql-rows', box), was = old ? $('.ql-row.on', old)?.dataset.k : null, st = old ? old.scrollTop : null;
  const sig = qSig(), q = PB.q;
  // “正在播放 / 接下来播放”的小标题会跟着挪（上下留白变了）：记住看得见的第一行，更新完把它放回原来的位置，列表不跳
  let anc = null; if (old) for (const r of old.children) { if (r.offsetTop + r.offsetHeight > old.scrollTop && !r.classList.contains('on')) { anc = r; break; } }
  const ay = anc ? anc.offsetTop - old.scrollTop : 0, keep = () => { if (anc?.isConnected) { const d = anc.offsetTop - old.scrollTop - ay; if (Math.abs(d) > .5) old.scrollTop += d; } };
  let rows;
  if (sig && old && old._qSig === sig && old.children.length === q.items.length) {
    // 只换了歌：列表内容一样，只重画旧的和新的那一行，不建整张表、不逐行比较
    // “正在播放 / 接下来播放”的小标题会跟着挪（上下留白变了）：记住看得见的第一行，换完把它放回原来的位置，列表不跳
    const ks = new Set([was == null ? -1 : +was, q.i]);
    for (const k of ks) {
      const o = old.children[k]; if (!o || !q.items[k]) continue;
      const t = document.createElement('template'); t.innerHTML = qRowHtml(q.items[k], k, k === q.i); o.replaceWith(t.content.firstElementChild);
    }
    keep(); qBind(box);
    return qGlide(box, old, old, was, old.scrollTop);
  }
  const tmp = document.createElement('div'); tmp.innerHTML = wrap(qListHtml());
  const nrows = $('.ql-rows', tmp);
  if (old && nrows && old.children.length === nrows.children.length && box.firstElementChild?.className === tmp.firstElementChild?.className) {
    // 同一个列表（换歌时只有两行变了）：只换变了的行，列表本身不重建——滚动位置不动，正在进行的平滑滚动也不会被打断
    [...nrows.children].forEach((n, i) => { const o = old.children[i]; if (o && o.outerHTML !== n.outerHTML) o.replaceWith(n); });
    const oh = $('.ql-head', box), nh = $('.ql-head', tmp); if (oh && nh && oh.outerHTML !== nh.outerHTML) oh.replaceWith(nh);
    const oe = $('.ql-empty', box), ne = $('.ql-empty', tmp); if (oe && ne) oe.replaceWith(ne);
    keep(); qBind(box); rows = old;
  } else {
    box.replaceChildren(...tmp.childNodes); qBind(box);
    rows = $('.ql-rows', box); if (!rows) return;
    const mine = () => { box._qUser = Date.now(); box._qG = null; };  // 自己滚：停下正在进行的平滑滚动
    rows.addEventListener('wheel', mine, { passive: true });
    rows.addEventListener('touchmove', mine, { passive: true });
  }
  rows._qSig = sig;
  qGlide(box, rows, old, was, st);
}
function qGlide(box, rows, old, was, st) {
  const on = $('.ql-row.on', rows);
  const target = () => { const r = rows.getBoundingClientRect(), o = on.getBoundingClientRect(); return Math.max(0, Math.min(rows.scrollHeight - rows.clientHeight, rows.scrollTop + o.top - r.top - rows.clientHeight * .3 + o.height / 2)); };
  if (rows !== old && st == null) { if (on) { rows.scrollTop = target(); requestAnimationFrame(() => { if (on.isConnected && Date.now() - (box._qUser || 0) > 3000) rows.scrollTop = target(); }); } return; }  // 刚打开列表（比如从字幕切过来）：直接停在正在播的那首；下一帧排版定下来后再校正一次（切换标签时这一刻的高度还不准，以前会停在一半往下）
  if (rows !== old) { rows.scrollTop = st; box._qG = null; }  // 首数变了（比如坏文件被跳过）：先回到原来的位置，下面再滚过去
  if (!on || Date.now() - (box._qUser || 0) < 3000) { box._qG = null; return; }
  if (on.dataset.k === was) return;  // 没换歌：正在滚的接着滚
  const to = target(), from = rows.scrollTop, d = to - from;
  if (reduceMotion || Math.abs(d) < 2) { rows.scrollTop = to; return; }
  // 滚动的状态记在外面这个框上：中途列表又重画了，新的列表接着滚，不停下
  box._qG = { from, d, t0: performance.now(), D: Math.min(700, 360 + Math.abs(d) / 6) };  // 先快后慢，离得远稍微久一点
  const step = now => {
    const g = box._qG, el = $('.ql-rows', box); if (!g || !el) return;
    const t = Math.max(0, Math.min(1, (now - g.t0) / g.D)); el.scrollTop = g.from + g.d * (1 - Math.pow(1 - t, 4));
    if (t < 1) requestAnimationFrame(step); else box._qG = null;
  };
  requestAnimationFrame(step);
}
function qPanelPaint() {
  const p = $('#qpanel'); if (p && !p.hidden) qRepaint(p, h => h);
  const r = $('#np-right'); if (r && NP.tab === 'queue' && !$('#np').hidden) qRepaint(r, h => `<div class="np-queue">${h}</div>`);
  $('#pb-queue')?.classList.toggle('on', !!(p && !p.hidden));
}
function qPanelToggle() { const p = $('#qpanel'); if (p.hidden) { spClose(); p.hidden = false; p._scrolled = false; qPanelPaint(); pbLayout(); } else qPanelClose(); }
function qPanelClose() { const p = $('#qpanel'); if (p) p.hidden = true; $('#pb-queue')?.classList.remove('on'); }
document.addEventListener('mousedown', e => { const p = $('#qpanel'); if (p && !p.hidden && !p.contains(e.target) && !e.target.closest('#pb-queue')) qPanelClose(); });

/* ================= 音效与声道（底栏右侧的面板） =================
   上半部分“声道”：正在播放的（主音轨）和叠加的音轨，各自放 左 / 中 / 右 / 环绕，各自调音量；
   下半部分“音效”：一键预设 + 逐项微调。具体怎么处理声音在 sound.js。 */
const SP_POS = [['l', '左'], ['c', '中'], ['r', '右'], ['8d', '环绕']];
const spPct = v => Math.round(v * 100) + '%';
function spBtnPaint() {
  const on = Sound.fxActive() || Sound.layers.length > 0;
  ['#pb-fx', '#np-fx', '#np-fxm'].forEach(sel => $(sel)?.classList.toggle('fx-on', on));
}
function spHtml() {
  const m = Sound.main, f = Sound.fx, L = Sound.layers, cur = PB.a === qAudio ? qCur() : null, mainName = cur?.title || (PB.a && sndMain() === PB.a ? (typeof PB.a._pbMeta === 'function' ? PB.a._pbMeta() : PB.a._pbMeta)?.title || $('#pb-title')?.textContent || '当前播放' : '尚未播放');
  const seg = (v) => `<div class="seg mini sp-pos">${SP_POS.map(([k, n]) => `<button data-pos="${k}" class="${v === k ? 'on' : ''}">${n}</button>`).join('')}</div>`;
  const vol = v => `<div class="sp-vol"><input type="range" min="0" max="1.5" step="0.01" value="${v}" data-vol><span class="sp-v">${spPct(v)}</span></div>`;
  const track = (id, title, tag, t, extra = '', below = '') => `<div class="sp-track" data-t="${id}">
      <div class="sp-tt"><span class="sp-tag">${tag}</span><span class="sp-name" title="${esc(title)}">${esc(title)}</span>${extra}</div>
      <div class="sp-ctl">${seg(t.pos)}${vol(t.vol)}</div>${below}</div>`;
  const any8d = m.pos === '8d' || L.some(l => l.pos === '8d');
  const range = (k, v, min, max, step, show) => `<div class="sp-range"><input type="range" min="${min}" max="${max}" step="${step}" value="${v}" data-fx="${k}"><span class="sp-v" data-show="${k}">${show(v)}</span></div>`;
  // 2026-11-17 跟新播放页统一：说明放在名字的悬停提示里（不再每个名字后面一个“?”），行放进分组卡片
  const tip = h => esc(String(h).replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, ''));
  const row = (name, hint, ctl) => `<div class="sp-fx"><div class="sp-fx-n" data-tip="${tip(hint)}">${name}</div>${ctl}</div>`;
  const pct = v => v > 0 ? spPct(v) : '关';
  return `<div class="ql-head"><div><b data-tip="${tip('佩戴耳机效果最佳。仅作用于底部播放条当前播放的内容，不影响配音、换声的试听。<br><br>视频弹出到应用外的小窗口时，视频本身的声音不经过此处设置（叠加的音轨仍会同步播放）。')}">音效与声道</b></div>
      <button class="ql-mode" data-sp="reset" title="将声道和音效全部恢复为原样，并移除叠加的音轨">全部还原</button></div>
    <div class="sp-body">
      <div class="sec-label" style="margin-top:2px" data-tip="${tip('<b>左 / 右</b>：仅在该侧耳机播放（立体声会先合并为单声道）。<br><b>中</b>：保持原样，两侧均有。<br><b>环绕</b>：声音围绕头部缓慢旋转（8D）。<br><br><b>叠加音轨</b>：与当前内容同时播放；暂停、拖动进度、变速均会同步。在播放页的列表中点击 ' + ICON.layers.replace('<svg', '<svg width="13" height="13" style="vertical-align:-2px"') + ' 也可叠加。')}">声道</div>
      <div class="sp-grp">${track('main', mainName, '主音轨', m)}
      ${L.map((l, i) => track(l.id, l.title, '叠加 ' + (i + 1), l,
        `<button class="sp-ib ${l.loop ? 'on' : ''}" data-loop title="${l.loop ? '循环：开（此音轨短于主音轨时将从头循环播放）' : '循环：关'}">${repeatIcon('all')}</button>
         <label class="sp-off" title="错开秒数：正数表示延后开始，负数表示提前">错开<input class="input" type="number" step="0.5" value="${l.offset}" data-off>秒</label>
         <button class="sp-ib" data-rm title="移除此叠加音轨">${ICON.x}</button>`, `<div class="sp-seek"><input type="range" min="0" max="${Math.max(1, l.d || 1).toFixed(1)}" step="0.1" value="${Math.min(l.t, l.d || l.t).toFixed(1)}" data-seek aria-label="进度"><span class="sp-v sp-st">${fmtT(l.t)} / ${l.d ? fmtT(l.d) : '--:--'}</span></div>`)).join('')}
      <button class="sp-add" data-sp="add">${ICON.layers}叠加音轨…</button></div>
      ${any8d ? `<div class="sp-fx" style="margin-top:10px"><div class="sp-fx-n">环绕速度</div>${range('spin', f.spin, 2, 20, 1, v => v + ' 秒一圈')}</div>` : ''}
      <div class="sec-label">音效</div>
      <div class="chips sp-presets">${Object.entries(Sound.PRESETS).map(([k, p]) => `<button class="chip ${f.preset === k ? 'on' : ''}" data-preset="${k}">${p.name}</button>`).join('')}${f.preset === 'custom' ? '<span class="chip on sp-custom">自定义</span>' : ''}</div>
      <div class="sp-grp">${row('细节增强', '使耳语、摩擦、敲击等细微声音更清晰、更贴耳。', range('detail', f.detail, 0, 1, .01, pct))}
      ${row('温暖', '低频更饱满、高频更柔和，长时间聆听不刺耳，适合助眠。', range('warm', f.warm, 0, 1, .01, pct))}
      ${row('空间混响', '添加少量房间回响，如同在真实房间中聆听。小房间最贴耳，大厅最空旷。',
        `<div class="sp-room seg mini">${Object.entries(Sound.ROOMS).map(([k, n]) => `<button data-room="${k}" class="${f.room === k ? 'on' : ''}">${n}</button>`).join('')}</div>` + range('reverb', f.reverb, 0, 1, .01, pct))}
      ${row('立体声宽度', '100% 为原样；调高则左右分离更明显、更具包围感，调低则更集中，0% 为单声道。', range('width', f.width, 0, 2, .05, spPct))}
      ${row('耳机舒适', '将另一侧的声音少量混入，类似音箱的聆听效果，长时间佩戴耳机更舒适。单侧录音的偏向感也会减轻。', range('xfeed', f.xfeed, 0, 1, .01, pct))}
      <div class="sp-fx sp-fx-sw"><div class="sp-fx-n" data-tip="${tip('压低响亮部分、提升轻柔部分，使音量更平稳，夜间不会被突然的大声惊扰。')}">夜间模式</div><label class="switch"><input type="checkbox" data-night ${f.night ? 'checked' : ''}><span></span></label></div></div>
    </div>`;
}
function spPaint() {
  const p = $('#spanel'); if (!p || p.hidden || p._pick) return;
  const y = $('.sp-body', p)?.scrollTop || 0;
  p.innerHTML = spHtml(); spBind(p);
  const b = $('.sp-body', p); if (b) b.scrollTop = y;
}
function spBind(p) {
  const tid = el => { const t = el.closest('.sp-track')?.dataset.t; return t === 'main' ? 'main' : +t; };
  const setT = (id, patch) => id === 'main' ? Sound.setMain(patch) : Sound.setLayer(id, patch);
  $$('.sp-pos button', p).forEach(b => b.onclick = () => { setT(tid(b), { pos: b.dataset.pos }); spPaint(); });
  $$('[data-vol]', p).forEach(r => r.oninput = () => { setT(tid(r), { vol: +r.value }); r.nextElementSibling.textContent = spPct(+r.value); });
  $$('[data-loop]', p).forEach(b => b.onclick = () => { const id = tid(b); setT(id, { loop: !Sound.layers.find(l => l.id === id)?.loop }); spPaint(); });
  $$('[data-off]', p).forEach(i => i.onchange = () => setT(tid(i), { offset: +i.value || 0 }));
  $$('[data-rm]', p).forEach(b => b.onclick = () => { Sound.removeLayer(tid(b)); spPaint(); });
  $$('[data-seek]', p).forEach(r => {
    r.oninput = () => { r._drag = true; const id = tid(r), l = Sound.layers.find(x => x.id === id); r.nextElementSibling.textContent = `${fmtT(+r.value)} / ${l?.d ? fmtT(l.d) : '--:--'}`; };
    r.onchange = () => { Sound.seekLayer(tid(r), +r.value); r._drag = false; const o = $('[data-off]', r.closest('.sp-track')); if (o) o.value = Sound.layers.find(x => x.id === tid(r))?.offset ?? o.value; };
  });
  // 进度条跟着走（面板开着时每半秒刷一次；正在拖的那条不动）
  clearInterval(p._seekIv); p._seekIv = setInterval(() => {
    if (p.hidden || p._pick || !p.isConnected) return clearInterval(p._seekIv);
    $$('[data-seek]', p).forEach(r => { if (r._drag || document.activeElement === r) return; const l = Sound.layers.find(x => x.id === tid(r)); if (!l) return;
      if (l.d) r.max = l.d.toFixed(1); r.value = Math.min(l.t, l.d || l.t).toFixed(1); r.nextElementSibling.textContent = `${fmtT(l.t)} / ${l.d ? fmtT(l.d) : '--:--'}`;
      const o = $('[data-off]', r.closest('.sp-track')); if (o && document.activeElement !== o && +o.value !== l.offset) o.value = l.offset; });  // 键盘快进快退改了“错开”
  }, 500);
  $$('[data-preset]', p).forEach(b => b.onclick = () => { Sound.preset(b.dataset.preset); spPaint(); });
  $$('[data-room]', p).forEach(b => b.onclick = () => { Sound.setFx({ room: b.dataset.room, reverb: Sound.fx.reverb || .25 }); spPaint(); });
  $$('[data-fx]', p).forEach(r => r.oninput = () => {
    const k = r.dataset.fx, v = +r.value;
    Sound.setFx(k === 'spin' ? { spin: v, preset: Sound.fx.preset } : { [k]: v });
    const show = $(`[data-show="${k}"]`, p); if (show) show.textContent = k === 'spin' ? v + ' 秒一圈' : k === 'width' ? spPct(v) : v > 0 ? spPct(v) : '关';
    if (k !== 'spin') { $$('[data-preset]', p).forEach(c => c.classList.remove('on')); if (!$('.sp-custom', p)) $('.sp-presets', p).insertAdjacentHTML('beforeend', '<span class="chip on sp-custom">自定义</span>'); }
  });
  const nt = $('[data-night]', p); if (nt) nt.onchange = () => { Sound.setFx({ night: nt.checked }); spPaint(); };
  $('[data-sp="reset"]', p).onclick = () => { Sound.reset(); spPaint(); toast('已恢复原声'); };
  $('[data-sp="add"]', p).onclick = () => spPick();
}
function spToggle() { const p = $('#spanel'); if (p.hidden) spOpen(); else spClose(); }
function spOpen() { qPanelClose(); const p = $('#spanel'); p.hidden = false; p._pick = false; p.classList.toggle('over-np', !$('#np').hidden); spPaint(); pbLayout(); ['#pb-fx', '#np-fx', '#np-fxm'].forEach(s => $(s)?.classList.add('on')); }
function spClose() { const p = $('#spanel'); if (p) p.hidden = true; ['#pb-fx', '#np-fx', '#np-fxm'].forEach(s => $(s)?.classList.remove('on')); }
document.addEventListener('mousedown', e => { const p = $('#spanel'); if (p && !p.hidden && !p.contains(e.target) && !e.target.closest('#pb-fx, #np-fx, #np-fxm, .pop, .dd-menu, .tip-float')) spClose(); });
// 叠加：在面板里换成“选文件”的界面——和播放页一样先看文件夹，点进去再选文件；搜索时直接列出所有匹配的文件
async function spPick() {
  const p = $('#spanel'); if (!p || p.hidden) return;
  p._pick = true;
  p.innerHTML = `<div class="ql-head"><button class="sp-back" data-sp="back" title="返回">${ICON.chev}<b>选择要叠加的音轨</b></button></div>
    <div class="play-search sp-q"><span>${ICON.search}</span><input class="input" id="sp-q" placeholder="搜索全部音源和作品…"></div>
    <div class="sp-crumb"></div><div class="sp-body sp-pick"><div class="ql-empty">正在读取…</div></div>`;
  const back = () => { p._pick = false; spPaint(); };
  $('[data-sp="back"]', p).onclick = back;
  const gen = VGEN, [lib, jobs] = await Promise.all([libCache ? Promise.resolve(libCache) : api('/api/play/library').catch(() => []), api('/api/jobs').catch(() => [])]);
  if (gen !== VGEN || !p._pick) return;
  libCache = lib;
  const playing = PB.a === qAudio ? qCur()?.url : null;
  const works = jobs.filter(j => j.state === 'done' && j.has_output).map(j => ({ url: `/media/job/${j.id}/output.mp3?t=${j.finished}`, title: j.title, sub: j.kind === 'vc' ? '换声作品' : '配音作品', dir: '\:works' }));
  const files = lib.map(x => ({ url: libUrl(x.path), title: x.name, sub: dirLabel(x.dir || x.folder).split('/').join(' / '), video: x.video, dir: x.dir || x.folder })).filter(x => x.url !== playing);
  const all = [...works.filter(x => x.url !== playing), ...files];
  const dirs = new Set(); files.forEach(x => { if (x.dir === '未分类') return; const parts = x.dir.split('/'); for (let k = 1; k <= parts.length; k++) dirs.add(parts.slice(0, k).join('/')); });
  const ord = (pre, list) => { const o = SRC_ORDER['d:' + pre] || []; const ix = d => { const i = o.indexOf(d.split('/').pop()); return i < 0 ? 1e9 : i; }; return list.sort((a, b) => ix(a) - ix(b) || a.localeCompare(b, 'zh', { numeric: true })); };
  const kids = pre => ord(pre, [...dirs].filter(d => pre ? d.startsWith(pre + '/') && !d.slice(pre.length + 1).includes('/') : !d.includes('/')));
  const count = d => files.filter(x => x.dir === d || x.dir.startsWith(d + '/')).length;
  let cur = '';  // '' = 最上层；'\0works' = 作品
  const fileRow = (x, i) => `<div class="sp-pick-row" data-i="${i}" title="${esc(x.title)}"><span class="sp-pi">${x.video ? ICON.film : ICON.note}</span><div class="sp-pm"><div class="sp-pt">${esc(x.title)}</div>${x.showSub ? `<div class="sp-ps">${esc(x.sub)}</div>` : ''}</div></div>`;
  const dirRow = (d, name, n) => `<div class="sp-pick-row sp-dir" data-d="${esc(d)}"><span class="sp-pi">${ICON.folder}</span><div class="sp-pm"><div class="sp-pt">${esc(name)}</div></div><span class="sp-pn">${n}</span>${ICON.chev}</div>`;
  const draw = () => {
    const q = $('#sp-q', p).value.trim().toLowerCase();
    let list = [], html = '';
    if (q) {
      list = all.filter(x => (x.title + ' ' + x.sub).toLowerCase().includes(q)).slice(0, 200).map(x => ({ ...x, showSub: true }));
      $('.sp-crumb', p).innerHTML = `<span class="tiny">搜索结果 ${list.length} 个</span>`;
      html = list.map(fileRow).join('');
    } else {
      const parts = cur && cur !== '\:works' ? cur.split('/') : [];
      $('.sp-crumb', p).innerHTML = cur ? `<button data-go="">音源库</button>` + (cur === '\:works' ? '<span>/</span><b>作品</b>'
        : parts.map((x, k) => k === parts.length - 1 ? `<span>/</span><b>${esc(x)}</b>` : `<span>/</span><button data-go="${esc(parts.slice(0, k + 1).join('/'))}">${esc(x)}</button>`).join('')) : '<b>音源库</b>';
      if (!cur) {
        html = (works.length ? dirRow('\:works', '作品', works.length) : '') + kids('').map(d => dirRow(d, d, count(d))).join('');
        list = files.filter(x => x.dir === '未分类');  // 直接放在音源库里的文件
      } else if (cur === '\:works') list = works.filter(x => x.url !== playing);
      else { html = kids(cur).map(d => dirRow(d, d.split('/').pop(), count(d))).join(''); list = files.filter(x => x.dir === cur); }
      html += list.map(fileRow).join('');
    }
    const box = $('.sp-pick', p); box.innerHTML = html || '<div class="ql-empty">此处没有可叠加的音频或视频</div>'; box.scrollTop = 0;
    $$('[data-go]', p).forEach(b => b.onclick = () => { cur = b.dataset.go; draw(); });
    $$('.sp-dir', box).forEach(r => r.onclick = () => { cur = r.dataset.d; draw(); });
    $$('.sp-pick-row[data-i]', box).forEach(r => r.onclick = () => { const x = list[+r.dataset.i]; Sound.addLayer({ url: x.url, title: x.title }); back(); toast('已叠加：' + x.title); });
  };
  draw();
  const i = $('#sp-q', p); i.oninput = draw; setTimeout(() => i.focus(), 30);
}

/* ================= 全屏播放页（像音乐播放器的歌词页） =================
   左边：封面 / Siri 球（视频就显示画面）、标题、进度、控制；右边：字幕（三种排版、查找、点字幕跳转）或播放列表。
   背景用封面颜色做大幅模糊（没有封面时用 Siri 球的配色慢慢流动）。 */
const NP = { tab: 'subs', key: null };
/* 视频画面上的字幕（转换过字幕才有；可以在右上角关掉） */
function capPaint() {
  const cap = $('#np-cap'); if (!cap) return;
  const on = S.ui?.cap !== false && NP.sents?.length && PB.a === qAudio && PB.meta?.video;
  cap.hidden = !on; $('#np-capbtn')?.classList.toggle('on', S.ui?.cap !== false);
  if (!on) return;
  const tm = qAudio.currentTime; let s = null, k = -1;
  NP.sents.forEach((x, i) => { if (x.s <= tm + 0.05) { s = x; k = i; } });
  const txt = s && tm <= s.e + 1.2 ? s.text : '', tr = txt && S.tr.on && NP.tr ? NP.tr[k] || '' : '';
  const sig = txt + '|' + tr;
  if (cap.dataset.t !== sig) { cap.dataset.t = sig; cap.innerHTML = txt ? `<span>${esc(txt)}${tr && tr !== txt ? `<em class="tr">${esc(tr)}</em>` : ''}</span>` : ''; }
}
qAudio.addEventListener('timeupdate', () => { capPaint(); });
/* 悬浮小窗：视频在播放、但全屏播放页关着时，画面缩到右下角。可以拖动、拖四个角改大小；
   拖出窗口边缘（或点“弹出”）就变成窗口外的独立小窗：应用里是一个可以放在桌面任何地方、可选“始终在最前面”的小窗口；
   网页里是浏览器的画中画窗口（界面还是这一套）。 */
const IN_APP = () => !!window.pywebview?.api?.mini_open;
const MINI_BAR = 0;            // 小窗的按钮都浮在画面上，没有单独的控制栏
let MINI_OUT = null;           // null 在页面里 / 'pip' 网页画中画窗口 / 'win' 应用的独立小窗
let miniUI = null, pipWin = null, mdrag = null, mrz = null;
const miniAr = () => +getComputedStyle(MINI).getPropertyValue('--ar') || 16 / 9;
function miniPaint() { if (!MINI.hidden || MINI_OUT) miniUI?.paint(); }
/* 小窗大小：S.miniW 记的是画面“长边”的长度，横屏、竖屏视频看起来一样大；太高时缩小到窗口放得下 */
function miniSize(ar = miniAr()) {
  let w = ar >= 1 ? S.miniW || 360 : (S.miniW || 360) * ar;
  const maxH = innerHeight * .8 - MINI_BAR; if (w / ar > maxH) w = maxH * ar;
  w = Math.min(w, innerWidth * .6);  // 窗口很窄时也别太大
  return Math.round(Math.max(ar >= 1 ? 240 : 170, w));
}
function miniReset() {  // 清掉位置，回到右下角；保留用户调过的大小和画面比例
  MINI.removeAttribute('style');
  miniUI?.aspect();
  if (!MINI.classList.contains('dock')) MINI.style.width = miniSize() + 'px';
}
qAudio.addEventListener('loadedmetadata', () => {  // 换了一个比例不同的视频：小窗跟着变
  const m = MINI; if (MINI_OUT || mrz) return;
  miniUI?.aspect();
  if (m.classList.contains('dock')) return miniLayout();
  m.style.width = miniSize() + 'px';
  if (m.style.top) m.style.top = Math.min(innerHeight - m.offsetHeight - 8, Math.max(8, parseFloat(m.style.top))) + 'px';
});
/* “从播放条展开”：视频面板浮在底栏上方，跟着底栏走。
   默认和底栏一样宽（太高时按高度缩）；拖四个角可以改大小，按住画面可以左右挪，底边始终贴着底栏（S.dock 记住大小和左右位置） */
function miniLayout() {
  const mini = MINI, bar = $('#pbar'); if (!mini || !mini.classList.contains('dock') || MINI_OUT) return;
  const r0 = bar.getBoundingClientRect(), ar = miniAr(), D = S.dock || {}, fab = $('#pb-fab');
  // 播放条收起了：贴在右下角小圆钮的上方，而不是悬在空着的地方
  const r = document.body.classList.contains('pb-min') && fab && !fab.hidden ? { left: r0.left, width: r0.width, top: fab.getBoundingClientRect().top } : r0;
  const room = Math.max(120, r.top - 18);  // 底栏上方能放多高
  let w = D.w || r.width, h = w / ar;
  if (!D.w) { const cap = Math.max(160, Math.min(innerHeight * .42, r.top - 24)); if (h > cap) { h = cap; w = Math.min(r.width, h * ar); } }
  w = Math.max(200, Math.min(w, innerWidth - 16, room * ar)); h = w / ar;
  const cx = r.left + r.width / 2 + (D.dx || 0);
  let left = Math.min(innerWidth - w - 8, Math.max(8, cx - w / 2));
  if (w <= r.width) left = Math.min(r.left + r.width - w, Math.max(r.left, left));  // 左右挪动不超出播放条的宽度
  const gap = 10;  // 底边始终贴着播放条
  Object.assign(mini.style, { left: left + 'px', width: w + 'px', height: h + 'px', top: 'auto', right: 'auto', bottom: (innerHeight - r.top + gap) + 'px' });
}
addEventListener('resize', () => {
  miniLayout();
  const m = MINI; if (!m || MINI_OUT || m.classList.contains('dock') || !m.style.left) return;  // 窗口变小时，小窗别跑到外面去
  m.style.left = Math.min(innerWidth - m.offsetWidth - 8, Math.max(8, parseFloat(m.style.left))) + 'px';
  m.style.top = Math.min(innerHeight - m.offsetHeight - 8, Math.max(8, parseFloat(m.style.top))) + 'px';
});
/* 收起小窗：先播放收起动画（从播放条展开的会缩回播放条，悬浮小窗淡出缩小），结束后再真正隐藏 */
function miniHide(mini) {
  if (mini.hidden || mini._hiding) return;
  mini._hiding = true; mini.classList.remove('show');
  clearTimeout(mini._ht);
  mini._ht = setTimeout(() => { mini._hiding = false; if (!mini.classList.contains('show')) mini.hidden = true; }, 340);
}
function miniSync() {
  const mini = MINI; if (!mini) return;
  if (MINI_OUT === 'pip') { $('#pb-video')?.classList.add('on'); return; }  // 在画中画窗口里：不动它
  if (MINI_OUT === 'win') { if (!mdrag?.out) miniHide(mini); $('#pb-video')?.classList.add('on'); return; }
  const dock = S.vidMode === 'dock' && !document.body.classList.contains('pb-min');  // 播放条收起时：默认用悬浮小窗（画中画）
  if (mini.classList.contains('dock') !== dock) { mini.classList.toggle('dock', dock); miniReset(); }
  if (dock) miniLayout();
  const np = $('#np'), isVid = PB.a === qAudio && PB.meta?.video && qAudio.getAttribute('src');
  if (document.pictureInPictureElement === qAudio) { miniHide(mini); return; }  // 浏览器自带的画中画（不支持新版画中画的浏览器才会用到）
  if (isVid && np.hidden && !mini._dismissed) {
    if (qAudio.parentElement !== $('.mini-v', mini)) $('.mini-v', mini).prepend(qAudio);
    if (mini._hiding) { clearTimeout(mini._ht); mini._hiding = false; mini.classList.add('show'); }  // 收起动画中途又要显示：直接展开回来
    if (mini.hidden) { mini.hidden = false; miniLayout(); void mini.offsetWidth; mini.classList.add('show'); }
    miniPaint();
  } else {
    if (!np.hidden && qAudio.parentElement !== $('#np-stage')) $('#np-stage').prepend(qAudio);
    miniHide(mini);
  }
  $('#pb-video')?.classList.toggle('on', !mini.hidden);
}
/* ---- 弹到窗口外 ---- */
async function miniPopOut(e, pos) {
  if (IN_APP() && !VAULT) return appPopOut(e, pos);  // 私密空间里不开新窗口（地址和标题会被记进历史）
  if (window.documentPictureInPicture) return pipOpen().catch(er => toast('无法弹出：' + er.message, true));
  try { await qAudio.requestPictureInPicture(); } catch (er) { toast('无法弹出：' + er.message, true); }  // 老浏览器：只能用浏览器自带的画中画
}
const miniOutW = () => Math.round(MINI.classList.contains('dock') || MINI.hidden ? miniSize() : MINI.getBoundingClientRect().width);
/* 网页：浏览器的画中画窗口（Document Picture-in-Picture），把小窗整个搬进去，视频不中断；画中画窗口总在最前面 */
async function pipOpen() {
  const mini = MINI, ar = miniAr(), w = miniOutW();
  const win = await documentPictureInPicture.requestWindow({ width: w, height: Math.round(w / ar + MINI_BAR) });
  const css = [...document.styleSheets].find(s => /mini\.css/.test(s.href || ''));
  const st = win.document.createElement('style');
  st.textContent = 'html,body{margin:0;height:100%;background:#000;overflow:hidden;font:13px -apple-system,"Segoe UI","Microsoft YaHei UI",sans-serif}' + (css ? [...css.cssRules].map(r => r.cssText).join('\n') : '');
  win.document.head.append(st); win.document.title = VAULT ? 'Studio' : (PB.meta?.title || 'Studio');
  pipWin = win; MINI_OUT = 'pip';
  clearTimeout(mini._ht); mini._hiding = false;
  if (qAudio.parentElement !== $('.mini-v', mini)) $('.mini-v', mini).prepend(qAudio);
  mini.classList.remove('dock', 'drag'); mini.removeAttribute('style'); miniUI.aspect();
  mini.hidden = false; mini.classList.add('out', 'show');
  win.document.body.append(mini);
  miniUI.icon('pop', 'back'); $('[data-mini="pop"]', mini).title = '放回页面';
  win.addEventListener('keydown', e => { if (e.key === ' ') { e.preventDefault(); if (!e.repeat) qAudio.paused ? qAudio.play().catch(playErr) : qAudio.pause(); }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); keySeek(qAudio, Math.min((qAudio.duration || 1e9) - .05, Math.max(0, qAudio.currentTime + (e.key === 'ArrowLeft' ? -5 : 5)))); } });
  win.addEventListener('pagehide', pipRestore, { once: true });
  miniSync();
}
function pipRestore() {  // 画中画窗口关掉（或点“放回页面里”）：小窗回到页面右下角
  if (MINI_OUT !== 'pip') return;
  const mini = MINI, w = pipWin; MINI_OUT = null; pipWin = null;
  mini.classList.remove('out', 'show'); mini.hidden = true;
  document.body.append(mini); miniReset();
  miniUI.icon('pop', 'pop'); $('[data-mini="pop"]', mini).title = '弹出到窗口外（可拖动到任意位置）';
  miniSync();
  try { w?.close(); } catch { }
}
/* 应用：一个独立的小窗口（没有标题栏，可以拖到桌面任何地方、拖四个角改大小、选“始终在最前面”）。
   小窗口在放的时候，这边的视频先暂停；底栏的播放 / 拖动 / 快进快退会转给小窗口，进度也跟着它走。 */
async function appPopOut(e, pos) {
  const mini = MINI, ar = miniAr(), w = miniOutW(), r = mini.getBoundingClientRect();
  const ox = e ? e.screenX - e.clientX : screenX, oy = e ? e.screenY - e.clientY : screenY;  // 页面左上角在屏幕上的位置
  const p = pos || { x: ox + r.left, y: oy + r.top };
  const st = { src: new URL(qAudio.currentSrc || qAudio.src, location.href).href, t: qAudio.currentTime, paused: qAudio.paused, title: PB.meta?.title || '',
    vol: qAudio.volume, rate: PB.rate, ar, w, h: Math.round(w / ar + MINI_BAR), x: Math.round(p.x), y: Math.round(p.y), top: S.miniTop !== false, drag: !!p.drag };
  MINI_OUT = 'win'; PB.ext = { t: st.t, d: qAudio.duration || 0, paused: st.paused };
  if (Sound.fxActive()) toast('在应用外的小窗口中，视频声音不经过音效和声道设置');
  qAudio.pause(); miniSync(); pbPaint();
  try { await window.pywebview.api.mini_open(st); }
  catch (er) { MINI_OUT = null; PB.ext = null; if (!st.paused) qAudio.play().catch(playErr); miniSync(); toast('无法弹出：' + er.message, true); }
}
const extCmd = c => { if (RC.ctl) return rcCmd(c); window.pywebview?.api?.mini_cmd(c).catch(() => { }); return true; };  // 控制手机时：命令转给手机
const extOn = () => (MINI_OUT === 'win' || RC.ctl) && PB.a === qAudio;
async function appReturn(mode) {  // mode：back 放回页面里 / fold 收起画面、声音继续 / close 关闭并暂停
  if (MINI_OUT !== 'win') return;
  await window.pywebview.api.mini_close(mode).catch(() => window.miniReturn({ mode }));
  if (MINI_OUT === 'win') window.miniReturn({ mode });
}
window.miniDragDone = () => { if (mdrag?.out) miniDrag('end', {}); };  // 从页面里拖出去、系统接手拖动后松开了鼠标
document.addEventListener('pointerdown', () => { if (mdrag?.out) miniDrag('end', {}); }, true);  // 保险：万一没收到松手
window.miniExt = st => {  // 小窗口每隔一会儿报一次进度；和页面里一样，每 5 秒记一次看到哪里
  if (MINI_OUT !== 'win' || !st) return; PB.ext = st; pbPaint();
  const x = qCur();
  if (x?.pos && st.t >= 15 && Date.now() - lastSave >= 5000) { lastSave = Date.now(); const m = playPos(); m[x.pos] = Math.round(st.t); savePos(m); }
};
window.miniExtEnded = () => {
  if (MINI_OUT !== 'win') return;
  const q = PB.q, x = qCur();
  if (x?.pos) { const m = playPos(); delete m[x.pos]; savePos(m); }  // 看完了：下次从头开始
  if (S.qmode.repeat === 'one') extCmd({ seek: 0, play: true });
  else if (q && (q.i < q.items.length - 1 || S.qmode.repeat === 'all')) qNext(true);
  else { PB.ext = { ...(PB.ext || {}), paused: true }; pbPaint(); }
};
window.miniReturn = st => {  // 小窗口关掉 / 放回页面：从它停下的地方接着放
  if (MINI_OUT !== 'win') return;
  st = st || {}; MINI_OUT = null; PB.ext = null;
  if (st.w) S.miniW = Math.round(st.ar && st.ar < 1 ? st.w / st.ar : st.w);
  if (st.top != null) S.miniTop = !!st.top;
  persist();
  if (isFinite(st.t)) qAudio.currentTime = st.t;
  MINI._dismissed = st.mode === 'close' || st.mode === 'fold';
  if (st.mode !== 'close' && st.paused === false) qAudio.play().catch(playErr);
  miniReset(); miniSync(); pbPaint();
};
qAudio.addEventListener('volumechange', () => { if (MINI_OUT === 'win') extCmd({ vol: qAudio.volume }); });

/* ================= 遥控播放：私密空间里用电脑控制手机正在播放的内容（2026-11-16 用户；后台中转见 vaultrc.py） =================
   电脑（本机）在私密空间里：播放条上一直有手机图标，点了 = 开启控制（手机还没播放也可以先开）。之后播放条显示手机的进度，
   播放 / 暂停 / 上一首 / 下一首 / 拖进度 / 快进快退 / 速度都转给手机，在电脑上点一首也交给手机放（借用桌面应用小窗口那一套：PB.ext 是手机的进度，extCmd 转给手机）。
   手机（REMOTE，“允许电脑控制”默认开）：不管在不在私密空间，只要在放东西，就挂着一个等命令的请求，顺便知道电脑开没开控制；
   - 在私密空间里：一直报在放什么（电脑一开就能看到）；
   - 不在私密空间：电脑开着控制时才报；电脑点的私密内容换成一次性地址发过来，手机上只显示“电脑控制播放”，不露出名字 / 封面 / 画面，
     不记进最近播放、播放进度；电脑关掉控制或退出私密空间，这些马上停掉、清掉；
   - 在私密空间里放着、电脑开着控制时退出私密空间：先换成一次性地址，退出后从原来的位置接着放（rcHandoff）。
   2026-11-16 iPhone 真机测试（iOS 27，主屏幕应用，devtest/tools/ios_lock_probe.py）：锁屏时只要还在出声，网页照常运行、命令当秒执行；
   真暂停十几秒后网页就被系统挂起、收不到命令。所以手机上暂停（或放完）时改放一段无声音频保持运行，最长 30 分钟（rcKeep）。
   音量改不了：iPhone 不允许网页改音量。后台只在内存里转，不存、不记日志。 */
function rcPhone() { return REMOTE && localStorage.getItem('rcAllow') !== '0'; }
function rcPC() { return VAULT && !REMOTE; }
const rcHdr = () => ({ 'X-Space': VAULT ? 'v' : 'n' });
function rcPost(body) { if (RC.lock) return Promise.resolve(null); return fetch('/api/rc/state', { method: 'POST', headers: { ...rcHdr(), 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive: true }).then(r => r.ok ? r.json() : null).catch(() => null); }
/* ---- 手机这边 ---- */
const rcActive = () => !!qCur() && PB.a === qAudio;
const rcMayKeep = () => rcPhone() && rcActive() && (VAULT || RC.armed);  // 普通空间里：电脑开着控制才放无声音频
function rcState() {
  const x = qCur(); if (!x || PB.a !== qAudio) return null;
  const o = { t: qAudio.currentTime || 0, d: pbDur(qAudio) || 0, paused: qAudio.paused, rate: PB.rate || 1, i: PB.q.i, n: PB.q.items.length, soft: !!RC.keep, qv: RC.qv || 0, ...(RC.kerr ? { kerr: RC.kerr } : {}) };
  if (x.rc) return { ...o, rc: true };  // 电脑发来的私密内容：名字后台记着（手机这边没有）
  return { ...o, title: x.title || '', sub: x.sub || '', video: !!x.video, cover: x.cover || '', orb: x.orb || '', ...(VAULT ? { key: x.key || '', subsKey: x.subsKey || '' } : {}) };  // key / subsKey：电脑收藏、看字幕用（只给私密空间里的）
}
function rcReport(force) {
  if (!rcPhone() || !rcActive()) { if (!RC.gone) rcBye(); return; }
  rcListen();  // 等命令，顺便知道电脑开没开控制
  if (!VAULT && !RC.armed) return;  // 普通空间：电脑开着控制才报在放什么
  const sig = PB.q.items.length + ':' + PB.q.items.map(x => x.key).join('|'), qChanged = sig !== RC.qsig;
  const now = Date.now(); if (!force && !qChanged && now - RC.lastRep < 1800) return;
  RC.lastRep = now; RC.gone = false;
  if (qChanged) { RC.qsig = sig; RC.qv = (RC.qv || 0) + 1; }
  const st = rcState();
  if (qChanged) st.queue = qCur()?.rc ? [] : PB.q.items.map(x => ({ title: x.title || '', sub: x.sub || '' }));  // 播放列表变了才带（电脑上显示手机的播放列表）
  rcPost(st);
}
function rcBye() { const was = !RC.gone; RC.gone = true; rcKeep(false); if (was) rcPost({ gone: true }); }
async function rcListen() {
  if (RC.loop) return; RC.loop = true;
  try {
    let since = -1;
    while (rcPhone() && rcActive()) {  // 不用 api()：进出空间时它的结果永远不回来，这个循环就停在那里了
      if (since >= 0 && !VAULT && !RC.armed && qAudio.paused && !RC.keep) break;  // 普通空间、电脑没开控制、也没在放：不用再等
      const ac = RC.ac = new AbortController(), v0 = VAULT;  // 换空间时取消挂着的请求（vaultSwitchUI），按新空间重新等
      const r = await fetch(`/api/rc/wait?since=${since}&armed=${RC.armed ? 1 : 0}&p=${qAudio.paused ? 0 : 1}`, { headers: rcHdr(), signal: ac.signal }).then(x => x.ok ? x.json() : null).catch(() => null);  // p：正在放（电脑据此自动开启控制）
      if (!r) { await sleep(ac.signal.aborted ? 100 : 2000); continue; }
      if (v0 && !VAULT) r.cmds = (r.cmds || []).filter(c => c.c !== 'queue' || c.items?.every(x => x.rc));  // 保险：退出私密空间前发出的请求带回来的私密原地址不要
      since = r.seq;  // 后台重启过序号会变小：跟着它
      const was = RC.armed; RC.armed = !!r.armed;
      if (RC.armed && !was) { RC.qsig = ''; rcReport(true); }  // 电脑刚开启控制：马上报一次（连播放列表）
      if (!RC.armed && was) rcDisarmed();
      for (const c of r.cmds || []) if (rcPhone()) rcRun(c);
    }
  } finally { RC.loop = false; }
}
function rcDisarmed() {  // 电脑关掉了控制 / 退出了私密空间：不在私密空间时，电脑发来的私密内容马上停掉、清掉
  if (VAULT) return;
  rcKeep(false); RC.rpos = {};
  if (qCur()?.rc) { pbReset(true); toast('电脑已停止控制'); }
}
function rcRun(c) {
  idleT = Date.now();  // 电脑在操作：不算没人用（私密空间的自动退出）
  const a = qAudio;
  if (c.c === 'queue') { RC.rpos = {}; playQueue(c.items, c.i); return setTimeout(() => rcReport(true), 400); }  // 新的一串：上一串的内存进度作废（rc:序号会对不上）
  if (!qCur()) return;
  if (c.c === 'jump') { if (c.v < PB.q.items.length && c.v !== PB.q.i) { PB.q.i = c.v; qLoad(); } }
  else if (c.c === 'next') qNext(false);
  else if (c.c === 'prev') qPrev();
  else if (c.c === 'toggle') a.paused ? a.play().catch(() => { }) : a.pause();
  else if (c.c === 'play') a.play().catch(() => { });
  else if (c.c === 'pause') a.pause();
  else if (c.c === 'seek') a.currentTime = Math.max(0, c.v);
  else if (c.c === 'seekBy') a.currentTime = Math.max(0, Math.min((pbDur(a) || 1e9) - 0.05, a.currentTime + c.v));
  else if (c.c === 'rate' && c.v > 0) { PB.rate = c.v; a.playbackRate = c.v; const r = $('#pb-rate'); if (r) { r.textContent = PB.rate + '×'; r.classList.toggle('on', PB.rate !== 1); } }
  pbPaint(); setTimeout(() => rcReport(true), 300);
}
/* 无声播放器只建一个、一直用它（2026-11-17 用户真机：暂停一小会儿电脑就显示手机已休眠）：iPhone 上一个播放器要先在点按里启动过一次，
   之后程序（电脑发来的暂停、锁屏）叫它放才不会被拒绝。以前每次暂停都新建一个，没在点按里启动过 → 放不出来 → 十几秒后网页被挂起。
   所以：你在手机上点播放的那一下（playQueue / 播放按钮）顺手把它启动一次再停下（rcPrime），以后都用这一个，停的时候只暂停不丢掉 */
function rcKeepEl() { if (!RC.kel) { const k = RC.kel = new Audio(); k.loop = true; k.preload = 'auto'; k.src = '/api/rc/silence.wav'; } return RC.kel; }
function rcPrime() {
  if (!REMOTE || RC.primed || localStorage.getItem('rcAllow') === '0') return;
  const k = rcKeepEl(); RC.primed = true;
  const pr = k.play(); if (!RC.keep) k.pause();  // 只要在点按里叫过一次 play 就算启动过；马上停下，不出声、不多占声音
  pr?.catch?.(() => { });
}
function rcKeep(on) {  // 暂停 / 放完时放无声音频，网页不被挂起，电脑还能叫醒它；不登记到播放条（PB）里，不影响正在放的那个
  clearTimeout(RC.keepT);
  if (!on) { const k = RC.keep; RC.keep = null; if (k) k.pause(); return; }
  if (!rcMayKeep()) return;
  const k = RC.keep = rcKeepEl();
  k.play().then(() => { if (RC.kerr) { RC.kerr = ''; rcReport(true); } }, e => { if (e?.name === 'AbortError') return; RC.kerr = e?.name || 'error'; rcReport(true); });  // 放不出来：告诉电脑原因
  RC.keepT = setTimeout(() => { rcKeep(false); rcReport(true); }, 30 * 60000);
}
const rcIdle = () => setTimeout(() => { if (rcMayKeep() && qAudio.paused) { rcKeep(true); rcReport(true); } }, 500);  // 换歌时也会短暂暂停：过一会儿还停着才算
qAudio.addEventListener('pause', rcIdle);
qAudio.addEventListener('ended', rcIdle);
qAudio.addEventListener('play', () => { if (RC.ctl) { qAudio.pause(); return void rcCmd({ c: 'toggle' }); } rcKeep(false); rcReport(true); });  // 电脑控制手机时，电脑这边的播放器不出声：空格键之类直接让它放的，转成手机的播放 / 暂停
['seeked', 'loadedmetadata', 'ratechange'].forEach(t => qAudio.addEventListener(t, () => rcReport(true)));
setInterval(() => rcReport(false), 2000);
async function rcHandoff() {  // 手机要退出私密空间、电脑开着控制、正在放：先把正在放的这一串换成一次性地址
  if (!rcPhone() || !RC.armed || !rcActive() || qAudio.ended || qCur()?.rc) return null;
  const q = PB.q, items = q.items.map(x => ({ key: x.key, subsKey: x.subsKey, title: x.title, sub: x.sub, cover: x.cover, orb: x.orb, url: x.url, convUrl: x.convUrl, conv: x.conv }));  // 名字只留在后台给电脑看
  const r = await fetch('/api/rc/hand', { method: 'POST', headers: { 'X-Space': 'v', 'Content-Type': 'application/json' }, body: JSON.stringify({ items, i: q.i }) }).then(x => x.ok ? x.json() : null).catch(() => null);
  return r?.items?.length ? { items: r.items, i: r.i, t: qAudio.currentTime || 0, paused: qAudio.paused } : null;
}
function rcResume(h) {  // 退出私密空间以后：从原来的位置接着放（原来是暂停的就还暂停着）
  const x = h.items[h.i]; if (x && h.t > 1) x.startAt = h.t;
  if (h.paused) qAudio.addEventListener('play', () => qAudio.pause(), { once: true });
  RC.rpos = {}; playQueue(h.items, h.i);
}
/* ---- 电脑这边 ---- */
/* 全屏播放页的字幕要一个“播放器”：这个代表手机——时间 / 暂停取手机的，改时间 = 让手机跳过去，play = 让手机放 */
const RCA = new EventTarget();
Object.defineProperties(RCA, {
  currentTime: { get: () => PB.ext?.t || 0, set: v => rcCmd({ c: 'seek', v }) },
  paused: { get: () => !RC.ctl || !!PB.ext?.paused },
  duration: { get: () => PB.ext?.d || 0 },
});
RCA.play = () => { if (RC.ctl && PB.ext?.paused) rcCmd({ c: 'play' }); return Promise.resolve(); };
RCA.pause = () => { if (RC.ctl && !PB.ext?.paused) rcCmd({ c: 'pause' }); };
const npAud = () => RC.ctl ? RCA : PB.a;
function rcQListHtml() {  // 手机的播放列表：点哪首手机就跳到哪首（顺序、随机、循环在手机上改）
  const L = RC.queue || [], cur = RC.st?.i;
  const head = `<div class="ql-head"><div><b>播放列表</b><span class="tiny">${L.length ? L.length + ' 首' : ''}</span></div></div>`;
  if (!L.length) return head + `<div class="ql-empty">${RC.st ? '手机的播放列表为空' : '等待手机播放'}</div>`;
  return head + `<div class="ql-rows">${L.map((x, k) => `<div class="ql-row ${k === cur ? 'on' : ''}" data-k="${k}" role="button" tabindex="0">${rowArt({}, k === cur, 36)}<div class="ql-main"><div class="ql-t">${k === cur ? '<span class="eq"><i></i><i></i><i></i></span>' : ''}${esc(x.title || '')}</div><div class="ql-s">${esc(x.sub || '')}</div></div></div>`).join('')}</div>`;
}
function rcQBind(box) { $$('.ql-row', box).forEach(r => r.onclick = () => { const k = +r.dataset.k; if (k !== RC.st?.i) rcCmd({ c: 'jump', v: k }); }); }
function rcLive() { return !!RC.st && RC.st.age < 15; }  // 手机 15 秒没报状态就当它断开了（锁屏后网页大约 2 秒才能动一次）
function rcSub() {  // 手机在普通空间里放电脑发过去的：名字是后台记着的（手机那边只有“电脑控制播放”）
  const p = RC.st;
  if (!p) return '等待手机播放';
  if (!rcLive()) return p.kerr ? '手机已休眠（暂停后没能保持连接）' : '手机已休眠或断开连接';
  return '手机' + (p.sub ? ' · ' + p.sub : '');
}
function rcMeta() {
  const p = RC.st || {}, title = p.title || '手机';
  return { title, sub: rcSub(), orb: p.orb || title, cover: p.cover || '', subsKey: p.subsKey || '' };
}
function rcBtn() {
  const b = $('#pb-rc'); if (!b) return;
  b.hidden = !rcPC();
  b.classList.toggle('on', RC.ctl);
  b.title = RC.ctl ? '停止控制手机' : '控制手机的播放'; b.setAttribute('aria-label', b.title);
}
/* 自动开启（2026-11-17 用户：手机在放的时候，电脑默认打开手机控制）：电脑在私密空间里、没在控制时，每 3 秒看一眼有没有手机在放
   （私密空间里的手机报了状态；普通空间的手机只让后台知道“有手机在放”，不报放的是什么），有就自动开启。
   电脑自己正在放、或者这一轮手动关掉过（手机停下 20 秒以后才算新的一轮）：不自动开。自动开的，手机停下 1 分钟就自动关掉 */
const rcPlaying = r => !!r && (r.near || (!!r.phone && r.phone.age < 15 && !r.phone.paused));
function rcPoll() {
  clearTimeout(RC.pollT);
  if (!rcPC()) return;
  if (!RC.ctl) {
    if (RC.parked && Date.now() - RC.parked > 30 * 60000) { RC.parked = 0; api('/api/rc/arm', { body: { on: false } }).catch(() => { }); }  // 停着的控制：30 分钟后真的关掉
    api('/api/rc/view' + (RC.parked ? '?ctl=1' : '')).then(r => {  // 停着的控制：顺便续上“开着”（手机上的内容不被清掉）
      if (RC.ctl || !rcPC()) return;
      if (!rcPlaying(r)) { RC.quiet = RC.quiet || Date.now(); if (Date.now() - RC.quiet > 20000) RC.noAuto = false; return; }
      RC.quiet = 0;
      if (RC.noAuto || (PB.a && !PB.a.paused) || MINI_OUT) return;
      rcStart(true);
    }).catch(() => { }).finally(() => { if (!RC.ctl && rcPC()) RC.pollT = setTimeout(rcPoll, document.hidden ? 8000 : 3000); });
    return;
  }
  api('/api/rc/view?ctl=1').then(r => {
    if (!RC.ctl) return;
    if (!r.armed) api('/api/rc/arm', { body: { on: true } }).catch(() => { });  // 后台重启过 / 太久没来问：重新开上
    if (rcPlaying(r)) RC.act = Date.now();
    else if (RC.auto && Date.now() - RC.act > 60000) return rcStop();  // 自动开的：手机停下 1 分钟就关掉
    RC.st = r.phone || null; RC.stAt = performance.now(); rcMirror(); rcSavePos(RC.st);
    if (RC.st && RC.st.qv !== RC.qvSeen) { RC.qvSeen = RC.st.qv; api('/api/rc/queue').then(q => { if (RC.ctl) { RC.queue = q.items || []; qPanelPaint(); } }).catch(() => { }); }  // 手机的播放列表变了
  }).catch(() => { }).finally(() => { if (RC.ctl) RC.pollT = setTimeout(rcPoll, 1000); });
}
const rcT = () => { const p = RC.st; if (!p) return 0; const t = p.t + (p.paused || !rcLive() ? 0 : (p.age + (performance.now() - RC.stAt) / 1000) * (p.rate || 1)); return p.d ? Math.min(p.d, t) : t; };
function rcMirror() {
  const p = RC.st, was = PB.ext?.paused;
  PB.ext = { t: rcT(), d: p?.d || 0, paused: !rcLive() || !!p?.paused };
  const m = rcMeta(), k = [m.title, p?.i, m.cover, m.sub, m.subsKey].join('|'), meta = k !== RC.mk; RC.mk = k;
  pbPaint(meta);
  if (meta) qPanelPaint();  // 换了一首：播放列表里的“正在放”跟着挪
  if (was !== PB.ext.paused) RCA.dispatchEvent(new Event(PB.ext.paused ? 'pause' : 'play'));
}
setInterval(() => { if (RC.ctl && PB.ext && !PB.ext.paused && !PB.scrub) { PB.ext.t = rcT(); pbPaint(); RCA.dispatchEvent(new Event('timeupdate')); } }, 250);  // 两次取状态之间进度条、字幕照常走
function rcStart(auto = false) {
  if (!rcPC()) return;
  RC.auto = auto; RC.act = Date.now(); RC.noAuto = false; RC.parked = 0;
  if (MINI_OUT === 'win') appReturn('close');
  for (const x of PB.all) { try { if (!x.paused) x.pause(); } catch { } }  // 电脑这边正在放的先停
  RC.ctl = true; RC.mk = ''; RC.st = null; RC.queue = []; RC.qvSeen = null;
  pbRegister(qAudio, rcMeta);
  PB.a = qAudio; qPanelClose(); try { spClose(); } catch { }
  rcMirror(); rcBtn();
  api('/api/rc/arm', { body: { on: true } }).then(rcPoll, e => { toast(e.message, true); rcStop(false); });
}
function rcStop(send = true, manual = false) {
  if (manual) { RC.noAuto = true; RC.quiet = 0; }  // 手动关掉：这一轮不再自动打开
  if (send) RC.parked = 0;
  if (!RC.ctl) return;
  RC.ctl = false; PB.ext = null; RC.mk = ''; RC.st = null; RC.queue = null; clearTimeout(RC.pollT);
  if (send && VAULT) api('/api/rc/arm', { body: { on: false } }).catch(() => { });  // 手机上电脑发过去的私密内容随之停掉
  const x = qCur();
  if (x && qAudio.currentSrc) pbRegister(qAudio, () => ({ title: x.title, sub: x.sub, orb: x.orb, cover: x.cover, subsKey: x.subsKey, video: x.video }));
  else { PB.a = null; $('#pb-title') && ($('#pb-title').textContent = '未在播放'); $('#pb-sub') && ($('#pb-sub').textContent = ''); $('#pb-art') && ($('#pb-art').innerHTML = ''); }
  pbPaint(true); rcBtn(); qPanelPaint();
  if (rcPC()) RC.pollT = setTimeout(rcPoll, 3000);  // 接着看有没有手机在放（自动开启）
}
addEventListener('pagehide', () => { if (RC.ctl) navigator.sendBeacon?.('/api/rc/arm', new Blob([JSON.stringify({ on: false })], { type: 'application/json' })); });  // 关掉 / 刷新页面：不留着开着的控制
function rcCmd(c) {  // c：{ c: 'next' } 这种，或者小窗口那一套的 { toggle } / { seek } / { seekBy } / { rate }
  const m = c.c ? c : c.toggle ? { c: 'toggle' } : c.seekBy != null ? { c: 'seekBy', v: c.seekBy } : c.seek != null ? { c: 'seek', v: c.seek } : c.rate != null ? { c: 'rate', v: c.rate } : null;
  if (!m) return true;
  const p = RC.st;
  if (p && rcLive()) {  // 先在这边显示出效果，不等手机下一次报状态
    const t = rcT();
    if (m.c === 'seek' || m.c === 'seekBy') Object.assign(p, { t: Math.max(0, m.c === 'seek' ? m.v : t + m.v), age: 0 });
    else if (m.c === 'toggle' || m.c === 'play' || m.c === 'pause') Object.assign(p, { t, age: 0, paused: m.c === 'toggle' ? !p.paused : m.c === 'pause' });
    RC.stAt = performance.now(); rcMirror();
    if (m.c === 'seek' || m.c === 'seekBy') RCA.dispatchEvent(new Event('seeked'));
  }
  api('/api/rc/cmd', { body: m }).catch(e => toast(e.message, true)).finally(() => { clearTimeout(RC.pollT); RC.pollT = setTimeout(rcPoll, 400); });
  return true;
}
function rcQueue(items, i) {  // 在电脑上点了一首 / 播放全部：交给手机（最多 500 首，点的那首前面留 100 首）；每首带上电脑记着的上次进度
  const pp = playPos(), s = Math.max(0, i - 100), list = items.slice(s, s + 500).map(x => ({ key: x.key, title: x.title, sub: x.sub, orb: x.orb, cover: x.cover, url: x.url, convUrl: x.convUrl, conv: x.conv, pos: x.pos, video: x.video, subsKey: x.subsKey,
    ...(x.pos && pp[x.pos] >= 15 ? { resume: pp[x.pos] } : {}) }));
  rcCmd({ c: 'queue', items: list, i: i - s });
}
/* 续播（2026-11-17 用户：手机在放时电脑换一首再换回来，不会接着放）：控制手机时，电脑每 5 秒把手机放到哪记进电脑自己的续播记录
   （和电脑自己放时同一份，私密空间里的），再点这一首时把进度带给手机（rcQueue）。播到最后 15 秒以内的，手机那边照旧从头放 */
let rcPosT = 0;
function rcSavePos(p) {
  if (!p || p.paused || !rcLive() || !p.key?.startsWith('lib:') || p.t < 15 || Date.now() - rcPosT < 5000) return;
  rcPosT = Date.now(); const m = playPos(); m[p.key.slice(4)] = Math.round(p.t); savePos(m);
}
/* 控制手机时电脑自己放了别的：手机先暂停，播放条回到电脑自己的；控制保持开着（手机上的内容、进度都留着，最长 30 分钟），再点手机图标接着放 */
function rcPark() {
  if (!RC.ctl) return;
  if (rcLive() && !RC.st.paused) api('/api/rc/cmd', { body: { c: 'pause' } }).catch(() => { });
  rcStop(false); RC.parked = Date.now();
}
/* ---- 页面里的小窗：拖动 / 改大小 ---- */
function miniDrag(ph, e) {
  const mini = MINI, zone = $('#dock-zone');
  const nearBar0 = (x, y) => { const b = $('#pbar').getBoundingClientRect(); return !document.body.classList.contains('pb-min') && x > b.left - 60 && x < b.right + 60 && y > b.top - 220 && y < b.bottom; };
  const nearBar = (x, y, dd = mdrag) => dd?.undock ? dd.sy - y < 50 && nearBar0(x, y) : nearBar0(x, y);  // 刚从底栏拖开的：拖回原来的高度附近才重新贴回去
  if (MINI_OUT && !mdrag?.out) return;
  if (ph === 'start') { const r = mini.getBoundingClientRect(); mdrag = { sx: e.clientX, sy: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top, moved: false, wasDock: mini.classList.contains('dock') }; return; }
  const d = mdrag; if (!d) return;
  if (ph === 'move') {
    if (d.out) {  // 已经弹出成独立小窗：继续跟着鼠标走，直到松手
      if (!d.raf) d.raf = requestAnimationFrame(() => { d.raf = 0; window.pywebview.api.mini_move(Math.round(d.mx), Math.round(d.my)).catch(() => { }); });
      d.mx = e.screenX - d.dx; d.my = e.screenY - d.dy; return;
    }
    if (!d.moved) {
      if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 6) return;
      d.moved = true; mini.classList.add('drag');
      if (d.wasDock) d.ox = (S.dock || {}).dx || 0;
    }
    // 鼠标拖出了窗口边缘：弹到窗口外
    if (e.clientX <= 0 || e.clientY <= 0 || e.clientX >= innerWidth - 1 || e.clientY >= innerHeight - 1) {
      if (IN_APP()) {
        d.out = true; zone?.classList.remove('show', 'hot'); mini.style.opacity = '0';
        d.mx = e.screenX - d.dx; d.my = e.screenY - d.dy;
        appPopOut(e, { x: d.mx, y: d.my, drag: true });  // 小窗口出现后由系统接着拖（跟手）
        return;
      }
      if (window.documentPictureInPicture && !d.tried) {
        d.tried = true; mdrag = null; mini.classList.remove('drag'); zone?.classList.remove('show', 'hot');
        pipOpen().catch(() => toast('松开鼠标后，点击小窗下方的“弹出”按钮也可弹出到窗口外'));
        return;
      }
    }
    if (d.wasDock && d.sy - e.clientY > 70) {  // 贴着底栏的视频往上拖开：变成悬浮小窗（画中画），继续跟着鼠标走
      const r = mini.getBoundingClientRect(), fx = d.dx / r.width, fy = d.dy / r.height;
      d.wasDock = false; d.undock = true; S.vidMode = 'float';
      mini.classList.remove('dock'); mini.removeAttribute('style'); miniUI?.aspect(); mini.style.width = miniSize() + 'px'; mini.classList.add('drag');
      d.dx = fx * mini.offsetWidth; d.dy = fy * mini.offsetHeight;
    }
    if (d.wasDock) {  // 贴着底栏：只能左右挪，不超出播放条的宽度
      const b = $('#pbar').getBoundingClientRect(), w = mini.offsetWidth;
      const half = Math.max(0, (b.width - w) / 2);
      S.dock = { ...(S.dock || {}), dx: Math.max(-half, Math.min(half, d.ox + e.clientX - d.sx)) };
      miniLayout(); return;
    }
    const x = Math.min(innerWidth - mini.offsetWidth - 8, Math.max(8, e.clientX - d.dx)), y = Math.min(innerHeight - mini.offsetHeight - 8, Math.max(8, e.clientY - d.dy));
    Object.assign(mini.style, { left: x + 'px', top: y + 'px', right: 'auto', bottom: 'auto' });
    if (zone) { const b = $('#pbar').getBoundingClientRect(); Object.assign(zone.style, { left: b.left + 'px', width: b.width + 'px', bottom: (innerHeight - b.top + 10) + 'px', height: Math.min(b.width * 9 / 16, innerHeight * .55) + 'px' }); zone.classList.add('show'); zone.classList.toggle('hot', nearBar(e.clientX, e.clientY)); }
    return;
  }
  // 松手
  mdrag = null; mini.classList.remove('drag'); zone?.classList.remove('show', 'hot');
  if (d.out) { mini.classList.remove('show'); mini.hidden = true; mini.style.opacity = ''; miniSync(); return; }
  if (!d.moved) return;
  if (d.wasDock) { persist(); return; }
  const toDock = e && e.clientX != null && nearBar(e.clientX, e.clientY, d);
  S.vidMode = toDock ? 'dock' : 'float'; persist();
  if (toDock) { mini.classList.add('dock'); miniReset(); miniLayout(); }
}
const ar0 = w => { const ar = miniAr(); return ar >= 1 ? w : w / ar; };  // 宽度 → 画面长边
function miniResize(c, ph, e) {  // 拖四个角：画面比例不变，对角固定不动
  const mini = MINI; if (MINI_OUT) return;
  if (ph === 'start') { const r = mini.getBoundingClientRect(); mrz = { r, sx: e.clientX, sy: e.clientY, ar: miniAr() }; return; }
  const z = mrz; if (!z) return;
  if (mini.classList.contains('dock')) {
    if (ph !== 'move') { mrz = null; persist(); return; }
    const { r, ar } = z, b = $('#pbar').getBoundingClientRect();
    const dx = (e.clientX - z.sx) * (c.includes('w') ? -1 : 1), dy = (e.clientY - z.sy) * (c.includes('n') ? -1 : 1);
    const w = Math.max(200, Math.min(innerWidth - 16, (b.top - 18) * ar, r.width + (Math.abs(dx) > Math.abs(dy * ar) ? dx : dy * ar)));
    const cx = c.includes('w') ? r.right - w / 2 : r.left + w / 2;  // 拖左边的角：右边不动；拖右边的角：左边不动
    S.dock = { ...(S.dock || {}), w, dx: cx - (b.left + b.width / 2) };
    miniLayout(); return;
  }
  if (ph === 'move') {
    const { r, ar } = z, dx = (e.clientX - z.sx) * (c.includes('w') ? -1 : 1), dy = (e.clientY - z.sy) * (c.includes('n') ? -1 : 1);
    const dw = Math.abs(dx) > Math.abs(dy * ar) ? dx : dy * ar;
    const w = Math.min(innerWidth * .9, (innerHeight * .9 - MINI_BAR) * ar, Math.max(ar >= 1 ? 240 : 170, r.width + dw)), h = w / ar + MINI_BAR;
    const left = c.includes('w') ? r.right - w : r.left, top = c.includes('n') ? r.bottom - h : r.top;
    Object.assign(mini.style, { width: w + 'px', left: Math.max(4, left) + 'px', top: Math.max(4, top) + 'px', right: 'auto', bottom: 'auto' });
    return;
  }
  mrz = null; S.miniW = Math.round(ar0(mini.offsetWidth)); persist();
}
function bindMini() {
  const mini = MINI; if (!mini) return;
  mini.innerHTML = MiniUI.html(['pop'], ['open', 'fold', 'x']);
  miniUI = MiniUI.bind(mini, qAudio, {
    cmd: (name, e) => {
      if (name === 'pop') { if (MINI_OUT === 'pip') pipRestore(); else miniPopOut(e); return; }
      pipRestore();  // 其他按钮：先从画中画窗口放回页面
      if (name === 'open' || name === 'dbl') npOpen();
      else if (name === 'fold') { mini._dismissed = true; miniSync(); }                   // 只收起画面，声音继续
      else if (name === 'x') { mini._dismissed = true; qAudio.pause(); miniSync(); }     // 关掉小窗 = 暂停（底栏保留，随时可以继续）
    },
    drag: miniDrag,
    resize: miniResize,
  });
  miniReset();
  /* 点过小窗（从播放条展开的或悬浮的）之后：空格 = 播放 / 暂停，← / → = 后退 / 前进 5 秒；点了页面别处就不再接管 */
  let foc = false;
  document.addEventListener('pointerdown', e => { foc = !!e.target.closest?.('#mini'); }, true);
  const mine = e => foc && !mini.hidden && !MINI_OUT && $('#np')?.hidden && PB.a === qAudio && !e.ctrlKey && !e.metaKey && !e.altKey
    && !e.target.closest?.('input, textarea, select, [contenteditable]') && !$('.modal-bg') && !ImageViewer.isOpen();
  addEventListener('keydown', e => {
    if (!mine(e)) return;
    const k = e.key;
    if (k === ' ') { e.preventDefault(); e.stopPropagation(); if (!e.repeat) qAudio.paused ? qAudio.play().catch(playErr) : qAudio.pause(); }
    else if (k === 'ArrowLeft' || k === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); keySeek(qAudio, Math.min((qAudio.duration || 1e9) - .05, Math.max(0, qAudio.currentTime + (k === 'ArrowLeft' ? -5 : 5)))); miniPaint(); pbPaint(); }
  }, true);
  addEventListener('keyup', e => { if (e.key === ' ' && mine(e)) { e.preventDefault(); e.stopPropagation(); } }, true);  // 焦点在小窗的按钮上时，空格别再“按一下”那个按钮
}
let fsFrom = null;
async function npFullscreen() {
  const np = $('#np');
  const de = document.documentElement, fsEl = document.fullscreenElement || document.webkitFullscreenElement;
  if (!de.requestFullscreen && !de.webkitRequestFullscreen) {  // iPhone 的 Safari 不支持网页全屏：视频交给系统自带的全屏播放器；音频用“页面内全屏”
    if (qAudio.classList.contains('is-video') && qAudio.webkitEnterFullscreen) { try { qAudio.webkitEnterFullscreen(); return; } catch { } }
    const on = !np.classList.contains('fs'); np.classList.toggle('fs', on); npTheater(); fitVideo(); npTabsPlace();
    setIcon($('#np-fs'), on ? 'fsExit' : 'fs'); return;
  }
  fsFrom = qAudio.getBoundingClientRect();
  try {
    if (fsEl) await (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    else await (de.requestFullscreen || de.webkitRequestFullscreen).call(de);  // iPad 的 Safari 只有带 webkit 前缀的
  } catch (e) { fsFrom = null; toast('无法全屏：' + e.message, true); }
}
document.addEventListener('webkitfullscreenchange', () => { if (!('onfullscreenchange' in document)) document.dispatchEvent(new Event('fullscreenchange')); });
/* 页面里的视频全屏（生视频大预览、详情等，播放页除外）：应用会把窗口也变成全屏、退出时再变回来。
   这期间背后的页面不跟着重排（以前退出全屏时缩略图、卡片先按全屏的大小排一遍，再排回来，看起来闪一下、重新排列）；
   窗口变回原来的大小后什么都不用动。
   2026-11-06 用户：放大 / 缩小动画怪，不要了；全屏和退出时应用不要闪。以前只挡住了脚本重排，页面本身（CSS）还会先按全屏窗口的大小排一遍再排回来：
   现在退出时窗口如果还是全屏那么大：先用一张盖满窗口的黑底画面停在视频最后一帧上（看起来就是视频晚一点点退出），
   等窗口变回原来的大小、背后排好了再拿掉 */
let FS_V = null, FS_UNTIL = 0, FS_WH = null;
const fsHold = window.fsHold = () => !!FS_V || performance.now() < FS_UNTIL;
addEventListener('resize', e => { if (fsHold()) e.stopImmediatePropagation(); }, true);  // 窗口大小变化：背后的页面先不管
const fsSame = wh => !!wh && Math.abs(innerWidth - wh[0]) < 3 && Math.abs(innerHeight - wh[1]) < 3;
function fsCover(v, wh) {  // 退出全屏后、窗口变回来之前：盖住背后的页面
  if (fsSame(wh)) return;
  const c = document.createElement('canvas'); c.className = 'fs-cover'; c.width = innerWidth; c.height = innerHeight;
  try { const g = c.getContext('2d'), a = v.videoWidth / v.videoHeight || 16 / 9, k = Math.min(c.width / (c.height * a), 1), w = c.width * k, h = w / a;
    g.fillStyle = '#000'; g.fillRect(0, 0, c.width, c.height); if (v.videoWidth) g.drawImage(v, (c.width - w) / 2, (c.height - h) / 2, w, h); } catch { }
  document.body.append(c);
  const t0 = performance.now();  // 每帧看一次窗口大小（resize 事件这时被上面挡住了）；变回来后再等两帧让背后排好；最多盖 0.9 秒
  const chk = () => { if (fsSame(wh)) requestAnimationFrame(() => requestAnimationFrame(() => c.remove())); else if (performance.now() - t0 > 900) c.remove(); else requestAnimationFrame(chk); };
  requestAnimationFrame(chk);
}
document.addEventListener('fullscreenchange', () => {
  const el = document.fullscreenElement || document.webkitFullscreenElement;
  if (el && el.tagName === 'VIDEO') {
    FS_V = el; FS_UNTIL = 0; if (!FS_WH) FS_WH = [innerWidth, innerHeight];
  } else if (!el && FS_V) {
    const v = FS_V; FS_V = null; FS_UNTIL = performance.now() + 900;
    if (document.body.classList.contains('in-app')) fsCover(v, FS_WH);
    setTimeout(() => { FS_UNTIL = 0; const w = FS_WH; FS_WH = null; if (w && !fsSame(w)) dispatchEvent(new Event('resize')); }, 920);  // 窗口没回到原来的大小：再按现在的大小排一次
  }
});
document.addEventListener('fullscreenchange', () => {
  window.pywebview?.api?.fullscreen?.(!!document.fullscreenElement).catch(() => { });  // 应用：窗口本身也全屏 / 退出全屏
  // 应用：马上去掉给标题栏留的空位，窗口变成全屏大小后再按新大小重排一次视频（以前偶尔四周会留一圈边）
  if (document.body.classList.contains('in-app')) {
    document.body.classList.toggle('app-fs', !!document.fullscreenElement);
    [120, 350, 700].forEach(ms => setTimeout(() => { fitVideo(); npTabsPlace(); }, ms));
  }
  const np = $('#np'); if (!np) return;
  const from = fsFrom; fsFrom = null;
  const apply = () => { np.classList.toggle('fs', document.fullscreenElement === document.documentElement && !np.hidden); npTheater(); };
  // 全屏前后窗口尺寸变了：视频从原来的位置平滑放大 / 缩小到新位置
  if (from && from.width && $('#np-stage').classList.contains('video') && !reduceMotion) {
    const side = $('#np-right'), hadTheater = np.classList.contains('theater');
    apply(); fitVideo(); npTabsPlace();
    const b = qAudio.getBoundingClientRect();
    qAudio.animate([{ transform: `translate(${from.left - b.left}px, ${from.top - b.top}px) scale(${from.width / b.width}, ${from.height / b.height})`, transformOrigin: '0 0', opacity: .85 },
      { transform: 'none', transformOrigin: '0 0', opacity: 1 }], { duration: 480, easing: 'cubic-bezier(.2, .8, .2, 1)' });
    if (!hadTheater && np.classList.contains('theater')) side.getAnimations().forEach(x => x.cancel());
  } else apply();
  setIcon($('#np-fs'), document.fullscreenElement ? 'fsExit' : 'fs');
});
/* 视频按框的大小等比放到最大（保留圆角阴影；比原始分辨率大时也放大） */
function fitVideo() {
  const st = $('#np-stage'); if (!st || !st.classList.contains('video') || !qAudio.videoWidth || qAudio.parentElement !== st) { qAudio.style.width = qAudio.style.height = ''; return; }
  const cs = getComputedStyle(st), w = st.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), h = st.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  const k = Math.min(w / qAudio.videoWidth, h / qAudio.videoHeight);
  if (k > 0) { qAudio.style.width = Math.floor(qAudio.videoWidth * k) + 'px'; qAudio.style.height = Math.floor(qAudio.videoHeight * k) + 'px'; }
  const fb = $('#np-fs2');
  if (fb) { fb.style.left = (qAudio.offsetLeft + qAudio.offsetWidth - 52) + 'px'; fb.style.top = (qAudio.offsetTop + qAudio.offsetHeight - 52) + 'px'; }  // 画面右下角
}
qAudio.addEventListener('loadedmetadata', fitVideo);
addEventListener('resize', fitVideo);
/* 环境光（2026-11-18 用户选的方案 B，设计稿 docs/设计稿/视频画面方案_1118.html；照 YouTube 的“氛围模式”）：
   视频不开侧栏 / 全屏时画面铺满，比例对不上的地方不是黑的，而是画面自己的颜色放大、模糊后铺开。
   每 2 秒（拖动后立刻）从视频取一帧画到 48 像素宽的小画布上，两张画布交替淡入淡出；暂停且没动就不重画（不和视频抢显卡） */
const AMB = { el: null, cv: [], k: 0, lt: -1 };
const ambOn = () => { const np = $('#np'); return !!np && !np.hidden && np.classList.contains('is-video') && np.classList.contains('theater') && !MOB() && qAudio.parentElement?.id === 'np-stage'; };
function ambTick(force) {
  const on = ambOn(); if (AMB.el) AMB.el.hidden = !on; if (!on) return;
  if (!AMB.el) { const w = document.createElement('div'); w.className = 'np-amb'; w.setAttribute('aria-hidden', 'true'); w.innerHTML = '<canvas></canvas><canvas></canvas>'; $('#np-bg').after(w); AMB.el = w; AMB.cv = [...w.children]; }
  const v = qAudio; if (v.readyState < 2 || !v.videoWidth) return;
  if (!force && Math.abs(v.currentTime - AMB.lt) < .05) return;
  const c = AMB.cv[AMB.k ^ 1], W = 48, H = Math.max(8, Math.round(W * v.videoHeight / v.videoWidth));
  if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
  try { c.getContext('2d').drawImage(v, 0, 0, W, H); } catch { return; }
  AMB.lt = v.currentTime; AMB.k ^= 1; AMB.cv.forEach((x, i) => x.classList.toggle('on', i === AMB.k));
}
setInterval(() => { if (!document.hidden) ambTick(); }, 2000);
['seeked', 'loadeddata'].forEach(t => qAudio.addEventListener(t, () => ambTick(true)));
/* 页签（字幕 / 播放列表）在视频模式下对齐到右侧字幕栏的左边 */
/* 电脑上的全屏播放页按钮（2026-11-18 用户选的方案 Y，设计稿 docs/设计稿/视频播放页方案_1118_第三轮.html；照 QQ 音乐 / YouTube）：
   - 右上角一组（#np-wg）：视频 = 侧栏开关 · 迷你播放器，音频 = 迷你播放器 ·（不是底部通栏时 ⋯）· 全屏；应用里右边紧挨着一直显示的 最小化 / 最大化 / 关闭；
   - 视频右下角（#np-vr）：音量 · 画面字幕 · 全屏 · ⋯；上面整条进度条；随机 / 循环、音效、画中画、PotPlayer、隐藏控制条收进 ⋯；
   - 音频底部通栏：⋯ 放在右下角最右边，音效收进 ⋯。
   手机 / 窄窗口（≤760）全部放回原处（各自的位置用注释节点记着） */
function npYPlace() {
  const np = $('#np'), wg = $('#np-wg'), vr = $('#np-vr'), dock = $('#np-dock'); if (!np || !wg || !vr) return;
  const D = !MOB(), vid = np.classList.contains('is-video'), full = np.classList.contains('bar-full');
  const el = id => { const e = $('#' + id); if (e && !e._home) { e._home = document.createComment(id); e.before(e._home); } return e; };
  const mini = el('np-mini'); if (mini) mini.hidden = !!REMOTE || !(cpApp() || window.documentPictureInPicture);
  const plan = new Map();  // 元素 → 放进哪个盒子（没写的放回原处）
  const into = (box, ids) => ids.forEach(id => { const e = el(id); if (e) plan.set(e, box); });
  if (D && vid) { into(wg, ['np-mini']); into(vr, ['np-vol', 'np-fx', 'np-more2', 'np-theater', 'np-fs']); }  // 11-18 第三次：侧栏开关也放下面（全屏前面）  // 11-18 第二次：音量 · 音轨（音效与声道）· 设置 · 全屏（全屏在最右下角，画面字幕进设置）
  else if (D) { into(wg, full ? ['np-mini', 'np-fs'] : ['np-mini', 'np-more2', 'np-fs']); if (full && dock) into(dock, ['np-vol', 'np-more2']); }
  for (const box of [wg, vr]) {  // 按顺序放；已经是这个顺序就不动（免得每次调整窗口都改一遍 DOM）
    const want = [...plan].filter(([, b]) => b === box).map(([e]) => e);
    if (![...box.children].every((c, k) => c === want[k]) || box.children.length !== want.length) want.forEach(e => box.append(e));
  }
  if (dock && plan.get($('#np-vol')) === dock && dock.firstElementChild !== $('#np-vol')) dock.prepend($('#np-vol'));
  if (dock && plan.get($('#np-more2')) === dock && dock.lastElementChild !== $('#np-more2')) dock.append($('#np-more2'));
  for (const id of ['np-theater', 'np-mini', 'np-fs', 'np-more2', 'np-capbtn', 'np-vol', 'np-fx']) {
    const e = el(id); if (e && !plan.has(e) && e._home.nextSibling !== e) e._home.after(e);
  }
  { const m = $('#np-more2'); if (m) {  // 视频：⋯ 换成齿轮“设置”（用户 11-18）；音频还是 ⋯
    if (m._ic == null) { m._ic = m.innerHTML; m._tt = m.title; m._tip = m.getAttribute('data-tip'); }
    const gear = D && vid; if (m.classList.contains('as-gear') !== gear) { m.classList.toggle('as-gear', gear); m.innerHTML = gear ? ($('#side-gear svg')?.outerHTML.replace('class="ri"', 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"') || m._ic) : m._ic; m.title = gear ? '设置' : m._tt; m.setAttribute('aria-label', gear ? '设置' : '更多'); if (gear || m._tip == null) m.removeAttribute('data-tip'); else m.setAttribute('data-tip', m._tip); }
  } }
  const tb = $('.tb'); np.style.setProperty('--tbw', (document.body.classList.contains('in-app') && tb && tb.offsetWidth ? tb.offsetWidth : 0) + 'px');
  np.style.setProperty('--wgw', (D ? wg.offsetWidth : 0) + 'px');  // 顶栏右边给这组让出位置（音频的“字幕 / 播放列表”页签在它左边）
}
function npTabsPlace() {
  npYPlace(); ambTick(true);
  const np = $('#np'), tabs = $('.np-tabs', np), tools = $('.np-tools', np), th = $('#np-theater'), topBar = $('.np-top', np);
  if (!np || !tabs || !tools || !th) return;
  const split = np.classList.contains('is-video') && !np.classList.contains('theater');
  np.classList.toggle('split', split);
  const own = !MOB();  // 电脑：侧栏开关在右上角那组里（npYPlace），这里只摆页签
  if (!split) {  // 音频 / 收起字幕栏：右上角一排（画面字幕、画中画、字幕栏、全屏）
    tabs.style.left = ''; tools.style.right = ''; th.style.left = '';
    if (!own && th.parentElement !== tools) { const fs = $('#np-fs'); if (fs?.parentElement === tools) tools.insertBefore(th, fs); else tools.append(th); }
    return;
  }
  // 用 offsetLeft（只看布局，不受 transform 动画影响）；getBoundingClientRect 会把切换动画中的位移也算进去
  const offX = el => { let x = 0; for (let e = el; e && e !== np; e = e.offsetParent) x += e.offsetLeft; return x; };
  const sideEl = $('#np-right'), leftEl = $('.np-left', np);
  const sideL = offX(sideEl), sideR = sideL + sideEl.offsetWidth, leftR = offX(leftEl) + leftEl.offsetWidth, topL = offX(topBar);
  tabs.style.left = (sideL - topL) + 'px';                            // 页签：字幕栏左边
  if (own) { th.style.left = ''; tools.style.right = (topL + topBar.offsetWidth - leftR) + 'px'; return; }
  if (th.parentElement !== topBar) topBar.appendChild(th);
  const winBtns = 0;  // 播放页里窗口按钮是收起的（悬停才出现），不用给它留位置
  th.style.left = (sideR - topL - th.offsetWidth - winBtns) + 'px';             // 隐藏字幕栏：字幕栏右边
  tools.style.right = (topL + topBar.offsetWidth - leftR) + 'px';     // 画面字幕 / 画中画 / 全屏：视频那一栏右边
}
addEventListener('resize', npTabsPlace);
/* FLIP：先记下视频原来的位置大小，换好布局后再从原位置平滑过渡到新位置（不会先跳一下再放大） */
function flipVideo(change) {
  const st = $('#np-stage');
  if (!st?.classList.contains('video') || reduceMotion) { change(); fitVideo(); npTabsPlace(); return; }
  const a = qAudio.getBoundingClientRect();
  change(); fitVideo(); npTabsPlace();
  const b = qAudio.getBoundingClientRect();
  if (!a.width || !b.width) return;
  qAudio.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`, transformOrigin: '0 0' },
    { transform: 'none', transformOrigin: '0 0' }], { duration: 520, easing: 'cubic-bezier(.2, .8, .2, 1)' });
}
/* 视频铺满（隐藏侧边栏）只在电脑上有：S.ui 是几台设备共用的，电脑上开了，手机（≤760）上以前也跟着变成铺满的排法——
   标题、进度条、按钮都改成绝对定位叠在一起（11-21 用户 iPhone 截图：按钮压在进度条上） */
const npTheaterOn = np => !MOB() && (np.classList.contains('fs') ? !S.ui?.fsPanel : !!S.ui?.theater);
function npTheater() {
  const np = $('#np'); if (!np) return;
  const on = npTheaterOn(np);  // 真全屏默认只看视频；窗口里默认显示字幕栏
  if (np.classList.contains('theater') === on) { fitVideo(); npTabsPlace(); }
  else {
    const side = $('#np-right');
    if (on && !reduceMotion) side.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(24px)' }], { duration: 200, easing: 'ease-in' });
    flipVideo(() => np.classList.toggle('theater', on));
    if (!on && !reduceMotion) side.animate([{ opacity: 0, transform: 'translateX(24px)' }, { opacity: 1, transform: 'none' }], { duration: 380, delay: 120, easing: 'cubic-bezier(.2, .8, .2, 1)', fill: 'backwards' });
  }
  $('#np-theater')?.classList.toggle('on', on);
  if ($('#np-theater')) $('#np-theater').title = on ? '显示侧边栏' : '隐藏侧边栏（视频铺满）';
}
/* 状态栏颜色：主屏幕 App 用不透明的状态栏（不用 black-translucent），状态栏的颜色 = 页面的 theme-color。
   全屏播放页打开时改成它最上面的颜色，关掉时改回页面的颜色（随时改都会生效）。
   做法来自 andrewck24/volleybro #427（iOS 27 真机验证：每个页面声明自己的颜色，客户端切换时改写 theme-color）；
   WebKit bug 317153 里的回复：去掉 black-translucent，状态栏会自动和网页同色 */
function sbFlash() {
  const m = $('meta[name="theme-color"]'), np = $('#np'); if (!m || !np) return;
  if (!m.dataset.page) m.dataset.page = m.content;
  const open = !np.hidden && np.classList.contains('show');
  const c = open ? getComputedStyle(np).getPropertyValue('--np-top').trim() || '#111' : m.dataset.page;
  m.content = c; document.documentElement.style.backgroundColor = open ? c : '';
}
/* 手机上的全屏播放页有三种样子（参照 Apple Music）：封面（大封面）/ 字幕 / 播放列表（封面和标题缩到左上角，中间给字幕或列表）。电脑上不变（右边一栏 + 页签） */
NP.mv = ['cover', 'subs', 'queue'].includes(S.ui?.npView) ? S.ui.npView : 'cover';
function npViewPaint() {
  const np = $('#np'); if (!np) return;
  const m = MOB();
  ['cover', 'subs', 'queue'].forEach(k => np.classList.toggle('mv-' + k, m && NP.mv === k));
  $$('#np-dock [data-mv]').forEach(b => { const on = NP.mv === b.dataset.mv; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
}
// 手机全屏播放的播放 / 暂停字形（参照 SF Symbols 的 play.fill / pause.fill：圆角、实心）
const NP_GLYPH = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7.9 3.7C6.9 3.1 5.7 3.8 5.7 5v14c0 1.2 1.2 1.9 2.2 1.3l11.4-7c1-.6 1-2 0-2.6z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="5.3" y="3.8" width="4.7" height="16.4" rx="1.4"/><rect x="14" y="3.8" width="4.7" height="16.4" rx="1.4"/></svg>',
};
function npSetView(v) {
  if (v === NP.mv) v = 'cover';  // 再点一下同一个按钮：回到封面
  const np = $('#np'), els = ['#np-stage', '.np-meta', '.np-prog', '.np-ctl'].map(x => $(x, np));
  const anim = MOB() && !reduceMotion, r0 = anim ? els.map(e => e?.getBoundingClientRect()) : [];
  NP.mv = v; S.ui = { ...(S.ui || {}), npView: v }; persist();
  if (v !== 'cover' && NP.tab !== v) { NP.tab = v; NP.key = null; }
  npViewPaint(); npPaint(true);
  if (!anim) return;
  // 先记下原来的位置，换好布局后从原位置平滑移到新位置；封面同时缩放（只动这一个元素，不会出现两个）
  els.forEach((e, n) => {
    const a = r0[n], b = e?.getBoundingClientRect(); if (!a || !b || !b.width || !a.width) return;
    const dx = a.left - b.left, dy = a.top - b.top, k = n === 0 && !np.classList.contains('is-video') ? a.width / b.width : 1;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(k - 1) < .01) return;
    e.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${k})`, transformOrigin: '0 0' }, { transform: 'none', transformOrigin: '0 0' }], { duration: 420, easing: 'cubic-bezier(.2, .8, .2, 1)' });
  });
  if (v !== 'cover') $('#np-right').animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { duration: 340, delay: 90, easing: 'cubic-bezier(.2, .8, .2, 1)', fill: 'backwards' });
}
addEventListener('resize', () => npViewPaint());
function npMore(a, top) {
  if (top) {  // 右上角的 ⋯（2026-11-18 用户：换肤这些设置放右上角；音效也在这里，免得和底下的按钮重复）：用菜单，字幕的操作也在里面
    const np = $('#np'), vid = np.classList.contains('is-video');
    const ext = EXT_OK && !VAULT && !RC.ctl && (vid ? !!$('#np-ext') : PB.a === qAudio && !!qCur()?.subsKey);
    const ic = sel => $(sel + ' svg')?.outerHTML || '';
    const items = vid ? [{ label: '外观…', icon: window.NPL?.SHIRT || '', on: () => window.NPL?.open() }, { label: '画面字幕', icon: ic('#np-capbtn'), checked: S.ui?.cap !== false, on: () => $('#np-capbtn')?.click() }] : [{ label: '外观…', icon: window.NPL?.SHIRT || '', on: () => window.NPL?.open() }, { label: '音效与声道…', icon: ICON.sliders || CTX_IC.open || '', on: () => spToggle() }];
    if (vid && $('#np-pip')) items.push({ label: '画中画', icon: ic('#np-pip'), on: () => $('#np-pip').click() });
    if (ext) items.push({ label: '用 PotPlayer 打开', icon: EXT_ICON, on: () => openExternal() });
    if (vid) {  // 方案 Y（2026-11-18）：视频右下角只留 音量 · 画面字幕 · 全屏 · ⋯，随机 / 循环 / 隐藏控制条在这里
      const sh = $('#np-shuffle'), rp = $('#np-repeat'), q = [];
      if (sh && !sh.disabled) q.push({ label: '随机播放', icon: ic('#np-shuffle'), checked: !!S.qmode?.shuffle, on: () => sh.click() });
      if (rp && !rp.disabled) q.push({ label: S.qmode?.repeat === 'one' ? '单曲循环' : '循环', icon: ic('#np-repeat'), checked: S.qmode?.repeat !== 'off', on: () => rp.click() });
      if (q.length) items.push('-', ...q);
      if (np.classList.contains('theater')) items.push({ label: '隐藏控制条', icon: ic('#np-hide'), on: () => $('#np-hide')?.click() });
    }
    if (mkKey()) { items.push('-', { label: '添加书签', icon: MK_IC, hint: 'B', on: mkAdd }); const mm = mkMenu(); if (mm) items.push(mm); }
    const sa = npSubsActions(a); if (sa.length) items.push('-', { label: '字幕', icon: $('#np-dock [data-mv="subs"] svg')?.outerHTML || '', sub: sa });
    return ctxMenu({ anchor: a }, items);
  }  // 标题旁边的“更多”：外观（样式、背景颜色、封面；以前的“背景 / 封面”两行并进去了，见 npstyle.js）
  // 2026-11-16 用户（手机）：字幕的“逐行 / 段落 / 全文”放到这里（字幕上面那组藏起来）。只在手机、有字幕时
  const smOn = document.documentElement.classList.contains('ph') && $('#np-right [data-mode]'), smCur = smOn ? $('#np-right [data-mode] .on')?.dataset.m || 'line' : '';
  const SM = [['line', '逐行'], ['para', '段落'], ['full', '全文']];
  // 音频：用 PotPlayer 打开（视频在右上角有按钮）。只在电脑上装了 PotPlayer、不在私密空间、放的是播放列表里的文件、不是控制手机时
  const ext = EXT_OK && !VAULT && !RC.ctl && !$('#np').classList.contains('is-video') && PB.a === qAudio && !!qCur()?.subsKey;
  const subRow = smOn ? `<div class="gp-row"><span class="gp-l">字幕<em id="npm-sm-n">${SM.find(x => x[0] === smCur)?.[1] || ''}</em></span><div class="seg gp-seg" id="npm-sm">${SM.map(([v, n]) => `<button type="button" data-sm="${v}" class="${v === smCur ? 'on' : ''}">${n}</button>`).join('')}</div></div>` : '';
  popover(a, `<div class="gear-pop np-more-pop"><div class="gp-list">
      <button type="button" class="gp-row npm-look">${window.NPL?.SHIRT || ''}<span class="gp-l">外观</span></button>
      ${ext ? `<button type="button" class="gp-row npm-look npm-ext" data-tip="交给 PotPlayer 从当前位置接着放：可在 PotPlayer 里设成独占输出，按文件原本的采样率（如 192 kHz）播放">${EXT_ICON}<span class="gp-l">用 PotPlayer 打开</span></button>` : ''}
      ${NP.subsTarget && !$('#np').classList.contains('is-video') ? `<button type="button" class="gp-row npm-look npm-subload">${CTX_IC.open || ''}<span class="gp-l">载入字幕 / 歌词</span></button>` : ''}
      ${subRow}
      ${mkKey() ? `<button type="button" class="gp-row npm-look npm-mkadd">${MK_IC}<span class="gp-l">添加书签</span></button>${mkList().map(t => `<div class="gp-row npm-mk"><button type="button" class="npm-mkgo" data-t="${t}">${MK_IC}<span class="gp-l">${fmtT(t)}</span></button><button type="button" class="npm-mkdel" data-t="${t}" aria-label="删除书签">${ICON.x}</button></div>`).join('')}` : ''}
    </div></div>`, pop => {
    { const ma = $('.npm-mkadd', pop); if (ma) ma.onclick = () => { pop.close?.(true); mkAdd(); }; }
    $$('.npm-mkgo', pop).forEach(b => b.onclick = () => { pop.close?.(true); mkGo(+b.dataset.t); });
    $$('.npm-mkdel', pop).forEach(b => b.onclick = () => { mkDel(+b.dataset.t); b.closest('.npm-mk').remove(); });
    $('.npm-look', pop).onclick = () => { pop.close?.(true); window.NPL?.open(); };
    const sl = $('.npm-subload', pop); if (sl) sl.onclick = () => { pop.close?.(true); npSubsPick(); };
    const e = $('.npm-ext', pop); if (e) e.onclick = () => { pop.close?.(true); openExternal(); };
    // 字幕排版：点了就去点字幕上面那组（手机上那组藏起来了）
    $$('#npm-sm button', pop).forEach(b => b.onclick = () => { $(`#np-right [data-mode] [data-m="${b.dataset.sm}"]`)?.click(); $$('#npm-sm button', pop).forEach(y => y.classList.toggle('on', y === b)); $('#npm-sm-n', pop).textContent = b.textContent; });
  }, { width: 220 });
}
/* ================= 书签（2026-11-18 用户：音视频都能记住某个进度，不要太显眼） =================
   照 PotPlayer 的书签 / 视频网站进度条上的章节点：进度条上一个个小点（移上去变大、显示时间；点一下跳过去，右键删除）；
   按 B 添加；全屏播放页右上角 ⋯ 里有“添加书签”和“书签”列表（手机在 ⋯ 里）。按文件记，存在各空间自己的设置里（S.ui.marks） */
const mkKey = () => {
  const a = PB.a; if (!a) return null;
  if (a === qAudio) return qCur()?.key || null;
  const u = a.currentSrc || a.src; if (!u || u.startsWith('blob:')) return null;
  try { return 'url:' + decodeURIComponent(new URL(u, location.href).pathname); } catch { return null; }
};
const mkList = () => { const k = mkKey(); return (k && S.ui?.marks?.[k]) || []; };
const mkNow = () => extOn() ? PB.ext.t || 0 : PB.a?.currentTime || 0;
function mkSave(list) {
  const k = mkKey(); if (!k) return;
  const m = { ...(S.ui?.marks || {}) }; if (list.length) m[k] = list; else delete m[k];
  S.ui = { ...(S.ui || {}), marks: m }; persist(); mkPaint(true);
}
function mkAdd() {
  if (!PB.a) return; if (!mkKey()) return toast('此项不能添加书签', true);
  const t = Math.round(mkNow() * 10) / 10, L = mkList();
  if (L.some(x => Math.abs(x - t) < 1)) return toast('这里已有书签');
  mkSave([...L, t].sort((x, y) => x - y)); toast('已添加书签 ' + fmtT(t));
}
function mkGo(t) { const a = PB.a; if (!a) return; if (extOn()) { PB.ext.t = t; extCmd({ seek: t }); } else a.currentTime = t; pbPaint(); }
const mkDel = t => mkSave(mkList().filter(x => x !== t));
function mkPaint(force) {
  const a = PB.a, d = a ? (extOn() ? PB.ext.d : pbDur(a)) || 0 : 0, L = d ? mkList() : [], sig = `${mkKey()}|${Math.round(d)}|${L.join(',')}`;
  ['#pb-track', '#np-track'].forEach(sel => {
    const tr = $(sel); if (!tr || (!force && tr._mk === sig)) return; tr._mk = sig;
    let box = $('.mk-box', tr); if (!L.length) return box?.remove();
    if (!box) { box = document.createElement('div'); box.className = 'mk-box'; tr.append(box); }
    box.innerHTML = L.map(t => `<i class="mk" data-mk="${t}" style="left:${Math.min(100, t / d * 100).toFixed(3)}%" data-tip="书签 ${fmtT(t)}"></i>`).join('');
  });
}
// 进度条上的小点：点一下跳过去（不当成拖进度），右键删除
document.addEventListener('pointerdown', e => { const m = e.target.closest?.('.mk-box .mk'); if (!m || e.button) return; e.stopPropagation(); e.preventDefault(); mkGo(+m.dataset.mk); }, true);
document.addEventListener('contextmenu', e => {
  const m = e.target.closest?.('.mk-box .mk'); if (!m) return; const t = +m.dataset.mk;
  ctxMenu(e, [{ label: '跳到 ' + fmtT(t), on: () => mkGo(t) }, { label: '删除书签', danger: true, on: () => mkDel(t) }]);
}, true);
// B：在当前位置加书签（输入框里、弹窗开着、生图的涂抹工具用 B 时不算）
document.addEventListener('keydown', e => {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.repeat || e.key.toLowerCase() !== 'b' || !PB.a) return;
  if (e.target.closest?.('input, textarea, select, [contenteditable]') || $('.modal-bg, #ig-pen:not([hidden])')) return;
  e.preventDefault(); mkAdd();
});
// 菜单里的“书签”：每个书签一行（点了跳过去），最后“全部删除”
const mkMenu = () => { const L = mkList(); return L.length ? { label: `书签（${L.length}）`, icon: MK_IC, sub: [...L.map(t => ({ label: fmtT(t), on: () => mkGo(t) })), '-', { label: '全部删除', danger: true, on: () => mkSave([]) }] } : null; };
const MK_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M7 4h10v16l-5-3.6L7 20z"/></svg>';
/* 展开 / 收起全屏播放页（2026-11-17 用户：照 Apple Music——从播放条放大到全屏，收起时缩回播放条）。
   电脑、音频、没开“减少动态效果”时：整页从播放条的位置展开（clip-path），封面从播放条上的小封面飞到大封面的位置，其余内容稍后淡入；收起反过来。
   其他情况（手机有自己的下拉手势、视频、全屏模式）照旧淡入淡出 */
const NP_EASE = 'cubic-bezier(.32, .72, 0, 1)', NP_MORPH_MS = 460;
function npMorphFrom() {  // 播放条（收起成小圆钮时就是小圆钮）和它上面的小封面
  const bar = $('#pbar'), fab = $('#pb-fab'), vis = e => e && !e.hidden && e.getClientRects().length && e.getBoundingClientRect().width > 4;
  if (vis(bar) && !document.body.classList.contains('pb-min')) { const a = $('#pb-art'); return { box: bar.getBoundingClientRect(), art: vis(a) ? a.getBoundingClientRect() : null, r: 18 }; }
  if (vis(fab)) { const r = fab.getBoundingClientRect(); return { box: r, art: r, r: r.height / 2 }; }
  return null;
}
function npMorphOk(np) { return !reduceMotion && !document.documentElement.classList.contains('ph') && !np.classList.contains('is-video') && !document.fullscreenElement && !!PB.a; }
function npMorph(np, open, from, done) {
  np._morph?.forEach(a => a.cancel());  // 上一段（展开到一半就收起 / 反过来）先收掉，不留 fill 的残影
  const W = innerWidth, H = innerHeight, b = from.box;
  const clip = `inset(${b.top}px ${Math.max(0, W - b.right)}px ${Math.max(0, H - b.bottom)}px ${b.left}px round ${from.r}px)`, full = 'inset(0px 0px 0px 0px round 0px)';
  const opt = { duration: NP_MORPH_MS, easing: NP_EASE, fill: 'both' }, anims = [np.animate({ clipPath: open ? [clip, full] : [full, clip] }, opt)];
  const cov = $('#np-art > *', np);
  if (cov && from.art) {  // 封面：以中心为原点，从小封面的位置 / 大小飞过去（结束时回到它自己的样子，暂停时本来就缩小一点）
    const c = cov.getBoundingClientRect(), end = getComputedStyle(cov).transform, k = c.width / (cov.offsetWidth || c.width);
    const sc = from.art.width / (cov.offsetWidth || c.width), dx = from.art.left + from.art.width / 2 - (c.left + c.width / 2), dy = from.art.top + from.art.height / 2 - (c.top + c.height / 2);
    const tf = `translate(${dx}px, ${dy}px) scale(${sc})`, base = end === 'none' ? `scale(${k})` : end;
    anims.push(cov.animate({ transform: open ? [tf, base] : [base, tf], transformOrigin: ['50% 50%', '50% 50%'] }, opt));
  }
  const rest = [...np.querySelectorAll(':scope > :not(.np-body):not(#np-bg):not(.npl-bg), .np-body > :not(.np-left), .np-left > :not(.np-stage)')];
  rest.forEach(e => anims.push(e.animate({ opacity: open ? [0, 1] : [1, 0] }, open ? { duration: 260, delay: 160, easing: 'ease-out', fill: 'both' } : { duration: 160, easing: 'ease-in', fill: 'both' })));
  np._morph = anims;
  Promise.all(anims.map(a => a.finished)).catch(() => { }).then(() => { if (np._morph !== anims) return; np._morph = null; anims.forEach(a => a.cancel()); done?.(); });
}
function npOpen() {
  if (MINI_OUT === 'win') { appReturn('back').then(npOpen); return; }  // 先把应用外的小窗口收回来
  pipRestore();
  const np = $('#np'), from = npMorphFrom(); np.hidden = false; np._morph?.forEach(a => a.cancel()); np._morph = null; np._closing = false;
  const morph = from && npMorphOk(np);
  if (morph) { np.style.transition = 'none'; np.classList.add('show'); } else { np.style.transition = ''; void np.offsetWidth; np.classList.add('show'); }  // 先排版一次再加 show，过渡动画才会播放
  document.body.classList.add('np-open'); qPanelClose();
  NP.key = null; npViewPaint(); npPaint(true); sbFlash();
  if (morph && npMorphOk(np)) npMorph(np, true, from, () => { np.style.transition = ''; });
  else np.style.transition = '';
  const mini = MINI; if (mini) mini._dismissed = false;
}
function npClose(instant) {
  const np = $('#np'); if (!np || np.hidden) return;
  if (document.fullscreenElement === document.documentElement) document.exitFullscreen().catch(() => { });
  if (!instant && !np._closing && npMorphOk(np)) {  // 先缩回播放条，再收起
    const from = npMorphFrom();  // 播放条在播放页打开时只是透明，位置照样量得到
    if (from) { np._closing = true; np.style.transition = 'none'; npMorph(np, false, from, () => { np._closing = false; npClose(true); np.style.transition = ''; }); return; }
  }
  np._morph?.forEach(a => a.cancel()); np._morph = null; np._closing = false;
  np.classList.remove('show'); document.body.classList.remove('np-open'); sbFlash();
  const fin = () => { if (!np.classList.contains('show')) { np.hidden = true; miniSync(); sbFlash(); } };
  if (instant) fin(); else setTimeout(fin, 320);
}
function npPaint(full) {
  const np = $('#np'); if (!np || np.hidden) return;
  const a = PB.a, m = PB.meta || {};
  // 音频 ↔ 视频（2026-11-18 用户：从播放列表切换时闪一下就换了，两边样子差得多，很突兀）：用浏览器自带的 View Transitions
  // 封面那块变形成视频画面，标题、进度条、按钮那排、侧栏各自从旧位置滑到新位置，背景交叉淡化（npstyle.css 的 vt-np）；不支持 / 减少动态效果 / 别的页面动画进行中就直接换
  if (full && !npPaint._vt && np.classList.contains('show') && !!(a === qAudio && m.video) !== np.classList.contains('is-video')
    && document.startViewTransition && !reduceMotion && !go._vt && !document.hidden) {
    npPaint._vt = true; const R = document.documentElement; R.classList.add('vt-np');
    // 新样子要在这一步里全部摆好再拍快照（以前按钮位置、画面大小、页签位置晚一帧才摆，动画放完又跳一下）
    let done = false; const run = () => { if (done) return; done = true; try { npPaint(true); np.classList.toggle('theater', npTheaterOn(np)); fitVideo(); npTabsPlace(); } finally { npPaint._vt = false; } };
    const t = document.startViewTransition(run);
    t.finished.finally(() => R.classList.remove('vt-np'));
    setTimeout(() => { if (!done) { try { t.skipTransition(); } catch { } run(); } }, 250);  // 浏览器没开始动画（页面在后台等）：直接换，绝不卡住
    return;
  }
  if (full) {
    $('#np-title').textContent = m.title || '未在播放'; $('#np-sub').textContent = m.sub || ''; favPaintNow();
    const stage = $('#np-stage'), isVid = a === qAudio && m.video;
    stage.classList.toggle('video', !!isVid); np.classList.toggle('is-video', !!isVid);
    if (qAudio.parentElement !== stage) stage.prepend(qAudio);
    miniSync(); requestAnimationFrame(() => { fitVideo(); npTabsPlace(); }); setTimeout(() => { fitVideo(); npTabsPlace(); }, 50);
    const art = $('#np-art'); art.dataset.vinyl = vinylHtml(m, a?.dataset.orbkey || ''); art.innerHTML = npArtHtml(m, a?.dataset.orbkey || '');
    np.classList.toggle('bg-dark', S.npBg === 'dark');  // 背景：多彩（默认，原来的流光 / 封面模糊）或暗色（固定的深灰渐变，不跟封面）
    const bg = $('#np-bg'), want = S.npBg !== 'dark' && S.coverMode === 'file' && m.cover ? m.cover : '';
    if (bg.dataset.src !== want) {
      bg.dataset.src = want; bg.style.backgroundImage = ''; bg.classList.remove('img');
      if (want) { const im = new Image(); im.onload = () => { if (bg.dataset.src === want) { bg.style.backgroundImage = `url("${want}")`; bg.classList.add('img'); } }; im.src = want; }
    }
    window.NPL?.paint();  // 外观：样式、背景颜色、封面（npstyle.js）
    $('#np-shuffle').classList.toggle('on', S.qmode.shuffle); $('#np-repeat').innerHTML = repeatIcon(S.qmode.repeat); $('#np-repeat').classList.toggle('on', S.qmode.repeat !== 'off'); $('#np-repeat').title = REPEAT[S.qmode.repeat][0];
    $$('[data-npb="prev"], [data-npb="next"], #np-shuffle, #np-repeat', np).forEach(b => b.disabled = RC.ctl ? (b.id === 'np-shuffle' || b.id === 'np-repeat') : !(a && a === qAudio && PB.q));  // 控制手机时：随机 / 循环在手机上改
    $$('.np-tabs button', np).forEach(b => b.classList.toggle('on', b.dataset.np === NP.tab));
    if (NP.tab === 'queue') qPanelPaint();
    else if (NP.key !== (m.subsKey || '') + '|' + (a ? 1 : 0) + (RC.ctl ? '|rc' : '')) { NP.key = (m.subsKey || '') + '|' + (a ? 1 : 0) + (RC.ctl ? '|rc' : ''); npSubs(m.subsKey, a && npAud()); }  // 控制手机时：字幕跟着手机（RCA）
  }
  if (!a) return;
  const ex = extOn() ? PB.ext : null, paused = ex ? !!ex.paused : a.paused;  // 控制手机时：手机的播放状态和进度
  { const pb = $('[data-npb="play"]', np), st = paused ? 'play' : 'pause';
    if (MOB() || np.classList.contains('npl-on')) { if (pb.dataset.ap !== st) { const was = !!pb.dataset.ap; pb.dataset.ap = st; pb.innerHTML = NP_GLYPH[st]; if (was && !reduceMotion) pb.firstChild.animate([{ transform: 'scale(.55)', opacity: .2 }, { transform: 'scale(1.06)', opacity: 1, offset: .7 }, { transform: 'none' }], { duration: 300, easing: 'cubic-bezier(.2, .8, .2, 1)' }); } }
    else { delete pb.dataset.ap; setIcon(pb, st); } }
  np.classList.toggle('playing', !paused);
  const d = ex ? ex.d || 0 : pbDur(a), c = ex ? (PB.scrub ? PB.scrub.t : ex.t || 0) : pbCur(a);
  $('#np-fill').style.width = (d ? Math.min(100, c / d * 100) : 0) + '%';
  $('#np-thin').style.width = (d ? Math.min(100, c / d * 100) : 0) + '%';  // 控制条隐藏后屏幕最底下的细进度线
  $('#np-t0').textContent = fmtT(c); $('#np-t1').textContent = d ? '-' + fmtT(Math.max(0, d - c)) : '0:00'; scrubAria($('#np-track'), c, d);
}
/* ---- 字幕翻译（谷歌翻译，只发送字幕文字）：可以开关、选翻译成什么语言；原文语言默认自动识别，也可以自己指定 ---- */
S.tr = Object.assign({ on: false, to: 'zh-CN', from: 'auto', eng: 'google' }, S.tr || {});
const TR_LANGS = [['zh-CN', '简体中文'], ['zh-TW', '繁體中文'], ['en', 'English'], ['ja', '日本語'], ['ko', '한국어'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español'],
  ['ru', 'Русский'], ['pt', 'Português'], ['it', 'Italiano'], ['th', 'ไทย'], ['vi', 'Tiếng Việt'], ['id', 'Bahasa Indonesia'], ['ar', 'العربية']];
const ASR_LANG = { chinese: 'zh-CN', mandarin: 'zh-CN', cantonese: 'zh-TW', english: 'en', japanese: 'ja', korean: 'ko', french: 'fr', german: 'de', spanish: 'es',
  russian: 'ru', portuguese: 'pt', italian: 'it', thai: 'th', vietnamese: 'vi', indonesian: 'id', arabic: 'ar' };
const langName = c => { if (!c) return ''; const k = String(c).toLowerCase(); const code = ASR_LANG[k] || c; return (TR_LANGS.find(x => x[0].toLowerCase() === String(code).toLowerCase()) || TR_LANGS.find(x => x[0].split('-')[0] === String(code).split('-')[0].toLowerCase()) || [0, c])[1]; };
const sameLang = (a, b) => a && b && (ASR_LANG[String(a).toLowerCase()] || a).toLowerCase() === b.toLowerCase();
// 字幕时间调节：S.ui.subOff[字幕键] = 秒（正数 = 字幕提前）
const npSubOff = () => +(S.ui?.subOff?.[NP.subsKey] || 0);
function npSubOffSet(v) {
  v = Math.round(Math.max(-10, Math.min(10, v)) * 10) / 10;
  const m = { ...(S.ui?.subOff || {}) }; if (v) m[NP.subsKey] = v; else delete m[NP.subsKey];
  S.ui = { ...(S.ui || {}), subOff: m }; persist(); $('#np-right .np-subs')?._upd?.();
  toast(v ? `字幕${v > 0 ? '提前' : '推后'} ${Math.abs(v).toFixed(1)} 秒` : '字幕时间已还原');
}
const npSubOffName = () => { const v = npSubOff(); return v ? `${v > 0 ? '提前' : '推后'} ${Math.abs(v).toFixed(1)} 秒` : '未调整'; };
// 字幕的操作（2026-11-18 用户：逐行 / 段落 / 全文、重新生成、翻译、查找收进右键菜单和右上角 ⋯，界面上不常驻）
function npSubsActions(anchor) {
  const r = $('#np-right'), host = $('.np-subs', r), has = NP.tab === 'subs' && !!host && !!NP.sents?.length;
  const out = [];
  if (NP.subsTarget) out.push({ label: '载入字幕 / 歌词文件…', icon: CTX_IC.open || '', on: npSubsPick });
  if (!has) return out;
  const mode = $('[data-mode] .on', host)?.dataset.m || 'line';
  out.push('-', { group: '显示方式' }, ...[['line', '逐行'], ['para', '段落'], ['full', '全文']].map(([m, n]) => ({ label: n, checked: mode === m, on: () => $(`[data-mode] [data-m="${m}"]`, host)?.click() })));
  out.push('-', { label: '查找…', hint: 'Ctrl+F', icon: ICON.search, on: () => host._find?.() },
    { label: S.tr.on ? `翻译：${langName(S.tr.to)}` : '翻译…', icon: ICON.translate, on: () => trPopover(anchor || $('#np-more2') || $('#np-more'), npAud()) });
  const rg = $('[data-regen]', host); if (rg) out.push({ label: '重新生成字幕…', icon: ICON.redo, on: () => rg.click() });
  out.push('-', { group: `字幕时间（${npSubOffName()}）` },
    { label: '提前 0.1 秒', on: () => npSubOffSet(npSubOff() + .1) }, { label: '推后 0.1 秒', on: () => npSubOffSet(npSubOff() - .1) },
    ...(npSubOff() ? [{ label: '还原', on: () => npSubOffSet(0) }] : []));
  return out;
}
function trBtnHtml() {
  const st = NP.trBusy ? `翻译中${NP.trBusy}` : S.tr.on ? langName(S.tr.to) : '翻译';
  return `<button type="button" class="icon-link tr-btn${S.tr.on ? ' on' : ''}" data-tr title="字幕翻译">${ICON.translate}<span class="tr-state">${esc(st)}</span></button>`;
}
function npSubsDraw(audio) {
  const box = $('#np-right'), tr = S.tr.on ? NP.tr : null;
  const render = tr ? (x, i) => esc(x.text) + (tr[i] && tr[i] !== x.text ? `<span class="tr">${esc(tr[i])}</span>` : '') : null;
  box.innerHTML = '<div class="np-subs"></div>';
  // 2026-11-17 用户：有些气声没转出来——加“重新生成”：删掉现在的字幕（连译文），重新识别
  const regen = NP.subsKey && !RC.ctl ? `<button type="button" class="icon-link np-regen" data-regen title="删除现在的字幕，重新识别">${ICON.redo}重新生成</button>` : '';
  subsWidget($('.np-subs', box), NP.sents, audio, { lyrics: true, render, tools: regen + trBtnHtml(), mode: NP.subMode, onMode: m => { NP.subMode = m; }, off: npSubOff });
  $('[data-tr]', box).onclick = e => trPopover(e.currentTarget, audio);
  const rb = $('[data-regen]', box);
  if (rb) rb.onclick = async () => {
    if (!await confirmBox('重新生成字幕？', '现在的字幕和译文会被删除，然后重新识别这段音频（较长的音频约需 1–2 分钟）。', '重新生成')) return;
    const key = NP.subsKey, r = await api('/api/play/subs?key=' + encodeURIComponent(key) + '&redo=1', { body: {} }).catch(e => ({ state: 'error', error: e.message }));
    if (r.state === 'error') return toast('重新生成失败：' + (r.error || ''), true);
    NP.sents = null; NP.tr = null; npSubs(key, audio);
  };
}
function trPaintBtn() { const b = $('#np-right [data-tr]'); if (b) b.outerHTML = trBtnHtml(); const nb = $('#np-right [data-tr]'); if (nb) nb.onclick = e => trPopover(e.currentTarget, npAud()); }
async function trLoad(token) {
  const key = NP.subsKey, to = S.tr.to, from = S.tr.from, eng = S.tr.eng;
  const q = `/api/play/translate?key=${encodeURIComponent(key)}&to=${encodeURIComponent(to)}&from=${encodeURIComponent(from)}&engine=${eng}`;
  const still = () => NP.key === token && S.tr.on && S.tr.to === to && S.tr.from === from && S.tr.eng === eng;
  const fail = e => ({ state: 'error', error: e.message });
  let r = await api(q).catch(fail);
  if (r.state === 'none') r = await api(q, { body: {} }).catch(fail);
  while (r.state === 'running' && still()) {
    NP.trBusy = r.total && r.done ? ` ${r.done}/${r.total}` : eng === 'local' && !r.done ? '（加载模型）' : '…'; trPaintBtn();
    await sleep(1000); r = await api(q).catch(fail);
  }
  NP.trBusy = '';
  if (!still()) return trPaintBtn();
  if (r.state === 'done') { NP.tr = r.lines; NP.trSrc = r.src || NP.trSrc; npSubsDraw(npAud()); capPaint(); }
  else { trPaintBtn(); toast('翻译失败：' + (r.error || ''), true); }
}
function trPopover(anchor, audio) {
  const det = NP.trSrc || NP.lang;
  const opt = (v, n, cur) => `<option value="${v}"${v === cur ? ' selected' : ''}>${esc(n)}</option>`;
  popover(anchor, `<div class="tr-pop">
      <div class="gp-row" style="padding:0 0 8px"><span class="gp-l">显示翻译</span><label class="switch"><input type="checkbox" id="tr-on" ${S.tr.on ? 'checked' : ''}><span></span></label></div>
      <div class="seg full tr-eng" id="tr-eng"><button type="button" data-e="google" class="${S.tr.eng !== 'local' ? 'on' : ''}">谷歌翻译</button><button type="button" data-e="local" class="${S.tr.eng === 'local' ? 'on' : ''}">本地模型</button></div>
      <label class="tr-lbl" for="tr-to">翻译为</label><select class="select" id="tr-to">${TR_LANGS.map(([v, n]) => opt(v, n, S.tr.to)).join('')}</select>
      <label class="tr-lbl" for="tr-from">原文语言</label><select class="select" id="tr-from">${opt('auto', '自动识别' + (det ? `（${langName(det)}）` : ''), S.tr.from)}${TR_LANGS.map(([v, n]) => opt(v, n, S.tr.from)).join('')}</select>
      <div class="tiny tr-note" id="tr-same"${sameLang(det, S.tr.to) && S.tr.from === 'auto' ? '' : ' hidden'}>原文已是所选语言，请选择其他目标语言。</div>
      <div class="tiny tr-note" id="tr-eng-note"></div></div>`,
    pop => {
      const apply = () => {
        S.tr = { on: $('#tr-on', pop).checked, to: $('#tr-to', pop).value, from: $('#tr-from', pop).value, eng: $('#tr-eng button.on', pop)?.dataset.e || 'google' }; persist(); note();
        $('#tr-same', pop).hidden = !(sameLang(NP.trSrc || NP.lang, S.tr.to) && S.tr.from === 'auto');
        NP.tr = null; npSubsDraw(audio); capPaint();
        if (S.tr.on) trLoad(NP.key);
      };
      ['#tr-on', '#tr-to', '#tr-from'].forEach(s => $(s, pop).onchange = () => { if (s !== '#tr-on') $('#tr-on', pop).checked = true; apply(); });
      const note = () => { $('#tr-eng-note', pop).textContent = S.tr.eng === 'local' ? '本地 Index-Translate-9B，离线运行、不联网；首次使用需加载约 10 秒，闲置 10 分钟后自动释放显存。' : '由谷歌翻译提供，仅发送字幕文本。'; };
      note();
      $$('#tr-eng button', pop).forEach(b => b.onclick = async () => {
        if (b.dataset.e === 'local' && !(await api('/api/play/translate-engines').catch(() => ({}))).local) return toast('没有安装本地翻译模型', true);
        $$('#tr-eng button', pop).forEach(x => x.classList.toggle('on', x === b)); $('#tr-on', pop).checked = true; apply();
      });
    }, { width: 248 });
}
/* 载入字幕 / 歌词文件（2026-11-17 用户）：字幕区右键、⋯ 菜单，或把文件拖到字幕区。换掉现在的字幕（旧译文作废），格式见 subimport.py */
const SUB_EXT = '.lrc,.srt,.vtt,.ass,.ssa,.qrc,.krc,.txt';  // .qrc / .krc：QQ 音乐、酷狗的逐字歌词（2026-11-18）
async function npSubsLoad(file) {
  const key = NP.subsTarget, audio = npAud(); if (!key || !file || RC.ctl) return;
  if (!/\.(lrc|srt|vtt|ass|ssa|qrc|krc|txt)$/i.test(file.name)) return toast('请选择 LRC、SRT、VTT、ASS、QRC 或 KRC 字幕 / 歌词文件', true);
  if (file.size > 4 << 20) return toast('字幕文件太大（最多 4 MB）', true);
  if (NP.sents?.length && !await confirmBox('换成这个字幕文件？', '现在的字幕和译文会被替换。', '载入')) return;
  const u8 = new Uint8Array(await file.arrayBuffer()); let bin = '';
  for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  const r = await api('/api/play/subs?key=' + encodeURIComponent(key) + '&import=1', { body: { name: file.name, data: btoa(bin) } }).catch(e => ({ error: e.message }));
  if (r.error) return toast('载入失败：' + r.error, true);
  toast(`已载入字幕（${r.sents.length} 句）`);
  if (NP.subsTarget === key) { NP.sents = null; NP.tr = null; npSubs(key, audio); }
}
function npSubsPick() {
  const f = Object.assign(document.createElement('input'), { type: 'file', accept: SUB_EXT });
  f.onchange = () => { if (f.files[0]) npSubsLoad(f.files[0]); };
  f.click();
}
async function npSubs(key, audio) {
  const box = $('#np-right'), token = NP.key;
  NP.subsTarget = key && audio && !RC.ctl ? key : null;
  NP.sents = null; capPaint();
  if (!key || !audio) { box.innerHTML = `<div class="np-empty">${audio ? '此音频暂不支持字幕' : '未在播放'}</div>`; return; }
  const draw = r => {
    if (NP.key !== token || NP.tab !== 'subs') return;
    if (r.state === 'done') {
      NP.sents = r.sents; NP.lang = r.language; NP.tr = null; NP.subsKey = key; capPaint();
      if (!r.sents.length) {  // 没识别出来（气声、很轻的声音常这样）：也能重新生成
        box.innerHTML = `<div class="np-empty">未识别到人声${RC.ctl ? '' : `<button class="btn np-gen" id="np-regen0">${ICON.redo}重新生成</button>`}</div>`;
        const b0 = $('#np-regen0', box); if (b0) b0.onclick = async () => { const r2 = await api('/api/play/subs?key=' + encodeURIComponent(key) + '&redo=1', { body: {} }).catch(e => ({ state: 'error', error: e.message })); if (r2.state === 'error') return toast('重新生成失败：' + (r2.error || ''), true); npSubs(key, audio); };
        return; }
      npSubsDraw(audio);
      if (S.tr.on) trLoad(token);
    } else if (r.state === 'running') {
      // 2026-11-18 用户：要有进度、能取消，不要说明文字。进度是后台按音频长度和上次的识别速度估的（引擎不报进度）
      const pc = Math.round((r.p || 0) * 100), was = $('.np-genning', box);
      if (was) { $('.np-gbar i', was).style.width = pc + '%'; $('.np-gpc', was).textContent = pc + '%'; }
      else {
        box.innerHTML = `<div class="np-empty np-genning"><div class="np-gl"><span>正在生成字幕…</span><span class="np-gpc">${pc}%</span></div><div class="np-gbar"><i style="width:${pc}%"></i></div><button type="button" class="np-gcancel">取消</button></div>`;
        $('.np-gcancel', box).onclick = async () => draw(await api('/api/play/subs?key=' + encodeURIComponent(key) + '&cancel=1', { body: {} }).catch(() => ({ state: 'none' })));
      }
      setTimeout(async () => { if (!$('.np-genning', box)) return; draw(await api('/api/play/subs?key=' + encodeURIComponent(key)).catch(e => ({ state: 'error', error: e.message }))); }, 1000);
    } else {
      box.innerHTML = `<div class="np-empty">${r.state === 'error' ? '字幕生成失败：' + esc(r.error || '') + '<br>' : ''}<button class="btn np-gen" id="np-gen">${ICON.wave}转换字幕</button></div>`;
      $('#np-gen', box).onclick = async () => draw(await api('/api/play/subs?key=' + encodeURIComponent(key), { body: {} }).catch(e => ({ state: 'error', error: e.message })));
    }
  };
  box.innerHTML = '<div class="np-empty"><span class="spinner"></span></div>';
  draw(await api('/api/play/subs?key=' + encodeURIComponent(key)).catch(e => ({ state: 'error', error: e.message })));
}
function bindNowPlaying() {
  const np = $('#np'); if (!np) return;
  { const r = $('#np-right');  // 字幕区：右键菜单、拖入字幕文件
    r.addEventListener('contextmenu', e => {
      if (NP.tab !== 'subs' || !NP.subsTarget || e.target.closest('input, textarea')) return;
      const items = npSubsActions();
      const rg0 = $('#np-regen0', r); if (rg0 && !$('[data-regen]', r)) items.push('-', { label: '重新识别', on: () => rg0.click() });
      ctxMenu(e, items);
    });
    // Ctrl+F：全屏播放页的字幕里查找（以前要先点到字幕区里才行）
    document.addEventListener('keydown', e => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'f' || $('#np').hidden || NP.tab !== 'subs') return;
      const h = $('#np-right .np-subs'); if (!h?._find) return; e.preventDefault(); e.stopPropagation(); h._find();
    }, true);
    r.addEventListener('dragover', e => { if (NP.tab === 'subs' && NP.subsTarget && [...(e.dataTransfer?.items || [])].some(x => x.kind === 'file')) { e.preventDefault(); r.classList.add('np-drop'); } });
    r.addEventListener('dragleave', e => { if (!r.contains(e.relatedTarget)) r.classList.remove('np-drop'); });
    r.addEventListener('drop', e => { r.classList.remove('np-drop'); const f = e.dataTransfer?.files?.[0]; if (!f || NP.tab !== 'subs' || !NP.subsTarget) return; e.preventDefault(); npSubsLoad(f); });
  }
  $('#np-stage').prepend(qAudio);
  $('#np-close').onclick = () => npClose();
  $$('#np-dock [data-mv]').forEach(b => b.onclick = () => npSetView(b.dataset.mv));
  $('#np-fxm').onclick = () => spToggle();
  $('#np-more').onclick = e => npMore(e.currentTarget);
  { const m2 = $('#np-more2'); if (m2) m2.onclick = e => npMore(e.currentTarget, true); }
  { const mn = $('#np-min'); if (mn) mn.onclick = () => npClose(); }  // 左下角的“退出全屏播放”：和左上角的收起一样
  { // 手机手势：在顶上 / 封面 / 标题 / 空白处往下拖 = 收起（跟着手指走，松手不够远就弹回）；封面视图里在封面上左右滑 = 下一首 / 上一首
    const np = $('#np'); let g = null;
    np.addEventListener('touchstart', e => {
      g = null; const tg = e.target;
      if (!MOB() || e.touches.length !== 1 || !tg.closest('.np-top, .np-body') || tg.closest('button, input, .np-track, #np-right, .np-ctl, .np-dock, video')) return;
      if ($('.np-body', np).scrollTop > 0) return;
      const t = e.touches[0]; g = { x: t.clientX, y: t.clientY, t: Date.now(), mode: null, d: 0, side: !!tg.closest('#np-stage') && NP.mv === 'cover' && !np.classList.contains('is-video') };
    }, { passive: true });
    np.addEventListener('touchmove', e => {
      if (!g) return; const t = e.touches[0], dx = t.clientX - g.x, dy = t.clientY - g.y;
      if (!g.mode) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; g.mode = Math.abs(dy) > Math.abs(dx) ? (dy > 0 ? 'down' : 'none') : (g.side ? 'side' : 'none'); }
      if (g.mode === 'none') return;
      e.preventDefault();  // 拖动时后面的文件页不跟着滚
      if (g.mode === 'down') { g.d = Math.max(0, dy); np.style.transition = 'none'; np.style.transform = `translateY(${g.d}px)`; }
      else { g.d = dx; const st = $('#np-stage'); st.style.transition = 'none'; st.style.transform = `translateX(${dx}px)`; st.style.opacity = 1 - Math.min(.6, Math.abs(dx) / 420); }
    }, { passive: false });
    const EZ = 'cubic-bezier(.2, .8, .2, 1)';
    const end = () => {
      if (!g || !g.mode || g.mode === 'none') { g = null; return; }
      const fast = Date.now() - g.t < 350, d = g.d, mode = g.mode; g = null;
      if (mode === 'down') {
        if (d > 130 || (fast && d > 50)) { np.style.transition = `transform .26s ${EZ}`; np.style.transform = `translateY(${innerHeight}px)`; setTimeout(() => { npClose(true); np.style.transition = np.style.transform = ''; }, 260); }
        else { np.style.transition = `transform .3s ${EZ}`; np.style.transform = ''; setTimeout(() => { np.style.transition = ''; }, 320); }
        return;
      }
      const st = $('#np-stage'), go = (Math.abs(d) > 90 || (fast && Math.abs(d) > 40)) && PB.q;
      if (go) {
        st.style.transition = `transform .18s ease-in, opacity .18s`; st.style.transform = `translateX(${d < 0 ? -innerWidth : innerWidth}px)`; st.style.opacity = '0';
        setTimeout(() => {
          if (d < 0) qNext(false); else qPrev();
          st.style.transition = 'none'; st.style.transform = `translateX(${d < 0 ? 60 : -60}px)`;
          requestAnimationFrame(() => { st.style.transition = `transform .32s ${EZ}, opacity .32s`; st.style.transform = ''; st.style.opacity = ''; setTimeout(() => { st.style.transition = ''; }, 340); });
        }, 180);
      } else { st.style.transition = `transform .3s ${EZ}, opacity .3s`; st.style.transform = ''; st.style.opacity = ''; setTimeout(() => { st.style.transition = ''; }, 320); }
    };
    np.addEventListener('touchend', end); np.addEventListener('touchcancel', end);
  }
  $('#np-fav').onclick = () => { const k = RC.ctl ? RC.st?.key : qCur()?.key; if (k) toggleFav(k); };
  $('#np-fs').onclick = npFullscreen;
  $('#np-mini').onclick = () => compactOpen();  // 迷你播放器（2026-11-18 用户：放进全屏播放页右上角，照 QQ 音乐）
  // 隐藏字幕栏：视频在当前窗口里铺满（再按一次恢复）；真全屏时默认隐藏
  $('#np-theater').onclick = () => { const fs = $('#np').classList.contains('fs'); S.ui = { ...(S.ui || {}), ...(fs ? { fsPanel: !S.ui?.fsPanel } : { theater: !S.ui?.theater }) }; persist(); npTheater(); };
  npTheater();
  // 真全屏时鼠标 2.5 秒不动：隐藏控制条和指针（像视频播放器）
  let idleT = 0;
  const canIdle = () => (np.classList.contains('fs') || np.classList.contains('theater')) && np.classList.contains('is-video');
  const wake = e => {
    if (e?.type === 'pointermove' && np._hideUntil && Date.now() < np._hideUntil) return;  // 刚点过“隐藏控制条”：鼠标的小抖动不唤醒
    np.classList.remove('idle'); clearTimeout(idleT);
    idleT = setTimeout(() => { if (canIdle() && PB.a && !PB.a.paused) np.classList.add('idle'); }, 1600);
  };
  $('#np-hide').onclick = e => { e.stopPropagation(); if (!canIdle()) return; clearTimeout(idleT); np._hideUntil = Date.now() + 700; np.classList.add('idle'); };
  np.addEventListener('pointermove', wake); np.addEventListener('pointerdown', wake); document.addEventListener('fullscreenchange', wake);
  $('#np-pip').onclick = async () => {  // 画中画 = 缩成页面里的小窗，页面回到文件列表
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => { });
    const mini = MINI; if (mini) mini._dismissed = false;
    npClose();
  };
  $('#np-fs2').onclick = e => { e.stopPropagation(); npFullscreen(); };
  qAudio.addEventListener('enterpictureinpicture', () => setTimeout(miniSync, 50));
  qAudio.addEventListener('leavepictureinpicture', () => setTimeout(miniSync, 50));
  $('#np-capbtn').onclick = () => { S.ui = { ...(S.ui || {}), cap: S.ui?.cap === false }; persist(); capPaint(); toast(S.ui.cap === false ? '已关闭画面字幕' : '已开启画面字幕'); };
  // 视频：单击画面暂停 / 播放，双击全屏
  qAudio.addEventListener('click', () => { if ($('#np').hidden) return; qAudio.paused ? qAudio.play().catch(playErr) : qAudio.pause(); });
  qAudio.addEventListener('dblclick', () => { if (!$('#np').hidden) npFullscreen(); });
  const typing = el => !!el?.closest?.('textarea, select, [contenteditable=""], [contenteditable="true"]') || (el?.tagName === 'INPUT' && !/^(range|checkbox|radio|button)$/.test(el.type));
  const upper = () => curPop || CTX || $('.dd-menu.show') || $('.modal-bg') || ImageViewer.isOpen();  // 上面还盖着一层：按键给那一层
  addEventListener('keydown', e => {
    if (np.hidden || typing(e.target) || e.ctrlKey || e.metaKey || e.altKey || upper()) return;
    const k = e.key;
    if (k !== ' ' && e.target.closest?.('#np-vtrack')) return;  // 音量条有焦点：方向键调音量
    if (k === ' ') { e.preventDefault(); e.stopPropagation(); if (!e.repeat) $('[data-pb="play"]').click(); }
    else if ((k === 'ArrowLeft' || k === 'ArrowRight') && PB.a) {
      e.preventDefault(); e.stopPropagation(); const d = k === 'ArrowLeft' ? -5 : 5;
      if (extOn()) extCmd({ seekBy: d }); else keySeek(PB.a, Math.min((PB.a.duration || 1e9) - .05, Math.max(0, PB.a.currentTime + d)));
      pbPaint();
    }
  }, true);
  document.addEventListener('keydown', e => {
    if (np.hidden || e.target.closest('input, textarea, select')) return;
    if (e.key === 'Escape' && (e.defaultPrevented || upper())) return;  // 先关上面那层
    if (e.key === 'Escape' && !document.fullscreenElement) npClose();
    else if (e.key.toLowerCase() === 'f' && np.classList.contains('is-video')) npFullscreen();
  });
  $$('.np-tabs button', np).forEach(b => b.onclick = () => {
    if (NP.tab === b.dataset.np) return;
    const box = $('#np-right'), dir = b.dataset.np === 'queue' ? 1 : -1;
    $$('.np-tabs button', np).forEach(x => x.classList.toggle('on', x === b));
    box.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translateX(${-16 * dir}px)` }], { duration: 140, easing: 'ease-in', fill: 'forwards' });
    setTimeout(() => {  // 先淡出，再换内容并从另一侧滑入
      NP.tab = b.dataset.np; NP.key = null; npPaint(true);
      box.getAnimations().forEach(a => a.cancel());
      box.animate([{ opacity: 0, transform: `translateX(${20 * dir}px)` }, { opacity: 1, transform: 'none' }], { duration: 320, easing: EASE });
    }, 140);
  });
  $('[data-npb="play"]', np).onclick = () => $('[data-pb="play"]').click();
  $('[data-npb="back"]', np).onclick = () => $('[data-pb="back"]').click();
  $('[data-npb="fwd"]', np).onclick = () => $('[data-pb="fwd"]').click();
  $('[data-npb="prev"]', np).onclick = () => qPrev();
  $('[data-npb="next"]', np).onclick = () => qNext(false);
  $('#np-shuffle').onclick = () => qSetShuffle(!S.qmode.shuffle);
  $('#np-repeat').onclick = () => qCycleRepeat();
  bindScrub($('#np-track'), np);
}

/* ================= 朗读页 ================= */
function renderTTS() {
  drawerOwner = null;
  const m = curModel();
  $('#main').innerHTML = `
  <div class="page-head">
    <h1 class="page-title">配音</h1>
    <div class="row"><span class="tiny">模型</span><select class="select" id="model" style="width:auto;min-width:200px">${models.map(x => `<option value="${x.key}" ${x.key === m?.key ? 'selected' : ''}>${esc(x.display_name)}</option>`).join('')}</select></div>
  </div>
  <div class="grid-tts">
    <div class="stack">
      <div class="card">
        <div class="row tts-head"><span class="card-title" style="margin:0">文本</span><span class="spacer"></span>
          <span class="tip-q" tabindex="0" aria-label="写法小技巧">?<span class="tip-card"><b>写法小技巧</b>
            <span>空一行表示换段落，段落之间停顿更长<em>所有模型</em></span>
            <span>[停顿 1.5秒]：在此处插入指定时长的静音<em>所有模型</em></span>
            <span>段首写 {委屈得快哭了}：仅更改该段语气<em>Qwen3-TTS 用克隆音色时无效</em></span>
            <span>[笑]、[叹气]、[咳嗽] 等声音事件<em>仅 Breeze TTS 2</em></span>
            <span>&lt;银行|yin2 hang2&gt; 指定读音<em>仅 IndexTTS-2.5</em></span></span></span>
          <button class="btn small ghost" id="ai-text" title="使用 AI 助手撰写或改写台词（将附带当前文本）">${ICON.wand}AI 撰写</button><button class="btn small ghost" id="clear-text">清空</button></div>
        <div class="toolbar tts-ins">${toolbarHtml()}</div>
        <div id="tool-drawer" class="drawer"></div>
        <textarea class="textarea script" id="script" placeholder="输入或粘贴要合成的文本。空一行表示新段落。">${esc(S.text)}</textarea>
        <div class="stat"><span id="stat" style="display:contents"></span><label class="seg-switch" title="开：长段落在句号处切分生成，更稳定。关：整段生成，语气更连贯（超过 450 字仍会切分）。"><span class="switch"><input type="checkbox" id="split-sw" ${S.job.split === false ? '' : 'checked'}><span></span></span>智能分段</label></div>
        <div class="compose-foot">
          <div class="now now-mini" id="now"></div>
          <button class="btn big" id="preview" title="试听选中的文字；未选中时试听第一段（最多 300 字）">${ICON.play}试听</button>
          <button class="btn grad big" id="go"><span class="wave"></span><span class="lbl">开始生成</span></button>
        </div>
      </div>
      <div id="preview-out"></div>
    </div>
    <div class="side-col">
      <div class="seg full tts-tabs" id="tts-tabs"><button type="button" data-t="set">设置</button><button type="button" data-t="rec">记录<span class="rec-n" id="rec-n"></span></button></div>
      <div id="tts-rec" class="tts-pane"><div class="card rec-card"><div class="row between rec-head"><span class="tiny" id="rec-sum"></span><button type="button" class="btn small ghost" id="rec-clear" title="仅在此处隐藏，历史记录中仍保留">清空</button></div><div id="rec-list" class="rec-list"></div></div></div>
      <div id="tts-set" class="tts-pane">
      <div class="card"><details class="adv" id="voice-box" ${S.voice ? '' : 'open'}><summary>${ICON.chev}音色<span class="spacer"></span><span class="sum-voice" id="voice-sum"></span></summary>
        <div style="margin-top:12px"><div class="voice-pick" id="voice-pick"></div><div style="text-align:right;margin-top:8px"><a href="/voices" data-page="voices" class="tiny">管理音色 ›</a></div></div></details></div>
      <div class="card"><details class="adv" id="dir-box" ${S.ui?.dirOpen === false ? '' : 'open'}><summary>${ICON.chev}导演<span class="spacer"></span><span id="dir-pill"></span></summary><div id="director" style="margin-top:12px"></div></details></div>
      <div class="card"><details class="adv" id="adv"><summary>${ICON.chev}高级参数<span class="spacer"></span><span class="tiny" id="adv-count"></span><button class="icon-link" id="adv-pop" title="在大窗口中编辑全部参数">⤢ 弹窗编辑</button></summary><div id="adv-body" style="margin-top:12px"></div></details></div>
    </div>
    </div>
  </div>`;
  $('#model').onchange = e => {
    // 每个模型各自记住自己的导演设置和高级参数，切换模型不会互相串
    S.byModel = S.byModel || {};
    S.byModel[curModel().key] = { dir: S.dir, adv: S.adv };
    S.model = e.target.value;
    const saved = S.byModel[S.model] || {};
    S.dir = saved.dir || { emotion: '', level: 1, styles: [], pace: '', extra: '', useVector: false, vector: [0, 0, 0, 0, 0, 0, 0, 0] };
    S.adv = saved.adv || {};
    if (curPreset() && !roles().preset) S.voice = null;
    persist(); renderTTS();
  };
  const ta = $('#script');
  ta.oninput = () => { S.text = ta.value; persistSoon(); updateStat(); };
  $('#clear-text').onclick = () => { const old = ta.value; if (!old) return; ta.value = ''; ta.oninput(); toastAct('已清空', '撤销', () => { if (!ta.isConnected) return; ta.value = old; ta.oninput(); }); };
  $('#ai-text').onclick = () => pgOpen(ta.value.trim(), 'tts');
  bindToolbar(ta);
  $('#split-sw').onchange = e => { S.job.split = e.target.checked; persist(); updateStat(); toast(S.job.split ? '已开启智能分段：长段落在句号处切分，最为稳定' : '已关闭智能分段：每个自然段整段生成，语气更连贯'); };
  $('#dir-box').ontoggle = e => { S.ui = { ...(S.ui || {}), dirOpen: e.target.open }; persist(); };
  $('#preview').onclick = doPreview;
  $('#go').onclick = startJob;
  const tab = () => { $('#tts-set').hidden = true; $('#tts-rec').hidden = false; };  // 右边固定是产出（记录）；音色、导演、模型都在文本框底下的按钮里
  renderTTS.tab = tab;
  $$('#tts-tabs button').forEach(b => b.onclick = () => { tab(b.dataset.t); persist(); if (b.dataset.t === 'rec') recWatch(); });
  $('#rec-clear').onclick = () => { const old = S.ttsRec || []; if (!old.length) return; S.ttsRec = []; persist(); recPaint(); toastAct('已清空此处的记录（历史记录中仍保留）', '撤销', () => { S.ttsRec = old; persist(); recPaint(); recWatch(); }); };
  if (S.jobId) { S.ttsRec = [S.jobId, ...(S.ttsRec || []).filter(x => x !== S.jobId)]; S.jobId = null; persist(); }  // 旧版本记的“当前任务”
  tab(); recWatch();
  $('#adv-pop').onclick = e => { e.preventDefault(); e.stopPropagation(); openAdvModal(); };
  { // 配音（和生图 / 生视频一个思路）：文本框底下一排——音色、导演（点开是面板）、模型、高级参数……试听、开始生成；右边只放产出
    const card = $('#script').closest('.card'), foot = $('.compose-foot', card), sel = $('#model'), hr = sel?.closest('.row');
    if (card && foot && sel) {
      if (hr?.closest('.page-head')) hr.remove();
      card.classList.add('tts-comp');
      const chips = document.createElement('div'); chips.className = 'tts-chips';
      chips.innerHTML = `<button type="button" class="ig-chip" id="tts-voice-chip" title="音色"><span></span></button><button type="button" class="ig-chip" id="tts-dir-chip" title="导演"><span>导演</span>${IG_CHEV}</button>`;
      sel.classList.add('tts-model-sel'); sel.style.width = ''; sel.style.minWidth = '';
      { const head = $('.tts-head', card), tt = head && $('.card-title', head); if (tt) tt.after(sel); else chips.append(sel); }  // 模型紧跟在“文本”后面，底栏只留音色、导演、高级参数、试听、开始生成
      { const ins = $('.tts-ins', card), q = $('.tts-head .tip-q', card); if (ins && q) { const row = document.createElement('div'); row.className = 'tts-insrow'; ins.before(row); row.append(ins, q); } }  // “?”放到插入标记这一行的最右边
      foot.prepend(chips);
      requestAnimationFrame(() => { if (!chips.isConnected) return; const ab = card.querySelector('#adv-btn'); if (ab) chips.append(ab); const pv = card.querySelector('#preview'); if (pv) { pv.classList.remove('big'); pv.classList.add('tts-pv'); }
        barSplit(foot, [foot.querySelector(':scope > #preview'), foot.querySelector(':scope > #go')]); });
      const panels = [];
      const mkp = (chip, cardEl, detId) => {
        const p = document.createElement('div'); p.className = 'tts-panel'; p.hidden = true; p.append(cardEl); card.append(p); panels.push([p, chip]);
        if ($('#' + detId)) $('#' + detId).open = true;
        chip.onclick = e => { e.stopPropagation(); const was = !p.hidden; panels.forEach(([q, c]) => { q.hidden = true; c.classList.remove('open'); }); if (was) return;
          p.hidden = false; chip.classList.add('open'); p.style.bottom = (card.offsetHeight - foot.offsetTop + 8) + 'px'; };
        p.addEventListener('click', e => e.stopPropagation());
      };
      mkp($('#tts-voice-chip'), $('#voice-box').closest('.card'), 'voice-box');
      mkp($('#tts-dir-chip'), $('#dir-box').closest('.card'), 'dir-box');
      const offDoc = e => { if (!card.isConnected) return document.removeEventListener('click', offDoc); if (e.target.closest('.modal-bg, .pop, .dd-menu')) return; panels.forEach(([q, c]) => { q.hidden = true; c.classList.remove('open'); }); };
      document.addEventListener('click', offDoc);
      const vs = $('#voice-sum'), dp = $('#dir-pill');
      const syncL = () => {
        $('#tts-voice-chip span').innerHTML = vs?.innerHTML && !/未选择/.test(vs.textContent) ? vs.innerHTML : '选择音色';
        const d = (dp?.textContent || '').trim(); $('#tts-dir-chip span').textContent = d && !/未/.test(d) ? d : '导演';
      };
      [vs, dp].forEach(x => x && new MutationObserver(syncL).observe(x, { childList: true, subtree: true, characterData: true })); syncL();
    } }
  if ($('#preview') && !$('#adv-btn')) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'ig-cb'; b.id = 'adv-btn'; b.title = '高级参数'; b.innerHTML = `${ICON.sliders}高级参数<span class="ig-adv-n" id="adv-btn-n"></span>`;
    $('#preview').before(b); b.onclick = () => openAdvModal();
    const syncN = () => { const n = b.querySelector('#adv-btn-n'); if (n) n.textContent = ($('#adv-count')?.textContent || '').replace(/\D/g, ''); };
    if ($('#adv-count')) { new MutationObserver(syncN).observe($('#adv-count'), { childList: true, characterData: true, subtree: true }); syncN(); }
  }
  renderVoicePick(); renderDirector(); renderAdv(); updateStat();
  bindFitScript();
  recWatch();
}
/* 配音页的“记录”：这一页生成过的（新的在最上面）。每条：标题、状态 / 进度、播放、保存到作品、下载、详情（分段、日志、重做）、从这里拿掉。
   清空只是不在这里显示，“作品 → 历史记录”里还在。 */
const recRow = j => {
  const running = ['queued', 'running'].includes(j.state), pct = j.total ? Math.round(j.done / j.total * 100) : 0;
  const st = j.state === 'done' ? (j.warn ? `<span class="pill orange">${j.warn} ${unit(j)}可能读错</span>` : '') : j.state === 'error' ? `<span class="pill red">${j.message === '已取消' ? '已取消' : '失败'}</span>` : `<span class="pill blue">${j.state === 'queued' ? '排队中' : `${j.done}/${j.total}`}</span>`;
  return `<div class="rec" data-id="${esc(j.id)}"><div class="rec-h"><span class="rec-t" title="${esc(j.title)}">${esc(j.title)}</span>${st}<button type="button" class="pl-ib rec-x" data-rx title="不在此处显示" aria-label="不在此处显示">${ICON.x}</button></div>
    <div class="tiny rec-s">${esc([j.voice_name, modesText(j), j.duration ? fmtDur(j.duration) : '', running ? '' : j.finished ? fmtClock(j.finished - j.created) + ' 生成' : ''].filter(Boolean).join(' · '))}</div>
    ${running ? `<div class="progress"><div style="width:${pct}%"></div></div><div class="row rec-a"><span class="tiny">${esc(j.message)}</span>${jobTimer(j, 'sm')}<span class="spacer"></span><button type="button" class="btn small" data-rcancel>取消</button></div>`
      : j.has_output ? `${apHtml(`/media/job/${j.id}/output.mp3?t=${j.finished}`, 'job:' + j.id, { mini: true, title: j.title, sub: '配音成品' + (j.voice_name ? ' · ' + j.voice_name : ''), orb: j.voice, subs: 'job:' + j.id })}
        <div class="row rec-a"><button type="button" class="btn small ${j.saved ? '' : 'primary'}" data-rsave title="${j.saved ? '点击移出作品' : '保存到作品（可在播放页的“作品”中查看）'}">${j.saved ? '✓ 已保存' : '☆ 保存'}</button><a class="btn small" href="/media/job/${j.id}/output.mp3?dl=1" title="下载 MP3">MP3</a><a class="btn small" href="/media/job/${j.id}/output.wav?dl=1">WAV</a><span class="spacer"></span><button type="button" class="btn small ghost" data-ropen>详情</button></div>`
        : `<div class="row rec-a"><span class="tiny"${j.state === 'error' ? ' style="color:var(--red)"' : ''}>${esc(j.error || j.message)}</span><span class="spacer"></span><button type="button" class="btn small ghost" data-ropen>详情</button></div>`}</div>`;
};
async function recPaint() {
  const box = $('#rec-list'); if (!box) return [];
  const ids = S.ttsRec || [], gen = VGEN;
  const all = ids.length ? await api('/api/jobs').catch(() => null) : [];
  if (!all) return null;  // 这次没读到：下次再试（不当成“都生成完了”）
  if (!$('#rec-list') || gen !== VGEN) return [];
  const ids2 = S.ttsRec || [];  // 等待期间可能点了 × 或者又开始了一条：以现在的为准
  const map = new Map(all.map(j => [j.id, j])), list = ids2.filter(id => map.has(id) || !ids.includes(id)).map(id => map.get(id)).filter(Boolean);
  const gone = ids.filter(id => !map.has(id));
  if (gone.length) { S.ttsRec = ids2.filter(id => !gone.includes(id)); persist(); }  // 历史记录里已经删掉的：这里也拿掉
  const run = list.filter(j => ['queued', 'running'].includes(j.state)).length;
  $('#rec-n').textContent = list.length ? ` ${list.length}` : ''; $('#rec-n').classList.toggle('run', !!run);
  $('#rec-sum').textContent = list.length ? `${list.length} 条${run ? ` · ${run} 条在生成` : ''}` : '';
  $('#rec-clear').hidden = !list.length;
  if (!list.length) { box.innerHTML = '<div class="tiny rec-empty">生成的配音将显示在此处</div>'; box.dataset.sig = ''; return list; }
  // 只重画变了的那几条（正在听的那条不动，不打断播放）
  const have = new Map([...box.children].filter(c => c.dataset.id).map(c => [c.dataset.id, c]));
  [...box.children].forEach(c => { if (!c.dataset.id || !map.has(c.dataset.id) || !ids.includes(c.dataset.id)) c.remove(); });
  list.forEach((j, i) => {
    const sig = [j.state, j.done, j.message, j.saved, j.has_output, j.warn].join('|');
    let el = have.get(j.id);
    if (!el || (el.dataset.sig !== sig && !$('.ap.on', el))) {
      const tmp = document.createElement('div'); tmp.innerHTML = recRow(j); const nu = tmp.firstElementChild; nu.dataset.sig = sig;
      if (el) el.replaceWith(nu); el = nu; bindRec(el, j);
    }
    if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null);
  });
  return list;
}
function bindRec(el, j) {
  const q = s2 => el.querySelector(s2);
  q('[data-rx]').onclick = () => { S.ttsRec = (S.ttsRec || []).filter(x => x !== j.id); persist(); if (PB.a && el.contains(PB.a._el)) PB.a.pause(); el.remove(); recPaint(); };
  q('[data-ropen]') && (q('[data-ropen]').onclick = () => openWork(j.id));
  q('[data-rcancel]') && (q('[data-rcancel]').onclick = async e => { const b = e.currentTarget; b.disabled = true; b.textContent = '正在取消'; try { await api(`/api/jobs/${j.id}/cancel`, { body: {} }); } catch (er) { toast(er.message, true); b.disabled = false; b.textContent = '取消'; } recWatch(); });
  q('[data-rsave]') && (q('[data-rsave]').onclick = async e => {
    const b = e.currentTarget, now = b.dataset.saved ? b.dataset.saved === '1' : !!j.saved;  // 正在听的那条不重画：按钮自己记着现在的状态
    try { await api(`/api/jobs/${j.id}/save`, { body: { saved: !now } }); b.dataset.saved = now ? '0' : '1'; b.textContent = now ? '☆ 保存' : '✓ 已保存'; b.classList.toggle('primary', now); toast(now ? '已移出作品' : '已保存到作品'); } catch (er) { toast(er.message, true); } recWatch(); });
}
function recWatch() {  // 有正在生成的就每 1.2 秒刷新一次，全部结束就停
  if (!$('#rec-list')) return;
  pollStart(async stop => { const list = await recPaint(); if (!$('#rec-list')) return stop(); if (list && !list.some(j => ['queued', 'running'].includes(j.state))) stop(); }, 1200);
}

/* 配音页：文字框的高度跟着窗口变，让“试听 / 开始生成”那一排始终露在播放条上面。
   窗口矮就短一些（最矮 180），窗口高就长一些；工具栏换行、展开抽屉时也会重新算。
   再矮、或者上面展开了抽屉放不下时，按钮那一排贴在播放条上面（跟着页面滚动停住），不会被挡住。 */
let fitRO = null;
function fitScript() {
  const ta = $('#script'), card = ta?.closest('.card'); if (!ta || !ta.offsetParent) return;
  const pb = $('#pbar'), limit = (pb && pb.offsetHeight ? pb.offsetTop : innerHeight) - 16;  // offsetTop：不受收起动画的位移影响（收起 / 展开播放条时正文框不再变大变小）
  const cur = ta.offsetHeight, bottom = card.getBoundingClientRect().bottom + scrollY;  // 页面在最顶上时，卡片底边的位置
  const h = Math.max(180, Math.round(cur + limit - bottom));
  if (Math.abs(h - cur) > 1) ta.style.height = h + 'px';
  card.style.setProperty('--foot-b', Math.round(innerHeight - limit - 14) + 'px');  // 实在放不下时，按钮那一排贴在播放条上面
  const side = $('.grid-tts > .side-col');  // 右边（设置 / 记录）：底边和左边对齐，内容多了在里面滚，整页不会多出一截要滚
  if (side) side.style.maxHeight = MOB() ? '' : Math.max(260, Math.round(limit - (side.getBoundingClientRect().top + scrollY))) + 'px';
}
function bindFitScript() {
  fitRO?.disconnect();
  const ta = $('#script'), card = ta?.closest('.card'); if (!ta) return;
  let raf = 0;
  fitRO = new ResizeObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; fitScript(); }); });
  [...card.children].filter(x => x !== ta).forEach(x => fitRO.observe(x));
  fitScript();
}
addEventListener('resize', fitScript);

function refreshModeUI() {
  const md = mode();
  const cls = { clone: 'green', direct: 'blue', design: 'purple', preset: 'blue', none: 'orange' }[md];
  const pill = `<span class="pill ${cls}">${MODE_NAME[md]}</span>`;
  if ($('#dir-pill')) $('#dir-pill').innerHTML = pill;
  const ins = instructText(), v = curVoice(), pr = curPreset();
  if ($('#now')) {
    const id = v ? v.id : pr ? 'preset' + pr : null;
    const who = v ? esc(v.name) : pr ? esc(presetName(pr)) : (md === 'design' ? '音色设计（按描述生成）' : '未选择音色');
    const html = `<div style="min-width:0;flex:1"><div class="who">${who}</div>
      <div class="tiny" style="margin-top:4px">${pill} <span style="margin-left:4px">${esc(curModel()?.display_name)}</span></div>
      ${ins && md !== 'clone' ? `<div class="tiny" style="margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">“${esc(ins)}”</div>` : ''}</div>`;
    if ($('#now').dataset.html !== html) { $('#now').innerHTML = html; $('#now').dataset.html = html; }
  }
  if ($('#voice-sum')) $('#voice-sum').innerHTML = v ? `${vav(v.id, 'sm', '', v.name)}${esc(v.name)}` : pr ? `${vav('preset' + pr, 'sm', '', presetName(pr))}${esc(presetName(pr))}` : '未选择';
}
const presetName = id => (profile().presets || []).find(p => p.id === id)?.name || id;

/* 工具栏：根据模型能力显示声音事件 / 读音标注 / 段落语气 */
function toolbarHtml() {
  const ev = profile().events || {}, parts = [];
  parts.push(`<button class="chip ins-tool" id="pause-btn" title="在光标处插入一段精确时长的静音，所有模型通用">⏸ 停顿</button>`);
  if (dirKind() !== 'none') parts.push(`<button class="chip ins-tool" id="para-dir" title="在本段开头插入语气指令。适用于 Breeze TTS 2、IndexTTS-2.5；Qwen3-TTS 仅限音色设计与预设音色">${ICON.wand}段落语气</button>`);
  if (ev.pronunciation) parts.push(`<button class="chip ins-tool" id="pron" title="仅 IndexTTS-2.5 可用：用 <字|拼音> 指定读音">${ICON.wand}读音</button>`);
  if ((ev.official || []).length) parts.push(`<span class="ins-sep"></span><button class="chip ins-tool" id="ev-toggle" title="插入笑、叹气等声音事件">声音事件 ▾</button>`);
  return `<span class="ins-l">插入标记</span>` + parts.join('');
}
function bindToolbar(ta) {
  $$('[data-tag]').forEach(b => b.onclick = () => insertAtCursor(ta, b.dataset.tag));
  if ($('#more-ev')) $('#more-ev').onclick = moreEvents;
  if ($('#ev-toggle')) $('#ev-toggle').onclick = () => {
    const ev = profile().events || {};
    drawer('ev-toggle', `<div class="chips">${(ev.official || []).map(e => `<button class="chip" data-evi="${esc(e.tag)}">${esc(e.label)}</button>`).join('')}${(ev.experimental || []).length ? '<button class="chip exp" id="ev-more">更多…</button>' : ''}</div>`, box => {
      $$('[data-evi]', box).forEach(b => b.onclick = () => insertAtCursor(ta, b.dataset.evi));
      if ($('#ev-more', box)) $('#ev-more', box).onclick = moreEvents;
    });
  };
  if ($('#pron')) $('#pron').onclick = () => pronDialog(ta);
  if ($('#para-dir')) $('#para-dir').onclick = () => paraDirectionDialog(ta);
  if ($('#pause-btn')) $('#pause-btn').onclick = () => drawer('pause-btn', `<div class="label" style="margin-bottom:4px">插入停顿</div>
    <div class="card-sub">网页会在此处切分文字，插入一段真实的静音（时长精确，所有模型通用，标记本身不会被朗读）。</div>
    <div class="chips">${[0.3, 0.5, 0.8, 1, 1.5, 2, 3].map(x => `<button class="chip" data-ps="${x}">${x} 秒</button>`).join('')}</div>
    <div class="row" style="margin-top:12px"><input class="input" id="ps-n" type="number" step="0.1" min="0.1" placeholder="自定义秒数" style="width:140px"><button class="btn primary" id="ps-ok">插入</button><span class="spacer"></span><button class="btn" data-close>取消</button></div>`, box => {
    const ins = v => { insertAtCursor(ta, `[停顿 ${v}秒]`); box.close(); };
    $$('[data-ps]', box).forEach(b => b.onclick = () => ins(b.dataset.ps));
    $('#ps-ok', box).onclick = () => { const v = parseFloat($('#ps-n', box).value); if (v > 0) ins(v); };
  });
}
function moreEvents() {
  const ev = profile().events;
  drawer('more-ev', `<div class="label" style="margin-bottom:4px">更多声音事件</div>
    <p class="help">${esc(ev.note)}</p>
    <div class="sec-label">官方列出的</div><div class="chips">${ev.official.map(e => `<button class="chip" data-ins="${esc(e.tag)}">${esc(e.label)} <span class="k">${esc(e.tag)}</span></button>`).join('')}</div>
    <div class="sec-label">可尝试的（实验性）</div><div class="chips">${(ev.experimental || []).map(e => `<button class="chip exp" data-ins="${esc(e.tag)}">${esc(e.label)} <span class="k">${esc(e.tag)}</span></button>`).join('')}</div>
    <div class="sec-label">自定义</div><div class="row"><input class="input" id="custom-tag" placeholder="例如：打喷嚏" style="flex:1"><button class="btn primary" id="ins-custom">插入</button></div>
`, box => {
    const ta = $('#script');
    $$('[data-ins]', box).forEach(b => b.onclick = () => insertAtCursor(ta, b.dataset.ins));
    $('#ins-custom', box).onclick = () => { const v = $('#custom-tag', box).value.trim(); if (v) insertAtCursor(ta, `[${v.replace(/[\[\]]/g, '')}]`); };
  });
}
function pronDialog(ta) {
  const sel = ta.value.slice(ta.selectionStart, ta.selectionEnd).trim();
  drawer('pron', `<div class="label" style="margin-bottom:4px">标注读音</div>
    <div class="card-sub">${esc(profile().events?.note || '')}</div>
    <div class="field"><span class="label">要标注的字或词</span><input class="input" id="pr-w" value="${esc(sel)}" placeholder="在文本中选中后再点击按钮，将自动填入"></div>
    <div class="field"><span class="label">读音（拼音 + 声调数字，空格分隔）</span><input class="input" id="pr-p" placeholder="例如：yin2 hang2"></div>
    <div class="row" style="justify-content:flex-end"><button class="btn" data-close>取消</button><button class="btn primary" id="pr-ok">插入</button></div>`, box => {
    $('#pr-ok', box).onclick = () => {
      const w = $('#pr-w', box).value.trim(), p = $('#pr-p', box).value.trim();
      if (!w || !p) return toast('请填写字词和读音', true);
      insertAtCursor(ta, `<${w}|${p}>`); box.close();
    };
  });
}
function insertAtCursor(ta, s) {
  const a = ta.selectionStart, b = ta.selectionEnd;
  ta.value = ta.value.slice(0, a) + s + ta.value.slice(b);
  ta.focus(); ta.selectionStart = ta.selectionEnd = a + s.length; ta.oninput();
}
function paraDirectionDialog(ta) {
  const p = profile().director;
  const pos = ta.selectionStart, start = ta.value.lastIndexOf('\n', pos - 1) + 1;
  const line = ta.value.slice(start).split('\n')[0];
  const m = line.match(/^\s*[{｛]([^}｝]*)[}｝]\s*/);
  const quick = p.kind === 'emotion' ? p.emotions.map(e => e.text) : p.emotions.flatMap(e => [e.levels[1], e.levels[2]]).concat(p.styles || []);
  drawer('para-dir', `<div class="label" style="margin-bottom:4px">段落语气</div>
    <div class="card-sub">仅作用于光标所在的段落：「${esc(line.replace(/^\s*[{｛][^}｝]*[}｝]\s*/, '').slice(0, 30))}…」${p.kind === 'emotion' ? '<br>IndexTTS 会将此处的文字作为情绪描述。' : ''}</div>
    <textarea class="textarea" id="pd" rows="2" placeholder="例如：委屈得快哭了，小声地说">${esc(m ? m[1] : '')}</textarea>
    <div class="sec-label">快捷</div>
    <div class="chips">${quick.map(t => `<button class="chip" data-q="${esc(t)}">${esc(t)}</button>`).join('')}</div>
    <div class="row" style="justify-content:flex-end;margin-top:18px">${m ? '<button class="btn danger" id="pd-rm">移除</button>' : ''}<div class="spacer"></div><button class="btn" data-close>取消</button><button class="btn primary" id="pd-ok">确定</button></div>`, box => {
    const inp = $('#pd', box);
    $$('[data-q]', box).forEach(b => b.onclick = () => { inp.value = inp.value ? inp.value.replace(/，?$/, '，') + b.dataset.q : b.dataset.q; });
    const apply = txt => {
      const rest = line.replace(/^\s*[{｛][^}｝]*[}｝]\s*/, '');
      let at = start;  // 打开以后又改过文字：按这一段的内容重新找它在哪
      if (ta.value.slice(at, at + line.length) !== line || (at > 0 && ta.value[at - 1] !== '\n')) {
        const lines = ta.value.split('\n'); let pos = 0; at = -1;
        for (const l of lines) { if (l === line) { at = pos; break; } pos += l.length + 1; }
        if (at < 0) { box.close(); return toast('该段已修改，请将光标放回该段后再次点击', true); }
      }
      ta.value = ta.value.slice(0, at) + (txt ? `{${txt}}` + rest : rest) + ta.value.slice(at + line.length); ta.oninput(); box.close();
    };
    $('#pd-ok', box).onclick = () => apply(inp.value.trim().replace(/[{}｛｝]/g, ''));
    if (m) $('#pd-rm', box).onclick = () => apply('');
  });
}
const NOSPLIT_MAX = 450;  // 关闭智能分段时，单段最多字数（Breeze 单次生成上限约 120 秒）
const effMaxlen = () => S.job.split === false ? NOSPLIT_MAX : S.job.maxlen;
function updateStat() {
  const t = S.text, chars = t.replace(/\s/g, '').length;
  const n = splitPreview(t, effMaxlen());
  const longParas = S.job.split === false ? t.split(/\n+/).filter(p => p.replace(/\s/g, '').length > NOSPLIT_MAX).length : 0;
  $('#stat').innerHTML = `<span><b>${chars}</b> 字</span><span>约 <b>${fmtDur(chars / 4.3)}</b></span><span>${S.job.split === false ? '按自然段' : '将分成'} <b>${n}</b> 段生成</span>${longParas ? `<span style="color:var(--orange)">${longParas} 个段落超过 ${NOSPLIT_MAX} 字，仍会在句号处切分</span>` : ''}<span class="spacer"></span><span>预计用时约 ${fmtDur(chars / 4.3 * 0.75 + n * 1.5)}</span>`;
}

function renderVoicePick() {
  const box = $('#voice-pick'), r = roles(), prof = profile();
  let html = '';
  if (r.design) html += `<div class="vp ${!S.voice ? 'on' : ''}" data-v="">${vav(null, '', '', '无')}<div class="nm">不使用音色</div><div class="tiny" style="margin-top:-6px">按描述生成</div></div>`;
  if (r.clone) html += voices.map(v => `<div class="vp ${v.id === S.voice ? 'on' : ''}" data-v="${v.id}" title="${esc(v.description || v.transcript)}">
      <button class="play" data-play="v:${v.id}" data-url="${v.url}" title="试听" aria-label="试听">${ICON.play}</button>${vav(v.id, '', 'v:' + v.id, v.name)}<div class="nm">${esc(v.name)}</div></div>`).join('') +
    `<a class="vp" href="/voices" data-page="voices"><div class="orb none" style="display:grid;place-items:center;color:var(--blue)">${ICON.plus}</div><div class="nm" style="color:var(--blue)">新建音色</div></a>`;
  if (r.preset) html += `<div style="grid-column:1/-1" class="sec-label">官方预设音色</div>` + (prof.presets || []).map(p => `<div class="vp ${S.voice === 'preset:' + p.id ? 'on' : ''}" data-v="preset:${p.id}" title="${esc(p.desc)}">${vav('preset' + p.id, '', '', p.name)}<div class="nm">${esc(p.name)}</div></div>`).join('');
  box.innerHTML = html || '<div class="tiny">当前模型没有可选的音色方式。</div>';
  $$('.vp[data-v]', box).forEach(el => el.onclick = e => {
    if (e.target.closest('.play')) return;
    S.voice = el.dataset.v || null; persist(); renderVoicePick(); renderDirector(); renderAdv();
    setTimeout(() => toggleDetails($('#voice-box'), false), 200);
  });
  $$('.play', box).forEach(b => b.onclick = e => { e.stopPropagation(); togglePlay(b.dataset.play, b.dataset.url); });
  if (S.voice && !curPreset() && !r.clone) S.voice = null;
}

function renderDirector() {
  const el = $('#director'), m = curModel(), p = profile().director, modes = profile().modes || {};
  const md = mode(), d = S.dir;
  const note = md === 'none' ? (curVoice() ? '当前模型不支持此用法，请更换模型。' : roles().design ? '请选择一个音色，或在下方描述所需的声音（将使用音色设计）。' : '请先选择一个音色。') : (modes[md] || '');
  const qwenCloneLocked = m?.family === 'qwen3_tts' && curVoice();
  const ni = note.search(/[：:]/), noteHtml = md !== 'none' && ni > 0 ? `<b>${esc(note.slice(0, ni))}</b>${hintHtml(esc(note.slice(ni + 1)), 'sm')}` : esc(note);
  let body = `<div class="mode-banner"><div class="tiny">${noteHtml}${md === 'design' ? '<br><b style="color:var(--orange)">提示：</b>长文本建议先在“音色库”中将满意的声音保存为音色后再使用，以确保全文音色一致。' : ''}</div></div>`;
  if (!p || qwenCloneLocked) {
    el.innerHTML = body + (qwenCloneLocked ? '<div class="help keep">Qwen3-TTS 的官方克隆模型（Base）不接受语气指令。如需改变克隆声音的语气，请切换到 Breeze TTS 2 或 IndexTTS-2.5。</div>' : '<div class="help keep">当前模型没有语气控制参数。</div>');
    refreshModeUI(); return;
  }
  const presetsOpen = S.ui?.presetsOpen ?? !!(d.emotion || d.styles.length || d.pace || d.useVector);
  body += `<details class="adv" id="presets" ${presetsOpen ? 'open' : ''} style="margin-bottom:4px"><summary style="font-size:14px">${ICON.chev}快捷预设</summary>`;
  body += `<div class="sec-label">情绪</div><div class="chips">${p.emotions.map(e => `<button class="chip ${d.emotion === e.key ? 'on' : ''}" data-emo="${e.key}">${e.key}</button>`).join('')}</div>`;
  if (d.emotion && !(p.kind === 'emotion' && d.useVector)) body += `<div style="margin-top:12px"><input type="range" min="0" max="2" step="1" value="${d.level}" id="lvl"><div class="levels"><span>轻微</span><span>明显</span><span>强烈</span></div></div>`;
  if (p.kind === 'emotion') {
    body += `<div class="row between" style="margin-top:14px"><span class="sec-label" style="margin:0">精确调配 8 种情绪</span><label class="switch"><input type="checkbox" id="use-vec" ${d.useVector ? 'checked' : ''}><span></span></label></div>`;
    if (d.useVector) body += `<div style="display:grid;grid-template-columns:56px 1fr 36px;gap:6px 10px;align-items:center;margin-top:8px">${p.vector_labels.map((l, i) => `<span class="tiny">${l}</span><input type="range" min="0" max="1" step="0.05" value="${d.vector[i] || 0}" data-vec="${i}"><span class="tiny" id="vv${i}">${(d.vector[i] || 0).toFixed(2)}</span>`).join('')}</div>`;
  } else {
    body += `<div class="sec-label">表演方式（可多选）</div><div class="chips">${(p.styles || []).map(s => `<button class="chip ${d.styles.includes(s) ? 'on' : ''}" data-sty="${esc(s)}">${esc(s)}</button>`).join('')}</div>`;
    if ((p.paces || []).length) body += `<div class="sec-label">语速</div><div class="seg full">${p.paces.map(x => `<button class="${d.pace === x.text ? 'on' : ''}" data-pace="${esc(x.text)}">${x.label}</button>`).join('')}</div>`;
  }
  body += `</details>`;
  if (p.kind === 'emotion' && curVoice()) {
    const a = +(d.alpha ?? p.levels?.[d.level] ?? 0.6);
    body += `<div class="row between" style="margin-top:10px"><span class="sec-label" style="margin:0">情绪跟随正文${hintHtml('未填写情绪描述时，根据每段正文自动推断情绪；长稿无需逐段填写情绪。', 'sm')}</span><label class="switch"><input type="checkbox" id="emo-auto" ${d.autoEmo ? 'checked' : ''}><span></span></label></div>
      <div class="row emo-a-row" style="gap:10px;align-items:center;margin-top:8px"${md === 'direct' ? '' : ' hidden'}><span class="sec-label" style="margin:0;white-space:nowrap">情绪强度${hintHtml('情绪混合进声音的程度（emotion_alpha，0~1）。官方建议文字情绪用 0.6。', 'sm')}</span><input type="range" min="0" max="1" step="0.05" id="emo-a" value="${a}" style="flex:1;min-width:0"><b class="tiny" id="emo-a-v" style="min-width:32px;text-align:right">${a.toFixed(2)}</b></div>`;
  }
  body += `<div class="sec-label">${p.kind === 'emotion' ? '情绪描述' : !S.voice ? '音色描述 / 补充指令' : '补充指令'}${p.tips ? hintHtml(esc(p.tips), 'sm') : ''}</div>
    <textarea class="textarea" id="extra" rows="2" placeholder="${p.kind === 'emotion' ? '例如：你吓死我了！你是鬼吗？' : S.voice ? '例如：说到“等等”时突然压低声音' : '例如：一位温柔的年轻女性，声音清晰'}">${esc(d.extra)}</textarea>
    <div class="help keep" style="margin-top:8px">最终发给模型的${p.kind === 'emotion' ? '情绪' : '指令'}：<b id="final-ins" style="color:var(--text)"></b></div>
    <div class="row" style="margin-top:10px;justify-content:flex-end"><button class="btn small ghost" id="dir-reset">清除</button></div>`;
  el.innerHTML = body;
  $('#presets', el).ontoggle = e => { S.ui = { ...(S.ui || {}), presetsOpen: e.target.open }; persist(); };
  const showFinal = () => {
    const v = emotionVector();
    $('#final-ins').textContent = v ? '情绪向量 ' + v.map(x => x.toFixed(2)).join(' / ') : (instructText() || (emotionAuto() ? '（跟随正文自动推断）' : '（无，使用纯克隆）'));
    const ar = $('.emo-a-row', el); if (ar) ar.hidden = mode() !== 'direct';
    refreshModeUI();
  };
  const rerender = () => { persist(); renderDirector(); renderAdv(); };
  $$('[data-emo]', el).forEach(b => b.onclick = () => { d.emotion = d.emotion === b.dataset.emo ? '' : b.dataset.emo; rerender(); });
  $$('[data-sty]', el).forEach(b => b.onclick = () => { const s = b.dataset.sty; d.styles = d.styles.includes(s) ? d.styles.filter(x => x !== s) : [...d.styles, s]; rerender(); });
  $$('[data-pace]', el).forEach(b => b.onclick = () => { d.pace = b.dataset.pace; rerender(); });
  const lvl = $('#lvl', el); if (lvl) lvl.oninput = () => { d.level = +lvl.value; if (p.kind === 'emotion' && p.levels?.[d.level] != null) { d.alpha = p.levels[d.level]; const ea = $('#emo-a', el); if (ea) { ea.value = d.alpha; $('#emo-a-v', el).textContent = (+d.alpha).toFixed(2); } } persist(); showFinal(); renderAdv(); };
  const ea = $('#emo-a', el); if (ea) ea.oninput = () => { d.alpha = +ea.value; $('#emo-a-v', el).textContent = (+ea.value).toFixed(2); persistSoon(); };
  const eauto = $('#emo-auto', el); if (eauto) eauto.onchange = () => { d.autoEmo = eauto.checked; rerender(); };
  const uv = $('#use-vec', el); if (uv) uv.onchange = () => {
    d.useVector = uv.checked;
    // 打开精确调配时，用已选的情绪预填对应的那一维，免得从全 0 开始
    const idx = { 开心: 0, 生气: 1, 悲伤: 2, 委屈: 2, 害怕: 3, 厌恶: 4, 惊讶: 6, 平静: 7 }[d.emotion];
    if (d.useVector && idx !== undefined && !(d.vector || []).some(x => x > 0)) { d.vector = [0, 0, 0, 0, 0, 0, 0, 0]; d.vector[idx] = [0.4, 0.6, 0.9][d.level] ?? 0.6; }
    rerender();
  };
  $$('[data-vec]', el).forEach(r => r.oninput = () => { d.vector[+r.dataset.vec] = +r.value; $('#vv' + r.dataset.vec).textContent = (+r.value).toFixed(2); persistSoon(); showFinal(); });
  const ex = $('#extra', el);
  ex.oninput = () => { d.extra = ex.value; persistSoon(); showFinal(); };
  ex.onchange = () => { renderDirector(); renderAdv(); };
  $('#dir-reset', el).onclick = () => { S.dir = { emotion: '', level: 1, styles: [], pace: '', extra: '', useVector: false, vector: [0, 0, 0, 0, 0, 0, 0, 0] }; rerender(); };
  showFinal();
}

/* 当前模式下由网页按官方建议设置的参数默认值 */
function modeDefault(name) {
  const m = curModel(), d = profile().defaults || {}, md = mode();
  if (m?.family === 'breeze_tts' && name === 'guidance_scale') return md === 'clone' ? 0 : (d[md + '_guidance'] ?? 4);
  if (m?.family === 'index_tts2' && name === 'emotion_alpha') return md === 'direct' ? (S.dir.alpha ?? profile().director?.levels?.[S.dir.level] ?? d.direct_emotion_alpha ?? 0.6) : null;
  return undefined;
}

/* 自动核对的三个设置（配音、换声共用）：开关、通过标准（准确率 ≥ X% 就不重做）、最多重做几次 */
function checkOptsHtml(attr, st, defPass, title, help) {
  const pass = st.pass ?? defPass, retries = st.retries ?? 2;
  return `<div class="opt"><div class="row between"><span class="label">${title}</span><label class="switch"><input type="checkbox" data-${attr}="check" ${st.check !== false ? 'checked' : ''}><span></span></label></div>
    <div class="help" style="margin-top:6px">${help}</div>
    <div class="check-sub" ${st.check === false ? 'hidden' : ''}>
      <div class="head" style="margin-top:12px"><span class="label">通过标准：准确率 ≥ <b data-show="pass">${pass}</b>%</span><span class="def">默认 ${defPass}%</span></div>
      <div class="range-row"><input type="range" min="50" max="100" step="1" value="${pass}" data-${attr}="pass"><input class="input" type="number" min="50" max="100" step="1" value="${pass}" data-${attr}="pass"></div>
      <div class="help" style="margin-top:4px">达到此准确率即不再重做。设为 100% 最严格（语气夸张或口语较多时容易反复重做），调低可节省时间。</div>
      <div class="head" style="margin-top:12px"><span class="label">最多重做次数</span><span class="def">默认 2</span></div>
      <div class="range-row"><input type="range" min="0" max="5" step="1" value="${retries}" data-${attr}="retries"><input class="input" type="number" min="0" max="5" step="1" value="${retries}" data-${attr}="retries"></div>
      <div class="help" style="margin-top:4px">0 表示仅核对并标出可疑内容，不自动重做。每增加一次，将多耗费一次生成时间。</div>
    </div></div>`;
}

/* 高级参数：完全由 audio.cpp 官方 model_spec 自动生成，换模型也能用 */
/* 高级参数：常用的放上面，其余收进“更多参数”（点开 / 收起会记住，每个页面各记各的） */
function advMore(key, n, inner) {
  const open = !!(S.ui?.advMore || {})[key];
  return `<details class="adv-more" data-more="${key}"${open ? ' open' : ''}><summary><span>更多参数</span>${n ? `<span class="tiny">${n} 项</span>` : ''}${ICON.chev}</summary><div class="adv-more-b">${inner}</div></details>`;
}
function advMoreBind(root) {
  $$('details[data-more]', root).forEach(d => d.ontoggle = () => { S.ui = { ...(S.ui || {}), advMore: { ...(S.ui?.advMore || {}), [d.dataset.more]: d.open } }; persist(); });
}
/* 已经画好的面板：把不常用的块搬进“更多参数”（块 = 选择器对应元素向上找到的 .field / .ig-2 / 小节） */
function advFoldDom(root, key, moreSels, label) {
  const blocks = []; moreSels.forEach(sel => { const el = typeof sel === 'string' ? root.querySelector(sel) : sel; if (el && !blocks.includes(el)) blocks.push(el); });
  if (!blocks.length) return;
  const host = document.createElement('div'); host.innerHTML = advMore(key, label ?? '', ''); const d = host.firstElementChild, b = $('.adv-more-b', d);
  blocks.forEach(el => b.append(el));
  d.classList.add('cols'); root.append(d); advMoreBind(root);
  const rs = root.querySelector('#ig-reset, #va-reset')?.closest('.row'); if (rs) root.append(rs);  // “全部恢复默认”放在最下面
  $$('.ig-sec', root).forEach(h => { let n = h.nextElementSibling; if (!n || n.classList.contains('ig-sec') || n.classList.contains('adv-more')) if (!h.querySelector('input')) h.remove(); });  // 搬空了的小节标题
}
function renderAdv(target) {
  const body = target || $('#adv-body'); if (!body) return;
  const setCount = t => { if ($('#adv-count')) $('#adv-count').textContent = t; };
  const m = curModel(); if (!m) return;
  refreshModeUI();
  const prof = m.profile, zh = prof.options_zh || {}, hidden = new Set(prof.hidden_options || []);
  const md = mode();
  const opts = m.options.filter(o => !hidden.has(o.name) && o.name !== 'seed' && !(o.name === 'x_vector_only_mode' && md !== 'clone'));
  const posMin = o => /temperature/.test(o.name) || o.name === 'duration_scale' ? 0.05 : o.name === 'top_p' ? 0.01 : null;  // 引擎要求大于 0：拖到 0 会整段失败
  const changed = Object.keys(S.adv).filter(k => S.adv[k] !== undefined && opts.some(o => o.name === k)).length;
  const COMMON = new Set(['temperature', 'guidance_scale', 'duration_scale', 'language', 'use_random_emotion', 'x_vector_only_mode', 'emotion_alpha', 'speed']);
  const optsA = opts.filter(o => COMMON.has(o.name)), optsB = opts.filter(o => !COMMON.has(o.name));
  setCount(changed ? `已修改 ${changed} 项` : '全部为官方默认');
  const optHtml = o => {
    const z = zh[o.name] || {}, v = S.adv[o.name];
    const md0 = modeDefault(o.name);
    const def = md0 !== undefined && md0 !== null ? md0 : o.default;
    const dis = m.family === 'breeze_tts' && o.name === 'guidance_scale' && md === 'clone';
    const val = v ?? def ?? '';
    let ctl;
    if (o.type === 'bool') ctl = `<label class="switch"><input type="checkbox" data-opt="${o.name}" ${(v ?? def) ? 'checked' : ''}><span></span></label>`;
    else if (o.type === 'enum') ctl = `<select class="select" data-opt="${o.name}">${(o.values || []).map(x => `<option ${String(val) === String(x) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
    else if (o.type === 'float' || o.type === 'int') {
      const lo = Math.max(o.min ?? 0, posMin(o) ?? -Infinity), hi = o.max ?? (o.name.includes('temperature') ? 2 : o.name === 'guidance_scale' ? 8 : o.name.includes('top_p') ? 1 : o.name === 'duration_scale' ? 2 : null);
      const step = o.type === 'int' ? 1 : 0.05;
      ctl = hi != null && o.type === 'float'
        ? `<div class="range-row"><input type="range" min="${lo}" max="${hi}" step="${step}" value="${val}" data-opt="${o.name}" data-t="${o.type}" data-min="${lo}" ${dis ? 'disabled' : ''}><input class="input" type="number" step="${step}" min="${lo}" value="${val}" data-opt="${o.name}" data-t="${o.type}" data-min="${lo}" ${dis ? 'disabled' : ''}></div>`
        : `<input class="input" type="number" step="${step}" value="${val}" data-opt="${o.name}" data-t="${o.type}"${posMin(o) != null ? ` min="${lo}" data-min="${lo}"` : ''} ${dis ? 'disabled' : ''}>`;
    } else ctl = `<input class="input" value="${esc(val)}" data-opt="${o.name}">`;
    let extra = '';
    if (m.family === 'breeze_tts' && o.name === 'guidance_scale') extra = md === 'clone' ? '纯克隆模式：网页自动设为 0（还原官方纯克隆提示），此项不生效。' : `当前模式默认 ${def}（官方推荐）。`;
    return `<div class="opt"><div class="head"><span class="label" title="${esc(o.name)}">${esc(z.label || o.name)}</span><span class="def">默认 ${esc(def ?? '—')}${v !== undefined ? ` · <a href="#" data-reset="${o.name}">恢复</a>` : ''}</span></div>${ctl}
      <div class="help" style="margin-top:6px">${esc(z.help || o.description || '')}${extra ? '<br>' + esc(extra) : ''}</div></div>`;
  };
  body.innerHTML = `
    <div class="sec-label" style="margin-top:0">模型参数 · ${esc(m.display_name)}</div>
    <div class="help" style="margin-bottom:6px">这些参数根据引擎的官方说明自动生成，默认值即官方默认值，不修改即为原版效果。</div>
    <div class="opt"><div class="head"><span class="label" title="seed">随机种子</span><span class="def">默认 123</span></div>
      <div class="row"><input class="input" type="number" id="seed" value="${S.seed}" style="flex:1"><button class="btn small" id="seed-rand">随机</button></div>
      <div class="help" style="margin-top:6px">${esc(zh.seed?.help || '')}</div></div>
    ${target ? '<div class="adv-grid">' : ''}${optsA.map(optHtml).join('')}${target ? '</div>' : ''}
    <div class="sec-label">长文本</div>
    <div class="opt"><div class="head"><span class="label">句间停顿（秒）</span><span class="def">默认 0.35</span></div>
      <div class="range-row"><input type="range" min="0" max="1.5" step="0.05" value="${S.job.pause}" data-job="pause"><input class="input" type="number" step="0.05" value="${S.job.pause}" data-job="pause"></div>
      <div class="help" style="margin-top:6px">同一段落中被切分的两块之间的停顿。网页会先去除每块首尾多余的静音，再加入此停顿。</div></div>
    <div class="opt"><div class="head"><span class="label">段落停顿（秒）</span><span class="def">默认 0.8</span></div>
      <div class="range-row"><input type="range" min="0" max="3" step="0.1" value="${S.job.pause_para}" data-job="pause_para"><input class="input" type="number" step="0.1" value="${S.job.pause_para}" data-job="pause_para"></div></div>
    ${checkOptsHtml('job', S.job, 80, '自动核对并重做读错的段', '每段生成后通过语音识别与原文比对；准确率未达到“通过标准”（漏读、错读）时更换种子自动重做。不改变声音本身，仅挑选更准确的结果；多次重做仍未通过时，保留最佳结果并标记为“建议检查”。')}
    ${advMore('tts', optsB.length + 1 + (['breeze_tts', 'qwen3_tts'].includes(m.family) ? 1 : 0), `${target ? '<div class="adv-grid">' : ''}${optsB.map(optHtml).join('')}${target ? '</div>' : ''}
    <div class="opt"><div class="head"><span class="label">每段最长字数</span><span class="def">默认 200</span></div>
      <div class="range-row"><input type="range" min="60" max="400" step="10" value="${S.job.maxlen}" data-job="maxlen"><input class="input" type="number" value="${S.job.maxlen}" data-job="maxlen"></div>
      <div class="help" style="margin-top:6px">网页优先将整个自然段一次生成，段落超过此字数时才在句号处切分，因此语气连贯；每段均使用同一参考音色，音色不会漂移。字数越多越连贯，但单段出错的概率也越高（会由自动核对发现并重做）。</div></div>
    ${['breeze_tts', 'qwen3_tts'].includes(m.family) ? `<div class="sec-label">性能（重新载入模型后生效）</div><div id="tts-perf" class="tts-perf"><div class="tiny">读取中…</div></div>` : ''}
`)}
    <div class="row" style="justify-content:flex-end;margin-top:8px"><button class="btn small" id="adv-reset">全部恢复默认</button></div>`;
  advMoreBind(body);
  $$('[data-opt]', body).forEach(inp => {
    const name = inp.dataset.opt;
    inp.oninput = inp.onchange = ev => {
      let v = inp.type === 'checkbox' ? inp.checked : inp.value;
      if (inp.dataset.t === 'int') v = parseInt(v, 10); else if (inp.dataset.t === 'float') v = parseFloat(v);
      if (Number.isNaN(v)) return;
      if (inp.dataset.min && v < +inp.dataset.min) { if (ev?.type === 'input' && inp.type === 'number') return; v = +inp.dataset.min; inp.value = v; }  // 输入 0 等非法值：输完按下限算
      S.adv[name] = v; persist();
      $$(`[data-opt="${name}"]`, body).forEach(o => { if (o !== inp && o.type !== 'checkbox') o.value = v; });
      setCount('已修改');
    };
  });
  $$('[data-reset]', body).forEach(a => a.onclick = e => { e.preventDefault(); delete S.adv[a.dataset.reset]; persist(); renderAdv(target); });
  $$('[data-job]', body).forEach(inp => {
    const k = inp.dataset.job;
    inp.oninput = inp.onchange = () => {
      S.job[k] = inp.type === 'checkbox' ? inp.checked : parseFloat(inp.value); persist();
      $$(`[data-job="${k}"]`, body).forEach(o => { if (o !== inp && o.type !== 'checkbox') o.value = inp.value; });
      $$(`[data-show="${k}"]`, body).forEach(o => o.textContent = inp.value);
      if (k === 'check') $$('.check-sub', body).forEach(s => s.hidden = !inp.checked);
      updateStat();
    };
  });
  $('#seed', body).oninput = e => { S.seed = parseInt(e.target.value || '0', 10); persistSoon(); };
  $('#seed-rand', body).onclick = () => { S.seed = Math.floor(Math.random() * 99999); $('#seed', body).value = S.seed; persist(); };
  if ($('#tts-perf', body)) ttsPerf($('#tts-perf', body), m.family);
  $('#adv-reset', body).onclick = () => { S.adv = {}; S.seed = 123; S.job = { maxlen: 200, pause: 0.35, pause_para: 0.8, check: true, retries: 2, split: S.job.split }; persist(); renderAdv(target); if (target) renderAdv(); updateStat(); };
}

/* 配音引擎的会话参数：性能模式（Breeze / Qwen3）、Qwen3 的 LoRA。写进引擎配置，引擎空闲时马上重启生效 */
async function ttsPerf(box, fam) {
  let o;
  try { o = await api('/api/tts/engine-opts'); } catch (e) { box.innerHTML = `<div class="tiny">${esc(e.message)}</div>`; return; }
  if (!box.isConnected) return;
  const seg = (k, list) => `<div class="seg full" data-po="${k}">${list.map(([v, n]) => `<button type="button" data-v="${v}" class="${String(o[k]) === v ? 'on' : ''}">${n}</button>`).join('')}</div>`;
  box.innerHTML = fam === 'breeze_tts'
    ? `<div class="opt"><div class="head"><span class="label">解码方式${hintHtml('加速：将有条件 / 无条件两路合并为一次批量解码，速度明显提升；音质等价，但与标准方式不再逐位一致。', 'sm')}</span><span class="def">默认 标准</span></div>${seg('breeze_perf', [['off', '标准'], ['cuda_perf', '加速']])}</div>
       <div class="opt"><div class="row between"><span class="label">内核融合${hintHtml('将 bf16 舍入合并到 CUDA 内核中，仅提升速度，声音逐位一致。', 'sm')}</span><label class="switch"><input type="checkbox" data-pb="breeze_fusion"${o.breeze_fusion ? ' checked' : ''}><span></span></label></div></div>`
    : `<div class="opt"><div class="head"><span class="label">推理方式${hintHtml('快速：仅改用 flash 注意力；极速：另加打包投影、f16 KV 缓存等，速度最快，但声音和显存占用可能略有变化。对三个 Qwen3 模型同时生效。', 'sm')}</span><span class="def">默认 标准</span></div>${seg('qwen3_perf', [['off', '标准'], ['flash_attention', '快速'], ['cuda_perf', '极速']])}</div>
       <div class="opt"><div class="head"><span class="label">LoRA${hintHtml('加载自行训练的音色 / 风格 LoRA（PEFT 适配器文件夹）。留空表示不使用。', 'sm')}</span><span class="def">强度 <b id="tp-ls-v">${(+o.qwen3_lora_scale).toFixed(2)}</b></span></div>
         <div class="row" style="gap:8px"><input class="input" id="tp-lora" placeholder="LoRA 文件夹或文件的完整路径" value="${esc(o.qwen3_lora)}" style="flex:1;min-width:0"><input type="range" id="tp-ls" min="0" max="2" step="0.05" value="${o.qwen3_lora_scale}" style="width:120px"><button type="button" class="btn small" id="tp-save">应用</button></div></div>`;
  const send = async body => {
    try {
      const r = await api('/api/tts/engine-opts', { body });
      Object.assign(o, r);
      toast(!r.changed ? '没有变化' : r.restarted ? '已应用：配音引擎已按新设置重启' : '已保存：当前有任务正在使用引擎，将在下次重启引擎后生效');
    } catch (e) { toast(e.message, true); ttsPerf(box, fam); }
  };
  $$('[data-po]', box).forEach(g => $$('button', g).forEach(b => b.onclick = () => { $$('button', g).forEach(x => x.classList.toggle('on', x === b)); send({ [g.dataset.po]: b.dataset.v }); }));
  $$('[data-pb]', box).forEach(c => c.onchange = () => send({ [c.dataset.pb]: c.checked }));
  const ls = $('#tp-ls', box); if (ls) ls.oninput = () => { $('#tp-ls-v', box).textContent = (+ls.value).toFixed(2); };
  const sv = $('#tp-save', box); if (sv) sv.onclick = () => send({ qwen3_lora: $('#tp-lora', box).value.trim(), qwen3_lora_scale: +ls.value });
}

function openAdvModal() {
  const box = modal(`<div class="row between" style="margin-bottom:6px"><h3 class="card-title">高级参数 · ${esc(curModel()?.display_name)}</h3><button class="btn small" data-close>完成</button></div><div id="adv-modal"></div>`, null, true);
  box.style.width = 'min(1180px, 94vw)';
  renderAdv($('#adv-modal', box));
  const bg = box.parentElement, done = () => { if (!$('#director')) return; renderAdv(); renderDirector(); };  // 弹窗开着时用返回键离开了配音页
  new MutationObserver((_, ob) => { if (!document.body.contains(bg)) { ob.disconnect(); done(); } }).observe(document.body, { childList: true });
}

/* 右栏各部分重绘时保持滚动位置，避免“突然跳到别处” */
function keepSide(fn) {
  return function (...args) {
    const sc = $('.side-col'), y = sc ? sc.scrollTop : 0, wy = window.scrollY;
    const r = fn.apply(this, args);
    if (sc && Math.abs(sc.scrollTop - y) > 1) sc.scrollTop = y;
    if (Math.abs(window.scrollY - wy) > 1) window.scrollTo(0, wy);
    return r;
  };
}
renderDirector = keepSide(renderDirector);
renderAdv = keepSide(renderAdv);
renderVoicePick = keepSide(renderVoicePick);

function genParams() {
  const m = curModel(), options = { ...S.adv };
  if (m?.family === 'index_tts2' && mode() === 'direct' && options.emotion_alpha === undefined) options.emotion_alpha = modeDefault('emotion_alpha');
  return { model: m?.key, voice: curVoice()?.id || null, preset: curPreset(), instruct: instructText(), emotion_vector: emotionVector(), emotion_auto: emotionAuto(), seed: S.seed, options, ...S.job, maxlen: effMaxlen(),
    bad_cer: S.job.pass != null ? +(1 - S.job.pass / 100).toFixed(3) : undefined };
}

async function doPreview() {
  const ta = $('#script');
  let text = ta.value.slice(ta.selectionStart, ta.selectionEnd).trim();
  if (!text) text = (ta.value.split(/\n\s*\n|\n/).find(x => x.trim()) || '').trim();
  if (!text) return toast('请先输入要试听的文字', true);
  if (mode() === 'none') return toast('请选择一个音色，或在“导演”中描述声音', true);
  const btn = $('#preview'); btn.disabled = true; btn.innerHTML = '<span class="spinner dark"></span>生成中';
  const out = $('#preview-out'), op = newOp();
  out.innerHTML = '<div class="pv-log"></div><div class="pv-audio"></div>';
  const stop = liveLog($('.pv-log', out), op, '试听：' + text.slice(0, 18) + (text.length > 18 ? '…' : ''));
  try {
    const r = await api('/api/preview', { body: { ...genParams(), text: text.slice(0, 300), op } });
    await stop();
    $('.pv-audio', out).innerHTML = `<div style="margin-top:10px">${apHtml(r.url, 'now', { autoplay: true, title: '试听', sub: text.slice(0, 40), orb: curVoice()?.id })}</div>`;
  } catch (e) { await stop(); toast(e.message, true); }
  btn.disabled = false; btn.innerHTML = ICON.play + '试听';
}

async function startJob() {
  if (!S.text.trim()) return toast('请先输入文本', true);
  if (mode() === 'none') return toast('请选择一个音色，或在“导演”中描述声音', true);
  if (startJob.busy) return;  // 连点两下只生成一条
  startJob.busy = true; const go = $('#go'); if (go) go.disabled = true;
  try {
    const j = await api('/api/jobs', { body: { ...genParams(), text: S.text } });
    S.ttsRec = [j.id, ...(S.ttsRec || []).filter(x => x !== j.id)].slice(0, 40); persist();
    if ($('#tts-tabs')) {  // 等的时候去了别的页面：记录里已经有了，不用切标签
      renderTTS.tab?.('rec'); persist(); recWatch();
      if (MOB()) $('#tts-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });  // 手机上：滑到记录那里
    } else toast('已开始生成，可在“配音”页的记录中查看');
  } catch (e) { toast(e.message, true); }
  finally { startJob.busy = false; const g = $('#go'); if (g) g.disabled = false; }
}

async function showJob(id, areaSel = '#job-area', btnSel = '#go', onGone = () => { S.jobId = null; persist(); }) {
  const area = $(areaSel); if (!area) return;
  return pollStart(async stop => {
    let j;
    try { j = await api('/api/jobs/' + id); }
    catch (e) {  // 只有任务真的不存在才清掉卡片；网络偶发错误等下一轮再刷新
      if (e.message.includes('不存在')) { area.innerHTML = ''; stop(); onGone(); }
      return;
    }
    if (!$(areaSel)) return stop();
    area._dismiss = () => { stop(); if (PB.a && area.contains(PB.a._el)) PB.a.pause(); area.innerHTML = ''; delete area.dataset.jid; $(btnSel)?.classList.remove('busy'); onGone(); };
    renderJobInto(area, j, () => showJob(id, areaSel, btnSel, onGone));
    const running = ['queued', 'running'].includes(j.state);
    $(btnSel)?.classList.toggle('busy', running);
    if (!running) stop();
  }, 1200);
}

/* 局部刷新任务卡片：段落状态没变时只追加新日志，避免整块重绘导致页面跳动 */
const jobSig = j => [j.state, j.message, j.has_output, j.saved, (j.segments || []).map(s => s.status + ':' + s.attempts + ':' + s.text.length).join(',')].join('|');
function appendLogs(el, j) {
  const con = $('.console', el); if (!con) return false;
  const have = con.querySelectorAll('.ln').length, logs = (j.logs || []).slice(-300);
  if (logs.length < have) return false;
  const atBottom = con.scrollHeight - con.scrollTop - con.clientHeight < 24;
  const cur = $('.cursor', con);
  logs.slice(have).forEach(e => (cur || con).insertAdjacentHTML(cur ? 'beforebegin' : 'beforeend', logLine(e)));
  if (atBottom) con.scrollTop = con.scrollHeight;
  const sum = el.querySelector('details[data-k^="log"] > summary'); if (sum) sum.innerHTML = `${ICON.chev}运行日志（${(j.logs || []).length} 条）`;
  return true;
}
function renderJobInto(el, j, refresh) {
  if (el.dataset.jid === j.id && el.dataset.sig === jobSig(j) && appendLogs(el, j)) return;
  // 正在试听某一段：先不整块重绘（否则播放会被打断），只追加日志，等停下来再刷新
  if (el.dataset.jid === j.id && $$('.ap.on', el).length && $('.console', el)) { appendLogs(el, j); return; }
  const wy = window.scrollY, sc = $('.side-col'), sy = sc ? sc.scrollTop : 0;
  const segs = $('.segs', el), segY = segs ? segs.scrollTop : 0;
  const con = $('.console', el), conBottom = !con || con.scrollHeight - con.scrollTop - con.clientHeight < 24, conY = con ? con.scrollTop : 0;
  el.innerHTML = jobCard(j, true, !!el._dismiss);
  el.dataset.jid = j.id; el.dataset.sig = jobSig(j);
  bindJobCard(el, j, refresh);
  const segs2 = $('.segs', el); if (segs2) segs2.scrollTop = segY;
  const con2 = $('.console', el); if (con2) con2.scrollTop = conBottom ? con2.scrollHeight : conY;
  if (sc) sc.scrollTop = sy;
  if (Math.abs(window.scrollY - wy) > 1) window.scrollTo(0, wy);
}
const openMap = {};
const isOpen = (j, k, dflt) => (openMap[j.id + ':' + k] ?? dflt) ? 'open' : '';
const unit = j => j.kind === 'vc' ? '块' : '段';
const modesText = j => (j.modes || []).map(m => MODE_NAME[m] || m).join(' / ');
const fmtClock = sec => { sec = Math.max(0, Math.round(sec)); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };
/* 任务计时：正在生成的任务旁边显示已经用了多久（每秒走一格）；点一下弹出每一步：做完的用了几秒、正在做的已经做了几秒。
   数据来自后台的 timing（stages.py：t0 开始时间、now 后台当时的时间、stages 每一步）；按后台时间算，电脑时间不准也不影响 */
const JT = {};  // 任务 id → { t: timing, off: 本机时间 - 后台时间 }
const jtNow = x => Date.now() / 1000 - x.off;
// LoRA 名字去掉路径和扩展名（商店 / 我的下载用文件名 x.safetensors，生图页的列表用 x，视频页用相对路径：比的时候都换成这个）
const loraStem = s => String(s || '').split(/[\\/]/).pop().replace(/\.(safetensors|gguf|ckpt|pt|pth|bin)$/i, '').toLowerCase();
function jobTimer(j, cls = '') {
  const t = j?.timing; if (!t?.t0 || j.state !== 'running') return '';
  JT[j.id] = { t, off: Date.now() / 1000 - t.now };
  requestAnimationFrame(jtTick);
  return `<button type="button" class="jt ${cls}" data-jt="${esc(j.id)}" title="已用时长；点击查看各步骤" aria-label="计时，点击查看各步骤">${ICON.clock || '⏱'}<span></span></button>`;
}
function jtTick() {
  $$('.jt[data-jt]').forEach(b => { const x = JT[b.dataset.jt], s = b.querySelector('span'), v = x && fmtClock(jtNow(x) - x.t.t0); if (s && v && s.textContent !== v) s.textContent = v; });  // U09：做完的任务时长不变，不再每秒重写
  const p = $('.jt-pop'); if (p && JT[p.dataset.jt]) jtFill(p);
}
setInterval(jtTick, 1000);
function jtFill(p) {
  const x = JT[p.dataset.jt], t = x.t, now = jtNow(x), sec = v => v < 60 ? v.toFixed(v < 10 ? 1 : 0) + ' 秒' : fmtClock(v);
  const rows = (t.stages || []).map(g => { const live = g.live && !t.t1, v = live ? g.sec + (now - t.now) : g.sec;
    return `<div class="jt-row${live ? ' live' : ''}"><span class="jt-d">${live ? '<span class="spinner dark" style="width:10px;height:10px"></span>' : '✓'}</span><span class="jt-n">${esc(g.name)}</span><span class="jt-s">${live ? '已 ' : ''}${sec(Math.max(0, v))}</span></div>`; }).join('');
  const html = `<div class="jt-h">已用时 ${fmtClock(now - t.t0)}</div>${rows || '<div class="tiny">尚未开始</div>'}`;
  if (p._h !== html) { p._h = html; p.innerHTML = html; }
}
function jtOpen(b) {
  $('.jt-pop')?.remove();
  const p = document.createElement('div'); p.className = 'jt-pop'; p.dataset.jt = b.dataset.jt; p.setAttribute('role', 'dialog');
  document.body.append(p); jtFill(p);
  const r = b.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
  let x = Math.min(innerWidth - w - 10, Math.max(10, r.left)), y = r.bottom + 6; if (y + h > innerHeight - 10) y = Math.max(10, r.top - h - 6);
  p.style.left = x + 'px'; p.style.top = y + 'px';
}
document.addEventListener('click', e => {
  const b = e.target.closest?.('.jt[data-jt]');
  if (b) { e.preventDefault(); e.stopPropagation(); return $('.jt-pop')?.dataset.jt === b.dataset.jt ? $('.jt-pop').remove() : jtOpen(b); }
  if (!e.target.closest?.('.jt-pop')) $('.jt-pop')?.remove();
}, true);
addEventListener('keydown', e => { if (e.key === 'Escape') $('.jt-pop')?.remove(); });
setInterval(() => $$('[data-elapsed]').forEach(e => { const v = fmtClock(Date.now() / 1000 - +e.dataset.elapsed); if (e.textContent !== v) e.textContent = v; }), 1000);
function jobCard(j, withSegs = true, closable = false) {
  const pct = j.total ? Math.round(j.done / j.total * 100) : 0;
  const running = ['queued', 'running'].includes(j.state);
  const elapsed = (running ? Date.now() / 1000 : (j.finished || Date.now() / 1000)) - j.created;
  const logs = j.logs || [];
  return `<div class="card">
    <div class="row between"><h3 class="card-title">${esc(j.title)}</h3>
      <div class="row">${j.state === 'done' ? `<span class="pill green">完成 · 用时 ${fmtClock(elapsed)}</span>` : j.state === 'error' ? `<span class="pill red">${j.message === '已取消' ? '已取消' : '生成失败'}</span>` : (jobTimer(j, 'pill') || `<span class="pill blue"><span class="spinner dark" style="width:12px;height:12px"></span>已运行 <span data-elapsed="${j.created}">${fmtClock(elapsed)}</span></span>`)}
      ${running ? (j.message.startsWith('正在取消') ? '<button class="btn small" disabled><span class="spinner dark" style="width:11px;height:11px"></span>正在取消</button>' : '<button class="btn small" data-cancel>取消</button>') : ''}${closable ? `<button class="btn icon-btn small ghost card-x" data-dismiss title="${running ? '从此处收起，任务将在后台继续' : '从此处收起'}（记录仍保留在“作品 → 历史记录”中）">${ICON.x}</button>` : ''}</div></div>
    <div class="card-sub">${esc(j.model_name || j.model || '')}${j.modes?.length ? ' · ' + esc(modesText(j)) : ''}${j.voice_name ? ' · 音色：' + esc(j.voice_name) : ''}<br>${esc(j.message)} · 已完成 ${j.done}/${j.total} ${unit(j)}${j.warn ? ` · <span style="color:var(--orange)">${j.warn} ${unit(j)}建议检查</span>` : ''}</div>
    <div class="progress"><div style="width:${pct}%"></div></div>
    <div class="mini-bars">${(j.segments || []).map(s => `<i class="${s.status}" title="第 ${s.index + 1} 段"></i>`).join('')}</div>
    ${j.has_output && j.state === 'done' ? `<div class="result"><div style="flex:1;min-width:0"><div style="font-weight:650;margin-bottom:6px">成品 · ${fmtDur(j.duration)}</div>${apHtml(`/media/job/${j.id}/output.mp3?t=${j.finished}`, 'job:' + j.id, { title: j.title, sub: (j.kind === 'vc' ? '换声成品' : '配音成品') + (j.voice_name ? ' · ' + j.voice_name : ''), orb: j.voice, subs: 'job:' + j.id })}
      <div class="row" style="margin-top:8px"><button class="btn small ${j.saved ? '' : 'primary'}" data-savework>${j.saved ? '✓ 已保存到作品' : '☆ 保存到作品'}</button>${j.kind === 'vc' ? `<button class="btn small primary-soft" data-compare title="原声与换声并排对比，可逐句切换">⇄ 对比原声</button>` : ''}<a class="btn small" href="/media/job/${j.id}/output.mp3?dl=1">${ICON.dl}下载 MP3</a><a class="btn small" href="/media/job/${j.id}/output.wav?dl=1">${ICON.dl}下载 WAV</a>${(j.segments || []).length === 1 ? `<button class="btn small" data-redo="0">${ICON.redo}重做</button>` : ''}</div></div></div>` : ''}
    ${logs.length ? `<details style="margin-top:12px" data-k="log-${running ? 'run' : 'end'}" ${isOpen(j, 'log-' + (running ? 'run' : 'end'), running)}><summary class="tiny job-sum">${ICON.chev}运行日志（${logs.length} 条）</summary><div class="console">${logs.slice(-300).map(e => logLine(e, true)).join('')}${running ? '<span class="cursor"></span>' : ''}</div></details>` : ''}
    ${withSegs && (j.segments || []).length > 1 ? `<details style="margin-top:14px" data-k="segs" ${isOpen(j, 'segs', !!j.warn && !running)}><summary class="tiny seg-sum job-sum">${ICON.chev}${j.kind === 'vc' ? '分块详情' : '分段详情'}<span class="spacer"></span><button class="icon-link" data-segtext>${S.ui?.segTextHidden ? '显示字幕' : '隐藏字幕'}</button></summary><div class="segs${S.ui?.segTextHidden ? ' hide-text' : ''}">${(j.segments || []).map(s => segRow(j, s)).join('')}</div></details>` : ''}
  </div>`;
}
function segRow(j, s) {
  const ok = ['done', 'warn'].includes(s.status);
  const badge = s.status === 'warn' ? `<span class="pill orange" title="语音识别结果：${esc(s.asr)}">可能读错 ${Math.round(s.cer * 100)}%</span>`
    : s.status === 'done' ? (s.cer != null ? `<span class="pill green" title="语音识别结果：${esc(s.asr)}">✓ ${Math.round((1 - s.cer) * 100)}%</span>` : '<span class="pill green">✓</span>')
    : s.status === 'waiting' ? '<span class="pill">等待</span>' : '<span class="pill blue">生成中</span>';
  // 每段一个带拖动条的小播放器（点播放才加载）
  const ap = ok ? `<div class="sg-ap">${apHtml(`/media/job/${j.id}/seg/${s.index}?a=${s.attempts}`, '', { mini: true, lazy: true, dur: s.seconds, title: `${j.title} · 第 ${s.index + 1} ${unit(j)}`, sub: j.kind === 'vc' ? s.text : (s.text || '').slice(0, 40), orb: j.voice })}</div>` : '';
  if (j.kind === 'vc') return `<div class="sg ${s.status}"><div class="n">${s.index + 1}</div><div style="min-width:0"><div class="d">${esc(s.text)}</div><div class="t">${esc(s.asr || s.src_asr || '')}</div>${ap}</div>
    <div class="acts">${badge}${ok ? `<button class="btn icon-btn small" title="更换随机种子重做此块" data-redo="${s.index}">${ICON.redo}</button>` : ''}</div></div>`;
  return `<div class="sg ${s.status}"><div class="n">${s.index + 1}</div><div style="min-width:0">${s.direction ? `<div class="d">{${esc(s.direction)}}</div>` : ''}<div class="t">${esc(s.text)}</div>${ap}</div>
    <div class="acts">${badge}${ok ? `<button class="btn icon-btn small" title="修改 / 重做此段" data-redo="${s.index}">${ICON.redo}</button>` : ''}</div></div>`;
}
function bindJobCard(el, j, refresh) {
  $$('details[data-k]', el).forEach(d => d.ontoggle = () => { openMap[j.id + ':' + d.dataset.k] = d.open; });

  $$('[data-play]', el).forEach(b => b.onclick = () => togglePlay(b.dataset.play, b.dataset.url));
  const c = $('[data-cancel]', el); if (c) c.onclick = async () => {
    c.disabled = true; c.innerHTML = '<span class="spinner dark" style="width:11px;height:11px"></span>正在取消';
    try { const r = await api(`/api/jobs/${j.id}/cancel`, { body: {} }); toast(r.state === 'error' ? '已取消' : '当前段生成完成后即会停止（引擎无法中途打断）'); refresh(); }
    catch (e) { toast(e.message, true); c.disabled = false; c.textContent = '取消'; }
  };
  $$('[data-redo]', el).forEach(b => b.onclick = () => redoDialog(j, j.segments[+b.dataset.redo], refresh));
  const cmp = $('[data-compare]', el); if (cmp) cmp.onclick = () => openCompare(j);
  const dx = $('[data-dismiss]', el); if (dx) dx.onclick = () => { const card = dx.closest('.card'); card.classList.add('leave'); setTimeout(() => el._dismiss?.(), 200); };
  // 分段/分块里的字幕可以收起：只留编号、播放条和状态，列表更紧凑
  const stb = $('[data-segtext]', el); if (stb) stb.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    S.ui = { ...(S.ui || {}), segTextHidden: !S.ui?.segTextHidden }; persist();
    $$('.segs').forEach(x => x.classList.toggle('hide-text', !!S.ui.segTextHidden));
    $$('[data-segtext]').forEach(b => b.textContent = S.ui.segTextHidden ? '显示字幕' : '隐藏字幕');
  };
  const sv = $('[data-savework]', el); if (sv) sv.onclick = async () => {
    try { const r = await api(`/api/jobs/${j.id}/save`, { body: { saved: !j.saved } }); toast(r.saved ? '已保存到“作品”' : '已从“作品”移除（历史记录中仍保留）'); refresh(); }
    catch (e) { toast(e.message, true); }
  };
}
function redoDialog(j, s, refresh) {
  if (j.kind === 'vc') return modal(`<h3 class="card-title">重做第 ${s.index + 1} 块（${esc(s.text)}）</h3>
    <div class="card-sub">更换随机种子重新转换此块，并自动重新拼接成品。${s.src_asr ? `<br>原录音：「${esc(s.src_asr)}」` : ''}${s.asr ? `<br>当前结果：「${esc(s.asr)}」` : ''}</div>
    <div class="row" style="justify-content:flex-end"><button class="btn" data-close>取消</button><button class="btn primary" id="rd-ok">重做</button></div>`, box => {
    $('#rd-ok', box).onclick = async () => {
      const btn = $('#rd-ok', box); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>转换中';
      try { await api(`/api/jobs/${j.id}/redo/${s.index}`, { body: {} }); box.close(); toast('已重做并重新拼接'); refresh(); }
      catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = '重做'; }
    };
  });
  modal(`<h3 class="card-title">重做第 ${s.index + 1} 段</h3>
    <div class="card-sub">将更换随机种子重新生成，并自动重新拼接成品。${s.asr ? `<br>语音识别结果：「${esc(s.asr)}」` : ''}</div>
    <div class="field"><span class="label">此段的语气（可留空）</span><input class="input" id="rd-dir" value="${esc(s.direction)}" placeholder="例如：委屈得快哭了"></div>
    <div class="field"><span class="label">文字（可修改，例如将读错的多音字替换为同音字）</span><textarea class="textarea" id="rd-text" rows="4">${esc(s.text)}</textarea></div>
    <div class="row" style="justify-content:flex-end"><button class="btn" data-close>取消</button><button class="btn primary" id="rd-ok">重做</button></div>`, box => {
    $('#rd-ok', box).onclick = async () => {
      const btn = $('#rd-ok', box); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>生成中';
      try { await api(`/api/jobs/${j.id}/redo/${s.index}`, { body: { text: $('#rd-text', box).value, direction: $('#rd-dir', box).value } }); box.close(); toast('已重做并重新拼接'); refresh(); }
      catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = '重做'; }
    };
  });
}

/* ================= 浮层（不遮挡正文） ================= */
let curPop = null;
function popover(anchor, html, bind, opts = {}) {
  if (curPop && curPop._anchor === anchor) { curPop.close(); return null; }
  if (curPop) curPop.close(true);
  if (window.phSheet?.on() && !opts.anchored) {  // 手机：从底部升起的面板（2026-11-16 手机改版），标题用 opts.title 或按钮的名字
    const p = document.createElement('div'); p.className = 'pop ph-pop'; p._anchor = anchor; p.innerHTML = html;
    const t = opts.title || anchor.getAttribute('aria-label') || anchor.dataset.tip || (anchor.textContent || '').trim().slice(0, 12);
    p.close = () => { if (curPop === p) phSheet.close(); };
    curPop = p;
    phSheet.open(p, { title: t, opener: anchor, onClose: () => { if (curPop === p) curPop = null; p.remove(); opts.onClose?.(); } });
    $$('[data-close]', p).forEach(b => b.onclick = () => p.close());
    bind && bind(p);
    return p;
  }
  const p = document.createElement('div');
  p.className = 'pop'; p._anchor = anchor;
  if (opts.width) p.style.width = opts.width + 'px';
  p.innerHTML = '<button class="x" title="关闭（Esc）">×</button>' + html;
  document.body.appendChild(p);
  const place = () => {
    if (!anchor.isConnected) return;  // 按钮被重新画过：浮层留在原处，不跳到左上角
    const r = anchor.getBoundingClientRect();
    if (MOB() && anchor.closest('.rail, nav')) {  // 手机：贴在底部导航栏上方（按导航栏实际的位置算，不盖住“更多”），太高就在里面滚
      const navTop = (anchor.closest('.rail') || anchor).getBoundingClientRect().top;
      p.style.setProperty('bottom', (innerHeight - navTop + 8) + 'px', 'important'); p.style.setProperty('top', 'auto', 'important');
      p.style.setProperty('max-height', Math.max(200, navTop - 24 - (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sat')) || 0)) + 'px', 'important');
      return;
    }
    p.style.maxHeight = ''; const h = p.offsetHeight, w = p.offsetWidth;
    const below = innerHeight - r.bottom - 20, above = r.top - 20;
    let left = Math.min(r.left, innerWidth - w - 12), top;
    if (h <= below) top = r.bottom + 8;  // 下面放得下：放下面
    else if (h <= above) top = r.top - h - 8;  // 上面放得下：放上面
    else if (r.right + w + 20 < innerWidth && r.left < innerWidth / 3) {  // 都放不下（比如左下角的设置）：放到按钮右边，贴着底，不盖住按钮
      left = r.right + 10; top = Math.max(12, Math.min(r.bottom - h, innerHeight - h - 12));
      if (h > innerHeight - 24) { p.style.maxHeight = (innerHeight - 24) + 'px'; top = 12; }
    } else {  // 放在空间大的一边，超出的部分在浮层里面滚动
      const up = above > below; p.style.maxHeight = Math.max(160, up ? above : below) + 'px';
      top = up ? Math.max(12, r.top - p.offsetHeight - 8) : r.bottom + 8;
    }
    const tmin = document.body.classList.contains('in-app') ? 42 : 12;
    if (top < tmin) { p.style.maxHeight = Math.max(160, top + p.offsetHeight - tmin) + 'px'; top = tmin; }
    p.style.left = Math.max(12, left) + 'px'; p.style.top = top + 'px';
  };
  place();
  const ro = new ResizeObserver(() => { if (p.isConnected) place(); }); ro.observe(p);  // 内容后来才填进来（比如显存）：高度变了重新放
  const keep = e => e.target.closest('#script');  // 点击正文（移动光标）时浮层保持打开
  const outside = e => { if (!p.contains(e.target) && !anchor.contains(e.target) && !e.target.closest('.dd-menu') && !keep(e)) p.close(); };
  const escKey = e => { if (e.key === 'Escape' && !$('.dd-menu.show') && !$('.modal-bg')) { e.preventDefault(); e.stopImmediatePropagation(); p.close(); } };
  const onScroll = () => place();
  p.close = instant => {
    if (curPop !== p) return;
    curPop = null; ro.disconnect();
    document.removeEventListener('pointerdown', outside, true); document.removeEventListener('keydown', escKey, true);
    window.removeEventListener('scroll', onScroll, true); window.removeEventListener('resize', onScroll);
    if (instant) { p.remove(); return; }
    p.classList.add('out'); setTimeout(() => p.remove(), 140);
  };
  setTimeout(() => { document.addEventListener('pointerdown', outside, true); document.addEventListener('keydown', escKey, true); });  // pointerdown：iPhone 上点标题这类不可点的地方不会有 mousedown / click（11-23 点外面关不掉）
  window.addEventListener('scroll', onScroll, true); window.addEventListener('resize', onScroll);
  $('.x', p).onclick = () => p.close();
  $$('[data-close]', p).forEach(b => b.onclick = () => p.close());
  curPop = p;
  bind && bind(p);
  place(); [80, 400].forEach(t => setTimeout(() => { if (curPop === p) place(); }, t));  // 内容填好后再放一次（显存等是后来才读到的）
  return p;
}

/* 工具抽屉：在工具栏下方展开，把正文往下推而不是盖住它；同一个按钮再点一次收起 */
let drawerOwner = null;
function drawer(ownerId, html, bind) {
  const host = $('#tool-drawer'); if (!host) return;
  const was = drawerOwner;
  const closeIt = () => {
    drawerOwner = null; $$('.toolbar .btn.on, .toolbar .chip.on').forEach(b => b.classList.remove('on'));
    const h = host.offsetHeight;
    const a = host.animate({ height: [h + 'px', '0px'], opacity: [1, 0] }, { duration: 200, easing: EASE, fill: 'forwards' });
    const fin = () => { a.cancel(); if (!drawerOwner) host.innerHTML = ''; };
    a.onfinish = fin; setTimeout(fin, 260);
  };
  if (was === ownerId) { closeIt(); return null; }
  drawerOwner = ownerId;
  $$('.toolbar .btn.on, .toolbar .chip.on').forEach(b => b.classList.remove('on'));
  $('#' + ownerId)?.classList.add('on');
  const from = host.offsetHeight;
  host.innerHTML = `<div class="drawer-in"><button class="x" title="收起">×</button>${html}</div>`;
  const to = host.scrollHeight;
  const an = host.animate({ height: [from + 'px', to + 'px'] }, { duration: 240, easing: EASE });
  setTimeout(() => an.cancel(), 300);  // 后台页面动画会暂停：到点直接结束，保证内容可见
  const box = host.firstElementChild;
  box.close = closeIt;
  $('.x', box).onclick = closeIt;
  $$('[data-close]', box).forEach(b => b.onclick = closeIt);
  bind && bind(box);
  return box;
}

/* 从音源库选文件（换声 / 音色库 / 语音转文字）：只列当前空间的音源库（普通 / 私密各是各的），
   选中后服务器直接从音源库复制，不经过浏览器（手机上不用先下载再上传，大视频也行） */
function libPickRow(drop, onPick) {
  // 2026-11-07：和别的上传框一样——框里只写“添加音频”，点一下弹出来源菜单（电脑 / 音源库）；拖入照常
  const t = drop.querySelector(':scope > div'); if (t) { t.textContent = /视频/.test(t.textContent) ? '添加音频或视频' : '添加音频'; t.removeAttribute('style'); }
  drop.classList.add('b5-drop'); drop.setAttribute('role', 'button'); drop.tabIndex = 0;
  let pass = false;
  drop.addEventListener('click', e => {
    if (pass) { pass = false; return; }
    e.stopImmediatePropagation(); e.preventDefault();
    ctxMenu({ anchor: drop }, [{ label: '从电脑选择', icon: ICON.up, on: () => { pass = true; drop.click(); } }, { label: `从${VAULT ? '私密' : ''}音源库选择`, icon: CTX_IC.open, on: () => libPicker(onPick) }]);
  }, true);
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drop.click(); } });
}
async function libPicker(onPick) {
  const gen = VGEN;
  let list = null, q = '', cwd = '';  // cwd：当前打开的文件夹（'' = 音源库根目录；私密空间就是私密音源库的根目录）
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">从${VAULT ? '私密' : ''}音源库选择</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <input class="input" id="lp-q" placeholder="搜索整个音源库" autocomplete="off">
    <div class="lp-crumb" id="lp-crumb"></div>
    <div class="lp-list" id="lp-list"><div class="shimmer" style="margin-top:12px"></div></div>`, b => {
    const dirOf = x => x.dir === '未分类' ? '' : x.dir;  // 直接放在音源库里的文件：根目录
    const fileBtn = x => `<button type="button" class="lp-it" data-p="${esc(x.path)}"><span class="lp-ic">${x.video ? ICON.film : ICON.note}</span><span class="lp-n">${esc(x.name)}</span><span class="tiny">${esc(x.ext.toUpperCase())} · ${fmtSize(x.size)}</span></button>`;
    const paint = () => {
      const el = $('#lp-list', b), cr = $('#lp-crumb', b); if (!el || !list) return;
      const k = q.trim().toLowerCase();
      if (k) {  // 搜索：整个音源库里找，按文件夹分组
        cr.innerHTML = `<span class="tiny">搜索结果</span>`;
        const hit = list.filter(x => (x.name + ' ' + x.dir).toLowerCase().includes(k)), MAX = 300; let html = '', last = null;
        hit.slice(0, MAX).forEach(x => { if (x.dir !== last) { last = x.dir; html += `<div class="lp-dir">${esc(dirOf(x) || '根目录')}</div>`; } html += fileBtn(x); });
        if (hit.length > MAX) html += `<div class="tiny lp-empty">另有 ${hit.length - MAX} 个，请缩小搜索范围</div>`;
        el.innerHTML = hit.length ? html : '<div class="tiny lp-empty">没有找到匹配的文件</div>';
      } else {  // 按文件夹浏览：先显示当前文件夹里的子文件夹，再显示文件
        const parts = cwd ? cwd.split('/') : [];
        cr.innerHTML = [`<button type="button" class="lp-cb" data-d="">${VAULT ? '私密音源库' : '音源库'}</button>`, ...parts.map((n, i) => `<span class="lp-sep">/</span><button type="button" class="lp-cb" data-d="${esc(parts.slice(0, i + 1).join('/'))}">${esc(n)}</button>`)].join('');
        const subs = new Map();
        list.forEach(x => { const d = dirOf(x); if (d === cwd || !(cwd === '' ? d : d.startsWith(cwd + '/'))) return; const name = (cwd ? d.slice(cwd.length + 1) : d).split('/')[0]; subs.set(name, (subs.get(name) || 0) + 1); });
        const files = list.filter(x => dirOf(x) === cwd);
        el.innerHTML = [...subs].sort((x, y) => x[0].localeCompare(y[0], 'zh', { numeric: true })).map(([n, c]) => `<button type="button" class="lp-it lp-folder" data-d="${esc(cwd ? cwd + '/' + n : n)}"><span class="lp-ic">${ICON.folder}</span><span class="lp-n">${esc(n)}</span><span class="tiny">${c} 个</span></button>`).join('')
          + files.map(fileBtn).join('') || `<div class="tiny lp-empty">${list.length ? '此文件夹中没有音频或视频' : '音源库中尚无音频或视频'}</div>`;
      }
      $$('[data-d]', b).forEach(bt => bt.onclick = () => { cwd = bt.dataset.d; paint(); $('#lp-list', b).scrollTop = 0; });
      $$('.lp-it[data-p]', el).forEach(bt => bt.onclick = () => {
        const x = list.find(y => y.path === bt.dataset.p); if (!x || gen !== VGEN) return;
        b.close();
        onPick({ name: `${x.name}.${x.ext}`, size: x.size, type: (x.video ? 'video/' : 'audio/') + x.ext, libPath: x.path, url: libUrl(x.path) });
      });
    };
    $('#lp-q', b).oninput = e => { q = e.target.value; paint(); };
    setTimeout(() => $('#lp-q', b)?.focus(), 50);
    b._paint = paint;
  }, true);
  try { list = (await api('/api/play/library')).filter(x => x && x.path); } catch (e) { const el = $('#lp-list', box); if (el) el.innerHTML = loadFail('无法读取音源库', e.message); return; }
  if (gen !== VGEN) return box.close();
  box._paint?.();
}

/* 读取失败：代替一直转的占位条，说清楚原因，给一个“重试” */
const LOADFAIL = new Map();
function loadFail(title, err, retry, noBtn) {
  const id = 'lf' + Math.random().toString(36).slice(2, 8); if (retry) LOADFAIL.set(id, retry);
  const why = /not found|404/i.test(err || '') ? '后台版本过旧，请重启 Studio。' : err ? esc(err) : '后台无响应，请稍后再试。';
  return `<div class="load-fail" data-lf="${id}"><b>${esc(title)}</b><div class="tiny">${why}</div>${retry && !noBtn ? '<button type="button" class="btn small">重试</button>' : ''}</div>`;
}
function bindLoadFail() { $$('.load-fail[data-lf]').forEach(el => { const f = LOADFAIL.get(el.dataset.lf), b = $('button', el); if (f && b) b.onclick = () => { LOADFAIL.delete(el.dataset.lf); f(); }; }); }

/* ================= 弹窗 ================= */
function confirmBox(title, body = '', ok = '确定', danger = false) {  // 代替浏览器的 confirm()：返回 Promise<是否确定>
  return new Promise(res => {
    let done = false;
    const box = modal(`<h3 class="card-title" style="margin:0 0 8px">${esc(title)}</h3>${body ? `<div class="tiny" style="line-height:1.7">${esc(body)}</div>` : ''}
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:18px"><button class="btn" data-close>取消</button><button class="btn ${danger ? 'del-solid' : 'primary'}" id="cf-ok">${danger ? CTX_IC.del : ''}${esc(ok)}</button></div>`, b => {
      setTimeout(() => $('#cf-ok', b)?.focus(), 30);
      $('#cf-ok', b).onclick = () => { done = true; res(true); b.close(); };
      $$('[data-close]', b).forEach(x => x.onclick = () => b.close());  // 取消：走下面换过的 close（返回 false）
    });
    box.classList.add('m-alert');  // 手机上确认框照旧居中（iOS 的提示框），别的弹窗从底部升起
    const close0 = box.close; box.close = () => { if (!done) { done = true; res(false); } close0(); };
  });
}
/* 2026-11-08 用户：打开带视频的弹窗（详情、放大播放、对比……），或弹窗里的视频开始播放时，弹窗外面正在播的视频
   （生视频的大预览 / 对比播放器、缩略图点开的那段、视频小窗）都暂停，免得两边一起放 */
const pauseOutside = bg => document.querySelectorAll('video').forEach(v => { if (!v.paused && !bg.contains(v)) v.pause(); });
document.addEventListener('play', e => { const bg = e.target.closest?.('.modal-bg'); if (bg && e.target.tagName === 'VIDEO') pauseOutside(bg); }, true);
function modal(html, bind, wide) {
  const bg = document.createElement('div');
  bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal ${wide ? 'wide' : ''}">${html}</div>`;
  document.body.appendChild(bg);
  if (bg.querySelector('video')) pauseOutside(bg);
  const box = $('.modal', bg), opener = document.activeElement;
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true');
  const esc = e => {  // Esc 关掉最上面的那个弹窗（里面的下拉菜单开着时先关菜单）；Tab 只在弹窗里转
    if ([...document.querySelectorAll('.modal-bg:not(.out)')].pop() !== bg) return;
    if (e.key === 'Tab') {
      const f = [...box.querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(x => !x.disabled && x.offsetParent);
      if (!f.length) return;
      const i = f.indexOf(document.activeElement);
      if (e.shiftKey ? i <= 0 : i === f.length - 1 || i < 0) { e.preventDefault(); (e.shiftKey ? f[f.length - 1] : f[0]).focus(); }
      return;
    }
    if (e.key !== 'Escape' || $('.dd-menu.show') || CTX) return;
    e.preventDefault(); e.stopImmediatePropagation(); box.close();
  };
  box.close = () => {
    if (bg.classList.contains('out')) return; document.removeEventListener('keydown', esc, true); bg.classList.add('out'); setTimeout(() => bg.remove(), 200);
    if (opener?.isConnected && opener !== document.body) setTimeout(() => { try { opener.focus({ preventScroll: true }); } catch { } }, 0);  // 关掉后焦点回到打开它的按钮
  };
  document.addEventListener('keydown', esc, true);
  bg.addEventListener('mousedown', e => { if (e.target === bg) box.close(); });
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
  bind && bind(box);
  return box;
}

/* ================= 音色库 ================= */
let createTab = 'design';
/* 2026-11-15 界面检查：常用的是“我的音色”，新建表单以前占了上半屏。现在标题栏右边一个「新建音色」，点开才在上面展开（Apple：渐进展开）；
   还没有音色、或者正在生成候选时自动展开；开 / 关记在 S.ui.vNew */
function renderVoices() {
  const busy = (createDesign.state?.cands || []).some(c => c.state === 'working' || c.state === 'pending');
  const open = !voices.length || busy || !!S.ui?.vNew;
  $('#main').innerHTML = `
  <div class="page-head"><div><h1 class="page-title">音色库</h1></div><button type="button" class="btn${open ? ' on' : ''}" id="v-new" aria-expanded="${open}">${ICON.plus}<span>新建音色</span></button></div>
  <div class="card v-new-card" id="v-new-card" style="margin-bottom:24px"${open ? '' : ' hidden'}>
    <div class="row between" style="margin-bottom:16px"><h3 class="card-title">新建音色</h3>
      <div class="seg" id="ctab"><button data-t="design">设计</button><button data-t="upload">上传</button><button data-t="record">录音</button></div></div>
    <div id="create-body"></div>
  </div>
  <div class="row between" style="margin-bottom:14px"><h3 class="card-title" style="font-size:20px">我的音色 <span class="tiny" id="vcount"></span></h3></div>
  <div id="vlist"></div>`;
  $$('#ctab button').forEach(b => { b.classList.toggle('on', b.dataset.t === createTab); b.onclick = () => { createTab = b.dataset.t; renderVoices(); }; });
  $('#v-new').onclick = () => { const c = $('#v-new-card'), on = c.hidden; c.hidden = !on; S.ui = { ...(S.ui || {}), vNew: on }; persist(); $('#v-new').classList.toggle('on', on); $('#v-new').setAttribute('aria-expanded', on); if (on) c.querySelector('textarea, input')?.focus(); };
  ({ design: createDesign, upload: createUpload, record: createRecord })[createTab]($('#create-body'));
  renderVoiceList();
}

function renderVoiceList() {
  const box = $('#vlist'); if (!box) return;
  $('#vcount').textContent = `${voices.length} 个`;
  if (!voices.length) { box.innerHTML = `<div class="card empty">${vav(null, 'lg', '', '＋')}暂无音色</div>`; return; }
  const SRC = { design: ['purple', '描述设计'], clone: ['blue', '音频克隆'], record: ['green', '录音克隆'] };
  box.innerHTML = `<div class="voice-grid">${voices.map(v => {
    const s = SRC[v.source] || SRC.clone;
    return `<div class="vcard"><div class="top">${vav(v.id, 'lg', 'v:' + v.id, v.name)}<div style="min-width:0;flex:1"><div class="nm">${esc(v.name)}</div><span class="pill ${s[0]}" style="margin-top:4px">${s[1]}</span></div>
      <button class="btn icon-btn" data-play="v:${v.id}" data-url="${v.url}" title="试听参考音频">${ICON.play}</button></div>
      <div class="desc">${esc(v.description || '')}</div><div class="tr">参考文字：${esc(v.transcript)}</div>
      <div class="row"><button class="btn small primary" data-use="${v.id}">用于配音</button><button class="btn small" data-edit="${v.id}">编辑</button></div></div>`;
  }).join('')}</div>`;
  $$('[data-play]', box).forEach(b => b.onclick = () => togglePlay(b.dataset.play, b.dataset.url));
  $$('[data-use]', box).forEach(b => b.onclick = () => { S.voice = b.dataset.use; persist(); go('tts'); });
  $$('[data-edit]', box).forEach(b => b.onclick = () => editVoice(voices.find(x => x.id === b.dataset.edit)));
}
function editVoice(v) {
  modal(`<h3 class="card-title">编辑音色</h3><div class="card-sub">参考文字须与参考音频中的话语完全一致，克隆质量在很大程度上取决于此。</div>
    <div class="field"><span class="label">名称</span><input class="input" id="ev-name" value="${esc(v.name)}"></div>
    <div class="field"><span class="label">描述</span><textarea class="textarea" id="ev-desc" rows="2">${esc(v.description)}</textarea></div>
    <div class="field"><span class="label">参考文字</span><textarea class="textarea" id="ev-tr" rows="3">${esc(v.transcript)}</textarea></div>
    ${apHtml(v.url, 'v:' + v.id)}
    <div class="row" style="margin-top:16px"><button class="btn ghost danger" id="ev-del">删除音色…</button><span class="spacer"></span><button class="btn" data-close>取消</button><button class="btn primary" id="ev-ok">保存</button></div>`, box => {
    $('#ev-del', box).onclick = async () => {
      if (!await confirmBox(`删除音色「${v.name}」？`, '参考音频将一并删除，且无法恢复。', '删除', true)) return;
      try { await api('/api/voices/' + v.id, { method: 'DELETE' }); } catch (e) { return toast('删除失败：' + e.message, true); }
      if (S.voice === v.id) { S.voice = null; persist(); }
      box.close(); await loadVoices(); renderVoices(); toast('已删除');
    };
    $('#ev-ok', box).onclick = async () => {
      try { await api('/api/voices/' + v.id, { method: 'PATCH', body: { name: $('#ev-name', box).value, description: $('#ev-desc', box).value, transcript: $('#ev-tr', box).value } }); box.close(); await loadVoices(); renderVoiceList(); toast('已保存'); }
      catch (e) { toast(e.message, true); }
    };
  });
}

function saveForm(prefill) {
  return `<div class="field" style="margin-top:12px"><span class="label">音色名称</span><input class="input" data-f="name" value="${esc(prefill.name || '')}" placeholder="例如：知性女主播"></div>
    <div class="field"><span class="label">描述（可选）</span><input class="input" data-f="description" value="${esc(prefill.description || '')}"></div>`;
}

function createDesign(el) {
  const dms = models.filter(x => x.roles.design);
  if (!dms.length) { el.innerHTML = '<div class="muted">已安装的模型均不支持通过描述设计音色。</div>'; return; }
  const st = createDesign.state || (createDesign.state = { desc: '', text: '', count: 3, cands: [], model: null });
  const m = dms.find(x => x.key === st.model) || dms.find(x => x.key === S.model) || dms[0];
  st.model = m.key;
  el.innerHTML = `
    <div class="row" style="margin-bottom:12px"><span class="tiny">模型</span><div class="seg" id="d-model">${dms.map(x => `<button data-m="${x.key}" class="${x.key === m.key ? 'on' : ''}">${esc(x.display_name)}</button>`).join('')}</div></div>
    <div class="field"><span class="label">音色描述</span><textarea class="textarea" id="d-desc" rows="3" placeholder="例如：温柔的年轻女声，语速适中">${esc(st.desc)}</textarea></div>
    <div class="field"><span class="label">试听文本</span><input class="input" id="d-text" value="${esc(st.text)}" placeholder="可选"></div>
    <div class="row"><span class="tiny">数量</span><div class="seg" id="d-count">${[1, 2, 3, 4].map(n => `<button data-n="${n}" class="${st.count === n ? 'on' : ''}">${n} 个</button>`).join('')}</div><span class="spacer"></span><button class="btn grad" id="d-go"><span class="wave"></span><span class="lbl">生成</span></button></div>
    <div class="cands" id="d-cands"></div>`;
  $('#d-desc').oninput = e => st.desc = e.target.value;
  $('#d-text').oninput = e => st.text = e.target.value;
  $$('[data-n]', el).forEach(b => b.onclick = () => { st.count = +b.dataset.n; createDesign(el); });
  $$('[data-m]', el).forEach(b => b.onclick = () => { st.model = b.dataset.m; createDesign(el); });
  const cbox = $('#d-cands');
  const CB = () => createDesign.state === st ? $('#d-cands') : null;  // 生成途中离开再回来 / 换了空间：写到现在页面上的那个
  /* 每个候选一张卡片：等待中 → 正在生成（带已用时间）→ 生成好（可试听、保存）。逐个生成，生成好一个就显示一个 */
  const card = (c, i) => c.state === 'working'
    ? `<div class="cand pending working enter" data-i="${i}">${vav('wk' + i, 'xl', '', '')}<div class="state"><b>正在生成</b></div><div class="tiny">已用 <span data-since="${c.t0}">0</span> 秒</div><div class="shimmer"></div></div>`
    : c.state === 'error'
      ? `<div class="cand pending" data-i="${i}"><div class="state" style="color:var(--red)">候选 ${i + 1} 生成失败</div><div class="tiny">${esc(c.err)}</div></div>`
      : c.state === 'pending'
        ? `<div class="cand pending" data-i="${i}">${vav(null, 'xl', '', '')}<div class="state">候选 ${i + 1}</div><div class="tiny">排队中</div></div>`
        : `<div class="cand enter" data-i="${i}">${vav(c.file, 'xl', 'c:' + c.file, String(i + 1))}<div style="font-weight:600">候选 ${i + 1}<span class="tiny"> · 种子 ${c.seed}</span></div>${apHtml(c.url, 'c:' + c.file)}${saveForm({ description: st.desc })}<button class="btn primary" data-save="${i}">保存为音色</button></div>`;
  const bindSave = root => $$('[data-save]', root).forEach(b => b.onclick = async () => {
    const i = +b.dataset.save, c = st.cands[i], el2 = b.closest('.cand');
    try {
      await api('/api/voices/save', { body: { file: c.file, transcript: c.transcript, seed: c.seed, source: 'design', name: $('[data-f=name]', el2).value, description: $('[data-f=description]', el2).value } });
      toast('已保存到音色库'); st.cands.splice(i, 1); await loadVoices(); createDesign(el); renderVoiceList();
    } catch (e) { toast(e.message, true); }
  });
  const progress = () => {
    const box = $('#d-prog'); if (!box || createDesign.state !== st) return;
    const total = st.cands.length, done = st.cands.filter(c => c.state === 'done').length, cur = st.cands.findIndex(c => c.state === 'working');
    box.innerHTML = total ? `<div class="dots">${st.cands.map(c => `<i class="${c.state === 'done' ? 'done' : c.state === 'working' ? 'now' : ''}"></i>`).join('')}</div>
      <span>${cur >= 0 ? `已生成 ${done} 个，正在生成第 ${cur + 1} 个…` : `已生成 ${done} 个候选${done < total ? `（${total - done} 个失败）` : ''}，请选择最满意的一个保存`}</span>` : '';
  };
  const setCard = i => {
    const cb = CB(); if (!cb) return;
    const old = $(`.cand[data-i="${i}"]`, cb), html = card(st.cands[i], i);
    if (old) old.outerHTML = html; else cb.insertAdjacentHTML('beforeend', html);
    bindSave($(`.cand[data-i="${i}"]`, cb) || cb); progress();
  };
  const busyBtn = on => { const b = $('#d-go'); if (!b || createDesign.state !== st) return; b.disabled = on; b.classList.toggle('busy', on);
    b.innerHTML = on ? `<span class="wave"></span><span class="lbl"><span class="spinner"></span>生成中…</span>` : `<span class="wave"></span><span class="lbl">生成</span>`; };
  if (st.running) busyBtn(true);
  cbox.insertAdjacentHTML('beforebegin', '<div class="design-progress" id="d-prog"></div>');
  cbox.innerHTML = st.cands.map(card).join(''); bindSave(cbox); progress();
  const tick = setInterval(() => { if (!document.contains(cbox)) return clearInterval(tick); $$('[data-since]', cbox).forEach(x => { x.textContent = Math.round((Date.now() - +x.dataset.since) / 1000); }); }, 500);
  $('#d-go').onclick = async () => {
    if (!st.desc.trim()) return toast('请先描述所需的声音', true);
    if (st.running) return;
    st.running = true; busyBtn(true);
    const base = Math.floor(Math.random() * 90000) + 1000;
    st.cands = Array.from({ length: st.count }, () => ({ state: 'pending' }));
    const cb0 = CB(); if (cb0) cb0.innerHTML = st.cands.map(card).join(''); progress();
    for (let i = 0; i < st.cands.length; i++) {
      if (createDesign.state !== st) break;
      st.cands[i] = { state: 'working', t0: Date.now() }; setCard(i);
      try {
        const r = await api('/api/voices/design', { body: { model: st.model, description: st.desc, text: st.text, count: 1, seed: base + i * 101, op: newOp() } });
        st.cands[i] = { ...r[0], state: 'done' };
      } catch (e) { st.cands[i] = { state: 'error', err: e.message }; }
      setCard(i);
    }
    st.running = false; busyBtn(false);
  };
}

function clipResult(el, r, source) {
  // 截取结果：默认就是原声；用户自己点“去除背景声”才做人声分离，做完可以在“原声 / 去除背景声”之间来回切换对比，保存的是当前选中的那个
  let vox = null, useVox = false;
  el.innerHTML = `<div class="cand" style="margin-top:16px"><div id="c-clip"></div>
    <div class="row c-sep" id="c-sep"></div>
    <div class="field"><span class="label">参考文本（音频中的原话）</span><textarea class="textarea" data-f="transcript" rows="3">${esc(r.transcript)}</textarea></div>
    ${saveForm({})}<div class="row"><span class="spacer"></span><button class="btn primary" id="c-save">保存为音色</button></div></div>`;
  const cur = () => useVox ? vox : r;
  const paintClip = () => {
    const c = cur(), box = $('#c-clip', el);
    box.querySelector('.ap')?._a?.pause();
    box.innerHTML = `<div class="row">${vav(c.file, 'xl', 'c:' + c.file, '新')}<div><div style="font-weight:650">已截取的参考音频 · ${c.seconds.toFixed(1)} 秒${useVox ? ' · 已去除背景声' : ''}</div></div></div>
      ${apHtml(c.url, 'c:' + c.file)}`;
  };
  const paintSep = () => {
    const box = $('#c-sep', el);
    if (!vox) {
      box.innerHTML = `<span class="tiny">有背景声？${hintHtml('仅处理截取的片段：去除音乐和音效，只保留人声。', 'sm')}</span><span class="spacer"></span><button class="btn" id="c-sep-go">${ICON.wand}去除背景声</button>`;
      $('#c-sep-go', box).onclick = async e => {
        const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spinner dark"></span>正在去除背景声…';
        try {
          vox = await api('/api/voices/separate', { body: { file: r.file, op: newOp() } });
          useVox = true; paintClip(); paintSep();
        } catch (err) { toast(err.message, true); b.disabled = false; b.innerHTML = `${ICON.wand}去除背景声`; }
      };
      return;
    }
    box.innerHTML = `<span class="spacer"></span><div class="seg mini" id="c-ver"><button type="button" data-v="0" class="${useVox ? '' : 'on'}">原声</button><button type="button" data-v="1" class="${useVox ? 'on' : ''}">去除背景声</button></div>`;
    $('#c-ver', box).onclick = e => {
      const v = e.target.closest('[data-v]'); if (!v || (v.dataset.v === '1') === useVox) return;
      useVox = v.dataset.v === '1'; paintClip(); paintSep();
    };
  };
  paintClip(); paintSep();
  $('#c-save', el).onclick = async () => {
    try {
      await api('/api/voices/save', { body: { file: cur().file, source, transcript: $('[data-f=transcript]', el).value, name: $('[data-f=name]', el).value, description: $('[data-f=description]', el).value } });
      toast('已保存到音色库'); el.innerHTML = ''; await loadVoices(); renderVoiceList();
    } catch (e) { toast(e.message, true); }
  };
}

async function uploadClip(blob, filename, start, duration, btn, out, source) {
  const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>截取并识别中…';
  const op = newOp(), t0 = Date.now();
  out.innerHTML = `<div class="design-progress"><span class="spinner dark"></span><span id="clip-st">正在截取音频并识别文字…</span><span class="tiny" style="margin-left:auto">已用 <span id="clip-t">0</span> 秒</span></div>`;
  const tk = setInterval(() => { const x = $('#clip-t'); if (!x) return clearInterval(tk); x.textContent = Math.round((Date.now() - t0) / 1000); }, 500);
  const stop = async () => { clearInterval(tk); };
  try {
    const r = await api(`/api/voices/import?start=${start}&duration=${duration}&op=${op}`, { raw: blob, headers: { 'X-Filename': encodeURIComponent(filename), 'Content-Type': 'application/octet-stream' } });
    await stop(false);
    clipResult(out, r, source);
  } catch (e) { await stop(); out.innerHTML = ''; toast(e.message, true); }
  btn.disabled = false; btn.innerHTML = old;
}

function createUpload(el) {
  el.innerHTML = `<div class="drop" id="drop">${ICON.up}<div style="font-weight:600;font-size:15px">拖入音频或视频文件，或点击上传</div></div>
    <input type="file" id="file" accept="audio/*,video/*" hidden><div id="up-body"></div>`;
  const drop = $('#drop'), file = $('#file');
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && pick(file.files[0]);
  libPickRow(drop, pick);
  function pick(f) {
    const url = f.url || URL.createObjectURL(f), isVideo = f.type.startsWith('video');
    $('#up-body').innerHTML = `<div class="cand" style="margin-top:16px">
      <div class="row"><b>${esc(f.name)}</b></div>
      <div class="media-preview">${isVideo ? `<video id="media" controls src="${url}"></video>` : apHtml(url, '', { id: 'media' })}</div>
      <div class="row"><div class="field" style="margin:0;width:150px"><span class="label">起点（秒）</span><input class="input" type="number" id="st" value="0" step="0.1" min="0"></div>
        <button class="btn" id="here" style="align-self:flex-end">从当前播放位置开始</button>
        <div class="field" style="margin:0;flex:1;min-width:200px"><span class="label">截取时长：<span id="dv">10</span> 秒</span><input type="range" id="du" min="3" max="20" step="0.5" value="10"></div>
        <button class="btn primary" id="cut" style="align-self:flex-end">截取并识别</button></div>
      <div id="clip-out"></div></div>`;
    const media = $('#media');
    $('#here').onclick = () => { $('#st').value = (media._a || media).currentTime.toFixed(1); };
    $('#du').oninput = e => $('#dv').textContent = e.target.value;
    $('#cut').onclick = () => uploadClip(f, f.name, $('#st').value, $('#du').value, $('#cut'), $('#clip-out'), 'clone');
  }
}

function createRecord(el) {
  el.innerHTML = `<div class="cand" style="align-items:center;text-align:center;padding:30px">
    <div class="tiny">朗读以下内容（5–15 秒）</div>
    <div style="font-size:16px;margin:6px 0 10px">“今天的天气不错，我们一起去河边走走吧，顺便聊聊最近发生的事情。”</div>
    <button class="btn grad big" id="rec">${ICON.mic}开始录音</button><div id="rec-state" class="tiny"></div></div><div id="rec-out"></div>`;
  let mr = null, chunks = [], t0 = 0, timer = null;
  $('#rec').onclick = async () => {
    const btn = $('#rec');
    if (mr && mr.state === 'recording') { mr.stop(); return; }
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error(MIC_HTTP);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true } });
      mr = new MediaRecorder(stream); chunks = [];
      mr.ondataavailable = e => chunks.push(e.data);
      mr.onstop = async () => {
        clearInterval(timer); stream.getTracks().forEach(t => t.stop());
        if (!btn.isConnected) return;  // 已经离开了这个页面
        const dur = (Date.now() - t0) / 1000;
        btn.innerHTML = ICON.mic + '重新录音'; $('#rec-state').textContent = `已录 ${dur.toFixed(1)} 秒`;
        await uploadClip(new Blob(chunks, { type: mr.mimeType }), 'record.webm', 0, Math.min(30, dur), btn, $('#rec-out'), 'record');
        btn.innerHTML = ICON.mic + '重新录音';
      };
      mr.start(); t0 = Date.now();
      btn.innerHTML = '<span class="rec-dot"></span> 停止录音';
      timer = setInterval(() => { if (!btn.isConnected) return mr.stop(); $('#rec-state').textContent = `录音中 ${((Date.now() - t0) / 1000).toFixed(1)} 秒`; }, 100);
    } catch (e) { toast('无法使用麦克风：' + e.message, true); }
  };
}

/* ================= 换声（语音转换） ================= */
/* 你自己按想要的语气念一遍（上传或现场录），模型只把嗓音换成音色库里的某个声音；内容、语气、停顿都保持原样 */
let vcModels = [];
S.vc = Object.assign({ model: null, voice: null, adv: {}, seed: 123, check: true, chunk: null, src: null, jobId: null }, S.vc || {});
const V = () => S.vc;
const vcModel = () => vcModels.find(m => m.key === V().model) || vcModels[0];
async function renderVC() {
  drawerOwner = null;
  let vcErr = null;
  if (!vcModels.length) vcModels = await api('/api/vc/models').catch(e => { vcErr = e; return []; });
  if (location.pathname !== '/vc') return;  // 等模型列表时去了别的页面
  if (vcErr) { $('#main').innerHTML = `<div class="page-head"><h1 class="page-title">换声</h1></div><div class="card">${loadFail('无法读取换声模型', /not found|404/i.test(vcErr.message) ? vcErr.message : '配音引擎尚未启动完成，或启动失败（' + vcErr.message + '）', () => renderVC())}</div>`; bindLoadFail(); return; }
  const st = V(), m = vcModel();
  if (!m) { $('#main').innerHTML = `<div class="page-head"><h1 class="page-title">换声</h1></div><div class="card empty">${vav(null, 'lg', '', '♪')}引擎中尚无换声模型（Seed-VC）。</div>`; return; }
  st.model = m.key;
  if (st.voice && !voices.some(v => v.id === st.voice)) st.voice = null;
  $('#main').innerHTML = `
  <div class="page-head"><h1 class="page-title">换声</h1>
    <div class="row"><span class="tiny">模型</span><select class="select" id="vc-model" style="width:auto;min-width:160px">${vcModels.map(x => `<option value="${x.key}" ${x.key === m.key ? 'selected' : ''}>${esc(x.display_name)}</option>`).join('')}</select></div></div>
  <div class="grid-tts">
    <div class="stack">
      <div class="card vc-src-card" id="vc-src-card"></div>
      <div id="vc-job-area"></div>
    </div>
    <div class="side-col">
      <div class="card actions">
        <div class="now" id="vc-now"></div>
        <button class="btn grad big" id="vc-go" style="width:100%;justify-content:center"><span class="wave"></span><span class="lbl">开始换声</span></button>
      </div>
      <div class="card"><details class="adv" id="vc-voice-box" ${st.voice ? '' : 'open'}><summary>${ICON.chev}目标音色<span class="spacer"></span><span class="sum-voice" id="vc-voice-sum"></span></summary>
        <div style="margin-top:12px"><div class="voice-pick" id="vc-voice-pick"></div><div style="text-align:right;margin-top:8px"><a href="/voices" data-page="voices" class="tiny">管理音色 ›</a></div></div></details></div>
      <div class="card"><details class="adv" id="vc-adv"><summary>${ICON.chev}高级参数<span class="spacer"></span><span class="tiny" id="vc-adv-count"></span><button class="icon-link" id="vc-adv-pop" title="在大窗口中编辑全部参数">⤢ 弹窗编辑</button></summary><div id="vc-adv-body" style="margin-top:12px"></div></details></div>
    </div>
  </div>`;
  { // 换声（参考生图 / 生视频）：上面一张紧凑的“输入”卡——原录音 + 底部一排（模型、目标音色、高级参数、开始换声）；
    //   下面是产出（正在换的 + 换声记录），一开始就占好位置，整页是满的
    const src = $('#vc-src-card'), grid = src.closest('.grid-tts'), left = src.parentElement, side = grid.querySelector('.side-col');
    grid.classList.add('vc2'); side.hidden = true;
    const wrap = document.createElement('div'); wrap.className = 'card vc-in'; src.before(wrap); wrap.append(src);
    const sel = $('#vc-model'), hr = sel?.closest('.row'); if (hr?.closest('.page-head')) hr.remove();
    sel.classList.add('vc-model-sel'); sel.style.width = ''; sel.style.minWidth = '';
    const bar = document.createElement('div'); bar.className = 'row vc-bar';
    bar.innerHTML = `<button type="button" class="ig-chip" id="vc-voice-chip" title="目标音色"><span></span>${IG_CHEV}</button>
      <button type="button" class="ig-cb" id="vc-adv-btn">${ICON.sliders}<span>高级参数</span><span class="ig-adv-n" id="vc-adv-btn-n"></span></button><span class="spacer"></span>`;
    bar.prepend(sel);
    const goB = $('#vc-go'); goB.style.width = ''; bar.append(goB); wrap.append(bar); barSplit(bar, [goB]);
    // 目标音色：点开是面板
    const vb = $('#vc-voice-box').closest('.card'), pnl = document.createElement('div'); pnl.className = 'vc-panel'; pnl.hidden = true; pnl.append(vb); wrap.append(pnl);
    $('#vc-voice-box').open = true;
    const chip = $('#vc-voice-chip', bar), sum = $('#vc-voice-sum');
    const syncV = () => { chip.querySelector('span').innerHTML = sum?.innerHTML && !/未选择/.test(sum.textContent) ? sum.innerHTML : '选择目标音色'; };
    if (sum) new MutationObserver(syncV).observe(sum, { childList: true, subtree: true, characterData: true }); syncV();
    chip.onclick = e => { e.stopPropagation(); pnl.hidden = !pnl.hidden; chip.classList.toggle('open', !pnl.hidden); };
    pnl.addEventListener('click', e => { e.stopPropagation(); if (e.target.closest('[data-v], .vp-item, .voice-item, .vcard')) setTimeout(() => { pnl.hidden = true; chip.classList.remove('open'); }, 120); });
    const offDoc = e => { if (!wrap.isConnected) return document.removeEventListener('click', offDoc); if (!pnl.hidden && !e.target.closest('.modal-bg, .pop')) { pnl.hidden = true; chip.classList.remove('open'); } };
    document.addEventListener('click', offDoc);
    // 高级参数（弹窗）
    $('#vc-adv-btn', bar).onclick = () => openVcAdvModal();
    const syncN = () => { $('#vc-adv-btn-n', bar).textContent = ($('#vc-adv-count')?.textContent || '').replace(/\D/g, ''); };
    if ($('#vc-adv-count')) { new MutationObserver(syncN).observe($('#vc-adv-count'), { childList: true, characterData: true, subtree: true }); syncN(); }
    // 产出
    const out = document.createElement('div'); out.className = 'card vc-out';
    out.innerHTML = `<div class="row between vc-out-h"><h3 class="card-title" style="margin:0">换声记录</h3><a class="btn small ghost" href="/works" data-page="works" onclick="worksKind='vc'">全部作品</a></div><div id="vc-rec-list"></div>`;
    out.insertBefore($('#vc-job-area'), $('#vc-rec-list', out)); left.append(out);
    { const ja = $('#vc-job-area'); let rq = 0, k0 = '';  // 只在换了任务、任务状态变了（做完 / 存好）时重画记录（以前进度 / 日志每变一次都重画，换声时每秒一次，2026-11-16 审查）
      new MutationObserver(() => { const g = (ja.dataset.sig || '').split('|'), k = (ja.dataset.jid || '') + '|' + g[0] + '|' + g[3]; if (k === k0) return; k0 = k; clearTimeout(rq); rq = setTimeout(() => vcRecPaint(), 800); }).observe(ja, { childList: true, attributes: true, attributeFilter: ['data-sig', 'data-jid'] }); }
    vcRecPaint(); requestAnimationFrame(fitPages);
  }
  $('#vc-model').onchange = e => { st.model = e.target.value; st.adv = {}; persist(); renderVC(); };
  $('#vc-go').onclick = vcStart;
  $('#vc-adv-pop').onclick = e => { e.preventDefault(); e.stopPropagation(); openVcAdvModal(); };
  vcSrcRender(); vcVoicePick(); vcAdv(); vcNow();
  if (vcInJob()) vcShowJob(st.jobId);
}
/* 卡片切换：浏览器原生 View Transitions —— 两种状态下同名的卡片会自动“变形”过去（位置、大小、圆角一起过渡），
   不支持的浏览器直接切换。原录音卡片：没有任务时是完整的上传区；开始换声后收成顶部一条带播放条的小卡片。 */
function vcSwap(fn) {
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches || go._vt) return fn();  // 页面切换动画进行中：不再嵌套
  const sc = $('.side-col'), y = sc ? sc.scrollTop : 0;
  let done = false;
  const run = () => { if (done) return; done = true; fn(); if (sc) sc.scrollTop = y; };
  const t = document.startViewTransition(run);
  // 页面在后台/不渲染时浏览器不会调用回调：250 毫秒内没开始就跳过动画直接切换，状态绝不会卡住
  setTimeout(() => { if (!done) { try { t.skipTransition(); } catch { } run(); } }, 250);
}
let vcTab = 'up';
function vcSrcRender() {
  const st = V(), m = vcModel(), card = $('#vc-src-card'); if (!card) return;
  const compact = vcInJob();
  card.classList.toggle('mini', compact);
  if (compact) {
    // 任务视图：顶部是这个任务自己的原录音（存在任务文件夹里，不受上传区影响）
    const s = st.jobSrc || {}, url = `/media/job/${st.jobId}/source.wav`;
    card.innerHTML = `<div class="row vc-mini-head"><span class="vc-mini-ic">${ICON.wave}</span>
        <div style="flex:1;min-width:0"><div class="tt">${esc(s.filename || '原录音')}</div><div class="tiny">原录音${s.seconds ? ' · ' + fmtDur(s.seconds) : ''}${s.split != null ? ' · ' + (s.split ? '智能分段' : '整段转换') : ''}</div></div>
        <button class="btn small" id="vc-next" title="准备下一段，当前任务在后台继续">${ICON.plus}转换下一个</button></div>
      ${apHtml(url, 'vcsrc', { title: s.filename || '原录音', sub: '原录音' })}${subsBoxHtml('原录音字幕', !!st.ui?.vcSubsOpen)}`;
    apInit(card);
    $('#vc-next', card).onclick = vcGoNew;
    const sb = $('.subs-box', card), jid = st.jobId;
    sb.ontoggle = () => { S.ui = { ...(S.ui || {}), vcSubsOpen: sb.open }; persist(); };
    // 先用上传时做好的字幕；没有就让后台补做一份
    vcSubsInto(sb, async () => {
      if (st.jobSrc?.file) { const r = await api(`/api/vc/subs?file=${encodeURIComponent(st.jobSrc.file)}`); if (r.state === 'done' || r.state === 'running') return r; }
      const x = await api(`/api/jobs/${jid}/subs?wait=1`);
      return x.state === 'done' ? { state: 'done', sents: x.src } : x;
    }, $('.ap', card));
    return;
  }
  card.innerHTML = `${st.jobId ? '<div class="vc-back" id="vc-back" role="button" tabindex="0"></div>' : ''}<div class="row between" style="margin-bottom:12px"><h3 class="card-title" style="margin:0">原录音${hintHtml(esc(m.description || '') + '<br><br>原录音最好仅有一人说话、无背景音乐；原录音越清晰，转换结果越清晰。', 'sm')}</h3><div class="seg" id="vc-tabs"><button data-t="up">上传文件</button><button data-t="rec">录音</button></div></div>
    <div id="vc-src"></div>
    <div class="stat"><span id="vc-stat" style="display:contents"></span><label class="seg-switch" title="开：在语句间最安静处切分为约 ${m.profile?.chunk_seconds || 10} 秒的小块分别转换，实测最不易吞字。关：整段一次转换（显卡单次最多约 ${Math.round((m.profile?.whole_max_seconds || 300) / 60)} 分钟，更长的仍会切分）。"><span class="switch"><input type="checkbox" id="vc-split" ${st.split === false ? '' : 'checked'}><span></span></span>智能分段</label></div>`;
  const setTab = t => { vcTab = t; $$('#vc-tabs button', card).forEach(b => b.classList.toggle('on', b.dataset.t === t)); (t === 'rec' ? vcRecord : vcUpload)($('#vc-src', card)); };
  $$('#vc-tabs button', card).forEach(b => b.onclick = () => setTab(b.dataset.t));
  setTab(vcTab);
  $('#vc-split', card).onchange = e => { st.split = e.target.checked; persist(); vcStat(); toast(st.split ? '已开启智能分段：按停顿切分为小块转换，最不易吞字' : '已关闭智能分段：整段一次转换'); };
  vcStat();
  if (st.jobId) vcBackBar();
}
const vcInJob = () => !!V().jobId && V().view !== 'new';
function vcShowJob(id) {
  showJob(id, '#vc-job-area', '#vc-go', () => vcSwap(() => { Object.assign(V(), { jobId: null, view: 'new' }); persist(); vcSrcRender(); }));
}
/* 上传区顶部的“返回任务”条：实时显示上一个任务的进度，点一下切回任务视图。任务进行中或已完成都能切。 */
function vcBackBar() {
  const st = V(), id = st.jobId;
  const paint = async () => {
    const b = $('#vc-back'); if (!b || V().jobId !== id || vcInJob()) return false;
    let j; try { j = await api('/api/jobs/' + id); } catch (e) { if (e.message.includes('不存在')) { st.jobId = null; persist(); b.remove(); return false; } return true; }
    const running = ['queued', 'running'].includes(j.state);
    const status = running ? `<span class="spinner dark" style="width:11px;height:11px"></span>转换中 ${j.done}/${j.total} 块${jobTimer(j, 'sm')}`
      : j.state === 'done' ? '<span class="dot ok"></span>已完成' : `<span class="dot bad"></span>${esc(j.message === '已取消' ? '已取消' : '失败')}`;
    const html = `<span class="vc-back-l">${ICON.wave}<span class="tt">上一个任务：${esc(j.title)}</span></span><span class="vc-back-r">${status}<b>返回查看 ›</b><button type="button" class="vc-back-x" data-back-x title="不再显示（记录仍保留在“作品 → 历史记录”中）">${ICON.x}</button></span>`;
    if (b.dataset.html !== html) { b.innerHTML = html; b.dataset.html = html; }
    return running;
  };
  $('#vc-back').onclick = e => {
    if (e.target.closest('[data-back-x]')) {  // 叉掉：这里不再显示上一个任务（记录仍在“作品 → 历史记录”里）
      e.stopPropagation(); pollStop();
      Object.assign(st, { jobId: null, view: 'new' }); persist();
      const b = $('#vc-back'); b.classList.add('leave'); setTimeout(() => b.remove(), 220);
      return;
    }
    vcGoJob();
  };
  pollStart(async stop => { if (!(await paint())) stop(); }, 1500);
}
/* 转换下一个：切到上传区，任务在后台继续；上传区里你新放的录音、切回任务再回来都还在 */
function vcGoNew() {
  const st = V();
  vcSwap(() => {
    pollStop();
    st.view = 'new';
    if (st.src && st.jobSrc && st.src.file === st.jobSrc.file) st.src = null;  // 刚转过的这段不再占着上传区
    persist();
    $('#vc-job-area').innerHTML = ''; delete $('#vc-job-area').dataset.jid;
    $('#vc-go')?.classList.remove('busy');
    vcSrcRender(); vcNow();
  });
}
function vcGoJob() {
  const st = V(); if (!st.jobId) return;
  pollStop();
  vcSwap(() => { st.view = 'job'; persist(); vcSrcRender(); });
  vcShowJob(st.jobId);
}
/* 统计行：按当前开关估算会切成几块（实际在停顿处下刀，块数可能略多） */
function vcStat() {
  const st = V(), prof = vcModel()?.profile || {}, el = $('#vc-stat'); if (!el) return;
  if (!st.src) { el.innerHTML = ''; return; }  // 还没放录音：上面的上传框已经写了“添加音频”，这里空着（以前“尚无原录音”紧挨着智能分段开关，读着像开关的名字，2026-11-15）
  const sec = st.src.seconds, whole = prof.whole_max_seconds || 300, chunk = st.chunk ?? prof.chunk_seconds ?? 10;
  const max = st.split === false ? whole : chunk, n = sec <= max ? 1 : Math.ceil(sec / (max * 0.8));
  el.innerHTML = `<span>时长 <b>${fmtDur(sec)}</b></span><span>${st.split === false ? (n === 1 ? '<b>整段一次</b>转换' : `超过 ${Math.round(whole / 60)} 分钟，仍会切分为约 <b>${n}</b> 块（显卡单次最多 ${Math.round(whole / 60)} 分钟）`) : `按停顿切分为约 <b>${n}</b> 块转换`}</span>`;
}
function vcNow() {
  if (!$('#vc-now')) return;  // 已经离开换声页
  vcStat();
  const st = V(), v = voices.find(x => x.id === st.voice);
  const src = st.src ? `${esc(st.src.filename)} · ${fmtDur(st.src.seconds)}` : '尚无原录音';
  $('#vc-now').innerHTML = `<div style="min-width:0;flex:1"><div class="who">${v ? '目标音色：' + esc(v.name) : '未选择目标音色'}</div>
    <div class="tiny" style="margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${src}</div></div>`;
  if ($('#vc-voice-sum')) $('#vc-voice-sum').innerHTML = v ? `${vav(v.id, 'sm', '', v.name)}${esc(v.name)}` : '未选择';
}
function vcVoicePick() {
  const st = V(), box = $('#vc-voice-pick');
  box.innerHTML = voices.map(v => `<div class="vp ${v.id === st.voice ? 'on' : ''}" data-v="${v.id}" title="${esc(v.description || v.transcript)}">
      <button class="play" data-play="v:${v.id}" data-url="${v.url}" title="试听" aria-label="试听">${ICON.play}</button>${vav(v.id, '', 'v:' + v.id, v.name)}<div class="nm">${esc(v.name)}</div></div>`).join('') +
    `<a class="vp" href="/voices" data-page="voices"><div class="orb none" style="display:grid;place-items:center;color:var(--blue)">${ICON.plus}</div><div class="nm" style="color:var(--blue)">新建音色</div></a>`;
  $$('.vp[data-v]', box).forEach(el => el.onclick = e => {
    if (e.target.closest('.play')) return;
    st.voice = el.dataset.v; persist(); vcVoicePick(); vcNow();
    setTimeout(() => toggleDetails($('#vc-voice-box'), false), 200);
  });
  $$('.play', box).forEach(b => b.onclick = e => { e.stopPropagation(); togglePlay(b.dataset.play, b.dataset.url); });
}
async function vcRecPaint() {  // 换声记录：换好的成品，最新的在上面
  const box = $('#vc-rec-list'); if (!box) return;
  const all = await api('/api/jobs').catch(() => null); if (!all || !$('#vc-rec-list')) return;
  const list = all.filter(j => j.kind === 'vc' && j.state === 'done' && j.has_output).sort((a, b) => (b.finished || 0) - (a.finished || 0)).slice(0, 30);
  box.innerHTML = list.length ? list.map(j => `<div class="rec" data-id="${esc(j.id)}"><div class="rec-h"><span class="rec-t" title="${esc(j.title)}">${esc(j.title)}</span><span class="tiny">${fmtTime(j.finished || j.created)}</span></div>
    ${apHtml(`/media/job/${j.id}/output.mp3?t=${j.finished}`, 'job:' + j.id, { mini: true, title: j.title, sub: '换声' + (j.voice_name ? ' · ' + j.voice_name : ''), orb: j.voice })}</div>`).join('')
    : '<div class="tiny rec-empty">暂无记录</div>';
  apInit(box); fitPages();
}
function openVcAdvModal() {
  const box = modal(`<div class="row between" style="margin-bottom:6px"><h3 class="card-title">高级参数 · ${esc(vcModel()?.display_name)}</h3><button class="btn small" data-close>完成</button></div><div id="vc-adv-modal"></div>`, null, true);
  box.style.width = 'min(1180px, 94vw)';
  vcAdv($('#vc-adv-modal', box));
  const bg = box.parentElement;
  new MutationObserver((_, ob) => { if (!document.body.contains(bg)) { ob.disconnect(); vcAdv(); vcStat(); } }).observe(document.body, { childList: true });
}
/* 高级参数：由官方 model_spec 自动生成；只显示当前转换路线下真正生效的参数 */
function vcAdv(target) {
  const st = V(), m = vcModel(), body = target || $('#vc-adv-body'); if (!body) return;
  const again = () => target ? vcAdv(target) : keepSide(vcAdv)();
  const prof = m.profile || {}, zh = prof.options_zh || {}, hidden = new Set(prof.hidden_options || []), defs = prof.defaults || {};
  const route = st.adv.route ?? defs.route ?? m.options.find(o => o.name === 'route')?.values?.[0];
  const opts = m.options.filter(o => !hidden.has(o.name) && (!zh[o.name]?.routes || zh[o.name].routes.includes(route)));
  const changed = Object.keys(st.adv).filter(k => opts.some(o => o.name === k)).length;
  const VC_COMMON = new Set(['route', 'semitone_shift', 'similarity_guidance_scale', 'intelligibility_guidance_scale', 'f0_condition', 'auto_f0_adjust', 'num_inference_steps']);
  const optsA = opts.filter(o => VC_COMMON.has(o.name)), optsB = opts.filter(o => !VC_COMMON.has(o.name));
  if ($('#vc-adv-count')) $('#vc-adv-count').textContent = changed ? `已修改 ${changed} 项` : '全部为默认';
  const html = o => {
    const z = zh[o.name] || {}, v = st.adv[o.name], def = defs[o.name] ?? (o.name === 'f0_condition' && o.default == null ? route === 'v1_svc' : o.default), val = v ?? def ?? '';
    let ctl;
    if (o.type === 'bool') ctl = `<label class="switch"><input type="checkbox" data-o="${o.name}" ${(v ?? def) ? 'checked' : ''}><span></span></label>`;
    else if (o.type === 'enum') ctl = `<select class="select" data-o="${o.name}">${(o.values || []).map(x => `<option value="${esc(x)}" ${String(val) === String(x) ? 'selected' : ''}>${esc(z.values_zh?.[x] || x)}</option>`).join('')}</select>`;
    else if (o.type === 'float' && o.name.includes('guidance')) ctl = `<div class="range-row"><input type="range" min="0" max="2" step="0.05" value="${val}" data-o="${o.name}" data-t="float"><input class="input" type="number" step="0.05" value="${val}" data-o="${o.name}" data-t="float"></div>`;
    else ctl = `<input class="input" type="number" step="${o.type === 'int' ? 1 : 0.05}" value="${val}" data-o="${o.name}" data-t="${o.type}">`;
    return `<div class="opt"><div class="head"><span class="label" title="${esc(o.name)}">${esc(z.label || o.name)}</span><span class="def">默认 ${esc((z.values_zh?.[def] || def) ?? '—')}${v !== undefined ? ` · <a href="#" data-r="${o.name}">恢复</a>` : ''}</span></div>${ctl}
      <div class="help" style="margin-top:6px">${esc(z.help || o.description || '')}</div></div>`;
  };
  body.innerHTML = `<div class="sec-label" style="margin-top:0">模型参数</div><div class="help">参数根据引擎的官方说明自动生成。“转换路线”默认使用实测效果最佳的 v1 · XLSR + HiFT，其余均为官方默认。</div>
    ${target ? '<div class="adv-grid">' : ''}${optsA.map(html).join('')}${target ? '</div>' : ''}
    ${advMore('vc', optsB.length + 2, `${target ? '<div class="adv-grid">' : ''}${optsB.map(html).join('')}${target ? '</div>' : ''}
    <div class="opt"><div class="head"><span class="label" title="seed">随机种子</span><span class="def">默认 123</span></div>
      <div class="row"><input class="input" type="number" id="vc-seed" value="${st.seed}" style="flex:1"><button class="btn small" id="vc-seed-rand">随机</button></div></div>
    <div class="sec-label">长录音</div>
    <div class="opt"><div class="head"><span class="label">每块最长（秒）</span><span class="def">默认 ${prof.chunk_seconds || 10}</span></div>
      <input class="input" type="number" min="4" max="20" step="1" id="vc-chunk" value="${st.chunk ?? prof.chunk_seconds ?? 10}">
      <div class="help" style="margin-top:6px">长录音会在语句间最安静处切分为小块分别转换，每块前后各附带 1 秒上下文，转换后按原时间轴拼接，总时长与原录音完全一致。实测单块超过 20 秒时会开始吞掉“了”等轻声字，因此默认 10 秒。</div></div>
`)}
    ${checkOptsHtml('vck', st, 90, '自动核对并重做吞字的块', '每块转换后通过语音识别分别比对原录音与结果，准确率未达到“通过标准”（吞字、变字）时更换种子自动重做。不影响声音本身；多次重做仍未通过时，保留最佳结果并标记为“建议检查”。语气夸张、气声较多的录音本身识别准确率较低，可适当调低标准。')}
    <div class="row" style="justify-content:flex-end;margin-top:8px"><button class="btn small" id="vc-adv-reset">全部恢复默认</button></div>`;
  advMoreBind(body);
  { const d = $('details[data-more=vc]', body), rr = $('#vc-adv-reset', body)?.closest('.row'); if (d && rr) rr.before(d); }  // “更多参数”放在最后
  $$('[data-o]', body).forEach(inp => inp.oninput = inp.onchange = () => {
    const k = inp.dataset.o;
    let v = inp.type === 'checkbox' ? inp.checked : inp.value;
    if (inp.dataset.t === 'int') v = parseInt(v, 10); else if (inp.dataset.t === 'float') v = parseFloat(v);
    if (Number.isNaN(v)) return;
    st.adv[k] = v; persist();
    if (k === 'route' || inp.type === 'checkbox') return again();
    $$(`[data-o="${k}"]`, body).forEach(o => { if (o !== inp) o.value = v; });
  });
  $$('[data-r]', body).forEach(a => a.onclick = e => { e.preventDefault(); delete st.adv[a.dataset.r]; persist(); again(); });
  $('#vc-seed', body).oninput = e => { st.seed = parseInt(e.target.value || '0', 10); persistSoon(); };
  $('#vc-seed-rand', body).onclick = () => { st.seed = Math.floor(Math.random() * 99999); $('#vc-seed', body).value = st.seed; persist(); };
  $('#vc-chunk', body).onchange = e => { st.chunk = Math.max(4, Math.min(20, parseFloat(e.target.value) || 10)); e.target.value = st.chunk; persist(); vcStat(); };
  $$('[data-vck]', body).forEach(inp => inp.oninput = inp.onchange = () => {
    const k = inp.dataset.vck;
    st[k] = inp.type === 'checkbox' ? inp.checked : parseFloat(inp.value); persist();
    $$(`[data-vck="${k}"]`, body).forEach(o => { if (o !== inp && o.type !== 'checkbox') o.value = inp.value; });
    $$(`[data-show="${k}"]`, body).forEach(o => o.textContent = inp.value);
    if (k === 'check') $$('.check-sub', body).forEach(s => s.hidden = !inp.checked);
  });
  $('#vc-adv-reset', body).onclick = () => { Object.assign(st, { adv: {}, seed: 123, chunk: null, check: true, pass: null, retries: null }); persist(); again(); };
}
function vcSrcCard(el) {
  const s = V().src;
  if (!s) return;
  el.insertAdjacentHTML('beforeend', `<div class="cand enter" style="margin-top:14px"><div class="row between"><b style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.filename)}</b>
    <div class="row" style="gap:6px;flex:none"><span class="tiny">${fmtDur(s.seconds)}</span><button class="btn icon-btn small ghost" data-src-del title="移除此录音并重新选择">${ICON.x}</button></div></div>${apHtml(s.url, 'vcsrc', { title: s.filename, sub: '原录音' })}
    ${subsBoxHtml('原录音字幕（自动识别）', true)}</div>`);
  apInit(el);
  vcSubsInto($('.cand .subs-box', el), () => api(`/api/vc/subs?file=${encodeURIComponent(s.file)}`), $('.cand .ap', el));
  $('[data-src-del]', el).onclick = () => {
    if (playingKey === 'vcsrc') player.pause();
    const c = $('.cand', el); c.classList.add('leave');
    setTimeout(() => { V().src = null; persist(); c.remove(); vcNow(); }, 220);
  };
}
async function vcSend(blob, filename, el) {
  const op = newOp(), box = document.createElement('div');
  box.innerHTML = `<div class="design-progress" style="margin-top:14px"><span class="spinner dark"></span><span>正在读取音频…</span></div>`;
  $('.cand', el)?.remove(); el.appendChild(box);
  try {
    const r = await api(`/api/vc/upload?op=${op}`, { raw: blob, headers: { 'X-Filename': encodeURIComponent(filename), 'Content-Type': 'application/octet-stream' } });
    V().src = r; persist(); box.remove(); vcSrcCard(el); vcNow();
  } catch (e) { box.remove(); toast(e.message, true); }
}
function vcUpload(el) {
  el.innerHTML = `<div class="drop" id="vc-drop">${ICON.up}<div style="font-weight:600;font-size:15px">拖入音频文件，或点击上传</div></div><input type="file" id="vc-file" accept="audio/*,video/*" hidden>`;
  const drop = $('#vc-drop', el), file = $('#vc-file', el);
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); const f = e.dataTransfer.files[0]; if (f) vcSend(f, f.name, el); };
  file.onchange = () => { const f = file.files[0]; if (f) vcSend(f, f.name, el); };
  libPickRow(drop, f => vcSend(f, f.name, el));
  vcSrcCard(el);
}
function vcRecord(el) {
  el.innerHTML = `<div class="cand" style="align-items:center;text-align:center;padding:26px">
    <button class="btn grad big" id="vc-rec" style="margin-top:12px">${ICON.mic}开始录音</button><div id="vc-rec-state" class="tiny"></div></div>`;
  let mr = null, chunks = [], t0 = 0, timer = null;
  $('#vc-rec', el).onclick = async () => {
    const btn = $('#vc-rec', el);
    if (mr && mr.state === 'recording') { mr.stop(); return; }
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error(MIC_HTTP);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: false } });
      mr = new MediaRecorder(stream); chunks = [];
      mr.ondataavailable = e => chunks.push(e.data);
      mr.onstop = () => {
        clearInterval(timer); stream.getTracks().forEach(t => t.stop());
        if (!btn.isConnected) return;  // 已经离开了这个页面
        btn.innerHTML = ICON.mic + '重新录音'; $('#vc-rec-state', el).textContent = `已录 ${((Date.now() - t0) / 1000).toFixed(1)} 秒`;
        vcSend(new Blob(chunks, { type: mr.mimeType }), `录音 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}.webm`, el);
      };
      mr.start(); t0 = Date.now();
      btn.innerHTML = '<span class="rec-dot"></span> 停止录音';
      timer = setInterval(() => { if (!btn.isConnected) return mr.stop(); $('#vc-rec-state', el).textContent = `录音中 ${((Date.now() - t0) / 1000).toFixed(1)} 秒`; }, 100);
    } catch (e) { toast('无法使用麦克风：' + e.message, true); }
  };
  vcSrcCard(el);
}
async function vcStart() {
  const st = V();
  if (!st.src) return toast('请先上传或录制要换声的音频', true);
  if (!st.voice) return toast('请选择目标音色', true);
  try {
    const j = await api('/api/jobs', { body: { kind: 'vc', model: st.model, source: st.src.file, filename: st.src.filename, voice: st.voice, options: st.adv, seed: st.seed, check: st.check !== false, chunk: st.chunk, split: st.split !== false,
      retries: st.retries ?? 2, bad_cer: st.pass != null ? +(1 - st.pass / 100).toFixed(3) : undefined } });
    pollStop();
    // 上传区收成顶部小卡片，任务卡片从下方浮现；之后再开始轮询进度
    vcSwap(() => { Object.assign(st, { jobId: j.id, view: 'job', jobSrc: { ...st.src, split: st.split !== false } }); persist(); vcSrcRender(); renderJobInto($('#vc-job-area'), j, () => vcShowJob(j.id)); $('#vc-go')?.classList.add('busy'); });
    vcShowJob(j.id);
    toast('已开始换声，可离开此页面，也可在“作品”中查看进度');
  } catch (e) { if (e.message.includes('失效')) { st.src = null; persist(); renderVC(); } toast(e.message, true); }
}

/* ================= 字幕：跟着播放走，点字幕跳到对应位置 =================
   每个字幕框是一个独立的小组件：逐行 / 段落 两种排版（只影响这一个框），自带查找（上一个 / 下一个）。 */
function subsWidget(host, sents, audio, opts = {}) {
  host._subsAC?.abort();  // 同一块地方重画：上一份字幕挂在播放器上的监听全部去掉
  const ac = host._subsAC = new AbortController(), sig = { signal: ac.signal };
  host.classList.toggle('lyrics', !!opts.lyrics);  // 全屏播放页：歌词式大字
  host.innerHTML = `<div class="subs-tools">
      <div class="seg mini" data-mode><button data-m="line" class="on" title="一句一行">逐行</button><button data-m="para" title="数句一段">段落</button><button data-m="full" title="连成全文，仅在较长停顿处分段">全文</button></div>
      <span class="spacer"></span>${opts.tools || ''}
      <div class="subs-find" hidden><input class="input" placeholder="查找字幕中的文字…" aria-label="查找字幕"><span class="cnt"></span>
        <button type="button" data-f="prev" title="上一个（Shift+Enter）">${ICON.up2}</button><button type="button" data-f="next" title="下一个（Enter）">${ICON.down2}</button><button type="button" data-f="x" title="关闭（Esc）">${ICON.x}</button></div>
      <button type="button" class="icon-link find-btn" data-find title="查找">${ICON.search}查找</button></div>
    <div class="subs"></div>`;
  const list = $('.subs', host), findBox = $('.subs-find', host), inp = $('input', findBox), cnt = $('.cnt', findBox);
  let mode = opts.mode || 'line', items = [], cur = -1, userScroll = 0, q = '', hits = [], hi = -1;
  if (mode !== 'line') $$('[data-m]', host).forEach(x => x.classList.toggle('on', x.dataset.m === mode));
  const body = (x, i) => opts.render ? opts.render(x, i) : (esc(x.text) || '<i class="muted">（未识别到声音）</i>');
  // 2026-11-18 用户：字幕总感觉有延迟。全屏播放页（歌词式）提前 0.25 秒切到下一句（照 Apple Music：唱到时高亮和滚动已经到位）；别的地方照旧提前 0.05 秒
  const LEAD = opts.lyrics ? 0.25 : 0.05;
  // opts.off：字幕时间调节（秒，正数 = 字幕提前；11-18 用户：要能手动提前 / 推后）
  const at = tm => { const t = tm + LEAD + (opts.off?.() || 0); let k = -1; for (let i = 0; i < sents.length; i++) { if (sents[i].s <= t) k = i; else break; } return k; };
  // 2026-11-17 用户：换句时滚动不丝滑——浏览器的 smooth 时长不固定、来新目标就重新起步；改成自己算：0.65 秒先快后慢，
  // 中途来了下一句就从当前位置接着滚（不停顿、不回弹）；你一滚动就停下
  let tw = 0;
  const glideTo = top => {
    cancelAnimationFrame(tw);
    top = Math.max(0, Math.min(top, list.scrollHeight - list.clientHeight));
    const from = list.scrollTop, d = top - from;
    if (reduceMotion || Math.abs(d) < 1) { list.scrollTop = top; return; }
    const t0 = performance.now(), D = opts.lyrics ? 480 : 650;  // 歌词式滚快一点（11-18：650 毫秒看着跟不上）
    const step = now => { const t = Math.max(0, Math.min(1, (now - t0) / D)); list.scrollTop = from + d * (1 - Math.pow(1 - t, 4)); if (t < 1) tw = requestAnimationFrame(step); };
    tw = requestAnimationFrame(step);
  };
  const scrollTo = (el, force, jump) => {
    if (!el || (!force && Date.now() - userScroll < 2500)) return;  // 你自己在滚动字幕时不抢位置
    // 全屏播放页（歌词式）：正在播的那句放在偏上的位置（约 30%，照 Apple Music；2026-11-17 用户：再往上一句），下面多看几句；别的地方照旧居中
    const at = opts.lyrics ? (parseFloat(getComputedStyle(list).getPropertyValue('--lyr-at')) || .3) : .5;  // --lyr-at：样式里可以改（底部通栏放低一点）
    const top = el.offsetTop - list.clientHeight * at + el.offsetHeight / 2;
    if (jump) { cancelAnimationFrame(tw); list.scrollTop = Math.max(0, top); } else glideTo(top);
  };
  const show = (k, force, jump) => {
    if (k === cur && !force) return;
    items[cur]?.classList.remove('on'); cur = k;
    const el = items[k]; if (!el) return;
    el.classList.add('on'); scrollTo(el, force, jump);
  };
  const upd = () => audio && show(at(audio.currentTime));
  const pick = i => { if (opts.onPick) return opts.onPick(i); if (!audio) return; audio.currentTime = sents[i].s; audio.play().catch(() => { }); };
  // 段落模式：停顿超过 1.6 秒或满 6 句就分段；每一句仍是可点、可高亮的一小段
  // 段落：停顿超过 1.6 秒或满 6 句分段；全文：几乎不分段，只有超过 5 秒的长停顿才另起一段
  const groups = () => {
    const [gap, max] = mode === 'full' ? [5, Infinity] : [1.6, 6];
    const g = []; let c = [];
    sents.forEach((x, i) => { if (c.length && (x.s - sents[i - 1].e > gap || c.length >= max)) { g.push(c); c = []; } c.push(i); });
    if (c.length) g.push(c); return g;
  };
  const draw = () => {
    list.classList.toggle('para-mode', mode !== 'line'); list.classList.toggle('full-mode', mode === 'full');
    list.innerHTML = mode === 'line'
      ? sents.map((x, i) => `<div class="sub" data-i="${i}" data-s="${x.s}" data-e="${x.e}"><span class="st">${fmtT(x.s)}</span><span class="tx">${body(x, i)}</span></div>`).join('')
      : groups().map(g => `<p class="para"><span class="st">${fmtT(sents[g[0]].s)}</span>${g.map(i => `<span class="sub" data-i="${i}" data-s="${sents[i].s}" data-e="${sents[i].e}">${body(sents[i], i)}</span>`).join('')}</p>`).join('');
    items = $$('.sub', list);
    items.forEach((el, i) => el.onclick = () => pick(i));
    // 刚画好（打开、换排版、换外观）：直接到当前那句，不从第一句一路滚下来（2026-11-17 用户）
    const k = cur; cur = -1; show(k >= 0 ? k : (audio ? at(audio.currentTime) : -1), true, true);
    highlight(false);
  };
  /* 查找：把当前字幕里所有匹配的字标出来，Enter / ↓ 下一个，Shift+Enter / ↑ 上一个；跳到哪个，播放位置也跟过去 */
  const highlight = jump => {
    hits = []; hi = -1;
    if (q) {
      const walker = document.createTreeWalker(list, NodeFilter.SHOW_TEXT, { acceptNode: n => n.parentElement.closest('.st') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
      const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      const ql = q.toLowerCase();
      nodes.forEach(n => {
        const s = n.nodeValue, low = s.toLowerCase(); let pos = 0, idx, frag = null;
        while ((idx = low.indexOf(ql, pos)) >= 0) {
          frag = frag || document.createDocumentFragment();
          frag.append(s.slice(pos, idx));
          const m = document.createElement('mark'); m.className = 'hit'; m.textContent = s.slice(idx, idx + q.length); frag.append(m);
          pos = idx + q.length;
        }
        if (frag) { frag.append(s.slice(pos)); n.replaceWith(frag); }
      });
      hits = $$('mark.hit', list);
    }
    cnt.textContent = q ? (hits.length ? `0/${hits.length}` : '没有找到') : '';
    if (jump && hits.length) go(0);
  };
  const go = k => {
    if (!hits.length) return;
    hits[hi]?.classList.remove('cur');
    hi = (k + hits.length) % hits.length;
    const m = hits[hi]; m.classList.add('cur'); cnt.textContent = `${hi + 1}/${hits.length}`;
    const sub = m.closest('.sub'), i = +sub.dataset.i;
    if (audio && audio.paused) audio.currentTime = sents[i].s;  // 没在播放时把播放位置也挪过去，点播放就从这里开始
    show(i, true);
    glideTo(m.offsetTop - list.clientHeight / 2);
  };
  const openFind = () => { findBox.hidden = false; $('[data-find]', host).hidden = true; inp.focus(); inp.select(); };
  const closeFind = () => { findBox.hidden = true; $('[data-find]', host).hidden = false; q = ''; inp.value = ''; draw(); };
  $('[data-find]', host).onclick = openFind;
  inp.oninput = () => { q = inp.value.trim(); clearTimeout(inp._t); inp._t = setTimeout(() => { draw(); if (hits.length) go(0); }, 150); };
  inp.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); go(hi + (e.shiftKey ? -1 : 1)); } else if (e.key === 'Escape') { e.preventDefault(); closeFind(); } };
  $$('[data-f]', findBox).forEach(b => b.onclick = () => b.dataset.f === 'x' ? closeFind() : go(hi + (b.dataset.f === 'next' ? 1 : -1)));
  $$('[data-m]', host).forEach(b => b.onclick = () => { mode = b.dataset.m; opts.onMode?.(mode); $$('[data-m]', host).forEach(x => x.classList.toggle('on', x === b)); draw(); });
  host.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); openFind(); } }, sig);
  // 2026-11-17 用户：滑动查看字幕时不要模糊（Apple Music 的做法）：一滑就全部变清楚，停手 2.5 秒后回到跟着播放（和上面“不抢位置”的时间一样）
  let browseT = 0;
  const browse = () => { list.classList.add('browsing'); clearTimeout(browseT); browseT = setTimeout(() => list.classList.remove('browsing'), 2500); };
  ['wheel', 'touchstart', 'touchmove', 'pointerdown'].forEach(ev => list.addEventListener(ev, () => { userScroll = Date.now(); cancelAnimationFrame(tw); if (ev === 'wheel' || ev === 'touchmove') browse(); }, { passive: true }));
  list.addEventListener('keydown', e => { if (/^(Arrow|Page|Home|End)/.test(e.key)) userScroll = Date.now(); });
  if (audio) {
    let iv = 0;
    const alive = () => { if (host.isConnected) return true; ac.abort(); return false; };  // 字幕所在的地方没了：自己把监听去掉
    ac.signal.addEventListener('abort', () => clearInterval(iv));
    ['timeupdate', 'seeked', 'loadedmetadata'].forEach(ev => audio.addEventListener(ev, () => { if (alive()) upd(); }, sig));
    // 播放时：歌词式每一帧看一次（换句不再最多晚 120 毫秒）；页面在后台时 requestAnimationFrame 停了，靠 120 毫秒的定时器兜底
    let raf = 0;
    const frame = () => { raf = 0; if (!alive() || audio.paused) return; upd(); raf = requestAnimationFrame(frame); };
    const start = () => { clearInterval(iv); cancelAnimationFrame(raf); if (!alive()) return; iv = setInterval(() => { if (alive()) upd(); }, 120); if (opts.lyrics) raf = requestAnimationFrame(frame); };
    ac.signal.addEventListener('abort', () => cancelAnimationFrame(raf));
    audio.addEventListener('play', start, sig);
    audio.addEventListener('pause', () => { clearInterval(iv); cancelAnimationFrame(raf); raf = 0; if (alive()) upd(); }, sig);
    if (!audio.paused) start();
  }
  draw();
  host._find = openFind; host._upd = () => audio && show(at(audio.currentTime), true);  // 右键菜单 / Ctrl+F / 调了字幕时间：从外面调用
  return { show: k => show(k), host };
}
const apAudio = el => { apInit(el.parentElement || document); return el._a; };

/* 原录音字幕：上传后后台自动识别；可以收起 / 展开 */
async function vcSubsInto(box, getter, audioEl) {
  let tries = 0;
  const paint = async () => {
    if (!box.isConnected) return;
    let r; try { r = await getter(); } catch (e) { r = { state: 'error', error: e.message }; }
    if (!box.isConnected) return;
    const st = $('.subs-state', box.closest('details') || box);
    if (r.state === 'done') {
      if (st) st.textContent = `${r.sents.length} 句 · 点击字幕可跳转`;
      if (r.sents.length) subsWidget($('.subs-body', box), r.sents, apAudio(audioEl));
      else $('.subs-body', box).innerHTML = '<div class="tiny">未识别到人声。</div>';
      return;
    }
    if (r.state === 'error' || r.state === 'none') { if (st) st.textContent = r.state === 'none' ? '暂无字幕' : '识别失败'; $('.subs-body', box).innerHTML = `<div class="tiny">${esc(r.error || '此录音尚无字幕。')}</div>`; return; }
    if (st) st.innerHTML = '<span class="spinner dark" style="width:10px;height:10px"></span> 正在识别…';
    if (++tries < 400) setTimeout(paint, 1500);
  };
  paint();
}
const subsBoxHtml = (title, open) => `<details class="subs-box" ${open ? 'open' : ''}><summary>${ICON.chev}${title}<span class="spacer"></span><span class="tiny subs-state"></span></summary><div class="subs-body"><div class="shimmer" style="height:18px;margin-top:10px"></div></div></details>`;

/* ================= 对比：左原声、右换声，字幕逐句对齐，可以逐句交替播放 ================= */
/* 右侧把和原录音识别结果不一样的字标出来，方便发现吞字、变字 */
function diffMark(a, b) {
  const n = a.length, m = b.length;
  if (!m) return '<i class="muted">（未识别到声音）</i>';
  if (n * m > 40000) return esc(b);
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let k = m - 1; k >= 0; k--) dp[i][k] = a[i] === b[k] ? dp[i + 1][k + 1] + 1 : Math.max(dp[i + 1][k], dp[i][k + 1]);
  let i = 0, k = 0, out = '';
  const word = c => /[一-鿿0-9A-Za-z]/.test(c);
  while (k < m) {
    if (i < n && a[i] === b[k]) { out += esc(b[k]); i++; k++; }
    else if (i < n && dp[i + 1][k] >= dp[i][k + 1]) i++;
    else { out += word(b[k]) ? `<mark>${esc(b[k])}</mark>` : esc(b[k]); k++; }
  }
  return out;
}
async function openCompare(j) {
  const box = modal(`<div class="cmp">
    <div class="row between cmp-head"><div style="min-width:0"><h3 class="card-title" style="margin:0">对比 · ${esc(j.title)}</h3><div class="tiny" id="cmp-st">正在准备字幕…</div></div>
      <div class="row" style="gap:8px"><button class="btn primary" id="cmp-ab" disabled>${ICON.play}逐句对比</button><button class="btn" data-close>关闭</button></div></div>
    <div class="cmp-cols">
      <div class="cmp-col"><div class="cmp-label"><span class="pill">原声</span><span class="tiny">原始录音</span></div>${apHtml(`/media/job/${j.id}/source.wav`, 'cmpA', { title: j.title, sub: '对比 · 原声' })}<div class="cmp-subs" id="cmp-a"></div></div>
      <div class="cmp-col"><div class="cmp-label"><span class="pill blue">换声</span><span class="tiny">${esc(j.voice_name || '')} · 与原声识别结果不同的字会<mark>标出</mark></span></div>${apHtml(`/media/job/${j.id}/output.mp3?t=${j.finished}`, 'cmpB', { title: j.title, sub: '对比 · 换声' + (j.voice_name ? ' · ' + j.voice_name : ''), orb: j.voice })}<div class="cmp-subs" id="cmp-b"></div></div>
    </div></div>`, null, true);
  box.classList.add('cmp-modal');
  apInit(box);
  const [elA, elB] = $$('.ap', box), A = elA._a, B = elB._a;
  let r = { state: 'running' };
  for (let k = 0; k < 600 && r.state === 'running' && box.isConnected; k++) {
    r = await api(`/api/jobs/${j.id}/subs?wait=1`).catch(e => ({ state: 'error', error: e.message }));
    if (r.state === 'running') { $('#cmp-st', box).innerHTML = '<span class="spinner dark" style="width:10px;height:10px"></span> 正在为两侧生成字幕（首次打开需要一些时间）…'; await sleep(1500); }
  }
  if (!box.isConnected) return;
  if (r.state !== 'done') { $('#cmp-st', box).textContent = '字幕生成失败：' + (r.error || ''); return; }
  const src = r.src, out = r.out.length ? r.out : r.src.map(x => ({ ...x, text: '' }));
  const diffs = out.filter((x, i) => x.text.replace(/[^一-鿿0-9A-Za-z]/g, '') !== src[i].text.replace(/[^一-鿿0-9A-Za-z]/g, '')).length;
  $('#cmp-st', box).textContent = `${src.length} 句 · ${!r.out.length ? '换声结果未识别出字幕，仅可通过聆听对比' : diffs ? diffs + ' 句识别结果与原声不同（可能为吞字、变字，也可能仅是识别误差）' : '两侧识别结果完全一致'} · 点击字幕可跳转`;
  // 两边同一句一起高亮，方便对照
  let ab = null;
  const showA = subsWidget($('#cmp-a', box), src, A, { onPick: i => { stopAB(); A.currentTime = src[i].s; A.play(); } }).show;
  const showB = subsWidget($('#cmp-b', box), out, B, { onPick: i => { stopAB(); B.currentTime = out[i].s; B.play(); }, render: (x, i) => diffMark(src[i].text, x.text) }).show;
  const mirror = (from, show) => from.addEventListener('timeupdate', () => { if (!from.paused) { let k = -1; for (let i = 0; i < src.length; i++) { if (src[i].s <= from.currentTime + 0.05) k = i; else break; } show(k); } });
  mirror(A, showB); mirror(B, showA);
  /* 逐句对比：原声第 1 句 → 换声第 1 句 → 原声第 2 句 → …… 再点一次停止 */
  const btn = $('#cmp-ab', box); btn.disabled = false;
  const playRange = (au, s, e, token) => new Promise(res => {
    au.currentTime = Math.max(0, s - 0.08);
    au.play().catch(() => res());
    const iv = setInterval(() => { if (ab !== token || au.paused || au.currentTime >= e + 0.12) { clearInterval(iv); if (!au.paused && ab === token) au.pause(); res(); } }, 25);
  });
  const stopAB = () => { if (!ab) return; ab = null; A.pause(); B.pause(); btn.innerHTML = ICON.play + '逐句对比'; btn.classList.remove('busy'); $$('.sub.side', box).forEach(x => x.classList.remove('side')); };
  btn.onclick = async () => {
    if (ab) return stopAB();
    const token = ab = {}; btn.innerHTML = ICON.pause + '停止逐句'; btn.classList.add('busy');
    let start = Math.max(0, $('#cmp-a .sub.on', box) ? +$('#cmp-a .sub.on', box).dataset.i : 0);
    for (let i = start; i < src.length && ab === token; i++) {
      for (const [au, col, show] of [[A, '#cmp-a', showA], [B, '#cmp-b', showB]]) {
        if (ab !== token) break;
        showA(i); showB(i);
        $$('.sub.side', box).forEach(x => x.classList.remove('side')); $(`${col} .sub[data-i="${i}"]`, box)?.classList.add('side');
        $('#cmp-st', box).textContent = `逐句对比：第 ${i + 1}/${src.length} 句 · ${au === A ? '原声' : '换声'}`;
        await playRange(au, src[i].s, src[i].e, token);
        if (ab === token) await sleep(250);
      }
    }
    if (ab === token) { stopAB(); $('#cmp-st', box).textContent = '逐句对比播放完毕'; }
  };
  new MutationObserver((_, ob) => { if (!document.body.contains(box)) { ob.disconnect(); ab = null; A.pause(); B.pause(); } }).observe(document.body, { childList: true, subtree: true });
}

/* ================= 作品 ================= */
/* 作品页：类别 = 全部（默认，所有类型按时间排在一起）/ 配音 / 换声 / 图片 / 视频 / 语音转文字 / 提示词对话。
   配音、换声有两个标签：“已保存”（手动保存的）和“全部记录”（可按 全部 / 已完成 / 失败 筛选） */
let worksTab = 'works', histFilter = 'all', worksKind = 'any';
const W_KINDS = [['any', '全部'], ['tts', '配音'], ['vc', '换声'], ['img', '图片'], ['video', '视频'], ['stt', '语音转文字'], ['pg', '提示词对话']];
const W_AUDIO = k => k === 'tts' || k === 'vc';
const kindOf = j => j.kind === 'vc' ? 'vc' : 'tts';
const jobOk = j => j.state === 'done' && j.has_output;
const jobFailed = j => j.state === 'error';
async function renderWorks(keep) {
  if (!W_KINDS.some(k => k[0] === worksKind)) worksKind = worksKind === 'all' ? 'any' : 'any';  // 以前的“音频”（配音 + 换声）去掉了：换成“全部”
  // 切换类别：标题和两排按钮不重画，只换下面的列表；列表区先按住原来的高度，新内容出来再放开（不然高度先塌再撑开，会抖一下）
  const box0 = $('#wlist'), hold = keep && box0 ? box0.offsetHeight : 0;
  if (!keep || !$('#w-kind')) {
    $('#main').innerHTML = `<div class="page-head"><h1 class="page-title">作品</h1></div>
    <div class="row w-bar"><div class="seg" id="w-kind">${W_KINDS.map(([k, n]) => { const sh = { 语音转文字: '转文字', 提示词对话: '对话' }[n]; return `<button data-k="${k}"${sh ? ` aria-label="${n}"` : ''}>${sh ? `<span class="wk-l">${n}</span><span class="wk-s">${sh}</span>` : n}</button>`; }).join('')}</div>
      <span class="spacer"></span><div class="seg" id="w-tabs"><button data-t="works">已保存 <span class="tiny" id="w-n1"></span></button><button data-t="history">全部记录 <span class="tiny" id="w-n2"></span></button></div></div>
    <div id="w-filter" class="chips" style="margin-bottom:14px"></div>
    <div id="wlist" class="works"></div>`;
    $$('#w-kind button').forEach(b => b.onclick = () => { if (b.dataset.k !== worksKind) { worksKind = b.dataset.k; renderWorks(true); } });
  }
  $$('#w-kind button').forEach(b => b.classList.toggle('on', b.dataset.k === worksKind));
  const AUDIO = W_AUDIO(worksKind);
  $('#w-tabs').style.visibility = AUDIO ? '' : 'hidden';  // 不用 hidden：按钮那一排的高度（窄窗口时两行）保持不变
  $('#w-tabs').setAttribute('aria-hidden', AUDIO ? 'false' : 'true');
  const box = $('#wlist'); box.className = 'works'; box.dataset.html = ''; $('#w-filter').innerHTML = ''; $('#w-filter').dataset.html = '';
  if (hold) box.style.minHeight = hold + 'px';
  const release = () => requestAnimationFrame(() => { if (box.isConnected) box.style.minHeight = ''; });
  if (!AUDIO) {  // 全部 / 图片 / 视频 / 语音转文字 / 提示词对话：各自的列表（加载完再放开高度）
    pageRefresh(['jobs'], () => { if (worksKind === 'any') worksAll(); });
    return (worksKind === 'any' ? worksAll() : worksOther(worksKind)).finally(release);
  }
  setTimeout(release, 4000);  // 配音 / 换声：第一次读到列表时放开（见 tick），4 秒兜底
  const setTab = t => { worksTab = t; $$('#w-tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === t)); $('#wlist').dataset.html = ''; tick(); };
  $$('#w-tabs button').forEach(b => b.onclick = () => setTab(b.dataset.t));
  $$('#w-tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === worksTab));
  const row = j => {
    const running = ['queued', 'running'].includes(j.state);
    const status = jobOk(j) ? (j.warn ? `<span style="color:var(--orange)">${j.warn} ${unit(j)}建议检查</span>` : '<span style="color:#1f9d45">完成</span>')
      : jobFailed(j) ? `<span style="color:var(--red)">${j.message === '已取消' ? '已取消' : '生成失败'}${j.error && j.message !== '已取消' ? '：' + esc(j.error.slice(0, 40)) : ''}</span>`
      : `<span style="color:var(--blue)">${esc(j.message)}</span>${jobTimer(j, 'sm')}`;
    return `<div class="work">${vav(j.voice || j.id, '', 'w:' + j.id, j.voice_name || j.title)}<div style="min-width:0"><div class="tt">${esc(j.title)}${j.saved && worksTab === 'history' ? ' <span class="pill" style="margin-left:6px">已保存</span>' : ''}</div>
      <div class="tiny"><b style="color:var(--text);font-weight:600">${esc(j.model_name || j.model || '')}</b>${j.modes?.length ? ' · ' + esc(modesText(j)) : ''}${j.voice_name ? ' · ' + esc(j.voice_name) : ''}<br>${fmtTime(j.created)} · ${j.total} ${unit(j)} · ${fmtDur(j.duration)} · ${status}</div></div>
      <div class="row">${j.has_output ? `<button class="btn icon-btn" data-play="w:${j.id}" data-url="/media/job/${j.id}/output.mp3?t=${j.finished}" title="播放" aria-label="播放">${ICON.play}</button><a class="btn small" href="/media/job/${j.id}/output.mp3?dl=1">${ICON.dl}MP3</a>` : ''}
        ${jobOk(j) ? (j.saved ? `<button class="btn small" data-unsave="${j.id}" title="从作品中移除，历史记录中仍保留">移出作品</button>` : `<button class="btn small primary" data-savew="${j.id}">☆ 保存到作品</button>`) : ''}
        ${j.saved ? `<button class="btn small" data-rename="${j.id}">重命名</button>` : ''}
        <button class="btn small" data-open="${j.id}">详情</button>${running ? '' : `<button class="btn small ghost danger" data-wdel="${j.id}">删除</button>`}</div></div>`;
  };
  pageRefresh(['jobs'], () => tick());
  const tick = async (stop = () => { }) => {
    let err = null; const everything = await api('/api/jobs').catch(e => { err = e; return null; });
    if (!everything) { const b = $('#wlist'); if (!b) return stop(); if (!b.dataset.html) { b.innerHTML = loadFail('无法读取作品列表', err?.message, () => tick()); b.dataset.html = ''; bindLoadFail(); } return; }  // 读取失败：说清楚，别显示成“还没有作品”
    if (!W_AUDIO(worksKind)) return stop();  // 已经切到别的类别
    const all = everything.filter(j => kindOf(j) === worksKind);
    const box = $('#wlist'); if (!box) return stop();
    const saved = all.filter(j => j.saved);
    $('#w-n1').textContent = saved.length; $('#w-n2').textContent = all.length;
    const fbox = $('#w-filter');
    if (worksTab === 'history') {
      const counts = { all: all.length, ok: all.filter(jobOk).length, fail: all.filter(jobFailed).length };
      const fh = [['all', '全部'], ['ok', '已完成'], ['fail', '失败']].map(([k, n]) => `<button class="chip ${histFilter === k ? 'on' : ''}" data-f="${k}">${n} ${counts[k]}</button>`).join('');
      if (fbox.dataset.html !== fh) { fbox.innerHTML = fh; fbox.dataset.html = fh; $$('[data-f]', fbox).forEach(b => b.onclick = () => { histFilter = b.dataset.f; fbox.dataset.html = ''; box.dataset.html = ''; tick(); }); }
    } else { fbox.innerHTML = ''; fbox.dataset.html = ''; }
    const list = worksTab === 'works' ? saved : all.filter(j => histFilter === 'ok' ? jobOk(j) : histFilter === 'fail' ? jobFailed(j) : true);
    const html = list.length ? list.map(row).join('')
      : `<div class="card empty">${vav(null, 'lg', '', '♪')}${worksTab === 'works' ? '暂无已保存的作品。生成完成后点击“保存”，作品将显示在此处；所有生成记录均在“全部记录”中。' : histFilter === 'fail' ? '没有失败的记录。' : worksKind === 'vc' ? '暂无换声记录。' : '暂无生成记录，请前往“配音”生成第一个作品。'}</div>`;
    if (box.dataset.html !== html) { const wy = window.scrollY; box.innerHTML = html; box.dataset.html = html; if (Math.abs(window.scrollY - wy) > 1) window.scrollTo(0, wy); }
    release();
    $$('[data-play]', box).forEach(b => { if (b.dataset.play === playingKey && !player.paused) { b.classList.add('on'); b.innerHTML = ICON.pause; } b.onclick = () => { const w = b.closest('.work'); togglePlay(b.dataset.play, b.dataset.url, null, w ? { title: $('.tt', w)?.childNodes[0]?.textContent.trim(), sub: '作品', orb: b.dataset.orb } : null); }; });
    $$('[data-open]', box).forEach(b => b.onclick = () => openWork(b.dataset.open));
    const saveReq = async (id, body, msg) => { try { await api(`/api/jobs/${id}/save`, { body }); toast(msg); box.dataset.html = ''; tick(); } catch (e) { toast(e.message, true); } };
    $$('[data-savew]', box).forEach(b => b.onclick = () => saveReq(b.dataset.savew, { saved: true }, '已保存到“作品”'));
    $$('[data-unsave]', box).forEach(b => b.onclick = () => saveReq(b.dataset.unsave, { saved: false }, '已移出“作品”，历史记录中仍保留'));
    $$('[data-rename]', box).forEach(b => b.onclick = () => {
      const j = all.find(x => x.id === b.dataset.rename);
      modal(`<h3 class="card-title">重命名作品</h3><input class="input" id="rn" value="${esc(j.title)}" style="margin:12px 0">
        <div class="row" style="justify-content:flex-end"><button class="btn" data-close>取消</button><button class="btn primary" id="rn-ok">保存</button></div>`, m => {
        $('#rn', m).focus(); $('#rn', m).select();
        $('#rn-ok', m).onclick = async () => { const t = $('#rn', m).value.trim(); if (t) { m.close(); await saveReq(j.id, { title: t }, '已重命名'); } };
      });
    });
    $$('[data-wdel]', box).forEach(b => b.onclick = async () => {
      if (!await confirmBox('删除此记录？', '音频文件将一并删除，且无法恢复。', '删除', true)) return;
      try { await api('/api/jobs/' + b.dataset.wdel, { method: 'DELETE' }); toast('已删除'); } catch (e) { toast('删除失败：' + e.message, true); }
      box.dataset.html = ''; tick();
    });
    if (!everything.some(j => ['queued', 'running'].includes(j.state))) stop();
  };
  await pollStart(tick, 2000);
}
/* 作品页：图片（全部生成过的图）、语音转文字记录、提示词对话历史 */
/* 作品页 · 全部：配音、换声、图片、视频、语音转文字、提示词对话按时间倒序排在一起（最近 300 条），每条带类型角标；点开和各自类别里一样 */
async function worksAll() {
  const box = $('#wlist'); if (!box) return;
  const [jobs, imgs, vids, stt] = await Promise.all([api('/api/jobs').catch(() => null), api('/api/img/gallery').catch(() => null), api('/api/video/gallery').catch(() => null), api('/api/stt').catch(() => null)]);
  if (!$('#wlist') || worksKind !== 'any') return;
  const it = [];
  (jobs || []).forEach(j => it.push({ t: j.created, k: kindOf(j), j }));
  (imgs || []).forEach(x => it.push({ t: x.created, k: 'img', x }));
  (vids || []).forEach(x => it.push({ t: x.created, k: 'video', x }));
  (stt || []).forEach(x => it.push({ t: x.created, k: 'stt', x }));  // 提示词对话不放进“全部”，只在自己的类别里
  it.sort((a, b) => (b.t || 0) - (a.t || 0));
  const list = it.slice(0, 300), KN = Object.fromEntries(W_KINDS);
  const tag = k => `<span class="ve-new w-kt">${KN[k]}</span>`;
  const thumb = (src, vid) => `<span class="w-th${vid ? ' vid' : ''}"><img src="${esc(src)}" alt="" loading="lazy"></span>`;
  const html = list.length ? list.map((r, i) => {
    if (r.j) { const j = r.j; return `<div class="work" data-i="${i}" role="button" tabindex="0">${vav(j.voice || j.id, '', 'w:' + j.id, j.voice_name || j.title)}<div style="min-width:0"><div class="tt"><span class="tt-t">${esc(j.title)}</span>${tag(r.k)}</div>
      <div class="tiny">${fmtTime(j.created)} · ${esc(j.model_name || j.model || '')}${j.duration ? ' · ' + fmtDur(j.duration) : ''}${jobFailed(j) ? ' · <span style="color:var(--red)">生成失败</span>' : ''}</div></div>
      <div class="row">${j.has_output ? `<button class="btn icon-btn" data-play="w:${j.id}" data-url="/media/job/${j.id}/output.mp3?t=${j.finished}" title="播放" aria-label="播放">${ICON.play}</button>` : ''}<button class="btn small">详情</button></div></div>`; }
    if (r.k === 'img') { const x = r.x; return `<div class="work" data-i="${i}" role="button" tabindex="0">${thumb('/media/img/' + encodeURIComponent(x.file) + '?thumb=1')}<div style="min-width:0"><div class="tt"><span class="tt-t">${esc((x.prompt || x.note || '图片').slice(0, 80))}</span>${tag('img')}</div><div class="tiny">${fmtTime(x.created)} · ${x.width}×${x.height}${x.model_name ? ' · ' + esc(x.model_name) : ''}</div></div><div class="row"><button class="btn small">查看</button></div></div>`; }
    if (r.k === 'video') { const x = r.x; return `<div class="work" data-i="${i}" role="button" tabindex="0">${x.thumb ? thumb('/media/video/' + encodeURIComponent(x.thumb), 1) : `<span class="w-ic">${ICON.play}</span>`}<div style="min-width:0"><div class="tt"><span class="tt-t">${esc((x.prompt || '视频').slice(0, 80))}</span>${tag('video')}</div><div class="tiny">${fmtTime(x.created)} · ${x.width}×${x.height} · ${fmtDur(x.duration || x.seconds)}${x.model_name ? ' · ' + esc(x.model_name) : ''}</div></div><div class="row"><button class="btn small">播放</button></div></div>`; }
    if (r.k === 'stt') { const x = r.x; return `<div class="work" data-i="${i}" role="button" tabindex="0">${vav(x.id, '', '', x.filename)}<div style="min-width:0"><div class="tt"><span class="tt-t">${esc(x.filename)}</span>${tag('stt')}</div><div class="tiny">${fmtTime(x.created)} · ${fmtDur(x.duration)} · ${x.chars || 0} 字</div></div><div class="row"><button class="btn small">打开</button></div></div>`; }
    const h = r.h; return `<div class="work" data-i="${i}" role="button" tabindex="0"><span class="w-ic">${ICON.wand}</span><div style="min-width:0"><div class="tt"><span class="tt-t">${esc(h.title)}</span>${tag('pg')}</div><div class="tiny">${fmtTime(h.t)} · ${h.msgs.filter(m => m.role === 'user').length} 轮</div></div><div class="row"><button class="btn small">打开</button></div></div>`;
  }).join('') : '<div class="w-empty">暂无作品</div>';
  if (box.dataset.html === html) return;
  box.innerHTML = html; box.dataset.html = html;
  $$('[data-play]', box).forEach(b => { if (b.dataset.play === playingKey && !player.paused) { b.classList.add('on'); b.innerHTML = ICON.pause; } b.onclick = e => { e.stopPropagation(); const w = b.closest('.work'); togglePlay(b.dataset.play, b.dataset.url, null, w ? { title: $('.tt', w)?.childNodes[0]?.textContent.trim(), sub: '作品' } : null); }; });
  const open = r => {
    if (r.j) return openWork(r.j.id);
    if (r.k === 'img') { const L = list.filter(z => z.k === 'img').map(z => z.x); return ImageViewer.open(L.map(x => ({ src: '/media/img/' + encodeURIComponent(x.file), thumb: '/media/img/' + encodeURIComponent(x.file) + '?thumb=1', name: (x.prompt || '').slice(0, 60) })), Math.max(0, L.indexOf(r.x))); }
    if (r.k === 'video') return typeof vePlayBig === 'function' ? vePlayBig({ url: '/media/video/' + encodeURIComponent(r.x.file), dur: r.x.duration }) : go('video');
    if (r.k === 'stt') { sttCur = r.x.id; return go('stt'); }
    const st = pgState(); if (PG_RUN) return toast('AI 助手正在生成，请先停止', true);
    st.cur = r.h.id; st.msgs = r.h.msgs.map(m => ({ ...m })); if (r.h.preset) { st.preset = r.h.preset; st.cat = ''; } persist(); go('prompt');
  };
  $$('.work[data-i]', box).forEach(el => { el.onclick = () => open(list[+el.dataset.i]); el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(list[+el.dataset.i]); } }; });
}
async function worksOther(kind) {
  const box = $('#wlist'); if (!box) return;
  if (kind === 'img') {
    box.className = 'works card'; box.innerHTML = `<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">全部图片<span class="tiny" id="ig-n" style="margin-left:8px;font-weight:400"></span></h3><a class="btn small" href="/img" data-page="img">${ICON.wand}去生图</a></div><div class="ig-gal" id="w-gal"><div class="shimmer"></div></div>`;
    return imgGallery();
  }
  if (kind === 'video') {
    box.className = 'works card'; box.innerHTML = `<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">全部视频<span class="tiny" id="w-vn" style="margin-left:8px;font-weight:400"></span></h3><a class="btn small" href="/video" data-page="video">${ICON.wand}去生视频</a></div><div class="vd-gal" id="w-vgal"><div class="shimmer"></div></div>`;
    return vidGallery();
  }
  if (kind === 'stt') {
    const list = await api('/api/stt').catch(() => null); if (!$('#wlist')) return;
    if (!list) { box.innerHTML = loadFail('无法读取语音转文字记录', ''); return; }
    box.innerHTML = list.length ? list.map(j => `<div class="work" data-s="${esc(j.id)}" role="button" tabindex="0">${vav(j.id, '', '', j.filename)}<div style="min-width:0"><div class="tt">${esc(j.filename)}</div><div class="tiny">${fmtTime(j.created)} · ${fmtDur(j.duration)} · ${j.engine === 'whisper' ? 'Whisper' : 'Qwen3-ASR'} · ${j.chars || 0} 字</div></div><div class="row"><button class="btn small">打开</button></div></div>`).join('')
      : `<div class="card empty">${vav(null, 'lg')}暂无语音转文字记录。</div>`;
    $$('[data-s]', box).forEach(el => el.onclick = () => { sttCur = el.dataset.s; go('stt'); });
    return;
  }
  // 提示词对话：最近 ${PG_KEEP_DAYS} 天、最多 ${PG_KEEP_N} 条
  const all = pgHist(), list = [...all.filter(h => h.pin), ...all.filter(h => !h.pin)], when = t => fmtTime(t);  // 置顶的排在前面
  const PIN = '<svg class="w-pin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-label="已置顶"><path d="M9 3.5h6M10 3.5v5.2L6.8 12.4h10.4L14 8.7V3.5M12 12.4V20.5"/></svg>';
  box.innerHTML = list.length ? list.map(h => `<div class="work${h.pin ? ' pinned' : ''}" data-h="${esc(h.id)}" role="button" tabindex="0"><span class="w-ic">${ICON.wand}</span><div style="min-width:0"><div class="tt">${h.pin ? PIN : ''}${esc(h.title)}</div><div class="tiny">${when(h.t)} · ${h.msgs.filter(m => m.role === 'user').length} 轮</div></div><div class="row"><button class="btn small" data-open>打开</button><button class="btn small" data-pin data-tip="${h.pin ? '取消后，超过 ' + PG_KEEP_DAYS + ' 天的对话将自动删除' : '置顶的对话排在最前面，不会在 ' + PG_KEEP_DAYS + ' 天后自动删除'}">${h.pin ? '取消置顶' : '置顶'}</button><button class="btn small" data-ren>重命名</button><button class="btn small ghost danger" data-del>删除</button></div></div>`).join('')
    : `<div class="card empty">${vav(null, 'lg')}暂无提示词对话（保留最近 ${PG_KEEP_DAYS} 天）。</div>`;
  $$('[data-h]', box).forEach(el => el.onclick = e => {
    const id = el.dataset.h;
    if (e.target.closest('[data-del]')) { S.pgHist = pgHist().filter(h => h.id !== id); if (S.pg?.cur === id) { S.pg.cur = null; S.pg.msgs = []; } persist(); return worksOther('pg'); }
    if (e.target.closest('[data-pin]')) { const h = pgHist().find(z => z.id === id); if (!h) return; pgTogglePin(h); return worksOther('pg'); }
    if (e.target.closest('[data-ren]')) {
      const h = pgHist().find(z => z.id === id); if (!h) return;
      return modal(`<h3 class="card-title">重命名对话</h3><input class="input" id="rn" value="${esc(h.title)}" maxlength="60" style="margin:12px 0">
        <div class="row" style="justify-content:flex-end"><button class="btn" data-close>取消</button><button class="btn primary" id="rn-ok">保存</button></div>`, m => {
        const inp = $('#rn', m), ok = () => { const t = inp.value.trim(); if (!t) return toast('标题不能为空', true); h.title = t; h.named = true; persist(); m.close(); worksOther('pg'); };
        inp.focus(); inp.select(); inp.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); ok(); } };
        $('#rn-ok', m).onclick = ok;
      });
    }
    const h = pgHist().find(z => z.id === id); if (!h) return;
    const st = pgState(); if (PG_RUN) return toast('AI 助手正在生成，请先停止', true);
    st.cur = h.id; st.msgs = h.msgs.map(m => ({ ...m })); if (h.preset) { st.preset = h.preset; st.cat = ''; } persist(); go('prompt');  // 分类清空：页面打开时按这条的预设补上
  });
}
async function openWork(id) {
  let j; try { j = await api('/api/jobs/' + id); } catch (e) { return toast('无法打开详情：' + e.message, true); }
  const box = modal(`<div id="wd"></div><div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>关闭</button></div>`, null, true);
  let cur = j;
  const paint = jj => { cur = jj; if (!box.isConnected) return; $('#wd', box).innerHTML = jobCard(jj); $('#wd details', box)?.setAttribute('open', ''); bindJobCard($('#wd', box), jj, draw); };
  const draw = async () => { const jj = await api('/api/jobs/' + id).catch(() => null); if (jj) paint(jj); };
  paint(j);
  const iv = setInterval(() => { if (!box.isConnected) return clearInterval(iv); if (['queued', 'running'].includes(cur.state) && !$('.ap.on', box)) draw(); }, 1500);  // 还在生成：跟着更新
  const close0 = box.close; box.close = () => { close0(); clearInterval(iv); if ($('#rec-list')) recWatch(); };  // 详情里重做过：配音页的记录跟着刷新
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
}

/* ================= 生图（Z-Image Turbo · stable-diffusion.cpp） =================
   左边写想画什么、选模型 / 尺寸 / 张数，点“生成”（Ctrl + 回车也行）；右边上面是正在画的（实时预览、可以取消），下面是图库。
   图库：点开大图浏览（← → 翻页、右键退出、I 看提示词和种子）；每张可以“用这组设置”回填到左边、存进音源库（播放页里就能看到）、下载、删除。
   普通空间和私密空间各有自己的图库，互相看不到。 */
const IMG_SIZES = [['1:1', '方形', 1024, 1024], ['3:4', '竖图', 896, 1152], ['4:3', '横图', 1152, 896], ['9:16', '手机竖屏', 768, 1344], ['16:9', '宽屏', 1344, 768]];
const IMG_IC = {
  reuse: CI('<path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.7M20 4v4.7h-4.7M20 12a8 8 0 0 1-13.7 5.6L4 15.3M4 20v-4.7h4.7"/>'),
  lib: CI('<path d="M4 6.5h16M4 12h10M4 17.5h7"/><path d="M17.5 14v7M14 17.5h7"/>'),
  dl: CI('<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>'),
  del: CTX_IC.del,
  edit: CI('<path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M13.5 7.5l3 3"/>'),
  brush: CI('<path d="M14.5 4.5l5 5-8 8-5-5z"/><path d="M6.5 12.5 4 15c-1 1-1 4 1.5 4.5 2.5.5 3.5-1.5 4.5-2.5l2.5-2.5"/>'),
  up: CI('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><path d="M9 15l6-6M10 9h5v5"/>'),
  dice: CI('<rect x="4" y="4" width="16" height="16" rx="3.5"/><g fill="currentColor" stroke="none"><circle cx="9" cy="9" r="1.4"/><circle cx="15" cy="15" r="1.4"/><circle cx="15" cy="9" r="1.4"/><circle cx="9" cy="15" r="1.4"/><circle cx="12" cy="12" r="1.4"/></g>'),
};
let imgGal = [];
let IMGST = null;
let ENH_RUN = null;  // 正在跑的“先增强”（{t0, stop}）
const WITH_AI_J = ['ai'];  // 要临时载入 AI 助手的几档（和 q21.WITH_AI 一致）  // 生图状态：模型、默认参数、引擎支持的东西（采样器、调度器、LoRA、放大……）
let IMG_SRC = null;  // 图生图 / 局部重画的原图：{ kind: 'gallery', id, url, w, h } 或 { kind: 'upload', data, url, w, h, name }（上传的只在内存里）
let IMG_MASK = null;  // 局部重画涂抹的范围：和原图一样大的画布（白色 = 要重画）
const IMG_MODES = [['txt', '文生图'], ['img', '图生图'], ['inpaint', '局部重画'], ['edit', '指令改图']];
let IMG_CTL = null, IMG_REFS = [], IMG_POSE = null;  // IMG_POSE：Qwen 2.1 的 3D 人偶摆姿势 { data（人偶图 PNG）, pose_json（编辑器的姿势，不含人偶图）, w, h }  // IMG_REFS：指令改图的参考图（图 2、图 3）  // 参考图控制（ControlNet）用的图 { kind, data | id, url, w, h }
const imgDefaults = (model = S.img?.model) => {  // 每个模型自己的推荐参数（步数、CFG、采样器）
  const d = IMGST?.model_defaults?.[model] || IMGST?.defaults || {};
  return { steps: d.steps ?? 8, cfg: d.cfg ?? 1, sampler: d.sampler || '', scheduler: d.scheduler || '', flowShift: '', eta: '', strength: d.strength ?? .6, negative: '',
    hires: Object.assign({ enabled: false, upscaler: 'Latent', scale: 1.5, steps: 0, denoise: .5, by: 'scale', target_width: 2048, target_height: 2048 }, d.hires || {}, { by: 'scale', target_width: 2048, target_height: 2048 }),
    vaeTiling: !!d.vae_tiling, vaeTile: { size: d.vae_tile?.size ?? 256, overlap: d.vae_tile?.overlap ?? .5 }, cacheMode: d.cache_mode || '', cacheOption: d.cache_option || '',
    noiseSampler: d.noise_sampler || '', betaA: '', betaB: '', extraArgs: '', guidance: '', rng: d.rng || 'cuda', sage: !!d.sage,
    apg: { enabled: false, eta: 1, momentum: 0, norm_threshold: 5, ...(d.apg || {}), ...{ enabled: false } }, slg: { scale: 0, layers: '7,8,9', start: .01, end: .2 },
    maskGrow: 0, maskFeather: 4,
    loras: [], format: d.format || 'png', quality: d.quality ?? 92, meta: d.meta ?? true };
};
function maskOut(src, grow, feather) {  // 局部重画遮罩：白色区域向外扩 grow 像素，再羽化 feather 像素
  if (!grow && !feather) return src;
  const c = document.createElement('canvas'); c.width = src.width; c.height = src.height;
  const g = c.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, c.width, c.height);
  if (grow) {  // 扩张：模糊后把灰的都当成白的
    const t = document.createElement('canvas'); t.width = c.width; t.height = c.height;
    const tg = t.getContext('2d'); tg.fillStyle = '#000'; tg.fillRect(0, 0, t.width, t.height); tg.filter = `blur(${grow / 2}px)`; tg.drawImage(src, 0, 0); tg.filter = 'none';
    const d = tg.getImageData(0, 0, t.width, t.height), p = d.data;
    for (let n = 0; n < p.length; n += 4) { const v = p[n] > 8 ? 255 : 0; p[n] = p[n + 1] = p[n + 2] = v; p[n + 3] = 255; }
    tg.putImageData(d, 0, 0); src = t;
  }
  g.filter = feather ? `blur(${feather / 2}px)` : 'none'; g.drawImage(src, 0, 0); g.filter = 'none';
  return c;
}
const imgSize16 = (w, h) => {  // 原图的尺寸换成引擎能用的：最长边不超过 2048、最短边不小于 512，都是 16 的倍数
  let k = Math.min(1, 2048 / Math.max(w, h)); if (Math.min(w, h) * k < 512) k = 512 / Math.min(w, h);
  return [Math.max(512, Math.min(2048, Math.round(w * k / 16) * 16)), Math.max(512, Math.min(2048, Math.round(h * k / 16) * 16))];
};
/* 生图 / 生视频（v56，参考可灵）：提示词放最上面、最显眼；参数收成输入框底下的几个小按钮（点开是面板），
   参考图是输入框左边的“+”方块，“生成”在输入框右下角；下面整宽显示结果。原来表单里的控件原样搬进面板，事件都还在 */
const IG_CHEV = '<svg class="ig-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
/* 尺寸 / 时长那个小标签的图标：画面比例（参照 SF Symbols 的 aspectratio）。以前和“高级参数”一样是滑杆，手机上只剩图标时分不清（2026-11-15 界面检查） */
const IG_FRAME = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5.5" width="18" height="13" rx="3"/><path d="M6.5 11V9h2.5M17.5 13v2H15"/></svg>';
let PG_AUTO = false;  // 打开AI 助手后自动发送（反推提示词用）
async function imgDescribe(x) {
  const img = await pgImgPrep('/media/img/' + encodeURIComponent(x.file)).catch(() => null);
  if (!img) return toast('无法读取此图片', true);
  PG_AUTO = true; pgOpen('', 'img', 'img-describe', img);
}
/* 图片的标注和详情（和生视频页同一套）：缩略图左上角模型 / LoRA，左下角生成时间；鼠标停留显示完整信息（不含提示词）；点大图看详情和提示词 */
const IMG_SHORT = { 'zit-official': 'Z-Image 官方', 'zit-diving': 'Diving', krea2: 'Krea 2', qedit: 'Qwen 改图', q21: 'Qwen 2.1', 'q21-fast': 'Qwen 2.1 快速', moss: 'MOSS', 'moss-photo': 'MOSS 写真', h3img: 'H3-Image' };
function taReplace(ta, text) {  // 换掉输入框里整段文字，但保留浏览器自己的撤销记录（Ctrl+Z 回到上一版、Ctrl+Shift+Z 再回来；2026-11-16 用户）
  const ro = ta.readOnly; ta.readOnly = false; ta.focus({ preventScroll: true }); ta.select();
  let ok = false; try { ok = document.execCommand('insertText', false, text); } catch { }  // 各家编辑器保留原生撤销的通常做法
  if (!ok || ta.value !== text) { ta.value = text; ta.dispatchEvent(new Event('input', { bubbles: true })); }
  ta.readOnly = ro;
}
const IMG_VAR = { 'zit-official': '官方', 'zit-diving': 'Diving v7', krea2: 'Turbo 官方', qedit: 'Rapid AIO v23', 'q21-fast': '快速', q21: '高质量', moss: 'SFT', 'moss-photo': '写真', h3img: '原版' };  // 模型选择里每个底子下的版本短名
const imgShort = x => IMG_SHORT[x.model] || String(x.model_name || x.model || '').split(/[\s·(（]/)[0];
const imgT = t => { if (!t) return ''; const d = new Date(t * 1000), n = new Date(), p = v => String(v).padStart(2, '0'), hm = `${p(d.getHours())}:${p(d.getMinutes())}`; return d.toDateString() === n.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`; };
const imgTook = s => !s ? '' : s < 60 ? `${Math.round(s)} 秒` : `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒`;
const imgLoras = x => (x.loras || []).map(l => `${l.name} ${l.weight}`).join('、');
const IMG_MODE_N = { txt: '文生图', img: '图生图', inpaint: '局部重画', edit: '指令改图' };
const imgTip = x => [x.model_name || '', `生成于 ${imgT(x.created)}${x.seconds ? ` · 用时 ${imgTook(x.seconds)}` : ''}`, [x.width && `${x.width} × ${x.height}`, x.kind === 'upscale' ? '放大' : x.kind === 'extract' ? '提取的衣服' : IMG_MODE_N[x.mode]].filter(Boolean).join(' · '), `LoRA：${imgLoras(x) || '无'}`].filter(Boolean).join(String.fromCharCode(10));
function imgKV(x) {
  const dt = x.detail?.done && Object.keys(x.detail.done).length ? Object.entries(x.detail.done).map(([k, n]) => k + (n > 1 ? ' ×' + n : '')).join('、') : '';
  const kv = [['用途', x.note], ['模型', x.model_name], ['方式', x.kind === 'upscale' ? `放大 ${x.scale || 4} 倍` : IMG_MODE_N[x.mode]], ['尺寸', x.width && `${x.width} × ${x.height}`], ['步数', x.steps], ['CFG', x.cfg],
    ['采样器', x.sampler || (x.steps ? '默认' : '')], ['调度器', x.scheduler || (x.steps ? '默认' : '')], ['种子', x.seed], ['重绘强度', x.strength != null && x.mode !== 'edit' ? Math.round(x.strength * 100) + '%' : ''],
    ['放大细画', x.crop ? '是' : ''], ['参考图', x.refs ? `另 ${x.refs} 张（图 2${x.refs > 1 ? '、图 3' : ''}）` : ''], ['高清修复', x.hires?.enabled ? `×${x.hires.scale}` : ''], ['LoRA', imgLoras(x) || '无'], ['自动细化', dt], ['参考图控制', x.control ? `${x.control.type === 'canny' ? '线条' : '姿势'} ${Math.round(x.control.strength * 100)}%` : ''],
    ['提示词增强', ({ pe: '官方', ai: '助手' }[x.enhance] || '') + (x.enh_ver && x.enhance ? ' · ' + x.enh_ver : '')], ['用时', imgTook(x.seconds)], ['时间', imgWhen(x.created)]];
  return kv.filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `<span><i>${k}</i>${esc(String(v))}</span>`).join('');
}
/* ================= 对比：原图 / 原视频 与 生成结果（生图、生视频共用） =================
   o = { video, a: 原来的地址, b: 生成的地址, la, lb: 两边的名字, off: 原视频从第几秒对上成品的第 0 秒, title }
   看法：并排 / 滑动（同一个框里叠在一起，拖中间的竖线左右看）；视频以生成结果为准，原视频跟着它走（偏差大就跳过去，偏差小就微调播放速度追上） */
const IC_CMP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M12 3v18"/><path d="M7 10l-2 2 2 2M17 10l2 2-2 2"/></svg>';
/* 拖动进度条时让画面跟上：上一次跳转的画面画出来了，才跳到最新的位置（中间的位置直接跳过），不会越拖越慢 */
function vSeek(v, t) {
  if (!v) return; v._want = t; if (v._skBusy) return;
  const run = () => { const w = v._want; v._want = null; if (w == null) { v._skBusy = false; return; } v._skBusy = true;
    clearTimeout(v._skT); v._skT = setTimeout(() => { if (v._skBusy) { v._skBusy = false; if (v._want != null) run(); } }, 400);
    try { v.currentTime = w; } catch { v._skBusy = false; } };
  if (!v._skHook) { v._skHook = 1; v.addEventListener('seeked', () => { v._skBusy = false; if (v._want != null) run(); }); }
  run();
}
/* 对比播放器（可以放在弹窗里，也可以嵌在页面里）：o = { video, a, b, la, lb, off, inline, emptyA, emptyB, autoplay }
   并排 / 滑动；视频以生成结果为准（没有就以原视频为准），另一路跟着它走；一条进度条管两路 */
function abMount(root, o) {
  const V = !!o.video, key = V ? 'abModeV' : 'abModeI', two = !!(o.a && o.b); let off = +o.off || 0;  // off 可以晚一点再定（o.offP：量完帧差再对齐）
  // 声音放哪一路：每段视频各记各的（o.sndKey，2026-11-05 用户要求；以前是全局的、也没存下来）；没选过时用 o.sndDef（拼接好的视频默认原视频），再没有就是成品
  let mode = two ? (S[key] || (V ? 'side' : 'wipe')) : 'side', snd = (o.sndKey && S.abSndBy?.[o.sndKey]) || o.sndDef || 'b', pos = 50;
  const med = (u, c) => V ? `<video class="ab-m ${c}" src="${esc(u)}" preload="auto" playsinline muted></video>` : `<img class="ab-m ${c}" src="${esc(u)}" alt="" draggable="false">`;
  const pane = (u, c, l, emp, tb) => u ? `<div class="ab-pane ab-p${c}">${med(u, 'ab-' + c)}<span class="ab-tag${tb ? ' ab-tag-b' : ''}">${esc(l)}</span></div>` : emp ? `<div class="ab-pane ab-p${c} ab-empty">${emp}</div>` : '';
  root.innerHTML = `<div class="ab-stage">${pane(o.a, 'a', o.la, o.emptyA)}${pane(o.b, 'b', o.lb, o.emptyB, true)}${two ? '<div class="ab-line" aria-hidden="true"><span class="ab-knob"></span></div>' : ''}</div>
    <div class="ab-ctl">${V ? `<button type="button" class="ab-pl" aria-label="播放">${ICON.play}</button><span class="tiny ab-time">0:00.0</span>
      <div class="ab-bar" role="slider" tabindex="0" aria-label="播放进度"><div class="ab-fill"></div><div class="ab-dot"></div></div><span class="tiny ab-dur">0:00.0</span>` : '<span class="spacer"></span>'}
      ${two ? '<div class="seg ab-mode" role="group" aria-label="对比方式"><button type="button" data-m="side">并排</button><button type="button" data-m="wipe">滑动</button></div>' : ''}
      ${V && two ? '<div class="seg ab-snd" role="group" aria-label="播放哪一路的声音"><button type="button" data-s="a" data-tip="播放原视频的声音">原视频</button><button type="button" data-s="b" data-tip="播放生成结果的声音">成品</button><button type="button" data-s="off">静音</button></div>' : ''}</div>`;
  root.classList.add('ab-root'); root.classList.toggle('ab-inline', !!o.inline); if (!root.hasAttribute('tabindex')) root.tabIndex = -1;
  const stage = $('.ab-stage', root), A = $('.ab-a', root), B = $('.ab-b', root), M = B || A, O = B ? A : null;
  const ar = () => { const e = M; const w = e ? (V ? e.videoWidth : e.naturalWidth) : 0, h = e ? (V ? e.videoHeight : e.naturalHeight) : 0; return w && h ? w / h : 1; };
  const lay = () => { if (!root.isConnected) return; stage.classList.toggle('col', !o.inline && mode === 'side' && ar() > 1.15 && stage.clientWidth < 900); stage.style.setProperty('--ar', ar().toFixed(4)); };
  const setPos = p => { pos = Math.max(0, Math.min(100, p)); stage.style.setProperty('--p', pos + '%'); };
  const setMode = m => { mode = m; if (two) { S[key] = m; persist(); } stage.classList.toggle('wipe', m === 'wipe'); stage.classList.toggle('side', m === 'side');
    $$('.ab-mode button', root).forEach(b => b.classList.toggle('on', b.dataset.m === m)); lay(); setPos(pos); };
  $$('.ab-mode button', root).forEach(b => b.onclick = () => setMode(b.dataset.m));
  M?.addEventListener(V ? 'loadedmetadata' : 'load', lay); addEventListener('resize', lay);
  let wdrag = false;  // 滑动：按住画面左右拖，竖线跟着走
  const wat = e => { const r = stage.getBoundingClientRect(); setPos((e.clientX - r.left) / r.width * 100); };
  stage.addEventListener('pointerdown', e => { if (mode !== 'wipe' || !two) return; wdrag = true; try { stage.setPointerCapture(e.pointerId); } catch { } wat(e); e.preventDefault(); });
  stage.addEventListener('pointermove', e => { if (wdrag) wat(e); });
  stage.addEventListener('pointerup', () => { wdrag = false; }); stage.addEventListener('pointercancel', () => { wdrag = false; });
  setMode(mode);
  let raf = 0;
  const api = { stop: () => { cancelAnimationFrame(raf); removeEventListener('resize', lay); A?.pause?.(); B?.pause?.(); }, root };
  if (!V || !M) return api;
  // ---- 视频：一条进度条管两路
  const pl = $('.ab-pl', root), bar = $('.ab-bar', root), fill = $('.ab-fill', root), dot = $('.ab-dot', root), tm = $('.ab-time', root), td = $('.ab-dur', root);
  let scrub = null, hold = null;
  const fmt = t => { t = Math.max(0, t || 0); return `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`; };
  const dur = () => M.duration || 0;
  const draw = t => { const d = dur(); t = t ?? (scrub ?? M.currentTime ?? 0); const p = d ? Math.min(100, t / d * 100) : 0; fill.style.width = p + '%'; dot.style.left = p + '%'; tm.textContent = fmt(t); td.textContent = fmt(d); };
  const oT = t => Math.max(0, Math.min(t + off, (O?.duration || 1e9) - 0.04));
  const setT = t => { t = Math.max(0, Math.min(dur() || 0, t)); vSeek(M, t); if (O) vSeek(O, oT(t)); draw(t); };
  const sound = () => { const m = !!S.muted; [A, B].forEach(v => { if (v) v.volume = vol(); });
    if (two) { A.muted = m || snd !== 'a'; B.muted = m || snd !== 'b'; } else M.muted = m;
    $$('.ab-snd button', root).forEach(b => b.classList.toggle('on', b.dataset.s === snd)); };
  const isPlay = () => !M.paused && !M.ended;
  const btn = () => { const p = isPlay() || !!hold; pl.innerHTML = p ? ICON.pause : ICON.play; pl.setAttribute('aria-label', p ? '暂停' : '播放'); };
  const go = () => { if (M.ended || M.currentTime >= dur() - 0.05) setT(0); hold = null; sound(); Promise.all([M.play(), O?.play()]).catch(() => { }).finally(btn); btn(); };
  const stop = () => { hold = null; M.pause(); O?.pause(); if (O) { O.playbackRate = 1; vSeek(O, oT(M.currentTime)); } btn(); };
  pl.onclick = () => (isPlay() || hold ? stop() : go());
  // 进度条：按住拖动 = 画面实时跟着（暂停着拖，松手后原来在播就接着播）
  let was = false;
  const at = e => { const r = bar.getBoundingClientRect(), d = dur(); return d ? Math.max(0, Math.min(d - 0.001, (e.clientX - r.left) / r.width * d)) : 0; };
  bar.addEventListener('pointerdown', e => { was = isPlay(); M.pause(); O?.pause(); scrub = at(e); bar.classList.add('on'); try { bar.setPointerCapture(e.pointerId); } catch { } setT(scrub); e.preventDefault(); });
  bar.addEventListener('pointermove', e => { if (scrub == null) return; scrub = at(e); setT(scrub); });
  const up = () => { if (scrub == null) return; scrub = null; bar.classList.remove('on'); if (was) go(); else btn(); };
  bar.addEventListener('pointerup', up); bar.addEventListener('pointercancel', up);
  $$('.ab-snd button', root).forEach(b => b.onclick = () => { snd = b.dataset.s;
    if (o.sndKey) { const m = S.abSndBy = S.abSndBy || {}; delete m[o.sndKey]; m[o.sndKey] = snd; const ks = Object.keys(m); if (ks.length > 400) ks.slice(0, ks.length - 400).forEach(k => delete m[k]); }  // 最多记 400 段
    persist(); sound(); });
  stage.addEventListener('click', e => { if (mode === 'side' && !e.target.closest('.ab-empty')) pl.click(); });  // 并排时点画面 = 播放 / 暂停
  if (O) [A, B].forEach(v => {  // 有一路在缓冲：另一路先停一下，等它好了一起走
    v.addEventListener('waiting', () => { if (!isPlay() || hold) return; hold = v; (v === A ? B : A).pause(); });
    v.addEventListener('playing', () => { if (hold === v) { hold = null; (v === A ? B : A).play().catch(() => { }); } btn(); });
  });
  M.addEventListener('ended', () => { O?.pause(); if (O) O.playbackRate = 1; btn(); draw(); });
  M.addEventListener('pause', btn); M.addEventListener('loadedmetadata', () => { draw(); if (o.autoplay) go(); });
  ['play', 'pause', 'ended'].forEach(ev => M.addEventListener(ev, () => o.onState?.()));  // 外面（缩略图上的播放 / 暂停图标）跟着变
  api.toggle = () => pl.click(); api.playing = () => isPlay() || !!hold;  // 外面点缩略图：播放 / 暂停这个对比播放器
  const tick = () => { if (!root.isConnected) return;
    if (O && isPlay() && !hold && O.readyState >= 2 && !O.ended && scrub == null) { const want = M.currentTime + off, d = O.currentTime - want;
      if (Math.abs(d) > 0.3) vSeek(O, want); else O.playbackRate = Math.abs(d) < 0.03 ? 1 : d > 0 ? 0.92 : 1.08;
      if (O.paused && want < (O.duration || 0) - 0.05) O.play().catch(() => { }); }
    if (isPlay() || scrub != null) draw(); raf = requestAnimationFrame(tick); };
  raf = requestAnimationFrame(tick);
  api.key = e => { if (e.target?.closest?.('textarea, select, input')) return false;
    if (e.key === ' ') { e.preventDefault(); pl.click(); return true; }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setT(M.currentTime + (e.key === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 5 : 1)); return true; } return false; };
  if (o.inline) root.addEventListener('keydown', e => api.key(e));  // 嵌在页面里：点过它以后空格 / 左右键管它
  bar.addEventListener('keydown', e => { if (!o.inline) api.key(e); });
  O?.addEventListener('loadedmetadata', () => { O.currentTime = off; });
  o.offP?.then?.(v => { if (typeof v !== 'number' || !root.isConnected || Math.abs(v - off) < 0.001) return; off = v; if (O) vSeek(O, oT(M.currentTime)); });
  sound(); btn(); draw();
  return api;
}
function abCompare(o) {  // 弹窗里的对比
  const box = modal(`<div class="row between ab-head"><h3 class="card-title" style="margin:0">对比${o.title ? ' · ' + esc(o.title) : ''}</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div><div class="ab-host"></div>`, null, true);
  box.classList.add('ab-modal');
  const ab = abMount($('.ab-host', box), o);
  const keys = e => { if ([...document.querySelectorAll('.modal-bg:not(.out)')].pop() !== box.parentElement) return; ab.key?.(e); };
  if (o.video) document.addEventListener('keydown', keys, true);
  const c0 = box.close; box.close = () => { ab.stop(); document.removeEventListener('keydown', keys, true); c0(); };
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
  return box;
}
/* 生图：这张图对比的是哪张（改图 / 图生图 / 局部重画 / 放大 → 原图；文生图细化过 → 细化前） */
function imgCmpSrc(x) {
  if (!x) return null;
  const u = f => '/media/img/' + encodeURIComponent(f);
  if (x.src_file) return { a: u(x.src_file), la: '原图' };
  const g = x.src && imgGal.find(y => y.id === x.src);
  if (g) return { a: u(g.file), la: '原图' };
  const r1 = x.refine_of && imgGal.find(y => y.id === x.refine_of);  // 二采（Krea 2 润色）：和同一张的一采对比
  if (r1) return { a: u(r1.file), la: '一采' };
  if (x.orig) return { a: u(x.orig), la: '细化前' };
  return null;
}
function imgCompare(x) {
  const s = imgCmpSrc(x); if (!s) return toast('这张图没有可对比的原图', true);
  abCompare({ a: s.a, la: s.la, b: '/media/img/' + encodeURIComponent(x.file), lb: s.la === '细化前' ? '细化后' : s.la === '一采' ? '二采' : '生成结果', title: x.model_name || '' });
}
/* 2026-11-10 用户：生图页宽窗口——空画面（点缩略图查看）；上传 / 选了原图时把原图放大在画面上（× 回到空画面，原图格里的图不动） */
function imgStageBack() {  // 局部重画时搬到大画面上的原图（#ig-src，带涂抹画布）放回原图面板；面板已经重画过（占位没了）就丢掉旧的
  const box = $('#ig-stage #ig-src'); if (!box) return;
  const ph = $('#ig-src-ph2'); box.classList.remove('stg');
  if (ph) ph.replaceWith(box); else box.remove();
}
/* 原图放回大画面（点了 × 以后，点输入框左上角原图那一格；或切到局部重画） */
function imgSrcToStage() { if (!IG_WIDE() || !IMG_SRC?.url) return; imgStage.srcOn = true; imgStage.closed = false; imgStage.off = false; const g = $('#ig-gal'); if (g) delete g.dataset.sig; imgGallery(); }
function imgStageBox() {
  imgStageBack();
  const card = $('#ig-gal')?.closest('.ig-gal-card'); if (!card) return null;
  let st = $('#ig-stage'); if (!st) { st = document.createElement('div'); st.id = 'ig-stage'; st.className = 'vd-stage ig-stage'; card.insertBefore(st, $('#ig-gal')); }
  imgStage.cur = null; $$('#ig-gal .ig-tile').forEach(t => t.classList.remove('on')); card.classList.toggle('port', galCol(card)); return st;
}
function imgStageClosed() {
  const st = imgStageBox(); if (!st) return;
  st.innerHTML = `<div class="vd-ab-empty vd-empty vd-closed"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M20 16l-4.5-4.5L7 19.5"/></svg><span>点击缩略图查看</span></div>`;
  st.onclick = null;
}
function imgStageSrc() {
  const st = imgStageBox(); if (!st || !IMG_SRC?.url) return;
  const box = S.img?.mode === 'inpaint' && $('#ig-src-f #ig-src');
  if (box && $('#ig-mask-c', box)) {  // 2026-11-10 用户：局部重画找不到涂的地方（涂抹画布在收起的原图面板里）——直接在大画面上涂
    st.innerHTML = `<div class="ig-stage-paint"><div class="ig-stage-pbox"></div>
      <div class="row ig-stage-mbar"><span class="tiny">在图上涂抹要重画的地方${hintHtml('快捷键：B 涂抹、E 擦除、W 智能选取，按住 Ctrl 临时换成另一种；Ctrl+Z 撤销。滚轮缩放（右栏的小图里按住 Ctrl 再滚）；放大后按住空格、鼠标右键或中键拖动可移动画面，点左上角的百分比还原。', 'sm')}</span><span class="tiny">画笔</span><input type="range" min="4" max="100" data-a="size" aria-label="画笔大小">
        <div class="seg"><button type="button" data-a="draw">涂抹</button><button type="button" data-a="erase">擦除</button></div><button type="button" class="pl-ib ig-smart" data-msmart aria-pressed="false" aria-label="智能选取" data-tip="智能选取（W）：在图上点一下要改的东西，自动选出它的轮廓（点衣服只选衣服）；同一处再点一下选大一圈（整个人）。擦除模式或按住 Ctrl 点 = 去掉那一块；选完可以接着用画笔修"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m4 20 10.5-10.5"/><path d="m13 8 3 3"/><path d="M18 3v3M16.5 4.5h3M20 9v2M19 10h2M10 3v2M9 4h2"/></svg></button><button type="button" class="pl-ib ig-mundo" data-mundo="undo" aria-label="撤销" data-tip="撤销（Ctrl+Z）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button><button type="button" class="btn small ghost" data-a="clear">清空</button>
        <button type="button" class="pl-ib" data-s="close" title="关闭大图（原图仍在原图格里）" aria-label="关闭大图">${ICON.x}</button></div></div>`;
    const ph = document.createElement('div'); ph.id = 'ig-src-ph2'; ph.hidden = true; box.before(ph);
    box.classList.add('stg'); $('.ig-stage-pbox', st).append(box);
    const bar = $('.ig-stage-mbar', st), rng = $('[data-a=size]', bar), pb = $('#ig-brush');
    if (pb) rng.value = pb.value;
    const pen = () => $$('[data-a=draw], [data-a=erase]', bar).forEach(b => b.classList.toggle('on', !!$(`#ig-pen [data-p="${b.dataset.a}"].on`)));
    pen();
    rng.oninput = () => { if (pb) { pb.value = rng.value; pb.oninput?.({ target: pb }); } };
    renderImg.maskUndoPaint?.();
    renderImg.maskSmartPaint?.();
    bar.onclick = e => { if (e.target.closest('[data-mundo]')) return renderImg.maskUndo?.(); if (e.target.closest('[data-msmart]')) return renderImg.maskSmartToggle?.(); const a = e.target.closest('[data-a]')?.dataset.a;
      if (a === 'draw' || a === 'erase') { $(`#ig-pen [data-p="${a}"]`)?.click(); pen(); } else if (a === 'clear') $('#ig-mask-x')?.click(); };
  } else
  st.innerHTML = `<div class="ig-stage-img ig-stage-src"><img src="${esc(IMG_SRC.url)}" alt="" draggable="false"><span class="ig-stage-lab">原图</span><button type="button" class="ig-stage-x" data-s="close" title="关闭大图（原图仍在原图格里）" aria-label="关闭大图">${ICON.x}</button></div>`;
  st.onclick = e => { if (!e.target.closest('[data-s="close"]')) return; imgStage.srcOn = false; imgStage.closed = true; const g = $('#ig-gal'); if (g) delete g.dataset.sig; imgGallery(); };
}
const IC_INFO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.1"/></svg>';
function imgStage(i) {  // 生图页右边的大图预览
  const card = $('#ig-gal')?.closest('.ig-gal-card'); if (!card) return;
  let st = $('#ig-stage'); if (!st) { st = document.createElement('div'); st.id = 'ig-stage'; st.className = 'vd-stage ig-stage'; card.insertBefore(st, $('#ig-gal')); }
  imgStageBack();
  const x = i == null ? null : imgGal[i]; imgStage.cur = x ? i : null; if (x) { imgStage.closed = false; imgStage.srcOn = false; $('#ig-live')?.classList.remove('open'); }
  card.classList.toggle('port', !!x && galCol(card));  // 缩略图在右边一列还是下面一排：用户自己选（默认下面一排，记住选择）
  $$('#ig-gal .ig-tile').forEach(t => t.classList.toggle('on', +t.dataset.i === imgStage.cur));
  if (!x) { st.innerHTML = ''; return; }
  const u = '/media/img/' + encodeURIComponent(x.file);
  st.innerHTML = `<div class="ig-stage-img"><img src="${u}" alt="" draggable="false"><button type="button" class="ig-stage-x" data-s="close" title="关闭大图" aria-label="关闭大图">${ICON.x}</button></div>
    <div class="row vd-stage-bar"><span class="tiny vd-stage-i" title="${esc(imgTip(x))}">${esc([x.model_name, (x.loras || []).length ? 'LoRA ' + imgLoras(x) : '无 LoRA', imgT(x.created) + (x.seconds ? '（用时 ' + imgTook(x.seconds) + '）' : ''), x.width && `${x.width} × ${x.height}`].filter(Boolean).join(' · '))}</span><span class="spacer"></span>
      <button type="button" class="btn small" data-s="reuse">${IMG_IC.reuse}复用</button><button type="button" class="btn small" data-s="edit">${IMG_IC.edit}改图</button>
      <a class="btn small" href="${u}" download="${esc(x.file)}">${ICON.dl}下载</a><button type="button" class="btn small" data-s="desc"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2"/><path d="M8 10h8M8 14h5"/></svg>反推</button>${imgCmpSrc(x) ? `<button type="button" class="btn small" data-s="cmp" title="与${imgCmpSrc(x).la}对比">${IC_CMP}对比</button>` : ''}<button type="button" class="btn small" data-s="view" title="详情和提示词">${IC_INFO}详情</button><button type="button" class="btn small danger" data-s="del">${IMG_IC.del}删除</button></div>`;
  fitCompact($('.vd-stage-bar', st), stageTight, ['c1']);
  { const im = $('.ig-stage-img img', st); if (im) im.onerror = () => { const w = im.parentElement; if (w && !w.querySelector('.ig-stage-err')) w.insertAdjacentHTML('beforeend', '<span class="ig-stage-err">图片读取失败</span>'); }; }  // 2026-11-10：读不出来时写出来（以前只是一片黑，分不清是没加载新版本还是图坏了）
  st.onclick = e => { const a = e.target.closest('[data-s]')?.dataset.s; if (a === 'close') { if (IG_WIDE()) imgStage.closed = true; else imgStage.off = true; const g = $('#ig-gal'); if (g) delete g.dataset.sig; return imgGallery(); } if (a === 'reuse') imgReuse(x); else if (a === 'edit') renderImg.useSrc?.(x, 'img'); else if (a === 'del') imgDelete([x]); else if (a === 'desc') imgDescribe(x); else if (a === 'cmp') imgCompare(x); else if (a === 'view') imgView(i, { info: true }); else if (e.target.closest('.ig-stage-img')) imgView(i); };  // 2026-11-16 用户：点图直接看大图（照 Apple 相册），详情从下面的 (i) 或大图右上角的「···」进
}
/* 生图 / 生视频 大画面下的缩略图：排在下方（默认）或右侧一列；用户选的记住（S.galLay）。右边太窄时仍排在下方 */
/* 缩略图位置图标：外框 + 缩略图那一块（浅色填充）。鼠标停上去时，那一块用动画滑到另一种排法的位置（下方 ⇄ 右侧），点了就是这样（2026-11-05 用户要求） */
const GAL_LAY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect class="gl-p" rx="1.2"/><rect x="3.5" y="4.5" width="17" height="15" rx="2"/></svg>';
const GAL_LAY_IC = { row: GAL_LAY_SVG, col: GAL_LAY_SVG };
/* 鼠标滚轮横着滚（下方那一排缩略图）：不再一格一跳，按滚动的量平滑地滑过去（2026-11-05 用户要求） */
function smoothHScroll(el, e) {
  const k = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? el.clientWidth : 1, max = el.scrollWidth - el.clientWidth;
  let s = el._hs; if (!s?.run) s = el._hs = { t: el.scrollLeft, run: false };
  s.t = Math.max(0, Math.min(max, s.t + e.deltaY * k));
  if (s.run) return; s.run = true;
  const step = () => {
    const c = el.scrollLeft, d = s.t - c;
    if (!el.isConnected || Math.abs(d) < 1) { if (el.isConnected) el.scrollLeft = s.t; s.run = false; return; }
    let v = d * 0.2; if (Math.abs(v) < 1) v = Math.sign(d);
    el.scrollLeft = c + v;
    if (el.scrollLeft === c) { s.run = false; return; }  // 到头了
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const galCol = card => S.galLay === 'col' && !S.galFold && !(card?.clientWidth && card.clientWidth < 860) && !B5_COL();  // 创作栏版：缩略图固定在视频下面（2026-11-19 用户：左边东西太多）
const galLayBtn = id => `<span class="gal-home" hidden></span><button type="button" class="pl-ib gal-lay" id="${id}" data-l="${S.galLay === 'col' ? 'col' : 'row'}" aria-label="缩略图位置">${GAL_LAY_IC[S.galLay === 'col' ? 'col' : 'row']}</button><button type="button" class="pl-ib gal-lay gal-fb" id="${id}-f" aria-label="收起缩略图"></button>`;
const GAL_FOLD_D = { down: 'M6 9l6 6 6-6', up: 'M6 15l6-6 6 6', right: 'M9 6l6 6-6 6', left: 'M15 6l-6 6 6 6' };
function galLayBind(id, redo) {
  const b = $('#' + id); if (!b) return; const col = S.galLay === 'col';
  b.innerHTML = GAL_LAY_IC[col ? 'col' : 'row']; b.dataset.l = col ? 'col' : 'row'; b.dataset.tip = col ? '缩略图在左边' : '缩略图在下面';
  // 换排法 / 展开时：缩略图先藏住，等重新排好（到了左边一列 / 下面一排）再显示——以前先在下面出现一下才跳到左边（2026-11-08 用户）
  const run = () => { const cd = b.closest('.ig-gal-card') || b._card;
    if (cd) { const st = cd.querySelector(':scope > #vd-stage, :scope > #ig-stage'); if (!S.galFold && st?.firstElementChild) cd.classList.toggle('port', galCol(cd));
      cd.classList.add('gal-hold'); clearTimeout(cd._holdT); const rel = () => cd.classList.remove('gal-hold'); cd._holdT = setTimeout(rel, 800);
      galLayBind(id, redo); Promise.resolve(redo()).then(() => requestAnimationFrame(() => requestAnimationFrame(rel)), rel); return; }
    galLayBind(id, redo); redo(); };
  b.onclick = () => { S.galLay = col ? 'row' : 'col'; persist(); run(); };
  // 收起 / 展开缩略图那一块（右侧一列或下方一排都适用；记住选择）
  const F = !!S.galFold, f = $('#' + id + '-f'); (b.closest('.ig-gal-card') || b._card)?.classList.toggle('gal-fold', F); b.hidden = F || B5_COL();  // 创作栏版：缩略图只在下面，“排法”按钮没用
  if (f) { delete f.dataset.d;  // 2026-11-08 用户：左上角箭头太多——换成面板图标（和右上角收起选项栏那个对称），缩略图那一块显示着就填上浅色
    f.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${F ? '' : col ? '<rect x="3" y="3" width="6" height="18" rx="2" fill="currentColor" opacity=".28" stroke="none"/>' : '<rect x="3" y="15" width="18" height="6" rx="2" fill="currentColor" opacity=".28" stroke="none"/>'}<rect x="3" y="3" width="18" height="18" rx="2"/><path d="${col ? 'M9 3v18' : 'M3 15h18'}"/></svg>`;
    f.dataset.tip = F ? '展开缩略图' : '收起缩略图'; f.setAttribute('aria-label', f.dataset.tip); f.setAttribute('aria-pressed', String(!F));
    f.onclick = () => { S.galFold = !F; persist(); run(); }; }
  const card = b.closest('.ig-gal-card') || b._card; if (card) { galLayPlace(card); if (!card._galRO) { card._galRO = new ResizeObserver(() => galLayPlace(card)); card._galRO.observe(card); }
    const stg = card.querySelector(':scope > #vd-stage, :scope > #ig-stage'); if (stg && card._galStg !== stg) { card._galStg = stg; card._galRO.observe(stg); } }  // 生图页打开大图时卡片大小不变：大图那块变了也重新摆
}
/* 缩略图排在大画面下面时（2026-11-06 用户：大部分时候缩略图在下面，按钮放在上面怪怪的）：
   缩略图下面一行 = 拖动条 + 排法、收起两个按钮（拖动条是自己画的，代替浏览器的横向滚动条，右端让出按钮的位置；缩略图本身保持全宽）；
   收起后只剩“展开”按钮，还在那一行的最右边（用户：放中间很怪）。
   缩略图设成右侧一列时（宽度够、真的排在右边）：按钮一直在标题栏里，收起后也是；平铺全部时也在标题栏 */
function galLeftActs() {  // 标题栏左边、标题后面的一小组按钮（缩略图的排法 / 收起）
  const h = $('#main > .page-head'); if (!h) return null;
  let a = h.querySelector('.b5-gl'); if (a) return a;
  a = document.createElement('div'); a.className = 'b5-gl';
  const ctx = h.querySelector(':scope > .b5-ctx');
  if (ctx && h.classList.contains('b5-head')) { const w = document.createElement('div'); w.className = 'b5-l'; ctx.before(w); w.append(ctx, a); }  // 生视频的标题栏是三栏：和“改视频 ▾”放在同一栏
  else (h.firstElementChild || h).after(a);
  return a;
}
function galLayPlace(card) {
  const b = card.querySelector('.gal-lay:not(.gal-fb)') || (card._lb?.isConnected && card._lb), f = card.querySelector('.gal-fb') || (card._lf?.isConnected && card._lf), home = card.querySelector('.gal-home'); if (!b || !f || !home) return;
  card._lb = b; card._lf = f; b._card = f._card = card;
  const strip = card.querySelector(':scope > #vd-gal, :scope > #ig-gal'), stage = card.querySelector(':scope > #vd-stage, :scope > #ig-stage');
  const right = S.galLay === 'col' && !(card.clientWidth && card.clientWidth < 860) && !B5_COL();  // 和 galCol 一样的宽度条件，但不看收没收起
  const staged = !!stage && !stage.hidden && stage.offsetHeight > 40, bottom = !!strip && staged && !right;
  let ctl = card.querySelector(':scope > .gal-ctl');
  if (bottom) {
    if (!ctl) { ctl = document.createElement('div'); ctl.className = 'gal-ctl'; ctl.innerHTML = '<div class="gal-sb"><div class="gal-sb-th"></div></div>'; }
    if (ctl.previousElementSibling !== strip) strip.after(ctl);
    const acts = card.closest('.ig-grid.b5-on') && galLeftActs();  // 新版：按钮在标题栏左边（2026-11-07 用户：右边按钮太多），这一行只剩拖动条
    if (acts) { if (b.parentElement !== acts) acts.prepend(b, f); } else if (b.parentElement !== ctl) ctl.append(b, f);
    card.classList.add('gal-ctl-on');
    galSb(ctl.firstElementChild, strip);
  } else {
    // 宽窗口新版（提示词在底部）：放进标题栏右边那排图标里，不单独占一行（2026-11-07）
    const acts = card.closest('.ig-grid.b5-on') && galLeftActs();
    if (acts) { if (b.parentElement !== acts) acts.prepend(b, f); } else if (b.previousElementSibling !== home) home.after(b, f);
    ctl?.remove(); card.classList.remove('gal-ctl-on');
  }
  const gl = $('#main > .page-head .b5-gl'); if (gl) gl.hidden = !staged;  // 没有大画面（全部平铺 / 还没有结果）：排法、收起按钮没用，不显示
}
/* 缩略图那一排的拖动条：跟着滚动位置画，拖动滑块或点空白处翻一页 */
function galSb(sb, strip) {
  const th = sb.firstElementChild;
  const geo = () => { const sw = strip.scrollWidth, cw = strip.clientWidth, tw = sb.clientWidth, w = Math.max(28, tw * cw / Math.max(sw, 1)); return { sw, cw, tw, w, max: Math.max(0, sw - cw) }; };
  const paint = () => { const g = geo(); sb.classList.toggle('none', g.max < 2 || !g.tw);
    if (g.max >= 2) { th.style.width = g.w + 'px'; th.style.transform = `translateX(${(g.tw - g.w) * strip.scrollLeft / g.max}px)`; } };
  if (sb._strip !== strip) {
    sb._strip = strip;
    strip.addEventListener('scroll', paint, { passive: true });
    new MutationObserver(() => requestAnimationFrame(paint)).observe(strip, { childList: true });
    new ResizeObserver(paint).observe(strip);
    sb.addEventListener('pointerdown', e => {
      if (e.button !== 0) return; e.preventDefault(); const g = geo(); if (g.max < 2) return;
      if (e.target !== th) { const x = e.clientX - sb.getBoundingClientRect().left; strip.scrollBy({ left: (x < (g.tw - g.w) * strip.scrollLeft / g.max ? -1 : 1) * g.cw * .9, behavior: 'smooth' }); return; }
      const x0 = e.clientX, s0 = strip.scrollLeft, k = g.max / Math.max(1, g.tw - g.w);
      try { sb.setPointerCapture(e.pointerId); } catch { } sb.classList.add('drag');
      const mv = ev => { strip.scrollLeft = s0 + (ev.clientX - x0) * k; };
      const up = () => { sb.classList.remove('drag'); sb.removeEventListener('pointermove', mv); sb.removeEventListener('pointerup', up); sb.removeEventListener('pointercancel', up); };
      sb.addEventListener('pointermove', mv); sb.addEventListener('pointerup', up); sb.addEventListener('pointercancel', up);
    });
  }
  paint();
}
imgStage.off = false; imgStage.closed = true;  // 2026-11-10 用户：打开生图页先是空画面（以前先平铺全部图片）；右上角“全部图片”点一下平铺、再点一下回到空画面
const IG_WIDE = () => matchMedia('(min-width: 1200px)').matches;  // 宽窗口：左右排，参数直接展开在左栏
async function clipImage() {
  try {
    for (const it of await navigator.clipboard.read()) { const t = it.types.find(x => x.startsWith('image/')); if (t) return new File([await it.getType(t)], 'paste.' + t.split('/')[1], { type: t }); }
    toast('剪贴板中没有图片', true);
  } catch { toast(`此处无法直接读取剪贴板：请将鼠标停在此格上并按 ${/Mac/.test(navigator.platform) ? '⌘' : 'Ctrl'} + V`, true); }
  return null;
}
/* 空间不够时按钮只留图标（鼠标停留显示文字）：一级一级收（c1：次要按钮；c2：生成按钮），收到不挤为止；空间够了自动恢复。
   不为缩小而缩小：只在真的会挤到第二行 / 把信息截断时才收 */
function fitCompact(el, tooTight, levels = ['c1', 'c2']) {
  if (!el) return;
  el._fcTest = tooTight; el._fcLv = levels;
  $$('button, a.btn', el).forEach(b => { if (!b.title) { const t = (b.textContent || '').trim(); if (t) b.title = t; } });  // 只剩图标时靠悬停看文字
  // 后面几级要真的有用才收：手机上生成按钮单独占一行，收掉“生成”两个字也不会少一行，就别收
  const run = () => { if (!el.isConnected) return; levels.forEach(c => el.classList.remove(c)); let h = el.offsetHeight;
    for (const [k, c] of levels.entries()) { if (!el._fcTest(el)) break; el.classList.add(c); if (k && el._fcTest(el) && el.offsetHeight >= h) { el.classList.remove(c); break; } h = el.offsetHeight; } };
  el._fcRun = run;
  if (!el._fcRO && window.ResizeObserver) { el._fcRO = new ResizeObserver(() => { if (!window.fsHold?.()) requestAnimationFrame(run); }); el._fcRO.observe(el); }
  run(); requestAnimationFrame(run);
}
// 是否换了行：第一行最矮的那个元素的底边以下还有元素（看不见的占位 / 高度很小的不算）
const wrapped = ks => { ks = ks.filter(c => c.offsetWidth > 2 && c.offsetHeight > 6); if (ks.length < 2) return false;
  const rs = ks.map(c => c.getBoundingClientRect()), t0 = Math.min(...rs.map(r => r.top)), first = rs.filter(r => r.top < t0 + 4), b0 = Math.min(...first.map(r => r.bottom));
  return rs.some(r => r.top >= b0 - 2); };
const rowsOf = box => wrapped([...box.children]) ? 2 : 1;
const wrapOf = el => wrapped([...el.querySelectorAll(':scope > .bar-l > *, :scope > .bar-l > .ig-chips > *, :scope > .bar-l > .tts-chips > *')].filter(c => !c.classList.contains('ig-chips') && !c.classList.contains('tts-chips')));
/* 底栏分左右两块：右边只放生成（和试听），永远在第一行最右边、不会被挤走；左边的模型、选项、AI 优化、高级参数太长时只在左边自己换行，名字完整显示 */
function barSplit(bar, right) {
  if (!bar || bar.querySelector(':scope > .bar-l')) return;
  right = right.filter(Boolean);
  const L = document.createElement('div'), Rt = document.createElement('div'); L.className = 'bar-l'; Rt.className = 'bar-r';
  [...bar.children].forEach(c => { if (c.classList.contains('spacer')) c.remove(); else if (!right.includes(c)) L.append(c); });
  right.forEach(c => Rt.append(c)); bar.append(L, Rt); bar.classList.add('bar-split');
  fitCompact(bar, wrapOf);
}
/* 大图 / 视频下面那一排按钮：挤到信息文字被截断时只留图标 */
const stageTight = bar => { const i = bar.querySelector('.vd-stage-i'); return (i && i.scrollWidth > i.clientWidth + 8) || rowsOf(bar) > 1; };  // 信息被截掉一截就收（按钮只留图标，信息显示全一些）
function igV2(o) {
  const ta = $(o.prompt), f = ta?.closest('.field'), grid = f?.closest('.ig-grid'); if (!grid) return () => { };
  const comp = f.querySelector('.ig-composer'), bar = f.querySelector('.ig-cbar');
  grid.classList.add('ig-v2'); grid.prepend(f); f.classList.add('ig-top-f');
  { const live = grid.querySelector('#ig-live, #vd-live'), card = grid.querySelector('.ig-gal-card'), head = card?.firstElementChild; if (live && head) head.after(live); }
  const chips = document.createElement('div'); chips.className = 'ig-chips'; bar.prepend(chips);
  if (o.model) { o.model.classList.add('ig-chip'); chips.append(o.model); }
  const panels = [], pw = document.createElement('div'); pw.className = 'ig-pw'; f.append(pw, bar); comp.classList.add('ig-comp-top');
  const close = () => { panels.forEach(p => p.hidden = true); $$('.ig-chip.open, .ig-srct.open', f).forEach(c => c.classList.remove('open')); };
  const mk = (btn, nodes) => {
    const p = document.createElement('div'); p.className = 'ig-panel'; p.hidden = true; p.dataset.o = btn === tile ? '1' : String(2 + 2 * o.items.indexOf(o.items.find(it => it.chip === btn))); nodes.forEach(n => n && p.append(n)); pw.append(p); panels.push(p);
    btn.addEventListener('click', e => {
      e.stopPropagation(); const pc = grid.classList.contains('b5-pc') && grid.classList.contains('b5-on'); if (IG_WIDE() && !pc) return; const was = !p.hidden; close(); if (was) return;
      if (btn === tile && o.src.pick && !o.src.thumb()) return o.src.pick();  // 还没放图：直接选图（2026-11-16 用户：手机上要点三次）
      p.hidden = false; btn.classList.add('open');
      // 手机也贴着按钮往上弹一个小面板（11-23 用户：以前从底下升起一整页，不像点了一个选项）；点外面、按 Esc 关（onDoc）
      const br = btn.getBoundingClientRect(), fr = f.getBoundingClientRect();
      if (pc || window.phSheet?.on()) {  // 输入框在底部：贴着按钮往上弹，内容变高时往上长（外面有一层会改变 fixed 的参照位置：放好以后按实际位置再校正一次）
        const L = Math.round(Math.max(8, Math.min(br.left, innerWidth - p.offsetWidth - 8))), D = Math.round(br.top - 8);
        p.style.top = 'auto'; p.style.left = L + 'px'; p.style.bottom = '0px';
        const r2 = p.getBoundingClientRect(); p.style.left = (2 * L - Math.round(r2.left)) + 'px'; p.style.bottom = Math.round(r2.bottom - D) + 'px'; return; }
      p.style.bottom = ''; p.style.left = Math.max(0, Math.min(br.left - fr.left, fr.width - p.offsetWidth)) + 'px'; p.style.top = (br.bottom - fr.top + 8) + 'px';
    });
    p.addEventListener('click', e => { e.stopPropagation(); setTimeout(refresh); });
  };
  let tile = null;
  if (o.src) {  // 参考图：输入框左边的方块，点开选图；选好后显示缩略图
    const row = document.createElement('div'); row.className = 'ig-crow';
    tile = document.createElement('button'); tile.type = 'button'; tile.className = 'ig-srct'; tile.title = typeof o.src.title === 'function' ? '' : o.src.title || '参考图';
    const host = ta.closest('.clr-wrap') || ta; comp.insertBefore(row, host); row.append(tile, host);
    tile.addEventListener('click', e => { if (e.target.closest('.ig-srct-x')) { e.stopPropagation(); e.preventDefault(); o.src.x ? o.src.x() : o.src.node.querySelector('.ig-src-x')?.click(); setTimeout(refresh); } }, true);  // o.src.x：自己指定 × 移除什么（生视频的改视频模式）
    mk(tile, [o.src.node]);
    new MutationObserver(() => setTimeout(refresh)).observe(o.src.node, { childList: true, subtree: true });
  }
  o.items.forEach(it => {
    it.chip = document.createElement('button'); it.chip.type = 'button'; it.chip.className = 'ig-chip';
    it.chip.innerHTML = `${it.icon || ''}<span></span>${IG_CHEV}`; chips.append(it.chip); mk(it.chip, it.nodes);
  });
  barSplit(bar, [bar.querySelector(':scope > .ig-gen')]);
  const refresh = () => {
    if (!f.isConnected) return;
    o.items.forEach(it => { it.chip.querySelector('span').textContent = it.label(); if (it.tip) { it.chip.dataset.tip = it.tip(); it.chip.setAttribute('aria-label', it.chip.dataset.tip); } });
    if (tile) {
      const show = o.src.show ? o.src.show() : true, u = o.src.thumb();
      // o.src.ar()：按画面比例显示（改视频的原视频：竖屏就竖着放全，2026-11-06 用户）；o.src.badge()：底部一行小字（选了哪一段 / 整段）
      const ar = o.src.ar?.() || 0, bd = o.src.badge?.() || '';
      tile.classList.toggle('ar', !!ar); tile.classList.toggle('tall', ar > 0 && ar < .9); tile.classList.toggle('wide', ar >= .9); tile.style.setProperty('--sar', ar || 1);
      tile.hidden = !show; tile.innerHTML = (u ? `<img src="${esc(u)}" alt=""><span class="ig-srct-x" role="button" title="移除" aria-label="移除">${ICON.x}</span>` : (o.src.icon?.() || '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>'))
        + (bd ? `<span class="ig-srct-b">${esc(bd)}</span>` : '');
      if (typeof o.src.title === 'function') { tile.title = o.src.title(); tile.setAttribute('aria-label', tile.title); }  // 标题跟着模式变
    }
  };
  const onDoc = e => { if (!f.isConnected) return document.removeEventListener('click', onDoc); if (!e.target.closest('.pop')) close(); };
  document.addEventListener('click', onDoc);
  // 手指点在不可点的地方（标题、空白）iPhone 不发 click：按下时就关（点的是面板、按钮本身时不管，按钮自己会开 / 关）
  const onDown = e => { if (!f.isConnected) return document.removeEventListener('pointerdown', onDown, true); if (e.pointerType === 'mouse' || e.target.closest('.pop, .ig-panel, .ig-chip, .ig-srct, .dd-menu, .ctx-menu')) return; close(); };
  document.addEventListener('pointerdown', onDown, true);
  addEventListener('keydown', function esc_(e) { if (!f.isConnected) return removeEventListener('keydown', esc_); if (e.key === 'Escape') close(); });
  // 提示词框跟着内容长高：宽窗口时最多长到左栏刚好不超出页面（其余参数、底部按钮都还看得见）；窄窗口最多半屏。内容少时保持最小高度
  const fitTa = () => {
    if (!f.isConnected) return;
    const cs = ta.style;
    if (grid.classList.contains('b5-on')) {
      if (!f.classList.contains('open')) { cs.setProperty('max-height', '24px', 'important'); cs.setProperty('height', '24px', 'important'); return; }
      cs.setProperty('max-height', 'none', 'important'); cs.setProperty('height', 'auto', 'important');
      cs.setProperty('height', Math.round(Math.max(84, Math.min(ta.scrollHeight + 2, innerHeight * .32))) + 'px', 'important'); return;
    }
    cs.setProperty('max-height', 'none', 'important'); cs.setProperty('height', 'auto', 'important');
    // 空框时 Chrome 的 scrollHeight 会算上占位提示：提示长短不同（换人 / 改衣 / 自由修改）框就忽高忽低，下面整栏跟着跳。量的时候先拿掉占位提示
    const ph = !ta.value && ta.placeholder; if (ph) ta.placeholder = '';
    const nat = ta.scrollHeight + 2; let h, avail = Infinity;
    if (ph) ta.placeholder = ph;
    if (IG_WIDE()) {
      const cb = f.querySelector(':scope > .ig-cbar'); cb.style.marginTop = '0';
      const used = cb.getBoundingClientRect().bottom - f.getBoundingClientRect().top + f.scrollTop + parseFloat(getComputedStyle(f).paddingBottom);
      cb.style.marginTop = '';
      avail = Math.floor(f.clientHeight - (used - ta.getBoundingClientRect().height)) - 1;
      h = Math.max(+ta.dataset.minh || 120, Math.min(nat, avail));  // data-minh：改视频时提示词可选，最小高度小一点  // 取整再留 1px：小数高度会让左栏多出 1px，出现一个滚不动的滚动条
    } else if (document.documentElement.classList.contains('ph')) h = Math.max(38, Math.min(nat - 2, 140));  // 手机：底部输入框从一行开始，跟着字长高，最多约 6 行（2026-11-16 手机改版）
    else h = Math.max(92, Math.min(nat, innerHeight * .45));
    if (!ta.value && ta.dataset.minh && !document.documentElement.classList.contains('ph')) h = +ta.dataset.minh;  // 改视频、框是空的：总是最小高度（不跟着下面剩多少空间变，换人 / 改衣 / 自由修改来回切时左栏不跳）
    if (h > avail && avail >= 64) h = avail;  // 宽窗口：剩下的地方不够最小高度时，框变矮（最矮 64；缩到 64 也放不下就不缩），左栏不出现滚动（2026-11-05 用户要求；本次使用换成多行时也一样）
    cs.setProperty('height', h + 'px', 'important');
    if (avail < Infinity) { const ov = f.scrollHeight - f.clientHeight; if (ov > 0 && h - ov >= 64) cs.setProperty('height', (h - ov) + 'px', 'important'); }  // 量完还多出来（框高 auto 时量得不准）：再按多出来的减一次
  };
  let fq = 0; const fitSoon = () => { if (!fq) fq = requestAnimationFrame(() => { fq = 0; fitTa(); }); };
  ta.addEventListener('input', fitTa);
  const ro = new ResizeObserver(() => { if (!f.isConnected) return ro.disconnect(); if (!window.fsHold?.()) fitSoon(); });
  ro.observe(f); panels.forEach(p => ro.observe(p));
  igB5(grid, f, pw, fitSoon);
  refresh(); fitSoon(); return refresh;
}
/* 界面改版（2026-11-07，方案 B5）：宽窗口时 结果在左、选项在右栏（右上角按钮收起，左边缘拖动改宽度，都记住）；
   提示词框在底部、按整个内容区居中：平时一行（右边是生成），点进去变大（最宽 860），点外面收起。
   右栏收起后，选项变成输入框里的“值 ▾”，点了往上弹。设置里可把提示词放回右栏（S.ui.ppos = 'side'：和以前一样，只是在右边） */
// 2026-11-19 用户：两版并存——输入框版（默认，= 以前右栏收起时）和创作栏版（S.ui.ppos = 'side'：选项 + 输入框在左边一整栏，缩略图在视频下面）；右边那张选项卡片去掉。
// 在右下角设置（齿轮）和设置页里换。宽窗口（≥1200）都走新版底部输入框这一套；以前“提示词在右栏”的老排法（b5-side）不再用
const B5_BOTTOM = () => IG_WIDE();
const B5_COL = () => IG_WIDE() && S.ui?.ppos === 'side';
function b5Relayout() {  // 换了版式：当前是生图 / 生视频页就重排一次
  const pg = $('#main')?.dataset.page; if (pg === 'img' || pg === 'video') go(pg, false);
}
function igB5(grid, f, pw, fitSoon) {
  const key = (document.getElementById('main')?.dataset.page || 'x');
  grid.classList.add('b5');
  const opt = document.createElement('aside'); opt.className = 'card b5-opt';
  const sc = document.createElement('div'); sc.className = 'b5-sc'; opt.append(sc);
  const drag = document.createElement('div'); drag.className = 'b5-drag'; drag.setAttribute('aria-hidden', 'true');
  grid.append(opt, drag);
  const chips = f.querySelector('.ig-chips'), mb = chips?.querySelector(':scope > .ig-model-btn'), ta = f.querySelector('textarea');
  // 2026-11-07 用户：框外的按钮头重脚轻、还压在缩略图上 → 都放进框里“生成”左边，只留图标（AI 优化 = 写着 AI 的图标）
  const TOOL_IDS = ['ig-ai', 'ig-enh-q', 'ig-enh-undo', 'vd-ai', 'vd-struct', 'vd-adv-open', 'ig-adv-open'];
  const tools = document.createElement('div'); tools.className = 'b5-tools'; tools.hidden = true; grid.append(tools);  // 框外面：只放“查看完整提示词”（2026-11-07 用户）
  const tin = document.createElement('div'); tin.className = 'b5-tools in'; tin.hidden = true;
  { const br = f.querySelector('.ig-cbar > .bar-r'); br ? br.prepend(tin) : f.append(tin); }
  // 收起（一行）时图标横着排、和输入框上下居中；展开（大框）时竖着贴在框右下角
  const fitTools = fr => { if (tools.hidden || !grid.isConnected) return; const gr = grid.getBoundingClientRect(); fr = fr || f.getBoundingClientRect(); if (!fr.width) return;
    const row = !f.classList.contains('open'); tools.classList.toggle('row', row);
    tools.style.left = Math.round(fr.right - gr.left + 10) + 'px';
    tools.style.bottom = Math.round(gr.bottom - fr.bottom + (row ? Math.max(0, (fr.height - 36) / 2) : 0)) + 'px'; };
  if (window.ResizeObserver) new ResizeObserver(() => { if (f._anim?.playState !== 'running') fitTools(); }).observe(f);
  // 输入框固定在整个窗口的正中间（2026-11-07 用户：开关左边导航、右边选项栏时都不动）；放不下（窗口窄）时才退回到中间那块的正中
  const fitC = () => {
    if (!grid.isConnected || !grid.classList.contains('b5-on')) return;
    const gr = grid.getBoundingClientRect(), op = !pcOn() && !colOn() && opt.offsetParent ? opt.getBoundingClientRect() : null;
    const n = [...tools.children].filter(c => !c.hidden).length, open = f.classList.contains('open'), tw = n ? (open ? 56 : n * 38 + 14) : 0;
    const L = gr.left + 20, R = (op ? op.left : gr.right) - 16 - tw;
    // 中轴：导航栏（按收起时 88px 算）右边到窗口右边这一段的正中（2026-11-07 用户：按整个窗口算的正中看着偏左）；开关导航、右栏都不动
    const rl = document.getElementById('rail'), rr = rl && rl.offsetParent ? 88 : 0, stk = colOn() && grid.querySelector(':scope > .stack')?.getBoundingClientRect(), AX = stk?.width ? (stk.left + stk.right) / 2 : (rr + innerWidth) / 2; grid._ax = AX;  // 创作栏版：中轴 = 右边看成品那一块的正中
    let cx = AX, half = Math.min(cx - L, R - cx);
    if (half < 280) { cx = (L + R) / 2; half = (R - L) / 2; }
    grid.style.setProperty('--b5cx', Math.round(cx - gr.left) + 'px'); grid.style.setProperty('--b5cw', Math.max(260, Math.floor(half * 2)) + 'px');
    if (f._anim?.playState !== 'running') fitTools();  // 输入框换了位置：旁边的图标马上跟上
    // 大画面（视频 + 剪辑控件 / 信息栏）放在“左边缩略图到右边选项栏”这一段的正中：左右两边的空隙一样（2026-11-07 用户：视觉居中、缝隙要对称）
    const sg = grid.querySelector('.ig-gal-card > .vd-stage:not(:empty), .ig-gal-card > .ig-stage:not(:empty)');
    if (sg) { const r = sg.getBoundingClientRect(), cs = getComputedStyle(sg), pl = parseFloat(cs.paddingLeft) || 0, pr = parseFloat(cs.paddingRight) || 0;
      const us = [...sg.querySelectorAll('video, img, canvas, .vseg-side, .vd-stage-bar, .ig-stage-bar, .ab-ctl')].map(e => e.getBoundingClientRect()).filter(q => q.width > 2 && q.height > 2);
      if (us.length && r.width) {
        const msr = [...sg.querySelectorAll('video, img, canvas, .vseg-side')].map(e => e.getBoundingClientRect()).filter(q => q.width > 2 && q.height > 2);
        const uL = Math.min(...us.map(q => q.left)), uR = Math.max(...us.map(q => q.right)), sh0 = (pl - pr) / 2;
        const sideW = sg.classList.contains('side-acts') ? (sg.querySelector(':scope > .vd-stage-bar')?.offsetWidth || 168) + 32 : 0;
        const c0 = (msr.length ? (Math.min(...msr.map(q => q.left)) + Math.max(...msr.map(q => q.right))) / 2 : (uL + uR) / 2) - sh0 + sideW * .3;  // 中心只看画面；按钮放在视频右边时，视频往左让出一点（整组看着居中）
        const gal = sg.nextElementSibling, gr2 = gal?.offsetParent ? gal.getBoundingClientRect() : null, L = gr2 && gr2.right <= r.left + 4 && gr2.width ? gr2.right : r.left;
        const R = !pcOn() && !colOn() && opt.offsetParent ? opt.getBoundingClientRect().left : r.right;
        const ms = [...sg.querySelectorAll('video, img, canvas, .vseg-side')].map(e => e.getBoundingClientRect()).filter(q => q.width > 2 && q.height > 2);  // 判断窄不窄只看画面（下面那行信息、按钮跟着画面居中）
        const mw = ms.length ? Math.max(...ms.map(q => q.right)) - Math.min(...ms.map(q => q.left)) : uR - uL;
        const uw = uR - uL, slack = Math.max(0, (r.width - uw) / 2), sW = (grid._ax || innerWidth / 2) - c0, gl = c0 + sW - mw / 2 - L, gr = R - (c0 + sW + mw / 2);
        const s = Math.max(-slack, Math.min(slack, gl >= 120 && gr >= 120 ? sW : (L + R) / 2 - c0));  // 2026-11-07 用户：竖屏视频要在窗口正中（截图 5），剪辑那样宽的放在中间那段的正中（截图 9）
        grid.style.setProperty('--b5pl', Math.round(s > 0 ? 2 * s : 0) + 'px'); grid.style.setProperty('--b5pr', Math.round(s < 0 ? -2 * s : 0) + 'px'); }
      const v0 = sg.querySelector(':scope > video'); if (v0?.offsetWidth) sg.style.setProperty('--vdw', v0.offsetWidth + 'px');
      { const bar = sg.querySelector(':scope > .vd-stage-bar'), vr = v0?.getBoundingClientRect(), Rr = !pcOn() && !colOn() && opt.offsetParent ? opt.getBoundingClientRect().left : sg.getBoundingClientRect().right;
        const was = sg.classList.contains('side-acts'), on = !!(bar && vr?.width && (pcOn() || colOn()) && Rr - vr.right >= 200 + (was ? 0 : 0));
        sg.classList.toggle('side-acts', on);
        if (on) { const v2 = v0.getBoundingClientRect(), s2 = sg.getBoundingClientRect(); bar.style.left = Math.round(v2.right - s2.left + 32) + 'px'; } else if (bar) bar.style.left = '';
        if (on !== was) requestAnimationFrame(fitC);  // 换了排法：再按新的样子居中一次
        if (v0 && window.ResizeObserver && v0 !== fitC.v0) { fitC.vro?.disconnect(); fitC.v0 = v0; (fitC.vro = new ResizeObserver(() => fitC())).observe(v0); } } }  // 视频读到尺寸 / 换了一段：按钮跟着它  // 右栏收起、视频右边空得多：按钮带名字竖着放到视频右边
    stackFit(sg && sg.nextElementSibling?.matches('.vd-gal, .ig-gal') ? sg.nextElementSibling : grid.querySelector('.vd-gal.stk, .ig-gal.stk'));
    if (sg && window.ResizeObserver && sg !== fitC.sg) { fitC.ro?.disconnect(); fitC.sg = sg; (fitC.ro = new ResizeObserver(() => fitC())).observe(sg, { box: 'border-box' }); }  // 大画面那一块出现 / 换了大小（缩略图挪到左边时）：重新算
  };
  /* 左边缩略图放不下时：像一叠文件，每张只露出上面一截（最少 64px），鼠标停在哪张就抽出哪张（2026-11-07 用户）；放得下就正常排 */
  function stackFit(gal) {
    if (!gal) return;
    const off = () => { if (gal.classList.contains('stk')) { gal.classList.remove('stk'); gal.style.removeProperty('--stk'); gal.style.removeProperty('--stkH'); } };
    const card = gal.closest('.ig-gal-card'), cs = getComputedStyle(gal);
    if (!S.ui?.galStack || !card?.classList.contains('port') || cs.display !== 'grid' || !matchMedia('(min-width: 1200px)').matches || !gal.previousElementSibling?.firstElementChild) return off();  // 设置里的“缩略图叠放”（默认关：平铺）
    const tiles = [...gal.querySelectorAll('.vd-tile, .ig-ju')].filter(t => t.offsetParent), cols = cs.gridTemplateColumns.split(' ').filter(Boolean).length || 1;
    if (tiles.length <= cols) return off();
    const tH = Math.max(...tiles.map(t => t.offsetHeight)), rows = Math.ceil(tiles.length / cols), gap = parseFloat(cs.rowGap) || 12;
    const avail = gal.clientHeight - 14;
    if (!tH || avail <= 0 || rows * tH + (rows - 1) * gap <= avail) return off();
    const step = Math.max(96, Math.floor((avail - tH) / (rows - 1)));
    if (step >= tH + gap) return off();
    gal.classList.add('stk'); gal.style.setProperty('--stk', step + 'px'); gal.style.setProperty('--stkH', tH + 'px');
    tiles.forEach((t, i) => { if (!t.querySelector(':scope > .stk-hit')) t.insertAdjacentHTML('beforeend', '<i class="stk-hit" aria-hidden="true"></i>'); t.classList.toggle('stk-last', i >= (rows - 1) * cols); t.classList.toggle('stk-first', i < cols); });
  }
  if (window.ResizeObserver) new ResizeObserver(() => { fitC(); if (f._anim?.playState !== 'running') requestAnimationFrame(() => fitTools()); }).observe(grid);
  f.addEventListener('transitionend', e => { if (e.target === f && f._anim?.playState !== 'running') fitTools(); });
  { let q = 0; new MutationObserver(ms => { if (!grid.isConnected || !ms.some(m => m.target.matches?.('.ig-gal-card, .vd-stage, .ig-stage, .vd-gal, .ig-gal'))) return; cancelAnimationFrame(q); q = requestAnimationFrame(fitC); }).observe(grid, { childList: true, subtree: true }); }  // 换了正在播放的那段：大画面重新居中  // 输入框挪位置（有过渡动画）停下后，旁边的图标跟上
  /* 选项栏收起时：输入框左上角放这次用的素材（参考 Kling，2026-11-07 用户）——平时叠成一小摞（最上面是视频），鼠标移上去展开成一排；
     点视频那一格：在上面展开播放（不带进度条，循环）；鼠标拿开就停，再移上来从头放。必须有视频而还没放时，第一格是虚线框。
     素材本身还是右栏那几格（原图 / 参考图 / 原视频 / 人物图……）：这里只是照着它们画，点“＋”或虚线框就是点那一格 */
  const refs = document.createElement('div'); refs.className = 'b5-refs'; refs.hidden = true; f.append(refs);
  let rItems = [], rPin = false;
  const slotLab = s => s.dataset.b5n || s.querySelector('.ig-ref-n')?.textContent.trim() || (s.id === 'ig-src' ? ((s.closest('#ig-src-f') || document.querySelector('#ig-src-f'))?.querySelector('.ig-refs') ? '图 1' : '原图') : s.classList.contains('ve-vid') ? '原视频' : '')
    || [...s.querySelectorAll(':scope > div, :scope > span:not(.tiny)')].map(e => e.textContent.trim()).find(Boolean) || (s.getAttribute('aria-label') || s.title || '').replace(/[（(：:].*$/, '');  // 放了图的格子只有悬停说明（“衣服图（可选）：换成这身衣服”）：只取名字
  const scan = () => [...(pw.contains($('#ig-stage #ig-src')) ? [] : [$('#ig-stage #ig-src')].filter(Boolean)), ...pw.querySelectorAll('.ig-src, .vd-f2, .ig-ref, .vx-it, .b5-add')].filter(  // 局部重画时原图格搬到了大画面上：左上角照样显示它（2026-11-11）
    s => !s.hidden && !s.closest('.b5-refs') && !s.parentElement?.closest('[hidden]:not(.ig-panel)')).map(s => {
    // .b5-add：只是“添加 XX”的按钮（生视频的参考图 / 参考视频 / 更多素材）；.b5-aud：放好的声音（没有画面，显示成图标）
    const m = s.querySelector('video, img'), aud = s.classList.contains('b5-aud'), empty = s.classList.contains('b5-add') || s.classList.contains('empty') || (!m && !aud);
    return { s, empty, aud, vid: m ? m.tagName === 'VIDEO' : /视频/.test(slotLab(s)), url: m ? (m.currentSrc || m.getAttribute('src') || '') : '', lab: slotLab(s), req: /必填/.test(s.textContent), x: s.querySelector('.ig-src-x, [data-rx]') }; });
  const RF_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';
  const RF_FILM = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4-2.5z"/></svg>';
  const RF_AUD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/></svg>';
  const rfTile = (it, i, cls) => it.empty
    ? `<button type="button" class="b5-rf-t e0${cls}" data-i="${i}" title="添加${esc(it.lab)}">${it.vid ? RF_FILM : RF_PLUS}<span class="b5-rf-l">${esc(it.lab)}</span></button>`
    : `<div class="b5-rf-t${it.vid ? ' vid' : ''}${it.aud ? ' aud' : ''}${cls}" data-i="${i}" role="button" tabindex="-1" aria-label="${esc(it.lab)}">${it.aud ? `<i class="b5-rf-ai">${RF_AUD}</i>` : it.vid ? `<video src="${esc(it.url)}" muted playsinline preload="metadata"></video><i class="b5-rf-play">${typeof VID_IC !== 'undefined' ? VID_IC.play : ''}</i>` : `<img src="${esc(it.url)}" alt="" draggable="false">`}<span class="b5-rf-l">${esc(it.lab)}</span>${it.x ? `<span class="b5-rf-x" data-x="${i}" role="button" aria-label="移除">${ICON.x}</span>` : ''}</div>`;
  function paintRefs() {
    const show = grid.classList.contains('b5-on') && grid.classList.contains('b5-pc'), all = show ? scan() : [];
    const vids = all.filter(it => it.vid && (!it.empty || it.req) && !it.s.matches('.b5-add, [data-b5l]')), imgs = all.filter(it => !it.vid && !it.empty), req = all.filter(it => !it.vid && it.empty && it.req), pz = all.find(it => it.empty && it.s.classList.contains('ig-pose-t')) || null,
      // 带名字的“添加”格（2026-11-11 用户：生视频要能从这里加首帧、尾帧、参考图、参考视频、更多素材）：每个单独一格、写着名字；其余空格照旧只并成一个“＋”
      adds = all.filter(it => it.empty && !it.req && it !== pz && it.s.matches('.b5-add, [data-b5l]')),
      plus = all.find(it => it.empty && !it.req && it !== pz && !adds.includes(it)) || null;  // 摆姿势（3D 人偶）不是“再放一张图”：单独一格，不并进“＋”（2026-11-11 用户：找不到摆姿势）
    rItems = [...vids, ...imgs, ...req]; rItems.plus = plus; rItems.pz = pz; rItems.adds = adds;
    refs.hidden = !show || (!rItems.length && !plus && !pz && !adds.length); f.classList.toggle('b5-hasrefs', !refs.hidden);
    if (refs.hidden) { refs.dataset.sig = ''; return; }
    const sig = JSON.stringify(rItems.map(it => [it.url, it.lab, it.empty])) + (plus ? '+' + plus.lab : '') + (pz ? '|pz' : '') + '|' + adds.map(it => it.lab).join(',');
    if (sig === refs.dataset.sig) return; refs.dataset.sig = sig; rPin = false;
    const filled = rItems.filter(it => !it.empty), top = (filled.length ? filled.slice(0, 3) : rItems.slice(0, 1)).reverse();  // 叠起来时：最上面是第一个（视频）
    refs.classList.toggle('none', !filled.length && !adds.length);  // 2026-11-10 用户：一个素材都没放时鼠标移上去不展开，点一下直接选（第一格）；有几种可加的（生视频）时照样展开，让人挑
    refs.innerHTML = `<div class="b5-rf-stack">${top.length ? top.map((it, k) => rfTile(it, rItems.indexOf(it), ' r' + (top.length - 1 - k))).join('') : `<span class="b5-rf-t e0 r0">${RF_PLUS}</span>`}</div>`
      + `<div class="b5-rf-pop">${rItems.map((it, i) => rfTile(it, i, '')).join('')}${plus ? `<button type="button" class="b5-rf-t e0 plus" data-p="1" title="添加${esc(plus.lab)}">${RF_PLUS}</button>` : ''}${adds.map((it, k) => `<button type="button" class="b5-rf-t e0 add" data-a="${k}" title="添加${esc(it.lab)}">${/视频/.test(it.lab) ? RF_FILM : RF_PLUS}<span class="b5-rf-l">${esc(it.lab)}</span></button>`).join('')}${pz ? `<button type="button" class="b5-rf-t e0 pose" data-pz="1" title="3D 摆姿势：用真人人偶摆一个姿势，图 1 的人照这个姿势重画">${pz.s.querySelector('svg')?.outerHTML || RF_PLUS}<span class="b5-rf-l">摆姿势</span></button>` : ''}<div class="b5-rf-pv" hidden><video muted loop playsinline></video><img alt="" draggable="false" hidden></div></div>`;
  }
  // 2026-11-10 用户：点图片（参考图 / 衣服图 / 原图…）也在上方弹出放大看，和点视频一样（再点一下 / 鼠标拿开就收起）
  const rfPv = it => { const pv = refs.querySelector('.b5-rf-pv'), v = pv?.querySelector('video'), im = pv?.querySelector('img'); if (!v || !im || !it) return;
    pv.classList.toggle('img', !it.vid); v.hidden = !it.vid; im.hidden = !!it.vid; pv.hidden = false;
    if (it.vid) { if (v.getAttribute('src') !== it.url) v.src = it.url; try { v.currentTime = 0; } catch { } v.play().catch(() => { }); }
    else { v.pause(); if (im.getAttribute('src') !== it.url) im.src = it.url; } };
  const rfPvOff = () => { const pv = refs.querySelector('.b5-rf-pv'); if (!pv) return; pv.hidden = true; pv.querySelector('video')?.pause(); };
  const rfClick = (s, at) => { window.ctxAnchorFor = at; try { s.click(); } finally { setTimeout(() => { window.ctxAnchorFor = null; }, 0); } setTimeout(paintRefs, 300);  // 右栏收起时那一格看不见：菜单贴着这里弹
    // 2026-11-10 用户：展开后点了一格、鼠标往上移到弹出的菜单上时，展开的这一排不要收起——菜单 / 选素材的窗口还开着就一直展开
    refs.classList.add('keep'); clearInterval(rfClick.t);
    rfClick.t = setInterval(() => { if (!document.querySelector('.ctx-menu, .modal-bg')) { refs.classList.remove('keep'); clearInterval(rfClick.t); if (refs.contains(document.activeElement)) document.activeElement.blur(); } }, 200); };  // 关窗口时焦点回到这一格（:focus-visible 会让它一直展开）：拿掉
  refs.addEventListener('pointerdown', e => e.stopPropagation()); refs.addEventListener('focusin', e => e.stopPropagation());  // 点素材不把输入框撑开
  refs.addEventListener('click', e => {
    e.stopPropagation(); e.preventDefault();
    const x = e.target.closest('[data-x]'); if (x) { rItems[+x.dataset.x]?.x?.click(); setTimeout(paintRefs, 300); return; }
    const p = e.target.closest('[data-p]'); if (p) return rItems.plus && rfClick(rItems.plus.s, p);
    const ad = e.target.closest('[data-a]'); if (ad) { rfPvOff(); return rItems.adds?.[+ad.dataset.a] && rfClick(rItems.adds[+ad.dataset.a].s, ad); }
    if (e.target.closest('.b5-rf-stack') && rItems.adds?.length) {  // 点那一摞（没用鼠标停留）：展开，点外面收起
      refs.classList.add('keep'); const off = ev => { if (refs.contains(ev.target)) return; refs.classList.remove('keep'); document.removeEventListener('pointerdown', off, true); };
      document.addEventListener('pointerdown', off, true); return; }
    const pzb = e.target.closest('[data-pz]'); if (pzb) { rfPvOff(); return rItems.pz && rfClick(rItems.pz.s, pzb); }
    const sk = e.target.closest('.b5-rf-stack'); if (sk && refs.classList.contains('none')) { const it0 = rItems[0] || rItems.plus; return it0 && rfClick(it0.s, sk); }  // 什么都没放：点这一格直接选
    const t = e.target.closest('.b5-rf-pop [data-i]'), it = t && rItems[+t.dataset.i]; if (!it) return;
    if (it.empty || it.s.id === 'ig-pose-t') { rfPvOff(); return rfClick(it.s, t); }  // 放了人偶：点它再改姿势（和右栏那一格一样）
    if (it.s?.id === 'ig-src' && IG_WIDE() && typeof imgSrcToStage === 'function') { rfPvOff(); refs.classList.remove('keep'); return imgSrcToStage(); }  // 生图页的原图：放回大画面（关掉以后点这里能再打开，2026-11-10）
    if (rPin === it.url) { rPin = false; rfPvOff(); } else { rPin = it.url; rfPv(it); }  // 视频、图片都一样：点一下在上方放大，再点收起
  });
  refs.addEventListener('mouseleave', () => { rPin = false; rfPvOff(); });  // 鼠标拿开就停；再移上来要再点一次才放
  { let q = 0; new MutationObserver(() => { cancelAnimationFrame(q); q = requestAnimationFrame(paintRefs); }).observe(pw, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'class', 'hidden'] }); }
  // @ 引用（参考 Kling）：在提示词里打 @，弹出一个小框选图片，选了就写成“图 N”（和右栏、上面那一排的编号一样）
  if (ta) {
    let am = null, ai = 0, aList = [];
    const aClose = () => { am?.remove(); am = null; };
    const aPick = it => { const p = ta.selectionStart, v = ta.value, k = v.lastIndexOf('@', p - 1), w = it.lab.replace(/\s+/g, '');
      if (k >= 0) { ta.value = v.slice(0, k) + w + v.slice(p); ta.selectionStart = ta.selectionEnd = k + w.length; ta.dispatchEvent(new Event('input', { bubbles: true })); } aClose(); ta.focus(); };
    const aPaint = () => { $$('button', am).forEach((b, i) => b.classList.toggle('on', i === ai)); };
    ta.addEventListener('input', e => {
      if (e.data !== '@') { if (am && !/@[^\s@]*$/.test(ta.value.slice(0, ta.selectionStart))) aClose(); return; }
      aList = scan().filter(it => !it.empty && !it.vid && /^图\s*\d+$/.test(it.lab)); if (!aList.length) return;
      aClose(); am = document.createElement('div'); am.className = 'b5-at'; am.setAttribute('role', 'listbox'); ai = 0;
      am.innerHTML = aList.map((it, i) => `<button type="button" role="option" data-a="${i}"><img src="${esc(it.url)}" alt=""><span>${esc(it.lab)}</span></button>`).join('');
      f.append(am); aPaint();
      am.addEventListener('pointerdown', ev => ev.preventDefault());
      am.addEventListener('click', ev => { const b = ev.target.closest('[data-a]'); if (b) aPick(aList[+b.dataset.a]); });
    });
    ta.addEventListener('keydown', e => { if (!am) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); ai = (ai + (e.key === 'ArrowDown' ? 1 : aList.length - 1)) % aList.length; aPaint(); }
      else if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); e.stopPropagation(); aPick(aList[ai]); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); aClose(); } }, true);
    ta.addEventListener('blur', () => setTimeout(aClose, 120));
  }
  // 底栏左边的选项按钮放不下：带图标的只留图标（2026-11-07 用户：不够的时候就只放图标，别截掉一半）
  { const bl = f.querySelector('.ig-cbar > .bar-l');
    // 2026-11-08：先收起“AI 优化 / 秋叶写法 / 高级参数”这类按钮的字（图标认得出），还放不下再收起带数值的选项（分辨率、时长这些更要紧），最后才折行
    const fitBl = () => { if (!bl || !bl.offsetParent) return; bl.classList.remove('ic', 'ic1', 'wr');
      if (document.documentElement.classList.contains('ph')) return;  // 手机：这一排能左右滑，不收成图标、不截短模型名（2026-11-16 手机改版） bl.querySelectorAll('.ig-chip, .ig-cb').forEach(c => { const t = c.querySelector(':scope > span')?.textContent.trim(); if (t && !c.title) c.title = t; });
      // 2026-11-10 用户：改视频的“本次使用”那行（vd-sum）和选项按钮在同一排、放不下时，先把这行藏起来（它会回到输入框左边显示，见 vdDockFit），
      // 不要为了它把参数按钮收成只剩图标（按钮上的“跟随 / 加速”这些就看不到了）
      const bar = bl.parentElement, sm = bar?.querySelector(':scope > .vd-sum'), had = bar?.classList.contains('nosum');
      if (sm) { bar.classList.remove('nosum');
        if (bl.scrollWidth > bl.clientWidth && sm.offsetParent) { const a = sm.getBoundingClientRect(), b = bl.getBoundingClientRect(); if (a.top < b.bottom && a.bottom > b.top) bar.classList.add('nosum'); }
        if (had !== bar.classList.contains('nosum') && typeof vdDockFit === 'function') requestAnimationFrame(vdDockFit); }
      if (bl.scrollWidth > bl.clientWidth) bl.classList.add('ic1');  // 多出 1px 也算放不下（iPad 上 1px 也能横着晃）
      if (bl.scrollWidth > bl.clientWidth) bl.classList.add('ic');
      { const m = bl.querySelector('.ig-model-btn'); if (m) m.style.maxWidth = '';  // 2026-11-16 用户（手机）：还放不下时先把模型名截短（…），不折成两行
        if (m && bl.scrollWidth > bl.clientWidth) { const room = m.offsetWidth - (bl.scrollWidth - bl.clientWidth) - 1; if (room >= 96) m.style.maxWidth = room + 'px'; } }
      if (bl.scrollWidth > bl.clientWidth) bl.classList.add('wr'); };  // 2026-11-08：只留图标还放不下 → 折行（不再左右滑、不截半个）
    // 2026-11-10 用户：按钮被收成只剩图标后一直不恢复——这一排的宽度跟着内容走，收成图标后它自己的大小不再变，旁边空出来了也不会重量。
    // 所以整条底栏（输入框变宽）和同一栏里的其它东西（“本次使用”那行变短）变了大小也重新量一次
    if (bl && window.ResizeObserver) { const ro = new ResizeObserver(() => requestAnimationFrame(fitBl)); ro.observe(bl);
      const bar = bl.parentElement; if (bar) { ro.observe(bar); const obs = () => [...bar.children].forEach(c => c !== bl && ro.observe(c)); obs(); new MutationObserver(obs).observe(bar, { childList: true }); }
      new MutationObserver(() => requestAnimationFrame(fitBl)).observe(bar || bl, { childList: true, subtree: true, characterData: true }); } }  // 整栏的文字：藏起来的“本次使用”变短了也要重量（藏着时它没有大小变化）
  // 右上角：收起 / 展开选项栏
  const head = $('#main > .page-head');
  const tog = document.createElement('button'); tog.type = 'button'; tog.className = 'b5-ib b5-ptog';
  tog.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/></svg>';
  if (head) { let acts = head.querySelector(':scope > .b5-acts'); if (!acts) { acts = document.createElement('div'); acts.className = 'b5-acts'; head.append(acts); } acts.append(tog);
    const all = key === 'img' && $('#ig-all'); if (all && typeof B5_IC !== 'undefined') { all.className = 'b5-ib vd-allb'; all.innerHTML = B5_IC.grid; all.setAttribute('aria-label', '全部图片'); all.dataset.tip = '全部图片'; tog.before(all); } }
  const pcOn = () => !B5_COL();  // 2026-11-19：没有右栏了——输入框版 = 一直“收起”；创作栏版 = 选项一直摊开（在左栏）
  const colOn = () => grid.classList.contains('b5-col');
  const paintTog = () => { const c = pcOn(), t = c ? '展开选项栏' : '收起选项栏'; tog.setAttribute('aria-label', t); tog.dataset.tip = t; tog.setAttribute('aria-pressed', String(!c)); tog.classList.toggle('on', !c); };
  // 开 / 关右边选项栏：从右边滑进来 / 滑出去（关的时候先滑走再改版面）
  const SLIDE = [{ transform: 'translateX(calc(100% + 32px))', opacity: .4 }, { transform: 'none', opacity: 1 }], EZ = 'cubic-bezier(.32, .72, 0, 1)';
  tog.onclick = () => {
    const closing = !pcOn();
    const run = () => { S.ui = { ...(S.ui || {}), pc: { ...(S.ui?.pc || {}), [key]: closing } }; persist(); (grid.b5place || place)();
      if (!closing && !reduceMotion) opt.animate(SLIDE, { duration: 320, easing: EZ }); };
    if (closing && !reduceMotion && opt.offsetParent) { const a = opt.animate([...SLIDE].reverse(), { duration: 220, easing: 'cubic-bezier(.4, 0, 1, 1)', fill: 'forwards' }); a.onfinish = () => { run(); a.cancel(); }; }
    else run();
  };
  // 创作栏版：左栏离导航栏 20px（和右边一样），栏的底色从导航栏右边一直铺到栏右边 20px；标题栏左半边跟着左移，返回、“改视频 ▾”落在栏里
  const b5ColFit = col => { const m = $('#main'), hd = $('#main > .page-head'); if (!m) return;
    for (const e of [grid, hd]) { e?.style.removeProperty('margin-left'); e?.style.removeProperty('width'); e?.style.removeProperty('max-width'); }
    if (!col) { m.style.removeProperty('--b5sw'); document.documentElement.style.removeProperty('--b5edge'); return; }
    const ml = m.getBoundingClientRect().left, d = Math.round(grid.getBoundingClientRect().left - ml - 20);
    // 大屏时网格本来居中（外边距 auto）：在原来的外边距上再往左挪；宽度加上挪的这段，右边不动
    for (const e of [grid, hd]) if (e) { const w = e.getBoundingClientRect().width, m0 = parseFloat(getComputedStyle(e).marginLeft) || 0; e.style.setProperty('margin-left', (m0 - d) + 'px', 'important'); e.style.setProperty('max-width', 'none', 'important'); e.style.setProperty('width', (w + d) + 'px', 'important'); }  // b5.css 给 #main 的子元素加了 !important 的外边距
    const cw = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--b5col')) || 372;
    const tf = getComputedStyle(m).transform !== 'none';  // #main 有 transform 时 fixed 相对它（左边 = 导航栏右边），没有时相对窗口（连导航栏一起铺，同一个颜色）
    m.style.setProperty('--b5sw', Math.round((tf ? 0 : ml) + 20 + cw + 20) + 'px');
    document.documentElement.style.setProperty('--b5edge', Math.round(ml + 20 + cw + 20) + 'px'); };  // 窗口坐标：应用顶上拖动条（.tb-strip）左边这段也涂成栏的颜色
  const iw = () => (S.ui?.iw || {})[key] || (key === 'video' ? 340 : 320);
  const place = () => {
    if (!grid.isConnected) return off();
    const on = B5_BOTTOM();
    grid.classList.toggle('b5-on', on); grid.classList.toggle('b5-side', IG_WIDE() && !on); grid.classList.toggle('b5-pc', on && pcOn());
    const col = on && B5_COL(), wasCol = grid.classList.contains('b5-col');
    grid.classList.toggle('b5-col', col);
    b5ColFit(col);
    tog.hidden = true; paintTog();  // 右上角的收起 / 展开选项栏不要了（换版式在设置里）
    grid.style.setProperty('--iw', iw() + 'px');
    if (on && pw.parentElement !== sc) sc.append(pw);
    // 模型按钮（生图）：右栏开着时放在右栏最上面（一直看得见）；收起时回到输入框里
    if (mb) { const want = on && !pcOn() ? sc : chips; if (mb.parentElement !== want) want.prepend(mb); }
    if (!on && pw.parentElement !== f) f.insertBefore(pw, f.querySelector(':scope > .ig-cbar'));
    if (!on) f.classList.remove('open');
    // 输入框右边外面竖着一列小图标（参考可灵的 Tools）：高级参数、查看完整提示词。框里只留一行
    const pk = ta?._promptPeek;
    const items = [...TOOL_IDS.map(id => document.getElementById(id)), pk].filter(Boolean);
    items.forEach(el => {
      const ai = el.id === 'ig-ai' || el.id === 'vd-ai';
      const box = el === pk && !col ? tools : tin;  // 创作栏版：“查看完整提示词”也放进框里（框外面就是看成品的地方了）
      if (on) { if (el.parentElement !== box) { if (!el._home) el._home = { p: el.parentElement, n: el.nextSibling }; if (el === pk) el.classList.add('ig-cb', 'b5-peek'); box.append(el); }
        if (ai && el._b5h === undefined) { el._b5h = el.innerHTML; el.innerHTML = '<span class="b5-aig" aria-hidden="true">AI</span>'; el.setAttribute('aria-label', 'AI 优化'); } }
      else if ((el.parentElement === tools || el.parentElement === tin) && el._home) { const h = el._home; if (el === pk) el.classList.remove('ig-cb', 'b5-peek'); h.n && h.n.parentNode === h.p ? h.p.insertBefore(el, h.n) : h.p.append(el); el._home = null;
        if (ai && el._b5h !== undefined) { el.innerHTML = el._b5h; el._b5h = undefined; } }
    });
    tools.hidden = !on || col; tin.hidden = !on; fitC(); requestAnimationFrame(fitTools); paintRefs();
    if (col) setOpen(true, true); else if (wasCol) setOpen(false, true);  // 创作栏版：提示词框一直是展开的样子
    grid.style.setProperty('--b5top', Math.round(grid.getBoundingClientRect().top + scrollY) + 'px');
    $$('.ig-panel', grid).forEach(p => { if (on && !pcOn()) { p.style.left = ''; p.style.top = ''; p.style.bottom = ''; } });
    fitSoon();
  };
  // 点进输入框：展开；点外面（不是选项、菜单、弹窗）：收起
  const isOut = t => !t.closest || !(t.closest('.ig-top-f') || t.closest('.ig-panel') || t.closest('.pop, .modal, .modal-bg, .dd-menu, .tip-float, .vft-pop, .menu'));
  // 展开 / 收起：先量好前后的大小，再用动画从旧的大小过渡到新的（以前是一下子跳过去，看着闪一下）
  const taH = on => { if (!ta) return; const cs = ta.style;
    if (!on) { cs.setProperty('max-height', '24px', 'important'); cs.setProperty('height', '24px', 'important'); return; }
    cs.setProperty('max-height', 'none', 'important'); cs.setProperty('height', 'auto', 'important');
    cs.setProperty('height', Math.round(Math.max(84, Math.min(ta.scrollHeight + 2, innerHeight * .32))) + 'px', 'important'); };
  const setOpen = (on, inst) => {
    if (f.classList.contains('open') === on) return;
    const r0 = f.getBoundingClientRect();
    const tb = [...tools.children].filter(c => !c.hidden).map(c => [c, c.getBoundingClientRect()]);
    f._anim?.cancel(); f.classList.toggle('open', on); fitC(); taH(on);
    document.body.classList.add('tip-hold');  // 框变大后按钮移到鼠标下面：鼠标真的动了才弹说明
    { let x0 = null, y0 = null; const mv = e => { if (x0 === null) { x0 = e.clientX; y0 = e.clientY; return; } if (Math.hypot(e.clientX - x0, e.clientY - y0) > 6) { document.body.classList.remove('tip-hold'); removeEventListener('mousemove', mv); } }; addEventListener('mousemove', mv); }
    const r1 = f.getBoundingClientRect(); fitTools(r1);
    if (reduceMotion || !r0.height || inst) { document.body.classList.remove('tip-hold'); return; }
    const ease = 'cubic-bezier(.2, .8, .2, 1)';
    f._anim = f.animate([{ width: r0.width + 'px', height: r0.height + 'px' }, { width: r1.width + 'px', height: r1.height + 'px' }], { duration: 260, easing: ease });
    f._anim.onfinish = () => fitTools();
    // 图标从横排滑到竖排（或反过来）：每个按钮从原来的位置平移到新位置，和输入框一起动，后面的稍晚一点
    tb.forEach(([c, a], i) => { if (!a.width) return; const b = c.getBoundingClientRect(); const dx = a.left - b.left, dy = a.top - b.top; if (!dx && !dy) return;
      c.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 300, delay: i * 18, easing: ease, fill: 'backwards' }); });
    [...f.children].forEach(c => c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, delay: on ? 60 : 0, easing: 'ease-out', fill: 'backwards' }));
  };
  const onIn = e => { if (e.target.closest?.('.ig-gen, .b5-tools, .b5-refs, .b5-at')) return; if (grid.classList.contains('b5-on') && !f.classList.contains('open')) setOpen(true); };
  const onDown = e => { if (!grid.isConnected) return off(); if (colOn()) return; if (f.classList.contains('open') && isOut(e.target)) setOpen(false); };  // 创作栏版：不收起
  f.addEventListener('focusin', onIn); f.addEventListener('pointerdown', onIn);
  document.addEventListener('pointerdown', onDown, true);
  addEventListener('resize', place);
  function off() { document.removeEventListener('pointerdown', onDown, true); removeEventListener('resize', place); }
  // 拖右栏左边缘改宽度（240～480，记住）
  drag.addEventListener('pointerdown', e => {
    e.preventDefault(); drag.classList.add('on'); const right = grid.getBoundingClientRect().right;
    const mv = ev => { const w = Math.round(Math.max(240, Math.min(480, right - ev.clientX))); grid.style.setProperty('--iw', w + 'px'); S.ui = { ...(S.ui || {}), iw: { ...(S.ui?.iw || {}), [key]: w } }; };
    const up = () => { drag.classList.remove('on'); persist(); removeEventListener('pointermove', mv); removeEventListener('pointerup', up); fitSoon(); };
    addEventListener('pointermove', mv); addEventListener('pointerup', up);
  });
  place(); requestAnimationFrame(place);
  grid.b5place = place;
}
/* 生图 / 生视频：参考 Krea、即梦——结果占满右边，提示词输入框停靠在右栏最底下，“生成”在输入框右下角；
   左栏只放参数。整页正好一屏高，什么都不悬浮、不遮挡（手机上还是从上到下排） */
function igDock(sel) {
  const f = $(sel)?.closest('.field'), grid = f?.closest('.ig-grid'), right = grid && grid.querySelector(':scope > .stack'); if (!right) return;
  f.classList.add('ig-dock-f'); right.append(f); grid.classList.add('ig-dock'); igDockFit();
}
/* 让一块区域正好铺到窗口底部（留出播放条），整页不多滚：AI 助手的三栏、换声的产出区 */
/* 播放条在 el 正下方时它的顶边（要让开）；不在下面时（别的页面上播放条缩成左栏里的小卡片、收起、隐藏）= 窗口底边。
   2026-11-11 用户：AI 助手整页（连左边历史）被定成一个矮的高度、下面空一大块——以前不管播放条在哪都按它的顶边让 */
function pbTopUnder(el) {
  const pb = $('.pbar'); if (!pb || !el) return innerHeight; const cs = getComputedStyle(pb); if (cs.display === 'none' || cs.visibility === 'hidden') return innerHeight;
  const pr = pb.getBoundingClientRect(), er = el.getBoundingClientRect();
  // 贴在左边导航栏上的播放器（导航里竖着一块 / 窗口矮时圆钮旁边横着的小胶囊）不是压在页面底下的播放条：不用给它让位
  // （2026-11-18 用户：小窗口 AI 助手输入框下面空一截）
  const rail = $('.rail'); if (rail && getComputedStyle(rail).display !== 'none' && pr.left < rail.getBoundingClientRect().right - 1) return innerHeight;
  return pr.width && pr.height && pr.top < innerHeight && pr.right > er.left + 1 && pr.left < er.right - 1 ? pr.top : innerHeight;
}
/* 高级参数里改过的项（和默认不一样）：标签前一个小蓝点；收起的“更多参数”里有改过的，标题旁也有点（2026-11-11 用户：按钮上只有数字，进去找不到改了哪里） */
function advMark(root, ids) {
  if (!root) return;
  root.querySelectorAll('.adv-chg').forEach(e => { e.classList.remove('adv-chg'); if (e.dataset.chgT) { e.removeAttribute('title'); delete e.dataset.chgT; } });
  root.querySelectorAll('.adv-chg-in').forEach(e => e.classList.remove('adv-chg-in'));
  for (const id of ids) {
    const el = root.querySelector('#' + id); if (!el) continue;
    let f = el.closest('.field') || el.closest('.ig-sec, label');  // 有字段标题的标在标题前
    if (!f || !root.contains(f)) { const p = el.previousElementSibling; f = p && p.matches('.ig-sec, .label') ? p : el; }  // LoRA 列表这类容器：标在它上面的小标题
    f.classList.add('adv-chg'); if (!f.title) { f.title = '已修改（和默认不同）'; f.dataset.chgT = '1'; }
    const d = f.closest('details'); if (d) d.classList.add('adv-chg-in');
  }
}
function fitBottom(el, prop = 'height', min = 300) {
  if (!el || !el.isConnected) return;
  if (MOB()) { el.style[prop] = ''; return; }
  // 只量“上面占了多少、底下要让多少”（和窗口高度无关），高度交给 100vh 自己跟着窗口变：
  // 以前直接写死像素，退出迷你播放器 / 最大化时窗口会先经过一个小尺寸，赶上那一下底下就空一截（2026-11-18 用户：AI 助手输入框不在最下面）
  const top = el.getBoundingClientRect().top + scrollY, pt = pbTopUnder(el);
  const gap = pt < innerHeight ? innerHeight - pt + 14 : 24;
  let cut = Math.round(top + gap);
  const set = () => { el.style[prop] = `max(${min}px, calc(100vh - ${cut}px))`; };
  set();
  // 它下面还有东西（页面内边距等）、整页多出一截能滚：把多出来的收回来。量的是“它下面有多高”，同样和窗口高度无关
  const de = document.documentElement;
  if (de.scrollHeight > innerHeight) { const add = de.scrollHeight - Math.round(el.getBoundingClientRect().bottom + scrollY) - gap; if (add > 0 && add < 120) { cut += add; set(); } }
}
function fitPages() { fitBottom($('.pg-grid'), 'height', 460); fitBottom($('.vc-out'), 'height', 120); }
{ let t = 0; addEventListener('resize', () => { fitPages(); clearTimeout(t); t = setTimeout(fitPages, 160); }); }  // 窗口一变先算一次；别的 resize 处理（导航栏变宽变窄等）跑完、布局稳定后再算一次，免得量到中间状态多扣一截
/* 左边工具、右边“记录”的页面（改录音、批量、语音转文字）：右边的记录卡片底边和左边对齐（和配音页右栏一样整列，不再半截停住），
   记录多了在卡片里面滚，最多到窗口底边（2026-11-15 界面检查）。配音页自己管（fitScript），换声是上下排的，不走这里 */
const fitSideRO = window.ResizeObserver ? new ResizeObserver(() => setTimeout(fitSide, 0)) : null;
function fitSide() {
  const g = $('.grid-tts'), side = g?.querySelector(':scope > .side-col'), stack = g?.querySelector(':scope > .stack'), card = side?.children.length === 1 ? side.firstElementChild : null;
  if (!card || side.hidden || $('#script')) return;
  if (MOB() || getComputedStyle(g).gridTemplateColumns.split(' ').length < 2) { card.style.minHeight = card.style.maxHeight = ''; card.classList.remove('side-fit'); return; }
  const h = Math.round(stack.getBoundingClientRect().height), pb = $('#pbar'), limit = (pb && pb.offsetHeight ? pb.offsetTop : innerHeight) - 16;
  card.classList.add('side-fit'); card.style.minHeight = h + 'px'; card.style.maxHeight = Math.max(h, Math.round(limit - (card.getBoundingClientRect().top + scrollY))) + 'px';
  if (fitSideRO && fitSideRO._s !== stack) { fitSideRO.disconnect(); fitSideRO.observe(stack); fitSideRO._s = stack; }
}
addEventListener('resize', fitSide);
{ let q = 0; const kick = () => { if (!q) q = setTimeout(() => { q = 0; fitSide(); }, 30); }; new MutationObserver(ms => { if (ms.some(m => m.target === $('#main') || m.target.closest?.('.side-col'))) kick(); }).observe($('#main') || document.body, { childList: true, subtree: true }); }  // 只在换页面、或右边记录列表重画时对齐（以前播放条每次改时间都会触发，2026-11-15 审查）  // 页面和记录列表会整块重画：每次重画后再对齐一次
function igDockFit() {
  const g = $('.ig-grid.ig-dock'); if (!g) return;
  if (MOB()) { g.style.height = ''; return; }
  const top = g.getBoundingClientRect().top + scrollY, pt = pbTopUnder(g), gap = pt < innerHeight ? innerHeight - pt + 14 : 24;
  g.style.height = Math.max(460, Math.round(innerHeight - top - gap)) + 'px';
}
addEventListener('resize', igDockFit);
/* 宽窗口生图页：放了原图以后左栏也不出现滚动——原图的高度 = 左栏剩下的空间（150~620 像素）。
   竖图左右排时，右边那一列（参考图、画笔……）本来就有这么高，图至少和它一样高（不白白缩小） */
function igSrcFit() {
  const f = $('#ig-src-f'), col = f?.closest('.ig-top-f'), img = f && $('#ig-src > img', f);
  if (!f || !col) return;
  if (!img || !IG_WIDE()) { f.style.removeProperty('--igh'); return; }
  const port = f.dataset.port === '1', MAX = port ? 620 : 440, MIN = 150;
  f.style.setProperty('--igh', MAX + 'px');
  const over = col.scrollHeight - col.clientHeight, now = img.getBoundingClientRect().height || MAX;
  let h = Math.floor(now - Math.max(0, over));
  if (port) { const side = $('.ig-sb-side', f); h = Math.max(h, Math.floor(side?.getBoundingClientRect().height || 0)); }
  f.style.setProperty('--igh', Math.max(MIN, Math.min(MAX, h)) + 'px');
}
addEventListener('resize', () => {
  const w = IG_WIDE(); if (w !== igSrcFit.wide && $('#ig-src-f')) renderImg.repaintSrc?.();  // 宽 / 窄窗口切换：“使用此图”放回原处或搬进原图面板
  igSrcFit.wide = w; requestAnimationFrame(igSrcFit);
});
/* Qwen 2.1 的角色组合指令：中文、按「图 N」编号；姿势只照图 1 人台的四肢和头（不要人台的体型） */
function q21ComboPrompt(c) {
  const two = /双人/.test(c.pose?.rel || ''), pose = `姿势只参考图 1 人台的四肢和头部位置（不要图 1 的体型）${two ? '，两个人' : ''}`;
  const n = c.outfit ? 3 : 2, who = c.face ? `图 ${n} 女性的脸和发型` : '一位年轻女性';
  const wear = c.outfit ? '，穿图 2 的整套服装（只取衣服，不要图 2 里的人；款式、颜色、面料、鞋子和配饰都一样）' : '，穿合身的简单服装';
  return `${who}${wear}，${pose}，真实照片，浅灰色纯色背景`;
}
/* Fisher Pose 的 3D 人偶编辑器（插件 ComfyUI-Fisher-Pose 的独立网页，接口由 studio/fisher.py 提供）。
   onApply({ data: 人偶图 PNG, pose_json, w, h })：编辑器里点“仅应用”后回调；person：上方人物图的地址（编辑器按它的比例摆人偶） */
const FP_BODY_SEED = [{ name: '纤长', mesh: { age: 23, gender: 0, weight: 0.36, muscle: 0.42, height: 0.62, breast_size: 0, firmness: 0.65, show_genitals: false },
  proportions: { head: 0.95, neck: 1.05, shoulder: 0.95, spine: 0.97, upper_arm: 1, forearm: 1, thigh: 1.07, shin: 1.08 } }];  // 偏瘦但不露骨、腿长但不夸张（2026-11-06）
function fpSeedBodies() {  // 编辑器的“身材”预设存在本站 localStorage（编辑器和本站同源）：只放一次，删了不再补
  try {
    if (localStorage.getItem('studio.fp-body-seed') === '1') return;
    const k = 'fisher.body-presets.v1', cur = lsJSON(k, []);
    const add = FP_BODY_SEED.filter(x => !cur.some(c => c.name === x.name));
    localStorage.setItem(k, JSON.stringify([...cur, ...add].slice(0, 30))); localStorage.setItem('studio.fp-body-seed', '1');
  } catch { }
}
function fisherEdit(person, poseJson, onApply) {
  fpSeedBodies();
  const ov = document.createElement('div'); ov.className = 'fp-ov';
  ov.innerHTML = `<div class="fp-load tiny">正在载入 3D 人偶编辑器…</div><iframe class="fp-frame" src="/extensions/ComfyUI-Fisher-Pose/editor/freepose.html?embedded=1" title="3D 人偶编辑器" allow="clipboard-read; clipboard-write"></iframe>`;
  document.body.append(ov);
  const fr = $('iframe', ov);
  const close = () => { removeEventListener('message', recv); document.removeEventListener('keydown', esc_, true); try { fr.contentWindow?.freePose?.dispose?.(); } catch { } ov.remove(); };
  const esc_ = e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  document.addEventListener('keydown', esc_, true);
  const recv = e => {
    if (e.source !== fr.contentWindow || e.origin !== location.origin) return;
    const t = e.data?.type;
    if (t === 'fisher-ready') {
      $('.fp-load', ov)?.remove();
      fr.contentWindow.postMessage({ type: 'fisher-load', payload: { pose_json: poseJson || '{}', extra_prompt: '', autoApply: false,
        studio: { camera: false, canGenerate: false, canOpenWorkflow: false, cameraEnabled: false, outputWidth: 1024, outputHeight: 1024 },
        referencePreview: person || null, referencePreview2: null, referenceImage2Connected: false } }, location.origin);
    } else if (t === 'fisher-close') close();
    else if (t === 'fisher-editor-error') toast(e.data.message || '人偶编辑器出错', true);
    else if (t === 'fisher-apply') {
      let d; try { d = JSON.parse(e.data.payload?.pose_json || '{}'); } catch { d = {}; }
      const img = d.poseReference;
      if (typeof img !== 'string' || !img.startsWith('data:image/png;base64,')) return fr.contentWindow.postMessage({ type: 'fisher-error', message: '没有拿到人偶图，请再点一次“仅应用”' }, location.origin);
      delete d.poseReference; delete d.shotPreview;  // 存起来的姿势不带图（下次打开编辑器时它自己重画）
      const im = new Image(); im.onload = () => { onApply({ data: img, pose_json: JSON.stringify(d), w: im.naturalWidth, h: im.naturalHeight }); close(); }; im.src = img;
    }
  };
  addEventListener('message', recv);
}
const IMG_DT0 = { on: false, face: true, hand: true, strength: .35, strength2: .45, prompt: '' };  // 自动细化：默认关
async function renderImg() {
  const st = S.img = Object.assign({ model: '', mode: 'txt', size: '1:1', count: 1, seed: -1, prompt: '' }, imgDefaults(), S.img || {});
  $('#main').innerHTML = `<div class="page-head"><div><h1 class="page-title">生图</h1></div></div>
    <div class="ig-grid">
      <div class="card ig-form">
        <div class="field"><span class="label">模型</span><button type="button" class="ig-model-btn" id="ig-model" aria-haspopup="dialog"></button><div class="tiny" id="ig-model-d" style="margin-top:2px" hidden></div></div>
        <div class="field ig-mode-f"><span class="label">使用此图${hintHtml('<b>图生图</b>：参照原图重新绘制整张图，保留大致构图，风格、颜色和细节会改变；改动幅度由“重绘强度”决定。<br><b>局部重画</b>：仅重画在图上涂抹的区域，未涂抹的部分完全不变，适合更换衣服、脸部、背景或移除物体。<br><b>提示词写法</b>：图生图描述修改后整张图的样子；局部重画只描述涂抹区域要画成的内容。如需直接下达“把短袖换成长裙”这类指令，请选择“Qwen 指令改图”模型。', 'sm')}</span><div class="seg full" id="ig-mode">${IMG_MODES.filter(([k]) => k !== 'txt' && k !== 'edit').map(([k, n]) => `<button type="button" data-k="${k}" class="${st.mode === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
        <div class="field"><span class="label" id="ig-p-label">提示词</span>
          <div class="ig-composer">
            <textarea class="textarea" id="ig-prompt" rows="5">${esc(st.prompt)}</textarea>
            <div class="ig-cbar">
              <button type="button" class="ig-cb" id="ig-ai" title="使用 AI 助手将想法扩写为完整的提示词">${ICON.wand}<span>AI 优化</span></button>
              <button type="button" class="ig-cb" id="ig-enh-q" hidden aria-label="增强提示词">${ICON.sparkle}<span>增强</span></button><button type="button" class="ig-cb" id="ig-enh-undo" hidden aria-label="撤销增强" data-tip="撤销增强，恢复原文（Ctrl+Z）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button>
              <button type="button" class="ig-cb" id="ig-combo-p" hidden data-tip="填入角色组合指令（指令改图模型）：图 1 为姿势线稿，图 2、图 3 为衣服或脸" aria-label="组合指令"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="9.5" r="5"/><circle cx="15" cy="9.5" r="5"/><circle cx="12" cy="14.5" r="5"/></svg><span>组合指令</span></button>
              <button type="button" class="ig-cb" id="ig-adv-open" title="采样、种子、负面提示词、高清修复、LoRA、输出格式">${ICON.sliders}<span>高级参数</span><span class="ig-adv-n" id="ig-adv-n"></span></button>
              <span class="spacer"></span>
              <button type="button" class="ig-gen" id="ig-go" title="生成（Ctrl + Enter）"><span>生成</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
            </div>
          </div>
          <div class="tiny ig-note" id="ig-note"></div></div>
        <div class="field" id="ig-enh-f" hidden></div>
        <div class="field ig-src-f" id="ig-src-f"></div>
        <div class="field" id="ig-ctl-f"></div>
        <div class="field" id="ig-size-f"></div>
        <div class="row" style="gap:14px;align-items:flex-end;flex-wrap:wrap">
          <div class="field" style="margin:0"><span class="label">生成数量</span><div class="seg" id="ig-count">${[1, 2, 3, 4].map(n => `<button type="button" data-n="${n}" class="${st.count === n ? 'on' : ''}">${n} 张</button>`).join('')}</div></div>

        </div>
      </div>
      <div class="stack">
        <div id="ig-live"></div>
        <div class="card ig-gal-card"><div class="row between"><h3 class="card-title" style="margin:0"><span id="ig-ttl">生成结果</span><span class="tiny" id="ig-n" style="margin-left:8px;font-weight:400"></span></h3><div class="row" style="gap:6px">${galLayBtn('ig-lay')}<button type="button" class="btn small ghost vd-allb" id="ig-all" aria-pressed="false" data-tip="在此平铺显示全部生成的图片">全部图片</button></div></div><div class="ig-gal" id="ig-gal"><div class="shimmer"></div></div></div>
      </div>
    </div>`;
  const igCtlIt = { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="4.5" r="2"/><path d="M12 7v7M12 9l-5 3M12 9l5-2M12 14l-3 6M12 14l3 6"/></svg>',
    label: () => IMG_CTL ? (st.ctlType === 'canny' ? '照线条画' : '照姿势画') : '参考姿势', nodes: [$('#ig-ctl-f')] };
  const igModeIt = { label: () => (IMG_MODES.find(m => m[0] === st.mode) || [, '文生图'])[1], nodes: [$('#ig-mode').closest('.field')] };  // 只在放了原图时出现（见 paintMode）
  const igEnhIt = { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/></svg>',
    // 2026-11-16 用户：输入框下面这排显示不全，字再精简——按钮上只写用谁增强（图标就是“增强”），完整的写在悬停说明里
    label: () => (enhLbl(enhVal()).replace(/ \+ /g, '+') || '不增强') + enhVer(), tip: () => '提示词增强：' + (enhLbl(enhVal()) || '关') + enhVer(), nodes: [$('#ig-enh-f')] };  // Qwen 2.1 的提示词增强（见 paintEnh）
  const igRefresh = renderImg.chipsRefresh = igV2({
    prompt: '#ig-prompt', model: $('#ig-model'),
    src: { node: $('#ig-src-f'), thumb: () => IMG_SRC?.url || null, pick: () => $('#ig-src-pick')?.click(), title: '原图：不添加图片即为文生图，添加后可选择图生图或局部重画' },
    items: [
      igModeIt,
      igCtlIt,
      igEnhIt,
      { icon: IG_FRAME, label: () => (st.mode === 'txt' ? (st.size === 'custom' ? `${st.cw || 1024}×${st.ch || 1024}` : (IMG_SIZES.find(z => z[0] === st.size) || [, , ])[0] || '') : st.mode === 'edit' ? ((st.eSize || 'src') === 'src' ? '同图 1' : st.eSize === 'custom' ? `${st.ecw || 1024}×${st.ech || 1024}` : st.eSize) : '原尺寸') + ' · ' + (st.count || 1) + ' 张',
        nodes: [$('#ig-size-f'), $('#ig-count').closest('.row')] },
    ] });
  if (igEnhIt.chip) igEnhIt.chip.hidden = true;  // 读到状态、确定是 Qwen 2.1 才显示（paintEnh）
  igCtlIt.chip?.classList.add('ph-tool');  // 手机：参考姿势收进输入框上面那排最后的“⋯”（phone.js，2026-11-16）
  // 2026-11-17 用户：右边选项栏平时关着——“先提取衣服”也放进输入框下面那排（Qwen 2.1、放了参考图时才出现），点一下开 / 关，和选项栏里的开关同步
  const xchip = document.createElement('button'); xchip.type = 'button'; xchip.className = 'ig-chip ig-xchip'; xchip.hidden = true;
  xchip.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 5.5a2 2 0 1 1 2.6 1.9c-.4.1-.6.5-.6.9V9"/><path d="M12 9 3.4 15.2a1 1 0 0 0 .6 1.8h16a1 1 0 0 0 .6-1.8z"/></svg><span>提取衣服</span>';  // 衣架：电脑上只显示图标（这一排放不下会被截成“…”），手机上带字
  $('#ig-prompt').closest('.field')?.querySelector('.ig-chips')?.append(xchip);
  const paintX = () => {
    const on = !!st.refX; xchip.hidden = !(isQ() && IMG_REFS.length && (st.mode === 'edit' || st.mode === 'inpaint'));
    xchip.classList.toggle('on', on); xchip.setAttribute('aria-pressed', String(on));
    xchip.dataset.tip = (on ? '已开启：' : '') + '参考图是穿在人身上的衣服照片时开启：先把衣服单独提取成白底图再参考，镂空和露肤处按图 1 人物的肤色画，不照搬参考图模特的肤色。每张参考图约多 2～3 分钟，同一张只提取一次';
    xchip.setAttribute('aria-label', '先提取衣服' + (on ? '（已开启）' : ''));
    const sw = $('#ig-xref'); if (sw) sw.checked = on; };
  xchip.onclick = e => { e.stopPropagation(); st.refX = !st.refX; save(); paintX(); };
  const rid = renderImg.rid = (renderImg.rid || 0) + 1;  // 等状态期间又重画了一次（比如点了“复用”）：旧的这次不要再绑定
  const galP = imgGallery();  // 图库和状态一起读，不用等状态读完才开始
  const status = IMGST = await api('/api/img/status').catch(e => ({ error: e.message, models: [], caps: {} }));
  if (!$('#ig-model') || renderImg.rid !== rid) return;
  const caps = status.caps || {}, ms = status.models || [];
  Object.keys(imgDefaults()).forEach(k => { if (st[k] === undefined) st[k] = imgDefaults()[k]; });
  if (!status.error && !ms.some(m => m.key === st.model && !m.missing.length)) st.model = status.default_model || ms[0]?.key || '';  // 读不到状态时别把选好的模型改掉
  if (!status.error && status.model_defaults && (st.pdef || 0) < 3) {  // 以前所有模型共用一套默认值：还停在那套默认值上的，换成当前模型的推荐值（只做一次）
    const G = status.defaults || {}, M = imgDefaults(st.model);
    ['steps', 'cfg', 'sampler', 'scheduler'].forEach(k => { if (st[k] === (G[k] ?? '')) st[k] = M[k]; });
    if (st.sampler === 'dpm++2m_sde' && st.scheduler === 'beta') st.sampler = M.sampler;  // 测试版本推荐过的组合：在这个引擎里出图是色块
    if (st.strength === 0.6) st.strength = M.strength;  // 以前的默认改动幅度 60%（实测几乎不变）→ 新的默认
    st.pdef = 3; persist();
  }
  const save = () => persist();
  const modelTip = k => { const D = imgDefaults(k); return `
推荐：${D.steps} 步 · CFG ${D.cfg}${D.sampler ? ' · ' + D.sampler : ''}${D.scheduler ? ' + ' + D.scheduler : ''}`; };
  /* 模型选择器：按钮上显示当前模型；点开是按架构分组的列表（名字、特点、速度、大小、推荐参数），模型多了也好选 */
  const pick = k => {
    if (k === st.model) return;
    const A = imgDefaults(st.model), B = imgDefaults(k);
    const moved = ['steps', 'cfg', 'sampler', 'scheduler'].filter(x => st[x] === A[x] && A[x] !== B[x]);  // 没自己改过的，换成新模型的推荐值；自己改过的不动
    moved.forEach(x => { st[x] = B[x]; });
    st.model = k; save(); paintModel(); paintAdv(); paintMode(); paintCtl();
    if (moved.length && !ms.find(x => x.key === k)?.comfy) toast(`已切换为此模型的推荐参数：${B.steps} 步${B.sampler ? ' · ' + B.sampler + (B.scheduler ? ' + ' + B.scheduler : '') : ''}`);
  };
  const recText = k => { const D = imgDefaults(k); return `${D.steps} 步 · CFG ${D.cfg}${D.sampler ? ' · ' + D.sampler : ''}${D.scheduler ? ' + ' + D.scheduler : ''}`; };
  const paintModel = () => {
    const m = ms.find(x => x.key === st.model), btn = $('#ig-model');
    btn.innerHTML = m ? `<span class="igm-main"><b>${esc(m.name)}</b><span class="tiny">${esc([m.base, m.tag].filter(Boolean).join(' · '))}</span></span><span class="igm-speed tiny">${esc(m.speed || '')}</span>${ICON.chev}`
      : `<span class="igm-main"><b>选择模型</b></span>${ICON.chev}`;
    btn.title = m ? m.desc : '';
    if ($('#ig-fx-w')) $('#ig-fx-w').hidden = !(m && (m.edit || qEdit(m)));
    paintEnh();
    if ($('#ig-combo-p')) $('#ig-combo-p').hidden = typeof matsComboPrompt !== 'function';  // 组合指令一直显示（用别的模型时点它会先换成指令改图模型）
    const md = $('#ig-model-d'); md.hidden = !!(m && !m.missing.length); md.textContent = m ? '缺少文件：' + m.missing.join('、') : (/not found|404/i.test(status.error || '') ? '后台版本过旧，请重启 Studio。' : status.error || '无法读取模型');  // 只在出问题时显示
    /* 2026-11-16 用户：一个模型一行太多、不好选。改成一个底子一行（Apple 菜单的分组 + 分段选择）：
       底子名在上，几个版本是一排短名字的胶囊，当前的高亮；特点、速度、大小放在悬停说明里。放了图时只列能图生图 / 改图的 */
    btn.onclick = () => {
      const img = !!(IMG_SRC || st.srcId), ok = x => !img || !!(x.edit || qEdit(x));  // 2026-11-16 用户：放了图只列改图模型（Qwen 改图 v23、Qwen 2.1）
      const list = ms.filter(ok), groups = [...new Set(list.map(x => x.base || '其他'))];
      const miss = x => x.missing.every(t => t.startsWith('新版 ComfyUI')) ? '需更新 ComfyUI' : '未下载';
      const tip = x => [x.name, x.tag, x.missing.length ? miss(x) : [x.speed, x.gb ? x.gb + ' GB' : ''].filter(Boolean).join(' · '), x.desc].filter(Boolean).join('\n');
      popover(btn, `<div class="igm-pop">${groups.map(g => { const xs = list.filter(x => (x.base || '其他') === g), on = xs.some(x => x.key === st.model);
        return `<div class="igm-b${on ? ' on' : ''}"><div class="igm-g">${esc(g)}</div><div class="igm-vs">${xs.map(x => `<button type="button" class="igm-v${x.key === st.model ? ' on' : ''}" data-m="${esc(x.key)}"${x.missing.length ? ' disabled' : ''} data-tip="${esc(tip(x))}" aria-pressed="${x.key === st.model}">${esc(IMG_VAR[x.key] || x.name)}</button>`).join('')}</div></div>`; }).join('')}</div>`, pop => {
        $$('.igm-v', pop).forEach(it => it.onclick = () => { pop.close(); pick(it.dataset.m); });
      }, { width: 380, title: '模型', anchored: !!window.phSheet?.on() });  // 手机：贴着按钮弹出的小菜单（11-23 用户：点了从底下升起一整页不对）
    };
  };
  const curM = () => ms.find(x => x.key === st.model);
  // Qwen 2.1（ComfyUI）：文生图 / 指令改图 / 局部重画都在一个模型里
  // （用 IMGST：输入框下的小按钮在状态读到之前就会问一次，那时 ms 还没定义）
  function isQ() { return !!(IMGST?.models || []).find(x => x.key === st.model)?.comfy; }
  function editM() { const m = (IMGST?.models || []).find(x => x.key === st.model); return !!(m && (m.edit || qEdit(m))); }  // 能按指令改图的模型（v23 或 Qwen 2.1）
  function qEdit(m) { return !!(m?.comfy && (m.modes || []).includes('edit')); }  // ComfyUI 上能改图的（Qwen 2.1 高质量 / 快速）；MOSS、H3-Image 只做文生图
  // Qwen 2.1 的提示词增强：谁来写 —— 关 / 官方 / 助手（AI 助手看图直接写）。st.q21Enh 存后台的值：pe / ai / off
  function enhVer() {  // 文生图「助手」用的系统指令不是默认版本时，写在“增强”按钮上（在“查看完整提示词 → 系统指令”里选，2026-11-16）
    if (st.mode !== 'txt' || enhWho(enhVal()) !== 'ai') return '';
    const c = window.TPL?.cur, x = c?.vers?.img_ai_t2i; return x && (x.id || x.own) ? ' · ' + (x.own ? c.name : x.label) : ''; }
  function enhLbl(v) { return { pe: '官方', ai: '助手' }[v] || ''; }  // 函数（会提前生效）：输入框下的小按钮在这之前就会问
  function enhWho(v) { return { pe: 'pe', ai: 'ai' }[v] || 'off'; }
  function enhMake(who) { return who === 'pe' || who === 'ai' ? who : 'off'; }
  function enhVal() { const v = st.q21Enh; return enhLbl(v) ? v : 'off'; }
  function enhLastVal() { const v = st.q21EnhLast; return enhLbl(v) ? v : 'pe'; }
  function enhQPaint() {  // 输入框里的“增强”按钮：Qwen 2.1 才有；已增强过亮起；说明写清用哪种写法
    const b = $('#ig-enh-q'); if (!b) return;
    const ok = isQ() && (IMGST?.q21_pe || {})[st.mode === 'txt' ? 't2i' : 'i2i'] !== false; b.hidden = !ok; if (!ok) { const u = $('#ig-enh-undo'); if (u) u.hidden = true; return; }
    const v = enhVal() === 'off' ? enhLastVal() : enhVal();
    b.classList.toggle('on', !!st.q21Pre && !ENH_RUN);
    b.dataset.tip = ENH_RUN ? '停止增强' : st.q21Pre ? '这段提示词已增强过，生成时不会再增强。点击按「' + enhLbl(v) + '」重新增强' : '增强提示词（' + enhLbl(v) + '）：写好后填回输入框，可以先看、再改、再生成';
    b.setAttribute('aria-label', ENH_RUN ? '停止增强' : '增强提示词');
    const u = $('#ig-enh-undo'); if (u) u.hidden = !(ok && st.q21Pre && typeof st.q21Pre.orig === 'string' && !ENH_RUN);
  }
  async function enhRun(body) {
    if (!ta.value.trim()) return toast('请先描述要生成的画面', true);
    const comp = ta.closest('.ig-composer') || ta.parentElement, orig = ta.value, run = ENH_RUN = { t0: Date.now(), stop: false };
    const ov = document.createElement('div'); ov.className = 'ig-enh-run';
    ov.innerHTML = `<span class="pg-shim">正在增强 · ${esc(enhLbl(body.enhance))}</span><span class="ig-enh-sec">0 秒</span>`;
    comp.classList.add('ig-enhancing'); ta.classList.add('ig-ta-busy'); ta.readOnly = true;
    { const fld = ta.closest('.ig-top-f') || comp, host = fld.parentElement || comp, fr = fld.getBoundingClientRect(), hr = host.getBoundingClientRect();  // 外框会裁掉超出的部分：状态挂在外框外面，贴着输入框上沿
      host.append(ov); ov.style.left = Math.round(fr.left - hr.left + 10) + 'px'; ov.style.top = Math.round(fr.top - hr.top - 38) + 'px'; ov.style.bottom = 'auto'; } enhQPaint(); $('#ig-enh-q').innerHTML = ICON.x + '<span>停止</span>';
    const tick = setInterval(() => { const sec = Math.round((Date.now() - run.t0) / 1000); $('.ig-enh-sec', ov).textContent = sec + ' 秒' + (sec > 15 && WITH_AI_J.includes(body.enhance) ? ' · 首次需载入 AI 助手' : ''); }, 500);
    const done = () => { clearInterval(tick); ov.remove(); comp.classList.remove('ig-enhancing'); ta.classList.remove('ig-ta-busy'); ta.readOnly = false; if (ENH_RUN === run) ENH_RUN = null; const b = $('#ig-enh-q'); if (b) b.innerHTML = ICON.sparkle + '<span>增强</span>'; enhQPaint(); };
    try {
      const r = await api('/api/img/q21-enhance', { body });
      if (run.stop || !ta.isConnected) return;
      ta.readOnly = false; taReplace(ta, r.prompt || ta.value); st.prompt = ta.value; sessionStorage.setItem('igDraft', ta.value);
      st.q21Pre = { enh: body.enhance, orig, text: ta.value }; save(); enhQPaint();
      const undo = () => renderImg.enhUndo?.();
      if (r.note) toast(r.note); else toastAct('已增强提示词', '撤销', undo);
    } catch (e) { if (!run.stop) toast(e.message, true); }
    finally { done(); }
  }
  function enhStop() { if (!ENH_RUN) return; ENH_RUN.stop = true; toast('已停止增强'); const comp = ta.closest('.ig-composer') || ta.parentElement; document.querySelector('.ig-enh-run')?.remove(); comp.classList.remove('ig-enhancing'); ta.classList.remove('ig-ta-busy'); ta.readOnly = false; ENH_RUN = null; const b = $('#ig-enh-q'); if (b) b.innerHTML = ICON.sparkle + '<span>增强</span>'; enhQPaint(); }
  function paintEnh() {
    const f = $('#ig-enh-f'); if (!f) return;
    const pe = status.q21_pe || {}, kind = st.mode === 'txt' ? 't2i' : 'i2i', ok = isQ() && pe[kind] !== false;
    f.hidden = !ok; if (igEnhIt.chip) igEnhIt.chip.hidden = !ok; enhQPaint(); if (!ok) return;
    const v = enhVal(), who = enhWho(v);
    f.innerHTML = `<span class="label">提示词增强${hintHtml('<b>官方</b>：Qwen 官方的提示词增强模型把您的话扩写成详细的指令（姿势、关节、光影、保持项），最准、最快；偶尔会拒绝（此时按原话生成）。<br><b>助手</b>：本地 AI 助手（Qwen3.8）看图，按官方的写法直接写，不经过增强模型。<br>用到 AI 助手时每张多约 30~60 秒（需临时载入）。实际使用的提示词可在图片详情中查看。', 'sm')}</span>
      <div class="seg full" id="ig-enh">${[['off', '关'], ['pe', '官方'], ['ai', '助手']].map(([k, n]) => `<button type="button" data-k="${k}" class="${who === k ? 'on' : ''}">${n}</button>`).join('')}</div>
      <div class="row ig-enh-opts">${v !== 'off' && st.mode !== 'txt' ? `<label class="row ig-check ig-emph"><input type="checkbox" id="ig-emph"${st.q21Emph === true ? ' checked' : ''}> 强调主要改动${hintHtml('增强写出来的指令很长，要改的那件事常常只有一句，容易改不到位。打开后把主要改动写在指令的最前面和最后面，并注明左右（人物的左边在画面右边）。默认关。', 'sm')}</label>` : ''}</div>
      ${IMG_POSE && st.mode === 'edit' && v !== 'off' ? `<div class="tiny" style="margin-top:4px">放了 3D 人偶时不增强${hintHtml('增强会改掉姿势 LoRA 认的固定指令，所以按原话生成。', 'sm')}</div>` : ''}
      <div class="row ig-enh-pre"${v === 'off' ? ' hidden' : ''}><button type="button" class="btn small" id="ig-enh-go" title="只写提示词、不出图，把结果填进提示词框：看过、改过再点“生成”">先增强</button><span class="tiny">先看增强后的提示词，改好再生成</span></div>`;
    { const lab = f.querySelector(':scope > .label'), pre = $('.ig-enh-pre', f), hd = document.createElement('div');  // “先增强”放在标题那一行右边（不另占一行）
      hd.className = 'row ig-enh-h'; lab.before(hd); hd.append(lab, pre); pre.querySelector('.tiny')?.remove(); }
    const set = nv => { st.q21Enh = nv; if (nv !== 'off') st.q21EnhLast = nv; save(); paintEnh(); igRefresh?.(); requestAnimationFrame(igSrcFit); };
    $$('#ig-enh button', f).forEach(b => b.onclick = () => set(enhMake(b.dataset.k)));
    $('#ig-enh-go', f).onclick = () => renderImg.preEnh?.();
    if ($('#ig-emph', f)) $('#ig-emph', f).onchange = e => { st.q21Emph = e.target.checked; save(); };
  }
  $('#ig-combo-p').onclick = e => {  // 角色组合的指令（matsComboPrompt，video.js）：按现在放了几张参考图推荐一种，替换框里的内容
    e.stopPropagation();
    if (!editM()) { const em = ms.find(m => m.edit && !m.missing.length) || ms.find(m => qEdit(m) && !m.missing.length); if (!em) return toast('没有可用的指令改图模型', true); pick(em.key); toast('已切换为 ' + em.name); }
    const fill = (outfit, face) => {
      const c = { pose: { rel: IMG_SRC?.name || '' }, outfit, face };
      const ta = $('#ig-prompt'), p = isQ() ? q21ComboPrompt(c) : matsComboPrompt(c);
      ta.value = st.prompt = p; st.q21Pre = null; renderImg.comboP = p; ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus(); toast('已填入组合指令');
    };
    ctxMenu({ anchor: $('#ig-combo-p') || e.currentTarget }, [{ group: '图 1 为姿势线稿' },
      { label: '图 2 衣服 + 图 3 脸', on: () => fill(true, true) },
      { label: '图 2 衣服', on: () => fill(true, false) },
      { label: '图 2 脸', on: () => fill(false, true) }]);
  };
  paintModel();
  // ---- 方式：文生图 / 图生图 / 局部重画
  // 方式跟着原图走：没放图就是文生图；放了图默认图生图，可以换成局部重画；把图移除又回到文生图
  const paintMode = () => {
    restoreSrc();
    if ((IMG_SRC || st.srcId) && curM() && !editM()) {  // 放了图、现在的模型不是改图模型（只做文生图的，或 sd.cpp 的图生图，2026-11-16 用户不要）：换成 Qwen 2.1
      const em = ms.find(m => qEdit(m) && !m.missing.length) || ms.find(m => m.edit && !m.missing.length);
      if (em) { pick(em.key); toast('已切换为 ' + em.name + '（放了图时用改图模型）'); return; }
    }
    const ed = !!curM()?.edit, q = isQ();
    if (ed) st.mode = 'edit';  // 指令改图模型：只有这一种用法（没放图时生成会提示先放图）
    else if (q) st.mode = !IMG_SRC && !st.srcId ? 'txt' : st.qMode === 'inpaint' ? 'inpaint' : 'edit';  // Qwen 2.1：没放图 = 文生图；放了图 = 指令改图，或涂抹后局部重画
    else if (!IMG_SRC && !st.srcId) st.mode = 'txt'; else if (st.mode === 'txt' || st.mode === 'edit') st.mode = st.useInp ? 'inpaint' : 'img';  // 经过只能改图的 v23 再换回来：还是上次选的局部重画 / 图生图
    const mf = $('#ig-mode').closest('.field'), modes = q ? [['edit', '指令改图'], ['inpaint', '局部重画']] : IMG_MODES.filter(([k]) => k !== 'txt' && k !== 'edit');
    if ($('#ig-mode').dataset.q !== String(q)) {  // 换了模型种类：重建“使用此图”的选项和说明
      $('#ig-mode').dataset.q = String(q);
      $('#ig-mode').innerHTML = modes.map(([k, n]) => `<button type="button" data-k="${k}">${n}</button>`).join('');
      $$('#ig-mode button').forEach(b => b.onclick = () => { st.mode = b.dataset.k; st.useInp = b.dataset.k === 'inpaint'; if (isQ() || st.useInp) st.qMode = b.dataset.k; save(); paintMode(); if (st.mode === 'inpaint') requestAnimationFrame(imgSrcToStage); });  // 局部重画：原图放到大画面上直接涂（2026-11-10）
      $('.label', mf).innerHTML = '使用此图' + (q ? hintHtml('<b>指令改图</b>：直接写要怎么改（换衣服、换姿势、换背景），可再放图 2、图 3 作参考，例如“将图1女性穿上图2的服装，保持脸、发型和背景不变”。<br><b>局部重画</b>：在图上涂抹要改的地方（例如脸和头发、鞋子），只重画涂抹的区域，其余完全不变；同样可以放参考图，例如“将图1女性的面部和头发替换成图2的女性”。适合原图很大或要改的地方很小的情况。', 'sm')
        : hintHtml('<b>图生图</b>：参照原图重新绘制整张图，保留大致构图，风格、颜色和细节会改变；改动幅度由“重绘强度”决定。<br><b>局部重画</b>：仅重画在图上涂抹的区域，未涂抹的部分完全不变，适合更换衣服、脸部、背景或移除物体。<br><b>提示词写法</b>：图生图描述修改后整张图的样子；局部重画只描述涂抹区域要画成的内容。如需直接下达“把短袖换成长裙”这类指令，请选择“Qwen 指令改图”模型。', 'sm'));
    }
    mf.hidden = st.mode === 'txt' || ed;
    if (igModeIt.chip) igModeIt.chip.hidden = st.mode === 'txt' || ed;
    // 不同用法，提示词的写法不一样：图生图写改完后整张图的样子；局部重画只写涂抹的那一块；只有指令改图能直接说“把…换成…”
    $('#ig-prompt').placeholder = q ? (st.mode === 'edit' ? '直接写要怎么改，例如：将图1女性的衣服换成图2的连衣裙，保持脸、发型、姿势和背景不变'
      : st.mode === 'inpaint' ? '写涂抹区域要改成什么，例如：将图1女性的面部和头发替换成图2的女性' : '描述要生成的画面，中文即可')
      : ed ? ''
      : st.mode === 'img' ? '描述修改后整张图的样子（请勿写“把…换成…”），例如：一位长发女子穿着白色短袖 T 恤站在海边，阳光，写实摄影'
      : st.mode === 'inpaint' ? '仅描述涂抹区域要画成的内容，例如：白色短袖 T 恤，棉质，自然褶皱' : '描述想要的画面';
    $$('#ig-mode button').forEach(b => b.classList.toggle('on', b.dataset.k === st.mode));
    $('#ig-p-label').innerHTML = st.mode === 'txt' ? '' : st.mode === 'img' ? '修改后的画面描述' : st.mode === 'edit' ? '修改指令' : q ? '修改指令（只改涂抹的区域）' : '重绘区域的内容';
    paintSrc(); paintSize(); paintEnh(); igRefresh?.();
  };
  // ---- 原图（图生图 / 局部重画）
  const restoreSrc = () => {  // 上次选的图库里的原图：还在的话接着用
    if (IMG_SRC || !st.srcId) return;
    const x = imgGal.find(g => g.id === st.srcId);
    if (x) IMG_SRC = { kind: 'gallery', id: x.id, url: '/media/img/' + encodeURIComponent(x.file), w: x.width, h: x.height, name: x.prompt, _r: 1 };  // _r：恢复上次的原图（不算新放进来，不放大到画面上）
    else if (imgGal.length) st.srcId = null;  // 图库读到了、那张图却已经删了：回到文生图
  };
  const paintSrc = () => {
    const f = $('#ig-src-f'); if (!f) return;
    restoreSrc();
    // 大画面上搬过去的原图（局部重画的涂抹画布）：等这次面板重画完再看——面板重画了（占位没了）那份就是旧的；不是局部重画了要放回去。
    // 以前在面板重画之前就判断（占位还在），切回指令改图时大画面停在涂抹的样子、原图格也没放回去，输入框左上角的预览图就没了（2026-11-11 用户）
    if ($('#ig-stage #ig-src')) requestAnimationFrame(() => { if (!$('#ig-stage #ig-src') || $('#ig-src-ph2') && st.mode === 'inpaint') return;
      if (imgStage.srcOn && IG_WIDE()) imgStageSrc(); else imgStageBack(); });
    else if (st.mode === 'inpaint' && $('#ig-stage .ig-stage-src')) requestAnimationFrame(() => {  // 大画面上是改图时那张普通原图（比如刚从 v23 换回来）：换成可以涂的这份
      if (st.mode !== 'inpaint' || !$('#ig-src-f #ig-mask-c') || !$('#ig-stage .ig-stage-src')) return;
      if (imgStage.srcOn && IG_WIDE()) imgStageSrc(); else imgStageBack(); });
    { const su = IMG_SRC?.url || null, so = IMG_SRC || null;  // 按“放进来的那一次”（对象）判断：同一张图再选一次也放到大画面上（以前比地址，选同一张不显示）
      if (imgStage.srcInit) { imgStage.srcInit = false; imgStage.srcUrl = su; imgStage.srcObj = so; }
      else if (so !== imgStage.srcObj && !so?._r) { imgStage.srcUrl = su; imgStage.srcObj = so;
        if (IG_WIDE()) { if (su) { imgStage.srcOn = true; imgStage.closed = false; imgStage.off = false; } else if (imgStage.srcOn) { imgStage.srcOn = false; imgStage.closed = true; }
          const g = $('#ig-gal'); if (g) { delete g.dataset.sig; requestAnimationFrame(() => imgGallery()); } } } }
    const s = IMG_SRC, R = st.mode === 'edit' || (st.mode === 'inpaint' && isQ());  // R：有图 2、图 3 参考图
    const mf = $('#ig-mode')?.closest('.field');
    if (mf && mf._home && mf.parentElement !== mf._home) mf._home.prepend(mf);  // 上次搬进原图面板的“使用此图”先放回原处（下面要重写这一块）
    f.innerHTML = `<span class="label">${st.mode === 'edit' ? '要改的图' : '原图'}${st.mode === 'inpaint' ? hintHtml('用手指或鼠标在图上涂抹需要重画的区域，再描述该区域要画成的内容。', 'sm') : s ? '' : hintHtml('不添加图片即为文生图。添加图片后，可在其基础上修改（图生图），或仅重画其中一部分（局部重画）。', 'sm')}</span>
      ${s ? `<div class="ig-src" id="ig-src"><img src="${esc(s.url)}" alt="" draggable="false">${st.mode === 'inpaint' ? '<canvas id="ig-mask-c"></canvas>' : ''}<button type="button" class="ig-src-x" id="ig-src-x" title="移除此图" aria-label="移除此图">${ICON.x}</button></div>
        <div class="tiny" style="margin-top:4px">${R ? '图 1 · ' : ''}${s.w} × ${s.h}</div>` : `<div class="ig-src empty b5-up" id="ig-src-pick" role="button" tabindex="0" aria-label="添加原图">${ICON.up}<div>${st.mode === 'edit' ? '要改的图' : '原图'}</div><span class="tiny">可选</span></div>
        ${R ? '' : `<div class="row ig-src-btns ig-src-btns-r"><button type="button" class="btn small" id="ig-paste" title="粘贴剪贴板中的图片（截图后直接点击此处）">粘贴</button><button type="button" class="btn small" id="ig-pick">从图库选</button><button type="button" class="btn small" id="ig-up" title="从电脑里选择图片">从电脑选</button></div>`}`}
      ${R ? `<div class="ig-refs"><div class="row ig-refs-h"><span class="label">参考图${hintHtml(isQ() ? '最多再添加 2 张，例如一件衣服、一张脸、画风图或另一个人物。上方的原图为图 1，此处依次为图 2、图 3。指令用中文按「图 N」称呼即可，例如：将图1女性穿上图2的服装，保持图1女性的脸、发型、姿势和背景不变。' : '最多再添加 2 张，例如一件衣服、一个背景或另一个人物。上方的原图为图 1（Picture 1），此处依次为图 2、图 3。提示词按以下方式书写最准确：Make the woman in Picture 1 wear the outfit from Picture 2, keep her face, pose and background unchanged.', 'sm')}</span>${isQ() && IMG_REFS.length ? `<span class="spacer"></span><label class="row ig-xref" data-tip="参考图是穿在人身上的衣服照片时开启：先把衣服单独提取成白底图再参考，镂空和露肤处按图 1 人物的肤色画，不照搬参考图模特的肤色。每张参考图约多 2～3 分钟，同一张只提取一次"><span class="tiny">先提取衣服</span><span class="switch"><input type="checkbox" id="ig-xref" aria-label="参考图先提取衣服" ${st.refX ? 'checked' : ''}><span></span></span></label>` : ''}${s ? '' : `<span class="spacer"></span><span class="row ig-src-btns ig-src-btns-r"><button type="button" class="btn small" id="ig-paste" title="粘贴剪贴板中的图片（截图后直接点击此处）">粘贴</button><button type="button" class="btn small" id="ig-pick">从图库选</button><button type="button" class="btn small" id="ig-up" title="从电脑里选择图片">从电脑选</button></span>`}</div>
        <div class="row ig-refs-r">${[0, 1].map(k => IMG_REFS[k] ? `<div class="ig-ref"><img src="${esc(IMG_REFS[k].url)}" alt="" draggable="false"><span class="ig-ref-n">图 ${k + 2}</span><button type="button" class="ig-src-x" data-rx="${k}" title="移除此参考图" aria-label="移除此参考图">${ICON.x}</button></div>`
          : k === IMG_REFS.length ? `<button type="button" class="ig-ref empty" data-ra="${k}" title="添加参考图（图 ${k + 2}）">${ICON.up}<span>图 ${k + 2}</span></button>` : '').join('')}</div><input type="file" id="ig-ref-file" accept="image/*" hidden>
</div>` : ''}
      ${st.mode === 'edit' && isQ() && s && IMGST?.q21_pose && !MOB() ? `<div class="ig-pose"><div class="row ig-refs-h"><span class="label">3D 摆姿势${hintHtml('用 3D 真人人偶摆一个姿势（拖动关节，或从 29 个常用姿势、209 张骨架图里点选），图 1 的人会照这个姿势重画（Fisher Pose + PoseStudio LoRA）。<br>人偶的身材会影响出图的体型：可以在编辑器的「体型」「比例」里调成接近图 1 的人，并用「我的身材」存下来。<br>提示词可以留空；要补充时照界面上的编号写（图 1 = 原图），会自动对上。不做提示词增强，25 步。', 'sm')}</span></div>
        <div class="row ig-refs-r">${IMG_POSE ? `<div class="ig-ref" id="ig-pose-t" title="点击修改姿势"><img src="${esc(IMG_POSE.data)}" alt="" draggable="false"><span class="ig-ref-n">人偶</span><button type="button" class="ig-src-x" id="ig-pose-x" title="不用 3D 摆姿势" aria-label="不用 3D 摆姿势">${ICON.x}</button></div>`
          : `<button type="button" class="ig-ref empty" id="ig-pose-t" title="打开 3D 人偶编辑器"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="4.5" r="2"/><path d="M12 7v7M12 9l-5 3M12 9l5-2M12 14l-3 6M12 14l3 6"/></svg><span>摆姿势</span></button>`}</div></div>` : ''}
      ${st.mode === 'inpaint' && s ? `<div class="row ig-brush"><span class="tiny">画笔</span>${isQ() ? hintHtml('Qwen 2.1 局部重画：自动按涂抹范围外扩 1.5 倍裁出，放大到 1536 重画后拼回，涂抹范围外完全不变。请涂满要改的整块，例如换脸时涂满脸和头发。', 'sm') : ''}<input type="range" id="ig-brush" min="4" max="100" value="${Math.min(100, S.ui?.igBrush || 36)}"><div class="seg" id="ig-pen"><button type="button" data-p="draw" class="on" data-tip="涂抹（B）">涂抹</button><button type="button" data-p="erase" data-tip="擦除（E）">擦除</button></div><button type="button" class="pl-ib ig-smart" data-msmart aria-pressed="false" aria-label="智能选取" data-tip="智能选取（W）：在图上点一下要改的东西，自动选出它的轮廓（点衣服只选衣服）；同一处再点一下选大一圈（整个人）。擦除模式或按住 Ctrl 点 = 去掉那一块；选完可以接着用画笔修"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m4 20 10.5-10.5"/><path d="m13 8 3 3"/><path d="M18 3v3M16.5 4.5h3M20 9v2M19 10h2M10 3v2M9 4h2"/></svg></button><button type="button" class="pl-ib ig-mundo" data-mundo="undo" aria-label="撤销" data-tip="撤销（Ctrl+Z）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button><button type="button" class="btn small ghost" id="ig-mask-x">清空</button><button type="button" class="btn small" id="ig-mask-big" title="放大到整个窗口中涂抹，更加精确">放大涂抹</button></div>
        <label class="row ig-check ig-crop"${isQ() ? ' hidden' : ''}><input type="checkbox" id="ig-crop"${st.inpaintCrop ? ' checked' : ''}> 放大细画涂抹的区域${hintHtml('仅将涂抹区域（连同周边一圈）裁切出来，放大到约 1024 后重画，再贴回原图：小区域（脸、手、衣服局部）细节显著增加，涂抹范围外完全不变。涂抹范围本身较大时，自动按普通方式绘制。', 'sm')}</label>
        <div class="row ig-brush ig-mask-adj"><span class="row ig-adj-p"><span class="tiny">扩张</span><input type="range" id="ig-mgrow" min="0" max="64" value="${st.maskGrow ?? 0}"><b class="tiny" id="ig-mgrow-v">${st.maskGrow ?? 0}px</b></span><span class="row ig-adj-p"><span class="tiny">羽化</span><input type="range" id="ig-mfea" min="0" max="64" value="${st.maskFeather ?? 4}"><b class="tiny" id="ig-mfea-v">${st.maskFeather ?? 4}px</b>${hintHtml('提交前将涂抹范围向外扩展若干像素并柔化边缘，使接缝更自然（同 ComfyUI 的 GrowMask / Feather）。', 'sm')}</span></div>` : ''}
      <div class="field" style="margin:10px 0 0"${s && st.mode !== 'edit' && !isQ() ? '' : ' hidden'}><span class="label">重绘强度：<span id="ig-str-v">${Math.round(st.strength * 100)}%</span>${hintHtml(st.mode === 'inpaint' ? '涂抹区域的改动程度：数值越大，与原图差异越大。' : '此类 Turbo 模型步数较少：60% 以下几乎不变，65%~75% 保留构图并改变颜色和细节，85% 以上仅保留大致轮廓。', 'sm')}</span>
        <div class="row ig-str-row"><input type="range" id="ig-str" min="5" max="100" step="1" value="${Math.round(st.strength * 100)}"><div class="seg ig-str-pre">${[[62, '轻微'], [72, '中等'], [85, '大改']].map(([v, n]) => `<button type="button" data-sv="${v}" class="${Math.round(st.strength * 100) === v ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>
      <input type="file" id="ig-file" accept="image/*" hidden>`;
    if (s) {  // 放了图：图（连同尺寸那行字）一块，参考图、画笔、重绘强度一块
      const sb = document.createElement('div'), a = document.createElement('div'), b = document.createElement('div');
      sb.className = 'ig-sb'; a.className = 'ig-sb-img'; b.className = 'ig-sb-side';
      const box = $('#ig-src', f); a.append(box, box.nextElementSibling);
      [...f.children].filter(c => c !== a && !c.matches('.label, input[type=file]')).forEach(c => b.append(c));
      { const pz = $('.ig-pose', b), rr = $('.ig-refs .ig-refs-r', b), pt = pz && $('#ig-pose-t', pz);  // 3D 摆姿势那一格放进参考图那一排（不另占一行）
        if (pz && rr && pt) { pt.classList.add('ig-pose-t'); pt.title = (pt.title ? pt.title + '。' : '') + '3D 摆姿势：用真人人偶摆一个姿势，图 1 的人照这个姿势重画'; rr.append(pt); const hl = $('.ig-refs .ig-refs-h > .label', b), tips = [...(pz.querySelector('.label')?.children || [])];
          const hc = hl?.querySelector('.tip-card'), pc = tips.map(x => x.querySelector?.('.tip-card')?.innerHTML).filter(Boolean).join('');
          if (hc && pc) hc.insertAdjacentHTML('beforeend', '<br><br><b>摆姿势</b>：' + pc); pz.remove(); } }  // 摆姿势的说明并进参考图的问号（一个问号就够）
      sb.append(a, b); f.querySelector(':scope > .label').after(sb);
      if (IG_WIDE()) { const rf = $(':scope > .ig-refs', b); if (rf) { rf.classList.add('ig-refs-full'); sb.after(rf); } }  // 宽窗口：参考图一排放在图下面
      const foot = [...b.querySelectorAll(':scope > .ig-brush, :scope > .ig-crop')];  // 涂抹工具（画笔、扩张 / 羽化）放在图下面整行，不挤在旁边那一列
      if (foot.length) { const ft = document.createElement('div'); ft.className = 'ig-sb-foot'; foot.forEach(x => ft.append(x)); sb.after(ft); }
      // 2026-11-10 用户：底部输入框（b5）那套里“指令改图”按钮点开是空的——“使用此图”被搬进了原图面板。b5 里它留在自己那个按钮的面板里
      if (mf && IG_WIDE() && !$('#main > .ig-grid')?.classList.contains('b5-on')) { mf._home = mf._home || mf.parentElement; b.prepend(mf); }
      f.dataset.port = s.h > s.w * 1.15 ? '1' : '';
      $('img', box).addEventListener('load', () => requestAnimationFrame(igSrcFit));
    } else f.dataset.port = '';
    { const col = f.closest('.ig-top-f'), g = f.closest('.ig-grid');  // 用类名标出“放了原图 / 竖图”（CSS 的 :has 在这里改完 DOM 后不一定重新算）
      col?.classList.toggle('ig-hassrc', !!s); g?.classList.toggle('ig-srcport', !!s); }  // 宽窗口：横图竖图都左右排（图在左、控件在右）
    { const t = $('#ig-prompt'); if (t && (t.dataset.minh || '') !== (s ? '84' : '')) { t.dataset.minh = s ? '84' : ''; t.dispatchEvent(new Event('input')); } }  // 放了原图：提示词框最矮 84（左栏还要滚动时 fitTa 可以再缩到 64），把地方让给原图
    requestAnimationFrame(igSrcFit);
    if ($('#ig-up')) $('#ig-up').onclick = () => $('#ig-file').click();
    // 参考图（图 2、图 3）：上传或从图库选
    const refMats = () => galPick(async x => { try { addRefFile(await matsFile(x)); } catch (e) { toast(e.message, true); } }, { title: '从素材库选参考图' });
    const refItems = () => [{ label: '从素材库选', icon: window.MATS_IC || CTX_IC.open, on: refMats }, { label: '从电脑选', icon: ICON.up, on: () => $('#ig-ref-file').click() },
      { label: '粘贴', icon: CTX_IC.open, on: async () => { const file = await clipImage(); if (file) addRefFile(file); } },
      { label: '从图库选', icon: CTX_IC.open, on: () => imgPick(x => { IMG_REFS.push({ kind: 'gallery', id: x.id, url: '/media/img/' + encodeURIComponent(x.file) }); paintSrc(); }) }, ...(typeof frUseItem === 'function' ? [frUseItem('用作参考图', fs => fs.forEach(f => addRefFile(f)), true)] : [])];
    const refMenu = b => ctxMenu({ anchor: b }, refItems());
    $$('[data-ra]', f).forEach(b => { b.title = MOB() ? '添加参考图' : '点击从素材库选；右键：从电脑选、粘贴、从图库选';
      b.onclick = () => slotPick(b, refItems()); b.oncontextmenu = e => { e.preventDefault(); refMenu(b); }; });
    $$('[data-rx]', f).forEach(b => b.onclick = e => { e.stopPropagation(); IMG_REFS.splice(+b.dataset.rx, 1); paintSrc(); });
    { const x = $('#ig-xref', f); if (x) x.onchange = () => { st.refX = x.checked; save(); paintX(); }; }
    paintX();  // 输入框下面那排的“提取衣服”：参考图有没有、模型 / 方式变了都重画
    if ($('#ig-pose-t', f)) $('#ig-pose-t', f).onclick = e => { if (e.target.closest('#ig-pose-x')) { e.stopPropagation(); IMG_POSE = null; paintEnh(); return paintSrc(); }
      fisherEdit(IMG_SRC?.url, IMG_POSE?.pose_json, r => { IMG_POSE = r; paintSrc(); paintEnh(); toast('已放入人偶姿势'); }); };
    const srcMats = () => galPick(async x => { try { loadUpload(await matsFile(x)); } catch (e) { toast(e.message, true); } },  // 素材库：里面有“角色组合”（依次选姿势 → 衣服 → 脸）
      { title: '从素材库选原图', combo: ms.some(m => (m.edit || qEdit(m)) && !m.missing.length) ? () => matsCombo(c => renderImg.applyCombo(c)) : null });
    const rf = $('#ig-ref-file'); if (rf) rf.onchange = e => { const file = e.target.files[0]; if (file) addRefFile(file); e.target.value = ''; };
    const sp = $('#ig-src-pick');
    if (sp) {
      const srcItems = () => [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: srcMats }, { label: '从电脑选择', icon: ICON.up, on: () => $('#ig-file').click() },
        ...($('#ig-paste') ? [{ label: '粘贴', icon: CTX_IC.open, on: () => $('#ig-paste').click() }] : []), ...($('#ig-pick') ? [{ label: '从生图图库选择', icon: CTX_IC.open, on: () => $('#ig-pick').click() }] : []), ...(typeof frUseItem === 'function' ? [frUseItem('用作原图', fs => loadUpload(fs[0]))] : [])];  // 视频截图（2026-11-19）
      sp.onclick = () => slotPick(sp, srcItems()); sp.oncontextmenu = e => { e.preventDefault(); ctxMenu({ anchor: sp }, srcItems()); };  // 2026-11-10：点一下直接打开素材库（右键：其他来源）  // 2026-11-07：来源收进菜单，框里只留图标和名字
      sp.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sp.click(); } };
      sp.ondragover = e => { e.preventDefault(); sp.classList.add('over'); }; sp.ondragleave = () => sp.classList.remove('over');
      sp.ondrop = e => { e.preventDefault(); sp.classList.remove('over'); const f = [...(e.dataTransfer.files || [])].find(x => x.type.startsWith('image/')); if (f) loadUpload(f); };
    }
    if ($('#ig-paste')) $('#ig-paste').onclick = async () => {  // 读剪贴板里的图片（浏览器不给读的话，提示用快捷键粘贴）
      try {
        const items = await navigator.clipboard.read();
        for (const it of items) { const t = it.types.find(x => x.startsWith('image/')); if (t) { const b = await it.getType(t); return loadUpload(new File([b], 'paste.' + t.split('/')[1], { type: t })); } }
        toast('剪贴板中没有图片', true);
      } catch { toast(`此处无法直接读取剪贴板：请按 ${/Mac/.test(navigator.platform) ? '⌘' : 'Ctrl'} + V 粘贴`, true); }
    };
    if ($('#ig-pick')) $('#ig-pick').onclick = () => imgPick(x => { setSrcGallery(x); });
    $('#ig-src-x') && ($('#ig-src-x').onclick = () => { IMG_SRC = null; IMG_MASK = null; st.srcId = null; save(); paintMode(); });
    $('#ig-file').onchange = e => { const file = e.target.files[0]; if (file) loadUpload(file); };
    const strSet = v => { st.strength = v / 100; $('#ig-str').value = v; $('#ig-str-v').textContent = v + '%'; $$('.ig-str-pre button').forEach(b => b.classList.toggle('on', +b.dataset.sv === v)); save(); };
    $('#ig-str').oninput = e => strSet(+e.target.value);
    $$('.ig-str-pre button').forEach(b => b.onclick = () => strSet(+b.dataset.sv));
    if (st.mode === 'inpaint' && s) bindMask();
    const all = () => [IMG_SRC?.url, ...(R ? IMG_REFS.map(r => r.url) : [])];
    const si = $('#ig-src > img', f); if (si && st.mode !== 'inpaint') { si.classList.add('zoomable'); si.title = '点击查看大图'; si.onclick = () => zoomImgs(all(), 0); }
    $$('.ig-ref img', f).forEach((im, k) => { im.classList.add('zoomable'); im.title = '点击查看大图'; im.onclick = () => zoomImgs(all(), k + 1); });
  };
  const setSrcGallery = x => { IMG_SRC = { kind: 'gallery', id: x.id, url: '/media/img/' + encodeURIComponent(x.file), w: x.width, h: x.height, name: x.prompt }; IMG_MASK = null; st.srcId = x.id; save(); paintMode(); };
  renderImg.repaintSrc = () => paintMode();
  const paintCtl = () => {  // 参考图控制（ControlNet）：只有 Z-Image Turbo 系的模型能用
    const f = $('#ig-ctl-f'); if (!f) return;
    const ok = !!curM()?.cn; if (igCtlIt.chip) igCtlIt.chip.hidden = !ok; f.hidden = !ok; if (!ok) return;
    const c = IMG_CTL, typ = st.ctlType || 'pose', str = st.ctlStr ?? .7;
    f.innerHTML = `<span class="label">参考图控制${hintHtml('<b>姿势</b>：从参考图中识别人物骨架，按此姿势绘制提示词中的人物（长相、衣服、风格均由提示词决定）。<br><b>线条</b>：按参考图的轮廓线条绘制，构图和形状与参考图一致。', 'sm')}</span>
      <div class="row ig-ctl">${c ? `<div class="ig-ctl-th"><img src="${esc(c.url)}" alt=""><button type="button" class="ig-src-x" id="ig-ctl-x" title="不使用参考图" aria-label="不使用参考图">${ICON.x}</button></div>` : `<button type="button" class="ig-ctl-th empty" id="ig-ctl-up" title="上传参考图">${ICON.up}</button>`}
        <div class="ig-ctl-o"><div class="seg full" id="ig-ctl-t">${[['pose', '姿势'], ['canny', '线条']].map(([k, n]) => `<button type="button" data-t="${k}" class="${typ === k ? 'on' : ''}">${n}</button>`).join('')}</div>
          <div class="field" style="margin:8px 0 0"><span class="label">控制强度：<span id="ig-ctl-s-v">${Math.round(str * 100)}%</span>${hintHtml('写实约 70%，动漫约 50%；过高会使画面僵硬、细节减少。', 'sm')}</span><input type="range" id="ig-ctl-s" min="20" max="120" value="${Math.round(str * 100)}"></div>
          <div class="row" style="gap:6px;margin-top:6px"><button type="button" class="btn small" id="ig-ctl-up2">${ICON.up}上传</button><button type="button" class="btn small" id="ig-ctl-pick">从图库选</button></div></div></div>
      <input type="file" id="ig-ctl-file" accept="image/*" hidden>`;
    const up = () => $('#ig-ctl-file').click();
    ['#ig-ctl-up', '#ig-ctl-up2'].forEach(q => { const b = $(q); if (b) b.onclick = up; });
    $('#ig-ctl-x') && ($('#ig-ctl-x').onclick = () => { IMG_CTL = null; paintCtl(); igRefresh?.(); });
    const ci = $('.ig-ctl-th img', f); if (ci) { ci.classList.add('zoomable'); ci.title = '点击查看大图'; ci.onclick = () => zoomImgs([IMG_CTL?.url]); }
    $('#ig-ctl-pick').onclick = () => imgPick(x => { IMG_CTL = { kind: 'gallery', id: x.id, url: '/media/img/' + encodeURIComponent(x.file), w: x.width, h: x.height }; paintCtl(); igRefresh?.(); });
    $('#ig-ctl-file').onchange = e => { const file = e.target.files[0]; if (!file) return; const fr = new FileReader(); fr.onload = () => { const im = new Image(); im.onload = () => {
      let data = fr.result, w = im.naturalWidth, h = im.naturalHeight;
      if (Math.max(w, h) > 2048) { const k = 2048 / Math.max(w, h), cv = document.createElement('canvas'); cv.width = Math.round(w * k); cv.height = Math.round(h * k); cv.getContext('2d').drawImage(im, 0, 0, cv.width, cv.height); data = cv.toDataURL('image/jpeg', .92); w = cv.width; h = cv.height; }
      IMG_CTL = { kind: 'upload', data, url: data, w, h }; paintCtl(); igRefresh?.(); }; im.src = fr.result; }; fr.readAsDataURL(file); };
    $$('#ig-ctl-t button').forEach(b => b.onclick = () => { st.ctlType = b.dataset.t; save(); $$('#ig-ctl-t button').forEach(x => x.classList.toggle('on', x === b)); igRefresh?.(); });
    $('#ig-ctl-s').oninput = e => { st.ctlStr = +e.target.value / 100; $('#ig-ctl-s-v').textContent = e.target.value + '%'; persistSoon(); };
  };
  paintCtl();
  renderImg.applyCombo = async c => {  // 角色组合：姿势 = 图 1，衣服 / 脸 = 图 2、图 3（现在不是指令改图模型的话先换过去）；生图页的按钮和素材库页面都用它
      const gen = VGEN;
      try {
        if (!editM()) { const em = ms.find(m => m.edit && !m.missing.length) || ms.find(m => qEdit(m) && !m.missing.length); if (!em) return toast('没有可用的指令改图模型', true); pick(em.key); toast('已切换为 ' + em.name); }
        if (isQ()) st.qMode = 'edit';
        const [P, ...R] = await Promise.all([c.pose, c.outfit, c.face].map(x => x ? matsFile(x).then(imgData) : null));
        if (gen !== VGEN || !$('#ig-src-f')) return;
        IMG_SRC = { kind: 'upload', data: P.data, url: P.data, w: P.w, h: P.h, name: c.pose.label || c.pose.name }; IMG_MASK = null; st.srcId = null;
        IMG_REFS = R.filter(Boolean).map(x => ({ kind: 'upload', data: x.data, url: x.data }));
        const ta = $('#ig-prompt'), p = isQ() ? q21ComboPrompt(c) : matsComboPrompt(c);
        if (ta && (!ta.value.trim() || ta.value === renderImg.comboP)) { ta.value = st.prompt = p; st.q21Pre = null; sessionStorage.setItem('igDraft', p); renderImg.comboP = p; ta.dispatchEvent(new Event('input')); toast('已放入图 1～图 ' + (IMG_REFS.length + 1) + '，并已填写修改指令'); }
        else toast('已放入图 1～图 ' + (IMG_REFS.length + 1) + '；修改指令框中已有内容，未作替换');
        save(); paintMode();
      } catch (e) { toast(e.message || '无法读取素材', true); }
  };
  renderImg.applySrc = async f => { try { loadUpload(await matsFile(f)); } catch (e) { toast(e.message, true); } };  // 素材库页面：作为生图原图
  if (window.GAL_TO_IMG) { const p = window.GAL_TO_IMG; window.GAL_TO_IMG = null; setTimeout(() => p.combo ? renderImg.applyCombo(p.combo) : renderImg.applySrc(p.src), 0); }  // 从素材库页面过来的
  renderImg.useSrc = (x, mode) => { st.mode = mode; save(); setSrcGallery(x); paintMode(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const imgData = file => new Promise((res, rej) => {  // 图片文件 → { data, w, h }（和上传一样：太大的缩到 2048 以内，别的格式转成 JPG）
    const fr = new FileReader();
    fr.onload = () => { const im = new Image(); im.onload = () => { let data = fr.result, w = im.naturalWidth, h = im.naturalHeight;
      if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) { const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height; }
      res({ data, w, h }); }; im.onerror = () => rej(new Error('无法打开此图片（仅支持 PNG / JPG / WebP）')); im.src = fr.result; };
    fr.onerror = () => rej(new Error('无法读取此图片')); fr.readAsDataURL(file);
  });
  const addRefFile = file => {  // 指令改图的参考图（图 2、图 3）：太大的先缩小
    if (IMG_REFS.length >= 2) return toast('最多 2 张参考图', true);
    const fr = new FileReader(), gen = VGEN;
    fr.onload = () => { const im = new Image(); im.onload = () => { if (gen !== VGEN) return; let data = fr.result; const w = im.naturalWidth, h = im.naturalHeight;
      if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) { const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .93); }
      IMG_REFS.push({ kind: 'upload', data, url: data }); paintSrc(); toast(`已作为图 ${IMG_REFS.length + 1}`); }; im.onerror = () => toast('无法打开此图片（仅支持 PNG / JPG / WebP）', true); im.src = fr.result; };
    fr.readAsDataURL(file);
  };
  const loadUpload = file => {
    const fr = new FileReader(), gen = VGEN;
    fr.onload = () => {
      if (gen !== VGEN || !$('#ig-src-f')) return;
      const im = new Image();
      im.onload = () => {
        let [w, h] = [im.naturalWidth, im.naturalHeight], data = fr.result;
        if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) {  // 太大的先缩小（引擎最大 2048）；别的格式转成 JPG
          const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k);
          c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height;
        }
        IMG_SRC = { kind: 'upload', data, url: data, w, h, name: file.name }; IMG_MASK = null; st.srcId = null; save(); paintMode();
      };
      im.onerror = () => toast('无法打开此图片（仅支持 PNG / JPG / WebP）', true);
      im.src = fr.result;
    };
    fr.readAsDataURL(file);
  };
  const bindMask = () => {  // 局部重画：在原图上涂抹；显示用半透明的红色，提交时换成黑底白色的遮罩（和原图一样大）
    // 要绑的是面板这次新画出来的那份（2026-11-16 用户：局部重画切到别的模型后涂不了）：大画面上可能还放着上一次搬过去的旧原图（同样的 id、排在前面），
    // 以前 $('#ig-src') 拿到的是那份旧的，下一帧大画面又换成这份新的——新的没绑过，点了没反应
    const box = $('#ig-src-f #ig-src') || $('#ig-src'), img = $('img', box), cv = $('canvas', box);
    if (!IMG_MASK || IMG_MASK.width !== IMG_SRC.w) { IMG_MASK = document.createElement('canvas'); IMG_MASK.width = IMG_SRC.w; IMG_MASK.height = IMG_SRC.h; const g = IMG_MASK.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, IMG_MASK.width, IMG_MASK.height); }
    let pen = 'draw', last = null, sp = 'draw';  // sp：这一笔实际用的（按住 Ctrl 时和 pen 相反）
    const tmp = document.createElement('canvas');
    // 撤销（2026-11-16 用户）：每一笔、每次清空之前存一份遮罩；Ctrl+Z 撤销、Ctrl+Shift+Z / Ctrl+Y 重做；画笔那一行有撤销按钮（手机用）。份数按图的大小算，总共约 120MB
    const H = IMG_MASK._h || (IMG_MASK._h = { u: [], r: [] }), HMAX = Math.max(3, Math.min(30, Math.floor(1.2e8 / (IMG_MASK.width * IMG_MASK.height * 4))));
    const grab = () => IMG_MASK.getContext('2d').getImageData(0, 0, IMG_MASK.width, IMG_MASK.height);
    const undoPaint = () => $$('[data-mundo]').forEach(b => { b.disabled = b.dataset.mundo === 'redo' ? !H.r.length : !H.u.length; });
    const snap = () => { H.u.push(grab()); if (H.u.length > HMAX) H.u.shift(); H.r = []; undoPaint(); };
    const hist = redo => { const from = redo ? H.r : H.u, to = redo ? H.u : H.r; if (!from.length) return false; to.push(grab()); IMG_MASK.getContext('2d').putImageData(from.pop(), 0, 0); showMask(); undoPaint(); return true; };
    renderImg.maskUndo = () => hist(false); renderImg.maskRedo = () => hist(true); renderImg.maskUndoPaint = () => undoPaint();
    renderImg.maskPenBar = () => penShow(pen);
    const penShow = p => { $$('#ig-pen button').forEach(x => x.classList.toggle('on', x.dataset.p === p)); $$('.ig-stage-mbar [data-a=draw], .ig-stage-mbar [data-a=erase]').forEach(x => x.classList.toggle('on', x.dataset.a === p)); };
    if (!window._igMaskKeys) { window._igMaskKeys = 1;  // 键盘：Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y（焦点在输入框里时归输入框自己的撤销）；按住 Ctrl 时画笔按钮显示成另一种
      const live = () => S.img?.mode === 'inpaint' && location.pathname === '/img' && document.querySelector('#ig-mask-c');
      addEventListener('keydown', e => {
        if (!live() || e.target.closest?.('input:not([type=range]), textarea, [contenteditable]')) return;
        const k = (e.key || '').toLowerCase();
        if ((e.ctrlKey || e.metaKey) && !e.altKey && (k === 'z' || k === 'y')) { e.preventDefault(); e.stopPropagation(); (k === 'y' || e.shiftKey ? renderImg.maskRedo : renderImg.maskUndo)?.(); return; }
        if ((e.key === 'Control' || e.key === 'Meta') && !e.repeat) renderImg.maskCtrl?.(true);
        if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.repeat && (k === 'w' || k === 'b' || k === 'e')) {  // W 智能选取、B 涂抹、E 擦除（2026-11-16 用户）
          e.preventDefault(); if (k === 'w') return renderImg.maskSmartToggle?.();
          document.querySelector(`#ig-pen [data-p="${k === 'b' ? 'draw' : 'erase'}"]`)?.click(); renderImg.maskPenBar?.(); }
      }, true);
      addEventListener('keyup', e => { if (e.key === 'Control' || e.key === 'Meta') renderImg.maskCtrl?.(false); });
      addEventListener('blur', () => renderImg.maskCtrl?.(false)); }
    renderImg.maskCtrl = on => penShow(on ? (pen === 'draw' ? 'erase' : 'draw') : pen);
    // 智能选取（2026-11-16 用户：手绘有时不准）：点一下，SAM3 选出那一整块，加进涂抹（擦除模式 / 按住 Ctrl = 去掉）。
    // 照 Photoshop「对象选择」、iPhone 相册「抠出主体」：工具条上一个开关，选完还能用画笔修；每次都能撤销
    const smartOn = () => !!S.ui?.igSmart;
    const smartPaint = () => { $$('[data-msmart]').forEach(b => { b.classList.toggle('on', smartOn()); b.setAttribute('aria-pressed', String(smartOn())); }); box.classList.toggle('smart', smartOn()); };
    renderImg.maskSmartPaint = smartPaint;
    let smartBusy = false, smartLast = null;  // 上一次点选：同一处再点一下 = 大一圈（衣服 → 整个人），中间没涂过别的才算
    const srcKey = () => IMG_SRC?.kind === 'gallery' ? 'g' + IMG_SRC.id : 'u' + (IMG_SRC._k || (IMG_SRC._k = Math.random().toString(36).slice(2, 10)));
    const srcData = () => { if (IMG_SRC?.kind === 'gallery') return { gallery: IMG_SRC.id };  // 上传的图：缩到最长边 1536 再传（SAM3 内部按 1008 算）
      const c = document.createElement('canvas'), k = Math.min(1, 1536 / Math.max(img.naturalWidth, img.naturalHeight)); c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); return { data: c.toDataURL('image/jpeg', .92) }; };
    const SP = window._igSamPrep || (window._igSamPrep = {});  // key → 'ok' / Promise（分析中）
    const smartPrep = () => {
      if (!smartOn() || !IMG_SRC || !img.naturalWidth) return null;
      const key = srcKey(); if (SP[key]) return SP[key] === 'ok' ? null : SP[key];
      SP[key] = (async () => { try { let r = await api('/api/img/sam', { body: { key, prep: true } }); if (r.need) r = await api('/api/img/sam', { body: { key, prep: true, image: srcData() } }); SP[key] = r.ok ? 'ok' : undefined; }
        catch { SP[key] = undefined; } })();
      return SP[key]; };
    renderImg.maskSmartPrep = smartPrep;
    const smartPick = async (nx, ny, mode, ex, ey) => {
      if (smartBusy) return; smartBusy = true;
      const r = box.getBoundingClientRect(), dot = document.createElement('span'); dot.className = 'ig-smart-dot';  // 点的地方一个转圈的小圆，表示正在选
      dot.style.left = (ex - r.left) + 'px'; dot.style.top = (ey - r.top) + 'px'; box.append(dot);
      const slow = setTimeout(() => toast('正在分析这张图（换图后第一次要几秒；ComfyUI 没开时约半分钟）…'), 3000);
      try {
        const pre = SP[srcKey()]; if (pre && pre !== 'ok') await pre;  // 放图时已经在分析：等它做完，不重复跑
        const key = srcKey(), L = smartLast, again = L && L.key === key && L.mode === mode && Math.hypot(L.x - nx, L.y - ny) < 0.015 && H.u.length === L.hl;
        if (again && L.level + 1 >= L.levels) { toast('已经是包含这一点的最大一块'); return; }
        const body = { key, x: nx, y: ny, level: again ? L.level + 1 : 0 };
        let res = await api('/api/img/sam', { body });
        if (res.need) res = await api('/api/img/sam', { body: { ...body, image: srcData() } });
                if (!res.mask || (res.area || 0) < 0.0005) { toast('这里没有选出东西，换个位置点'); return; }
        const m = new Image(); m.src = res.mask; await m.decode();
        if (again && (res.level || 0) <= L.level) { smartLast = { ...L, levels: L.level + 1 }; toast('已经是包含这一点的最大一块'); return; }
        if (again) hist(false);  // 放大一圈：先撤掉上一次选的那块
        snap();
        const W = IMG_MASK.width, Hh = IMG_MASK.height, g = IMG_MASK.getContext('2d');
        if (mode === 'draw') { g.save(); g.globalCompositeOperation = 'lighten'; g.drawImage(m, 0, 0, W, Hh); g.restore(); }  // 白的地方加进来，黑的地方不变
        else { const t = document.createElement('canvas'); t.width = W; t.height = Hh; const tg = t.getContext('2d');  // 去掉：选中的地方涂黑
          tg.drawImage(m, 0, 0, W, Hh); tg.globalCompositeOperation = 'difference'; tg.fillStyle = '#fff'; tg.fillRect(0, 0, W, Hh);
          g.save(); g.globalCompositeOperation = 'darken'; g.drawImage(t, 0, 0); g.restore(); }
        showMask();
        smartLast = { key, x: nx, y: ny, mode, level: res.level || 0, levels: res.levels || 1, hl: H.u.length };
      } catch (er) { toast(er.message || String(er), true); }
      finally { clearTimeout(slow); dot.remove(); smartBusy = false; }
    };
    // 缩放涂抹（2026-11-16 用户）：大图 / 放大涂抹里滚轮缩放，右栏小图里按住 Ctrl（或触控板双指捏合）再滚；放大后按住空格、鼠标右键或中键拖动移动画面。
    // 原图和画布一起 transform（框本身 overflow: hidden 裁掉）；画笔在屏幕上大小不变，放大后落在图上更细
    const Z = box._zm || (box._zm = { z: 1, x: 0, y: 0 });
    const zClamp = () => { const w = img.offsetWidth, h = img.offsetHeight; if (Z.z <= 1) { Z.z = 1; Z.x = Z.y = 0; return; } Z.x = Math.min(0, Math.max(w - w * Z.z, Z.x)); Z.y = Math.min(0, Math.max(h - h * Z.z, Z.y)); };
    const zApply = () => {
      zClamp(); const t = Z.z === 1 ? '' : `translate(${Z.x}px, ${Z.y}px) scale(${Z.z})`;
      [img, cv].forEach(el => { el.style.transformOrigin = '0 0'; el.style.transform = t; });
      { const w = img.offsetWidth, h = img.offsetHeight;  // 红色涂抹层按放大后的清晰度重画（否则放大后边缘一格一格的）；最多约 150 万像素，涂起来不卡
        if (w && IMG_MASK) { const k = Math.max(1, Math.min(Z.z * (devicePixelRatio || 1), IMG_MASK.width / w, Math.sqrt(1.5e6 / (w * h)))), bw = Math.round(w * k), bh = Math.round(h * k);
          if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; showMask(); } } }
      let b = $('.ig-zoom-b', box);
      if (Z.z === 1) { b?.remove(); return; }
      if (!b) { b = document.createElement('button'); b.type = 'button'; b.className = 'ig-zoom-b'; b.dataset.tip = '点击还原。滚轮缩放；按住空格、鼠标右键或中键拖动可移动画面';
        b.onpointerdown = e => e.stopPropagation(); b.onclick = e => { e.stopPropagation(); Z.z = 1; zApply(); }; box.append(b); }
      b.textContent = Math.round(Z.z * 100) + '%';
    };
    box.onwheel = e => {
      if (!box.classList.contains('stg') && !box.classList.contains('big') && !e.ctrlKey && !e.metaKey) return;  // 右栏小图：普通滚轮照常滚面板
      e.preventDefault();
      const r = box.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const nz = Math.min(8, Math.max(1, Z.z * Math.exp(-e.deltaY * (Math.abs(e.deltaY) >= 40 ? 0.0015 : 0.01))));  // 鼠标滚轮一格约 ×1.16；触控板捏合按小步算
      Z.x = px - (px - Z.x) / Z.z * nz; Z.y = py - (py - Z.y) / Z.z * nz; Z.z = nz; zApply();
    };
    if (!window._igSpace) { window._igSpace = { on: false };  // 按住空格 = 拖动画面（输入框里打空格不算）
      addEventListener('keydown', e => { if (e.code === 'Space' && !e.target.closest?.('input, textarea, [contenteditable]')) { if ($('.ig-zoom-b')) e.preventDefault(); window._igSpace.on = true; } });
      addEventListener('keyup', e => { if (e.code === 'Space') window._igSpace.on = false; }); addEventListener('blur', () => { window._igSpace.on = false; }); }
    cv.oncontextmenu = e => { if (Z.z > 1) e.preventDefault(); };
    const at = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; };  // 屏幕 → 画布坐标（算上缩放）
    let panAt = null;
    const paintAt = (x, y) => {
      const k = IMG_MASK.width / cv.width, r = (+$('#ig-brush').value) / 2 * IMG_MASK.width / ((img.offsetWidth || cv.width) * Z.z), g = IMG_MASK.getContext('2d');  // 画笔按屏幕上的大小
      g.strokeStyle = g.fillStyle = sp === 'draw' ? '#fff' : '#000'; g.lineWidth = r * 2; g.lineCap = 'round';
      g.beginPath(); if (last) { g.moveTo(last[0] * k, last[1] * k); g.lineTo(x * k, y * k); g.stroke(); } else { g.arc(x * k, y * k, r, 0, Math.PI * 2); g.fill(); }
      last = [x, y]; showMask();
    };
    const showMask = () => {  // 黑白遮罩 → 只把白色部分画成红色
      tmp.width = cv.width; tmp.height = cv.height;
      const t = tmp.getContext('2d'); t.drawImage(IMG_MASK, 0, 0, cv.width, cv.height);
      const d = t.getImageData(0, 0, cv.width, cv.height), p = d.data;
      let any = false; for (let n = 0; n < p.length; n += 4 * 13) if (p[n] > 127) { any = true; break; }
      for (let n = 0; n < p.length; n += 4) { const v = p[n]; if (v > 8 || !any) { p[n] = 255; p[n + 1] = 59; p[n + 2] = 107; p[n + 3] = v * .55; } else { p[n] = p[n + 1] = p[n + 2] = 0; p[n + 3] = 105; } }
      const g = cv.getContext('2d'); g.clearRect(0, 0, cv.width, cv.height); g.putImageData(d, 0, 0);
    };
    let pid = null, stroke = false;
    // 双指缩放（2026-11-16 用户：手机上涂抹要能两指放大缩小）：第二根手指落下就改成缩放 / 移动画面，第一根手指刚涂的那一笔撤掉；
    // 两指之间的那一点跟着手指走（同时能拖动画面）；松开到全部手指离开之前不再涂
    const T = new Map(); let pin = null, hold = false;
    const pinMid = () => { const [a, b] = [...T.values()], r = box.getBoundingClientRect(); return { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, x: (a[0] + b[0]) / 2 - r.left, y: (a[1] + b[1]) / 2 - r.top }; };
    const pinStart = () => {
      if (pid !== null && stroke && H.u.length) { IMG_MASK.getContext('2d').putImageData(H.u.pop(), 0, 0); showMask(); undoPaint(); }  // 撤掉第一根手指刚涂的
      if (pid !== null) { try { cv.releasePointerCapture(pid); } catch { } } pid = null; last = null; stroke = false; panAt = null;
      const m = pinMid(); pin = { d: m.d, z: Z.z, cx: (m.x - Z.x) / Z.z, cy: (m.y - Z.y) / Z.z };
    };
    const pinMove = () => { const m = pinMid(); Z.z = Math.min(8, Math.max(1, pin.z * m.d / pin.d)); Z.x = m.x - pin.cx * Z.z; Z.y = m.y - pin.cy * Z.z; zApply(); };
    { cv._pinOff?.();  // 同一块画布重新绑定（换模型等）：先去掉上一次的，免得两套一起算
      const dn = e => { if (e.pointerType !== 'touch') return; T.set(e.pointerId, [e.clientX, e.clientY]); if (T.size === 2) pinStart(); };
      const mv = e => { if (T.has(e.pointerId)) T.set(e.pointerId, [e.clientX, e.clientY]); if (pin && T.size >= 2) pinMove(); };
      const up = e => { if (!T.delete(e.pointerId)) return; if (pin && T.size < 2) { pin = null; hold = true; } if (!T.size) hold = false; };
      const L = [['pointerdown', dn], ['pointermove', mv], ['pointerup', up], ['pointercancel', up]];
      L.forEach(([n, f]) => cv.addEventListener(n, f, true)); cv._pinOff = () => L.forEach(([n, f]) => cv.removeEventListener(n, f, true)); }
    cv.onpointerdown = e => { e.preventDefault(); if (pin || hold || T.size > 1) return; if (pid !== null) return; pid = e.pointerId; cv.setPointerCapture(e.pointerId); last = null; stroke = false;
      if (Z.z > 1 && (e.button === 1 || e.button === 2 || window._igSpace?.on)) { panAt = [e.clientX - Z.x, e.clientY - Z.y]; cv.style.cursor = 'grabbing'; return; }  // 拖动画面
      sp = (e.ctrlKey || e.metaKey) ? (pen === 'draw' ? 'erase' : 'draw') : pen;  // 按住 Ctrl 点：涂抹 ⇄ 擦除，松开就回来（2026-11-16 用户）
      if (smartOn()) { const [px, py] = at(e); pid = null; try { cv.releasePointerCapture(e.pointerId); } catch { } smartPick(px / cv.width, py / cv.height, sp, e.clientX, e.clientY); return; }
      snap(); stroke = true; paintAt(...at(e)); };
    cv.onpointermove = e => { if (e.pointerId !== pid || pin) return; if (panAt) { Z.x = e.clientX - panAt[0]; Z.y = e.clientY - panAt[1]; zApply(); return; } paintAt(...at(e)); };
    cv.onpointerup = cv.onpointercancel = e => { if (e.pointerId === pid) { pid = null; last = null; if (panAt) { panAt = null; cv.style.cursor = ''; } } };
    $$('#ig-pen button').forEach(b => b.onclick = () => { pen = b.dataset.p; penShow(pen); });
    $$('[data-mundo]').forEach(b => b.onclick = e => { e.stopPropagation(); hist(b.dataset.mundo === 'redo'); }); undoPaint();
    renderImg.maskSmartToggle = () => { S.ui = { ...(S.ui || {}), igSmart: !smartOn() }; persist(); smartPaint(); if (smartOn()) smartPrep(); };
    $$('[data-msmart]').forEach(b => b.onclick = e => { e.stopPropagation(); renderImg.maskSmartToggle(); }); smartPaint();
    $('#ig-brush').oninput = e => { S.ui = { ...(S.ui || {}), igBrush: +e.target.value }; };
    $('#ig-mgrow').oninput = e => { st.maskGrow = +e.target.value; $('#ig-mgrow-v').textContent = e.target.value + 'px'; persistSoon(); };
    $('#ig-mfea').oninput = e => { st.maskFeather = +e.target.value; $('#ig-mfea-v').textContent = e.target.value + 'px'; persistSoon(); };
    if ($('#ig-crop')) $('#ig-crop').onchange = e => { st.inpaintCrop = e.target.checked; persist(); };
    $('#ig-mask-big').onclick = () => {  // 放大涂抹：把原图（连同画布）搬到最上层铺满窗口，涂完点“完成”放回原处；涂抹的结果直接就是遮罩
      let ov = $('#ig-mask-ov');
      if (ov) { const ph = $('#ig-src-ph'); if (ph) ph.replaceWith(box); box.classList.remove('big'); ov.remove(); $('#ig-mask-big').textContent = '放大涂抹'; return; }
      ov = document.createElement('div'); ov.id = 'ig-mask-ov'; ov.className = 'ig-mask-ov';
      const ph = document.createElement('div'); ph.id = 'ig-src-ph'; box.before(ph);
      ov.innerHTML = `<div class="ig-mask-bar"><span class="tiny">画笔</span><input type="range" min="4" max="100" value="${$('#ig-brush').value}" data-a="size">
        <button type="button" class="btn small" data-a="pen">${pen === 'erase' ? '涂抹' : '擦除'}</button><button type="button" class="pl-ib ig-smart" data-msmart aria-pressed="false" aria-label="智能选取" data-tip="智能选取（W）：在图上点一下要改的东西，自动选出它的轮廓（点衣服只选衣服）；同一处再点一下选大一圈（整个人）。擦除模式或按住 Ctrl 点 = 去掉那一块；选完可以接着用画笔修"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m4 20 10.5-10.5"/><path d="m13 8 3 3"/><path d="M18 3v3M16.5 4.5h3M20 9v2M19 10h2M10 3v2M9 4h2"/></svg></button><button type="button" class="pl-ib ig-mundo" data-mundo="undo" aria-label="撤销" data-tip="撤销（Ctrl+Z）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button><button type="button" class="btn small" data-a="clear">清空</button><button type="button" class="btn small grad" data-a="done">完成</button></div>`;
      ov.prepend(box); box.classList.add('big'); document.body.append(ov); $('#ig-mask-big').textContent = '完成';
      ov.addEventListener('click', e => e.stopPropagation());  // 别让页面把原图面板当成“点了外面”收起来
      ov.querySelector('[data-a=size]').oninput = e => { $('#ig-brush').value = e.target.value; $('#ig-brush').oninput?.({ target: $('#ig-brush') }); };
      undoPaint();
      smartPaint();
      ov.querySelector('.ig-mask-bar').onclick = e => { if (e.target.closest('[data-mundo]')) return hist(false); if (e.target.closest('[data-msmart]')) return renderImg.maskSmartToggle(); const a = e.target.closest('button')?.dataset.a;
        if (a === 'done') $('#ig-mask-big').click(); else if (a === 'clear') $('#ig-mask-x').click();
        else if (a === 'pen') { pen = pen === 'erase' ? 'draw' : 'erase'; e.target.textContent = pen === 'erase' ? '涂抹' : '擦除'; $$('#ig-pen button').forEach(x => x.classList.toggle('on', x.dataset.p === pen)); } };
      const esc = e => { if (e.key !== 'Escape' || !ov.isConnected) return document.removeEventListener('keydown', esc, true); e.stopPropagation(); $('#ig-mask-big').click(); };
      document.addEventListener('keydown', esc, true);
    };
    $('#ig-mask-x').onclick = () => { snap(); const g = IMG_MASK.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, IMG_MASK.width, IMG_MASK.height); showMask(); };  // 清空也能撤销
    const go2 = () => { if (!img.offsetWidth) return; cv.width = 0; zApply(); smartPrep(); };  // 画布清晰度由 zApply 按排版尺寸（不含缩放）和放大倍数定，并重画
    if (img.complete) go2(); else img.onload = go2;
    renderImg.ro?.disconnect(); renderImg.ro = new ResizeObserver(() => { if (!cv.isConnected) return renderImg.ro?.disconnect(); go2(); }); renderImg.ro.observe(img);
  };
  // ---- 尺寸：文生图选比例；图生图 / 局部重画跟原图一样
  const paintSize = () => {
    const f = $('#ig-size-f'); if (!f) return;
    f.closest('.ig-panel')?.classList.toggle('ig-row1', st.mode !== 'txt');
    if (st.mode === 'edit') {  // 指令改图：默认和图 1 一致，也可以选比例（Qwen 2.1 按比例出约 300 万像素；v23 按所选尺寸）或自定义宽高
      const q = isQ(), es = st.eSize || 'src', [w0, h0] = IMG_SRC ? imgSize16(IMG_SRC.w, IMG_SRC.h) : [0, 0];
      const cw = st.ecw || 1024, ch = st.ech || 1024;
      f.innerHTML = `<span class="label">尺寸${hintHtml('默认与图 1（要改的图）的宽高比一致。以姿势线稿或别的图为参考、想要另一种比例时，在这里选。' + (q ? 'Qwen 2.1 按所选比例出约 300 万像素的图。' : ''), 'sm')}</span>
        <div class="row ig-esz"><select class="select" id="ig-esize" aria-label="出图尺寸"><option value="src"${es === 'src' ? ' selected' : ''}>与图 1 一致${q ? '（宽高比）' : w0 ? `（${w0} × ${h0}）` : ''}</option>${IMG_SIZES.map(([k, n, w, h]) => `<option value="${k}"${es === k ? ' selected' : ''}>${k} ${n}${q ? '' : `（${w} × ${h}）`}</option>`).join('')}<option value="custom"${es === 'custom' ? ' selected' : ''}>自定义</option></select></div>
        <div class="row ig-csize"${es === 'custom' ? '' : ' hidden'}><input class="input" id="ig-ecw" type="number" min="512" max="2048" step="16" value="${cw}" aria-label="宽"><span class="tiny">×</span><input class="input" id="ig-ech" type="number" min="512" max="2048" step="16" value="${ch}" aria-label="高"><span class="tiny">${q ? '只取比例' : '像素'}</span></div>`;
      $('#ig-esize', f).onchange = e => { st.eSize = e.target.value; save(); $('.ig-csize', f).hidden = st.eSize !== 'custom'; igRefresh?.(); requestAnimationFrame(igSrcFit); };
      const fixE = (el, k) => { const v = Math.max(512, Math.min(2048, Math.round((+el.value || 1024) / 16) * 16)); el.value = v; st[k] = v; save(); };
      $('#ig-ecw', f).onchange = e => fixE(e.target, 'ecw'); $('#ig-ech', f).onchange = e => fixE(e.target, 'ech');
      return;
    }
    if (st.mode !== 'txt' && isQ()) { f.innerHTML = `<span class="label">尺寸</span><div class="tiny">与原图一致</div>`; return; }
    if (st.mode !== 'txt') { const [w, h] = IMG_SRC ? imgSize16(IMG_SRC.w, IMG_SRC.h) : [0, 0]; f.innerHTML = `<span class="label">尺寸</span><div class="tiny">${IMG_SRC ? `与原图一致：${w} × ${h}` : '与原图一致'}</div>`; return; }
    const cw = st.cw || 1024, ch = st.ch || 1024;  // 自定义宽高（512~2048，16 的倍数）
    f.innerHTML = `<span class="label">尺寸${/^q21/.test(st.model) ? hintHtml('Qwen 2.1 按所选宽高比出约 200 万像素的图。', 'sm') : st.model === 'h3img' ? hintHtml('H3-Image 按所选宽高比出约 415 万像素的图（模型按 2048×2048 的面积调校）。', 'sm') : ''}</span><div class="seg full ig-size" id="ig-size">${IMG_SIZES.map(([k, n, w, h]) => `<button type="button" data-k="${k}" class="${st.size === k ? 'on' : ''}" title="${n} · ${w} × ${h}"><i class="ar" style="aspect-ratio:${w}/${h}"></i><span>${k}</span></button>`).join('')}
      <button type="button" data-k="custom" class="${st.size === 'custom' ? 'on' : ''}" title="自定义宽高"><i class="ar ar-c"></i><span>自定义</span></button></div>
      <div class="row ig-csize"${st.size === 'custom' ? '' : ' hidden'}><input class="input" id="ig-cw" type="number" min="512" max="2048" step="16" value="${cw}" aria-label="宽"><span class="tiny">×</span><input class="input" id="ig-ch" type="number" min="512" max="2048" step="16" value="${ch}" aria-label="高"><span class="tiny">像素</span></div>`;
    $$('#ig-size [data-k]').forEach(b => b.onclick = () => { st.size = b.dataset.k; save(); $$('#ig-size button').forEach(x => x.classList.toggle('on', x === b)); $('.ig-csize', f).hidden = st.size !== 'custom'; });
    const fixC = (el, k) => { const v = Math.max(512, Math.min(2048, Math.round((+el.value || 1024) / 16) * 16)); el.value = v; st[k] = v; save(); };
    $('#ig-cw', f).onchange = e => fixC(e.target, 'cw'); $('#ig-ch', f).onchange = e => fixC(e.target, 'ch');
  };
  // ---- 高级参数：引擎能调的都在这里
  const opt = (list, cur, dflt = '默认（模型自带）') => `<option value="">${dflt}</option>` + list.map(v => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const paintAdv = () => {
    const D = imgDefaults(), hr = { ...D.hires, ...(st.hires || {}) }, C = IMGST.caps || {};
    const F = (C.features_by_model || {})[st.model] || null;  // 引擎报的功能开关（载入过这个模型才知道）；不知道时按支持处理，蒸馏引导除外
    const has = k => !F || F[k] !== false;
    const apg = { ...D.apg, ...(st.apg || {}) }, slg = { ...D.slg, ...(st.slg || {}) }, vt = { ...D.vaeTile, ...(st.vaeTile || {}) };
    const changed = imgAdvChg().length;  // 按钮上的数字 = 改过的项数，和弹窗里的蓝点是同一份（11-23 用户：开了二采，数字闪一下就没了——以前这里另算一遍、漏了二采）
    const advN = $('#ig-adv-n'); if (!advN) return;  // 已经切到别的页面（晚到的刷新）
    advN.textContent = changed ? String(changed) : ''; advN.title = changed ? `已修改 ${changed} 项` : '';
    if (!$('#ig-adv-body')) return;  // 弹窗没开：只更新按钮上的数字
    requestAnimationFrame(() => advMark($('#ig-adv-body'), imgAdvChg()));  // 画完再标（下面还会把一些项挪进“更多参数”）
    if (isQ()) return paintAdvQ();
    const dtl = st.detail = { ...IMG_DT0, ...(st.detail || {}) };
    const nin = (id, v, ph, min, max, step) => `<input class="input" id="${id}" type="number" step="${step}" min="${min}" max="${max}" placeholder="${ph}" value="${esc(v ?? '')}">`;
    $('#ig-adv-body').innerHTML = `<div class="ig-cols"><div class="ig-col">
      <div class="ig-sec">采样</div>
      <div class="field"><span class="label">步数：<span id="ig-steps-v">${st.steps}</span></span><input type="range" id="ig-steps" min="1" max="50" step="1" value="${st.steps}"></div>
      <div class="field"><span class="label">CFG：<span id="ig-cfg-v">${(+st.cfg).toFixed(1)}</span>${hintHtml('Turbo 模型使用 1。调到 1 以上负面提示词才会生效，但速度减半且容易过曝。', 'sm')}</span><input type="range" id="ig-cfg" min="0" max="10" step="0.1" value="${st.cfg}"></div>
      <div class="ig-2"><label class="field"><span class="label">采样器</span><select class="select" id="ig-sampler">${opt(C.samplers || [], st.sampler)}</select></label>
        <label class="field"><span class="label">调度器</span><select class="select" id="ig-scheduler">${opt(C.schedulers || [], st.scheduler)}</select></label></div>
      <div class="field"><span class="label">种子${hintHtml('相同的种子、提示词和参数会生成相同的图片。如需在满意的图片上微调，请固定种子；点击骰子可恢复随机。生成多张时种子依次 +1。', 'sm')}</span>
        <div class="row" style="gap:6px"><input class="input" id="ig-seed" type="number" min="0" placeholder="随机" value="${st.seed >= 0 ? st.seed : ''}" style="flex:1;min-width:0"><button type="button" class="btn icon-btn" id="ig-dice" title="随机种子" aria-label="随机种子">${IMG_IC.dice}</button></div></div>
      <div class="ig-2" id="ig-beta"${st.scheduler === 'beta' ? '' : ' hidden'}><label class="field"><span class="label">Beta α${hintHtml('beta 调度器的形状参数。留空表示使用引擎默认值；ComfyUI 默认为 0.6。', 'sm')}</span>${nin('ig-ba', st.betaA, '默认', 0.1, 2, 0.05)}</label>
        <label class="field"><span class="label">Beta β</span>${nin('ig-bb', st.betaB, '默认', 0.1, 2, 0.05)}</label></div>
      <div class="ig-2"><label class="field"><span class="label">Flow shift${hintHtml('流匹配模型的时间偏移。留空表示使用模型默认值（Z-Image 约为 3）；调大可使构图更稳定，但细节略少。', 'sm')}</span>${nin('ig-shift', st.flowShift, '自动', 0, 20, 0.1)}</label>
        <label class="field"><span class="label">Eta${hintHtml('仅对带随机噪声的采样器（名称含 _a、sde）有效。留空表示默认。', 'sm')}</span>${nin('ig-eta', st.eta, '自动', 0, 2, 0.05)}</label></div>
      <div class="ig-2"><label class="field"><span class="label">噪声采样${hintHtml('仅对带随机噪声的采样器有效。brownian_tree 与 ComfyUI 的 dpm++ sde 系列一致。', 'sm')}</span><select class="select" id="ig-noise">${opt(C.noise_samplers || ['iid', 'brownian_tree'], st.noiseSampler, '默认')}</select></label>
        <div class="field"><span class="label">随机数${hintHtml('选择“ComfyUI”后，相同的种子和参数将与 ComfyUI 生成相同的图片。切换后生图引擎将重启。', 'sm')}</span><div class="seg full" id="ig-rng">${[['cuda', '默认'], ['cpu', 'ComfyUI']].map(([k, n]) => `<button type="button" data-r="${k}" class="${(st.rng || 'cuda') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>
      <div class="field"><span class="label">排除内容（负面提示词）${hintHtml('CFG 大于 1 时才生效。', 'sm')}</span><textarea class="textarea" id="ig-neg" rows="2" placeholder="例如：模糊，畸形的手，多余的手指，水印，文字">${esc(st.negative)}</textarea></div>
      <label class="field"><span class="label">其他采样参数${hintHtml('直接传给引擎的 key=value，以逗号分隔，例如 gamma=0.5（euler_ge）、slg_uncond=true。', 'sm')}</span><input class="input" id="ig-extra" placeholder="key=value, key=value" value="${esc(st.extraArgs || '')}"></label>
    </div><div class="ig-col">
      <div class="ig-sec">引导${has('slg') ? hintHtml('跳层引导（SLG）：改善结构和肢体，仅对 DiT 模型有效。0 表示关闭，常用 1~3；速度会略慢。', 'sm') : ''}</div>
      <div id="ig-apg-b"${+st.cfg > 1 ? '' : ' hidden'}><label class="row ig-check"><input type="checkbox" id="ig-apg"${apg.enabled ? ' checked' : ''}> APG 自适应投影引导${hintHtml('CFG 大于 1 时减轻过曝和过饱和，同 ComfyUI 的 APG 节点。', 'sm')}</label>
        <div class="ig-3" id="ig-apg-o"${apg.enabled ? '' : ' hidden'}><label class="field"><span class="label">Eta</span>${nin('ig-apg-eta', apg.eta, '1', 0, 1, 0.05)}</label><label class="field"><span class="label">动量</span>${nin('ig-apg-m', apg.momentum, '0', -1, 1, 0.05)}</label><label class="field"><span class="label">范数阈值</span>${nin('ig-apg-n', apg.norm_threshold, '5', 0, 50, 0.5)}</label></div></div>
      ${has('slg') ? `<div class="ig-4"><label class="field"><span class="label">跳层引导</span>${nin('ig-slg', slg.scale, '0', 0, 5, 0.1)}</label>
        <label class="field"><span class="label">跳过的层</span><input class="input" id="ig-slg-l" placeholder="7,8,9" value="${esc(Array.isArray(slg.layers) ? slg.layers.join(',') : slg.layers)}"></label>
        <label class="field"><span class="label">开始</span>${nin('ig-slg-s', slg.start, '0.01', 0, 1, 0.01)}</label><label class="field"><span class="label">结束</span>${nin('ig-slg-e', slg.end, '0.2', 0, 1, 0.01)}</label></div>` : ''}
      ${F?.distilled_guidance ? `<div class="ig-2"><label class="field"><span class="label">蒸馏引导${hintHtml('模型自带的 guidance 输入。留空表示默认 3.5。', 'sm')}</span>${nin('ig-dg', st.guidance, '3.5', 0, 10, 0.1)}</label></div>` : ''}
      <div class="ig-sec">高清修复${hintHtml('先按原尺寸绘制，再放大并重绘细节（速度稍慢）。', 'sm')}<label class="switch ig-sw"><input type="checkbox" id="ig-hr"${hr.enabled ? ' checked' : ''}><span></span></label></div>
      <div id="ig-hr-b"${hr.enabled ? '' : ' hidden'}>
        <div class="ig-2"><label class="field"><span class="label">放大方式</span><select class="select" id="ig-hr-up">${(C.upscalers || ['Latent']).map(v => `<option${v === hr.upscaler ? ' selected' : ''}>${esc(v)}</option>`).join('')}</select></label>
          <label class="field"><span class="label">第二遍步数</span><input class="input" id="ig-hr-steps" type="number" min="0" max="60" value="${hr.steps}" placeholder="0 = 同上"></label></div>
        <div class="field"><span class="label">放大到</span><div class="row ig-hr-to"><div class="seg" id="ig-hr-by">${[['scale', '按倍数'], ['size', '按尺寸']].map(([k, n]) => `<button type="button" data-b="${k}" class="${(hr.by || 'scale') === k ? 'on' : ''}">${n}</button>`).join('')}</div>
          <span id="ig-hr-sc"${hr.by === 'size' ? ' hidden' : ''} class="row ig-hr-sc"><input type="range" id="ig-hr-scale" min="1" max="3" step="0.05" value="${hr.scale}"><b id="ig-hr-scale-v">${hr.scale}×</b></span>
          <span id="ig-hr-sz"${hr.by === 'size' ? '' : ' hidden'} class="row ig-csize"><input class="input" id="ig-hr-tw" type="number" min="512" max="4096" step="16" value="${hr.target_width || 2048}" aria-label="宽"><span class="tiny">×</span><input class="input" id="ig-hr-th" type="number" min="512" max="4096" step="16" value="${hr.target_height || 2048}" aria-label="高"></span></div></div>
        <div class="field"><span class="label">重画力度：<span id="ig-hr-dn-v">${Math.round(hr.denoise * 100)}%</span></span><input type="range" id="ig-hr-dn" min="1" max="100" value="${Math.round(hr.denoise * 100)}"></div>
      </div>
      <div class="ig-sec">自动细化${hintHtml('生成后自动识别脸、手，逐处放大后以较低的重画力度重绘再贴回：五官、手指、皮肤细节更清晰，长相和姿势不变，框外像素完全不变。全身照中的小脸提升最明显；本身较大的脸会自动跳过。每处约多耗时数秒。原图会保留，可在详情中对比。', 'sm')}<label class="switch ig-sw"><input type="checkbox" id="ig-dt"${dtl.on ? ' checked' : ''}><span></span></label></div>
      <div id="ig-dt-b"${dtl.on ? '' : ' hidden'}>
        <div class="seg full" id="ig-dt-k">${[['face', '脸'], ['hand', '手']].map(([k, n]) => `<button type="button" data-k="${k}" class="${dtl[k] ? 'on' : ''}"${C.detail && C.detail[k] === false ? ' disabled title="缺少识别模型"' : ''}>${n}</button>`).join('')}</div>
        <div class="ig-2" style="margin-top:8px"><div class="field"><span class="label">脸的重画力度：<span id="ig-dt-s-v">${Math.round(dtl.strength * 100)}%</span>${hintHtml('30%~40% 仅补充细节；更高时五官会开始变形。', 'sm')}</span><input type="range" id="ig-dt-s" min="10" max="70" value="${Math.round(dtl.strength * 100)}"></div>
          <div class="field"><span class="label">手的重画力度：<span id="ig-dt-s2-v">${Math.round(dtl.strength2 * 100)}%</span>${hintHtml('手指画错时需调到 50% 左右才能修正。', 'sm')}</span><input type="range" id="ig-dt-s2" min="10" max="70" value="${Math.round(dtl.strength2 * 100)}"></div></div>
        <label class="field"><span class="label">细化提示词${hintHtml('留空表示使用原提示词。也可单独填写，例如“精致的五官，清晰的眼睛，自然的皮肤纹理”。', 'sm')}</span><input class="input" id="ig-dt-p" placeholder="留空则使用上方的提示词" value="${esc(dtl.prompt || '')}"></label>
      </div>
      <div id="ig-fx-w"${ms.find(x => x.key === st.model)?.edit ? '' : ' hidden'}><div class="ig-sec">改图后处理${hintHtml('仅用于指令改图，默认关闭。保留原脸：把原图的脸对齐后贴回，并把新露出的皮肤校正为和原图的脸一致的色调（适合换衣）。按参考脸修脸：把脸部裁出放大，照着图 2 或图 3 的脸重画后贴回，全身照中的脸更像参考脸（适合角色组合）。每张多耗时约 15~40 秒，原图会保留，可在详情中对比。', 'sm')}</div>
        <div class="seg full" id="ig-fx">${[['', '关'], ['keep', '保留原脸'], ['f0', '按图 2 修脸'], ['f1', '按图 3 修脸']].map(([k, n]) => `<button type="button" data-k="${k}" class="${(st.editFix || '') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
      <div class="ig-sec">LoRA${hintHtml(`将此模型的 LoRA 文件放入 ${(C.lora_dirs || {})[st.model] || 'models\\Z-Image\\loras'}，刷新页面后即可选择。`, 'sm')}</div>
      <div id="ig-loras"></div>
      <div class="ig-sec">速度和显存</div>
      <label class="row ig-check"><input type="checkbox" id="ig-vt"${st.vaeTiling ? ' checked' : ''}> VAE 分块${hintHtml('大图显存不足时开启（稍慢）。块越小越节省显存，重叠越大接缝越少。', 'sm')}</label>
      <div class="ig-2" id="ig-vt-o"${st.vaeTiling ? '' : ' hidden'}><label class="field"><span class="label">块大小</span><select class="select" id="ig-vt-s">${[128, 192, 256, 320, 384, 512, 640, 768, 1024].map(n => `<option value="${n}"${+vt.size === n ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
        <label class="field"><span class="label">重叠</span>${nin('ig-vt-o2', vt.overlap, '0.5', 0, 0.9, 0.05)}</label></div>
      <label class="row ig-check"><input type="checkbox" id="ig-sage"${st.sage ? ' checked' : ''}> SageAttention${hintHtml('扩散模型使用 SageAttention 注意力，通常更快；不支持时自动回退。切换后生图引擎将重启。', 'sm')}</label>
      <div class="ig-2"><label class="field"><span class="label">加速缓存${hintHtml('跳过相邻步之间变化很小的计算，提速 30%~2 倍，画质略有下降。easycache 最稳定。', 'sm')}</span><select class="select" id="ig-cache">${opt(C.cache_modes || [], st.cacheMode, '不使用')}</select></label>
        <label class="field"><span class="label">缓存参数</span><input class="input" id="ig-cache-o" placeholder="例如 threshold=0.2" value="${esc(st.cacheOption)}"></label></div>
      <div class="ig-sec">输出</div>
      <div class="ig-2"><div class="field"><span class="label">格式</span><div class="seg full" id="ig-fmt">${(C.formats || ['png', 'jpeg', 'webp']).map(f => `<button type="button" data-f="${f}" class="${st.format === f ? 'on' : ''}">${f.toUpperCase()}</button>`).join('')}</div></div>
        <div class="field" id="ig-q-f"${st.format === 'png' ? ' hidden' : ''}><span class="label">质量：<span id="ig-q-v">${st.quality}</span></span><input type="range" id="ig-q" min="50" max="100" value="${st.quality}"></div></div>
      <label class="row ig-check"><input type="checkbox" id="ig-meta"${st.meta ? ' checked' : ''}> 将提示词和参数写入图片文件</label>
      <div class="row" style="justify-content:flex-end;margin-top:6px"><button type="button" class="btn small ghost" id="ig-reset">全部恢复默认</button></div>
    </div></div>`;
    const num = (id, key, after) => { const el = $('#' + id); if (!el) return; el.oninput = () => { st[key] = el.type === 'range' ? +el.value : el.value; after?.(el.value); persistSoon(); paintAdvN(); }; };
    const sub = (id, key, k, parse = v => v) => { const el = $('#' + id); if (!el) return; el.oninput = () => { st[key] = { ...D[key], ...(st[key] || {}), [k]: parse(el.value) }; persistSoon(); paintAdvN(); }; };
    num('ig-steps', 'steps', v => $('#ig-steps-v').textContent = v);
    num('ig-cfg', 'cfg', v => { $('#ig-cfg-v').textContent = (+v).toFixed(1); $('#ig-apg-b').hidden = !(+v > 1); });
    $('#ig-sampler').onchange = e => { st.sampler = e.target.value; save(); paintAdvN(); };
    $('#ig-scheduler').onchange = e => { st.scheduler = e.target.value; $('#ig-beta').hidden = st.scheduler !== 'beta'; save(); paintAdvN(); };
    $('#ig-seed').oninput = e => { const v = e.target.value.trim(); st.seed = v === '' ? -1 : Math.max(0, parseInt(v) || 0); persistSoon(); paintAdvN(); };
    $('#ig-dice').onclick = () => { st.seed = -1; $('#ig-seed').value = ''; save(); paintAdvN(); };
    num('ig-shift', 'flowShift'); num('ig-eta', 'eta'); num('ig-neg', 'negative'); num('ig-cache-o', 'cacheOption');
    num('ig-ba', 'betaA'); num('ig-bb', 'betaB'); num('ig-extra', 'extraArgs'); num('ig-dg', 'guidance');
    $('#ig-noise').onchange = e => { st.noiseSampler = e.target.value; save(); paintAdvN(); };
    $$('#ig-rng button').forEach(b => b.onclick = () => { st.rng = b.dataset.r; save(); $$('#ig-rng button').forEach(x => x.classList.toggle('on', x === b)); paintAdvN(); });
    $('#ig-apg').onchange = e => { st.apg = { ...apg, ...(st.apg || {}), enabled: e.target.checked }; $('#ig-apg-o').hidden = !e.target.checked; save(); paintAdvN(); };
    sub('ig-apg-eta', 'apg', 'eta', Number); sub('ig-apg-m', 'apg', 'momentum', Number); sub('ig-apg-n', 'apg', 'norm_threshold', Number);
    sub('ig-slg', 'slg', 'scale', v => +v || 0); sub('ig-slg-l', 'slg', 'layers'); sub('ig-slg-s', 'slg', 'start', Number); sub('ig-slg-e', 'slg', 'end', Number);
    $('#ig-cache').onchange = e => { st.cacheMode = e.target.value; save(); paintAdvN(); };
    $('#ig-vt').onchange = e => { st.vaeTiling = e.target.checked; $('#ig-vt-o').hidden = !e.target.checked; save(); paintAdvN(); };
    $('#ig-vt-s').onchange = e => { st.vaeTile = { ...vt, ...(st.vaeTile || {}), size: +e.target.value }; save(); };
    sub('ig-vt-o2', 'vaeTile', 'overlap', Number);
    $('#ig-sage').onchange = e => { st.sage = e.target.checked; save(); paintAdvN(); };
    $('#ig-meta').onchange = e => { st.meta = e.target.checked; save(); paintAdvN(); };
    $('#ig-hr').onchange = e => { st.hires = { ...hr, ...(st.hires || {}), enabled: e.target.checked }; $('#ig-hr-b').hidden = !e.target.checked; save(); paintAdvN(); };
    const hrSet = (k, v) => { st.hires = { ...hr, ...(st.hires || {}), [k]: v }; save(); };
    $('#ig-hr-up').onchange = e => hrSet('upscaler', e.target.value);
    $('#ig-hr-steps').oninput = e => hrSet('steps', +e.target.value || 0);
    $('#ig-hr-scale').oninput = e => { hrSet('scale', +e.target.value); $('#ig-hr-scale-v').textContent = e.target.value + '×'; };
    $$('#ig-hr-by button').forEach(b => b.onclick = () => { hrSet('by', b.dataset.b); $$('#ig-hr-by button').forEach(x => x.classList.toggle('on', x === b)); $('#ig-hr-sc').hidden = b.dataset.b === 'size'; $('#ig-hr-sz').hidden = b.dataset.b !== 'size'; });
    const fixT = (el, k) => { const v = Math.max(512, Math.min(4096, Math.round((+el.value || 2048) / 16) * 16)); el.value = v; hrSet(k, v); };
    $('#ig-hr-tw').onchange = e => fixT(e.target, 'target_width'); $('#ig-hr-th').onchange = e => fixT(e.target, 'target_height');
    $('#ig-hr-dn').oninput = e => { hrSet('denoise', +e.target.value / 100); $('#ig-hr-dn-v').textContent = e.target.value + '%'; };
    $$('#ig-fmt button').forEach(b => b.onclick = () => { st.format = b.dataset.f; save(); $$('#ig-fmt button').forEach(x => x.classList.toggle('on', x === b)); $('#ig-q-f').hidden = st.format === 'png'; paintAdvN(); });
    $('#ig-q').oninput = e => { st.quality = +e.target.value; $('#ig-q-v').textContent = e.target.value; persistSoon(); };
    $('#ig-dt').onchange = e => { dtl.on = e.target.checked; $('#ig-dt-b').hidden = !dtl.on; save(); paintAdvN(); };
    $$('#ig-fx button').forEach(b => b.onclick = () => { st.editFix = b.dataset.k; $$('#ig-fx button').forEach(x => x.classList.toggle('on', x === b)); save(); });
    $$('#ig-dt-k button').forEach(b => b.onclick = () => { dtl[b.dataset.k] = !dtl[b.dataset.k]; b.classList.toggle('on', dtl[b.dataset.k]); save(); });
    $('#ig-dt-s').oninput = e => { dtl.strength = +e.target.value / 100; $('#ig-dt-s-v').textContent = e.target.value + '%'; persistSoon(); };
    $('#ig-dt-s2').oninput = e => { dtl.strength2 = +e.target.value / 100; $('#ig-dt-s2-v').textContent = e.target.value + '%'; persistSoon(); };
    $('#ig-dt-p').oninput = e => { dtl.prompt = e.target.value; persistSoon(); };
    $('#ig-reset').onclick = () => { Object.assign(st, imgDefaults()); save(); paintAdv(); paintSrc(); toast('高级参数已恢复默认'); };
    paintLoras();
    { const B = $('#ig-adv-body'), q = x => B.querySelector(x), up = (el, sel) => el?.closest(sel);
      const secOf = t => [...B.querySelectorAll('.ig-sec')].find(h => h.textContent.trim().startsWith(t));
      const head = document.createElement('div'); head.className = 'ig-sec'; head.textContent = '采样细节';
      advFoldDom(B, 'img', [head, up(q('#ig-sampler'), '.ig-2'), q('#ig-beta'), up(q('#ig-shift'), '.ig-2'), up(q('#ig-noise'), '.ig-2'), up(q('#ig-extra'), '.field'),
        secOf('引导'), q('#ig-apg-b'), up(q('#ig-slg'), '.ig-4'), up(q('#ig-dg'), '.ig-2'),
        secOf('速度和显存'), up(q('#ig-vt'), 'label'), q('#ig-vt-o'), up(q('#ig-sage'), 'label'), up(q('#ig-cache'), '.ig-2'),
        secOf('输出'), up(q('#ig-fmt'), '.ig-2'), up(q('#ig-meta'), 'label')].filter(Boolean)); }
  };
  function paintAdvQ() {  // Qwen 2.1 的高级参数
    const B = $('#ig-adv-body'), C = IMGST.caps || {}, fast = st.model === 'q21-fast', M = curM(), ed = qEdit(M), D = imgDefaults(st.model), q = /^q21/.test(st.model);
    B.innerHTML = `<div class="ig-cols"><div class="ig-col">
      <div class="ig-sec">采样${hintHtml((ed ? '推荐设置是老王论坛作者的：参考图先缩到 200 万像素，再按 1280 送进模型；放了 3D 人偶姿势时改为 25 步，并自动加上姿势 LoRA。' : '推荐设置照官方模板。') + '默认就用推荐设置；想改时直接改，清空或点「恢复推荐」回到推荐值。每种用法（文生图、改图、局部重画）各记各的。', 'sm')}</div>
      ${(() => { const QS = IMGST?.q_settings?.[st.model]?.[qMode()] || {}, o = qOv(), m = qMode();
        const sel = (id, list, cur, rec) => `<select class="select" id="${id}"><option value="">推荐 ${esc(rec || '')}</option>${list.map(v => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(v)}</option>`).join('')}</select>`;
        const mpRec = QS.mp ? `${QS.mp} 百万像素` : '按所选尺寸';
        return `<div class="row ig-q2"><div class="field"><span class="label">步数</span><input class="input" id="ig-qsteps" type="number" min="1" max="100" placeholder="推荐 ${QS.steps ?? ''}" value="${o.steps ?? ''}"></div>
          <div class="field"><span class="label">CFG</span><input class="input" id="ig-qcfg" type="number" min="0" max="20" step="0.1" placeholder="推荐 ${QS.cfg ?? 1}" value="${o.cfg ?? ''}"></div></div>
        <div class="row ig-q2"><div class="field"><span class="label">采样器</span>${sel('ig-qsamp', IMGST?.q_samplers || [], o.sampler, QS.sampler)}</div>
          <div class="field"><span class="label">调度器</span>${sel('ig-qsch', IMGST?.q_schedulers || [], o.scheduler, QS.scheduler)}</div></div>
        ${m === 'inpaint' ? '' : `<div class="field"><span class="label">像素${hintHtml('出图大小按百万像素算，宽高比照所选比例（改图时照原图）。像素越多越清楚、越慢。', 'sm')}</span><select class="select" id="ig-qmp"><option value="">推荐 ${mpRec}</option>${m === 'txt' && QS.mp ? `<option value="page"${o.mp === 'page' ? ' selected' : ''}>按所选尺寸</option>` : ''}${[1, 1.5, 2, 3, 4].map(v => `<option value="${v}"${String(o.mp) === String(v) ? ' selected' : ''}>${v} 百万像素</option>`).join('')}</select></div>`}
        <button type="button" class="btn small ghost" id="ig-qreset"${Object.keys(o).length ? '' : ' hidden'}>恢复推荐</button>`; })()}
      <div class="field"><span class="label">种子${hintHtml('相同的种子、提示词和参数会生成相同的图片。生成多张时种子依次 +1。', 'sm')}</span>
        <div class="row" style="gap:6px"><input class="input" id="ig-seed" type="number" min="0" placeholder="随机" value="${st.seed >= 0 ? st.seed : ''}" style="flex:1;min-width:0"><button type="button" class="btn icon-btn" id="ig-dice" title="随机种子" aria-label="随机种子">${IMG_IC.dice}</button></div></div>
      <div id="ig-fx-w"${ed ? '' : ' hidden'}><div class="ig-sec">改图后处理${hintHtml('仅用于指令改图，默认关闭。保留原脸：把原图的脸对齐后贴回，并把新露出的皮肤校正为和原图的脸一致的色调。原图会保留，可在详情中对比。（实测 Qwen 2.1 的脸本来就更像，“按参考脸修脸”反而会变差，这里不提供。）', 'sm')}</div>
        <div class="seg full" id="ig-fx">${[['', '关'], ['keep', '保留原脸']].map(([k, n]) => `<button type="button" data-k="${k}" class="${(st.editFix === 'keep' ? 'keep' : '') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
    </div><div class="ig-col">
      <div class="ig-sec">LoRA${hintHtml(q ? `Qwen 2.1 的 LoRA（几个版本共用），放在 ${(C.lora_dirs || {})[st.model] || 'ComfyUI\\models\\loras\\Qwen21'}；文生图、指令改图、局部重画都会用上。最多 4 个。` : `${esc(M?.name || '')} 的 LoRA，放在 ${(C.lora_dirs || {})[st.model] || ''}。最多 4 个。`, 'sm')}</div>
      <div id="ig-loras"></div>
      <div${ed ? '' : ' hidden'}><div class="ig-sec" style="margin-top:14px">3D 人偶姿势${hintHtml('只在指令改图里放了 3D 人偶姿势时生效：自动加上 PoseStudio 姿势 LoRA。默认 1.0（作者的设置）；身材被人偶带偏时可以试试调低到 0.6~0.8（姿势会跟得松一些）。', 'sm')}</div>
      <div class="field"><span class="label">姿势 LoRA 强度：<span id="ig-pw-v">${(+(st.poseW ?? 1)).toFixed(2)}</span></span><input type="range" id="ig-pw" min="0.3" max="1.5" step="0.05" value="${st.poseW ?? 1}"></div></div>
      ${M?.refine ? `<div class="ig-sec" style="margin-top:14px">二采${hintHtml('出图后再交给 Krea 2 润色一遍（作者的 5 个胶片、柔光 LoRA，只重画约 25%）：构图和人物不变，光影、肤质更有胶片感，皮肤更光滑；每张约多 10 秒。画面里的中文字会被改乱，脸会更偏东亚甜美。一采和二采各存一张，可在二采的详情中对比。默认关闭。', 'sm')}</div>
        <div class="seg full" id="ig-rf">${[['', '关'], ['krea2', 'Krea 2 润色']].map(([k, n]) => `<button type="button" data-k="${k}" class="${(st.refine2 ? 'krea2' : '') === k ? 'on' : ''}"${k && IMGST?.refine_missing?.length ? ` disabled data-tip="缺少文件：${esc(IMGST.refine_missing.join('、'))}"` : ''}>${n}</button>`).join('')}</div>` : ''}
      <div class="ig-sec" style="margin-top:14px">输出</div>
      <div class="field"><span class="label">格式</span><div class="seg full" id="ig-fmt">${(C.formats || ['png', 'jpeg', 'webp']).map(f => `<button type="button" data-f="${f}" class="${st.format === f ? 'on' : ''}">${f.toUpperCase()}</button>`).join('')}</div></div>
      <div class="field" id="ig-q-f"${st.format === 'png' ? ' hidden' : ''}><span class="label">质量：<span id="ig-q-v">${st.quality}</span></span><input type="range" id="ig-q" min="50" max="100" value="${st.quality}"></div>
    </div></div>`;
    paintLoras();
    { const setO = (k, v) => { const o = qOv(true); if (v === '' || v == null) delete o[k]; else o[k] = v; const r = $('#ig-qreset'); if (r) r.hidden = !Object.keys(o).length; persistSoon(); paintAdvN(); };
      $('#ig-qsteps').oninput = e => setO('steps', e.target.value === '' ? '' : Math.max(1, Math.min(100, parseInt(e.target.value) || 1)));
      $('#ig-qcfg').oninput = e => setO('cfg', e.target.value === '' ? '' : Math.max(0, Math.min(20, +e.target.value || 0)));
      $('#ig-qsamp').onchange = e => setO('sampler', e.target.value); $('#ig-qsch').onchange = e => setO('scheduler', e.target.value);
      const mp = $('#ig-qmp'); if (mp) mp.onchange = e => setO('mp', e.target.value);
      $('#ig-qreset').onclick = () => { if (st.qOver) delete st.qOver[st.model + '|' + qMode()]; save(); paintAdvQ(); paintAdvN(); }; }
    $('#ig-pw').oninput = e => { st.poseW = +e.target.value; $('#ig-pw-v').textContent = (+e.target.value).toFixed(2); persistSoon(); paintAdvN(); };
    $('#ig-seed').oninput = e => { const v = e.target.value.trim(); st.seed = v === '' ? -1 : Math.max(0, parseInt(v) || 0); persistSoon(); paintAdvN(); };
    $('#ig-dice').onclick = () => { st.seed = -1; $('#ig-seed').value = ''; save(); paintAdvN(); };
    $$('#ig-fx button').forEach(b => b.onclick = () => { st.editFix = b.dataset.k; $$('#ig-fx button').forEach(x => x.classList.toggle('on', x === b)); save(); });
    $$('#ig-rf button').forEach(b => b.onclick = () => { st.refine2 = !!b.dataset.k; $$('#ig-rf button').forEach(x => x.classList.toggle('on', x === b)); save(); paintAdvN(); });
    $$('#ig-fmt button').forEach(b => b.onclick = () => { st.format = b.dataset.f; save(); $$('#ig-fmt button').forEach(x => x.classList.toggle('on', x === b)); $('#ig-q-f').hidden = st.format === 'png'; paintAdvN(); });
    $('#ig-q').oninput = e => { st.quality = +e.target.value; $('#ig-q-v').textContent = e.target.value; persistSoon(); };
  }
  let advNT = 0;
  const IMG_ADV_ID = { steps: 'ig-steps', cfg: 'ig-cfg', sampler: 'ig-sampler', scheduler: 'ig-scheduler', flowShift: 'ig-shift', eta: 'ig-eta', negative: 'ig-neg', vaeTiling: 'ig-vt', cacheMode: 'ig-cache', format: 'ig-fmt', meta: 'ig-meta',
    noiseSampler: 'ig-noise', betaA: 'ig-ba', betaB: 'ig-bb', extraArgs: 'ig-extra', guidance: 'ig-dg', rng: 'ig-rng', sage: 'ig-sage' };
  // ComfyUI 跑的模型（Qwen 2.1、MOSS、Krea 2、H3-Image、Z-Image 官方）：步数 / CFG / 采样器 / 调度器 / 像素默认用推荐设置，用户改了的存在 st.qOver[模型|用法]（2026-11-23 用户：不要都固定死）
  const qMode = () => st.mode === 'edit' || st.mode === 'inpaint' ? st.mode : 'txt';
  const qOv = (make) => { const k = st.model + '|' + qMode(); if (make) { st.qOver = st.qOver || {}; return st.qOver[k] = st.qOver[k] || {}; } return st.qOver?.[k] || {}; };
  const Q_F = { steps: 'ig-qsteps', cfg: 'ig-qcfg', sampler: 'ig-qsamp', scheduler: 'ig-qsch', mp: 'ig-qmp' };
  const imgAdvChg = () => { const D = imgDefaults();
    if (isQ()) { const o = qOv();
      return [...Object.keys(Q_F).filter(k => o[k] !== undefined && o[k] !== '').map(k => Q_F[k]), ...(st.loras?.length ? ['ig-loras'] : []), ...((st.poseW ?? 1) !== 1 && qEdit(curM()) ? ['ig-pw'] : []),
        ...(st.refine2 && curM()?.refine ? ['ig-rf'] : []), ...(st.format !== D.format ? ['ig-fmt'] : []), ...(st.seed >= 0 ? ['ig-seed'] : [])]; }
    return [...Object.keys(IMG_ADV_ID).filter(k => String(st[k] ?? '') !== String(D[k] ?? '')).map(k => IMG_ADV_ID[k]),
      ...(st.hires?.enabled ? ['ig-hr'] : []), ...(st.loras?.length ? ['ig-loras'] : []), ...(st.apg?.enabled ? ['ig-apg'] : []), ...(+st.slg?.scale ? ['ig-slg'] : []),
      ...(st.detail?.on ? ['ig-dt'] : []), ...(isQ() && (st.poseW ?? 1) !== 1 ? ['ig-pw'] : []), ...(st.refine2 && curM()?.refine ? ['ig-rf'] : []), ...(st.seed >= 0 ? ['ig-seed'] : [])]; };
  const paintAdvN = () => { clearTimeout(advNT); advNT = setTimeout(() => { const b = $('#ig-adv-body'); if (!b) return paintAdv(); const n = imgAdvChg().length; $('#ig-adv-n').textContent = n ? String(n) : ''; advMark(b, imgAdvChg()); }, 150); };
  const paintLoras = () => {
    const box = $('#ig-loras'), C = IMGST.caps || {}, all = (C.loras_by_model || {})[st.model] || (C.loras_by_model ? [] : C.loras || []);
    if (!IMGST.error) st.loras = (st.loras || []).filter(x => all.includes(x.name));  // 读不到状态时别把选好的 LoRA 清掉；换了模型，别的模型的 LoRA 不带过来
    const lm = n => ((C.lora_meta || {})[st.model] || {})[n] || null;
    box.innerHTML = (all.length ? st.loras.map((x, n) => `<div class="ig-lora"><span class="ig-lora-n" title="${esc(x.name)}">${esc(loraLabel(x.name, lm(x.name)).name)}<span class="ig-lora-f">${esc(x.name)}</span></span><input type="range" min="-3" max="3" step="0.05" value="${x.weight}" data-n="${n}"><b>${(+x.weight).toFixed(2)}</b><button type="button" class="pl-ib" data-x="${n}" title="不使用此项" aria-label="不使用此项">${ICON.x}</button></div>
        ${(lm(x.name)?.words || []).length ? `<div class="vd-lw"><span class="tiny">触发词</span>${lm(x.name).words.slice(0, 8).map(w => `<button type="button" class="chip" data-w="${esc(w)}" title="点击添加到提示词">${esc(w)}</button>`).join('')}</div>` : ''}`).join('')
      + (all.some(n => !st.loras.find(x => x.name === n)) && st.loras.length < (isQ() ? 4 : 8) ? `<button type="button" class="btn small ig-lora-add" id="ig-lora-add">＋ 添加 LoRA</button>` : '')
      : `<div class="tiny">暂无 LoRA${hintHtml('可在下方从 Civitai 下载，或将文件放入 <b>' + esc((C.lora_dirs || {})[st.model] || 'models\\Z-Image\\loras') + '</b>，刷新后即可选择。', 'sm')}</div>`)
      + `<div class="row" style="gap:8px;margin-top:8px"><button type="button" class="btn small ghost" id="ig-cv" title="在应用中搜索、预览并一键下载 Civitai 上的 LoRA">在 Civitai 查找 LoRA</button><button type="button" class="btn small ghost" id="ig-mine" title="本机已有的 LoRA：模型名、示例、说明和模型页">我的下载</button></div>`;
    $$('[data-w]', box).forEach(b => b.onclick = () => { const ta = $('#ig-prompt'), w = b.dataset.w; if (!ta) return; if (ta.value.toLowerCase().includes(w.toLowerCase())) return toast('提示词中已包含'); ta.value = (ta.value.trim() ? ta.value.trim().replace(/[，,]?$/, ', ') : '') + w; ta.dispatchEvent(new Event('input')); toast('已添加到提示词：' + w); });
    const cvOpen = (view, po) => { const base = (IMGST.models || []).find(m => m.key === st.model)?.base || ''; civitaiOpen(/Krea/.test(base) ? 'krea' : /Qwen-Image 2\.1/.test(base) ? 'q21' : /Qwen/.test(base) ? 'qedit' : /MOSS/.test(base) ? 'moss' : /H3-Image/.test(base) ? 'h3img' : 'zimage', async () => { const r = await api('/api/img/status').catch(() => null); if (r) { IMGST.caps = r.caps; } if (box.isConnected) paintLoras(); }, view, po); };
    $('#ig-cv', box).onclick = () => cvOpen(); $('#ig-mine', box).onclick = () => cvOpen('mine');
    $$('input[data-n]', box).forEach(r => r.oninput = () => { st.loras[+r.dataset.n].weight = +r.value; r.nextElementSibling.textContent = (+r.value).toFixed(2); persistSoon(); });
    $$('[data-x]', box).forEach(b => b.onclick = () => { st.loras.splice(+b.dataset.x, 1); save(); paintLoras(); paintAdvN(); });
    // 添加 LoRA（2026-11-11 用户：下拉框里只有显示不全的名字）：打开“我的下载”，有封面、翻译、详情，点“使用”加上
    const fit = f => { const L = (IMGST.caps?.loras_by_model || {})[st.model] || IMGST.caps?.loras || []; return L.includes(f) ? f : L.find(n => loraStem(n) === loraStem(f)) || ''; };  // 列表里没有扩展名、商店传来的有：按去掉扩展名比
    const add = $('#ig-lora-add'); if (add) add.onclick = () => cvOpen('mine', { used: new Set(st.loras.map(x => loraStem(x.name))), pick: async f => {
      let n = fit(f); if (!n) { const r = await api('/api/img/status').catch(() => null); if (r) IMGST.caps = r.caps; n = fit(f); }  // 刚下载完：列表还没刷新
      if (!n) return toast('这个 LoRA 不适用于当前模型', true);
      if (st.loras.find(x => x.name === n)) return toast('已经添加过了');
      st.loras.push({ name: n, weight: lm(n)?.weight || 1 }); save(); paintLoras(); paintAdvN(); toast('已添加：' + loraLabel(n, lm(n)).name); } });
  };
  $('#ig-adv-open').onclick = () => {
    const box = modal(`<div class="row between" style="margin-bottom:8px"><h3 class="card-title" style="margin:0">高级参数</h3><button type="button" class="btn small" data-close>完成</button></div><div id="ig-adv-body" class="ig-adv-body"></div>`, null, true);
    box.classList.add('ig-adv-modal');
    paintAdv();
    const c0 = box.close; box.close = () => { c0(); setTimeout(paintAdv, 220); };
    $$('[data-close]', box).forEach(b => b.onclick = box.close);
  };
  paintAdv(); paintMode();
  // 粘贴截图：在生图页任何地方按 Ctrl+V（剪贴板里是图片时）→ 自动切到图生图并用这张图
  const onPaste = e => {
    if (!$('#ig-form-wrap') && !$('#ig-go')) return document.removeEventListener('paste', onPaste);
    const f = [...(e.clipboardData?.files || [])].find(x => x.type.startsWith('image/'));
    if (!f) return;  // 粘贴的是文字：照常粘进输入框
    e.preventDefault();
    if ((st.mode === 'edit' || (st.mode === 'inpaint' && isQ())) && document.querySelector('.ig-refs:hover, .ig-ref:focus')) return addRefFile(f);  // 鼠标停在参考图上：粘成图 2 / 图 3
    loadUpload(f);  // 放了图会自动从文生图切到图生图（paintMode） toast('已用粘贴的图片作为原图');
  };
  document.removeEventListener('paste', renderImg.paste || (() => { })); renderImg.paste = onPaste; document.addEventListener('paste', onPaste);
  const ta = $('#ig-prompt');
  if (!ta.value && sessionStorage.getItem('igDraft')) { ta.value = st.prompt = sessionStorage.getItem('igDraft'); }
  ta.oninput = () => { st.prompt = ta.value; sessionStorage.setItem('igDraft', ta.value); persistSoon(); };
  ta.addEventListener('input', () => requestAnimationFrame(igSrcFit));
  PromptInspector.bind(ta, () => api('/api/img/prompt-preview', { body: {
    prompt: ta.value.trim(), prompt_input: ta.value, negative: st.negative,
    detail: st.detail?.on ? st.detail : null,
    ...(isQ() ? { q21: { mode: st.mode, enhance: !$('#ig-enh-f')?.hidden ? enhVal() : 'off', pose: !!(IMG_POSE && st.mode === 'edit') } } : {})  // 局部重画：后台按生成时的规则补上开头那句
  } }), { tpl: { pages: ['img'] } });
  ta.onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } };  // （go() 不带参数 = 正常生成）
  $$('#ig-count [data-n]').forEach(b => b.onclick = () => { st.count = +b.dataset.n; save(); $$('#ig-count button').forEach(x => x.classList.toggle('on', x === b)); });
  const go = async (pre = false) => {
    const btn = $(pre === true ? '#ig-enh-go' : '#ig-go'); if (!btn || btn.disabled) return;  // Ctrl+Enter 连按：不重复提交
    const poseOn = !!(IMG_POSE && isQ() && st.mode === 'edit');  // 3D 人偶摆姿势：提示词可以不写（后台用 Fisher 的固定指令）
    if (!ta.value.trim() && !(poseOn && pre !== true)) { ta.focus(); return toast('请先描述要生成的画面', true); }
    if (st.mode !== 'txt' && !IMG_SRC) return toast('请先添加原图', true);
    let [, , w, h] = st.size === 'custom' ? [, , st.cw || 1024, st.ch || 1024] : IMG_SIZES.find(x => x[0] === st.size) || IMG_SIZES[0];
    const body = { model: st.model, mode: st.mode, prompt: ta.value.trim(), prompt_input: ta.value, negative: st.negative, count: st.count, seed: st.seed, steps: st.steps, cfg: st.cfg,
      sampler: st.sampler, scheduler: st.scheduler, flow_shift: st.flowShift === '' ? null : +st.flowShift, eta: st.eta === '' ? null : +st.eta,
      hires: { ...st.hires, ...(st.hires?.by === 'size' ? {} : { target_width: 0, target_height: 0 }) }, vae_tiling: st.vaeTiling, vae_tile: st.vaeTile, cache_mode: st.cacheMode, cache_option: st.cacheOption,
      noise_sampler: st.noiseSampler, beta_alpha: st.betaA === '' ? null : +st.betaA, beta_beta: st.betaB === '' ? null : +st.betaB, extra_args: st.extraArgs,
      apg: st.apg, guidance: st.guidance === '' || st.guidance == null ? null : +st.guidance, rng: st.rng, sage: st.sage,
      slg: { ...st.slg, layers: String(st.slg?.layers ?? '7,8,9').split(/[,，\s]+/).filter(Boolean).map(Number).filter(n => Number.isInteger(n)) },
      loras: st.loras, format: st.format, quality: st.quality, meta: st.meta,
      detail: st.detail?.on && (st.detail.face || st.detail.hand) ? { face: !!st.detail.face, hand: !!st.detail.hand, strength: st.detail.strength, strength2: st.detail.strength2, prompt: st.detail.prompt || '' } : null };
    if (st.mode !== 'txt') {
      [w, h] = imgSize16(IMG_SRC.w, IMG_SRC.h);
      body.init = IMG_SRC.kind === 'gallery' ? { gallery: IMG_SRC.id } : { data: IMG_SRC.data };
      body.strength = st.strength;
      if (st.mode === 'edit' && st.editFix === 'keep') body.keep_face = true;  // 改图后处理（默认关）
      else if (st.mode === 'edit' && /^f[01]$/.test(st.editFix || '') && !isQ()) body.face_ref = +st.editFix[1];
      if (st.mode === 'inpaint') {
        if (!IMG_MASK) return toast('请先涂抹要重画的区域', true);
        const d = IMG_MASK.getContext('2d').getImageData(0, 0, IMG_MASK.width, IMG_MASK.height).data;
        let any = false; for (let n = 0; n < d.length; n += 4 * 97) if (d[n] > 127) { any = true; break; }
        if (!any) return toast('请先涂抹要重画的区域', true);
        body.mask = { data: maskOut(IMG_MASK, +st.maskGrow || 0, +st.maskFeather || 0).toDataURL('image/png') }; body.crop = !!st.inpaintCrop;
      }
    }
    if (st.mode === 'edit' && (st.eSize || 'src') !== 'src') {  // 指令改图自选尺寸
      [, , w, h] = st.eSize === 'custom' ? [, , st.ecw || 1024, st.ech || 1024] : IMG_SIZES.find(x => x[0] === st.eSize) || [, , w, h];
      body.size_free = true;
    }
    body.width = w; body.height = h;
    if (poseOn && pre !== true) { body.pose = { data: IMG_POSE.data }; body.pose_w = st.poseW ?? 1; body.enhance = 'off'; if (!body.prompt) body.prompt = 'Draw character from image2.'; }
    if ((st.mode === 'edit' || (st.mode === 'inpaint' && isQ())) && IMG_REFS.length) body.refs = IMG_REFS.slice(0, 2).map(r => r.kind === 'gallery' ? { gallery: r.id } : { data: r.data });  // 多图改图：图 2、图 3
    if (body.refs && isQ() && st.refX) body.ref_extract = true;  // 参考图先提取衣服（2026-11-16，默认关，见 q21.extract_refs）
    if (st.refine2 && curM()?.refine && body.mode === 'txt' && !body.init) body.refine = true;
    if (isQ() && Object.keys(qOv()).length) body.q_over = { ...qOv() };  // 用户改过的步数 / CFG / 采样器 / 调度器 / 像素（没改的后台用推荐设置）  // 二采：Krea 2 润色（2026-11-23，默认关，见 q21.wf_refine）
    if (isQ()) { body.enhance = !$('#ig-enh-f')?.hidden ? enhVal() : 'off'; body.emph = st.q21Emph === true && body.enhance !== 'off'; body.loras = (st.loras || []).slice(0, 4); body.hires = { enabled: false }; body.detail = null; }
    if (IMG_CTL && curM()?.cn) body.control = { type: st.ctlType || 'pose', strength: st.ctlStr ?? .7, image: IMG_CTL.kind === 'gallery' ? { gallery: IMG_CTL.id } : { data: IMG_CTL.data } };
    if (pre === true) {  // 先增强（2026-11-15 用户：要点两层、看不到进度）：输入框里一键，进度就地显示（照 Apple 写作工具：原文上流光 + 可撤销）
      if (body.enhance === 'off') body.enhance = enhLastVal();  // 增强关着：用上次用的写法（没有就用官方）
      body.emph = st.q21Emph === true;
      return enhRun(body);
    }
    if (isQ() && st.q21Pre && body.enhance !== 'off') { body.enhance = 'off'; body.emph = false; }  // 这段提示词已经先增强过：生成时不再增强一遍
    btn.disabled = true;
    try {
      await api('/api/img/jobs', { body });
      const nt = $('#ig-note'); if (nt) nt.textContent = '';
      if ($('#ig-live')) watch();  // 已经离开生图页的话不要接管别的页面的刷新
    } catch (e) { toast(e.message, true); }
    btn.disabled = false;
  };
  $('#ig-go').onclick = () => go();
  renderImg.preEnh = () => go(true);
  $('#ig-enh-q').onclick = () => { if (ENH_RUN) return enhStop(); go(true); };
  // “已增强过”的记号（生成时不再增强）：自己打字怎么改都保留（2026-11-16 用户：我可能会自己大改）；清空、或整段被粘贴 / 拖进来的文字替换掉 = 新的话，下次生成照常增强
  ta.addEventListener('beforeinput', e => { if (st.q21Pre && /^insertFrom|^insertReplacement/.test(e.inputType || '') && ta.value && ta.selectionStart === 0 && ta.selectionEnd === ta.value.length) ta._q21New = true; });
  ta.addEventListener('input', e => {
    if (/^history(Undo|Redo)$/.test(e.inputType || '')) {  // Ctrl+Z 退回增强前的原文：不再算“已增强过”；Ctrl+Shift+Z 回到增强后：又算
      const p = st.q21Pre || st.q21PreUndone;
      if (p && ta.value === p.orig) { st.q21PreUndone = p; st.q21Pre = null; save(); enhQPaint(); }
      else if (p && ta.value === p.text) { st.q21Pre = p; st.q21PreUndone = null; save(); enhQPaint(); }
      ta._q21New = false; return; }
    if (st.q21Pre && (!ta.value.trim() || ta._q21New)) { st.q21Pre = null; save(); enhQPaint(); } ta._q21New = false; });
  renderImg.enhUndo = () => { const p = st.q21Pre; if (!p || typeof p.orig !== 'string') return; taReplace(ta, p.orig); st.prompt = ta.value; sessionStorage.setItem('igDraft', ta.value); st.q21PreUndone = p; st.q21Pre = null; save(); enhQPaint(); toast('已恢复增强前的原文'); };
  $('#ig-enh-undo').onclick = () => renderImg.enhUndo();
  $('#ig-ai').onclick = async () => {  // 图生图 / 局部重画：把原图一起带给AI 助手（模型能识图时），让它照着原图写
    const R = st.mode === 'edit' || (st.mode === 'inpaint' && isQ());
    const srcs = st.mode !== 'txt' && IMG_SRC?.url && PGST?.vision !== false ? [IMG_SRC.url, ...(R ? IMG_REFS.map(r => r.url) : [])] : [];
    const img = (await Promise.all(srcs.map(u => pgImgPrep(u).catch(() => null)))).filter(Boolean);
    pgOpen(ta.value.trim(), 'img', (isQ() ? { txt: 'img-zh', edit: 'img-q21', inpaint: 'img-q21' } : { img: 'img-i2i', inpaint: 'img-inpaint', edit: 'img-qedit' })[st.mode] || null, img);  // 每种用法用自己的写法
  };
  pageRefresh(['img'], () => { if (!$('#ig-live')) return; imgGallery(); watch(); });
  await galP;
  if (st.mode !== 'txt' && !IMG_SRC && st.srcId) paintMode();  // 图库读到了：上次选的原图可以显示了
  if ($('#ig-live')) watch();
}
/* 正在画的：每 0.8 秒看一次进度（有实时预览）；画完一张图库马上多一张；全都结束就停。
   每个任务的卡片只建一次，之后原地改文字 / 进度条 / 预览图（整块重画的话“取消”会点不中）。
   失败的任务一直留着，点“知道了”才收起；取消的留几秒。 */
const imgSeen = new Set(lsJSON('imgSeen', null) || lsJSON('imgSeen', [], sessionStorage));  // 已经点过“知道了”的失败任务（刷新页面后也不再出来）
/* 2026-11-10 用户：生图页的任务卡片在上面被截掉——宽窗口（底部输入框）和生视频页一样：任务收进右下角的小条（名字 + 进度条 + 百分比），
   鼠标停上去弹出小窗口看各任务、可以取消；在空画面 / 全部图片时点它，把完整的任务卡片在上方展开（最多两条高，多的在里面滚动），再点收起；
   正在看某张大图时点它 = 小窗口一直开着（和生视频页一样） */
const imgJobPct = d => d.state === 'running' && d.total ? Math.round(((d.done + d.step / d.total) / (d.count || 1)) * 100) : 0;
function imgJobDock(live, act, fin, det) {
  const wide = IG_WIDE() && !!$('#main > .ig-grid')?.classList.contains('b5-on');
  let pl = $('#ig-jp');
  if (!wide) { pl?.remove(); live.classList.remove('dock-mode', 'open'); live.style.maxHeight = ''; return; }
  live.classList.add('dock-mode');
  const all = [...act, ...fin];
  if (!pl) { pl = document.createElement('div'); pl.id = 'ig-jp'; pl.className = 'vd-jp dock'; $('#main').append(pl);
    pl.onpointerdown = () => { pl._down = 1; }; pl.onpointerup = pl.onpointercancel = () => { setTimeout(() => { pl._down = 0; }, 0); };
    pl.onclick = () => { if (imgStage.closed || imgStage.off) { live.classList.toggle('open'); pl.classList.remove('pin'); imgJobFit(live); pl.blur(); }  /* 展开上方列表时不再同时弹小窗口（焦点留在小条上会让小窗口一直开着） */ else pl.classList.toggle('pin'); pl.setAttribute('aria-expanded', String(pl.classList.contains('pin') || live.classList.contains('open'))); };
    pl.onkeydown = e => { if (e.target === pl && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pl.click(); } else if (e.key === 'Escape') { pl.classList.remove('pin'); pl.blur(); } };
    if (!imgJobDock.out) { imgJobDock.out = 1; document.addEventListener('pointerdown', e => { const q = $('#ig-jp.pin'); if (q && !q.contains(e.target)) q.classList.remove('pin'); }, true); } }
  if (!all.length) { pl.hidden = true; pl.innerHTML = ''; pl.classList.remove('pin'); live.classList.remove('open'); return; }
  pl.hidden = false;
  if (!pl._down) {
    const D = j => (det && det.id === j.id ? det : j), name = j => j.prompt || (j.kind === 'upscale' ? '放大' : '生成图片');
    const run = act.find(j => j.state === 'running'), lead = run || act[0] || fin[0], more = all.length - 1, p = run ? imgJobPct(D(run)) : 0, err = fin.filter(j => j.state === 'error').length;
    const st = run ? p + '%' : act.length ? '排队中' : '失败';
    const row = j => { const d = D(j), s = d.state;
      return `<div class="vd-jp-r ${s}" data-id="${esc(d.id)}"><div class="vd-jp-rt"><b>${esc(name(d))}</b><span>${s === 'running' ? imgJobPct(d) + '%' : s === 'queued' ? '排队中' : s === 'error' ? '失败' : '已取消'}</span>${act.includes(j) ? '<button type="button" class="btn small" data-x>取消</button>' : s === 'error' ? `<button type="button" class="pl-ib" data-ok aria-label="知道了" title="知道了">${ICON.x}</button>` : ''}</div>
        <div class="tiny vd-jp-rm">${esc([d.model_name, d.kind === 'upscale' ? '放大' : '', d.width ? `${d.width} × ${d.height}` : '', d.kind === 'upscale' ? '' : `${d.count} 张`].filter(Boolean).join(' · '))}</div>
        <div class="tiny vd-jp-rs">${s === 'error' ? esc('生成失败：' + (d.error || '')) : esc(d.message || '') + (s === 'running' && d.total ? ` · 第 ${d.step}/${d.total} 步` : '') + (s === 'running' ? jobTimer(d, 'sm') : '')}</div>${s === 'running' ? `<div class="ig-bar"><i style="width:${imgJobPct(d)}%"></i></div>` : ''}</div>`; };
    pl.classList.toggle('err', !act.length);
    pl.setAttribute('role', 'button'); pl.tabIndex = 0; pl.setAttribute('aria-haspopup', 'true');
    pl.setAttribute('aria-label', '任务：' + name(lead) + ' ' + st + (more ? `，另有 ${more} 个` : ''));
    pl.innerHTML = `<span class="vd-jp-dot"></span><span class="vd-jp-nm">${esc(name(lead))}</span>${run ? `<span class="vd-jp-bar"><i style="width:${p}%"></i></span>` : ''}<span class="vd-jp-t">${st}</span>${more ? `<span class="vd-jp-n">+${more}</span>` : ''}
      <div class="vd-jp-pop" role="dialog" aria-label="任务"><div class="vd-jp-h"><b>任务</b><span class="tiny">${[act.length ? act.length + ' 个进行中 / 排队' : '', err ? err + ' 个失败' : ''].filter(Boolean).join(' · ')}</span></div>${all.map(row).join('')}</div>`;
    const pop = $('.vd-jp-pop', pl); pop.onclick = e => e.stopPropagation();
    $$('[data-x]', pop).forEach(b => b.onclick = () => live.querySelector(`[data-id="${b.closest('[data-id]').dataset.id}"] [data-x]`)?.click());  // 和上面的任务卡片用同一个按钮（取消 / 知道了）
    $$('[data-ok]', pop).forEach(b => b.onclick = () => live.querySelector(`[data-id="${b.closest('[data-id]').dataset.id}"] [data-x]`)?.click());
  }
  imgJobFit(live);
  if (typeof vdDockFit === 'function') vdDockFit();
}
function imgJobFit(live) {  // 展开时最多两条任务卡片高，多的在里面滚动
  if (!live.classList.contains('open')) { live.style.maxHeight = ''; return; }
  const cs = [...live.children].slice(0, 2); if (!cs.length) return;
  const gap = cs[1] ? cs[1].getBoundingClientRect().top - cs[0].getBoundingClientRect().bottom : 0;
  live.style.maxHeight = Math.ceil(cs.reduce((a, c) => a + c.offsetHeight, 0) + Math.max(0, gap)) + 'px';
}
function watch() {
  let seen = '', busy = false;
  pollStart(async stop => {
    if (busy) return; busy = true;
    try {
      const live = $('#ig-live'); if (!live) return stop();
      const list = await api('/api/img/jobs').catch(() => null); if (!list) return;
      const act = list.filter(j => j.state === 'queued' || j.state === 'running')  // 正在画的在最上面，排队的按先后
        .sort((a, b) => (b.state === 'running') - (a.state === 'running') || a.created - b.created);
      const fin = list.filter(j => (j.state === 'error' && !imgSeen.has(j.id)) || (j.state === 'cancelled' && Date.now() / 1000 - j.finished < 8));
      const run = act.find(j => j.state === 'running');
      const det = run ? await api('/api/img/jobs/' + run.id).catch(() => null) : null;
      if (!$('#ig-live')) return stop();
      const show = [...act, ...fin];
      [...live.children].forEach(c => { if (!show.some(j => j.id === c.dataset.id)) c.remove(); });
      show.forEach((j, n) => {
        const d = j.id === run?.id && det ? det : j;
        let c = live.querySelector(`[data-id="${d.id}"]`);
        if (!c) {
          c = document.createElement('div'); c.dataset.id = d.id;
          c.innerHTML = `<div class="ig-job-pv"><span class="spinner dark"></span></div>
            <div class="ig-job-main"><div class="ig-job-t">${esc(d.prompt)}</div>
              <div class="tiny">${esc([d.model_name, d.kind === 'upscale' ? '放大' : '', d.width ? `${d.width} × ${d.height}` : '', d.kind === 'upscale' ? '' : `${d.count} 张`, d.seed != null && d.seed !== '' ? `种子 ${d.seed}` : ''].filter(Boolean).join(' · '))}</div>
              <div class="ig-job-st" aria-live="polite"></div><div class="ig-bar" role="progressbar" aria-label="进度" aria-valuemin="0" aria-valuemax="100"><i></i></div></div>
            <button class="btn small" data-x></button>`;
          c.querySelector('[data-x]').onclick = async e => {
            const b = e.currentTarget;
            if (b.dataset.x === 'ok') { imgSeen.add(c.dataset.id); localStorage.setItem('imgSeen', JSON.stringify([...imgSeen].slice(-80))); c.remove(); return; }
            b.disabled = true; b.textContent = '正在取消…';
            await api(`/api/img/jobs/${c.dataset.id}/cancel`, { body: {} }).catch(err => { toast(err.message, true); b.disabled = false; b.textContent = '取消'; });
          };
        }
        if (live.children[n] !== c) live.insertBefore(c, live.children[n] || null);
        c.className = `card ig-job ${d.state}`;
        const pct = d.state === 'running' && d.total ? Math.round(((d.done + d.step / d.total) / d.count) * 100) : 0;
        const st = d.state === 'queued' ? (d.queue_pos > 1 ? `排队中（前面还有 ${d.queue_pos - 1} 个）` : esc(d.message || '排队中'))
          : d.state === 'running' ? `${esc(d.message)}${d.total ? ` · 第 ${d.step}/${d.total} 步` : ''}${jobTimer(d, 'sm')}`
            : d.state === 'error' ? `<span style="color:var(--red)">生成失败：${esc(d.error)}${d.done ? `（已生成的 ${d.done} 张在图库中）` : ''}</span>` : esc(d.message);
        const stEl = c.querySelector('.ig-job-st'); if (stEl._st !== st) { stEl._st = st; stEl.innerHTML = st; }  // 没变就不动（读屏不会反复念）
        const bar = c.querySelector('.ig-bar'); bar.hidden = d.state !== 'running' || !d.total; bar.firstElementChild.style.width = pct + '%'; bar.setAttribute('aria-valuenow', pct);
        const pv = c.querySelector('.ig-job-pv');
        if (!d.preview && d.state !== 'running' && d.state !== 'queued' && pv.querySelector('.spinner')) pv.innerHTML = `<span class="ig-job-ic">${d.state === 'error' ? '!' : '×'}</span>`;  // 结束了：不再转圈
        if (d.preview) { let im = pv.querySelector('img'); if (!im) { pv.innerHTML = '<img alt="">'; im = pv.firstChild; } const src = 'data:image/png;base64,' + d.preview; if (im.getAttribute('src') !== src) im.src = src; }
        const x = c.querySelector('[data-x]'), kind = act.includes(j) ? 'cancel' : d.state === 'error' ? 'ok' : '';
        if (x.dataset.x !== kind) { x.dataset.x = kind; x.style.display = kind ? '' : 'none'; x.disabled = false; x.textContent = kind === 'ok' ? '知道了' : '取消'; }
      });
      imgJobDock(live, act, fin, run && det ? det : null);
      const sig = list.map(j => j.id + ':' + j.done + ':' + j.state).join('|');
      if (sig !== seen) { if (seen) await imgGallery(); seen = sig; }
      if (!act.length && !list.some(j => j.state === 'cancelled' && Date.now() / 1000 - j.finished < 8)) stop();
    } finally { busy = false; }
  }, 800);
}
/* 图库：同一次生成的几张图挨在一起，前面有一条“这一批”的标题（张数、时间、模型），可以整批删除；单张的就不加标题。
   每张图：点开看大图；鼠标停上去（手机上一直显示）有 复用设置 / 改图 / 下载 / 删除；右键（手机长按）有全部操作。 */
const imgBatches = () => {
  const out = []; let cur = null;
  imgGal.forEach((x, i) => { const k = x.job || x.id; if (!cur || cur.key !== k) { cur = { key: k, items: [] }; out.push(cur); } cur.items.push({ x, i }); });
  return out;
};
const SESS_T0 = +(sessionStorage.getItem('sessT0') || (() => { const t = Date.now() / 1000 - 5; sessionStorage.setItem('sessT0', t); return t; })());  // 这次打开应用的时间（关掉应用后重新算）
const imgWhen = t => { const d = new Date(t * 1000), p = n => String(n).padStart(2, '0'), now = new Date(); return (d.toDateString() === now.toDateString() ? '' : `${d.getMonth() + 1}月${d.getDate()}日 `) + `${p(d.getHours())}:${p(d.getMinutes())}`; };
/* 大图关掉以后：等高自适应排列（像相册那样每行一样高、图片保持原比例、正好铺满一行）。
   鼠标指着的那张微微浮起，其余稍暗；底部滑出模型和时间。行高随宽度在 170~260 之间取 */
function jusLayout(box) {
  const inner = $('.ig-jus', box); if (!inner) return;
  const go = () => {
    if (!inner.isConnected) return;
    const W = Math.floor(inner.getBoundingClientRect().width) - 1, gap = 8, items = [...inner.children]; if (W < 50 || !items.length) return;  // 留 1px：宽度是小数时，正好等宽的一行会被挤到下一行
    const target = Math.max(170, Math.min(260, W / 4.2));
    let row = [], sum = 0;
    const flush = last => { if (!row.length) return; const hgt = last ? Math.min(target, (W - gap * (row.length - 1)) / sum) : (W - gap * (row.length - 1)) / sum;
      row.forEach(({ el, ar }, k) => { el.style.width = Math.floor(ar * hgt) + 'px'; el.style.height = Math.round(hgt) + 'px'; el.style.marginRight = k < row.length - 1 ? gap + 'px' : '0'; }); row = []; sum = 0; };
    items.forEach(el => { const ar = Math.max(.4, Math.min(2.5, +el.dataset.ar || 1)); row.push({ el, ar }); sum += ar; if (sum * target + gap * (row.length - 1) >= W) flush(false); });
    flush(true);
  };
  go(); box._jusRO?.disconnect(); if (window.ResizeObserver) { box._jusRO = new ResizeObserver(() => { if (!window.fsHold?.()) requestAnimationFrame(go); }); box._jusRO.observe(box); }
}
async function imgGallery(cached) {
  const box = $('#ig-gal') || $('#w-gal'); if (!box) return;
  const ALL = box.id === 'w-gal';  // 作品页：全部图片
  // 2026-11-17 用户：切到生图页会闪一下空框——以前要等图库读完才画。现在先用上次读到的马上画出来，读回来有变化再更新（签名一样就不动）
  if (!cached && imgGal.length && !box.dataset.sig) imgGallery(true);
  let gerr = ''; const gen = VGEN, got = cached ? null : await api('/api/img/gallery').catch(e => { gerr = e.message; return null; });
  if (!box.isConnected || gen !== VGEN) return;
  if (!cached && !got && !box.dataset.sig) { box.innerHTML = loadFail('图库读取失败', gerr, () => { box.innerHTML = '<div class="shimmer"></div>'; imgGallery(); }); bindLoadFail(); return; }
  if (got) imgGal = got;
  if (!ALL && imgGal[0]) { const nw = imgGal[0];  // 平铺时有了这次新生成的图片：切到大图看它
    if ((imgStage.off || imgStage.closed || imgStage.srcOn) && imgStage.top !== undefined && nw.id !== imgStage.top && (nw.created || 0) >= SESS_T0) { imgStage.off = false; imgStage.closed = false; imgStage.srcOn = false; imgStage.cur = 0; delete box.dataset.sig; }
    imgStage.top = nw.id; }
  const recent = new Set((imgStage.off ? imgGal : imgGal.slice(0, 80)).map(x => x.id));
  if (imgStage.cur != null && imgGal[imgStage.cur]) recent.add(imgGal[imgStage.cur].id);  // 从“全部图片”里点开的较早的一张：也放进下面一排  // 生图页 · 生成结果：最近 80 张；“全部图片”（或关掉大图）显示全部
  const mine = ALL ? imgBatches() : imgBatches().map(b => ({ ...b, items: b.items.filter(it => recent.has(it.x.id)) })).filter(b => b.items.length);
  const nMine = mine.reduce((a, b) => a + b.items.length, 0);
  if ($('#ig-n')) $('#ig-n').textContent = nMine ? nMine + ' 张' : '';
  const hex = !!(!ALL && IG_WIDE() && imgStage.off && nMine > 0);  // 大图关掉了：全部平铺（一定要是 true / false：classList.toggle 第二个参数是 undefined 时会变成“切换”）  // 大图关掉了：蜂窝网格
  if (!ALL) { galLayBind('ig-lay', () => { delete box.dataset.sig; imgGallery(); }); const OFF = !!imgStage.off, tt = $('#ig-ttl'), ab = $('#ig-all'); if (tt) tt.textContent = OFF ? '全部图片' : '生成结果';  // 标题跟着显示的内容变
    if (ab) { ab.classList.toggle('on', OFF); ab.setAttribute('aria-pressed', String(OFF)); ab.onclick = () => { imgStage.off = !imgStage.off; if (!imgStage.off && IG_WIDE()) { imgStage.closed = true; imgStage.srcOn = false; } delete box.dataset.sig; imgGallery(); }; } }
  const sig = (hex ? 'hex:' : '') + (imgStage.off ? 'all:' : '') + (imgStage.closed ? 'closed:' : '') + (imgStage.srcOn ? 'src:' + (IMG_SRC?.url || '') + ':' : '') + (mine.map(b => b.items.map(it => it.x.id).join()).join('|') || 'empty');
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  const url = x => '/media/img/' + encodeURIComponent(x.file);
  const tile = ({ x, i }) => `<div class="ig-tile" data-i="${i}" title="${esc(imgTip(x))}" tabindex="0" aria-label="查看大图：${esc(x.prompt.slice(0, 40))}">
      <img loading="lazy" decoding="async" src="${url(x)}?thumb=1" alt=""><span class="vd-badges"><b>${esc(imgShort(x))}</b>${(x.loras || []).length ? `<b class="lo">LoRA ${x.loras.length}</b>` : ''}</span><span class="vd-meta">${imgT(x.created)}</span>${x.kind === 'upscale' ? '<span class="ig-badge">放大</span>' : x.kind === 'extract' ? '<span class="ig-badge">衣服</span>' : x.mode === 'img' ? '<span class="ig-badge">改图</span>' : x.mode === 'inpaint' ? '<span class="ig-badge">重画</span>' : x.mode === 'edit' ? '<span class="ig-badge">指令</span>' : ''}
      <span class="ig-acts"><button class="pl-ib" data-a="reuse" title="使用此组设置（提示词、尺寸、种子、参数）" aria-label="使用此组设置">${IMG_IC.reuse}</button><button class="pl-ib" data-a="edit" title="用此图改图" aria-label="用此图改图">${IMG_IC.edit}</button><a class="pl-ib" data-a="dl" href="${url(x)}" download="${esc(x.file)}" title="下载" aria-label="下载">${IMG_IC.dl}</a><button class="pl-ib" data-a="del" title="删除此图" aria-label="删除此图">${IMG_IC.del}</button></span></div>`;
  box.classList.toggle('ig-all', hex);
  if (hex) {
    imgStage(null);
    box.innerHTML = `<div class="ig-jus">${mine.flatMap(b => b.items).map(({ x, i }, k) => `<div class="ig-ju" data-i="${i}" data-ar="${(x.width && x.height) ? (x.width / x.height).toFixed(3) : 1}" title="${esc(imgTip(x))}" tabindex="0" style="animation-delay:${Math.min(k, 16) * 28}ms"><img loading="lazy" decoding="async" src="${url(x)}?thumb=1" alt="" draggable="false"><button type="button" class="gl-del" data-gdel aria-label="删除" title="删除">${IMG_IC.del}</button><span class="gl-ring" aria-hidden="true"></span><span class="ig-ju-i"><b>${esc(imgShort(x))}</b>${imgT(x.created)}${(x.loras || []).length ? ' · LoRA ' + x.loras.length : ''}</span></div>`).join('')}</div>`;
    jusLayout(box);
    box.onclick = e => { const t = e.target.closest('.ig-ju'); if (!t) return;
      if (e.target.closest('[data-gdel]')) { e.stopPropagation(); const it = mine.flatMap(b => b.items).find(o => o.i === +t.dataset.i); return it && imgDelete([it.x]); }
      imgStage.off = false; imgStage.closed = false; imgStage.srcOn = false; delete box.dataset.sig; imgStage.cur = +t.dataset.i; imgGallery(); };
    box.onkeydown = e => { const t = e.target.closest('.ig-ju'); if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); t.click(); } };
    box.oncontextmenu = null;
    return;
  }
  box.innerHTML = nMine ? mine.map(b => b.items.length < 2 ? tile(b.items[0]) : `<div class="ig-batch" data-b="${esc(b.key)}"><span class="ig-batch-t"><b>${b.items.length} 张</b> · ${imgWhen(b.items[0].x.created)} · ${esc(b.items[0].x.model_name || '')}</span>
      <span class="spacer"></span><button class="btn small ghost" data-ba="reuse">${IMG_IC.reuse}复用</button><button class="btn small ghost danger" data-ba="del">${IMG_IC.del}删除此批</button></div>` + b.items.map(tile).join('')).join('')
    : ALL || !imgGal.length ? `<div class="ig-empty">${IMG_IC.edit}<b>尚未生成过图片</b></div>` : '';
  if (!ALL) { const ids = mine.flatMap(b => b.items.map(it => it.i)), W = IG_WIDE();
    if (W && imgStage.srcOn && IMG_SRC?.url) imgStageSrc(); else if (W && imgStage.closed && imgGal.length) imgStageClosed(); else imgStage(ids.includes(imgStage.cur) ? imgStage.cur : ids[0]); }  // 一张都没有时不写“点击缩略图查看”，只留“尚未生成过图片”（和生视频一样，2026-11-07 用户：不要说明文字）
  box.onkeydown = e => { const t = e.target.closest('.ig-tile'); if (t && e.target === t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); imgView(+t.dataset.i); } };
  box.onclick = async e => {
    const bh = e.target.closest('.ig-batch');
    if (bh) { const b = imgBatches().find(z => z.key === bh.dataset.b), a = e.target.closest('[data-ba]')?.dataset.ba; if (!b || !a) return; return a === 'del' ? imgDelete(b.items.map(z => z.x)) : imgReuse(b.items[0].x); }
    const t = e.target.closest('.ig-tile'); if (!t) return;
    const x = imgGal[+t.dataset.i], a = e.target.closest('[data-a]')?.dataset.a;
    if (a === 'dl') return;
    if (a === 'reuse') return imgReuse(x);
    if (a === 'edit') return ALL ? imgUseFromWorks(x, 'img') : renderImg.useSrc?.(x, 'img');
    if (a === 'del') return imgDelete([x]);
    if (!ALL && IG_WIDE()) return imgStage(+t.dataset.i);
    imgView(+t.dataset.i);
  };
  box.oncontextmenu = e => {
    const t = e.target.closest('.ig-tile'); if (!t) return;
    const x = imgGal[+t.dataset.i], b = imgBatches().find(z => z.items.some(it => it.x === x));
    ctxMenu(e, [{ label: '详情和提示词', icon: CTX_IC.info, on: () => imgView(+t.dataset.i, { info: true }) }, { label: '全屏查看', icon: CTX_IC.expand, on: () => imgView(+t.dataset.i) },
      { label: '使用此组设置', icon: IMG_IC.reuse, on: () => imgReuse(x) },
      { label: '用此图改图', icon: IMG_IC.edit, on: () => ALL ? imgUseFromWorks(x, 'img') : renderImg.useSrc?.(x, 'img') },
      { label: '反推提示词', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2"/><path d="M8 10h8M8 14h5"/></svg>', on: () => imgDescribe(x) },
      { label: '生成视频', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.2-2.5z" fill="currentColor" stroke="none"/></svg>', on: () => { renderVideo.useSrc(x); go('video'); } },
      { label: '局部重绘', icon: IMG_IC.brush, on: () => ALL ? imgUseFromWorks(x, 'inpaint') : renderImg.useSrc?.(x, 'inpaint') },
      ...(IMGST?.caps?.upscale ? [{ label: x.width ? '放大 4 倍（' + x.width * 4 + ' × ' + x.height * 4 + '）' : '放大 4 倍', icon: IMG_IC.up, on: () => imgUpscale(x) }] : []),
      ...(VAULT ? [] : [{ label: '放进「提取的衣服」', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 5.5a2 2 0 1 1 2.6 1.9c-.4.1-.6.5-.6.9V9"/><path d="M12 9 3.4 15.2a1 1 0 0 0 .6 1.8h16a1 1 0 0 0 .6-1.8z"/></svg>',  // 2026-11-17 用户：生成的衣服图也放进素材库这个文件夹（硬链接），选参考图时好找；私密空间不行（素材库不分空间）
        on: () => api(`/api/img/gallery/${x.id}/tomats`, { body: {} }).then(r => toast(r.existed ? '素材库中已有此图：' + r.rel : '已放进素材库：' + r.rel), err => toast(err.message, true)) }]),
      { label: '存入音源库', icon: IMG_IC.lib, on: () => api(`/api/img/gallery/${x.id}/tolib`, { body: {} }).then(r => { libCache = null; toast(r.existed ? '音源库中已存在此图片：' + r.path : '已存入音源库：' + r.path); }, err => toast(err.message, true)) },
      ...(REMOTE || VAULT ? [] : [{ label: '在资源管理器中显示', icon: CTX_IC.reveal, on: () => api(`/api/img/gallery/${x.id}/reveal`, { body: {} }).catch(err => toast(err.message, true)) }]), '-',
      { label: '删除此图', icon: CTX_IC.del, danger: true, on: () => imgDelete([x]) },
      ...(b && b.items.length > 1 ? [{ label: `删除此批（${b.items.length} 张）`, icon: CTX_IC.del, danger: true, on: () => imgDelete(b.items.map(z => z.x)) }] : [])]);
  };
}
async function imgUpscale(x) {
  try { await api('/api/img/jobs', { body: { kind: 'upscale', id: x.id } }); toast('已开始放大'); if ($('#ig-live')) watch(); }
  catch (e) { toast(e.message, true); }
}
/* 从图库里挑一张当原图 */
function imgPick(onPick) {
  if (!imgGal.length) return toast('图库中暂无图片', true);
  const pick = imgGal.slice(0, 200);  // 选的时候图库刷新了（新图插到最前面）：按打开时的那份来找，不会选错
  modal(`<h3 class="card-title" style="margin:0 0 10px">从图库选择一张</h3><div class="ig-pick">${pick.map((x, i) => `<button type="button" class="ig-pick-t" data-i="${i}" title="${esc(x.prompt)}"><img loading="lazy" src="/media/img/${encodeURIComponent(x.file)}?thumb=1" alt=""></button>`).join('')}</div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>取消</button></div>`, box => {
    $$('.ig-pick-t', box).forEach(b => b.onclick = () => { box.close(); onPick(pick[+b.dataset.i]); });
  }, true);
}
function imgView(i, o = {}) {  // o.info：打开时就显示信息面板（“详情和提示词”，2026-11-23 起代替原来的详情页）
  const MODE = { txt: '文生图', img: '图生图', inpaint: '局部重画' };
  ImageViewer.open(imgGal.map(x => { const cs = imgCmpSrc(x); return { src: '/media/img/' + encodeURIComponent(x.file), thumb: '/media/img/' + encodeURIComponent(x.file) + '?thumb=1', name: x.prompt.slice(0, 60) + (x.prompt.length > 60 ? '…' : ''),
    sub: x.model_name + (x.detail?.done && Object.keys(x.detail.done).length ? ' · 已细化' : '') + (x.editfix ? ' · ' + x.editfix : ''), alt: cs?.a || null, altName: cs?.la,  // 对比：原图 / 一采 / 细化前（以前只有细化前，其余要进详情页才能比）
    info: async () => ({ w: x.width, h: x.height, size: x.size, ext: (x.file.split('.').pop() || 'png'), mtime: x.created, prompt: x.prompt, negative: x.negative, model: x.model_name, seed: x.seed != null ? String(x.seed) : '',
      used: x.prompt_used && x.prompt_used !== x.prompt ? x.prompt_used : '', note: x.enhance_note || '',
      took: x.seconds ? x.seconds + ' 秒' : '', mode: x.kind === 'upscale' ? `放大 ${x.scale || 4} 倍` : MODE[x.mode] || '',
      sample: [x.steps ? x.steps + ' 步' : '', x.cfg != null ? 'CFG ' + x.cfg : '', x.sampler, x.scheduler, x.strength != null ? '改动 ' + Math.round(x.strength * 100) + '%' : '', x.hires?.enabled ? '高清修复 ×' + x.hires.scale : '',
        ...(x.loras || []).map(l => `${l.name} ${l.weight}`), x.detail?.done && Object.keys(x.detail.done).length ? '细化 ' + Object.entries(x.detail.done).map(([k, n]) => k + (n > 1 ? '×' + n : '')).join('、') : ''].filter(Boolean).join(' · ') }) }; }), i,
    { info: !!o.info, actions: k => { const x = imgGal[k], out = f => () => { ImageViewer.close(); f(); }, works = location.pathname === '/works';
      return x ? [{ label: '使用此组设置', short: '复用', icon: IMG_IC.reuse, on: out(() => imgReuse(x)) },  // short：手机看图时底部工具栏上的字
        { label: '用此图改图', short: '改图', icon: IMG_IC.edit, on: out(() => works ? imgUseFromWorks(x, 'img') : renderImg.useSrc?.(x, 'img')) },
        { label: '下载', short: '下载', icon: ICON.dl, on: () => { const a = document.createElement('a'); a.href = '/media/img/' + encodeURIComponent(x.file); a.download = x.file; a.click(); } },
        ...(imgCmpSrc(x) ? [{ label: '对比', short: '对比', icon: IC_CMP, on: out(() => imgCompare(x)) }] : []), '-',  // 2026-11-23 用户：详情页的信息右上角 (i) 里都有，详情页去掉；它的“对比”搬到这里
        { label: '删除…', short: '删除', icon: CTX_IC.del, danger: true, on: out(() => imgDelete([x])) }] : []; } });
}
function imgUseFromWorks(x, mode) {  // 作品页里点“改图 / 局部重绘”：到生图页并用这张作原图
  S.img = Object.assign(S.img || {}, { mode, srcId: x.id, qMode: mode === 'inpaint' ? 'inpaint' : 'edit', useInp: mode === 'inpaint' }); IMG_SRC = null; IMG_MASK = null; persist(); go('img');  // 放了图会换成 Qwen 2.1：按这里选的局部重画 / 改图
}
async function imgReuse(x) {
  if (!IMGST) IMGST = await api('/api/img/status').catch(() => null);  // 刚打开就从「作品」复用：生图状态还没取过，先取（第二轮审查 6）
  S.img = S.img || {};
  const st = S.img, D = imgDefaults();
  // 基础尺寸：新记录存了 base_width；旧记录开过高清修复按倍数倒推（按目标尺寸放大的推不出，就不改尺寸）；放大作品 / 超出 2048 的不填
  const hr = x.hires?.enabled ? x.hires : null, r8 = v => Math.round(v / 8) * 8;
  let bw = x.base_width || (hr ? (hr.target_width ? 0 : r8(x.width / (hr.scale || 1))) : x.width), bh = x.base_height || (hr ? (hr.target_width ? 0 : r8(x.height / (hr.scale || 1))) : x.height);
  if (x.kind === 'upscale' || bw > 2048 || bh > 2048) bw = bh = 0;
  const preset = bw && IMG_SIZES.find(s => s[2] === bw && s[3] === bh);
  const qm = (IMGST?.models || []).find(m => m.key === x.model)?.comfy;  // ComfyUI 跑的模型（Qwen 2.1、MOSS、Krea 2……）
  if (qm) { st.q21Enh = x.enhance || 'off'; st.refine2 = !!x.refine;  // 提示词增强、二采也填回（以前只有 Qwen 2.1 填增强，审查 15）
    st.qOver = st.qOver || {}; if (x.q_over && Object.keys(x.q_over).length) st.qOver[x.model + '|txt'] = { ...x.q_over }; else delete st.qOver[x.model + '|txt']; }
  Object.assign(st, { prompt: x.prompt, q21Pre: null, seed: x.seed ?? -1, model: x.model, mode: 'txt', ...(preset ? { size: preset[0] } : bw ? { size: 'custom', cw: bw, ch: bh } : {}),
    ...(qm ? {} : { steps: x.steps || D.steps, cfg: x.cfg ?? D.cfg }), negative: x.negative || '', sampler: x.sampler || '', scheduler: x.scheduler || '', flowShift: x.flow_shift ?? '', eta: x.eta ?? '',
    hires: x.hires ? { ...D.hires, ...x.hires, by: x.hires.target_width ? 'size' : 'scale', target_width: x.hires.target_width || 2048, target_height: x.hires.target_height || 2048 } : D.hires,
    vaeTiling: !!x.vae_tiling, cacheMode: x.cache_mode || '', cacheOption: x.cache_option || '', loras: x.loras || [], format: x.format || D.format, quality: x.quality || D.quality, meta: x.meta ?? D.meta,
    noiseSampler: x.noise_sampler || '', betaA: x.beta_alpha ?? '', betaB: x.beta_beta ?? '', extraArgs: x.extra_args || '', guidance: x.guidance ?? '', rng: x.rng || D.rng, sage: x.sage ?? D.sage,
    apg: x.apg ? { ...D.apg, ...x.apg } : D.apg, slg: x.slg ? { ...D.slg, ...x.slg, layers: (x.slg.layers || [7, 8, 9]).join(',') } : D.slg,
    detail: x.detail ? { ...IMG_DT0, on: true, face: !!x.detail.face, hand: !!x.detail.hand, strength: x.detail.strength ?? IMG_DT0.strength, strength2: x.detail.strength2 ?? IMG_DT0.strength2, prompt: x.detail.prompt || '' } : { ...IMG_DT0 } });
  sessionStorage.setItem('igDraft', x.prompt || '');
  persist(); if (location.pathname === '/img') renderImg(); else go('img'); toast('已填回全部参数');
}
function imgDelete(list) {
  const n = list.length;
  modal(`<h3 class="card-title" style="margin:0 0 8px">${n > 1 ? `删除这 ${n} 张图？` : '删除此图？'}</h3><div class="tiny">删除后无法恢复（已存入音源库的副本不受影响）。</div>
    <div class="row" style="justify-content:flex-end;gap:8px;margin-top:18px"><button class="btn" data-close>取消</button><button class="btn del-solid" id="igd-ok">${CTX_IC.del}删除${n > 1 ? ` ${n} 张` : ''}</button></div>`, box => {
    setTimeout(() => $('#igd-ok', box)?.focus(), 30);
    $('#igd-ok', box).onclick = async () => {
      box.close();
      try { await api('/api/img/gallery/delete', { body: { ids: list.map(x => x.id) } }); toast(n > 1 ? `已删除 ${n} 张` : '已删除'); } catch (e) { toast(e.message, true); }
      if (list.some(x => x.id === IMG_SRC?.id)) { IMG_SRC = null; IMG_MASK = null; S.img.srcId = null; persist(); if ($('#ig-src-f')) renderImg.repaintSrc?.(); }
      imgGallery();
    };
  });
}

/* ================= AI 助手 =================
   本地的无审查大模型（Qwen3.8 27B）帮你写生图提示词、配音台词：选一套预设（system prompt），直接描述想要什么，
   写出来以后一键“填进生图 / 填进配音”。可以接着说“再暗一点”“改成白天”多轮修改。参数和预设都能随时改。 */
let PGST = null, PG_RUN = null, PG_IMG = null, PG_MATS = null;  // PG_MATS：从生视频带来的素材说明（声音、时长等文字），随下一条消息发出去  // PG_IMG：要随下一条消息发出去的图 [{ image, thumb }…]（最多 4 张；null = 没有）
const PG_ORIG = new Map();  // 缩略图 → 原图（只在内存里，不进本地存储；进出私密空间时清掉）
const pgImgs = () => Array.isArray(PG_IMG) ? PG_IMG : PG_IMG ? [PG_IMG] : [];
const PG_MAX_IMG = 4;
/* 识图：图缩到最长边 1024（发给模型）+ 240 的小图（对话里显示、存进历史） */
function pgImgPrep(src) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => {
      const out = max => { const k = Math.min(1, max / Math.max(im.naturalWidth, im.naturalHeight)), c = document.createElement('canvas');
        c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); return c.toDataURL('image/jpeg', max > 300 ? .88 : .7); };
      res({ image: out(1024), thumb: out(240), orig: typeof src === 'string' && !src.startsWith('blob:') ? src : out(2048) });
    };
    im.onerror = () => rej(new Error('无法打开此图片'));
    im.src = typeof src === 'string' ? src : URL.createObjectURL(src);
  });
}  // 状态（预设、默认参数、引擎设置）；正在写的那一次 { ctrl, i }
/* 预设的分类：内置的按 id 分，自己加的按用途（target）分；每类“自动”时选哪一个见 pgAuto */
const PG_CATS = [['img', '生图'], ['edit', '改图'], ['video', '生视频'], ['vedit', '改视频'], ['describe', '看图写提示词'], ['tts', '配音台词'], ['polish', '改写润色'], ['chat', '自由对话']];  // 改视频 2026-11-09 从“视频”分出来
const PG_CAT_OF = { 'img-zh': 'img', 'img-en': 'img', 'img-i2i': 'edit', 'img-inpaint': 'edit', 'img-qedit': 'edit', 'img-q21': 'edit', 'q21pe-i2i': 'edit', 'q21pe-t2i': 'img', 'video-base': 'video', 'video-ref': 'video', 'video-h3s': 'video',
  video: 'video', 'head-face': 'vedit', 'outfit-frame': 'vedit', 'vedit-outfit': 'vedit', 'img-describe': 'describe', tts: 'tts', polish: 'polish', chat: 'chat' };
/* 选预设时先收起的（2026-11-09 用户：改视频只留和模板对应的几个，生视频留官方两份，其余放进“更多”） */
const PG_MORE = new Set(['video', 'video-h3s', 'head-face', 'outfit-frame']);
const pgCatOf = p => (PG_CATS.some(c => c[0] === p?.cat) && p.cat) || PG_CAT_OF[p?.id] || ({ img: 'img', video: 'video', tts: 'tts' }[p?.target] || ((p?.system || '').trim() ? 'polish' : 'chat'));  // cat：编辑预设里选的主要用途（7 类）
const PG_CAT_TARGET = { img: 'img', edit: 'img', describe: 'img', video: 'video', vedit: 'video', tts: 'tts', polish: '', chat: '' };  // 分类 → 旧的 target（生图 / 配音页“AI 优化”找预设用）
const PG_AUTO0 = { img: 'img-zh', edit: 'img-qedit', video: 'video-base', vedit: 'vedit-outfit', describe: 'img-describe', tts: 'tts', polish: 'polish', chat: 'chat' };
/* 分类 + 选择（'auto' 或具体 id）→ 实际用的预设 id。自动时：从别的页面带过来的那一个（st.hint，比如有参考素材时是参考写法），没有就用这一类的默认 */
function pgAuto(st, list) {
  const inCat = id => list.some(p => p.id === id && pgCatOf(p) === st.cat);
  if (st.hint && inCat(st.hint)) return st.hint;
  if (inCat(PG_AUTO0[st.cat])) return PG_AUTO0[st.cat];
  return list.find(p => pgCatOf(p) === st.cat)?.id || list[0]?.id || '';
}
const pgState = () => {  // 原地补默认值，不换对象：页面里的 st 和存历史用的必须是同一个（换对象会导致删掉的对话又回来）
  const d = { preset: 'img-zh', msgs: [], draft: '', params: {}, cur: null, cat: '', pick: '', hint: '' };
  S.pg = S.pg || {}; for (const k in d) if (S.pg[k] === undefined) S.pg[k] = d[k];
  return S.pg;
};
const PG_KEEP_N = 60, PG_KEEP_DAYS = 30;  // 对话历史：最多留 60 条、30 天（每条最多 30 句），存在浏览器里 / 私密空间的存在后台，不影响速度
const pgTrim = L => { const cut = Date.now() / 1000 - PG_KEEP_DAYS * 86400; let n = 0; return L.filter(h => h && (h.pin || (h.t >= cut && n++ < PG_KEEP_N))); };  // 置顶的对话（pin）不会因超过 30 天或条数上限被删除
const pgHist = () => (S.pgHist = pgTrim(S.pgHist || []));
const PG_PIN_IC = '<svg class="w-pin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-label="已置顶"><path d="M9 3.5h6M10 3.5v5.2L6.8 12.4h10.4L14 8.7V3.5M12 12.4V20.5"/></svg>';
function pgRename(h, done) {  // 重命名一条对话（改过的标题以后继续聊也不会被第一句话覆盖）
  modal(`<h3 class="card-title">重命名对话</h3><input class="input" id="rn" value="${esc(h.title)}" maxlength="60" style="margin:12px 0">
    <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" data-close>取消</button><button class="btn primary" id="rn-ok">保存</button></div>`, m => {
    const inp = $('#rn', m), ok = () => { const t = inp.value.trim(); if (!t) return toast('标题不能为空', true); h.title = t; h.named = true; persist(); m.close(); done && done(); };
    inp.focus(); inp.select(); inp.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); ok(); } };
    $('#rn-ok', m).onclick = ok;
  });
}
const pgTogglePin = h => { if (h.pin) delete h.pin; else h.pin = true; persist(); toast(h.pin ? '已置顶（不会因超过 30 天被自动删除）' : '已取消置顶'); };
/* 后台记录（/api/img/q21-log）：生图页 Qwen 2.1 的提示词增强、AI 助手直接写，以及 AI 助手里直接问官方增强小模型，每一次的输入和输出。
   按空间分开存（私密空间的只在私密空间里看得到），最多留 200 条；和对话历史分开，不会混进去 */
async function pgBgLog() {
  const box = modal(`<div class="row between" style="margin-bottom:8px"><h3 class="card-title" style="margin:0">后台记录${hintHtml('生图选 Qwen 2.1 并打开提示词增强、点“先增强”，或在 AI 助手里选“官方增强小模型”预设时，后台每一步写了什么：您的原话 → 官方增强小模型的输出 → AI 助手的输入和输出 → 最终交给出图模型的提示词。', 'sm')}</h3>
    <div class="row" style="gap:8px"><button type="button" class="btn small ghost" id="bgl-clear">清空</button><button type="button" class="btn small" data-close>关闭</button></div></div><div class="bgl-list" id="bgl-list"><div class="shimmer"></div></div>`, null, true);
  box.classList.add('bgl-modal');
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
  const SRC = { '生图': '生图', '先增强': '先增强', 'AI 助手': 'AI 助手' }, ENH = { pe: '官方增强', ai: '助手直接写', chat: '直接问小模型' }, MODE = { txt: '文生图', edit: '指令改图', inpaint: '局部重画', i2i: '改图', t2i: '文生图' };
  const sec = (t, body, open = false) => body ? `<details class="bgl-sec"${open ? ' open' : ''}><summary>${t}</summary><div class="bgl-txt">${esc(body)}</div></details>` : '';
  const paint = items => {
    const L = $('#bgl-list', box); if (!L) return;
    if (!items.length) { L.innerHTML = '<div class="tiny" style="padding:20px 0;text-align:center">还没有记录</div>'; return; }
    L.innerHTML = items.map(x => `<div class="bgl-it" data-id="${esc(x.id)}">
      <div class="row bgl-h"><b>${esc(SRC[x.source] || x.source || '')}</b><span class="tiny">${esc([new Date(x.time * 1000).toLocaleString('zh-CN', { hour12: false }), x.model, MODE[x.mode], ENH[x.enhance], x.enh_ver].filter(Boolean).join(' · '))}</span><span class="spacer"></span>
        ${x.final ? '<button type="button" class="btn small ghost" data-a="copy">复制最终提示词</button>' : ''}<button type="button" class="btn small ghost" data-a="del">删除</button></div>
      ${(x.images || []).length ? `<div class="row bgl-imgs">${x.images.map(u => `<img src="${esc(u)}" alt="">`).join('')}</div>` : ''}
      ${sec('您的原话', x.user, true)}
      ${sec(`官方增强小模型的输出${x.pe_bad === 'refused' ? '（拒绝了）' : x.pe_bad === 'junk' ? '（乱码）' : ''}${x.pe_sec ? ` · ${x.pe_sec} 秒` : ''}`, x.pe_raw, !x.rs_text)}
      ${x.pe_system ? sec('小模型用的系统提示词（改过）', x.pe_system) : ''}
      ${x.rs_text ? sec('AI 助手 · 收到的内容', x.rs_input) + sec(`AI 助手 · 写出的指令${x.rs_sec ? ` · ${x.rs_sec} 秒` : ''}`, x.rs_text, true) + sec('AI 助手用的系统提示词', x.rs_system) : ''}
      ${x.final ? sec('最终交给出图模型的提示词', x.final, true) : ''}${x.note ? `<div class="tiny bgl-note">${esc(x.note)}</div>` : ''}</div>`).join('');
  };
  let items = [];
  try { items = (await api('/api/img/q21-log')).items || []; } catch (e) { $('#bgl-list', box).innerHTML = `<div class="tiny">${esc(e.message)}</div>`; return; }
  paint(items);
  $$('.bgl-imgs img', box).forEach((im, k, all) => { im.classList.add('zoomable'); });
  box.onclick = async e => {
    const im = e.target.closest('.bgl-imgs img'); if (im) { const its = [...im.parentElement.querySelectorAll('img')]; return zoomImgs(its.map(x => x.src), its.indexOf(im)); }
    const a = e.target.closest('[data-a]')?.dataset.a, it = e.target.closest('.bgl-it'), x = it && items.find(z => z.id === it.dataset.id); if (!a || !x) return;
    if (a === 'copy') return copyText(x.final).then(() => toast('已复制'), er => toast(er.message, true));
    if (a === 'del') { try { await api('/api/img/q21-log', { body: { id: x.id } }); items = items.filter(z => z !== x); paint(items); } catch (er) { toast(er.message, true); } }
  };
  $('#bgl-clear', box).onclick = async () => { if (!items.length) return; if (!await confirmBox('清空全部后台记录？', '只删除这里的记录，不影响生成的图片和对话历史。', '清空', true)) return; try { await api('/api/img/q21-log', { body: {} }); items = []; paint(items); } catch (er) { toast(er.message, true); } };
}
function pgHistSave() {  // 把当前对话存进历史（有新内容才动）
  const st = pgState(); if (!st.msgs.some(m => m.role === 'user')) return;
  const list = pgHist(), title = (st.msgs.find(m => m.role === 'user')?.content || '对话').replace(/\s+/g, ' ').slice(0, 30);
  if (!st.cur) st.cur = 'c' + Date.now().toString(36);
  const it = { id: st.cur, title, preset: st.preset, msgs: st.msgs.map(m => ({ role: m.role, content: m.content, prompt_input: m.prompt_input, prompt_trace_id: m.prompt_trace_id, reasoning: m.reasoning || undefined, err: m.err || undefined, secs: m.secs, tps: m.tps, pps: m.pps, mtp: m.mtp, thumb: m.thumb || undefined, had_image: (m.had_image || !!m.image) || undefined })), t: Date.now() / 1000 };
  const old = list.find(h => h.id === st.cur); if (old?.named) { it.title = old.title; it.named = true; } if (old?.pin) it.pin = true;  // 改过的标题、置顶跟着留下
  S.pgHist = pgTrim([it, ...list.filter(h => h.id !== st.cur)]); persist();
}
const PG_BUILTIN = { temperature: 0.8, top_p: 0.9, top_k: 20, min_p: 0, presence_penalty: 0.5, repeat_penalty: 1, max_tokens: 2500, seed: -1, thinking: false, effort: 'low' };  // 后台没给全时的兜底（不会显示 undefined）
const pgParams = () => { const p = Object.assign({}, PG_BUILTIN, PGST?.gen_defaults || {}, pgState().params || {}); if (+p.max_tokens === 1200) p.max_tokens = 2500; return p; };  // 1200 是旧默认值（太短，长提示词会被截短）
const pgClean = t => { const m = String(t || '').match(/```(?:\w+)?\n([\s\S]*?)```/); return (m ? m[1] : String(t || '')).trim(); };  // 填进去的只要正文
function pgAbort() {
  if (!PG_RUN) return;
  const m = pgState().msgs?.[PG_RUN.i]; if (m && m.role === 'assistant' && !m.err) m.err = m.content ? '未写完即停止' : '已停止';  // 半截的回答标出来（进出私密空间时也是）
  try { PG_RUN.ctrl.abort(); } catch { } PG_RUN = null;
}
/* 一条消息里的几张图（按图 1、图 2 的顺序）：原图优先，其次 1024 的，最后才是小图 */
function pgMsgImgs(m) {
  if (!m) return [];
  const th = m.thumbs || (m.thumb ? [m.thumb] : []), im = m.images || (m.image ? [m.image] : []);
  return Array.from({ length: Math.max(th.length, im.length) }, (_, k) => PG_ORIG.get(th[k]) || im[k] || th[k]).filter(Boolean);
}
function pgLastImgs() { return pgMsgImgs([...(pgState().msgs || [])].reverse().find(x => x.role === 'user' && (x.images || x.image || x.thumbs || x.thumb))); }
function pgLastImg() { return pgLastImgs()[0] || null; }
const toDataURL = async u => u.startsWith('data:') ? u : await fetch(u).then(r => r.blob()).then(b => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(b); }));
/* 点一下看大图（上传的图、AI 助手里的图）：用看图器，几张时可以左右切换 */
function zoomImgs(urls, i = 0) {
  urls = (urls || []).filter(Boolean); if (!urls.length) return;
  ImageViewer.open(urls.map((u, k) => ({ src: u, thumb: u, name: urls.length > 1 ? `图 ${k + 1}` : '' })), Math.min(i, urls.length - 1));
}
const imgDims = url => new Promise(r => { const im = new Image(); im.onload = () => r([im.naturalWidth, im.naturalHeight]); im.onerror = () => r([0, 0]); im.src = url; });
/* 回答区自动滚到底：只在本来就停在底部时跟着走；往上翻看时不再把人拉回去，翻回底部后继续跟 */
function pgStick(box, y) {
  if (box.dataset.free === '1') { if (y != null) box.scrollTop = y; return; }
  box.scrollTop = box.scrollHeight;
}
/* 模型状态：电脑在页头（#pg-model）；手机页头藏起来了，在输入框下面说明“未就绪”，发送键变淡（照样能写草稿，点发送会再查一次）。
   2026-11-17 UI 审查 #3：以前手机上要发送之后才知道没有模型 */
function pgAvailPaint() {
  const ok = !!PGST?.available, m = $('#pg-model'), note = $('#pg-note'), go = $('#pg-go');
  if (m) m.textContent = ok ? `${PGST.model}${PGST.running ? ' · 已载入' : ''}` : '尚无提示词模型';
  if (go) { go.setAttribute('aria-disabled', ok ? 'false' : 'true'); go.title = ok ? '发送（Enter）' : '提示词模型未就绪'; }
  if (note && !PG_RUN) { note.textContent = !ok && document.documentElement.classList.contains('ph') ? '提示词模型未就绪' : ''; note.setAttribute('role', 'status'); }
}
function pgWaitHead(m) {  // 闪光的“正在生成 / 思考中”+ 秒数（动画按全局时间对齐，重画也不会从头开始）
  const secs = m.t0 ? Math.max(0, Math.round((Date.now() - m.t0) / 1000)) : 0;
  return `<span class="pg-wait"><span class="pg-shim" style="animation-delay:-${Math.round(performance.now() % 1800)}ms">${m.reasoning?.trim() ? '思考中' : '正在生成'}</span><span class="pg-sec">${secs} 秒</span></span>`;
}
async function pgFill(text, where) {
  const t = pgClean(text); if (!t) return;
  const lastU = [...(pgState().msgs || [])].reverse().find(x => x.role === 'user');
  if (where === 'video' && pgState().preset === 'head-face') { S.vidg = Object.assign(S.vidg || {}, { eprompt: t, mode: 'edit' }); sessionStorage.setItem('veDraft', t); persist(); go('video'); return toast('已填入换头的提示词（头像的脸部描述）'); }
  if (where === 'video' && pgState().back === 'edit') { S.vidg = Object.assign(S.vidg || {}, { eprompt: t, mode: 'edit' }); sessionStorage.setItem('veDraft', t); persist(); go('video'); return toast('已填入改视频的提示词'); }  // 改视频（参考生成）点的 AI 优化：填回改视频，原视频、人物图不动
  const urls = pgState().preset === 'img-describe' || (where === 'video' && (lastU?.labels || lastU?.mats)) ? [] : pgLastImgs();
  const pics = (where === 'video' || where === 'img') && urls.length ? await Promise.all(urls.slice(0, 3).map(async u => { const d = await toDataURL(u).catch(() => null); if (!d) return null; const [w, h] = await imgDims(d); return { kind: 'upload', data: d, url: d, w, h, name: 'prompt.jpg' }; })).then(l => l.filter(Boolean)) : [];
  const pic = pics[0] || null;
  if (pic) {
    if (where === 'video') { VID_SRC = pic; vidState().srcId = null; if (pics[1]) VID_END = pics[1]; }
    else if (pics.length > 1 || ['img-qedit', 'img-q21', 'outfit-frame'].includes(pgState().preset)) {  // 几张图 / 指令改图：图 1 是原图，其余是参考图，换成指令改图模型（Qwen 2.1 的写法 → Qwen 2.1）
      IMG_SRC = pic; IMG_MASK = null; IMG_REFS = pics.slice(1, 3).map(x => ({ kind: 'upload', data: x.data, url: x.url }));
      const q21 = pgState().preset === 'img-q21' || /^q21/.test(S.img?.model || '');
      S.img = Object.assign(S.img || {}, { mode: 'edit', srcId: null, model: q21 ? (/^q21/.test(S.img?.model || '') ? S.img.model : 'q21-fast') : 'qedit' }, q21 ? { qMode: 'edit' } : {});
    } else { IMG_SRC = pic; IMG_MASK = null; S.img = Object.assign(S.img || {}, { mode: 'img', srcId: null }); }
  }
  if (where === 'img') { S.img = Object.assign(S.img || {}, { prompt: t, q21Pre: null }); sessionStorage.setItem('igDraft', t); persist(); go('img'); toast(pic ? '已填入生图的提示词，图片作为原图（图生图）' : '已填入生图的提示词'); }
  else if (where === 'video') { S.vidg = Object.assign(S.vidg || {}, { prompt: t, mode: 'gen' }); sessionStorage.setItem('vdDraft', t); persist(); go('video'); toast(pic ? '已填入生视频的提示词，图片作为首帧' : '已填入生视频的提示词'); }
  else { S.text = t; persist(); go('tts'); toast('已填入配音的文字'); }
}
function pgOpen(text, target, presetId, img, mats) {  // mats：素材说明（生视频的“更多素材”）；带了素材时最多 8 张图，每张图有 lab（发给模型的说明）/ short（缩略图上的字）  // 从生图 / 配音页点“AI 优化”：带着现在的文字过来，选好对应的预设（图生图 / 局部重绘用改图预设）
  const st = pgState(), list = PGST?.presets || [], pre = (presetId && list.find(p => p.id === presetId)) || list.find(p => p.target === target);
  if (pre) st.preset = pre.id; else st.preset = presetId || (target === 'tts' ? 'tts' : 'img-zh');
  st.cat = PG_CAT_OF[st.preset] || pgCatOf(pre) || (target === 'tts' ? 'tts' : target === 'video' ? 'video' : 'img'); st.pick = 'auto'; st.hint = st.preset;  // 分类跟着带过来的预设，具体那一项是“自动”
  if (st.msgs.some(m => m.role === 'user')) { pgHistSave(); st.msgs = []; st.cur = null; }  // 带着新的内容过来：开一个新对话（之前的在历史里）
  if (text) st.draft = text;
  PG_IMG = (Array.isArray(img) ? img.filter(Boolean) : img ? [img] : []).slice(0, mats ? 8 : PG_MAX_IMG); if (!PG_IMG.length) PG_IMG = null; PG_MATS = mats || null;  // 可以带几张图过来（多图改图：原图 + 参考图）
  persist(); go('prompt');
}
function pgAttPaint() {  // 输入框里待发的图 + “添加图片”按钮
  const b = $('#pg-att'), pv = $('#pg-att-prev'); if (!b) return;
  b.hidden = !PGST?.vision;
  const L = pgImgs();
  pv.innerHTML = L.map((it, k) => `<span class="pg-att-it">${it.short ? `<span class="pg-att-n">${esc(it.short)}</span>` : it.vt != null ? `<span class="pg-att-n">${it.vt.toFixed(1)} 秒</span>` : L.length > 1 ? `<span class="pg-att-n">图 ${k + 1}</span>` : ''}<img src="${it.thumb}" alt=""><button type="button" class="pg-att-x" data-k="${k}" title="移除" aria-label="移除图片">${ICON.x}</button></span>`).join('');
  pv.hidden = !L.length;
  $$('.pg-att-it img', pv).forEach((im, k) => { im.title = '点击查看大图'; im.onclick = () => zoomImgs(pgImgs().map(x => x.orig || x.image), k); });
  $$('.pg-att-x', pv).forEach(x => x.onclick = () => { const l = pgImgs().slice(); l.splice(+x.dataset.k, 1); PG_IMG = l.length ? l : null; pgAttPaint(); });
  b.disabled = L.length >= PG_MAX_IMG; b.title = L.length >= PG_MAX_IMG ? `最多 ${PG_MAX_IMG} 张图` : '添加图片（也可直接粘贴截图，最多 4 张）';
}
// 视频：取第一帧（原尺寸的 PNG），当一张图发给模型（“改衣首帧”模板用；用于生图时这一帧就是改图的原图）
function pgVideoFrame(file) {
  return new Promise((res, rej) => {
    const v = document.createElement('video'), url = URL.createObjectURL(file);
    const done = () => { URL.revokeObjectURL(url); v.removeAttribute('src'); v.load(); };
    v.muted = true; v.playsInline = true; v.preload = 'auto';
    v.onloadeddata = () => { try { v.currentTime = 0; } catch (e) { } };
    v.onseeked = () => { try { const c = document.createElement('canvas'); c.width = v.videoWidth; c.height = v.videoHeight; c.getContext('2d').drawImage(v, 0, 0); const d = c.toDataURL('image/png'); done(); res(d); } catch (e) { done(); rej(new Error('无法读取此视频的第一帧')); } };
    v.onerror = () => { done(); rej(new Error('无法打开此视频（请尝试转换为 MP4）')); };
    v.src = url;
  });
}
// 整段视频：按时间均匀抽 n 帧（长边 640，省显存和上下文），每帧记下是第几秒；模型按顺序看这几帧就知道整段在发生什么
function pgVideoFrames(file, n = 6) {
  return new Promise((res, rej) => {
    const v = document.createElement('video'), url = URL.createObjectURL(file), out = [];
    const done = () => { URL.revokeObjectURL(url); v.removeAttribute('src'); v.load(); };
    let times = [], k = 0;
    v.muted = true; v.playsInline = true; v.preload = 'auto';
    v.onloadedmetadata = () => { const d = v.duration || 0; if (!d) { done(); return rej(new Error('无法读取此视频的时长')); }
      times = Array.from({ length: n }, (_, i) => Math.min(d - 0.05, d * (i + 0.5) / n)); v.currentTime = times[0]; };
    v.onseeked = () => { try { const s = Math.min(1, 640 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement('canvas');
        c.width = Math.round(v.videoWidth * s); c.height = Math.round(v.videoHeight * s); c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
        out.push({ data: c.toDataURL('image/jpeg', .85), t: times[k] }); } catch (e) { done(); return rej(new Error('无法读取此视频的画面')); }
      if (++k < times.length) v.currentTime = times[k]; else { const dur = v.duration; done(); res({ frames: out, dur }); } };
    v.onerror = () => { done(); rej(new Error('无法打开此视频（请尝试转换为 MP4）')); };
    v.src = url;
  });
}
const PG_VIDEO_FRAMES = 6;
async function pgAttach(src) {
  if (!PGST?.vision) return toast('当前提示词模型不支持识图', true);
  // 视频：“改衣首帧”模板只要第一帧（拿去改图）；其他时候看整段——均匀抽几帧按顺序发给模型（llama.cpp 里每帧就是一张图）
  if (src instanceof File && src.type.startsWith('video/') && pgState().preset !== 'outfit-frame') {
    if (pgImgs().length) return toast('分析整段视频时请单独发送（请先移除已添加的图片）', true);
    try {
      const r = await pgVideoFrames(src, PG_VIDEO_FRAMES);
      const its = []; for (const f of r.frames) { const it = await pgImgPrep(f.data); it.vt = f.t; it.vdur = r.dur; its.push(it); }
      PG_IMG = its; pgAttPaint(); $('#pg-in')?.focus(); toast(`已从视频中均匀抽取 ${its.length} 帧（整段 ${r.dur.toFixed(1)} 秒）`);
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (pgImgs().length >= PG_MAX_IMG) return toast(`最多 ${PG_MAX_IMG} 张图`, true);
  try {
    if (src instanceof File && src.type.startsWith('video/')) {
      if (typeof framePick === 'function') { const u = URL.createObjectURL(src); return framePick({ local: u, name: src.name }, { primary: '用这一帧', onDone: fs => { if (fs[0]) pgAttach(fs[0]); } }); }  // 2026-11-19：挑一帧（以前固定取第一帧）
      src = await pgVideoFrame(src); toast('已取视频的第一帧'); }
    const it = await pgImgPrep(src); PG_IMG = [...pgImgs(), it].slice(0, PG_MAX_IMG); pgAttPaint(); $('#pg-in')?.focus();
  } catch (e) { toast(e.message, true); }
}
const PG_MIC = {  // 手机顶栏 / 抽屉里的图标（Lucide 风格）
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h10M4 15h16"/></svg>',
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.4 2.6a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
  log: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' };
const pgDrawerGone = () => { document.querySelectorAll('body > #pg-hist').forEach(e => e.parentNode.removeChild(e)); document.body.classList.remove('pg-hist-open'); };
async function renderPrompt() {
  const st = pgState();
  pgDrawerGone();
  const SEND_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
  const STOP_IC = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>';
  $('#main').innerHTML = `<div class="page-head"><div><h1 class="page-title">AI 助手</h1></div><div class="row" style="gap:8px"><span class="tiny" id="pg-model"></span>
      <button type="button" class="btn small pg-hist-t" id="pg-hist-t" title="对话历史">${ICON.list || '☰'}<span>历史</span></button>
      <button type="button" class="btn small" id="pg-side-t">${ICON.sliders || '⚙'}<span>参数</span></button></div></div>
    <div class="pg-grid side-off">
      <aside class="card pg-hist" id="pg-hist"></aside>
      <div class="card pg-card">
        <div class="row pg-top"><button type="button" class="pg-mb pg-m lg" id="pg-hist-m" aria-label="对话历史">${PG_MIC.menu}</button><select class="select native" id="pg-preset" disabled aria-label="预设" hidden></select><div class="pg-cap"><button type="button" class="dd pg-cat-b" id="pg-cat-b" disabled aria-haspopup="dialog" title="选择分类"><span class="dd-t">分类</span><span class="dd-c"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10l5 5 5-5"/></svg></span></button><button type="button" class="dd pg-pre-b" id="pg-preset-b" disabled aria-haspopup="dialog" title="选择预设"><span class="dd-t">预设</span><span class="dd-c"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10l5 5 5-5"/></svg></span></button></div><button type="button" class="btn small ghost" id="pg-edit" title="编辑预设（System prompt）">编辑预设</button><span class="spacer"></span><button type="button" class="btn small ghost" id="pg-new" title="开始新对话（当前对话将保存在历史中）">${ICON.plus || '+'}新对话</button><div class="pg-mcap pg-m lg"><button type="button" class="pg-mb" id="pg-side-m" aria-label="参数">${ICON.sliders}</button><button type="button" class="pg-mb" id="pg-new-m" aria-label="新对话">${PG_MIC.pen}</button></div></div>
        <div class="tiny pg-sys" id="pg-sys"></div>
        <div class="pg-msgs" id="pg-msgs"></div>
        <div class="pg-in"><div class="pg-composer"><div class="pg-att-prev" id="pg-att-prev"></div><button type="button" class="pg-att" id="pg-att" title="添加图片或视频（视频将按时间均匀抽取 6 帧以分析整段内容；也可直接粘贴截图）" aria-label="添加图片或视频" hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M21 16l-5-5-9 9"/></svg></button><input type="file" id="pg-att-f" accept="image/*,video/*" multiple hidden><textarea class="textarea" id="pg-in" rows="1" placeholder="输入消息">${esc(st.draft || '')}</textarea>
          <button type="button" class="pg-think-b${st.params?.thinking ? ' on' : ''}" id="pg-think-b" title="深度思考：先推理再回答，更周全但更慢" aria-pressed="${st.params?.thinking ? 'true' : 'false'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3z"/></svg><span>深度思考</span></button>
          <button type="button" class="pg-send" id="pg-go" title="发送（Enter）" aria-label="发送">${SEND_IC}</button><button type="button" class="pg-send stop" id="pg-stop" title="停止生成" aria-label="停止生成" hidden>${STOP_IC}</button></div>
          <div class="tiny pg-note" id="pg-note"></div></div>
      </div>
      <div class="side-col pg-side-col"><div class="card" id="pg-side"><div class="shimmer"></div></div></div>
    </div><div class="pg-scrim" aria-hidden="true"></div>`;
  // 手机：历史记录是从左边滑出的抽屉（整页往右推开）；放到 body 下面，才不会跟着页面一起被推走
  const pgMob = MOB();
  if (pgMob) document.body.append($('#pg-hist'));
  const pgDrawer = on => { document.body.classList.toggle('pg-hist-open', on); if (on) { const q = $('#pg-hist .pg-dw-q'); if (q && q.value) { q.value = ''; q.dispatchEvent(new Event('input')); } } };
  { const mo = new MutationObserver(() => { if ($('#main .pg-grid')) return; mo.disconnect(); pgDrawerGone(); });
    mo.observe($('#main'), { childList: true }); }
  { let x0 = null; const ts = e => { x0 = e.touches[0].clientX; }, te = e => { if (x0 != null && e.changedTouches[0].clientX - x0 < -50 && !document.documentElement.classList.contains('ph')) pgDrawer(false); x0 = null; };  // 往左一划：关上（手机外壳 phone.js 里是跟着手指拖）
    [$('#pg-hist'), $('.pg-scrim')].forEach(el => { el.addEventListener('touchstart', ts, { passive: true }); el.addEventListener('touchend', te, { passive: true }); }); }
  $('.pg-scrim').onclick = () => pgDrawer(false);
  $('#pg-hist-m').onclick = () => pgDrawer(!document.body.classList.contains('pg-hist-open'));
  $('#pg-new-m').onclick = () => $('#pg-new').click();
  $('#pg-side-m').onclick = () => $('#pg-side-t').click();
  // 对话历史（左边；手机上点“历史”弹出）
  const paintHist = () => {
    const box = $('#pg-hist'); if (!box) return;
    const all = pgHist(), list = [...all.filter(h => h.pin), ...all.filter(h => !h.pin)], day = t => { const d = new Date(t * 1000), now = new Date(); return d.toDateString() === now.toDateString() ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : `${d.getMonth() + 1}月${d.getDate()}日`; };
    if (pgMob) {
      const row = h => `<div class="pg-hi${h.id === st.cur ? ' on' : ''}" data-h="${esc(h.id)}" data-q="${esc(h.title.toLowerCase())}" role="button" tabindex="0"><span class="pg-hi-t">${esc(h.title)}</span><span class="tiny">${day(h.t)}</span><button type="button" class="pl-ib pg-hi-x" data-hx="${esc(h.id)}" aria-label="删除此对话">${ICON.x}</button></div>`;
      const pins = list.filter(h => h.pin), rest = list.filter(h => !h.pin);
      box.innerHTML = `<div class="pg-dw-q-w lg">${PG_MIC.search}<input class="pg-dw-q" type="search" placeholder="搜索对话" aria-label="搜索对话" enterkeyhint="search"></div>
        <div class="pg-dw-menu"><button type="button" data-m="new">${PG_MIC.pen}<span>新对话</span></button><button type="button" data-m="edit">${PG_MIC.edit}<span>编辑预设</span></button><button type="button" data-m="log" id="pg-bglog">${PG_MIC.log}<span>后台记录</span></button></div>
        ${pins.length ? `<div class="pg-dw-s">置顶</div><div class="pg-hist-l">${pins.map(row).join('')}</div>` : ''}
        <div class="pg-dw-s">最近</div>${rest.length ? `<div class="pg-hist-l">${rest.map(row).join('')}</div>` : '<div class="tiny pg-hist-e">暂无对话</div>'}`;
      const q = $('.pg-dw-q', box);
      q.oninput = () => { const w = q.value.trim().toLowerCase(); $$('[data-h]', box).forEach(r => { r.hidden = !!w && !r.dataset.q.includes(w); }); };
      $$('.pg-dw-menu [data-m]', box).forEach(b => b.onclick = e => { e.stopPropagation(); pgDrawer(false);
        if (b.dataset.m === 'new') $('#pg-new').click(); else if (b.dataset.m === 'edit') $('#pg-edit').click(); else pgBgLog(); });
    } else
    box.innerHTML = `<div class="pg-hist-h"><b>对话历史</b><span class="tiny">${list.length ? list.length + ' 条' : ''}</span><span class="spacer"></span><button type="button" class="pg-bglog-b" id="pg-bglog" title="后台记录：生图时提示词增强、AI 助手写提示词，以及这里直接问官方增强小模型时，后台每一步的输入和输出（不算在对话历史里）">后台记录</button></div>` + (list.length ? `<div class="pg-hist-l">${list.map(h => `<div class="pg-hi${h.id === st.cur ? ' on' : ''}" data-h="${esc(h.id)}" role="button" tabindex="0" title="${esc(h.title)}"><span class="pg-hi-t">${h.pin ? PG_PIN_IC : ''}${esc(h.title)}</span><span class="tiny">${day(h.t)}</span><button type="button" class="pl-ib pg-hi-x" data-hx="${esc(h.id)}" title="删除此对话" aria-label="删除此对话">${ICON.x}</button></div>`).join('')}</div>`
      : `<div class="tiny pg-hist-e">暂无对话</div>`);
    box.onclick = e => {
      const x = e.target.closest('[data-hx]');
      if (x) { e.stopPropagation(); S.pgHist = pgHist().filter(h => h.id !== x.dataset.hx); if (st.cur === x.dataset.hx) { st.cur = null; st.msgs = []; paintMsgs(); } persist(); return paintHist(); }
      const it = e.target.closest('[data-h]'); if (!it) return;
      if (PG_RUN) return toast('正在生成，请先停止', true);
      const h = pgHist().find(z => z.id === it.dataset.h); if (!h) return;
      st.cur = h.id; st.msgs = h.msgs.map(m => ({ ...m })); if (h.preset && PGST.presets.some(p => p.id === h.preset)) { st.preset = h.preset; st.cat = pgCatOf(PGST.presets.find(p => p.id === h.preset)); st.pick = h.preset; }
      persist(); paintPresets(); paintMsgs(); paintHist(); document.body.classList.remove('pg-hist-open');
    };
    box.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-h]')) { e.preventDefault(); e.target.click(); } };
    if (!pgMob) $('#pg-bglog', box).onclick = e => { e.stopPropagation(); pgBgLog(); };
    box.oncontextmenu = e => {
      const it = e.target.closest('[data-h]'); if (!it) return; e.preventDefault();
      const h = pgHist().find(z => z.id === it.dataset.h); if (!h) return;
      ctxMenu(e, [{ label: h.pin ? '取消置顶' : '置顶', on: () => { pgTogglePin(h); paintHist(); } },
        { label: '重命名', on: () => pgRename(h, paintHist) }, '-',
        { label: '删除此对话', icon: CTX_IC.del, danger: true, on: () => { S.pgHist = pgHist().filter(z => z.id !== h.id); if (st.cur === h.id) { st.cur = null; st.msgs = []; paintMsgs(); } persist(); paintHist(); } }]);
    };
  };
  $('#pg-hist-t').onclick = () => document.body.classList.toggle('pg-hist-open');
  $('#pg-side-t').onclick = () => {  // 参数一律在横向的宽弹窗里（2026-11-07 用户：不要从右边展开）：左边生成参数，右边模型设置
    const side = $('#pg-side'), home = side?.parentElement; if (!side) return;
    const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">参数</h3><button class="btn small" data-close>完成</button></div><div id="pg-side-host"></div>`, null, true);
    box.classList.add('pg-sm'); $('#pg-side-host', box).append(side);
    new MutationObserver((_, o) => { if (!box.isConnected) { if (home?.isConnected) home.append(side); o.disconnect(); } }).observe(document.body, { childList: true, subtree: true });
  };
  PGST = await api('/api/prompt/status').catch(e => ({ error: e.message, presets: [], gen_defaults: {} }));
  if (!$('#pg-msgs')) return;
  pgAttPaint();
  if (PGST.error) {  // 读不到状态（后台没响应 / 版本旧）：不要留一个空下拉框和一直转的占位
    $('#pg-model').textContent = '';
    $('#pg-side').closest('.side-col').hidden = true;
    $('.pg-top').hidden = true; $('#pg-sys').hidden = true; $('.pg-in').hidden = true; $('#pg-hist').hidden = true;
    $('#pg-msgs').innerHTML = loadFail('AI 助手暂时无法使用', PGST.error, () => renderPrompt());
    bindLoadFail(); return;
  }
  pgAvailPaint();
  if (!Array.isArray(PGST.presets)) PGST.presets = [];
  PGST.presets = PGST.presets.filter(p => p && p.id).map(p => ({ ...p, name: p.name || p.id, system: p.system || '' }));
  if (!PGST.presets.some(p => p.id === st.preset)) st.preset = PGST.presets[0]?.id || '';
  // 分类 / 选择：旧版只记了 preset——按它补上分类，选择就是它本身
  if (!PG_CATS.some(([k]) => k === st.cat)) { st.cat = pgCatOf(PGST.presets.find(p => p.id === st.preset)); st.pick = st.preset; }
  const resolve = () => { const L = PGST.presets; if (st.pick === 'auto') st.preset = pgAuto(st, L); else if (L.some(p => p.id === st.pick && pgCatOf(p) === st.cat)) st.preset = st.pick; else { st.pick = 'auto'; st.preset = pgAuto(st, L); } };
  const inCat = () => PGST.presets.filter(p => pgCatOf(p) === st.cat);
  const paintPresets = () => {
    resolve();
    const sel = $('#pg-preset'); sel.disabled = false;
    sel.innerHTML = PGST.presets.map(p => `<option value="${esc(p.id)}"${p.id === st.preset ? ' selected' : ''}>${esc(p.name)}</option>`).join('');
    const p = PGST.presets.find(x => x.id === st.preset), cb = $('#pg-cat-b'), pb = $('#pg-preset-b');
    $('#pg-sys').textContent = '';
    if (cb) { cb.disabled = false; $('.dd-t', cb).textContent = (PG_CATS.find(c => c[0] === st.cat) || [, '分类'])[1]; }
    if (pb) { pb.disabled = false; $('.dd-t', pb).textContent = st.pick === 'auto' && inCat().length > 1 ? `自动（本次：${p?.name || ''}）` : p?.name || '预设'; pb.title = '选择预设：' + (p?.name || ''); }
  };
  const ppIt = ([id, name, cur]) => `<button type="button" class="pp-it${cur ? ' on' : ''}" data-id="${esc(id)}" title="${esc(name)}"><span>${esc(name)}</span>${cur ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>' : ''}</button>`;
  const ppPop = (btn, items, on, more = []) => { const open = more.some(x => x[2]);  // more：先收起的几项（选中的在里面时直接展开）
    return popover(btn, `<div class="pp-pop"><div class="pp-grid">${items.map(ppIt).join('')}</div>${more.length ? `<button type="button" class="pp-more" aria-expanded="${open}"><span>更多</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg></button><div class="pp-grid pp-more-g"${open ? '' : ' hidden'}>${more.map(ppIt).join('')}</div>` : ''}</div>`,
      pop => { $$('.pp-it', pop).forEach(b => b.onclick = () => { pop.close(); on(b.dataset.id); });
        const mb = $('.pp-more', pop); if (mb) mb.onclick = () => { const g = $('.pp-more-g', pop), o = g.hidden; g.hidden = !o; mb.setAttribute('aria-expanded', o); }; }, { width: 440 }); };
  /* 选分类：7 个；选预设：这一类里的全部（第一个是“自动”） */
  $('#pg-cat-b').onclick = () => ppPop($('#pg-cat-b'), PG_CATS.filter(([k]) => PGST.presets.some(p => pgCatOf(p) === k)).map(([k, n]) => [k, n, k === st.cat]),
    k => { if (k === st.cat) return; st.cat = k; st.pick = 'auto'; st.hint = ''; persist(); paintPresets(); paintMsgs(); });
  $('#pg-preset-b').onclick = () => { const L = inCat(), auto = pgAuto({ ...st, pick: 'auto' }, PGST.presets);
    const it = p => [p.id, p.name, st.pick !== 'auto' && p.id === st.preset];
    ppPop($('#pg-preset-b'), [...(L.length > 1 ? [['auto', `自动（本次：${PGST.presets.find(p => p.id === auto)?.name || ''}）`, st.pick === 'auto']] : []), ...L.filter(p => !PG_MORE.has(p.id)).map(it)],
      id => { st.pick = id; persist(); paintPresets(); paintMsgs(); }, L.filter(p => PG_MORE.has(p.id)).map(it)); };
  paintPresets();
  $('#pg-preset').onchange = e => { st.preset = st.pick = e.target.value; st.cat = pgCatOf(PGST.presets.find(p => p.id === st.preset)); persist(); paintPresets(); paintMsgs(); };
  $('#pg-edit').onclick = () => pgPresetEditor(() => { paintPresets(); paintMsgs(); });
  $('#pg-new').onclick = () => { if (PG_RUN) return toast('正在生成，请先停止', true); pgHistSave(); st.msgs = []; st.cur = null; persist(); paintMsgs(); paintHist(); $('#pg-in').focus(); };
  const target = () => PGST.presets.find(x => x.id === st.preset)?.target || '';
  const paintMsgs = () => {
    const box = $('#pg-msgs'); if (!box) return;
    const y0 = box.scrollTop, chat = !(PGST.presets.find(x => x.id === st.preset)?.system || '').trim();
    if (!box.dataset.sb) { box.dataset.sb = '1'; box.addEventListener('scroll', () => { box.dataset.free = box.scrollHeight - box.scrollTop - box.clientHeight > 40 ? '1' : ''; }, { passive: true }); }
    // 2026-11-10 用户：发出第一句后输入框要移到最底部（动画过去）。以前靠 CSS 的 :has(.pg-empty) 判断“空对话（输入框居中）”，
    // 桌面版的 WebView2 内容变了不一定重新判断，输入框就停在中间——改成这里直接给卡片打标记 is-empty，并且从中间滑到底部
    const card = box.closest('.pg-card'), cin = card?.querySelector('.pg-in'), was = card?.classList.contains('is-empty'), now = !st.msgs.length;
    const y1 = was !== now && cin && card.dataset.pp ? cin.getBoundingClientRect().top : null; if (card) card.dataset.pp = '1';  // 刚打开这一页的第一次不动
    if (card) card.classList.toggle('is-empty', now);
    if (y1 != null && !reduceMotion) requestAnimationFrame(() => { const dy = y1 - cin.getBoundingClientRect().top; if (Math.abs(dy) > 4) cin.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.32, .72, 0, 1)' }); });
    if (now) { box.innerHTML = `<div class="pg-empty"><b>${esc(PGST.presets.find(x => x.id === st.preset)?.name || 'AI 助手')}</b></div>`; return; }
    box.innerHTML = st.msgs.map((m, i) => m.role === 'user' ? `<div class="pg-u">${(m.thumbs || (m.thumb ? [m.thumb] : [])).length ? `<div class="pg-u-imgs">${(m.thumbs || [m.thumb]).map((t, k) => `<img class="pg-u-img" src="${t}" alt="" data-mi="${i}" data-k="${k}" title="点击查看大图">`).join('')}</div>` : ''}${esc(m.content)}</div>`
      : `<div class="pg-a${m.err ? ' err' : ''}" data-i="${i}">${m.reasoning?.trim() ? `<details class="pg-think${!m.content && !m.err ? ' live' : ''}"${m.thinkOpen ? ' open' : ''}><summary>${!m.content && !m.err ? pgWaitHead(m) : `<span>已思考${m.thinkSecs ? `（用时 ${m.thinkSecs} 秒）` : ''}</span>`}<svg class="pg-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></summary><div>${esc(m.reasoning)}</div></details>` : ''}
        <div class="pg-txt">${m.content || m.err ? esc(m.content || '') : m.reasoning?.trim() ? '' : pgWaitHead(m)}${m.err ? `<span class="pg-errm">${esc(m.err)}</span>` : ''}</div>
        ${m.err && !m.content && i === st.msgs.length - 1 ? '<div class="row pg-acts"><button type="button" class="btn small" data-r>重新生成</button></div>' : ''}
        ${m.content && !(PG_RUN && PG_RUN.i === i) ? `<div class="row pg-acts">${chat ? '' : `<button type="button" class="btn small" data-f="img" title="填入生图页的提示词">${ICON.wand}用于生图</button><button type="button" class="btn small" data-f="video" title="填入生视频页的提示词">${ICON.wand}用于生视频</button><button type="button" class="btn small" data-f="tts" title="填入配音页的文本">${ICON.wand}用于配音</button>`}
          <button type="button" class="btn small ghost" data-c>复制</button>${m.prompt_trace_id ? '<button type="button" class="pl-ib" data-pi-history title="查看生成时的完整提示词" aria-label="查看生成时的完整提示词">⌕</button>' : ''}${i === st.msgs.length - 1 ? '<button type="button" class="btn small ghost" data-r>重新生成</button>' : ''}${m.secs ? `<span class="tiny">${m.secs} 秒${m.tps ? ` · ${m.tps} tok/s` : ''}${m.pps ? ` · 预填 ${m.pps >= 1000 ? (m.pps / 1000).toFixed(1) + 'k' : m.pps} tok/s` : ''}${m.mtp != null ? ` · MTP ${m.mtp}%` : ''}</span>` : ''}</div>` : ''}</div>`).join('');
    $$('.pg-u-img[data-mi]', box).forEach(im => im.onclick = () => zoomImgs(pgMsgImgs(st.msgs[+im.dataset.mi]), +im.dataset.k));
    $$('.pg-a', box).forEach(el => {
      const m = st.msgs[+el.dataset.i];
      $$('[data-f]', el).forEach(b => b.onclick = () => pgFill(m.content, b.dataset.f));
      const c = $('[data-c]', el); if (c) c.onclick = () => copyText(pgClean(m.content)).then(() => toast('已复制'), e => toast(e.message, true));
      const ph = $('[data-pi-history]', el); if (ph) ph.onclick = () => PromptInspector.show(() => api('/api/prompt/traces/' + encodeURIComponent(m.prompt_trace_id)), { saved: true, source: ph });
      const r = $('[data-r]', el); if (r) r.onclick = () => { st.msgs.splice(+el.dataset.i, 1); persist(); send(); };
      const th = $('.pg-think', el); if (th) th.ontoggle = () => { m.thinkOpen = th.open; };  // 记住展开 / 收起，重画后保持
    });
    pgStick(box, y0);
  };
  renderPrompt.paint = paintMsgs;
  const busy = on => { $('#pg-go').hidden = on; $('#pg-stop').hidden = !on; };
  const chatRequest = messages => ({ preset: st.preset, prompt_input: messages.findLast(m => m.role === 'user')?.prompt_input ?? messages.findLast(m => m.role === 'user')?.content ?? '', messages: messages.filter(m => m.content || m.image || m.images).map(m => ({ role: m.role, content: m.content, image: m.image, images: m.images, video: m.images ? m.video : undefined, labels: m.images ? m.labels : undefined, mats: m.mats, had_image: m.had_image || !!m.thumb })), params: pgParams() });
  PromptInspector.bind($('#pg-in'), () => {
    const input = $('#pg-in').value, imgs = pgImgs();
    let messages = st.msgs.map(m => ({ ...m }));
    if (input.trim() || imgs.length) {
      if (imgs.length) messages = messages.map(m => ({ ...m, image: undefined, images: undefined, had_image: m.had_image || !!m.image || !!m.images }));
      messages.push({ role: 'user', content: input.trim(), images: imgs.length ? imgs.map(x => x.image) : undefined,
        video: imgs[0]?.vt != null ? { dur: imgs[0].vdur, times: imgs.map(x => +x.vt.toFixed(1)) } : undefined,
        labels: imgs.some(x => x.lab) ? imgs.map(x => x.lab || '') : undefined, mats: PG_MATS });
    }
    return api('/api/prompt/preview', { body: { ...chatRequest(messages), prompt_input: input } });
  });
  { const ta = $('#pg-in'), pk = ta?._promptPeek, comp = ta?.closest('.pg-composer');  // 2026-11-09 用户：“查看完整提示词”放到输入框外面的右侧
    if (pk && comp) { pk.closest('.has-prompt-peek')?.classList.remove('has-prompt-peek', 'pi-short'); pk.classList.add('pg-peek');
      const row = document.createElement('div'); row.className = 'pg-in-row'; comp.before(row); row.append(comp, pk); } }
  const send = async () => {
    if (PG_RUN) return;
    if (!PGST.available) {  // 再问一次：模型可能已经好了（草稿和光标都不动）
      const s2 = await api('/api/prompt/status').catch(() => null);
      if (s2 && !s2.error) { PGST = { ...PGST, ...s2 }; pgAvailPaint(); }
      if (!PGST.available) return toast('提示词模型未就绪', true);
    }
    if (!st.cur) st.cur = 'c' + Date.now().toString(36);
    const ta = $('#pg-in'), q = ta.value.trim();
    if (q || pgImgs().length) {
      const um = { role: 'user', content: q, prompt_input: ta.value };
      const L = pgImgs();
      if (L.length) { st.msgs.forEach(m => { if (m.image || m.images) { delete m.image; delete m.images; m.had_image = true; } }); um.images = L.map(x => x.image); um.thumbs = L.map(x => x.thumb); um.thumb = L[0].thumb; if (L[0].vt != null) um.video = { dur: L[0].vdur, times: L.map(x => +x.vt.toFixed(1)) }; if (L.some(x => x.lab)) { um.labels = L.map(x => x.lab || ''); um.shorts = L.map(x => x.short || ''); } L.forEach(x => { if (x.orig) PG_ORIG.set(x.thumb, x.orig); }); PG_IMG = null; pgAttPaint(); }
      if (PG_MATS) { um.mats = PG_MATS; PG_MATS = null; }
      st.msgs.push(um); ta.value = ''; st.draft = ''; ta.dispatchEvent(new Event('input'));
    }
    if (!st.msgs.length || st.msgs[st.msgs.length - 1].role !== 'user') return toast('请先输入需求', true);
    const a = { role: 'assistant', content: '', reasoning: '', t0: Date.now() }; st.msgs.push(a);
    const i = st.msgs.length - 1, ctrl = new AbortController(), gen = VGEN, t0 = Date.now();
    PG_RUN = { ctrl, i }; busy(true); { const b = $('#pg-msgs'); if (b) b.dataset.free = ''; } paintMsgs();
    const tick = setInterval(() => { if (!PG_RUN || PG_RUN.i !== i || a.content) return clearInterval(tick); repaint(true); }, 1000);  // 秒数每秒走一下
    const note = $('#pg-note'); if (note) note.textContent = '';
    let last = 0;
    const repaint = force => { if (!force && Date.now() - last < 80) return; last = Date.now(); const el = $(`#pg-msgs .pg-a[data-i="${i}"]`); if (!el) return paintMsgs();
      const tx = $('.pg-txt', el);
      if (a.content) { if ($('.pg-think.live', el) || !tx) return paintMsgs(); tx.textContent = a.content; }  // 开始出正文：“思考中”换成“推理过程”
      else {
        if (a.reasoning.trim() && !$('.pg-think', el)) return paintMsgs();  // 开始推理：换成可展开的“思考中”
        const sec = $('.pg-sec', el); if (sec) sec.textContent = (a.t0 ? Math.max(0, Math.round((Date.now() - a.t0) / 1000)) : 0) + ' 秒';
      }
      if (a.reasoning.trim()) { const th = $('.pg-think', el); if (th) { const d = $('div', th); if (d.textContent !== a.reasoning) d.textContent = a.reasoning; } }
      const box = $('#pg-msgs'); if (box) pgStick(box); };
    try {
      const r = await fetch('/api/prompt/chat', { method: 'POST', signal: ctrl.signal, headers: { 'Content-Type': 'application/json', 'X-Space': VAULT ? 'v' : 'n' },
        body: JSON.stringify(chatRequest(st.msgs.slice(0, -1))) });
      if (r.status === 409) { vaultCheck(); throw new Error('空间已切换，请重试'); }
      if (!r.ok || !r.body) { let m = ''; try { m = (await r.json()).error; } catch { } throw new Error(/not found/i.test(m || '') || r.status === 404 ? '后台版本过旧，请重启 Studio。' : m || '请求失败 ' + r.status); }
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await rd.read(); if (done) break;
        if (gen !== VGEN) { ctrl.abort(); break; }  // 进出了私密空间：不再往这边写
        buf += dec.decode(value, { stream: true });
        let k; while ((k = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, k).trim(); buf = buf.slice(k + 2);
          if (!line.startsWith('data:')) continue;
          const d = JSON.parse(line.slice(5));
          if (d.type === 'text') { if (!a.content && a.reasoning.trim()) a.thinkSecs = Math.max(1, Math.round((Date.now() - t0) / 1000)); a.content += d.v; if ($('#pg-note')) $('#pg-note').textContent = ''; repaint(); }
          else if (d.type === 'reasoning') { a.reasoning += d.v; if ($('#pg-note') && a.reasoning.trim()) $('#pg-note').textContent = '正在推理…'; repaint(); }
          else if (d.type === 'prompt_trace') a.prompt_trace_id = d.v;
          else if (d.type === 'error') a.err = d.v;
          else if (d.type === 'wait' && $('#pg-note')) $('#pg-note').textContent = d.v;
          else if (d.type === 'done') { a.secs = d.v.seconds; a.tps = d.v.tps; a.pps = d.v.pps; a.mtp = d.v.mtp; }
        }
      }
    } catch (e) { if (e.name !== 'AbortError') a.err = e.message; }
    if (gen !== VGEN) return;
    if (!a.content && !a.err) a.err = '没有生成内容';
    if (!a.secs) a.secs = Math.round((Date.now() - t0) / 100) / 10;
    a.thinkOpen = false;  // 写完了：推理过程自动收起
    if (PG_RUN?.ctrl === ctrl) PG_RUN = null;
    st.msgs = st.msgs.slice(-30); persist(); pgHistSave();
    if ($('#pg-msgs')) { paintHist();
      if (!PG_RUN) busy(false);  // 停下后马上又写了一次：别把新的那次的“停止”按钮藏起来
      paintMsgs(); const n2 = $('#pg-note'); if (n2 && !PG_RUN) n2.textContent = '';
      if (a.content) { PGST.running = true; $('#pg-model').textContent = `${PGST.model} · 已载入`; }  // 真写出来了才算已载入
    }
  };
  $('#pg-go').onclick = send;
  $('#pg-stop').onclick = () => { pgAbort(); };
  const ta = $('#pg-in');
  ta.oninput = () => { st.draft = ta.value; persistSoon(); };
  ta.onkeydown = e => {  // 电脑：Enter 发送、Shift+Enter 换行（和 ChatGPT / Claude 一样）；手机键盘上的回车就是换行
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && (e.ctrlKey || e.metaKey || !MOB())) { e.preventDefault(); send(); }
  };
  const comp = ta.closest('.pg-composer');
  $('#pg-think-b').onclick = () => {
    const on = !pgParams().thinking; st.params = { ...st.params, thinking: on }; persist();
    $('#pg-think-b').classList.toggle('on', on); $('#pg-think-b').setAttribute('aria-pressed', on ? 'true' : 'false');
    const cb = $('#pg-think'); if (cb) { cb.checked = on; if ($('#pg-think-o')) $('#pg-think-o').hidden = !on; }
  };
  $('#pg-att').onclick = () => $('#pg-att-f').click();
  $('#pg-att').oncontextmenu = e => { e.preventDefault(); if (typeof frUseItem !== 'function') return; ctxMenu({ anchor: e.currentTarget }, [{ label: '从电脑选择', icon: ICON.up, on: () => $('#pg-att-f').click() }, frUseItem('用这一帧', async fs => { for (const f of fs) await pgAttach(f); }, true)]); };  // 右键：从视频截取（2026-11-19）
  $('#pg-att-f').onchange = async e => { const fs = [...e.target.files]; e.target.value = ''; for (const f of fs) await pgAttach(f); };  // 可以一次选几张
  ta.addEventListener('paste', async e => { const fs = [...(e.clipboardData?.files || [])].filter(x => x.type.startsWith('image/')); if (fs.length && PGST?.vision) { e.preventDefault(); for (const f of fs) await pgAttach(f); } });
  pgAttPaint();
  const fit = () => {  // 输入框跟着内容长高；一行放不下就换成“文字在上、按钮在下”，清空后回到一行
    if (!ta.value) comp.classList.remove('multi');
    ta.style.height = 'auto';
    if (!comp.classList.contains('multi') && (ta.value.includes('\n') || ta.scrollHeight > ta.clientHeight + 4)) { comp.classList.add('multi'); ta.style.height = 'auto'; }
    ta.style.height = Math.min(220, ta.scrollHeight + 2) + 'px';
  };
  ta.addEventListener('input', fit); fit();
  busy(!!PG_RUN); paintMsgs(); paintHist(); pgSide(); requestAnimationFrame(fitPages);
  if (PG_AUTO) { PG_AUTO = false; if (pgImgs().length && PGST?.vision) setTimeout(() => $('#pg-go')?.click(), 250); else if (PG_IMG) toast('当前提示词模型不支持识图', true); }
}
/* 右边：生成参数 + 引擎设置 */
function pgSide() {
  const box = $('#pg-side'); if (!box) return;
  const st = pgState(), p = pgParams(), D = PGST.gen_defaults || {}, E = PGST.engine || {};
  const rng = (k, label, min, max, step, hint) => `<div class="field"><span class="label">${label}：<b id="pg-${k}-v">${p[k]}</b>${hint ? hintHtml(hint, 'sm') : ''}</span><input type="range" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${p[k]}"></div>`;
  box.innerHTML = `<div class="pg-sd-a"><h3 class="card-title">生成参数</h3>
    ${rng('temperature', '温度', 0, 2, 0.05, '数值越高越富有创造性，但稳定性越低。')}
    ${rng('top_p', 'Top P', 0, 1, 0.01)}
    <div class="ig-2">${['top_k', 'max_tokens'].map(k => `<label class="field"><span class="label">${k === 'top_k' ? 'Top K' : '最大输出 token'}</span><input class="input" type="number" data-n="${k}" value="${p[k]}"></label>`).join('')}</div>
    ${rng('min_p', 'Min P', 0, 1, 0.01)}
    ${rng('presence_penalty', '存在惩罚', -2, 2, 0.05, '数值越高越不易重复相同的词。')}
    ${rng('repeat_penalty', '重复惩罚', 0.5, 2, 0.01)}
    <label class="field"><span class="label">种子${hintHtml('-1 表示随机。固定种子（并将温度调为 0）后，每次输出均相同。', 'sm')}</span><input class="input" type="number" data-n="seed" value="${p.seed}"></label>
    <label class="row ig-check"><input type="checkbox" id="pg-think"${p.thinking ? ' checked' : ''}> 深度思考${hintHtml('先推理再输出：结果更周全，但速度明显变慢。', 'sm')}</label>
    <div id="pg-think-o"${p.thinking ? '' : ' hidden'}><div class="seg" id="pg-effort">${[['low', '低'], ['medium', '中'], ['xhigh', '高']].map(([k, n]) => `<button type="button" data-e="${k}" class="${p.effort === k ? 'on' : ''}">${n}</button>`).join('')}</div>
      <label class="field" style="margin-top:8px"><span class="label">思考预算（token）${hintHtml('思考最多使用的 token 数，用完后开始输出正文。-1 表示不限，0 表示不思考直接输出。', 'sm')}</span><input class="input" type="number" data-n="think_budget" min="-1" max="16384" step="256" value="${p.think_budget ?? -1}"></label></div>
    <details class="pg-more"${S.ui?.pgMore ? ' open' : ''}><summary>${ICON.chev}更多采样参数</summary>
      ${rng('frequency_penalty', '频率惩罚', -2, 2, 0.05, '按出现次数惩罚重复用词。')}
      <div class="ig-2"><label class="field"><span class="label">惩罚范围${hintHtml('重复 / 存在 / 频率惩罚仅考虑最近的若干 token。-1 表示整个上下文，0 表示关闭。', 'sm')}</span><input class="input" type="number" data-n="repeat_last_n" min="-1" max="8192" value="${p.repeat_last_n}"></label>
        <label class="field"><span class="label">Top N Sigma${hintHtml('-1 表示关闭，常用 1~2。', 'sm')}</span><input class="input" type="number" data-f="top_n_sigma" min="-1" max="5" step="0.1" value="${p.top_n_sigma}"></label></div>
      ${rng('typical_p', 'Typical P', 0, 1, 0.01, '1 表示关闭。')}
      <div class="ig-2"><label class="field"><span class="label">动态温度范围${hintHtml('实际温度 = 温度 ± 此值；0 表示关闭。', 'sm')}</span><input class="input" type="number" data-f="dynatemp_range" min="0" max="2" step="0.05" value="${p.dynatemp_range}"></label>
        <label class="field"><span class="label">动态温度指数</span><input class="input" type="number" data-f="dynatemp_exponent" min="0" max="5" step="0.1" value="${p.dynatemp_exponent}"></label></div>
      <div class="ig-2"><label class="field"><span class="label">XTC 概率${hintHtml('按此概率移除最高概率的候选，使文字更具新意。0 表示关闭。', 'sm')}</span><input class="input" type="number" data-f="xtc_probability" min="0" max="1" step="0.05" value="${p.xtc_probability}"></label>
        <label class="field"><span class="label">XTC 阈值</span><input class="input" type="number" data-f="xtc_threshold" min="0" max="0.5" step="0.01" value="${p.xtc_threshold}"></label></div>
      <div class="ig-2"><label class="field"><span class="label">DRY 防复读${hintHtml('惩罚整句或长片段的重复。0 表示关闭，常用 0.8。', 'sm')}</span><input class="input" type="number" data-f="dry_multiplier" min="0" max="5" step="0.05" value="${p.dry_multiplier}"></label>
        <label class="field"><span class="label">DRY 底数</span><input class="input" type="number" data-f="dry_base" min="1" max="4" step="0.05" value="${p.dry_base}"></label></div>
      <div class="ig-2"><label class="field"><span class="label">DRY 允许长度</span><input class="input" type="number" data-n="dry_allowed_length" min="1" max="20" value="${p.dry_allowed_length}"></label>
        <label class="field"><span class="label">DRY 范围${hintHtml('-1 表示整个上下文。', 'sm')}</span><input class="input" type="number" data-n="dry_penalty_last_n" min="-1" max="8192" value="${p.dry_penalty_last_n}"></label></div>
    </details>
    <div class="row" style="justify-content:flex-end;margin-top:8px;gap:6px"><button type="button" class="btn small ghost" id="pg-rec" title="Qwen 官方推荐：思考 1.0 / 0.95 / 20，不思考 0.7 / 0.8 / 20，存在惩罚 1.5">官方推荐</button><button type="button" class="btn small ghost" id="pg-reset">恢复默认</button></div></div>
    <div class="pg-sd-b"><h3 class="card-title">模型设置</h3>
    <div class="tiny" style="margin-bottom:8px">${esc(PGST.model || '')}</div>
    <div class="ig-2"><label class="field"><span class="label">上下文长度${hintHtml('此模型的 KV 缓存很小：8K→16K 仅多占约 0.3GB，32K 约 1.1GB（显存紧张）。修改后将在下次启动模型时生效。', 'sm')}</span><select class="select" id="pg-ctx">${[...new Set([...(PGST.ctx_choices || [4096, 8192, 16384]), ...(E.ctx ? [E.ctx] : [])])].sort((x, y) => x - y).map(n => `<option value="${n}"${E.ctx === n ? ' selected' : ''}>${n % 1024 ? n : n / 1024 + 'K'}${n >= 32768 ? '（显存紧张）' : ''}</option>`).join('')}</select></label>
      <label class="field"><span class="label">KV 缓存精度</span><select class="select" id="pg-kv">${(PGST.kv_types || []).map(k => `<option${E.kv === k ? ' selected' : ''}>${k}</option>`).join('')}</select></label></div>
    <div class="row" style="gap:10px;align-items:center;flex-wrap:wrap"><label class="row ig-check"><input type="checkbox" id="pg-mtp"${E.mtp ? ' checked' : ''}> MTP 加速${hintHtml('模型自带的多 token 预测，输出更快；无法启动时将自动关闭。草稿长度即每次预测的 token 数，接受率高时调大可进一步提速。', 'sm')}</label>
      <span class="row" id="pg-mtp-o" style="gap:6px;align-items:center"${E.mtp ? '' : ' hidden'}><span class="tiny">草稿长度</span><input class="input" type="number" id="pg-dn" min="1" max="8" value="${E.draft_n ?? 3}" style="width:64px"><span class="tiny">最低把握</span><input class="input" type="number" id="pg-dp" min="0" max="1" step="0.05" value="${E.draft_pmin ?? 0}" style="width:70px"></span></div>
    <div class="ig-2"><label class="field"><span class="label">预填批大小${hintHtml('影响读取长提示词、多轮对话和图片时的速度。数值越大预填越快，但占用显存更多。', 'sm')}</span><select class="select" id="pg-ub">${(PGST.ubatch_choices || [256, 512, 1024, 2048]).map(n => `<option value="${n}"${(E.ubatch ?? 512) === n ? ' selected' : ''}>${n}${n === 512 ? '（默认）' : ''}</option>`).join('')}</select></label>
      <div class="field"><span class="label">显存放置${hintHtml('全部放入显存速度最快。显存不足或速度异常缓慢时，请选择“自动适配”：放不下的层将放入内存，不会溢出到共享显存。', 'sm')}</span><div class="seg full" id="pg-gpu">${[['all', '全部放显存'], ['fit', '自动适配']].map(([k, n]) => `<button type="button" data-g="${k}" class="${(E.gpu || 'all') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>
    ${PGST.vision ? `<div class="ig-2"><label class="field"><span class="label">识图 token 下限${hintHtml('每张图至少使用的 token 数：越多识别越细致，反推提示词越准确。0 表示模型默认，建议 1024。', 'sm')}</span><input class="input" type="number" id="pg-imin" min="0" max="16384" step="256" value="${E.img_min ?? 0}"></label>
      <label class="field"><span class="label">识图 token 上限</span><input class="input" type="number" id="pg-imax" min="0" max="16384" step="256" value="${E.img_max ?? 0}"></label></div>` : ''}
    <div class="row" style="justify-content:flex-end"><button type="button" class="btn small" id="pg-free">释放显存</button></div></div>`;
  const save = () => { st.params = Object.fromEntries(Object.entries(pgParams()).filter(([k, v]) => v !== D[k])); persist(); };
  $$('input[type=range][data-k]', box).forEach(r => r.oninput = () => { st.params = { ...st.params, [r.dataset.k]: +r.value }; $(`#pg-${r.dataset.k}-v`).textContent = r.value; save(); });
  $$('input[data-n]', box).forEach(r => r.onchange = () => { const v = parseInt(r.value); st.params = { ...st.params, [r.dataset.n]: isNaN(v) ? D[r.dataset.n] : v }; save(); });
  $$('input[data-f]', box).forEach(r => r.onchange = () => { const v = parseFloat(r.value); st.params = { ...st.params, [r.dataset.f]: isNaN(v) ? D[r.dataset.f] : v }; save(); });
  $('.pg-more', box).ontoggle = e => { S.ui = { ...(S.ui || {}), pgMore: e.target.open }; persist(); };
  $('#pg-rec').onclick = () => { const th = !!pgParams().thinking, R = (PGST.recommended || {})[th ? 'thinking' : 'plain']; if (!R) return; st.params = { ...st.params, ...R }; save(); pgSide(); toast(th ? '已套用官方推荐（思考模式）' : '已套用官方推荐（不思考）'); };
  $('#pg-think').onchange = e => { st.params = { ...st.params, thinking: e.target.checked }; $('#pg-think-o').hidden = !e.target.checked; save(); $('#pg-think-b')?.classList.toggle('on', e.target.checked); };
  $$('#pg-effort button', box).forEach(b => b.onclick = () => { st.params = { ...st.params, effort: b.dataset.e }; $$('#pg-effort button', box).forEach(x => x.classList.toggle('on', x === b)); save(); });
  $('#pg-reset').onclick = () => { st.params = {}; persist(); pgSide(); toast('生成参数已恢复默认'); };
  const eng = async () => {
    $('#pg-mtp-o').hidden = !$('#pg-mtp').checked;
    const n = id => { const el = $(id); return el ? +el.value || 0 : undefined; };
    try { PGST.engine = await api('/api/prompt/engine', { body: { ...E, ctx: +$('#pg-ctx').value, kv: $('#pg-kv').value, mtp: $('#pg-mtp').checked, draft_n: n('#pg-dn') || 3, draft_pmin: n('#pg-dp'), ubatch: +$('#pg-ub').value,
      gpu: $('#pg-gpu button.on')?.dataset.g || 'all', ...(PGST.vision ? { img_min: n('#pg-imin'), img_max: n('#pg-imax') } : {}) } }); Object.assign(E, PGST.engine); toast('已保存，下次启动模型时生效'); } catch (e) { toast(e.message, true); }
  };
  ['#pg-ctx', '#pg-kv', '#pg-mtp', '#pg-dn', '#pg-dp', '#pg-ub', '#pg-imin', '#pg-imax'].forEach(id => { const el = $(id, box); if (el) el.onchange = eng; });
  $$('#pg-gpu button', box).forEach(b => b.onclick = () => { $$('#pg-gpu button', box).forEach(x => x.classList.toggle('on', x === b)); eng(); });
  { const more = $('details.pg-more', box), sm = more && $('summary', more);
    if (sm) { const f = k => $(`[data-k="${k}"]`, box)?.closest('.field'); [f('top_p'), $('[data-n="top_k"]', box)?.closest('label'), f('min_p'), f('presence_penalty'), f('repeat_penalty')].filter(Boolean).reverse().forEach(el => sm.after(el)); }
  }
  $('#pg-free').onclick = async () => { try { await api('/api/prompt/stop', { body: {} }); PGST.running = false; const m = $('#pg-model'); if (m) m.textContent = PGST.model; toast('已释放提示词模型的显存'); } catch (e) { toast(e.message, true); } };
}
/* 预设编辑：左边列表，右边改名字、用途、system prompt；可以新建、复制、删除、恢复默认 */
function pgPresetEditor(done) {
  let list = PGST.presets.map(p => ({ ...p })), cur = list.findIndex(p => p.id === pgState().preset);
  if (cur < 0) cur = 0;
  modal(`<h3 class="card-title" style="margin:0 0 12px">预设（system prompt）</h3>
    <div class="pg-ed"><div class="pg-ed-l" id="pge-list"></div><div class="pg-ed-r" id="pge-form"></div></div>
    <div class="row" style="gap:8px;margin-top:14px;flex-wrap:wrap"><button class="btn small" id="pge-new">＋ 新建</button><button class="btn small" id="pge-dup">复制此预设</button><button class="btn small ghost danger" id="pge-del">删除此预设</button><button class="btn small ghost" id="pge-def">恢复默认预设</button>
      <span class="spacer"></span><button class="btn" data-close>取消</button><button class="btn primary" id="pge-save">保存</button></div>`, box => {
    /* 左边按 7 个分类分组，每组可以折叠；展开了哪些记在 S.ui.pgeOpen，选中的那一项所在的组总是展开 */
    const opened = new Set(S.ui?.pgeOpen || [pgCatOf(list[cur])]);
    const keepOpen = () => { S.ui = { ...(S.ui || {}), pgeOpen: [...opened] }; persist(); };
    const paintList = () => {
      const L = $('#pge-list', box), y = L.scrollTop; if (list[cur]) opened.add(pgCatOf(list[cur]));
      L.innerHTML = PG_CATS.map(([k, n]) => { const its = list.map((p, i) => [p, i]).filter(([p]) => pgCatOf(p) === k); if (!its.length) return '';
        const op = opened.has(k);
        return `<div class="pg-ed-g${op ? ' open' : ''}"><button type="button" class="pg-ed-gh" data-g="${k}" aria-expanded="${op}"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg><span>${n}</span><span class="pg-ed-n">${its.length}</span></button>
          <div class="pg-ed-gb"${op ? '' : ' hidden'}>${its.map(([p, i]) => `<button type="button" class="pg-ed-i${i === cur ? ' on' : ''}" data-i="${i}">${esc(p.name || '（未命名）')}</button>`).join('')}</div></div>`; }).join('');
      L.scrollTop = y;
      $$('.pg-ed-i', L).forEach(b => b.onclick = () => { cur = +b.dataset.i; paint(); });
      $$('.pg-ed-gh', L).forEach(b => b.onclick = () => { const k = b.dataset.g; if (opened.has(k)) opened.delete(k); else opened.add(k);
        const g = b.parentElement, op = opened.has(k); g.classList.toggle('open', op); b.setAttribute('aria-expanded', op); $('.pg-ed-gb', g).hidden = !op; keepOpen(); });
    };
    const paint = () => {
      paintList();
      const p = list[cur], pc = p && pgCatOf(p);
      $('#pge-form', box).innerHTML = p ? `<label class="field"><span class="label">名称</span><input class="input" id="pge-name" value="${esc(p.name)}" maxlength="40"></label>
        <div class="field"><span class="label">主要用途${hintHtml('预设按用途分类显示；在生图、生视频、配音页点击“AI 优化 / AI 撰写”时，也将据此自动选择预设。', 'sm')}</span><div class="seg pge-cats" id="pge-t">${PG_CATS.map(([k, n]) => `<button type="button" data-t="${k}" class="${pc === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
        <label class="field"><span class="label">System prompt</span><textarea class="textarea" id="pge-sys" rows="12" placeholder="说明模型的角色、输出格式及输出内容">${esc(p.system)}</textarea></label>` : '';
      if (!p) return;
      $('#pge-name', box).oninput = e => { p.name = e.target.value; const b = $(`.pg-ed-i[data-i="${cur}"]`, box); if (b) b.textContent = p.name || '（未命名）'; };
      $('#pge-sys', box).oninput = e => { p.system = e.target.value; };
      $$('#pge-t button', box).forEach(b => b.onclick = () => { p.cat = b.dataset.t; p.target = PG_CAT_TARGET[p.cat] ?? ''; $$('#pge-t button', box).forEach(x => x.classList.toggle('on', x === b)); paintList(); $('.pg-ed-i.on', box)?.scrollIntoView({ block: 'nearest' }); });
    };
    paint();
    $('#pge-new', box).onclick = () => { const c = list[cur] ? pgCatOf(list[cur]) : 'chat'; list.push({ id: 'p' + Date.now().toString(36), name: '新预设', cat: c, target: PG_CAT_TARGET[c] ?? '', system: '' }); /* 新建的放在当前所在的分类 */ cur = list.length - 1; paint(); $('#pge-name', box).select(); };
    $('#pge-dup', box).onclick = () => { const p = list[cur]; if (!p) return; list.splice(cur + 1, 0, { ...p, id: 'p' + Date.now().toString(36), name: p.name + ' 副本' }); cur++; paint(); };
    $('#pge-del', box).onclick = () => { if (list.length < 2) return toast('至少需保留一个预设', true); list.splice(cur, 1); cur = Math.max(0, cur - 1); paint(); };
    $('#pge-def', box).onclick = () => { list = (PGST.default_presets || []).map(p => ({ ...p })); cur = 0; paint(); toast('已恢复默认预设（点击保存后生效）'); };
    $('#pge-save', box).onclick = async () => {
      const bad = list.find(p => !p.name.trim()); if (bad) return toast('每个预设都必须有名称（system prompt 可留空，即直接对话）', true);
      try { PGST.presets = await api('/api/prompt/presets', { body: { presets: list } }); if (!PGST.presets.some(p => p.id === pgState().preset)) pgState().preset = PGST.presets[0].id; persist(); box.close(); done?.(); toast('预设已保存'); }
      catch (e) { toast(e.message, true); }
    };
  }, true);
}

/* ================= 语音转文字 ================= */
let sttCur = null;
// 识别语言：Qwen3-ASR 支持 30 种（+ 中文方言），Whisper 支持 99 种（这里列常用的）
const STT_LANG_Q = [['zh', '中文'], ['en', '英语'], ['yue', '粤语'], ['ja', '日语'], ['ko', '韩语'], ['de', '德语'], ['fr', '法语'], ['es', '西班牙语'], ['pt', '葡萄牙语'], ['ru', '俄语'], ['it', '意大利语'], ['ar', '阿拉伯语'],
  ['th', '泰语'], ['vi', '越南语'], ['id', '印尼语'], ['tr', '土耳其语'], ['hi', '印地语'], ['ms', '马来语'], ['nl', '荷兰语'], ['sv', '瑞典语'], ['da', '丹麦语'], ['fi', '芬兰语'], ['pl', '波兰语'], ['cs', '捷克语'],
  ['fil', '菲律宾语'], ['fa', '波斯语'], ['el', '希腊语'], ['hu', '匈牙利语'], ['mk', '马其顿语'], ['ro', '罗马尼亚语']];
const STT_LANG_W = [...STT_LANG_Q.filter(x => x[0] !== 'fil'), ['tl', '菲律宾语'], ['uk', '乌克兰语'], ['he', '希伯来语'], ['no', '挪威语'], ['bg', '保加利亚语'], ['hr', '克罗地亚语'], ['sr', '塞尔维亚语'], ['sk', '斯洛伐克语'],
  ['sl', '斯洛文尼亚语'], ['lt', '立陶宛语'], ['lv', '拉脱维亚语'], ['et', '爱沙尼亚语'], ['ca', '加泰罗尼亚语'], ['bn', '孟加拉语'], ['ta', '泰米尔语'], ['ur', '乌尔都语'], ['sw', '斯瓦希里语'], ['la', '拉丁语']];
const sttOpts = () => (S.ui = S.ui || {}, S.ui.stt = Object.assign({ eng: 'qwen', lang: 'auto', prompt: '', vocal: false, batched: false, batch_size: 8, split: '', compute: 'float32', max_line_width: 0, max_line_count: 0, hotwords: '' }, S.ui.stt || {}));
function sttAdv() {  // Whisper 的高级选项
  const o = sttOpts();
  const box = modal(`<div class="row between" style="margin-bottom:8px"><h3 class="card-title" style="margin:0">Whisper 高级选项</h3><button type="button" class="btn small" data-close>完成</button></div>
    <label class="row ig-check"><input type="checkbox" id="sw-vocal"${o.vocal ? ' checked' : ''}> 先提取人声${hintHtml('先分离背景音乐再识别，影视、歌曲、直播素材识别更准确。首次使用时将自动下载 MDX 模型。', 'sm')}</label>
    <label class="row ig-check"><input type="checkbox" id="sw-bat"${o.batched ? ' checked' : ''}> 批量模式${hintHtml('按语音段批量识别，提速 2~8 倍，长音频质量略有下降。', 'sm')}<span id="sw-bs-r"${o.batched ? '' : ' hidden'} class="row" style="gap:6px;align-items:center;margin-left:8px"><span class="tiny">批大小</span><input class="input" type="number" id="sw-bs" min="1" max="32" value="${o.batch_size}" style="width:64px"></span></label>
    <div class="field"><span class="label">字幕断句</span><div class="seg full" id="sw-split">${[['', '默认'], ['sentence', '按句'], ['asia', '标准亚洲']].map(([k, n]) => `<button type="button" data-k="${k}" class="${o.split === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
    <div class="ig-2"><label class="field"><span class="label">每行最多字数${hintHtml('0 表示不限。', 'sm')}</span><input class="input" type="number" id="sw-mlw" min="0" max="200" value="${o.max_line_width}"></label>
      <label class="field"><span class="label">每条最多行数${hintHtml('0 表示不限。需同时设置每行最多字数。', 'sm')}</span><input class="input" type="number" id="sw-mlc" min="0" max="10" value="${o.max_line_count || 0}"></label></div>
    <div class="ig-2"><label class="field"><span class="label">热词${hintHtml('优先识别的词，以空格分隔。', 'sm')}</span><input class="input" id="sw-hw" maxlength="300" value="${esc(o.hotwords || '')}"></label>
      <label class="field"><span class="label">计算精度${hintHtml('float32 最稳定。float16 / int8_float16 更快、更节省显存，但此显卡可能不支持（失败时请改回 float32）。', 'sm')}</span><select class="select" id="sw-ct">${['float32', 'float16', 'int8_float16', 'auto'].map(k => `<option${o.compute === k ? ' selected' : ''}>${k}</option>`).join('')}</select></label></div>`, null, false);
  const set = (k, v) => { o[k] = v; persist(); };
  $('#sw-vocal', box).onchange = e => set('vocal', e.target.checked);
  $('#sw-bat', box).onchange = e => { set('batched', e.target.checked); $('#sw-bs-r', box).hidden = !e.target.checked; };
  $('#sw-bs', box).onchange = e => set('batch_size', Math.max(1, Math.min(32, parseInt(e.target.value) || 8)));
  $$('#sw-split button', box).forEach(b => b.onclick = () => { set('split', b.dataset.k); $$('#sw-split button', box).forEach(x => x.classList.toggle('on', x === b)); });
  $('#sw-mlw', box).onchange = e => set('max_line_width', Math.max(0, Math.min(200, parseInt(e.target.value) || 0)));
  $('#sw-ct', box).onchange = e => set('compute', e.target.value);
  $('#sw-mlc', box).onchange = e => set('max_line_count', Math.max(0, Math.min(10, parseInt(e.target.value) || 0)));
  $('#sw-hw', box).oninput = e => set('hotwords', e.target.value);
  $$('[data-close]', box).forEach(b => b.onclick = box.close);
}
async function renderSTT() {
  $('#main').innerHTML = `
  <div class="page-head"><div><h1 class="page-title">语音转文字</h1></div>
    <button class="btn" id="llm-set">校对设置</button></div>
  <div class="grid-tts">
    <div class="stack">
      <div class="card">
        <div class="drop" id="sdrop">${ICON.up}<div style="font-weight:600;font-size:15px">拖入音频或视频文件，或点击上传</div></div>
        <input type="file" id="sfile" accept="audio/*,video/*" hidden>
        <div class="row" style="margin-top:14px">
          <span class="tiny">引擎</span>
          <div class="seg" id="s-eng"><button data-e="qwen">Qwen3-ASR</button><button data-e="whisper">Whisper</button></div>
          <span class="tiny">语言</span><select class="select" id="s-lang" style="width:auto"></select>
          <button type="button" class="btn small ghost" id="s-wadv" hidden>高级选项</button>
        </div>
        <div class="row" id="s-prompt-r" style="margin-top:10px" hidden><input class="input" id="s-prompt" placeholder="专有名词 / 背景（可选）：人名、术语、节目名，以逗号分隔" style="flex:1"></div>
      </div>
      <div id="stt-detail"></div>
    </div>
    <div class="side-col"><div class="card"><h3 class="card-title">记录</h3><div id="stt-list" class="segs" style="max-height:none"></div></div></div>
  </div>`;
  { const det = $('#stt-detail'), fit = () => $('#sdrop')?.classList.toggle('big', !det.children.length); new MutationObserver(fit).observe(det, { childList: true }); fit(); }  // 没打开记录：上传区大；打开了：收小
  const so = sttOpts();
  let eng = so.eng === 'whisper' ? 'whisper' : 'qwen';
  const paintEng = () => {
    $$('#s-eng button').forEach(x => x.classList.toggle('on', x.dataset.e === eng));
    const L = eng === 'whisper' ? STT_LANG_W : STT_LANG_Q;
    if (!L.some(x => x[0] === so.lang)) so.lang = so.lang === 'fil' ? 'tl' : so.lang === 'tl' ? 'fil' : 'auto';
    $('#s-lang').innerHTML = `<option value="auto">自动</option>` + L.map(([k, n]) => `<option value="${k}"${so.lang === k ? ' selected' : ''}>${n}</option>`).join('');
    $('#s-wadv').hidden = $('#s-prompt-r').hidden = eng !== 'whisper';
  };
  $$('#s-eng button').forEach(b => b.onclick = () => { if (b.disabled) return; eng = so.eng = b.dataset.e; persist(); paintEng(); });
  $('#s-lang').onchange = e => { so.lang = e.target.value; persist(); };
  $('#s-prompt').value = so.prompt || ''; $('#s-prompt').oninput = e => { so.prompt = e.target.value; persistSoon(); };
  $('#s-wadv').onclick = sttAdv;
  paintEng();
  $('#llm-set').onclick = llmSettings;
  const drop = $('#sdrop'), file = $('#sfile');
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  const send = async f => {
    drop.innerHTML = `<span class="spinner dark"></span><div style="margin-top:8px">正在上传 ${esc(f.name)}…</div>`;
    try {
      const xo = eng === 'whisper' ? { prompt: so.prompt, vocal: so.vocal, batched: so.batched, batch_size: so.batch_size, split: so.split, compute: so.compute, max_line_width: so.max_line_width, max_line_count: so.max_line_count, hotwords: so.hotwords } : {};
      const j = await api(`/api/stt?engine=${eng}&language=${encodeURIComponent($('#s-lang').value)}`, { raw: f, headers: { 'X-Filename': encodeURIComponent(f.name), 'X-Stt-Opts': encodeURIComponent(JSON.stringify(xo)), 'Content-Type': 'application/octet-stream' } });
      sttCur = j.id;
      if (location.pathname === '/stt') renderSTT(); else toast(`「${f.name}」已开始转写，可在“语音转文字”中查看进度`);  // 上传期间去了别的页面：不把这里画到那个页面上
    } catch (e) { toast(e.message, true); if (location.pathname === '/stt') renderSTT(); }
  };
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) send(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && send(file.files[0]);
  libPickRow(drop, send);
  const st = await api('/api/settings').catch(() => ({}));
  if (!$('#stt-list')) return;  // 等设置时去了别的页面：不要动那个页面的刷新
  if (!st.whisper_available) { const w = $('[data-e=whisper]'); w.disabled = true; w.title = '没有找到 PotPlayer 的 Whisper'; if (eng === 'whisper') { eng = 'qwen'; paintEng(); } }
  pageRefresh(['stt'], () => tick());
  const tick = async (stop = () => { }) => {
    const list = await api('/api/stt').catch(() => []);
    const box = $('#stt-list'); if (!box) return stop();
    const lh = list.length ? list.map(j => `<div class="sg ${j.id === sttCur ? 'generating' : ''}" style="grid-template-columns:1fr auto;cursor:pointer" data-open="${j.id}">
      <div><div class="t" style="font-weight:600">${esc(j.filename)}</div><div class="tiny">${fmtTime(j.created)} · ${fmtDur(j.duration)} · ${j.engine === 'whisper' ? 'Whisper' : 'Qwen3-ASR'} · ${j.state === 'done' ? j.chars + ' 字' : esc(j.message)}${jobTimer(j, 'sm')}</div></div>
      <div>${j.state === 'running' ? '<span class="spinner dark"></span>' : ''}</div></div>`).join('') : '<div class="tiny">暂无记录</div>';
    if (box.dataset.html !== lh) { box.innerHTML = lh; box.dataset.html = lh; }
    $$('[data-open]', box).forEach(el => el.onclick = () => { sttCur = el.dataset.open; showStt(); tick(); });
    if (list.length && !list.some(j => j.id === sttCur)) sttCur = list[0].id;  // 没选 / 选的那条已经删了：选最新的
    const cur = list.find(j => j.id === sttCur);
    if (cur && (cur.state !== 'running') && !$('#stt-text') && $('#stt-detail') && !$('#stt-detail').dataset.live) showStt();
    if (cur && cur.state === 'running' && $('#stt-detail') && $('#stt-detail').dataset.live !== cur.id) {
      $('#stt-detail').dataset.live = cur.id;
      $('#stt-detail').innerHTML = `<div class="card"><b>${esc(cur.filename)}</b><div id="stt-live"></div></div>`;
      const stop = liveLog($('#stt-live'), cur.id, '正在转写');
      (async () => { const det0 = $('#stt-detail'); while (true) { await sleep(1000); if ($('#stt-detail') !== det0) return stop(); const x = await api('/api/stt/' + cur.id).catch(() => null); if (!x || x.state !== 'running') break; } await stop(); const d = $('#stt-detail'); if (!d) return; d.dataset.live = ''; showStt(); })();
    }
    if (!list.some(j => j.state === 'running')) stop();
  };
  await pollStart(tick, 1500);
}

async function showStt() {
  const j = await api('/api/stt/' + sttCur).catch(() => null);
  const box = $('#stt-detail'); if (!box || !j) return;
  if (j.state === 'error') { box.innerHTML = `<div class="card"><b>${esc(j.filename)}</b><div class="tiny" style="color:var(--red)">${esc(j.message)}</div><button class="btn small ghost danger" id="s-del" style="margin-top:8px">删除记录</button></div>`; $('#s-del').onclick = () => delStt(j); return; }
  if (j.state === 'running') return;
  box.innerHTML = `<div class="card">
    <div class="row between"><div><h3 class="card-title">${esc(j.filename)}</h3><div class="tiny">${fmtDur(j.duration)} · ${j.engine === 'whisper' ? 'Whisper' : 'Qwen3-ASR 1.7B'} · <span id="s-count"></span></div></div>
      <div class="row"><button class="btn small" id="s-copy">复制全文</button><a class="btn small" href="/media/stt/${j.id}/transcript.txt?dl=1" id="s-dl">${ICON.dl}TXT</a>${j.has_srt ? `<a class="btn small" href="/media/stt/${j.id}/transcript.srt?dl=1">${ICON.dl}SRT 字幕</a>` : ''}<button class="btn small primary" id="s-tts" title="追加到配音页正文末尾">＋ 加入配音</button><button class="btn small ghost danger" id="s-del">删除</button></div></div>
    <textarea class="textarea" id="stt-text" style="min-height:320px;font-size:15px;margin-top:12px"${j.text?.trim() ? '' : ' placeholder="未识别到人声（可能为纯音乐或静音）。也可在此处直接输入文字。"'}>${esc(j.text)}</textarea>
    <div class="row" style="margin-top:6px"><span class="tiny" id="s-saved">修改将自动保存</span></div>
    <div class="hr"></div>
    <h3 class="card-title"><span class="ttl-ico">${ICON.wand}</span>AI 校对</h3>
    <div class="card-sub">由大模型根据上下文修正明显的识别错误（同音字、人名、术语、标点），不改写内容。改动将高亮显示，确认后再替换。</div>
    <div class="field"><span class="label">背景信息（可选，可大幅提高人名和术语的准确率）</span><input class="input" id="s-bg" placeholder="例如：这是一段关于考研数学的讲课，主讲人张宇；书名《海底两万里》"></div>
    <div class="row"><button class="btn grad" id="s-fix"><span class="wave"></span><span class="lbl">${ICON.wand}一键 AI 校对</span></button><button class="btn" id="s-prompt" title="复制完整提示词，可粘贴到任意 AI 对话">复制给 AI（无需 API）</button><span class="tiny" id="s-llm"></span></div>
    <div id="s-diff"></div>
  </div>`;
  const ta = $('#stt-text');
  PromptInspector.bind($('#s-bg'), async () => {
    const background = $('#s-bg').value;
    const r = await api('/api/stt/prompt', { body: { text: ta.value, background } });
    return { input: background, stages: [{ label: 'AI 校对完整提示词', text: r.prompt }], notes: [], templates: ['STT_SYS'] };
  }, { tpl: { pages: ['stt'] } });
  const count = () => $('#s-count').textContent = ta.value.replace(/\s/g, '').length + ' 字';
  count();
  let saveT = null;
  ta.oninput = () => { count(); clearTimeout(saveT); $('#s-saved').textContent = '正在保存…'; saveT = setTimeout(async () => { const m = $('#s-saved'); try { await api('/api/stt/' + j.id, { method: 'PATCH', body: { text: ta.value } }); if (m) m.textContent = '已保存'; } catch (e) { if (m) m.textContent = '保存失败（再次修改时将重试）'; toast('保存失败：' + e.message, true); } }, 600); };
  $('#s-copy').onclick = async () => { await copyText(ta.value); toast('已复制到剪贴板'); };
  $('#s-tts').onclick = () => appendToDub(ta.value);
  $('#s-del').onclick = () => delStt(j);
  const st = await api('/api/settings').catch(() => ({}));
  const ready = st.llm_provider === 'local' ? true : st.llm_provider === 'anthropic' ? st.anthropic_api_key_set : !!(st.openai_base_url && st.openai_model);
  $('#s-llm').innerHTML = ready ? `使用：${st.llm_provider === 'local' ? '本地 Qwen3.8 27B（离线）' : st.llm_provider === 'anthropic' ? 'Claude · ' + esc(st.anthropic_model) : esc(st.openai_model)}` : '<a href="#" id="s-cfg">尚未设置 API，点击此处设置</a>';
  if ($('#s-cfg')) $('#s-cfg').onclick = e => { e.preventDefault(); llmSettings(); };
  $('#s-prompt').onclick = async () => {
    const r = await api('/api/stt/prompt', { body: { text: ta.value, background: $('#s-bg').value } });
    await copyText(r.prompt); toast('提示词已复制，可粘贴到任意 AI 对话中；再将结果粘贴回上方的文本框');
  };
  $('#s-fix').onclick = async () => {
    if (!ready) return llmSettings();
    const btn = $('#s-fix'); btn.disabled = true; btn.classList.add('busy'); btn.innerHTML = '<span class="wave"></span><span class="lbl"><span class="spinner"></span>AI 正在校对…</span>';
    const op = newOp(), stop = liveLog($('#s-diff'), op, 'AI 校对');
    try {
      const r = await api(`/api/stt/${j.id}/correct`, { body: { text: ta.value, background: $('#s-bg').value, op } });
      await stop(false);
      if (!$('#s-diff')) return;
      const changes = r.ops.filter(o => o[0] !== 'eq').length;
      $('#s-diff').innerHTML = `<div class="cand" style="margin-top:14px"><div class="row between"><b>校对结果 · ${changes ? `${changes} 处改动` : '未发现需要修改之处'}</b>
        <div class="row"><button class="btn small primary" id="s-acc" ${changes ? '' : 'disabled'}>全部采用</button><button class="btn small" id="s-cpy2">复制校对稿</button><button class="btn small" id="s-add2">＋ 校对稿加入配音</button></div></div>
        <div class="tiny"><span style="background:rgba(255,59,48,.15);text-decoration:line-through;padding:0 3px;border-radius:4px">删除内容</span> <span style="background:rgba(52,199,89,.2);padding:0 3px;border-radius:4px">修改内容</span></div>
        <div style="white-space:pre-wrap;line-height:1.9;font-size:15px;max-height:420px;overflow:auto">${r.ops.map(([op, t]) => op === 'eq' ? esc(t) : op === 'del' ? `<span style="background:rgba(255,59,48,.15);text-decoration:line-through;color:#b3261e">${esc(t)}</span>` : `<span style="background:rgba(52,199,89,.22);color:#146c2e">${esc(t)}</span>`).join('')}</div></div>`;
      $('#s-acc').onclick = () => { ta.value = r.corrected; ta.oninput(); $('#s-diff').innerHTML = ''; toast('已采用校对稿'); };
      $('#s-cpy2').onclick = async () => { await copyText(r.corrected); toast('已复制校对稿'); };
      $('#s-add2').onclick = () => appendToDub(r.corrected);
    } catch (e) { await stop(); toast(e.message, true); }
    btn.disabled = false; btn.classList.remove('busy'); btn.innerHTML = `<span class="wave"></span><span class="lbl">${ICON.wand}一键 AI 校对</span>`;
  };
}
function appendToDub(text) {
  text = (text || '').trim();
  if (!text) return toast('没有可加入的文字', true);
  const had = S.text.trim();
  S.text = had ? S.text.replace(/\s+$/, '') + '\n\n' + text : text;
  persist(); go('tts');
  toast(had ? `已追加到原有内容之后（+${text.length} 字）` : `已加入配音（${text.length} 字）`);
  setTimeout(() => { const ta = $('#script'); if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = ta.value.length; ta.scrollTop = ta.scrollHeight; } }, 80);
}
async function delStt(j) {
  if (!await confirmBox('删除此记录？', '', '删除', true)) return;
  try { await api('/api/stt/' + j.id, { method: 'DELETE' }); sttCur = null; renderSTT(); } catch (e) { toast(e.message, true); }
}

async function llmSettings() {
  const st = await api('/api/settings');
  const PRE = [
    { k: 'deepseek', n: 'DeepSeek', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    { k: 'qwen', n: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
    { k: 'openai', n: 'OpenAI', url: 'https://api.openai.com/v1', model: '' },
    { k: 'ollama', n: '本地 Ollama', url: 'http://127.0.0.1:11434/v1', model: '' },
  ];
  modal(`<h3 class="card-title">AI 校对设置</h3>
    <div class="card-sub">密钥仅保存在本机的 D:\\AI-TTS\\studio\\settings.json 中。校对时文字将发送给所选的服务商（本地 Ollama 除外）。</div>
    <div class="seg full" id="lp" style="margin-bottom:14px"><button data-p="anthropic" class="${st.llm_provider === 'anthropic' ? 'on' : ''}">Claude</button><button data-p="openai_compat" class="${st.llm_provider === 'openai_compat' ? 'on' : ''}">OpenAI 兼容接口</button><button data-p="local" class="${st.llm_provider === 'local' ? 'on' : ''}">本地模型（离线）</button></div>
    <div id="lp-l" class="help" style="margin-bottom:10px">使用本机的提示词模型（Qwen3.8 27B）校对：无需联网，无需密钥。首次使用需先载入模型（约 20 秒），校对期间将占用显卡。</div>
    <div id="lp-a">
      <div class="field"><span class="label">Claude API Key ${st.anthropic_api_key_set ? `<small>已设置 ${esc(st.anthropic_api_key_hint)} · <a href="#" data-clr="anthropic_api_key">清除</a></small>` : ''}</span><input class="input" id="a-key" type="password" placeholder="${st.anthropic_api_key_set ? '留空则不修改' : 'sk-ant-…（在 console.anthropic.com 创建）'}"></div>
      <div class="field"><span class="label">模型</span><select class="select" id="a-model">${[['claude-opus-5-5', 'Claude Opus 5.5（默认，最准）'], ['claude-sonnet-5-5', 'Claude Sonnet 5.5（更便宜）'], ['claude-haiku-5-5', 'Claude Haiku 5.5（最便宜最快）']].map(([v, n]) => `<option value="${v}" ${st.anthropic_model === v ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <div class="help">Opus / Sonnet 已开启官方的“误拒自动回退”：若某段内容被安全机制误拦，将自动改用备用模型重试。</div></div>
    </div>
    <div id="lp-o">
      <div class="chips" style="margin-bottom:10px">${PRE.map(p => `<button class="chip" data-pre="${p.k}">${p.n}</button>`).join('')}</div>
      <div class="field"><span class="label">接口地址（OpenAI 兼容）</span><input class="input" id="o-url" value="${esc(st.openai_base_url)}" placeholder="https://…/v1"></div>
      <div class="field"><span class="label">API Key ${st.openai_api_key_set ? `<small>已设置 ${esc(st.openai_api_key_hint)} · <a href="#" data-clr="openai_api_key">清除</a></small>` : ''}</span><input class="input" id="o-key" type="password" placeholder="${st.openai_api_key_set ? '留空则不修改' : '本地 Ollama 可不填'}"></div>
      <div class="field"><span class="label">模型名</span><input class="input" id="o-model" value="${esc(st.openai_model)}" placeholder="按服务商文档填写"></div>
    </div>
    <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-close>取消</button><button class="btn primary" id="l-ok">保存</button></div>`, box => {
    let prov = st.llm_provider || 'anthropic';
    const clr = new Set();
    $$('[data-clr]', box).forEach(a => a.onclick = e => { e.preventDefault(); clr.add(a.dataset.clr); a.closest('small').textContent = '保存后将清除'; });
    const show = () => { $('#lp-a', box).style.display = prov === 'anthropic' ? '' : 'none'; $('#lp-o', box).style.display = prov === 'openai_compat' ? '' : 'none'; const lpl = $('#lp-l', box); if (lpl) lpl.style.display = prov === 'local' ? '' : 'none'; $$('#lp button', box).forEach(b => b.classList.toggle('on', b.dataset.p === prov)); };
    show();
    $$('#lp button', box).forEach(b => b.onclick = () => { prov = b.dataset.p; show(); });
    $$('[data-pre]', box).forEach(b => b.onclick = () => { const p = PRE.find(x => x.k === b.dataset.pre); $('#o-url', box).value = p.url; if (p.model) $('#o-model', box).value = p.model; });
    $('#l-ok', box).onclick = async () => {
      const body = { llm_provider: prov, anthropic_model: $('#a-model', box).value, openai_base_url: $('#o-url', box).value, openai_model: $('#o-model', box).value };
      if ($('#a-key', box).value.trim()) body.anthropic_api_key = $('#a-key', box).value.trim();
      if ($('#o-key', box).value.trim()) body.openai_api_key = $('#o-key', box).value.trim();
      for (const k of clr) if (!body[k]) body[k] = '';  // 点了“清除”：把保存的密钥删掉
      try { await api('/api/settings', { body }); } catch (e) { return toast('保存失败：' + e.message, true); }
      box.close(); toast('已保存'); if ($('#stt-text')) showStt();
    };
  });
}

/* ================= 说明 ================= */
function renderHelp() {
  const ev = models.find(m => m.family === 'breeze_tts')?.profile?.events;
  const fam = k => models.find(m => m.family === k);
  $('#main').innerHTML = `<div class="page-head"><div><h1 class="page-title">使用说明</h1></div></div>
  <div class="card help-doc">
    <h2>1. 先准备一个音色</h2>
    <p>前往 <a href="/voices" data-page="voices">音色库</a>，有三种方法：</p>
    <ul><li><b>用描述设计</b>：输入一句描述，例如“一位四十岁的男性旁白，声音低沉有磁性”，选择 Breeze 或 Qwen3 进行设计，一次生成多个候选，从中选择一个保存。</li>
    <li><b>上传音频 / 视频</b>：拖入 MP3/MP4，播放并找到一段 5~15 秒、仅有一人说话且无背景音乐的片段，点击“从当前播放位置开始”，再点击“截取并识别”；如有背景音乐，截取后点击“去除背景声”以仅保留人声。文字将自动识别，核对错字后即可保存。</li>
    <li><b>录音</b>：对着麦克风朗读一段文字。</li></ul>
    <p>音色库中的音色<b>适用于所有支持克隆的模型</b>。克隆结果的整体腔调会偏向参考音频的语气；如需朗读剧本、旁白，请选择语气平稳的片段。</p>

    <h2>2. 如何选择模型</h2>
    <table><tr><th>模型</th><th>擅长</th><th>功能</th></tr>
    <tr><td><b>Breeze TTS 2</b></td><td>中文自然度和表演力最佳，位列开源排行榜第一</td><td>纯克隆、导演模式（用一句话控制语气）、音色设计、[笑] 等声音事件</td></tr>
    <tr><td><b>IndexTTS-2.5</b>${fam('index_tts2') ? '' : '（未安装）'}</td><td>中文克隆相似度高，情绪与音色解耦</td><td>纯克隆、情绪控制（一句话描述或 8 维情绪滑杆，强度是真实参数）、&lt;字|拼音&gt; 指定读音</td></tr>
    <tr><td><b>Qwen3-TTS 1.7B</b>${fam('qwen3_tts') ? '' : '（未安装）'}</td><td>稳定、多语言，北京话 / 四川话预设</td><td>纯克隆（官方 Base 不接受语气指令）、音色设计、9 个官方预设音色 + 语气指令</td></tr></table>

    <h2>3. 生成方式（网页会自动判断）</h2>
    <table><tr><th>方式</th><th>触发条件</th><th>效果</th></tr>
    <tr><td><span class="pill green">纯克隆</span></td><td>已选音色，导演中未做任何选择</td><td>官方原版克隆，最贴近参考音频的音色、节奏和情绪</td></tr>
    <tr><td><span class="pill blue">导演模式</span></td><td>已选音色，并选择情绪 / 表演方式或填写指令</td><td>同一声音，改变情绪与演绎方式（Breeze / IndexTTS）</td></tr>
    <tr><td><span class="pill purple">音色设计</span></td><td>选择“不使用音色”，仅填写描述</td><td>根据描述创造全新的声音；长文本建议先保存为音色再使用</td></tr>
    <tr><td><span class="pill blue">预设音色</span></td><td>在 Qwen3 中选择一个官方预设</td><td>官方内置声音，可加语气指令</td></tr></table>

    <h2>4. 文本中的控制标记</h2>
    <p><b>声音事件（Breeze）</b>：<code>她看了我一眼[笑]，没说话。</code> 官方支持 ${(ev?.official || []).map(e => `<code>${esc(e.tag)}</code>`).join(' ')}，可尝试 ${(ev?.experimental || []).map(e => `<code>${esc(e.tag)}</code>`).join(' ')}。${esc(ev?.note || '')}</p>
    <p><b>指定读音（IndexTTS-2.5）</b>：<code>我去&lt;银行|yin2 hang2&gt;取钱</code>，数字表示声调。可使用工具栏中的“标注读音”插入。</p>
    <p><b>停顿（所有模型通用）</b>：<code>你真的以为[停顿 1.5秒]我会放过你吗？</code> 网页会在此处切分并插入精确时长的静音，标记本身不会被朗读。仅写 <code>[停顿]</code> 时默认为 0.8 秒。可使用工具栏中的“插入停顿”一键插入。</p>
    <p><b>Qwen3-TTS 的限制</b>：不支持声音事件标签，也不能在句中插入指令；指令仅对整段生效，且仅在“音色设计”和“预设音色”下有效（官方克隆模型不接受指令）。如需“挑逗地嘲笑一声”这类效果，请使用 Breeze：段首写 <code>{挑逗、带着嘲讽}</code>，再在需要笑声的位置插入 <code>[笑]</code>。</p>
    <p><b>某一段的语气（所有支持指令的模型）</b>：在段首写 <code>{委屈得快哭了，小声地说}</code>，仅作用于该段，并与全文的语气叠加。IndexTTS 会将其作为情绪描述。</p>

    <h2>5. 导演：控制表达方式</h2>
    <p>右侧“导演”面板会根据模型自动变化：Breeze 为一句话指令（情绪 + 表演方式 + 语速 + 自由书写），指令可以写得非常具体，例如“说到‘等等’时突然惊恐，倒吸一口气”；IndexTTS 为情绪控制，强度滑杆即模型的真实参数 emotion_alpha，开启“精确调配”后可分别调节 8 种情绪。</p>
    <p class="muted">Breeze 没有“开心程度 0~100”这类数值旋钮，情绪强弱依靠措辞表达，网页的滑杆会将其转换为不同强度的措辞。</p>

    <h2>6. 长文本（10~30 分钟）</h2>
    <ul><li>网页<b>优先将整个自然段一次生成</b>，段落超过“每段最长字数”（默认 200 字）时才在句号处切分，语气更连贯。</li>
    <li>每段均使用<b>同一参考音色</b>，因此全程音色不会漂移。</li>
    <li>拼接时先去除每段首尾多余的静音，再按“句间停顿 / 段落停顿”插入自然停顿。</li>
    <li>每段生成后自动通过语音识别核对，读错、漏读的段落将<b>自动更换种子重做</b>；如仍不满意，可在“分段详情”中单独重做，或修改个别字词后重做。</li>
    <li>生成在后台进行，可关闭此页面，并在 <a href="/works" data-page="works">作品</a> 中查看进度和下载。</li></ul>

    <h2>7. 语音转文字</h2>
    <p>前往 <a href="/stt" data-page="stt">语音转文字</a> 上传音频或视频。<b>Qwen3-ASR</b> 中文识别更准确、速度很快；<b>Whisper</b> 使用 PotPlayer 自带的 large-v3-turbo，可同时导出 SRT 字幕。识别完成后可直接编辑、复制或下载 TXT。</p>
    <p><b>AI 校对</b>：在“AI 校对设置”中填写 Claude 或其他服务商的 API Key，点击“一键 AI 校对”，大模型将根据上下文改正同音字、人名、术语和标点（不改写内容），改动高亮显示，确认后再替换。填写“背景信息”（人名、书名、术语）效果更佳。如不使用 API，可点击“复制给 AI”，粘贴到 Claude / ChatGPT 网页版即可。</p>

    <h2>8. 换声：亲自演绎，转换为他人的声音</h2>
    <p>前往 <a href="/vc" data-page="vc">换声</a>，上传一段录音（或现场录制），选择音色库中的目标音色，点击“开始换声”。<b>说话内容、语气、停顿、节奏均保持录音原样</b>，仅替换嗓音，男女互换时音高会自动调整到目标声音的音域。适合对话、台词等对语气要求较高的场景：例如“嗯？”的上扬方式，只需亲自读出即可。</p>
    <ul><li>长度不限，10~30 分钟的录音会在语句间最安静处自动切分为约 10 秒的小块转换，再按原时间轴拼接，成品与原录音时长相同。</li>
    <li>每块转换后自动通过语音识别核对，吞字、变字的块将更换种子重做；也可在“分块详情”中单独重做某一块。通过成品下方的“⇄ 对比原声”可逐句对比。</li>
    <li>原录音应尽量干净：仅有一人说话，无背景音乐和回声。录音中含糊的部分，转换后同样会含糊。</li>
    <li>模型为 Seed-VC（无需训练）。网页默认使用实测吞字最少的 v1 · XLSR + HiFT 路线，可在高级参数中切换到官方默认的 v2。</li></ul>
    <h2>9. 播放页：音源库</h2>
    <ul><li>将音频、视频、图片放入音源库文件夹后，<a href="/play" data-page="play">播放</a>页左侧将按文件夹列出；新放入的文件数十秒内自动显示。</li>
    <li>列表右上角的按钮可切换排序（默认 / 最新 / 最大 / 名称）和显示方式（列表 / 封面网格），每个文件夹分别记忆。</li>
    <li>右键文件：播放、下一首播放、加入播放列表、在资源管理器中显示、删除（移到回收站）；右键文件夹：播放全部、在资源管理器中打开、删除文件夹（移到回收站）。</li>
    <li>长音频、视频会记忆上次的播放位置；有字幕时可点击字幕跳转、搜索字幕或翻译。键盘：↑ ↓ 选择，回车播放，空格暂停，/ 搜索。</li>
    <li>左下角齿轮中的“手机访问”：手机安装 Tailscale 并登录同一账号，配对后即可在手机上使用全部功能（包括私密空间）；“在资源管理器中打开”及修改手机访问设置仅能在电脑上操作。</li></ul>

    <h2>10. 生图</h2>
    <ul><li>前往 <a href="/img" data-page="img">生图</a>，输入画面描述（中英文均可），选择尺寸和张数，点击“生成”（也可按 Ctrl + 回车）。首次使用需先载入模型，约 10~30 秒，之后 1024 尺寸的图片每张约 8~15 秒。</li>
    <li>可选多个模型（Z-Image Turbo、Krea 2、Qwen-Image 2.1、MOSS、H3-Image 等），均在本机运行，无需联网。</li>
    <li>如需在满意的图片上微调：将鼠标移到图片上并点击“使用此组设置”，提示词、尺寸、种子将全部填回，修改个别字词后再生成，画面会非常接近。</li>
    <li>生成的图片位于下方图库中，打开大图后可左右翻页，按 I 查看提示词和种子；“存入音源库”后，也可在播放页的“AI 生图”文件夹中查看。私密空间中生成的图片仅保存在私密空间内。</li>
    <li>生图与配音轮流使用显卡：配音 / 换声 / 识别需要显卡时，生图会在完成当前图片后让出显卡，其余图片待对方使用完毕后自动继续生成；生图引擎闲置 5 分钟后也会自动退出并释放显存。</li>
    <li>请勿未经本人同意使用真人的肖像生成图片。</li></ul>

    <h2>11. 视频功能一览</h2>
    <p>生视频 / 改视频各功能默认使用的模型、LoRA、提示词与做法（生视频页标题旁的按钮里也能看到）。</p>
    ${typeof vidGoalTable === 'function' ? '<h3>快速对照：想做什么 → 去哪里</h3>' + vidGoalTable() + (typeof vidFitTable === 'function' ? '<h3>每个功能适合什么、不适合什么</h3>' + vidFitTable() : '') + '<h3>详细</h3>' : ''}${typeof vidFuncTable === 'function' ? vidFuncTable('') : ''}

    <h2>12. 高级参数</h2>
    <p>右侧“高级参数”根据引擎的官方说明自动生成，默认值即官方默认值，不修改即为原版效果，每一项下方均有中文说明。今后添加其他模型后，在右上角切换即可，参数面板会自动切换为该模型的参数。</p>

    <h2>13. 使用技巧</h2>
    <ul><li>某句朗读效果不佳时：先更换随机种子，再尝试调低“表现力”。</li>
    <li>多音字读错时：IndexTTS 可使用 &lt;字|拼音&gt;；其他模型可将该字替换为同音字，并在分段详情中重做该段。</li>
    <li>“试听”仅生成选中的文字（未选中时试听第一段），可用于快速调整语气。</li>
    <li>切换模型后首次生成需多等待几秒（加载模型）。不使用时，可在左下角齿轮的“显存”中点击“释放”，或退出应用，以释放显卡内存。</li></ul>

    <h2>14. 许可提醒</h2>
    <p class="muted">Breeze TTS 2 权重仅限个人、研究和非商业用途；IndexTTS-2.5 使用 bilibili 模型许可（禁止用输出训练其他模型）；Qwen3-TTS 为 Apache 2.0；Seed-VC 为 GPL-3.0。仅可克隆本人或已获本人同意的声音，请勿用于冒充他人。</p>
  </div>`;
}

/* ================= 启动 ================= */
async function loadVoices() { voices = await api('/api/voices').catch(() => []); if (S.voice && !curPreset() && !voices.some(v => v.id === S.voice)) S.voice = null; }
/* 进度条悬停预览：鼠标停在视频的进度条上，上方显示那一刻的画面和时间。
   用一个看不见、静音的视频去跳到那个时间点取一帧；鼠标移得快时只取最新的位置，不会排长队。 */
const TH = { v: null, want: null, busy: false, tip: null };
function thumbTip() {
  if (TH.tip) return TH.tip;
  const d = document.createElement('div'); d.className = 'thumb-tip'; d.hidden = true;
  d.innerHTML = '<canvas width="208" height="117"></canvas><span></span>';
  document.body.append(d); TH.tip = d; return d;
}
function thumbGrab() {
  if (TH.busy || !TH.want) return;
  const { t, src } = TH.want; TH.want = null;
  if (!TH.v) { TH.v = document.createElement('video'); TH.v.muted = true; TH.v.preload = 'auto'; TH.v.playsInline = true; }
  const v = TH.v; TH.busy = true;
  let fin = false;
  const done = () => {
    if (fin) return; fin = true; TH.busy = false;
    const c = $('canvas', thumbTip());
    if (v.videoWidth) { c.height = Math.round(c.width * v.videoHeight / v.videoWidth); c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); }
    thumbGrab();
  };
  const seek = () => { v.addEventListener('seeked', done, { once: true }); v.currentTime = Math.max(0, t); setTimeout(done, 900); };
  if (v.getAttribute('src') !== src) { v.src = src; v.addEventListener('loadedmetadata', seek, { once: true }); setTimeout(done, 2500); }
  else seek();
}
function bindThumb(track, getDur) {
  if (!track) return;
  const hide = () => { if (TH.tip) TH.tip.hidden = true; };
  track.addEventListener('pointermove', e => {
    const isVid = PB.a === qAudio && PB.meta?.video && qAudio.getAttribute('src');
    const d = getDur(); if (!isVid || !d) return hide();
    const r = track.getBoundingClientRect(), p = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), t = p * d;
    const tip = thumbTip(); tip.hidden = false;
    $('span', tip).textContent = fmtT(t);
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(innerWidth - w - 8, Math.max(8, e.clientX - w / 2)) + 'px';
    tip.style.top = Math.max(8, r.top - h - 12) + 'px';
    TH.want = { t, src: qAudio.currentSrc || qAudio.src }; thumbGrab();
  });
  track.addEventListener('pointerleave', hide);
  track.addEventListener('pointerdown', () => setTimeout(hide, 0));
}
/* ================= 精简模式 =================
   页面右上角的小按钮：应用 → 整个窗口缩成一条小播放器（没有标题栏、浮在最前面，可以拖到任何地方）；
   网页 → 打开一个画中画小窗（总在最前面）。点左边的封面返回完整界面。
   中间：鼠标移上去显示 上一首 / 播放 / 下一首 / 播放列表 / 字幕；不移上去显示当前这句字幕（没有字幕就一直显示按钮）。
   字幕、播放列表展开后往下延伸，可以滚动、查找，点一句跳过去。 */
const CP_H = 60, cpW = () => S.cpW || 340, cpDH = () => S.cpDrawerH || 280;
let CP = null;  // { doc, root, win（网页的画中画窗口）, drawer: null | 'subs' | 'queue', key, sents, state }
const CPI = {
  queue: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 6h11M4 12h11M4 18h7"/><path d="M18 14v6M15 17h6"/></svg>',
  subs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 11h4M13 11h4M7 15h7M16 15h1"/></svg>',
  pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3.5h6M10 3.5v5.2L6.8 12.4h10.4L14 8.7V3.5M12 12.4V20.5"/></svg>',
  min: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 12h12"/></svg>',
  expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7"/></svg>',
  open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="15" rx="3"/><rect x="11.5" y="12" width="7" height="5" rx="1.4" fill="currentColor" stroke="none"/></svg>',
};
function cpHtml(inApp) {
  const pb = n => $(`[data-pb="${n}"]`)?.innerHTML || '';
  return `<div class="cp" id="cp">
    <div class="cp-main${inApp ? ' has-win' : ''}">
      <button type="button" class="cp-art" data-cp="restore" title="返回完整界面"><span class="cp-art-in"></span><span class="cp-art-x">${CPI.expand}</span></button>
      <div class="cp-mid"><div class="cp-title"></div>
        <div class="cp-stage"><div class="cp-line"></div>
          <div class="cp-ctl"><button type="button" data-cp="subs" title="字幕">${CPI.subs}</button><button type="button" data-cp="prev" title="上一首">${pb('prev')}</button><button type="button" data-cp="play" title="播放 / 暂停"></button><button type="button" data-cp="next" title="下一首">${pb('next')}</button><button type="button" data-cp="queue" title="播放列表">${CPI.queue}</button></div></div></div>
      ${inApp ? `<div class="cp-win"><button type="button" data-cp="pin" title="始终在最前面">${CPI.pin}</button><button type="button" data-cp="x" title="关闭（隐藏到右下角托盘，音乐继续播放）">${ICON.x}</button></div>` : ''}
    </div>
    <div class="cp-prog"><i></i></div>
    <div class="cp-drawer" hidden></div></div>`;
}
const cpApp = () => !!window.pywebview?.api?.compact;
async function compactOpen() {
  if (CP) return;
  if (cpApp()) {
    let host = $('#cp-host'); if (!host) { host = document.createElement('div'); host.id = 'cp-host'; document.body.append(host); }
    host.hidden = false; host.innerHTML = cpHtml(true);
    document.body.classList.add('compact');
    CP = { doc: document, root: $('#cp', host), inApp: true, top: S.cpTop !== false };
    await window.pywebview.api.compact(true, cpW(), CP_H, CP.top).catch(() => { });
  } else if (window.documentPictureInPicture) {
    const win = await documentPictureInPicture.requestWindow({ width: cpW(), height: CP_H }).catch(e => { toast('无法打开精简模式：' + e.message, true); return null; });
    if (!win) return;
    const st = win.document.createElement('style');
    st.textContent = 'html,body{margin:0;height:100%;overflow:hidden;background:#1c1c1f}' + [...document.styleSheets].map(s => { try { return [...s.cssRules].map(r => r.cssText).join('\n'); } catch { return ''; } }).join('\n');
    win.document.head.append(st); win.document.title = 'Studio';
    win.document.documentElement.dataset.theme = document.documentElement.dataset.theme;
    win.document.body.innerHTML = cpHtml(false);
    CP = { doc: win.document, root: win.document.getElementById('cp'), win, inApp: false };
    win.addEventListener('pagehide', () => { if (CP?.win === win) cpClosed(); }, { once: true });
    win.addEventListener('keydown', e => { if (e.key === ' ' && !e.target.closest('input')) { e.preventDefault(); $('[data-pb="play"]').click(); } });
  } else return toast('此浏览器不支持精简模式（需要新版 Chrome / Edge）', true);
  cpBind(); cpPaint(true);
}
async function compactClose() {
  if (!CP) return;
  const c = CP;
  if (c.inApp) { cpClosed(); await window.pywebview.api.compact(false).catch(() => { }); }
  else { cpClosed(); try { c.win.close(); } catch { } window.focus(); }
}
function cpClosed() {
  const c = CP; CP = null; if (!c) return;
  if (c.inApp) { document.body.classList.remove('compact'); const h = $('#cp-host'); if (h) { h.hidden = true; h.innerHTML = ''; } requestAnimationFrame(() => { pbLayout(); miniSync(); }); }
}
function cpBind() {
  const c = CP, r = c.root, q = s => r.querySelector(s);
  const click = n => $(`[data-pb="${n}"]`)?.click();
  q('[data-cp="restore"]').onclick = compactClose;
  q('[data-cp="prev"]').onclick = () => click('prev');
  q('[data-cp="next"]').onclick = () => click('next');
  q('[data-cp="play"]').onclick = () => click('play');
  q('[data-cp="queue"]').onclick = () => cpDrawer(c.drawer === 'queue' ? null : 'queue');
  q('[data-cp="subs"]').onclick = () => cpDrawer(c.drawer === 'subs' ? null : 'subs');
  // 最下面那条进度可以点 / 拖（2026-11-18：以前只能看）
  { const pr = q('.cp-prog'), seek = ev => { const a = PB.a, d = a && isFinite(a.duration) ? a.duration : 0, rc = pr.getBoundingClientRect(); if (!d || !rc.width || extOn()) return; keySeek(a, Math.max(0, Math.min(1, (ev.clientX - rc.left) / rc.width)) * d); cpPaint(); };
    pr.addEventListener('pointerdown', ev => { if (ev.button !== 0) return; ev.preventDefault(); ev.stopPropagation(); pr.setPointerCapture?.(ev.pointerId); pr.classList.add('drag'); seek(ev);
      const mv = e => seek(e), up = () => { pr.classList.remove('drag'); pr.removeEventListener('pointermove', mv); pr.removeEventListener('pointerup', up); pr.removeEventListener('pointercancel', up); };
      pr.addEventListener('pointermove', mv); pr.addEventListener('pointerup', up); pr.addEventListener('pointercancel', up); }); }
  if (c.inApp) {
    q('[data-cp="x"]').onclick = () => window.pywebview.api.compact_hide().catch(() => { });
    const pin = q('[data-cp="pin"]'); pin.classList.toggle('on', c.top);
    pin.onclick = () => { c.top = !c.top; S.cpTop = c.top; persist(); pin.classList.toggle('on', c.top); pin.title = c.top ? '始终在最前面：开' : '始终在最前面：关'; window.pywebview.api.compact_pin(c.top).catch(() => { }); };
    // 按住空白处拖动整个小窗口（交给系统拖，跟手）
    q('.cp-main').addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target.closest('button')) return;
      const sx = e.clientX, sy = e.clientY;
      const mv = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) > 4) { off(); window.pywebview.api.compact_drag().catch(() => { }); } };
      const off = () => { removeEventListener('pointermove', mv); removeEventListener('pointerup', off); };
      addEventListener('pointermove', mv); addEventListener('pointerup', off);
    });
  }
}
async function cpDrawer(kind) {
  const c = CP; if (!c) return;
  c.drawer = kind;
  const box = c.root.querySelector('.cp-drawer');
  c.root.querySelector('[data-cp="queue"]').classList.toggle('on', kind === 'queue');
  c.root.querySelector('[data-cp="subs"]').classList.toggle('on', kind === 'subs');
  const h = CP_H + (kind ? cpDH() : 0);
  if (c.inApp) await window.pywebview.api.compact_size(innerWidth, h, !!kind).catch(() => { });
  else try { c.win.resizeTo(c.win.outerWidth, c.win.outerHeight - c.win.innerHeight + h); } catch { }
  box.hidden = !kind;
  cpDrawerPaint();
}
function cpDrawerPaint() {
  const c = CP; if (!c || !c.drawer) return;
  const box = c.root.querySelector('.cp-drawer');
  if (c.drawer === 'queue') { box.innerHTML = `<div class="cp-q">${qListHtml()}</div>`; qBind(box); return; }
  const a = PB.a;
  if (!a || !PB.meta?.subsKey) { box.innerHTML = '<div class="cp-empty">此音频没有字幕</div>'; return; }
  if (c.state === 'done' && c.sents?.length) {
    if (box.querySelector('.subs-host')?._key === c.key) return;
    box.innerHTML = '<div class="subs-host"></div>'; const host = box.querySelector('.subs-host'); host._key = c.key;
    subsWidget(host, c.sents, a, { lyrics: true, off: () => +(S.ui?.subOff?.[c.key] || 0) }); return;  // 2026-11-18 用户：精简模式的字幕照全屏播放页的歌词式（当前句亮、别的暗，不要时间和“逐行 / 段落 / 全文”），时间调节一起生效
  }
  if (c.state === 'running') { box.innerHTML = '<div class="cp-empty">正在生成字幕…</div>'; return; }
  box.innerHTML = `<div class="cp-empty">${c.state === 'done' ? '未识别到人声' : '尚无字幕'}${c.state === 'done' ? '' : '<br><button type="button" class="btn small primary" data-cpgen>生成字幕</button>'}</div>`;
  const g = box.querySelector('[data-cpgen]');
  if (g) g.onclick = async () => { c.state = 'running'; cpDrawerPaint(); cpSubs(await api('/api/play/subs?key=' + encodeURIComponent(c.key), { body: {} }).catch(() => ({ state: 'error' }))); };
}
function cpSubs(r) {  // 取到字幕状态：完成就显示；还在生成就过一会儿再问
  const c = CP; if (!c) return;
  c.state = r.state; c.sents = r.state === 'done' ? r.sents : null;
  if (r.state === 'running') { const k = c.key; setTimeout(async () => { if (CP && CP.key === k) cpSubs(await api('/api/play/subs?key=' + encodeURIComponent(k)).catch(() => ({ state: 'error' }))); }, 2000); }
  cpLine(); cpDrawerPaint();
}
function cpLine() {
  const c = CP; if (!c) return;
  const line = c.root.querySelector('.cp-line'), a = PB.a, tm = a?.currentTime || 0;
  let txt = '';
  if (c.sents?.length) { let s = null; for (const x of c.sents) { if (x.s <= tm + .05) s = x; else break; } if (s && tm <= s.e + 1.2) txt = s.text; }
  c.root.classList.toggle('nosub', !c.sents?.length);
  if (line.dataset.t !== txt) { line.dataset.t = txt; line.innerHTML = txt ? `<span>${esc(txt)}</span>` : ''; }
}
function cpPaint(withMeta) {
  const c = CP; if (!c) return;
  const a = PB.a, m = PB.meta || {}, r = c.root;
  const ex = extOn() ? PB.ext : null, paused = ex ? ex.paused : !a || a.paused;
  const pb = r.querySelector('[data-cp="play"]'); const ic = paused ? 'play' : 'pause';
  if (pb.dataset.icon !== ic) { pb.dataset.icon = ic; pb.innerHTML = ICON[ic]; }
  const d = ex ? ex.d : (a && isFinite(a.duration) ? a.duration : 0), t = ex ? ex.t : (a?.currentTime || 0);
  r.querySelector('.cp-prog i').style.width = (d ? Math.min(100, t / d * 100) : 0) + '%';
  if (withMeta || r.querySelector('.cp-title').dataset.k !== (m.title || '')) {
    const tt = r.querySelector('.cp-title'); tt.dataset.k = m.title || '';
    tt.textContent = a ? (m.title || '音频') + (m.sub ? ' · ' + m.sub : '') : '未在播放';
    r.querySelector('.cp-art-in').innerHTML = a ? artHtml(m, 44, a.dataset.orbkey || '') : '';
    if (c.win) c.win.document.title = VAULT ? 'Studio' : (m.title || 'Studio');
    const key = m.subsKey || '';
    if (key !== c.key) {
      c.key = key; c.sents = null; c.state = key ? 'loading' : 'none';
      if (key) api('/api/play/subs?key=' + encodeURIComponent(key)).then(cpSubs, () => cpSubs({ state: 'error' }));
      cpLine(); cpDrawerPaint();
    }
    if (c.drawer === 'queue') cpDrawerPaint();
  }
  cpLine();
}
window.compactRestore = () => { if (CP?.inApp) cpClosed(); };
/* 精简模式下拖边改了宽度 / 字幕区高度：记住，下次打开还是这么大 */
let cpRt = 0;
addEventListener('resize', () => {
  if (!CP?.inApp) return;
  clearTimeout(cpRt); cpRt = setTimeout(() => {
    if (!CP) return;
    S.cpW = Math.round(innerWidth);
    if (CP.drawer && innerHeight > CP_H + 100) S.cpDrawerH = Math.round(innerHeight - CP_H);
    persist();
  }, 300);
});  // 应用：窗口被系统恢复成正常大小时（比如双击任务栏）

/* 应用：系统标题栏去掉了，右上角是自己画的一排按钮（精简模式 / 最小化 / 最大化 / 关闭），和 Windows 的样式一致；
   拖顶部空白处移动窗口（可以贴边分屏），双击最大化；最上面 4 像素可以拖着改高度 */
function appChrome() {
  if (appChrome.done || !window.pywebview?.api?.win_drag) return;
  appChrome.done = true;
  const A = window.pywebview.api;
  document.body.classList.add('in-app');  // 不能叫 app：.app 是页面左右两栏的布局
  document.documentElement.classList.add('in-app');
  const I = {
    min: '<svg viewBox="0 0 10 10"><path d="M0 5h10" stroke="currentColor" stroke-width="1"/></svg>',
    max: '<svg viewBox="0 0 10 10"><rect x=".5" y=".5" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="1"/></svg>',
    restore: '<svg viewBox="0 0 10 10"><rect x=".5" y="2.5" width="7" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="1"/><path d="M2.5 2.5V1.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-1" fill="none" stroke="currentColor" stroke-width="1"/></svg>',
    x: '<svg viewBox="0 0 10 10"><path d="M.5.5l9 9M9.5.5l-9 9" stroke="currentColor" stroke-width="1"/></svg>',
  };
  const tb = document.createElement('div'); tb.className = 'tb'; tb.id = 'tb';
  tb.innerHTML = `<button type="button" data-tb="cp" title="精简模式">${CPI.open}</button><button type="button" data-tb="min" title="最小化">${I.min}</button><button type="button" data-tb="max" title="最大化">${I.max}</button><button type="button" data-tb="x" class="tb-x" title="关闭">${I.x}</button>`;
  const edge = document.createElement('div'); edge.className = 'tb-edge';
  const strip = document.createElement('div'); strip.className = 'tb-strip';  // 最上面一整行的底色：滚上去的内容被它遮住
  document.body.append(strip, tb, edge);
  const side = $('.rail'), fitStrip = () => { strip.style.left = (side && getComputedStyle(side).display !== 'none' ? Math.round(side.getBoundingClientRect().right) : 0) + 'px'; };  // 只盖右边内容区，不压在左边导航栏上
  fitStrip(); addEventListener('resize', fitStrip); if (side && window.ResizeObserver) new ResizeObserver(fitStrip).observe(side);
  $('[data-tb="cp"]', tb).onclick = compactOpen;
  $('[data-tb="min"]', tb).onclick = () => A.win_min();
  $('[data-tb="max"]', tb).onclick = () => A.win_max().then(paint);
  $('[data-tb="x"]', tb).onclick = () => A.win_close();
  const paint = async () => {
    const st = await A.win_state().catch(() => ({})) || {};
    const was = document.body.classList.contains('app-fs');
    document.body.classList.toggle('app-max', !!st.max); document.body.classList.toggle('app-fs', !!st.fs);
    if (was !== !!st.fs) { fitVideo(); npTabsPlace(); }
    const b = $('[data-tb="max"]', tb); b.innerHTML = st.max ? I.restore : I.max; b.title = st.max ? '向下还原' : '最大化';
  };
  let pt = 0; addEventListener('resize', () => { clearTimeout(pt); pt = setTimeout(paint, 120); }); paint();
  // 鼠标碰到右上角最上边（14 像素以内）时浮出，移开 0.5 秒后收起；刚打开应用时先露 2 秒，让人知道它在哪
  let hideT = 0;
  const show = ms => { clearTimeout(hideT); hideT = 0; tb.classList.add('show'); if (ms) hideT = setTimeout(() => { tb.classList.remove('show'); hideT = 0; }, ms); };
  document.addEventListener('pointermove', e => {
    const hot = e.clientY < 14 && e.clientX > innerWidth - 240, over = tb.contains(e.target);
    if (hot || over) show(0);
    else if (tb.classList.contains('show') && !hideT) hideT = setTimeout(() => { tb.classList.remove('show'); hideT = 0; }, 500);
  }, { passive: true });
  document.addEventListener('pointerleave', () => { if (tb.classList.contains('show')) { clearTimeout(hideT); hideT = setTimeout(() => { tb.classList.remove('show'); hideT = 0; }, 500); } });

  document.addEventListener('fullscreenchange', () => setTimeout(paint, 300));
  // 顶部 32 像素的空白处：按住拖动窗口，双击最大化 / 还原（按钮、输入框等照常可以点）
  const NODRAG = 'button, a, input, textarea, select, label, [contenteditable], .seg, .ps-item, .pl-row, .vmini, .pop, .modal-bg, .np-stage, .np-right, .sub, .chip, .tb, .tb-edge';
  const band = e => (e.clientY < 32 || e.target.classList?.contains('tb-strip')) && !CP && !document.body.classList.contains('app-fs') && !e.target.closest(NODRAG);
  // 按住后挪动超过 3 像素才交给系统拖动（单击、双击照常是网页自己的事件）；双击最大化 / 还原
  document.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !band(e)) return;
    const sx = e.clientX, sy = e.clientY;
    const off = () => { removeEventListener('pointermove', mv, true); removeEventListener('pointerup', off, true); };
    const mv = ev => { if (!(ev.buttons & 1)) return off(); if (Math.hypot(ev.clientX - sx, ev.clientY - sy) > 3) { off(); A.win_drag(); } };
    addEventListener('pointermove', mv, true); addEventListener('pointerup', off, true);
  }, true);
  document.addEventListener('dblclick', e => { if (band(e)) A.win_max().then(paint); }, true);
  edge.addEventListener('pointerdown', e => { if (e.button !== 0) return; e.preventDefault(); A.win_edge(e.clientX < 8 ? 'topleft' : e.clientX > innerWidth - 8 ? 'topright' : 'top'); });
}
/* 视频掉帧监测：放视频时每 4 秒看一次掉了多少帧；明显掉帧时把当时的情况（哪个界面、窗口多大、播放到哪）记到服务器的
   outputs/play-diag.log，方便查“偶尔卡一下”到底是什么时候、在干什么的时候发生的 */
let diagPrev = null, diagLast = 0;
setInterval(() => {
  const a = PB.a;
  if (VAULT || !a || a !== qAudio || !PB.meta?.video || a.paused || !a.getVideoPlaybackQuality) { diagPrev = null; return; }
  const q = a.getVideoPlaybackQuality(), now = { f: q.totalVideoFrames, d: q.droppedVideoFrames, t: a.currentTime };
  const p = diagPrev; diagPrev = now;
  if (!p || now.f <= p.f) return;
  const drop = now.d - p.d, frames = now.f - p.f;
  if (drop < 6 || drop / frames < .03 || Date.now() - diagLast < 15000) return;
  diagLast = Date.now();
  const np = $('#np'), where = !np.hidden ? (np.classList.contains('fs') ? '全屏' : np.classList.contains('theater') ? '播放页铺满' : '播放页') : MINI_OUT ? '弹出小窗' : MINI.classList.contains('dock') ? '贴底栏' : !MINI.hidden ? '悬浮小窗' : '只有声音';
  api('/api/diag', { body: { dropped: drop, frames, at: Math.round(now.t), where, page: location.pathname, win: innerWidth + 'x' + innerHeight, hidden: document.hidden, focus: document.hasFocus(),
    title: PB.meta?.title, video: a.videoWidth + 'x' + a.videoHeight, hover: !!document.querySelector(':hover > .np-ctl, .np:not(.idle)'), subs: !!NP.sents?.length } }).catch(() => { });
}, 4000);
/* 用 PotPlayer 打开当前视频（从当前位置接着放）：特别重的视频（比如 4K 120 帧）在这里还卡时的退路。
   音频也可以（2026-11-17 用户）：网页的声音要经过 Windows 混音，PotPlayer 能用 WASAPI 独占、原采样率输出（入口在播放页的 ⋯ 里） */
let EXT_OK = false;  // 装了 PotPlayer、在电脑上（不是手机）
const EXT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-8 8"/><path d="M11 5H6.5A2.5 2.5 0 0 0 4 7.5v10A2.5 2.5 0 0 0 6.5 20h10a2.5 2.5 0 0 0 2.5-2.5V13"/></svg>';
async function openExternal() {
  const x = qCur(); if (!x?.subsKey) return;
  const t = qAudio.currentTime; qAudio.pause();
  await api('/api/play/external', { body: { key: x.subsKey, t } }).then(() => toast('已在 PotPlayer 中打开'), e => toast('无法打开：' + e.message, true));
}
function bindVolume() {
  const r = $('#vol'), b = $('#vol-btn'), t = $('#vol-v'), pop = $('#vol-pop'), mb = $('#vol-mute'); if (!r) return;
  const nt = $('#np-vtrack'), nf = $('#np-vfill'), nk = $('#np-vknob'), nm = $('#np-vmute');  // 全屏播放页的音量条
  const icon = v => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/>${v === 0 ? '<path d="M17 9l5 6M22 9l-5 6"/>' : `<path d="M16.5 9.5a3.5 3.5 0 0 1 0 5"/>${v > .5 ? '<path d="M19 7a7 7 0 0 1 0 10"/>' : ''}`}</svg>`;
  // 竖条上的静音键：实心喇叭，显示当前状态（没静音 = 声波，静音 = 红色 ×），和播放栏的描边喇叭是不同的一对
  const icon2 = m => `<svg viewBox="0 0 24 24"><path d="M3.5 9.2v5.6c0 .4.3.7.7.7h3.1l4.6 3.9c.5.4 1.1.1 1.1-.5V5.1c0-.6-.6-.9-1.1-.5L7.3 8.5H4.2c-.4 0-.7.3-.7.7z" fill="currentColor"/>${m ? '<path d="M16.5 9.5l5 5M21.5 9.5l-5 5" fill="none" stroke="#ff453a" stroke-width="2.2" stroke-linecap="round"/>' : '<path d="M16 9a4.2 4.2 0 0 1 0 6M18.6 6.4a8 8 0 0 1 0 11.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'}</svg>`;
  // 全屏播放页的喇叭（照 Apple Music）：实心喇叭，静音 = ×，其余按音量 1 / 2 / 3 道声波
  const arc = d => `<path d="${d}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`;
  const icon3 = v => `<svg viewBox="0 0 24 24"><path d="M3.5 9.2v5.6c0 .4.3.7.7.7h3.1l4.6 3.9c.5.4 1.1.1 1.1-.5V5.1c0-.6-.6-.9-1.1-.5L7.3 8.5H4.2c-.4 0-.7.3-.7.7z" fill="currentColor"/>${v === 0 ? arc('M16 9.5l5 5M21 9.5l-5 5') : arc('M15.2 10.2a2.6 2.6 0 0 1 0 3.6') + (v > .33 ? arc('M17.6 8a5.8 5.8 0 0 1 0 8') : '') + (v > .66 ? arc('M20 5.8a9 9 0 0 1 0 12.4') : '')}</svg>`;
  const paint = () => {
    const v = S.muted ? 0 : vol();
    r.value = vol(); r.style.setProperty('--p', (S.muted ? 0 : vol()) * 100 + '%');
    b.innerHTML = icon(v); t.textContent = S.muted ? '静音' : Math.round(vol() * 100) + '%';
    mb.innerHTML = icon2(!!S.muted); mb.title = S.muted ? '取消静音' : '静音'; mb.classList.toggle('on', !!S.muted);
    b.classList.toggle('on', !pop.hidden);
    if (nt) { nf.style.width = v * 100 + '%'; nt.setAttribute('aria-valuenow', Math.round(v * 100)); nt.setAttribute('aria-valuetext', S.muted ? '静音' : Math.round(v * 100) + '%');
      nk.style.left = v * 100 + '%'; nm.innerHTML = icon3(v); nm.title = nm.ariaLabel = S.muted ? '取消静音' : '静音'; nm.classList.toggle('on', !!S.muted); }
  };
  window.volPaint = paint;  // 在视频上调了音量：这里也重画
  const set = x => { S.volume = Math.round(Math.min(1, Math.max(0, x)) * 100) / 100; S.muted = false; persist(); applyVolume(); paint(); };
  r.oninput = () => set(+r.value);
  mb.onclick = () => { S.muted = !S.muted; if (!S.muted && vol() === 0) S.volume = .8; persist(); applyVolume(); paint(); };
  // 点音量键：弹出 / 收起竖条；点别处或按 Esc 收起
  const close = () => { if (pop.hidden) return; pop.hidden = true; paint(); };
  b.onclick = e => { e.stopPropagation(); pop.hidden = !pop.hidden; paint(); };
  document.addEventListener('pointerdown', e => { if (!e.target.closest('#vol-ctl')) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  // 鼠标放在音量键或竖条上滚动滚轮：每格 5%
  $('#vol-ctl').addEventListener('wheel', e => { e.preventDefault(); set((S.muted ? 0 : vol()) + (e.deltaY < 0 ? .05 : -.05)); }, { passive: false });
  if (nt) {
    // 全屏播放页：点哪儿就到哪儿、按住拖动（手机上点一下就生效）；滚轮每格 5%；方向键 5%
    const at = e => { const q = nt.getBoundingClientRect(); return (e.clientX - q.left) / Math.max(1, q.width); };
    nt.addEventListener('pointerdown', e => {
      if (e.button) return; e.preventDefault(); e.stopPropagation(); nt.setPointerCapture?.(e.pointerId); nt.classList.add('drag'); set(at(e));
      const mv = ev => set(at(ev)), up = () => { nt.classList.remove('drag'); nt.removeEventListener('pointermove', mv); nt.removeEventListener('pointerup', up); nt.removeEventListener('pointercancel', up); };
      nt.addEventListener('pointermove', mv); nt.addEventListener('pointerup', up); nt.addEventListener('pointercancel', up);
    });
    nt.addEventListener('keydown', e => { const d = { ArrowRight: .05, ArrowUp: .05, ArrowLeft: -.05, ArrowDown: -.05 }[e.key]; if (d == null) return; e.preventDefault(); e.stopPropagation(); set((S.muted ? 0 : vol()) + d); });
    $('#np-vol').addEventListener('wheel', e => { e.preventDefault(); e.stopPropagation(); set((S.muted ? 0 : vol()) + (e.deltaY < 0 ? .05 : -.05)); }, { passive: false });
    nm.onclick = mb.onclick;
  }
  paint();
}
/* 滚动时不让鼠标下面的行一行行亮起来（2026-11-17 用户：滚动时文件不停地高亮；参照 Google 等）：
   滚轮一动就给 html 加 .is-scrolling，行的悬停样子先压住（CSS；行照样能点），停手 220 毫秒后去掉——这时鼠标下面那一行才亮。
   做法来自 Paul Lewis / Ryan Seddon 的“滚动时关掉 hover”（css-tricks.com/turn-hovers-scroll），只作用在行上，滚动的框本身照常接滚轮。
   手机没有悬停，不用。另外鼠标快速划过时不闪：行的高亮晚 70 毫秒出现（CSS transition-delay，同 hoverIntent 的思路） */
(() => {
  let t = 0; const root = document.documentElement;
  addEventListener('wheel', () => {
    if (root.classList.contains('ph')) return;
    if (!root.classList.contains('is-scrolling')) root.classList.add('is-scrolling');
    clearTimeout(t); t = setTimeout(() => root.classList.remove('is-scrolling'), 220);
  }, { passive: true, capture: true });
})();
(async function init() {
  applyTheme(false);
  bindVolume(); bindPlayerBar(); bindGear(); bindNowPlaying(); bindMini();
  // 新打开的应用 / 标签页（这次还没在这里进过私密空间）：先把上次留下的私密空间凭证退掉，再读任何数据。
  // 以前这一步排在后面：手机上次没退出私密空间时，第一个请求就被服务器拒绝（页面以为在普通空间，凭证却是私密的），整个页面一直卡在加载，
  // 重进几次后又被“已在别的窗口打开”直接带进私密空间。现在每次重新打开都从普通空间开始，要进私密空间得重新输密钥
  { const v0 = await fetch('/api/vault/status').then(r => r.json()).catch(() => ({})), tab = sessionStorage.getItem('vaultTab');
    // 2026-11-17 审查 F20：浏览器里新开的标签页不再退出私密空间（Cookie 是共用的，会把别的标签页的私密会话也撤了）：这个页面按普通空间用，服务器按 X-Space 只给普通内容。
    // 只有桌面应用重新打开（LAUNCH）时才把上次留下的私密凭证退掉
    if (v0.vault && !tab && LAUNCH && NEW_SESSION) await fetch('/api/vault/lock', { method: 'POST' }).catch(() => { });
    // 刷新 / 重启 Studio 时本来就在私密空间：先认下来，后面的请求才不会因为“空间对不上”被拒、整个页面卡在加载
    if (v0.vault && tab) VAULT = true;
    // 这个标签页之前在私密空间、但私密空间已经失效：它留在本标签页的生图 / 生视频草稿是私密的，不能带到普通空间
    if (!v0.vault && tab) { sessionStorage.removeItem('vaultTab'); sessionStorage.removeItem('igDraft'); sessionStorage.removeItem('vdDraft'); } }
  const st0 = await api('/api/status').catch(() => ({}));
  REMOTE = !!st0.remote; VK = st0.vk || null; VKS = st0.vks || '';
  if (!REMOTE) api('/api/play/external').then(r => {  // 播放页右上角：用 PotPlayer 打开（只有装了 PotPlayer、在电脑上用时才有）
    if (!r.potplayer) return;
    EXT_OK = true;
    const b = document.createElement('button'); b.type = 'button'; b.className = 'np-x vid-only'; b.id = 'np-ext'; b.title = '用 PotPlayer 打开（从当前位置继续播放）';
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-8 8"/><path d="M11 5H6.5A2.5 2.5 0 0 0 4 7.5v10A2.5 2.5 0 0 0 6.5 20h10a2.5 2.5 0 0 0 2.5-2.5V13"/></svg>';
    b.onclick = openExternal;
    const ref = $('#np-pip'); if (ref) ref.before(b);
  }, () => { });
  if (REMOTE) document.body.classList.add('remote');  // 手机上：功能都能用，只是没有“在资源管理器中打开”、PotPlayer、精简模式这些电脑上的
  addEventListener('pywebviewready', appChrome); if (window.pywebview?.api?.win_drag) appChrome();
  const cpb = $('#cp-open');  // 页面右上角：精简模式
  if (cpb) { cpb.innerHTML = CPI.open; cpb.onclick = compactOpen; cpb.hidden = !('pywebview' in window || window.documentPictureInPicture); addEventListener('pywebviewready', () => { cpb.hidden = false; }); }
  const qDur = () => extOn() ? PB.ext.d : (isFinite(qAudio.duration) ? qAudio.duration : 0);
  bindThumb($('#pb-track'), qDur); bindThumb($('#np-track'), qDur);
  let vs = !!(await api('/api/vault/status').catch(() => ({}))).vault;
  if (vs && !sessionStorage.getItem('vaultTab')) vs = false;  // 新打开的标签页：不沿用私密空间（按普通空间用，不去撤别的标签页的会话，F20）
  vaultSwitchUI(vs); spaceSwap(); if (vs) await vprefsLoad();
  window.BOOTED = true;
  setInterval(refreshStatus, 5000); await Promise.race([refreshStatus(), sleep(8000)]);  // 第一次没回来也不卡住整个页面
  try { models = await api('/api/models'); } catch (e) { toast('读取模型失败：' + e.message, true); }
  if (models.length && !models.some(m => m.key === S.model || (m.ids || []).includes(S.model))) S.model = models[0].key;
  else if (models.length) S.model = curModel().key;
  await loadVoices();
  if (NEW_SESSION) history.replaceState({}, '', '/play');  // 重新打开应用：总是从播放页开始
  go(location.pathname.slice(1), false);  // 地址里没有页面时 go 会换成播放页（地址栏也改成 /play）
})();

/* 改录音（腾讯 AuK-Flash，audioedit.py）：放一段录音，选改法（替换 / 在后面加 / 在前面加 / 删掉 / 自己写），一句话改里面的字，声音和语气照原来的。
   指令按 AuK 官方中文模板拼：把‘原文’改成‘新文’、在‘锚点’后面加上‘内容’、删掉‘内容’ */
const AE_KINDS = [['replace', '替换'], ['insert_after', '在后面添加'], ['insert_before', '在前面添加'], ['remove', '删除'], ['custom', '自定义']];
const AE_LAB = { replace: ['原文（录音中要替换的文字）', '替换为'], insert_after: ['在以下文字之后', '添加'], insert_before: ['在以下文字之前', '添加'], remove: ['要删除的文字', ''], custom: ['指令（例如：把语速放慢一点 / 语气更开心）', ''] };
const AE = { kind: 'replace', a: '', b: '', secs: '', src: null };
const AE_TPL = { replace: ['AE_REPLACE', '把‘{a}’改成‘{b}’'], insert_after: ['AE_AFTER', '在‘{a}’后面加上‘{b}’'], insert_before: ['AE_BEFORE', '在‘{a}’前面加上‘{b}’'], remove: ['AE_REMOVE', '删掉‘{a}’'] };
const aeTplName = () => AE_TPL[AE.kind]?.[0];
const aeInst = () => { const a = AE.a.trim(), b = AE.b.trim(), x = AE_TPL[AE.kind];  // 和后台 audioedit.instruction 一样：照当前默认那套模板拼（2026-11-09）
  return x ? (window.TPL?.cur?.t?.[x[0]] ?? x[1]).replace(/\{(a|b)\}/g, (_, k) => k === 'a' ? a : b) : a; };
addEventListener('tplchange', () => renderImg.chipsRefresh?.());  // 换了系统指令的版本 / 默认模板：生图“增强”按钮上的版本跟着变
addEventListener('tplchange', () => { const el = $('#ae-inst'); if (el && AE.a.trim()) el.textContent = '发给模型的指令：' + aeInst();
 });
async function renderAudioEdit() {
  $('#main').innerHTML = `
  <div class="page-head"><div><h1 class="page-title">改录音${hintHtml('替换、添加或删除录音中的个别字词，声音和语气保持不变（腾讯 AuK）')}</h1></div></div>
  <div class="grid-tts">
    <div class="stack"><div class="card">
      <div class="drop" id="ae-drop">${ICON.up}<div style="font-weight:600;font-size:15px">拖入或点击上传录音</div></div>
      <input type="file" id="ae-file" accept="audio/*,video/*" hidden>
      <div id="ae-src" class="ae-src"></div>
      <div class="field" style="margin-top:14px"><span class="label">修改方式${hintHtml('<b>替换</b>：将录音中的某几个字替换为其他内容。<br><b>在后面 / 前面添加</b>：在某几个字的后面或前面添加新的内容。<br><b>删除</b>：删除某几个字。<br><b>自定义</b>：直接填写一句编辑指令，例如“把语速放慢一点”“语气更开心”（AuK 也支持修改语速、音调、情绪及去噪）。<br>原文须与录音内容完全一致；改动越小越自然。', 'sm')}</span>
        <div class="seg full" id="ae-kind">${AE_KINDS.map(([k, n]) => `<button type="button" data-k="${k}" class="${AE.kind === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>
      <div class="ae-ab"><label class="field"><span class="label" id="ae-al"></span><input class="input" id="ae-a" autocomplete="off"></label>
        <label class="field" id="ae-bw"><span class="label" id="ae-bl"></span><input class="input" id="ae-b" autocomplete="off"></label></div>
      <div class="tiny ae-inst" id="ae-inst"></div>
      <label class="field ae-secs"><span class="label">修改后的时长（秒）${hintHtml('不填写则自动估算：按增减的字数计算（约每秒 4 个字）。在“自定义”中修改语速时需填写，例如原为 10 秒、希望放慢则填 12。', 'sm')}</span><input class="input" id="ae-s" type="number" min="0.5" max="120" step="0.1" placeholder="自动"></label>
      <div class="row" style="margin-top:12px"><span class="spacer"></span><button class="btn primary" id="ae-go">开始修改</button></div>
    </div></div>
    <div class="side-col"><div class="card"><h3 class="card-title">记录</h3><div id="ae-list" class="segs" style="max-height:none"><div class="shimmer"></div></div></div></div>
  </div>`;
  const drop = $('#ae-drop'), file = $('#ae-file');
  const paintSrc = () => { const s = AE.src, el = $('#ae-src'); if (!el) return;
    el.innerHTML = s ? `<div class="row"><span class="tiny">录音：</span><b class="ae-n">${esc(s.name)}</b><span class="spacer"></span><button type="button" class="btn small ghost" id="ae-x">更换</button></div>` : '';
    drop.hidden = !!s; $('.lib-pick-row')?.toggleAttribute('hidden', !!s);
    $('#ae-x') && ($('#ae-x').onclick = () => { AE.src = null; paintSrc(); }); };
  const pick = f => { AE.src = f; paintSrc(); };
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && pick(file.files[0]);
  libPickRow(drop, pick);
  const paintKind = () => { const [la, lb] = AE_LAB[AE.kind];
    $('#ae-al').textContent = la; $('#ae-bl').textContent = lb; $('#ae-bw').hidden = !lb;
    $('#ae-a').value = AE.a; $('#ae-b').value = AE.b; paintInst(); };
  ['#ae-a', '#ae-b'].forEach(k => PromptInspector.bind($(k), null, { tpl: { pages: ['aedit'] } }));  // 查看完整提示词：第二页是改录音的四种写法
  const paintInst = () => { $('#ae-inst').textContent = AE.a.trim() ? '发给模型的指令：' + aeInst() : ''; };
  $$('#ae-kind [data-k]').forEach(b => b.onclick = () => { AE.kind = b.dataset.k; $$('#ae-kind button').forEach(x => x.classList.toggle('on', x === b)); paintKind(); });
  $('#ae-a').oninput = e => { AE.a = e.target.value; paintInst(); };
  $('#ae-b').oninput = e => { AE.b = e.target.value; paintInst(); };
  $('#ae-s').value = AE.secs; $('#ae-s').oninput = e => { AE.secs = e.target.value; };
  paintKind(); paintSrc();
  $('#ae-go').onclick = async () => {
    if (!AE.src) return toast('请先添加一段录音', true);
    if (!AE.a.trim()) { $('#ae-a').focus(); return toast(AE.kind === 'custom' ? '请写明修改方式' : '请填写录音中要修改的文字', true); }
    if (AE_LAB[AE.kind][1] && !AE.b.trim()) { $('#ae-b').focus(); return toast('请填写要替换为 / 添加的文字', true); }
    const btn = $('#ae-go'); btn.disabled = true;
    try {
      let audio;
      if (AE.src.libPath) audio = { lib: AE.src.libPath };
      else { if (AE.src.size > 50 * 1048576) throw new Error('录音过大（上限约 50MB），请先剪短');
        const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(new Error('无法读取此文件')); r.readAsDataURL(AE.src); });
        audio = { data, ext: (AE.src.name.split('.').pop() || 'wav').toLowerCase() }; }
      const secs = parseFloat(AE.secs);
      await api('/api/audioedit', { body: { audio, kind: AE.kind, a: AE.a, b: AE.b, ...(secs > 0 ? { seconds: secs } : {}) } });
      toast('开始修改'); tick();
    } catch (e) { toast(e.message, true); }
    btn.disabled = false;
  };
  const row = j => { const run = ['queued', 'running'].includes(j.state);
    return `<div class="ae-it" data-id="${esc(j.id)}"><div class="row"><b class="ae-t">${esc(j.instruction)}</b><span class="spacer"></span>${run ? '' : `<button type="button" class="pl-ib" data-del title="删除此条" aria-label="删除">${ICON.x}</button>`}</div>
      <div class="tiny">${fmtTime(j.created)}${j.src_seconds ? ' · 原录音 ' + j.src_seconds + ' 秒' : ''}${j.seconds ? ' · 修改后 ' + j.seconds + ' 秒' : ''} · ${j.state === 'error' ? `<span style="color:var(--red)">${esc(j.error || '失败')}</span>` : esc(j.message)}${jobTimer(j, 'sm')}</div>
      ${j.state === 'done' ? `<div class="ae-pl"><span class="tiny">修改后</span>${apHtml(`/media/audioedit/${j.id}/output.wav`, 'ae:' + j.id, { mini: true, title: j.instruction, sub: '改录音' })}<a class="btn small ghost" href="/media/audioedit/${j.id}/output.wav?dl=1" download>下载</a></div>
        <div class="ae-pl"><span class="tiny">修改前</span>${apHtml(`/media/audioedit/${j.id}/input.wav`, 'aei:' + j.id, { mini: true, title: '原录音', sub: '改录音' })}<span></span></div>` : ''}</div>`; };
  let busy = false;
  async function tick(stop = () => { }) {
    if (busy) return; busy = true;
    try {
      const r = await api('/api/audioedit').catch(() => null); const box = $('#ae-list'); if (!box) return stop();
      if (r && !r.ok) { box.innerHTML = `<div class="tiny">改录音所需的模型尚未下载：${esc((r.missing || []).join('、'))}</div>`; return; }
      const list = r?.jobs || [], sig = list.map(j => [j.id, j.state, j.message].join(':')).join('|');
      if (box.dataset.sig !== sig) { box.dataset.sig = sig; box.innerHTML = list.length ? list.map(row).join('') : '<div class="tiny">暂无记录</div>';
        $$('[data-del]', box).forEach(b => b.onclick = async () => { const id = b.closest('[data-id]').dataset.id; try { await api('/api/audioedit/' + id, { method: 'DELETE' }); delete box.dataset.sig; tick(); } catch (e) { toast(e.message, true); } }); }
    } finally { busy = false; }
  }
  tick();
  const box0 = $('#ae-list'), iv = setInterval(() => { if ($('#ae-list') !== box0) return clearInterval(iv); tick(); }, 2000);  // 只认这次进页面时的那个列表：来回切页面不再叠加（2026-11-15 审查）
}

/* 缩略图加载失败自动重试（2026-11-16 用户：手机上生成结果时不时显示问号，点进去又能看）：
   主屏幕应用切到后台时正在下载的图会被系统打断，浏览器不会自己再取；服务器排队生成缩略图时也可能慢。
   图库 / 素材库的小图（/media/img、/media/mats、/media/thumb、/media/vid 带 thumb）出错后隔 1、3、8 秒再取；切回前台时把没加载出来的重新取一遍 */
{ const THUMB = /\/media\/(img|mats|thumb|vid|video)\//, WAIT = [1000, 3000, 8000];
  const again = im => { const n = +(im.dataset.rt || 0); if (n >= WAIT.length) return; im.dataset.rt = n + 1;
    setTimeout(() => { if (!im.isConnected) return; const u = new URL(im.getAttribute('src'), location.href); u.searchParams.set('rt', n + 1); im.src = u.pathname + u.search; }, WAIT[n]); };
  document.addEventListener('error', e => { const im = e.target; if (im?.tagName === 'IMG' && THUMB.test(im.getAttribute('src') || '')) again(im); }, true);
  const sweep = () => document.querySelectorAll('img').forEach(im => { const s = im.getAttribute('src') || ''; if (THUMB.test(s) && im.complete && !im.naturalWidth) { im.dataset.rt = 0; again(im); } });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(sweep, 300); });
  addEventListener('pageshow', () => setTimeout(sweep, 300)); }
