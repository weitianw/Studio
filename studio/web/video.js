/* 生视频（图生视频）：后台是看不见的 ComfyUI（MiniMax H3；Wan 2.2 于 2026-11-06 去掉），这一页是我们自己的界面。
   布局和生图页一样：左边是表单（模型、首帧图片、提示词输入框 + 右下角“生成”），右边是本次生成的视频。
   首帧可以上传、粘贴截图、从生图的图库里选；生图页的图片右键也能“生成视频”。以前生成的视频在“作品 → 视频”。
   另外：尾帧（首尾帧生视频，可选）、续接（用上一段的最后一帧接着生成，做完自动合成完整的一段）、
   高级参数（采样器 / 调度器 / CFG / 偏移 / 切换步 / 帧率 / 插帧 / 超分……模型能调的都在这里）。 */
'use strict';
let VID_SRC = null, VID_END = null, VIDST = null, vidGal = [];
/* H3 的更多条件（生视频，见 h3extra.py）：关键帧 [{img, t}]、开头片段 {vid, part, n, chain?}、指定声音 {name, data, dur, start}、参考图 / 参考视频 / 参考音频。
   图片的格式和首帧一样；视频 = { kind: 'upload', file, url, dur, w, h } 或 { kind: 'gallery', id, url, dur, w, h }；声音 = { name, data（data URL）, dur } */
// guide：引导视频（整段从第 0 帧起逐帧引导，“自由修改”并进来后用：配特效编辑 LoRA 改视频）；参考视频的 v.snd = 原声怎么用（none / ref / lock）
const VID_X = { keys: [], clip: null, audio: null, refs: [], rvids: [], raudios: [], guide: null };
const vidXn = () => VID_X.keys.length + !!VID_X.clip + !!VID_X.audio + VID_X.refs.length + VID_X.rvids.length + VID_X.raudios.length + !!VID_X.guide;
const vidXref = () => !!(VID_X.refs.length || VID_X.rvids.length || VID_X.raudios.length || VID_X.guide);  // 用了参考：官方底模换成 Ref2VA
/* 素材库（D:\AI-TTS\素材库，后台 /api/mats）：选素材时除了生成过的，还能从这里选。视频不下载到网页里，提交时传路径 {mats}；图片、声音读成 data URL 走原来的路 */
const matsUrl = rel => '/media/mats/' + rel.split('/').map(encodeURIComponent).join('/');
const matsVidRef = v => v.kind === 'gallery' ? { gallery: v.id } : v.kind === 'mats' ? { mats: v.rel } : null;  // 视频库 / 素材库的视频：不用读文件
function matsVid(f, done) {  // 素材库的视频 → 和上传的一样的对象（时长、宽高、缩略图从网页里读）
  const v = { kind: 'mats', rel: f.rel, name: f.name, url: matsUrl(f.rel) + '?scrub=1', dur: 0, w: 0, h: 0, poster: '' }, pr = document.createElement('video'); pr.preload = 'metadata'; pr.muted = true;
  pr.onloadedmetadata = () => { v.dur = pr.duration || 0; v.w = pr.videoWidth; v.h = pr.videoHeight; pr.currentTime = Math.min(.1, v.dur / 2 || 0); done(v, true); };
  pr.onseeked = () => { try { const k = 160 / Math.max(pr.videoWidth, pr.videoHeight), c = document.createElement('canvas'); c.width = Math.round(pr.videoWidth * k); c.height = Math.round(pr.videoHeight * k);
    c.getContext('2d').drawImage(pr, 0, 0, c.width, c.height); v.poster = c.toDataURL('image/jpeg', .8); done(v, true); } catch { } pr.removeAttribute('src'); pr.load(); };
  pr.src = v.url; done(v, false);
}
async function matsFile(f) {  // 素材库的图片 / 声音 → File（交给原来的上传流程：缩图、读时长……）
  const r = await fetch(matsUrl(f.rel)); if (!r.ok) throw new Error('无法读取该文件');
  const b = await r.blob(); return new File([b], f.name, { type: b.type || (f.kind === 'image' ? 'image/png' : f.kind === 'audio' ? 'audio/mpeg' : 'video/mp4') });
}
/* 从素材库选：kind = video / image / audio；能进子文件夹 */
/* o（可选）：dir 从哪个文件夹开始、title 标题、note 标题下的一行说明、skip 底部“跳过这一步”的按钮文字（点了 fn(null)）、onCancel 关掉弹窗没选时 */
function matsPick(kind, fn, o = {}) {
  if (typeof galPick === 'function') return galPick(fn, { ...o, kind });  // 新版素材库窗口（gallery.js）：选图片先打开 gallery，选视频 / 声音直接打开“文件夹”
  const KN = { video: '视频', image: '图片', audio: '声音' }[kind];
  const FOLDER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v6.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z"/></svg>';
  const thumb = rel => matsUrl(rel) + '?thumb=1';  // 小图：素材站来的有现成的缩略图，别的后台现做
  let box = null, cur = o.dir || '', seq = 0, done = false;
  const open = async (dir, qs) => {
    const my = ++seq;
    let r; try { r = await api('/api/mats?kind=' + kind + '&dir=' + encodeURIComponent(dir || '') + (qs ? '&q=' + encodeURIComponent(qs) : '')); } catch (e) { if (!box && o.dir && dir) return open(''); return toast(e.message, true); }
    if (my !== seq) return;  // 搜索打字快：只用最后一次的结果
    if (r.missing && dir && !box) return open('');  // 起始文件夹不在了：从素材库根目录开始
    if (r.missing) return toast('尚未找到素材库文件夹：' + r.root, true);
    cur = r.dir;
    const crumbs = (r.dir ? r.dir.split('/') : []);
    const th = f => kind === 'video' ? `<video src="${esc(matsUrl(f.rel))}#t=0.1" muted playsinline preload="metadata"></video>` : kind === 'image' ? `<img loading="lazy" src="${esc(thumb(f.rel))}" alt="">` : `<span class="mats-au">${'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/></svg>'}</span>`;
    const cov = r.covers || {};
    const body = `<div class="row mats-path"><button type="button" class="vd-link" data-d="">素材库</button>${crumbs.map((c, i) => `<span>/</span><button type="button" class="vd-link" data-d="${esc(crumbs.slice(0, i + 1).join('/'))}">${esc(c)}</button>`).join('')}${r.search ? `<span>·</span><span>共找到 ${r.files.length}${r.more ? '+' : ''} 个</span>` : ''}</div>
      <div class="ig-pick mats-grid">${r.dirs.map(d => `<button type="button" class="ig-pick-t mats-dir${cov[d] ? ' cov' : ''}" data-d="${esc((r.dir ? r.dir + '/' : '') + d)}" title="${esc(d)}">${cov[d] ? `<img loading="lazy" src="${esc(thumb(cov[d]))}" alt="">` : FOLDER}<span class="mats-n">${esc(d)}</span></button>`).join('')}
        ${r.files.map((f, i) => `<button type="button" class="ig-pick-t mats-f" data-i="${i}" title="${esc(f.label || f.name)}">${th(f)}<span class="mats-n">${esc(f.label || f.name)}</span></button>`).join('')}</div>
      ${r.dirs.length || r.files.length ? '' : `<div class="tiny" style="padding:18px 4px">${r.search ? '未找到结果。请尝试其他关键词（衣服可用英文关键词搜索，例如 dress、swimsuit）。' : `该文件夹中没有${KN}。将素材放入 ${esc(r.root)} 后即可在此选择。`}</div>`}`;
    if (!box?.isConnected) {
      box = modal(`<div class="row between" style="margin-bottom:${o.note ? 4 : 10}px;gap:8px"><h3 class="card-title" style="margin:0">${esc(o.title || '从素材库选择' + KN)}</h3><span class="spacer"></span>${o.skip ? `<button type="button" class="btn small" data-skip>${esc(o.skip)}</button>` : ''}<button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
        ${o.note ? `<div class="tiny" style="margin-bottom:10px">${esc(o.note)}</div>` : ''}
        <div class="row mats-q"><input class="input" type="search" placeholder="在当前文件夹中搜索" aria-label="在当前文件夹中搜索" enterkeyhint="search"></div>
        <div class="mats-body"></div>`, null, true);
      box.classList.add('mats-m');
      const inp = $('.mats-q input', box); let tm = 0;
      inp.oninput = () => { clearTimeout(tm); tm = setTimeout(() => open(cur, inp.value.trim()), 250); };
      const sk = $('[data-skip]', box); if (sk) sk.onclick = () => { done = true; box.close(); fn(null); };
      if (o.onCancel) { const c0 = box.close; box.close = () => { c0(); if (!done) { done = true; o.onCancel(); } }; $$('[data-close]', box).forEach(b => b.onclick = box.close); }  // 没选就关掉（Esc、点外面、关闭按钮）
    }
    $('.mats-body', box).innerHTML = body;
    $$('.mats-body [data-d]', box).forEach(b => b.onclick = () => {
      const g = /^gallery(?:\/([^/]+))?/.exec(b.dataset.d);
      if (g && kind === 'image' && typeof galPick === 'function') { done = true; box.close(); return galPick(fn, { lib: g[1], skip: o.skip, onCancel: o.onCancel }); }  // gallery：换成原站那样的筛选窗口
      $('.mats-q input', box).value = ''; open(b.dataset.d);
    });
    $$('.mats-f', box).forEach(b => b.onclick = () => { done = true; box.close(); fn(r.files[+b.dataset.i]); });
  };
  open(cur);
}
/* 角色组合：从素材库（gallery 里三个素材站整理来的）依次选姿势 → 衣服 → 脸，衣服和脸可以跳过（至少选一个）。
   done({ pose, outfit, face })：三个都是素材库的文件对象（{ name, rel, label }）或 null；中途关掉就不调用 */
function matsCombo(done) {
  const pick = (dir, title, note, skip, free) => new Promise(res => {  // gallery.js 在：用原站那样的筛选窗口；不在就退回文件夹选择
    const o = { title, note, skip, onCancel: () => res(null) };  // free：也可以从素材库里自己的文件夹选（衣服、脸）
    if (typeof galPick === 'function') galPick(f => res(f || false), { ...o, lib: dir.split('/')[1], lock: !free, folders: !!free });
    else matsPick('image', f => res(f || false), { ...o, dir });
  });
  (async () => {
    const pose = await pick('gallery/姿势','角色组合 · 第 1 步：选择姿势', '此图为图 1：成品沿用它的姿势、角度和构图。');
    if (!pose) return;
    const outfit = await pick('gallery/衣服', '角色组合 · 第 2 步：选择衣服', '此图为图 2：为图 1 中的人物换上这身衣服。也可以在“文件夹”中选择自己的图片。', '不换衣服', true);
    if (outfit === null) return;
    const face = await pick('gallery/脸', '角色组合 · 第 3 步：选择脸部', `此图为图 ${outfit ? 3 : 2}：换成此图中的脸和发型。也可以在“文件夹”中选择自己的图片。`, '不换脸', true);
    if (face === null) return;
    if (!outfit && !face) return toast('衣服和脸至少需选择一项', true);
    done({ pose, outfit: outfit || null, face: face || null });
  })();
}
/* 角色组合的修改指令（Qwen 指令改图：图 1 = 姿势，然后依次是衣服、脸） */
function matsComboPrompt(c) {  // 素材站的姿势是人体模型线稿、衣服是单独摆拍的衣服：要说清楚“照图 1 的姿势画一个真人”
  // 2026-11-04 测了几种写法：开头先说“图 1 只当姿势参考”、主语用“图 3 的女人”最跟姿势；把脸放成图 1 会丢姿势，先用姿势控制出图再改衣服也会丢姿势
  const n = c.outfit ? 3 : 2, two = /双人/.test(c.pose?.rel || '');
  const who = c.face ? (two ? `two women who both look like the woman from Picture ${n} (same face and hairstyle)` : `the woman from Picture ${n} (same face and hairstyle)`) : (two ? 'two real young women' : 'a real young woman');
  const wear = c.outfit ? ', wearing the outfit from Picture 2 (same design, colors, fabric, shoes and accessories)' : ', wearing simple, well-fitting clothes';
  return [`Use the mannequin sketch in Picture 1 only as a pose guide. Generate a photorealistic photo of ${who}${wear},`,
    `posed exactly like the ${two ? 'mannequins' : 'mannequin'} in Picture 1: same arm, hand, leg and head positions and the same camera angle and framing. Plain light gray studio background.`].join(' ');
}
const VID_HIDE = new Set();  // 这次打开应用里收起的失败记录
const vidState = () => {  // 原地补默认值（不换对象）：页面里各处拿到的都是同一个 S.vidg
  const d = { model: 'h3', prompt: '', seconds: 5, size: '480p', res: '', seed: -1, srcId: null, adv: {}, mode: 'gen', eprompt: '', eseconds: 5 };
  S.vidg = S.vidg || {}; for (const k in d) if (S.vidg[k] === undefined) S.vidg[k] = d[k];
  if (S.vidg.ev !== 2) { if (S.vidg.engine === '1') S.vidg.engine = 'auto'; S.vidg.ev = 2; }
  if (!(S.vidg.gbv >= 2)) { S.vidg.gbase = 'official'; S.vidg.gbv = 2; }  // 生视频底模的默认改成官方原版（2026-11-04）  // 以前只有 ① 能选，存着的 '1' 就是默认：改成“自动”（官方底模用 ②）
  return S.vidg;
};
/* 改视频（换人 / 换头 / 改衣）：H3 的参考模式（改衣的保真替换 / 参考编辑不是 H3），底模跟着做法走，后台见 videoedit.py。
   原视频：{ kind: 'upload', file, url（本地预览）, dur, w, h } 或 { kind: 'gallery', id, url, dur, w, h }；人物图 / 衣服图的格式和首帧一样 */
let VE_VID = null, VE_REF = null;
const vidKey = () => { const s = vidState(); return s.mode === 'edit' ? 'h3' : s.model; };
const VE_TASKS = [['swap', '换人'], ['head', '换头'], ['outfit', '改衣'], ['motion', '动作迁移']];  // 动作迁移 2026-11-12（Alissonerdx Motion Transfer 作者配方）  // 去人去物 2026-11-04 按用户要求去掉；自由修改并进生视频（引导视频 + 特效编辑 LoRA）
const VE_AUDIO = [['keep', '原声'], ['gen', '重新生成'], ['none', '无声']];
const VE_AUDIO_IC = { keep: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  gen: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M18 5.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>', none: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>' };  // 标签短一点：窄窗口时和旁边一栏并排也不挤
const VE_MAX_MB = 70;
const VE0 = { task: 'swap', swap_by: 'v11', target: '', audio: 'keep', start: 0, base: 'lite', tpl: true, method: 'ref', own: false, follow: false, emph: true, pose: true, locon: false, locq: 'cloth', head_by: 'fs', vg: false, mv: 8, tpls: {} };
// 改视频的底模：官方完整版；作者配方 / 换脸 LoRA 固定官方精简；“高级参数”里能选官方精简
const tipNote = (tip, note) => note ? tip.replace('</b><span>', `</b><span><b>${note}。</b><br>`) : tip;  // 优势说明放进提示最前面
const REC = '<span class="ve-new" aria-label="推荐">荐</span>';  // 推荐的那个选项上的角标
const VE_BASES = [['auto', '跟随做法', '自动'], ['full', '官方', '官方'], ['lite', '官方精简', '精简']];  // 官方精简 = 精简版 + nvfp4 文字编码器（2026-11-09 夜测后加，默认不用）  // 官方精简版 2026-11-04 去掉（和完整版画面、速度都一样）  // 第 3 个：手机上的短名字（4 个按钮一行放得下）
// 每种做法的优势（按用户的偏好和第 3 轮测试写，2026-11-04）：放在按钮的鼠标停留提示最前面，界面上不另写说明
const VE_NOTE = { v11: '推荐：背景、镜头、动作沿用原视频，人物按人物图', ref_swap: '参考生成：画面更美观', ref: '推荐：24 fps、清晰，脸和动作不变',
};
// 换人的两种做法：新版 = 作者配方；审美优先 = 参考生成（原视频当 <Video 1>、人物图当 <Picture 1>，结构化提示词，官方底模）
const VE_SWAPS = [['v11', '新版', '<b>新版</b><span>Alissonerdx 换人 v1.1（作者配方）：人物图先自动去背景，再把原视频里的人逐帧换成图中的人；背景、镜头、动作沿用原视频，人物的长相、发型、衣服按人物图（只有半身或坐姿也可以）。官方精简底模，DMD 8 步加速，① 原生节点；720p 每 5 秒约 16 分钟。</span>'],
  ['ref', '审美优先', '<b>审美优先</b><span>参考生成：以原视频为参考视频、人物图为参考图，使用官方底模按结构化提示词重新生成整段。画面更美观、更清晰，但动作不一定逐帧一致；最长 15 秒；默认使用 ② 秋叶节点（14 步），速度较慢。</span>']];
// 换头：换脸 LoRA = UntMods
const VE_HEADS = [['fs', '换脸 LoRA', '<b>换脸 LoRA</b><span>UntMods 换脸 LoRA：原视频作为参考视频，换成头像里的脸和发型；身体、衣服、动作、背景沿用原视频。官方精简底模，官方加速 8 步（480p 不加速），① 原生节点；提示词只用触发词，无需填写。</span>'],];
VE_NOTE.fs = '推荐：换出来的脸和头像最像';
const veFs = () => { const ve = veState(); return ve.task === 'head' && (ve.head_by || 'fs') === 'fs' && (VIDST?.edit?.head_by || ['fs']).includes('fs'); };
// 改衣 · Viggle 重拍（2026-11-13，默认关）：Qwen 改好那一帧，Viggle Remake 照着它把整段重拍（光照最接近原视频）；不叠局部修改 / 动作跟随 / 加速
const veVg = () => { const ve = veState(); return ve.task === 'outfit' && ve.vg === true && !!VIDST?.edit?.vg; };
const veRef = () => { const ve = veState(); return (ve.task === 'swap' && ve.swap_by === 'ref') || (ve.task === 'outfit' && veMethod() === 'ref'); };  // 参考生成（换人 · 审美优先 / 改衣 · 参考生成）
// 作者配方（换人 · 新版 / 动作迁移，2026-11-12）：固定官方精简 + 做法 LoRA + DMD 8 步 + ① 原生节点（原视频逐帧引导），不叠动作跟随——和后台 videoedit.parse 一样
const veRecipe = () => { const ve = veState(); return (ve.task === 'swap' && ve.swap_by === 'v11') || ve.task === 'motion'; };
const vidGbase = () => 'official';  // 生视频 · H3 的底模：官方原版
const vidEngNow = (E) => {  // 这次实际用的做法：自动 = 官方底模用 ②（秋叶节点），其余用 ①；② 接不了参考 + 关键帧 / 开头片段 / 引导视频 / 从中间开始的指定声音
  const st = vidState(), e = st.engine || 'auto', ok2 = (VIDST?.engines || []).some(x => x.key === '2' && x.ready);
  const off = E ? veRef() && veBaseNow() === 'full' : vidGbase() === 'official';  // 改视频参考生成：官方完整版用 ②
  const refs = !E && !!VID_X.rvids.length;  // 生视频放了参考视频（拿它的动作当参考）：自动时用 ① 原生；改视频的参考生成用 ②（2026-11-04 用户定）
  const bad = !E && ((VID_X.keys.length && (VID_X.refs.length || VID_X.rvids.length || VID_X.raudios.length)) || VID_X.clip || VID_X.guide || (VID_X.audio && +VID_X.audio.start > 0));
  if (E && (veRecipe() || veVg())) return '1';  // 作者配方：原视频走逐帧引导，② 接不了；Viggle 重拍只在 ① 上
  return e === 'auto' ? (off && !refs && ok2 && !bad ? '2' : '1') : e;
};
const veBaseNow = () => { const ve = veState(), VS = VIDST?.edit || {}; let b = ve.base;  // 这次实际用的底模（和后台 videoedit.parse 一样）
  void b; void VS;  // 改视频都用官方（官方精简见 veLite）
  return 'full'; };
// 改衣只剩参考生成（保真替换 / 参考编辑随 Wan 2.2 一起去掉了，2026-11-06）；LoRA 都是 H3 的
const veLite = () => ((veState().base === 'lite' && veRef()) || vePose() || veRecipe() || veFs()) && !!VIDST?.edit?.lite && veBaseNow() === 'full';
// 动作跟随只配官方精简底模（官方只出了精简版的 Fun ControlNet）：只在官方底模时能开，开了这一单用官方精简（2026-11-10）
const vePose = () => !veRecipe() && !veFs() && !veVg() && (veState().pose === true || veLoc()) && !!VIDST?.edit?.pose && !!VIDST?.edit?.lite && veBaseNow() === 'full';  // 这次用官方精简（精简版 + nvfp4）
// 局部修改（2026-11-12 夜测，默认关）：只重画衣服那块、其余贴回原视频；自带动作跟随（Fun ControlNet 2.0），和后台 videoedit.parse 同样的条件
const veLoc = () => { const ve = veState(); return ve.locon === true && ve.task === 'outfit' && veRef() && !veVg() && !!VIDST?.edit?.loc && !!VIDST?.edit?.lite && veBaseNow() === 'full'; };
const veMethod = () => 'ref';
// “使用模板”开关：每种做法各记各的（换人的两种、换头、改衣的三种），默认都开
const veTplKey = (task = veState().task, method = veMethod()) => task === 'outfit' ? (veVg() ? 'outfit_vg' : 'outfit_' + method) : task === 'head' && veFs() ? 'head_fs' : task === 'swap' && ['ref', 'v11'].includes(veState().swap_by) ? 'swap_' + veState().swap_by : task;
const veTpl = (k = veTplKey()) => { const v = (veState().tpls || {})[k]; return v === undefined ? true : !!v; };
const veSetTpl = (on, k = veTplKey()) => { const ve = veState(); ve.tpls = { ...(ve.tpls || {}), [k]: !!on }; };
// 关了模板时提示词旁边的“写法要点”：每条标出处（作者 = 模型作者的说明 / 示例；实测 = 我们在这台电脑上对比过）
const VE_TIPS = {
  outfit_edit: ['<b>实测</b>：此句发送给 Qwen 改图——先用一句话说明修改内容，再写明哪些保持不变（人、脸、发型、身材、姿势、表情、背景、光线）。',
    '<b>实测</b>：放入衣服图时请写“只拿图 2 的衣服，不要图 2 里的人、脸和头发”，否则会把衣服图中的模特（连同长发）一并换过来。',
    '<b>作者</b>（Phr00t Rapid）：加上 Professional digital photography 一句可减少塑料感。'],
  v11: ['<b>作者</b>（Character Swap v1.1）：开头是触发词 body_swap:，整段一行；&lt;Subject 1&gt; 后面接人物图中此人从头到脚的样子（英文、逗号分隔、以性别开头）。程序会看人物图自动写这一段，您写的内容接在后面。',
    '<b>作者</b>：原视频作为逐帧引导（不是参考视频），人物图作为 &lt;Picture 1&gt;；人物图要先去背景，否则会把图里的场景带进视频（程序会自动去背景）。',
    '<b>作者</b>：小脸、遮挡、快速动作、难的角度、光线变化、长片段容易走样；先用一段几秒的单个镜头测试。'],
  faceswap: ['<b>作者</b>（UntMods 换脸 LoRA）：只用一个触发词 Faceswap，强度 1.0；原视频作为参考视频，头像作为参考图（可以放多张同一人的脸）。',
    '<b>实测</b>：头像和视频里的人差别越大越能看出效果；头像最好是清晰的正脸、光线均匀。'],
  vg: ['<b>官方</b>（Viggle Remake）：写成目标视频的样子，而不是指令；retention_analysis 会被照字面执行。程序用官方的六段式，您写的衣服描述放进 &lt;Subject 2&gt; 那一行。',
    '<b>官方</b>：Qwen 改好的那一帧会钉在原来那一帧上，整段照着它重拍；改动越多，这一帧越要画准。',
    '<b>实测</b>：光照、脸最接近原视频；分辨率固定 480 / 736，最短约 3.8 秒、最长 14 秒。'],
  motion: ['<b>作者</b>（Motion Transfer v1.0）：开头是触发词 motion_transfer:；人物图里的人做出原视频里的动作，动作、节奏、镜头来自原视频。',
    '<b>作者</b>：人物图里有真实场景（房间、街道……）时，成品用这个场景；人物图是纯色 / 棚拍背景时，沿用原视频的场景。程序会看人物图自动写人物和场景，您写的内容接在人物后面。',
    '<b>作者</b>：人物图里的姿势不是动作——成品的姿势全部跟原视频；取景、比例也跟原视频。'],
  ref: ['<b>结构化写法</b>（MiniMax H3 官方 skills）——subject_definitions（各人物来自哪张图 / 哪段视频）、summary（以 [video editing] 开头）、retention_analysis（哪些沿用原视频、哪些按参考图）、detailed_description、overall_soundscape、non_diegetic_music。',
    '<b>实测</b>（A/B）：原视频写作 &lt;Video 1&gt;，人物图写作 &lt;Picture 1&gt;；写明“动作、机位、场景和光线与 &lt;Video 1&gt; 逐帧一致”，换衣服时再写明“脸、发型、身材和原视频一致，没有变胖或变瘦”。',
    '<b>实测</b>：提示词框中的内容如果已是整段结构化提示词（含 subject_definitions 或 &lt;Subject 1&gt;），将原样发送给模型，不再套用模板。'],
};
const veTips = () => { const ve = veState(), m = veMethod();
  const list = ve.task === 'motion' ? VE_TIPS.motion : ve.task === 'swap' ? VE_TIPS[ve.swap_by === 'ref' ? 'ref' : 'v11'] : ve.task === 'outfit' && veVg() ? [...VE_TIPS.outfit_edit, ...VE_TIPS.vg] : ve.task === 'outfit' && m === 'ref' ? [...VE_TIPS.outfit_edit, ...VE_TIPS.ref] : ve.task === 'head' ? VE_TIPS.faceswap
    : VE_TIPS.outfit_edit;
  return list.join('<br><br>'); };
const veOwn = () => veState().task === 'outfit' && veState().own === true;  // 上传的图就是换好衣服的人物图（跳过 Qwen 改图）
const veFfg = () => veState().task === 'outfit' && veMethod() === 'ref' && !veOwn() && veState().ffguide === true && !veVg();  // 锁定首帧：只在参考生成、用 Qwen 生图时才有用（默认关）
const veState = () => {  // 原地补默认值（不换对象）：和 vidState 一样，页面里各处拿到的是同一个
  const st = vidState(); if (!st.edit || typeof st.edit !== 'object') st.edit = {};
  // 版本号只往上升：以前写成 mv !== 2，到了第 3 版每次都被拉回 2、再被下面重置一遍（改衣的做法、底模都切不动，2026-11-04 修）
  if (!(st.edit.mv >= 2)) { st.edit.mv = 2; }
  if (st.edit.task === 'remove') st.edit.task = 'swap';  // 去人去物去掉了
  if (st.edit.base === 'official') st.edit.base = 'full';  // 官方精简版去掉了（2026-11-04）：按官方完整版
  if (!(st.edit.mv >= 3)) {  // 2026-11-04 用户定：改衣默认参考生成、整体重绘藏起来、底模跟着做法走、自由修改并进生视频
    st.edit.method = 'ref'; st.edit.base = 'auto'; st.edit.mv = 3;
  }
  if (!(st.edit.mv >= 4)) { st.edit.mv = 4; }
  if (!(st.edit.mv >= 5)) { st.edit.emph = true; st.edit.mv = 5; }  // 2026-11-11 用户定：「改动写进每一段」默认开
  if (!(st.edit.mv >= 6)) { if (!st.edit.base || st.edit.base === 'auto') st.edit.base = 'lite'; st.edit.pose = true; st.edit.mv = 6; }
  if (!(st.edit.mv >= 7)) { st.edit.mv = 7; }
  if (!(st.edit.mv >= 8)) { st.edit.head_by = 'fs'; st.edit.mv = 8; }  // 2026-11-13 用户定：换头默认改成换脸 LoRA（UntMods）  // 2026-11-12 用户定：换人默认改成新版（作者 v1.1 配方）  // 2026-11-11 用户定：改视频默认 精简 + 动作跟随（720p、加速 8 步见 vidEditDefaults）
  if (st.edit.method === 'swap') st.edit.method = 'ref';
  if (st.edit.task === 'free') st.edit.task = 'swap';
  if (!['v11', 'ref'].includes(st.edit.swap_by)) st.edit.swap_by = 'v11';
  // 2026-11-06：左栏的“跟随原视频”去掉了；以前开着它存下的 follow（没有 segUrl）会让剪辑显示整段、实际只发上次的时长——清掉
  if (st.edit.follow && !st.edit.segUrl) st.edit.follow = false;
  delete st.edit.loose;
  for (const k in VE0) if (st.edit[k] === undefined) st.edit[k] = VE0[k];
  return st.edit;
};
/* 高级参数最下面：本次实际会用的提示词模板（不能改；‹…› 是会被换掉的部分）。关了模板就不显示 */
const veTplBlock = (ve, VS) => {
  if (!veTpl()) return '';  // 关了模板：没有模板可看
  const T = VS.templates || {};
  const list = ve.task === 'head' ? [['换头 · 换脸 LoRA（UntMods 作者：只用触发词）', T.faceswap]]
    : ve.task === 'outfit' && veVg() ? [['改衣 · 先为人物改图（Qwen 指令改图）', T.outfit_edit], ['放入衣服图时', T.outfit_edit_img], ['重拍时（Viggle 官方六段式）', T.vg]]
    : ve.task === 'motion' ? [['动作迁移（Motion Transfer 作者的模板）', T.motion]]
    : ve.task === 'swap' && ve.swap_by === 'v11' ? [['换人 · 新版（Character Swap v1.1 作者的模板）', T.v11]]
    : ve.task === 'swap' && ve.swap_by === 'ref' ? [['换人 · 审美优先', T.ref_swap]]
    : [['改衣 · 先为人物改图（Qwen 指令改图）', T.outfit_edit], ['放入衣服图时', T.outfit_edit_img], ['生成视频时', T.ref_outfit]];
  const items = list.filter(([, t]) => t);
  if (!items.length) return '';
  const note = veRecipe() ? '‹…› 是程序看人物图自动写的英文描述；您填写的内容接在人物描述后面（可选）。' : veRef() ? (ve.task === 'swap' ? '您填写的内容将填入“人物”一栏（可选，描述人物图中此人的样子）；如已是整段结构化提示词，则原样发送给模型。' : '程序选取一帧人物脸部清晰的画面，用 Qwen 改图换好衣服作为 <Picture 1>（关闭“Qwen 生图”则使用您上传的图；不上传时跳过此步，提示词中不出现 <Picture 1>）；您填写的衣服描述也会写入这段提示词。成品为整段重新生成，不贴回原视频。')
    : ve.task === 'swap' ? '您填写的提示词附加在最后（作者建议描述原视频中的人在做什么）；未填写“要换掉的人”时为 the main person。' : '';
  return `<div class="ig-sec" data-tip="${esc('程序会将您填写的提示词放入此模板，再发送给模型；此处仅供查看，不可修改。')}">提示词模板</div>`
    + items.map(([n, t]) => `<div class="field ve-tplv"><span class="label">${esc(n)}</span><div class="ve-tplt">${esc(t)}</div></div>`).join('')
    + (note ? hintHtml(esc(note)) : '');
};
/* 视频功能一览（生视频页标题旁的按钮、使用说明里的那一节都用这一份；改默认值时这里跟着改） */
const VID_FUNCS = [
  ['gen', '生视频', '文字或图片生成；按参考视频的动作生成新人物、新场景；保留人物、修改背景或添加特效（引导视频 + 特效编辑 LoRA）', '官方原版', '默认不加载，可手动添加；官方原版可在高级参数中选用加速 LoRA', 'AI 助手编写或手动编写', '放入参考视频时为 ① 原生节点，其余为 ② 秋叶节点'],
  ['swap-v11', '换人 · 新版', '背景、镜头、动作沿用原视频，人物换为人物图里的人（半身、坐姿的图也行）', '官方精简', '换人 v1.1 + DMD 加速', 'LoRA 作者模板（看图自动写人物）', '① 原生节点'],
  ['swap-ref', '换人 · 审美优先', '画面观感优先', '官方', '无', '实测模板', '② 秋叶节点'],
  ['head', '换头', '仅替换头部 / 脸，其余保持原视频', '官方精简', 'UntMods 换脸 LoRA + 官方加速', 'LoRA 作者的触发词', '① 原生节点'],
  ['motion', '动作迁移', '人物图里的人在人物图的场景里做原视频的动作', '官方精简', '动作迁移 v1.0 + DMD 加速', 'LoRA 作者模板（看图自动写人物和场景）', '① 原生节点'],
  ['outfit-ref', '改衣', '换衣；24 fps，画面清晰', '官方（先由 Qwen 生成换衣参考图）', '无（可选加速 LoRA）', '实测模板', '② 秋叶节点'],
  ['outfit-vg', '改衣 · Viggle 重拍', '光照、脸最接近原视频；开关默认关', 'Viggle Remake（H3 首帧版合并 edit LoRA）', '已合并', 'Viggle 官方六段式', '① 原生节点'],
];
const VID_FUNCS_H = ['功能', '适用场景', '模型', 'LoRA', '提示词', '做法（节点）'];
const VID_FUNCS_NOTE = ['“做法”为默认值，可在“高级参数 → 做法”中修改；本次实际使用的组合见生成按钮上方的“本次使用”。',
  '① 原生节点：参考视频的动作节奏更准确；② 秋叶节点：速度约快一倍，不支持开头片段、引导视频、参考图与关键帧同时使用（遇到时自动改用 ①）。'];
function vidFuncTable(cur) {  // cur：要高亮的那一行（见 vidFuncCur）
  return `<div class="vft-wrap"><table class="vft"><thead><tr>${VID_FUNCS_H.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${VID_FUNCS.map(([k, ...c]) => `<tr${k === cur ? ' class="on"' : ''}>${c.map((x, i) => `<td data-l="${VID_FUNCS_H[i]}">${i ? esc(x) : `<b>${esc(x)}</b>`}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
    + `<div class="tiny vft-note">${VID_FUNCS_NOTE.map(esc).join('<br>')}</div>`;
}
/* 快速对照：想做什么 → 去哪里（去处是链接：点了切到生视频 / 改视频的那个功能，见 vidGoTo） */
const VID_GOALS = [  // 2026-11-13 用户：功能太多分不清——每行写清去哪里、怎么选（默认够用的就写“默认即可”）
  ['用文字或一张图生成视频', '生视频', 'gen', '有图就放首帧'],
  ['让图片里的人做视频里的动作，画面照图片（例如坐在桌前）', '生视频', 'gen-pin', '首帧放图片，参考视频放动作视频，底模选官方'],
  ['让图片里的人做视频里的动作，镜头照视频（动作最准）', '改视频 → 动作迁移', 'motion', '默认即可'],
  ['人物不变，只改背景或加特效', '生视频', 'gen-guide', '引导视频放原视频，再加特效编辑 LoRA'],
  ['给视频里的人换衣服', '改视频 → 改衣', 'outfit', '默认即可；衣服上的小改动开“局部修改”；换衣服时要光照最像原视频开“Viggle 重拍”'],
  ['把视频里的人整个换成另一个人', '改视频 → 换人', 'swap', '默认“新版”；衣服、动作要最贴原视频选“还原优先”'],
  ['只换头 / 脸', '改视频 → 换头', 'head', '默认“换脸 LoRA”'],
];
/* 2026-11-13 用户：每个功能适合什么、不适合什么（按这几晚的实测写；只测过一两次的写在“备注”里）。
   VID_FIT = 详细版（“查看详细”里），VID_FIT_S = 简化版（弹窗第二页） */
const VID_FIT = [
  ['改视频 · 改衣', [
    ['默认（参考生成）', 'Qwen 先改好一帧，H3 参考原视频整段重新生成。大部分换衣：整件换掉、换成完全不同的款式；动作和脸都不错（脸相似度约 0.93）', '对光照要求很高时：整体会偏暗一点（实测亮度约 −5）', '默认用，先把衣服改好那一帧。已有改好的图可以关掉“Qwen 生成”，直接放图', '开“匹配原视频色调”可以在生成后调回来'],
    ['局部修改', '只重画衣服那一块，脸和背景直接用原视频的。衣服上的小改动：换图案、换蝴蝶结颜色、保留外套只改里面那件；脸和色调几乎和原视频一样，没有分界线', '整件拿掉或衣服明显变小（外套整件拿掉、宽开衫换紧身）：原来的衣服会被画回来，请关掉用默认。两个人一起改：只有后半段改到', '更换衣服用', '“保留外套、换里面那件”这次没测成，效果不确定；手划过时冒白块已修好'],
    ['Viggle 重拍', 'Qwen 改好一帧后，Viggle 照着这一帧把整段重拍。最在意光照和脸跟原视频一样时；原视频光线复杂（暖光、逆光、偏色）时尤其值得开。实测光照最接近原视频（换衣：脸亮度差 0.7、相似 0.953）', '选段长于 14 秒；要用局部修改或动作跟随时（不能一起开）', '必须有一张改好的图：默认由 Qwen（v23）改，或自己放（自己放的图不钉在某一帧上，只当参考）', '6 秒约 20 分钟（H3 开动作跟随约 30 分钟）；大幅换款、多人视频还没测过'],
    ['动作跟随', '动作多、手势快、上次生成跑偏了的段落', '动作很平稳的段落（差别不大，还慢一半）；Viggle 重拍时不能用', '—', ''],
    ['匹配原视频色调', '成品偏暗、肤色偏红时，生成完自动调回原视频的颜色，只花几秒', '动作迁移（场景本来就换了）', '—', ''],
  ]],
  ['改视频 · 换人', [
    ['新版（默认）', '背景、镜头、动作都想留着原视频，只把人换为人物图里的人；人物图是半身照、坐着的都行，背景会自动去掉，描述会看图自动写', '对光照很挑剔时（光照一般，还没解决）；脸很小、遮挡多、动作特别快时容易走样', '不用，放人物图', '720p 一段 5 秒约 17 分钟'],
    ['审美优先', '画面好看比动作逐帧一致更重要', '需要动作一模一样', '不用，放人物图', ''],
  ]],
  ['改视频 · 换头', [
    ['换脸 LoRA（默认）', '只换脸和发型，身体、衣服、动作、背景都不动；头像和视频里的人差得越多越明显。实测和参考脸最像（0.48）', '头像模糊、侧脸、光线很怪；想连衣服一起换（那是换人）', '不用，放头像', ''],
  ]],
  ['让图里的人做视频里的动作', [
    ['改视频 → 动作迁移', '画面照视频：镜头、构图跟原视频走，人物和场景换成图里的；动作最准（和原视频的角度差 4°）。想要“图里的人跳这段舞”，构图无所谓', '想保留图片的构图', '不用，放人物图', ''],
    ['生视频：首帧放图片 + 参考视频', '画面照图片：构图、场景、桌子、灯光都不变；图里的人坐着、被桌子挡住，只想让露出来的部分动。动作的类型和节奏一致（角度差 17°）', '要求每个动作都和视频一模一样（不是逐帧复刻）', '不用', '底模选官方；加速 8 步和不加速差不多'],
  ]],
  ['加速', [
    ['加速 LoRA', '720p：8 步，快一倍左右，画质几乎一样', '480p：一律不用', '—', '换人新版、动作迁移、换脸 LoRA、Viggle 重拍都自带，不用管'],
  ]],
];
const VID_FIT_S = [
  ['改衣 · 默认', '大部分换衣', '最在意光照（会偏暗，开调色可补）', '默认用'],
  ['改衣 · 局部修改', '衣服上的小改动：换图案、换颜色', '整件拿掉、衣服变小、两个人一起改', '更换衣服用'],
  ['改衣 · Viggle 重拍', '换衣时光照、脸要和原视频一样', '长于 14 秒；要局部修改 / 动作跟随', '必须有改好的图（默认 Qwen 改）'],
  ['动作跟随', '动作多、手势快、上次跑偏', '动作平稳的段落', '—'],
  ['匹配原视频色调', '成品偏暗、肤色偏红', '动作迁移', '—'],
  ['换人 · 新版', '只换人，背景、镜头、动作留原视频', '脸很小、遮挡多、动作很快', '不用'],
  ['换人 · 还原优先', '衣服、动作、口型要最贴原视频', '人物图背景复杂', '不用'],
  ['换人 · 审美优先', '画面好看优先', '要动作逐帧一致', '不用'],
  ['换头 · 换脸 LoRA', '只换脸和发型', '头像模糊、侧脸；想连衣服一起换', '不用'],
  ['动作迁移', '图里的人做这段动作，镜头照视频，动作最准', '要保留图片的构图', '不用'],
  ['生视频 · 首帧 + 参考视频', '画面照图片（坐在桌前、半身）', '要每个动作一模一样', '不用'],
  ['加速', '720p', '480p', '—'],
];
function vidFitTable(short) {  // short：弹窗第二页的简化版
  if (short) return `<div class="vft-wrap"><table class="vft vff"><thead><tr><th>功能</th><th>用它</th><th>别用</th><th>要先用 Qwen 吗</th></tr></thead><tbody>${VID_FIT_S.map(([n, a, b, q]) => `<tr><td data-l="功能">${esc(n)}</td><td data-l="用它">${esc(a)}</td><td data-l="别用">${esc(b)}</td><td data-l="Qwen">${esc(q)}</td></tr>`).join('')}</tbody></table></div>`;
  return VID_FIT.map(([g, rows]) => `<div class="vft-g">${esc(g)}</div><div class="vft-wrap"><table class="vft vff vffd"><thead><tr><th>选项</th><th>适合</th><th>不适合</th><th>要先用 Qwen 吗</th><th>备注</th></tr></thead><tbody>${rows.map(([n, a, b, q, c]) => `<tr><td data-l="选项">${esc(n)}</td><td data-l="适合">${esc(a)}</td><td data-l="不适合">${esc(b)}</td><td data-l="Qwen">${esc(q)}</td><td data-l="备注">${esc(c || '—')}</td></tr>`).join('')}</tbody></table></div>`).join('');
}
function vidGoalTable() {
  return `<table class="vft vfq"><thead><tr><th>想做什么</th><th>去哪里</th><th>怎么选</th></tr></thead><tbody>${VID_GOALS.map(([g, d, k, h]) => `<tr><td data-l="想做什么">${esc(g)}</td><td data-l="去哪里"><button type="button" class="vft-go" data-go="${k}">${esc(d)}</button></td><td data-l="怎么选">${esc(h)}</td></tr>`).join('')}</tbody></table>`;
}
/* 点了快速对照里的去处：关掉浮层 / 弹窗，切到生视频（H3）或改视频的那个功能；要放的素材用一句提示说明 */
function vidGoTo(k) {
  document.querySelectorAll('.vft-pop').forEach(x => x.remove());
  document.querySelector('.vft-m [data-close]')?.click();
  const st = vidState();
  if (['outfit', 'swap', 'head', 'motion'].includes(k)) { st.mode = 'edit'; veState().task = k; }
  else { st.mode = 'gen'; st.model = 'h3'; }
  persist();
  if (location.pathname === '/video' && typeof renderVideo === 'function') renderVideo(); else go('video');
  const tip = { 'gen-ref': '请在“素材”中放入人物参考图与参考视频（参考视频提供动作）', 'gen-pin': '首帧放入图片，“更多素材 → 参考视频”放入动作视频，底模选官方', 'gen-guide': '请在“更多素材 → 引导视频”中放入原视频，并在“高级参数 → LoRA”中添加特效编辑 LoRA' }[k];
  if (tip) setTimeout(() => toast(tip), 400);
}
document.addEventListener('click', e => { const b = e.target.closest?.('.vft-go'); if (b) { e.preventDefault(); e.stopPropagation(); vidGoTo(b.dataset.go); } });
const vidFuncCur = () => { const st = vidState(); if (st.mode !== 'edit') return 'gen'; const ve = veState();
  return ve.task === 'motion' ? 'motion' : ve.task === 'swap' ? (ve.swap_by === 'ref' ? 'swap-ref' : 'swap-v11') : ve.task === 'head' ? 'head' : veVg() ? 'outfit-vg' : 'outfit-' + veMethod(); };
const veTaskName = k => (VE_TASKS.find(t => t[0] === k) || VE_TASKS[0])[1];
// 播放用的副本（每 4 帧一个关键帧，拖动时画面跟得上）；下载用 vidUrl。
// 副本还没做好（视频库列表里 scrub 没有它）就放原文件：同一个地址中途换成另一个文件会播到一半卡住（2026-11-05）。scrub=2：换个地址，不用浏览器以前缓存的
const vidScrubOk = f => { for (const x of vidGal) if (x.file === f || x.src_file === f) return !Array.isArray(x.scrub) || x.scrub.includes(f); return true; };
const vidPlay = f => vidUrl(f) + (vidScrubOk(f) ? '?scrub=2' : '');
const veGalVid = x => ({ kind: 'gallery', id: x.id, url: vidPlay(x.file), dur: +x.duration || x.seconds, w: x.width, h: x.height, poster: x.thumb ? vidUrl(x.thumb) : '' });  // poster：窄窗口输入框左边方块里的缩略图
/* 原视频放大播放（竖屏视频在左栏里小）：带进度条、声音、全屏 */
function vePlayBig(v) {
  if (!v?.url) return;
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">原视频${v.dur ? `<span class="tiny" style="margin-left:8px;font-weight:400">${(+v.dur).toFixed(1)} 秒</span>` : ''}</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <video class="vd-player" src="${esc(v.url)}" controls playsinline preload="auto"></video>`, null, true);
  box.classList.add('vd-view', 've-big-m'); vidVolSync($('video', box)); if (videoAutoplay()) videoPreviewPlay($('video', box), true);  // 关了自动播放：放大后不自动播
  if (typeof frAttach === 'function') frAttach($('video', box), matsVidRef(v) || { local: v.url, name: v.name || '原视频', dur: v.dur });  // 视频截图（2026-11-19）
}
const VE_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="13" height="14" rx="3"/><path d="M16 10l5-3v10l-5-3"/><path d="M7.5 15.5l4-4 1.5 1.5-4 4H7.5z" fill="currentColor" stroke="none"/></svg>';
function vidEditThis(x, after) {  // 视频库里的一段 → “改视频”的原视频
  if (!x) return;
  const st = vidState(); st.mode = 'edit';
  if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url);
  VE_VID = veGalVid(x); veState().start = 0; persist(); after?.();
  go('video', location.pathname !== '/video');
  toast('已放入“改视频”：选择模式并放入人物图后即可生成');
}
const VID_ADV0 = { negative: '', interp: false, upscale: false, fast: false };  // 其余（步数、采样器……）按模型各记各的，默认跟模型走
const VID_PER = ['steps', 'sampler', 'scheduler', 'shift', 'cfg', 'split', 'ashift', 'audio', 'fps'];  // 每个模型各自一份的参数
const VID_IC = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>',
  pause: '<svg class="vd-pz" viewBox="0 0 24 24" fill="currentColor"><rect x="6.5" y="5.5" width="4" height="13" rx="1.2"/><rect x="13.5" y="5.5" width="4" height="13" rx="1.2"/></svg>',
  film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.2-2.5z" fill="currentColor" stroke="none"/></svg>',
  chain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h11M11 7l5 5-5 5"/><path d="M20 5v14"/></svg>',
  end: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M9 12h6M12.5 9.5 15 12l-2.5 2.5"/></svg>',
};
const vidUrl = f => '/media/video/' + encodeURIComponent(f);
const vidImg = x => ({ kind: 'gallery', id: x.id, url: '/media/img/' + encodeURIComponent(x.file), w: x.width, h: x.height, gp: x.prompt || '' });  // gp：生成这张图时的提示词（视频页“生图提示词”一键填入）
/* 上传的图：按文件内容找图库里是不是生成过（用原文件算，缩小之前）；找到了把当时的提示词记在图上 */
async function vidImgPrompt(file, obj, done) {
  try { if (!crypto?.subtle) return; const b = await file.arrayBuffer(), h = [...new Uint8Array(await crypto.subtle.digest('SHA-1', b))].map(x => x.toString(16).padStart(2, '0')).join('');
    const r = await api(`/api/img/by-hash?size=${b.byteLength}&sha=${h}`); if (r?.prompt) { obj.gp = r.prompt; done?.(); } } catch { }
}
const vidStM = () => (VIDST?.models || []).find(m => m.key === vidKey());
const vidAdv = () => { const st = vidState(); st.adv = st.adv || {}; for (const k in VID_ADV0) if (st.adv[k] === undefined) st.adv[k] = VID_ADV0[k]; return st.adv; };
/* 当前模型某个参数的值：改过的用改过的，否则用模型默认（status 里的 tune / defaults） */
const vidP = (k, model = vidKey()) => {
  const a = vidAdv(), v = a[k + '_' + model], m = (VIDST?.models || []).find(x => x.key === model);
  if (v !== undefined && v !== '' && v !== null) return v;
  if (k === 'steps') return m?.defaults?.steps || (model === 'h3' ? 8 : 4);
  if (k === 'split') return Math.max(1, Math.floor(vidP('steps', model) / 2));
  if (k === 'fps') return m?.fps || (model === 'h3' ? 24 : 16);
  return m?.tune?.[k];
};
// LoRA 是不是 H3 能用的：后台按文件头 / Civitai 记录认出 'h3'、'other'（别的模型，包括 Wan）、'?'（看不出来，放行）
const vidLoraOk = (f, M) => { const k = (VIDST?.lora_kind || {})[f]; return !k || k === M || k === '?'; };
// 加速 LoRA（lightx2v 官方，2026-11-06）：官方底模没有内置加速，可选一个叠上去、按它的步数生成；默认不用。
// 生视频只有首帧 / 首尾帧 = FL2VA，放了参考图 / 参考视频 / 参考音频 = Ref2VA；改视频（官方完整版）= Ref2VA。
// 两种各记各的（vidAdv().turbo = { fl2v: 文件名, ref2v: 文件名 }，'' = 不用）
// 2026-11-12 用户定：480p 一律不用加速（后台 videogen 同样跳过）——480p 时不显示“加速”；作者配方（换人 · 新版 / 动作迁移）自带 DMD 8 步，也不显示
const vidLowRes = () => { const st = vidState(); if (st.size !== 'custom') return st.size === '480p' || !st.size; const r = String(st.res || '').trim().replace(/\s*[x×*]\s*/i, 'x');
  const m = r.match(/^(\d+)p?$/) || r.match(/^(\d+)x(\d+)$/); return !!m && Math.min(+m[1], +(m[2] || m[1])) <= 544; };
const vidTurboKind = () => { const st = vidState(); if (vidLowRes()) return null;
  if (st.mode === 'edit') return veRecipe() || veFs() || veVg() ? null : veBaseNow() === 'full' ? 'ref2v' : null;
  return vidGbase() === 'official' ? (vidXref() ? 'ref2v' : 'fl2v') : null; };
const vidTurboKey = () => { const k = vidTurboKind(); return k && (vidState().mode === 'edit' ? 'e_' + k : k); };  // 存的位置：fl2v / ref2v（生成视频）、e_ref2v（改视频）
// 默认的加速：改视频（参考生成）没选过时用 8 步（2026-11-11 用户定）；选了“关”存的是空字符串，照旧不加速
const vidTurboDef = () => { const k = vidTurboKind(); if (k !== 'ref2v' || vidState().mode !== 'edit') return ''; const L = (VIDST?.turbo || []).filter(x => x.kind === k && x.steps === 8); return (L.find(x => x.hd) || L[0])?.file || ''; };
const vidTurbo = () => { const k = vidTurboKind(); let f = k && (vidAdv().turbo || {})[vidTurboKey()]; if (k && f === undefined) f = vidTurboDef(); return f && (VIDST?.turbo || []).find(x => x.file === f && x.kind === k) || null; };
// 表单里“加速”那一行的按钮（不使用 / 8 步 / 4 步…）：没有文件时返回 ''（整行不显示）
const vidTurboHtml = () => { const k = vidTurboKind(), L = (VIDST?.turbo || []).filter(x => x.kind === k), cur = vidTurbo()?.file || '';
  if (!k || !L.length) return '';
  const AB = { fl2v: { 8: '实测：生视频官方原版首帧 480p 用时约为默认的 0.6 倍（34 秒 / 54 秒），画质同样好，动作略大。' },
    ref2v: { 8: '实测：改衣 720p 用时约为默认的一半（399 秒 / 778 秒），画质几乎一样，颜色稍浓。', 4: '实测：改衣 720p 快约 4.6 倍（170 秒 / 778 秒），画面稍柔，大动作时可能有拖影。' } };
  const dup = n => L.filter(x => x.steps === n).length > 1, K = k === 'fl2v' ? 'FL2VA' : 'Ref2VA';
  return `<button type="button" data-k="" class="${cur ? '' : 'on'}" data-tip="默认：不叠加加速 LoRA，按底模默认的步数生成">关</button>`
    + L.map(x => `<button type="button" data-k="${esc(x.file)}" class="${cur === x.file ? 'on' : ''}" data-tip="${esc(`<b>${x.steps} 步</b>（${K} 版 v${x.ver || '?'}${x.hd ? '，768p 训练' : ''}，偏移 ${x.shift} / ${x.ashift}）<br>` + (AB[k]?.[x.steps] || ''))}">${x.steps} 步${dup(x.steps) ? ' v' + esc(x.ver) : ''}</button>`).join(''); };
const VID_TB_TIP = '<b>加速</b>：叠加 lightx2v 官方加速 LoRA，按它的步数生成，明显更快；默认不使用。<br>生视频只有首帧 / 首尾帧时用 FL2VA 版；放入参考图 / 参考视频 / 参考音频、以及改视频时用 Ref2VA 版——这里只列出当前能用的。';
// 画面 / 声音偏移这次起不起作用：② 秋叶节点用它自己的（12 / 3），开了加速按加速 LoRA 的——这两种情况填了也不用
const vidShiftOff = () => { const st = vidState(), E = st.mode === 'edit', off = E ? ['official', 'full'].includes(veBaseNow()) : vidGbase() === 'official';
  return vidTurbo() ? '使用加速 LoRA 时按它的偏移（' + vidTurbo().shift + ' / ' + vidTurbo().ashift + '），这里填的不起作用。' : off && vidEngNow(E) === '2' ? '② 秋叶节点使用它自己的偏移（画面 12、声音 3），这里填的不起作用；要自己设偏移，请在“做法”中选 ① 原生。' : ''; };
const vidLoras4 = M => (vidAdv()['loras_' + M] || []).filter(L => vidLoraOk(L.name, M));
const vidChanged = (k, model = vidKey()) => { const v = vidAdv()[k + '_' + model]; return v !== undefined && v !== '' && v !== null; };
/* 本次会用什么（生成按钮上方那一行，只列值，例如：官方完整版 · 秋叶节点 · 14 步 · 1248×704 · 5 秒），改过的高级参数也列上（2026-11-04 用户要求） */
// skip：这些部分别处已经显示了，不再重复（base 模型 / 底模、res 分辨率、sec 时长、aud 声音、lang 提示词语言）——窄窗口底栏的两个选项按钮、宽窗口展开的参数里都有（2026-11-04 用户要求：同一信息不显示两次）
const vidStepsNow = () => { const st = vidState(), E = st.mode === 'edit', M = vidKey(), a = vidAdv(), m = vidStM() || {}, tb = vidTurbo();
  const off = E ? ['official', 'full'].includes(veBaseNow()) : M === 'h3' && vidGbase() === 'official', en = M === 'h3' ? vidEngNow(E) : '';
  if (E && veRecipe()) return 8;  // 作者配方：DMD 8 步
  if (E && veVg()) return 6;  // Viggle 重拍：官方 6 步
  if (E && veFs()) return vidLowRes() ? (VIDST?.official_steps || 20) : 8;  // 换脸 LoRA：官方加速 8 步（480p 不加速）
  return tb ? tb.steps : en === '2' && off ? 14 : vidChanged('steps', M) ? a['steps_' + M] : off ? (VIDST?.official_steps || 20) : m.defaults?.steps || ''; };
/* 改视频选项里打开了的开关，缩略框里用短字列出（2026-11-10 用户：选了之后下面也要显示，字简单点）：
   Qwen 生成 → Qwen、锁定首帧 → 首帧、共用衣服图 → 共用、加速 → 加速、动作跟随 → 跟随、匹配原视频 → 调色 */
const veOnTags = () => { const ve = veState(), VS = VIDST?.edit || {}, out = [], ref = ve.task === 'outfit' && veMethod() === 'ref';
  if (ref && !veOwn()) { out.push('Qwen'); if (veFfg()) out.push('首帧'); if (ve.qshare === true && veXs().length) out.push('共用'); }
  if (vidTurbo()) out.push('加速');
  if (veVg()) out.push('Viggle'); else if (veLoc()) out.push('局部'); else if (vePose()) out.push('跟随');
  if (ve.task === 'outfit' && ve.emph === true) out.push('每段');
  if (ve.cmatch === true) out.push('调色');
  return out; };
/* 右栏、输入框都收起时（2026-11-08 用户）：输入框左边一行小字，确认这次用的是哪一套——做法、分辨率、步数、声音、底模、节点；点一下展开右栏 */
function vidCurTxt() {
  const st = vidState(), E = st.mode === 'edit', M = vidKey(), ve = veState(), out = [];
  if (E) { out.push(veTaskName(ve.task) + (ve.task === 'swap' ? '（' + ((VE_SWAPS.find(s => s[0] === ve.swap_by) || [])[1] || '') + '）' : ve.task === 'head' ? '（换脸 LoRA）' : veVg() ? '（Viggle 重拍）' : '')); }
  const res = st.size === 'custom' ? String(st.res || '').trim() : st.size;
  out.push(/^\d+$/.test(res) ? res + 'p' : (res || '480p').replace(/\s*[x×]\s*/i, '×'));
  const s = vidStepsNow(); if (s) out.push(s + ' 步');
  out.push(E ? ({ keep: '原声', gen: '重新生成声音', none: '无声' }[ve.audio] || '原声') : M === 'h3' && vidP('audio') === false ? '无声' : '有声');
  out.push(E ? (veVg() ? 'Viggle Remake' : veLite() ? '官方精简' : { official: '官方', full: '官方' }[veBaseNow()] || '') : '官方');
  const en = M === 'h3' ? vidEngNow(E) : ''; if (en) out.push(en === '2' ? '秋叶节点' : '原生节点');
  return out.filter(Boolean).join(' · ');
}
function vidSummary(skip = []) {
  const st = vidState(), E = st.mode === 'edit', M = vidKey(), a = vidAdv(), m = vidStM() || {}, ve = veState();
  const out = [], BN = { official: '官方', full: '官方' }, no = k => skip.includes(k);  // 官方底模在这一行只写 H3（2026-11-05 用户要求，一行放得下）
  const off = E ? ['official', 'full'].includes(veBaseNow()) : M === 'h3' && vidGbase() === 'official';
  if (!no('base')) out.push(E ? (veVg() ? 'Viggle Remake' : veLite() ? '官方精简' : BN[veBaseNow()]) : '官方');  // base：底模
  const en = M === 'h3' ? vidEngNow(E) : '';
  if (en) out.push(en === '2' ? '秋叶节点' : '原生节点');
  const tb = vidTurbo();  // 加速 LoRA：按它的步数
  out.push(vidStepsNow() + ' 步');
  if (tb) out.push('加速 LoRA');
  const src = E ? VE_VID : VID_SRC, mul = 32;
  const res = st.size === 'custom' ? String(st.res || '').trim() : '', short = /^\d+$/.test(res) ? +res : { '480p': 480, '576p': 576, '720p': 720 }[st.size] || 480;
  if (no('res')) ;
  else if (/^\d+\s*[x×]\s*\d+$/i.test(res)) out.push(res.replace(/\s*[x×]\s*/i, '×'));
  else if (src?.w && src?.h) { const k = short / Math.min(src.w, src.h); out.push(src.w && [src.w, src.h].map(v => Math.max(256, Math.round(v * k / mul) * mul)).join('×')); }
  else out.push(short + 'p');
  const sec = E ? (VE_VID ? +(+veSecs()).toFixed(2) : st.eseconds) : st.seconds;  // 改视频选了一段：按真正选的长度（小数）
  if (!no('sec')) out.push(sec + ' 秒');
  if (no('aud')) ;
  else if (E) out.push({ keep: '原声', gen: '重新生成声音', none: '无声' }[ve.audio] || '原声');
  else if (M === 'h3' && vidP('audio') === false) out.push('无声');
  { if (vidChanged('sampler', M)) out.push(a['sampler_' + M]); if (vidChanged('scheduler', M)) out.push(a['scheduler_' + M]);
    if (!vidShiftOff()) { if (vidChanged('shift', M)) out.push('画面偏移 ' + a['shift_' + M]); if (vidChanged('ashift', M)) out.push('声音偏移 ' + a['ashift_' + M]); }
    if (vidChanged('cfg', M)) out.push('CFG ' + a['cfg_' + M]); if (vidChanged('split', M)) out.push(`第 ${a['split_' + M]} 步切换`); }
  if (!E && vidChanged('fps', M)) out.push(a['fps_' + M] + ' fps');
  const ix = a.interp_x || (a.interp ? 2 : 1); if (ix > 1) out.push('插帧 ×' + ix);
  if (a.upscale) out.push('超分 ×2');
  if (a.fast && M === 'h3' && !E && vidEngNow(false) !== '2') out.push('稀疏注意力');  // ② 秋叶节点会去掉稀疏注意力：不列
  const nl = vidLoras4('h3').length; if (nl) out.push(nl === 1 ? '1 个 LoRA' : nl + ' 个 LoRA');
  if (st.seed >= 0) out.push('种子 ' + st.seed);
  if ((st.count || 1) > 1) out.push(`${st.count} 段`);
  if (!no('lang')) out.push(st.plang === 'en' ? '英文提示词' : '中文提示词');
  return out.filter(Boolean).join(' · ');
}

async function renderVideo() {
  const st = vidState();
  // 2026-11-08 用户：打开应用后第一次进生视频页，成品页上什么视频都不放（不平铺全部视频、也不自动打开最近那段，和点了 × 一样）；
  // 之后离开再回来保持上次的样子（看过哪段还是那段）。这次新生成的成品出来时仍会自动切过去（vidGallery 里的“有新成品”）
  if (!renderVideo.entered) { renderVideo.entered = true; vidStage.grid = false; vidStage.closed = true; vidStage.closedFrom = 'one'; vidStage.src = false; vidStage.cur = null; }
  if (!['480p', '576p', '720p', 'custom'].includes(st.size)) st.size = '480p';
  vidSizeMode();
  $('#main').innerHTML = `<div class="page-head"><div class="row vd-title"><h1 class="page-title">生视频</h1><button type="button" class="vd-info" id="vd-info" aria-label="各功能所用的模型与做法" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/><path d="M8 7h8M8 11h6"/></svg></button></div>
      <div class="row ve-head"><div class="row ve-base-h" id="ve-base-h" hidden></div><div class="seg ve-mode" id="vd-mode-sw" role="tablist">${[['gen', '生成视频'], ['edit', '改视频']].map(([k, n]) => `<button type="button" role="tab" data-v="${k}" class="${(st.mode || 'gen') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div></div>
    <div class="ig-grid">
      <div class="card ig-form">
        <div class="field"><span class="label" id="vd-model-l">模型</span><div class="seg full vd-model" id="vd-model"></div><div class="seg full ve-task" id="ve-task" hidden></div><div class="tiny" id="vd-model-d" style="margin-top:6px"></div></div>
        <div class="field"><span class="label" id="vd-src-l" hidden>首帧图片</span><div id="vd-src"></div><div id="ve-src" hidden></div></div>
        <div class="field"><div class="label vd-plab"><span>提示词</span><span class="vd-lang" id="vd-lang"><span class="seg vd-lang-s" data-tip="${esc('中文（默认）：和以前一样。<br>英文：生成前先用本地 AI 模型（约占 23 GB 显存，用完即释放）把中文翻译成英文，翻译结果显示在提示词框下方，可修改；对白（&lt;d&gt;…&lt;/d&gt;）、引号中的画面文字、标签（&lt;Subject 1&gt;、[Shot 1] 等）保持原样，翻译前后不一致时改用中文。改视频的模板换成英文版；AI 优化按英文写。')}">${[['zh', '中文'], ['en', '英文']].map(([k, n]) => `<button type="button" data-l="${k}" class="${(st.plang || 'zh') === k ? 'on' : ''}">${n}</button>`).join('')}</span></span><span class="ve-tplw" id="ve-tplw" hidden></span></div>
          <div class="ig-composer">
            <textarea class="textarea" id="vd-prompt" rows="5">${esc(st.prompt)}</textarea>
            <div class="ig-cbar">
              <button type="button" class="ig-cb" id="vd-ai" title="使用 AI 助手撰写图生视频提示词（会附带首帧图）">${ICON.wand}<span>AI 优化</span></button>
              <button type="button" class="ig-cb" id="vd-gp" hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="10" height="9" rx="2"/><path d="M5.5 11.5l2.5-2.5 3.5 3.5"/><path d="M16.5 9h4M16.5 13h4M3.5 18h17"/></svg><span>生图提示词</span></button>
              <button type="button" class="ig-cb" id="vd-struct" hidden title="提示词模板"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14M5 10h9M5 15h14M5 20h9"/></svg><span>模板</span></button>
              <button type="button" class="ig-cb" id="vd-adv-open" title="步数、采样器、CFG、偏移、帧率、插帧、超分、负面提示词、种子">${ICON.sliders}<span>高级参数</span><span class="ig-adv-n" id="vd-adv-n"></span></button>
              
              <span class="spacer"></span>
              <button type="button" class="ig-gen" id="vd-go" title="生成（Ctrl + Enter）"><span>生成</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
            </div>
          </div><div class="vd-tr" id="vd-tr" hidden></div><div class="tiny ig-note" id="vd-note"></div></div>
        <div class="ig-2">
          <div class="field"><span class="label">时长</span><div class="seg full" id="vd-sec"></div></div>
          <div class="field"><span class="label" data-tip="${esc('按短边计算，长边随首帧比例变化。480p 速度最快；720p 更清晰，但明显更慢、占用显存更多。“自定义”可填写短边（如 640）或宽×高（如 832x480），取 32 的倍数。')}">分辨率</span>
            <div class="seg full" id="vd-size">${[['480p', '480p'], ['576p', '576p'], ['720p', '720p'], ['custom', '自定义']].map(([v, n]) => `<button type="button" data-s="${v}" class="${st.size === v ? 'on' : ''}">${n}</button>`).join('')}</div>
            <input class="input vd-res" id="vd-res" placeholder="短边 640，或 832x480" value="${esc(st.res || '')}"${st.size === 'custom' ? '' : ' hidden'} autocomplete="off" spellcheck="false"></div>
        </div>
        <div class="field vd-gbase-f" id="vd-gbase-f" hidden></div>
        <div class="row vd-opts"></div>
        <div class="ve-opts" id="ve-opts" hidden></div>
        <div class="field vd-tb-f" id="vd-tb-f" hidden><span class="label" data-tip="${esc(VID_TB_TIP)}">加速</span><div class="seg full" id="vd-tb"></div></div>
      </div>
      <div class="stack">
        <div id="vd-live"></div>
        <div class="card ig-gal-card"><div class="row between"><h3 class="card-title" style="margin:0"><span id="vd-ttl">生成结果</span><span class="tiny" id="vd-n" style="margin-left:8px;font-weight:400"></span></h3><div class="vd-jp" id="vd-jp" hidden></div><div class="row" style="gap:8px"><div class="seg vd-dual-t" id="vd-dual-t" role="group" aria-label="右侧显示内容"><button type="button" data-v="src" data-tip="剪辑原视频：拖动黄色框选择要修改的片段">剪辑</button><button type="button" data-v="one" data-tip="只显示生成结果">成品</button><button type="button" data-v="cmp" data-tip="原视频与生成结果同步播放，便于对比">对比</button></div>${galLayBtn('vd-lay')}<button type="button" class="btn small ghost vd-allb" id="vd-all" aria-pressed="false" data-tip="在此平铺显示全部生成的视频">全部视频</button></div></div><div class="vd-gal" id="vd-gal"><div class="shimmer"></div></div></div>
      </div>
    </div>`;
  const tipLabel = (el, text, tip) => { if (!el) return; el.textContent = text; if (tip) el.dataset.tip = tip; else delete el.dataset.tip; };  // 说明停在文字上显示（2026-11-04：问号太多，改掉）
  const SRC_TIP1 = '视频从这张图开始运动：人物长相、服装、场景均以此图为准。使用生图生成的写实图效果最佳。另可添加一张尾帧，视频将停在尾帧画面。';
  const SRC_TIPH = '首帧、参考图、参考视频均放在此处，均为可选：只放首帧 = 图生视频（视频从这张图开始运动）；放入参考图 / 参考视频 = 参考生成（人物、衣服、场景按参考图，动作和镜头按参考视频）；也可同时放入。关键帧、尾帧、开头片段、声音、引导视频位于“更多素材”中。';
  // 生成视频 · H3：首帧、参考图、参考视频放在同一个“素材”区（都可以不放）；Wan 只有首帧
  const vdSrcLabel = () => tipLabel($('#vd-src-l'), st.model === 'h3' ? '素材' : '首帧图片', st.model === 'h3' ? SRC_TIPH : SRC_TIP1);
  const sizeLabel = () => st.size === 'custom' ? (st.res ? (/x|×/i.test(st.res) ? st.res.replace(/x/i, '×') : st.res.replace(/p$/i, '') + 'p') : '自定义') : st.size;
  const vdRefresh0 = igV2({
    prompt: '#vd-prompt',
    // 输入框左边的方块：生成视频 = 首帧图片；改视频 = 原视频（人物图 / 衣服图在旁边的小方块，见 paintVeTile）
    src: { node: $('#vd-src').closest('.field'), thumb: () => st.mode === 'edit' ? (VE_VID ? VE_VID.poster || null : null) : (VID_SRC?.url || null),
      title: () => st.mode === 'edit' ? (VE_VID ? '原视频：点击可更换视频、设置起点' : '原视频：上传或从视频库选择') : '首帧图片',
      icon: () => st.mode === 'edit' ? VID_IC.film : '', x: () => $(st.mode === 'edit' ? '#ve-vid-x' : '#vd-src-x')?.click(),
      ar: () => st.mode === 'edit' && VE_VID?.w && VE_VID?.h ? VE_VID.w / VE_VID.h : 0, badge: () => st.mode === 'edit' && VE_VID ? veSrcBadge() : '' },
    items: [
      { label: () => (st.mode === 'edit' ? veTaskName(veState().task) : '官方原版'), nodes: [$('#vd-model').closest('.field'), $('#vd-gbase-f')] },
      { icon: IG_FRAME, label: () => st.mode === 'edit' ? [`${sizeLabel()} · ${VE_VID ? +(+veSecs()).toFixed(1) : st.eseconds} 秒 · ${(VE_AUDIO.find(a => a[0] === veState().audio) || VE_AUDIO[0])[1]}`, ...veOnTags()].join(' · ')
        : `${sizeLabel()} · ${st.seconds} 秒`, nodes: [$('#vd-sec').closest('.ig-2'), $('.vd-opts'), $('#ve-opts'), $('#vd-tb-f')] },
    ] });
  // 窄窗口 / 手机：点开的参数框不伸到底部播放条下面（以前最后一项“声音”被播放条盖住）；放不下就在框里滚动
  $$('.ig-top-f .ig-chip').forEach(c => c.addEventListener('click', () => {  // igV2 的监听先跑：这时框已经打开、放好位置
    const p = $$('.ig-top-f .ig-panel').find(x => !x.hidden && x.offsetHeight); if (!p || IG_WIDE()) return;
    const pr = pbTopUnder(p);
    p.style.maxHeight = Math.max(220, Math.floor(Math.min(innerHeight * .62, pr - p.getBoundingClientRect().top - 10))) + 'px';
  }));
  const vdRefresh = () => { vdRefresh0(); paintSum(); vdGpSync(); }; renderVideo.vdRefresh = vdRefresh;
  vdB5Head();
  const save = () => persist();
  // ---- 标题旁的“视频功能一览”：电脑上鼠标停 0.6 秒浮出表格、点一下固定（再点 / 点空白处 / Esc 关闭）；手机上点开弹窗。当前所在的功能那一行高亮
  { const info = $('#vd-info'), HOV = matchMedia('(hover: hover) and (pointer: fine)').matches;
    let pop = null, pinned = false, tmr = 0;
    const body = () => `<div class="seg vft-tabs" role="tablist"><button type="button" class="on" data-p="0" role="tab" aria-selected="true">快速对照</button><button type="button" data-p="1" role="tab" aria-selected="false">适不适合</button></div>`
      + `<div class="vft-page" data-p="0"><div class="vft-h">想做什么 → 去哪里</div>${vidGoalTable()}<div class="vft-more"><button type="button" class="btn small ghost vft-more-b" aria-expanded="false">查看详细</button></div>`
      + `<div class="vft-full" hidden><div class="vft-h">每个功能适合什么、不适合什么</div>${vidFitTable()}<div class="vft-h">视频功能一览</div>${vidFuncTable(vidFuncCur())}</div></div>`
      + `<div class="vft-page" data-p="1" hidden><div class="vft-h">什么时候用、什么时候别用</div>${vidFitTable(true)}</div>`;
    const bindMore = root => { $$('.vft-tabs [data-p]', root).forEach(t => t.onclick = e => { e.stopPropagation();  // 两页：快速对照 / 适不适合（简化版）
        $$('.vft-tabs [data-p]', root).forEach(x => { x.classList.toggle('on', x === t); x.setAttribute('aria-selected', String(x === t)); });
        $$('.vft-page', root).forEach(pg => pg.hidden = pg.dataset.p !== t.dataset.p); if (pop && root === pop) { pinned = true; info.classList.add('on'); } });
      const b = $('.vft-more-b', root); if (b) b.onclick = e => { e.stopPropagation(); const f = $('.vft-full', root), open = f.hidden; f.hidden = !open; b.textContent = open ? '收起详细' : '查看详细'; b.setAttribute('aria-expanded', String(open)); if (pop && root === pop) { pinned = true; info.classList.add('on'); } }; };
    const hide = () => { clearTimeout(tmr); pop?.remove(); pop = null; pinned = false; info.classList.remove('on'); info.setAttribute('aria-expanded', 'false'); };
    const show = () => { if (!info.isConnected) return;
      if (!pop) { pop = document.createElement('div'); pop.className = 'vft-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', '视频功能一览'); document.body.append(pop);
        pop.onmouseenter = () => clearTimeout(tmr); pop.onmouseleave = () => { if (!pinned) { clearTimeout(tmr); tmr = setTimeout(hide, 200); } }; }
      pop.innerHTML = body(); bindMore(pop); info.setAttribute('aria-expanded', 'true');
      const r = info.getBoundingClientRect(); pop.style.top = Math.round(r.bottom + 8) + 'px'; pop.style.left = Math.round(Math.max(12, Math.min(r.left - 12, innerWidth - pop.offsetWidth - 12))) + 'px'; };
    if (HOV) { info.onmouseenter = () => { clearTimeout(tmr); if (!pop) tmr = setTimeout(show, 600); }; info.onmouseleave = () => { clearTimeout(tmr); if (pop && !pinned) tmr = setTimeout(hide, 200); }; }
    info.onclick = e => { e.stopPropagation();
      if (!HOV) { const m = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">视频功能一览</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>${body()}`, null, true); m.classList.add('vft-m'); bindMore(m); return; }
      if (pinned) return hide(); clearTimeout(tmr); show(); pinned = true; info.classList.add('on'); };
    const away = e => { if (!info.isConnected) { document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc_, true); return hide(); }
      if (pop && !pop.contains(e.target) && !info.contains(e.target)) hide(); };
    const esc_ = e => { if (e.key === 'Escape' && pop) hide(); };
    if (renderVideo.vftOff) renderVideo.vftOff(); document.addEventListener('pointerdown', away, true); document.addEventListener('keydown', esc_, true);
    renderVideo.vftOff = () => { document.removeEventListener('pointerdown', away, true); document.removeEventListener('keydown', esc_, true); hide(); }; }
  // ---- 提示词语言（中文 / 英文）。英文时生成前把中文翻成英文（后台 ptrans.py：本地 AI 模型，锁住对白 / 画面文字 / 标签，翻完释放显存，按原文缓存）
  //      翻译结果在提示词框下面，可以改；改了原文就重新翻。第一次翻完先停下给人确认，再点一次生成才用
  let TR = null;  // { src, srcT, en, enT, err }
  const hasZh = t => /[\u4e00-\u9fff]/.test(t || '');
  const paintTr = () => {
    const box = $('#vd-tr'); if (!box) return;
    const on = st.plang === 'en' && TR && TR.src === ta.value.trim(); box.hidden = !on; if (!on) return;
    box.innerHTML = TR.busy ? `<div class="vd-tr-h"><span>正在翻译为英文…</span><span class="tiny">本地 AI 模型约占 23 GB 显存，翻译完成后释放</span></div>`
      : TR.err ? `<div class="vd-tr-h err"><span>翻译未通过检查，本次将使用中文生成</span></div><div class="tiny vd-tr-src">${esc(TR.err)}</div>`
      : `<div class="vd-tr-h"><span>英文提示词（翻译结果，可修改）</span><button type="button" class="btn small ghost" id="vd-tr-re">重新翻译</button></div>
        <textarea class="textarea vd-tr-t" id="vd-tr-t" rows="3" spellcheck="false">${esc(TR.en)}</textarea>${TR.srcT ? `<div class="tiny vd-tr-src">要${ve.task === 'swap' ? '换掉' : '改衣'}的人：${esc(TR.enT)}（原文：${esc(TR.srcT)}）</div>` : ''}
        <div class="tiny vd-tr-src">中文原文：${esc(TR.src)}</div>`;
    $('#vd-tr-t', box) && ($('#vd-tr-t', box).oninput = e => { TR.en = e.target.value; });
    $('#vd-tr-re', box) && ($('#vd-tr-re', box).onclick = () => { TR = null; paintTr(); vdTr(st.mode === 'edit', true); });
  };
  async function vdTr(E, force) {  // → { prompt, target, plang } 或 null（先停下：刚翻完给人看 / 出错）
    const src = ta.value.trim(), srcT = E ? (ve.target || '').trim() : '';
    if (st.plang !== 'en') return { prompt: src, target: srcT, plang: 'zh' };
    if (!hasZh(src) && !hasZh(srcT)) return { prompt: src, target: srcT, plang: 'en' };  // 已经是英文（比如 AI 优化按英文写的）
    if (!force && TR && TR.src === src && TR.srcT === srcT && !TR.busy) return TR.err ? { prompt: src, target: srcT, plang: 'zh' } : { prompt: TR.en.trim() || src, target: TR.enT, plang: 'en' };
    TR = { src, srcT, busy: true }; paintTr();
    const one = async t => hasZh(t) ? await api('/api/video/translate', { body: { text: t, lang: 'en' } }) : { text: t };
    try {
      const r1 = await one(src), r2 = await one(srcT);
      TR = r1.error || r2.error ? { src, srcT, err: r1.error || r2.error } : { src, srcT, en: r1.text, enT: r2.text, cached: r1.cached && r2.cached !== false };
    } catch (e) { TR = { src, srcT, err: e.message }; }
    paintTr();
    toast(TR.err ? '翻译未通过检查：再次点击“生成”将使用中文' : '已翻译为英文：请确认后再次点击“生成”', !!TR.err);
    return null;
  }
  $$('#vd-lang [data-l]').forEach(b => b.onclick = () => { const L = b.closest('.vd-lang')?.classList.contains('in-bar') && b.classList.contains('on') ? (b.dataset.l === 'zh' ? 'en' : 'zh') : b.dataset.l;  // 在选项那一排里只显示当前语言：点它 = 换成另一个
    const t = $(`#vd-lang [data-l="${L}"]`) || b; st.plang = L; save(); $$('#vd-lang button').forEach(x => x.classList.toggle('on', x === t)); paintTr(); paintSum(); });
  // 生成按钮那一栏上方：本次使用（只列值）；改视频在宽窗口时可以收起参数（参数那一块藏起来，只留这一行），提示词框变高（2026-11-04）
  const topF = $('#vd-prompt').closest('.ig-top-f'), sumEl = document.createElement('div');
  sumEl.className = 'vd-sum'; sumEl.innerHTML = `<span class="vd-sum-t" id="vd-sum-t"></span><button type="button" class="vd-fold" id="vd-fold" hidden></button>`;
  // 放在生成那一栏里（那一栏贴底，这一行也一直看得见；提示词框量高度时也算进去）：并在 AI 优化等按钮后面，放不下才换到下一行（2026-11-04）
  // 底栏挤的时候（fitCompact）：“本次使用”放不下先让 AI 优化等按钮只留图标；还放不下就自己换到下一行，不再为它把“生成”两个字也收掉
  { const bar = topF?.querySelector(':scope > .ig-cbar'), bl = bar?.querySelector(':scope > .bar-l'), base = bar?._fcTest;
    if (bar) { bar.prepend(sumEl); bar.classList.add('has-sum'); }  // 生成按钮那一栏的最上面单独一行、占满整栏宽度（用户 2026-11-04 定：在生成按钮上面，不排在按钮后面）
    if (base) { bar._fcTest = b => { const s = b.classList.contains('c1') && b.querySelector('.bar-l > .vd-sum'); if (!s) return base(b);
      const d = s.style.display; s.style.display = 'none'; try { return base(b); } finally { s.style.display = d; } }; } }
  const FOLD_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l6-6 6 6"/></svg>';
  function paintCur() {
    const g = $('#main > .ig-grid'); if (!g) return;
    let c = $('#vd-cur');
    if (!c) { c = document.createElement('button'); c.type = 'button'; c.id = 'vd-cur'; c.className = 'vd-cur'; c.hidden = true; c.dataset.tip = '放大提示词框';
      // 2026-11-08 用户：点这一行是放大提示词框（和点进输入框一样展开），不是打开右边的选项栏（右上角的按钮管选项栏）
      c.onclick = () => { const ta = $('#vd-prompt'); if (!ta) return; ta.focus({ preventScroll: true }); const n = ta.value.length; ta.setSelectionRange(n, n); };
      $('#main').append(c); }  // 和任务角标一样放在 #main 下面（那一块有 transform）
    if (c._g !== g) { c._g = g;
      new MutationObserver(() => requestAnimationFrame(vdDockFit)).observe(g, { attributes: true, attributeFilter: ['class'] });
      const comp = g.querySelector(':scope > .ig-top-f'); if (comp && window.ResizeObserver) new ResizeObserver(() => requestAnimationFrame(vdDockFit)).observe(comp);
      if (!vidCurTxt.rs) { vidCurTxt.rs = 1; addEventListener('resize', () => requestAnimationFrame(vdDockFit), { passive: true }); } }
    const t = vidCurTxt(); if (c.dataset.t !== t) { c.dataset.t = t; c.innerHTML = t.split(' · ').map(x => `<span class="vc-i">${esc(x)}</span>`).join(' · '); }  // 每一项不拆开：窄的时候在“ · ”处换行
    c.setAttribute('aria-label', '本次使用：' + t + '（放大提示词框）');
    requestAnimationFrame(vdDockFit);
  }
  function paintTurbo() {  // “加速”：生成视频在左栏一行（#vd-tb），改视频在选项里（#ve-tb）；跟着底模 / 参考 / 做法换成对应的几个，用不了时不显示
    const h = vidTurboHtml(), E = st.mode === 'edit';
    [['#vd-tb-f', '#vd-tb', !E], ['#ve-tb-f', '#ve-tb', E]].forEach(([w, q, on]) => { const f = $(w); if (!f) return; f.hidden = !(h && on); if (h && on && $(q).innerHTML !== h) $(q).innerHTML = h; });
  }
  // 2026-11-08 全面检查：提示词上面那一行只剩“中文 / 英文”时（生视频；改视频没有“使用模板”时），它独占一整行——挪进输入框下面那一排选项里
  function placeLang() {
    const lang = $('#vd-lang'), plab = lang?.closest('.vd-plab') || $('.vd-plab'), bl = topF?.querySelector(':scope > .ig-cbar > .bar-l'), tw = $('#ve-tplw');
    if (!lang || !plab || !bl) return;
    const inBar = !$('#main > .ig-grid')?.classList.contains('b5-on') && (!tw || tw.hidden);
    if (inBar && lang.parentElement !== bl) bl.append(lang);
    else if (!inBar && lang.parentElement !== plab) plab.insertBefore(lang, tw || null);
    lang.classList.toggle('in-bar', inBar); plab.classList.toggle('vd-plab-empty', inBar);
    if (tw && !tw._langMo) { tw._langMo = 1; new MutationObserver(placeLang).observe(tw, { attributes: true, attributeFilter: ['hidden'] }); }
    const g = $('#main > .ig-grid'); if (g && !g._langMo) { g._langMo = 1; new MutationObserver(() => requestAnimationFrame(placeLang)).observe(g, { attributes: true, attributeFilter: ['class'] }); }
  }
  function paintSum() {
    paintTurbo(); paintCur(); placeLang();
    const t = $('#vd-sum-t'); if (!t) return;
    // 同一信息不显示两次：提示词语言本来就在旁边；分辨率 / 时长 / 声音在窄窗口的选项按钮上、宽窗口展开的参数里（收起参数时才列出）；
    // 生成视频的模型 / 底模在模型按钮和标题栏的“底模”上
    const W = IG_WIDE(), full = vidSummary(), txt = vidSummary(['lang', ...(st.mode === 'edit' ? [] : ['base']), ...(W && st.mode === 'edit' && st.efold ? [] : ['res', ...(st.mode === 'edit' && W ? [] : ['sec']), 'aud'])]);
    t.textContent = txt.replace(/ · /g, ' · '); t.title = '本次使用：' + full; { const g = $('#vd-go'); if (g) g.dataset.tip = '本次使用：' + full + '（Ctrl + Enter）'; } $('#va-sum') && ($('#va-sum').textContent = full);  // 点两边用窄空格：省一点宽度，一行放得下（2026-11-05）
    const can = st.mode === 'edit' && W, on = can && !!st.efold, b = $('#vd-fold');
    b.hidden = !can; b.classList.toggle('on', on); b.innerHTML = FOLD_IC + `<span>${on ? '展开参数' : '收起参数'}</span>`;
    b.setAttribute('aria-expanded', String(!on));
    topF?.classList.toggle('vd-folded', on); sumEl.classList.toggle('on', on);
    { const bar = sumEl.closest('.ig-cbar'); if (bar) { const v = Math.max(0, t.offsetHeight - 24) + 'px'; if (bar.style.getPropertyValue('--sumx') !== v) { bar.style.setProperty('--sumx', v); $('#vd-prompt')?.dispatchEvent(new Event('input')); } } }  // 换成多行时：生成那一栏上边距加高（2026-11-05）
    requestAnimationFrame(vePortFit);
    sumEl.closest('.ig-cbar')?._fcRun?.();  // 文字变了：底栏按钮要不要只留图标重新量一次
    growTa();
  }
  // 收起参数时：提示词框的最小高度调大（先多占一点）；之后跟着字数往下长、长满左栏再在框里滚动——这些由 igV2 的 fitTa 做（参数那块一藏，它会重新量）
  const FOLD_MINH = 240;
  function growTa() {
    const ta = $('#vd-prompt'); if (!ta) return;
    const E = st.mode === 'edit' && IG_WIDE(), want = E ? (topF?.classList.contains('vd-folded') ? String(FOLD_MINH) : '80') : null;  // 窄窗口：参数都在弹出的面板里，提示词框和生成视频一样高（2026-11-04 用户要求）
    const rows = E ? 3 : 5;  // 窄窗口的改视频和生成视频一样 5 行高（宽窗口改视频仍是 3 行，参数在下面）
    if ((ta.dataset.minh || null) === want && ta.rows === rows) return;
    ta.rows = rows;
    if (want) ta.dataset.minh = want; else delete ta.dataset.minh;
    ta.dispatchEvent(new Event('input'));  // 让 fitTa 按新的最小高度重新量一次
  }
  $('#vd-fold').onclick = e => { e.stopPropagation(); st.efold = !st.efold; save(); paintSum(); };  // 不往上冒：按钮里的字会重画，冒到这一行时就认不出是点了按钮（以前点了没反应，2026-11-04 修）
  sumEl.onclick = e => { if (!e.target.closest('.vd-fold') && st.efold && st.mode === 'edit' && IG_WIDE()) { st.efold = false; save(); paintSum(); } };
  $('#vd-prompt').addEventListener('input', () => { paintTr(); vdGpSync(); if (!vePortFit.busy) requestAnimationFrame(vePortFit); });
  // 生图提示词（2026-11-11 用户：放了生成的图后，要去生图页→详情→复制提示词再回来）：放的图是生成过的，输入框下面就多一个按钮，点一下填入当时的提示词（可撤销）
  $('#vd-gp').onclick = () => { const g = vdGp(), ta = $('#vd-prompt'); if (!g || !ta) return; const old = ta.value; ta.value = g; ta.dispatchEvent(new Event('input', { bubbles: true }));
    if (old.trim()) toastAct('已填入生图提示词', '撤销', () => { ta.value = old; ta.dispatchEvent(new Event('input', { bubbles: true })); }); else toast('已填入生图提示词'); ta.focus(); };
  if (renderVideo.onRs) removeEventListener('resize', renderVideo.onRs);
  renderVideo.onRs = () => { if ($('#vd-sum-t')) paintSum(); }; addEventListener('resize', renderVideo.onRs, { passive: true });
  if (window.ResizeObserver) { let lh = -1; new ResizeObserver(() => { const t = $('#vd-sum-t'), b = sumEl.closest('.ig-cbar'); if (!t || !b || t.offsetHeight === lh || window.fsHold?.()) return;
    lh = t.offsetHeight; const v = Math.max(0, lh - 24) + 'px'; if (b.style.getPropertyValue('--sumx') !== v) { b.style.setProperty('--sumx', v); $('#vd-prompt')?.dispatchEvent(new Event('input')); } requestAnimationFrame(vePortFit); }).observe($('#vd-sum-t')); }  // 左栏宽度变了、行数跟着变
  let ms = VIDST?.models || [];
  const paintModel = () => {
    if (!$('#vd-model')) return;
    if (VIDST?.error && !ms.length) { $('#vd-model-d').textContent = /not found|404/i.test(VIDST.error) ? '后台仍是旧版本，请重启 Studio。' : VIDST.error; return; }
    // 模型说明放在按钮的悬停提示里，左栏只在缺文件时显示一行（一屏放下）
    $('#vd-model').innerHTML = ms.map(m => `<button type="button" data-m="${m.key}" class="${st.model === m.key ? 'on' : ''}" title="${esc(`${m.tag} · ${m.speed}${m.audio ? ' · 带声音' : ''}\n${m.desc}`)}"${m.missing.length ? ' disabled' : ''}>${esc(m.key === 'h3' ? 'MiniMax H3' : m.name)}${m.missing.length ? ' · 未下载' : ''}</button>`).join('');  // H3 只用官方原版
    const m = ms.find(x => x.key === st.model);
    $('#vd-model-d').textContent = m?.missing.length ? '尚缺文件：' + m.missing.join('、') : ''; $('#vd-model-d').hidden = !$('#vd-model-d').textContent;
    mfHide();
    $$('#vd-model [data-m]').forEach(b => b.onclick = () => { st.model = b.dataset.m; save(); paintModel(); paintAdvN(); renderVideo.paintSec?.(); paintSrc(); paintStruct(); vdRefresh?.(); });
    paintGenBase();
  };
  // 生视频 · H3 的底模：官方原版（官方完整版 int8：只有首帧时 FL2VA，用了参考时 Ref2VA；没加速，20 步）
  const GB_HINT = '<b>官方原版</b>（推荐）：参考更准确。MiniMax H3 官方完整版（34GB，int8），只有首帧时使用 FL2VA，放入参考图 / 参考视频 / 参考音频时自动切换为 Ref2VA；放入参考视频（以它的动作为参考）时默认使用 ① 原生节点（20 步，较慢，动作节奏与参考视频更一致）；其余情况（首帧、首尾帧、只有参考图 / 参考音频）默认使用 ② 秋叶节点（14 步）。';
  const paintGenBase = () => {
    const show = false, ok = VIDST?.official || {}, can = ok.fl2va || ok.ref2va;  // 只有官方原版：不显示底模选择
    const seg = full => `<div class="seg${full ? ' full' : ''} ve-base vd-gbase">${[['official', '官方原版', '<b>官方原版</b>（推荐）：参考更准确']].map(([k, n, tip]) => `<button type="button" data-k="${k}" class="${vidGbase() === k ? 'on' : ''}"${k === 'official' && VIDST && !can ? ' disabled title="尚未放入官方完整版底模（minimax_h3_fl2va / ref2va_int8_convrot）"' : ` data-tip="${esc(tip)}"`}>${n}${k === 'official' ? REC : ''}</button>`).join('')}</div>`;
    const lab = `<span class="label" data-tip="${esc(GB_HINT)}">底模</span>`;
    const hb = $('#ve-base-h'), f = $('#vd-gbase-f');
    if (hb) { hb.innerHTML = lab + seg(false); hb.hidden = !show; }
    if (f) { f.innerHTML = lab + seg(true); f.hidden = !show; }
    $$('.vd-gbase [data-k]').forEach(b => b.onclick = () => { st.gbase = b.dataset.k; save(); paintGenBase(); paintAdvN(); vdRefresh?.(); });
  };
  renderVideo.paintGenBase = () => paintGenBase();
  // 只剩一个模型（H3，2026-11-06 去掉 Wan）：生成视频时不显示“模型”这一栏（只有一个按钮，没得选）；缺文件、出错时照样显示说明
  const mfHide = () => { const mf = $('#vd-model')?.closest('.field'); if (mf) mf.hidden = st.mode !== 'edit' && ms.length <= 1 && !$('#vd-model-d').textContent; };
  const fixModel = () => { if (!ms.some(m => m.key === st.model)) st.model = 'h3'; };  // 以前存的 'wan' 换成 H3
  fixModel(); paintModel(); vdRefresh();
  api('/api/video/status').then(r => r, e => ({ error: e.message, models: [] })).then(r => {
    VIDST = r; ms = r.models || []; fixModel(); paintModel(); paintAdvN(); paintSrc(); vdRefresh(); renderVideo.paintMode?.();
  });
  // ---- 首帧 / 尾帧
  const flfOk = () => vidStM()?.flf !== false;
  const paintSrc = () => {
    const box = $('#vd-src'); if (!box) return;
    { const mf = $('#vd-model')?.closest('.field'); if (mf?._home && mf.parentElement !== mf._home) mf._home.prepend(mf); }  // 上次搬到首帧旁边的“模型”先放回原处（下面要重写这一块）
    if (!VID_SRC && st.srcId) { const x = imgGal.find(g => g.id === st.srcId); if (x) VID_SRC = vidImg(x); }
    const s = VID_SRC, e = VID_END, M = /Mac/.test(navigator.platform) ? '⌘' : 'Ctrl';
    if (st.mode !== 'edit') vdSrcLabel();
    // H3：首帧的“粘贴 / 选图”放进空的首帧框里（下面那一排留给参考图、参考视频、更多素材，不挤成两行）
    const H3g = st.model === 'h3' && st.mode !== 'edit';
    const PB = `<span class="vd-pick-in"><button type="button" class="btn small" id="vd-paste" title="粘贴剪贴板中的图片（截图后直接点击此处）">粘贴</button><button type="button" class="btn small" id="vd-up" title="从电脑里选择图片">从电脑选</button><button type="button" class="btn small" id="vd-pick" title="从生图图库选择">从图库选</button></span>`;
    // 首帧（大）和尾帧（右边窄的一格，可选）并排
    box.innerHTML = `<div class="vd-frames">` + (s ? `<div class="ig-src" data-b5n="首帧" data-b5l="1"><img src="${esc(s.url)}" alt="" draggable="false"><button type="button" class="ig-src-x" id="vd-src-x" title="移除此图" aria-label="移除此图">${ICON.x}</button></div>`
      : `<div class="ig-src empty b5-up" id="vd-pick-area" data-b5n="首帧" data-b5l="1" role="button" tabindex="0" aria-label="添加首帧">${ICON.up}<div>首帧</div>${H3g ? '<span class="tiny">可选</span>' + PB : ''}</div>`)
      + (flfOk() ? `<div class="vd-f2${e ? '' : ' empty'}" id="vd-f2" data-b5n="尾帧" data-b5l="1" role="button" tabindex="0" title="尾帧（可选）：视频最终停在此图画面">${e ? `<img src="${esc(e.url)}" alt="" draggable="false"><button type="button" class="ig-src-x" id="vd-ex" title="移除尾帧" aria-label="移除尾帧">${ICON.x}</button>`
        : `${VID_IC.end}<span>尾帧</span><span class="tiny">可选</span>`}</div><input type="file" id="vd-efile" accept="image/*" hidden>` : '') + `</div>`
      + (s ? `<div class="tiny vd-src-i">${s.w || '?'} × ${s.h || '?'}${s.kind === 'gallery' ? ' · 生图图库' : ''}${s.chain ? ` · <span class="vd-chain-t">${VID_IC.chain}续接上一段，完成后自动合成</span><button type="button" class="vd-link" id="vd-chain-x">取消续接</button>` : ''}</div>` : '')
      + (s && !(st.model === 'h3' && st.mode !== 'edit') ? '' : `<div class="row ig-src-btns ig-src-btns-r vd-src-row"><span id="vd-xslot" class="row vd-xslot"></span><span class="spacer"></span>${s || H3g ? '' : PB}</div>`) + `<input type="file" id="vd-file" accept="image/*" hidden>`;  // 放了首帧后这排只给首帧用、容易误会：隐藏；点 × 去掉首帧后再出现
    vdSide(box, s);
    if ($('#vd-up')) $('#vd-up').onclick = e => { e.stopPropagation(); $('#vd-file').click(); };
    const area = $('#vd-pick-area');
    const srcMats = () => matsPick('image', async f => { try { loadFile(await matsFile(f)); } catch (er) { toast(er.message, true); } });
    const srcItems = () => [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: srcMats }, { label: '从电脑选择', icon: ICON.up, on: () => $('#vd-file').click() },
      { label: '粘贴', icon: CTX_IC.open, on: () => $('#vd-paste')?.click() }, { label: '从生图图库选择', icon: CTX_IC.open, on: () => $('#vd-pick')?.click() }, ...(typeof frUseItem === 'function' ? [frUseItem('用作首帧', fs => loadFile(fs[0]))] : [])];  // 视频截图（2026-11-19）
    if (area) { area.onclick = ev => { if (ev.target.closest('button')) return;
        slotPick(area, srcItems()); };  // 2026-11-10：点一下直接打开素材库（右键：其他来源）
      area.oncontextmenu = ev => { ev.preventDefault(); ctxMenu({ anchor: area }, srcItems()); };
      area.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); area.click(); } };
      area.ondragover = ev => { ev.preventDefault(); area.classList.add('over'); }; area.ondragleave = () => area.classList.remove('over');
      area.ondrop = ev => { ev.preventDefault(); area.classList.remove('over'); const f = [...(ev.dataTransfer.files || [])].find(x => x.type.startsWith('image/')); if (f) loadFile(f); }; }
    $('#vd-file').onchange = ev => { const f = ev.target.files[0]; if (f) loadFile(f); };
    { const vi = $('#vd-src .ig-src > img'); if (vi) { vi.classList.add('zoomable'); vi.title = '点击查看大图'; vi.onclick = () => zoomImgs([VID_SRC?.url, VID_END?.url], 0); } }  // 首帧点开看大图
    $('#vd-src-x') && ($('#vd-src-x').onclick = () => { VID_SRC = null; st.srcId = null; save(); paintSrc(); });
    $('#vd-chain-x') && ($('#vd-chain-x').onclick = () => { if (VID_SRC) delete VID_SRC.chain; paintSrc(); });
    if ($('#vd-pick')) $('#vd-pick').onclick = e => { e.stopPropagation(); pickGal(x => { VID_SRC = vidImg(x); st.srcId = x.id; save(); paintSrc(); }); };
    if ($('#vd-paste')) $('#vd-paste').onclick = async e => { e.stopPropagation();
      try { for (const it of await navigator.clipboard.read()) { const t = it.types.find(x => x.startsWith('image/')); if (t) return loadFile(new File([await it.getType(t)], 'paste.png', { type: t })); } toast('剪贴板中没有图片', true); }
      catch { toast(`此处无法直接读取剪贴板：请按 ${M} + V 粘贴`, true); }
    };
    const f2 = $('#vd-f2');
    if (f2) {
      $('#vd-efile').onchange = ev => { const f = ev.target.files[0]; if (f) loadFile(f, true); ev.target.value = ''; };
      f2.onclick = ev => { if (ev.target.closest('#vd-ex')) { ev.stopPropagation(); VID_END = null; return paintSrc(); }
        if (VID_END) return zoomImgs([VID_SRC?.url, VID_END.url], VID_SRC ? 1 : 0);  // 有尾帧：点开看大图（换图：右键，或者先点 × 去掉）
        endMenu(f2, true); };  // 空的：电脑上直接从素材库选（右键：从电脑选、粘贴、生图图库）
      if (!VID_END) f2.title = MOB() ? '尾帧（可选）' : '尾帧（可选）：点击从素材库选；右键：从电脑选、粘贴、生图图库';
      f2.oncontextmenu = ev => { ev.preventDefault(); endMenu(f2); };
      f2.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); endMenu(f2); } };
      f2.ondragover = ev => { ev.preventDefault(); f2.classList.add('over'); }; f2.ondragleave = () => f2.classList.remove('over');
      f2.ondrop = ev => { ev.preventDefault(); f2.classList.remove('over'); const f = [...(ev.dataTransfer.files || [])].find(x => x.type.startsWith('image/')); if (f) loadFile(f, true); };
    }
    paintEndTile(); paintX();
    requestAnimationFrame(vdSrcFit);  // 尾帧 / 素材按钮画完以后右边那一列多高才知道
  };
  renderVideo.repaintSrc = paintSrc;
  { const ta = $('#vd-prompt'); if (ta && !ta._vdfit) { ta._vdfit = 1; ta.addEventListener('input', () => requestAnimationFrame(vdSrcFit)); } }
  // ---- H3 的更多条件：首帧下面一排，加了才显示；Wan 没有这些
  const X_IC = {
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M12 2.5v4M12 17.5v4"/></svg>',
    aud: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/></svg>' };
  const X_HINT = '首帧、参考图、参考视频均放在此处，均为可选。以下均为 MiniMax H3 自带的功能，可同时使用：<br><b>关键帧</b>：在指定秒数放入一张图，视频到该时刻即为此画面（可放入多张）。<br><b>开头片段</b>：取一段视频的末尾（或开头）不到 2 秒，接在新视频最前面，动作和声音随之延续；与首帧二选一。实测片段结束处画面常会变亮、跳动一下（社区中不使用自定义节点的做法均有此问题），因此“续接”仍使用最后一帧。<br><b>指定声音</b>：放入一段声音，从指定秒数开始对齐，例如让人物按这段话说话、随这段音乐律动。<br><b>参考图</b>：人物、衣服、物品、场景、画风按这几张图生成（提示词中可用 &lt;Picture 1&gt;、&lt;Picture 2&gt; 指代）。<br><b>参考视频</b>：动作和镜头按这段视频生成（&lt;Video 1&gt;）；其原声可不使用、作为参考，或直接用于驱动（成品的声音即为这段原声）。<br><b>参考音频</b>：说话的音色按这段声音生成（&lt;Audio N&gt;，排在带原声的参考视频之后）。<br><b>引导视频</b>：整段从第 0 帧起逐帧跟随，配合特效编辑（VFX Edit）这类 LoRA 修改视频（即以前的“自由修改”）。<br>提示词中未提及的参考会自动在末尾补充一句。使用参考时，官方原版自动切换为 Ref2VA。H3 也可不放首帧，仅按文字和这些素材生成。点击“AI 优化”时，这些素材会一并提供给 AI 助手。';
  const xImg = (file, done) => {  // 图片：和首帧一样，太大时缩到 2048 以内
    const fr = new FileReader(); fr.onload = () => { const im = new Image(); im.onload = () => {
      let [w, h] = [im.naturalWidth, im.naturalHeight], data = fr.result;
      if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) { const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height; }
      done({ kind: 'upload', data, url: data, w, h }); }; im.onerror = () => toast('无法打开此图（仅支持 PNG / JPG / WebP）', true); im.src = fr.result; }; fr.readAsDataURL(file); };
  const xVid = (file, done) => {
    if (!file.type.startsWith('video/') && !/\.(mp4|mov|m4v|webm|avi)$/i.test(file.name || '')) return toast('仅支持视频文件（MP4 / MOV / WebM / AVI）', true);
    if (file.size > 30 * 1048576) return toast('视频过大（最多约 30MB），请先剪短', true);
    const v = { kind: 'upload', file, url: URL.createObjectURL(file), dur: 0, w: 0, h: 0 }, pr = document.createElement('video'); pr.preload = 'metadata'; pr.muted = true;
    pr.onloadedmetadata = () => { v.dur = pr.duration || 0; v.w = pr.videoWidth; v.h = pr.videoHeight; paintX(); }; pr.src = v.url; done(v); };
  const xAud = (file, done) => {
    if (file.size > 20 * 1048576) return toast('声音文件过大（最多约 20MB）', true);
    const fr = new FileReader(); fr.onload = () => { const a = { name: file.name || '声音', data: fr.result, dur: 0 }, au = new Audio(); au.preload = 'metadata';
      au.onloadedmetadata = () => { a.dur = au.duration || 0; paintX(); }; au.src = fr.result; done(a); }; fr.readAsDataURL(file); };
  const xPick = (accept, fn) => { const i = document.createElement('input'); i.type = 'file'; i.accept = accept; i.onchange = () => { const f = i.files[0]; if (f) fn(f); }; i.click(); };
  const xPickVid = async put => {
    if (!vidGal.length) vidGal = await api('/api/video/gallery').catch(() => []);
    const list = vidGal.slice(0, 200); if (!list.length) return toast('视频库中尚无视频', true);
    modal(`<h3 class="card-title" style="margin:0 0 10px">从视频库选择一段</h3><div class="ig-pick">${list.map((x, i) => `<button type="button" class="ig-pick-t ve-pick-t" data-i="${i}" title="${esc(x.prompt || '')}">${x.thumb ? `<img loading="lazy" src="${vidUrl(x.thumb)}" alt="">` : VID_IC.film}<span class="ve-pick-d">${Math.round(+x.duration || x.seconds || 0)} 秒</span></button>`).join('')}</div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>取消</button></div>`, box => {
      $$('.ve-pick-t', box).forEach(b => b.onclick = () => { box.close(); put(veGalVid(list[+b.dataset.i])); });
    }, true);
  };
  const xAdd = (anchor, only) => {  // only：'refs' / 'rvids' = 直接加参考图 / 参考视频（素材区里的两个按钮）
    if (anchor && !anchor.getClientRects().length && window.ctxAnchorFor) anchor = window.ctxAnchorFor;  // 从输入框上那一摞点的：后面几层菜单也贴着那里（2026-11-11）
    const full = (k, n) => VID_X[k].length >= n;
    const AUD = 'audio/*,.wav,.mp3,.m4a,.flac,.ogg';
    const imgMenu = (put, label) => ctxMenu({ anchor }, [{ label: '上传' + label, icon: ICON.up, on: () => xPick('image/*', f => xImg(f, put)) },
      { label: '粘贴', icon: CTX_IC.open, on: async () => { const f = await clipImage(); if (f) xImg(f, put); } },
      { label: '从生图图库选择', icon: CTX_IC.open, on: () => pickGal(x => put(vidImg(x))) },
      { label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: () => matsPick('image', async f => { try { xImg(await matsFile(f), put); } catch (e) { toast(e.message, true); } }) }, ...(typeof frUseItem === 'function' ? [frUseItem('用作' + label, fs => fs.forEach(f => xImg(f, put)), true)] : [])]);
    const audMenu = put => ctxMenu({ anchor }, [{ label: '上传声音', icon: ICON.up, on: () => xPick(AUD, f => xAud(f, put)) },
      { label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: () => matsPick('audio', async f => { try { xAud(await matsFile(f), put); } catch (e) { toast(e.message, true); } }) }]);
    const RMAX = VIDST?.h3max?.refs || 9;
    const vidMenu = (put, label) => ctxMenu({ anchor }, [{ label: '上传' + label, icon: ICON.up, on: () => xPick('video/*,.mov,.m4v', f => xVid(f, put)) },
      { label: '从视频库选择', icon: CTX_IC.open, on: () => xPickVid(put) },
      { label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: () => matsPick('video', f => { let put1 = false; matsVid(f, v => { if (!put1) { put1 = true; put(v); } else paintX(); }); }) }]);
    if (only === 'refs') return full('refs', RMAX) ? toast(`参考图最多 ${RMAX} 张`, true) : imgMenu(im => { VID_X.refs.push(im); paintX(); vdRefresh(); }, '参考图');
    if (only === 'rvids') return full('rvids', 3) ? toast('参考视频最多 3 段', true) : vidMenu(v => { VID_X.rvids.push(Object.assign(v, { snd: 'none' })); paintX(); vdRefresh(); }, '参考视频');
    ctxMenu({ anchor }, [
      { label: '关键帧：指定秒数显示此图', icon: X_IC.key, on: () => full('keys', 6) ? toast('关键帧最多 6 张', true) : imgMenu(im => { VID_X.keys.push({ img: im, t: Math.max(1, Math.round(st.seconds / 2)) }); paintX(); }, '关键帧') },
      { label: '开头片段：接续一段视频', icon: VID_IC.chain, on: () => vidMenu(v => { VID_X.clip = { vid: v, part: 'tail', n: 22 }; paintX(); }, '视频') },
      { label: '指定声音：按这段声音生成', icon: X_IC.aud, on: () => audMenu(a => { VID_X.audio = { ...a, start: 0 }; paintX(); }) },
      { label: '参考图：人物 / 衣服 / 场景 / 画风', icon: CTX_IC.open, on: () => full('refs', RMAX) ? toast(`参考图最多 ${RMAX} 张`, true) : imgMenu(im => { VID_X.refs.push(im); paintX(); }, '参考图') },
      { label: '参考视频：动作和镜头', icon: VID_IC.film, on: () => full('rvids', 3) ? toast('参考视频最多 3 段', true) : vidMenu(v => { VID_X.rvids.push(Object.assign(v, { snd: 'none' })); paintX(); }, '参考视频') },
      { label: '参考音频：说话的音色', icon: X_IC.aud, on: () => full('raudios', 3) ? toast('参考音频最多 3 段', true) : audMenu(a => { VID_X.raudios.push(a); paintX(); }) },
      { label: '引导视频：逐帧跟随修改（特效编辑 LoRA）', icon: VID_IC.film, on: () => VID_X.guide ? toast('仅可放入一段引导视频', true) : vidMenu(v => { VID_X.guide = { vid: v, audio: true }; paintX(); vdRefresh(); }, '引导视频') }]);
  };
  const paintX = () => {
    const box = $('#vd-src'); if (!box) return;
    let el = $('#vd-x', box);
    const slot = $('#vd-xslot', box);
    if (st.model !== 'h3' || st.mode === 'edit') { if (el) el.remove(); if (slot) slot.innerHTML = ''; return; }
    if (!el) { el = document.createElement('div'); el.id = 'vd-x'; el.className = 'vd-x'; box.appendChild(el); }
    const X = VID_X, sec = st.seconds;
    const th = (u, vid) => u ? (vid ? `<video src="${esc(u)}" muted playsinline preload="metadata"></video>` : `<img src="${esc(u)}" alt="">`) : `<span class="vx-ic">${X_IC.aud}</span>`;
    const dur = d => d ? ` · ${(+d).toFixed(1)} 秒` : '';
    const rows = [
      ...X.keys.map((k, i) => ({ k: 'keys', i, t: th(k.img.url), b: `关键帧 ${k.t} 秒`, n: '关键帧', c: `<label class="vx-c">第<input class="input" type="number" min="0" max="${sec}" step="0.5" value="${k.t}" data-kt="${i}">秒</label>` })),
      ...(X.clip ? [{ k: 'clip', t: th(X.clip.vid.url, true), b: '开头片段', n: '开头片段' + dur(X.clip.vid.dur),
        c: `<select class="select vx-sel" data-clip="1" aria-label="选取片段">${[['tail', 22, '取最后 0.9 秒'], ['tail', 39, '取最后 1.6 秒'], ['head', 22, '取最前 0.9 秒'], ['head', 39, '取最前 1.6 秒']].map(([p, n, l]) => `<option value="${p}${n}"${X.clip.part === p && X.clip.n === n ? ' selected' : ''}>${l}</option>`).join('')}</select>` }] : []),
      ...(X.audio ? [{ k: 'audio', t: th(null), b: '指定声音', aud: 1, n: '指定声音 · ' + esc(X.audio.name.slice(0, 40)) + dur(X.audio.dur), c: `<label class="vx-c">从第<input class="input" type="number" min="0" max="${sec}" step="0.5" value="${X.audio.start}" data-as="1">秒开始</label>` }] : []),
      ...X.refs.map((r, i) => ({ k: 'refs', i, t: th(r.url), b: `参考图 ${i + 1}`, n: `参考图 · &lt;Picture ${i + 1}&gt;` })),
      ...(X.guide ? [{ k: 'guide', t: th(X.guide.vid.url, true), b: '引导视频', n: '引导视频' + dur(X.guide.vid.dur),
        c: `<label class="vx-c" title="原视频有声音时，成品使用其原声"><input type="checkbox" data-gau="1"${X.guide.audio !== false ? ' checked' : ''}>原声</label>` }] : []),
      ...X.rvids.map((r, i) => ({ k: 'rvids', i, t: th(r.url, true), b: `参考视频 ${i + 1}`, n: `<span title="参考视频 &lt;Video ${i + 1}&gt;${r.name ? ' · ' + esc(r.name) : ''}">&lt;Video ${i + 1}&gt;${dur(r.dur)}</span>`,
        c: `<select class="select vx-sel" data-snd="${i}" aria-label="原声" title="这段视频原声的用法：不使用；作为参考（声音的风格、音色以其为准）；驱动（成品的声音即为这段原声）；重混（重新生成原声部分，需要做法 ② 的节点）">${[['none', '不使用原声'], ['ref', '原声作参考'], ['lock', '原声驱动'], ['remix', '重混（需 ②）']].map(([k, n]) => `<option value="${k}"${(r.snd || 'none') === k ? ' selected' : ''}${k === 'remix' ? ' disabled' : ''}>${n}</option>`).join('')}</select>` })),
      ...X.raudios.map((r, i) => ({ k: 'raudios', i, t: th(null), b: `参考音频 ${i + 1}`, aud: 1, n: `参考音频 · &lt;Audio ${X.rvids.filter(v => v.snd && v.snd !== 'none').length + i + 1}&gt; · ${esc(r.name.slice(0, 30))}` + dur(r.dur) }))];
    el.innerHTML = rows.map(r => `<div class="vx-it${r.aud ? ' b5-aud' : ''}" data-k="${r.k}" data-i="${r.i ?? ''}" data-b5n="${esc(r.b)}"><span class="vx-th">${r.t}</span><span class="vx-n">${r.n}</span>${r.c || ''}<button type="button" class="pl-ib vx-x" data-rx="1" title="移除" aria-label="移除">${ICON.x}</button></div>`).join('');
    el.hidden = !rows.length;
    if (slot) { slot.innerHTML = `<button type="button" class="btn small ghost vx-addb" id="vx-ref" title="参考图：人物、衣服、物品、场景、画风以此为准（&lt;Picture N&gt;）">${ICON.plus}参考图</button>`
        + `<button type="button" class="btn small ghost vx-addb" id="vx-rvid" title="参考视频：动作和镜头以此为准（&lt;Video N&gt;）">${ICON.plus}参考视频</button>`
        + `<button type="button" class="btn small ghost vx-addb" id="vx-add" data-tip="${esc(X_HINT)}">${ICON.plus}更多素材</button>`;
      $$('.vx-addb', slot).forEach(b => { b.classList.add('b5-add'); b.dataset.b5n = b.id === 'vx-ref' ? '参考图' : b.id === 'vx-rvid' ? '参考视频' : '更多素材'; });
      $('#vx-add', slot).onclick = e => { e.stopPropagation(); xAdd(e.currentTarget); };
      $('#vx-ref', slot).onclick = e => { e.stopPropagation(); xAdd(e.currentTarget, 'refs'); };
      $('#vx-rvid', slot).onclick = e => { e.stopPropagation(); xAdd(e.currentTarget, 'rvids'); }; }
    $$('.vx-x', el).forEach(b => b.onclick = () => { const it = b.closest('.vx-it'), k = it.dataset.k, i = +it.dataset.i;
      const drop = v => { if (v?.url?.startsWith('blob:')) URL.revokeObjectURL(v.url); };
      if (k === 'clip') { drop(X.clip.vid); X.clip = null; } else if (k === 'guide') { drop(X.guide.vid); X.guide = null; } else if (k === 'audio') X.audio = null; else { if (k === 'rvids') drop(X.rvids[i]); X[k].splice(i, 1); }
      paintX(); vdRefresh(); });
    $$('[data-kt]', el).forEach(i => i.onchange = () => { const v = Math.max(0, Math.min(sec, Math.round((+i.value || 0) * 2) / 2)); X.keys[+i.dataset.kt].t = v; i.value = v; });
    $('[data-as]', el) && ($('[data-as]', el).onchange = e => { const v = Math.max(0, Math.min(sec, Math.round((+e.target.value || 0) * 2) / 2)); X.audio.start = v; e.target.value = v; });
    $$('[data-snd]', el).forEach(sel => sel.onchange = () => { const i = +sel.dataset.snd, v = sel.value;
      if (v === 'lock') { if (X.audio) { sel.value = X.rvids[i].snd || 'none'; return toast('“指定声音”和“原声驱动”只能二选一：请先移除指定声音', true); } X.rvids.forEach((r, k) => { if (k !== i && r.snd === 'lock') r.snd = 'ref'; }); }
      X.rvids[i].snd = v; paintX(); });
    $('[data-gau]', el) && ($('[data-gau]', el).onchange = e => { X.guide.audio = e.target.checked; });
    $('[data-clip]', el) && ($('[data-clip]', el).onchange = e => { const v = e.target.value; X.clip.part = v.startsWith('head') ? 'head' : 'tail'; X.clip.n = +v.replace(/\D/g, ''); });
    $$('.vx-th img', el).forEach(im => { im.classList.add('zoomable'); im.onclick = () => zoomImgs([im.src], 0); });
  };
  const pickGal = async fn => { if (!imgGal.length) imgGal = await api('/api/img/gallery').catch(() => []); imgPick(fn); };
  const endMats = () => matsPick('image', async f => { try { loadFile(await matsFile(f), true); } catch (e) { toast(e.message, true); } });
  // endMenu(anchor, direct)：direct = 点空格（电脑上直接开素材库，2026-11-10）
  const endMenu = (anchor, direct) => (direct ? slotPick : (a, it) => ctxMenu({ anchor: a }, it))(anchor, [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: endMats },
    { label: VID_END ? '从电脑选择（更换）' : '从电脑选择', icon: ICON.up, on: () => $('#vd-efile')?.click() },
    { label: '粘贴', icon: CTX_IC.open, on: async () => { const f = await clipImage(); if (f) { loadFile(f, true); toast('已将粘贴的图片设为尾帧'); } } },
    { label: '从生图图库选择', icon: CTX_IC.open, on: () => pickGal(x => { VID_END = vidImg(x); paintSrc(); }) },
    ...(typeof frUseItem === 'function' ? [frUseItem('用作尾帧', fs => loadFile(fs[0], true))] : []), ...(VID_END ? [{ label: '移除尾帧', icon: CTX_IC.del, danger: true, on: () => { VID_END = null; paintSrc(); } }] : [])]);
  // 窄窗口：输入框左边首帧方块旁边再放一个小方块（尾帧）；宽窗口时这些方块不显示，尾帧在左栏首帧下面
  const paintEndTile = () => {
    const row = $('.ig-crow'); if (!row) return;
    let t = $('#vd-endt');
    if (!t) { t = document.createElement('button'); t.type = 'button'; t.id = 'vd-endt'; t.className = 'ig-srct vd-endt'; t.title = '尾帧（可选）'; t.setAttribute('aria-label', '尾帧（可选）'); row.querySelector('.ig-srct')?.after(t);
      t.onclick = ev => { ev.stopPropagation(); endMenu(t); }; }
    t.hidden = st.mode === 'edit' || !(flfOk() && (VID_SRC || VID_END));  // 去掉首帧时尾帧留着（重新放首帧就行）；改视频时不显示
    t.innerHTML = VID_END ? `<img src="${esc(VID_END.url)}" alt="">` : VID_IC.end;
  };
  const loadFile = (file, isEnd) => {
    const fr = new FileReader(), gen = VGEN;
    fr.onload = () => {
      if (gen !== VGEN || !$('#vd-src')) return;
      const im = new Image();
      im.onload = () => {
        let [w, h] = [im.naturalWidth, im.naturalHeight], data = fr.result;
        if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) {
          const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k);
          c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height;
        }
        if (isEnd) VID_END = { kind: 'upload', data, url: data, w, h };
        else { VID_SRC = { kind: 'upload', data, url: data, w, h }; st.srcId = null; save(); vidImgPrompt(file, VID_SRC, vdGpSync); }
        paintSrc();
      };
      im.onerror = () => toast('无法打开此图（仅支持 PNG / JPG / WebP）', true);
      im.src = fr.result;
    };
    fr.readAsDataURL(file);
  };
  paintSrc();
  if (st.srcId && !VID_SRC && !imgGal.length) api('/api/img/gallery').then(g => { imgGal = g; paintSrc(); }, () => { });
  const onPaste = e => {
    if (!$('#vd-go')) return document.removeEventListener('paste', onPaste);
    if (st.mode === 'edit') {  // 改视频：粘贴视频 = 原视频；粘贴图片 = 人物图 / 衣服图
      const fs = [...(e.clipboardData?.files || [])], v = fs.find(x => x.type.startsWith('video/')), im = fs.find(x => x.type.startsWith('image/'));
      if (v) { e.preventDefault(); return veLoadVid(v); }
      if (im && veState().task !== 'free') { e.preventDefault(); veLoadImg(im); toast(['swap', 'motion'].includes(veState().task) ? '已将粘贴的图片设为人物图' : veState().task === 'head' ? '已将粘贴的图片设为头像' : veOwn() ? '已将粘贴的图片设为参考图' : '已将粘贴的图片设为衣服图'); }
      return;
    }
    const f = [...(e.clipboardData?.files || [])].find(x => x.type.startsWith('image/')); if (!f) return;
    e.preventDefault();
    if (flfOk() && document.querySelector('#vd-f2:hover, #vd-f2:focus, #vd-endt:hover, #vd-endt:focus')) { loadFile(f, true); return toast('已将粘贴的图片设为尾帧'); }  // 鼠标停在尾帧格子上：粘成尾帧
    loadFile(f); toast('已将粘贴的图片设为首帧');
  };
  document.removeEventListener('paste', renderVideo.paste || (() => { })); renderVideo.paste = onPaste; document.addEventListener('paste', onPaste);
  // ---- 按结构写：生成视频（H3）和改视频的参考生成都有。模板按现在放的素材拼（‹…› 是要换成自己内容的地方），照 laowang A/B 的写法
  function paintStruct() {
    const b = $('#vd-struct'); if (!b) return;
    b.hidden = st.mode === 'edit' ? false : st.model !== 'h3';  // 改视频：每个任务都有模板可填（2026-11-08）
  }
  const structTpl = () => {
    const X = VID_X, E = st.mode === 'edit', ve = veState(), L = [], R = [];
    if (E) {  // 改视频的参考生成：原视频 <Video 1>，人物图 / 换好衣服的图 <Picture 1>
      const T = VIDST?.edit?.templates || {}, tg = (ve.target || '').trim();
      if (ve.task === 'motion') return T.motion || '';
      if (ve.task === 'swap' && ve.swap_by === 'v11') return T.v11 || '';
      return ve.task === 'swap' ? (T.ref_swap || '').replace('‹提示词框里写的（可选）›', '‹人物的样子：发型、肤色、身材、穿着›').replace(/‹要换掉的人›/g, tg || '主要人物')
        : (T.ref_outfit || '').replace('‹提示词框里写的（可选）›', '‹新衣服的样子›').replace(/‹要改衣的人›/g, tg || '人物');
    }
    const ref = vidXref(), first = !!VID_SRC;
    const tag = X.guide ? '[video editing]' : ref && first ? '[keyframe completion + reference generation]' : ref ? '[reference generation]' : first ? '[image to video]' : '[text to video]';
    if (first && !ref) { L.push('<Subject 1> 是来自 <Picture 1> 的‹人物：性别、年龄、脸、发型、肤色、身材、穿着›。'); L.push('<Subject 2> 是来自 <Picture 1> 的‹场景：地点、陈设、光线›。'); L.push('<Picture 1> 是目标视频的精确首帧。');
      R.push('<Subject 1>（出现在 [Shot 1]）：fully_preserved - 脸、发型、肤色、身材和穿着完整保留。'); R.push('<Subject 2>（出现在 [Shot 1]）：fully_preserved - 场景和光线完整保留。'); R.push('<Picture 1>：fully_preserved - 作为首帧，构图、机位和光线保持一致。'); }
    else {
      X.refs.forEach((r, i) => { L.push(`<Subject ${i + 1}> 是来自 <Picture ${i + 1}> 的‹人物 / 衣服 / 物品 / 场景：写清样子›。`); L.push(`<Picture ${i + 1}> 是提供 <Subject ${i + 1}> 外观的参考图。`);
        R.push(`<Subject ${i + 1}>（出现在 [Shot 1]）：fully_preserved - ‹哪些和 <Picture ${i + 1}> 一致›。`); });
      if (first) { L.push('视频从首帧的画面开始。'); }
      X.rvids.forEach((v, i) => { L.push(`<Video ${i + 1}> 是参考视频，提供‹动作 / 机位 / 节奏›${v.snd && v.snd !== 'none' ? '和声音' : ''}。`); R.push(`<Video ${i + 1}>：attribute_transfer - 保留它的‹动作、身体朝向与节奏›，人物和场景换成上面的主体。`); });
      if (X.guide) { L.push('原视频（引导视频）提供每一帧的画面、动作和机位。'); R.push('原视频：partially_preserved - ‹哪些不变、只改什么›。'); }
      if (!L.length) { L.push('<Subject 1> 是‹人物：性别、年龄、脸、发型、肤色、身材、穿着›。'); R.push('<Subject 1>（出现在 [Shot 1]）：‹出现时的状态›。'); }
    }
    const nt = X.rvids.filter(v => v.snd && v.snd !== 'none').length;
    X.raudios.forEach((a, i) => L.push(`<Audio ${nt + i + 1}> 是参考音频，提供说话的音色。`));
    return ['subject_definitions:', ...L, '', 'summary:', `${tag} ‹一两句话概括整段视频›`, '', 'retention_analysis:', ...R, '',
      'detailed_description:', '写实风格，‹镜头 / 景别›，‹光线›，画面清晰锐利，无切镜。', `[Shot 1] ‹按时间写动作：动作开始、连续发展、结果；写清身体部位、方向、速度和幅度，头发、衣服的反应和表情›。脸始终清晰。`, '',
      'overall_soundscape:', '‹环境声、动作声、人声›', '', 'non_diegetic_music:', 'N/A'].join('\n');
  };
  $('#vd-struct').onclick = async e => { e.stopPropagation(); const ta = $('#vd-prompt'), anchor = e.currentTarget;
    if (st.mode === 'edit') {  // 改视频（2026-11-08）：当前任务能用的模板全部列出来（后台按现在的设置拼好），填入后关掉“使用模板”，自己改写
      let items = [];
      try { items = (await api('/api/video/edit-templates', { body: { edit: { ...ve, target: (ve.target || '').trim(), plang: st.plang === 'en' ? 'en' : 'zh' }, prompt: ta.value, has_ref: !!VE_REF } })).items || []; }
      catch (er) { return toast(/not found|404/i.test(er.message) ? '后台版本过旧，请重启 Studio' : er.message, true); }
      return ctxMenu({ anchor }, items.map(x => ({ label: `填入「${x.label}」模板`, icon: CTX_IC.open, on: () => veFillTpl(x) })));
    }
    ctxMenu({ anchor }, [
      { label: '填入结构化模板' + (ta.value.trim() ? '（替换当前提示词）' : ''), icon: CTX_IC.open, on: () => { ta.value = structTpl(); const m = /‹[^›]*›/.exec(ta.value); ta.focus(); if (m) ta.setSelectionRange(m.index, m.index + m[0].length); ta.dispatchEvent(new Event('input', { bubbles: true })); toast('请将 ‹…› 替换为您的内容'); } },
      { label: '由 AI 助手按结构化写法撰写（附带素材）', icon: ICON.wand, on: () => vdAi('video-h3s') }]); };
  // ---- 选项
  const ta = $('#vd-prompt');
  if (!ta.value && sessionStorage.getItem('vdDraft')) ta.value = st.prompt = sessionStorage.getItem('vdDraft');
  if (!st.eprompt && sessionStorage.getItem('veDraft')) st.eprompt = sessionStorage.getItem('veDraft');
  ta.oninput = () => {  // 生成视频 / 改视频各记各的提示词
    if (st.mode === 'edit') { st.eprompt = ta.value; sessionStorage.setItem('veDraft', ta.value); }
    else { st.prompt = ta.value; sessionStorage.setItem('vdDraft', ta.value); }
    persistSoon();  // 2026-11-17 审查 P09：打字时合并写入（失焦 / 换页时立刻写）
  };
  ta.onkeydown = e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); return; }
    if ((e.key === 'Tab' || e.key === 'Enter') && !e.shiftKey && !e.altKey && !e.isComposing && veTplFill()) e.preventDefault();  // 关了模板：空框里按 Tab / 回车填入原本的模板
  };
  const paintSec = () => {  // 时长：滑杆 + 数字框（像可灵）
    // 拖动条的范围：Wan 2~6 秒（训练长度约 5 秒，再长容易倒退 / 循环）；H3 生视频 4~15 秒；改视频：参考生成 2~15 秒、还原优先 / 换头 / 保真替换 2~10 秒、参考编辑 2~5 秒。
    // 数字框可以填到这种做法本身的硬上限（改视频：VIDST.edit.hard_seconds，H3 节点最多 3600 帧 = 150 秒；参考编辑 5 秒），超过拖动条时拖动条停在最右端、标成“已超出拖动范围”。
    // 改视频还有“跟随原视频”：时长 = 原视频从起点往后剩下的长度（不超过硬上限）。刻度均匀（同一个间隔，从右端往左排）（2026-11-04 改）
    const E = st.mode === 'edit', K = E ? 'eseconds' : 'seconds', ve = veState(), VS = VIDST?.edit || {};
    // 改视频的时长 = 剪辑里选的那一段（2026-11-06 用户：有剪辑了，左栏的时长、跟随原视频都是重复的），这一行不显示
    { const fld = $('#vd-sec')?.closest('.field'); if (fld) fld.hidden = E; if (E) return; }
    const left = E && VE_VID?.dur ? Math.max(0, VE_VID.dur - (+ve.start || 0)) : 0;
    const R = E && veRef();
    const HS = VS.hard_seconds || {}, hard = E ? HS.h3 || 150 : 15;
    const [lo, sMax0] = E ? [2, R ? VS.max_seconds_ref || 15 : VS.max_seconds || 10] : [4, 15];
    const cap = E && left >= 1 ? Math.min(hard, Math.floor(left)) : hard;  // 数字框的上限：不超过原视频剩下的长度
    const sMax = Math.max(lo, Math.min(sMax0, cap));
    const follow = E && !!ve.follow, lock = follow && left >= 1;  // 还没放原视频时跟随不了：拖动条、数字框照常能调（以前一直锁着，2026-11-04 修）
    const stp = [1, 2, 3, 5].find(k => Math.floor((sMax - lo) / k) + 1 <= 6) || 5;
    const ticks = []; for (let t = sMax; t >= lo; t -= stp) ticks.unshift(t);
    if (follow && left >= 1) st[K] = Math.min(hard, Math.floor(left));
    st[K] = Math.max(lo, Math.min(cap, Math.round(+st[K] || 5)));
    const box = $('#vd-sec'); box.className = 'vd-dur' + (E ? ' vd-dur-e' : '');
    const pct = v => sMax > lo ? (Math.min(v, sMax) - lo) / (sMax - lo) * 100 : 100;
    box.innerHTML = `<div class="vd-dur-s"><input type="range" id="vd-sec-r" min="${lo}" max="${sMax}" step="1" value="${Math.min(st[K], sMax)}" aria-label="时长"${sMax > lo && !lock ? '' : ' disabled'}>
        <div class="vd-dur-t">${ticks.map(t => `<span style="left:${pct(t)}%">${t}</span>`).join('')}</div></div>
      ${E ? `<button type="button" class="vd-follow${follow ? ' on' : ''}" id="vd-follow" aria-pressed="${follow}" data-tip="${esc('打开后，时长与原视频从起点往后的长度一致' + (hard < 150 ? `（此做法最长 ${hard} 秒）` : '') + '。')}">跟随原视频</button>` : ''}
      <label class="vd-dur-n"><input type="number" id="vd-sec-n" min="${lo}" max="${cap}" step="1" value="${st[K]}" aria-label="秒"${lock ? ' disabled' : ''}><span>s</span>
        <span class="vd-dur-b"><button type="button" data-d="1" aria-label="加一秒"${lock ? ' disabled' : ''}>▲</button><button type="button" data-d="-1" aria-label="减一秒"${lock ? ' disabled' : ''}>▼</button></span></label>`;
    const set = v => {
      st[K] = Math.max(lo, Math.min(cap, Math.round(+v || lo))); save();
      const over = st[K] > sMax;  // 超出拖动范围：拖动条停在最右端，最右的刻度标成“15+”
      $('#vd-sec-r').value = Math.min(st[K], sMax); $('#vd-sec-n').value = st[K];
      $('#vd-sec-r').style.setProperty('--p', pct(st[K]) + '%');
      box.classList.toggle('over', over);
      $$('.vd-dur-t span', box).forEach(x => { const t = +x.textContent.replace('+', ''); x.classList.toggle('on', t === st[K] || (over && t === sMax)); x.textContent = t + (over && t === sMax ? '+' : ''); });
      box.title = over ? `已超出拖动范围（${sMax} 秒），将按填写的 ${st[K]} 秒生成` : E ? (left && left < sMax0 ? `原视频从起点起仅剩 ${Math.floor(left)} 秒` : R ? '参考生成建议不超过 15 秒；时长越长，耗时越久' : '换人 4~5 秒效果最稳定，更长时容易走样') : st[K] >= 10 ? '耗时较长：24GB 显卡上可能需要十分钟左右' : '';
      vdRefresh?.();
    };
    const unseg = () => { if (E && veCut()) { delete ve.end; if (!((+ve.start || 0) > 0.05)) ve.splice = false; setTimeout(veSegSync); } };  // 手动改时长：选段的结束点不再用
    $('#vd-sec-r').oninput = e => { unseg(); set(e.target.value); };
    $('#vd-sec-n').onchange = e => { unseg(); set(e.target.value); };
    $$('.vd-dur-b button', box).forEach(b => b.onclick = () => { unseg(); set(st[K] + +b.dataset.d); });
    $('#vd-follow') && ($('#vd-follow').onclick = () => { unseg(); ve.follow = !ve.follow; save(); paintSec(); });
    set(st[K]);
  };
  paintSec(); renderVideo.paintSec = paintSec;
  const resOk = v => !v || /^\d{3,4}p?$/i.test(v) || /^\d{3,4}\s*[x×*]\s*\d{3,4}$/i.test(v);
  $$('#vd-size [data-s]').forEach(b => b.onclick = () => {
    st.size = b.dataset.s; save(); $$('#vd-size button').forEach(x => x.classList.toggle('on', x === b));
    $('#vd-res').hidden = st.size !== 'custom'; if (st.size === 'custom') $('#vd-res').focus(); vdRefresh();
  });
  $('#vd-res').oninput = e => { st.res = e.target.value.trim(); e.target.classList.toggle('bad', !resOk(st.res)); persistSoon(); vdRefresh(); };
  function tbClick(e) { const b = e.target.closest('[data-k]'), k = vidTurboKind(); if (!b || !k) return;
    const a = vidAdv(); a.turbo = { ...(a.turbo || {}), [vidTurboKey()]: b.dataset.k }; save(); $$('#vd-tb button, #ve-tb button').forEach(x => x.classList.toggle('on', x.dataset.k === b.dataset.k)); paintAdvN(); }
  $('#vd-tb').onclick = tbClick;
  // ---- 高级参数（弹窗）：模型能调的都在这里；每个模型各记各的
  const curM = () => ms.find(x => x.key === vidKey());
  function paintAdvN() {
    const a = vidAdv(), M = vidKey();
    const n = VID_PER.filter(k => vidChanged(k, M) && !(['shift', 'ashift'].includes(k) && vidShiftOff()) && String(a[k + '_' + M]) !== String(k === 'steps' ? curM()?.defaults?.steps : k === 'fps' ? curM()?.fps : curM()?.tune?.[k])).length
      + ((vidTurbo()?.file || '') !== vidTurboDef() ? 1 : 0) + (a.interp ? 1 : 0) + (a.upscale ? 1 : 0) + (a.fast && M === 'h3' && st.mode !== 'edit' && vidEngNow(false) !== '2' ? 1 : 0) + (st.seed >= 0 ? 1 : 0) + (vidLoras4('h3').length ? 1 : 0) + ((st.count || 1) > 1 ? 1 : 0)
      + (st.mode === 'edit' && (veState().base || 'lite') !== 'lite' ? 1 : 0) + ((st.engine || 'auto') !== 'auto' ? 1 : 0)
      + (st.mode === 'edit' ? (veTpl() && veState().task !== 'head' && (veState().target || '').trim() ? 1 : 0) : 0);
    if ($('#vd-adv-n')) { $('#vd-adv-n').textContent = n ? String(n) : ''; $('#vd-adv-n').title = n ? `已修改 ${n} 项` : ''; }
    { const root = $('#va-seed')?.closest('.modal');  // 弹窗开着：标出改过的是哪几项（和上面的数字一样的判断）
      if (root) advMark(root, [...VID_PER.filter(k => vidChanged(k, M) && !(['shift', 'ashift'].includes(k) && vidShiftOff()) && String(a[k + '_' + M]) !== String(k === 'steps' ? curM()?.defaults?.steps : k === 'fps' ? curM()?.fps : curM()?.tune?.[k])).map(k => 'va-' + k),
        ...(a.interp ? ['va-ix'] : []), ...(a.upscale ? ['va-up'] : []), ...(a.fast && M === 'h3' && st.mode !== 'edit' && vidEngNow(false) !== '2' ? ['va-fast'] : []),
        ...(st.seed >= 0 ? ['va-seed'] : []), ...(vidLoras4('h3').length ? ['va-loras'] : []), ...((st.count || 1) > 1 ? ['va-count'] : []),
        ...(st.mode === 'edit' && (veState().base || 'lite') !== 'lite' ? ['va-base'] : []), ...((st.engine || 'auto') !== 'auto' ? ['va-eng'] : []),
        ...(st.mode === 'edit' ? [...(veTpl() && veState().task !== 'head' && (veState().target || '').trim() ? ['va-target'] : [])] : [])]); }
    paintSum();
  }
  $('#vd-adv-open').onclick = () => {
    const a = vidAdv(), m = curM() || {}, M = vidKey(), T = m.tune || {}, E = st.mode === 'edit', ve = veState(), VS = VIDST?.edit || {};
    const LM = 'h3';  // 只有 H3（Wan 2.2 及其保真替换 / 参考编辑 2026-11-06 去掉）
    const ixNow = a.interp_x || (a.interp ? 2 : 1);
    const opt = (list, cur, dflt) => `<option value="">默认（${esc(dflt)}）</option>` + (list || []).map(v => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(v)}</option>`).join('');
    const pv = k => vidChanged(k) ? a[k + '_' + M] : '';
    const sw = (id, on, txt, hint, dis) => `<label class="vd-sw${dis ? ' off' : ''}"><span${hint ? ` data-tip="${esc(hint)}"` : ''}>${txt}</span><span class="switch"><input type="checkbox" id="${id}"${on ? ' checked' : ''}${dis ? ' disabled' : ''}><span></span></span></label>`;
    const fastF = () => { const e2 = vidEngNow(false) === '2';  // ② 秋叶节点会把稀疏注意力去掉（换成它自己的 Sage 注意力）：开了也没用，变灰并说明（2026-11-06）
      return `<div class="field va-fast-f"><span class="label">注意力</span>${sw('va-fast', !!a.fast && !e2, '稀疏注意力', e2 ? '当前使用 ② 秋叶节点（官方原版底模默认用它）：它自带 Sage 注意力，会去掉稀疏注意力，开启也不起作用。<br>要使用稀疏注意力：在“做法”中选 ①。' : '社区推荐的 BlockSparseAttention：每步只计算最相关的约 10% 注意力，生成速度提升约四分之一（实测 5 秒 480p：47 → 36 秒），清晰度不变；但同一种子生成的画面会与未开启时不同。<br>只在 ① 原生节点上起作用（② 秋叶节点会去掉它）。', e2)}</div>`; };
    const offNow = () => E ? ['official', 'full'].includes(veBaseNow()) : M === 'h3' && vidGbase() === 'official';  // 官方底模：没加速，默认 20 步
    const OS = VIDST?.official_steps || 20, BN = { official: '官方精简版', full: '官方' };
    const ENG = [{ key: 'auto', name: '自动', ready: true }, ...(VIDST?.engines || [{ key: '1', name: '① 原生节点', short: '原生', ready: true }]).filter(x => x.key !== '3')];
    const ENG_TIP = { auto: '<b>自动</b>（默认）：生视频放入参考视频（以它的动作为参考）时使用 ① 原生（20 步）；其余情况官方底模均使用 ② 秋叶节点（14 步），包括首帧、首尾帧、只有参考图 / 参考音频，以及改视频的换人 · 审美优先、改衣 · 参考生成；开头片段、引导视频使用 ①。',
      1: '<b>① 原生</b>：本应用自行搭建的工作流，20 步。生视频放入参考视频时推荐使用：动作节奏与参考视频对得更准（第 3 轮同框对比的结论）。开头片段、引导视频也使用此做法。',
      2: '<b>② 秋叶节点</b>：秋叶的“质量稳定优先流”（T8 条件、多速率采样、Sage 注意力），14 步，速度快一倍。除“生视频放入参考视频”外均推荐使用（含改视频的参考生成）；仅适用于官方底模。' };
    const RV = !E && !!VID_X.rvids.length;  // 生视频放了参考视频：推荐 ①，否则推荐 ②
    const fEng = M === 'h3' ? `<div class="field ve-wide"><span class="label">做法</span>`
      + `<div class="seg full" id="va-eng">${ENG.map(x => `<button type="button" data-k="${x.key}" class="${(st.engine || 'auto') === x.key ? 'on' : ''}"${x.ready ? ` data-tip="${esc(ENG_TIP[x.key] || '')}"` : ' disabled title="尚未安装"'}>${esc(x.key === 'auto' ? '自动' : x.key === '1' ? '① 原生' : x.name)}${(x.key === '1' && RV) || (x.key === '2' && !RV && x.ready) ? REC : ''}</button>`).join('')}</div>`
      + `</div>` : '';
    const BASE_TIP = { auto: '<b>跟随做法</b>（默认）：参考生成（换人 · 审美优先、改衣 · 参考生成）使用官方；作者配方、换脸 LoRA 使用官方精简。',
      full: '<b>官方</b>（推荐用于参考生成）：参考更准确。官方 Ref2VA 完整版（34GB）+ int8 文字编码器；参考生成默认使用 ② 秋叶节点（14 步）。',
      lite: '<b>官方精简</b>：官方 Ref2VA 精简版（21GB）+ nvfp4 文字编码器。少占约 15GB 内存、略快，画面与官方相当（2026-11-09 夜测）；其余设置与官方相同。' };
    const fBaseE = E ? `<div class="field ve-wide"><span class="label">底模</span>`
      + `<div class="seg full" id="va-base">${VE_BASES.map(([k, n, sn]) => `<button type="button" data-k="${k}" class="${(ve.base || 'auto') === k ? 'on' : ''}"${(k === 'official' && !VS.official) || (k === 'full' && !VS.full) || (k === 'lite' && !VS.lite) ? ' disabled title="尚未下载"' : ` data-tip="${esc(BASE_TIP[k])}"`}><span class="lb-l">${n}</span><span class="lb-s">${sn}</span></button>`).join('')}</div>`
      + `</div>` : '';
    const advTitle = () => `高级参数 · ${E ? '改视频（' + esc(veLite() ? 'H3 官方精简' : BN[veBaseNow()] ? 'H3 ' + BN[veBaseNow()] : 'H3') + '）' : esc(M === 'h3' && vidGbase() === 'official' ? 'MiniMax H3 · 官方原版' : m.name || '')}`;
    const shOff = () => vidShiftOff();
    const shiftF = () => `<label class="field va-sh-f"><span class="label" data-tip="${esc(shOff() || 'MiniMax H3 视频部分的 sigma 偏移，官方默认 12。')}">画面偏移 Shift</span><input class="input" id="va-shift" type="number" step="0.5" min="0.5" max="30" placeholder="${shOff() && vidTurbo() ? vidTurbo().shift : T.shift ?? ''}" value="${shOff() ? '' : pv('shift')}"${shOff() ? ' disabled' : ''}></label>`;
    const ashiftF = () => `<label class="field va-ash-f"><span class="label" data-tip="${esc(shOff() || 'H3 声音部分的 sigma 偏移，官方默认 3。')}">声音偏移</span><input class="input" id="va-ashift" type="number" step="0.5" min="0.5" max="30" placeholder="${shOff() && vidTurbo() ? vidTurbo().ashift : T.ashift ?? 3}" value="${shOff() ? '' : pv('ashift')}"${shOff() ? ' disabled' : ''}></label>`;
    const stepsF = () => vidTurbo() ? `<label class="field"><span class="label" data-tip="${esc('使用加速 LoRA 时按它的步数生成，不可修改。')}">步数</span><input class="input" id="va-steps" type="number" placeholder="${vidTurbo().steps}" value="" disabled></label>`
      : offNow() && vidEngNow(E) === '2' ? `<label class="field"><span class="label" data-tip="${esc('② 秋叶节点使用其自带的采样设置：视频、声音各 14 步，不可修改。')}">步数</span><input class="input" id="va-steps" type="number" placeholder="14" value="" disabled></label>`
      : offNow() ? `<label class="field"><span class="label" data-tip="${esc(`官方底模没有内置加速，默认 ${OS} 步（ComfyUI 官方模板的取值）；步数越多，速度越慢。`)}">步数</span><input class="input" id="va-steps" type="number" min="1" max="40" placeholder="${OS}" value="${pv('steps')}"></label>`
      : `<label class="field"><span class="label" data-tip="${esc(`已内置加速，默认 ${m.defaults?.steps || ''} 步即可；增加步数会更慢，画面不一定更好。`)}">步数</span><input class="input" id="va-steps" type="number" min="1" max="40" placeholder="${m.defaults?.steps || ''}" value="${pv('steps')}"></label>`;
    const box = modal(`<div class="row between vd-adv-h"><h3 class="card-title" style="margin:0" id="va-title">${advTitle()}</h3><button class="btn small" data-close>完成</button></div>
      <div class="tiny vd-sum-a" id="va-sum">${esc(vidSummary())}</div>
      <div class="vd-adv">
        <div class="ig-sec" data-tip="${esc('放入 ComfyUI\\models\\loras 的 MiniMax H3 LoRA 均可在此选择，最多 4 个。' + (E || vidXref() ? '当前使用参考模式（Ref2VA），作者区分版本时请选 Ref2VA 版。' : '当前使用首帧模式（FL2VA），作者区分版本时请选 FL2VA 版。'))}">LoRA</div>
        <div id="va-loras"></div>
        <div class="vd-g2 va-gen">
          <div class="field"><span class="label" data-tip="${esc('一次排队生成多段，每段使用不同的种子。')}">生成数量</span><div class="seg full" id="va-count">${[1, 2, 3, 4].map(n => `<button type="button" data-n="${n}" class="${(st.count || 1) === n ? 'on' : ''}">${n} 段</button>`).join('')}</div></div>
          <div class="field"><span class="label" data-tip="${esc('留空 = 每次随机。如需在同一效果上微调提示词，请填入上次的种子。')}">种子</span><div class="row" style="gap:6px"><input class="input" id="va-seed" type="number" min="0" placeholder="随机" value="${st.seed >= 0 ? st.seed : ''}" style="flex:1;min-width:0"><button type="button" class="btn icon-btn" id="va-dice" title="随机种子" aria-label="随机种子">${IMG_IC.dice}</button></div></div>
          <div class="field"><span class="label" data-tip="${esc('生成后在帧间补帧：帧率按倍数提高，时长和动作速度不变，画面更顺滑。RIFE：速度快、效果好（推荐 ×2）；FILM：甩手、转身这类大动作重影更少，但约慢 4 倍；ffmpeg：旧方式，大动作容易拉扯变形。倍数越高越容易出现细小扭曲，一般不超过 ×3。')}">插帧</span><div class="seg full" id="va-ix">${[1, 2, 3, 4].map(n => `<button type="button" data-x="${n}" class="${ixNow === n ? 'on' : ''}">${n === 1 ? '关' : '×' + n}</button>`).join('')}</div>
            <select class="select vd-iby" id="va-iby"${ixNow > 1 ? '' : ' hidden'}>${[['rife', 'RIFE 4.26（推荐）'], ['film', 'FILM（大动作更稳，较慢）'], ['ff', 'ffmpeg（旧方式）']].filter(([k]) => k === 'ff' || (VIDST?.interp || []).includes(k)).map(([k, n]) => `<option value="${k}"${(a.interp_by || 'rife') === k ? ' selected' : ''}>${n}</option>`).join('')}</select></div>
          <div class="field"><span class="label">超分</span>${sw('va-up', a.upscale, '分辨率 ×2', VIDST?.upscaler ? '使用 Real-ESRGAN x2 逐帧放大（较长的视频自动改用 Lanczos）。' : '未找到 Real-ESRGAN 模型，将使用 Lanczos 放大。')}</div>
          ${E && veTpl() && ve.task !== 'head' && !veRecipe() ? `<div class="field"><span class="label" data-tip="${esc('视频中有多人时请写明是哪一位，例如“左边穿白衣服的女人”。只有一人时无需填写。')}">要${ve.task === 'swap' ? '换掉' : '改衣'}的人</span><input class="input" id="va-target" placeholder="可选，例如：左边的女人" value="${esc(ve.target || '')}" autocomplete="off" spellcheck="false"></div>` : ''}
        </div>
        <details class="adv-more" data-more="video-more"><summary><span>更多参数</span>${ICON.chev}</summary><div class="adv-more-b">
          ${fBaseE || fEng ? `<div class="vd-stack">${fBaseE}${fEng}</div>` : ''}
          <div class="vd-g3 va-more">
            ${stepsF()}
            <label class="field"><span class="label">采样器</span><select class="select" id="va-sampler">${opt(VIDST?.samplers, pv('sampler'), T.sampler)}</select></label>
            <label class="field"><span class="label">调度器</span><select class="select" id="va-scheduler">${opt(VIDST?.schedulers, pv('scheduler'), T.scheduler)}</select></label>
            ${shiftF()}
            ${ashiftF()}
            <div class="field"><span class="label">声音</span>${sw('va-audio', vidP('audio') !== false, '生成声音', '关闭后只生成画面，速度稍快。')}</div>
            <label class="field"><span class="label" data-tip="${esc(`模型按此帧率生成（默认 ${m.fps || ''} fps）。调高后帧数增加、速度变慢；H3 训练使用 24 fps。`, 'sm')}">生成帧率</span><input class="input" id="va-fps" type="number" min="8" max="30" placeholder="${m.fps || ''}" value="${pv('fps')}"></label>
            ${!E ? fastF() : ''}
          </div>
        </div></details>
        ${E && veTplBlock(ve, VS) ? `<details class="adv-more" data-more="video-tpl"><summary><span>提示词模板</span>${ICON.chev}</summary><div class="adv-more-b va-tplb">${veTplBlock(ve, VS)}</div></details>` : ''}
        <div class="row" style="justify-content:flex-end;margin-top:6px"><button type="button" class="btn small ghost" id="va-reset">全部恢复默认</button></div>
      </div>`, null, true);
    box.classList.add('vd-adv-m');
    const upd = () => { save(); paintAdvN(); };
    // 底模 / 做法一变：步数、“这次用”、标题跟着变——原地换掉这几处（以前是关掉重开，用户看着像又弹了一次框，2026-11-04 改）
    const reAdv = () => { save(); paintAdvN();
      const sf = $('#va-steps', box)?.closest('.field'); if (sf) { sf.outerHTML = stepsF(); per('va-steps', 'steps', v => Math.max(1, Math.min(40, parseInt(v)))); }
      const shf = $('.va-sh-f', box); if (shf) { shf.outerHTML = shiftF(); per('va-shift', 'shift', parseFloat); }  // 偏移起不起作用跟着底模 / 做法变
      const ashf = $('.va-ash-f', box); if (ashf) { ashf.outerHTML = ashiftF(); per('va-ashift', 'ashift', parseFloat); }
      const ff = $('.va-fast-f', box); if (ff) { ff.outerHTML = fastF(); bindFast(); }  // 换了做法：稀疏注意力能不能用跟着变
      $('#va-title', box).innerHTML = advTitle(); };
    $$('#va-base [data-k]', box).forEach(b => b.onclick = () => { ve.base = b.dataset.k; $$('#va-base button', box).forEach(x => x.classList.toggle('on', x === b)); reAdv(); renderVideo.paintMode?.(); });
    $$('#va-eng [data-k]', box).forEach(b => b.onclick = () => { st.engine = b.dataset.k; $$('#va-eng button', box).forEach(x => x.classList.toggle('on', x === b)); reAdv(); });
    if (E) {  // 改视频：帧率跟原视频（24 fps），声音在左边“声音”里选，这两项不显示
      $('#va-fps', box)?.closest('.field')?.remove(); $('#va-audio', box)?.closest('.field')?.remove();
    }
    const per = (id, k, parse) => { const el = $('#' + id, box); if (!el || el.disabled) return; el.oninput = el.onchange = () => { const v = el.value.trim(); a[k + '_' + M] = v === '' ? undefined : parse ? parse(v) : v; if (a[k + '_' + M] === undefined || Number.isNaN(a[k + '_' + M])) delete a[k + '_' + M]; upd(); }; };
    per('va-steps', 'steps', v => Math.max(1, Math.min(40, parseInt(v))));
    per('va-sampler', 'sampler'); per('va-scheduler', 'scheduler');
    per('va-shift', 'shift', parseFloat); per('va-cfg', 'cfg', parseFloat); per('va-split', 'split', v => parseInt(v)); per('va-ashift', 'ashift', parseFloat);
    per('va-fps', 'fps', v => parseInt(v));
    $('#va-audio', box) && ($('#va-audio', box).onchange = e => { if (e.target.checked) delete a['audio_' + M]; else a['audio_' + M] = false; upd(); });
    $$('#va-ix [data-x]', box).forEach(b => b.onclick = () => { a.interp_x = +b.dataset.x; a.interp = a.interp_x > 1; $$('#va-ix button', box).forEach(x => x.classList.toggle('on', x === b)); $('#va-iby', box).hidden = !a.interp; upd(); });
    $('#va-iby', box).onchange = e => { a.interp_by = e.target.value; upd(); };
    $$('#va-count [data-n]', box).forEach(b => b.onclick = () => { st.count = +b.dataset.n; $$('#va-count button', box).forEach(x => x.classList.toggle('on', x === b)); save(); });
    // 只列这个模型能用的 LoRA（Wan 的不给 H3，反过来也一样）；已经选了但不对的去掉
    const LK = 'loras_' + LM, kind = f => (VIDST?.lora_kind || {})[f]; let files = (VIDST?.loras || []).filter(f => vidLoraOk(f, LM));
    if ((a[LK] || []).some(L => !vidLoraOk(L.name, LM))) { a[LK] = a[LK].filter(L => vidLoraOk(L.name, LM)); save(); }
    const lmeta = f => (VIDST?.lora_meta || {})[f] || null;
    const addWord = w => { const ta = $('#vd-prompt'); if (!ta) return; if (ta.value.toLowerCase().includes(w.toLowerCase())) return toast('提示词中已包含该词'); ta.value = (ta.value.trim() ? ta.value.trim().replace(/[，,]?$/, ', ') : '') + w; ta.dispatchEvent(new Event('input')); toast('已加入提示词：' + w); };
    const paintL = () => {  // LoRA 列表：文件、强度、（Wan）作用于高噪 / 低噪 / 两者
      const ls = a[LK] || [], el = $('#va-loras', box); if (!el) return;
      el.innerHTML = (files.length ? '' : `<div class="tiny vd-lora-e">ComfyUI\\models\\loras 中尚无适用于 MiniMax H3 的 LoRA</div>`)
        + ls.map((L, i) => `<div class="row vd-lora" data-i="${i}"><select class="select" data-k="name">${files.map(f => `<option value="${esc(f)}"${f === L.name ? ' selected' : ''}>${esc(loraOpt(f, lmeta(f)))}${kind(f) === '?' ? '（无法识别所属模型）' : ''}</option>`).join('')}</select>
          <input class="input" data-k="w" type="number" step="0.05" min="-2" max="3" value="${L.w ?? 1}" title="强度">
          <button type="button" class="pl-ib" data-rm title="移除" aria-label="移除">${ICON.x}</button></div>
          <div class="tiny vd-lora-f">文件：${esc(L.name)}</div>
          ${(lmeta(L.name)?.words || []).length ? `<div class="vd-lw"><span class="tiny">触发词</span>${lmeta(L.name).words.slice(0, 8).map(w => `<button type="button" class="chip" data-w="${esc(w)}" title="点击加入提示词">${esc(w)}</button>`).join('')}</div>` : ''}`).join('')
        + `<div class="row" style="gap:8px">${files.length && ls.length < 4 ? `<button type="button" class="btn small ghost" id="va-lora-add">＋ 添加 LoRA</button>` : ''}<button type="button" class="btn small ghost" id="va-cv" title="在应用内搜索、预览、一键下载 Civitai 上的 LoRA">在 Civitai 查找 LoRA</button><button type="button" class="btn small ghost" id="va-mine" title="本机已有的 LoRA：模型名、示例、说明和模型页">我的下载</button></div>`;
      $$('[data-w]', el).forEach(b => b.onclick = () => addWord(b.dataset.w));
      const cvDone = async () => { const r = await api('/api/video/status').catch(() => null); if (r) { VIDST = r; files = (r.loras || []).filter(f => vidLoraOk(f, LM)); } if (el.isConnected) paintL(); };
      $('#va-cv', el).onclick = () => civitaiOpen('h3', cvDone);
      $('#va-mine', el).onclick = () => civitaiOpen('h3', cvDone, 'mine');
      const guess = () => 'both';
      // 添加 LoRA（2026-11-11 用户）：打开“我的下载”（封面、翻译、详情），点“使用”加上；以前是先随便加一个、再在下拉框里改
      const fitF = f => files.includes(f) ? f : files.find(x => loraStem(x) === loraStem(f)) || '';
      $('#va-lora-add', el) && ($('#va-lora-add', el).onclick = () => civitaiOpen('h3', cvDone, 'mine', { used: new Set(ls.map(L => loraStem(L.name))), pick: async f0 => {
        let f = fitF(f0); if (!f) { await cvDone(); f = fitF(f0); }
        if (!f) return toast('这个 LoRA 不适用于当前的视频模型', true);
        if ((a[LK] || []).some(L => L.name === f)) return toast('已经添加过了');
        a[LK] = [...(a[LK] || []), { name: f, w: lmeta(f)?.weight || 1, on: guess(f) }]; upd(); paintL(); vfxAsk(f); toast('已添加：' + loraOpt(f, lmeta(f))); } }));
      $$('.vd-lora', el).forEach(r => {
        const L = ls[+r.dataset.i];
        $('[data-k=name]', r).onchange = e => { L.name = e.target.value; if (lmeta(L.name)?.weight) L.w = lmeta(L.name).weight; upd(); paintL(); vfxAsk(L.name); };
        $('[data-k=w]', r).onchange = e => { L.w = Math.max(-2, Math.min(3, +e.target.value || 0)); e.target.value = L.w; upd(); };
        $('[data-rm]', r).onclick = () => { ls.splice(+r.dataset.i, 1); a[LK] = ls; upd(); paintL(); };
      });
    };
    // 生成视频里加了特效编辑 LoRA（以前“自由修改”用的 Alissonerdx VFX Edit）：问要不要用它推荐的写法（触发词 vfx_edit: + 引导视频）
    const vfxAsk = async f => {
      if (E || M !== 'h3' || !/vfx[_ -]?edit/i.test(f || '') || /^\s*vfx_edit:/i.test($('#vd-prompt')?.value || '')) return;
      const ok = await confirmBox('是否使用该 LoRA 推荐的写法？', '这是特效编辑 LoRA（VFX Edit）：用一句话修改一段视频。作者的写法是在提示词开头加触发词 vfx_edit:，再写明如何修改（英文更稳定），并写明需要保留的内容（姿势、手、背景）；放入参考图时用 <Subject 1> 指代图中的内容，并写上 shown in <Picture 1>。要修改的视频请放入“更多素材 → 引导视频”（从第 0 帧起逐帧跟随）。选择“使用”后，提示词将改为此写法，当前内容附加在其后。', '使用', false);
      if (!ok) return;
      const t = $('#vd-prompt'), cur = t.value.trim();
      t.value = 'vfx_edit: ' + (cur || '‹怎么改，例如 Add falling snow, keep the person, pose and camera unchanged›') + (VID_X.refs.length && !/<picture 1>/i.test(cur) ? ', using <Subject 1> shown in <Picture 1>' : '');
      t.dispatchEvent(new Event('input', { bubbles: true }));
      if (!VID_X.guide) toast('请在“更多素材”中放入要修改的视频（引导视频）');
    };
    paintL();
    $('.va-tplb > .ig-sec', box)?.remove();
    $('#va-target', box) && ($('#va-target', box).oninput = e => { ve.target = e.target.value.slice(0, 200); upd(); paintTr(); });
    $('#va-up', box).onchange = e => { a.upscale = e.target.checked; upd(); };
    const bindFast = () => $('#va-fast', box) && ($('#va-fast', box).onchange = e => { a.fast = e.target.checked; upd(); }); bindFast();
    $('#va-seed', box).oninput = e => { const v = e.target.value.trim(); st.seed = v === '' ? -1 : Math.max(0, parseInt(v) || 0); upd(); };
    $('#va-dice', box).onclick = () => { st.seed = -1; $('#va-seed', box).value = ''; upd(); };
    requestAnimationFrame(paintAdvN);  // 打开时标出改过的项
    $('#va-reset', box).onclick = () => { vidState().adv = {}; vidState().seed = -1; vidState().engine = 'auto'; Object.assign(veState(), { base: 'lite' }); upd(); box.close(); toast('已恢复默认设置'); };
  };
  paintAdvN();
  // ---- 改视频：换人 / 改衣 / 自由修改（原视频 + 人物图 / 衣服图 / 参考图；H3 的参考模式，底模可选，见 videoedit.py）
  const ve = veState(), SRC_L0 = $('#vd-src-l').innerHTML;
  const VEP = {
    head: '（可选，建议英文）这张脸的样子，例如：Female, oval face, long black hair',
    headFs: '无需填写（换脸 LoRA 只用触发词）',
    vg: '新衣服，例如：白色缎面露肩连衣裙（放了衣服图可不填）',
    outfit: '新衣服，例如：红色吊带长裙（放了衣服图可不填）',
    outfitOwnA: '（可选）衣服的样子，写上背面更准确',
    refSwap: '（可选）人物图中此人的样子，例如：黑色长直发、白衬衫',
    refOutfit: '新衣服，例如：红色吊带长裙（放了衣服图可不填）',
    refOutfitOwn: '（可选）衣服的样子，写上背面更准确',
    v11: '（可选）补充人物的样子；程序会看人物图自动写',
    motion: '（可选）补充人物的样子；程序会看人物图自动写人物和场景',
    raw: '未用模板：原样发送，请写完整（空框按 Tab 填入原模板）' };
  const VE_HINT = {
    head: '只换头：身体、衣服、动作、镜头、背景均沿用原视频，头部（脸、发型）换成头像中的人。头像请使用清晰的正脸；作者指出困难角度、遮挡、运动模糊、远景小脸容易走样，建议先用几秒的单个镜头测试。',
    swap: '将视频中的人换为人物图中的人：动作、表情、镜头、背景沿用原视频，长相、发型、衣服按人物图。每次替换一人。<b>新版</b>（默认，作者 v1.1 配方）人物图先自动去背景，半身、坐姿的图也行；<b>审美优先</b>（参考生成）画面更美观，动作不一定逐帧一致，最长 15 秒。',
    motion: '让人物图里的人做出原视频里的动作：人物、衣服按人物图；人物图里有真实场景（房间、街道……）时成品用这个场景，纯色背景时沿用原视频的场景。动作、节奏、镜头、取景都跟原视频。<br>和换人的区别：换人保留原视频的背景，人物图要去背景；动作迁移连背景一起用人物图的，不去背景。',
    outfit: '更换衣服，人物、脸、动作、背景均沿用原视频。默认“参考生成”：先为人物换好衣服，再按原视频整段重新生成，画面清晰、衣服最接近（秋叶 A/B 中效果最好的 A4 做法）；“保真替换”只重绘身体，脸、头发和背景直接沿用原视频，镜头切换、多人、背影也能稳定跟随；“参考编辑”款式可与原视频差异较大（最长约 5 秒）。可以写明要换成的衣服，也可以放入一张衣服图（或两者都提供）。' };
  const VE_SRC_HINT = '要修改的视频（MP4 / MOV / WebM，最多约 70MB），也可从视频库中选择以前生成的视频。从“从第几秒开始”处起，截取上方所选的时长，按 24 fps 和所选分辨率处理（比例与原视频一致）。';
  const vePh = () => !veTpl() ? VEP.raw : ve.task === 'motion' ? VEP.motion : ve.task === 'swap' && ve.swap_by === 'ref' ? VEP.refSwap  // 提示词框里的提示：跟着做法和模板开关变
    : ve.task === 'outfit' && veVg() ? VEP.vg : ve.task === 'outfit' && veMethod() === 'ref' ? (veOwn() ? VEP.refOutfitOwn : VEP.refOutfit) : ve.task === 'swap' ? VEP[ve.swap_by] || '' : ve.task === 'head' ? VEP.headFs
    : veOwn() ? VEP.outfitOwnA : VEP.outfit;
  // 关了模板、提示词框是空的：Tab / 回车填入这种做法原本的模板（和开着模板时发给模型的一样），选中第一个 ‹…› 直接打字替换
  // 用后台给的模板（VS.templates）
  const veTplText = () => {
    const T = VIDST?.edit?.templates || {}, tg = (ve.target || '').trim();
    if (ve.task === 'motion') return T.motion || '';
    if (ve.task === 'swap' && ve.swap_by === 'v11') return T.v11 || '';
    if (ve.task === 'swap' && ve.swap_by === 'ref') return (T.ref_swap || '').replace('：‹提示词框里写的（可选）›', '').replace(/‹要换掉的人›/g, tg || '主要人物');
    if (ve.task === 'outfit' && veVg()) return (T.vg || '').replace(/‹要改衣的人›/g, tg || 'the main person');
    if (ve.task === 'outfit' && veMethod() === 'ref') return (T.ref_outfit || '').replace(/‹要改衣的人›/g, tg || '人物').replace('‹提示词框里写的（可选）›', '‹新衣服的样子›');
    if (ve.task === 'head') return T.faceswap || '';
    return (T[VE_REF ? 'outfit_edit_img' : 'outfit_edit'] || '').replace('‹要改衣的人›', tg || '画面里的人');
  };
  const veTplFill = () => {
    if (st.mode !== 'edit' || veTpl() || ta.value.trim()) return false;
    const t = veTplText(); if (!t) return false;
    ta.value = t;
    const m = /‹[^›]*›/.exec(t); if (m) ta.setSelectionRange(m.index, m.index + m[0].length);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  const veSeg = (id, list, cur, ic) => `<div class="seg full${ic ? ' ve-ic' : ''}" id="${id}">${list.map(([k, n]) => `<button type="button" data-k="${k}" class="${cur === k ? 'on' : ''}"${ic ? ` aria-label="${n}" data-tip="${n}"` : ''}>${ic && ic[k] ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ic[k]}</svg><span class="vt">${n}</span>` : n}</button>`).join('')}</div>`;
  const veLoadVid = file => {
    if (!file.type.startsWith('video/') && !/\.(mp4|mov|m4v|webm|avi)$/i.test(file.name || '')) return toast('仅支持视频文件（MP4 / MOV / WebM / AVI）', true);
    if (file.size > VE_MAX_MB * 1048576) return toast(`视频过大（最多约 ${VE_MAX_MB}MB），请先剪短`, true);
    if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url);
    const v = VE_VID = { kind: 'upload', file, url: URL.createObjectURL(file), dur: 0, w: 0, h: 0 }; ve.start = 0;
    vtFileFps(file).then(f => { if (f && VE_VID === v) v.fps = f; });  // 帧率从文件头读（剪辑的 ±1 帧、修剪都按它）
    const pr = document.createElement('video'); pr.preload = 'metadata'; pr.muted = true;
    pr.onloadedmetadata = () => { if (VE_VID !== v) return; v.dur = pr.duration || 0; v.w = pr.videoWidth; v.h = pr.videoHeight; paintVeSrc(); paintSec(); pr.currentTime = Math.min(.1, v.dur / 2 || 0); };
    pr.onseeked = () => {  // 取一帧当缩略图（窄窗口输入框左边的方块）
      if (VE_VID !== v || v.poster || !pr.videoWidth) return;
      try { const k = 160 / Math.max(pr.videoWidth, pr.videoHeight), c = document.createElement('canvas'); c.width = Math.round(pr.videoWidth * k); c.height = Math.round(pr.videoHeight * k);
        c.getContext('2d').drawImage(pr, 0, 0, c.width, c.height); v.poster = c.toDataURL('image/jpeg', .8); vdRefresh(); } catch { }
    };
    pr.onerror = () => { if (VE_VID === v) toast('该视频无法在此预览，但仍可正常生成（后台会转码）'); };
    pr.src = v.url; save(); paintVeSrc(); paintSec(); vdRefresh();
  };
  window.veLoadVidX = veLoadVid;  // 重新生成 → 放回剪辑：原视频不在视频库里时，按上传的文件载入
  const veLoadImg = file => {  // 人物图 / 衣服图：和首帧一样，太大时缩到 2048 以内
    const fr = new FileReader(), gen = VGEN;
    fr.onload = () => {
      if (gen !== VGEN || !$('#ve-src')) return;
      const im = new Image();
      im.onload = () => {
        let [w, h] = [im.naturalWidth, im.naturalHeight], data = fr.result;
        if (Math.max(w, h) > 2048 || !/^image\/(png|jpeg|webp)$/.test(file.type)) {
          const k = Math.min(1, 2048 / Math.max(w, h)), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k);
          c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height;
        }
        VE_REF = { kind: 'upload', data, url: data, w, h }; paintVeSrc(); vdRefresh(); vidImgPrompt(file, VE_REF, vdGpSync);
      };
      im.onerror = () => toast('无法打开此图（仅支持 PNG / JPG / WebP）', true);
      im.src = fr.result;
    };
    fr.readAsDataURL(file);
  };
  const vePickVid = async () => {
    if (!vidGal.length) vidGal = await api('/api/video/gallery').catch(() => []);
    const list = vidGal.slice(0, 200); if (!list.length) return toast('视频库中尚无视频', true);
    modal(`<h3 class="card-title" style="margin:0 0 10px">从视频库选择一段</h3><div class="ig-pick">${list.map((x, i) => `<button type="button" class="ig-pick-t ve-pick-t" data-i="${i}" title="${esc(x.prompt || '')}">${x.thumb ? `<img loading="lazy" src="${vidUrl(x.thumb)}" alt="">` : VID_IC.film}<span class="ve-pick-d">${Math.round(+x.duration || x.seconds || 0)} 秒</span></button>`).join('')}</div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>取消</button></div>`, box => {
      $$('.ve-pick-t', box).forEach(b => b.onclick = () => { box.close(); if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = veGalVid(list[+b.dataset.i]); ve.start = 0; save(); paintVeSrc(); paintSec(); vdRefresh(); });
    }, true);
  };
  const refMats = () => matsPick('image', async f => { try { veLoadImg(await matsFile(f)); } catch (e) { toast(e.message, true); } });
  // refMenu(anchor, direct)：direct = 点空格（电脑上直接开素材库，2026-11-10）
  const refMenu = (anchor, direct) => (direct ? slotPick : (a, it) => ctxMenu({ anchor: a }, it))(anchor, [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: refMats },
    { label: VE_REF ? '从电脑选择（更换）' : '从电脑选择', icon: ICON.up, on: () => $('#ve-rfile')?.click() },
    { label: '粘贴', icon: CTX_IC.open, on: async () => { const f = await clipImage(); if (f) veLoadImg(f); } },
    { label: '从生图图库选择', icon: CTX_IC.open, on: () => pickGal(x => { VE_REF = vidImg(x); paintVeSrc(); vdRefresh(); }) },
    ...(VE_REF ? [{ label: '移除', icon: CTX_IC.del, danger: true, on: () => { VE_REF = null; paintVeSrc(); vdRefresh(); } }] : [])]);
  const paintVeSrc = renderVideo.paintVeSrc = () => {
    const box = $('#ve-src'); if (!box) return;
    const v = VE_VID, r = VE_REF, T = ve.task, own = veOwn(), refN = T === 'remove' ? '' : T === 'swap' || T === 'motion' ? '人物图' : T === 'head' ? '头像' : T === 'outfit' ? (own ? '参考图' : '衣服图') : '参考图';
    // 原视频：不自动播放；点画面播放 / 暂停，右下角放大看（竖屏的在这里小）；竖屏的框高一些
    box.innerHTML = (v ? `<div class="ve-src-c">${VID_IC.film}<b>原视频</b><span class="tiny ve-seg-txt"></span><span class="spacer"></span><button type="button" class="btn small ghost" id="ve-trim" title="去掉原视频里不要的帧或片段（存成一段新视频后再用作原视频）">修剪</button><button type="button" class="btn small ghost" id="ve-chg" title="更换原视频">更换</button><button type="button" class="pl-ib" id="ve-vid-x2" title="移除此视频" aria-label="移除此视频">${ICON.x}</button></div>` : '')
      + `<div class="vd-frames">` + (v ? `<div class="ig-src ve-vid${v.h > v.w ? ' tall' : ''}"><video src="${esc(v.url)}" playsinline preload="metadata"></video>`
        + `<button type="button" class="ve-play" id="ve-play" title="播放" aria-label="播放">${VID_IC.play}</button>`
        + `<button type="button" class="ve-bigb" id="ve-big" title="放大播放" aria-label="放大播放"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg></button>`
        + `<button type="button" class="ig-src-x" id="ve-vid-x" title="移除此视频" aria-label="移除此视频">${ICON.x}</button></div>`
        : `<div class="ig-src empty b5-up" id="ve-pick-area" role="button" tabindex="0" aria-label="添加原视频">${VID_IC.film}<div>原视频</div><span class="tiny">必填</span><button type="button" class="btn small ve-pick-in" id="ve-pick" hidden>从电脑 / 视频库选</button></div>`)
      + (refN ? `<div class="vd-f2${r ? '' : ' empty'}" id="ve-ref" role="button" tabindex="0" title="${T === 'swap' ? '人物图（必填）：换成此人' : T === 'head' ? '头像（必填）：换成这张脸（最好是清晰的正脸）' : T === 'outfit' ? (own ? (veMethod() === 'ref' ? '参考图（可选）：此人换好衣服后的图，直接使用；不放入时跳过 Qwen 改图，仅按提示词修改' : '参考图（必填）：此人换好衣服后的图，直接使用') : '衣服图（可选）：换成这身衣服') : '参考图（可选）：将图中的内容放入视频'}">${r ? `<img src="${esc(r.url)}" alt="" draggable="false"><button type="button" class="ig-src-x" id="ve-ref-x" title="移除" aria-label="移除">${ICON.x}</button>`
        : `${ICON.up}<span>${refN}</span><span class="tiny">${T === 'swap' || T === 'head' || T === 'motion' || own && veMethod() !== 'ref' ? '必填' : '可选'}</span>`}</div>` : '') + `</div>`
      + (v ? `<div class="tiny vd-src-i ve-src-i"><span class="ve-src-m">${[v.w && v.h ? `${v.w} × ${v.h}` : '', v.dur ? `${(+v.dur).toFixed(1)} 秒` : '', v.kind === 'gallery' ? '视频库' : v.kind === 'mats' ? '素材库' : ''].filter(Boolean).join(' · ')}</span><span class="ve-seg-txt"></span><button type="button" class="btn small ghost ve-segb" id="ve-seg" title="在大画面中逐帧选择开始和结束的位置，也可以直接填秒数">${VSEG_IC.cut}选段</button></div>`
        + `<div class="ve-mini"><div class="vseg-track vtrim ve-trk" tabindex="0" role="slider" aria-label="原视频播放位置"><div class="vtrim-film"></div><div class="vseg-rng" data-live><span class="vtrim-h a" aria-hidden="true"></span><span class="vtrim-h b" aria-hidden="true"></span></div><div class="vseg-head"></div></div>`
        + `<button type="button" class="btn small ghost" data-ms="a" title="把当前播放位置设为开始">设为开始</button><button type="button" class="btn small ghost" data-ms="b" title="把当前播放位置设为结束">设为结束</button>`
        + `<button type="button" class="btn small ghost ve-ff" data-tip="复制这一段开头那一帧（原视频的清晰度）：到生图页粘贴为原图，用 Qwen 2.1 改好（比如把外套敞开）后，放回参考图格，关掉“Qwen 生成”，几段都用这一张">复制首帧</button><button type="button" class="btn small ghost ve-ffs" data-tip="把这一段开头那一帧（原画质）存进素材库">存进素材库</button>`
        + `<button type="button" class="btn small ghost ve-add" data-tip="再选一段：从白色标（当前画面）开始；白色标在某一段中间时从那里切成两段">＋ 添加一段</button>` + `<button type="button" class="btn small ghost vsg-find" title="分析音乐的节拍和人物的动作，在选段条上标出适合换装 / 拼接的时间点（只用 CPU，不占显卡）">找换装点</button>`
        + `<button type="button" class="chip ve-spl" hidden aria-pressed="false" data-tip="${esc(VSEG_SPL_TIP)}">${VSEG_IC.join}拼接</button><div class="vseg-cp" hidden></div></div>`
        : '')  // “从视频库选”放在上面空框的右下角：少占一行，整栏一屏放得下
      + `<input type="file" id="ve-file" accept="video/*,.mov,.m4v" hidden><input type="file" id="ve-rfile" accept="image/*" hidden>`;
    const area = $('#ve-pick-area');
    const vidMats = () => matsPick('video', f => { let first = true; matsVid(f, v => { if (first) { first = false; if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = v; ve.start = 0; save(); } if (VE_VID === v) { paintVeSrc(); paintSec(); vdRefresh(); } }); });
    const vidItems = () => [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: vidMats }, { label: '从电脑选择', icon: ICON.up, on: () => $('#ve-file').click() }, { label: '从视频库选择', icon: CTX_IC.open, on: () => vePickVid() }];
    if (area) { area.onclick = ev => { if (ev.target.closest('button')) return;
        slotPick(area, vidItems()); };  // 2026-11-10：点一下直接打开素材库（右键：其他来源）
      area.oncontextmenu = ev => { ev.preventDefault(); ctxMenu({ anchor: area }, vidItems()); };
      area.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); area.click(); } };
      area.ondragover = ev => { ev.preventDefault(); area.classList.add('over'); }; area.ondragleave = () => area.classList.remove('over');
      area.ondrop = ev => { ev.preventDefault(); area.classList.remove('over'); const f = [...(ev.dataTransfer.files || [])][0]; if (f) veLoadVid(f); }; }
    $('#ve-file').onchange = ev => { const f = ev.target.files[0]; if (f) veLoadVid(f); ev.target.value = ''; };
    $('#ve-rfile').onchange = ev => { const f = ev.target.files[0]; if (f) veLoadImg(f); ev.target.value = ''; };
    $$('#ve-vid-x, #ve-vid-x2').forEach(b => b.onclick = () => { if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = null; ve.start = 0; save(); paintVeSrc(); paintSec(); vdRefresh(); });
    const vv = $('#ve-src video');
    if (vv) {
      vidVolSync(vv); const vb = vv.parentNode, pb = $('#ve-play');
      const sync = () => { vb.classList.toggle('playing', !vv.paused); pb.title = vv.paused ? '播放' : '暂停'; pb.setAttribute('aria-label', pb.title); };
      const tog = () => { vv.paused ? vv.play().catch(() => { }) : vv.pause(); };
      vv.onplay = vv.onpause = vv.onended = sync; vv.onclick = tog; pb.onclick = tog;
      $('#ve-big').onclick = () => { vv.pause(); vePlayBig(VE_VID); };
    }
    $('#ve-chg') && ($('#ve-chg').onclick = e => ctxMenu({ anchor: e.currentTarget }, [{ label: '从素材库选择', icon: window.MATS_IC || CTX_IC.open, on: vidMats },
      { label: '从电脑选择', icon: ICON.up, on: () => $('#ve-file').click() }, { label: '从视频库选择', icon: CTX_IC.open, on: () => vePickVid() }, { label: '修剪原视频', icon: VSEG_IC.cut, on: () => vtrimOpen(vtFromSrc()) }]));
    $('#ve-trim') && ($('#ve-trim').onclick = () => vtrimOpen(vtFromSrc()));
    $('#ve-pick') && ($('#ve-pick').onclick = e => { e.stopPropagation(); ctxMenu({ anchor: e.currentTarget }, [{ label: '从电脑选择', icon: ICON.up, on: () => $('#ve-file').click() }, { label: '从视频库选择', icon: CTX_IC.open, on: () => vePickVid() }]); });  // 在上传框里面：点框本身是从素材库选
    $('#ve-seg') && ($('#ve-seg').onclick = () => { $('#ve-src video')?.pause(); veSegOpen(() => { paintSec(); vdRefresh(); }); });
    { const mv = $('#ve-src video'), trk = $('#ve-src .ve-trk');
      if (mv && trk) {
        veTrack(trk, mv, () => mv.duration || VE_VID?.dur || 0, { onRange: (a, b) => veSegSet(a, b > (mv.duration || VE_VID?.dur || 0) - 0.05 ? null : b), getAB: veSegAB, film: VE_VID.url });
        $$('#ve-src [data-ms]').forEach(x => x.onclick = () => { const t = veSegR2(mv.currentTime), [a, b] = veSegAB();
          if (x.dataset.ms === 'a') veSegSet(t, b < t + 1 ? null : b); else { if (t < a + 1) return toast('结束需比开始晚至少 1 秒', true); veSegSet(a, t); } });
        const ad = $('#ve-src .ve-add'); if (ad) ad.onclick = () => { mv.pause(); veSegAdd(mv.currentTime); };
        const fd = $('#ve-src .vsg-find'); if (fd) fd.onclick = () => { mv.pause(); veCpFind(); };
        const sp = $('#ve-src .ve-spl'); if (sp) sp.onclick = () => { ve.splice = ve.splice === false; ve.segUrl = VE_VID.url; persist(); veSegSync(); };
        trk.onkeydown = e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); mv.pause(); mv.currentTime = Math.max(0, mv.currentTime + (e.key === 'ArrowLeft' ? -1 : 1) / (VE_VID.fps || 30) * (e.shiftKey ? 30 : 1)); } };
        mv.addEventListener('loadedmetadata', () => veSegSync());
        veSegSync();
      } }
    if (veSrcStageOk()) { if (VE_VID.url !== vidStage.srcUrl) { vidStage.srcUrl = VE_VID.url; vidStage.src = true; if (vidStage.grid) { vidStage.grid = false; vidGallery(); } }  // 换了原视频：右边先显示它（剪辑）
      if (vidStage.grid) vdDualBind(); else if (vidStage.src) vidSrcStage(); else vidStage(vidGal.find(g => g.id === vidStage.cur) || null); }
    else if ($('#vd-stage')?.dataset.id?.startsWith('src:')) { vidStage.src = false; $('#vd-stage').querySelector('.vseg-host')?._seg?.stop(); delete $('#vd-stage').dataset.id; vidGallery(); }  // 移除了原视频 / 换到生成视频
    const rt = $('#ve-ref');
    box.style.setProperty('--refw', rt ? (rt.offsetWidth + 10) + 'px' : '0px');  // 宽窗口：拖动条只盖在原视频那一格上（不盖右边的参考图）
    box.dataset.port = v && v.h > v.w * 1.15 ? '1' : '';  // 竖屏原视频：宽窗口里那一格变高，其余放右边一列（放不下时 vePortFit 不用这种排法）
    if (v?.w && v?.h) box.style.setProperty('--var', `${v.w} / ${v.h}`);
    veLeftSync(); requestAnimationFrame(vePortFit);
    if (rt) {
      rt.onclick = ev => { if (ev.target.closest('#ve-ref-x')) { ev.stopPropagation(); VE_REF = null; paintVeSrc(); vdRefresh(); return; } r ? zoomImgs([r.url], 0) : refMenu(rt, true); };  // 空的：电脑上直接从素材库选（右键：其他方式）  // 空的：上传 / 粘贴 / 从图库选；放了图：看大图（右键换图）
      rt.oncontextmenu = ev => { ev.preventDefault(); refMenu(rt); };
      rt.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); refMenu(rt); } };
      rt.ondragover = ev => { ev.preventDefault(); rt.classList.add('over'); }; rt.ondragleave = () => rt.classList.remove('over');
      rt.ondrop = ev => { ev.preventDefault(); rt.classList.remove('over'); const f = [...(ev.dataTransfer.files || [])].find(x => x.type.startsWith('image/')); if (f) veLoadImg(f); };
    }
    paintVeTile();
  };
  // 窄窗口：输入框左边的方块改视频时是“原视频”，旁边的小方块是人物图 / 衣服图 / 参考图（像生成视频时的尾帧）
  const paintVeTile = () => {
    const row = $('.ig-crow'); if (!row) return;
    let t = $('#ve-reft');
    if (!t) { t = document.createElement('button'); t.type = 'button'; t.id = 've-reft'; t.className = 'ig-srct vd-endt';
      (row.querySelector('#vd-endt') || row.querySelector('.ig-srct'))?.after(t);
      t.onclick = ev => { ev.stopPropagation(); if (ev.target.closest('.ig-srct-x')) { VE_REF = null; paintVeSrc(); vdRefresh(); return; } VE_REF ? zoomImgs([VE_REF.url], 0) : refMenu(t, true); };
      t.oncontextmenu = ev => { ev.preventDefault(); ev.stopPropagation(); refMenu(t); }; }
    const T = ve.task, n = T === 'swap' || T === 'motion' ? '人物图（必填）' : T === 'head' ? '头像（必填）' : T === 'outfit' ? (veOwn() ? '参考图（可选）' : '衣服图（可选）') : '参考图（可选）';
    t.hidden = st.mode !== 'edit' || T === 'remove'; t.title = n + (VE_REF ? '：点击查看大图，右键更换' : ''); t.setAttribute('aria-label', n);
    t.innerHTML = VE_REF ? `<img src="${esc(VE_REF.url)}" alt=""><span class="ig-srct-x" role="button" title="移除" aria-label="移除">${ICON.x}</span>`
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="13" height="13" rx="3"/><path d="M3.5 14l3.5-3.5 4 4"/><path d="M19.5 14.5v6M16.5 17.5h6"/></svg>';
  };
  const paintVeOpts = () => {
    const box = $('#ve-opts'); if (!box) return;
    window.vePaintOpts = paintVeOpts; vePaintOpts.multi = veXs().length > 0;  // 选段多了 / 少了时 veSegSync 叫它重画（“共用衣服图”只在多段时出现）
    const VS = VIDST?.edit || {}, by = VS.swap_by || ['v11', 'ref'];
    // 状态还没取到时不纠正
    if (VS.swap_by && ve.task === 'swap' && !by.includes(ve.swap_by) && by.length) ve.swap_by = by[0];
    // 宽窗口两列排（.ve-wide 占一整行）：换人 = 换人方式 | 声音、要换掉的人；改衣 = 换哪部分（整行）、要改衣的人 | 声音
    if (ve.task === 'swap' && !['v11', 'ref'].includes(ve.swap_by)) ve.swap_by = by[0] || 'v11';  // 以前存的 bfs（Alissonerdx 旧版）等
    const hbs = VS.head_by || ['fs'];
    if (VS.head_by && ve.task === 'head' && !hbs.includes(ve.head_by || 'fs') && hbs.length) ve.head_by = hbs[0];
    const fHb = `<div class="field"><span class="label">做法</span><div class="seg full" id="ve-hb">${VE_HEADS.filter(([k]) => hbs.includes(k)).map(([k, n, tip]) => `<button type="button" data-k="${k}" class="${(ve.head_by || 'fs') === k ? 'on' : ''}" data-tip="${esc(tipNote(tip, VE_NOTE[k]))}">${n}${k === 'fs' ? REC : ''}</button>`).join('')}</div></div>`;
    const fBy = `<div class="field"><span class="label">做法</span>`
      + `<div class="seg full" id="ve-by">${VE_SWAPS.filter(([k]) => by.includes(k)).map(([k, n, tip]) => `<button type="button" data-k="${k}" class="${ve.swap_by === k ? 'on' : ''}" data-tip="${esc(tipNote(tip, VE_NOTE[k === 'ref' ? 'ref_swap' : k]))}">${n}${k === 'v11' ? REC : ''}</button>`).join('')}</div></div>`;
    const VSm = VIDST?.edit || {}, tplOn = veTpl();
    const sw2 = (id, on, txt) => `<label class="vd-sw ve-sw"><span>${txt}</span><span class="switch"><input type="checkbox" id="${id}"${on ? ' checked' : ''}><span></span></span></label>`;
    const tog = (id, on, txt, tip, disabled = false) => `<button type="button" class="vd-follow ve-tog${on && !disabled ? ' on' : ''}" id="${id}" aria-pressed="${on && !disabled}"${disabled ? ' disabled' : ''} data-tip="${esc(tip)}">${txt}</button>`;
    // 2026-11-06 用户：这几个开关原来挤在时长下面、没有名字，看着突兀。参考图：Qwen 生成（开 = 用 Qwen 改图）+ 锁定首帧 + 共用衣服图（这两个只在用 Qwen 时有）
    const qOn = !veOwn(), qTip = '<b>Qwen 生成</b>：先从原视频取一帧，用 Qwen 改图为此人换上要的衣服（放入衣服图时照衣服图换），这张图再作为参考图。多一步，约慢 1 分钟，Qwen 偶尔会改动脸。<br>关闭时不经过 Qwen：上传的图直接作为参考图（应为换好衣服的人物，最好全身正面）；也可以不上传，只按提示词修改原视频。<br>默认开启';
    const fOwn = `<div class="field ve-wide"><span class="label" data-tip="${esc(qTip)}">参考图</span><div class="ve-togs">${tog('ve-qwen', qOn, 'Qwen 生成', qTip)}`
      + (veMethod() === 'ref' && qOn && !veVg() ? tog('ve-ffg', ve.ffguide === true, '锁定首帧', '开启后，Qwen 换好衣服的那一帧会固定在成品的第一帧上，开头姿势和原视频对上，中间更不容易跑偏。<br>代价：只能用引擎 ①，约慢一倍。<br>适合动作多、容易跑偏的段落，或上次中间跑偏了想重做时；动作平稳的段落开不开差别不大。原视频开头几帧认不出人脸时用不上（完成时会提示）。') : '')
      + (veMethod() === 'ref' && qOn && veXs().length ? tog('ve-qsh', ve.qshare === true, '共用衣服图', '选了多段时：<br>开启：只为第一段用 Qwen 换一次衣服，后面几段都用这张图，各段衣服完全一样，拼起来接缝处不会换了衣服；也少跑几次 Qwen。<br>关闭（默认）：每段各取自己的一帧、各换一次，人物姿势、角度更贴合各段，但各段衣服的细节可能略有不同。<br>开启时只有第一段能用“锁定首帧”。') : '') + `</div></div>`;
    const fAud = `<div class="field"><span class="label" data-tip="${esc('<b>原声</b>：使用原视频该片段的声音（原视频无声时即为无声）。<br><b>重新生成</b>：H3 按画面重新生成声音；换人时会参考原声的节奏。<br><b>无声</b>：只生成画面，速度稍快。')}">声音</span>${veSeg('ve-audio', VE_AUDIO, ve.audio, VE_AUDIO_IC)}</div>`;
    // 底模不再单独选（2026-11-04）：跟着做法走，“高级参数”里能改；标题栏那一处现在给生成视频的底模用
    // 提示词那一行右边的“使用模板”开关：换人、换头、改衣（三种做法）都有，各记各的，默认开；关掉就不要“要换掉 / 改衣的人”这一栏，提示词原样发给模型
    const tw = $('#ve-tplw'), T = VS.templates || {};
    const tplHelp = '开启（默认）：将填写的内容放入此做法的模板，再发送给模型（模板位于“高级参数”最下方）。<br>关闭：提示词框中的内容将原样发送给模型' + (ve.task === 'outfit' ? '（改衣时发送给 Qwen 改图；后续步骤不变）' : '') + '，“要' + (ve.task === 'swap' ? '换掉' : '改衣') + '的人”一栏也不再使用。输入框为空时按 Tab 或回车，可填入原模板后再修改。';
    if (tw) { tw.hidden = st.mode !== 'edit';
      tw.innerHTML = (tplOn ? '' : `<span class="ve-tips">写法要点${hintHtml(veTips(), 'sm')}</span>`)
        + `<span data-tip="${esc(tplHelp)}">使用模板</span><label class="switch ve-tplsw" title="使用模板"><input type="checkbox" id="ve-tpl"${tplOn ? ' checked' : ''}><span></span></label>`; }
    const fTb = `<div class="field" id="ve-tb-f" hidden><span class="label" data-tip="${esc(VID_TB_TIP)}">加速</span><div class="seg full" id="ve-tb"></div></div>`;
    // 2026-11-10 色调：H3 的成品通常偏暗、肤色偏红，开了就在生成后自动调回原视频的样子（colorfix 照原视频，默认关）
    const cmTip = '<b>匹配原视频</b>：生成完自动把亮度和肤色调回原视频的样子（成品通常偏暗、皮肤偏红一点）。只改颜色，约几秒；调色前的那份另存在辅助文件里。<br>想要别的风格（冷白、照参考图），可以生成后在视频的“后期处理”里调。';
    // 2026-11-10 全面检查：“动作”“色调”两行各只有一个小按钮（小组件独占一行）——这两个都是开 / 关，改成整行的开关（和生视频那边一样）
    const swT = (id, on, txt, tip) => `<label class="vd-sw ve-sw"><span data-tip="${esc(tip)}">${txt}</span><span class="switch"><input type="checkbox" id="${id}"${on ? ' checked' : ''}><span></span></span></label>`;
    const fCol = ve.task === 'motion' ? '' : swT('ve-cm', ve.cmatch === true, '匹配原视频色调', cmTip);  // 动作迁移是人物图的场景：不能往原视频的颜色调
    // 2026-11-10 动作跟随：原视频的全身骨架逐帧约束生成（H3 Fun ControlNet），约慢一半；2026-11-12 起后台默认用 2.0 · 1.0（第一版 0.6 偶尔跑偏），版本和强度网页不传
    const poTip = '<b>动作跟随</b>：识别原视频每一帧的全身姿势（身体、手、脸），让成品逐帧照着做，快速手势也能对上。<br>生成约慢一半，适合动作多、上次跑偏的段落。<br>开启后这一单使用官方精简底模（动作跟随只支持精简版）。';
    const lOn = veLoc(), fPose = VS.pose && VS.lite && veBaseNow() === 'full' && !veRecipe() && !veFs() && !veVg() ? swT('ve-pose', ve.pose === true || lOn, '动作跟随', lOn ? '<b>动作跟随</b>：局部修改自带动作跟随，开着局部修改时不能关。' : poTip) : '';
    // 2026-11-12 夜测：局部修改 = SAM3 逐帧找出衣服，只重画那块，其余贴回原视频（脸 / 背景亮度差 -4 → -0.4，脸相似 0.6~0.8 → 0.95+，接缝看不出；docs/AB测试/ControlNet2_1112）
    const locTip = '<b>局部修改</b>：逐帧找出衣服，只重画衣服那一块，脸和背景保持原视频，脸和色调几乎不变。<br>适合衣服上的小改动：换图案、换颜色、只换里面那件（外套留着）。整件拿掉或衣服变小（外套整件拿掉、宽开衫换紧身）做不到，这类请关掉局部修改。<br>自带动作跟随。<br><b>衣服</b>：只重画衣服。<b>整个人</b>：脸以外都重画。';
    // 开着时“衣服 / 整个人”放在同一行（不多占一行，选项框不用滚动）；这一行不是 label，点选段不会顺带关掉开关
    const lq = ve.locq === 'person' ? 'person' : 'cloth';
    const vgTip = '<b>Viggle 重拍</b>：Qwen 改好那一帧后，用 Viggle 官方的 Remake 模型照着这一帧把整段重拍，镜头、动作、光照直接跟着原视频；夜测光照和脸最接近原视频（脸亮度差 0.7，参考生成约 5）。<br>不能和局部修改、动作跟随、加速一起用；分辨率固定 480 / 736，每段最长 14 秒（更长请分成几段）；第一次用要载入 21 GB 的模型。<br>默认关闭。';
    const fVg = ve.task === 'outfit' && VS.vg && veMethod() === 'ref' ? swT('ve-vg', veVg(), 'Viggle 重拍', vgTip) : '';
    const fLoc = !(ve.task === 'outfit' && veRef() && !veVg() && VS.loc && VS.lite && veBaseNow() === 'full') ? '' : !lOn ? swT('ve-loc', false, '局部修改', locTip)
      : `<div class="vd-sw ve-sw ve-locrow"><span data-tip="${esc(locTip)}">局部修改</span><div class="seg mini" id="ve-locq">${[['cloth', '衣服'], ['person', '整个人']].map(([k, n]) => `<button type="button" data-k="${k}" class="${lq === k ? 'on' : ''}">${n}</button>`).join('')}</div><label class="switch" title="局部修改"><input type="checkbox" id="ve-loc" checked><span></span></label></div>`;
    // 2026-11-11 夜测：同一件衣服上的小改动（外套敞开、换颜色）不开这个时会被原视频拉回原样；开了以后 720p + 动作跟随下两段、两个种子都改到位（docs/AB测试/夜间测试_1111）。默认关
    const fEmph = ve.task === 'outfit' && !veVg() ? swT('ve-emph', ve.emph === true, '改动写进每一段', '提示词框里写的改动（例如外套敞开、换颜色），除了开头，也写进提示词的每一段。<br>同一件衣服上的小改动，不开时容易被原视频拉回原样。<br>写的时候连衣服一起写，例如“白色亚麻外套敞开，露出里面的蓝色条纹衬衫……”。') : '';
    const tbOn = !veRecipe() && !veFs() && !veVg();  // 作者配方自带 DMD 8 步、换脸 LoRA 固定官方加速、Viggle 自己 6 步：不显示“加速”
    box.innerHTML = (ve.task === 'swap' ? fBy + (tbOn ? fTb : '') + fAud : ve.task === 'head' ? fHb + fAud + (tbOn && veBaseNow() === 'full' ? fTb : '') : ve.task === 'motion' ? fAud : (tbOn ? fTb : '') + fAud + fOwn) + (fVg + fLoc + fEmph + fPose + fCol ? `<div class="field ve-sws ve-wide">${fVg}${fLoc}${fEmph}${fPose}${fCol}</div>` : '');
    if ($('#ve-tb', box)) { $('#ve-tb', box).onclick = tbClick; paintTurbo(); }  // “要改衣 / 换掉的人”在高级参数里（多人时才用，2026-11-06）
    const segOn = (id, k, after) => $$(`#${id} [data-k]`, box).forEach(b => b.onclick = () => { ve[k] = b.dataset.k; $$(`#${id} button`, box).forEach(x => x.classList.toggle('on', x === b)); save(); after?.(); vdRefresh(); });
    segOn('ve-by', 'swap_by', () => { paintVeOpts(); ta.placeholder = vePh(); paintSec(); paintAdvN(); });
    segOn('ve-hb', 'head_by', () => { paintVeOpts(); ta.placeholder = vePh(); paintSec(); paintAdvN(); });
    $('#ve-vg', box) && ($('#ve-vg', box).onchange = e => { ve.vg = e.target.checked; save(); paintVeOpts(); ta.placeholder = vePh(); paintSec(); paintAdvN(); vdRefresh(); });
    segOn('ve-audio', 'audio');
    $('#ve-qwen', box) && ($('#ve-qwen', box).onclick = () => { const use = veOwn(); ve.own = !use; save(); paintVeOpts(); paintVeSrc(); paintVeTile(); ta.placeholder = vePh(); vdRefresh(); });  // use：点了以后要不要用 Qwen
    $('#ve-ffg', box) && ($('#ve-ffg', box).onclick = () => { ve.ffguide = ve.ffguide !== true; save(); paintVeOpts(); vdRefresh(); });
    $('#ve-cm', box) && ($('#ve-cm', box).onchange = e => { ve.cmatch = e.target.checked; save(); paintVeOpts(); vdRefresh(); });
    $('#ve-emph', box) && ($('#ve-emph', box).onchange = e => { ve.emph = e.target.checked; save(); paintVeOpts(); vdRefresh(); });
    $('#ve-pose', box) && ($('#ve-pose', box).onchange = e => { if (veLoc()) { e.target.checked = true; return; } ve.pose = e.target.checked; save(); paintVeOpts(); vdRefresh(); });
    $('#ve-loc', box) && ($('#ve-loc', box).onchange = e => { ve.locon = e.target.checked; save(); paintVeOpts(); vdRefresh(); });
    segOn('ve-locq', 'locq');
    $('#ve-qsh', box) && ($('#ve-qsh', box).onclick = () => { ve.qshare = ve.qshare !== true; save(); paintVeOpts(); vdRefresh(); });
    $('#ve-tpl') && ($('#ve-tpl').onchange = e => { veSetTpl(e.target.checked); save(); paintVeOpts(); ta.placeholder = vePh(); paintAdvN(); vdRefresh(); });
    $('#vd-ai').hidden = !((ve.task === 'head' && veTpl() && !veFs()) || veRef());  // 换头开着模板时：AI 优化写头像的脸部描述；参考生成：AI 按结构写整段
    paintStruct();
  };
  const paintMode = () => {
    if (!$('#ve-src')) return;
    const E = st.mode === 'edit', VS = VIDST?.edit;
    $$('#vd-mode-sw [data-v]').forEach(b => b.classList.toggle('on', b.dataset.v === (E ? 'edit' : 'gen')));
    { const c = $('#b5-ctx-l'); if (c) c.textContent = E ? '改视频' : '生成视频'; }
    paintModel();
    $('#vd-model').hidden = E; $('#ve-task').hidden = !E;
    tipLabel($('#vd-model-l'), E ? '模式' : '模型', E ? VE_HINT[ve.task] : '');
    // 改视频：“模式”标签和三个按钮同一行；宽窗口时这一行排在原视频上面（video.css 里按 .ve-on 调顺序）
    $('#vd-model').closest('.field').classList.toggle('ve-mode-f', E); $('#ve-src').closest('.ig-grid')?.classList.toggle('ve-on', E);
    if (E) {
      if (VS && !VS.tasks?.[ve.task]) ve.task = VE_TASKS.map(t => t[0]).find(k => VS.tasks?.[k]) || ve.task;
      // “模式”两个字不再显示（三个按钮一看就懂，2026-11-04）：原来标签上的说明放到各个按钮的鼠标停留提示里
      $('#ve-task').innerHTML = VE_TASKS.map(([k, n]) => `<button type="button" data-t="${k}" class="${ve.task === k ? 'on' : ''}"${!VS || VS.tasks?.[k] ? (VE_HINT[k] ? ` data-tip="${esc(VE_HINT[k])}"` : '') : ' disabled title="所需的文件尚未下载"'}>${n}</button>`).join('');
      $$('#ve-task [data-t]').forEach(b => b.onclick = () => { ve.task = b.dataset.t; save(); paintMode(); });
      $('#vd-model-d').textContent = VS && VS.missing?.length && !VS.tasks?.[ve.task] ? '改视频尚缺文件：' + VS.missing.join('、') : ''; $('#vd-model-d').hidden = !$('#vd-model-d').textContent;
    }
    mfHide();
    $('#vd-src').hidden = E; $('#ve-src').hidden = !E;
    if (E) tipLabel($('#vd-src-l'), '原视频', VE_SRC_HINT); else vdSrcLabel();
    $('.vd-opts').hidden = E; $('#ve-opts').hidden = !E; paintGenBase();
    $('#vd-ai').hidden = E && !((ve.task === 'head' && veTpl() && !veFs()) || veRef()); if (!E) { $('#ve-tplw').hidden = true; }
    $('#vd-ai').title = E ? (veRef() ? '由 AI 助手参照原视频和素材，在程序按当前设置写好的底稿上补全整段提示词' : '由 AI 助手参照头像撰写脸部描述（会附带头像）') : '使用 AI 助手撰写视频提示词（会附带首帧、尾帧和更多素材）';
    paintStruct();
    if (E) { ta.dataset.minh = st.efold && IG_WIDE() ? '240' : '80'; ta.rows = 3; } else { delete ta.dataset.minh; ta.rows = 5; }  // 改视频的提示词是可选的：宽窗口时框可以矮一点（左栏一屏放下）；收起参数时高一点
    const want = (E ? st.eprompt : st.prompt) || ''; if (ta.value !== want) ta.value = want;
    ta.placeholder = E ? vePh() : '描述画面和动作';
    if ($('#vd-endt')) $('#vd-endt').hidden = E || !(flfOk() && (VID_SRC || VID_END));
    paintVeTile();
    if (E) { paintVeSrc(); paintVeOpts(); }
    if (vidStage.grid) vdDualBind(); else if (!(E && vidStage.src && VE_VID)) vidStage(vidGal.find(g => g.id === (vidStage.cur || vidStage.last)) || vidGal[0] || null);  // 换了模式：右边按这个模式重新显示（生成视频没有剪辑 / 对比）
    paintSec(); paintAdvN(); vdRefresh(); ta.dispatchEvent(new Event('input'));
  };
  $$('#vd-mode-sw [data-v]').forEach(b => b.onclick = () => { if (st.mode === b.dataset.v) return; st.mode = b.dataset.v; vidSizeMode(); save(); paintMode(); });
  renderVideo.paintMode = paintMode; renderVideo.paintSrc = paintSrc;
  paintMode();
  const fileData = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(new Error('无法读取该视频文件')); r.readAsDataURL(f); });
  const veGo = async btn => {
    const T = ve.task, promptInput = ta.value; let p = promptInput.trim();
    if (!VE_VID) return toast('请先放入要修改的视频', true);
    if (T === 'swap' && !VE_REF) return toast('换人需要放入一张人物图（要换成的那个人）', true);
    if (T === 'head' && !VE_REF) return toast('换头需要放入一张头像（新的那张脸）', true);
    if (veOwn() && !VE_REF && veMethod() !== 'ref') return toast('已关闭“Qwen 生图”：请先放入一张换好衣服的人物图', true);  // 参考生成可以不放图：跳过 Qwen 改图，只按提示词修改
    const slot = !veTpl() && /‹[^›]*›/.exec(ta.value);
    if (slot) { ta.focus(); ta.setSelectionRange(slot.index, slot.index + slot[0].length); return toast(`请先将模板中的 ${slot[0]} 替换为您的内容`, true); }
    if (!p && !veTpl() && !veOwn()) { ta.focus(); return toast('关闭模板后，提示词将原样发送给模型：请写完整', true); }
    if (!p && T === 'outfit' && !VE_REF) { ta.focus(); return toast(veOwn() ? '未放入参考图时，请写明要换成的衣服' : '请写明要换成的衣服，或放入一张衣服图', true); }
    if (veVg() && veOwn() && !VE_REF) return toast('Viggle 重拍需要一张改好的图：放入参考图，或打开“Qwen 生成”', true);
    if (st.size === 'custom' && !resOk(st.res)) { $('#vd-res')?.focus(); return toast('自定义分辨率请填写为 640 或 832x480 的形式', true); }
    if (VE_VID.dur && VE_VID.dur - (+ve.start || 0) < 1) { $('#ve-start')?.focus(); return toast('从该起点往后不足 1 秒，请将起点前移', true); }
    { const S2 = veXs().length ? veAllSegs() : []; if (S2.some((s, i) => i && s.start < S2[i - 1].end - 0.05)) return toast('选的几段时间有重叠：请调整黄色框，让各段互不重叠', true); }
    const a = vidAdv(), per = {}; VID_PER.forEach(k => { if (k !== 'fps' && k !== 'audio' && vidChanged(k, 'h3')) per[k] = a[k + '_h3']; });
    const lab = btn.querySelector('span'), old = lab.textContent; btn.disabled = true;
    let tr; try { lab.textContent = st.plang === 'en' ? '翻译中…' : old; tr = await vdTr(true); } finally { lab.textContent = old; }
    if (!tr) { btn.disabled = false; return; }
    p = tr.prompt;
    try {
      if (VE_VID.kind === 'upload') lab.textContent = '上传中…';
      const video = matsVidRef(VE_VID) || { data: await fileData(VE_VID.file) };
      const n = Math.max(1, Math.min(4, st.count || 1));  // 生成数量：排 n 段，种子各不相同
      // 官方原版没改过步数：不传，后台用它自己的默认（20 步）
      const steps = ['official', 'full'].includes(veBaseNow()) && !vidChanged('steps', 'h3') ? {} : { steps: vidP('steps', 'h3') };
      const qsb = ve.qshare === true && veXs().length && veMethod() === 'ref' && !veOwn() ? Date.now().toString(36) + Math.random().toString(36).slice(2, 6) : '';  // 多段共用衣服图：这一批的记号（生成几个版本就各版本各一张）
      for (const sg of (veXs().length ? veAllSegs() : [null])) for (let i = 0; i < n; i++) await api('/api/video/jobs', { body: { model: 'h3', edit: { ...ve, segs: undefined, qshare: qsb && sg ? qsb + '-' + i : undefined, ...(sg ? { start: veSegR2(sg.start), end: veSegR2(sg.end), follow: false } : {}), splice: sg ? true : veSpl(), tpl: veTpl(), target: tr.target, plang: tr.plang, own: veOwn(), ffguide: veFfg(), vg: veVg() }, video, ...(VE_REF ? { init: VE_REF.kind === 'gallery' ? { gallery: VE_REF.id } : { data: VE_REF.data } } : {}),
        prompt: p, prompt_input: promptInput, seconds: sg ? +(sg.end - sg.start).toFixed(3) : veSecs(), size: st.size === 'custom' ? '480p' : st.size, res: st.size === 'custom' ? st.res : '', seed: st.seed >= 0 ? st.seed + i : -1, ...steps, engine: st.engine || 'auto',
        ...per, interp: !!a.interp, interp_x: a.interp_x || (a.interp ? 2 : 1), interp_by: a.interp_by || 'rife', upscale: !!a.upscale, loras: vidLoras4('h3'), ...(vidTurbo() ? { turbo: { ref2v: vidTurbo().file } } : {}) } });
      $('#vd-note').textContent = ''; $$('#vd-live .ig-job.error').forEach(c => VID_HIDE.add(c.dataset.id)); vidWatch();
      // 2026-11-14 推荐分段学偏好：这次选的段落（和当时推荐的）记下来，只在本机、只有数字（segpref.jsonl）；找过换装点的素材库 / 视频库视频才记
      if (veCpOk() && matsVidRef(VE_VID)) api('/api/video/segpref', { body: { video: matsVidRef(VE_VID), segs: veAllSegs().map(x => [+x.start, +x.end]), rec: VE_CP.rec || null, task: ve.task } }).catch(() => { });
    } catch (e) { toast(e.message, true); }
    lab.textContent = old; btn.disabled = false;
  };
  // 视频里某一秒的画面（参考视频、开头片段给 AI 助手看）
  const vidFrameAt = (url, t) => new Promise((ok, no) => { const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto';
    v.onloadedmetadata = () => { v.currentTime = Math.max(0, Math.min((v.duration || 1) - 0.05, t < 0 ? (v.duration || 1) + t : t)); };
    v.onseeked = () => { try { const k = Math.min(1, 1024 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement('canvas'); c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
      c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); ok(c.toDataURL('image/jpeg', .9)); } catch (e) { no(e); } v.removeAttribute('src'); v.load(); };
    v.onerror = () => no(new Error('无法读取该视频')); v.src = url; });
  const vdAi = async preset => {  // H3 用官方格式的预设；首帧、尾帧和更多素材都带过去（图片给模型看，声音写成文字说明）
    const b = $('#vd-ai'); b.disabled = true;
    try {
      const vis = PGST?.vision !== false, items = [], notes = [], X = VID_X, H3 = st.model === 'h3';
      if (st.mode === 'edit' && veRef()) {  // 参考生成：原视频几帧 + 人物图 / 衣服图，按结构写整段
        if (!VE_VID) return toast('请先放入原视频', true);
        const ve = veState(), sw = ve.task === 'swap', it2 = [], st0 = +ve.start || 0, d = Math.max(1, Math.min(veSecs(), (VE_VID.dur || st.eseconds) - st0));
        for (const [k, t] of [[0, st0 + 0.05], [1, st0 + d / 2], [2, st0 + d - 0.1]]) { const f = vis ? await vidFrameAt(VE_VID.url, t).catch(() => null) : null; const x = f ? await pgImgPrep(f).catch(() => null) : null;
          if (x) { x.lab = `原视频 <Video 1> 的第 ${(t - st0).toFixed(1)} 秒（${['开头', '中间', '结尾'][k]}）`; x.short = ['原视频·头', '原视频·中', '原视频·尾'][k]; it2.push(x); } }
        if (VE_REF && vis) { const x = await pgImgPrep(VE_REF.url).catch(() => null); if (x) { x.lab = sw ? '人物图 <Picture 1>：换成这个人' : veOwn() ? '<Picture 1>：这个人换好衣服后的样子' : '衣服图：程序会先用 Qwen 把原视频里的人换上这件衣服，换好的图才是 <Picture 1>'; x.short = sw ? '人物图' : '衣服图'; it2.push(x); } }
        // 2026-11-08：把程序按当前设置写好的整段模板当底稿发过去（保留写了的、朝向 / 人数 / 节奏都在里面），AI 只补细节——
        // 以前只说“只换衣服”：写了保留什么 AI 都不知道；没放图时也说有 <Picture 1>
        const pic = sw || !veOwn() || !!VE_REF, base = veTpl() ? await api('/api/video/prompt-preview', { body: vdPreviewBody().body })
          .then(r => ((r.stages || []).find(x => x.label === '视频生成') || {}).text || '').catch(() => '') : '';
        const mats = ['素材说明（改视频 · ' + (sw ? '换人 · 审美优先' : '改衣 · 参考生成') + '）：', `原视频是 <Video 1>，取 ${d.toFixed(1)} 秒`, sw ? '把原视频里的' + (ve.target || '主要人物') + '完全换成 <Picture 1> 的人，动作、机位、场景、光线照原视频逐帧一致'
          : '同一个人、同样的动作和场景，只换衣服' + (ta.value.trim() ? '：' + ta.value.trim() : '') + '；脸、发型、身材和原视频一致'
          + (/保留|留着|留下|不变|keep|leave/i.test(ta.value) ? '。要保留的每一样都照原视频画面写清楚具体样子（颜色、款式、长度、在身上的位置），写进底稿里出现它的每一处' : ''), '写法：summary 以 [video editing] 开头',
          ...(base ? ['', '程序按当前设置写好的底稿（以它为准：保留六个部分和全部要求，只按素材补充人物外观、按时间顺序的动作、场景和光线）：', base] : [])].join('\n');
        pgState().back = 'edit';
        const head = `语言：${st.plang === 'en' ? '英文' : '中文'}\n素材清单：${pic ? `<Picture 1>=${sw ? '人物图' : '换好衣服的人物图'}，` : '没有 <Picture 1>（不要写这个标签），'}<Video 1>=原视频；时长 ${Math.round(d)} 秒`;
        const pre = sw ? 'video-ref' : 'vedit-outfit';  // 2026-11-09：改视频按任务选对应的预设
        return pgOpen(ta.value.trim(), 'video', pre, it2, head + '\n' + mats);
      }
      if (st.mode === 'edit') {  // 换头：带上头像，让模型照着写 Facial details
        if (!VE_REF) return toast('请先放入一张头像', true);
        const it = vis ? await pgImgPrep(VE_REF.url).catch(() => null) : null;
        pgState().back = 'edit';
        return pgOpen(ta.value.trim(), 'video', 'head-face', it ? [it] : []);
      }
      pgState().back = null;
      const add = async (url, lab, short) => { if (!url) return; if (!vis || items.length >= 8) { notes.push(lab + '（这张图没法一起发过去）'); return; }
        const it = await pgImgPrep(url).catch(() => null); if (it) { it.lab = lab; it.short = short; items.push(it); } };
      const fr = async (v, t) => v?.url ? await vidFrameAt(v.url, t).catch(() => null) : null;
      if (VID_SRC) await add(VID_SRC.url, '首帧：视频第 0 秒的画面', '首帧');
      if (H3 && X.clip) await add(await fr(X.clip.vid, X.clip.part === 'head' ? 0.05 : -0.05), `开头片段：一段视频的${X.clip.part === 'head' ? '最前' : '最后'} ${X.clip.n === 39 ? '1.6' : '0.9'} 秒接在新视频最前面，这是那一段的${X.clip.part === 'head' ? '第一' : '最后'}帧；新视频从这里接着往下演`, '开头片段');
      if (H3) for (const k of [...X.keys].sort((p, q) => p.t - q.t)) await add(k.img.url, `关键帧：视频到第 ${k.t} 秒时是这个画面`, `${k.t} 秒`);
      if (VID_END) await add(VID_END.url, '尾帧：视频最后停在这个画面', '尾帧');
      if (H3) {
        for (const [i, r] of X.refs.entries()) await add(r.url, `参考图 <Picture ${i + 1}>：人物 / 衣服 / 物品 / 场景 / 画风照着它`, `参考图 ${i + 1}`);
        for (const [i, v] of X.rvids.entries()) await add(await fr(v, (v.dur || 2) / 2), `参考视频 <Video ${i + 1}> 的中间一帧（这段视频${v.dur ? ' ' + (+v.dur).toFixed(1) + ' 秒' : ''}，动作和镜头照着它${v.snd === 'lock' ? '；成品的声音就用这段视频的原声' : v.snd === 'ref' ? '；它的原声也当参考' : ''}）`, `参考视频 ${i + 1}`);
        if (X.guide) await add(await fr(X.guide.vid, 0.05), `引导视频的第一帧：新视频从第 0 帧起逐帧照着这段原视频（${X.guide.vid.dur ? (+X.guide.vid.dur).toFixed(1) + ' 秒' : ''}），只改提示词里写的地方`, '引导视频');
        if (X.audio) notes.push(`指定声音：「${X.audio.name}」${X.audio.dur ? (+X.audio.dur).toFixed(1) + ' 秒' : ''}，从视频第 ${X.audio.start} 秒开始对上（人照着这段声音说话 / 跟着这段音乐动）`);
        X.raudios.forEach((a, i) => notes.push(`参考音频 <Audio ${i + 1}>：「${a.name}」${a.dur ? (+a.dur).toFixed(1) + ' 秒' : ''}，说话的音色照着它`));
      }
      { const nt = X.rvids.filter(v => v.snd && v.snd !== 'none').length; if (H3 && nt) notes.push(`带原声的参考视频：它们的原声排在参考音频前面，编号是 <Audio 1>${nt > 1 ? ' ~ <Audio ' + nt + '>' : ''}；单独的参考音频从 <Audio ${nt + 1}> 开始`); }
      if (H3 && (X.refs.length || X.rvids.length || X.raudios.length || X.clip)) notes.push('写法：用了参考 / 开头片段，提示词不要写第一行“For the target video, at 0.00 seconds … <Picture 1> … is fully referenced.”；<Picture N> 只指参考图 N（不是首帧、关键帧），<Video N>、<Audio N> 同样按上面的编号');
      const many = items.length > 1 || notes.length || (H3 && vidXn());
      let mats = many ? ['素材说明（生视频页上放的）：', `视频时长 ${st.seconds} 秒${VID_SRC ? '' : '；没有首帧'}`, ...notes].join('\n') : null;
      let pre = preset || (H3 ? 'video-base' : 'video');
      if (H3 && !preset) {  // 自动选写法：有参考图 / 参考视频 / 参考音频 → 官方参考写法；没有 → 官方基础写法（文生 / 首帧 / 首尾帧 / 尾帧）
        const R = X.refs.length || X.rvids.length || X.raudios.length, lang = `语言：${st.plang === 'en' ? '英文' : '中文'}`;
        if (R) { pre = 'video-ref';
          const L = [...X.refs.map((_, i) => `<Picture ${i + 1}>=参考图 ${i + 1}`), ...X.rvids.map((_, i) => `<Video ${i + 1}>=参考视频 ${i + 1}`), ...X.raudios.map((_, i) => `<Audio ${i + 1}>=参考音频 ${i + 1}`)];
          mats = `${lang}\n素材清单：${L.join('，')}；时长 ${st.seconds} 秒` + (mats ? '\n' + mats : '');
        } else { const mode = VID_SRC && VID_END && flfOk() ? 'FL2VA' : VID_SRC ? 'I2VA' : VID_END && flfOk() ? 'L2VA' : 'T2VA';
          mats = `${lang}\n模式：${mode}，时长：${st.seconds} 秒` + (mats ? '\n' + mats : ''); }
      }
      pgOpen(ta.value.trim(), 'video', pre, items, mats);
    } finally { b.disabled = false; }
  };
  $('#vd-ai').onclick = () => vdAi();
  const vdPreviewBody = () => {  // 程序按当前设置真正会发的提示词（查看提示词、AI 助手的底稿都用它）
    const E = st.mode === 'edit', src = ta.value.trim(), srcT = E ? (ve.target || '').trim() : '';
    const translated = st.plang === 'en' && TR && TR.src === src && TR.srcT === srcT && !TR.busy && !TR.err;
    return { translated, src, srcT, body: { model: st.model, prompt_input: ta.value, prompt: translated ? TR.en.trim() || src : src,
      has_ref: !!VE_REF, seconds: E ? veSecs() : st.seconds,
      ...(E ? { edit: { ...ve, splice: veSpl(), tpl: veTpl(), target: translated ? TR.enT : srcT, plang: translated || st.plang === 'en' && !hasZh(src) && !hasZh(srcT) ? 'en' : 'zh', method: veMethod(), own: veOwn(), ffguide: veFfg(), vg: veVg() } }
        : { h3x: { refs: VID_X.refs.map(() => ({})), rvids: VID_X.rvids.map(v => ({ audio: v.snd || 'none' })), raudios: VID_X.raudios.map(() => ({})) } }) } };
  };
  const veTextIn = (text, msg, own0) => {  // 整段提示词放进提示词框，关掉“使用模板”（以后原样发送），选中第一个 ‹…›
    const own = own0 ?? veOwn(); ta.value = text; veSetTpl(false); if (ve.task === 'outfit') ve.own = own; save();  // 关模板前后参考图的做法不变 paintVeOpts(); paintVeSrc(); paintVeTile(); ta.placeholder = vePh(); vdRefresh();
    ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus();
    const m = /‹[^›]*›/.exec(text); if (m) ta.setSelectionRange(m.index, m.index + m[0].length); else ta.setSelectionRange(0, 0);
    toast(msg);
  };
  const veFillTpl = x => {  // 填入模板：参考图的做法照模板给的（没给就照现在的）
    veTextIn(x.text, `已填入「${x.label}」模板，已关闭「使用模板」` + (/‹/.test(x.text) ? '：请改写 ‹…› 处' : ''), x.own === null || x.own === undefined ? ve.own === true : !!x.own);
  };
  PromptInspector.bind(ta, async () => {
    const { translated, src, srcT, body } = vdPreviewBody();
    const trace = await api('/api/video/prompt-preview', { body });
    if (st.plang === 'en' && (hasZh(src) || hasZh(srcT)) && !translated) trace.notes.unshift('英文翻译尚未确认：当前预览使用中文。确认翻译后可再次查看最终的英文内容。');
    return trace;
  }, { use: t => { const s = st.mode === 'edit' && veTpl() && ((t.stages || []).find(x => x.label === '视频生成') || {}).text;
      return s && s.trim() !== ta.value.trim() ? () => veTextIn(s, '已放到提示词框，已关闭「使用模板」') : null; }, tpl: () => ({ pages: [st.mode === 'edit' ? 'vedit' : 'vgen'] }) });
  const go = async () => {
    const btn = $('#vd-go'); if (!btn || btn.disabled) return;
    if (st.mode === 'edit') return veGo(btn);
    const H3 = st.model === 'h3', X = VID_X, promptInput = ta.value;
    if (!VID_SRC && !H3) return toast('请先选择一张首帧图片', true);  // H3 可以没有首帧：只按文字和更多素材生成
    if (!ta.value.trim()) { ta.focus(); return toast('请写明画面中要发生的内容', true); }
    if (H3 && X.clip && VID_SRC) return toast('开头片段和首帧都位于第 0 帧，只能二选一：请移除首帧或开头片段', true);
    if (H3 && X.guide && (VID_SRC || X.clip)) return toast('引导视频从第 0 帧起逐帧引导：与首帧、开头片段只能择一使用', true);
    if (H3 && X.audio && X.rvids.some(v => v.snd === 'lock')) return toast('“指定声音”和“参考视频原声驱动”只能二选一', true);
    if (H3 && X.keys.some(k => k.t > st.seconds)) return toast(`部分关键帧的时间超过了视频时长（${st.seconds} 秒）`, true);
    if (H3 && X.audio && X.audio.start >= st.seconds) return toast(`声音的开始时间超过了视频时长（${st.seconds} 秒）`, true);
    if (st.size === 'custom' && !resOk(st.res)) { $('#vd-res')?.focus(); return toast('自定义分辨率请填写为 640 或 832x480 的形式', true); }
    const a = vidAdv(), M = st.model, img = x => x.kind === 'gallery' ? { gallery: x.id } : { data: x.data };
    const OFFB = H3 && vidGbase() === 'official';  // 官方底模没改过步数：不传，后台用 20 步
    const per = {}; VID_PER.forEach(k => { if (vidChanged(k, M)) per[k] = a[k + '_' + M]; });
    btn.disabled = true;
    const tr = await vdTr(false).catch(e => { toast(e.message, true); return null; });
    if (!tr) { btn.disabled = false; return; }
    try {
      let h3x = null;  // H3 的更多条件：上传的视频 / 声音在这时才读成 data URL
      if (H3 && vidXn()) {
        const vref = v => matsVidRef(v) || fileData(v.file).then(data => ({ data }));
        h3x = { keys: X.keys.map(k => ({ t: k.t, img: img(k.img) })), refs: X.refs.map(img), raudios: X.raudios.map(r => ({ data: r.data })),
          rvids: await Promise.all(X.rvids.map(async v => ({ ...(await vref(v)), audio: v.snd || 'none' }))), clip: X.clip ? { video: await vref(X.clip.vid), part: X.clip.part, n: X.clip.n } : null,
          guide: X.guide ? { video: await vref(X.guide.vid), audio: X.guide.audio !== false } : null,
          audio: X.audio ? { data: X.audio.data, start: X.audio.start } : null };
        if (JSON.stringify(h3x).length > 90e6) throw new Error('放入的视频 / 声音过大（合计最多约 65MB），请换用较短的文件，或从视频库选择');
      }
      const chain = VID_SRC?.chain || null;
      const n = Math.max(1, Math.min(4, st.count || 1));  // 生成数量：排 n 段，种子各不相同（填了种子就依次 +1）
      for (let i = 0; i < n; i++) await api('/api/video/jobs', { body: { model: M, prompt: tr.prompt, prompt_input: promptInput, seconds: st.seconds, size: st.size === 'custom' ? '480p' : st.size, res: st.size === 'custom' ? st.res : '',
        seed: st.seed >= 0 ? st.seed + i : -1, ...(OFFB && !vidChanged('steps') ? {} : { steps: vidP('steps') }), ...(vidTurbo() ? { turbo: { [vidTurboKind()]: vidTurbo().file } } : {}),
        ...(H3 ? { base: 'official', engine: st.engine || 'auto' } : {}),
        ...per, interp: !!a.interp, interp_x: a.interp_x || (a.interp ? 2 : 1), interp_by: a.interp_by || 'rife', upscale: !!a.upscale, loras: vidLoras4(st.model), ...(M === 'h3' && a.fast ? { h3fast: true } : {}),
        ...(VID_SRC ? { init: img(VID_SRC) } : {}), ...(VID_END && flfOk() ? { end: img(VID_END) } : {}), ...(chain ? { chain_of: chain } : {}), ...(h3x ? { h3x } : {}) } });
      $('#vd-note').textContent = ''; $$('#vd-live .ig-job.error').forEach(c => VID_HIDE.add(c.dataset.id)); vidWatch();
    } catch (e) { toast(e.message, true); }
    btn.disabled = false;
  };
  $('#vd-go').onclick = go;
  pageRefresh(['video'], () => { if ($('#vd-live')) { vidGallery(); vidWatch(); } });
  vidGallery(); vidWatch();
}
renderVideo.useSrc = x => { VID_SRC = vidImg(x); vidState().srcId = x.id; vidState().mode = 'gen'; persist(); };

/* 续接：取出这段视频的最后一帧当首帧，填回提示词；生成后自动和前面合成一段完整的 */
async function vidChain(x, after, prompt) {
  if (!x) return;
  try {
    const r = await api('/api/video/lastframe/' + encodeURIComponent(x.id));
    const st = vidState();
    VID_SRC = { kind: 'upload', data: r.data, url: r.data, w: r.width, h: r.height, chain: x.id }; VID_END = null;
    st.srcId = null; st.mode = 'gen'; st.prompt = prompt ?? x.prompt ?? ''; sessionStorage.setItem('vdDraft', st.prompt);
    if (x.model && (!VIDST || (VIDST.models || []).some(m => m.key === x.model && !m.missing.length))) st.model = x.model;
    persist(); after?.();
    go('video', location.pathname !== '/video');
    toast('已将最后一帧设为首帧：生成后将自动合成完整视频');
  } catch (e) { toast(e.message, true); }
}

/* 正在做的视频：每 1.5 秒看一次进度；做完一段，右边马上多一段 */
function vidWatch() {
  let seen = '';
  pollStart(async stop => {
    const live = $('#vd-live'); if (!live) return stop();
    const list = await api('/api/video/jobs').catch(() => null); if (!list) return;
    if (!$('#vd-live')) return stop();
    const act = list.filter(j => ['queued', 'running'].includes(j.state)).sort((a, b) => (b.state === 'running') - (a.state === 'running') || a.created - b.created), fin = list.filter(j => j.state === 'error' && Date.now() / 1000 - j.finished < 600 && !VID_HIDE.has(j.id));  // 失败 / 取消的：点 × 或开始下一条时收起
    vidJobsPaint(live, act, fin);
    const sig = list.map(j => j.id + j.state).join();
    if (sig !== seen) { if (seen) vidGallery(); seen = sig; }
    const w = list.find(j => j.state === 'done' && j.warn && !VID_HIDE.has('w' + j.id)); if (w) { VID_HIDE.add('w' + w.id); toast(w.warn, true); }
    if (!act.length) stop();
  }, 1500);
}
/* 任务列表（2026-11-05 用户定）：标题栏中间一个小进度条（有任务时才有），一眼看到大致进度；鼠标停上去弹出一张小卡片，列出每个任务的进度；
   点它 = 在上方展开完整的任务列表，再点 = 收起（收起时上方那块不占地方）。收起 / 展开会记住，默认展开 */
const vidJobName = j => j.prompt || (j.edit ? '改视频 · ' + veTaskName(j.edit.task) : '生成视频');
function vidJobsPaint(live, act, fin) {
    live._jobs = [act, fin];
    const all = [...act, ...fin], F = !MOB() || !!S.vdJobFold;  // 电脑：不再在上方列出（2026-11-08 用户），全部放进右下角的任务角标
    live.classList.toggle('many', all.length > 1); live.classList.toggle('folded', F);
    live.innerHTML = F ? '' : all.map(j => `<div class="card ig-job ${j.state}" data-id="${esc(j.id)}" title="${esc([j.prompt, [j.edit ? '改视频 · ' + veTaskName(j.edit.task) : '', j.model_name, j.size, j.seconds + ' 秒', '种子 ' + j.seed].filter(Boolean).join(' · ')].filter(Boolean).join('\n'))}"><div class="ig-job-pv"><span class="ig-job-ic">${j.state === 'error' ? '!' : VID_IC.film}</span></div>
      <div class="ig-job-main"><div class="ig-job-t">${esc(j.prompt || (j.edit ? '改视频 · ' + veTaskName(j.edit.task) : ''))}</div><div class="tiny">${esc([j.edit ? '改视频 · ' + veTaskName(j.edit.task) : '', j.model_name, j.size, j.seconds + ' 秒', j.chain_of ? '续接' : '', j.flf ? '首尾帧' : '', j.interp ? '插帧' : '', j.upscale ? '超分' : '', '种子 ' + j.seed].filter(Boolean).join(' · '))}</div>
        <div class="ig-job-st">${j.state === 'error' ? `<span style="color:var(--red)">${esc(/^生成失败/.test(j.error) ? j.error : '生成失败：' + j.error)}</span>` : esc(j.message) + jobTimer(j, 'sm')}</div>${j.state === 'running' ? `<div class="ig-bar"><i style="width:${j.progress || 0}%"></i></div>` : ''}</div>
      ${j.state === 'error' ? '<button type="button" class="pl-ib" data-hide title="不再显示此条（不影响作品）" aria-label="关闭">' + ICON.x + '</button>' : '<button class="btn small" data-x>取消</button>'}</div>`).join('');
    $$('[data-hide]', live).forEach(b => b.onclick = () => { VID_HIDE.add(b.closest('[data-id]').dataset.id); b.closest('[data-id]').remove(); vidJobsPaint(live, act, fin.filter(f => !VID_HIDE.has(f.id))); });
    $$('[data-x]', live).forEach(b => b.onclick = async () => { b.disabled = true; b.textContent = '正在取消…'; await api(`/api/video/jobs/${b.closest('[data-id]').dataset.id}/cancel`, { body: {} }).catch(e => toast(e.message, true)); });
    vidJobPill(live, act, fin);
}
function vidJobPill(live, act, fin) {
    const pl = $('#vd-jp'); if (!pl) return;
    if (!MOB()) return vidJobDock(pl, live, act, fin);
    pl.classList.remove('dock', 'pin');
    const all = [...act, ...fin], F = !!S.vdJobFold; pl.hidden = !all.length; if (!all.length) { pl.innerHTML = ''; return; }
    const run = act.find(j => j.state === 'running'), q = act.filter(j => j.state === 'queued').length, err = fin.length, p = Math.round(run?.progress || 0);
    const txt = run ? `<span class="vd-jp-w">生成中 </span>${p}%` : act.length ? '排队中' : '生成失败';
    const row = j => `<div class="vd-jp-r ${j.state}"><div class="vd-jp-rt"><b>${esc(vidJobName(j))}</b><span>${j.state === 'running' ? (Math.round(j.progress || 0)) + '%' : j.state === 'queued' ? '排队中' : '失败'}</span></div>
      <div class="tiny vd-jp-rs">${j.state === 'error' ? esc(/^生成失败/.test(j.error) ? j.error : '生成失败：' + j.error) : esc(j.message || '') + jobTimer(j, 'sm')}</div>${j.state === 'running' ? `<div class="ig-bar"><i style="width:${j.progress || 0}%"></i></div>` : ''}</div>`;
    pl.classList.toggle('err', !act.length); pl.classList.toggle('folded', F);
    pl.setAttribute('role', 'button'); pl.tabIndex = 0; pl.setAttribute('aria-expanded', String(!F)); pl.setAttribute('aria-label', (F ? '展开任务列表：' : '收起任务列表：') + (run ? '生成中 ' + p + '%' : txt));
    pl.innerHTML = `<span class="vd-jp-dot"></span><span class="vd-jp-t">${txt}</span>${run ? `<span class="vd-jp-bar"><i style="width:${p}%"></i></span>` : ''}${q ? `<span class="vd-jp-n" title="排队中">+${q}</span>` : ''}${err && act.length ? `<span class="vd-jp-n e">失败 ${err}</span>` : ''}
      <svg class="vd-jp-ch" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${F ? 'M6 9l6 6 6-6' : 'M6 15l6-6 6 6'}"/></svg>
      <div class="vd-jp-pop" role="tooltip"><div class="vd-jp-h"><b>任务</b><span class="tiny">${[act.length ? act.length + ' 个进行中 / 排队' : '', err ? err + ' 个失败' : ''].filter(Boolean).join(' · ')}</span></div>${all.map(row).join('')}</div>`;
    $('.vd-jp-pop', pl).onclick = e => e.stopPropagation();  // 卡片里的计时按钮：点开看各步骤，不触发收起 / 展开
    pl.onclick = () => { S.vdJobFold = !S.vdJobFold; persist(); vidJobsPaint(live, ...live._jobs); };
    pl.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pl.click(); } };
}
/* 电脑（2026-11-08 用户）：任务固定在右下角，和输入框同一高度——名字 + 进度条 + 百分比（还有几个在排队就 +N）；
   鼠标停上去弹出每个任务的详细进度，可以在里面取消；点一下 = 一直开着（再点 / 点别处收起） */
function vidJobDock(pl, live, act, fin) {
    const all = [...act, ...fin];
    pl.classList.add('dock'); pl.classList.remove('folded');
    { const host = $('#main'); $$('#main > .vd-jp.dock').forEach(o => o !== pl && o.remove());  // 生视频那一块整个有 transform：fixed 会跟着它走，放到 #main 下面（换页时跟着页面一起清掉）
      if (host && pl.parentElement !== host) host.append(pl); }
    if (!all.length) { pl.hidden = true; pl.innerHTML = ''; pl.classList.remove('pin'); return; }
    pl.hidden = false;
    if (pl._down) return;  // 正按着里面的按钮：这一轮先不重画（不然按钮被换掉，点不到）
    const run = act.find(j => j.state === 'running'), lead = run || act[0] || fin[0], more = all.length - 1, p = Math.round(run?.progress || 0), err = fin.length;
    const st = run ? p + '%' : act.length ? '排队中' : '失败';
    const row = j => `<div class="vd-jp-r ${j.state}" data-id="${esc(j.id)}"><div class="vd-jp-rt"><b>${esc(vidJobName(j))}</b><span>${j.state === 'running' ? (Math.round(j.progress || 0)) + '%' : j.state === 'queued' ? '排队中' : '失败'}</span>${j.state === 'error' ? `<button type="button" class="pl-ib" data-hide aria-label="不再显示此条" title="不再显示此条（不影响作品）">${ICON.x}</button>` : '<button type="button" class="btn small" data-x>取消</button>'}</div>
      <div class="tiny vd-jp-rm">${esc([j.model_name, j.size, j.seconds + ' 秒', j.chain_of ? '续接' : '', j.flf ? '首尾帧' : '', j.interp ? '插帧' : '', j.upscale ? '超分' : '', '种子 ' + j.seed].filter(Boolean).join(' · '))}</div>
      <div class="tiny vd-jp-rs">${j.state === 'error' ? esc(/^生成失败/.test(j.error) ? j.error : '生成失败：' + j.error) : esc(j.message || '') + jobTimer(j, 'sm')}</div>${j.state === 'running' ? `<div class="ig-bar"><i style="width:${j.progress || 0}%"></i></div>` : ''}</div>`;
    pl.classList.toggle('err', !act.length);
    pl.setAttribute('role', 'button'); pl.tabIndex = 0; pl.setAttribute('aria-haspopup', 'true'); pl.setAttribute('aria-expanded', String(pl.classList.contains('pin')));
    pl.setAttribute('aria-label', '任务：' + vidJobName(lead) + ' ' + st + (more ? `，另有 ${more} 个` : ''));
    pl.innerHTML = `<span class="vd-jp-dot"></span><span class="vd-jp-nm">${esc(vidJobName(lead))}</span>${run ? `<span class="vd-jp-bar"><i style="width:${p}%"></i></span>` : ''}<span class="vd-jp-t">${st}</span>${more ? `<span class="vd-jp-n">+${more}</span>` : ''}
      <div class="vd-jp-pop" role="dialog" aria-label="任务"><div class="vd-jp-h"><b>任务</b><span class="tiny">${[act.length ? act.length + ' 个进行中 / 排队' : '', err ? err + ' 个失败' : ''].filter(Boolean).join(' · ')}</span></div>${all.map(row).join('')}</div>`;
    const pop = $('.vd-jp-pop', pl);
    pop.onclick = e => e.stopPropagation();
    $$('[data-hide]', pop).forEach(b => b.onclick = () => { VID_HIDE.add(b.closest('[data-id]').dataset.id); vidJobsPaint(live, act, fin.filter(f => !VID_HIDE.has(f.id))); });
    $$('[data-x]', pop).forEach(b => b.onclick = async () => { b.disabled = true; b.textContent = '正在取消…'; await api(`/api/video/jobs/${b.closest('[data-id]').dataset.id}/cancel`, { body: {} }).catch(e => toast(e.message, true)); });
    pl.onclick = () => { pl.classList.toggle('pin'); pl.setAttribute('aria-expanded', String(pl.classList.contains('pin'))); };
    pl.onkeydown = e => { if (e.target === pl && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pl.click(); } else if (e.key === 'Escape') { pl.classList.remove('pin'); pl.blur(); } };
    pl.onpointerdown = () => { pl._down = 1; }; pl.onpointerup = pl.onpointercancel = () => { setTimeout(() => { pl._down = 0; }, 0); };
    if (!vidJobDock.out) { vidJobDock.out = 1; document.addEventListener('pointerdown', e => { const q = $('#vd-jp.pin'); if (q && !q.contains(e.target)) q.classList.remove('pin'); }, true); }
    vdDockFit();
}
/* 右下角的位置：竖着和输入框（收起时那一条）居中对齐；右边选项栏一直伸到底部时，放在它左边；横着放不下名字时只留进度 */
function vdDockFit() {
    const pl = $('#vd-jp.dock') || $('#ig-jp.dock'), cur = $('#vd-cur'), grid = $('#main > .ig-grid');  // 生图页的任务小条（#ig-jp，2026-11-10）也按这里摆
    if (!grid) return;
    const comp = grid.classList.contains('b5-on') ? grid.querySelector(':scope > .ig-top-f') : null, opt = grid.classList.contains('b5-pc') || grid.classList.contains('b5-col') ? null : grid.querySelector('.b5-opt');  // 创作栏版：选项在左栏，任务角标照旧在右下角
    const cr = comp && comp.offsetParent ? comp.getBoundingClientRect() : null, H = innerHeight, Wd = innerWidth;
    const rowH = 58, mid = cr ? cr.bottom - Math.min(rowH, cr.height) / 2 : H - 24 - 18;  // 输入框最下面那一行的中线
    const or = opt && opt.offsetParent ? opt.getBoundingClientRect() : null;
    if (pl && !pl.hidden) {
      const ph = pl.offsetHeight || 36; let right = 24;
      if (or && or.bottom > mid - ph / 2 - 4) right = Wd - or.left + 14;
      pl.style.bottom = Math.round(H - mid - ph / 2) + 'px'; pl.style.right = Math.round(right) + 'px';
      pl.classList.remove('slim');
      if (cr) { const room = Wd - right - (cr.right + 56); if (pl.offsetWidth > room) pl.classList.add('slim'); }  // 56：输入框右边“提示词检查”那个按钮
    }
    if (cur) {
      // 2026-11-10 用户：以前只在右边选项栏收起时显示（开着选项栏就看不到了），提示词框展开时又和框里那行重复。
      // 晚些时候用户又定：这一行始终放在提示词框外的左边（框里不再显示，b5.css 末尾），框展开、收起都一样
      const col = grid.classList.contains('b5-col'), on = !!cr && !MOB(), rail = $('#rail')?.getBoundingClientRect().right || 0, room = cr ? (col ? cr.width : cr.left - rail - 40) : 0;  // 创作栏版：这一行放在左栏输入框的正上方
      cur.hidden = !on || room < 100;  // 2026-11-10：右边选项栏开着时（1440 宽）左边只剩 120 左右：截断显示，悬停看全
      if (!cur.hidden) { cur.style.right = Math.round(Wd - cr.left + 20) + 'px'; cur.style.setProperty('max-width', Math.round(Math.min(room, 420)) + 'px', 'important');  /* b5.css 给 #main 的子元素都加了 max-width 1840px !important：内联也要 !important 才压得住（以前这一行宽度没限住） */ cur.style.top = 'auto';
        cur.style.bottom = Math.round(H - mid - cur.offsetHeight / 2) + 'px'; cur.classList.toggle('in-col', col); if (col) { cur.style.right = Math.round(Wd - cr.right) + 'px'; cur.style.bottom = Math.round(H - cr.top + 8) + 'px'; }
        cur.dataset.tip = cur.scrollWidth > cur.clientWidth + 1 || cur.scrollHeight > cur.clientHeight + 1 ? cur.textContent + '（点击放大提示词框）' : '放大提示词框'; }
    }
}

/* 视频库：生视频页只显示这次打开应用以后的；作品页（#w-vgal）显示全部 */
/* ===== 视频组（2026-11-06 用户）：同一个原视频的所有片段、每段的不同版本、拼好的不同完整视频，缩略图里只占一格（叠放的样子）；
   鼠标停一会 / 点一下从这一格展开组面板（像 Google 相册的“叠放”）。后台给每条记了 grp（原视频指纹，videogen.ensure_groups）。
   齿轮里“拼接片段 · 显示”打开时照旧全部平铺 */
const VG_ON = () => !S.vdPcs;
const VG_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="7" width="13" height="13" rx="2.5"/><path d="M8 4h10.5A2.5 2.5 0 0 1 21 6.5V16"/></svg>';
const vgLen = x => +((x.edit || {}).want || x.duration || x.seconds || 0);
const vgSlotK = x => { const e = x.edit || {}; return `${Math.round((+e.start || 0) * 20) / 20}|${Math.round(vgLen(x) * 20) / 20}`; };
function vgBuild() {  // grp → { all, splices, parts, other, slots: [{ k, start, len, vers（最早的是第 1 版） }], rep: 封面（最新的拼接视频） }
  const M = new Map();
  for (const x of vidGal) { if (!x.grp) continue; let g = M.get(x.grp); if (!g) M.set(x.grp, g = { grp: x.grp, all: [], splices: [], parts: [], other: [] }); g.all.push(x);
    (x.spliced_of ? g.splices : x.splice_src ? g.parts : g.other).push(x); }
  for (const g of M.values()) {
    const sl = new Map(); g.parts.forEach(p => { const k = vgSlotK(p); if (!sl.has(k)) sl.set(k, { k, start: +(p.edit?.start || 0), len: vgLen(p), vers: [] }); sl.get(k).vers.push(p); });
    g.slots = [...sl.values()].sort((a, b) => a.start - b.start); g.slots.forEach(s => s.vers.sort((a, b) => (a.created || 0) - (b.created || 0)));
    g.rep = g.splices[0] || g.all[0];
  }
  vgBuild.m = M; return M;
}
const vgStacked = g => !!g && g.all.length > 1;
const vgTileIs = (t, id) => !!id && (t.dataset.id === id || (!!t.dataset.grp && !!vgBuild.m?.get(t.dataset.grp)?.all.some(y => y.id === id)));
const vgSlotOf = (g, id) => { for (let i = 0; i < (g?.slots || []).length; i++) { const k = g.slots[i].vers.findIndex(v => v.id === id); if (k >= 0) return [i, k, g.slots[i]]; } return null; };
const vgBadge = g => `<b class="vg-n" title="同一个原视频：${g.splices.length} 个拼接视频、${g.parts.length} 个片段">${VG_IC}${g.all.length}</b>`;
/* 自动质检（2026-11-06，设置里开了才会查，见 qc.py）：有问题的那一条在缩略图、组面板、大画面下面标出来 */
const VQC_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/></svg>';
const vqcFlags = x => x?.qc?.flags || [];
const vqcText = f => `${f.a.toFixed(1)}–${f.b.toFixed(1)} 秒：${f.msg}`;
const vqcBadge = list => { const bad = list.filter(x => vqcFlags(x).length); if (!bad.length) return '';
  const tip = bad.length === 1 ? '自动质检：' + vqcFlags(bad[0]).map(vqcText).join('；') : `自动质检：${bad.length} 段可能有问题（点开查看）`;
  return `<b class="vqc" title="${esc(tip)}">${VQC_IC}${bad.length === 1 ? vqcFlags(bad[0]).length : bad.length}</b>`; };
function vqcBar(host, x, v) {  // 大画面 / 详情下面：每处问题一个小块，点了跳到那里
  host.querySelector('.vd-qc')?.remove(); const fl = vqcFlags(x); if (!fl.length) return;
  const d = document.createElement('div'); d.className = 'vd-qc'; d.setAttribute('role', 'group'); d.setAttribute('aria-label', '自动质检');
  d.innerHTML = `<span class="vd-qc-h">${VQC_IC}自动质检</span>` + fl.map((f, i) => `<button type="button" class="vd-qc-f" data-i="${i}" title="跳到第 ${f.a.toFixed(1)} 秒">${esc(vqcText(f))}</button>`).join('');
  d.onclick = e => { const b = e.target.closest('.vd-qc-f'); if (!b || !v) return; v.currentTime = fl[+b.dataset.i].a; v.pause?.(); };
  host.append(d);
}
let VG_POP = null, VG_NOHOV = null;  // VG_NOHOV：刚关掉的那一组，鼠标离开那一格之前不再因为停留而自动弹出
function vgPopClose(now) {
  const p = VG_POP; if (!p) return; VG_POP = null; VG_NOHOV = p.dataset.grp || null; clearTimeout(p._t); p._off?.();
  if (now || reduceMotion) return p.remove();
  p.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.96)' }], { duration: 130, easing: 'ease-in' }).onfinish = () => p.remove();
}
/* 组面板：o.slot 打开时停在哪一段；o.ctx 以哪个拼接视频为准（“换上”替换它里面的那一段）；o.hover 鼠标停留打开（移开就关）；o.open(x) 点了某一条 */
function vgPop(anchor, grp, o = {}) {
  vgBuild(); const g = vgBuild.m.get(grp); if (!g || !anchor?.isConnected) return;
  const r0 = anchor.getBoundingClientRect(); vgPopClose(true);
  const ctx = o.ctx || g.splices.find(s => s.id === vidStage.cur) || g.splices[0] || null, used = new Set(ctx?.spliced_ids || []);
  const card = (x, sub, extra = '') => `<div class="vg-it${x.id === vidStage.cur ? ' on' : ''}" data-id="${esc(x.id)}" tabindex="0" title="${esc(vidTip(x))}">${x.thumb ? `<img src="${vidUrl(x.thumb)}" alt="" loading="lazy" draggable="false">` : `<span class="vd-noth">${VID_IC.film}</span>`}`
    + `${sub.includes(esc(vidPostS(x)) + '<') ? '' : vidPostB(x)}<span class="vg-it-t">${sub}</span>${extra}${vqcFlags(x).length ? `<span class="vg-qc" title="${esc('自动质检：' + vqcFlags(x).map(vqcText).join('；'))}">${VQC_IC}</span>` : ''}<button type="button" class="vg-del" data-del title="删除" aria-label="删除">${IMG_IC.del}</button></div>`;
  const spl = g.splices.map(s => card(s, `${vidT(s.created)} · ${Math.round(s.duration || s.seconds || 0)} 秒<small>${(s.spliced_ids || []).map(id => { const v = vgSlotOf(g, id); return v ? `片段${v[0] + 1}·第${v[1] + 1}版` : ''; }).filter(Boolean).join(' ')}</small>`, s === ctx && g.splices.length > 1 ? '<span class="vg-used">当前</span>' : '')).join('');
  const slots = g.slots.map((s, i) => `<div class="vg-sec vg-slot${o.slot === s.k ? ' focus' : ''}" data-k="${esc(s.k)}"><div class="vg-h"><b>片段 ${i + 1}</b><span class="tiny">${s.start.toFixed(1)} – ${(s.start + s.len).toFixed(1)} 秒 · ${s.vers.length} 个版本</span><span class="spacer"></span>`
    + `${s.vers.length > 1 ? `<button type="button" class="pl-ib vg-cmp" data-k="${esc(s.k)}" title="并排同步播放这一段的各个版本" aria-label="并排对比各版本">${VGC_IC}</button>` : ''}`
    + `${s.vers.some(v => v.redo) ? `<button type="button" class="btn small vg-redo" data-k="${esc(s.k)}" title="${VID_REDO_TIP}">${TL_IC.redo}重新生成</button>` : ''}</div>`
    // 事后处理出来的那条写“第 N 版 · 调色”（N = 从哪一版处理来的），不当成新生成的一版（2026-11-10）
    + `<div class="vg-row">${s.vers.map((v, k) => { const b = v.upscaled_of ? s.vers.findIndex(y => y.id === v.upscaled_of) : -1;
      return card(v, `${vidPostL(v) ? (b >= 0 ? `第 ${b + 1} 版 · ` : '') + esc(vidPostS(v)) : `第 ${k + 1} 版`}<small>${vidT(v.created)}</small>`, used.has(v.id) ? '<span class="vg-used">已拼接</span>'
      : ctx ? `<button type="button" class="btn small vg-swap" data-id="${esc(v.id)}" data-k="${esc(s.k)}" title="用这一版替换拼接视频里的这一段，拼成一个新的完整视频（原来的保留）">换上</button>` : ''); }).reverse().join('')}</div></div>`).join('');
  const p = document.createElement('div'); p.className = 'vg-pop'; p.dataset.grp = grp; p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', '同一个原视频的所有版本');
  p.innerHTML = `<div class="vg-top">${VG_IC}<b>同一个原视频</b><span class="tiny">${g.splices.length} 个拼接视频 · ${g.parts.length} 个片段</span><span class="spacer"></span><button type="button" class="pl-ib vg-x" aria-label="关闭">${ICON.x || '×'}</button></div>`
    + (spl ? `<div class="vg-sec"><div class="vg-h"><b>拼接视频</b></div><div class="vg-row">${spl}</div></div>` : '') + slots
    + (g.other.length ? `<div class="vg-sec"><div class="vg-h"><b>其他</b><span class="tiny">修剪等</span></div><div class="vg-row">${g.other.map(x => card(x, `${vidT(x.created)} · ${x.seconds} 秒`)).join('')}</div></div>` : '');
  document.body.append(p); VG_POP = p;
  // 位置：手机贴底；电脑在这一格的上方（放不下就下方），左右对着这一格
  const W = innerWidth, H = innerHeight, phone = W < 700;
  if (phone) p.classList.add('sheet');
  else { const pw = p.offsetWidth, ph = p.offsetHeight, up = r0.top - 10 >= ph || r0.top > H - r0.bottom;
    p.style.left = Math.round(Math.max(10, Math.min(W - pw - 10, r0.left + r0.width / 2 - pw / 2))) + 'px';
    p.style.top = Math.round(up ? Math.max(10, r0.top - ph - 8) : Math.min(H - ph - 10, r0.bottom + 8)) + 'px'; }
  p.querySelector('.vg-slot.focus')?.scrollIntoView({ block: 'nearest' });
  if (!reduceMotion && !o.noAnim) { const b = p.getBoundingClientRect(), s = Math.max(.2, Math.min(1, r0.width / b.width));  // 从这一格放大出来（FLIP）
    p.animate([{ transform: `translate(${r0.left + r0.width / 2 - (b.left + b.width / 2)}px, ${r0.top + r0.height / 2 - (b.top + b.height / 2)}px) scale(${s})`, opacity: 0 }, { transform: 'none', opacity: 1 }], { duration: 220, easing: 'cubic-bezier(.2, .8, .2, 1)' }); }
  const open = x => { vgPopClose(); if (o.open) return o.open(x); const strip = $('#vd-gal'); if (strip && matchMedia('(min-width: 1200px)').matches) vidStage(x, true, videoAutoplay()); else vidView(x, videoAutoplay()); };
  const reopen = async () => { await vidGallery(); const a = document.querySelector(`[data-grp="${CSS.escape(grp)}"]`) || (anchor.isConnected ? anchor : null); if (a && vgBuild().get(grp)) vgPop(a, grp, { ...o, noAnim: true }); };
  p.onclick = async e => {
    const b = e.target.closest('button'), it = e.target.closest('.vg-it');
    if (b?.classList.contains('vg-x')) return vgPopClose();
    if (b?.hasAttribute('data-del') && it) { if (!await confirmBox('删除此视频？', '删除后无法恢复。', '删除', true)) return;
      try { await api('/api/video/gallery/delete', { body: { ids: [it.dataset.id] } }); if (vidStage.cur === it.dataset.id) vidStage.cur = null; toast('已删除'); reopen(); } catch (er) { toast(er.message, true); } return; }
    if (b?.classList.contains('vg-cmp')) { const s = g.slots.find(z => z.k === b.dataset.k); if (s) { vgPopClose(true); vgCompare(g, s, ctx, open); } return; }
    if (b?.classList.contains('vg-redo')) { const s = g.slots.find(z => z.k === b.dataset.k), v = s && [...s.vers].reverse().find(z => z.redo); if (v) { vgPopClose(true); vidRedo(v); } return; }  // 先关面板：提示词框在它上面
    if (b?.classList.contains('vg-swap') && ctx) { const s = g.slots.find(z => z.k === b.dataset.k), ids = (ctx.spliced_ids || []).map(id => s?.vers.some(v => v.id === id) ? b.dataset.id : id);
      if (!ids.includes(b.dataset.id)) ids.push(b.dataset.id);
      const same = g.splices.find(s => (s.spliced_ids || []).length === ids.length && ids.every(id => s.spliced_ids.includes(id)));  // 已经有用这几个版本拼好的：直接打开，不再拼出一个一模一样的
      if (same) { toast('已有用这几个版本拼好的视频，直接打开'); return open(same); }
      b.disabled = true; b.textContent = '拼接中…';
      try { const r = await api('/api/video/splice', { body: { id: ids[0], ids } }); toast('已用新版本重新拼接（原来的保留）'); vgPopClose(true); await vidGallery(); const n = vidGal.find(y => y.id === r.id); if (n) open(n); } catch (er) { toast(er.message, true); b.disabled = false; b.textContent = '换上'; } return; }
    if (it && !b) { const x = vidGal.find(y => y.id === it.dataset.id); if (x) open(x); }
  };
  p.onkeydown = e => { const it = e.target.closest('.vg-it'); if (it && e.target === it && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); it.click(); } };
  // 关：点外面 / Esc；鼠标停留打开的：移开这一格和面板 0.35 秒后关
  const out = e => { if (!p.contains(e.target) && !anchor.contains(e.target)) vgPopClose(); }, esc_ = e => { if (e.key === 'Escape') { e.stopPropagation(); vgPopClose(); } };
  setTimeout(() => document.addEventListener('pointerdown', out, true)); document.addEventListener('keydown', esc_, true);
  let hov = o.hover, lv = null;
  const enter = () => clearTimeout(lv), leave = () => { if (hov) { clearTimeout(lv); lv = setTimeout(() => vgPopClose(), 350); } };
  p.addEventListener('pointerenter', enter); p.addEventListener('pointerleave', leave); anchor.addEventListener('pointerleave', leave); anchor.addEventListener('pointerenter', enter);
  p.addEventListener('pointerdown', () => { hov = false; clearTimeout(lv); });  // 在面板里点过：不再因为鼠标移开而关
  p._off = () => { document.removeEventListener('pointerdown', out, true); document.removeEventListener('keydown', esc_, true); anchor.removeEventListener('pointerleave', leave); anchor.removeEventListener('pointerenter', enter); clearTimeout(lv); };
}
/* 并排对比（2026-11-06 用户）：同一段的几个版本（最多最新 4 个）+ 原视频这一段，一起同步播放、一根进度条；默认静音，点某一格的喇叭只听它。
   每格下面“换上”（有拼接视频时）/“打开”。在组面板的段标题上点小图标打开，主界面不加按钮 */
const VGC_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="3" y="5" width="8" height="14" rx="2"/><rect x="13" y="5" width="8" height="14" rx="2"/></svg>';
const VGC_SND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/></svg>';
function vgCompare(g, slot, ctx, open) {
  const vers = slot.vers.map((v, k) => ({ v, k })).slice(-4).reverse();  // 最新的在前
  const src = vers.map(x => x.v).find(v => v.src_file);
  const cells = [...(src ? [{ url: vidPlay(src.src_file), lab: '原视频', src: true }] : []), ...vers.map(({ v, k }) => ({ url: vidPlay(v.file), lab: `第 ${k + 1} 版`, v }))];
  const used = new Set(ctx?.spliced_ids || []);
  const box = modal(`<div class="row between vgc-top"><h3 class="card-title" style="margin:0">片段对比<span class="tiny">　${slot.start.toFixed(1)} – ${(slot.start + slot.len).toFixed(1)} 秒</span></h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="vgc-grid n${cells.length}">${cells.map((c, i) => `<div class="vgc-c${c.src ? ' src' : ''}" data-i="${i}"><video src="${esc(c.url)}" muted playsinline preload="auto"></video>
      <div class="vgc-b"><b>${c.lab}</b>${c.v && vqcFlags(c.v).length ? `<span class="vgc-qc" title="${esc('自动质检：' + vqcFlags(c.v).map(vqcText).join('；'))}">${VQC_IC}</span>` : ''}<span class="spacer"></span>
      <button type="button" class="pl-ib vgc-snd" data-i="${i}" title="只听这一格" aria-label="只听这一格" aria-pressed="false">${VGC_SND}</button>
      ${c.v ? (used.has(c.v.id) ? '<span class="vgc-used">已拼接</span>' : ctx ? `<button type="button" class="btn small vg-swap" data-id="${esc(c.v.id)}">换上</button>` : `<button type="button" class="btn small vgc-open" data-id="${esc(c.v.id)}">打开</button>`) : ''}</div></div>`).join('')}</div>
    <div class="vgc-ctl"><button type="button" class="vseg-play vgc-play" aria-label="播放">${VID_IC.play}</button><input type="range" class="vgc-seek" min="0" max="1000" value="0" aria-label="进度"><span class="tiny vgc-t">0.0 秒</span></div>`, null, true);
  box.classList.add('vgc');
  document.querySelectorAll('video').forEach(v => { if (!box.contains(v)) v.pause(); });  // 页面上别的视频（大画面自动预览）先停：只看这几格
  const V = $$('video', box), M = V[0], pb = $('.vgc-play', box), sk = $('.vgc-seek', box), tt = $('.vgc-t', box);
  const dur = () => Math.max(0.1, ...V.map(v => v.duration || 0).filter(Boolean));
  const setPlay = on => { pb.innerHTML = on ? VID_IC.pause : VID_IC.play; pb.setAttribute('aria-label', on ? '暂停' : '播放'); };
  const all = f => V.forEach(f);
  pb.onclick = () => { if (M.paused) { const t = M.currentTime; all(v => { v.currentTime = t; v.play().catch(() => { }); }); setPlay(true); } else { all(v => v.pause()); setPlay(false); } };
  sk.oninput = () => { const t = sk.value / 1000 * dur(); all(v => { v.currentTime = Math.min(t, Math.max(0, (v.duration || t) - 0.02)); }); tt.textContent = t.toFixed(1) + ' 秒'; };
  let raf = 0; const tick = () => { if (!box.isConnected) return; const t = M.currentTime;
    V.slice(1).forEach(v => { if (!M.paused && !v.paused && Math.abs(v.currentTime - t) > 0.08 && t < (v.duration || 0)) v.currentTime = t; });  // 跟着第一格走
    if (document.activeElement !== sk) sk.value = Math.round(t / dur() * 1000); tt.textContent = t.toFixed(1) + ' 秒'; raf = requestAnimationFrame(tick); };
  raf = requestAnimationFrame(tick);
  M.onended = () => { all(v => v.pause()); setPlay(false); };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.classList.contains('vgc-snd')) { const i = +b.dataset.i, on = V[i].muted; V.forEach((v, j) => { v.muted = !(on && j === i); }); box.querySelectorAll('.vgc-snd').forEach((x, j) => { x.classList.toggle('on', on && j === i); x.setAttribute('aria-pressed', String(on && j === i)); }); return; }
    if (b.classList.contains('vgc-open')) { const x = vidGal.find(y => y.id === b.dataset.id); box.close(); if (x) open(x); return; }
    if (b.classList.contains('vg-swap') && ctx) { const ids = (ctx.spliced_ids || []).map(id => slot.vers.some(v => v.id === id) ? b.dataset.id : id);
      if (!ids.includes(b.dataset.id)) ids.push(b.dataset.id);
      const same = g.splices.find(s => (s.spliced_ids || []).length === ids.length && ids.every(id => s.spliced_ids.includes(id)));
      box.close(); if (same) { toast('已有用这几个版本拼好的视频，直接打开'); return open(same); }
      try { const r = await api('/api/video/splice', { body: { id: ids[0], ids } }); toast('已用这一版重新拼接（原来的保留）'); await vidGallery(); const n = vidGal.find(y => y.id === r.id); if (n) open(n); } catch (er) { toast(er.message, true); } }
  };
  const close0 = box.close; box.close = (...a) => { cancelAnimationFrame(raf); all(v => { v.pause(); v.removeAttribute('src'); v.load(); }); return close0.apply(box, a); };
  box.querySelectorAll('[data-close]').forEach(b => { b.onclick = () => box.close(); });  // modal() 绑的是原来的 close：换成会先停掉视频的
}
/* 缩略图里的叠放格子：点一下才展开（2026-11-07 用户：鼠标停一会就自己弹出来很烦，以前停 0.45 秒会展开） */
function vgBind(box, sel) { }
/* 拼好的视频：大画面下面一条分段条（哪几段是生成的、各是第几版；有更新的版本时亮一个点），点某一段打开组面板并停在那一段 */
function vgSegBar(st, x) {
  const v = $('video', st), T = +x.duration || +x.seconds || 0; if (!T || !x.spliced_rng?.length) return;
  vgBuild(); const g = x.grp ? vgBuild.m.get(x.grp) : null;
  const bar = document.createElement('div'); bar.className = 'vd-segbar'; bar.setAttribute('aria-label', '分段');
  bar.innerHTML = x.spliced_rng.map(([a, b], i) => { const id = (x.spliced_ids || [])[i], v2 = g && vgSlotOf(g, id), s = v2?.[2], nw = s && s.vers.some(z => (z.created || 0) > (s.vers[v2[1]].created || 0));
    return `<button type="button" class="vd-sb" data-i="${i}" style="left:${a / T * 100}%;width:${Math.max(0.5, (b - a) / T * 100)}%" title="${esc(`片段 ${v2 ? v2[0] + 1 : i + 1} · ${a.toFixed(1)} – ${b.toFixed(1)} 秒${v2 ? ` · 第 ${v2[1] + 1} 版（共 ${s.vers.length} 版）` : ''}${nw ? ' · 有更新的版本' : ''}；点击查看版本、重新生成`)}">${v2 ? v2[0] + 1 : i + 1}${v2 && s.vers.length > 1 ? `<small>v${v2[1] + 1}</small>` : ''}${nw ? '<i class="vd-sb-new"></i>' : ''}</button>`; }).join('') + '<span class="vd-sb-h"></span>';
  v.insertAdjacentElement('afterend', bar);
  const head = $('.vd-sb-h', bar), paint = () => { head.style.left = (Math.min(1, (v.currentTime || 0) / T) * 100) + '%'; };
  v.addEventListener('timeupdate', paint); v.addEventListener('seeked', paint); paint();
  bar.onclick = e => { const b = e.target.closest('.vd-sb');
    if (b) { const id = (x.spliced_ids || [])[+b.dataset.i], s = g && vgSlotOf(g, id); if (g) vgPop(b, g.grp, { slot: s?.[2].k, ctx: x }); else toast('这个拼接视频用的片段已经删掉了', true); return; }
    const r = bar.getBoundingClientRect(); v.currentTime = Math.max(0, Math.min(T - 0.05, (e.clientX - r.left) / r.width * T)); };  // 原视频的部分：跳到那里
}
async function vidGallery(cached) {
  const box = $('#vd-gal') || $('#w-vgal'); if (!box) return;
  const ALL = box.id === 'w-vgal', gen = VGEN; let G = !ALL && !!vidStage.grid;
  // 2026-11-17 用户：切到生视频页会闪一下空框——先用上次读到的马上画出来，读回来一样就不再重画（免得右边正在播的视频重来）
  let got, pre = '';
  if (cached) got = vidGal;
  else {
    if (vidGal.length && !box._pre) { box._pre = 1; pre = JSON.stringify(vidGal); vidGallery(true); }
    got = await api('/api/video/gallery').catch(e => { if (!pre) box.innerHTML = loadFail('无法读取视频库', e.message); return null; });
    if (pre && got && JSON.stringify(got) === pre) return;
  }
  if (!got || !box.isConnected || gen !== VGEN) return;
  vidGal = got;
  { const nw = vidGal[0];  // 平铺时有了这次新生成的视频：切到大画面看它
    if (G && nw && vidStage.top !== undefined && nw.id !== vidStage.top && (nw.created || 0) >= SESS_T0) { vidStage.grid = false; vidStage.src = false; vidStage.closed = false; vidStage.cur = nw.id; vidStage.top = nw.id; G = false; }
    if (!ALL && vidStage.top === undefined) vidStage.top = nw?.id || '-'; }
  // 已经拼接回原视频的那段成品（只是一小段，和拼好的完整视频重复）：默认不显示，标题栏的“拼接片段”打开才显示（2026-11-05 用户要求）
  const PCS = new Set(vidGal.filter(x => x.spliced_of).flatMap(x => [x.spliced_of, ...(x.spliced_ids || [])])), hidePcs = !S.vdPcs && PCS.size > 0;  // 作品页也一样（2026-11-07 用户）
  // 视频组：同一个原视频的都并成一格（放在组里最新那条的位置，封面是最新的拼接视频）；没分组的老片段照以前的规则隐藏
  const GR = VG_ON() ? vgBuild() : (vgBuild(), null), seenG = new Set();
  const src0 = GR ? vidGal.flatMap(x => { const g = x.grp && GR.get(x.grp); if (vgStacked(g)) { if (seenG.has(g.grp)) return []; seenG.add(g.grp); return [g.rep]; } return hidePcs && PCS.has(x.id) ? [] : [x]; })
    : hidePcs ? vidGal.filter(x => !PCS.has(x.id)) : vidGal;
  const stk = x => GR && x.grp && vgStacked(GR.get(x.grp)) ? GR.get(x.grp) : null;  // 这一格是叠放的组
  const list = ALL || G ? src0 : src0.slice(0, 60);  // 生成结果：最近 60 段；“全部视频”显示全部
  { const pb = $('#vd-pcs'); if (pb && !ALL) { const nP = vidGal.filter(x => PCS.has(x.id)).length, on = !!S.vdPcs;
    pb.hidden = !nP; pb.setAttribute('aria-pressed', String(on)); pb.setAttribute('aria-label', on ? '隐藏拼接片段' : '显示拼接片段');
    pb.dataset.tip = on ? `正在显示已拼接回原视频的生成片段（${nP} 段）；点击隐藏` : `已拼接回原视频的生成片段（${nP} 段）已隐藏；点击显示`;
    pb.onclick = () => { S.vdPcs = !S.vdPcs; persist(); vidGallery(); }; } }
  const inList = id => list.some(x => x.id === id || stk(x)?.all.some(y => y.id === id));
  if (!ALL && !G && vidStage.cur && !inList(vidStage.cur)) { const c = vidGal.find(x => x.id === vidStage.cur); if (c) list.push(stk(c) ? stk(c).rep : c); }  // 从“全部视频”里点开的较早的一段：也放进下面一排
  const n = $('#vd-n') || $('#w-vn'); if (n) n.textContent = list.length ? list.length + ' 段' : '';
  const wide = () => !ALL && matchMedia('(min-width: 1200px)').matches;
  box._jusRO?.disconnect(); box._jusRO = null;
  if (G && wide()) {  // 全部视频：右边整块平铺（同生图页关掉大图后的样子）
    vdStageClear(); box.classList.add('ig-all'); vdMason();
    box.innerHTML = list.length ? `<div class="ig-jus">${list.map((x, k) => { const g = stk(x); return `<div class="ig-ju vd-ju vd-gl${g ? ' vg-stack' : ''}" data-id="${esc(x.id)}"${g ? ` data-grp="${esc(g.grp)}"` : ''} data-ar="${x.width && x.height ? (x.width / x.height).toFixed(3) : 1.6}" tabindex="0" title="${esc(vidTip(x))}" style="animation-delay:${Math.min(k, 16) * 28}ms${x.thumb ? `;--th:url('${vidUrl(x.thumb)}')` : ''}">${x.thumb ? `<img src="${vidUrl(x.thumb)}" alt="" loading="lazy" draggable="false">` : `<span class="vd-noth">${VID_IC.film}</span>`}<button type="button" class="vd-ju-p" data-play aria-label="在这里播放" title="在这里播放">${VID_IC.play}</button><button type="button" class="gl-del" data-gdel aria-label="${g ? '删除这一组' : '删除'}" title="${g ? '删除这一组（拼接视频和所有片段）' : '删除'}">${IMG_IC.del}</button>${g ? `<button type="button" class="vg-open" data-vgo aria-label="查看这一组的所有片段" title="查看这一组的所有片段（拼接视频和每一段）">${VG_IC}</button>` : ''}<span class="gl-ring" aria-hidden="true"></span>${g || vqcBadge([x]) ? `<span class="vd-badges">${g ? vgBadge(g) : ''}${vqcBadge(g ? g.all : [x])}</span>` : ''}<span class="ig-ju-i"><b>${esc(vidShort(x))}${vidPostL(x) ? ' · ' + esc(vidPostS(x)) : ''}</b>${vidT(x.created)} · ${x.seconds} 秒${(x.loras || []).length ? ' · LoRA ' + x.loras.length : ''}</span></div>`; }).join('')}</div>`
      : `<div class="ig-empty">${VID_IC.film}<b>尚未生成过视频</b></div>`;
    if (!matchMedia('(min-width: 1200px)').matches || !box.closest('.ig-grid.b5-on')) jusLayout(box);  // 新版宽窗口：固定大小的横框（CSS 网格，2026-11-07 用户参考 Kling），不再按比例拉满一行
    const gridOpen = id => { vidStage.grid = false; vidStage.src = false; vidStage.cur = id; box.classList.remove('ig-all'); vidGallery(); };
    box.onclick = e => { const t = e.target.closest('.vd-ju'); if (!t) return;
      if (e.target.closest('[data-gdel]')) { e.stopPropagation(); return vgDelTile(t, stk(vidGal.find(y => y.id === t.dataset.id) || {})); }
      if (e.target.closest('[data-play]')) { e.stopPropagation(); return vgInlinePlay(t); }
      vgInlineStop(); if (e.target.closest('[data-vgo]')) { e.stopPropagation(); return vgPop(t, t.dataset.grp, { open: x => gridOpen(x.id) }); } gridOpen(t.dataset.id); };
    if (!box._vgB) { box._vgB = 1; vgBind(box, '.vd-ju'); vgBind(box, '.vd-tile'); }
    box.onkeydown = e => { const t = e.target.closest('.vd-ju'); if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); t.click(); } };
    box.onwheel = null; vdDualBind(); return;
  }
  box.classList.remove('ig-all');
  const tar = x => x.width && x.height ? Math.max(.75, Math.min(1.6, x.width / x.height)).toFixed(3) : 1.6;
  box.innerHTML = list.length ? list.map(x => { const g = stk(x); return `<div class="vd-tile vd-gl${g ? ' vg-stack' : ''}" data-id="${esc(x.id)}"${g ? ` data-grp="${esc(g.grp)}"` : ''} tabindex="0" title="${esc(g ? vidTip(x) + '（右下角：查看这一组的所有片段）' : vidTip(x))}" style="--tar:${tar(x)}${x.thumb ? `;--th:url('${vidUrl(x.thumb)}')` : ''}"><span class="gl-ring" aria-hidden="true"></span>
      ${x.thumb ? `<img src="${vidUrl(x.thumb)}" alt="" loading="lazy">` : `<span class="vd-noth">${VID_IC.film}</span>`}<span class="vd-play">${VID_IC.play}${VID_IC.pause}</span>
      <span class="vd-badges"><b>${esc(vidShort(x))}</b>${vidPostL(x) ? `<b class="pp">${esc(vidPostS(x))}</b>` : ''}${g ? vgBadge(g) : ''}${(x.loras || []).length ? `<b class="lo">LoRA ${x.loras.length}</b>` : ''}${x.merged ? '<b>完整版</b>' : ''}${vqcBadge(g ? g.all : [x])}</span>
      <span class="vd-meta">${vidT(x.created)} · ${x.seconds} 秒${x.audio ? ' · 有声' : ''}</span><button type="button" class="gl-del gl-sm" data-gdel aria-label="${g ? '删除这一组' : '删除'}" title="${g ? '删除这一组（拼接视频和所有片段）' : '删除'}">${IMG_IC.del}</button>${g ? `<button type="button" class="vg-open" data-vgo aria-label="查看这一组的所有片段" title="查看这一组的所有片段（拼接视频和每一段）">${VG_IC}</button>` : ''}</div>`; }).join('')
    : ALL || !vidGal.length ? `<div class="ig-empty">${VID_IC.film}<b>尚未生成过视频</b></div>` : '';  // 手机 / 窄窗口一个都没有时也写一句（以前是空白的一块）
  if (!box._vgB) { box._vgB = 1; vgBind(box, '.vd-tile'); vgBind(box, '.vd-ju'); }
  // 宽窗口：右边上方直接播放（默认最新一段），点下面的缩略图换着看；窄窗口 / 作品页：点开弹窗
  if (!ALL) { vidStage((vidStage.cur && inList(vidStage.cur) && vidGal.find(x => x.id === vidStage.cur)) || list[0]); tlSync(); tlPaint(); vdMason(); }
  box.onclick = async e => {
    const t = e.target.closest('.vd-tile'); if (!t) return;
    if (e.target.closest('[data-gdel]')) { e.stopPropagation(); return vgDelTile(t, stk(vidGal.find(y => y.id === t.dataset.id) || {})); }
    if (e.target.closest('[data-vgo]')) { e.stopPropagation(); return vgPop(t, t.dataset.grp); }  // 一摞：右下角的图标才展开这一组；点别处直接播放（2026-11-07 用户）
    if (e.target.closest('[data-del]')) {
      if (!await confirmBox('删除此视频？', '删除后无法恢复。', '删除', true)) return;
      try { await api('/api/video/gallery/delete', { body: { ids: [t.dataset.id] } }); toast('已删除'); vidGallery(); } catch (er) { toast(er.message, true); }
      return;
    }
    const x = vidGal.find(y => y.id === t.dataset.id), sv = $('#vd-stage video'), st0 = $('#vd-stage');
    // 对比页：点正在对比的这一段 = 播放 / 暂停对比播放器（以前点了没反应，2026-11-05）
    if (wide() && st0?._ab?.toggle && t.dataset.id === vidStage.cur && (st0.dataset.id || '').startsWith('ab:' + t.dataset.id + '|')) return st0._ab.toggle();
    // 大预览里正在播的就是这一段：点它暂停 / 继续（播完了再点从头播）
    if (wide() && sv && t.dataset.id === vidStage.cur && $('#vd-stage').dataset.id === t.dataset.id && !sv.paused && !sv.ended) return sv.pause();
    const play = videoAutoplay() || !!e.target.closest('.vd-play');  // 关了“自动播放”：点缩略图只打开看，点上面的 ▶ 才播放（2026-11-05 用户要求）
    wide() ? vidStage(x, true, play) : vidView(x, play); };
  box.onkeydown = e => { const t = e.target.closest('.vd-tile'); if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); t.click(); } };
  // 大预览下面的缩略图是一横排（只左右滚动）：鼠标滚轮上下滚也让它左右走
  box.onwheel = ALL ? null : e => { if (box.scrollWidth <= box.clientWidth + 2 || box.scrollHeight > box.clientHeight + 2 || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    e.preventDefault(); smoothHScroll(box, e); };
}
/* 缩略图上的标注：模型、有没有 LoRA、几点生成；鼠标停留时显示完整信息 */
// 2026-11-10 用户：事后超分 / 插帧 / 调色的成品，在视频库和组面板里和原来那条一模一样——加上做了什么（短名放在缩略图上，全称在悬停提示里）
// 2026-11-11 用户：片段调色后拼接 ≠ 拼好后整段调色——拼接视频记 parts_post（用到的片段做过什么），标注写“片段调色”；整段做的照旧写“调色”
const vidPostL = x => [x.parts_post ? String(x.parts_post).split(' + ').map(t => '片段' + t).join(' + ') : '', x.upscaled_of ? (x.post_label || '后处理') : ''].filter(Boolean).join(' + ');
const vidPostS1 = t => /^AI 修复超分/.test(t) ? 'AI 超分' : /^超分/.test(t) ? '超分' : /^插帧/.test(t) ? '插帧' : /^调色/.test(t) ? '调色' : t;
const vidPostS = x => vidPostL(x).split(' + ').map(t => t.startsWith('片段') ? '片段' + vidPostS1(t.slice(2)) : vidPostS1(t)).join(' + ');
const vidPostB = x => vidPostL(x) ? `<span class="vg-post" title="${esc('后期处理：' + vidPostL(x))}">${esc(vidPostS(x))}</span>` : '';
const vidShort = x => x.edit ? '改视频' : x.model === 'h3' ? 'H3' : x.model === 'wan' ? 'Wan 2.2' : String(x.model_name || '').split(/[ ·]/)[0];  // 以前生成的 Wan 视频照样标出来
function vidT(t) {
  if (!t) return ''; const d = new Date(t * 1000), n = new Date(), p = v => String(v).padStart(2, '0'), hm = `${p(d.getHours())}:${p(d.getMinutes())}`;
  return d.toDateString() === n.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}
const vidTook = s => !s ? '' : s < 60 ? `${Math.round(s)} 秒` : `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒`;
const vidLoras = x => (x.loras || []).map(L => `${L.name.replace(/\.[^.]+$/, '')} ${L.w}${L.on && L.on !== 'both' ? (L.on === 'high' ? '（高噪）' : '（低噪）') : ''}`).join('、');
const vidMN = s => String(s || '').replace('官方完整版', '官方');  // 以前存的记录：名字也显示成“官方”
const vidTip = x => [vidMN(x.model_name), vidPostL(x) && '后期处理：' + vidPostL(x), `生成于 ${vidT(x.created)}${x.took ? ` · 用时 ${vidTook(x.took)}` : ''}`, `${x.width} × ${x.height} · ${x.seconds} 秒`, `LoRA：${vidLoras(x) || '无'}`].filter(Boolean).join(String.fromCharCode(10));
/* 改视频的成品：和原视频对比（新的有处理过的原视频 src_file：起点、帧率与成品一致；旧的退回图库里的原视频，从改视频时的起点对上） */
function vidCmpSrc(x) {
  if (!x?.edit) return null;
  if (x.src_file) return { a: vidPlay(x.src_file), off: 0 };
  // 拼接回原视频的成品是从原视频第 0 秒开始的完整视频：原视频也从 0 秒对上（以前按选段起点错开，滑动对比时两边不在同一帧，2026-11-05）
  const off = x.spliced_of ? 0 : +x.edit.start || 0, p = x.spliced_of && vidGal.find(y => y.id === x.spliced_of);
  if (p?.splice_src) return { a: vidPlay(p.splice_src), off: 0 };
  const g = x.src_vid && vidGal.find(y => y.id === x.src_vid);
  if (g) return { a: vidPlay(g.file), off };
  return VE_VID ? { a: VE_VID.url, off, cur: true } : null;  // 以前生成的、没存原视频：用左边当前放入的原视频
}
/* 改视频成品比原视频早 / 晚几帧（模型本身的错位，2026-11-05 实测 H3 早 2 帧）：对比时原视频跟着错开，滑动对比每一帧对得上。
   新成品做完后台就量好了（x.lag）；以前的第一次对比时量一次（几秒），量完自动对齐 */
const vidLagOk = (x, s) => !!(s && x?.src_file && !x.spliced_of && s.off === 0);
function vidLagP(x) { if (x.lag != null) return Promise.resolve(+x.lag || 0); return api('/api/video/lag', { body: { id: x.id } }).then(r => (x.lag = +r.lag || 0)).catch(() => 0); }
const vidCmpOff = (x, s) => { const ok = vidLagOk(x, s); return { off: (s?.off || 0) + (ok ? +x.lag || 0 : 0), offP: ok && x.lag == null ? vidLagP(x).then(l => s.off + l) : null }; };
function vidCompare(x) {
  const s = vidCmpSrc(x); if (!s) return toast('这段视频没有保存原视频：请先在左边放入原视频，再点“对比”', true);
  if (s.cur) toast('这段视频没有保存原视频，正在用左边当前放入的原视频对比');
  document.querySelectorAll('video.vd-player').forEach(v => v.pause());  // 先停掉预览，免得声音叠在一起
  abCompare({ video: true, a: s.a, ...vidCmpOff(x, s), sndKey: x.id, sndDef: vdSndDef(x), la: '原视频', b: vidPlay(x.file), lb: '生成结果', title: x.edit && typeof veTaskName === 'function' ? veTaskName(x.edit.task) : x.model_name });
}
/* 大预览正在播的那段：缩略图上不再显示 ▶（鼠标停上去显示暂停）；暂停 / 播完时显示 ▶ */
function vidTileSync() {
  const st = $('#vd-stage'), ab = st?._ab, v = $('#vd-stage video'), on = ab?.playing ? ab.playing() : !!v && !v.paused && !v.ended;  // 对比时看对比播放器
  $$('#vd-gal .vd-tile').forEach(t => { const me = on && vgTileIs(t, vidStage.cur); t.classList.toggle('playing', me);
    const p = t.querySelector('.vd-play'); if (p) p.setAttribute('aria-label', me ? '暂停' : '播放'); });
}
/* ---- 改视频 · 选段：结束点只对选它时的那个原视频有效（换了视频自动失效） ---- */
const veCut = () => { const ve = veState(); return VE_VID && +ve.end > (+ve.start || 0) && ve.segUrl === VE_VID.url ? ve : null; };
const veSecs = () => { const s = veCut(), ve = veState(); if (s) return Math.max(0.2, +(s.end - (+s.start || 0)).toFixed(3));
  if (veToEnd() && VE_VID.dur) return Math.max(0.2, +(VE_VID.dur - (+ve.start || 0)).toFixed(3));  // 选到了结尾：按真正剩下的长度（以前发的是取整后的秒数，4.9 秒变成 4 秒，2026-11-05 修）
  const left = VE_VID?.dur ? VE_VID.dur - (+ve.start || 0) : 0;  // 左栏的时长去掉了（剪辑里选）：没选结束点时按上次的长度，不超过原视频剩下的
  return left > 0 && left < vidState().eseconds ? Math.max(0.2, +left.toFixed(3)) : vidState().eseconds; };  // 发给后台的时长：选了结束点就按它（可以有小数）
const VSEG_IC = { cut: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><path d="M8.2 7.6L20 18M8.2 16.4L20 6"/></svg>',
  join: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="6" height="10" rx="1.5"/><rect x="15" y="7" width="6" height="10" rx="1.5"/><path d="M9 12h6M12.5 9.5L15 12l-2.5 2.5"/></svg>' };
/* 选段：开始 / 结束 / 拼接写进改视频的设置（左边原视频框、右边大画面、弹窗三处共用） */
const veSegR2 = x => Math.round(x * 100) / 100;
// 2026-11-10 用户：拼接始终默认打开（以前要选段后在弹窗里点“拼接”，忘了点就拼不回去）。只有手动关掉（splice === false）才不留
const veSpl = () => { const ve = veState(); return !!(VE_VID && ve.task !== 'motion' && ve.splice !== false && ((+ve.start || 0) > 0.05 || veCut())); };  // 动作迁移是另一个人、另一个场景：不拼回原视频  // 这次要不要留完整原视频（选了一段就留）
const veToEnd = () => { const ve = veState(); return !!(ve.follow && VE_VID && ve.segUrl === VE_VID.url); };  // 剪辑里选到了结尾（只对选它的那个原视频算）
const veSegAB = () => { const ve = veState(), d = VE_VID?.dur || 0, a = +ve.start || 0, c = veCut(); return [a, c ? +c.end : (veToEnd() || !d ? d : Math.min(d, a + (+vidState().eseconds || 5)))]; };
/* 一次选好几段（2026-11-05 用户要求）：当前这段照旧是 ve.start / ve.end（带把手、能拖、开始结束框改的就是它），
   另外加的几段放在 ve.segs（带原视频地址，换了原视频就不算）；点别的黄框切换到那一段，生成时每段各排一个任务，自动打开拼接 */
const veXs = () => { const ve = veState(); return VE_VID && Array.isArray(ve.segs) ? ve.segs.filter(s => s && s.url === VE_VID.url && +s.end > +s.start) : []; };
/* 原视频方块底部的小字（手机上不点开剪辑也看得出选了什么）：整段 / 2–5 秒 / 共 3 段 */
function veSrcBadge() {
  const d = VE_VID?.dur || 0; if (!d) return ''; const xs = veXs();
  if (xs.length) return `共 ${xs.length + 1} 段`;
  const [a, b] = veSegAB(), f = t => (Math.round(t * 10) / 10).toString();
  return a <= 0.05 && b >= d - 0.05 ? '整段' : `${f(a)}–${f(b)} 秒`;
}
const veAllSegs = () => { const [a, b] = veSegAB(); return [{ start: a, end: b, cur: true }, ...veXs().map(s => ({ start: +s.start, end: Math.min(+s.end, VE_VID?.dur || +s.end) }))].sort((p, q) => p.start - q.start); };
/* 添加一段（2026-11-06 用户：新的一段从白色标、也就是当前画面的位置开始）：
   白色标在空着的地方：从那里开始，长度和当前这段一样（碰到下一段或结尾就停）；白色标在某一段中间：在那里切开，后半段成为新的一段；
   白色标后面不到 1 秒：往前挪到刚好 1 秒；切开后有一边不到 1 秒：放到离白色标最近的空位 */
function veSegAdd(at) {
  const v = VE_VID, ve = veState(), d = v?.dur || 0; if (!v || !d) return toast('请先放入原视频', true);
  veSegRec();
  const [a, b] = veSegAB(), L = Math.max(1, b - a), all = [...veXs(), { url: v.url, start: veSegR2(a), end: veSegR2(b) }].sort((p, q) => p.start - q.start);
  let s0 = null, s1 = null, cut = null, near = false;
  if (Number.isFinite(at)) {
    const t = veSegR2(Math.max(0, Math.min(d, at))), hit = all.find(s => t > +s.start + 0.01 && t < +s.end - 0.01);
    if (!hit) { const nx = all.find(s => +s.start >= t - 0.01), lim = nx ? +nx.start : d, pv = Math.max(0, ...all.filter(s => +s.end <= t + 0.01).map(s => +s.end));
      if (lim - t >= 1) { s0 = t; s1 = Math.min(lim, t + L); }
      else if (lim - pv >= 1) { s0 = veSegR2(lim - 1); s1 = lim; near = true; } }  // 白色标后面不到 1 秒：尽量贴着白色标，往前挪到刚好 1 秒
    else if (t - hit.start >= 1 && hit.end - t >= 1) { cut = hit; s0 = t; s1 = +hit.end; }
  }
  const atOk = s0 != null;
  if (!atOk) {
    const gaps = []; let t = 0; for (const s of all) { if (s.start - t >= 1) gaps.push([t, s.start]); t = Math.max(t, s.end); } if (d - t >= 1) gaps.push([t, d]);
    const ph = Number.isFinite(at) ? at : null, dist = x => ph == null ? 0 : ph < x[0] ? x[0] - ph : ph > x[1] ? ph - x[1] : 0;
    const g = ph != null ? gaps.slice().sort((p, q) => dist(p) - dist(q))[0]  // 有白色标：离它最近的空位
      : gaps.find(x => x[0] >= b - 0.01) || gaps[0];  // 没有：先找当前这段后面空着的，再从头找（每段至少 1 秒）
    if (!g) return toast('原视频里已经没有空着的部分了（每段至少 1 秒）', true);
    if (ph != null && ph > g[1]) { s1 = g[1]; s0 = Math.max(g[0], g[1] - L); }  // 空位在白色标前面：贴着空位的末尾
    else { s0 = g[0]; s1 = Math.min(g[1], g[0] + L); }
  }
  if (cut) cut.end = s0;
  ve.segs = all; ve.splice = true;
  veSegSet(s0, s1 >= d - 0.05 ? null : s1);
  toast(`已添加第 ${all.length + 1} 段` + (near ? `（白色标后面不到 1 秒，从 ${s0} 秒开始）` : Number.isFinite(at) && !atOk ? '（白色标处放不下，放在了离它最近的空位）' : ''));
}
function veSegPick(k) {  // 点了另外的一段：它变成当前这段（能拖、能改开始结束），原来的那段放回去
  veSegRec(); const ve = veState(), xs = veXs(), s = xs[k]; if (!s) return; const [a, b] = veSegAB();
  ve.segs = [...xs.filter((_, i) => i !== k), { url: VE_VID.url, start: veSegR2(a), end: veSegR2(b) }];
  veSegSet(+s.start, +s.end >= (VE_VID.dur || 0) - 0.05 ? null : +s.end);
  $$('.vseg video').forEach(V => { if (V.src && V.closest('.vseg.live')) vSeek(V, +s.start); });
}
function veSegDel(k) { veSegRec(); const ve = veState(); ve.segs = veXs().filter((_, i) => i !== k); persist(); veSegSync(); }
function veSegSet(a, b) {  // b 为空或到结尾：一直到原视频结束（跟随原视频）
  const ve = veState(), st = vidState(), v = VE_VID, d = v?.dur || 0; if (!v) return;
  veSegRec();
  const xs = veXs();
  if (xs.length) {  // 不能和另外几段重叠：按新范围的中点分左右，卡在相邻那段的边上；放不下 1 秒就不改
    const be = b == null ? d : b, c = (a + be) / 2; let lo = 0, hi = d || be;
    xs.forEach(x => { if ((+x.start + +x.end) / 2 < c) lo = Math.max(lo, +x.end); else hi = Math.min(hi, +x.start); });
    const na = Math.max(a, lo), nb = Math.min(be, hi);
    if (nb - na < 1) { veSegSync(); return; }
    a = na; if (b != null || hi < d - 0.05) b = nb;
  }
  a = Math.max(0, Math.min(veSegR2(a), Math.max(0, d - 1)));
  ve.start = a; ve.segUrl = v.url;
  if (b == null || (d && b > d - 0.05)) { delete ve.end; ve.follow = true; }
  else { ve.end = veSegR2(Math.max(a + 1, b)); ve.follow = false; st.eseconds = Math.max(1, Math.round(ve.end - a)); }
  ve.splice = !(a < 0.05 && !veCut());  // 整段：没什么可拼的；选了一段：默认拼接（2026-11-10）
  persist(); veSegSync();
}
/* 剪辑：撤销 / 重做（2026-11-06 用户要求：误触了能回到上一步）。Ctrl + Z 撤销，Ctrl + Shift + Z 或 Ctrl + Y 重做。
   记的是当前这段 + 另外几段；一次连续拖动（0.6 秒内的改动）算一步 */
const VSEG_HIST = { u: [], r: [], t: 0 };
const veSegSnap = () => { const ve = veState(); return JSON.stringify({ start: ve.start ?? 0, end: ve.end ?? null, follow: !!ve.follow, segs: ve.segs || [], url: ve.segUrl || '' }); };
function veSegRec() {
  const H = VSEG_HIST, now = Date.now(), s = veSegSnap();
  if (now - H.t < 600 && H.u.length) { H.t = now; return; }
  H.t = now; if (H.u[H.u.length - 1] === s) return;
  H.u.push(s); if (H.u.length > 100) H.u.shift(); H.r = [];
}
function veSegUndo(redo) {
  const H = VSEG_HIST, from = redo ? H.r : H.u, to = redo ? H.u : H.r, s = from.pop();
  if (!s) return toast(redo ? '没有可重做的' : '没有可撤销的');
  const o = JSON.parse(s); if (VE_VID && o.url && o.url !== VE_VID.url) return toast('原视频已经换了，无法撤销');
  to.push(veSegSnap());
  const ve = veState(); ve.start = o.start; if (o.end == null) delete ve.end; else ve.end = o.end; ve.follow = o.follow; ve.segs = o.segs; if (o.url) ve.segUrl = o.url;
  H.t = 0; persist(); veSegSync();
  $$('.vseg.live video').forEach(V => { V.pause(); vSeek(V, +o.start || 0); });
}
document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const k = e.key.toLowerCase(); if (k !== 'z' && k !== 'y') return;
  if (e.target.closest?.('input, textarea, select, [contenteditable]') || document.querySelector('.modal-bg')) return;  // 输入框里是输入框自己的撤销；弹窗（修剪）有自己的
  if ($('#main')?.dataset.page !== 'video' || vidState().mode !== 'edit' || !VE_VID) return;
  e.preventDefault(); veSegUndo(k === 'y' || e.shiftKey);
});
function veSegSync() {  // 选段变了：三处的范围、文字、拼接开关、时长一起更新（不重建视频，播放位置不丢）
  $$('[data-seg-live]').forEach(r => r._segPull?.());
  if (window.vePaintOpts && vePaintOpts.multi !== (veXs().length > 0)) vePaintOpts();  // 一段 ↔ 多段：改衣选项里的“共用衣服图”跟着出现 / 消失
  const d = VE_VID?.dur || 0, [a, b] = veSegAB(), part = a > 0.05 || (d && b < d - 0.05), spl = veState().splice !== false && part;
  $$('.vseg-rng[data-live]').forEach(e => { e.style.left = d ? a / d * 100 + '%' : '0'; e.style.width = d ? (b - a) / d * 100 + '%' : '100%'; });
  $$('.ve-seg-txt').forEach(e => { e.textContent = part ? `${veSegR2(a)} – ${veSegR2(b)} 秒` : '整段'; });
  $$('.ve-spl').forEach(e => { e.hidden = !part || veState().task === 'motion'; e.classList.toggle('on', !!spl); e.setAttribute('aria-pressed', String(!!spl)); });
  $$('.vseg-in-a').forEach(e => { if (document.activeElement !== e) e.value = veSegR2(a); });
  $$('.vseg-in-b').forEach(e => { if (document.activeElement !== e) e.value = veSegR2(b); });
  $$('.vseg-len[data-live]').forEach(e => { e.innerHTML = veSegLen(a, b, true); });
  const xs = veXs();
  $$('.vseg-rng[data-live]').forEach(e => { const tr = e.parentElement; let bx = $('.vseg-xs', tr); if (!bx) { bx = document.createElement('div'); bx.className = 'vseg-xs'; e.after(bx); }
    bx.innerHTML = d ? xs.map((s, i) => `<i class="vseg-x" data-k="${i}" style="left:${s.start / d * 100}%;width:${(Math.min(s.end, d) - s.start) / d * 100}%" title="第 ${veSegR2(s.start)} – ${veSegR2(s.end)} 秒：点击切换到这一段"><button type="button" class="vseg-xd" aria-label="删除这一段" title="删除这一段">${ICON.x}</button></i>`).join('') : '';
    $$('.vseg-x', bx).forEach(x => x.onpointerdown = ev => { ev.stopPropagation(); ev.preventDefault(); if (ev.target.closest('.vseg-xd')) veSegDel(+x.dataset.k); else veSegPick(+x.dataset.k); }); });
  if (xs.length) $$('.ve-seg-txt').forEach(e => { e.textContent += ` · 共 ${xs.length + 1} 段`; });
  veCpPaint();
  renderVideo.paintSec?.(); renderVideo.vdRefresh?.();
}
/* 找换装点（2026-11-05，后台 cutpoints.py，只用 CPU）：音乐的节拍 / 重拍 + 人物动作（定格、大动作、转身），
   标记画在选段条上（点一下跳到那里），拖黄框把手时吸附过去；“推荐分段”按分高的几个点自动分好段 */
/* 2026-11-10 用户：选好段落后复制这一段开头那一帧（原分辨率），自己到生图页用 Qwen 2.1 改，再粘贴回参考图格（几段共用这一张） */
async function veCopyFrame() {
  const v = VE_VID; if (!v) return toast('请先放入原视频', true);
  const t = Math.max(0, veSegAB()[0] || 0);
  const shot = new Promise((ok, no) => {
    const el = document.createElement('video'), fail = () => no(new Error('无法读取这一帧'));
    el.muted = true; el.playsInline = true; el.preload = 'auto'; el.onerror = fail;
    el.onloadeddata = () => {
      el.onseeked = () => { try { const c = document.createElement('canvas'); c.width = el.videoWidth; c.height = el.videoHeight; c.getContext('2d').drawImage(el, 0, 0);
        c.toBlob(b => { el.removeAttribute('src'); el.load(); b ? ok(b) : fail(); }, 'image/png'); } catch (e) { no(e); } };
      el.currentTime = Math.min(t + 0.001, Math.max(0, (el.duration || t + 1) - 0.05)); };
    el.src = v.url;
  });
  try {
    if (!window.ClipboardItem || !navigator.clipboard?.write) throw new Error('no clipboard');
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': shot })]);  // 直接给 Promise：读帧的这段时间不算离开了这次点击
    toast(`已复制第 ${t.toFixed(1)} 秒的画面`);
  } catch {
    try { const b = await shot, a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `首帧_${t.toFixed(1)}秒.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000); toast('无法写入剪贴板，已改为下载这一帧'); }
    catch (e) { toast(e.message || '无法读取这一帧', true); }
  }
}
document.addEventListener('click', e => { if (e.target.closest?.('.ve-ff')) veCopyFrame(); if (e.target.closest?.('.ve-ffs') && VE_VID && typeof frGrab === 'function') frGrab(matsVidRef(VE_VID) || { local: VE_VID.url, name: VE_VID.name || '原视频', dur: VE_VID.dur }, Math.max(0, veSegAB()[0] || 0)); });  // 存进素材库：这一段开头那一帧（2026-11-19）
let VE_CP = null;
const VCP_K = { beat: '卡点', hit: '定格', swing: '大动作', turn: '转身' };  // beat（2026-11-10）：只有音乐的重音 / 段落变化
const veCpOk = () => !!(VE_CP && VE_VID && VE_CP.url === VE_VID.url && !VE_CP.busy && VE_CP.points && VE_CP.shown);
/* 后台提前分析：放入视频库 / 素材库里的原视频就开始算（不用上传，只用 CPU 的几个线程），点“找换装点”时直接显示；电脑上传的点了才算 */
function veCpAuto() {
  const v = VE_VID; if (!v || S.vdCpAuto === false || !matsVidRef(v) || (VE_CP && VE_CP.url === v.url)) return;
  veCpFind(true);
}
async function veCpFind(bg) {
  const v = VE_VID; if (!v) return toast('请先放入原视频', true);
  if (VE_CP && VE_CP.url === v.url && (VE_CP.busy || VE_CP.points)) { if (!bg) { VE_CP.shown = true; veCpPaint(); veCpNone();  // 后台已经在算 / 算好了：直接显示
      if (VE_CP.busy && matsVidRef(v)) api('/api/video/cutpoints', { body: { video: matsVidRef(v), hurry: true } }).catch(() => { }); } return; }  // 还在算：让它换成全速
  VE_CP = { url: v.url, busy: true, shown: !bg }; veCpPaint();
  try {
    const video = matsVidRef(v) || { data: await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(new Error('无法读取该视频文件')); r.readAsDataURL(v.file); }) };
    const r = await api('/api/video/cutpoints', { body: { video, bg: !!bg } });  // 后台提前分析只用几个线程；点了按钮用全速
    if (VE_VID?.url !== v.url) return;
    const shown = !!VE_CP?.shown; VE_CP = { url: v.url, ...r, shown };
    veCpNone();
  } catch (e) { const shown = !!VE_CP?.shown; if (VE_CP?.url === v.url) VE_CP = { url: v.url, err: e.message }; if (shown) toast(e.message, true); }
  veCpPaint();
}
function veCpNone() { if (VE_CP?.shown && VE_CP.points && !VE_CP.points.length) toast('没有找到明显的换装点', true); }
const veCpSnap = (tr, d) => { if (!veCpOk() || S.vdSnap === false || !d) return t => t; const thr = 10 / (tr.clientWidth || 600) * d;  // 10 像素以内
  return t => { let best = t, bd = thr; VE_CP.points.forEach(p => { const x = Math.abs(p.t - t); if (x < bd) { bd = x; best = p.t; } }); return best; }; };
/* 推荐分段（2026-11-10 用户：以前把整段首尾相连切满，和平时的用法不一样）：挑出几段，每段的开头、结尾都卡在点上——
   音乐重音（卡点）或定格 / 大动作，两者都卡上的优先，落在重拍（每小节第一拍）上的再优先；每段 2.5–8 秒（4.5 秒左右最好）；
   段与段之间至少隔 1.2 秒；视频结尾也可以当一段的结尾。段数大约每 5 秒一段，最多 6 段。
   （用户 @十一酱 那段自己选的是 0.8–5.3 / 6.9–10.8 / 13.0–结尾；这样推荐 0.73–5.10 / 6.87–10.37 / 12.13–结尾，时间上重合 86%。
    先前一版按另一段视频猜的“开头先留原视频、9 秒一段”只有 43%，已去掉） */
/* 2026-11-14：分段改在后台算（segpref.split，同一套规则）：用户有了足够多的选段记录、而且按记录学出来的更贴近用户时，用学出来的偏好；
   只有电脑上传、不在素材库 / 视频库里的视频还在这里按规则算 */
async function veCpSplit() {
  if (!veCpOk()) return; const ref = matsVidRef(VE_VID);
  if (!ref) return veCpSplitRule();
  const url = VE_VID.url; let r;
  try { r = await api('/api/video/cutpoints/split', { body: { video: ref, dur: VE_VID.dur || VE_CP.dur || 0 } }); } catch (e) { return toast(e.message, true); }
  if (VE_VID?.url !== url) return;
  const d = VE_VID.dur || VE_CP.dur || 0, pick = (r.segs || []).map(([a, b]) => ({ a, b }));
  veCpApply(pick, d, r.by === 'learned' ? `已按你以前 ${r.videos} 个视频的选段推荐 ${pick.length} 段` : '');
}
function veCpApply(pick, d, msg) {
  if (!pick.length) return toast('没有足够明显的换装点可以分段', true);
  veSegRec(); VE_CP.rec = pick.map(x => [x.a, Math.min(d, x.b)]);  // 记下推荐的：提交时和用户最后的选段一起记（segpref）
  const ve = veState();
  ve.segs = pick.slice(1).map(x => ({ url: VE_VID.url, start: veSegR2(x.a), end: veSegR2(Math.min(d, x.b)) })); ve.splice = true;
  veSegSet(pick[0].a, pick[0].b >= d - 0.05 ? null : pick[0].b);
  toast(msg || `已推荐 ${pick.length} 段：开头和结尾都卡在音乐或动作上，其余保持原视频`);
}
function veCpSplitRule() {
  const d = VE_VID.dur || VE_CP.dur || 0;
  const P = VE_CP.points.filter(p => p.t >= 0.5 && p.t <= d - 0.3).map(p => ({ t: p.t, s: p.score + (p.sync ? 0.1 : 0) + (p.db ? 0.35 : 0) }));
  if (d > 3) P.push({ t: d, s: 1.3, end: true });  // 换到视频结尾：只有开头一个接缝，和卡在重拍上的点一样好
  const C = [];  // 候选段：开头、结尾都是点；5 秒左右最好，太短 / 太长扣分
  P.forEach(a => { if (a.end) return; P.forEach(b => { const L = b.t - a.t; if (L < 2.5 || L > 8) return; C.push({ a: a.t, b: b.t, s: a.s + b.s + 0.4 * (1 - Math.min(1, Math.abs(L - 4.5) / 3)) }); }); });
  const N = Math.max(1, Math.min(6, Math.round(d / 5)));
  // 几段加起来最好（以前一段一段挑最好的，先挑走的那段常把别的位置挤成很短的一段）：按开头排序，f[k][i] = 以第 i 个候选结尾、共 k 段的最好总分
  C.sort((x, y) => x.a - y.a);
  const f = [C.map(c => c.s)], bk = [C.map(() => -1)];
  for (let k = 1; k < N; k++) { f[k] = []; bk[k] = [];
    C.forEach((c, i) => { let best = -Infinity, bi = -1; for (let j = 0; j < C.length; j++) if (C[j].b + 1.2 <= c.a && f[k - 1][j] > best) { best = f[k - 1][j]; bi = j; } f[k][i] = bi < 0 ? -Infinity : best + c.s; bk[k][i] = bi; }); }
  let pick = [];
  for (let k = N - 1; k >= 0 && !pick.length; k--) { let i = f[k].reduce((m, v, j, A) => v > (A[m] ?? -Infinity) ? j : m, -1); if (i < 0 || !isFinite(f[k][i])) continue;
    for (let q = k; q >= 0 && i >= 0; q--) { pick.unshift(C[i]); i = bk[q][i]; } }  // 放不下 N 段时少分几段
  veCpApply(pick, d);
}
function veCpPaint() {
  veCpAuto();
  const ok = veCpOk(), busy = !!(VE_CP?.busy && VE_CP.shown && VE_VID && VE_CP.url === VE_VID.url), d = VE_VID?.dur || VE_CP?.dur || 0, key = ok ? VE_CP.url + '|' + VE_CP.took + '|' + d : '';
  $$('.vseg-rng').forEach(e => { const tr = e.parentElement; let bx = $('.vseg-cps', tr);
    if (!ok) { bx?.remove(); return; }
    if (bx && bx.dataset.k === key) return;
    if (!bx) { bx = document.createElement('div'); bx.className = 'vseg-cps'; tr.insertBefore(bx, $('.vseg-head', tr)); }
    bx.dataset.k = key; const db = new Set(VE_CP.downbeats.map(t => t.toFixed(3)));
    bx.innerHTML = (VE_CP.beats.length <= 600 ? VE_CP.beats.map(t => `<i class="vbt${db.has(t.toFixed(3)) ? ' d' : ''}" style="left:${t / d * 100}%"></i>`).join('') : '')
      + VE_CP.points.map((p, i) => `<i class="vcp k-${p.kind}${p.sync ? ' sync' : ''}" data-i="${i}" style="left:${p.t / d * 100}%;height:${Math.round(8 + 12 * p.score)}px" title="${esc(`${p.t.toFixed(2)} 秒 · ${VCP_K[p.kind]}：${p.why.join('、')} · 推荐度 ${Math.round(p.score * 100)}`)}"></i>`).join('');
    $$('.vcp', bx).forEach(m => m.onpointerdown = ev => { ev.stopPropagation(); ev.preventDefault(); const t = VE_CP.points[+m.dataset.i]?.t; if (t == null) return;
      (tr.closest('.vseg.live') ? $$('.vseg.live video') : $$('video', tr.closest('.vseg, #ve-src') || tr)).forEach(V => { V.pause(); vSeek(V, t); }); }); });
  $$('.vseg-cp').forEach(e => {
    // 横屏原视频（2026-11-06 用户：不要多出两行）：图例放进“开始…结束”那一行的最左边、两个按钮放最右边；其他排法照旧在下面一行
    const root = e.closest('.vseg'), land = !!root?.matches('.st.land'), sl = land ? $('.vcp-slot.l', root) : null, sr = land ? $('.vcp-slot.r', root) : null;
    const put = (leg, btns) => { if (sl && sr) { e.hidden = true; e.innerHTML = ''; sl.innerHTML = leg; sr.innerHTML = btns; } else { e.hidden = false; e.innerHTML = leg + btns; } };
    if (sl && sr) sl.innerHTML = sr.innerHTML = '';
    if (busy) return put('<div class="vcp-leg"><span class="vcp-busy"></span>分析中…</div>', '');
    if (!ok) { e.hidden = true; e.innerHTML = ''; return; }
    const n = k => VE_CP.points.filter(p => p.kind === k).length, on = S.vdSnap !== false;
    const tip = '适合换装 / 拼接的时间点，标在选段条上，越高越推荐；点一下跳到那里；动作和音乐都卡上的带白边（最推荐）<br><b style="color:#0a84ff">卡点</b>：音乐重音、段落变化（鼓点进来 / 突然安静）<br><b style="color:#34c759">定格</b>：一个动作刚做完、停住<br><b style="color:#ff9f0a">大动作</b>：动作最猛的一下<br><b style="color:#bf5af2">转身</b>：背对镜头'
      + (VE_CP.bpm ? '<br>上方白色刻度是节拍，长的是重拍' : '<br>这段视频没有音乐，只按动作找') + (VE_CP.by === 'pose' ? '' : '<br>找不到人体姿势模型，按画面变化估算');
    put(`<div class="vcp-leg">${Object.keys(VCP_K).map(k => `<span><i class="vcp-dot k-${k}"></i>${VCP_K[k]} ${n(k)}</span>`).join('')}${VE_CP.bpm ? `<span class="tiny">${VE_CP.bpm} BPM</span>` : ''}${hintHtml(tip)}</div>`,
      `<div class="vcp-btns">${VE_CP.points.length ? `<button type="button" class="btn small vcp-split" title="挑出几段要换的（大约每 5 秒一段）：每段的开头、结尾都卡在音乐重音或定格 / 大动作上（两者都卡上的优先），每段 2.5–8 秒，其余保持原视频；推荐完可以再拖动调整">推荐分段</button>` : ''}<button type="button" class="chip vcp-snap${on ? ' on' : ''}" aria-pressed="${on}" title="拖动黄色框的把手时，靠近换装点就吸过去">吸附</button></div>`);
    const box = sl && sr ? root : e, sp = $('.vcp-split', box); if (sp) sp.onclick = async () => { await veCpSplit(); e.closest('.vseg-host')?._segPull?.(); };
    $('.vcp-snap', box).onclick = () => { S.vdSnap = S.vdSnap === false; persist(); veCpPaint(); };
  });
}
const veSegLen = (a, b, live) => { const HS = VIDST?.edit?.hard_seconds || {}, hard = veVg() ? 14 : HS.h3 || 150, len = b - a;  // Viggle 重拍：节点最多 345 帧（后台 videoedit.max_seconds）
  const all = live && veXs().length ? veAllSegs() : null, ovl = !!all && all.some((x, i) => i && x.start < all[i - 1].end - 0.05);
  const tip = ['生成的正好是这一段，每一帧都重新生成', all ? `共 ${all.length} 段：每段各生成一个视频，之后可以一起拼接回原视频` : '', `此做法最长 ${hard} 秒`].filter(Boolean).join('<br>');
  const main = all ? `共 ${all.reduce((t, x) => t + x.end - x.start, 0).toFixed(2)} 秒 · ${all.map((x, i) => `<${x.cur ? 'b' : 'span'}>片段${i + 1} ${(x.end - x.start).toFixed(2)} 秒</${x.cur ? 'b' : 'span'}>`).join(' · ')}`  // 多段：总时长，再按时间顺序列每段（当前这段加粗）
    : `${len.toFixed(2)} 秒 · ${Math.round(Math.min(len, hard) * 24)} 帧`;
  return `<span data-tip="${esc(tip)}">${main}</span>`
    + (len > hard ? `<span class="vseg-warn">超过上限：只生成前 ${hard} 秒</span>` : (() => { const VS = VIDST?.edit || {}, rec = veRef() ? VS.max_seconds_ref || 15 : VS.max_seconds || 10, segs = all || [{ start: a, end: b }];
        return segs.some(x => x.end - x.start > rec + 0.05) ? `<span class="vseg-warn" data-tip="${esc(veRef() ? '参考生成建议不超过 15 秒（H3 官方建议参考视频 2~15 秒）；更长会更慢，也更容易走样。' : '换人 / 换头 LoRA 在 4~5 秒的连续镜头最稳，超过 10 秒容易走样；更长也更慢。')}">超过建议的 ${rec} 秒</span>` : ''; })()) + (ovl ? '<span class="vseg-warn">片段有重叠</span>' : ''); };  // 说明放在长度文字的鼠标停留提示里（2026-11-06 用户：不要问号）  // H3：先生成稍长的一段再按帧裁（videoedit.exact_trim）
const VSEG_SPL_TIP = '默认打开：保留一份完整的原视频，生成后在成品上点“拼接回原视频”，用这一段替换原视频中对应的部分，得到完整的视频（可多生成几次，挑满意的那次拼接）';
/* 拖动条：track 上按住拖 = 跳到那里（视频暂停）；playhead 跟着视频走 */
/* 选段条：按住拖 = 跳到那里（画面实时跟着，视频暂停）；拖黄色框两头的把手 = 改开始 / 结束（o.onRange）；o.film：底下铺这段视频的画面 */
function veTrack(tr, V, getD, o = {}) {
  let drag = null, tgt = null;
  if (tr.classList.contains('vtrim') && !tr.querySelector(':scope > .vtrim-in')) {  // 时间 0 ~ 结尾对应里面这一层（左右留出把手的宽度）
    const inn = document.createElement('div'); inn.className = 'vtrim-in';
    while (tr.firstChild) inn.appendChild(tr.firstChild);
    tr.appendChild(inn);
  }
  const box = () => (tr.querySelector(':scope > .vtrim-in') || tr);
  const tAt = e => { const r = box().getBoundingClientRect(), d = getD(); return d ? Math.max(0, Math.min(d - 0.001, (e.clientX - r.left) / r.width * d)) : 0; };
  const head = $('.vseg-head', tr);
  const paint = () => { const d = getD(); if (head && d) head.style.left = ((tgt ?? V.currentTime) / d * 100) + '%'; };
  const move = e => { const t = tAt(e);
    if (drag !== 's' && o.onRange) { const [a, b] = o.getAB(), mn = o.minLen ?? 1; if (drag === 'a') o.onRange(Math.max(0, Math.min(t, b - mn)), b); else o.onRange(a, Math.max(t, a + mn)); }  // minLen：最短多长（修剪时是一帧）
    tgt = t; paint(); vSeek(V, t); };
  tr.addEventListener('pointerdown', e => { const h = e.target.closest('.vtrim-h'); drag = h && o.onRange ? (h.classList.contains('a') ? 'a' : 'b') : 's';
    tr.classList.add('drag'); try { tr.setPointerCapture(e.pointerId); } catch { } V.pause(); move(e); e.preventDefault(); });
  tr.addEventListener('pointermove', e => { if (drag) move(e); });
  const up = () => { if (!drag) return; drag = null; tgt = null; tr.classList.remove('drag'); paint(); };
  tr.addEventListener('pointerup', up); tr.addEventListener('pointercancel', up);
  V.addEventListener('timeupdate', paint); V.addEventListener('seeked', paint); V.addEventListener('loadedmetadata', paint);
  let raf = 0; const loop = () => { if (!tr.isConnected) return; if (!V.paused) paint(); raf = requestAnimationFrame(loop); }; loop();
  if (o.film) veFilm(tr, o.film);
  return paint;
}
/* 胶片条：从视频里取几帧铺在选段条底下（同一段视频只取一次） */
const VFILM = new Map();
function veFilm(tr, url) {
  const f = $('.vtrim-film', tr); if (!f || !url) return;
  const go = () => { const W = tr.clientWidth, H = tr.clientHeight; if (!W || !H) return setTimeout(go, 300);
    const k0 = url + '|', ar0 = VFILM.get(k0 + 'ar') || (VE_VID?.url === url && VE_VID.w && VE_VID.h ? VE_VID.w / VE_VID.h : 0), k = k0 + (ar0 ? Math.max(3, Math.min(60, Math.ceil(W / (H * ar0)))) : Math.round(W / H));
    // 2026-11-08：素材库 / 视频库里的视频交给后台截（ffmpeg 只用 CPU、截好的会存起来）——以前在这里用隐藏的播放器来回跳着截，
    // 4K / HEVC 很慢，生成视频时显卡占满就一直出不来。后台失败时才退回下面的老办法
    const path = (() => { try { return new URL(url, location.href).pathname; } catch { return ''; } })();
    if (ar0 && /^\/media\/(mats|video)\//.test(path) && !VFILM.has(k)) VFILM.set(k, new Promise(res => {
      const N = Math.max(3, Math.min(60, Math.ceil(W / (H * ar0)))), src = `/api/video/film?u=${encodeURIComponent(path)}&n=${N}&h=72`, im = new Image();
      im.onload = () => res(src); im.onerror = () => { VFILM.delete(k); res(veFilmLocal(url, W, H, k0, k)); }; im.src = src; }));
    if (!VFILM.has(k)) VFILM.set(k, veFilmLocal(url, W, H, k0, k));
    VFILM.get(k).then(img => { if (img && f.isConnected) { f.style.backgroundImage = `url("${img}")`; tr.classList.add('has-film'); } });
  };
  go();
}
function veFilmLocal(url, W, H, k0, k) {  // 在浏览器里截（本地上传的视频、后台截不了时）
    return new Promise(res => {
      const v = document.createElement('video'); v.muted = true; v.preload = 'auto'; v.playsInline = true; let dead = false;
      const quit = x => { if (dead) return; dead = true; v.removeAttribute('src'); v.load(); res(x); };
      setTimeout(() => quit(null), 25000);
      v.onerror = () => quit(null);
      v.onloadedmetadata = async () => {
        const d = v.duration, ar = v.videoWidth / v.videoHeight || 1, fh = 72, fw = Math.max(16, Math.round(fh * ar)), N = Math.max(3, Math.min(60, Math.ceil(W / (H * ar)))); VFILM.set(k0 + 'ar', ar);
        const cv = document.createElement('canvas'); cv.width = fw * N; cv.height = fh; const g = cv.getContext('2d');
        try { for (let i = 0; i < N && !dead; i++) { await new Promise(r => { v.onseeked = r; v.currentTime = Math.min(d - 0.05, (i + 0.5) * d / N); }); g.drawImage(v, i * fw, 0, fw, fh); }
          quit(cv.toDataURL('image/jpeg', 0.72)); } catch { quit(null); }
      };
      v.src = url;
    });
}
/* 分辨率：生视频 / 改视频各记各的（2026-11-11 用户：改视频默认 720p；生视频照旧）。st.size 是现在这种的；st.sizes 记两种的，st._sm = st.size 属于哪种 */
function vidSizeMode() { const st = vidState(); st.sizes = st.sizes || {};
  if (!st._sm) st._sm = st.mode === 'edit' ? 'edit' : 'gen';
  const m = st.mode === 'edit' ? 'edit' : 'gen'; if (st._sm === m) return;
  st.sizes[st._sm] = st.size; st.size = st.sizes[m] || (m === 'edit' ? '720p' : st.size); st._sm = m;
  document.querySelectorAll('#vd-size [data-s]').forEach(x => x.classList.toggle('on', x.dataset.s === st.size)); const r = document.querySelector('#vd-res'); if (r) r.hidden = st.size !== 'custom'; }
/* 视频页现在放的那张图（改视频：参考图；生视频：首帧）生成时的提示词 */
function vdGp() { const E = vidState().mode === 'edit', im = E ? VE_REF : VID_SRC; let g = im?.gp;
  if (!g && im?.kind === 'gallery') g = (typeof imgGal !== 'undefined' ? imgGal : []).find(x => x.id === im.id)?.prompt; return String(g || '').trim(); }
function vdGpSync() { const b = $('#vd-gp'); if (!b) return; const g = vdGp(), ta = $('#vd-prompt');
  b.hidden = !g || !!ta && ta.value.trim() === g; b.title = g ? '填入这张图生成时用的提示词：' + (g.length > 160 ? g.slice(0, 160) + '…' : g) : ''; }
/* 剪辑里正在播放、后台还在提前找换装点：每 1.5 秒告诉后台一次，让它先停下（不和播放抢显卡 / CPU，2026-11-11 用户：剪辑里播放卡） */
function veCalm() { if (!VE_CP?.busy || VE_CP.shown) return; /* 只让打开视频时自动开始的后台分析停；点了“找换装点”（shown）就全速算，边等边看原视频也不停 */ const t = Date.now(); if (t - (veCalm.t || 0) < 1500) return; veCalm.t = t; api('/api/video/cutpoints/calm', { body: {} }).catch(() => { }); }
/* 选段组件：o.live = 直接生效（右边大画面）；否则是弹窗里的（点“应用”才生效，选了一段时问要不要拼接） */
function veSegUI(root, o = {}) {
  const v = VE_VID, ve = veState(), st = vidState(), fps = v.fps || 30, C = !!o.compact, port = !C && v.h > v.w * 1.15, L = !!o.live;
  const ST = L && !C, TRK = `<div class="vseg-track vtrim" tabindex="0" role="slider" aria-label="播放位置"><div class="vtrim-film"></div><div class="vseg-rng"${L ? ' data-live' : ''}><span class="vtrim-h a" aria-hidden="true"></span><span class="vtrim-h b" aria-hidden="true"></span></div><div class="vseg-head"></div></div>`;
  const FREE = `<button type="button" class="chip vseg-only${S.vsegFree ? '' : ' on'}" aria-pressed="${S.vsegFree ? 'false' : 'true'}" data-tip="打开：只播放选中的片段，到结尾就停。关闭：从白色标一直往后播，播到选中的片段时画面四周亮一圈黄色">只放选段</button>`;
  const TL = `<button type="button" class="btn small vseg-play" aria-label="播放">${VID_IC.play}</button>${FREE}<button type="button" class="btn small ghost" data-k="-1" title="后退 1 秒（Shift + ←）">−1 秒</button><button type="button" class="btn small ghost" data-k="-f" title="上一帧（←）">−1 帧</button><button type="button" class="btn small ghost" data-k="f" title="下一帧（→）">+1 帧</button><button type="button" class="btn small ghost" data-k="1" title="前进 1 秒（Shift + →）">+1 秒</button>`;
  if (ST) root.innerHTML = `<div class="vseg live st ${port ? 'port' : 'land'}" style="--ar:${v.w && v.h ? v.w + ' / ' + v.h : '9 / 16'}"><div class="vseg-v"><video src="${esc(v.url)}" playsinline preload="auto"></video><span class="vseg-tag">原视频</span></div>
      ${port ? '<div class="vseg-side">' : ''}<div class="vseg-trw">${TRK}</div>
      <div class="vseg-p"><div class="vseg-tw"><div class="vseg-t"></div><div class="vseg-x"><button type="button" class="pl-ib vsg-all" data-tip="选择整段视频（另外加的几段也会去掉）" aria-label="选择整段"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7v10M20 7v10M8 12h8M8 12l2.5-2.5M8 12l2.5 2.5M16 12l-2.5-2.5M16 12l-2.5 2.5"/></svg></button><button type="button" class="pl-ib ve-spl" aria-pressed="false" aria-label="拼接回原视频" data-tip="${esc('<b>拼接回原视频</b>（蓝色 = 开启）<br>' + VSEG_SPL_TIP)}">${VSEG_IC.join}</button></div></div><div class="row vseg-tl">${TL}</div>
        <div class="vseg-rows"><div class="vcp-slot l"></div><label class="vseg-row"><span>开始</span><input class="input vseg-in-a" type="number" min="0" step="0.01" aria-label="开始（秒）"><span class="tiny">秒</span><button type="button" class="btn small ghost" data-set="a" title="把当前播放位置设为开始">设为当前位置</button></label>
          <label class="vseg-row"><span>结束</span><input class="input vseg-in-b" type="number" min="0" step="0.01" aria-label="结束（秒）"><span class="tiny">秒</span><button type="button" class="btn small ghost" data-set="b" title="把当前播放位置设为结束">设为当前位置</button></label><div class="vcp-slot r"></div></div>
        <div class="row vseg-act"><button type="button" class="btn small ghost vsg-add" title="再选一段：从白色标（当前画面）开始多出一个黄色框；白色标在某一段中间时，从那里切成两段。每段各生成一个视频，之后可以一起拼接回原视频">＋ 添加一段</button><button type="button" class="btn small ghost vsg-find" title="分析音乐的节拍和人物的动作，在选段条上标出适合换装 / 拼接的时间点（只用 CPU，不占显卡）">找换装点</button><button type="button" class="btn small ghost ve-ff" title="复制这一段开头那一帧（原视频的清晰度）：到生图页粘贴为原图，用 Qwen 2.1 改好后，放回参考图格、关掉“Qwen 生成”，几段都用这一张">复制首帧</button><button type="button" class="btn small ghost ve-ffs" data-tip="把这一段开头那一帧（原画质）存进素材库">存进素材库</button></div>
        <div class="tiny vseg-len" data-live></div><div class="vseg-cp" hidden></div></div>${port ? '</div>' : ''}</div>`;
  else root.innerHTML = `<div class="vseg${port ? ' port' : ''}${L ? ' live' : ''}${C ? ' compact' : ''}" style="--ar:${v.w && v.h ? v.w + ' / ' + v.h : '9 / 16'}"><div class="vseg-v"><video src="${esc(v.url)}" playsinline preload="auto"></video><span class="vseg-tag">原视频</span></div>
      <div class="vseg-c">
        <div class="vseg-track vtrim" tabindex="0" role="slider" aria-label="播放位置"><div class="vtrim-film"></div><div class="vseg-rng"${L ? ' data-live' : ''}><span class="vtrim-h a" aria-hidden="true"></span><span class="vtrim-h b" aria-hidden="true"></span></div><div class="vseg-head"></div></div>
        <div class="row vseg-tl"><button type="button" class="btn small vseg-play" aria-label="播放">${VID_IC.play}</button>${FREE}
          <button type="button" class="btn small ghost" data-k="-1" title="后退 1 秒（Shift + ←）">−1 秒</button><button type="button" class="btn small ghost" data-k="-f" title="上一帧（←）">−1 帧</button>
          <button type="button" class="btn small ghost" data-k="f" title="下一帧（→）">+1 帧</button><button type="button" class="btn small ghost" data-k="1" title="前进 1 秒（Shift + →）">+1 秒</button>
          <span class="tiny vseg-t"></span></div>
        ${C ? `<div class="row vseg-qk"><button type="button" class="btn small" data-set="a" title="把当前播放位置设为开始">设为开始</button><button type="button" class="btn small" data-set="b" title="把当前播放位置设为结束">设为结束</button><span class="tiny ve-seg-txt"></span><span class="spacer"></span><button type="button" class="btn small ghost vsg-all">整段</button><button type="button" class="chip ve-spl" aria-pressed="false" data-tip="${esc(VSEG_SPL_TIP)}">${VSEG_IC.join}拼接</button></div>` : `<div class="vseg-rows">
          <label class="vseg-row"><span>开始</span><input class="input vseg-in-a" type="number" min="0" step="0.01" aria-label="开始（秒）"><span class="tiny">秒</span><button type="button" class="btn small" data-set="a">设为当前位置</button></label>
          <label class="vseg-row"><span>结束</span><input class="input vseg-in-b" type="number" min="0" step="0.01" aria-label="结束（秒）"><span class="tiny">秒</span><button type="button" class="btn small" data-set="b">设为当前位置</button></label>
        </div>
        <div class="tiny vseg-len"${L ? ' data-live' : ''}></div>${C ? '' : '<div class="vseg-cp" hidden></div>'}
        <div class="row vseg-act"><button type="button" class="btn small ghost vsg-all">整段视频</button>${L ? `<button type="button" class="btn small ghost vsg-add" title="再选一段：从白色标（当前画面）开始多出一个黄色框；白色标在某一段中间时，从那里切成两段。每段各生成一个视频，之后可以一起拼接回原视频">＋ 添加一段</button><button type="button" class="btn small ghost vsg-find" title="分析音乐的节拍和人物的动作，在选段条上标出适合换装 / 拼接的时间点（只用 CPU，不占显卡）">找换装点</button><button type="button" class="btn small ghost ve-ff" title="复制这一段开头那一帧（原视频的清晰度）：到生图页粘贴为原图，用 Qwen 2.1 改好后，放回参考图格、关掉“Qwen 生成”，几段都用这一张">复制首帧</button><button type="button" class="btn small ghost ve-ffs" data-tip="把这一段开头那一帧（原画质）存进素材库">存进素材库</button><button type="button" class="chip ve-spl" aria-pressed="false" data-tip="${esc(VSEG_SPL_TIP)}">${VSEG_IC.join}拼接回原视频</button>` : `<button type="button" class="pl-ib vsg-add2" aria-label="添加一段" data-tip="先记下这一段，再从白色标（当前画面）开始加一段；白色标在某一段中间时从那里切开"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="3"/><path d="M12 9v6M9 12h6"/></svg></button><button type="button" class="btn small ghost vsg-find" title="分析音乐的节拍和人物的动作，在选段条上标出适合换装 / 拼接的时间点（只用 CPU，不占显卡）">找换装点</button><button type="button" class="btn small ghost ve-ff" title="复制这一段开头那一帧（原视频的清晰度）：到生图页粘贴为原图，用 Qwen 2.1 改好后，放回参考图格、关掉“Qwen 生成”，几段都用这一张">复制首帧</button><button type="button" class="btn small ghost ve-ffs" data-tip="把这一段开头那一帧（原画质）存进素材库">存进素材库</button><span class="spacer"></span><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary vsg-ok">应用</button>`}</div>`}
      </div></div>`;
  const V = $('video', root), tr = $('.vseg-track', root), pb = $('.vseg-play', root), ia = $('.vseg-in-a', root), ib = $('.vseg-in-b', root);
  vidVolSync(V);
  const D = () => V.duration || v.dur || 0;
  let [a, b] = veSegAB();
  const paint = () => {
    const d = D(); if (!d) return;
    if (!b || b > d) b = d; a = Math.max(0, Math.min(a, d - 1)); if (b < a + 1) b = Math.min(d, a + 1);
    // 播放时每一帧都会进来：选段、时长、另外几段只在变了时才重画（以前每帧都重建，2026-11-11）
    const sk = [a, b, d, veXs().map(x => x.start + '-' + x.end).join()].join('|'), ch = sk !== paint.k; paint.k = sk;
    if (!L && ia) { if (ch) { $('.vseg-rng', root).style.cssText = `left:${a / d * 100}%;width:${(b - a) / d * 100}%`; $('.vseg-len', root).innerHTML = veSegLen(a, b); } if (document.activeElement !== ia) ia.value = veSegR2(a); if (document.activeElement !== ib) ib.value = veSegR2(b); }
    const tt = $('.vseg-t', root); if (ST) tt.innerHTML = `<b>${V.currentTime.toFixed(2)}</b> / ${d.toFixed(2)} 秒`; else tt.textContent = `${V.currentTime.toFixed(2)} / ${d.toFixed(2)} 秒`;
    if (!L && ch) oth(d);
  };
  // 弹窗（手机上选段用的）：另外几段画成淡黄框，点一下切过去（2026-11-06：手机上也能加多段）
  const oth = d => { const inn = tr.querySelector(':scope > .vtrim-in') || tr; inn.querySelectorAll('.vseg-oth').forEach(e => e.remove());
    veXs().forEach((x, k) => { const e = document.createElement('span'); e.className = 'vseg-oth'; e.dataset.k = k; e.style.cssText = `left:${+x.start / d * 100}%;width:${(+x.end - +x.start) / d * 100}%`; inn.append(e); }); };
  const set = (na, nb) => {
    if (veXs().length) {  // 不能和另外几段重叠：卡在左右相邻那段的边上
      let lo = 0, hi = D(); veXs().forEach(x => { if (x.end <= a + 0.05) lo = Math.max(lo, +x.end); else if (x.start >= b - 0.05) hi = Math.min(hi, +x.start); });
      const ca = Math.max(na, lo), cb = Math.min(nb, hi);
      if (ca !== na || cb !== nb) { const t = Date.now(); if (!set.tip || t - set.tip > 2500) { set.tip = t; toast('不能与其他片段重叠'); } }
      if (cb - ca < 1) { if (ia) { ia.value = veSegR2(a); ib.value = veSegR2(b); } paint(); return; }  // 不行：输入框也改回去
      if (ia && (ca !== na || cb !== nb)) { ia.value = veSegR2(ca); ib.value = veSegR2(cb); }
      na = ca; nb = cb;
    }
    a = na; b = nb; if (L) veSegSet(a, b); paint(); };
  root._segPull = () => { [a, b] = veSegAB(); paint(); }; if (L) root.dataset.segLive = '1';  // 别处改了当前这段（切换 / 添加 / 推荐分段）：跟着更新
  veTrack(tr, V, D, { onRange: (na, nb) => { const sn = veCpSnap(tr, D()), ra = na !== a ? sn(na) : na, rb = nb !== b ? sn(nb) : nb; if (rb - ra >= 1) { na = ra; nb = rb; } set(na, nb); }, getAB: () => [a, b], film: v.url }); V.addEventListener('timeupdate', paint); V.addEventListener('seeked', paint);  // 拖把手：靠近换装点时吸过去；秒数跟着画面（白线）走
  vSmooth(V, () => root.isConnected && root.contains(V) ? paint() : false);  // 播放时秒数每一帧都走（0.01 秒连续变，不再 0.25 秒跳一下，2026-11-05）
  const seek = t => vSeek(V, Math.max(0, Math.min(D() - 0.001, t)));
  const step = k => { V.pause(); seek(V.currentTime + (k === 'f' ? 1 / fps : k === '-f' ? -1 / fps : +k)); };
  $$('[data-k]', root).forEach(x => x.onclick = () => step(x.dataset.k));
  const btn = () => { pb.innerHTML = V.paused ? VID_IC.play : VID_IC.pause; pb.setAttribute('aria-label', V.paused ? '播放' : '暂停'); };
  /* 只放选段（默认，原来的样子）/ 关掉后从白色标随便播（2026-11-06 用户）：随便播时，白色标在任何一段黄色框里，画面四周亮一圈淡黄色 */
  const only = $('.vseg-only', root), vbox = $('.vseg-v', root), free = () => !!S.vsegFree;
  const inSel = t => (t >= a - 0.01 && t <= b + 0.01) || (L && veXs().some(x => t >= +x.start - 0.01 && t <= +x.end + 0.01));
  const ring = () => vbox?.classList.toggle('in-sel', free() && inSel(V.currentTime));
  if (only) only.onclick = () => { S.vsegFree = !S.vsegFree; persist(); $$('.vseg-only').forEach(x => { x.setAttribute('aria-pressed', String(!S.vsegFree)); x.classList.toggle('on', !S.vsegFree); }); ring(); };
  pb.onclick = () => { if (V.paused) { if (free()) { if (V.currentTime >= D() - 0.05) V.currentTime = 0; } else if (V.currentTime >= b - 0.02 || V.currentTime < a - 0.02) V.currentTime = a; V.play().catch(() => { }); } else V.pause(); };
  V.onplay = V.onpause = btn; V.onloadedmetadata = () => { V.currentTime = a; paint(); ring(); if (L) veSegSync();
 };
  V.onclick = () => pb.click();
  V.addEventListener('seeked', ring);
  let raf = 0; const loop = () => { if (!root.isConnected) return; if (!V.paused && !free() && V.currentTime >= b) { V.pause(); V.currentTime = b; } if (!V.paused) { ring(); veCalm(); } raf = requestAnimationFrame(loop); }; loop();
  $$('[data-set]', root).forEach(x => x.onclick = e => { e.preventDefault(); const t = veSegR2(V.currentTime);
    if (x.dataset.set === 'a') set(t, b < t + 1 ? D() : b); else { if (t < a + 1) return toast('结束需比开始晚至少 1 秒', true); set(a, t); } });
  if (ia) ia.onchange = () => { const t = Math.max(0, +ia.value || 0); set(t, b < t + 1 ? D() : b); seek(t); };
  if (ib) ib.onchange = () => { const t = +ib.value || 0; if (t < a + 1) { toast('结束需比开始晚至少 1 秒', true); paint(); if (L) veSegSync(); return; } set(a, t); seek(t); };
  $('.vsg-all', root).onclick = () => { veSegRec(); veState().segs = []; set(0, D()); seek(0); };  // 整段：另外加的几段也不要了
  if ($('.vsg-add', root)) $('.vsg-add', root).onclick = () => veSegAdd(V.currentTime);
  if ($('.vsg-add2', root)) $('.vsg-add2', root).onclick = () => {  // 弹窗：先记下这一段，再从白色标加一段
    const d = D(); veSegSet(a, b >= d - 0.05 ? null : b); veSegAdd(V.currentTime); [a, b] = veSegAB(); paint(); };
  if (!L) tr.addEventListener('pointerdown', e => { const o2 = e.target.closest('.vseg-oth'); if (!o2) return; e.stopPropagation(); e.preventDefault();  // 点另外一段：切过去改
    const d = D(); veSegSet(a, b >= d - 0.05 ? null : b); veSegPick(+o2.dataset.k); [a, b] = veSegAB(); paint(); seek(a); }, true);
  if ($('.vsg-find', root)) $('.vsg-find', root).onclick = () => veCpFind();
  tr.onkeydown = e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); step(e.key === 'ArrowLeft' ? (e.shiftKey ? -1 : '-f') : (e.shiftKey ? 1 : 'f')); } };
  root._seg = { V, step, play: () => pb.click(), stop: () => { cancelAnimationFrame(raf); V.pause(); } };
  if (L) { const sp = $('.ve-spl', root); sp.onclick = () => { ve.splice = ve.splice === false; ve.segUrl = v.url; persist(); veSegSync(); }; veSegSync(); }
  return { get a() { return a; }, get b() { return b; }, D };
}
function veSegOpen(after) {  // 弹窗（窄窗口、或想用大画面逐帧选时）
  const v = VE_VID; if (!v) return toast('请先放入原视频', true);
  const ve = veState();
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">选择要修改的片段</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div><div class="vseg-host"></div>`, null, true);
  box.classList.add('vseg-m');
  const host = $('.vseg-host', box), ui = veSegUI(host); veCpPaint();  // 已经找过换装点：弹窗里的选段条也标上
  const keys = e => { if ([...document.querySelectorAll('.modal-bg:not(.out)')].pop() !== box.parentElement || e.target.closest?.('input, textarea')) return;
    if (e.key === ' ') { e.preventDefault(); host._seg.play(); } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.target.closest?.('.vseg-track')) { e.preventDefault(); host._seg.step(e.key === 'ArrowLeft' ? (e.shiftKey ? -1 : '-f') : (e.shiftKey ? 1 : 'f')); } };
  document.addEventListener('keydown', keys, true);
  const c0 = box.close; box.close = () => { host._seg.stop(); document.removeEventListener('keydown', keys, true); c0(); }; $$('[data-close]', box).forEach(x => x.onclick = box.close);
  $('.vsg-ok', box).onclick = async () => {
    const d = ui.D(); if (!d) return;
    const a = ui.a, b = ui.b, whole = a < 0.05 && b > d - 0.05;
    box.close(); veSegSet(a, b);
    if (!whole && veXs().length) { ve.splice = true; ve.segUrl = v.url; persist(); veSegSync(); }  // 多段：一定要拼接（不用再问）
    else if (!whole) { ve.splice = true; ve.segUrl = v.url; persist(); veSegSync(); }  // 2026-11-10：不再弹窗问，默认拼接
    after?.();
    toast(whole ? '已选择整段视频' : `已选择第 ${veSegR2(a)} – ${veSegR2(b)} 秒${ve.splice ? '，生成后可拼接回原视频' : ''}`);
  };
}
/* 宽窗口改视频 · 并排（试用，默认开）：左原视频 + 选段，右生成结果；“并排”按钮关掉回到单个大画面 */
const veEditWide = () => vidState().mode === 'edit' && matchMedia('(min-width: 1200px)').matches && !!$('#vd-gal');
/* 标题栏（2026-11-07 改版）：左边 生成视频 / 改视频 ▾（点开切换），中间 剪辑 / 成品 / 对比，右边 用法、全部视频、收起选项栏。
   底模在选项里（“H3 · 官方原版”那一项） */
const B5_IC = { down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>', grid: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>',
  book: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg>',
  ck: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>' };
function vdB5Head() {
  const head = $('#main > .page-head'); if (!head || head.classList.contains('b5-head')) return;
  head.classList.add('b5-head');
  const E = () => vidState().mode === 'edit';
  const ctx = document.createElement('button'); ctx.type = 'button'; ctx.className = 'b5-ctx'; ctx.setAttribute('aria-haspopup', 'menu');
  ctx.innerHTML = `<span id="b5-ctx-l">${E() ? '改视频' : '生成视频'}</span>${B5_IC.down}`;
  ctx.onclick = () => popover(ctx, `<div class="b5-menu" role="menu">${[['gen', '生成视频'], ['edit', '改视频']].map(([k, n]) => `<button type="button" role="menuitemradio" aria-checked="${(E() ? 'edit' : 'gen') === k}" data-v="${k}"${(E() ? 'edit' : 'gen') === k ? ' class="on"' : ''}><span>${n}</span>${B5_IC.ck}</button>`).join('')}</div>`,
    pop => $$('[data-v]', pop).forEach(b => b.onclick = () => { pop.close(); $(`#vd-mode-sw [data-v="${b.dataset.v}"]`)?.click(); }), { width: 180 });
  head.prepend(ctx);
  const mid = document.createElement('div'); mid.className = 'b5-mid'; ctx.after(mid);
  const dual = $('#vd-dual-t'); if (dual) mid.append(dual);
  let acts = head.querySelector(':scope > .b5-acts'); if (!acts) { acts = document.createElement('div'); acts.className = 'b5-acts'; head.append(acts); }
  const info = $('#vd-info'); if (info) { info.classList.add('b5-ib'); info.innerHTML = B5_IC.book; info.dataset.tip = '用法'; acts.prepend(info); }
  const all = $('#vd-all'); if (all) { all.className = 'b5-ib vd-allb'; all.innerHTML = B5_IC.grid; all.setAttribute('aria-label', '全部视频'); all.dataset.tip = '全部视频'; info ? info.after(all) : acts.prepend(all); }
  // 底模：在“H3 · 官方原版”那一项里（标题栏不再放）
}
const vdDual = () => veEditWide() && S.vdDual !== false;
const vdDualBtn = () => '';  // 切换在标题那一行（#vd-dual-t）
/* 右侧显示什么：剪辑原视频（vidStage.src）/ 成品 / 与原视频对比（S.vdDual）/ 全部视频平铺（vidStage.grid）。标题跟着变 */
function vdDualBind() {
  const card = $('#vd-gal')?.closest('.ig-gal-card'); if (!card) return;
  const E = vidState().mode === 'edit', G = !!vidStage.grid, st = $('#vd-stage'), t = $('#vd-dual-t');
  card.classList.toggle('vd-edit', E);
  const cur = G ? '' : st?.dataset.id?.startsWith('src:') || (st?.dataset.id === 'closed' && vidStage.closedFrom === 'src') ? 'src' : vdDual() ? 'cmp' : 'one';
  if (t) $$('button', t).forEach(b => { b.classList.toggle('on', b.dataset.v === cur); b.disabled = b.dataset.v === 'src' && !VE_VID; b.title = b.disabled ? '请先在左边放入原视频' : ''; b.onclick = () => vdView(b.dataset.v); });
  const ttl = $('#vd-ttl'); if (ttl) ttl.textContent = G ? '全部视频' : E && cur === 'src' && veEditWide() ? '剪辑原视频' : E && cur === 'cmp' ? '对比原视频与成品' : '生成结果';
  const all = $('#vd-all'); if (all) { all.classList.toggle('on', G); all.setAttribute('aria-pressed', String(G)); all.onclick = () => vdGrid(!vidStage.grid); }
  galLayBind('vd-lay', () => vidGallery());
  veLeftSync();
}
function vdView(v) {
  const was = !!vidStage.grid; vidStage.grid = false;
  if (v === 'src') { if (!VE_VID) return toast('请先在左边放入原视频', true); vidStage.src = true; }
  else { vidStage.src = false; S.vdDual = v === 'cmp'; persist(); }
  vidStage.closed = false; vdStageClear(true);
  if (was) return vidGallery();
  vidStage(vidGal.find(g => g.id === (vidStage.cur || vidStage.last)) || vidGal[0] || null);
}
function vdGrid(on) { vidStage.grid = on; if (on) vdStageClear(); vidGallery(); }
vidStage.grid = false;  // 打开应用 / 重启 Studio 后：不平铺全部视频（2026-11-08 用户：第一次进来成品页空着，见 renderVideo）
function vdStageClear(keep) {  // 清空右边大画面（停掉播放）；keep：只清内容、标题等之后再更新
  const st = $('#vd-stage'); if (st) { st.querySelector('.vseg-host')?._seg?.stop(); st._ab?.stop(); st._ab = null; st.querySelectorAll('video').forEach(v => v.pause()); st.innerHTML = ''; delete st.dataset.id; }
  if (!keep) { $('#vd-gal')?.closest('.ig-gal-card')?.classList.remove('port'); vdDualBind(); }
}
// 剪辑 / 成品 / 对比右上角的 ×：只让当前这个视频不在这里显示（还在当前这一页，上面的标签不变；不会回到“全部视频”）。
// 点下面的缩略图再播放；剪辑关掉后点“剪辑”重新打开（2026-11-08 用户：宽窗口里这个 × 被藏掉了，要加回来）
function vdX(st, from) {
  if (!st || !st.firstElementChild || st.querySelector(':scope > .vd-x')) return;
  st.insertAdjacentHTML('beforeend', `<button type="button" class="ig-stage-x vd-x" title="不在这里显示" aria-label="关闭画面">${ICON.x}</button>`);
  st.lastElementChild.onclick = e => { e.stopPropagation(); vidStage.closedFrom = from || (vdDual() ? 'cmp' : 'one'); vidStage.closed = true; if (from === 'src') vidStage.src = false; vidStage(null); };
}
/* 左边原视频：右侧正在剪辑时只留一行（不再重复显示画面和拖动条） */
function veLeftSync() {
  const b = $('#ve-src'); if (!b) return;
  const st = $('#vd-stage'), on = !!VE_VID && veSrcStageOk() && !vidStage.grid && (!!st?.dataset.id?.startsWith('src:') || vdDual() && !!st?.querySelector('.vd-ab, .vd-dual'));  // 剪辑、对比：大画面里已经有原视频，右栏只留一行
  if (b.classList.contains('onstage') === on) return;
  b.classList.toggle('onstage', on); if (on) $('#ve-src video')?.pause();
  requestAnimationFrame(vePortFit);
}
/* 缩略图的排法不跟着正在看的那一段变：改视频按原视频的方向，生成视频按最近多数视频的方向 */
const vdPortLay = () => {
  const cw = $('#vd-gal')?.closest('.ig-gal-card')?.clientWidth || 0; if (cw && cw < 860) return false;  // 右边太窄：缩略图仍在下面一排
  return galCol($('#vd-gal')?.closest('.ig-gal-card'));  // 用户自己选（标题行的按钮，默认排在下方）；不随正在看的那段变
};
/* 竖屏排法：右边一列两格宽，每格宽度一样、高度按视频比例（瀑布流，不留空） */
matchMedia('(min-width: 1200px)').addEventListener('change', () => { if ($('#vd-gal')) vdMason(); });  // 窗口拉宽 / 缩窄跨过 1200：瀑布流跟着开关
function vdMason() {
  const box = $('#vd-gal'), card = box?.closest('.ig-gal-card'); if (!box) return;
  // 瀑布流的样式只写在宽窗口（≥1200）里；窄窗口 / iPad 横屏（1180、1194）和“全部视频”平铺时不用它——以前照样按格子算了几十行高，第一排后面空出一大段（2026-11-09 用户 iPad）
  const W = () => matchMedia('(min-width: 1200px)').matches;
  const on = W() && !vidStage.grid && !!card?.classList.contains('port') && !!$('#vd-stage')?.firstElementChild && !box.classList.contains('ig-all');
  box.classList.toggle('mason', on);
  if (!on) { box._masRO?.disconnect(); box._masRO = null; $$('.vd-tile', box).forEach(t => { t.style.gridRowEnd = ''; t.style.removeProperty('--rs'); }); return; }
  const go = () => { if (!W()) return vdMason(); if (!box.classList.contains('mason')) return; const w = ($('.vd-tile', box)?.getBoundingClientRect().width) || 0; if (!w) return;
    $$('.vd-tile', box).forEach(t => { const n = Math.ceil((w / (+getComputedStyle(t).getPropertyValue('--tar') || 1.6) + 10) / 4); t.style.gridRowEnd = 'span ' + n; t.style.setProperty('--rs', n); }); };
  go(); if (!box._masRO && window.ResizeObserver) { box._masRO = new ResizeObserver(() => { if (!window.fsHold?.()) requestAnimationFrame(go); }); box._masRO.observe(box); }
}
function vidDualFrame(st) {  // 并排的框架（原视频那一半只在换了原视频时重建，轮询刷新时不打断播放）
  let w = st.querySelector(':scope > .vd-dual');
  if (!w) { st.querySelector('.vseg-host')?._seg?.stop(); st.innerHTML = `<div class="vd-dual"><div class="vd-dual-src"><div class="vseg-host"></div></div><div class="vd-dual-res"></div></div>`; delete st.dataset.id; w = st.querySelector(':scope > .vd-dual'); }
  const sh = $('.vd-dual-src .vseg-host', w);
  if (!VE_VID) {  // 还没放原视频：左边先留着位置
    w.classList.remove('land');
    if (sh.dataset.k !== 'none') { sh._seg?.stop(); sh.dataset.k = 'none'; sh.innerHTML = `<div class="vseg"><div class="vseg-v vd-dual-empty">${VID_IC.film}<span>在左边放入原视频后，这里显示原视频</span><span class="tiny">可拖动进度条选择要修改的片段</span></div><div class="vseg-c"></div></div>`; }
    return $('.vd-dual-res', w);
  }
  const key = 'src:' + VE_VID.url;
  w.style.setProperty('--ar', VE_VID.w && VE_VID.h ? VE_VID.w + ' / ' + VE_VID.h : '9 / 16');
  w.classList.toggle('land', VE_VID.w > VE_VID.h * 1.15);  // 横屏：上下两行（左右并排太小）
  if (sh.dataset.k !== key) { sh._seg?.stop(); sh.dataset.k = key; veSegUI(sh, { live: true, compact: true }); } else veSegSync();
  return $('.vd-dual-res', w);
}
/* 对比播放时默认听哪一路（2026-11-07 用户：改视频默认原声）：拼接好的、改视频且“声音 = 原声”的 → 原视频；其余 → 成品 */
const vdSndDef = x => x?.spliced_of || x?.edit && (x.edit.audio || 'keep') === 'keep' ? 'a' : 'b';
function vidDualEmpty(rp, st) {
  if (rp.dataset.id === '-') return; rp.dataset.id = '-';
  rp.innerHTML = `<div class="vd-dual-v vd-dual-empty">${VID_IC.film}<span>尚未生成视频</span></div>`;
  vdDualBind();
}
/* 并排：对比播放器（左原视频、右生成结果，一条进度条同步播放；并排 / 滑动）。不放剪辑控件（剪辑在左栏原视频那里） */
function vidDualAB(st, x, dk, manual) {
  if (!x) {
    st._ab?.stop(); st._ab = null; st.dataset.id = dk;
    // 还没有结果（2026-11-07 用户：不要虚线框和说明文字）：没放原视频时整块空着，只剩下面居中的“尚未生成过视频”；放了原视频时左边是原视频、右边一句“尚未生成视频”
    if (!VE_VID) { st.innerHTML = ''; return; }
    st.innerHTML = `<div class="vd-ab"></div>`;
    st._ab = abMount($('.vd-ab', st), { video: true, inline: true, a: VE_VID.url, la: '原视频', emptyB: `${VID_IC.film}<span>尚未生成视频</span>` }); return;
  }
  const sc = vidCmpSrc(x) || (VE_VID ? { a: VE_VID.url, off: 0 } : null);  // 不是改视频的成品：左边照样放当前的原视频
  st._ab = abMount($('.vd-ab', st), { video: true, inline: true, a: sc?.a || null, ...vidCmpOff(x, sc), la: sc?.cur ? '原视频（左边当前放入的）' : '原视频', b: vidPlay(x.file), lb: '生成结果', autoplay: manual, onState: vidTileSync, sndKey: x.id, sndDef: vdSndDef(x),
    emptyA: sc ? null : `${VID_IC.film}<span>这段没有保存原视频</span><span class="tiny">在左边放入原视频后可以同步对比</span>` });
}
/* 宽窗口改视频：右边显示原视频大画面 + 选段（还没有成品要看，或点了成品上的“原视频”） */
const veSrcStageOk = () => vidState().mode === 'edit' && !!VE_VID && matchMedia('(min-width: 1200px)').matches && !!$('#vd-gal');
function vidSrcStage() {
  const card = $('#vd-gal')?.closest('.ig-gal-card'); if (!card) return;
  let st = $('#vd-stage'); if (!st) { st = document.createElement('div'); st.id = 'vd-stage'; st.className = 'vd-stage'; card.insertBefore(st, $('#vd-gal')); }
  const key = 'src:' + VE_VID.url + '|' + (VE_VID.w || 0) + 'x' + (VE_VID.h || 0);  // 尺寸读到后按竖屏 / 横屏重排一次
  card.classList.toggle('port', vdPortLay() && !!$('#vd-gal .vd-tile'));  // 有缩略图时才把它们挪到右边一列
  $$('#vd-gal .vd-tile').forEach(t => t.classList.remove('on'));
  if (st.dataset.id === key && st.querySelector('.vseg')) { vdX(st, 'src'); vdDualBind(); vdMason(); return veSegSync(); }
  st.querySelector('.vseg-host')?._seg?.stop(); st._ab?.stop(); st._ab = null;
  st.dataset.id = key;
  st.innerHTML = `<div class="vseg-host vseg-stage"></div>`;
  veSegUI($('.vseg-host', st), { live: true }); vdX(st, 'src'); vdDualBind(); vdMason();
}
/* 成品拼回原视频（原视频 + 一段或几段成品，中间用原视频接上），存成一段新的视频。
   同一个原视频生成过好几段（都选了拼接）：先让你勾选要一起拼进去的几段（多段拼接，2026-11-05 用户要求）；时间重叠的只能选一段 */
const VID_REDO_TIP = '用同样的原视频、同样的片段和设置再生成一次（换一个随机种子），原来的这段保留';
/* 重新生成（2026-11-06 用户）：先弹出提示词框，里面是当时的提示词；不改直接点“生成”，改了就按新的提示词生成这一段（电脑、手机一样） */
async function vidRedo(x, btn) {
  if (btn) btn.disabled = true;
  let info = { prompt: x.prompt_input ?? x.prompt ?? '', edit: !!x.edit, start: x.edit?.start, tpl: x.edit?.tpl };
  try { info = await api('/api/video/redo/prompt?id=' + encodeURIComponent(x.id)); } catch { }
  if (btn?.isConnected) btn.disabled = false;
  const f2 = t => (Math.round(+t * 100) / 100).toString();
  const seg = info.edit && info.start != null ? `片段 ${f2(info.start)}${info.end != null ? ' – ' + f2(info.end) : ''} 秒 · ` : '';
  const box = modal(`<div class="row between" style="margin-bottom:6px"><h3 class="card-title" style="margin:0">重新生成</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="tiny vrd-i">${esc(seg)}同样的原视频、片段和设置，换一个随机种子${hintHtml('提示词不改，直接点“生成”即可；改了就按新的提示词生成这一段。按 Ctrl + Enter 也可以生成')}</div>
    <textarea class="textarea vrd-p" rows="6" placeholder="${info.tpl === false ? '提示词' : '没有填写：按模板生成'}">${esc(info.prompt || '')}</textarea>
    <div class="row vrd-b">${info.pv?.edit ? `<label class="vd-sw vrd-tpl"><span data-tip="${esc('打开：框里的字填进改视频的模板再发给模型（和生成时一样）。<br>关闭：框里的字原样发给模型——从“查看完整提示词”复制整段来改时关掉，不然会再套一次模板。')}">使用模板</span><span class="switch"><input type="checkbox" class="vrd-tplc"${info.tpl !== false ? ' checked' : ''}><span></span></span></label>` : ''}${x.edit ? `<button type="button" class="btn ghost vrd-back" data-tip="把原视频和当时选的这几段放回剪辑，可以重新调整片段再生成">${VSEG_IC.cut}放回剪辑</button>` : ''}<span class="spacer"></span><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary vrd-go">${TL_IC.redo}生成</button></div>`);
  box.classList.add('vrd-m');
  if ($('.vrd-back', box)) $('.vrd-back', box).onclick = async e => { const bb = e.currentTarget; bb.disabled = true; if (await vidBackToCut(x, ta.value)) box.close(); else if (bb.isConnected) bb.disabled = false; };
  const ta = $('.vrd-p', box), go = $('.vrd-go', box), p0 = (info.prompt || '').trim(), tc = $('.vrd-tplc', box);
  const tplOn = () => tc ? tc.checked : info.tpl !== false;
  if (tc) tc.onchange = () => { ta.placeholder = tplOn() ? '没有填写：按模板生成' : '提示词（原样发给模型）'; };
  if (matchMedia('(hover: hover) and (pointer: fine)').matches) setTimeout(() => { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }, 30);  // 手机上不自动弹出键盘
  // 2026-11-10 用户：这里的“查看完整提示词”以前只显示框里的字（看不到模板）。按当时的设置拼出这次真正会发出去的内容，第二页是改视频的模板
  // 和后台 redo_input 一样：没改 = 发当时发出去的那句（英文时是翻好的英文）；改了且写的是中文、当时是英文模板 = 改用中文模板
  if (info.pv?.edit) PromptInspector.bind(ta, () => {
    const same = ta.value.trim() === p0, e = { ...info.pv.edit, tpl: tplOn() };
    if (!same && e.plang === 'en' && /[一-鿿]/.test(ta.value)) e.plang = 'zh';
    const txt = same && info.pv.sent != null ? info.pv.sent : ta.value;
    return api('/api/video/prompt-preview', { body: { prompt: txt, prompt_input: ta.value, seconds: info.pv.seconds, edit: e, has_ref: !!info.pv.has_ref } });
  }, { tpl: { pages: ['vedit'] } });
  const run = async () => {
    go.disabled = true;
    if (!tplOn() && !ta.value.trim()) { toast('关掉模板时请填写完整的提示词', true); go.disabled = false; return ta.focus(); }
    try { await api('/api/video/redo', { body: { id: x.id, prompt: ta.value, ...(tc ? { tpl: tplOn() } : {}) } }); box.close();
      toast(ta.value.trim() === p0 ? '已重新排队：同样的设置，换了一个随机种子' : '已按新的提示词重新排队'); vidWatch(); }
    catch (e) { toast(e.message, true); go.disabled = false; }
  };
  go.onclick = run;
  ta.onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } };
}
/* 放回剪辑（2026-11-07 用户）：把这段（或这组）用的原视频放回改视频，生成它们时选的几段也一起放回去；任务、提示词也填回，方便改了再生成 */
async function vidBackToCut(x, prompt) {
  const fm = t => veSegR2(+t || 0);
  let grp = [];
  try { grp = await api('/api/video/splice/group?id=' + encodeURIComponent((x.spliced_ids || [])[0] || x.id)); } catch { }
  const segs = [], seen = new Set();
  for (const g of (Array.isArray(grp) && grp.length ? grp : [{ start: x.edit?.start || 0, len: +x.seconds || 0 }])) {
    const a = fm(g.start), b = g.len ? fm(+g.start + +g.len) : null, k = a + '|' + b; if (seen.has(k)) continue; seen.add(k); segs.push({ start: a, end: b });
  }
  segs.sort((p, q) => p.start - q.start);
  const st = vidState(), ve = veState();
  st.mode = 'edit'; if (x.edit?.task) ve.task = x.edit.task; if (prompt != null) { st.eprompt = prompt; sessionStorage.setItem('veDraft', prompt); }
  const sv = x.src_vid && vidGal.find(g => g.id === x.src_vid);
  const put = () => {  // 原视频已经放好：写入几段（第一段是当前那段，其余放到 segs）
    const [s0, ...rest] = segs;
    ve.segs = []; veSegSet(s0.start, s0.end);
    ve.segs = rest.filter(r => r.end != null).map(r => ({ url: VE_VID.url, start: r.start, end: r.end }));
    if (segs.length > 1 || s0.start > 0.05 || s0.end != null) { ve.splice = true; ve.segUrl = VE_VID.url; }
    vidStage.src = true; vidStage.grid = false; persist(); go('video', location.pathname !== '/video');
    toast(segs.length > 1 ? `已放回原视频和 ${segs.length} 段，可以重新调整` : '已放回原视频和这一段，可以重新调整');
  };
  if (sv) { if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = veGalVid(sv); ve.start = 0; put(); return true; }
  if (!x.splice_src) { toast('找不到这段用的原视频了', true); return false; }
  try {
    toast('正在载入原视频…');
    const r = await fetch(vidPlay(x.splice_src)); if (!r.ok) throw new Error('原视频读取失败');
    const blob = await r.blob(), file = new File([blob], '原视频.mp4', { type: blob.type || 'video/mp4' });
    if (location.pathname !== '/video' || !window.veLoadVidX) { persist(); go('video', true); }
    window.veLoadVidX(file);
    for (let i = 0; i < 60 && !(VE_VID?.dur > 0); i++) await new Promise(res => setTimeout(res, 100));  // 等读到时长才能按秒数放片段
    if (!(VE_VID?.dur > 0)) throw new Error('原视频读不到时长');
    put(); return true;
  } catch (er) { toast(er.message || '原视频读取失败', true); return false; }
}
/* 全部视频里的删除：一组（拼接视频 + 所有片段）一起删，先问一下（2026-11-07 用户） */
async function vgDelTile(t, g) {
  const x = vidGal.find(y => y.id === t.dataset.id); if (!x) return;
  const ids = g ? g.all.map(y => y.id) : [x.id];
  if (!await confirmBox(g ? `删除这一组（${ids.length} 段）？` : '删除此视频？', g ? '同一个原视频的拼接视频和所有片段都会删除，无法恢复。' : '删除后无法恢复。', '删除', true)) return;
  try { await api('/api/video/gallery/delete', { body: { ids } }); toast(g ? `已删除 ${ids.length} 段` : '已删除'); if (ids.includes(vidStage.cur)) vidStage.cur = null; vidGallery(); } catch (e) { toast(e.message, true); }
}
/* 全部视频：点格子上的 ▶ 就在格子里播放（再点暂停），点格子别处才去大画面（2026-11-07 用户） */
function vgInlineStop(except) { $$('.vd-ju.gl-playing').forEach(t => { if (t === except) return; t.querySelector('video.gl-v')?.remove(); t.classList.remove('gl-playing'); const b = t.querySelector('[data-play]'); if (b) b.innerHTML = VID_IC.play; }); }
function vgInlinePlay(t) {
  const x = vidGal.find(y => y.id === t.dataset.id); if (!x) return;
  vgInlineStop(t);
  let v = t.querySelector('video.gl-v'); const b = t.querySelector('[data-play]');
  if (v) { if (v.paused) { v.play().catch(() => { }); b.innerHTML = VID_IC.pause; } else { v.pause(); b.innerHTML = VID_IC.play; } return; }
  v = document.createElement('video'); v.className = 'gl-v'; v.src = vidPlay(x.file); v.playsInline = true; v.preload = 'auto';
  v.onended = () => vgInlineStop(); t.classList.add('gl-playing'); t.prepend(v); b.innerHTML = VID_IC.pause;
  v.play().catch(() => { v.muted = true; v.play().catch(() => { }); });
}
// 事后超分 / 插帧（2026-11-06）：生成时没勾，之后对这一段再做一次，存成新的一条（原来的不动，同一个视频组里多一个版本）
const VPOST_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M8 15V9l3 3 3-3v6M17 9v6"/></svg>';
function vidPostItems(x) {
  const go = (up, ix, what, color) => async () => {
    try { await api('/api/video/post', { body: { id: x.id, up, ix, ...(color ? { color } : {}) } }); toast(`已排队：${what}，完成后会作为新的一条出现（原视频不变）`); vidWatch(); }
    catch (e) { toast(e.message, true); }
  };
  // 2026-11-09 调色（colorfix.py）：只改颜色，几秒钟；照参考图时先选一张图
  const refPick = () => { const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*';
    inp.onchange = async () => { const f = inp.files?.[0]; if (!f) return; try { const it = await pgImgPrep(f); go(false, 1, '调色 · 参考图', { mode: 'ref', ref: it.image })(); } catch (e) { toast(e.message, true); } };
    inp.click(); };
  const color = [...(x.src_file ? [{ label: '调色 · 匹配原视频', icon: VCOLOR_IC, on: go(false, 1, '调色 · 匹配原视频', { mode: 'match' }) }] : []),
    { label: '调色 · 冷白', icon: VCOLOR_IC, on: go(false, 1, '调色 · 冷白', { mode: 'cold_white' }) },
    { label: '调色 · 参考图…', icon: VCOLOR_IC, on: refPick }];
  const upT = VIDST?.upscaler ? 'Real-ESRGAN' : 'Lanczos', ixT = VIDST?.interp?.length ? 'RIFE' : 'ffmpeg';
  return [{ label: `超分 ×2（${upT}）`, icon: VPOST_IC, on: go(true, 1, '超分 ×2') },
    { label: `插帧 ×2（${ixT}，更流畅）`, icon: VPOST_IC, on: go(false, 2, '插帧 ×2') },
    { label: '超分 + 插帧', icon: VPOST_IC, on: go(true, 2, '超分 + 插帧') },
    // AI 修复超分（SeedVR2 7B）：正常画面更自然清晰；生成时已经变形的脸会更明显（修不了）；约 50 秒处理 1 秒视频（2026-11-06 A/B）
    ...(VIDST?.seedvr ? [{ label: 'AI 修复超分 ×2（SeedVR2，较慢）', icon: VPOST_IC, on: async () => {
      const sec = Math.round(+x.duration || +x.seconds || 0), min = Math.max(1, Math.round(sec * 50 / 60));
      if (!await confirmBox('AI 修复超分（SeedVR2 7B）', `画面会比普通超分自然、清晰得多，但生成时已经变形的脸会被放大得更明显（修不了脸）。这段约 ${sec} 秒，大约需要 ${min} 分钟，期间显卡被占用。`)) return;
      go('seedvr', 1, 'AI 修复超分 ×2（约 ' + min + ' 分钟）')(); } }] : []), '-', ...color];
}
const VCOLOR_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17M12 3.5a8.5 8.5 0 0 1 0 17"/></svg>';
async function vidSplice(x, btn) {
  const go = async ids => {
    if (btn) { btn.disabled = true; btn.dataset.l = btn.textContent; }
    toast(ids.length > 1 ? `正在把 ${ids.length} 段拼接回原视频…` : '正在拼接回原视频…');
    try { const r = await api('/api/video/splice', { body: { id: x.id, ids } }); toast(r.existed ? '这几段已经拼过，直接打开（不重复保存）' : '已拼接为完整视频'); await vidGallery(); const n = vidGal.find(g => g.id === r.id);
      if (n) { if (matchMedia('(min-width: 1200px)').matches && $('#vd-gal')) vidStage(n, true, videoAutoplay()); else vidView(n, videoAutoplay()); } }  // 手机 / 窄窗口：直接打开拼好的视频（以前只在大画面里显示，手机上看不到结果，2026-11-06）
    catch (e) { toast(e.message, true); if (btn?.isConnected) btn.disabled = false; }
  };
  if (vidSplice.busy) return; vidSplice.busy = true;  // 连点两下：只拼一次
  toast('正在查找同一个原视频的其他片段…');  // 先给个反应（以前点了要等后台查完才有动静，手机上像没反应）
  const grp = await api('/api/video/splice/group?id=' + encodeURIComponent(x.id)).catch(() => []).finally(() => { vidSplice.busy = false; });
  if (!Array.isArray(grp) || grp.length < 2) return go([x.id]);
  const fm = t => veSegR2(t).toFixed(2), on = new Set([x.id]), gk = g => fm(g.start) + '|' + fm(g.start + g.len), G = [];
  grp.forEach(g => { let c = G.find(y => y.k === gk(g)); if (!c) G.push(c = { k: gk(g), start: g.start, len: g.len, items: [] }); c.items.push(g); });
  const row = (g, i, c) => `<label class="vsp-row" data-id="${esc(g.id)}"><input type="checkbox"${g.id === x.id ? ' checked' : ''}>
      <span class="vsp-th">${g.thumb ? `<img src="${vidUrl(g.thumb)}" alt="">` : VID_IC.film}</span>
      <span class="vsp-t"><b>${c.items.length > 1 ? `第 ${c.items.length - i} 次` : '生成结果'}</b><span class="tiny">${vidT(g.created)}${g.id === x.id ? ' · 当前这段' : ''}</span></span><em class="tiny vsp-ov"></em></label>`;
  const box = modal(`<div class="row between" style="margin-bottom:6px"><h3 class="card-title" style="margin:0">拼接回原视频${hintHtml('每个片段选一次要拼进去的结果；没有选的部分保持原视频；时间重叠的片段只能选一个')}</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    
    <div class="vsp-list">${G.map(c => `<div class="vsp-g"><div class="vsp-gh"><b>第 ${fm(c.start)} – ${fm(c.start + c.len)} 秒</b><span class="tiny">${fm(c.len)} 秒 · ${c.items.length > 1 ? `${c.items.length} 次` : ''}</span></div>${c.items.map((g, i) => row(g, i, c)).join('')}</div>`).join('')}</div>
    <div class="row" style="gap:8px;margin-top:14px;justify-content:flex-end"><button type="button" class="btn" data-close>取消</button><button type="button" class="btn primary" id="vsp-go">拼接</button></div>`, null, true);
  box.classList.add('vsp-m');
  const ov = (a, b) => a.start < b.start + b.len - 0.05 && b.start < a.start + a.len - 0.05;
  const paint = () => {
    const sel = grp.filter(g => on.has(g.id));
    $$('.vsp-row', box).forEach(r => { const g = grp.find(y => y.id === r.dataset.id), bad = !on.has(g.id) && sel.some(y => gk(y) !== gk(g) && ov(y, g));  // 同一个片段的另一次：可以点，点了就换成它
      r.classList.toggle('off', bad); $('input', r).disabled = bad; $('input', r).checked = on.has(g.id); $('.vsp-ov', r).textContent = bad ? '与已选片段重叠' : ''; });
    $$('.vsp-g', box).forEach(e => e.classList.toggle('on', $$('.vsp-row', e).some(r => on.has(r.dataset.id))));
    const b = $('#vsp-go', box); b.disabled = !on.size; b.textContent = on.size > 1 ? `拼接 ${on.size} 段` : '拼接';
  };
  $$('.vsp-row input', box).forEach(i => i.onchange = () => { const id = i.closest('.vsp-row').dataset.id, g = grp.find(y => y.id === id);
    if (i.checked) { grp.forEach(y => { if (gk(y) === gk(g)) on.delete(y.id); }); on.add(id); } else on.delete(id); paint(); });  // 同一个片段只能选一次
  $('#vsp-go', box).onclick = () => { const ids = grp.filter(g => on.has(g.id)).map(g => g.id); box.close(); go(ids); };
  paint();
}
/* 宽窗口改视频 · 竖屏原视频：原视频那一格的高度 = 左栏剩下的空间（不让左栏出现滚动）；提示词变长时先让给提示词 */
function vePortFit() {
  const src = $('#ve-src'); if (!src || vePortFit.busy) return;
  const f = src.closest('.ig-top-f'), on = !!f && src.dataset.port === '1' && IG_WIDE() && !!src.querySelector('.ve-vid') && !src.classList.contains('onstage');
  if (!on) { src.classList.remove('ptall'); src.style.removeProperty('--pth'); return; }
  vePortFit.busy = true;
  try {
    const BASE = 190, ta = $('#vd-prompt'), over = () => f.scrollHeight - f.clientHeight;
    // 先量普通排法，再量竖屏排法：竖屏排法会让左栏更长（窗口小、本来就挤）就不用它——绝不比原来更挤
    src.classList.remove('ptall'); src.style.removeProperty('--pth'); ta?.dispatchEvent(new Event('input')); const o0 = over();
    src.classList.add('ptall'); src.style.setProperty('--pth', BASE + 'px');
    ta?.dispatchEvent(new Event('input'));  // 提示词框先按最大空间量一次
    if (over() > o0) { src.classList.remove('ptall'); src.style.removeProperty('--pth'); ta?.dispatchEvent(new Event('input')); return; }
    const cb = f.querySelector(':scope > .ig-cbar'); if (!cb) return;
    const m0 = cb.style.marginTop; cb.style.marginTop = '0';
    const used = cb.getBoundingClientRect().bottom - f.getBoundingClientRect().top + f.scrollTop + parseFloat(getComputedStyle(f).paddingBottom);
    cb.style.marginTop = m0;
    const free = Math.floor(f.clientHeight - used) - 2, ar = (VE_VID?.w && VE_VID?.h) ? VE_VID.w / VE_VID.h : 9 / 16;
    const h = Math.max(BASE, Math.min(BASE + free, Math.floor(src.clientWidth * 0.5 / ar), 620));
    src.style.setProperty('--pth', h + 'px');
  } finally { vePortFit.busy = false; }
}
function vidStage(x, manual = false, play = manual) {  // play：要不要开始播放（关了自动播放时，点缩略图 manual 但不 play）  // manual：点击缩略图 / 时间线，明确要求播放
  const card = $('#vd-gal')?.closest('.ig-gal-card'); if (!card) return;
  if (vidStage.grid && matchMedia('(min-width: 1200px)').matches) { if (manual) { vidStage.grid = false; vidStage.cur = x?.id || null; vidGallery(); } return; }  // 正在平铺全部视频
  if (manual) { vidStage.src = false; vidStage.closed = false; }
  if (!x && vidStage.top === undefined) vidStage.top = '-';  // 本次还没有成品：之后第一段出来也算“有新成品”
  if (x && x.id !== vidStage.top && vidGal[0]?.id === x.id && (x.created || 0) >= SESS_T0) { if (vidStage.top) { vidStage.src = false; vidStage.closed = false; } vidStage.top = x.id; }  // 有新成品：切过去看
  const D = vdDual(); vdDualBind();
  if (veSrcStageOk() && vidStage.src) { vidStage.cur = null; return vidSrcStage(); }  // 改视频：剪辑原视频
  if (vidStage.closed && vidGal.length) {  // 点了 ×：上面的播放画面空着（显示一个图标），下面的缩略图照常；一段都没有时不写“点击缩略图播放”，走下面“没有结果”（2026-11-15）
    let st = $('#vd-stage'); if (!st) { st = document.createElement('div'); st.id = 'vd-stage'; st.className = 'vd-stage'; card.insertBefore(st, $('#vd-gal')); }
    if (st.dataset.id === 'closed' && (st.dataset.cf || '') !== (vidStage.closedFrom || '')) delete st.dataset.id;
    st.dataset.cf = vidStage.closedFrom || '';
    if (st.dataset.id !== 'closed') { st.querySelector('.vseg-host')?._seg?.stop(); st._ab?.stop(); st._ab = null; st.querySelectorAll('video').forEach(v => v.pause());
      st.innerHTML = `<div class="vd-ab-empty vd-empty vd-closed">${VID_IC.play}<span>${vidStage.closedFrom === 'src' ? '点击上方的“剪辑”重新打开' : '点击缩略图播放'}</span></div>`; st.dataset.id = 'closed'; }
    if (x) vidStage.last = x.id; vidStage.cur = null;
    $$('#vd-gal .vd-tile').forEach(t => t.classList.remove('on')); vidTileSync();
    card.classList.toggle('port', vdPortLay()); vdDualBind(); vdMason(); return;
  }
  if (!D) $('#vd-stage')?.querySelector('.vseg-host')?._seg?.stop();
  let st = $('#vd-stage'); if (!st) { st = document.createElement('div'); st.id = 'vd-stage'; st.className = 'vd-stage'; card.insertBefore(st, $('#vd-gal')); }
  vidStage.cur = x?.id || null; if (x) vidStage.last = x.id;
  $$('#vd-tl .vd-tl-s').forEach(t => { const s = tlOf()[+t.dataset.k]; t.classList.toggle('on', !!s && tlSel(s) === vidStage.cur); });
  $$('#vd-gal .vd-tile').forEach(t => t.classList.toggle('on', vgTileIs(t, vidStage.cur)));
  vidTileSync();
  card.classList.toggle('port', !!x && vdPortLay());  // 竖屏排法：缩略图在右边一列（按原视频 / 多数视频的方向定，不随正在看的那段变；对比时不挪）
  if (st.querySelector(':scope > .vd-dual, :scope > .vseg-host, :scope > .vd-empty')) { st.querySelector('.vseg-host')?._seg?.stop(); st.innerHTML = ''; delete st.dataset.id; }  // 旧的并排框架
  const tgt = st, dk = D ? 'ab:' + (x?.id || '-') + '|' + (VE_VID?.url || '') : null;
  if (D && st.dataset.id === dk && st.querySelector('.vd-ab')) return;  // 并排：同一对，不重建（轮询刷新不打断播放）
  if (st._ab && (!D || st.dataset.id !== dk)) { st._ab.stop(); st._ab = null; if (!D) { st.innerHTML = ''; delete st.dataset.id; } }
  if (!x) {
    if (D) { vidDualAB(st, null, dk); vdX(st); vdDualBind(); vdMason(); return; }
    st.innerHTML = ''; delete st.dataset.id;  // 没有结果：不放占位框，下面那句“尚未生成过视频”居中
    vdDualBind(); vdMason(); return; }
  if (!D && tgt.dataset.id === x.id && tgt.querySelector('video')) { if (manual && play) { vidVolSync($('video', tgt)); videoPreviewPlay($('video', tgt), true); } return; }  // 同一段：不重建；主动点它仍可开始播放
  tgt.dataset.id = D ? dk : x.id;
  // 自动显示的结果遵循设置；点击缩略图时直接播放。音量 / 静音跟播放栏一样。
  // 只播一遍（2026-11-04 用户要求不循环）；播放 / 暂停时下面缩略图上的图标跟着变（vidTileSync）
  const vHtml = `<video class="vd-player" src="${vidPlay(x.file)}" controls muted playsinline></video>`;
  tgt.innerHTML = (D ? '<div class="vd-ab"></div>' : vHtml) + `
    <div class="row vd-stage-bar"><span class="tiny vd-stage-i" title="${esc(vidTip(x))}">${esc([x.merged ? '完整版' : vidMN(x.model_name), (x.loras || []).length ? 'LoRA ' + vidLoras(x) : '无 LoRA', vidT(x.created) + (x.took ? '（用时 ' + vidTook(x.took) + '）' : ''), `${x.width} × ${x.height}`, `${x.seconds} 秒`].join(' · '))}</span><span class="spacer"></span>
      <button type="button" class="btn small" id="vs-trim" title="去掉不要的帧或片段，存成一段新视频（原来的不动）">${VSEG_IC.cut}修剪</button>${x.redo ? `<button type="button" class="btn small" id="vs-redo" title="${VID_REDO_TIP}">${TL_IC.redo}重新生成</button>` : ''}<a class="btn small" href="${vidUrl(x.file)}" download="${esc(x.file)}">${ICON.dl}下载</a>${vdDualBtn()}${x.splice_src ? `<button type="button" class="btn small" id="vs-join" title="用这一段替换原视频中第 ${x.edit?.start || 0} 秒起的对应部分，生成完整的视频">${VSEG_IC.join}拼接回原视频</button>` : ''}${vidCmpSrc(x) && !veEditWide() ? `<button type="button" class="btn small" id="vs-cmp" title="与原视频同步对比播放">${IC_CMP}对比</button>` : ''}<button type="button" class="btn small" id="vs-more" title="详情和提示词">${IC_INFO}详情</button><button type="button" class="btn small" id="vs-x" title="续接、加入时间线、改视频" aria-label="更多操作"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>更多</button><button type="button" class="btn small danger" id="vs-del">${IMG_IC.del}删除</button></div>`;
  fitCompact($('.vd-stage-bar', tgt), stageTight, ['c1']);  // 放不下：按钮先只留图标（都有图标，鼠标停留看文字），信息文字省略
  if (D) vidDualAB(st, x, dk, manual && play);
  else { const v = $('video', tgt); v.onplay = v.onpause = v.onended = v.onemptied = vidTileSync; vidTileSync(); vidVolSync(v, !manual); videoPreviewPlay(v, manual && play); if (typeof frAttach === 'function') frAttach(v, { gallery: x.id });  // 视频截图：S 键、截图标记
    if (x.spliced_rng) vgSegBar(tgt, x);  // 拼好的视频：下面一条分段条
    vqcBar(tgt, x, v); }  // 自动质检查出的问题
  vdX(st); vdDualBind(); vdMason();
  $('#vs-x', st).onclick = e => ctxMenu({ anchor: e.currentTarget }, [...(!D && typeof frGrab === 'function' ? [{ label: '截取这一帧', icon: FR_IC.cam, hint: 'S', on: () => { const v = $('video', st); if (v) frGrab({ gallery: x.id }, v.currentTime, { video: v }); } }, { label: '截取画面…', icon: FR_IC.stack, on: () => framePick({ gallery: x.id }, { mode: 'save', primary: '完成' }) }, '-'] : []), { label: '续接', icon: VID_IC.chain, on: () => vidChain(x) },
    ...(x.timeline ? [] : [{ label: '加入时间线', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>', on: () => tlAdd(x) }]),
    { label: '改视频', icon: VE_IC, on: () => vidEditThis(x) }, '-', ...vidPostItems(x)]);
  $('#vs-trim', st).onclick = () => vtrimOpen(vtFromItem(x));
  if ($('#vs-redo', st)) $('#vs-redo', st).onclick = e => vidRedo(x, e.currentTarget);
  $('#vs-more', st).onclick = () => vidView(x);
  if ($('#vs-cmp', st)) $('#vs-cmp', st).onclick = () => vidCompare(x);
  if ($('#vs-join', st)) $('#vs-join', st).onclick = e => vidSplice(x, e.currentTarget);
  $('#vs-del', st).onclick = async () => {
    if (!await confirmBox('删除此视频？', '删除后无法恢复。', '删除', true)) return;
    try { await api('/api/video/gallery/delete', { body: { ids: [x.id] } }); vidStage.cur = null; toast('已删除'); vidGallery(); } catch (e) { toast(e.message, true); }
  };
}
/* 详情：把这段用到的参数按组全部列出来（一屏放下）。2026-11-08 用户：要一眼看出这次开了什么、方便对比不同参数的效果——
   重要开关（加速 LoRA、首帧锁定…）开着关着都写出来，开着的高亮；旧记录里没存的项不写（不猜） */
const vidTbName = f => { if (/_dmd_/i.test(f || '')) return 'DMD 8 步（作者配方自带）'; const m = /(\d+)step_v([\d.]+)(?:_(\d+p))?/.exec(f || ''); return m ? `${m[1]} 步 v${m[2]}${m[3] ? ' · ' + m[3] + ' 版' : ''}` : f; };
function vidKV(x) {
  const M = (VIDST?.models || []).find(m => m.key === x.model), T = M?.tune || {}, e = x.edit, H3 = x.model === 'h3', sw = (v, t) => [t ?? (v ? '开' : '关'), v ? 'on' : 'off'];
  const base = e ? e.base : x.base, outfit = e?.task === 'outfit', ref = outfit && (e.method || 'ref') === 'ref', has = k => e && k in e;
  const seg = e && e.start != null && e.want ? `${+e.start} – ${+(+e.start + +e.want).toFixed(2)} 秒` : e?.start ? `从第 ${e.start} 秒` : undefined;
  const G = [
    ['画面', [['尺寸', `${x.width} × ${x.height}` + (x.gen_size && x.gen_size !== `${x.width}×${x.height}` ? `（生成 ${x.gen_size}）` : '')],
      ['时长', `${x.duration ? (+x.duration).toFixed(1) : x.seconds} 秒`], ['帧率', x.fps && `${x.fps} fps` + (x.gen_fps && Math.round(x.gen_fps) !== Math.round(x.fps) ? `（生成 ${x.gen_fps}）` : '')], ['帧数', x.frames], ['声音', x.audio ? '有' : '无']]],
    ['采样', [['引擎', H3 ? { 1: '① 原生节点', 2: '② 秋叶节点' }[x.engine] : undefined], ['步数', x.steps], ['种子', x.seed], ['采样器', x.sampler], ['调度器', x.scheduler],
      ['偏移', x.shift !== undefined ? x.shift + (x.ashift !== undefined && (x.ashift !== T.ashift || x.engine === '2') ? ` · 声音 ${x.ashift}` : '') : undefined], ['CFG', x.cfg], ['切换步', x.split]]],
    ['增强', [['加速 LoRA', H3 ? (x.turbo?.lora ? sw(1, vidTbName(x.turbo.lora)) : sw(0, '不使用')) : undefined],
      ['稀疏注意力', x.h3opt?.sparse && x.h3opt.sparse !== 'off' ? sw(1) : undefined], ['LoRA', vidLoras(x) || '无']]],
    ['改视频', e ? [['任务', [veTaskName(e.task), e.swap_by === 'v11' ? '新版（Alissonerdx v1.1 配方）' : e.swap_by === 'bfs' ? 'Alissonerdx v1.1' : e.task === 'motion' ? 'Alissonerdx Motion Transfer v1.0 配方' : e.task === 'head' ? '换脸 LoRA（UntMods）' : e.vg ? 'Viggle 重拍（Viggle Remake edit）' : ''].filter(Boolean).join(' · ')],
      ['人物（看图写的）', e.recipe ? (e.ref_desc || '没写成（按人物图）') : undefined], ['场景', e.task === 'motion' ? (e.ref_env || '沿用原视频') : undefined],
      ['做法', outfit ? { ref: '参考生成', animate: '保真替换', bernini: '参考编辑', swap: '整体重绘（已停用）', mask: '局部重绘（已停用）' }[e.method || 'mask'] : undefined],
      ['参考图', ref ? (e.own ? (e.ref ? '自己的图' : '无（只按提示词）') : e.qshared ? '共用同一批第一段的图' : 'Qwen 生成') : undefined],
      ['首帧锁定', ref && has('ffguide') && !e.own ? sw(e.ffguide) : undefined], ['色调', e.cmatch ? '已匹配原视频' : undefined], ['局部修改', e.loc ? (e.loc.q === 'person' ? '整个人' : '衣服') : undefined], ['动作跟随', e.pose ? (e.loc || e.pose_v === '2' ? '开启（2.0 · 官方精简底模）' : '开启（官方精简底模）') : undefined], ['模板', e.tpl === false ? sw(0, '未使用') : '使用'],
      ['提示词', e.plang === 'en' ? '英文' : e.plang ? '中文' : undefined], ['对象', e.target || undefined], ['声音', (VE_AUDIO.find(a => a[0] === e.audio) || [, ''])[1]],
      ['选段', seg], ['拼接', e.splice ? '可拼回原视频' : undefined]] : []],
    ['其他', [['插帧', x.interp ? `帧率 ×${x.interp_x || 2}${x.interp_by ? `（${x.interp_by}）` : '（ffmpeg）'}` : undefined], ['超分', x.upscale ? (x.upscale_by || '是') : undefined],
      ['调色', x.color ? ({ match: '匹配原视频', cold_white: '冷白', ref: '参考图' }[x.color.mode] || x.color.mode) + (x.color.strength < 1 ? ` · 强度 ${Math.round(x.color.strength * 100)}%` : '') : undefined], ['首尾帧', x.flf ? '是' : undefined],
      ['续接', x.merged ? `${(x.parts || []).length} 段合成` : x.chain_of ? '接续上一段' : undefined],
      ['更多素材', x.h3x ? [x.h3x.keys?.length ? '关键帧 ' + x.h3x.keys.map(t => t + ' 秒').join('、') : '', x.h3x.clip ? (x.h3x.clip.startsWith('head') ? '开头片段（取最前 ' : '开头片段（取最后 ') + x.h3x.clip.replace(/\D/g, '') + ' 帧）' : '',
        x.h3x.audio !== undefined ? `指定声音（从第 ${x.h3x.audio} 秒）` : '', x.h3x.refs ? `参考图 ${x.h3x.refs} 张` : '', x.h3x.rvids ? `参考视频 ${x.h3x.rvids} 段` : '', x.h3x.raudios ? `参考音频 ${x.h3x.raudios} 段` : ''].filter(Boolean).join(' · ') : undefined],
      ['用时', x.took ? vidTook(x.took) : undefined], ['时间', imgWhen(x.created)]]]];
  const cell = ([k, v]) => { const [t, c] = Array.isArray(v) ? v : [v, '']; return `<span${c ? ` class="${c}"` : ''}><i>${k}</i>${esc(String(t))}</span>`; };
  return G.map(([h, L]) => [h, L.filter(([, v]) => v !== undefined && v !== null && v !== '')]).filter(([, L]) => L.length)
    .map(([h, L]) => `<div class="vd-g"><b>${h}</b><div>${L.map(cell).join('')}</div></div>`).join('');
}
function vidView(x, play = videoAutoplay()) {  // 详情：关了自动播放时只打开、不播放
  if (!x) return;
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">${esc(x.merged ? '完整版 · ' + x.model_name : x.model_name)}</h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <video class="vd-player" src="${vidPlay(x.file)}" controls playsinline preload="auto" data-frg="${esc(x.id)}"></video>
    <div class="vd-kv vd-kvg">${vidKV(x)}</div>
    <div class="vd-prompt">${esc(x.prompt)}${x.negative ? `<div class="tiny" style="margin-top:6px">负面：${esc(x.negative)}</div>` : ''}</div>
    <div class="row" style="gap:8px;margin-top:12px"><a class="btn small" href="${vidUrl(x.file)}" download="${esc(x.file)}">${ICON.dl}下载</a><button type="button" class="btn small" id="vv-chain" title="以此段的最后一帧作为首帧继续生成">${VID_IC.chain}续接</button><button type="button" class="btn small" id="vv-edit" title="用此视频进行换人 / 改衣 / 修改">${VE_IC}改视频</button><button type="button" class="btn small" id="vv-trim" title="去掉不要的帧或片段，存成一段新视频（原来的不动）">${VSEG_IC.cut}修剪</button><button type="button" class="btn small" id="vv-post" title="对这一段再做超分、插帧或调色，存成新的一条（原来的不动）">${VPOST_IC}后期处理</button>${x.redo ? `<button type="button" class="btn small" id="vv-redo" title="${VID_REDO_TIP}">${TL_IC.redo}重新生成</button>` : ''}<button type="button" class="btn small" id="vv-reuse">使用这组设置</button>${vidCmpSrc(x) ? `<button type="button" class="btn small" id="vv-cmp">${IC_CMP}对比</button>` : ''}${x.splice_src ? `<button type="button" class="btn small" id="vv-join">${VSEG_IC.join}拼接回原视频</button>` : ''}<span class="spacer"></span><button type="button" class="btn small ghost danger" id="vv-del">删除</button></div>`, null, true);
  box.classList.add('vd-view');
  { const v = $('video', box), h = document.createElement('div'); v.after(h); vqcBar(h, x, v); if (!h.firstChild) h.remove(); }  // 自动质检查出的问题（手机详情）
  { const v = $('video', box), fit = () => { if (!box.isConnected) return removeEventListener('resize', fit); v.style.maxHeight = ''; const over = box.scrollHeight - box.clientHeight;
      if (over > 0) v.style.maxHeight = Math.max(120, v.getBoundingClientRect().height - over) + 'px'; };  // 参数多 / 屏幕矮（手机）时缩小播放器，整个详情一屏放下、不用滚动
    v.addEventListener('loadedmetadata', fit); addEventListener('resize', fit); requestAnimationFrame(fit); }
  PromptInspector.history($('.vd-prompt', box), x);
  vidVolSync($('video', box));  // 跟播放栏的音量 / 静音一致（两边谁调都同步）
  if (play) videoPreviewPlay($('video', box), true);
  $('#vv-chain', box).onclick = () => vidChain(x, () => box.close());
  if ($('#vv-cmp', box)) $('#vv-cmp', box).onclick = () => { box.close(); vidCompare(x); };
  if ($('#vv-join', box)) $('#vv-join', box).onclick = () => { box.close(); vidSplice(x); };
  $('#vv-edit', box).onclick = () => vidEditThis(x, () => box.close());
  $('#vv-trim', box).onclick = () => { box.close(); vtrimOpen(vtFromItem(x)); };
  $('#vv-post', box).onclick = e => ctxMenu({ anchor: e.currentTarget }, vidPostItems(x).map(it => it === '-' ? it : ({ ...it, on: () => { box.close(); it.on(); } })));
  if ($('#vv-redo', box)) $('#vv-redo', box).onclick = e => vidRedo(x, e.currentTarget);
  $('#vv-reuse', box).onclick = () => {
    const st = vidState(), a = vidAdv(), M = x.model, Mi = (VIDST?.models || []).find(m => m.key === M), T = Mi?.tune || {};
    const sz = ['480p', '576p', '720p'].includes(x.size) ? x.size : 'custom';
    if (x.edit) {  // 改视频做出来的：回到“改视频”，任务 / 原视频 / 人物图都填回去（原视频、人物图还在库里时）
      Object.assign(st, { mode: 'edit', eprompt: x.prompt, eseconds: x.seconds, size: sz, res: sz === 'custom' ? String(x.size || '').replace('×', 'x') : st.res, seed: x.seed });
      const { ref: _r, ...ed } = x.edit; Object.assign(veState(), { base: 'full', tpl: true, ...ed, method: 'ref', ...(ed.lite && ed.base === 'full' ? { base: 'lite' } : {}) }); delete veState().loose; delete veState().lite; veSetTpl(ed.tpl !== false, veTplKey(veState().task, veState().method)); sessionStorage.setItem('veDraft', x.prompt);  // 旧记录没有 base：按官方
      const sv = x.src_vid && vidGal.find(g => g.id === x.src_vid); if (sv) { if (VE_VID?.kind === 'upload') URL.revokeObjectURL(VE_VID.url); VE_VID = veGalVid(sv); }
      const ri = x.src_id && imgGal.find(g => g.id === x.src_id); VE_REF = ri ? vidImg(ri) : VE_REF;
    } else Object.assign(st, { mode: 'gen', model: M, prompt: x.prompt, seconds: x.seconds, size: sz, res: sz === 'custom' ? String(x.size || '').replace('×', 'x') : st.res, seed: x.seed });
    const setP = (k, v, d) => { if (v === undefined || v === null || String(v) === String(d)) delete a[k + '_' + M]; else a[k + '_' + M] = v; };
    setP('steps', x.steps, x.edit?.base === 'official' ? VIDST?.edit?.official_steps || 20 : Mi?.defaults?.steps); setP('sampler', x.sampler, T.sampler); setP('scheduler', x.scheduler, T.scheduler); setP('shift', x.shift, T.shift);
    setP('cfg', x.cfg, T.cfg); setP('split', x.split, Math.max(1, Math.floor((x.steps || 4) / 2))); setP('ashift', x.ashift, T.ashift);
    { const tk = x.turbo?.kind ? (x.edit ? 'e_' : '') + x.turbo.kind : '';  // 那次用了加速：恢复加速的选择；步数、偏移是加速 LoRA 的，不当成自己改的
      a.turbo = { ...(a.turbo || {}), ...(tk ? { [tk]: x.turbo.lora } : {}) }; if (x.turbo?.lora) ['steps', 'shift', 'ashift'].forEach(k => delete a[k + '_' + M]); }
    if (!x.edit) setP('fps', x.gen_fps, Mi?.fps);  // 改视频固定 24 fps、声音在“声音”里选：不动生成视频的这两项
    if (M === 'h3' && !x.edit) setP('audio', x.audio ? undefined : false);
    a['loras_' + x.model] = (x.loras || []).map(L => ({ ...L }));  // “用这组设置”：LoRA 也填回去
    Object.assign(a, { interp: !!x.interp, interp_x: x.interp_x || (x.interp ? 2 : 1), interp_by: /FILM/.test(x.interp_by || '') ? 'film' : /RIFE/.test(x.interp_by || '') ? 'rife' : x.interp ? 'ff' : (a.interp_by || 'rife'), upscale: !!x.upscale, negative: x.negative || '' });
    if (!x.edit) { sessionStorage.setItem('vdDraft', x.prompt); if (x.src_id) { st.srcId = x.src_id; VID_SRC = null; } }
    persist(); box.close(); go('video', location.pathname !== '/video'); toast('已填回提示词和全部参数');
  };
  $('#vv-del', box).onclick = async () => {
    if (!await confirmBox('删除此视频？', '删除后无法恢复。', '删除', true)) return;
    try { await api('/api/video/gallery/delete', { body: { ids: [x.id] } }); box.close(); toast('已删除'); vidGallery(); } catch (e) { toast(e.message, true); }
  };
}
PAGES.video = renderVideo;

/* 时间线：把几段按顺序排起来（续接出来的会自动排进去），每段可以有几个版本挑一个；连续预览、导出成一段完整的视频。
   S.vidg.tl = [{ v: [视频 id…], c: 选中的版本 }]，每个空间各自一份 */
const TL_IC = {
  redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.9l10.4-6.5a1 1 0 0 0 0-1.8L9.5 4.6A1 1 0 0 0 8 5.5z"/></svg>',
  out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 8v5M12 16.5v.5"/><circle cx="12" cy="12" r="9"/></svg>',
};
const tlOf = () => { const st = vidState(); st.tl = Array.isArray(st.tl) ? st.tl : []; return st.tl; };
const tlGet = id => vidGal.find(x => x.id === id);
const tlSel = slot => slot.v[Math.min(slot.c || 0, slot.v.length - 1)];
const tlRaw = id => { const x = tlGet(id); return x?.merged && !x.timeline ? (x.parts || []).slice(-1)[0] : id; };  // 合成版：对应它的最后一段
const tlWide = () => matchMedia('(min-width: 1200px)').matches;
/* 视频库刷新后：续接出来的新段自动排进时间线（接在它的上一段后面；那里已经有一段时就当作这一段的另一个版本） */
function tlSync() {
  const st = vidState(), tl = tlOf(), t0 = st.tlT || 0;
  if (!t0) { st.tlT = Math.max(SESS_T0, ...vidGal.map(x => x.created || 0)); persist(); return; }  // 第一次：只记下时间，不翻旧账
  const fresh = vidGal.filter(x => !x.merged && x.chain_of && (x.created || 0) > t0).sort((a, b) => a.created - b.created);
  if (!fresh.length) return;
  for (const x of fresh) {
    const pid = tlRaw(x.chain_of);
    let k = tl.findIndex(s => s.v.includes(pid));
    if (k < 0 && !tl.length) {  // 还没有时间线：用这条续接链建一条
      const p = tlGet(x.chain_of), ids = p?.merged ? (p.parts || []) : [pid];
      ids.filter(tlGet).forEach(id => tl.push({ v: [id], c: 0 })); k = tl.length - 1;
    }
    if (k < 0) continue;
    const nx = tl[k + 1];
    if (nx && nx.v.some(id => tl[k].v.includes(tlRaw(tlGet(id)?.chain_of)))) { nx.v.push(x.id); nx.c = nx.v.length - 1; }
    else tl.splice(k + 1, 0, { v: [x.id], c: 0 });
  }
  st.tlT = Math.max(t0, ...fresh.map(x => x.created)); persist();
}
function tlAdd(x) {
  if (!x) return; const tl = tlOf();
  if (tl.some(s => s.v.includes(x.id))) return toast('已在时间线中');
  tl.push({ v: [x.id], c: 0 }); persist(); tlPaint(); toast('已加入时间线');
}
function tlPaint() {
  const card = $('#vd-gal')?.closest('.ig-gal-card'); if (!card) return;
  const tl = tlOf();
  tl.forEach(s => { s.v = s.v.filter(tlGet); }); for (let i = tl.length - 1; i >= 0; i--) if (!tl[i].v.length) tl.splice(i, 1);  // 删掉的视频不再显示
  let el = $('#vd-tl'); if (!tl.length) { el?.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'vd-tl'; el.className = 'vd-tl'; card.append(el); }
  const secs = tl.reduce((n, s) => { const x = tlGet(tlSel(s)); return n + (+(x?.duration || x?.seconds || 0)); }, 0);
  el.innerHTML = `<div class="row vd-tl-h"><b>时间线</b><span class="tiny">${tl.length} 段 · 约 ${Math.round(secs)} 秒</span><span class="spacer"></span>
      <button type="button" class="ig-cb" id="tl-play" title="从第一段连续播放到最后一段">${TL_IC.play}连续预览</button>
      <button type="button" class="ig-cb" id="tl-out" title="按顺序拼接成一段完整视频，存入视频库"${tl.length < 2 ? ' disabled' : ''}>${TL_IC.out}导出完整视频</button>
      <button type="button" class="pl-ib" id="tl-clr" title="清空时间线（不删除视频本身）" aria-label="清空时间线">${ICON.x}</button></div>
    <div class="vd-tl-row">${tl.map((s, k) => {
      const id = tlSel(s), x = tlGet(id), prev = k ? tlSel(tl[k - 1]) : null, broken = k && x.chain_of && tlRaw(x.chain_of) !== prev;
      return `<div class="vd-tl-s${id === vidStage.cur ? ' on' : ''}" draggable="true" data-k="${k}" title="${esc(vidTip(x))}">
        <div class="vd-tl-th">${x.thumb ? `<img src="${vidUrl(x.thumb)}" alt="" draggable="false">` : VID_IC.film}<span class="vd-tl-i">${k + 1}</span><span class="vd-tl-d">${x.duration ? (+x.duration).toFixed(1) : x.seconds} 秒</span>
          ${broken ? `<span class="vd-tl-w" title="此段并非从上一段的最后一帧接续，导出时将直接切换">${TL_IC.warn}</span>` : ''}
          <button type="button" class="vd-tl-x" data-rm title="从时间线移除（不删除视频本身）" aria-label="移除">${ICON.x}</button></div>
        <div class="vd-tl-f">${s.v.length > 1 ? `<button type="button" data-pv="-1" aria-label="上一个版本">‹</button><span>版本 ${(s.c || 0) + 1}/${s.v.length}</span><button type="button" data-pv="1" aria-label="下一个版本">›</button>` : `<span class="vd-tl-p">${esc(x.prompt || '')}</span>`}
          ${k ? `<button type="button" class="vd-tl-r" data-redo title="以上一段的最后一帧和此段的提示词重新生成一个版本">${TL_IC.redo}</button>` : ''}</div></div>`;
    }).join('')}
      <button type="button" class="vd-tl-add" id="tl-next" title="以最后一段的最后一帧继续生成下一段">${VID_IC.chain}<span>续接下一段</span></button></div>`;
  const kOf = e => +e.target.closest('[data-k]').dataset.k;
  $$('.vd-tl-s', el).forEach(s => {
    s.onclick = e => { if (e.target.closest('button')) return; const x = tlGet(tlSel(tl[+s.dataset.k])); if (tlWide()) vidStage(x, true, videoAutoplay()); else vidView(x); };
    s.ondragstart = e => { e.dataTransfer.setData('text/plain', s.dataset.k); e.dataTransfer.effectAllowed = 'move'; s.classList.add('drag'); };
    s.ondragend = () => s.classList.remove('drag');
    s.ondragover = e => { e.preventDefault(); s.classList.add('over'); };
    s.ondragleave = () => s.classList.remove('over');
    s.ondrop = e => { e.preventDefault(); s.classList.remove('over'); const a = +e.dataTransfer.getData('text/plain'), b = +s.dataset.k; if (isNaN(a) || a === b) return; const [m] = tl.splice(a, 1); tl.splice(b, 0, m); persist(); tlPaint(); };
  });
  $$('[data-rm]', el).forEach(b => b.onclick = e => { const k = kOf(e), old = tl.splice(k, 1)[0]; persist(); tlPaint(); toastAct('已从时间线移除', '撤销', () => { tl.splice(k, 0, old); persist(); tlPaint(); }); });
  $$('[data-pv]', el).forEach(b => b.onclick = e => { const s = tl[kOf(e)]; s.c = ((s.c || 0) + +b.dataset.pv + s.v.length) % s.v.length; persist(); tlPaint(); if (tlWide()) vidStage(tlGet(tlSel(s)), true); });
  $$('[data-redo]', el).forEach(b => b.onclick = e => { const k = kOf(e); vidChain(tlGet(tlSel(tl[k - 1])), null, tlGet(tlSel(tl[k]))?.prompt); });
  $('#tl-next', el).onclick = () => vidChain(tlGet(tlSel(tl[tl.length - 1])));
  $('#tl-clr', el).onclick = () => { const old = tl.splice(0); persist(); tlPaint(); toastAct('已清空时间线', '撤销', () => { tl.push(...old); persist(); tlPaint(); }); };
  $('#tl-play', el).onclick = () => tlPlay(tl.map(tlSel).map(tlGet));
  $('#tl-out', el).onclick = async e => {
    const b = e.currentTarget; if (b.disabled) return; b.disabled = true; const t = b.innerHTML; b.innerHTML = `${TL_IC.out}正在导出…`;
    try {
      const x = await api('/api/video/timeline/export', { body: { ids: tl.map(tlSel) } });
      toast('已导出完整视频（' + x.seconds + ' 秒）'); await vidGallery(); if (tlWide()) vidStage(tlGet(x.id) || x);
    } catch (er) { toast(er.message, true); }
    if (b.isConnected) { b.disabled = false; b.innerHTML = t; }
  };
}
function tlPlay(list) {  // 连续预览：一段放完自动放下一段
  list = list.filter(Boolean); if (!list.length) return;
  let i = 0;
  const box = modal(`<div class="row between" style="margin-bottom:10px"><h3 class="card-title" style="margin:0">连续预览 <span class="tiny" id="tlp-i"></span></h3><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <video class="vd-player" controls autoplay playsinline></video>`, null, true);
  box.classList.add('vd-view');
  const v = $('video', box); vidVolSync(v);
  const load = () => { v.src = vidPlay(list[i].file); $('#tlp-i', box).textContent = `第 ${i + 1} / ${list.length} 段`; v.play().catch(() => { }); };
  v.onended = () => { if (i < list.length - 1) { i++; load(); } };
  load();
}

/* 宽窗口生视频（不含改视频）：放了首帧后，首帧图在左、右边一列放尾帧、尺寸那行字、参考图等素材按钮和“模型”，
   首帧图的高度 = 左栏剩下的空间（vdSrcFit），整栏不出现滚动（2026-11-05，和生图页的原图面板同一种排法） */
function vdSide(box, s) {
  box.classList.remove('vd-side-on'); box.style.removeProperty('--vdh');
  // 2026-11-11 用户（截图）：新版右栏（提示词在底部，B5_BOTTOM）里这样排会把右栏撑到一千多像素宽、下面空一大块——只在提示词还在旁边的老排法里用
  if (!s || !IG_WIDE() || vidState().mode === 'edit' || (typeof B5_BOTTOM === 'function' && B5_BOTTOM())) return requestAnimationFrame(vdSrcFit);
  const fr = $('.vd-frames', box); if (!fr) return;
  const side = document.createElement('div'); side.className = 'vd-side';
  [$('#vd-f2', box), $('#vd-efile', box), box.querySelector(':scope > .vd-src-i'), box.querySelector(':scope > .vd-src-row')].filter(Boolean).forEach(n => side.append(n));
  const mf = $('#vd-model')?.closest('.field');
  if (mf && !mf.closest('#vd-src')) { mf._home = mf._home || mf.parentElement; side.prepend(mf); }
  fr.append(side); box.classList.add('vd-side-on');
  box.dataset.port = s.h > s.w * 1.15 ? '1' : '';
  $('.ig-src > img', fr)?.addEventListener('load', () => requestAnimationFrame(vdSrcFit));
  requestAnimationFrame(vdSrcFit);
}
function vdSrcFit() {
  const box = $('#vd-src'), col = box?.closest('.ig-top-f'), img = box && $('.vd-frames > .ig-src > img', box);
  if (!box || !col || !img || !box.classList.contains('vd-side-on')) return;
  const MAX = box.dataset.port === '1' ? 560 : 400, MIN = 130;
  box.style.setProperty('--vdh', MAX + 'px');
  const over = col.scrollHeight - col.clientHeight, now = img.getBoundingClientRect().height || MAX;
  let h = Math.floor(now - Math.max(0, over));
  const side = $('.vd-side', box); if (side) h = Math.max(h, Math.floor(side.getBoundingClientRect().height));
  box.style.setProperty('--vdh', Math.max(MIN, Math.min(MAX, h)) + 'px');
}
addEventListener('resize', () => {
  const w = IG_WIDE(), box = $('#vd-src');
  if (box && w !== vdSrcFit.wide && vidState().mode !== 'edit' && VID_SRC) { vdSrcFit.wide = w; renderVideo.repaintSrc?.(); return; }
  vdSrcFit.wide = w; requestAnimationFrame(vdSrcFit);
});
