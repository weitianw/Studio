"""iPhone 模拟（2026-11-16）：Windows 上没有 Xcode 的 iOS Simulator，这里用 Playwright 的 WebKit（Safari 的排版引擎）尽量接近真机：
- 机型尺寸、3 倍像素、触摸、iPhone 的 UA；
- 刘海 / 灵动岛和底部横条的安全区：WebKit 桌面版 env(safe-area-inset-*) 都是 0，把网页里的 env(...) 换成真机的数值；
- 添加到主屏幕后的全屏模式（display-mode: standalone、navigator.standalone）；
- 截图时画上状态栏、灵动岛、底部横条（不挡点击）。
真机才有的回弹、真键盘、手势、Safari 工具栏模拟不了——那些要连真 iPhone（ios-webkit-debug-proxy）。

用法：
  from iphone import open_iphone          # with sync_playwright() as p: pg = open_iphone(p, url)
  python iphone.py [页面 id ...] [--safari] [--model "iPhone 16 Pro"] [--port 7898]   → 截图到 shots_iphone/
截图前藏起图片和视频（测试数据里有不适合截图的内容），音视频静音。"""
import os, re, sys
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))

# 竖屏：CSS 尺寸、安全区（上 / 下），Safari 里（非全屏）可视高度要减掉地址栏和工具栏
MODELS = {
    'iPhone 16 Pro': {'w': 402, 'h': 874, 'top': 62, 'bottom': 34, 'island': (126, 37, 11), 'safari_bars': 83 + 50},
    'iPhone 16 Pro Max': {'w': 440, 'h': 956, 'top': 62, 'bottom': 34, 'island': (126, 37, 11), 'safari_bars': 83 + 50},
    'iPhone 16': {'w': 393, 'h': 852, 'top': 59, 'bottom': 34, 'island': (126, 37, 11), 'safari_bars': 83 + 50},
    'iPhone SE': {'w': 375, 'h': 667, 'top': 20, 'bottom': 0, 'island': None, 'safari_bars': 44 + 44},
}
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
ENV = re.compile(r'env\(\s*safe-area-inset-(top|bottom|left|right)\s*(?:,[^()]*(?:\([^()]*\))?[^()]*)?\)')

SCROLLBAR = '::-webkit-scrollbar{width:0!important;height:0!important;display:none}'  # iPhone 的滚动条是浮在内容上的、平时看不见；WebKit 桌面版会占 10px 宽
HIDE = 'img,video,canvas,picture,[style*="background-image"],.thumb{visibility:hidden!important}'
HIDE_V = 'video{visibility:hidden!important}'  # 图片换成测试图以后只需要藏视频（视频文件也不加载）
# 测试数据里的作品不能出现在截图里（有不适合的内容）：/media/ 下的图片一律换成按网址生成的彩色测试图（SVG），比例在竖 / 方 / 横之间变，
# 视频文件不加载。这样截图里的页面结构和真机一样（缩略图、光晕、比例），但看不到任何作品。素材库里是我们自己生成的渐变图，照常加载
RATIOS = [(720, 1280), (768, 1024), (832, 1216), (1024, 1024), (1024, 768), (1280, 720), (896, 1152), (1216, 832)]
COLS = ['#3b5bdb', '#e8590c', '#2b8a3e', '#c2255c', '#5f3dc4', '#1098ad', '#f08c00', '#495057', '#d6336c', '#0b7285']


def fake_svg(url):
    import hashlib
    h = int(hashlib.md5(url.split('?')[0].encode()).hexdigest(), 16)
    w, hh = RATIOS[h % len(RATIOS)]; c1, c2 = COLS[h % len(COLS)], COLS[(h // 7) % len(COLS)]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{hh}" viewBox="0 0 {w} {hh}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/>'
            f'<circle cx="{w / 2}" cy="{hh * .42}" r="{min(w, hh) * .18}" fill="rgba(255,255,255,.35)"/><rect x="{w * .3}" y="{hh * .62}" width="{w * .4}" height="{hh * .2}" rx="{w * .04}" fill="rgba(255,255,255,.22)"/>'
            f'<rect x="4" y="4" width="{w - 8}" height="{hh - 8}" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="8"/></svg>')


def _init_js(m, standalone):
    isl = m['island']
    return """(() => {
  const SA = %s;
  if (SA) { try { Object.defineProperty(navigator, 'standalone', { get: () => true }); } catch (e) {} }
  const mm = window.matchMedia.bind(window);
  window.matchMedia = q => { const r = mm(q); if (/display-mode:\\s*standalone/.test(q)) return { ...r, matches: SA, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} };
    if (/hover:\\s*hover/.test(q) || /pointer:\\s*fine/.test(q)) return { ...r, matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} };
    if (/hover:\\s*none/.test(q) || /pointer:\\s*coarse/.test(q)) return { ...r, matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} };
    return r; };
  const chrome = () => { if (document.getElementById('__ios')) return; const d = document.createElement('div'); d.id = '__ios';
    d.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;font:600 17px -apple-system,system-ui,sans-serif;color:#fff;mix-blend-mode:difference';
    d.innerHTML = `<div style="position:absolute;top:%dpx;left:0;right:0;height:22px;display:flex;justify-content:space-between;padding:0 34px 0 52px;align-items:center"><span>9:41</span><span style="letter-spacing:2px">▮▮▮ ▰</span></div>`
      + (%s ? `<div style="position:absolute;top:%dpx;left:50%%;width:%dpx;height:%dpx;margin-left:-%dpx;border-radius:%dpx;background:#000;mix-blend-mode:normal"></div>` : '')
      + (%d ? `<div style="position:absolute;bottom:8px;left:50%%;width:134px;height:5px;margin-left:-67px;border-radius:3px;background:#fff"></div>` : '');
    document.documentElement.append(d); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', chrome); else chrome();
  new MutationObserver(() => { if (!document.getElementById('__ios') && document.documentElement) chrome(); }).observe(document, { childList: true, subtree: false });
})();""" % ('true' if standalone else 'false', 18 if m['top'] > 40 else 2, 'true' if isl else 'false', isl[2] if isl else 0, isl[0] if isl else 0, isl[1] if isl else 0, (isl[0] // 2) if isl else 0, (isl[1] // 2) if isl else 0, 1 if m['bottom'] else 0)


def open_iphone(p, url, model='iPhone 16 Pro Max', standalone=True, hide_media=True, dark=True, sfw=True):
    """返回 (browser, page)。standalone=True：主屏幕打开（全屏、安全区）；False：Safari 里（有地址栏，安全区只剩左右）"""
    m = MODELS[model]
    h = m['h'] if standalone else m['h'] - m['safari_bars']
    top, bottom = (m['top'], m['bottom']) if standalone else (0, 0)
    vals = {'top': f'{top}px', 'bottom': f'{bottom}px', 'left': '0px', 'right': '0px'}
    br = p.webkit.launch()
    ctx = br.new_context(viewport={'width': m['w'], 'height': h}, device_scale_factor=3, is_mobile=True, has_touch=True, user_agent=UA,
                         color_scheme='dark' if dark else 'light', locale='zh-CN')
    ctx.add_init_script(_init_js(m, standalone))

    def fix(route):
        r = route.fetch()
        ct = r.headers.get('content-type', '')
        if not any(t in ct for t in ('css', 'javascript', 'html')):
            return route.fulfill(response=r)
        body = r.text()
        body = ENV.sub(lambda x: vals[x.group(1)], body)
        if standalone:
            body = body.replace('(display-mode: standalone)', '(min-width: 0px)')
        else:
            body = body.replace('(display-mode: standalone)', '(max-width: 0px)')
        body = re.sub(r'\(hover:\s*hover\)', '(max-width: 0px)', body)
        body = re.sub(r'\(pointer:\s*fine\)', '(max-width: 0px)', body)
        body = re.sub(r'\(hover:\s*none\)', '(min-width: 0px)', body)
        body = re.sub(r'\(pointer:\s*coarse\)', '(min-width: 0px)', body)
        hd = {k: v for k, v in r.headers.items() if k.lower() not in ('content-length', 'content-encoding', 'etag')}
        route.fulfill(status=r.status, headers=hd, body=body)
    ctx.route(re.compile(r'.*/(static/.*|[^/?]*\.(css|js)(\?.*)?|)(\?.*)?$'), fix)
    if sfw:
        def media(route):  # 所有请求都过这里：图片（程序自带的图标、测试素材库除外）换成测试图，视频不加载，其余交给后面的 fix
            u, rt = route.request.url, route.request.resource_type
            path = u.split('://', 1)[-1].split('/', 1)[-1]
            if path.startswith('static/'):
                return route.fallback()
            if '/media/mats/' in u:
                return route.fallback()  # 测试素材库：只有我们自己生成的渐变图
            if rt == 'media' or re.search(r'\.(mp4|webm|mov|mkv|m4v|mp3|wav|m4a|flac)(\?|$)', u) or 'scrub=' in u:
                return route.abort()
            if rt == 'image' or re.search(r'\.(png|jpe?g|webp|gif|avif|bmp)(\?|$)', u) or 'thumb=' in u:
                return route.fulfill(status=200, content_type='image/svg+xml', body=fake_svg(u), headers={'Cache-Control': 'no-store'})
            return route.fallback()
        ctx.route(re.compile(r'.*'), media)
    pc = os.environ.get('STUDIO_TEST_PORT', '7897')
    if not url.startswith(f'http://127.0.0.1:{pc}'):  # 手机端口：先配对（配对码从电脑端口要，只在测试数据里多一台设备）
        code = p.request.new_context().post(f'http://127.0.0.1:{pc}/api/remote/code').json()['code']
        base = re.match(r'https?://[^/]+', url).group(0)
        r = ctx.request.post(base + '/api/remote/pair', data={'code': code, 'name': '模拟 iPhone'})
        if not r.ok:
            raise RuntimeError('配对失败：' + r.text())
    pg = ctx.new_page()
    pg.goto(url)
    pg.wait_for_timeout(2500)
    pg.add_style_tag(content=SCROLLBAR)
    if hide_media:
        pg.add_style_tag(content=HIDE_V if sfw else HIDE)
        pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")
    return br, pg


def hide(pg, sfw=True):
    pg.add_style_tag(content=HIDE_V if sfw else HIDE)
    pg.evaluate("document.querySelectorAll('video,audio').forEach(m => { m.muted = true; m.pause(); })")


if __name__ == '__main__':
    args = sys.argv[1:]
    safari = '--safari' in args
    model = args[args.index('--model') + 1] if '--model' in args else 'iPhone 16 Pro Max'
    port = args[args.index('--port') + 1] if '--port' in args else os.environ.get('STUDIO_TEST_PHONE_PORT', '7898')
    pages = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] not in ('--model', '--port'))] or ['play', 'img', 'video', 'mats']
    out = os.path.join(HERE, 'shots_iphone'); os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        br, pg = open_iphone(p, f'http://127.0.0.1:{port}/', model, not safari)
        print('hover:none', pg.evaluate("matchMedia('(hover: none)').matches"), 'touch', pg.evaluate("'ontouchstart' in window"), 'standalone', pg.evaluate('navigator.standalone'), 'dpr', pg.evaluate('devicePixelRatio'))
        for pid in pages:
            pg.evaluate(f"typeof go === 'function' ? go({pid!r}) : (location.hash = {pid!r})"); pg.wait_for_timeout(1800); hide(pg)
            f = os.path.join(out, f'{pid}{"_safari" if safari else ""}.png'); pg.screenshot(path=f); print(f)
        br.close()
