"""AI 助手页最上面那块的结构（2026-11-16，查标题栏改版后 AI 助手页变样）。用法：python ip_probe_prompt.py"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
JS = r"""() => { const out = [];
  const w = (e, lv) => { if (lv > 5) return; const r = e.getBoundingClientRect(), s = getComputedStyle(e); if (s.display === 'none' || r.top > 260 || !r.width) return;
    out.push('  '.repeat(lv) + e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ').slice(0, 3).join('.') + ' ' + [r.left, r.top, r.width, r.height].map(Math.round) + ' ' + s.display + ' ' + s.position);
    [...e.children].forEach(c => w(c, lv + 1)); };
  w(document.getElementById('main'), 0); return out.slice(0, 45).join('\n'); }"""
if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.evaluate("go('prompt')"); pg.wait_for_timeout(2500)
        print(pg.evaluate(JS))
        br.close()
