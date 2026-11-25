/* 音效与声道：播放页（底栏）正在放的那个音频 / 视频，加上任意几个“叠加音轨”，各自可以放在 左 / 中 / 右 / 环绕（8D），
   各自调音量；所有声音再一起经过一条音效链（细节增强、温暖、空间混响、立体声宽度、耳机舒适、夜间模式），最后过一个防爆音的限幅器。

   - 叠加音轨跟着当前播放走：一起播放、暂停、拖进度、变速；有误差时微调速度追上，差太多才直接跳过去（听不出卡顿）。
   - 浏览器规定：声音一旦接进音效链就不能再接回去，而且音效链要在用户点过页面之后才能启动。所以只有真的用到时（改了声道 / 音效 / 叠加了音轨）
     才接管；没用到时完全不碰，播放和以前一模一样。
   - 所有设置记在本机（localStorage），叠加音轨只在这次打开期间有效。 */
'use strict';
window.Sound = (() => {
  const KEY = 'sound';
  const FX0 = { preset: 'off', detail: 0, warm: 0, reverb: 0, room: 'room', width: 1, xfeed: 0, night: false, spin: 8 };
  const PRESETS = {
    off: { name: '原声', fx: {} },
    asmr: { name: 'ASMR 推荐', fx: { detail: .5, reverb: .12, room: 'small', width: 1.15 } },
    space: { name: '沉浸空间', fx: { detail: .2, reverb: .32, room: 'room', width: 1.3 } },
    sleep: { name: '助眠', fx: { warm: .6, reverb: .12, room: 'small', night: true } },
    spin: { name: '8D 环绕', fx: { reverb: .16, room: 'room' }, main: '8d' },
  };
  const ROOMS = { small: '小房间', room: '卧室', hall: '大厅' };
  let saved = {}; try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { }
  const st = { main: { pos: 'c', vol: 1, ...(saved.main || {}) }, fx: { ...FX0, ...(saved.fx || {}) } };
  const layers = [];  // { id, title, url, el, pos, vol, loop, offset, n }
  let ctx = null, G = null, mainEl = null, mainN = null, clock = null, onChange = () => { }, masterVol = 1, uid = 0;

  const save = () => { localStorage.setItem(KEY, JSON.stringify({ main: st.main, fx: st.fx })); };
  const fxOn = () => { const f = st.fx; return f.detail > 0 || f.warm > 0 || f.reverb > 0 || f.width !== 1 || f.xfeed > 0 || f.night; };
  // iPhone / iPad 不认网页设的 audio.volume（设了读回来还是 1）：这时音量调到 100% 以下才接进音效链，用增益调音量
  const NOVOL = (() => { try { const a = new Audio(); a.volume = .5; return Math.abs(a.volume - .5) > .01; } catch { return false; } })();
  const needed = () => fxOn() || st.main.pos !== 'c' || st.main.vol !== 1 || layers.length > 0 || (NOVOL && masterVol < 1);

  /* ---------- 音效链 ---------- */
  // 2026-11-17 用户（iPhone + AirPods）：叠加音轨以后两个都没声音。接进音效链以后声音只从 Web Audio 出来——
  // iPhone 把 Web Audio 当“环境声”：静音键、锁屏会把它静音；锁屏、来电、蓝牙耳机切换后它停在 interrupted / suspended，要重新 resume。
  // 做法（WebKit 的建议）：声明成媒体播放（navigator.audioSession，iOS 17 起）；状态一变、回到前台、点播放时都重新 resume
  const playing = () => (mainEl && !mainEl.paused) || layers.some(l => !l.el.paused);
  function ensureCtx() {
    try { if (navigator.audioSession && navigator.audioSession.type !== 'playback') navigator.audioSession.type = 'playback'; } catch { }
    if (!ctx) {
      try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch { return null; }
      ctx.onstatechange = () => { if (ctx.state !== 'running' && playing()) ctx.resume().catch(() => { }); watch(); };
    }
    if (ctx.state !== 'running') ctx.resume().catch(() => { });
    return ctx;
  }
  // 接管以后放着却没有声音（iPhone 有时必须点一下才肯恢复）：1.5 秒后还不行就提示点一下屏幕
  let wT = 0;
  function watch() {
    clearTimeout(wT);
    if (!ctx || !mainN || ctx.state === 'running' || !playing()) return;
    wT = setTimeout(() => { if (ctx.state !== 'running' && playing()) window.toast?.('声音被系统暂停了，点一下屏幕即可恢复'); }, 1500);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && ctx && ctx.state !== 'running') { ctx.resume().catch(() => { }); watch(); } });
  function build() {
    if (G || !ensureCtx()) return G;
    const c = ctx, g = v => { const n = c.createGain(); n.gain.value = v; return n; };
    const bq = (type, f, q) => { const n = c.createBiquadFilter(); n.type = type; n.frequency.value = f; if (q) n.Q.value = q; return n; };
    G = { bus: g(1), low: bq('lowshelf', 180), pres: bq('peaking', 3200, .9), air: bq('highshelf', 7500) };
    G.bus.connect(G.low); G.low.connect(G.pres); G.pres.connect(G.air);
    // 立体声宽度 + 耳机舒适：左右声道按比例互相混一点（宽度）；耳机舒适 = 把另一边的低频稍微延迟一点再混过来（像用音箱听，不那么“夹耳朵”）
    G.split = c.createChannelSplitter(2); G.merge = c.createChannelMerger(2);
    G.air.connect(G.split);
    G.ll = g(1); G.rl = g(0); G.rr = g(1); G.lr = g(0);
    G.split.connect(G.ll, 0); G.ll.connect(G.merge, 0, 0); G.split.connect(G.rl, 1); G.rl.connect(G.merge, 0, 0);
    G.split.connect(G.rr, 1); G.rr.connect(G.merge, 0, 1); G.split.connect(G.lr, 0); G.lr.connect(G.merge, 0, 1);
    const cross = (from, to) => { const d = c.createDelay(.01); d.delayTime.value = .00035; const lp = bq('lowpass', 700, .5), x = g(0); G.split.connect(d, from); d.connect(lp); lp.connect(x); x.connect(G.merge, 0, to); return x; };
    G.xl = cross(1, 0); G.xr = cross(0, 1);
    // 空间混响：干声 + 混响声并联
    G.dry = g(1); G.wet = g(0); G.conv = c.createConvolver(); G.convOn = false; G.sum = g(1);
    G.merge.connect(G.dry); G.dry.connect(G.sum); G.conv.connect(G.wet); G.wet.connect(G.sum);
    // 夜间模式（压缩：大声变小、小声变大）→ 补偿音量 → 限幅（叠加几轨、开了增强也不会爆音）
    G.night = c.createDynamicsCompressor(); G.make = g(1);
    G.lim = c.createDynamicsCompressor(); G.lim.threshold.value = -1.5; G.lim.knee.value = 0; G.lim.ratio.value = 20; G.lim.attack.value = .002; G.lim.release.value = .12;
    G.sum.connect(G.night); G.night.connect(G.make); G.make.connect(G.lim);
    G.out = g(NOVOL ? masterVol : 1); G.lim.connect(G.out); G.out.connect(c.destination);  // 总音量（只在不认 audio.volume 的 iPhone 上用）
    // 8D 环绕：两个相差 90° 的低频振荡器推着声源绕头转（不用定时器，转得很平滑）
    const wave = (re, im) => c.createPeriodicWave(new Float32Array(re), new Float32Array(im), { disableNormalization: true });
    G.sin = c.createOscillator(); G.sin.setPeriodicWave(wave([0, 0], [0, 1]));
    G.cos = c.createOscillator(); G.cos.setPeriodicWave(wave([0, 1], [0, 0]));
    G.sinR = g(1.2); G.cosR = g(1.2); G.sin.connect(G.sinR); G.cos.connect(G.cosR);
    const t0 = c.currentTime + .05; G.sin.start(t0); G.cos.start(t0);
    G.irs = {};
    applyFx();
    return G;
  }
  function makeIR(kind) {  // 房间的“回声样本”：随时间衰减、越来越闷的噪声，左右各不相同（听起来更宽）
    if (G.irs[kind]) return G.irs[kind];
    const [dur, decay, pre, bright] = { small: [.5, 3.4, .004, .55], room: [1.2, 2.8, .012, .42], hall: [2.6, 2.3, .03, .3] }[kind];
    const sr = ctx.sampleRate, n = Math.floor(sr * (dur + pre)), p0 = Math.floor(sr * pre), buf = ctx.createBuffer(2, n, sr);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch); let y = 0, e = 0;
      for (let i = p0; i < n; i++) {
        const t = (i - p0) / sr / dur, a = 1 - bright * (1 - t * .7);
        y = a * y + (1 - a) * (Math.random() * 2 - 1);
        d[i] = y * Math.pow(1 - t, decay); e += d[i] * d[i];
      }
      const k = 1 / Math.sqrt(e || 1); for (let i = 0; i < n; i++) d[i] *= k;
    }
    return (G.irs[kind] = buf);
  }
  function applyFx() {
    if (!G) return;
    const f = st.fx, now = ctx.currentTime, set = (p, v) => p.setTargetAtTime(v, now, .03);
    set(G.low.gain, f.warm * 5 - f.detail * 1);
    set(G.pres.gain, f.detail * 3.5);
    set(G.air.gain, f.detail * 6 - f.warm * 3);
    const w = f.width, a = (1 + w) / 2, b = (1 - w) / 2;
    set(G.ll.gain, a); set(G.rr.gain, a); set(G.rl.gain, b); set(G.lr.gain, b);
    set(G.xl.gain, f.xfeed * .45); set(G.xr.gain, f.xfeed * .45);
    const wantConv = f.reverb > 0;
    if (wantConv) { const ir = makeIR(f.room); if (G.conv.buffer !== ir) G.conv.buffer = ir; }
    if (wantConv && !G.convOn) { G.merge.connect(G.conv); G.convOn = true; }
    if (!wantConv && G.convOn) { G.merge.disconnect(G.conv); G.convOn = false; }
    set(G.wet.gain, f.reverb * .9); set(G.dry.gain, 1 - f.reverb * .25);
    const nt = G.night;
    // 压缩器自带补偿增益（约 +12 dB），这里再收回 5 dB：小声的地方大约 +5 dB、大声的地方压下来、中等音量基本不变
    if (f.night) { nt.threshold.value = -30; nt.knee.value = 8; nt.ratio.value = 3; nt.attack.value = .004; nt.release.value = .3; set(G.make.gain, .55); }
    else { nt.threshold.value = 0; nt.knee.value = 0; nt.ratio.value = 1; set(G.make.gain, 1); }
    const hz = 1 / Math.max(2, f.spin || 8);
    G.sin.frequency.setValueAtTime(hz, now); G.cos.frequency.setValueAtTime(hz, now);
  }

  /* ---------- 每个音轨：音量 → 位置（左 / 中 / 右 / 环绕）→ 音效链 ---------- */
  function trackNodes(el) {
    const c = ctx, n = { src: c.createMediaElementSource(el), g: c.createGain() };
    n.mono = c.createGain(); n.mono.channelCount = 1; n.mono.channelCountMode = 'explicit'; n.mono.channelInterpretation = 'speakers';  // 合成单声道
    n.pan = c.createStereoPanner();
    n.hrtf = c.createPanner(); Object.assign(n.hrtf, { panningModel: 'HRTF', distanceModel: 'inverse', refDistance: 1.2, rolloffFactor: .3 });
    n.hrtf.positionY.value = 0; n.hrtf.positionX.value = 0; n.hrtf.positionZ.value = 0;
    G.sinR.connect(n.hrtf.positionX); G.cosR.connect(n.hrtf.positionZ);
    n.src.connect(n.g);
    n.pan.connect(G.bus); n.hrtf.connect(G.bus);
    return n;
  }
  function route(n, pos, vol) {
    if (!n) return;
    n.g.gain.setTargetAtTime(vol, ctx.currentTime, .03);
    try { n.g.disconnect(); } catch { } try { n.mono.disconnect(); } catch { }
    if (pos === '8d') { n.g.connect(n.mono); n.mono.connect(n.hrtf); }
    else if (pos === 'c') { n.g.connect(n.pan); n.pan.pan.value = 0; }
    else { n.g.connect(n.mono); n.mono.connect(n.pan); n.pan.pan.value = pos === 'l' ? -1 : 1; }
  }
  // iPhone（2026-11-18 用户：调了声音面板里任何一项就没声音，退出重开才好）：Safari 里正在放的音频中途接进音效链会变成静音，
  // 开始播放前就接好的（重开软件时设置已经生效）没问题。所以 iPhone 上接进去以后把这个音频重新载入一次，回到原来的位置 / 速度 / 播放状态
  function reloadIOS(el) {
    if (!NOVOL || !el || el.readyState === 0 || !el.currentSrc) return;
    const t = el.currentTime, play = !el.paused, rate = el.playbackRate;
    const back = () => { try { el.currentTime = t; } catch { } el.playbackRate = rate; if (play) el.play().catch(() => { }); };
    el.addEventListener('loadedmetadata', back, { once: true });
    el.load();
  }
  // 真的需要时才接管当前播放（必须在用户点过页面之后，否则浏览器会让它没声音）
  function hook() {
    // 已经接进音效链的，就算现在什么都不需要了（比如点了“全部还原”）也要重新接一遍线：
    // 以前这里直接返回，声道还停在“左 / 右”，看着还原了、声音却只有一边（2026-11-17 用户）
    if (!mainEl || (!needed() && !mainEl.__sn)) return;
    if (!build()) return;
    if (ctx.state !== 'running') { ctx.resume().then(() => hook()).catch(() => { }); return; }
    if (!mainEl.__sn) { try { mainEl.__sn = trackNodes(mainEl); } catch { return; } reloadIOS(mainEl); }
    mainN = mainEl.__sn;
    route(mainN, st.main.pos, st.main.vol);
    layers.forEach(l => { if (!l.n) { try { l.n = trackNodes(l.el); reloadIOS(l.el); } catch { } } route(l.n, l.pos, l.vol); });
  }
  const unlock = () => { if (needed()) { ensureCtx(); hook(); } else if (ctx) ensureCtx(); if (layers.length) sync(); };
  document.addEventListener('pointerdown', unlock, true);
  document.addEventListener('keydown', unlock, true);

  /* ---------- 叠加音轨的同步 ---------- */
  function sync() {
    if (!layers.length) return;
    const k = clock ? clock() : { t: 0, paused: true, rate: 1 };
    layers.forEach(l => {
      const el = l.el, d = el.duration;
      let want = k.t - l.offset;
      if (l.loop && d > 0) want = ((want % d) + d) % d;
      const inside = want >= 0 && (!(d > 0) || want < d - .05);
      if (k.paused || !k.src || !inside) { if (!el.paused) el.pause(); if (inside && el.readyState > 0 && Math.abs(el.currentTime - want) > .3) el.currentTime = want; return; }
      if (el.readyState === 0) return;
      const drift = el.currentTime - want;
      if (Math.abs(drift) > .35 || el.paused) { el.currentTime = Math.max(0, want); el.playbackRate = k.rate; }
      else if (Math.abs(drift) > .04) el.playbackRate = k.rate * (1 - Math.max(-.06, Math.min(.06, drift * .6)));
      else el.playbackRate = k.rate;
      if (el.paused) el.play().catch(() => { });
    });
  }
  setInterval(sync, 250);

  /* ---------- 对外 ---------- */
  function changed() { save(); hook(); applyFx(); onChange(); }
  return {
    PRESETS, ROOMS,
    init(el, opts = {}) {
      clock = opts.clock; onChange = opts.onChange || onChange; this.setMainEl(el);
    },
    // 换主音轨（底栏现在放的那个播放器）：叠加的音轨跟着它走，声道 / 音量也作用在它上面
    setMainEl(el) {
      if (!el || el === mainEl) return;
      if (mainN) { try { route(mainN, 'c', 1); } catch { } }  // 换下来的那个：回到原样（它已经接进音效链，只能接着走这条路）
      mainEl = el; mainN = el.__sn || null;
      if (!el.__sev) { el.__sev = true; ['play', 'pause', 'seeked', 'ratechange', 'loadedmetadata', 'emptied'].forEach(ev => el.addEventListener(ev, () => { if (el !== mainEl) return; sync(); if (ev === 'play') { unlock(); watch(); } })); }
      hook(); sync(); onChange();
    },
    get main() { return { ...st.main }; },
    get fx() { return { ...st.fx }; },
    get layers() { return layers.map(({ id, title, pos, vol, loop, offset, el }) => ({ id, title, pos, vol, loop, offset, t: el.currentTime, d: el.duration || 0, playing: !el.paused })); },
    active: () => needed(),
    fxActive: () => fxOn() || st.main.pos !== 'c' || layers.some(l => l.pos === '8d'),
    hooked: () => !!mainEl?.__sn,
    setMain(p) { Object.assign(st.main, p); changed(); },
    setFx(p) { Object.assign(st.fx, p, 'preset' in p ? {} : { preset: 'custom' }); changed(); },
    preset(key) {
      const P = PRESETS[key]; if (!P) return;
      st.fx = { ...FX0, spin: st.fx.spin, ...P.fx, preset: key };
      if (P.main) st.main.pos = P.main; else if (st.main.pos === '8d') st.main.pos = 'c';
      changed();
    },
    addLayer({ url, title }) {
      const used = new Set([st.main.pos, ...layers.map(l => l.pos)]);
      const el = new Audio(); el.preload = 'auto'; el.src = url; el.volume = masterVol;
      const l = { id: ++uid, title, url, el, pos: !used.has('r') ? 'r' : !used.has('l') ? 'l' : 'c', vol: 1, loop: false, offset: 0, n: null };
      el.addEventListener('loadedmetadata', sync);
      layers.push(l); ensureCtx(); changed();
      // 在这次点按里就 play() 一次（iPhone 等要求第一次播放必须在点按里，否则之后定时器里 play() 会被拒、一直没声音）；主音轨停着就马上停下
      try { const pr = el.play(); pr?.catch?.(() => { }); const k = clock ? clock() : null; if (!k || k.paused || !k.src) el.pause(); } catch { }
      sync();
      return l.id;
    },
    // 调叠加音轨的进度（2026-11-18 用户）：音轨跟着主音轨走，所以就是改“错开”——让它此刻正好在 v 秒
    seekLayer(id, v) {
      const l = layers.find(x => x.id === id); if (!l) return;
      const k = clock ? clock() : { t: 0 }; l.offset = Math.round((k.t - Math.max(0, v)) * 100) / 100;
      try { l.el.currentTime = Math.max(0, v); } catch { }
      sync(); onChange();
    },
    // 主音轨跳了 d 秒、叠加的不跟着跳（键盘快进快退）：每个叠加音轨的“错开”加上 d
    shiftLayers(d) { if (!d || !layers.length) return; layers.forEach(l => { l.offset = Math.round((l.offset + d) * 100) / 100; }); sync(); onChange(); },
    setLayer(id, p) { const l = layers.find(x => x.id === id); if (!l) return; Object.assign(l, p); changed(); sync(); },
    removeLayer(id) {
      const i = layers.findIndex(x => x.id === id); if (i < 0) return;
      const [l] = layers.splice(i, 1); l.el.pause(); try { l.n?.pan.disconnect(); l.n?.hrtf.disconnect(); } catch { }
      l.el.removeAttribute('src'); l.el.load(); changed();
    },
    clearLayers() { [...layers].forEach(l => this.removeLayer(l.id)); },
    reset() { this.clearLayers(); st.main = { pos: 'c', vol: 1 }; st.fx = { ...FX0, spin: st.fx.spin }; changed(); },
    volume(v) {
      masterVol = v; layers.forEach(l => { l.el.volume = v; });
      if (NOVOL) { if (G) G.out.gain.setTargetAtTime(v, ctx.currentTime, .03); hook(); }
    },
    _novol: () => NOVOL,
    sync,
    _ctx: () => ctx,  // 测试用：看 / 模拟音效链的状态（被系统暂停后能不能自己恢复）
    // 左右声道的实时响度（0~1），给测试和以后的电平表用
    meter() {
      if (!G) return null;
      if (!G.met) { const sp = ctx.createChannelSplitter(2); G.lim.connect(sp); G.met = [0, 1].map(i => { const a = ctx.createAnalyser(); a.fftSize = 2048; sp.connect(a, i); return a; }); G.mbuf = new Float32Array(2048); }
      return G.met.map(a => { a.getFloatTimeDomainData(G.mbuf); let e = 0; for (const v of G.mbuf) e += v * v; return Math.sqrt(e / G.mbuf.length); });
    },
  };
})();
