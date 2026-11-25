"""齿轮菜单里新加的“缩略图 在左边 / 在下面”能不能真的换排法；左上角只剩一个面板图标、点了能收起 / 展开"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8')
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897'); INIT = "window.pywebview = { api: new Proxy({}, { get: () => () => Promise.resolve(null) }) };"
ST = """() => ({ lay: S.galLay, fold: !!S.galFold, headIcons: [...document.querySelectorAll('#main > .page-head .b5-gl > *, #main .gal-ctl > *')].filter(e => e.offsetParent).map(e => e.className.toString()),
  gal: (() => { const g = document.querySelector('#vd-gal'); if (!g || !g.offsetParent) return 'hidden'; const r = g.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; })() })"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio']); ctx = b.new_context(viewport={'width': 1920, 'height': 1080}, color_scheme='dark'); ctx.add_init_script(INIT)
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
    pg.route('**/*', lambda r: r.abort() if not r.request.url.startswith(B) else r.continue_())
    pg.goto(B + '/play'); pg.wait_for_timeout(1200); pg.evaluate("() => { try { appChrome(); } catch (e) {} }")
    pg.evaluate("() => { S.galLay = 'col'; S.galFold = false; vidState().mode = 'edit'; go('video'); }"); pg.wait_for_timeout(1800)
    pg.evaluate("() => new Promise(res => { try { matsVid({ rel: '测试/AI跳舞.mp4', name: 'AI跳舞.mp4' }, (v, done) => { VE_VID = v; if (done) { renderVideo.paintMode?.(); res(); } }); } catch (e) { res(); } setTimeout(res, 4000); })"); pg.wait_for_timeout(1200)
    pg.evaluate("() => { const t = document.querySelector('#vd-gal .vd-tile, #vd-gal .vd-ju'); t && t.click(); }"); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelectorAll('video,audio').forEach(v => { v.muted = true; v.pause(); })")
    print('开始', pg.evaluate(ST))
    pg.click('#side-gear'); pg.wait_for_timeout(500)
    print('齿轮菜单', pg.evaluate("() => { const r = document.querySelector('#gear-lay'); return r ? [r.closest('.gp-row').textContent.trim(), [...r.querySelectorAll('button')].map(b => b.title + (b.classList.contains('on') ? ' (当前)' : ''))] : null; }"))
    pg.click('#gear-lay [data-g="row"]'); pg.wait_for_timeout(1200); print('选“在下面”', pg.evaluate(ST))
    pg.click('#gear-lay [data-g="col"]'); pg.wait_for_timeout(1200); print('选“在左边”', pg.evaluate(ST))
    pg.keyboard.press('Escape'); pg.mouse.click(1000, 500); pg.wait_for_timeout(400)
    fb = pg.query_selector('#main .gal-fb')
    if fb and fb.is_visible():
        fb.click(); pg.wait_for_timeout(800); print('点收起', pg.evaluate(ST))
        pg.query_selector('#main .gal-fb').click(); pg.wait_for_timeout(800); print('再点展开', pg.evaluate(ST))
    else: print('没有看到收起按钮')
    pg.screenshot(path='sheets/lay_end.png')
    print('errs', errs); b.close()
