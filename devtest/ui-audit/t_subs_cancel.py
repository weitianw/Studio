"""正在生成字幕：进度 + 取消（2026-11-18 用户：要能取消、要有进度、不要说明文字）——界面这一半。
测试数据里的音频识别太快（1 秒内做完），这里拦下 /api/play/subs，模拟“识别中、进度一点点涨”；后台的取消逻辑见 tests/unit/test_play_subs_cancel.py。
用法：python t_subs_cancel.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)


S = {'p': 0.1, 'state': 'running', 'cancel': 0}


def fake(route):
    u = route.request.url
    if 'cancel=1' in u:
        S['state'] = 'none'; S['cancel'] += 1
    elif route.request.method == 'POST' and S['state'] == 'none':
        S['state'] = 'running'; S['p'] = 0.1
    elif S['state'] == 'running':
        S['p'] = min(.9, S['p'] + .1)
    body = {'state': 'running', 'p': S['p']} if S['state'] == 'running' else {'state': 'none'}
    route.fulfill(status=200, content_type='application/json', body=json.dumps(body))


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    pg.route('**/api/play/subs?**', fake)
    pg.evaluate("S.muted = true; go('play')"); pg.wait_for_timeout(1500)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /^很多文件/.test(x.textContent.trim()))?.click()"); pg.wait_for_timeout(1800)
    pg.evaluate("(e => { e?.click(); e?.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelector('#play-list .pl-row[data-i] .pl-main'))"); pg.wait_for_timeout(1500)
    pg.evaluate("PB.a.pause(); npOpen()"); pg.wait_for_timeout(1000); pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(1500)
    G = "(() => { const e = document.querySelector('#np-right .np-genning'); return e && { text: e.innerText, w: e.querySelector('.np-gbar i')?.style.width, cancel: !!e.querySelector('.np-gcancel') }; })()"
    g1 = pg.evaluate(G); pg.wait_for_timeout(2200); g2 = pg.evaluate(G); print('生成中', g1, g2)
    check('正在生成：进度条 + 百分比 + “取消”', g1 and g1['cancel'] and '%' in g1['text'] and g1['w'], g1)
    check('没有说明文字', g1 and '较长' not in g1['text'] and '约需' not in g1['text'] and '对齐' not in g1['text'], g1)
    check('进度会往前走（不重画整块）', g2 and float(g2['w'][:-1]) > float(g1['w'][:-1]), (g1, g2))
    pg.click('#np-right .np-gcancel'); pg.wait_for_timeout(800)
    t = pg.evaluate("document.querySelector('#np-right')?.innerText || ''")
    check(f'点取消：发出取消、回到“转换字幕”（{t[:12]}）', S['cancel'] == 1 and '转换字幕' in t, (S, t))
    check('“转换字幕”下面也没有说明文字', '自动识别' not in t and '点击字幕' not in t, t)
    pg.wait_for_timeout(2200)
    check('取消以后不再去问进度（停在“转换字幕”）', '转换字幕' in pg.evaluate("document.querySelector('#np-right')?.innerText || ''"))
    pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots_np_desk', 'subs_none.png'))
    pg.click('#np-gen'); pg.wait_for_timeout(1200)
    check('再点“转换字幕”：又显示进度', bool(pg.evaluate(G)))
    pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots_np_desk', 'subs_genning.png'))
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
