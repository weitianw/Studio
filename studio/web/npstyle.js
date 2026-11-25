/* 全屏播放页的“外观”（2026-11-17 用户）：⋯ 菜单里的「外观」（小衣服图标）→ 选样式、背景颜色、字幕大小、要不要显示封面。
   设计稿：docs/设计稿/全屏播放页方案_1117.html。原则（Apple HIG：Color / Materials）：颜色只取自封面、压暗降饱和；文字只用白 / 黑的不同透明度；玻璃只用在控制层。
   - 样式：封面雾色（默认：封面本身模糊后慢慢流动，Apple Music 的做法）/ 原版（以前的样子）/ 纯色 / 黑胶（唱片从封套里探出来）/ 居中（电脑：封面居中、按钮收进底部一条玻璃）
   - 应用是浅色时，新样式跟着变浅（原版仍是深色）
   - 背景颜色：跟随封面，或者预设的几种低饱和颜色（封面不好看时用）
   - 封面：显示 / 不显示（不显示时用通用的图案：同色系渐变 + 音符，像 Apple Music 没有封面时那样）
   - 电脑上弹窗从右边滑出、不挡左边，方便对比；手机上从底部升起
   设置存在 S.ui.npLook。视频播放时不改（只管音频）。 */
'use strict';
window.NPL = (() => {
  // 2026-11-17 用户：黑胶不要了；“居中”其实是换了一种播放栏 → 拆成“播放栏”选项（封面下方 / 底部一条），
  // 居中则是所有样式都有：字幕 / 播放列表收起时（再点一下上面选中的那个）封面居中
  // 2026-11-18 用户：加“流动渐变”（方案 B，docs/设计稿/封面雾色方案_1118.html），保留原来的封面雾色；默认仍是封面雾色
  const STYLES = [['mist', '封面雾色'], ['mesh', '流动渐变'], ['orig', '原版'], ['solid', '纯色']];
  // 2026-11-18 用户：再加一个，参考 QQ 音乐全屏页——底部一整条：左边歌名 / 收藏，中间控制 + 进度，右边字幕 / 音效 / 播放列表；当前那句歌词用封面里取的强调色
  const BARS = [['under', '封面下方'], ['dock', '底部一条'], ['full', '底部通栏']];
  const SIZES = [['s', '小', .85], ['m', '中', 1], ['l', '大', 1.18], ['xl', '特大', 1.36]];
  const DARK = [
    { id: 'ink', name: '曜石黑', c: '#3a3a3e', d: '#0c0c0d' }, { id: 'fog', name: '雾蓝', c: '#3e4f68', d: '#111722' }, { id: 'dusk', name: '暮紫', c: '#4d4463', d: '#15121c' },
    { id: 'pine', name: '墨绿', c: '#36503f', d: '#0f1712' }, { id: 'clay', name: '陶土', c: '#634a3a', d: '#1a130f' }, { id: 'wine', name: '酒红', c: '#5e3540', d: '#1a0e12' },
    { id: 'sand', name: '沙岩', c: '#5c5647', d: '#171511' }];
  const LIGHT = [
    { id: 'paper', name: '云白', c: '#f5f5f7', d: '#e4e4e8' }, { id: 'linen', name: '米白', c: '#f2eee7', d: '#e2dbcf' }, { id: 'mistl', name: '雾灰', c: '#e9ebef', d: '#d7dbe2' },
    { id: 'apricot', name: '浅杏', c: '#f4ebe3', d: '#e6d5c6' }, { id: 'sage', name: '薄荷', c: '#e7eee9', d: '#d2ded6' }, { id: 'lilac', name: '淡紫', c: '#ecebf3', d: '#d9d6e6' }];
  const FOG = DARK[1], FOGL = LIGHT[2];  // 没有封面可跟随时（不显示封面 / 文件没有封面）：清冷的雾蓝 / 雾灰
  // 没有封面时的音符：一整块实心（符杆、符尾、倾斜的符头），颜色不透明、整体用透明度——不会出现叠在一起的地方颜色不一样（2026-11-17 用户：以前的有点丑）
  const NOTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><g fill="currentColor"><path d="M8.6 5.5 19.6 3v12.4h-1.7V7.1l-7.6 1.75V18H8.6z"/><ellipse cx="6.75" cy="18" rx="3.15" ry="2.35" transform="rotate(-22 6.75 18)"/><ellipse cx="16.05" cy="15.45" rx="3.15" ry="2.35" transform="rotate(-22 16.05 15.45)"/></g></svg>';
  const SHIRT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M9 3.5 3.5 6.6l1.9 4 2.1-1V20.5h9V9.6l2.1 1 1.9-4L15 3.5c-.4 1.5-1.6 2.5-3 2.5s-2.6-1-3-2.5z"/></svg>';
  const SPARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.6L18.5 9l-4.7 1.4L12 15l-1.8-4.6L5.5 9l4.7-1.4z"/><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>';

  const L = () => {
    const o = S.ui?.npLook || {}, s = STYLES.some(x => x[0] === o.s) ? o.s : o.s === 'orig' ? 'orig' : 'mist';  // 默认：封面雾色（2026-11-17 用户）；以前的黑胶 / 居中 → 封面雾色
    const bar = BARS.some(x => x[0] === o.bar) ? o.bar : o.s === 'center' ? 'dock' : 'under';
    return { s, bar, color: o.color || (S.npBg === 'dark' ? 'ink' : 'cover'), art: o.art === 'none' ? 'none' : 'show', fs: SIZES.some(x => x[0] === o.fs) ? o.fs : 'm' };
  };
  const save = p => { const o = { ...L(), ...p }; S.ui = { ...(S.ui || {}), npLook: o }; if (o.s === 'orig') S.npBg = o.color === 'cover' ? 'vivid' : 'dark'; persist(); };
  const appLight = () => document.documentElement.dataset.theme === 'light';
  const isLight = l => l.s !== 'orig' && appLight() && !isVid();  // 原版一直是深色；视频页也一直是深色（控制条压在画面上，要白字）
  const presets = l => isLight(l) ? LIGHT : DARK;
  const preset = l => presets(l).find(p => p.id === l.color) || null;
  const meta = () => PB.meta || {};
  const showCover = (m, l = L()) => S.coverMode === 'file' && l.art !== 'none' && !!m.cover && !NOCOV.has(m.cover);
  const isVid = () => $('#np')?.classList.contains('is-video');

  /* ---------- 颜色 ---------- */
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mix = (h, w, t) => { const a = hex(h), b = hex(w); return '#' + a.map((x, i) => Math.round(x + (b[i] - x) * t).toString(16).padStart(2, '0')).join(''); };
  const hsl = (h, s, l) => { s /= 100; l /= 100; const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l), f = n => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
    return '#' + [0, 8, 4].map(n => Math.round(f(n) * 255).toString(16).padStart(2, '0')).join(''); };
  // 封面的主色：缩成 8×8 取平均 → 降饱和、压暗（深色）/ 压浅（浅色）
  const TONE = new Map();
  function toneOf(url, done) {
    if (TONE.has(url)) return TONE.get(url);
    TONE.set(url, null);
    const im = new Image();
    im.onload = () => {
      try {
        const c = document.createElement('canvas'); c.width = c.height = 8; const g = c.getContext('2d'); g.drawImage(im, 0, 0, 8, 8);
        const d = g.getImageData(0, 0, 8, 8).data; let r = 0, gg = 0, b = 0; for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; } r /= 64; gg /= 64; b /= 64;
        const mx = Math.max(r, gg, b), mn = Math.min(r, gg, b), l = (mx + mn) / 510; let h = 0; const sat = mx === mn ? 0 : (mx - mn) / 255 / (1 - Math.abs(2 * l - 1));
        if (mx !== mn) { h = mx === r ? ((gg - b) / (mx - mn)) % 6 : mx === gg ? (b - r) / (mx - mn) + 2 : (r - gg) / (mx - mn) + 4; h *= 60; if (h < 0) h += 360; }
        const S2 = Math.min(sat * .55, .28) * 100;
        TONE.set(url, { c: hsl(h, S2, 24), d: hsl(h, S2 * .8, 8), lc: hsl(h, Math.min(S2, 16), 95), ld: hsl(h, Math.min(S2, 18), 86),
          a: hsl(h, Math.max(48, Math.min(78, sat * 100)), 64), al: hsl(h, Math.max(48, Math.min(78, sat * 100)), 38) });  // a：强调色（底部通栏的播放键、当前那句歌词），al：浅色应用用的深一点的
      } catch { TONE.set(url, false); }
      done();
    };
    im.onerror = () => { TONE.set(url, false); };
    im.src = url;
    return null;
  }
  // 预设颜色也会“动”：画一张同色系的柔和色块图，代替封面放进流动背景
  const BLOB = {};
  function blobs(p, light) {
    const k = p.c + (light ? 'l' : '');
    if (BLOB[k]) return BLOB[k];
    const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
    g.fillStyle = light ? p.c : p.d; g.fillRect(0, 0, 128, 128);
    const hi = light ? '#ffffff' : mix(p.c, '#ffffff', .16), lo = light ? p.d : mix(p.c, '#000000', .3);
    [[35, 38, 65, hi], [95, 83, 75, light ? mix(p.d, p.c, .5) : p.c], [57, 105, 50, lo], [105, 25, 45, light ? '#ffffff' : mix(p.c, '#ffffff', .07)]].forEach(([x, y, r, col]) => {
      const gr = g.createRadialGradient(x, y, 0, x, y, r); gr.addColorStop(0, col); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); });
    return BLOB[k] = c.toDataURL('image/png');
  }

  /* ---------- 流动背景：画在一张很小的画布上（屏幕的 1/10），每秒 20 帧，只在播放时动 ----------
     （以前用 4 个屏幕那么大的元素 + 80px 模糊，每帧都要重新模糊整个屏幕：测试里只有 15 帧。小画布放大后本来就是模糊的，几乎不花时间） */
  const FL = { cv: null, tiny: null, img: null, prev: null, fadeAt: 0, url: '', veil: 'dark', t: 0, last: 0, raf: 0 };
  // 手机、没有封面时（2026-11-18 用户：背景有问题——旋转的色块只剩几团灰雾）：一张安静的竖向渐变，不转动
  const FLAT = {};
  function flat(p) {
    if (FLAT[p.c]) return FLAT[p.c];
    const c = document.createElement('canvas'); c.width = 8; c.height = 128; const g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 0, 128); gr.addColorStop(0, mix(p.c, '#ffffff', .1)); gr.addColorStop(.55, p.c); gr.addColorStop(1, p.d);
    g.fillStyle = gr; g.fillRect(0, 0, 8, 128); return FLAT[p.c] = c.toDataURL('image/png');
  }
  function flowTo(url, veil, still = false) {
    FL.still = still;
    let cv = $('#npl-flow');
    if (!cv) { cv = document.createElement('canvas'); cv.id = 'npl-flow'; cv.className = 'npl-flow'; $('#np-bg').after(cv); FL.tiny = document.createElement('canvas'); }
    FL.cv = cv; FL.veil = veil;
    if (FL.url !== url) {
      FL.url = url; const im = new Image();
      im.onload = () => { if (FL.url !== url) return; FL.prev = FL.img; FL.img = im; FL.fadeAt = performance.now(); flowKick(true); };
      im.src = url;
    }
    flowKick(true);
  }
  // 2026-11-18 用户：视频页的背景也跟着外观走（两边设置互通）；放视频时背景不流动（只画一帧，免得和视频抢显卡，见 app.css 的 vid-playing）
  const flowOn = () => { const np = $('#np'); return np && !np.hidden && np.classList.contains('look-mist') && !np.classList.contains('look-mesh'); };

  /* ---------- 流动渐变（2026-11-18）：AMLL（amll-dev/applemusic-like-lyrics）的网格渐变背景 MeshGradientRenderer ----------
     从封面取色铺成一张慢慢变形的网格（WebGL）。库只在选了这个样式时才加载（vendor/amll-bg.js，约 365 KB）。
     没有封面时把“默认封面”（同色系渐变 + 音符）当封面；按封面亮度压暗（浅色应用提亮），白字 / 黑字都看得清；暂停时停；减少动态效果时静止。
     画布放在自己的合成层里（translateZ(0)）：没有的话在一些容器里画不出来（方案页上试出来的） */
  const MESH = { bg: null, url: '', lib: null, cv: null, veil: null };
  const meshLib = () => MESH.lib || (MESH.lib = new Promise((res, rej) => {
    if (window.AMLLBG) return res(window.AMLLBG);
    const sc = document.createElement('script'); sc.src = '/static/vendor/amll-bg.js'; sc.onload = () => window.AMLLBG ? res(window.AMLLBG) : rej(new Error('amll')); sc.onerror = rej; document.head.append(sc);
  }));
  const meshOn = () => { const np = $('#np'); return np && !np.hidden && np.classList.contains('look-mesh'); };
  function meshCover(t, light) {  // 没有封面 / 选了预设颜色：画一张同色系的“默认封面”喂给网格
    const k = 'mc' + t.c + (light ? 'l' : ''); if (BLOB[k]) return BLOB[k];
    const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 256, 256); gr.addColorStop(0, light ? mix(t.d, '#ffffff', .25) : mix(t.c, '#ffffff', .14)); gr.addColorStop(1, light ? t.d : t.d); g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
    g.fillStyle = light ? 'rgba(0,0,0,.18)' : 'rgba(255,255,255,.4)'; g.save(); g.translate(128, 128); g.scale(2.8, 2.8); g.translate(-12, -12);
    g.fill(new Path2D('M8.6 5.5 19.6 3v12.4h-1.7V7.1l-7.6 1.75V18H8.6z'));
    [[6.75, 18], [16.05, 15.45]].forEach(([x, y]) => { g.beginPath(); g.ellipse(x, y, 3.15, 2.35, -22 * Math.PI / 180, 0, 7); g.fill(); }); g.restore();
    return BLOB[k] = c.toDataURL('image/png');
  }
  const LUMS = new Map();
  function lumOf(url) {  // 封面平均亮度 0–1（越亮压得越暗）
    if (LUMS.has(url)) return Promise.resolve(LUMS.get(url));
    return new Promise(res => { const im = new Image(); im.onload = () => { try { const c = document.createElement('canvas'); c.width = c.height = 16; const g = c.getContext('2d'); g.drawImage(im, 0, 0, 16, 16); const d = g.getImageData(0, 0, 16, 16).data; let v = 0; for (let i = 0; i < d.length; i += 4) v += .2126 * d[i] + .7152 * d[i + 1] + .0722 * d[i + 2]; LUMS.set(url, v / 256 / 255); } catch { LUMS.set(url, .4); } res(LUMS.get(url)); }; im.onerror = () => res(.4); im.src = url; });
  }
  const veilOf = (l, light) => light
    ? `linear-gradient(180deg, rgba(250,250,252,${(.42 - l * .2).toFixed(2)}), rgba(250,250,252,${(.3 - l * .15).toFixed(2)}) 45%, rgba(250,250,252,${(.5 - l * .2).toFixed(2)}))`
    : `linear-gradient(180deg, rgba(0,0,0,${(.22 + l * .32).toFixed(2)}) 0%, rgba(0,0,0,${(.12 + l * .3).toFixed(2)}) 45%, rgba(0,0,0,${(.32 + l * .3).toFixed(2)}) 100%)`;
  async function meshTo(url, light) {
    const np = $('#np'); if (!np) return;
    if (!MESH.cv) {
      const w = document.createElement('div'); w.className = 'npl-mesh'; w.innerHTML = '<canvas></canvas><i class="npl-meshv"></i>';
      $('#np-bg').after(w); MESH.cv = $('canvas', w); MESH.veil = $('.npl-meshv', w);
    }
    let lib; try { lib = await meshLib(); } catch { return; }
    if (!meshOn()) return;
    if (!MESH.bg) {
      MESH.bg = new lib.BackgroundRender(new lib.MeshGradientRenderer(MESH.cv), MESH.cv);
      MESH.bg.setRenderScale(.5); MESH.bg.setFPS(30); MESH.bg.setFlowSpeed(1.6);
      if (reduceMotion) MESH.bg.setStaticMode(true);
    }
    MESH.bg.setHasLyric(!!(NP.sents && NP.sents.length));
    if (MESH.url !== url) { MESH.url = url; MESH.bg.setAlbum(url).catch(() => { }); }
    const l = await lumOf(url); if (MESH.url === url) MESH.veil.style.background = veilOf(l, light);
    meshPlay();
  }
  function meshPlay() {  // 放着才流动；暂停、播放页关着、不是这个样式：停
    if (!MESH.bg) return;
    const np = $('#np'), vid = meshOn() && isVid(), go = meshOn() && np.classList.contains('playing') && !vid && !document.hidden;
    // 视频页：用“静止模式”画出一帧再停（2026-11-18 用户：最先打开视频时背景是黑的——以前直接 pause，网格还没画过一帧就停了）
    try { MESH.bg.setStaticMode(!!reduceMotion || vid); if (vid && !document.hidden) MESH.bg.resume(); else go ? MESH.bg.resume() : MESH.bg.pause(); } catch { }
  }
  document.addEventListener('visibilitychange', meshPlay);
  function flowKick(once) { if (!FL.raf) FL.raf = requestAnimationFrame(flowFrame); FL.once = FL.once || once; }
  function flowFrame(now) {
    FL.raf = 0;
    if (!flowOn() || !FL.img || document.hidden) return;
    const np = $('#np'), playing = np.classList.contains('playing') && !isVid(), fading = FL.prev && now - FL.fadeAt < 1200;
    if (playing || fading) FL.raf = requestAnimationFrame(flowFrame);
    if (!FL.once && now - FL.last < 48) return;  // 约 20 帧
    FL.once = false;
    FL.t += playing && FL.last ? Math.min(now - FL.last, 200) / 1000 : 0; FL.last = now;
    flowDraw(now);
  }
  function flowDraw(now) {
    const W = Math.max(1, innerWidth), H = Math.max(1, innerHeight), cv = FL.cv, T = FL.tiny;
    const cw = Math.max(64, Math.round(W / 10)), ch = Math.max(36, Math.round(cw * H / W)), tw = 28, th = Math.max(12, Math.round(tw * H / W));
    if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; }
    if (T.width !== tw || T.height !== th) { T.width = tw; T.height = th; }
    const g = T.getContext('2d'), t = FL.t, vw = Math.max(tw, th) / 100, P = Math.PI * 2;  // 按长边算：手机竖屏时上下也铺满
    g.globalAlpha = 1; g.fillStyle = FL.base || (FL.veil === 'light' ? '#f5f5f7' : '#000'); g.fillRect(0, 0, tw, th);
    const set = (im, a) => {
      g.globalAlpha = a;
      if (FL.still) { g.drawImage(im, 0, 0, tw, th); return; }  // 不转动：整张铺满
      const put = (x, y, s, ang) => { g.save(); g.translate(x, y); g.rotate(ang); g.drawImage(im, -s / 2, -s / 2, s, s); g.restore(); };
      put(tw / 2, th / 2, 125 * vw, t / 90 * P);
      put(tw * .28, th * .72, 80 * vw, -t / 70 * P);
      const a3 = t / 60 * P; put(tw / 2 + Math.cos(a3) * 24 * vw, th / 2 + Math.sin(a3) * 24 * vw, 50 * vw, -a3);
      const a4 = P * (1 - t / 46), f4 = 2 * P * t / 46; put(tw / 2 + Math.cos(a4) * 32 * vw, th / 2 + Math.sin(a4) * 32 * vw, 25 * vw, a4 + f4);
    };
    const f = FL.prev ? Math.max(0, Math.min(1, (now - FL.fadeAt) / 1200)) : 1;
    if (FL.prev && f < 1) set(FL.prev, 1);
    set(FL.img, f); if (f >= 1) FL.prev = null;
    const c = cv.getContext('2d'); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
    if ('filter' in c) c.filter = 'blur(3px) saturate(1.15)';
    c.globalAlpha = 1; c.drawImage(T, -3, -3, cw + 6, ch + 6);
    if ('filter' in c) c.filter = 'none';
    // 压暗 / 提亮（照 Apple Music：颜色是“雾”的，不是“霓虹”的）
    c.fillStyle = FL.veil === 'light' ? 'rgba(250,250,252,.52)' : FL.veil === 'pre' ? 'rgba(0,0,0,.1)' : 'rgba(0,0,0,.4)'; c.fillRect(0, 0, cw, ch);
  }
  addEventListener('resize', () => { if (flowOn()) flowKick(true); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && flowOn()) flowKick(true); });

  /* ---------- 画到播放页上 ---------- */
  function paint() {
    const np = $('#np'); if (!np) return;
    const l = L(), m = meta(), cov = showCover(m, l) ? m.cover : '', P = preset(l), light = isLight(l);
    STYLES.forEach(([k]) => np.classList.toggle('look-' + k, l.s === k));
    if (l.s === 'mesh') np.classList.add('look-mist');  // 流动渐变的排版和封面雾色一样（只换背景）
    np.classList.toggle('npl-on', l.s !== 'orig');
    np.classList.toggle('npl-light', light);
    SIZES.forEach(([k]) => np.classList.toggle('fs-' + k, l.fs === k));
    np.style.setProperty('--lyr', SIZES.find(x => x[0] === l.fs)[2]);
    let t = P || null;
    if (!t && cov) { const x = toneOf(cov, () => { if (meta().cover === cov) paint(); }); if (x) t = light ? { c: x.lc, d: x.ld } : x; }
    if (!t) t = light ? FOGL : FOG;
    const R = np.style;
    R.setProperty('--tone', t.c); R.setProperty('--tone-d', t.d);
    R.setProperty('--g1', light ? mix(t.d, '#ffffff', .25) : mix(t.c, '#ffffff', .14)); R.setProperty('--g2', light ? mix(t.d, '#000000', .06) : t.d);  // 不显示封面时的通用图案
    np.classList.toggle('npl-tone', l.s === 'solid' || (l.s === 'orig' && l.color !== 'cover'));
    FL.base = t.d;
    if (l.s === 'mesh') meshTo(!P && cov ? cov : meshCover(t, light), light); else meshPlay();
    if (l.s === 'mist') { const still = MOB() && !P && !cov; flowTo(!P && cov ? cov : still ? flat(t) : blobs(t, light), light ? 'light' : !P && cov ? 'dark' : 'pre', still); }
    // iPhone 状态栏 / 最上面那一点的颜色
    if (isVid() || (l.s === 'orig' && l.color === 'cover')) R.removeProperty('--np-top'); else R.setProperty('--np-top', t.c);
    np.classList.toggle('bar-dock', l.bar === 'dock' && !MOB());
    np.classList.toggle('bar-full', l.bar === 'full' && !MOB());
    if (window.npYPlace) npYPlace(); else { const v = $('#np-vol'), want = np.classList.contains('bar-full') && !np.classList.contains('is-video') ? $('#np-dock') : $('#np .np-ctl');  /* 视频页没有右边那组：留在控制按钮那排 */ if (v && want && v.parentElement !== want) { if (want.id === 'np-dock') want.prepend(v); else want.append(v); } }  // 2026-11-18 用户：音量和右边那几个按钮对齐  // 方案 Y（2026-11-18）起：音量 / ⋯ / 全屏放哪由 app.js 的 npYPlace 统一摆
    { const tc = cov && TONE.get(cov); R.setProperty('--acc', tc ? (light ? tc.al : tc.a) : light ? '#2f6fd6' : '#7fb2ff'); }  // 没封面：应用的蓝
    dockOn();
    np.classList.toggle('np-solo', solo());
    $$('.np-tabs button', np).forEach(b => { b.dataset.tip = b.dataset.np === NP.tab && !solo() ? '再点一下收起，封面居中' : ''; });
    flowKick(true);
  }
  // 字幕 / 播放列表收起（电脑、音频）：封面居中。记在 S.ui.npPanel
  const solo = () => !MOB() && !isVid() && S.ui?.npPanel === false;

  // 封面那块：新样式由这里画（原版仍是以前的封面 / 黑胶）
  function art(m, key) {
    const l = L();
    if (l.s === 'orig') return l.art === 'none' ? vinylHtml(m, key) : null;
    const cov = showCover(m, l);
    const img = cov ? `<img src="${esc(m.cover)}" alt="" draggable="false" onerror="this.remove()">` : '';
    return `<span class="npl-cov${cov ? '' : ' gen'}">${cov ? '' : NOTE}${img}</span>`;
  }

  /* ---------- 弹窗 ---------- */
  function mini(id, l) {
    const m = meta(), cov = showCover(m, l) ? m.cover : '', light = id !== 'orig' && appLight(), P = (light ? LIGHT : DARK).find(p => p.id === l.color) || null;
    const tc = cov && TONE.get(cov), t = P || (tc ? (light ? { c: tc.lc, d: tc.ld } : tc) : (light ? FOGL : FOG));
    const ci = cov ? `background-image:url(&quot;${esc(cov)}&quot;)` : `background:linear-gradient(150deg, ${light ? mix(t.d, '#ffffff', .25) : mix(t.c, '#ffffff', .14)}, ${t.d})`;
    const lines = '<i class="ml" style="top:30%"></i><i class="ml on" style="top:42%;right:18%"></i><i class="ml" style="top:54%"></i><i class="ml" style="top:66%;right:22%"></i>';
    const flow = `<i class="mf${light ? ' lt' : ''}" style="background-image:url(${!P && cov ? `&quot;${esc(cov)}&quot;` : blobs(t, light)})"></i>`;
    const lc = light ? ' light' : '';
    if (id === 'orig') return `<span class="mini" style="--mt:${l.color === 'cover' ? 'radial-gradient(60% 70% at 20% 30%, #5b46b8, transparent 70%), radial-gradient(60% 70% at 80% 80%, #9c3f78, transparent 70%), #1d1838' : `linear-gradient(${(DARK.find(p => p.id === l.color) || FOG).c}, #0b0b0c)`}"><i class="mb"></i><i class="md" style="left:10%;top:17%;width:31%"></i><i class="mo"></i>${lines}</span>`;
    if (id === 'mist') return `<span class="mini${lc}">${flow}<i class="mc" style="${ci}"></i>${lines}</span>`;
    if (id === 'mesh') return `<span class="mini${lc}" style="--mt:radial-gradient(70% 60% at 25% 25%, ${mix(t.c, '#ffffff', light ? .5 : .22)}, transparent 70%), radial-gradient(70% 70% at 80% 75%, ${light ? t.d : mix(t.c, '#000000', .2)}, transparent 70%), linear-gradient(160deg, ${t.c}, ${light ? t.d : t.d})"><i class="mb"></i><i class="mc" style="${ci}"></i>${lines}</span>`;
    if (id === 'solid') return `<span class="mini${lc}" style="--mt:linear-gradient(${t.c}, ${light ? t.d : '#0b0b0c'})"><i class="mb"></i><i class="mc" style="${ci}"></i>${lines}</span>`;
    return '';
  }
  // 播放栏的小样：封面下方 = 进度和按钮在封面下面；底部一条 = 屏幕底下一条玻璃
  function miniBar(id, l) {
    const light = isLight(l), lc = light ? ' light' : '', cc = light ? '#cfd4dc' : '#5a6880';
    const lines = '<i class="ml" style="top:24%"></i><i class="ml on" style="top:36%;right:18%"></i><i class="ml" style="top:48%"></i>';
    const bg = `<i class="mb" style="background:${light ? '#e9ebef' : 'linear-gradient(#3e4f68, #111722)'}"></i><i class="mc" style="top:12%;width:26%;left:11%;background:${cc}"></i>`;
    if (id === 'full') return `<span class="mini${lc}">${bg.replace('top:12%;width:26%;left:11%', 'top:16%;width:28%;left:12%')}${lines.replace(/top:(\d+)%/g, (m, v) => 'top:' + (+v - 4) + '%')}<i class="mfull"></i><i class="mk" style="left:8%;width:20%;top:84%"></i><i class="mk dot acc" style="left:47%;top:82%"></i><i class="mk" style="left:34%;width:32%;top:92%"></i></span>`;
    if (id === 'under') return `<span class="mini${lc}">${bg}<i class="mk" style="left:11%;width:26%;top:62%"></i><i class="mk dot" style="left:21%;top:72%"></i>${lines}</span>`;
    return `<span class="mini${lc}">${bg}${lines}<i class="mg"></i></span>`;
  }
  function sheetPaint(box) {
    const l = L(), m = meta(), cov = showCover(m, l) ? m.cover : '', ps = presets(l), P = preset(l), light = isLight(l);
    box.classList.toggle('light', light);
    const bars = $('.npl-bars', box); if (bars) bars.innerHTML = BARS.map(([id, n]) => `<button type="button" class="npl-card${l.bar === id ? ' on' : ''}" data-bar="${id}" aria-pressed="${l.bar === id}">${miniBar(id, l)}<span>${n}</span></button>`).join('');
    $('.npl-st', box).innerHTML = STYLES.map(([id, n]) =>`<button type="button" class="npl-card${l.s === id ? ' on' : ''}" data-st="${id}" aria-pressed="${l.s === id}">${mini(id, l)}<span>${n}</span></button>`).join('');
    const fog = light ? FOGL : FOG, fc = cov ? `background-image:url(&quot;${esc(cov)}&quot;)` : `background:linear-gradient(150deg, ${mix(fog.c, '#ffffff', .14)}, ${fog.d})`;
    $('.npl-sw', box).innerHTML = `<button type="button" class="follow${l.color === 'cover' ? ' on' : ''}" data-col="cover" data-tip="跟随封面" aria-label="跟随封面" style="${fc}">${SPARK}</button>`
      + ps.map(p => `<button type="button" class="${l.color === p.id ? 'on' : ''}" data-col="${p.id}" data-tip="${p.name}" aria-label="${p.name}" style="background:${light ? `linear-gradient(160deg, ${p.c}, ${p.d})` : `linear-gradient(160deg, ${mix(p.c, '#ffffff', .12)}, ${p.d})`}"></button>`).join('');
    $('.npl-swn', box).textContent = P ? P.name : (cov || l.s === 'orig' ? '跟随封面' : `跟随封面 · 没有封面时用${fog.name}`);
    const seg = (sel, key, cur) => $$(sel + ' button', box).forEach(b => { const on = b.dataset[key] === cur; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
    seg('.npl-fs', 'fs', l.fs);
    seg('.npl-art', 'art', l.art === 'none' || S.coverMode !== 'file' ? 'none' : 'show');
  }
  function open() {
    const old = $('.npl-bg'); if (old) { old._close(); return; }
    const side = !MOB();  // 电脑：从右边滑出，不挡左边、不变暗，方便对比；手机：从底部升起
    const box = document.createElement('div'); box.className = side ? 'npl-bg side' : 'modal-bg npl-bg';
    box.innerHTML = `<div class="npl-sheet" role="dialog" aria-label="外观">
      <div class="npl-hd">外观<button type="button" class="npl-x" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>
      <div class="npl-sec">样式</div><div class="npl-styles npl-st"></div>
      <div class="npl-sec">背景颜色<span class="npl-swn"></span></div><div class="npl-sw"></div>
      ${isVid() ? '' : `${side ? '<div class="npl-sec">播放栏</div><div class="npl-styles npl-bars"></div>' : ''}
      <div class="npl-sec">字幕大小</div><div class="npl-seg npl-fs">${SIZES.map(([k, n]) => `<button type="button" data-fs="${k}">${n}</button>`).join('')}</div>
      <div class="npl-sec">封面</div><div class="npl-seg npl-art"><button type="button" data-art="show">显示封面</button><button type="button" data-art="none">不显示</button></div>`}
    </div>`;
    document.body.append(box);
    const repaint = relayout => { if (relayout) NP.key = null; npPaint(true); sbFlash(); sheetPaint(box); };
    const close = () => { if (!box.isConnected) return; removeEventListener('keydown', esc, true); removeEventListener('pointerdown', outside, true); obs.disconnect();
      if (side && !reduceMotion) { box.classList.add('out'); setTimeout(() => box.remove(), 220); } else box.remove(); };
    box._close = close;
    const esc = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); } };
    addEventListener('keydown', esc, true);
    // 点外观以外的地方：关掉外观；这一下只用来关，不顺带点到底下的按钮 / 歌词
    const outside = e => {
      if (e.target.closest?.('.npl-sheet, .ctx-menu')) return;
      close(); const eat = ev => { ev.stopPropagation(); ev.preventDefault(); };
      addEventListener('click', eat, { capture: true, once: true }); setTimeout(() => removeEventListener('click', eat, true), 500);
    };
    if (side) setTimeout(() => box.isConnected && addEventListener('pointerdown', outside, true), 0);
    const obs = new MutationObserver(() => { if ($('#np').hidden) close(); }); obs.observe($('#np'), { attributes: true, attributeFilter: ['hidden'] });  // 播放页关了：一起关
    box.addEventListener('click', e => {
      if (e.target === box || e.target.closest('.npl-x')) return close();
      const st = e.target.closest('[data-st]'), col = e.target.closest('[data-col]'), ar = e.target.closest('[data-art]'), fs = e.target.closest('[data-fs]'), bar = e.target.closest('[data-bar]');
      if (st) { const l = L(), s = st.dataset.st, wasL = isLight(l), nowL = s !== 'orig' && appLight(); save({ s, color: wasL !== nowL && l.color !== 'cover' ? 'cover' : l.color }); repaint(); }
      else if (bar) { save({ bar: bar.dataset.bar }); repaint(true); }  // 字幕那栏高度变了：重新排
      else if (col) { save({ color: col.dataset.col }); repaint(); }
      else if (fs) { save({ fs: fs.dataset.fs }); repaint(true); }  // 字号变了：字幕重新排（直接到当前那句，不从头滚）
      else if (ar) {
        if (ar.dataset.art === 'show') { save({ art: 'show' }); if (S.coverMode !== 'file') { S.coverMode = 'file'; persist(); if (PB.a) pbPaint(true); qPanelPaint(); } }
        else save({ art: 'none' });
        repaint();
      }
    });
    sheetPaint(box);
  }

  function dockOn() {  // 底部通栏右边的字幕 / 播放列表按钮：亮着的是现在右边显示的那个
    const np = $('#np'); if (!np || MOB()) return;
    $$('#np-dock [data-mv]').forEach(b => { const on = np.classList.contains('bar-full') && !solo() && b.dataset.mv === NP.tab; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('#np-dock [data-mv]'); if (!b || MOB() || !$('#np')?.classList.contains('bar-full')) return;
    e.stopImmediatePropagation(); e.preventDefault();
    $(`#np .np-tabs button[data-np="${b.dataset.mv}"]`)?.click(); setTimeout(dockOn, 0);
  }, true);
  // 字幕 / 播放列表的收起（电脑、音频，所有样式）：点上面已经选中的那个 → 收起，封面居中；收起时点任意一个 → 打开
  document.addEventListener('click', e => {
    const b = e.target.closest('#np .np-tabs button'); if (!b || MOB() || isVid()) return;
    const setP = v => { S.ui = { ...(S.ui || {}), npPanel: v }; persist(); };
    if (solo()) { setP(true); if (b.dataset.np === NP.tab) { e.stopImmediatePropagation(); NP.key = null; npPaint(true); } else paint(); }  // 打开：字幕重新排到当前那句
    else if (b.dataset.np === NP.tab) { setP(false); paint(); e.stopImmediatePropagation(); }
  }, true);
  // 播放 / 暂停：流动背景跟着动 / 停
  const npEl = document.getElementById('np');
  if (npEl) new MutationObserver(() => {
    if (npEl.classList.contains('playing') !== FL.wasPlaying) { FL.wasPlaying = npEl.classList.contains('playing'); FL.last = 0; flowKick(true); }
    meshPlay();
  }).observe(npEl, { attributes: true, attributeFilter: ['class'] });
  // 应用换了浅色 / 深色：新样式跟着变
  new MutationObserver(() => { if (npEl && !npEl.hidden) { paint(); const b = $('.npl-bg'); if (b) sheetPaint(b); } }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  return { paint, art, open, SHIRT, _L: L, _FL: FL };
})();
