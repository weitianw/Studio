/* Interface language: English (default) or Chinese, switched in Settings -> Appearance (localStorage "studio.lang").
   The UI source strings are Chinese. In English mode, a runtime layer replaces Chinese UI text with English in place,
   using a dictionary extracted from the source (i18n-en.js): text nodes and the title / placeholder / aria-label / data-tip / alt
   attributes, kept up to date with a MutationObserver. Text the user types (inputs, textareas, editable areas) is never changed.
   Native alert / confirm / prompt messages and the document title are translated the same way. */
(() => {
  let lang = 'en';
  try { lang = localStorage.getItem('studio.lang') || 'en'; } catch (e) { /* private mode */ }
  window.STUDIO_LANG = lang;
  window.setStudioLang = v => { try { localStorage.setItem('studio.lang', v); } catch (e) { } location.reload(); };
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  const D = window.I18N_EN;
  window.t = s => s;
  if (lang !== 'en' || !D) return;
  const HAN = /[一-鿿]/;
  const keys = Object.keys(D).filter(k => k && D[k]).sort((a, b) => b.length - a.length);
  const RX = new RegExp(keys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  const PUNCT = [[/，\s*/g, ', '], [/。\s*/g, '. '], [/：\s*/g, ': '], [/；\s*/g, '; '], [/、\s*/g, ', '], [/！\s*/g, '! '], [/？\s*/g, '? '],
    [/（/g, ' ('], [/）/g, ') '], [/[“”]/g, '"'], [/[‘’]/g, "'"], [/…/g, '…'], [/～/g, '~'], [/《|》/g, '"'], [/【/g, '['], [/】/g, ']']];
  const WORD = /[A-Za-z0-9)\]%"]/, WORD_R = /[A-Za-z0-9(["]/;
  const cache = new Map();
  const tidy = (s, r) => {  // fully translated: switch the remaining full-width punctuation to ASCII
    const lead = /^\s/.test(s), trail = /\s$/.test(s);
    for (const [a, b] of PUNCT) r = r.replace(a, b);
    r = r.replace(/ {2,}/g, ' ').replace(/ ([,.;:!?)])/g, '$1').replace(/\( /g, '(');
    return (lead ? ' ' : '') + r.trim() + (trail ? ' ' : '');
  };
  // One piece of text (no HTML tags): exact entry first; otherwise assemble it from fragments (text built from a template
  // with numbers or names in between). A piece that cannot be translated completely is left as it is, never half-translated.
  const piece = s => {
    if (!HAN.test(s)) return s;
    const t = s.trim();
    if (D[t]) return s.replace(t, D[t]);
    let r = s.replace(RX, (m, off, str) => {
      const p = str[off - 1], n = str[off + m.length];
      if (m.length === 1 && ((p && HAN.test(p)) || (n && HAN.test(n)))) return m;  // a single character inside a word: not a fragment
      let e = D[m];
      if (p && WORD.test(p) && /^[A-Za-z(]/.test(e)) e = ' ' + e;
      if (n && WORD_R.test(n) && /[A-Za-z)]$/.test(e)) e += ' ';
      return e;
    });
    return HAN.test(r) ? s : tidy(s, r);
  };
  const tr = s => {
    if (!s || !HAN.test(s)) return s;
    let r = cache.get(s);
    if (r !== undefined) return r;
    r = s.includes('<') ? s.split(/(<[^>]*>)/).map(x => x.startsWith('<') ? x : piece(x)).join('') : piece(s);
    if (cache.size > 20000) cache.clear();
    cache.set(s, r);
    return r;
  };
  window.t = tr;
  const ATTRS = ['title', 'placeholder', 'aria-label', 'data-tip', 'alt', 'data-label', 'data-title'];
  const SKIP = 'script, style, .no-i18n';  // never touched
  const SKIP_TEXT = 'script, style, textarea, [contenteditable=""], [contenteditable="true"], .no-i18n';  // user-written text: placeholder / title still translated
  const skipEl = el => !el || (el.closest && el.closest(SKIP));
  const doText = n => { const p = n.parentElement; if (!p || p.closest(SKIP_TEXT)) return; const v = n.nodeValue, r = tr(v); if (r !== v) n.nodeValue = r; };
  const doAttrs = el => {
    if (el.closest && el.closest('.no-i18n')) return;
    for (const a of ATTRS) { const v = el.getAttribute(a); if (v && HAN.test(v)) { const r = tr(v); if (r !== v) el.setAttribute(a, r); } }
    if (el.tagName === 'INPUT' && /^(button|submit|reset)$/i.test(el.type) && HAN.test(el.value)) el.value = tr(el.value);
  };
  const walk = root => {
    if (root.nodeType === 3) return doText(root);
    if (root.nodeType !== 1 || skipEl(root)) return;
    doAttrs(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: n => n.nodeType === 1 && n.matches(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeType === 3 ? doText(n) : doAttrs(n);
  };
  const mo = new MutationObserver(list => {
    for (const m of list) {
      if (m.type === 'childList') m.addedNodes.forEach(walk);
      else if (m.type === 'characterData') doText(m.target);
      else if (m.type === 'attributes') doAttrs(m.target);
    }
  });
  mo.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  document.addEventListener('DOMContentLoaded', () => walk(document.documentElement));
  for (const f of ['alert', 'confirm', 'prompt']) { const o = window[f]; window[f] = (msg, ...a) => o.call(window, tr(String(msg ?? '')), ...a); }
})();
