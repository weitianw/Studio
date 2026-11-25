"""全屏播放页的性能（2026-11-17 用户：字幕切换时有点卡；优化一下性能）。
放 200 句测试字幕，每 0.7 秒换一句，量这段时间里每一帧的间隔（rAF），比较几种做法：
  base   = 现在的样子
  其他   = 用 --css 注入的样式（试验用）
另外量“外观”的背景（封面雾色）每帧的耗时。用法：python np_perf.py [宽 高]"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import np_desk
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
np_desk.W, np_desk.H = (int(args[0]), int(args[1])) if len(args) >= 2 else (1920, 1080)
np_desk.SENTS[:] = [{'s': i * 2.0, 'e': i * 2.0 + 1.7, 'text': f'第 {i + 1} 句测试字幕，' + '长一点的句子会换行' * (i % 3)} for i in range(200)]

MEASURE = r"""async ([n, gap]) => {
  const a = PB.a; const ts = []; let on = true;
  const loop = t => { ts.push(t); if (on) requestAnimationFrame(loop); }; requestAnimationFrame(loop);
  for (let i = 0; i < n; i++) { window.__t = 40 + i * 2.0 + .1; a.dispatchEvent(new Event('timeupdate')); await new Promise(r => setTimeout(r, gap)); }
  on = false; await new Promise(r => setTimeout(r, 50));
  const d = []; for (let i = 1; i < ts.length; i++) d.push(ts[i] - ts[i - 1]); d.sort((x, y) => x - y);
  const p = q => d[Math.min(d.length - 1, Math.floor(d.length * q))];
  return { frames: d.length, p50: +p(.5).toFixed(1), p95: +p(.95).toFixed(1), max: +d[d.length - 1].toFixed(1), long: d.filter(x => x > 25).length };
}"""


def run(p, look, css=''):
    b, pg = np_desk.open_np(p)
    pg.evaluate("([s]) => { S.ui = { ...(S.ui || {}), npLook: { s, color: 'cover', art: 'show' } }; npPaint(true); }", [look])
    if css: pg.add_style_tag(content=css)
    pg.wait_for_timeout(1200)
    r = pg.evaluate(MEASURE, [10, 700])
    b.close()
    return r


if __name__ == '__main__':
    VARIANTS = {
        'base': '',
    }
    with sync_playwright() as p:
        for look in ('orig', 'mist', 'solid'):
            for k, css in VARIANTS.items():
                print(look, k, run(p, look, css), flush=True)
