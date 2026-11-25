"""电脑播放页（2026-11-17 用户）：
1) 文件很多的文件夹（测试：很多文件（400 个），超过 300 个时列表只画看得见的一段）滚一下滚轮就一路滚到底 / 到顶
2) 点文件夹：展开；再点不收起，只有左边的箭头收起
3) 选中一级文件夹：右边列“子文件夹 + 这一层的文件”，不把子文件夹里的文件摊平
用法：python pl_desk.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
HERE = os.path.dirname(os.path.abspath(__file__))
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(('  ' if cond else '✗ ') + name + (f'  {info}' if info and not cond else ''), flush=True)


def dir_btn(pg, name):
    return pg.evaluate(f"(() => {{ const b = [...document.querySelectorAll('#play-src .ps-dir')].find(x => x.querySelector('.ps-name')?.textContent.trim() === {json.dumps(name)}); if (!b) return null; const r = b.getBoundingClientRect(); return {{ x: r.x + r.width * .6, y: r.y + r.height / 2, open: !!b.querySelector('.ps-tog.open'), on: b.classList.contains('on') }}; }})()")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE, args=['--mute-audio']); pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_timeout(2500)
    pg.evaluate("S.ui = { ...(S.ui || {}), openDirs: [] }; persist()")
    pg.evaluate("go('play')"); pg.wait_for_timeout(1800)
    # 1) 滚一下
    d = dir_btn(pg, '很多文件（400 个）'); pg.mouse.click(d['x'], d['y']); pg.wait_for_timeout(1500)
    r = pg.evaluate("(() => { const e = document.querySelector('#play-list .pl-rows'); const r = e.getBoundingClientRect(); return { virt: e.classList.contains('pl-virt'), x: r.x + r.width / 2, y: r.y + r.height / 2, h: e.scrollHeight, ch: e.clientHeight }; })()")
    print('list', r)
    pg.mouse.move(r['x'], r['y']); pg.mouse.wheel(0, 120); pg.wait_for_timeout(1500)
    y1 = pg.evaluate("document.querySelector('#play-list .pl-rows').scrollTop")
    check('滚轮滚一下（120）：只往下走一点，不一路到底', 0 < y1 < 600, (y1, r['h'] - r['ch']))
    pg.evaluate("(() => { const e = document.querySelector('#play-list .pl-rows'); e.scrollTop = e.scrollHeight; })()"); pg.wait_for_timeout(800)
    yb = pg.evaluate("document.querySelector('#play-list .pl-rows').scrollTop")
    pg.mouse.wheel(0, -120); pg.wait_for_timeout(1500)
    y2 = pg.evaluate("document.querySelector('#play-list .pl-rows').scrollTop")
    check('到底以后往上滚一下：只往上走一点，不一路到顶', 0 < yb - y2 < 600, (yb, y2))
    # 2) 点文件夹：展开，再点不收起；箭头收起
    d = dir_btn(pg, '剧集'); pg.mouse.click(d['x'], d['y']); pg.wait_for_timeout(900)
    d1 = dir_btn(pg, '剧集'); check('点“剧集”：选中并展开', d1 and d1['on'] and d1['open'], d1)
    pg.mouse.click(d1['x'], d1['y']); pg.wait_for_timeout(900)
    d2 = dir_btn(pg, '剧集'); check('再点“剧集”：不收起', d2 and d2['open'], d2)
    pg.evaluate("[...document.querySelectorAll('#play-src .ps-dir')].find(x => x.querySelector('.ps-name')?.textContent.trim() === '剧集')?.querySelector('[data-tog]').click()"); pg.wait_for_timeout(900)
    d3 = dir_btn(pg, '剧集'); check('点左边的箭头：收起', d3 and not d3['open'], d3)
    # 3) 右边：子文件夹 + 这一层的文件
    info = pg.evaluate("(() => ({ dirs: [...document.querySelectorAll('#play-list .pl-dirhit .pl-t')].map(x => x.textContent.trim()), files: document.querySelectorAll('#play-list .pl-row:not(.pl-dirhit)').length, head: document.querySelector('#play-list .pl-head .tiny')?.textContent }))()")
    print('剧集 右边', info)
    check('选中“剧集”：右边列出子文件夹', len(info['dirs']) >= 1, info)
    check('选中“剧集”：不把子文件夹里的视频摊平列出（“剧集”这一层没有直接放的文件）', info['files'] == 0, info)
    pg.evaluate("document.querySelector('#play-list .pl-dirhit')?.click()"); pg.wait_for_timeout(1200)
    info2 = pg.evaluate("(() => ({ title: document.querySelector('#play-list .pl-head .card-title')?.textContent, files: document.querySelectorAll('#play-list .pl-row:not(.pl-dirhit)').length }))()")
    check('点右边的子文件夹：进到那一层、列出里面的文件', info2['files'] > 0 and '第1季' in (info2['title'] or ''), info2)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'{ok}/{ok + bad} 通过')
