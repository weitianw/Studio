"""全屏播放页字幕的位置和字号（2026-11-17 用户：播放栏在底部一条时字幕不该伸到播放栏那么低；全屏后字太大）。
假字幕（接口拦截，合成的句子），不截图用户内容。用法：python np_subs_layout.py [shot]"""
import json, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
SH = tempfile.gettempdir()  # 截图放系统临时文件夹
SENTS = [{'s': k * 2.0, 'e': k * 2.0 + 1.8, 'text': f'这是第 {k + 1} 句测试字幕，用来看排版和位置'} for k in range(60)]
def subs(route):
    if route.request.method == 'GET':
        return route.fulfill(status=200, body=json.dumps({'state': 'done', 'sents': SENTS, 'language': 'zh'}, ensure_ascii=False), headers={'content-type': 'application/json'})
    route.continue_()
M = """(() => { const q = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom)]; };
  const cur = document.querySelector('#np-right .sub.on, #np-right .sub.cur, #np-right .sub.active'); const fs = cur ? getComputedStyle(cur).fontSize : getComputedStyle(document.querySelector('#np-right .sub') || document.body).fontSize;
  const vis = [...document.querySelectorAll('#np-right .sub')].filter(e => { const r = e.getBoundingClientRect(); return r.height && r.bottom > 0 && r.top < innerHeight && getComputedStyle(e).opacity > .05; }).map(e => Math.round(e.getBoundingClientRect().bottom));
  return { right: q('#np-right'), lastLineBottom: Math.max(...vis), bar: q('#np .np-ctl'), sub: q('#np-right .subs'), font: fs, cur: cur && q('#np-right .sub.on, #np-right .sub.cur, #np-right .sub.active') }; })()"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    for w, h, dock in ((1280, 720, True), (1920, 1080, True), (2560, 1440, True), (1920, 1080, False), (2560, 1440, False)):
        pg = b.new_page(viewport={'width': w, 'height': h}); pg.route(re.compile(r'.*/api/play/subs\?.*'), subs)
        pg.goto(B + '/'); pg.wait_for_timeout(2200); pg.add_style_tag(content='img,video{visibility:hidden!important}')
        pg.evaluate("document.documentElement.dataset.theme = 'dark'; go('play')"); pg.wait_for_timeout(1500)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("(e => { e.click(); e.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('.pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1200)
        pg.evaluate("qAudio.muted = true; qAudio.pause(); npOpen()"); pg.wait_for_timeout(1500)
        pg.evaluate("(d) => { S.ui = { ...(S.ui || {}), npLook: { ...((S.ui || {}).npLook || {}), bar: d ? 'dock' : 'under' } }; window.NPL?.paint(); npPaint(true); }", dock); pg.wait_for_timeout(600)
        pg.evaluate("NP.tab = 'subs'; NP.key = null; npPaint(true)"); pg.wait_for_timeout(1500)
        print(w, h, 'dock' if dock else 'under', pg.evaluate(M))
        if w == 1920 and dock: print(pg.evaluate("(() => { const out = []; for (let e = document.querySelector('#np-right .subs'); e && e.id !== 'np'; e = e.parentElement) { const r = e.getBoundingClientRect(), c = getComputedStyle(e); out.push([e.id || e.className.toString().slice(0, 30), Math.round(r.top), Math.round(r.bottom), c.display, c.height, c.minHeight, c.flex, c.overflowY]); } return out; })()"))
        if 'shot' in sys.argv: pg.screenshot(path=os.path.join(SH, f'subs_{w}{"d" if dock else "u"}.png'))
        pg.close()
    b.close()
