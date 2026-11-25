"""手机界面巡视（2026-11-16）：模拟 iPhone 16 Pro Max，按顺序走遍各页面、各状态，每一步截一张图，给人一张张看（shots_iphone/tour/编号_名字.png）。
图片都换成测试图（iphone.py 的 sfw），视频不加载。用法：python ip_tour.py [只跑名字里含这些字的步骤 ...] [--light]"""
import os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'tour'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
LIGHT = '--light' in sys.argv
ONLY = [a for a in sys.argv[1:] if not a.startswith('--')]


def tap(pg, sel, i=0):
    els = [e for e in pg.query_selector_all(sel) if e.bounding_box()]
    if len(els) <= i:
        print('  没有', sel); return False
    b = els[i].bounding_box(); pg.touchscreen.tap(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.wait_for_timeout(800); return True


def js(pg, code):
    try:
        return pg.evaluate(code)
    except Exception as e:
        print('  js 出错', str(e)[:120])


def go(pg, page):
    js(pg, f"go({page!r})"); pg.wait_for_timeout(1600); hide(pg); js(pg, "scrollTo(0, 0)"); pg.wait_for_timeout(300)


def reset(pg):
    js(pg, "document.activeElement?.blur?.(); window.__phNoKbCheck = false; document.documentElement.classList.remove('ph-kb')")
    js(pg, "document.querySelector('.ph-sheet-done')?.click(); document.querySelectorAll('.modal-bg [data-close], .modal-bg .x').forEach(b => b.click()); ctxClose?.(true); ImageViewer?.close?.(); document.body.classList.remove('ph-dw-open', 'pg-hist-open', 'mdw-open')")
    pg.wait_for_timeout(500)


STEPS = []
def step(name):
    def d(f):
        STEPS.append((name, f)); return f
    return d


@step('播放')
def _(pg): go(pg, 'play')
@step('播放-文件夹')
def _(pg): go(pg, 'play'); js(pg, "[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1500)
@step('侧栏')
def _(pg): go(pg, 'play'); tap(pg, '.ph-menu-b'); pg.wait_for_timeout(500)
@step('设置与更多')
def _(pg): go(pg, 'play'); tap(pg, '.ph-menu-b'); pg.wait_for_timeout(400); tap(pg, '#ph-dw [data-ph-more]'); pg.wait_for_timeout(900)
@step('生图')
def _(pg): go(pg, 'img')
@step('生图-滚动')
def _(pg): go(pg, 'img'); js(pg, "scrollTo(0, 900)"); pg.wait_for_timeout(700)
@step('生图-写了字')
def _(pg): go(pg, 'img'); js(pg, "(() => { const t = document.querySelector('#ig-prompt'); t.value = '一位二十岁出头的中国女生坐在海边礁石上，白色吊带裙，海风吹起头发，傍晚逆光，胶片质感'; t.dispatchEvent(new Event('input', { bubbles: true })); })()"); pg.wait_for_timeout(400)
@step('生图-选模型')
def _(pg): go(pg, 'img'); tap(pg, '#ig-model')
@step('生图-增强')
def _(pg): go(pg, 'img'); js(pg, "[...document.querySelectorAll('.ig-chips > .ig-chip')].find(c => c.textContent.includes('增强'))?.click()"); pg.wait_for_timeout(800)
@step('生图-尺寸')
def _(pg): go(pg, 'img'); js(pg, "[...document.querySelectorAll('.ig-chips > .ig-chip')].filter(c => !c.hidden).pop()?.click()"); pg.wait_for_timeout(800)
@step('生图-更多工具')
def _(pg): go(pg, 'img'); tap(pg, '#main .ig-top-f .ph-more-b'); pg.wait_for_timeout(700)
@step('生图-高级参数')
def _(pg): go(pg, 'img'); tap(pg, '#main .ig-top-f .ph-more-b'); pg.wait_for_timeout(700); js(pg, "[...document.querySelectorAll('.ph-tools button')].find(b => /高级/.test(b.textContent))?.click()"); pg.wait_for_timeout(1200)
@step('生视频-更多工具')
def _(pg): go(pg, 'video'); tap(pg, '#main .ig-top-f .ph-more-b'); pg.wait_for_timeout(700)
@step('生图-放了图')
def _(pg): go(pg, 'img'); pg.query_selector('#ig-file').set_input_files(os.path.join(HERE, 'aud_grid.png')); pg.wait_for_timeout(1500)
@step('生图-原图面板')
def _(pg): go(pg, 'img'); pg.query_selector('#ig-file').set_input_files(os.path.join(HERE, 'aud_grid.png')); pg.wait_for_timeout(1500); tap(pg, '.ig-srct')
@step('生图-局部重画')
def _(pg):
    go(pg, 'img'); js(pg, "document.querySelector('#ig-model').click()"); pg.wait_for_timeout(600); js(pg, "document.querySelector('.igm-v[data-m=\"q21\"]')?.click()"); pg.wait_for_timeout(900)
    pg.query_selector('#ig-file').set_input_files(os.path.join(HERE, 'aud_grid.png')); pg.wait_for_timeout(1500)
    js(pg, "document.querySelector('#ig-mode button[data-k=\"inpaint\"]')?.click()"); pg.wait_for_timeout(1000); tap(pg, '.ig-srct')
@step('生图-看大图')
def _(pg): go(pg, 'img'); tap(pg, '.ig-gal .ig-tile'); pg.wait_for_timeout(700)
@step('生图-长按')
def _(pg):
    go(pg, 'img'); js(pg, """(async () => { const t = document.querySelector('.ig-gal .ig-tile'), r = t.getBoundingClientRect(); const tc = { identifier: 1, target: t, clientX: r.left + 30, clientY: r.top + 30 };
      const ev = (n, ts) => { const e = new Event(n, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'touches', { value: ts }); Object.defineProperty(e, 'changedTouches', { value: [tc] }); t.dispatchEvent(e); };
      ev('touchstart', [tc]); await new Promise(r => setTimeout(r, 650)); ev('touchend', []); })()"""); pg.wait_for_timeout(900)
@step('生图-键盘')
def _(pg): go(pg, 'img'); js(pg, "window.__phNoKbCheck = true"); b = pg.query_selector('#ig-prompt').bounding_box(); pg.touchscreen.tap(b['x'] + 40, b['y'] + b['height'] / 2); pg.wait_for_timeout(800)
@step('生视频')
def _(pg): go(pg, 'video')
@step('生视频-切换')
def _(pg): go(pg, 'video'); tap(pg, '#main > .page-head .b5-ctx'); pg.wait_for_timeout(600)
@step('改视频')
def _(pg): go(pg, 'video'); js(pg, "document.querySelector('#main > .page-head .b5-ctx')?.click()"); pg.wait_for_timeout(600); js(pg, "[...document.querySelectorAll('.ph-sheet button, .pop button')].find(b => b.textContent.includes('改视频'))?.click()"); pg.wait_for_timeout(1500)
@step('生视频-详情')
def _(pg): go(pg, 'video'); tap(pg, '#vd-gal > .vd-tile'); pg.wait_for_timeout(1000); js(pg, "document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
@step('素材库')
def _(pg): go(pg, 'mats')
@step('素材库-文件夹')
def _(pg): go(pg, 'mats'); js(pg, "[...document.querySelectorAll('.gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500)
@step('素材库-文件夹里面')
def _(pg): go(pg, 'mats'); js(pg, "[...document.querySelectorAll('.gal-tabs button')].find(b => b.textContent.includes('文件夹'))?.click()"); pg.wait_for_timeout(1500); js(pg, "[...document.querySelectorAll('.gal-body .gal-fd')].find(f => f.textContent.includes('测试文件夹'))?.click()"); pg.wait_for_timeout(2000)
@step('选图')
def _(pg): go(pg, 'img'); tap(pg, '.ig-srct'); pg.wait_for_timeout(1200)
@step('AI助手')
def _(pg): go(pg, 'prompt')
@step('AI助手-抽屉')
def _(pg): go(pg, 'prompt'); tap(pg, '#pg-hist-m'); pg.wait_for_timeout(600)
for p in ['tts', 'vc', 'audioedit', 'batch', 'works', 'voices', 'stt', 'settings']:
    STEPS.append((p, (lambda p: (lambda pg: go(pg, p)))(p)))
@step('作品-滚动')
def _(pg): go(pg, 'works'); js(pg, "scrollTo(0, 600)"); pg.wait_for_timeout(700)
@step('设置-滚动')
def _(pg): go(pg, 'settings'); js(pg, "scrollTo(0, 900)"); pg.wait_for_timeout(700)

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH, dark=not LIGHT)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        js(pg, "S.muted = true")
        for k, (name, f) in enumerate(STEPS):
            if ONLY and not any(o in name for o in ONLY):
                continue
            reset(pg)
            try:
                f(pg)
            except Exception as e:
                print('✗', name, str(e)[:160]); continue
            pg.wait_for_timeout(300)
            fn = os.path.join(OUT, f'{k:02d}_{name}{"_l" if LIGHT else ""}.png'); pg.screenshot(path=fn); print(fn)
        print('页面报错：', errs[:5])
        br.close()
