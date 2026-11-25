/* 素材库 · gallery（三个素材站整理来的姿势 / 衣服 / 脸，见 D:\AI-TTS\素材库\gallery\index.json）的浏览界面，选图弹窗和“素材库”页面共用。
   和原站一样：一个页面切换筛选。上面一行：姿势 / 衣服 / 脸 + 大类 + 搜索 + “筛选”（左边细分类一栏，可以收起；窄屏盖在图上）。
   姿势：默认一个姿势一张（正面），点进去看这个姿势的所有角度；深色模式下线稿反色显示（只是显示，用的还是原图）。
   衣服的细分类来自原站的英文关键词（一共 86 个词），翻成中文、归成几组。
   galPick(fn, o)：弹窗选一张，fn(素材库文件对象 { name, rel, label, kind })；o：lib 从哪个开始、lock 只看这一个、title / note / skip / onCancel 同 matsPick */
'use strict';
const GAL = { items: null, load: null, st: {}, cnt: null, more: new Set() };
/* 素材库文件夹的排序（2026-11-05）：名称 / 加入时间（复制进来的那一刻，Windows 的创建时间）/ 修改时间；所有文件夹共用、记在本机 */
const MATS_SORTS = [['name', '名称', '升序（A→Z）'], ['name_d', '名称', '降序（Z→A）'], ['added', '添加日期', '最新在前'], ['added_o', '添加日期', '最早在前'], ['mtime', '修改日期', '最新在前'], ['mtime_o', '修改日期', '最早在前']];
// 2026-11-15 用户：排序名字更短、更正式 —— 照 macOS Finder：“排序方式”（名称 / 添加日期 / 修改日期）+ “顺序”两组
const matsSortName = k => { const x = MATS_SORTS.find(y => y[0] === k) || MATS_SORTS[0]; return x[1] + ' · ' + x[2]; };
const matsSortGet = () => MATS_SORTS.some(x => x[0] === localStorage.getItem('matsSort')) ? localStorage.getItem('matsSort') : 'name';
const MATS_COL = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' });
function matsSort(list, how, dadd = {}) {  // 文件夹在前、文件在后，各自按同一种方式排
  const t = x => x.dir ? (dadd[x.name] || 0) : (/^mtime/.test(how) ? x.mtime : x.added ?? x.mtime) || 0;
  const cmp = how === 'name_d' ? (a, b) => MATS_COL.compare(b.name, a.name) : how === 'name' ? (a, b) => MATS_COL.compare(a.name, b.name)
    : how === 'added_o' || how === 'mtime_o' ? (a, b) => t(a) - t(b) || MATS_COL.compare(a.name, b.name) : (a, b) => t(b) - t(a) || MATS_COL.compare(a.name, b.name);
  return [...list.filter(x => x.dir).sort(cmp), ...list.filter(x => !x.dir).sort(cmp)];
}
const galShut = () => { try { return new Set(JSON.parse(localStorage.getItem('galShut')) || GAL_SHUT0); } catch { return new Set(GAL_SHUT0); } };
const GAL_LIBS = ['姿势', '衣服', '脸'];
const GAL_ANGLES = ['正面', '斜侧', '侧面', '俯视', '仰视'];
const GAL_IC = {
  zoom: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 20 20M10.5 7.5v6M7.5 10.5h6"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  filter: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M7 7l10 10M17 7 7 17"/></svg>',
  chev: '<svg class="gal-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v6.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z"/></svg>',
};
/* 衣服：原站关键词 → 中文 */
const GAL_KW = { bag: '包', mini: '迷你', black: '黑色', skirt: '半身裙', knit: '针织', dress: '连衣裙', boots: '靴子', socks: '袜子', lace: '蕾丝', white: '白色', ribbon: '蝴蝶结', sandals: '凉鞋',
  leather: '皮革', stockings: '长筒袜', brown: '棕色', camisole: '吊带', tights: '连裤袜', cardigan: '开衫', necklace: '项链', ivory: '象牙白', satin: '缎面', pants: '长裤', jacket: '夹克', heels: '高跟鞋',
  shorts: '短裤', beige: '米色', grey: '灰色', denim: '牛仔', pleated: '百褶', red: '红色', gold: '金色', blue: '蓝色', shirt: '衬衫', fur: '毛绒', navy: '藏青', silver: '银色', frill: '荷叶边',
  choker: '颈链', midi: '中长', coat: '大衣', bra: '文胸', briefs: '内裤', pink: '粉色', sneakers: '运动鞋', suede: '麂皮', green: '绿色', blouse: '女式衬衫', tote: '托特包', loafers: '乐福鞋',
  belt: '腰带', mint: '薄荷绿', hat: '帽子', jeans: '牛仔裤', wool: '羊毛', cream: '奶油色', headband: '发箍', floral: '碎花', corset: '束腰', velvet: '丝绒', pumps: '浅口鞋', gloves: '手套',
  turtleneck: '高领', sunglasses: '墨镜', yellow: '黄色', khaki: '卡其', burgundy: '酒红', orange: '橙色', corduroy: '灯芯绒', scarf: '围巾', robe: '睡袍', swimsuit: '泳衣', sweater: '毛衣',
  chiffon: '雪纺', olive: '橄榄绿', tulle: '薄纱', mesh: '网纱', beret: '贝雷帽', vest: '背心', hoodie: '连帽衫', apron: '围裙', maxi: '长款', 'polka-dot': '波点', lavender: '薰衣草紫',
  beanie: '毛线帽', muffler: '围脖', purple: '紫色' };
/* 衣服的细分类：组 → [中文, 关键词…]；一件衣服可以在好几组里 */
const GAL_TAGS = {
  单品: [['连衣裙', 'dress'], ['半身裙', 'skirt'], ['长裤', 'pants', 'jeans'], ['短裤', 'shorts'], ['衬衫', 'shirt', 'blouse'], ['吊带', 'camisole'], ['针织 · 毛衣', 'knit', 'sweater', 'turtleneck'],
    ['开衫', 'cardigan'], ['外套', 'coat', 'jacket'], ['背心', 'vest'], ['连帽衫', 'hoodie'], ['内衣', 'bra', 'briefs', 'corset'], ['泳衣', 'swimsuit'], ['睡袍', 'robe'], ['围裙', 'apron']],
  长度: [['迷你', 'mini'], ['中长', 'midi'], ['长款', 'maxi']],
  颜色: [['黑', 'black'], ['白', 'white'], ['象牙白 · 奶油', 'ivory', 'cream'], ['米色', 'beige'], ['棕', 'brown'], ['卡其', 'khaki'], ['灰', 'grey'], ['红', 'red'], ['酒红', 'burgundy'], ['粉', 'pink'],
    ['橙', 'orange'], ['黄', 'yellow'], ['绿', 'green', 'mint', 'olive'], ['蓝', 'blue'], ['藏青', 'navy'], ['紫', 'purple', 'lavender'], ['金', 'gold'], ['银', 'silver']],
  '材质 · 元素': [['蕾丝', 'lace'], ['皮革', 'leather'], ['缎面', 'satin'], ['牛仔', 'denim'], ['毛绒', 'fur'], ['丝绒', 'velvet'], ['灯芯绒', 'corduroy'], ['麂皮', 'suede'], ['羊毛', 'wool'],
    ['雪纺', 'chiffon'], ['薄纱 · 网纱', 'tulle', 'mesh'], ['百褶', 'pleated'], ['荷叶边', 'frill'], ['蝴蝶结', 'ribbon'], ['碎花', 'floral'], ['波点', 'polka-dot']],
  鞋袜: [['靴子', 'boots'], ['凉鞋', 'sandals'], ['高跟鞋', 'heels', 'pumps'], ['运动鞋', 'sneakers'], ['乐福鞋', 'loafers'], ['袜子', 'socks'], ['长筒袜', 'stockings'], ['连裤袜', 'tights']],
  配饰: [['包', 'bag', 'tote'], ['项链', 'necklace'], ['颈链', 'choker'], ['帽子', 'hat', 'beret', 'beanie'], ['发箍', 'headband'], ['手套', 'gloves'], ['墨镜', 'sunglasses'], ['围巾', 'scarf', 'muffler'], ['腰带', 'belt']],
};
/* 脸的发型：原站 50 个发型名里混着剪法、刘海、质感、发色，按名字里的词拆成几组：组 → [中文, 名字里的词…] */
const GAL_HAIR = {
  剪法: [['波波头', '波波'], ['层次', '层次'], ['狼尾', '狼尾', '水母头'], ['蘑菇头', '蘑菇头'], ['蝴蝶剪 · 羽毛剪', '蝴蝶剪', '羽毛剪'], ['收颈', '收颈'], ['直发', '直发']],
  刘海: [['无刘海', '无刘海'], ['齐刘海', '齐刘海'], ['空气刘海', '空气刘海', '空气齐刘海'], ['侧 · 斜刘海', '侧刘海', '斜刘海'], ['长刘海', '长刘海'], ['两用刘海', '两用刘海']],
  质感: [['顺直', '直', '顺直'], ['烫 · 卷', '烫', '卷'], ['内扣', '内扣'], ['外翘', '外翘'], ['碎发 · 纹理', '碎', '纹理', '流苏']],
  发色: [['黑 · 深色', '黑发', '深色', '深棕'], ['棕', '棕', '栗', '榛子', '巧克力'], ['奶茶 · 米色', '奶茶', '米色'], ['灰', '灰'], ['红', '酒红', '樱桃红'], ['紫', '薰衣草'], ['金', '金色'], ['挑染', '挑染', '染色', '手刷染']],
};
const GAL_TAGDEF = { ...GAL_TAGS, ...GAL_HAIR };  // t: 开头的键都在这里找
/* 衣服颜色按钮前面的小色点 */
const GAL_DOT = { 黑: '#1d1d1f', 白: '#fff', '象牙白 · 奶油': '#f3ead6', 米色: '#d9c6a5', 棕: '#7a4e2d', 卡其: '#b59a6a', 灰: '#9a9a9e', 红: '#d23a3a', 酒红: '#7d1f34', 粉: '#f2a7bf',
  橙: '#f08a2c', 黄: '#f2cf3a', 绿: '#4f9a5c', 蓝: '#3d7be0', 藏青: '#22355e', 紫: '#9277c9', 金: 'linear-gradient(135deg, #f7e08a, #b8892d)', 银: 'linear-gradient(135deg, #f2f2f2, #9da3ab)' };
/* 每个库：上面第二层标签（大类），右边一栏的细分类（[键, 名字]；t: 开头的是从关键词 / 发型名拆出来的分组，一张图可以在好几组里） */
const GAL_TOP = { 姿势: ['group', '类型'], 衣服: ['cat', '分类'], 脸: ['cat', '类型'] };
const GAL_SIDE = { 姿势: [['cat', '分类']], 衣服: Object.keys(GAL_TAGS).map(g => ['t:' + g, g]),
  脸: [['hair', '发长'], ...Object.keys(GAL_HAIR).map(g => ['t:' + g, g]), ['style', '原站发型名']] };
const GAL_SHUT0 = ['style'];  // 默认收起的组（原站发型名 50 个，要精确挑的时候再打开）

function galItems() {
  if (GAL.items) return Promise.resolve(GAL.items);
  return GAL.load || (GAL.load = api('/api/mats/gallery').then(r => {
    const items = r.items || []; GAL.ver = r.ver || '';
    for (const x of items) if (x.lib === '衣服') {  // 衣服：中文名、细分类
      const kw = (x.keywords || '').split(/\s+/).filter(Boolean), ks = new Set(kw);
      x.zh = kw.map(w => GAL_KW[w] || w).join(' · ');
      for (const [g, os] of Object.entries(GAL_TAGS)) x['t:' + g] = os.filter(([, ...ws]) => ws.some(w => ks.has(w))).map(o => o[0]);
    } else if (x.lib === '脸' && x.style) {  // 脸：发型名拆成剪法 / 刘海 / 质感 / 发色
      for (const [g, os] of Object.entries(GAL_HAIR)) x['t:' + g] = os.filter(([, ...ws]) => ws.some(w => x.style.includes(w))).map(o => o[0]);
    }
    return (GAL.items = items);
  }).finally(() => { GAL.load = null; }));
}
const galThumb = x => matsUrl(x.rel) + '?thumb=1' + (GAL.ver ? '&v=' + GAL.ver : '');  // v：清单版本，浏览器可以一直缓存（2026-11-11）
const galFThumb = x => matsUrl(x.rel) + '?thumb=1' + (x.mtime ? '&v=' + Math.round(x.mtime) : '');  // 文件夹里的：按文件的修改时间
const galLabel = x => x.lib === '姿势' ? `${x.pose || ''} ${x.name || ''} · ${x.angle || ''}`.trim() : x.lib === '衣服' ? `${x.id || ''} · ${x.zh || x.keywords || ''}` : [x.cat, x.hair, x.style].filter(Boolean).join(' · ');
const galFile = x => ({ name: x.rel.split('/').pop(), rel: x.rel, label: galLabel(x), kind: 'image', lib: x.lib });
const galHas = (x, k, v) => k.startsWith('t:') ? (x[k] || []).includes(v) : x[k] === v;
const galImg = f => matsFile(f).then(file => new Promise((res, rej) => {  // 素材库的图 → { kind: 'upload', data, url, w, h }（太大的缩到 2048 以内）
  const fr = new FileReader();
  fr.onload = () => { const im = new Image(); im.onload = () => { let data = fr.result, w = im.naturalWidth, h = im.naturalHeight;
    if (Math.max(w, h) > 2048) { const k = 2048 / Math.max(w, h), c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); data = c.toDataURL('image/jpeg', .95); w = c.width; h = c.height; }
    res({ kind: 'upload', data, url: data, w, h }); }; im.onerror = () => rej(new Error('无法打开此图片')); im.src = fr.result; };
  fr.onerror = () => rej(new Error('无法读取此图片')); fr.readAsDataURL(file);
}));

/* 线稿底色（姿势是白底黑线的人体模型线稿）：0 = 原图白底；往右先变暗（灰底黑线），过了一半换成反色（深底浅线），越往右越深。只是显示，选用的还是原图 */
const GAL_SK_IC = {
  open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M14.5 4.5v15"/><path d="M10.5 9.5 8 12l2.5 2.5"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M14.5 4.5v15"/><path d="M8 9.5l2.5 2.5L8 14.5"/></svg>',
  audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/></svg>',
  combo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="9.5" r="5"/><circle cx="15" cy="9.5" r="5"/><circle cx="12" cy="14.5" r="5"/></svg>',
};
GAL_IC.fwd = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>';
GAL_IC.pin = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3.5h6M10 3.5v5.2L6.8 12.4h10.4L14 8.7V3.5M12 12.4V20.5"/></svg>';
GAL_IC.play = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 5.8v12.4a.8.8 0 0 0 1.2.7l9.6-6.2a.8.8 0 0 0 0-1.4L9.7 5.1a.8.8 0 0 0-1.2.7z"/></svg>';
GAL_IC.pause = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6.5" y="5" width="4" height="14" rx="1.2"/><rect x="13.5" y="5" width="4" height="14" rx="1.2"/></svg>';
/* “从素材库选择”菜单项的图标：和左边导航“素材库”一样（四格），跟“从图库 / 视频库选择”的文件夹图标区分开 */
var MATS_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="9" rx="2"/><rect x="13.5" y="3.5" width="7" height="6" rx="2"/><rect x="3.5" y="15.5" width="7" height="5" rx="2"/><rect x="13.5" y="12.5" width="7" height="8" rx="2"/></svg>';
/* 文件夹里的视频格子：点小播放键就在格子里预览（不选中、不放大）；音量 / 静音跟着播放栏；同一时间只放一个 */
function galPrev(b) {
  const im = b.parentElement, pr = $('.gal-prog', im);
  let v = $('video', im);
  if (!v) { const th = $('[data-vsrc]', im); if (!th) return;  // 格子里平时只有封面图：第一次点 ▶ 才放进播放器
    v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto'; v.className = 'gal-vv' + (th.classList.contains('gal-land') ? ' gal-land' : ''); v.src = th.dataset.vsrc; th.after(v); }
  if (!v.paused) return v.pause();
  $$('video.gal-pv').forEach(x => { if (x !== v) x.pause(); });
  if (!v._gp) {
    v._gp = 1; v.classList.add('gal-pv'); if (v.currentTime < .2) v.currentTime = 0;
    const sync = () => { const on = !v.paused; b.innerHTML = on ? GAL_IC.pause : GAL_IC.play; b.title = on ? '暂停预览' : '在这里预览'; im.classList.toggle('gal-playing', on); };
    v.addEventListener('play', sync); v.addEventListener('pause', sync);
    v.addEventListener('ended', () => { v.currentTime = 0; if (pr) pr.style.width = '0'; sync(); });
    v.addEventListener('timeupdate', () => { if (!v.isConnected) return v.pause(); if (pr) pr.style.width = (v.duration ? v.currentTime / v.duration * 100 : 0) + '%'; });
    vSmooth(v, () => { if (!v.isConnected) return false; if (pr) pr.style.width = (v.duration ? v.currentTime / v.duration * 100 : 0) + '%'; });  // 进度条连续走
  }
  vidVolSync(v); v.play().catch(() => { });
}
/* 素材库页面“文件夹”整理：新建文件夹 / 多选 / 移动 / 移到上一层 */
const GAL_FM = {
  newf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v6.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z"/><path d="M12 10.5v5M9.5 13h5"/></svg>',
  batch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="12" height="9" rx="2"/><path d="M7 17h10a2 2 0 0 0 2-2V8"/><path d="M11 21h8a2 2 0 0 0 2-2v-7"/></svg>',
  multi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3.5"/><path d="M8.5 12.2l2.4 2.4 4.6-5"/></svg>',
  move: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v6.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z"/><path d="M9 13.2h6M12.8 11l2.2 2.2-2.2 2.2"/></svg>',
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/></svg>',
  ck: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M6 12.5l4 4 8-9"/></svg>',
};
function galSkFilter(v) {
  const t = Math.max(0, Math.min(100, +v || 0)) / 100;
  return t === 0 ? 'none' : t <= .5 ? `brightness(${(1 - 1.1 * t).toFixed(3)})` : `invert(${(.7 + .4 * (t - .5)).toFixed(3)})`;
}
function galSkSet(v) { localStorage.setItem('galSk', String(v)); document.documentElement.style.setProperty('--gal-sk', galSkFilter(v)); }
document.documentElement.style.setProperty('--gal-sk', galSkFilter(localStorage.getItem('galSk') || 0));

/* 浏览界面本体：root 里画“上面一行 + 图片区 + 右边细分类一栏”。
   o.pick(x)：点了一张（姿势卡先进角度详情）；o.detail(x, angles)：页面里点了一张（打开详情，不直接选）；o.lib / o.lock；
   o.folders：多一个“文件夹”标签（素材库里 gallery 以外的东西，按文件夹浏览），o.kind 只看哪种（image / video / audio，不填 = 全部），o.pickFile(f)：点了文件夹里的一个文件；
   o.extra：上面一行“筛选”前面再放的按钮（HTML），o.onExtra(top)：绑定它；o.folderState：独立的文件夹路径 / 搜索状态 */
const GAL_SET_IC = {  // 图集角标：参照 SF Symbols 的 square.on.square / livephoto
  stack: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><rect x="2.2" y="4.8" width="9" height="9" rx="2"/><path d="M5 2.4h6.6a2.2 2.2 0 0 1 2.2 2.2V11"/></svg>',
  live: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="9.2" stroke-dasharray="1.6 2.2"/></svg>',
};
/* 图集格子翻看（2026-11-15 用户：鼠标划过去就换图，图多了一动就变好几张，满屏图集时移开鼠标也在不停地变）：
   改成 Airbnb 房源卡片的做法——鼠标停在格子上才出现左右两个圆箭头，点一下翻一张（第一张没有左箭头、最后一张没有右箭头），翻到的那张留着；
   下面的圆点参照 Instagram：不超过 5 个全显示，多了只显示 5 个、跟着当前那张滑动，两头还有更多的画小一点。键盘：选中格子按 ← →。 */
function galDots(n, k) {
  const W = 5, s = n <= W ? 0 : Math.max(0, Math.min(n - W, k - 2)), e = Math.min(n, s + W);
  let h = '';
  for (let j = s; j < e; j++) h += `<i class="${j === k ? 'on' : (j === s && s > 0) || (j === e - 1 && e < n) ? 'sm' : ''}"></i>`;
  return h;
}
/* 快捷位置：素材库页面右键（手机长按）文件夹“加到快捷位置”，上面一行库标签旁边一下直达；存在 S.ui.matsQk（跟着设置同步），值 = 文件夹的相对路径 */
const galQkList = () => Array.isArray(S.ui?.matsQk) ? [...S.ui.matsQk] : [];
const galQkKey = rel => rel;
const galQkSave = L => { S.ui = { ...(S.ui || {}), matsQk: [...new Set(L)] }; persist(); window.dispatchEvent(new Event('galqk')); };
function galLongPress(el) {  // 手机：长按 0.5 秒 = 右键菜单（松手那一下不算点击）
  let t = 0, x = 0, y = 0, fired = false;
  el.addEventListener('touchstart', e => { fired = false; clearTimeout(t); if (e.touches.length !== 1) return; const p = e.touches[0]; x = p.clientX; y = p.clientY;
    t = setTimeout(() => { fired = true; e.target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: x, clientY: y })); }, 500); }, { passive: true });
  el.addEventListener('touchmove', e => { const p = e.touches[0]; if (p && Math.hypot(p.clientX - x, p.clientY - y) > 10) clearTimeout(t); }, { passive: true });
  el.addEventListener('touchend', () => clearTimeout(t), { passive: true });
  el.addEventListener('click', e => { if (fired) { fired = false; e.preventDefault(); e.stopPropagation(); } }, true);
}
function galMount(root, o = {}) {
  const libs = o.lock ? [o.lib] : GAL_LIBS.concat(o.folders ? ['文件夹'] : []);
  let lib = libs.includes(o.lib) ? o.lib : libs.includes(GAL.lastLib) ? GAL.lastLib : libs[0], detail = null, shown = 0, list = [], io = null, tok = 0;
  const F = o.folderState || GAL.fold || (GAL.fold = { dir: '', q: '' }), fcache = new Map();
  const M = !!o.manage, sel = new Set();  // o.manage：素材库页面的“文件夹”可以整理（拖动 / 右键 / 多选）
  let multi = false, fkey = '', drag = null, fsrcNow = null;  // fsrcNow：打开的是视频截图的图集时，它的来源视频
  const narrow = () => root.clientWidth < 900;
  let sideOpen = narrow() ? false : localStorage.getItem('galSide') !== '0';
  const st = l => GAL.st[l] || (GAL.st[l] = { q: '', angle: '正面' });
  root.classList.add('gal-root');
  root.innerHTML = `<div class="gal-top"><div class="gal-t1"><button type="button" class="btn small gal-back" data-hback disabled title="回退到上一个位置" aria-label="回退">${GAL_IC.back}</button>${o.lock ? `<b class="gal-lib">${esc(lib)}</b>` : `<div class="seg gal-tabs">${libs.map(l => `<button type="button" data-lib="${l}">${l}</button>`).join('')}</div>`}<div class="gal-qk" role="group" aria-label="快捷位置" hidden></div>
      <div class="gal-q"><input class="input" type="search" placeholder="搜索" aria-label="搜索" enterkeyhint="search"></div><span class="spacer"></span>${o.extra || ''}
      <button type="button" class="btn small gal-qbtn" data-tip="搜索" aria-label="搜索"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg></button>
      <button type="button" class="btn small gal-fbtn" data-side>${GAL_SK_IC.open}<span>筛选</span><span class="gal-fn" hidden></span></button></div><div class="gal-t2"></div></div>
    <div class="gal-main"><div class="gal-body"><div class="gal-wait">正在读取素材…</div></div><div class="gal-scrim"></div><aside class="gal-side" aria-label="细分类"><div class="gal-side-in"></div></aside></div>`;
  const top = $('.gal-top', root), t2 = $('.gal-t2', root), side = $('.gal-side-in', root), body = $('.gal-body', root), scrim = $('.gal-scrim', root), inp = $('.gal-q input', root), fbtn = $('[data-side]', root);
  const isF = () => lib === '文件夹';
  /* 回退：记下去过的位置（库标签、文件夹、上面的大类、姿势的角度页），点“回退”回到上一个 */
  const hist = [], hb = $('[data-hback]', root);
  const here = () => ({ lib, dir: F.dir, det: detail, top: isF() ? '' : (st(lib)[GAL_TOP[lib][0]] || '') });
  const syncBack = () => { hb.disabled = !hist.length; };
  const mark = () => { const h = here(), p = hist[hist.length - 1]; if (!p || p.lib !== h.lib || p.dir !== h.dir || p.det !== h.det || p.top !== h.top) hist.push(h); if (hist.length > 60) hist.shift(); syncBack(); };
  hb.onclick = () => {
    const h = hist.pop(); syncBack(); if (!h) return;
    if (multi) setMulti(false);
    lib = h.lib; if (!isF()) { GAL.lastLib = lib; st(lib)[GAL_TOP[lib][0]] = h.top; } else { F.dir = h.dir; F.q = ''; }
    detail = h.det; syncTop(); refresh();
  };
  /* 快捷位置（见 galQkList）：右键快捷位置可以前后移、移除 */
  const qk = $('.gal-qk', root), qkOn = libs.includes('文件夹');
  let qkHave = null;  // 根目录里有的文件夹
  const qkHas = rel => !!qkHave?.has(rel);
  const qkCur = () => {  // 现在在哪个快捷位置里（最长的那个算）
    if (!isF()) return '';
    let best = '', len = -1;
    for (const v of galQkList()) {
      const n = F.dir === v || F.dir.startsWith(v + '/') ? v.length : -1;
      if (n > len) { best = v; len = n; }
    }
    return len >= 0 ? best : '';
  };
  /* 画快捷位置：结构只在快捷位置变了时重画；在哪个里面只换样式 */
  let qkHtml = null;
  const paintQk = () => {
    if (!root.isConnected) return window.removeEventListener('galqk', paintQk);
    const bs = !qkOn || !qkHave ? [] : galQkList().map(v => {
      const vt = v.split('/')[0], nm = v.split('/').pop();
      return (v.includes('/') || qkHas(vt)) ? `<button type="button" class="gal-qki gal-qkt" data-qk="${esc(v)}" data-tip="${esc(v.replace(/\//g, ' / '))}" aria-label="${esc(nm)}">${esc(nm)}</button>` : '';
    }).filter(Boolean);
    const html = bs.join('');
    qk.hidden = !bs.length;
    if (qkHtml !== html) { qkHtml = html; qk.innerHTML = html; qk.classList.add('gal-qk-now'); void qk.offsetWidth; setTimeout(() => qk.classList.remove('gal-qk-now'), 30); }  // 刚画好的这一下不放动画
    const cur = qkCur();
    $$('[data-qk]', qk).forEach(x => { const on = x.dataset.qk === cur; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on); });
  };
  const syncQk = paintQk;  // 换了文件夹：重画（展开 / 收起视频 | 图集）
  qk.onclick = e => {
    const x = e.target.closest('[data-qk]'); if (!x) return;
    const v = x.dataset.qk; if (v) goDir(v);
  };
  window.addEventListener('galqk', paintQk);  // 别的窗口 / 页面改了快捷位置
  qk.oncontextmenu = e => {
    const x = e.target.closest('[data-qk]'); if (!x) return;
    const v = x.dataset.qk, L = galQkList(), i = L.indexOf(v);
    ctxMenu(e, [...(i > 0 ? [{ label: '往前移', icon: GAL_IC.back, on: () => { L.splice(i, 1); L.splice(i - 1, 0, v); galQkSave(L); } }] : []),
      ...(i >= 0 && i < L.length - 1 ? [{ label: '往后移', icon: GAL_IC.fwd, on: () => { L.splice(i, 1); L.splice(i + 1, 0, v); galQkSave(L); } }] : []), ...(L.length > 1 ? ['-'] : []),
      { label: '从快捷位置移除', icon: GAL_IC.x, on: () => galQkSave(L.filter(y => y !== v)) }]);
  };
  galLongPress(qk);
  const goDir = rel => {  // 直接到素材库里的一个文件夹（从别的标签过来也行）
    if (multi) setMulti(false);
    if (isF() && F.dir === rel) return;
    mark(); lib = '文件夹'; detail = null; F.dir = rel; F.q = ''; F.tag = ''; syncTop(); refresh();
  };
  if (qkOn) api('/api/mats?dir=' + (o.kind ? '&kind=' + o.kind : '')).then(r => { if (!r.missing && !qkHave) { qkHave = new Set(r.dirs); paintQk(); } }).catch(() => { });
  const opts =(items, k) => k.startsWith('t:') ? GAL_TAGDEF[k.slice(2)].map(x => x[0]).filter(v => items.some(x => galHas(x, k, v))) : [...new Set(items.map(x => x[k]).filter(Boolean))];  // 按原站的顺序
  const sideKeys = () => GAL_SIDE[lib].map(r => r[0]).concat(lib === '姿势' ? ['angle'] : []);
  const active = s => GAL_SIDE[lib].filter(([k]) => s[k]).map(([k]) => [k, s[k]]).concat(lib === '姿势' && s.angle !== '正面' ? [['angle', s.angle === '*' ? '全部角度' : s.angle]] : []);
  const match = (x, s) => {
    const [tk] = GAL_TOP[lib]; if (s[tk] && x[tk] !== s[tk]) return false;
    for (const [k] of GAL_SIDE[lib]) if (s[k] && !galHas(x, k, s[k])) return false;
    const w = s.q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!w.length) return true;
    const hay = [x.rel, x.name, x.keywords, x.zh, x.id, x.style, x.hair, x.cat, x.group, x.angle].filter(Boolean).join(' ').toLowerCase();
    return w.every(t => hay.includes(t));
  };
  const chip = (k, v, on, txt) => `<button type="button" class="gal-chip${on ? ' on' : ''}" data-k="${esc(k)}" data-v="${esc(v)}">${esc(txt || v || '全部')}</button>`;
  const setSide = v => {  // 开 / 关细分类：只切换样式（有动画），图片区不重画
    sideOpen = v; if (!narrow()) localStorage.setItem('galSide', v ? '1' : '0');
    root.classList.toggle('gal-side-on', v); fbtn.classList.toggle('on', v); fbtn.title = v ? '收起细分类' : '打开细分类'; paintT2();
  };
  const syncTop = () => {  // 换库：标签、搜索框、筛选按钮（不整行重画，免得闪）
    $$('[data-lib]', top).forEach(b => b.classList.toggle('on', b.dataset.lib === lib));
    inp.value = isF() ? F.q : st(lib).q;
    fbtn.hidden = isF(); root.classList.toggle('gal-fold', isF());
  };
  const paintT2 = () => {
    syncQk();
    if (!isF() && !GAL.items) return;  // 清单还没读到
    if (isF()) {  // 文件夹：路径
      const cr = F.dir ? F.dir.split('/') : [];
      const acts = !M ? '' : multi ? `<div class="gal-facts"><span class="gal-seln">已选 ${sel.size} 项</span><button type="button" class="btn small" data-fa="all">全选</button>
          <button type="button" class="btn small" data-fa="move"${sel.size ? '' : ' disabled'}>${GAL_FM.move}<span>移动到…</span></button><button type="button" class="btn small" data-fa="batch"${list.some(x => sel.has(x.rel) && x.kind === 'video') ? '' : ' disabled'} title="选中的视频一起按一个配方做（批量页）">${GAL_FM.batch}<span>加入批量</span></button><button type="button" class="btn small gal-fdel" data-fa="del"${sel.size ? '' : ' disabled'}>${CTX_IC.del}<span>删除</span></button><button type="button" class="btn small" data-fa="done">完成</button></div>`
        : `<div class="gal-facts"><button type="button" class="btn small gal-fo gal-ic" data-fa="multi" data-tip="多选" aria-label="多选">${GAL_FM.multi}</button></div>`;
      const so = matsSortGet();
      t2.innerHTML = `<div class="row mats-path gal-path"><button type="button" class="vd-link" data-d="">素材库</button>${cr.map((c, i) => `<span>/</span><button type="button" class="vd-link" data-d="${esc(cr.slice(0, i + 1).join('/'))}" title="${esc(c)}">${esc(c)}</button>`).join('')}</div>${fsrcNow && window.FR_IC ? `<button type="button" class="vd-link fr-from" data-frsrc>${FR_IC.vid}<span>来自视频 · 打开</span></button>` : ''}<span class="gal-n"></span>
        <div class="row gal-fopts"><button type="button" class="btn small gal-fo gal-ic" data-fsort data-tip="排序：${esc(matsSortName(so))}" aria-label="排序：${esc(matsSortName(so))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4v16M3.5 16.5 7 20l3.5-3.5M17 20V4M13.5 7.5 17 4l3.5 3.5"/></svg></button>
          ${F.tag ? `<button type="button" class="gal-tag gal-ftag-on" data-ftagx title="取消 @ 标签筛选">@${esc(F.tag)}${GAL_IC.x}</button>` : ''}<button type="button" class="btn small gal-fo gal-ic" data-ftag data-tip="标签筛选：按文件名开头 @ 到第一个 _ 之间的文字（含子文件夹）" aria-label="标签筛选"><b class="gal-at">@</b></button></div>${acts}`;
      { const fb = $('[data-frsrc]', t2); if (fb) fb.onclick = () => frBackToVideo(fsrcNow, 0); }  // 视频截图的图集：打开来源视频
      $('[data-fsort]', t2).onclick = e => {  // 排序方式（名称 / 添加日期 / 修改日期）+ 顺序；所有文件夹通用
        const cur = MATS_SORTS.find(x => x[0] === matsSortGet()) || MATS_SORTS[0], set = k => { localStorage.setItem('matsSort', k); paintT2(); paint(); };
        const fields = [...new Set(MATS_SORTS.map(x => x[1]))];
        ctxMenu({ anchor: e.currentTarget }, [{ group: '排序方式' }, ...fields.map(f => ({ label: f, checked: cur[1] === f, on: () => set((MATS_SORTS.find(x => x[1] === f && x[2] === cur[2]) || MATS_SORTS.find(x => x[1] === f && (f === '名称' ? /A→Z/.test(x[2]) : x[2] === '最新在前')))[0]) })),
          '-', { group: '顺序' }, ...MATS_SORTS.filter(x => x[1] === cur[1]).map(x => ({ label: x[2], checked: x[0] === cur[0], on: () => set(x[0]) }))]);
      };
      $('[data-ftag]', t2).onclick = e => matsTagPick(e.currentTarget);
      if ($('[data-ftagx]', t2)) $('[data-ftagx]', t2).onclick = () => { mark(); F.tag = ''; paintT2(); paint(); };
      $$('[data-d]', t2).forEach(b => b.onclick = () => { if (b.dataset.d !== F.dir) mark(); F.dir = b.dataset.d; F.q = ''; F.tag = ''; inp.value = ''; paint(); paintT2(); });
      $$('[data-fa]', t2).forEach(b => b.onclick = () => fact(b.dataset.fa));
      return countN();
    }
    const s = st(lib), [tk] = GAL_TOP[lib], tops = opts(GAL.items.filter(x => x.lib === lib), tk), tags = active(s);
    t2.innerHTML = `<div class="gal-ctabs" role="tablist" aria-label="${esc(GAL_TOP[lib][1])}">${['', ...tops].map(v => `<button type="button" role="tab" class="gal-ctab${(s[tk] || '') === v ? ' on' : ''}" aria-selected="${(s[tk] || '') === v}" data-k="${esc(tk)}" data-v="${esc(v)}">${esc(v || '全部')}</button>`).join('')}</div>
      ${!sideOpen && tags.length ? `<div class="gal-tags">${tags.map(([k, v]) => `<button type="button" class="gal-tag" data-rm="${esc(k)}" title="移除此条件">${esc(v)}${GAL_IC.x}</button>`).join('')}</div>` : ''}<span class="gal-n"></span>`;
    $$('.gal-ctab', t2).forEach(b => b.onclick = () => { if ((st(lib)[b.dataset.k] || '') !== b.dataset.v) mark(); pickChip(b.dataset.k, b.dataset.v); });
    $$('[data-rm]', t2).forEach(b => b.onclick = () => pickChip(b.dataset.rm, b.dataset.rm === 'angle' ? '正面' : ''));
    const fn = $('.gal-fn', fbtn); fn.hidden = !tags.length; fn.textContent = tags.length;
    countN();
  };
  const matsTagPick = async btn => {
    let tags; try { tags = (await api('/api/mats/tags?dir=' + encodeURIComponent(F.dir) + (o.kind ? '&kind=' + o.kind : '') + (F.dir ? '' : '&skip=gallery'))).tags || []; } catch (e) { return toast(e.message, true); }
    if (!tags.length) return toast('没有带 @ 标签的文件');
    let by = localStorage.getItem('matsTagBy') === 'name' ? 'name' : 'n';
    popover(btn, `<div class="gal-tp"><div class="row gal-tp-h"><input class="input" type="search" placeholder="搜索标签（共 ${tags.length} 个）" aria-label="搜索标签"><div class="seg gal-tp-by">${[['n', '按数量'], ['name', '按名称']].map(([k, n]) => `<button type="button" data-by="${k}"${by === k ? ' class="on"' : ''}>${n}</button>`).join('')}</div></div><div class="gal-tp-l"></div></div>`, pop => {
      const L = $('.gal-tp-l', pop), q = $('input', pop);
      const draw = () => {
        const w = q.value.trim().toLowerCase(), its = tags.filter(t => !w || t.tag.toLowerCase().includes(w)).sort(by === 'name' ? (a, b) => MATS_COL.compare(a.tag, b.tag) : (a, b) => b.n - a.n || MATS_COL.compare(a.tag, b.tag));
        L.innerHTML = its.length ? its.map(t => `<button type="button" class="gal-tp-i${t.tag === F.tag ? ' on' : ''}" data-t="${esc(t.tag)}"><span>@${esc(t.tag)}</span><span class="tiny">${t.n}</span></button>`).join('') : '<div class="tiny" style="padding:10px">没有匹配的标签</div>';
      };
      draw(); q.oninput = draw; setTimeout(() => q.focus(), 30);
      $$('[data-by]', pop).forEach(b => b.onclick = () => { by = b.dataset.by; localStorage.setItem('matsTagBy', by); $$('[data-by]', pop).forEach(x => x.classList.toggle('on', x === b)); draw(); });
      L.onclick = e => { const it = e.target.closest('[data-t]'); if (!it) return; pop.close(); mark(); F.tag = it.dataset.t; detail = null; paintT2(); paint(); };
    }, { width: 320 });
  };
  const countN = () => { const n = $('.gal-n', t2); if (!n || detail) return; n.textContent = isF() ? (list.length ? `${list.length} 项` : '') : `共 ${list.length} ${lib === '姿势' && st(lib).angle !== '*' ? '个姿势' : '张'}`; };
  const paintSide = () => {
    if (isF()) { side.innerHTML = ''; return; }
    const s = st(lib), [tk] = GAL_TOP[lib], keep = side.scrollTop;
    let sub = GAL.items.filter(x => x.lib === lib && (!s[tk] || x[tk] === s[tk])), html = '';
    const shut = galShut(), dot = (k, v) => k === 't:颜色' && GAL_DOT[v] ? `<i class="gal-dot" style="background:${GAL_DOT[v]}"></i>` : '';
    const cchip = (k, v, txt, g) => `<button type="button" class="gal-chip${(s[k] || '') === v ? ' on' : ''}" data-k="${esc(k)}" data-v="${esc(v)}"${g ? ` data-g="${esc(g)}"` : ''}>${dot(k, v)}${esc(txt || v || '全部')}</button>`;
    const group = (k, nm, inner, sel) => `<div class="gal-grp${shut.has(k) ? ' shut' : ''}" data-gk="${esc(k)}"><button type="button" class="gal-gh" aria-expanded="${!shut.has(k)}"><span class="gal-rn">${esc(nm)}</span>${sel ? `<span class="gal-gsel">${esc(sel)}</span>` : ''}<span class="spacer"></span>${GAL_IC.chev}</button><div class="gal-gb">${inner}</div></div>`;
    for (const [k, nm] of GAL_SIDE[lib]) {  // 选项跟着上面的大类变（例如选了“全身单人·标准”，分类只列它有的）
      const os = opts(sub, k);
      if (s[k] && !os.includes(s[k])) s[k] = '';
      if (os.length > 1) {
        let inner;
        if (lib === '姿势' && k === 'cat' && !s[tk]) {  // 全部类型：分类按类型分开排（点一个分类，上面的类型也跟着选好）
          const by = new Map(); for (const x of sub) { if (!by.has(x.group)) by.set(x.group, new Set()); by.get(x.group).add(x.cat); }
          inner = `<div class="gal-chips">${cchip(k, '')}</div>` + [...by].map(([g, cs]) => `<div class="gal-subh">${esc(g)}</div><div class="gal-chips">${[...cs].map(v => cchip(k, v, v, g)).join('')}</div>`).join('');
        } else {
          const many = os.length > 10 && k !== 't:颜色' && !GAL.more.has(lib + k), show = many ? os.slice(0, 8) : os;
          if (many && s[k] && !show.includes(s[k])) show.push(s[k]);  // 选中的那个一直看得到
          inner = `<div class="gal-chips">${['', ...show].map(v => cchip(k, v)).join('')}${many ? `<button type="button" class="gal-chip gal-morec" data-more="${esc(k)}">更多 ${os.length - show.length} 个</button>` : os.length > 10 ? `<button type="button" class="gal-chip gal-morec" data-less="${esc(k)}">收起</button>` : ''}</div>`;
        }
        html += group(k, nm, inner, s[k]);
      }
      if (s[k] && !k.startsWith('t:')) sub = sub.filter(x => x[k] === s[k]);
    }
    if (lib === '姿势') {
      html += group('angle', '角度', `<div class="gal-chips">${[...GAL_ANGLES, '*'].map(v => `<button type="button" class="gal-chip${s.angle === v ? ' on' : ''}" data-k="angle" data-v="${v}">${v === '*' ? '全部角度' : v}</button>`).join('')}</div>`, s.angle !== '正面' ? (s.angle === '*' ? '全部角度' : s.angle) : '');
      const v = +(localStorage.getItem('galSk') || 0);
      html += group('sk', '线稿底色', `<input type="range" class="gal-sk" min="0" max="100" step="1" value="${v}" aria-label="线稿底色"><div class="gal-skl"><span>白</span><span>灰</span><span>深（反色）</span></div>`);
    }
    side.innerHTML = `<div class="row gal-sh"><b>细分类</b><span class="gal-scope">${esc(s[tk] || '全部' + GAL_TOP[lib][1])}</span><span class="spacer"></span>${active(s).length ? '<button type="button" class="vd-link" data-clear>清除</button>' : ''}<button type="button" class="pl-ib" data-side-x title="收起细分类" aria-label="收起细分类">${GAL_SK_IC.close}</button></div>${html}`;
    side.scrollTop = keep;
    $$('.gal-chip[data-k]', side).forEach(b => b.onclick = () => { if (b.dataset.g) st(lib)[tk] = b.dataset.g; pickChip(b.dataset.k, b.dataset.v); });
    $$('[data-more]', side).forEach(b => b.onclick = () => { GAL.more.add(lib + b.dataset.more); paintSide(); });
    $$('[data-less]', side).forEach(b => b.onclick = () => { GAL.more.delete(lib + b.dataset.less); paintSide(); });
    $$('.gal-gh', side).forEach(b => b.onclick = () => {  // 折叠 / 展开一组：只切换样式，记住
      const g = b.parentElement, k = g.dataset.gk, sh = galShut(), on = !g.classList.toggle('shut');
      if (on) sh.delete(k); else sh.add(k);
      b.setAttribute('aria-expanded', on); localStorage.setItem('galShut', JSON.stringify([...sh]));
    });
    $('[data-side-x]', side).onclick = () => setSide(false);
    const cl = $('[data-clear]', side); if (cl) cl.onclick = () => { for (const k of sideKeys()) s[k] = k === 'angle' ? '正面' : ''; detail = null; refresh(); };
    const sk = $('.gal-sk', side); if (sk) sk.oninput = () => galSkSet(sk.value);
  };
  const pickChip = (k, v) => { st(lib)[k] = v; detail = null; refresh(); };
  const card = (x, i, pose) => {  // pose：姿势卡（点进去看所有角度）；前 24 张马上加载（换筛选时等它们画好再换上，不闪）
    if (pose && !GAL.cnt) { GAL.cnt = new Map(); for (const y of GAL.items) if (y.lib === '姿势') GAL.cnt.set(y.group + '|' + y.pose, (GAL.cnt.get(y.group + '|' + y.pose) || 0) + 1); }
    const n = pose ? GAL.cnt.get(x.group + '|' + x.pose) || 0 : 0;
    const cap = x.lib === '姿势' ? (pose ? `${x.pose} ${x.name}` : `${x.pose} ${x.name} · ${x.angle}`) : x.lib === '衣服' ? x.zh || x.id : [x.hair, x.style].filter(Boolean).join(' · ') || x.cat;
    return `<div class="gal-card" role="button" tabindex="0" data-i="${i}" title="${esc(galLabel(x))}"><div class="gal-im${x.lib === '姿势' ? ' sketch' : ''}"><img ${i < 24 ? '' : 'loading="lazy" '}decoding="async" src="${esc(galThumb(x))}" alt="">
      ${pose ? (n > 1 ? `<span class="gal-badge">${n} 个角度</span>` : '') : o.view ? '' : `<button type="button" class="gal-zoom" data-z="${i}" title="查看大图" aria-label="查看大图">${GAL_IC.zoom}</button>`}</div>
      <div class="gal-cap">${esc(cap)}</div></div>`;
  };
  const fcard = (x, i) => {  // 文件夹里的一项：子文件夹（有封面就显示封面）、图集或文件
    if (x.set) {  // 图集：和一张图一样大的一格，右上角“几张”，有实况的左上角一个实况标记；电脑上鼠标左右划过去翻看
      return `<div class="gal-card gal-set${sel.has(x.rel) ? ' gal-on' : ''}" role="button" tabindex="0" data-i="${i}"${M ? ' draggable="true"' : ''} title="${esc(x.desc || x.name)}"><div class="gal-im gal-fim">${M ? `<span class="gal-ck">${GAL_FM.ck}</span>` : ''}<img ${i < 24 ? '' : 'loading="lazy" '}decoding="async" src="${esc(matsUrl(x.cover) + '?thumb=1')}" alt="">
        ${x.live ? `<span class="gal-stb gal-stb-l" aria-label="含实况">${GAL_SET_IC.live}</span>` : ''}${x.video && window.FR_IC ? `<span class="gal-stb gal-stb-v" aria-label="来自视频" data-tip="视频截图">${FR_IC.vid}</span>` : ''}<span class="gal-stb gal-stb-n" aria-label="${x.n} 张">${GAL_SET_IC.stack}${x.n}</span>${x.n > 1 ? `<button type="button" class="gal-sarr" data-sa="-1" tabindex="-1" aria-label="上一张" hidden>${GAL_IC.back}</button><button type="button" class="gal-sarr gal-sarr-r" data-sa="1" tabindex="-1" aria-label="下一张">${GAL_IC.back}</button><span class="gal-dots" aria-hidden="true">${galDots(x.n, 0)}</span>` : ''}
        <button type="button" class="gl-del gal-del" data-del="${i}" title="删除（移到回收站）" aria-label="删除"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg></button></div>
        <div class="gal-cap">${esc(x.name)}</div></div>`;
    }
    if (x.dir) {
      const g = x.rel === 'gallery';
      return `<div class="gal-card gal-fd${sel.has(x.rel) ? ' gal-on' : ''}" role="button" tabindex="0" data-i="${i}"${M ? ' draggable="true"' : ''} title="${esc(x.name)}"><div class="gal-im gal-fim">${M ? `<span class="gal-ck">${GAL_FM.ck}</span>` : ''}${x.cover ? `<img ${i < 24 ? '' : 'loading="lazy" '}src="${esc(matsUrl(x.cover) + '?thumb=1')}" alt="">` : GAL_IC.folder}</div>
        <div class="gal-cap">${esc(g ? 'gallery · 姿势 / 衣服 / 脸' : x.name)}</div></div>`;
    }
    const sk = /^gallery\/姿势\//.test(x.rel);
    const th = x.kind === 'image' ? `<img ${i < 24 ? '' : 'loading="lazy" '}decoding="async" src="${esc(galFThumb(x))}" alt="">${x.live ? `<span class="gal-stb gal-stb-l" aria-label="实况">${GAL_SET_IC.live}</span>` : ''}` : x.kind === 'video' ? `<img class="gal-vth" ${i < 18 ? '' : 'loading="lazy" '}decoding="async" src="${esc(galFThumb(x))}" data-vsrc="${esc(matsUrl(x.rel))}" alt=""><button type="button" class="gal-play" data-p="${i}" title="在这里预览" aria-label="预览视频">${GAL_IC.play}</button><span class="gal-prog"></span>${x.nframes && window.FR_IC ? `<span class="gal-stb gal-stb-f" aria-label="截图 ${x.nframes} 张" data-tip="截过 ${x.nframes} 张">${FR_IC.cam}${x.nframes}</span>` : ''}` : `<span class="gal-au">${GAL_SK_IC.audio}</span>`;
    return `<div class="gal-card${sel.has(x.rel) ? ' gal-on' : ''}" role="button" tabindex="0" data-i="${i}"${M ? ' draggable="true"' : ''} title="${esc(x.label || x.name)}"><div class="gal-im gal-fim${sk ? ' sketch' : ''}">${M ? `<span class="gal-ck">${GAL_FM.ck}</span>` : ''}${th}${x.kind === 'image' && !o.view ? `<button type="button" class="gal-zoom" data-z="${i}" title="查看大图" aria-label="查看大图">${GAL_IC.zoom}</button>` : ''}<button type="button" class="gl-del gal-del" data-del="${i}" title="删除（移到回收站）" aria-label="删除"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg></button></div>
      <div class="gal-cap">${esc(x.label || x.name)}</div></div>`;
  };
  const more = () => {  // 一次加 120 张，滚到底再加
    const g = $('.gal-grid', body); if (!g) return;
    const pose = lib === '姿势' && st(lib).angle !== '*';
    g.insertAdjacentHTML('beforeend', list.slice(shown, shown + 120).map((x, k) => isF() ? fcard(x, shown + k) : card(x, shown + k, pose)).join(''));
    shown = Math.min(list.length, shown + 120);
    const m = $('.gal-more', body); if (m) m.hidden = shown >= list.length;
  };
  const swap = (my, html, after) => {  // 新内容先在后台画好（前面的图解码完，最多等 0.4 秒）再一次换上：换筛选时不闪白
    const tmp = document.createElement('div'); tmp.innerHTML = html;
    const ims = [...tmp.querySelectorAll('img')].slice(0, 24);
    Promise.race([Promise.all(ims.map(im => im.decode().catch(() => { }))), new Promise(r => setTimeout(r, 120))]).then(() => {  // 最多等 0.12 秒（以前 0.4 秒：小图不缓存时几乎每次都等满，点了像没反应，2026-11-11）
      if (my !== tok || !root.isConnected) return;
      io?.disconnect(); body.replaceChildren(...tmp.childNodes); body.scrollTop = 0; $$('.gal-fim > img', body).forEach(t => t.complete && !t.closest('.gal-fd') && galVthMark(t)); after?.();
    });
  };
  const grid = (my, big) => swap(my, list.length ? `<div class="gal-grid${big ? ' gal-big' : ''}${isF() && o.kind === 'video' ? ' gal-vgrid' : ''}">${list.slice(0, 120).map((x, k) => isF() ? fcard(x, k) : card(x, k, lib === '姿势' && st(lib).angle !== '*')).join('')}</div><div class="gal-more"${list.length > 120 ? '' : ' hidden'}><button type="button" class="btn small">显示更多</button></div>`
    : `<div class="gal-wait">${isF() ? (F.q || F.tag ? '无匹配结果' : '文件夹为空') : '没有符合条件的素材'}</div>`, () => {
    shown = Math.min(120, list.length);
    const m = $('.gal-more', body); if (!m) return;
    $('button', m).onclick = more;
    io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) more(); }, { root: body, rootMargin: '600px' }); io.observe(m);
  });
  const paint = async () => {
    const my = ++tok, s = st(lib);
    root.classList.toggle('gal-detail', !!detail);
    if (detail) {  // 一个姿势的所有角度：大图
      list = GAL.items.filter(x => x.lib === '姿势' && x.group === detail.group && x.pose === detail.pose).sort((a, b) => GAL_ANGLES.indexOf(a.angle) - GAL_ANGLES.indexOf(b.angle));
      return swap(my, `<div class="row gal-dh"><button type="button" class="btn small" data-back>${GAL_IC.back}返回</button><b>${esc(detail.pose)} ${esc(detail.name)}</b><span class="gal-sub">${esc(detail.group)} · ${esc(detail.cat)} · 请选择一个角度${o.detail ? '查看' : '选用'}</span></div>
        <div class="gal-grid gal-big">${list.map((x, i) => `<div class="gal-card" role="button" tabindex="0" data-i="${i}" title="${esc(galLabel(x))}"><div class="gal-im sketch"><img decoding="async" src="${esc(matsUrl(x.rel))}" alt="">
          ${o.view ? '' : `<button type="button" class="gal-zoom" data-z="${i}" title="查看大图" aria-label="查看大图">${GAL_IC.zoom}</button>`}</div><div class="gal-cap">${esc(x.angle)}</div></div>`).join('')}</div>`,
      () => { $('[data-back]', body).onclick = () => { mark(); detail = null; paint(); }; });
    }
    if (isF()) {  // 文件夹：后台列出来（同一个文件夹记住，来回切不再等）
      const key = F.dir + '|' + F.q + '|' + (F.tag || '');
      let r = fcache.get(key);
      if (!r) {
        try { r = await api('/api/mats?dir=' + encodeURIComponent(F.dir) + (o.kind ? '&kind=' + o.kind : '') + (F.tag ? '&tag=' + encodeURIComponent(F.tag) + (F.dir ? '' : '&skip=gallery') : '') + (F.q ? '&q=' + encodeURIComponent(F.q) + (F.dir ? '' : '&skip=gallery') : '')); } catch (e) { if (my === tok) body.innerHTML = `<div class="gal-wait">${esc(e.message)}</div>`; return; }
        if (r.missing && F.dir) { const L = galQkList(); if (L.includes(F.dir)) { galQkSave(L.filter(v => v !== F.dir)); toast(`找不到「${F.dir.split('/').pop()}」，已从快捷位置移除`); } F.dir = ''; paintT2(); return paint(); }
        fcache.set(key, r);
      }
      if (my !== tok) return;
      if (r.missing) { list = []; body.innerHTML = `<div class="gal-wait">尚未创建素材库文件夹：${esc(r.root)}</div>`; return; }
      if (r.dir !== F.dir) { F.dir = r.dir; paintT2(); }
      { const fv = r.set ? ((r.files || []).find(x => x.fsrc) || {}).fsrc || null : null; if (JSON.stringify(fv) !== JSON.stringify(fsrcNow)) { fsrcNow = fv; paintT2(); } }
      if (fkey !== F.dir + '|' + F.q) { fkey = F.dir + '|' + F.q; if (sel.size) { sel.clear(); paintT2(); } }
      const cov = r.covers || {};  // 根目录不列 gallery：它已经有自己的“姿势 / 衣服 / 脸”标签
      list = matsSort(r.dirs.filter(d => r.dir || d !== 'gallery').map(d => ({ dir: true, name: d, rel: (r.dir ? r.dir + '/' : '') + d, cover: cov[d] })).concat(r.files), r.set ? 'name' : matsSortGet(), r.dirs_added || {});  // 图集里：按作品里的顺序（01、02…），不跟排序走
      if (!r.dir && !r.search && !r.tag) {  // 根目录：快捷位置跟着更新
        if (qkOn && (!qkHave || [...qkHave].join('/') !== r.dirs.join('/'))) { qkHave = new Set(r.dirs); paintQk(); }
      }
      countN();
      return grid(my);
    }
    const all = GAL.items.filter(x => x.lib === lib && match(x, s));
    if (lib === '姿势' && s.angle !== '*') {  // 一个姿势一张：选的角度；这个姿势没有这个角度就用它的第一张
      const by = new Map();
      for (const x of all) { const k = x.group + '|' + x.pose, c = by.get(k); if (!c || (x.angle === s.angle && c.angle !== s.angle)) by.set(k, x); }
      list = [...by.values()];
    } else list = all;
    countN();
    grid(my);
  };
  const refresh = () => { paintT2(); paintSide(); paint(); };
  root._galRefresh = () => { if (!root.isConnected) return; fcache.clear(); if (isF()) paint(); };  // 视频截图存好了：文件夹重新读（frames.js）
  const setLib = l => { mark(); if (multi) setMulti(false); lib = l; if (!isF()) GAL.lastLib = l; detail = null; syncTop(); refresh(); };
  $$('[data-lib]', top).forEach(b => b.onclick = () => { if (b.dataset.lib !== lib) setLib(b.dataset.lib); });
  fbtn.onclick = () => setSide(!sideOpen);
  scrim.onclick = () => setSide(false);
  let tm = 0;
  // 手机：搜索平时是一个图标，点开盖住这一行；点别处就收回（有搜索词时图标是蓝的）（2026-11-07）
  const qb = $('.gal-qbtn', root), qOpen = v => { root.classList.toggle('gal-qon', v); qb.classList.toggle('on', !!inp.value.trim()); };
  qb.onclick = () => { qOpen(true); inp.focus(); };
  inp.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== inp) qOpen(false); }, 120));  // 有搜索词时图标变蓝，表示正在筛选
  inp.onkeydown = e => { if (e.key === 'Escape') { inp.value = ''; inp.dispatchEvent(new Event('input')); inp.blur(); } };
  inp.oninput = () => { clearTimeout(tm); tm = setTimeout(() => { const v = inp.value.trim(); if (isF()) F.q = v; else st(lib).q = v; detail = null; paint(); }, 220); };
  o.onExtra?.(top);
  body.onclick = e => {
    const sa = e.target.closest('[data-sa]');
    if (sa) { e.stopPropagation(); return setFlip(sa.closest('.gal-set'), +sa.dataset.sa); }
    const dl = e.target.closest('[data-del]');
    if (dl) { e.stopPropagation(); const x = list[+dl.dataset.del]; if (x) delDlg([x.rel]); return; }  // 2026-11-08 用户：选素材的窗口里也能直接删
    const z = e.target.closest('[data-z]');
    if (z) {
      e.stopPropagation(); const imgs = list.filter(x => !x.dir && !x.set && (x.kind || 'image') === 'image'), k = Math.max(0, imgs.indexOf(list[+z.dataset.z]));
      if (imgs.some(x => x.live)) return ImageViewer.open(imgs.map(x => ({ src: matsUrl(x.rel), thumb: matsUrl(x.rel) + '?thumb=1', name: x.label || x.name, live: x.live ? matsUrl(x.live) : '' })), k);  // 图集里：实况按住播放
      return zoomImgs(imgs.map(x => matsUrl(x.rel)), k);
    }
    const pb = e.target.closest('[data-p]');
    if (pb) { e.stopPropagation(); return galPrev(pb); }
    const c = e.target.closest('.gal-card'); if (!c) return;
    const x = list[+c.dataset.i]; if (!x) return;
    if (isF()) {
      if (M && (multi || e.ctrlKey || e.metaKey)) { if (!multi) setMulti(true); return toggle(x.rel, c); }
      return openF(x);
    }
    if (lib === '姿势' && !detail && st(lib).angle !== '*') { mark(); detail = x; return paint(); }
    if (o.view && (x.kind || 'image') === 'image') return viewAt(x);
    if (o.detail) return o.detail(x, x.lib === '姿势' ? GAL.items.filter(y => y.lib === '姿势' && y.group === x.group && y.pose === x.pose).sort((a, b) => GAL_ANGLES.indexOf(a.angle) - GAL_ANGLES.indexOf(b.angle)) : null);
    o.pick?.(x);
  };
  /* 图集格子翻看（2026-11-15 第三版，用户：滚轮切换不丝滑）：参照 Embla Carousel + wheel-gestures 插件、iOS 的分页滚动——
     格子里是一条 [上一张 | 这一张 | 下一张] 的胶片（鼠标停上来就先摆好、读好图，第一下不闪）：
     · 触控板：图片跟着手指走，旁边一张跟着露出来；过了一半就换到那一张，松手吸到位；一次滑动最多翻一张，到头了是橡皮筋（越拉越拉不动）
     · 鼠标滚轮一格 / 箭头 / ← →：滑过去一张（0.32 秒）；还在滑的时候再滚一格，从现在的位置接着滑，不跳
     · 减少动态效果：直接换图，没有滑动 */
  const RM = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const thumbOf = (x, k) => x.items[k] ? matsUrl(x.items[k].rel) + '?thumb=1' : '';
  function flipTrack(c) {  // 胶片：三格，中间那格是正在看的；跟着 c.dataset.k
    const x = c && list[+c.dataset.i]; if (!x?.items) return null;
    const im = $('.gal-im', c); let t = c._trk;
    if (!t || !t.isConnected) {
      t = document.createElement('div'); t.className = 'gal-trk'; t.setAttribute('aria-hidden', 'true');
      const cov = $(':scope > img', im);
      for (let j = 0; j < 3; j++) { const i = document.createElement('img'); i.alt = ''; i.decoding = 'async'; t.append(i); }
      im.insertBefore(t, cov || im.firstChild); if (cov) cov.remove();
      c._trk = t; t._off = 0;
    }
    const k = +c.dataset.k || 0, [a, b, d] = t.children;
    [[a, k - 1], [b, k], [d, k + 1]].forEach(([el, j]) => { const u = thumbOf(x, j); if (el.getAttribute('src') !== u) { if (u) el.src = u; else el.removeAttribute('src'); } el.style.visibility = u ? '' : 'hidden'; });
    return t;
  }
  const trkW = t => t.parentElement.clientWidth || 1;
  const trkSet = (t, off, ms) => {  // 摆到 off（像素，0 = 正中那张）；ms > 0 有滑动
    t._off = off; t._tEnd = performance.now() + (ms || 0); t.style.transition = ms ? `transform ${ms}ms cubic-bezier(.22, .8, .24, 1)` : 'none';
    t.style.transform = `translate3d(${(-trkW(t) + off).toFixed(1)}px, 0, 0)`;
  };
  const trkNow = t => { if (performance.now() >= (t._tEnd || 0)) return t._off; const m = new DOMMatrixReadOnly(getComputedStyle(t).transform); return m.m41 + trkW(t); };  // 正在滑的半路上：现在实际在哪（滑完了就是终点）
  function flipShift(c, d) {  // 换到旁边一张（d = ±1）：胶片挪一格，看起来位置不变（off 补一整格）
    const x = list[+c.dataset.i], t = c._trk, k = (+c.dataset.k || 0) + d;
    c.dataset.k = k; const w = trkW(t), cur = t.style.transition === 'none' ? t._off : trkNow(t);
    flipTrack(c); trkSet(t, cur + d * w, 0);
    if (x.items[k + 2 * d]) new Image().src = thumbOf(x, k + 2 * d);  // 再下一张先读好
    $('.gal-dots', c).innerHTML = galDots(x.n, k);
    const [l, r] = $$('[data-sa]', c); l.hidden = k === 0; r.hidden = k === x.n - 1;
    const mid = t.children[1]; if (mid.complete) galVthMark(mid);  // 光晕 / 铺满跟着正中那张
  }
  function setFlip(c, d) {  // 一下一张（滚轮一格、箭头、← →）
    const x = c && list[+c.dataset.i]; if (!x?.items) return;
    const k = (+c.dataset.k || 0) + d, t = flipTrack(c);
    if (k < 0 || k >= x.n) {  // 到头了：往那边轻轻弹一下再回来
      if (RM() || t._bump) return; t._bump = 1; trkSet(t, -d * Math.min(26, trkW(t) * .12), 110); setTimeout(() => { trkSet(t, 0, 260); t._bump = 0; }, 110); return; }
    flipShift(c, d);
    if (RM()) return trkSet(t, 0, 0);
    void t.offsetWidth; trkSet(t, 0, 320);
  }
  /* 滚轮：一次滚动手势归它开始的地方（scroll latching）——在图集的图上开始滚 = 翻它（上下、左右都行），在别处开始滚 = 滚页面、途中不被抢走 */
  let gEnd = 0, gFlip = null, gN = 0, gLast = 0, gSnap = 0, gDir = 0, gNew = false;
  const rubber = (v, w) => Math.sign(v) * w * .16 * (1 - 1 / (Math.abs(v) / (w * .5) + 1));  // 越拉越拉不动，最多约 16%
  body.addEventListener('wheel', e => {
    const now = performance.now();
    if (now > gEnd) {  // 新的一次手势：看它从哪里开始
      const c = e.target.closest?.('.gal-set');
      gFlip = c && !multi && e.target.closest('.gal-im') && c.querySelector('[data-sa]') ? c : null; gN = 0; gDir = 0; gNew = true;
      if (gFlip) gFlip._raw = 0;
    }
    gEnd = now + 160;
    if (!gFlip || !gFlip.isConnected) return;  // 滚页面
    e.preventDefault();  // 也挡住浏览器的“左右滑 = 后退”
    const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY; if (!d) return;
    const c = gFlip, x = list[+c.dataset.i], t = flipTrack(c); if (!t) return;
    const notch = e.deltaMode === 1 || (Math.abs(d) >= 100 && Number.isInteger(d));  // 鼠标滚轮一格（触控板是一串小的数）
    clearTimeout(gSnap);
    if (notch) { if (now - gLast < 70) return; gLast = now; return setFlip(c, d > 0 ? 1 : -1); }
    if (RM()) { c._raw += d; if (Math.abs(c._raw) > 80 && !gN) { gN = 1; setFlip(c, d > 0 ? 1 : -1); } return; }
    // 触控板：跟手。pos = 手指带着走到哪了（没加橡皮筋的原始位置，像素；负 = 往下一张那边）
    const w = trkW(t);
    if (gNew) { gNew = false; t._pos = t.style.transition === 'none' ? t._off : trkNow(t); }  // 这次手势刚开始：从现在实际的位置接着走（可能还在吸附的半路上）
    t._pos -= d;
    const k = +c.dataset.k || 0, can = s => s > 0 ? k < x.n - 1 : k > 0;
    if (!gN && Math.abs(t._pos) > w / 2 && can(t._pos < 0 ? 1 : -1)) { const s = t._pos < 0 ? 1 : -1; gN = 1; gDir = s; t._pos += s * w; flipShift(c, s); }  // 过了一半：换到那一张
    const k2 = +c.dataset.k || 0, can2 = s => s > 0 ? k2 < x.n - 1 : k2 > 0, stop = s => !can2(s) || (gN && s === gDir);  // 这边不能再翻：到头了，或这次已经翻过一张
    const p = t._pos, off = p < 0 && stop(1) ? rubber(p, w) : p > 0 && stop(-1) ? rubber(p, w) : p;
    trkSet(t, off, 0);
    gSnap = setTimeout(() => trkSet(t, 0, 300), 150);  // 停手：吸到正中那张
  }, { passive: false });
  body.addEventListener('pointerover', e => { const c = e.target.closest?.('.gal-set'); if (c && !c._trk && !multi) flipTrack(c); });  // 鼠标停上来：先摆好胶片、读好旁边两张
  body.onkeydown = e => {
    if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && e.target.classList.contains('gal-set')) { e.preventDefault(); return setFlip(e.target, e.key === 'ArrowLeft' ? -1 : 1); }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('gal-card')) { e.preventDefault(); e.target.click(); }
  };
  /* ---------- 文件夹整理（素材库页面）：拖到文件夹 / 路径上 = 移动；右键 / 长按菜单；多选；新建文件夹；删除 = 进回收站 ---------- */
  function openF(x) {
    if (x.set) { mark(); F.dir = x.rel; F.q = ''; F.tag = ''; inp.value = ''; paintT2(); return paint(); }  // 图集：和文件夹一样点进去（素材库页面和选素材时一样，2026-11-15 用户）；里面的放大键左右翻、实况按住播放
    if (x.dir) { if (x.rel === 'gallery' && libs.includes('姿势')) return setLib('姿势'); mark(); F.dir = x.rel; F.q = ''; F.tag = ''; inp.value = ''; paintT2(); return paint(); }
    if (o.view && (x.kind || 'image') === 'image') return viewAt(x);
    return o.pickFile?.(x);
  }
  /* o.view(files, k)：素材库页面点一张图 → 直接看大图（同一页的图左右翻；姿势的角度页 = 这一组的各个角度）（2026-11-15 用户：不要中间那层详情） */
  function viewAt(x) {
    const imgs = list.filter(y => !y.dir && !y.set && (y.kind || 'image') === 'image');
    return o.view(imgs.map(y => isF() ? y : galFile(y)), Math.max(0, imgs.indexOf(x)));
  }
  function setMulti(v) {
    multi = v; if (!v) { sel.clear(); $$('.gal-card.gal-on', body).forEach(c => c.classList.remove('gal-on')); }
    root.classList.toggle('gal-multi', v); paintT2();
  }
  function toggle(rel, c) { sel.has(rel) ? sel.delete(rel) : sel.add(rel); c?.classList.toggle('gal-on', sel.has(rel)); paintT2(); }
  const fname = r => r ? r.split('/').pop() : '素材库';
  const reload = () => { fcache.clear(); if (multi) setMulti(false); else sel.clear(); paint(); paintT2(); };
  async function moveTo(items, to) {
    if (!items.length) return;
    try { const r = await api('/api/mats/move', { body: { items, to } }); toast(r.n ? `已将 ${r.n} 项移到「${fname(to)}」` : '这些项目已在该文件夹中'); } catch (e) { return toast(e.message, true); }
    reload();
  }
  function moveDlg(items) {
    const box = modal(`<div class="row gal-head"><h3 class="card-title" style="margin:0">将 ${items.length} 项移动到</h3><span class="spacer"></span><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
      <div class="gal-mvl"><div class="gal-wait">正在读取文件夹…</div></div>`);
    box.classList.add('gal-mvm');
    api('/api/mats/dirs').then(r => {
      const bad = d => items.some(x => d === x || d.startsWith(x + '/'));  // 不能移到自己里面
      const here = !F.q && items.every(x => x.split('/').slice(0, -1).join('/') === F.dir);
      $('.gal-mvl', box).innerHTML = [''].concat(r.dirs).filter(d => !bad(d)).map(d => {
        const cur = here && d === F.dir;
        return `<button type="button" class="gal-mvi" data-to="${esc(d)}"${cur ? ' disabled' : ''} style="padding-left:${12 + (d ? d.split('/').length : 0) * 18}px">${GAL_IC.folder}<span>${esc(d ? fname(d) : '素材库（根目录）')}</span>${cur ? '<small>当前位置</small>' : ''}</button>`;
      }).join('');
      $$('[data-to]', box).forEach(b => b.onclick = () => { box.close(); moveTo(items, b.dataset.to); });
    }).catch(e => { $('.gal-mvl', box).innerHTML = `<div class="gal-wait">${esc(e.message)}</div>`; });
  }
  function delDlg(items) {
    const xs = items.map(r => list.find(x => x.rel === r) || { rel: r, name: fname(r) }), nd = xs.filter(x => x.dir).length, nf = xs.length - nd;
    const what = xs.length === 1 ? `${nd ? '文件夹' : ''}「${esc(xs[0].name)}」` : ' ' + [nf ? `${nf} 个文件` : '', nd ? `${nd} 个文件夹` : ''].filter(Boolean).join('和 ') + ' ';
    modal(`<h3 class="card-title" style="margin:0 0 8px">将${what}移到回收站？</h3>
      <div class="tiny" style="line-height:1.7">${nd ? '文件夹中的所有内容将一并移走。' : ''}如有需要，可从 Windows 回收站中还原。</div>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:18px"><button class="btn" data-close>取消</button><button class="btn del-solid" data-ok>${CTX_IC.del}移到回收站</button></div>`, box => {
      const ok = $('[data-ok]', box); setTimeout(() => ok.focus(), 30);
      ok.onclick = async () => {
        ok.disabled = true;
        try { const r = await api('/api/mats/delete', { body: { items } }); toast(`已将 ${r.n} 项移到回收站`); } catch (e) { toast(e.message, true); }
        box.close(); reload();
      };
    });
  }
  function mkDlg() {
    modal(`<h3 class="card-title" style="margin:0 0 12px">新建文件夹</h3><div class="tiny" style="margin-bottom:10px">位置：${esc(F.dir ? '素材库 / ' + F.dir.split('/').join(' / ') : '素材库')}</div>
      <input class="input" data-nm placeholder="文件夹名称" aria-label="文件夹名称" style="width:100%" maxlength="80">
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:16px"><button class="btn" data-close>取消</button><button class="btn primary" data-ok>新建</button></div>`, box => {
      const nm = $('[data-nm]', box), ok = $('[data-ok]', box); setTimeout(() => nm.focus(), 30);
      const make = async () => {
        const name = nm.value.trim(); if (!name) return nm.focus();
        ok.disabled = true;
        try { await api('/api/mats/mkdir', { body: { dir: F.dir, name } }); box.close(); toast(`已新建文件夹「${name}」`); reload(); } catch (e) { ok.disabled = false; toast(e.message, true); }
      };
      ok.onclick = make; nm.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); make(); } };
    });
  }
  function fact(a) {
    if (a === 'mk') return mkDlg();
    if (a === 'multi') return setMulti(true);
    if (a === 'done') return setMulti(false);
    if (a === 'all') { const all = list.every(x => sel.has(x.rel)); list.forEach(x => all ? sel.delete(x.rel) : sel.add(x.rel)); $$('.gal-card', body).forEach(c => c.classList.toggle('gal-on', sel.has(list[+c.dataset.i]?.rel))); return paintT2(); }
    if (a === 'move') return sel.size && moveDlg([...sel]);
    if (a === 'del') return sel.size && delDlg([...sel]);
    if (a === 'batch') { const v = list.filter(x => sel.has(x.rel) && x.kind === 'video').map(x => ({ rel: x.rel, name: x.label || x.name })); if (!v.length) return toast('选中的里面没有视频', true); setMulti(false); return window.batchAdd?.(v); }
  }
  if (M) {
    const qkItem = rel => {  // 右键菜单里的“加到快捷位置 / 从快捷位置移除”
      const k = galQkKey(rel), L = galQkList(), on = L.includes(k);
      return { label: on ? '从快捷位置移除' : '加到快捷位置', icon: GAL_IC.pin, on: () => { galQkSave(on ? L.filter(v => v !== k) : [...L, k]); toast(on ? '已从快捷位置移除' : '已加到快捷位置'); } };
    };
    body.oncontextmenu = e => {
      if (!isF()) return;
      const c = e.target.closest('.gal-card'), x = c && list[+c.dataset.i];
      if (!x) return ctxMenu(e, [{ label: '新建文件夹…', icon: GAL_FM.newf, on: mkDlg }, ...(F.dir && !F.q && !F.tag ? [qkItem(F.dir)] : []), { label: multi ? '退出多选' : '多选', icon: GAL_FM.multi, on: () => setMulti(!multi) }]);
      if (multi && !sel.has(x.rel)) toggle(x.rel, c);  // 多选时右键没选中的那项：把它也选上
      const items = multi ? [...sel] : [x.rel], n = items.length;
      const up = F.dir && !F.q ? F.dir.split('/').slice(0, -1).join('/') : null;
      const useIt = n === 1 && !multi && o.use && !x.dir && !x.set && (x.kind || 'image') === 'image' ? [...o.use(x), '-'] : [];
      const frIt = n === 1 && !multi && typeof frCardMenu === 'function' ? frCardMenu(x) : [];  // 视频截图：截取画面… / 查看截图 / 打开来源视频
      const menu = [...useIt, ...(n === 1 ? [{ label: '打开', icon: CTX_IC.open, on: () => openF(x) }] : []), ...frIt,
        ...(n === 1 && x.dir && x.rel !== 'gallery' ? [qkItem(x.rel)] : []),
        ...(multi ? [] : [{ label: '多选', icon: GAL_FM.multi, on: () => { setMulti(true); toggle(x.rel, c); } }]), '-',
        { label: n > 1 ? `移动 ${n} 项到…` : '移动到…', icon: GAL_FM.move, on: () => moveDlg(items) },
        ...(up !== null ? [{ label: `移出到上一层（${fname(up)}）`, icon: GAL_FM.up, on: () => moveTo(items, up) }] : []), '-',
        { label: n > 1 ? `删除 ${n} 项…` : x.dir ? '删除文件夹…' : x.set ? '删除这组图…' : '删除…', icon: CTX_IC.del, danger: true, on: () => delDlg(items) }];
      while (menu[0] === '-') menu.shift();
      ctxMenu(e, menu);
    };
    let lt = 0, lx = 0, ly = 0, lfired = false;  // 手机：长按 0.5 秒 = 右键菜单（松手那一下不算点击）
    body.addEventListener('touchstart', e => {
      lfired = false; clearTimeout(lt);
      if (!isF() || e.touches.length !== 1) return;
      const p = e.touches[0]; lx = p.clientX; ly = p.clientY;
      lt = setTimeout(() => { lfired = true; e.target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: lx, clientY: ly })); }, 500);
    }, { passive: true });
    body.addEventListener('touchmove', e => { const p = e.touches[0]; if (p && Math.hypot(p.clientX - lx, p.clientY - ly) > 10) clearTimeout(lt); }, { passive: true });
    body.addEventListener('touchend', () => clearTimeout(lt), { passive: true });
    body.addEventListener('click', e => { if (lfired) { lfired = false; e.preventDefault(); e.stopPropagation(); } }, true);
    const dropAt = e => {  // 拖到哪里：文件夹卡片，或上面路径里的一层
      if (!drag) return null;
      const t = e.target.closest?.('.gal-fd, .gal-path [data-d]'); if (!t || !root.contains(t)) return null;
      const to = t.dataset.d ?? list[+t.dataset.i]?.rel;
      if (to == null || (to === F.dir && !F.q) || drag.some(r => to === r || to.startsWith(r + '/'))) return null;
      return [t, to];
    };
    body.addEventListener('dragstart', e => {
      const c = e.target.closest?.('.gal-card[draggable]'), x = c && list[+c.dataset.i]; if (!x || !isF()) return;
      drag = multi && sel.has(x.rel) ? [...sel] : [x.rel];
      e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('application/x-mats', JSON.stringify(drag));
      if (drag.length > 1) { const g = document.createElement('div'); g.className = 'gal-dragn'; g.textContent = `${drag.length} 项`; document.body.append(g); e.dataTransfer.setDragImage(g, 24, 18); setTimeout(() => g.remove()); }
      (multi && sel.has(x.rel) ? $$('.gal-card.gal-on', body) : [c]).forEach(k => k.classList.add('gal-dragging'));
    });
    root.addEventListener('dragover', e => {
      const h = dropAt(e);
      $$('.gal-drop', root).forEach(k => k !== h?.[0] && k.classList.remove('gal-drop'));
      if (!h) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; h[0].classList.add('gal-drop');
    });
    root.addEventListener('drop', e => { const h = dropAt(e); if (!h) return; e.preventDefault(); const items = drag; drag = null; moveTo(items, h[1]); });
    root.addEventListener('dragend', () => { drag = null; $$('.gal-dragging, .gal-drop', root).forEach(k => k.classList.remove('gal-dragging', 'gal-drop')); });
  }
  const ro = new ResizeObserver(() => { if (!root.isConnected) return ro.disconnect(); const nw = narrow(); if (nw !== root.classList.contains('gal-narrow')) { root.classList.toggle('gal-narrow', nw); if (nw && sideOpen) setSide(false); } });
  ro.observe(root);
  root.classList.toggle('gal-narrow', narrow()); root.classList.add('gal-noanim'); setSide(sideOpen); syncTop();
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('gal-noanim')));  // 打开时不放侧栏动画
  const ready = galItems().then(items => {
    if (!root.isConnected) return;
    if (!items.length && !isF()) { body.innerHTML = '<div class="gal-wait">还没有姿势、衣服或脸的素材。可以在“文件夹”里放入图片。</div>'; return; }
    refresh();
  }).catch(e => { if (root.isConnected) body.innerHTML = `<div class="gal-wait">无法读取素材清单：${esc(e.message)}</div>`; });
  return { stop: () => { io?.disconnect(); ro.disconnect(); $$('video', body).forEach(v => v.pause()); }, ready };
}

/* 选图弹窗。o.combo：上面一行加“角色组合”按钮（点了关掉这个弹窗、开始依次选姿势 → 衣服 → 脸）；o.folders 默认有（素材库里别的文件夹），o.lock 时没有 */
function galPick(fn, o = {}) {
  let done = false, g = null;
  const alt = o.alt || window.MATS_ALT || []; window.MATS_ALT = null;  // 别的来源（从电脑选、从视频库选…）：点空的素材格直接打开这里时放在右上角（slotPick）
  const box = modal(`<div class="row gal-head"><h3 class="card-title" style="margin:0">${esc(o.title || '从素材库选择' + ({ video: '视频', audio: '声音' }[o.kind] || '图片'))}</h3><span class="spacer"></span>
      ${MOB() && alt.length ? `<button type="button" class="pl-ib gal-alt-more" aria-label="其他来源" title="其他来源"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg></button>`  /* 手机：其他来源收进“···”（2026-11-16） */
        : alt.map((a, i) => `<button type="button" class="btn small ghost gal-alt" data-alt="${i}">${a.icon || ''}<span>${esc(a.label)}</span></button>`).join('')}
      ${o.skip ? `<button type="button" class="btn small" data-skip>${esc(o.skip)}</button>` : ''}<button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    ${o.note ? `<div class="gal-note">${esc(o.note)}</div>` : ''}<div class="gal-host"></div>`, null, true);
  box.classList.add('gal-m');
  const finish = x => { done = true; g?.stop(); box.close(); fn(x); };
  const c0 = box.close; box.close = () => { c0(); g?.stop(); if (!done) { done = true; o.onCancel?.(); } }; $$('[data-close]', box).forEach(b => b.onclick = box.close);
  const sk = $('[data-skip]', box); if (sk) sk.onclick = () => finish(null);
  $$('[data-alt]', box).forEach(b => b.onclick = () => { done = true; g?.stop(); box.close(); alt[+b.dataset.alt].on(); });
  const am = $('.gal-alt-more', box); if (am) am.onclick = () => ctxMenu({ anchor: am }, alt.map(a => ({ ...a, label: a.label === '从电脑选择' ? '照片或文件' : a.label, on: () => { done = true; g?.stop(); box.close(); a.on(); } })));  // 点选项：关掉素材库、换成那个来源（选文件要在这一下点击里直接打开）  // 关掉这个窗口、换成那个来源（不算“没选就关掉”）
  const av = o.kind === 'video' || o.kind === 'audio';  // 选视频 / 声音：只有“文件夹”（gallery 里都是图片）
  // 每次选素材从根目录开始，路径 / 搜索只在本次弹窗里保留；素材库页面仍记住自己的位置。
  g = galMount($('.gal-host', box), { folderState: { dir: o.dir || '', q: '' }, lib: av ? '文件夹' : o.lib, lock: av || o.lock, folders: !av && !o.lock && o.folders !== false, kind: o.kind || 'image', pick: x => finish(galFile(x)), pickFile: f => finish(f),
    extra: o.combo ? `<button type="button" class="btn small gal-combo" title="依次选择姿势、衣服、脸，分别作为图 1、图 2、图 3，并自动填写修改指令">${GAL_SK_IC.combo}<span>角色组合</span></button>` : '',
    onExtra: t => { const b = $('.gal-combo', t); if (b) b.onclick = () => { done = true; g?.stop(); box.close(); o.combo(); }; } });
}

/* ================= 素材库页面（左边导航）：浏览 gallery 和别的文件夹，点开看详情，放进组合栏 → 去生图；或加为生视频参考图 / 参考视频 / 参考音频、作为生图原图 ================= */
const GAL_TRAY = { pose: null, outfit: null, face: null };  // 组合栏：素材库文件对象
const GAL_SLOTS = [['pose', '姿势'], ['outfit', '衣服'], ['face', '脸']];
function renderMats() {
  const main = $('#main');
  main.innerHTML = `<div class="page-head gal-ph"><div><h1 class="page-title">素材库</h1></div><div class="gal-tray"></div></div><div class="card gal-page"></div>`;
  const host = $('.gal-page', main), tray = $('.gal-tray', main);
  const fit = () => {  // 页面一屏放下：只有框里的图片区滚动（底部的播放条 / 手机导航不挡住）
    if (!host.isConnected) { window.visualViewport?.removeEventListener('resize', fit); return removeEventListener('resize', fit); }  // 两处都摘（以前每进一次素材库多一个，2026-11-15 审查）
    let bottom = innerHeight;
    for (const q of ['.pbar', '.rail']) { const e = $(q), cs = e && getComputedStyle(e); if (!e || cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) continue; const r = e.getBoundingClientRect(); if (r.height && r.top > innerHeight / 2 && r.width > innerWidth * .6) bottom = Math.min(bottom, r.top); }  // 收成小圆钮的播放条浮在上面，不占位置
    host.style.height = Math.max(320, bottom - host.getBoundingClientRect().top - 14) + 'px';
  };
  const paintTray = () => {
    const n = GAL_SLOTS.filter(([k]) => GAL_TRAY[k]).length;
    tray.innerHTML = `<span class="gal-tray-l">组合</span>${GAL_SLOTS.map(([k, nm]) => GAL_TRAY[k] ? `<div class="gal-slot${GAL_TRAY[k].lib === '姿势' ? ' sketch' : ''}" title="${esc(GAL_TRAY[k].label || GAL_TRAY[k].name)}"><img src="${esc(matsUrl(GAL_TRAY[k].rel) + '?thumb=1')}" alt=""><span>${nm}</span><button type="button" class="gal-slot-x" data-tx="${k}" title="移除" aria-label="移除${nm}">${GAL_IC.x}</button></div>`
      : `<div class="gal-slot gal-empty" title="打开一张图片，在右上角的 ··· 菜单里选择“作为${nm}”"><span>${nm}</span></div>`).join('')}
      <button type="button" class="btn small primary" data-go ${GAL_TRAY.pose && (GAL_TRAY.outfit || GAL_TRAY.face) ? '' : 'disabled'} title="${GAL_TRAY.pose ? '' : '请先选择姿势，再选择衣服或脸'}">去生图</button>${n ? '<button type="button" class="btn small" data-vid title="将组合中的图片全部加为生视频的参考图"><span class="gal-long">加为生视频参考图</span><span class="gal-short">加为参考图</span></button>' : ''}`;
    $$('[data-tx]', tray).forEach(b => b.onclick = () => { GAL_TRAY[b.dataset.tx] = null; paintTray(); });
    $('[data-go]', tray).onclick = () => { window.GAL_TO_IMG = { combo: { ...GAL_TRAY } }; go('img'); };
    const v = $('[data-vid]', tray); if (v) v.onclick = () => galToVideo(GAL_SLOTS.map(([k]) => GAL_TRAY[k]).filter(Boolean));
  };
  galMount(host, { folders: true, manage: true, view: (files, k) => galView(files, k, paintTray), use: f => galUseMenu(f, paintTray),
    pickFile: f => f.kind === 'image' ? galView([f], 0, paintTray) : galMedia(f) });
  paintTray(); fit(); addEventListener('resize', fit); setTimeout(fit, 300); window.visualViewport?.addEventListener('resize', fit); fit.vv = 1;
  { const mo = new MutationObserver(() => { if (!host.isConnected) return mo.disconnect(); setTimeout(fit, 320); }); mo.observe(document.body, { attributes: true, attributeFilter: ['class'] }); }  // 播放条收起 / 展开后重新量
}
/* 文件夹里的视频 / 声音：播放 + 加为生视频的参考视频 / 参考音频 */
function galMedia(f) {
  const vid = f.kind === 'video';
  const box = modal(`<div class="row gal-head"><h3 class="card-title" style="margin:0">${esc(f.name)}</h3><span class="spacer"></span><button type="button" class="pl-ib" data-close aria-label="关闭">${ICON.x}</button></div>
    <div class="gal-media">${vid ? `<video src="${esc(matsUrl(f.rel) + '?scrub=1')}" controls playsinline preload="auto"></video>` : `<audio src="${esc(matsUrl(f.rel))}" controls preload="auto"></audio>`}</div>
    <div class="row gal-macts"><button type="button" class="btn primary" data-add>${vid ? '加为生视频参考视频' : '加为生视频参考音频'}</button></div>`, null, true);
  box.classList.add('gal-dm');
  if (vid && typeof frAttach === 'function') { const v = $('.gal-media video', box); frAttach(v, { mats: f.rel, name: f.name }); $('.gal-macts', box).prepend(frShotBtn(v)); }  // 视频截图（2026-11-19）
  const m = $('.gal-media video, .gal-media audio', box);  // 打开就播放：音量 / 静音跟着播放栏（在这里调了，播放栏也跟着变）
  vidVolSync(m); if (!vid || videoAutoplay()) m.play().catch(() => { });  // 视频：关了“自动播放”时打开不播放（2026-11-05）
  const tv = vid ? 0 : setInterval(() => vsApply(m), 300);  // 声音：播放栏那边调音量时跟着变（全站只自动同步视频）
  const c0 = box.close; box.close = () => { clearInterval(tv); m.pause(); c0(); }; $$('[data-close]', box).forEach(b => b.onclick = box.close);
  $('[data-add]', box).onclick = async () => {
    const k = vid ? 'rvids' : 'raudios';
    if (VID_X[k].length >= 3) return toast(vid ? '参考视频最多 3 段' : '参考音频最多 3 段', true);
    try {
      if (vid) { let first = true; matsVid(f, v => { if (first) { first = false; VID_X.rvids.push(Object.assign(v, { snd: 'none' })); } }); }
      else { const file = await matsFile(f); const data = await new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(file); }); VID_X.raudios.push({ name: f.name, data, dur: 0 }); }
      box.close(); galVideoGo(vid ? '已加为生视频参考视频' : '已加为生视频参考音频');
    } catch (e) { toast(e.message || '无法读取此文件', true); }
  };
  return box;
}

function galVideoGo(msg) {  // 参考图 / 视频 / 音频只有 MiniMax H3 的生视频会用：换过去
  const st = vidState(), sw = st.model !== 'h3' || st.mode === 'edit';
  if (sw) { st.model = 'h3'; st.mode = 'gen'; persist(); }
  go('video');
  toast(msg + (sw ? '，已切换为 MiniMax H3（仅该模型支持参考素材）' : ''));
}
/* 素材库页面点图片：直接铺满看大图（imgview.js）。“作为姿势 / 衣服 / 脸、生视频参考图、生图原图”放在右上角的 ··· 菜单里
   （2026-11-15 用户：中间那层详情没必要；照 Apple 相册：点开就是大图，操作在“更多”菜单 / 右键 / 长按里） */
function galView(files, k, onTray) {
  ImageViewer.open(files.map(f => ({ src: matsUrl(f.rel), thumb: matsUrl(f.rel) + '?thumb=1', name: f.label || f.name, live: f.live ? matsUrl(f.live) : '' })), k,
    { actions: i => galUseMenu(files[i], onTray, () => ImageViewer.close()) });
}
function galUseMenu(f, onTray, done = () => { }) {
  const slot = f.lib === '衣服' ? 'outfit' : f.lib === '脸' ? 'face' : f.lib === '姿势' ? 'pose' : null;  // 素材库里本来是哪一类：排在最前
  const slots = [...GAL_SLOTS].sort((a, b) => (b[0] === slot) - (a[0] === slot));
  return [{ group: '放入组合' }, ...slots.map(([k, nm]) => ({ label: `作为${nm}`, checked: GAL_TRAY[k]?.rel === f.rel,
    on: () => { GAL_TRAY[k] = f; done(); onTray?.(); toast(`已放入组合：${nm}`); } })), '-',
    { label: '加为生视频参考图', on: () => { done(); galToVideo([f]); } },
    { label: '作为生图原图', on: () => { done(); window.GAL_TO_IMG = { src: f }; go('img'); } },
    ...(f.ft != null && f.fsrc && typeof frBackToVideo === 'function' ? ['-', { label: `回到视频 ${frT(f.ft)}`, icon: FR_IC.vid, on: () => { done(); frBackToVideo(f.fsrc, f.ft); } },
      { label: '在素材库中显示', icon: FR_IC.folder, on: () => { done(); frShowInMats(f.rel); } }] : [])];  // 视频截图（2026-11-19）：回到视频里的那一刻
}
/* 加为生视频的参考图（MiniMax H3 的“参考图”）：读成和上传一样的图片，去生视频页 */
async function galToVideo(files) {
  try {
    const max = VIDST?.h3max?.refs || 9, room = max - VID_X.refs.length;
    if (room <= 0) return toast(`生视频的参考图已达 ${max} 张`, true);
    const ims = await Promise.all(files.slice(0, room).map(galImg));
    VID_X.refs.push(...ims);
    galVideoGo(`已加为生视频参考图（${ims.length} 张${files.length > room ? `，上限 ${max} 张，超出部分未添加` : ''}）`);
  } catch (e) { toast(e.message || '无法读取素材', true); }
}
PAGES.mats = renderMats;
document.addEventListener('loadedmetadata', e => { const v = e.target; if (v.tagName === 'VIDEO' && v.closest?.('.gal-fim')) v.classList.toggle('gal-land', v.videoWidth > v.videoHeight * 1.05); }, true);
// 封面图：横屏视频完整显示，上下用同一张图放大模糊的光晕补满（和“全部视频”一样，2026-11-08 用户）
/* 格子里的图 / 视频封面怎么放（用户 11-07、11-08 定的规矩，2026-11-15 推广到图片和图集）：画面要完整，空出来的地方用同一张图放大模糊的光晕补满，不留黑底；
   只差一点（铺满只裁掉每边约 6% 以内）就直接铺满。以前只有横屏视频有光晕：竖屏视频被裁掉上下各约 1/8，图片两边是黑底 */
function galVthMark(t) {
  if (!t?.naturalWidth) return;
  const trk = t.parentElement?.classList.contains('gal-trk') ? t.parentElement : null, im = (trk || t).parentElement;
  if (!im?.classList.contains('gal-fim') || (trk && t !== trk.children[1])) return;  // 胶片：按正中那张算
  const R = (im.clientWidth || 3) / (im.clientHeight || 4), r = t.naturalWidth / t.naturalHeight, fit = 1 - Math.min(r / R, R / r) > .12;
  (trk || t).classList.toggle('gal-land', fit); (trk || t).classList.toggle('gal-cov', !fit);
  im.classList.toggle('gal-glow', fit); if (fit) im.style.setProperty('--th', `url("${t.src}")`);
}
document.addEventListener('load', e => { const t = e.target; if (t.tagName === 'IMG' && t.closest?.('.gal-fim') && !t.closest('.gal-fd')) galVthMark(t); }, true);

/* 2026-11-04 · 素材库“文件夹”整理的样式（放在这里，不改共用的 css 文件） */
(() => {
  const s = document.createElement('style');
  s.textContent = `
.gal-facts { display: flex; align-items: center; gap: 6px; margin-left: auto; margin-bottom: 2px; flex: none; }
.gal-facts .btn svg { width: 15px; height: 15px; margin-right: 4px; flex: none; }
.gal-seln { font-size: 12.5px; color: var(--text-2); margin-right: 4px; white-space: nowrap; }
.gal-t2 .gal-path { min-width: 0; }
.gal-ck { position: absolute; top: 8px; left: 8px; z-index: 2; width: 22px; height: 22px; border-radius: 50%; display: none; place-items: center;
  background: rgba(0, 0, 0, .45); box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, .85); color: transparent; pointer-events: none; }
.gal-ck svg { width: 14px; height: 14px; }
.gal-multi .gal-ck { display: grid; }
.gal-card.gal-on .gal-ck { background: var(--blue); box-shadow: none; color: #fff; }
.gal-multi .gal-card.gal-on .gal-im { box-shadow: 0 0 0 2.5px var(--blue); }
.gal-multi .gal-zoom { display: none; }
.gal-card.gal-dragging { opacity: .45; }
.gal-fd.gal-drop .gal-im { box-shadow: 0 0 0 2.5px var(--blue); background: var(--blue-soft); }
.gal-path [data-d].gal-drop { background: var(--blue-soft); box-shadow: 0 0 0 2px var(--blue); border-radius: 6px; }
.gal-dragn { position: fixed; top: -200px; left: -200px; padding: 6px 12px; border-radius: 8px; background: var(--blue); color: #fff; font-size: 13px; font-weight: 600; }
.gal-mvm { max-width: 460px; }
.gal-mvl { display: flex; flex-direction: column; gap: 2px; margin-top: 12px; max-height: min(60vh, 520px); overflow: auto; }
.gal-mvi { all: unset; box-sizing: border-box; display: flex; align-items: center; gap: 9px; padding: 9px 12px; border-radius: 8px; cursor: pointer; color: var(--text); font-size: 14px; }
.gal-mvi svg { width: 18px; height: 18px; flex: none; color: var(--text-2); }
.gal-mvi span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gal-mvi small { margin-left: auto; color: var(--text-2); font-size: 12px; flex: none; }
.gal-mvi:disabled { cursor: default; opacity: .55; }
.gal-mvi:focus-visible { outline: 2px solid var(--blue); outline-offset: -2px; }
@media (hover: hover) { .gal-mvi:not(:disabled):hover { background: rgba(127, 127, 127, .14); } }
@media (max-width: 640px) { .gal-facts .btn > span { display: none; } .gal-facts .btn svg { margin-right: 0; } }
.gal-play { all: unset; box-sizing: border-box; position: absolute; left: 10px; bottom: 10px; z-index: 2; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
  background: rgba(0, 0, 0, .55); color: #fff; cursor: pointer; transition: background .15s, transform .15s; }
.gal-play svg { width: 17px; height: 17px; }
@media (hover: hover) { .gal-play:hover { background: var(--blue); transform: scale(1.06); } }
.gal-play:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.gal-prog { position: absolute; left: 0; bottom: 0; height: 3px; width: 0; background: var(--blue); z-index: 2; pointer-events: none; transition: width .25s linear; }
.gal-multi .gal-play { display: none; }
/* 2026-11-08 用户：选视频的格子小一点、细长一点——竖屏视频基本完整（9:14，只裁掉上下各约 6%），横屏视频完整显示不裁 */
.gal-grid.gal-vgrid { grid-template-columns: repeat(auto-fill, minmax(clamp(150px, 10.5vw, 210px), 1fr)) !important; gap: 20px 14px !important; }  /* 宽度和素材库页面一样（2026-11-15），只是格子细长 */
.gal-vgrid .gal-im { aspect-ratio: 9 / 14; }
.gal-fim video.gal-land, .gal-fim img.gal-vth.gal-land, .gal-fim > img.gal-land, .gal-fim > .gal-trk.gal-land > img { object-fit: contain; background: transparent; }
.gal-fim > img.gal-cov, .gal-fim > .gal-trk.gal-cov > img { object-fit: cover; }
.gal-im.gal-glow > img, .gal-im.gal-glow > .gal-trk { position: relative; z-index: 1; }
.gal-im.gal-glow > .gal-trk { position: absolute; }
.gal-im.gal-glow { background: #000; }
.gal-im.gal-glow::before { content: ""; position: absolute; inset: -24px; z-index: 0; background: var(--th) center / cover no-repeat; filter: blur(20px) saturate(1.35) brightness(.55); pointer-events: none; }
.gal-im.gal-glow > img.gal-vth { position: relative; z-index: 1; }
.gal-fim img.gal-vth { object-fit: cover; }
.gal-fim > video.gal-vv { position: absolute; inset: 0; z-index: 1; object-fit: cover; }
@media (max-width: 640px) { .gal-grid.gal-vgrid { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 14px 8px !important; } .gal-vgrid .gal-play { width: 30px; height: 30px; left: 6px; bottom: 6px; } }
/* 删除键：和生图 / 生视频缩略图一样，停上去才出现；图片右上角原来的放大键往左让一格 */
.gal-im > .gal-del { top: 8px; right: 8px; width: 30px; height: 30px; border-radius: 8px; background: rgba(0, 0, 0, .45); }  /* 和旁边的放大键同样大小、同样的圆角方块 */
.gal-im > .gal-del svg { width: 16px; height: 16px; }
.gal-card:is(:hover, :focus-within) .gal-im > .gal-del { opacity: 1; }
.gal-im:has(> .gal-del) > .gal-zoom { right: 42px; }
.gal-multi .gal-del { display: none; }
/* 鼠标停上去：白色跑马灯（和生图 / 生视频缩略图一样），不再是蓝框；多选选中、拖到文件夹上仍是蓝色 */
@media (hover: hover) { .gal-card:hover .gal-im { box-shadow: none; } }
.gal-card:focus-visible .gal-im { box-shadow: none; }
.gal-card .gal-im::after { content: ""; position: absolute; inset: 0; z-index: 4; border-radius: inherit; padding: 1.5px; pointer-events: none; opacity: 0; transition: opacity .35s;
  background: conic-gradient(from var(--ga), rgba(255, 255, 255, .1) 0deg, rgba(255, 255, 255, .1) 230deg, rgba(190, 215, 255, .55) 290deg, #fff 325deg, rgba(190, 215, 255, .55) 345deg, rgba(255, 255, 255, .1) 360deg);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0);
  animation: glSpin 4.2s linear infinite; animation-play-state: paused; }
@media (hover: hover) { .gal-card:hover .gal-im::after { opacity: 1; animation-play-state: running; } }
.gal-card:focus-visible .gal-im::after { opacity: 1; animation-play-state: running; }
.gal-multi .gal-card.gal-on .gal-im::after, .gal-fd.gal-drop .gal-im::after { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .gal-card .gal-im::after { animation: none; } }
`;
  document.head.append(s);
})();


/* 2026-11-15 用户：搜索放右边、第二行（路径那一行）不要折成两行、排序 / 标签 / 多选只放图标（悬停有说明）。
   照 Apple HIG 工具栏：常用的放在尾端、搜索框在尾端，三个以上按钮用图标。手机（≤640px）沿用原来的两行 + 搜索图标 */
(() => {
  const s = document.createElement('style');
  s.textContent = `
.gal-ic { width: 34px; height: 34px; padding: 0 !important; justify-content: center; }
.gal-ic svg { margin: 0 !important; }
.gal-ic .gal-at { font-size: 15px; line-height: 1; }
.gal-path > .vd-link { min-width: 0; flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gal-path > span, .gal-path > .vd-link:first-child { flex: none; }  /* “素材库”不缩；中间几层先缩，当前这层最后缩 */
.gal-path > .vd-link:not(:first-child):not(:last-child) { flex-shrink: 4; min-width: 2.5em; }
@media (min-width: 641px) {
  .gal-t1 > .gal-q { order: 1; flex: 0 1 240px; max-width: 280px; }  /* 第一行：搜索放在右边 */
  .gal-t1 > .gal-q ~ :not(.spacer) { order: 2; }
  .gal-fold .gal-t2 { flex-wrap: nowrap; }  /* 第二行（路径 · 几项 · 排序 / 标签 / 多选）只占一行：路径太长就缩短 */
  .gal-fold .gal-t2 > .gal-path { flex: 0 1 auto; min-width: 0; flex-wrap: nowrap; overflow: hidden; white-space: nowrap; }
  .gal-fold .gal-t2 > .gal-n { flex: none; }
  .gal-fold .gal-t2 > .gal-fopts { flex: none; flex-wrap: nowrap; margin-left: auto; }
  .gal-fold .gal-t2 > .gal-facts { flex: 0 1 auto; flex-wrap: nowrap; min-width: 0; overflow-x: auto; scrollbar-width: none; }
}`;
  document.head.append(s);
})();
