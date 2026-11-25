"""2026-11-17 UI 审查（docs/ux/Studio-UI-Experience.md）优先 1–5 的回归。只用合成的 SVG 测试图，不截图。
1 iPhone 看大图停在最后选的那张：横滑、减少动态效果下横滑、连点两次下一张、下一张后马上上一张、下一张后马上关掉再从第 1 张打开、手势被打断
2 手机「更多工具 → 高级参数」不再等 340 毫秒
3 手机 AI 助手：没有模型时输入框下面就说明、发送键变淡；模型好了点发送会再查一次
4 两端看大图：原图慢时先显示缩略图、标题和画面一致；原图打不开时缩略图留着；连跳 1→3→5 只显示最后那张
5 浅色主题输入框提示文字对比度 ≥ 4.5:1（手机 WebKit、电脑 Chromium）
用法：python ui_review_fix.py（测试 Studio 端口看 STUDIO_TEST_PORT，默认 7897）"""
import os, re, sys, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
from iphone import open_iphone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


COLS = ['#3b5bdb', '#e8590c', '#2b8a3e', '#c2255c', '#5f3dc4']


def svg(k, w=1200, h=900):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="{COLS[k % 5]}"/><text x="50%" y="50%" font-size="200" fill="#fff" text-anchor="middle">{k + 1}</text></svg>'


SLOW = {}  # 图号 → 原图延迟毫秒；-1 = 打不开


class _H(__import__('http.server').server.BaseHTTPRequestHandler):  # 单独的小服务器发测试图：慢图在它自己的线程里等，不卡住测试
    def do_GET(self):
        m = re.search(r'/(full|th)(\d+)\.svg', self.path)
        kind, k = m.group(1), int(m.group(2))
        if kind == 'full' and SLOW.get(k) == -1:
            self.send_response(404); self.end_headers(); return
        if kind == 'full' and SLOW.get(k):
            time.sleep(SLOW[k] / 1000)
        b = svg(k, 1200 if kind == 'full' else 200, 900 if kind == 'full' else 150).encode()
        self.send_response(200); self.send_header('content-type', 'image/svg+xml'); self.send_header('cache-control', 'no-store'); self.send_header('content-length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


import threading
from http.server import ThreadingHTTPServer
SRV = ThreadingHTTPServer(('127.0.0.1', 0), _H); threading.Thread(target=SRV.serve_forever, daemon=True).start()
IVB = f'http://127.0.0.1:{SRV.server_port}'


ITEMS = "Array.from({ length: %d }, (_, k) => ({ src: '" + IVB + "/full' + k + '.svg?' + Math.random(), thumb: '" + IVB + "/th' + k + '.svg', name: '测试图 ' + (k + 1) }))"
STATE = "(() => { const st = document.querySelector('.iv-stage'), ph = document.querySelector('.iv-ph'), img = document.querySelector('.iv-img'); return { title: document.querySelector('.iv-title b').textContent, tf: st.style.transform, left: Math.round(st.getBoundingClientRect().left), ph: !ph.hidden, phsrc: (ph.getAttribute('src') || '').replace(/.*\\//, ''), imgsrc: (img.getAttribute('src') || '').replace(/.*\\//, '').replace(/\\?.*/, ''), op: img.style.opacity, vis: img.style.visibility, open: !document.querySelector('.iv').hidden }; })()"
SWIPE = """([x0, x1, end]) => { const st = document.querySelector('.iv-stage'), y = innerHeight / 2;
  const ev = (t, x) => st.dispatchEvent(new PointerEvent(t, { pointerId: 7, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y, button: 0, buttons: t === 'pointerup' ? 0 : 1, bubbles: true }));
  ev('pointerdown', x0); for (let k = 1; k <= 8; k++) ev('pointermove', x0 + (x1 - x0) * k / 8); ev(end || 'pointerup', x1); }"""


def phone_viewer(p):
    print('— 1 iPhone 看大图（WebKit）')
    br, pg = open_iphone(p, B + '/')
    pg.wait_for_timeout(2500)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    op = lambda k=0: (pg.evaluate(f"ImageViewer.open({ITEMS % 4}, {k})"), pg.wait_for_timeout(500))
    for rm in ('no-preference', 'reduce'):
        pg.emulate_media(reduced_motion=rm); op()
        pg.evaluate(SWIPE, [330, 135]); pg.wait_for_timeout(700)
        s = pg.evaluate(STATE)
        check(f'横滑换图（{"减少动态效果" if rm == "reduce" else "普通"}）：到第 2 张、舞台居中（{s["tf"] or "无位移"}，左边 {s["left"]}）', s['title'] == '测试图 2' and s['left'] == 0 and not s['tf'], s)
        pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(300)
    pg.emulate_media(reduced_motion='no-preference')
    op(); pg.evaluate("document.querySelector('.iv-nav.next').click()"); pg.wait_for_timeout(80); pg.evaluate("document.querySelector('.iv-nav.next').click()"); pg.wait_for_timeout(900)
    s = pg.evaluate(STATE); check(f'间隔 80 毫秒按两次下一张：到第 3 张（{s["title"]}）', s['title'] == '测试图 3' and s['left'] == 0, s)
    pg.evaluate("document.querySelector('.iv-nav.next').click()"); pg.wait_for_timeout(40); pg.evaluate("document.querySelector('.iv-nav.prev').click()"); pg.wait_for_timeout(900)
    s = pg.evaluate(STATE); check(f'下一张后马上上一张：回到原图（{s["title"]}）', s['title'] == '测试图 3' and s['left'] == 0, s)
    pg.evaluate("document.querySelector('.iv-nav.next').click()"); pg.wait_for_timeout(30); pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(20); op(0); pg.wait_for_timeout(600)
    s = pg.evaluate(STATE); check(f'下一张后马上关掉、再从第 1 张打开：停在第 1 张（{s["title"]}）', s['title'] == '测试图 1' and s['left'] == 0 and not s['tf'], s)
    pg.evaluate(SWIPE, [330, 100, 'pointercancel']); pg.wait_for_timeout(500)
    s = pg.evaluate(STATE); check(f'横滑到一半被系统打断：不换图、弹回原位（{s["title"]}）', s['title'] == '测试图 1' and s['left'] == 0, s)
    pg.evaluate("ImageViewer.close()")
    check('没有页面报错', not errs, errs)
    br.close()


def thumb_bridge(pg, label):
    print(f'— 4 看大图用缩略图承接（{label}）')
    SLOW.clear(); SLOW.update({2: 650, 4: 650})
    pg.evaluate(f"ImageViewer.open({ITEMS % 5}, 0)"); pg.wait_for_timeout(700)
    pg.evaluate("document.querySelectorAll('.iv-th')[2].click()")
    samples = []
    for _ in range(5):
        pg.wait_for_timeout(110); samples.append(pg.evaluate(STATE))
    pg.wait_for_timeout(700); end = pg.evaluate(STATE)
    check(f'原图慢（650 ms）：等待期间一直显示这张的缩略图、标题一致（{len(samples)} 次采样）', all(s['ph'] and s['phsrc'] == 'th2.svg' and s['title'] == '测试图 3' for s in samples), samples)
    check('原图到了：换上原图、缩略图收起', end['imgsrc'] == 'full2.svg' and not end['ph'] and end['op'] == '', end)
    pg.evaluate("document.querySelectorAll('.iv-th')[2].click(); setTimeout(() => document.querySelectorAll('.iv-th')[4].click(), 60)")
    pg.wait_for_timeout(200); mid = pg.evaluate(STATE); pg.wait_for_timeout(1500); end = pg.evaluate(STATE)
    check(f'连跳 3→5：中途标题和缩略图都是第 5 张，最后是第 5 张原图', mid['title'] == '测试图 5' and mid['phsrc'] == 'th4.svg' and end['imgsrc'] == 'full4.svg' and end['title'] == '测试图 5', (mid, end))
    pg.evaluate("ImageViewer.close()"); pg.wait_for_timeout(300)
    SLOW.clear(); SLOW[2] = -1  # 新开一组（原图地址都是新的、没预载过），从第 1 张直接跳第 3 张
    pg.evaluate(f"ImageViewer.open({ITEMS % 5}, 0)"); pg.wait_for_timeout(700)
    pg.evaluate("document.querySelectorAll('.iv-th')[2].click()"); pg.wait_for_timeout(900)
    s = pg.evaluate(STATE); idx = pg.evaluate("document.querySelector('.iv-idx').textContent")
    check(f'原图打不开：缩略图留着，并写明无法打开（{idx.strip()}）', s['ph'] and s['phsrc'] == 'th2.svg' and s['vis'] == 'hidden' and '无法打开' in idx, s)
    pg.evaluate("ImageViewer.close()"); SLOW.clear()


def contrast(c1, c2):
    def lum(c):
        f = [float(x) for x in re.findall(r'[\d.]+', c)[:3]]
        v = f if 'color(' in c else [x / 255 for x in f]
        v = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in v]
        return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]
    a, b = sorted([lum(c1), lum(c2)], reverse=True)
    return (a + .05) / (b + .05)


def phone_rest(p):
    print('— 2 / 3 / 5 手机（WebKit，浅色）')
    br, pg = open_iphone(p, B + '/', dark=False)
    pg.wait_for_timeout(2500)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    # 5：提示文字颜色（输入栏底色按最暗的情况算：下面滚过纯黑的图）
    pg.evaluate("go('img')"); pg.wait_for_timeout(1500)
    col = pg.evaluate("getComputedStyle(document.querySelector('#ig-prompt'), '::placeholder').color")
    bg = pg.evaluate("getComputedStyle(document.querySelector('#ig-prompt').closest('.ig-composer') || document.querySelector('#ig-prompt')).backgroundColor")
    a = float((re.findall(r'[\d.]+', bg) + ['1', '1', '1', '1'])[3]) if 'rgba' in bg else 1.0
    rgb = [int(x) for x in re.findall(r'\d+', bg)[:3]]
    over_black = 'rgb(%d,%d,%d)' % tuple(round(c * a) for c in rgb)
    over_white = 'rgb(%d,%d,%d)' % tuple(round(c * a + 255 * (1 - a)) for c in rgb)
    cb, cw = contrast(col, over_black), contrast(col, over_white)
    check(f'5 手机浅色提示文字 {col}，输入栏 {bg}：下面是黑图 {cb:.2f}:1、白底 {cw:.2f}:1（≥ 4.5）', cb >= 4.5 and cw >= 4.5, (col, bg))
    # 2：更多工具 → 高级参数
    more = pg.query_selector('.ph-more-b')
    if more:
        more.click(); pg.wait_for_timeout(600)
        t = pg.evaluate("""() => new Promise(res => { const b = [...document.querySelectorAll('.ph-tools button')].find(x => x.textContent.includes('高级参数'));
          if (!b) return res(null); const t0 = performance.now(); const mo = new MutationObserver(() => { if (document.querySelector('.ig-adv-modal')) { mo.disconnect(); res(performance.now() - t0); } });
          mo.observe(document.body, { childList: true, subtree: true }); b.click(); setTimeout(() => res(-1), 1500); })""")
        check(f'2 更多工具 → 高级参数：点下到高级参数出现 {t:.0f} ms（以前 341 ms）' if t is not None else '2 找不到“高级参数”', t is not None and 0 <= t < 60, t)
        pg.wait_for_timeout(500)
        check('2 工具面板已收起、只开了一个高级参数', pg.evaluate("document.querySelectorAll('.ig-adv-modal').length === 1 && !document.querySelector('.ph-tools')"))
        pg.evaluate("document.querySelector('.ig-adv-modal [data-close]')?.click()"); pg.wait_for_timeout(400)
    else:
        check('2 找到“更多工具”按钮', False)
    # 3：AI 助手没有模型
    state = {'avail': False}

    def status(route):
        r = route.fetch(); import json
        d = r.json(); d['available'] = state['avail']; d.setdefault('model', '测试模型')
        route.fulfill(status=200, body=json.dumps(d, ensure_ascii=False), headers={'content-type': 'application/json'})
    pg.route(re.compile(r'.*/api/prompt/status.*'), status)
    pg.route(re.compile(r'.*/api/prompt/(chat|gen|run).*'), lambda r: r.fulfill(status=500, body='{"error":"测试：不真的生成"}', headers={'content-type': 'application/json'}))
    pg.evaluate("go('prompt')"); pg.wait_for_timeout(1500)
    s = pg.evaluate("(() => { const n = document.querySelector('#pg-note'), g = document.querySelector('#pg-go'); return { note: n.textContent, vis: n.getBoundingClientRect().height > 0, role: n.getAttribute('role'), dis: g.getAttribute('aria-disabled'), op: getComputedStyle(g).opacity }; })()")
    check(f'3 没有模型：输入前输入框下面就写“{s["note"]}”、发送键变淡（{s["op"]}）、读屏能读到（role={s["role"]}）', s['note'] == '提示词模型未就绪' and s['vis'] and s['dis'] == 'true' and float(s['op']) < .6 and s['role'] == 'status', s)
    pg.fill('#pg-in', '测试草稿'); pg.click('#pg-go', force=True); pg.wait_for_timeout(800)
    check('3 没有模型时点发送：草稿留着', pg.evaluate("document.querySelector('#pg-in').value") == '测试草稿')
    state['avail'] = True
    pg.click('#pg-go', force=True); pg.wait_for_timeout(1200)
    s = pg.evaluate("(() => ({ note: document.querySelector('#pg-note').textContent, dis: document.querySelector('#pg-go').getAttribute('aria-disabled'), avail: PGST.available }))()")
    check(f'3 模型好了再点发送：再查一次后能发（状态 {s}）', s['avail'] is True and s['dis'] == 'false' and s['note'] != '提示词模型未就绪', s)
    pg.evaluate("(() => { const ta = document.querySelector('#pg-in'); ta.value = ''; ta.dispatchEvent(new Event('input')); })()")
    check('没有页面报错', not errs, errs)
    br.close()


def phone_dark(p):
    print('— 5 手机深色输入栏（WebKit）')
    br, pg = open_iphone(p, B + '/'); pg.wait_for_timeout(2500)
    for page, sel in (('img', '#ig-prompt'), ('video', '#vd-prompt'), ('prompt', '#pg-in')):
        pg.evaluate(f"go('{page}')"); pg.wait_for_timeout(1500)
        d = pg.evaluate("(sel) => { const ta = document.querySelector(sel); let e = ta; while (e && /rgba\(0, 0, 0, 0\)/.test(getComputedStyle(e).backgroundColor)) e = e.parentElement; return [getComputedStyle(ta, '::placeholder').color, getComputedStyle(e).backgroundColor]; }", sel)
        n = [float(x) for x in re.findall(r'[\d.]+', d[1])]; a = n[3] if len(n) > 3 else 1
        cw = contrast(d[0], 'rgb(%d,%d,%d)' % tuple(round(n[i] * a + 255 * (1 - a)) for i in range(3)))
        cb = contrast(d[0], 'rgb(%d,%d,%d)' % tuple(round(n[i] * a) for i in range(3)))
        check(f'5 深色 {page} 提示文字 {d[0]}，输入栏 {d[1]}：下面是白图 {cw:.2f}:1、黑图 {cb:.2f}:1（≥ 4.5）', cw >= 4.5 and cb >= 4.5, d)
    br.close()


with sync_playwright() as p:
    phone_dark(p)
    phone_viewer(p)
    phone_rest(p)
    br, pg = open_iphone(p, B + '/', sfw=False); pg.wait_for_timeout(2500); thumb_bridge(pg, '手机 WebKit'); br.close()  # sfw=False：不把图片换成测试图（这里只开我们自己的合成图，不截图）
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1280, 'height': 720}); pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.add_style_tag(content='img,video{visibility:hidden!important}')
    thumb_bridge(pg, '电脑 Chromium 1280×720')
    print('— 5 电脑（Chromium，浅色）')
    pg.evaluate("document.documentElement.dataset.theme = 'light'; go('img')"); pg.wait_for_timeout(1500)
    col = pg.evaluate("getComputedStyle(document.querySelector('#ig-prompt'), '::placeholder').color")
    bg = pg.evaluate("(() => { let e = document.querySelector('#ig-prompt'); while (e) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\\(0, 0, 0, 0\\)|transparent/.test(c)) return c; e = e.parentElement; } return 'rgb(255, 255, 255)'; })()")
    c = contrast(col, bg if 'rgba' not in bg else 'rgb(255,255,255)')
    check(f'5 电脑浅色提示文字 {col} 对 {bg}：{c:.2f}:1（≥ 4.5）', c >= 4.5, (col, bg))
    b.close()
print(f'通过 {ok}，失败 {bad}')
