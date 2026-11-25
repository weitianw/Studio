/* 手机 / 平板（没有鼠标悬停）专用：让点按像原生 App 一样“点一下就生效”。
   - iPhone 的 Safari 会把第一下点按先当成“鼠标移上去”：如果 :hover 会让东西出现 / 变样（列表里的按钮、卡片上的操作……），
     第一下就只触发了悬停，要再点一次才算点击 —— 用起来像卡了一下。这里在手机上把样式表里所有 :hover 规则去掉，
     这样每次点按都直接是点击。电脑上不处理（鼠标悬停照常）。
   - 换成“按下时”的反馈：按住的那一下变暗一点 / 缩一点（:active），松手就恢复，和原生 App 一样。
   - 去掉点按时浏览器自带的灰色闪框、双击放大，长按按钮不会选中按钮上的字。 */
'use strict';
(() => {
  const touch = matchMedia('(hover: none)').matches;
  if (!touch) return;
  document.documentElement.classList.add('touch');

  // 1) 去掉所有 :hover 规则（只处理本站的样式表；规则里有几个选择器时只去掉带 :hover 的那几个）
  const strip = list => {
    for (let i = list.length - 1; i >= 0; i--) {
      const r = list[i];
      if (r.cssRules && !(r instanceof CSSStyleRule)) { strip(r.cssRules); continue; }  // @media / @supports 里面的
      if (!(r instanceof CSSStyleRule) || !r.selectorText.includes(':hover')) continue;
      const keep = r.selectorText.split(/,(?![^(]*\))/).map(s => s.trim()).filter(s => !s.includes(':hover'));
      try { if (keep.length) r.selectorText = keep.join(', '); else (r.parentRule || r.parentStyleSheet).deleteRule(i); } catch { }
    }
  };
  const run = () => {
    for (const sh of document.styleSheets) {
      if (sh._noHover) continue;
      try { if (!sh.cssRules.length) continue; strip(sh.cssRules); sh._noHover = true; } catch { }  // 还没加载完：下次再处理；别的网站的样式表读不到规则：跳过
    }
  };
  run();
  addEventListener('DOMContentLoaded', run);
  addEventListener('load', run);

  // 2) 按下时的反馈 + 去掉浏览器自带的点按闪框、双击放大、长按选字
  const st = document.createElement('style');
  st.textContent = `
    html.touch { -webkit-tap-highlight-color: transparent; }
    html.touch body { touch-action: manipulation; }
    html.touch :where(button, a, .btn, .chip, .seg button, .pl-row, .pl-card, .ps-item, .gp-link, .nav a, .vp, .work, .rec, .ig-tile, .img-tile, .lp-it, .pl-ib, .pb-btn, .pb-icon, [role=button]) {
      -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;
      transition-property: transform, opacity, background-color, color, box-shadow; }
    html.touch :where(button, .btn, .chip, .pl-ib, .pb-btn, .pb-icon, .gp-link, .nav a, [role=button]):active:not(:disabled) { opacity: .62; transform: scale(.97); transition-duration: 0s; }
    html.touch :where(.pl-row, .ps-item, .work, .rec, .lp-it, .vp):active { background-color: rgba(127, 127, 127, .14); transition-duration: 0s; }
    html.touch :where(.pl-card, .ig-tile, .img-tile):active { transform: scale(.98); transition-duration: 0s; }
    html.touch :where(input, textarea, [contenteditable]) { -webkit-user-select: text; user-select: text; }
  `;
  document.head.append(st);
})();
