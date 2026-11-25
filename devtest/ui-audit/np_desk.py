"""电脑版全屏播放页（2026-11-17 用户：字幕高亮右边是直角、颜色不好；换句不丝滑；左上角收起和旁边按钮太近、音频时按钮放右边；播放列表行错位）。
测试音频（静音）+ 测试自己编的字幕（接口换掉），截图到 shots_np_desk。用法：python np_desk.py [宽 高] [--rc]"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_np_desk'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
W, H = (int(args[0]), int(args[1])) if len(args) >= 2 else (1440, 900)
LINES = ['这是测试用的第一句字幕', '第二句稍微长一点，看看换行以后是什么样子，再长一点，再长一点让它换行', '第三句', '停顿之后的第四句', '第五句，正在播的应该是这句',
         '第六句', '第七句也是测试文字', '第八句', '第九句', '最后一句']
SENTS = [{'s': i * 4.0, 'e': i * 4.0 + 3.2, 'text': t} for i, t in enumerate(LINES)]


def open_np(p):
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': W, 'height': H})
    pg.route('**/api/play/subs?**', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'state': 'done', 'sents': SENTS, 'language': 'zh'}, ensure_ascii=False)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1600)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("npOpen()"); pg.wait_for_timeout(1000)
    pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(1500)
    pg.evaluate("(() => { const a = PB.a; a.pause(); Object.defineProperty(a, 'currentTime', { get: () => window.__t ?? 17, set: v => { window.__t = v; }, configurable: true }); a.dispatchEvent(new Event('timeupdate')); })()"); pg.wait_for_timeout(1200)
    pg.evaluate("document.querySelectorAll('.np img, .np video').forEach(e => e.style.visibility = 'hidden')")
    return b, pg


if __name__ == '__main__':
    with sync_playwright() as p:
        b, pg = open_np(p)
        print(pg.evaluate("""(() => { const q = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
          const on = document.querySelector('#np-right .sub.on'), c = on && getComputedStyle(on);
          return { close: q('#np-close'), tabs: q('.np-tabs'), top: q('.np-top'), right: q('#np-right'), tools: q('#np-right .subs-tools'), on: q('#np-right .sub.on'), list: q('#np-right .subs'),
            onBg: c?.backgroundColor, onTr: c?.transform, onRadius: c?.borderRadius }; })()"""))
        pg.screenshot(path=os.path.join(OUT, f'subs_{W}.png'))
        pg.evaluate("npSetView('queue')"); pg.wait_for_timeout(900)
        pg.screenshot(path=os.path.join(OUT, f'queue_{W}.png'))
        b.close()


def rc_queue(p):
    """控制手机时的播放列表（RC.ctl）：用测试自己的假数据画一次，量标题那一列的宽度"""
    b, pg = open_np(p)
    pg.evaluate("RC.ctl = true; RC.st = { i: 0, age: 1 }; RC.queue = Array.from({ length: 6 }, (_, k) => ({ title: '测试音频标题比较长的一条 ' + (k + 1), sub: '测试作者' })); npSetView('queue'); qPanelPaint?.()")
    pg.wait_for_timeout(900)
    r = pg.evaluate("[...document.querySelectorAll('.np .ql-row')].slice(0, 3).map(x => { const m = x.querySelector('.ql-main').getBoundingClientRect(), a = x.firstElementChild.getBoundingClientRect(); return { main: Math.round(m.width), artRight: Math.round(a.right), mainLeft: Math.round(m.left) }; })")
    pg.screenshot(path=os.path.join(OUT, f'rcqueue_{W}.png'))
    pg.evaluate("RC.ctl = false")
    b.close()
    return r


if __name__ == '__main__' and '--rc' in sys.argv:
    with sync_playwright() as p:
        print(rc_queue(p))


def glide(p):
    """换句时的滚动：每 50 毫秒记一次 scrollTop，看是不是一路平滑地到位（不跳、不停顿、不回弹）"""
    b, pg = open_np(p)
    r = pg.evaluate("""async () => { const list = document.querySelector('#np-right .subs'), a = PB.a, out = [];
      window.__t = 17; a.dispatchEvent(new Event('timeupdate')); await new Promise(r => setTimeout(r, 1200));
      window.__t = 21; a.dispatchEvent(new Event('timeupdate'));
      for (let i = 0; i < 18; i++) { out.push(Math.round(list.scrollTop)); await new Promise(r => setTimeout(r, 50)); }
      return out; }""")
    b.close()
    return r


if __name__ == '__main__' and '--glide' in sys.argv:
    with sync_playwright() as p:
        s = glide(p); d = [b - a for a, b in zip(s, s[1:])]
        print('scrollTop', s); print('step', d)
        print('单调不回弹', all(x >= 0 for x in d) or all(x <= 0 for x in d), '先快后慢', abs(d[1]) >= abs(d[-1]))
