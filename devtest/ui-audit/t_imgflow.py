"""生图页的流程回归测试（2026-11-16 起：这几类 bug 以前全面检查没抓到）。python t_imgflow.py
- 模型选择：没放图按底子分组；放了图只列改图模型（qedit / q21-fast / q21）
- 局部重画涂抹后来回切模型（Qwen 2.1 → v23 → Qwen 快速 → 高质量……）：每一步画布都在大画面上、点得到、绑好、涂过的保留、还能接着涂
- 缩放涂抹：大画面滚轮缩放以光标为中心、涂的点落在光标下；空格拖动；点百分比还原；右栏小图普通滚轮不缩放、Ctrl 才缩放
- “已增强过”记号：打字改保留，整段粘贴替换才清
只用自己画的格子图，不截用户的图。失败的项前面打 ✗，最后一行是通过数"""
import os, sys
import base64
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
GRID = os.path.join(HERE, 'aud_grid.png')
# 格子测试图：在浏览器里画（devtest/.venv 里没有 PIL）
GRID_JS = """(() => { const c = document.createElement('canvas'); c.width = 800; c.height = 1200; const g = c.getContext('2d');
  g.fillStyle = '#c8d2dc'; g.fillRect(0, 0, 800, 1200); g.fillStyle = '#5a6478'; for (let i = 0; i < 800; i += 50) g.fillRect(i, 0, 1, 1200); for (let j = 0; j < 1200; j += 50) g.fillRect(0, j, 800, 1);
  return c.toDataURL('image/png').split(',')[1]; })()"""
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


ST = """(() => { const c = document.querySelector('#ig-mask-c'), r = c?.getBoundingClientRect(); const top = r && r.width ? document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) : null;
  let white = 0; if (IMG_MASK) { const d = IMG_MASK.getContext('2d').getImageData(0, 0, IMG_MASK.width, IMG_MASK.height).data; for (let n = 0; n < d.length; n += 28) if (d[n] > 127) white++; }
  return { mode: S.img.mode, canvas: !!c, stage: !!c?.closest('#ig-stage'), hit: top === c, bound: !!c?.onpointerdown, white }; })()"""
DUP = "(() => { const m = {}; document.querySelectorAll('[id]').forEach(e => { m[e.id] = (m[e.id] || 0) + 1; }); return Object.entries(m).filter(([k, n]) => n > 1); })()"
WHITE_C = """(() => { const m = IMG_MASK, d = m.getContext('2d').getImageData(0, 0, m.width, m.height).data; let sx = 0, sy = 0, n = 0;
  for (let y = 0; y < m.height; y += 2) for (let x = 0; x < m.width; x += 2) if (d[(y * m.width + x) * 4] > 127) { sx += x; sy += y; n++; } return n ? [sx / n / m.width, sy / n / m.height] : null; })()"""
PASTE = """(t => { t.focus(); t.select(); t.dispatchEvent(new InputEvent('beforeinput', { inputType: 'insertFromPaste', bubbles: true, cancelable: true }));
  t.value = '完全不同的新话'; t.dispatchEvent(new InputEvent('input', { inputType: 'insertFromPaste', bubbles: true })); })(document.querySelector('#ig-prompt'))"""


def openc(pg):  # 11-19 起默认“输入框版”：输入框收起时看不到模型按钮，先点一下输入框展开
    if not pg.evaluate("!!document.getElementById('ig-model')?.offsetParent"):
        pg.click('#ig-prompt'); pg.wait_for_timeout(600)


def pick(pg, key):
    openc(pg); openc(pg); pg.click('#ig-model', force=True); pg.wait_for_timeout(400); pg.click(f'.igm-v[data-m="{key}"]', force=True); pg.wait_for_timeout(900)


def paint(pg, fx):
    r = pg.query_selector('#ig-mask-c').bounding_box(); x, y = r['x'] + r['width'] * fx, r['y'] + r['height'] * .5
    pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + 8, y + 8, steps=3); pg.mouse.up(); pg.wait_for_timeout(200)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/#img'); pg.wait_for_timeout(2500); open(GRID, 'wb').write(base64.b64decode(pg.evaluate(GRID_JS))); open(os.path.join(HERE, 'aud_halfmask.png'), 'wb').write(base64.b64decode(pg.evaluate("(() => { const c = document.createElement('canvas'); c.width = 200; c.height = 300; const g = c.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, 200, 300); g.fillStyle = '#fff'; g.fillRect(100, 0, 100, 300); return c.toDataURL('image/png').split(',')[1]; })()"))); pg.evaluate("typeof go==='function' && go('img')"); pg.wait_for_timeout(1500)
    openc(pg); openc(pg); pg.click('#ig-model', force=True); pg.wait_for_timeout(400)
    n0 = pg.evaluate("document.querySelectorAll('.igm-b').length"); check('模型选择：没放图时按底子分组', n0 >= 5, n0)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pick(pg, 'q21')
    # 系统指令和模板分开；「文生图 · 助手直接写」点版本就改用，“增强”按钮写出版本（2026-11-16）
    CHIP = "[...document.querySelectorAll('.ig-chips > *')].find(x => (x.dataset.tip || '').includes('增强'))?.textContent.trim()"
    pg.evaluate("document.querySelector('#ig-enh button[data-k=ai]').click()"); pg.wait_for_timeout(300)
    pg.evaluate("(document.querySelector('#ig-prompt')._promptPeek || document.querySelector('.prompt-peek')).click()"); pg.wait_for_timeout(1500)
    check('提示词窗口：有「系统指令」一页', bool(pg.query_selector('.pi-tabs [data-tab=s]')))
    pg.click('.pi-tabs [data-tab=t]'); pg.wait_for_timeout(800)
    check('模板页里没有系统指令', not pg.evaluate("[...document.querySelectorAll('.pt-sg, .pt-si, .pt-g, .pt-k')].some(b => /助手直接写/.test(b.textContent))"))
    pg.click('.pi-tabs [data-tab=s]'); pg.wait_for_timeout(800)
    pg.evaluate("[...document.querySelectorAll('.pt-si, .pt-k')].find(b => b.textContent.includes('助手直接写')).click()"); pg.wait_for_timeout(300)
    check('系统指令：默认是官方写法', pg.evaluate("document.querySelector('.pt-ver .on')?.textContent") == '官方写法' and pg.evaluate(CHIP) == '助手')
    pg.evaluate("[...document.querySelectorAll('.pt-ver button')].find(b => b.textContent === '动作拆开写').click()"); pg.wait_for_timeout(1500)
    check('系统指令：点版本就改用，“增强”按钮写出版本', pg.evaluate(CHIP) == '助手 · 动作拆开写' and pg.evaluate("document.querySelector('.pt-text').value.startsWith('你为文生图模型')"), pg.evaluate(CHIP))
    pg.click('.pi-tabs [data-tab=t]'); pg.wait_for_timeout(600); pg.click('.pi-tabs [data-tab=s]'); pg.wait_for_timeout(600)
    check('系统指令：切回来停在刚才那份', '助手直接写' in (pg.evaluate("document.querySelector('.pt-title')?.textContent") or ''))
    pg.evaluate("[...document.querySelectorAll('.pt-ver button')].find(b => b.textContent === '官方写法').click()"); pg.wait_for_timeout(1500)
    check('系统指令：改回官方写法', pg.evaluate(CHIP) == '助手')
    pg.evaluate("document.querySelector('.prompt-inspector [data-close]').click()"); pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('#ig-enh button[data-k=off]').click()"); pg.wait_for_timeout(300)
    pg.query_selector('input[type=file]').set_input_files(GRID); pg.wait_for_timeout(1500)
    openc(pg); openc(pg); pg.click('#ig-model', force=True); pg.wait_for_timeout(400)
    ks = pg.evaluate("[...document.querySelectorAll('.igm-v')].map(v => v.dataset.m)")
    check('放了图只列改图模型', set(ks) <= {'qedit', 'q21-fast', 'q21'} and 'q21' in ks, ks)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pg.evaluate("document.querySelector('#ig-mode button[data-k=inpaint]').click()")  # 输入框版里模式在标签菜单里（旧的分段按钮藏着，照样能触发）; pg.wait_for_timeout(1200)
    paint(pg, .2); s = pg.evaluate(ST); check('局部重画：画布在大画面、点得到、涂得上', s['stage'] and s['hit'] and s['white'] > 0, s); w = s['white']
    for i, key in enumerate(['qedit', 'q21-fast', 'q21', 'qedit', 'q21']):
        pick(pg, key); s = pg.evaluate(ST)
        dup = pg.evaluate(DUP); check(f'切到 {key}：页面上没有重复的 id（同 id 的旧元素会让代码绑错对象）', not dup, dup)
        if key == 'qedit':
            check('切到 v23：改图模式、没有涂抹画布', s['mode'] == 'edit' and not s['canvas'], s); continue
        check(f'切到 {key}：还是局部重画、画布在大画面且绑好、涂过的还在', s['mode'] == 'inpaint' and s['stage'] and s['hit'] and s['bound'] and s['white'] >= w, s)
        paint(pg, .3 + .1 * i); s2 = pg.evaluate(ST); check(f'  {key} 上接着涂得上', s2['white'] > s['white'], s2); w = s2['white']
    # 缩放
    pg.evaluate("(g => { g.fillStyle = '#000'; g.fillRect(0, 0, IMG_MASK.width, IMG_MASK.height); })(IMG_MASK.getContext('2d'))")
    box = pg.query_selector('#ig-stage .ig-src'); r = box.bounding_box(); cx, cy = r['x'] + r['width'] * .3, r['y'] + r['height'] * .3
    pg.mouse.move(cx, cy)
    for _ in range(6): pg.mouse.wheel(0, -100); pg.wait_for_timeout(50)
    z = pg.evaluate("document.querySelector('.ig-zoom-b')?.innerText"); check('大画面滚轮缩放', bool(z) and z != '100%', z)
    pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(200)
    c = pg.evaluate(WHITE_C); check('缩放后涂的点落在光标下', bool(c) and abs(c[0] - .3) < .02 and abs(c[1] - .3) < .02, c)
    t0 = pg.evaluate("document.querySelector('#ig-mask-c').style.transform")
    pg.keyboard.down('Space'); pg.mouse.down(); pg.mouse.move(cx + 100, cy + 60, steps=4); pg.mouse.up(); pg.keyboard.up('Space')
    check('按住空格拖动画面', pg.evaluate("document.querySelector('#ig-mask-c').style.transform") != t0)
    pg.click('.ig-zoom-b'); pg.wait_for_timeout(200); check('点百分比还原', not pg.query_selector('.ig-zoom-b'))
    # 智能选取（SAM3 接口在测试里换成假的：右半边是“选中的东西”）
    MASK = "data:image/png;base64," + __import__('base64').b64encode(open(os.path.join(HERE, 'aud_halfmask.png'), 'rb').read()).decode()
    calls = []
    def fake_sam(rt):
        import json as _j; body = _j.loads(rt.request.post_data or '{}'); calls.append(body)
        res = ({'ok': True} if body.get('image') else {'need': 'image'}) if body.get('prep') else {'mask': MASK, 'area': 0.5, 'level': 0, 'levels': 2}
        rt.fulfill(status=200, content_type='application/json', body=_j.dumps(res))
    pg.route('**/api/img/sam', fake_sam)
    pg.evaluate("(g => { g.fillStyle = '#000'; g.fillRect(0, 0, IMG_MASK.width, IMG_MASK.height); })(IMG_MASK.getContext('2d'))")
    pg.click('.ig-stage-mbar [data-msmart]'); pg.wait_for_timeout(600)
    check('智能选取：开关亮起', pg.evaluate("document.querySelector('.ig-stage-mbar [data-msmart]').classList.contains('on')"))
    r = pg.query_selector('#ig-mask-c').bounding_box(); pg.mouse.click(r['x'] + r['width'] * .75, r['y'] + r['height'] * .5); pg.wait_for_timeout(700)
    RH = "(() => { const m = IMG_MASK, d = m.getContext('2d').getImageData(0, 0, m.width, m.height).data, W = m.width; let L = 0, R = 0; for (let y = 0; y < m.height; y += 8) for (let x = 0; x < W; x += 8) { if (d[(y * W + x) * 4] > 127) { if (x < W / 2) L++; else R++; } } return [L, R]; })()"
    lr = pg.evaluate(RH)
    preps = [c for c in calls if c.get('prep')]; clicks = [c for c in calls if not c.get('prep')]
    check('智能选取：一打开就先分析这张图（带上原图，只传一次）', len(preps) == 2 and 'image' in preps[1] and not any('image' in c for c in clicks), [{k: v for k, v in c.items() if k != 'image'} for c in calls])
    check('智能选取：点的位置对', len(clicks) == 1 and abs(clicks[0]['x'] - .75) < .02 and clicks[0]['level'] == 0, clicks)
    check('智能选取：选中的一块加进涂抹', lr[0] == 0 and lr[1] > 0, lr)
    pg.keyboard.down('Control'); pg.mouse.click(r['x'] + r['width'] * .75, r['y'] + r['height'] * .5); pg.keyboard.up('Control'); pg.wait_for_timeout(700)
    check('智能选取：按住 Ctrl 点 = 去掉那一块', pg.evaluate(RH)[1] == 0, pg.evaluate(RH))
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(150); check('智能选取：能撤销', pg.evaluate(RH)[1] > 0)
    pg.keyboard.press('w'); pg.wait_for_timeout(150); check('快捷键 W 关掉智能选取', not pg.evaluate("document.querySelector('.ig-stage-mbar [data-msmart]').classList.contains('on')"))
    pg.keyboard.press('e'); pg.wait_for_timeout(100); check('快捷键 E = 擦除', pg.evaluate("document.querySelector('#ig-pen [data-p=erase]').classList.contains('on')"))
    pg.keyboard.press('b'); pg.wait_for_timeout(100); check('快捷键 B = 涂抹', pg.evaluate("document.querySelector('#ig-pen [data-p=draw]').classList.contains('on')"))
    pg.keyboard.press('w'); pg.wait_for_timeout(150)
    pg.click('.ig-stage-mbar [data-msmart]'); pg.wait_for_timeout(150); check('智能选取：再点一下关掉', not pg.evaluate("document.querySelector('.ig-stage-mbar [data-msmart]').classList.contains('on')"))
    # 涂抹撤销 / 重做 / 按住 Ctrl 擦除（2026-11-16）
    WH = "(() => { const d = IMG_MASK.getContext('2d').getImageData(0, 0, IMG_MASK.width, IMG_MASK.height).data; let n = 0; for (let i = 0; i < d.length; i += 28) if (d[i] > 127) n++; return n; })()"
    pg.evaluate("document.activeElement?.blur()")
    w0 = pg.evaluate(WH); paint(pg, .6); w1 = pg.evaluate(WH); paint(pg, .75); w2 = pg.evaluate(WH)
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(150); check('涂抹：Ctrl+Z 撤销一笔', pg.evaluate(WH) == w1, (w0, w1, w2, pg.evaluate(WH)))
    pg.keyboard.press('Control+Shift+z'); pg.wait_for_timeout(150); check('涂抹：Ctrl+Shift+Z 重做', pg.evaluate(WH) == w2)
    pg.click('.ig-stage-mbar [data-a=clear]'); pg.wait_for_timeout(150); pg.keyboard.press('Control+z'); pg.wait_for_timeout(150)
    check('涂抹：清空也能撤销', pg.evaluate(WH) == w2)
    pg.click('.ig-stage-mbar [data-mundo]'); pg.wait_for_timeout(150); check('涂抹：撤销按钮（手机用）', pg.evaluate(WH) == w1)
    r = pg.query_selector('#ig-mask-c').bounding_box(); x, y = r['x'] + r['width'] * .6, r['y'] + r['height'] * .5
    pg.keyboard.down('Control'); pg.wait_for_timeout(80)
    check('按住 Ctrl：画笔显示成擦除', pg.evaluate("document.querySelector('#ig-pen [data-p=erase]').classList.contains('on')"))
    pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + 6, y + 6, steps=2); pg.mouse.up(); pg.keyboard.up('Control'); pg.wait_for_timeout(150)
    check('按住 Ctrl 点 = 擦除', pg.evaluate(WH) < w1, (w1, pg.evaluate(WH)))
    check('松开 Ctrl：回到涂抹', pg.evaluate("document.querySelector('#ig-pen [data-p=draw]').classList.contains('on')"))
    w3 = pg.evaluate(WH); paint(pg, .45); check('松开后再涂是涂抹', pg.evaluate(WH) > w3)
    pg.evaluate("document.querySelector('#ig-stage [data-s=close]')?.click()"); pg.wait_for_timeout(1200)
    bx = pg.query_selector('#ig-src-f #ig-src')
    if bx and bx.bounding_box():  # 11-19 起没有右栏卡片：小图不显示时跳过这一项
        r = bx.bounding_box(); pg.mouse.move(r['x'] + r['width'] / 2, r['y'] + r['height'] / 2)
        pg.mouse.wheel(0, -300); pg.wait_for_timeout(200); check('右栏小图：普通滚轮不缩放', not pg.query_selector('.ig-zoom-b'))
        pg.keyboard.down('Control'); pg.mouse.wheel(0, -300); pg.keyboard.up('Control'); pg.wait_for_timeout(200)
        check('右栏小图：Ctrl + 滚轮缩放', bool(pg.query_selector('.ig-zoom-b')))
    else:  # 11-19 起没有右栏：关掉大图后原图还在（输入框里的原图格子 / IMG_SRC）
        check('关掉大图后原图还在', pg.evaluate("!!IMG_SRC && !!document.querySelector('.b5-refs img, .b5-ref img, #ig-src, .ig-src-th')"))
    # 已增强记号
    ta = '#ig-prompt'; pg.fill(ta, '一位女生在海边'); pg.evaluate("S.img.q21Pre = { enh: 'pe' }")
    pg.click(ta); pg.keyboard.press('End'); pg.keyboard.type('，自己大改了很多字'); check('已增强：打字改保留记号', pg.evaluate('!!S.img.q21Pre'))
    pg.evaluate(PASTE); check('已增强：整段粘贴替换清掉记号', not pg.evaluate('!!S.img.q21Pre'))
    # 增强后 Ctrl+Z 回到原文（增强接口换成假的，不用显卡）
    pg.route('**/api/img/q21-enhance', lambda rt: rt.fulfill(status=200, content_type='application/json', body='{"prompt": "增强后的一大段提示词", "note": ""}'))
    pg.fill(ta, '我自己写的原文'); pg.evaluate("S.img.q21Enh = 'pe'"); pg.evaluate("document.querySelector('#ig-enh-q').hidden = false")
    pg.click('#ig-enh-q', force=True); pg.wait_for_timeout(900)
    check('增强：填回增强后的文字', pg.input_value(ta) == '增强后的一大段提示词', pg.input_value(ta))
    check('增强：出现撤销增强按钮', pg.evaluate("!document.querySelector('#ig-enh-undo').hidden"))
    pg.click(ta); pg.keyboard.press('Control+z'); pg.wait_for_timeout(200)
    check('增强：Ctrl+Z 回到原文、不再算已增强', pg.input_value(ta) == '我自己写的原文' and not pg.evaluate('!!S.img.q21Pre'), pg.input_value(ta))
    pg.keyboard.press('Control+Shift+z'); pg.wait_for_timeout(200)
    check('增强：Ctrl+Shift+Z 回到增强后、又算已增强', pg.input_value(ta) == '增强后的一大段提示词' and pg.evaluate('!!S.img.q21Pre'), pg.input_value(ta))
    pg.click('#ig-enh-undo', force=True); pg.wait_for_timeout(200)
    check('增强：撤销增强按钮（手机用）', pg.input_value(ta) == '我自己写的原文' and pg.evaluate("document.querySelector('#ig-enh-undo').hidden"))
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok} / {ok + bad}')
