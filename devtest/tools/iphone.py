"""在电脑上看“Studio 装在 iPhone 主屏幕上”大概是什么样（轻量：只用 devtest/.venv 里现成的 Playwright）。

模拟的东西：
- iPhone 17 Pro 的屏幕大小（402×874，3 倍）、触屏、iPhone 的 UA、深色；
- 安全区：顶部 62px（灵动岛那一排）、底部 34px（横条），用 Chromium 的 Emulation.setSafeAreaInsetsOverride；
- 主屏幕 App（standalone）：Chromium 模拟不了 display-mode，就把 b5.css 里写给 standalone 的规则原样加进页面；navigator.standalone = true；
- 画在最上层、不挡点击的：状态栏（时间、电量）、灵动岛、状态栏下面系统那条模糊（iOS 26.1+ 用 black-translucent 时会有）、底部横条。
模拟不了的：iOS 真正的取色 / 模糊算法、WebKit 301108 那种“视口短一截”的 bug——这些还是要真机看。

用法（在 D:\\AI-TTS\\devtest 里）：
  .venv\\Scripts\\python.exe -I tools\\iphone.py                 打开一个窗口（默认 /play，测试 Studio 7899），关掉窗口就结束
  .venv\\Scripts\\python.exe -I tools\\iphone.py /tts            打开别的页面
  .venv\\Scripts\\python.exe -I tools\\iphone.py /play --shot out.png [--np cover|subs|queue]   不开窗口，截一张图（--np 先放一首再打开全屏播放）
  --port 7860  看别的 Studio（只是打开网页，不会启动 / 重启它）；--light 浅色
截图前会把图片和视频藏起来（测试数据里有不适合截图的内容），声音静音。
"""
import argparse, os, sys
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('path', nargs='?', default='/play')
ap.add_argument('--port', type=int, default=int(os.environ.get('STUDIO_TEST_PORT', 7899)))
ap.add_argument('--shot'); ap.add_argument('--np', choices=['cover', 'subs', 'queue'])
ap.add_argument('--light', action='store_true'); ap.add_argument('--show-media', action='store_true', help='窗口模式下也显示图片 / 视频')
a = ap.parse_args()
if ':' in a.path or '\\' in a.path: a.path = '/' + a.path.replace('\\', '/').rstrip('/').split('/')[-1]  # Git Bash 会把 /play 变成 D:/App/Git/play
if not a.path.startswith('/'): a.path = '/' + a.path

W, H, TOP, BOT = 402, 874, 62, 34
PW = os.path.join(os.environ['LOCALAPPDATA'], 'ms-playwright')
EXE = os.path.join(PW, r'chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe') if a.shot else os.path.join(PW, r'chromium-1217\chrome-win64\chrome.exe')
IPH = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'

# 页面一加载就做：标记成主屏幕 App、套上 b5.css 里 standalone 的规则、画状态栏那一层
INIT = r"""(() => {
  try { Object.defineProperty(navigator, 'standalone', { get: () => true }); } catch (e) { }
  const TOP = __TOP__, BOT = __BOT__, HIDE = __HIDE__;
  const force = () => {
    if (document.getElementById('ip-force')) return true;
    const out = []; let ready = false;
    for (const sh of document.styleSheets) {
      if (!(sh.href || '').includes('b5.css')) continue;
      let rs; try { rs = sh.cssRules; } catch (e) { continue; } ready = true;
      for (const r of rs) if (r instanceof CSSMediaRule && r.conditionText.includes('display-mode: standalone')) {
        const rest = r.conditionText.replace(/\(display-mode: standalone\)\s*(and)?\s*/, '').trim();
        const body = [...r.cssRules].map(x => x.cssText).join(' ');
        out.push(rest ? `@media ${rest} { ${body} }` : body);
      }
    }
    if (!ready) return false;
    const st = document.createElement('style'); st.id = 'ip-force';
    st.textContent = out.join('\n') + (HIDE ? ' img,video,.img-tile,.pc-art,.ig-tile{visibility:hidden!important}' : '');
    document.head.append(st); return true;
  };
  const chrome = () => {
    if (document.getElementById('ip-chrome')) return;
    const d = document.createElement('div'); d.id = 'ip-chrome';
    const t = new Date(), hm = t.getHours() + ':' + String(t.getMinutes()).padStart(2, '0');
    d.innerHTML = `<div class="ip-blur"></div><div class="ip-bar"><b>${hm}</b><i></i><span><em></em>78</span></div><div class="ip-home"></div>`;
    const css = document.createElement('style');
    css.textContent = `#ip-chrome { position: fixed; inset: 0; z-index: 2147483647; pointer-events: none; font: 600 17px -apple-system, "SF Pro Text", "Segoe UI", sans-serif; }
      #ip-chrome .ip-blur { position: absolute; left: 0; right: 0; top: 0; height: ${TOP + 26}px; -webkit-backdrop-filter: blur(5px); backdrop-filter: blur(5px);
        -webkit-mask: linear-gradient(#000 ${TOP - 6}px, transparent ${TOP + 26}px); mask: linear-gradient(#000 ${TOP - 6}px, transparent ${TOP + 26}px); }
      #ip-chrome .ip-bar { position: absolute; left: 0; right: 0; top: 0; height: ${TOP}px; display: flex; align-items: center; justify-content: space-between; padding: 6px 34px 0 46px; color: #fff; mix-blend-mode: difference; }
      #ip-chrome .ip-bar i { position: absolute; left: 50%; top: 11px; width: 126px; height: 37px; margin-left: -63px; border-radius: 20px; background: #000; mix-blend-mode: normal; }
      #ip-chrome .ip-bar span { font-size: 13px; display: flex; align-items: center; gap: 4px; }
      #ip-chrome .ip-bar span em { width: 25px; height: 12px; border-radius: 4px; background: #fff; display: inline-block; }
      #ip-chrome .ip-home { position: absolute; left: 50%; bottom: 8px; width: 140px; height: 5px; margin-left: -70px; border-radius: 3px; background: #fff; opacity: .55; mix-blend-mode: difference; }`;
    document.documentElement.append(css, d);
  };
  const tick = () => { const ok = document.head && force(); if (document.body) chrome(); if (!ok || !document.body) requestAnimationFrame(tick); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tick); else tick();
  addEventListener('load', tick);
})()""".replace('__TOP__', str(TOP)).replace('__BOT__', str(BOT)).replace('__HIDE__', 'true' if (a.shot or not a.show_media) else 'false')

with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, headless=bool(a.shot), args=['--mute-audio', f'--window-size={W + 16},{H + 90}'])
    ctx = br.new_context(viewport={'width': W, 'height': H}, device_scale_factor=3 if a.shot else 1, is_mobile=True, has_touch=True,
                         color_scheme='light' if a.light else 'dark', user_agent=IPH)
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); cdp = ctx.new_cdp_session(pg)
    cdp.send('Emulation.setSafeAreaInsetsOverride', {'insets': {'top': TOP, 'bottom': BOT, 'left': 0, 'right': 0}})
    pg.goto(f'http://127.0.0.1:{a.port}{a.path}'); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelectorAll('audio,video').forEach(e => { e.muted = true; })")
    if a.np:  # 先放一首（第一个有文件的文件夹里的第一个），再打开全屏播放
        pg.evaluate("""() => { const d = [...document.querySelectorAll('#play-src .ps-dir')].find(b => +(b.querySelector('.ps-n')?.textContent || 0) > 0); if (d) d.click(); }""")
        pg.wait_for_timeout(700)
        pg.evaluate("() => document.querySelector('#play-list .pl-row:not(.pl-dirhit)')?.click()"); pg.wait_for_timeout(900)
        pg.evaluate(f"() => {{ NP.mv = '{a.np}'; npOpen(); npViewPaint(); npPaint(true); document.querySelectorAll('audio,video').forEach(e => {{ e.muted = true; }}); }}"); pg.wait_for_timeout(800)
    if a.shot:
        pg.screenshot(path=a.shot); print('saved', a.shot)
    else:
        print('窗口已打开；关掉窗口结束'); pg.wait_for_event('close', timeout=0)
    br.close()
