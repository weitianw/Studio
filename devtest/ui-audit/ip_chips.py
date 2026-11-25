"""生图输入框下面那排按钮（2026-11-16 用户：Qwen 2.1 · 局部重画 · 增强：助手 · 原图尺寸 显示不全，字再精简）。
Qwen 2.1 高质量 + 局部重画 + 助手增强，输入框收起 / 展开，几种窗口宽度：量每个按钮的字有没有被截（…），截图在 shots_chips。
只用自己画的格子图。用法：python ip_chips.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_chips'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
GRID = os.path.join(HERE, 'aud_grid.png')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


M = """(() => [...document.querySelectorAll('.ig-top-f .ig-chips > :not([hidden])')].filter(c => c.offsetParent).map(c => {
  const s = c.querySelector('.igm-main b') || c.querySelector(':scope > span'); const vis = s && getComputedStyle(s).display !== 'none';
  return { t: (s?.textContent || '').trim(), tip: c.dataset.tip || '', cut: !!(vis && s.scrollWidth > s.clientWidth + 1), icon: !vis, w: Math.round(c.getBoundingClientRect().width) }; }))()"""
HIDE = "document.querySelectorAll('.ig-gal img, .ig-gal video, #ig-live img, #ig-live video').forEach(e => e.style.visibility = 'hidden')"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.evaluate("go('img')"); pg.wait_for_selector('#ig-model', state='attached', timeout=60000); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('#ig-prompt').focus()"); pg.wait_for_timeout(600)  # 2026-11-19：没有右栏了，选项在输入框里（先点开输入框）
    pg.click('#ig-model', force=True); pg.wait_for_timeout(400); pg.click('.igm-v[data-m="q21"]', force=True); pg.wait_for_timeout(900)
    pg.query_selector('input[type=file]').set_input_files(GRID); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('#ig-mode button[data-k=\"inpaint\"]').click()"); pg.wait_for_timeout(800)  # 输入框版：这一项收在弹框里，直接点
    pg.query_selector('#ig-ref-file').set_input_files(GRID); pg.wait_for_timeout(1200)  # 放一张参考图：输入框下面那排多一个“提取衣服”（2026-11-17）
    pg.evaluate("S.img.q21Enh = 'ai'; renderImg.chipsRefresh?.(); document.querySelectorAll('#ig-enh-f input[value=ai], #ig-enh-f [data-v=ai], #ig-enh-f [data-k=ai]').forEach(x => x.click())"); pg.wait_for_timeout(600)
    pg.fill('#ig-prompt', '一致。腰部两侧及腹部区域设计有交错的横向与斜向镂空条，所有镂空边缘带有轻微的织物毛边细节。' * 3); pg.wait_for_timeout(300)
    for w, h in [(1280, 800), (1440, 900), (1920, 1080), (2560, 1440), (1024, 768)]:
        pg.set_viewport_size({'width': w, 'height': h}); pg.wait_for_timeout(700)
        for st in ['收起', '展开']:
            if st == '展开': pg.click('#ig-prompt'); pg.wait_for_timeout(900)
            else: pg.mouse.click(5, h // 2); pg.wait_for_timeout(700)
            r = pg.evaluate(M); print(f'  {w}×{h} {st}', json.dumps(r, ensure_ascii=False))
            if st == '收起' and not r: continue  # 输入框收起成一行时这排按钮本来就不显示
            check(f'{w}×{h} {st}：按钮上的字都完整（没有…）', len(r) >= 5 and not any(c['cut'] for c in r), [c['t'] for c in r if c['cut']])
            pg.evaluate(HIDE); pg.screenshot(path=os.path.join(OUT, f'{w}_{st}.png'))
    enh = [c for c in pg.evaluate(M) if '增强' in c['tip']]
    check('增强按钮：字是“助手”，悬停说明写全', enh and enh[0]['t'] == '助手' and enh[0]['tip'] == '提示词增强：助手', enh)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'{ok}/{ok + bad} 通过')
