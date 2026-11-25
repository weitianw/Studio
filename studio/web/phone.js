/* 手机改版（2026-11-16，方案见 docs/设计方案/手机改版_1116）第 1 步：外壳。
   - html.ph：窄屏 + 触摸（只按能力判断，不看 UA）；phone.css 里的规则都挂在它下面，电脑上什么都不变
   - 大标题：页面往上滚就缩成标题栏中间的小标题（html.ph-scrolled）
   - 播放条：贴在底栏上面（--ph-tab = 底栏占的高度）；不再收成 ♪ 圆钮
   - phSheet.open(节点, { title, onClose })：从底部升起的面板。节点搬进面板，关掉时放回原处；拖动条 / 标题往下拉、点外面、点“完成”都能关
   - 长按：iPhone 的 Safari 长按不会触发 contextmenu，这里补上（有右键菜单的地方长按就出菜单） */
'use strict';
(() => {
  const H = document.documentElement, mq = matchMedia('(max-width: 760px) and (pointer: coarse)');
  const on = () => mq.matches;
  const sync = () => { H.classList.toggle('ph', on()); try { compose(); } catch { } };  // 横竖屏切换：输入框跟着换布局（U01）
  sync(); mq.addEventListener?.('change', sync);

  // ---------- 大标题收起 ----------
  let q = 0;
  const sat = () => { const d = document.createElement('div'); d.style.cssText = 'position:fixed;padding-top:env(safe-area-inset-top);visibility:hidden'; document.body.append(d); const v = parseFloat(getComputedStyle(d).paddingTop) || 0; d.remove(); return v; };
  // 收起后的标题栏 = 安全区 + 约 52px（iOS 的小标题栏）：标题栏是 sticky，top 取负值把上面多出来的那段推出屏幕；按钮那一行的中线对准安全区下面 23px
  const headFit = () => {
    const h = document.querySelector('#main > .page-head'), t = h?.querySelector('.page-title'); if (!h || !t) return;
    const was = H.classList.contains('ph-scrolled'); if (was) H.classList.remove('ph-scrolled');
    const hr = h.getBoundingClientRect(), tr = t.getBoundingClientRect(), btn = [...h.querySelectorAll('button, a.btn, .b5-ctx')].find(b => b.offsetParent && !b.closest('.page-title'));
    const br = btn ? btn.getBoundingClientRect() : tr, bc = br.top + br.height / 2 - hr.top, tc = tr.top + tr.height / 2 - hr.top, s = sat();
    const stick = Math.min(0, Math.round(s + 23 - bc));
    H.style.setProperty('--ph-stick', stick + 'px');
    H.style.setProperty('--ph-tx', Math.round(hr.left + hr.width / 2 - tr.left - tr.width / 4) + 'px');
    H.style.setProperty('--ph-ty', Math.round(bc - tc) + 'px');
    if (was) H.classList.add('ph-scrolled');
  };
  const scrolled = () => { q = 0; const sc = on() && (scrollY || document.scrollingElement?.scrollTop || 0) > 28;
    if (sc && !H.classList.contains('ph-scrolled')) headFit();
    H.classList.toggle('ph-scrolled', sc); };
  addEventListener('DOMContentLoaded', () => { const m = document.getElementById('main'); if (m) new MutationObserver(() => { if (on()) requestAnimationFrame(headFit); }).observe(m, { attributes: true, attributeFilter: ['data-page'] }); });
  addEventListener('resize', () => { if (on()) headFit(); });
  addEventListener('scroll', () => { if (!q) q = requestAnimationFrame(scrolled); }, { passive: true });
  addEventListener('popstate', () => setTimeout(scrolled, 50));

  // ---------- 播放条贴在底栏上面 ----------
  let SAB = null; addEventListener('resize', () => { SAB = null; });
  const sab = () => SAB ?? (SAB = sab0());  // 只量一次（量的时候会往页面里加一个元素：不缓存的话，看着页面变化的观察者会每一帧都跑）
  const sab0 = () => { const d = document.createElement('div'); d.style.cssText = 'position:fixed;padding-bottom:env(safe-area-inset-bottom);visibility:hidden'; document.body.append(d); const v = parseFloat(getComputedStyle(d).paddingBottom) || 0; d.remove(); return v; };
  const tab = () => { const r = document.getElementById('rail'); if (!r || !on()) return; const shown = getComputedStyle(r).display !== 'none', t = r.getBoundingClientRect().top;
    const v = shown && t > 0 ? Math.round(innerHeight - t) : Math.round(sab());  // 底栏藏起来（生图 / 生视频 / AI 助手）：只留底部安全区
    if (H.style.getPropertyValue('--ph-tab') !== v + 'px') H.style.setProperty('--ph-tab', v + 'px'); };
  addEventListener('resize', tab); addEventListener('load', () => { tab(); if (on()) { try { pbMin(false, false); } catch { } } });
  if (window.ResizeObserver) addEventListener('DOMContentLoaded', () => { const r = document.getElementById('rail'); if (r) new ResizeObserver(tab).observe(r); });

  // ---------- 生图 / 生视频：输入框放到底部（第 2 步，和 AI 助手页、ChatGPT 一样）----------
  // 生成按钮挪进输入框右边（圆形箭头）；“查看完整提示词”挪到上面那排选项最后；--ph-comp = 输入框占的高度（页面底部留出这么多）
  const CPAGES = ['img', 'video'];
  let compRO = null;
  const DOTS_IC = '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5.5" cy="12" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="18.5" cy="12" r="1.9"/></svg>';
  const TOOL_SEL = ':scope > .ig-cb:not(.ph-more-b):not(#ig-enh-q):not(#ig-enh-undo), :scope > .prompt-peek, .ig-chips > .ig-chip.ph-tool, :scope > #vd-lang';
  const TOOL_NAMES = { 'ig-ai': 'AI 写提示词', 'vd-ai': 'AI 写提示词', 'ig-combo-p': '组合指令', 'ig-adv-open': '高级参数', 'vd-adv-open': '高级参数', 'vd-struct': '提示词模板', 'vd-lang': '提示词语言' };
  const toolName = el => { if (TOOL_NAMES[el.id]) return TOOL_NAMES[el.id]; if (el.classList.contains('prompt-peek')) return '查看完整提示词'; if (/sliders|采样|步数/.test(el.getAttribute('aria-label') || el.title || el.dataset.tip || '')) return '高级参数';
    const t = el.getAttribute('aria-label') || el.title || (el.dataset.tip || '').split(/[：（(。]/)[0] || el.textContent; return String(t).trim().replace(/（.*$/, '').slice(0, 14) || '工具'; };
  const toolsSheet = f => {
    const bl = f.querySelector('.ig-cbar > .bar-l'); if (!bl) return;
    const its = [...bl.querySelectorAll(TOOL_SEL)].filter(el => !el.hidden);
    const box = document.createElement('div'); box.className = 'ph-tools';
    const GLOBE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17"/></svg>';
    box.innerHTML = its.map((el, i) => `<button type="button" data-i="${i}">${el.id === 'vd-lang' ? GLOBE : el.querySelector('svg')?.outerHTML || ''}<span></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m9 6 6 6-6 6"/></svg></button>`).join('');
    box.querySelectorAll('button').forEach((b, i) => { b.querySelector('span').textContent = toolName(its[i]);
      if (its[i].id === 'vd-lang') {  // 语言：写出现在用的，点一下换成另一种（不关面板）
        const on = its[i].querySelector('button.on'), v = document.createElement('em'); v.className = 'ph-tool-st'; v.textContent = on?.textContent || ''; b.querySelector('.chev').before(v);
        b.onclick = () => { its[i].querySelector('button:not(.on)')?.click(); setTimeout(() => { v.textContent = its[i].querySelector('button.on')?.textContent || ''; }, 50); }; return; }
      const cbx = its[i].querySelector?.('input[type=checkbox]'), pr = its[i].getAttribute('aria-pressed') ?? (cbx ? String(cbx.checked) : null); if (pr != null) { const v = document.createElement('em'); v.className = 'ph-tool-st'; v.textContent = pr === 'true' ? '开' : '关'; b.querySelector('.chev').before(v); }  // 开关类的工具：写出现在开没开
      b.onclick = () => { phSheet.close(); its[i].click(); }; });  // 2026-11-17 UI 审查 #2：当场转发（以前等 340 毫秒）——这一面板往下滑走，同时打开目标；点击还在用户手势里，选文件这类也能打开
    phSheet.open(box, { title: '更多工具', opener: f.querySelector('.ph-more-b') });
  };
  const compose = () => {
    const page = document.getElementById('main')?.dataset.page || '';
    if (H.dataset.phPage !== page) H.dataset.phPage = page;
    pad();
    if (!on()) {  // 2026-11-17 UI 审查 U01：竖屏（手机布局）转横屏（电脑布局）时，把手机布局挪过的东西放回原处（以前留着，和直接横屏打开不一样）
      document.querySelectorAll('#main .ig-top-f').forEach(f => { const u = f._ph; if (!u) return; f._ph = 0;
        for (const [el, par, nx] of u.moved) if (el.isConnected || par.isConnected) par.insertBefore(el, nx?.parentNode === par ? nx : null);
        f.querySelector('.ph-more-b')?.remove();
        const ta = f.querySelector('textarea'); if (ta && u.rows != null && ta.rows !== u.rows) { ta.rows = u.rows; ta.dispatchEvent(new Event('input')); } });
      return;
    }
    if (!CPAGES.includes(page)) return;
    // 生视频页有两个输入框（生成 / 改视频，同时只显示一个）：每个都整理
    if (!compRO) compRO = new ResizeObserver(() => requestAnimationFrame(() => { const f = [...document.querySelectorAll('#main .ig-top-f')].find(x => x.getClientRects().length);
      const v = f ? Math.round(f.offsetHeight) + 'px' : ''; if (v && H.style.getPropertyValue('--ph-comp') !== v) H.style.setProperty('--ph-comp', v); pad(); }));
    document.querySelectorAll('#main .ig-top-f').forEach(f => {
      const ta0 = f.querySelector('textarea'), rows0 = f._ph ? f._ph.rows : ta0?.rows;
      if (ta0 && ta0.rows !== 1) { ta0.rows = 1; ta0.dispatchEvent(new Event('input')); }  // 页面重画输入框后也是一行起步
      if (f._ph) return; const u = f._ph = { moved: [], rows: rows0 };  // 记下挪了什么、原来在哪（转回电脑布局时放回去）
      const mv = (el, to) => { u.moved.push([el, el.parentNode, el.nextSibling]); to.append(el); };
      const row = f.querySelector('.ig-crow'), go = f.querySelector('.ig-cbar .ig-gen'), bl = f.querySelector('.ig-cbar > .bar-l');
      if (row && go) mv(go, row);
      const pk = f.querySelector('textarea')?._promptPeek; if (pk && bl && pk.parentNode) mv(pk, bl);
      // 11-16 用户：按钮太密。只留模型 / 模式 / 增强 / 尺寸这几个常用的胶囊，其余图标工具（AI 写、组合、高级参数、查看完整提示词、参考姿势……）收进最后一个“⋯”
      if (bl && !bl.parentElement.querySelector(':scope > .ph-more-b')) { const mb = Object.assign(document.createElement('button'), { type: 'button', className: 'ig-cb ph-more-b', innerHTML: DOTS_IC });
        mb.setAttribute('aria-label', '更多工具'); mb.onclick = () => toolsSheet(f); bl.after(mb); }  // “⋯”放在能左右滑的那排外面，一直在最右边看得见
      compRO.observe(f);
    });
  };
  addEventListener('DOMContentLoaded', () => { const m = document.getElementById('main'); if (!m) return; let r = 0;
    new MutationObserver(() => { if (!r) r = requestAnimationFrame(() => { r = 0; compose(); }); }).observe(m, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-page'] }); compose(); });
  const pad = () => {
    const m = document.getElementById('main'); if (!m) return; let sp = document.getElementById('ph-spacer');
    if (!on() || !CPAGES.includes(m.dataset.page)) { sp?.remove(); return; }
    if (!sp || sp.parentElement !== m) { sp?.remove(); sp = Object.assign(document.createElement('div'), { id: 'ph-spacer' }); sp.setAttribute('aria-hidden', 'true'); m.append(sp); }
    else if (sp !== m.lastElementChild) m.append(sp);
    const tops = [...document.querySelectorAll('#main .ig-top-f, #rail, #pbar')]  /* 生视频页有两个输入框（生成 / 改视频），只显示一个：都看 */.filter(e => { if (!e) return false; const c = getComputedStyle(e); return c.display !== 'none' && c.visibility !== 'hidden' && c.position === 'fixed' && e.getClientRects().length; })  /* fixed 元素的 offsetParent 永远是 null，不能拿它判断看不看得见 */.map(e => e.getBoundingClientRect().top).filter(t => t > innerHeight * .4);
    const h = Math.max(0, Math.ceil(innerHeight - Math.min(innerHeight, ...tops)) + 12) + 'px'; if (sp.style.height !== h) sp.style.height = h;
  };
  window.phPad = pad;
  addEventListener('resize', pad); addEventListener('load', pad);
  // 播放条在不在（输入框要不要再往上让出它的高度）
  const acc = () => { locShow(); const b = document.getElementById('pbar'); const v = on() && b && !b.classList.contains('idle') && !H.classList.contains('kb-open') && !H.classList.contains('ph-kb'); const n = v ? '64px' : '0px'; if (H.style.getPropertyValue('--ph-acc') !== n) H.style.setProperty('--ph-acc', n); requestAnimationFrame(pad); };
  addEventListener('DOMContentLoaded', () => { const b = document.getElementById('pbar'); if (b) new MutationObserver(acc).observe(b, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(acc).observe(H, { attributes: true, attributeFilter: ['class'] }); acc(); });
  // 键盘弹起：输入框贴着键盘上沿（fixed 是按整个窗口算的，键盘盖在上面）
  const vv = window.visualViewport, KTA = '#main .ig-top-f textarea, #main[data-page=prompt] .pg-composer textarea';  // 生图 / 生视频的底部输入框、AI 助手的输入框
  const kbGuess = () => { const h = innerHeight, k = +localStorage.getItem('phKb') || Math.round(h * .46); return Math.max(Math.round(h * .3), Math.min(Math.round(h * .6), k)); };  // 记下的键盘高度限制在屏幕的 30%~50%（以前记错过一次就一直抬得太高）
  const kbOff = () => { if (document.activeElement?.matches?.(KTA)) return; H.classList.remove('ph-kb'); };
  // 11-16 用户：上一版先挪输入框、再让浏览器自己聚焦——手指下面的框被挪走了，点击落空，键盘弹不出来。
  // 现在：手指离开时拦下浏览器自己的点击，先抬起输入框，再在这一下触摸里亲自聚焦（iOS 允许在触摸事件里聚焦、会弹键盘）；手指滑动过就不算点
  let kt = null;
  document.addEventListener('touchstart', e => { const ta = e.target.closest?.(KTA); kt = on() && ta && document.activeElement !== ta && e.touches.length === 1 ? { ta, x: e.touches[0].clientX, y: e.touches[0].clientY } : null; }, { passive: true, capture: true });
  document.addEventListener('touchmove', e => { if (kt && Math.hypot(e.touches[0].clientX - kt.x, e.touches[0].clientY - kt.y) > 8) kt = null; }, { passive: true, capture: true });
  document.addEventListener('touchend', e => { const k = kt; kt = null; if (!k || document.activeElement === k.ta || e.target.closest?.(KTA) !== k.ta) return;
    e.preventDefault();
    H.style.setProperty('--ph-kb', kbGuess() + 'px'); H.classList.add('ph-kb');
    k.ta.focus({ preventScroll: true }); const n = k.ta.value.length; try { k.ta.setSelectionRange(n, n); } catch { }
    setTimeout(kbOff, 600);
    // 保险：抬起来了但键盘没出来（可视区域没变矮）→ 放回底部，不悬在半空；这时框已经聚焦，再点一下 iOS 会自己弹键盘（走浏览器原来的路）
    kbCheck();
  }, { passive: false, capture: true });
  // 不管怎么聚焦的：0.9 秒后键盘没出来（可视区域没变矮）就放回底部（11-16 用户截图：改视频页输入框悬在半空）
  const kbCheck = () => setTimeout(() => { if (window.__phNoKbCheck || !vv || !H.classList.contains('ph-kb')) return; if (!kbUp()) H.classList.remove('ph-kb'); else kbFit(); }, 900);
  document.addEventListener('focusin', e => { if (on() && e.target.matches?.(KTA)) { if (!H.classList.contains('ph-kb')) H.style.setProperty('--ph-kb', kbGuess() + 'px'); H.classList.add('ph-kb'); kbCheck(); } });
  // 换页：收起抬起的状态、让输入框失去焦点（以前换到别的页面后还悬着）
  addEventListener('DOMContentLoaded', () => { const m = document.getElementById('main'); if (!m) return; let last = m.dataset.page;
    new MutationObserver(() => { if (m.dataset.page === last) return; last = m.dataset.page; H.classList.remove('ph-kb'); if (document.activeElement?.matches?.(KTA)) document.activeElement.blur(); }).observe(m, { attributes: true, attributeFilter: ['data-page'] }); });
  document.addEventListener('focusout', e => { if (e.target.matches?.(KTA)) setTimeout(kbOff, 120); });
  // 11-16 用户截图：AI 助手页键盘出来后输入框停在屏幕上半截。以前按“键盘高 = 窗口高 − 可视区域高”去抬，iOS 有时连窗口一起变矮、或者记下的高度不对，就抬多了。
  // 现在键盘出来以后量实际位置：输入框底边应该在可视区域底边上面 8px，差多少补多少（两种 iOS 行为都对）
  let fullH = innerHeight; addEventListener('resize', () => { if (!document.activeElement?.matches?.(KTA)) fullH = innerHeight; });
  const kbUp = () => !!vv && fullH - vv.height > 120;  // 键盘出来了：可视区域比没键盘时矮了一大截
  const kbFit = (n = 3) => { const ta = document.activeElement; if (!on() || !vv || !ta?.matches?.(KTA) || !kbUp()) return;
    const box = ta.closest('.ig-top-f') || ta.closest('.pg-in') || ta.closest('.pg-composer'); if (!box) return;
    const d = box.getBoundingClientRect().bottom - (vv.offsetTop + vv.height - 8), cur = parseFloat(H.style.getPropertyValue('--ph-kb')) || 0;
    if (Math.abs(d) > 1.5) { H.style.setProperty('--ph-kb', Math.max(0, Math.round(cur + d)) + 'px'); H.classList.add('ph-kb'); if (n > 1) requestAnimationFrame(() => kbFit(n - 1)); } };
  window.__phKbFit = kbFit;
  // 11-16 用户截图：收起键盘后输入框不见了。第三方输入法 / 键盘上的“⌄”只收起键盘、不让输入框失去焦点，
  // 以前只在键盘“出来”时处理，收起时什么也不做，输入框一直抬在原来键盘上沿（高度记错时就在屏幕外面）。
  // 现在：这次聚焦里见过键盘，之后可视区域又恢复了 = 键盘收起了 → 放回底部，并让输入框失去焦点（下次点它会正常弹键盘）
  let kbSeen = false;
  document.addEventListener('focusin', e => { if (e.target.matches?.(KTA)) kbSeen = false; });
  const kbv = () => { if (!vv || !on() || !document.activeElement?.matches?.(KTA)) return;
    if (!kbUp()) { if (kbSeen) { kbSeen = false; H.classList.remove('ph-kb'); document.activeElement.blur(); } return; }
    kbSeen = true;
    const b = Math.max(0, Math.round(innerHeight - vv.height - vv.offsetTop)), k = Math.round(fullH - vv.height);
    // 下次先按键盘的整个高度抬（第一下不被 iOS 把整页往上推）。11-16：以前记的是 b，iOS 推过页面时 b 少了被推的那段，下次抬得更少、又被推，越记越小
    if (innerHeight > fullH - 40 && k > 120 && k < fullH * .7) localStorage.setItem('phKb', k);
    H.style.setProperty('--ph-kb', b + 'px'); H.classList.add('ph-kb'); requestAnimationFrame(() => kbFit()); };  // 键盘出来了（包括第二次点才出来的）：先估、再量着补
  vv?.addEventListener('resize', kbv); vv?.addEventListener('scroll', kbv);

  // ---------- 侧栏导航（11-16 用户：底下又有导航栏又有输入框很丑——参考 ChatGPT / Claude 手机版，页面放到左边侧栏）----------
  // 11-16 第二次：全部页面都不显示底栏，左上角 ≡ 或从屏幕左边缘往右滑打开侧栏，里面是全部页面 + 设置与更多。
  // AI 助手页本来就有左边的对话记录抽屉：页面列表加在它最上面
  const dwOn = () => on();
  const MENU_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 8h16M4 16h11"/></svg>';
  const navHtml = compact => {  // compact：AI 助手的抽屉里只列常用的几个，其余收进“更多页面”（下面还要放对话记录）
    const P = window.navPages?.() || [], pins = window.navPinned?.() || [], cur = document.getElementById('main')?.dataset.page;
    const top = pins.map(p => P.find(x => x.p === p)).filter(Boolean), rest = P.filter(x => !pins.includes(x.p));
    const a = x => `<a href="/${x.p}" data-ph-go="${x.p}" class="${x.p === cur ? 'on' : ''}"${x.p === cur ? ' aria-current="page"' : ''}>${x.svg}<span>${x.n}</span></a>`;
    return `<nav class="ph-dw-nav" aria-label="页面">${top.map(a).join('')}${compact && rest.length ? `<details class="ph-dw-more"${rest.some(x => x.p === cur) ? ' open' : ''}><summary>${MORE_IC}<span>更多页面</span></summary>${rest.map(a).join('')}</details>` : rest.map(a).join('')}</nav>`;
  };
  const MORE_IC = '<svg viewBox="0 0 24 24"><circle cx="5.5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="18.5" cy="12" r="1.2"/></svg>';
  let dw = null, scrim = null;
  const dwBuild = () => {
    if (dw) return;
    dw = Object.assign(document.createElement('aside'), { id: 'ph-dw', className: 'ph-dw' }); dw.setAttribute('aria-label', '页面');
    scrim = Object.assign(document.createElement('div'), { className: 'ph-dw-scrim' });
    document.body.append(scrim, dw);
    scrim.onclick = () => dwOpen(false);
    scrim.addEventListener('touchmove', e => { if (e.cancelable) e.preventDefault(); }, { passive: false });
    dw.addEventListener('click', e => {
      const a = e.target.closest('[data-ph-go]'); if (a) { e.preventDefault(); dwOpen(false); const p = a.dataset.phGo; setTimeout(() => window.go?.(p), 60); return; }
      if (e.target.closest('[data-ph-more]')) { dwOpen(false); setTimeout(() => document.getElementById('side-gear')?.click(), 60); }
      if (e.target.closest('[data-ph-exit]')) { dwOpen(false); setTimeout(() => window.vaultLock?.(), 60); }
    });
  };
  // 私密空间里：设置上面多一行“退出私密空间”（11-19 用户：手机上不用再进设置找）。只在私密空间里才画出来
  const EXIT_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/></svg>';
  const inVault = () => document.body.classList.contains('vault');
  const dwPaint = () => { if (!dw) return; dw._v = inVault(); dw.innerHTML = `<div class="ph-dw-h">Studio</div>${navHtml()}<div class="ph-dw-foot">${dw._v ? `<button type="button" class="ph-dw-exit" data-ph-exit>${EXIT_IC}<span>退出私密空间</span></button>` : ''}<button type="button" data-ph-more>${(document.getElementById('side-gear')?.querySelector('svg')?.outerHTML) || ''}<span>设置</span></button></div>`; };
  const dwOpen = v => {
    const pg = document.getElementById('main')?.dataset.page;
    if (pg === 'prompt' && document.getElementById('pg-hist')) { document.body.classList.toggle('pg-hist-open', v); return; }  // AI 助手：用它自己的抽屉（上面加了页面列表）
    dwBuild(); if (v) dwPaint(); document.body.classList.toggle('ph-dw-open', v);
  };
  addEventListener('DOMContentLoaded', () => { if (on()) { dwBuild(); dwPaint(); } });  // 先建好：第一次打开也是滑出来的
  window.phDrawer = dwOpen;
  // 标题左边的 ≡（AI 助手页有它自己的）
  const CLOCK_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.3-5.6L4 8.7"/><path d="M4 4v4.7h4.7M12 8v4.5l3 2"/></svg>';
  const recIcon = () => { const r = document.querySelector('#main > .page-head > .m-dw-b'); if (!r || r._ph) return; r._ph = 1; const sv = r.querySelector('svg'); if (sv) sv.outerHTML = CLOCK_IC; };  // 换声 / 转文字 / 改录音的“记录”：时钟图标（以前两道横线，和 ≡ 一模一样）
  // 11-16 标题栏改成一行：右边的文字按钮（新建音色、校对设置）只放图标，字留给读屏
  const SLIDERS_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>';
  const iconBtns = () => { document.querySelectorAll('#main > .page-head > :is(#v-new, #llm-set)').forEach(b => { if (b._ph) return; b._ph = 1; const t = b.textContent.trim();
    if (!b.querySelector('svg')) { b.innerHTML = SLIDERS_IC + '<span></span>'; b.lastChild.textContent = t; } if (t) { b.setAttribute('aria-label', t); b.dataset.tip ||= t; } }); };
  // 11-16 用户：播放栏里有一个（播放中或暂停）时，一键回到它在列表里的位置：播放页标题栏右边（播放栏空着时不显示）
  const LOC_IC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/></svg>';
  const locBtn = () => { const h = document.querySelector('#main[data-page=play] > .page-head'); if (!h || h.querySelector(':scope > .ph-locate')) return;
    const b = Object.assign(document.createElement('button'), { type: 'button', className: 'ph-locate', innerHTML: LOC_IC }); b.setAttribute('aria-label', '回到正在播放的文件'); b.dataset.tip = '回到正在播放的文件';
    b.onclick = () => window.plGoCur?.(); h.append(b); locShow(); };
  const locShow = () => { const b = document.querySelector('#main > .page-head > .ph-locate'), p = document.getElementById('pbar'); if (b) b.hidden = !p || p.classList.contains('idle'); };
  const menuBtn = () => {
    recIcon(); iconBtns(); locBtn();
    const pg = document.getElementById('main')?.dataset.page;
    document.querySelectorAll('.ph-menu-b').forEach(b => { if (!dwOn() || pg === 'prompt' || !document.getElementById('main').contains(b)) b.remove(); });
    H.classList.toggle('ph-dwp', dwOn());
    if (!dwOn() || pg === 'prompt') return;
    const h = document.querySelector('#main > .page-head'); if (!h || h.querySelector('.ph-menu-b')) return;
    const b = Object.assign(document.createElement('button'), { type: 'button', className: 'ph-menu-b', innerHTML: MENU_IC }); b.setAttribute('aria-label', '页面'); b.onclick = () => dwOpen(true);
    const t = h.querySelector('.page-title'), ctx = h.querySelector(':scope > .b5-l, :scope > .b5-ctx, .pg-titlew');
    if (ctx?.classList.contains('b5-ctx')) { const w = document.createElement('div'); w.className = 'b5-l'; ctx.before(w); w.append(b, ctx); }
    else if (ctx) ctx.prepend(b);
    else if (t) t.before(b);
    else h.prepend(b);
  };
  // AI 助手的抽屉：最上面加页面列表（它每次重画都会清掉，所以看着它）
  const pgNav = () => { const h = document.getElementById('pg-hist'); if (!h || !on() || h.querySelector(':scope > .ph-dw-nav')) return; h.insertAdjacentHTML('afterbegin', navHtml(true)); };
  document.addEventListener('click', e => { const a = e.target.closest('#pg-hist [data-ph-go]'); if (!a) return; e.preventDefault(); e.stopPropagation(); document.body.classList.remove('pg-hist-open'); const p = a.dataset.phGo; setTimeout(() => window.go?.(p), 60); }, true);
  addEventListener('DOMContentLoaded', () => { const m = document.getElementById('main'); if (!m) return; let r = 0;
    new MutationObserver(() => { if (!r) r = requestAnimationFrame(() => { r = 0; menuBtn(); pgNav(); tab(); if (!dwOn()) document.body.classList.remove('ph-dw-open'); }); }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-page'] }); menuBtn(); });
  // ---------- 侧栏跟着手指走（11-16 用户：像 Claude / ChatGPT 的 iOS 应用，手滑到哪侧栏就到哪） ----------
  // 整页往右推开、变成圆角卡片，侧栏贴着页面左边一起出来；松手按位置 + 速度决定开还是关。
  // 页面里有 position: fixed 的东西（输入框、托盘、播放条……）：给祖先加位移会把它们“钉”到祖先上，
  // 所以不移动它们的祖先，而是一层层往下找：不含固定元素的整块移动，固定元素自己单独移动（都用 CSS translate，不碰原来的 transform）
  const drawerEl = () => (document.getElementById('main')?.dataset.page === 'prompt' && document.getElementById('pg-hist')) || (dwBuild(), dw);
  const openCls = d => d.id === 'pg-hist' ? 'pg-hist-open' : 'ph-dw-open';
  let pos = 0, layers = null, layD = null, raf = 0, frame = null;
  const skipEl = e => e === dw || e === scrim || e === frame || e.id === 'pg-hist' || e.id === 'sb-strip' || e.matches('script, style, link, template, .ph-sheet, .ph-sheet-bg, .pg-scrim');
  const collect = () => {
    const fx = [], w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, { acceptNode: e => {
      if (skipEl(e)) return NodeFilter.FILTER_REJECT; const c = getComputedStyle(e); if (c.display === 'none') return NodeFilter.FILTER_REJECT;
      if (c.position === 'fixed') { fx.push(e); return NodeFilter.FILTER_REJECT; } return NodeFilter.FILTER_SKIP; } });
    while (w.nextNode());
    const out = [], walk = el => { for (const c of el.children) { if (skipEl(c)) continue; if (fx.includes(c)) { out.push(c); continue; }
      if (fx.some(f => c.contains(f))) walk(c); else if (getComputedStyle(c).display !== 'none') out.push(c); } };
    walk(document.body); return out;
  };
  window.__phCollect = collect;
  const paint = x => {
    const d = layD || drawerEl(), Wd = d.offsetWidth || 330, p = Math.max(0, Math.min(1, x / Wd)); pos = x;
    if (x > 0 && !layers) layers = collect();
    if (layers && layers.some(e => !e.isConnected)) layers = collect();  // 换页了：重新找一遍
    for (const e of layers || []) e.style.translate = x ? `${x}px 0` : '';
    const tx = (x - Wd) * .3;  // 视差：侧栏走得比页面慢（一开始就看得到里面的字），超出页面左边的部分裁掉
    d.style.transition = 'none'; d.style.transform = `translate3d(${tx}px, 0, 0)`; d.style.clipPath = x >= Wd ? '' : `inset(0 ${Math.max(0, Wd + tx - x)}px 0 0)`; d.style.visibility = x > 0 ? 'visible' : 'hidden'; d.style.opacity = '1';
    if (scrim) { scrim.style.transition = 'none'; scrim.style.opacity = String(p); }
    if (!frame) { frame = Object.assign(document.createElement('div'), { className: 'ph-dw-frame' }); document.body.append(frame); }
    frame.style.display = x > 0 ? 'block' : 'none'; if (!x) frame.style.translate = '';
    if (x > 0) { frame.style.translate = `${x}px 0`; frame.style.borderRadius = Math.round(38 * p) + 'px';
      frame.style.setProperty('--dwbg', getComputedStyle(d).backgroundColor); }
    // 状态栏下面那条实色条（m.js #sb-strip）不跟着动、一直整宽盖在最上面：iOS 26 主屏幕 App 顶上没有这条整宽的实色条，就会把最上面一段糊掉
    // （11-16 用户截图：打开侧栏后侧栏的标题和页面标题都糊了）。开着时左边涂侧栏的底色、右边涂变暗后的页面底色
    const sb = document.getElementById('sb-strip');
    if (sb) { if (x > 0) { if (!sb._bg) sb._bg = getComputedStyle(sb).backgroundColor; sb.style.zIndex = '95';
        sb.style.background = `linear-gradient(90deg, ${getComputedStyle(d).backgroundColor} ${x}px, color-mix(in srgb, ${sb._bg} ${Math.round(100 - 32 * p)}%, #000) ${x}px)`; }
      else { sb.style.zIndex = ''; sb.style.background = ''; } }
    if (!x) layers = null;
  };
  // 动到 to（开 = 侧栏宽，关 = 0）；v = 松手时的速度（px/ms），越快越短
  const animTo = (to, v = 0) => {
    cancelAnimationFrame(raf); const from = pos, dist = Math.abs(to - from);
    if (!dist || matchMedia('(prefers-reduced-motion: reduce)').matches) { paint(to); return; }
    const dur = Math.max(160, Math.min(380, Math.abs(v) > .3 ? dist / Math.abs(v) * 1.6 : 380 * Math.max(.5, dist / 330))), t0 = performance.now();
    const step = now => { const t = Math.max(0, Math.min(1, (now - t0) / dur)), k = 1 - Math.pow(1 - t, 3); paint(from + (to - from) * k); if (t < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step);
  };
  let want = null;  // 自己改的开关状态（班级变化时不再重复动）
  const dwSync = () => {  // 开关状态（body 上的 ph-dw-open / pg-hist-open，别的代码也会直接改）→ 动过去
    if (dw && dw._v !== inVault()) dwPaint();  // 进出私密空间：“退出私密空间”那一行跟着出现 / 消失
    if (!dwOn() || drag) return; const d = drawerEl(); if (!d) return; const o = document.body.classList.contains(openCls(d));
    if (o === want) return; want = o; layD = d; animTo(o ? d.offsetWidth : 0);
  };
  addEventListener('DOMContentLoaded', () => new MutationObserver(dwSync).observe(document.body, { attributes: true, attributeFilter: ['class'] }));
  // 手指：左边缘往右拖 = 打开；开着时在侧栏或右边露出来的页面上往左拖 = 关上；竖着滑不管（侧栏里照常滚动）
  let drag = false, sx = null, sy = 0, base = 0, hist = [];
  document.addEventListener('touchstart', e => { sx = null; drag = false;
    if (!dwOn() || e.touches.length !== 1 || document.querySelector('.ph-sheet, .modal-bg, body.iv-open, #ig-mask-ov, #np:not([hidden])')) return;
    const t = e.touches[0], d = drawerEl(), open = document.body.classList.contains(openCls(d));
    if (!open && (t.clientX > 28 || plFolder())) return; if (open && t.clientX < pos - 1 && !d.contains(e.target)) return;  // 播放页在文件夹里：左边缘是“退回上个文件夹”（下面），侧栏只能点 ≡
    sx = t.clientX; sy = t.clientY; layD = d; base = open ? d.offsetWidth : 0; hist = [[performance.now(), t.clientX]]; }, { passive: true });
  document.addEventListener('touchmove', e => { if (sx == null) return; const t = e.touches[0], dx = t.clientX - sx, dy = t.clientY - sy;
    if (!drag) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; if (Math.abs(dy) > Math.abs(dx) || (base ? dx > 0 : dx < 0)) { sx = null; return; } drag = true; cancelAnimationFrame(raf); if (!base && layD === dw) dwPaint(); }  // 拖开：先按当前页面重画（高亮当前页）
    if (e.cancelable) e.preventDefault();
    const Wd = layD.offsetWidth; paint(Math.max(0, Math.min(Wd, base + t.clientX - sx))); hist.push([performance.now(), t.clientX]); if (hist.length > 6) hist.shift(); }, { passive: false });
  const endDrag = () => { if (sx == null) return; sx = null; if (!drag) return; drag = false;
    const Wd = layD.offsetWidth, now = performance.now(), hs = hist.filter(h => now - h[0] < 110), a = hs[0], b = hs[hs.length - 1], v = hs.length > 1 && b[0] - a[0] > 0 ? (b[1] - a[1]) / (b[0] - a[0]) : 0;  // 只看松手前 0.11 秒：停住再松手 = 速度 0
    const open = v > .35 || (v > -.35 && pos > Wd / 2);
    want = open; document.body.classList.toggle(openCls(layD), open); animTo(open ? Wd : 0, v); };
  document.addEventListener('touchend', endDrag, { passive: true }); document.addEventListener('touchcancel', endDrag, { passive: true });

  // ---------- 播放页：从左边缘往右滑 = 退回上个文件夹（2026-11-16 用户：只有播放页这样；最上面那层照样是打开侧栏）----------
  // 列表跟着手指往右走，松手够远（35% 屏宽）或甩得够快：滑出去，退回上一层（plmBack：子文件夹 → 上一层文件夹，第一层 → 文件夹列表），新的那层从左边滑进来；不够就弹回
  function plFolder() { return document.getElementById('main')?.dataset.page === 'play' && !!document.querySelector('#main .play-grid.m-list'); }
  { let g = null;
    const blocked = () => document.body.classList.contains('ph-dw-open') || document.querySelector('.ph-sheet, .modal-bg, body.iv-open, #np:not([hidden])');
    document.addEventListener('touchstart', e => { g = null; if (!on() || e.touches.length !== 1 || !plFolder() || blocked()) return; const t = e.touches[0]; if (t.clientX > 28) return;
      const el = document.getElementById('play-list'); if (!el) return; g = { x: t.clientX, y: t.clientY, el, on: false, dx: 0, h: [[performance.now(), t.clientX]] }; }, { passive: true });
    document.addEventListener('touchmove', e => { if (!g) return; const t = e.touches[0], dx = t.clientX - g.x, dy = t.clientY - g.y;
      if (!g.on) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; if (Math.abs(dy) > Math.abs(dx) || dx < 0) { g = null; return; } g.on = true; g.el.style.boxShadow = '-14px 0 30px rgba(0, 0, 0, .35)'; }
      if (e.cancelable) e.preventDefault();
      g.dx = Math.max(0, dx); g.el.style.transition = 'none'; g.el.style.transform = `translateX(${g.dx}px)`; g.h.push([performance.now(), t.clientX]); if (g.h.length > 6) g.h.shift(); }, { passive: false });
    const slideIn = () => {  // 新的那一层（播放页整页重画）出来时，从左边一点滑进来
      const m = document.getElementById('main'); if (!m) return; let done = false;
      const mo = new MutationObserver(() => { const pg = m.querySelector('.play-grid'); if (!pg || done) return; done = true; mo.disconnect();
        pg.style.transition = 'none'; pg.style.transform = 'translateX(-28%)'; pg.style.opacity = '.4'; pg.getBoundingClientRect();
        pg.style.transition = 'transform .3s cubic-bezier(.2, .8, .2, 1), opacity .3s ease'; pg.style.transform = ''; pg.style.opacity = '';
        setTimeout(() => { pg.style.transition = ''; }, 340); });
      mo.observe(m, { childList: true }); setTimeout(() => mo.disconnect(), 3000);
    };
    const end = () => { const k = g; g = null; if (!k?.on) return;
      const now = performance.now(), hs = k.h.filter(x => now - x[0] < 110), v = hs.length > 1 ? (hs[hs.length - 1][1] - hs[0][1]) / Math.max(1, hs[hs.length - 1][0] - hs[0][0]) : 0;
      const el = k.el;
      if (k.dx > innerWidth * .35 || (v > .35 && k.dx > 30)) {  // 11-16 用户：退回有点慢 → 滑出去只用 0.12 秒，马上就地重画（plmBack 不再整页重新取数据），新的一层同时从左边滑进来
        el.style.transition = 'transform .12s cubic-bezier(.3, .6, .4, 1)'; el.style.transform = `translateX(${innerWidth}px)`;
        setTimeout(() => {
          const m = document.getElementById('main'), local = window.plmBack?.() === true;
          if (m && local) {  // 就地重画了：直接把新的一层滑进来
            el.style.transition = 'none'; el.style.transform = ''; el.style.boxShadow = '';
            const pg = m.querySelector('.play-grid'); if (pg) { pg.style.transition = 'none'; pg.style.transform = 'translateX(-28%)'; pg.style.opacity = '.4'; pg.getBoundingClientRect();
              pg.style.transition = 'transform .26s cubic-bezier(.2, .8, .2, 1), opacity .22s ease'; pg.style.transform = ''; pg.style.opacity = ''; setTimeout(() => { pg.style.transition = ''; }, 300); }
          } else slideIn();  // 整页重画（拿不到就地重画时）：等新的画好再滑进来
        }, 110);
      } else { el.style.transition = 'transform .26s cubic-bezier(.2, .8, .2, 1)'; el.style.transform = ''; setTimeout(() => { el.style.transition = ''; el.style.boxShadow = ''; }, 280); } };
    document.addEventListener('touchend', end, { passive: true }); document.addEventListener('touchcancel', end, { passive: true });
  }

  // ---------- 底部面板 ----------
  // 11-16 用户：生图里打开素材库选素材，往上翻图片时（手指往下划）面板被收起了。以前只看面板自己滚没滚，素材库是里面的图片区在滚。
  // 现在：手指下面到面板为止，只要有一层滚动区不在最上面，这一下就是滚动、不是往下拉关闭（iOS 的面板也是这样）
  const scrolledIn = (t, root) => { for (let n = t; n && n !== root.parentElement; n = n.parentElement) if (n.scrollTop > 0 && /auto|scroll/.test(getComputedStyle(n).overflowY)) return true; return false; };
  // 松手：关的话从手指的位置接着往下滑出去（不再先弹回原位再消失）；不关就顺滑地弹回（11-16 用户：滑动操作的面板都要像侧栏一样有动画）
  const EASE = 'cubic-bezier(.2, .8, .2, 1)';
  const springBack = el => { el.style.transition = `transform .26s ${EASE}`; el.style.transform = ''; setTimeout(() => { if (!el.style.transform) el.style.transition = ''; }, 280); };
  // 往下拉关闭（2026-11-23 用户：下滑很难用，有时划不动、划到背后的页面）：
  // 用 touch 事件、不用 pointer——iPhone 上一开始滚动就 pointercancel，手指还没松就断了；pointermove 又是 passive，挡不住背后的页面跟着滚。
  // 第一下移动就判断：往下、竖着、（不在标题那一段时）里面的内容已经在最上面 → 当成拉面板，此后每次 preventDefault（内容、背后的页面都不动）；否则交给原生滚动
  const scroller = (t, root) => { for (let n = t; n && n !== root.parentElement; n = n.parentElement) { const cs = getComputedStyle(n); if (/auto|scroll/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 1) return n; } return null; };
  const pullDown = (root, o) => {
    let s = null;
    root.addEventListener('touchstart', e => { s = null; if (e.touches.length !== 1 || o.skip?.(e)) return; const t = e.touches[0];
      s = { x: t.clientX, y: t.clientY, t: performance.now(), head: !!o.isHead?.(e), sc: scroller(e.target, root), dy: 0, on: false }; }, { passive: true });
    root.addEventListener('touchmove', e => { if (!s) return; const t = e.touches[0], dy = t.clientY - s.y, dx = t.clientX - s.x;
      if (!s.on) { if (!dy && !dx) return; if (dy <= 0 || Math.abs(dx) > Math.abs(dy) || (!s.head && s.sc && s.sc.scrollTop > 0)) { s = null; return; } s.on = true; s.y = t.clientY - dy; s.t = performance.now(); }
      if (e.cancelable) e.preventDefault(); s.dy = Math.max(0, t.clientY - s.y); o.move(s.dy); }, { passive: false });
    const end = () => { const z = s; s = null; if (!z?.on) return; const v = z.dy / Math.max(1, performance.now() - z.t); o.end(z.dy > 110 || (z.dy > 30 && v > .6), z.dy); };
    root.addEventListener('touchend', end); root.addEventListener('touchcancel', end);
  };
  window.phPullDown = pullDown;
  let cur = null;
  const close = (instant) => {
    const s = cur; if (!s) return; cur = null;
    s.mo?.disconnect();
    // 2026-11-17 UI 审查 U02：焦点在面板里（或没有焦点）时，关掉当下就还给打开它的按钮——不等滑出动画结束，免得抢走接着打开的新面板的焦点
    const ae = document.activeElement; if (s.opener?.isConnected && s.opener.getClientRects().length && (!ae || ae === document.body || s.el.contains(ae))) s.opener.focus({ preventScroll: true });
    const fin = () => { if (s.ph?.isConnected) s.ph.replaceWith(s.node); else s.home?.append(s.node); s.el.remove(); s.bg.remove(); try { s.onClose?.(); } catch { } };
    s.el.classList.remove('on'); s.bg.classList.remove('on');
    if (instant || matchMedia('(prefers-reduced-motion: reduce)').matches) fin(); else setTimeout(fin, 300);
  };
  const open = (node, o = {}) => {
    // 关掉后焦点回到哪：调用方给的入口（o.opener；手机上点按钮不会让按钮拿到焦点）> 当时的焦点；从别的面板里打开的回到最早的那个入口
    const ae = document.activeElement, opener = cur && cur.el.contains(ae) ? cur.opener : o.opener || (ae && ae !== document.body ? ae : null);
    close(true);
    const bg = Object.assign(document.createElement('div'), { className: 'ph-sheet-bg' });
    const el = Object.assign(document.createElement('div'), { className: 'ph-sheet' });
    el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); if (o.title) el.setAttribute('aria-label', o.title);
    el.innerHTML = `<div class="ph-sheet-h"><div class="ph-sheet-hr"><span class="ph-sheet-t"></span><button type="button" class="ph-sheet-done">完成</button></div></div><div class="ph-sheet-b"></div>`;
    el.querySelector('.ph-sheet-t').textContent = o.title || '';
    const ph = document.createComment('ph-sheet'), home = node.parentNode; node.before(ph);
    el.querySelector('.ph-sheet-b').append(node);
    document.body.append(bg, el);
    const s = cur = { el, bg, node, ph, home, onClose: o.onClose, opener };
    el.tabIndex = -1;  // 焦点放在面板本身（不直接给里面的输入框：手机会弹出键盘）
    // 原来的浮层被别处关掉（藏起来）时，面板跟着关
    s.mo = new MutationObserver(() => { if (node.hidden) close(); }); s.mo.observe(node, { attributes: true, attributeFilter: ['hidden'] });
    bg.onclick = () => close(); el.querySelector('.ph-sheet-done').onclick = () => close();
    el.addEventListener('click', e => e.stopPropagation());
    // 往下拉关闭：标题那一块随时能拉；内容滚到顶以后往下拉也能拉
    const body = el.querySelector('.ph-sheet-b'); let y0 = null, dy = 0, t0 = 0, fromBody = false;
    pullDown(el, { isHead: e => !!e.target.closest('.ph-sheet-h'), skip: e => !!e.target.closest('input, textarea, select, [contenteditable], input[type=range], canvas, .ig-src, .gal-host'),
      move: dy => { el.classList.add('drag'); el.style.transform = `translateY(${dy}px)`; },
      end: (shut, dy) => { el.classList.remove('drag'); if (shut) { el.style.transition = `transform .26s ${EASE}`; el.style.transform = 'translateY(105%)'; close(); } else if (dy > 0) springBack(el); else el.style.transform = ''; } });
    const down = e => { if (e.pointerType !== 'mouse' || e.button) return; fromBody = !e.target.closest('.ph-sheet-h'); if (fromBody && scrolledIn(e.target, el)) return;
      if (fromBody && e.target.closest('input, textarea, select, [contenteditable], .seg, input[type=range], canvas, .ig-src, .gal-host')) return;  /* 涂抹画布、可以横滑的区域：不当成往下拉 */ y0 = e.clientY; dy = 0; t0 = performance.now(); };
    const move = e => { if (y0 == null) return; dy = Math.max(0, e.clientY - y0); if (dy > 6) { el.classList.add('drag'); el.style.transform = `translateY(${dy}px)`; if (fromBody) e.preventDefault(); } };
    const up = () => { if (y0 == null) return; const v = dy / Math.max(1, performance.now() - t0); y0 = null; el.classList.remove('drag');
      if (dy > 110 || (dy > 30 && v > .6)) { el.style.transition = `transform .26s ${EASE}`; el.style.transform = 'translateY(105%)'; close(); } else if (dy > 0) springBack(el); else el.style.transform = ''; };
    el.addEventListener('pointerdown', down); addEventListener('pointermove', move, { passive: false }); addEventListener('pointerup', up); addEventListener('pointercancel', up);
    const off = () => { removeEventListener('pointermove', move); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); };
    const oc = s.onClose; s.onClose = () => { off(); oc?.(); };
    requestAnimationFrame(() => requestAnimationFrame(() => { el.classList.add('on'); bg.classList.add('on'); if (cur === s && !el.contains(document.activeElement)) el.focus({ preventScroll: true }); }));
    return close;
  };
  window.phSheet = { on, open, close: () => close(), get open_() { return !!cur; } };
  addEventListener('keydown', e => { if (e.key === 'Escape' && cur) { e.stopPropagation(); close(); } }, true);
  addEventListener('popstate', () => close(true));

  // ---------- 弹窗（modal）：手机上从底部升起，往下拉关闭（拉上面那一段；里面滚到顶以后往下拉也行）----------
  { let d = null;
    document.addEventListener('pointerdown', e => { if (!on() || e.pointerType === 'touch') return; const m = e.target.closest?.('.modal-bg > .modal:not(.m-alert)'); if (!m || e.target.closest('input, textarea, select, canvas, [contenteditable], input[type=range], .seg')) return;
      // 放大的视频（全屏黑底，和看大图一样）：在画面上往下拉也能关，只有最下面播放器自己的进度条那一段不算（11-16）
      const vid = e.target.closest('video'); if (vid && !(m.matches('.vd-view:not(.ig-dview)') && e.clientY < vid.getBoundingClientRect().bottom - 56)) return;
      const r = m.getBoundingClientRect(); if (e.clientY - r.top > 64 && scrolledIn(e.target, m)) return; d = { m, y: e.clientY, t: performance.now(), dy: 0 }; }, true);
    addEventListener('pointermove', e => { if (!d) return; d.dy = Math.max(0, e.clientY - d.y); if (d.dy > 6) { d.m.style.transition = 'none'; d.m.style.transform = `translateY(${d.dy}px)`;
      if (d.m.matches('.vd-view:not(.ig-dview)')) { d.m.style.transform += ` scale(${Math.max(.85, 1 - d.dy / 1600)})`; d.m.parentElement.style.opacity = String(Math.max(.35, 1 - d.dy / 500)); } } }, { passive: true });  // 视频：像看大图那样跟着手缩小、背景变淡
    const up = () => { if (!d) return; const { m, dy, t } = d; d = null; const bg = m.parentElement;
      if (dy > 120 || (dy > 30 && dy / Math.max(1, performance.now() - t) > .6)) {  // 关：接着往下滑出去、背景淡掉，滑完再真的关
        const full = m.matches('.vd-view:not(.ig-dview)'); m.classList.add('ph-slid'); m.style.transition = `transform .26s ${EASE}`; m.style.transform = full ? 'translateY(70vh) scale(.85)' : 'translateY(105%)';
        if (bg) { bg.style.transition = 'opacity .26s ease'; bg.style.opacity = '0'; }
        setTimeout(() => { if (typeof m.close === 'function') m.close(); else m.closest('.modal-bg')?.querySelector('[data-close], .x')?.click();
          setTimeout(() => { if (m.isConnected && m.closest('.modal-bg')) { if (bg) bg.style.opacity = ''; springBack(m); } }, 400); }, 240);  // 没关掉（比如要先确认）：回到原位，不留在屏幕外
      } else { if (bg) { bg.style.transition = 'opacity .2s ease'; bg.style.opacity = ''; } if (dy > 0) springBack(m); else { m.style.transition = ''; m.style.transform = ''; } } };
    addEventListener('pointerup', up); addEventListener('pointercancel', up);
    // 手指：每个弹窗出现时挂一次 pullDown（规则和上面一样：放大的视频在画面上也能拉，表单控件不算）
    const full = m => m.matches('.vd-view:not(.ig-dview)');
    const hook = m => { if (m._pd || m.matches('.m-alert')) return; m._pd = 1;
      pullDown(m, { isHead: e => e.touches[0].clientY - m.getBoundingClientRect().top < 64,
        skip: e => { if (e.target.closest('input, textarea, select, canvas, [contenteditable], input[type=range], .seg')) return true; const v = e.target.closest('video'); return !!v && !(full(m) && e.touches[0].clientY < v.getBoundingClientRect().bottom - 56); },
        move: dy => { m.style.transition = 'none'; m.style.transform = `translateY(${dy}px)` + (full(m) ? ` scale(${Math.max(.85, 1 - dy / 1600)})` : ''); if (full(m)) m.parentElement.style.opacity = String(Math.max(.35, 1 - dy / 500)); },
        end: (shut, dy) => { d = { m, dy, t: shut ? performance.now() - 1 : 0 }; if (shut) d.dy = Math.max(dy, 121); up(); } }); };
    new MutationObserver(ms => { if (!on()) return; for (const r of ms) for (const n of r.addedNodes) if (n.classList?.contains('modal-bg')) { const m = n.querySelector(':scope > .modal'); if (m) hook(m); } }).observe(document.body, { childList: true });
    // 点弹窗外面（露出来的那一截）关掉；在那一截上滑动不带动背后的页面
    // 按下、松开都在露出来的那一截上才算（iPhone 点不可点的 div 不一定有 click）；面板（phSheet）的那一截同理
    let bgDown = null;
    document.addEventListener('pointerdown', e => { bgDown = on() && (e.target.classList?.contains('modal-bg') || e.target.classList?.contains('ph-sheet-bg')) ? e.target : null; }, true);
    document.addEventListener('pointerup', e => { const b = bgDown; bgDown = null; if (!b || e.target !== b) return;
      if (b.classList.contains('ph-sheet-bg')) return void b.click();
      const m = b.querySelector(':scope > .modal'); if (!m || m.matches('.m-alert')) return;
      if (typeof m.close === 'function') m.close(); else m.querySelector('[data-close], .x')?.click(); }, true);
    document.addEventListener('touchmove', e => { if (on() && e.cancelable && (e.target.classList?.contains('modal-bg') || e.target.classList?.contains('ph-sheet-bg'))) e.preventDefault(); }, { passive: false }); }

  // ---------- 列表行 / 格子按下的样子（11-16 用户：按着慢慢滑也会亮）：手指不动 0.2 秒才亮，一动（6px）就灭；点一下松手时亮一下 ----------
  { const SEL = '.pl-row, .pl-card, .ps-item, .work, .rec, .lp-it, .vp, .ig-tile, .img-tile, .vd-tile, .gal-card, .gal-fd'; let pr = null;
    const off = () => { if (!pr) return; clearTimeout(pr.t); pr.el.classList.remove('ph-press'); pr = null; };
    document.addEventListener('touchstart', e => { off(); if (!on() || e.touches.length !== 1) return; const el = e.target.closest?.(SEL); if (!el) return;
      const t = e.touches[0]; pr = { el, x: t.clientX, y: t.clientY, lit: false }; pr.t = setTimeout(() => { if (pr?.el === el) { el.classList.add('ph-press'); pr.lit = true; } }, 200); }, { passive: true, capture: true });
    document.addEventListener('touchmove', e => { if (pr && Math.hypot(e.touches[0].clientX - pr.x, e.touches[0].clientY - pr.y) > 6) off(); }, { passive: true, capture: true });
    document.addEventListener('touchend', () => { if (!pr) return; const p0 = pr; clearTimeout(p0.t); pr = null;
      if (p0.lit) setTimeout(() => p0.el.classList.remove('ph-press'), 80); else { p0.el.classList.add('ph-press'); setTimeout(() => p0.el.classList.remove('ph-press'), 130); } }, { passive: true, capture: true });  // 点一下：松手时亮一下，看得出点到了
    document.addEventListener('touchcancel', off, { passive: true, capture: true });
    addEventListener('scroll', off, { passive: true, capture: true });
  }

  // ---------- 长按 = 右键菜单 ----------
  let lp = null;
  const cancel = () => { if (lp) { clearTimeout(lp.t); lp = null; } };
  document.addEventListener('touchstart', e => {
    if (!on() || e.touches.length !== 1) return cancel();
    if (e.target.closest?.('.pl-row, .img-tile, .ps-dir, .pl-dirhit, .ig-tile')) return cancel();  // 这些 app.js 自己就有长按菜单：不重复弹
    const t = e.target.closest?.('[data-lp], .vd-card, .vd-tile, .work, .gal-card, .gal-it, .mt-it, [oncontextmenu]'); if (!t) return;
    const p = e.touches[0]; cancel();
    lp = { x: p.clientX, y: p.clientY, el: t, t: setTimeout(() => { const l = lp; lp = null; if (!l?.el.isConnected) return;
      const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: l.x, clientY: l.y, button: 2 });
      if (!l.el.dispatchEvent(ev)) { l.fired = true; navigator.vibrate?.(8); window.__lpFired = performance.now(); } }, 480) };
  }, { passive: true });
  document.addEventListener('touchmove', e => { if (lp && Math.hypot(e.touches[0].clientX - lp.x, e.touches[0].clientY - lp.y) > 10) cancel(); }, { passive: true });
  document.addEventListener('touchend', cancel, { passive: true }); document.addEventListener('touchcancel', cancel, { passive: true });
  // 长按出了菜单：松手那一下不要再当成点击
  document.addEventListener('click', e => { if (window.__lpFired && performance.now() - window.__lpFired < 700) { e.preventDefault(); e.stopPropagation(); window.__lpFired = 0; } }, true);
})();
/* 网页改不了音量的手机（iPhone：媒体音量只读，2026-11-18 用户：调不了就不要音量条）：全屏播放页不显示音量条，用手机侧面的音量键 */
try { const a = document.createElement('audio'); a.volume = 0.5; if (Math.abs(a.volume - 0.5) > 0.01) document.documentElement.classList.add('no-vol'); } catch { }
