"""载入字幕 / 歌词文件（2026-11-17）：字幕区右键 → 载入；⋯ 菜单里也有；拖到字幕区也行；换掉已有字幕前先确认。
用合成的 LRC 文件；结束时删掉这次写进测试数据的字幕缓存。不截图。用法：python np_subs_import.py"""
import glob, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0
def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)
ST = os.environ.get('STUDIO_TEST_STATE') or os.path.join(os.path.dirname(__file__), '..', 'states', 'gpu')
t0 = time.time()
d = tempfile.mkdtemp(); f1 = os.path.join(d, '测试歌词.lrc'); f2 = os.path.join(d, '第二份.srt')
open(f1, 'w', encoding='gb18030').write('[ti:测试]\n' + ''.join(f'[00:{k:02d}.00]载入的第 {k + 1} 句歌词\n' for k in range(12)))
open(f2, 'w', encoding='utf-8').write('1\n00:00:00,500 --> 00:00:02,000\n换上的第二份字幕\n')
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.evaluate("document.documentElement.dataset.theme = 'dark'; go('play')"); pg.wait_for_timeout(1500)
    pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1500)
    pg.evaluate("(e => { e.click(); e.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); })(document.querySelectorAll('.pl-row[data-i] .pl-main')[7])"); pg.wait_for_timeout(1200); pg.evaluate("qAudio.muted = true; qAudio.pause(); npOpen()"); pg.wait_for_timeout(1500)
    pg.evaluate("NP.tab = 'subs'; NP.key = null; npPaint(true)"); pg.wait_for_timeout(1500)
    pg.click('#np-right', button='right', position={'x': 200, 'y': 200}); pg.wait_for_timeout(300)
    items = pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].map(e => e.textContent.trim())")
    check(f'字幕区右键：菜单里有“载入字幕 / 歌词文件…”（{items}）', any('载入字幕' in x for x in items))
    with pg.expect_file_chooser() as fc:
        pg.evaluate("[...document.querySelectorAll('.ctx-menu .ctx-i')].find(e => /载入字幕/.test(e.textContent)).click()")
    fc.value.set_files(f1); pg.wait_for_timeout(800)
    pg.evaluate("[...document.querySelectorAll('.modal-bg button')].find(b => /载入/.test(b.textContent))?.click()"); pg.wait_for_timeout(1000)
    n = pg.evaluate("document.querySelectorAll('#np-right .sub').length"); txt = pg.evaluate("document.querySelector('#np-right .sub')?.textContent || ''")
    check(f'载入 GBK 编码的 LRC：显示 {n} 句（{txt[:12]}）', n == 12 and '载入的第 1 句' in txt)
    pg.click('#np-more2'); pg.wait_for_timeout(400)  # 11-18：右上角的 ⋯ → “字幕”二级菜单
    top = pg.evaluate("[...document.querySelectorAll('.ctx-menu:not(.ctx-subm) .ctx-i')].map(e => e.textContent.trim())")
    check(f'右上角 ⋯：字幕的操作收成一项“字幕”（{top}）', '字幕' in top and not any('载入字幕' in x or '逐行' in x for x in top))
    pg.hover("xpath=//div[contains(@class,'ctx-menu') and not(contains(@class,'ctx-subm'))]//div[contains(@class,'ctx-i')][normalize-space(.)='字幕']"); pg.wait_for_timeout(300)
    sub = pg.evaluate("[...document.querySelectorAll('.ctx-subm .ctx-i')].map(e => e.textContent.trim())")
    check(f'移到“字幕”上：旁边展开二级菜单（{sub}）', any('载入字幕' in x for x in sub) and any('重新生成' in x for x in sub) and any('提前' in x for x in sub))
    sr = pg.evaluate("(() => { const a = document.querySelector('.ctx-menu:not(.ctx-subm)').getBoundingClientRect(), b = document.querySelector('.ctx-subm').getBoundingClientRect(); return [a.left, a.right, b.left, b.right, innerWidth]; })()")
    check(f'二级菜单在一级菜单旁边、不出屏幕（{sr}）', (abs(sr[2] - sr[1]) < 8 or abs(sr[3] - sr[0]) < 8) and sr[2] >= 0 and sr[3] <= sr[4])
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # 拖放第二份：已有字幕 → 先确认
    pg.evaluate("""async (txt) => { const f = new File([txt], '第二份.srt'); const dt = new DataTransfer(); dt.items.add(f); const r = document.querySelector('#np-right');
      r.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true })); r.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""", open(f2, encoding='utf-8').read())
    pg.wait_for_timeout(500)
    asked = pg.evaluate("!!document.querySelector('.modal-bg')")
    check('拖入第二份字幕：先问要不要替换', asked)
    pg.evaluate("[...document.querySelectorAll('.modal-bg button')].find(b => /载入/.test(b.textContent))?.click()"); pg.wait_for_timeout(1500)
    txt = pg.evaluate("[...document.querySelectorAll('#np-right .sub')].map(e => e.textContent).join('|')")
    check(f'确认后换成第二份（{txt[:20]}）', '换上的第二份字幕' in txt and '载入的第' not in txt)
    pg.evaluate("""async () => { const f = new File(['没有时间的普通文字'], 'x.txt'); const dt = new DataTransfer(); dt.items.add(f); const r = document.querySelector('#np-right'); r.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""")
    pg.wait_for_timeout(500); pg.evaluate("[...document.querySelectorAll('.modal-bg button')].find(b => /载入/.test(b.textContent))?.click()"); pg.wait_for_timeout(1200)
    toast = pg.evaluate("[...document.querySelectorAll('.toast')].map(t => t.textContent).join('|')")
    check(f'没有时间的文件：提示载入失败、原字幕不动（{toast[:40]}）', '载入失败' in toast and pg.evaluate("document.querySelector('#np-right .sub')?.textContent || ''").count('换上的第二份') == 1)
    check('没有页面报错', not errs, errs)
    b.close()
# 收拾：删掉这次写进测试数据的字幕缓存
gone = 0
for fp in glob.glob(os.path.join(ST, '**', 'play-cache', 'subs', '*.json'), recursive=True):
    if os.path.getmtime(fp) >= t0 - 1:
        try:
            if '"source": "import"' in open(fp, encoding='utf-8').read() or '"source":"import"' in open(fp, encoding='utf-8').read():
                os.remove(fp); gone += 1
        except OSError:
            pass
print(f'（删掉测试写入的字幕缓存 {gone} 个）')
print(f'通过 {ok}，失败 {bad}')
