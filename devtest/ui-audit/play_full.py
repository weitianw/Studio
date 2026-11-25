"""播放页完整检查（2026-11-18 用户：各个窗口大小都看看）。
每个窗口大小 × 每种状态：横向不溢出、各块不互相压住、关键按钮点得到（elementFromPoint）、文字不被截断到看不见、页面没报错；
截图到 shots_play_full（图片 / 视频 / 背景图都藏起来，只看 SFW 的排版）。用法：python play_full.py [--shots]"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, 'shots_play_full'); os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(os.environ['LOCALAPPDATA'], r'ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe')
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
SHOTS = '--shots' in sys.argv
SIZES = [(800, 600), (1024, 700), (1280, 800), (1366, 768), (1440, 900), (1680, 1050), (1920, 1080), (2560, 1440), (3440, 1440)]
HIDE = 'img,video,canvas{visibility:hidden!important} *,*::before,*::after{background-image:none!important} #mini{display:none!important}'
fails, notes = [], []


def check(name, ok, info=''):
    (notes if ok else fails).append(f'{name} {info}'.strip())


# 页面里跑的检查：返回问题列表
PROBE = r"""(state) => {
  const P = []; const vw = innerWidth, vh = innerHeight;
  const R = e => e.getBoundingClientRect();
  const vis = e => { if (!e || !e.isConnected) return false; const r = R(e), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05; };
  const nm = e => (e.id ? '#' + e.id : '') + '.' + [...e.classList].slice(0, 2).join('.');
  if (document.documentElement.scrollWidth > vw + 1) P.push('横向溢出 ' + document.documentElement.scrollWidth + '>' + vw);
  // 关键控件：在不在屏幕里、点得到吗（顶上没被别的盖住）
  const pb = document.querySelector('.pbar'), pbTop = pb && vis(pb) ? R(pb).top : vh;
  const keys = ['#play-q', '.ps-title', '#pl-kind', '.ps-item.on', '#pl-opts', '#pl-all', '#pl-shuf', '.pl-gtog', '.pl-gplay', '.pl-crumbs .crumb', '.pl-thead'];
  const inScroller = e => { const r = R(e); for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const cs = getComputedStyle(x); if (/(auto|scroll|hidden)/.test(cs.overflowX + cs.overflowY)) { const c = R(x); if (r.top < c.top - 1 || r.bottom > c.bottom + 1 || r.left < c.left - 1 || r.right > c.right + 1) return false; } } return true; };
  for (const s of keys) { const e = document.querySelector('#main ' + s); if (!e || !vis(e) || !inScroller(e)) continue; const r = R(e);
    if (r.right > vw + 1 || r.left < -1) P.push(s + ' 出了屏幕 ' + Math.round(r.left) + '..' + Math.round(r.right));
    const cx = Math.min(vw - 2, Math.max(1, r.left + Math.min(r.width / 2, 12))), cy = r.top + r.height / 2;
    if (cy > 0 && cy < pbTop - 2) { const h = document.elementFromPoint(cx, cy); if (h && h !== e && !e.contains(h) && !h.contains(e)) P.push(s + ' 被 ' + nm(h) + ' 盖住'); } }
  // 标题区：标题和右边按钮不能叠在一起
  const t = document.querySelector('.pl-head .card-title'), acts = [...document.querySelectorAll('.pl-head #pl-opts, .pl-head #pl-all, .pl-head #pl-shuf')].filter(vis);
  if (t && vis(t)) { const tr = R(t); for (const a of acts) { const ar = R(a); if (ar.left < tr.right - 1 && ar.right > tr.left && ar.top < tr.bottom && ar.bottom > tr.top) P.push('标题和 ' + nm(a) + ' 重叠'); } }
  { const all = acts.map(R); for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) { const a = all[i], b = all[j]; if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) P.push('标题区按钮互相重叠'); } }
  // 表头和行：每一列不叠在一起；时长 / 大小在行内、右对齐
  const rows = [...document.querySelectorAll('.pl-rows .pl-row[data-i]')].filter(vis).slice(0, 12);
  for (const r of rows) { const rr = R(r);
    const cols = ['.pl-n', '.art', '.pl-t', '.pl-a', '.pl-s', '.fav-btn', '.pl-d', '.pl-m'].map(s => r.querySelector(s)).filter(e => e && vis(e));
    for (let i = 0; i < cols.length - 1; i++) { const a = R(cols[i]), b = R(cols[i + 1]); if (a.right > b.left + 2 && a.width && b.width && a.top < b.bottom - 2 && b.top < a.bottom - 2) P.push(`行 ${r.dataset.i}：${nm(cols[i])} 压到 ${nm(cols[i + 1])}`); }
    if (rr.right > vw + 1) P.push(`行 ${r.dataset.i} 超出屏幕`);
    const tt = r.querySelector('.pl-tt'); if (tt && vis(tt) && R(tt).width < 24 && tt.textContent.length > 1) P.push(`行 ${r.dataset.i} 标题被挤到 ${Math.round(R(tt).width)}px`); }
  // 表头的列和第一行对得上
  const th = document.querySelector('.pl-thead'); if (th && vis(th) && rows[0]) { for (const [hs, rs] of [['.pl-d', '.pl-d'], ['.pl-m', '.pl-m']]) { const h = th.querySelector(hs), c = rows[0].querySelector(rs); if (h && c && vis(h) && vis(c) && Math.abs(R(h).right - R(c).right) > 3) P.push(`表头 ${hs} 和行没对齐 ${Math.round(R(h).right)} vs ${Math.round(R(c).right)}`); } }
  // 左栏：项不超出栏宽、文字没被挤没
  const side = document.querySelector('.play-side') || document.querySelector('#play-src');
  if (side && vis(side)) { const sr = R(side); for (const it of [...document.querySelectorAll('#play-src .ps-item')].filter(vis).slice(0, 30)) { const r = R(it); if (r.right > sr.right + 1) P.push('左栏项超出 ' + it.textContent.trim().slice(0, 10)); const n = it.querySelector('.ps-name'); if (n && R(n).width < 20) P.push('左栏名字被挤没 ' + it.textContent.trim().slice(0, 10)); }
    if (sr.bottom > pbTop + 2 && getComputedStyle(side).position === 'sticky') P.push('左栏被播放条盖住 ' + Math.round(sr.bottom) + '>' + Math.round(pbTop)); }
  // 左上角起始线：logo、左栏标题同一行（电脑）
  const logo = document.querySelector('.rail .brand'), st = document.querySelector('.ps-title');
  if (logo && st && vis(logo) && vis(st) && vh > 620) { /* 很矮的窗口（≤ 620）故意不对齐（导航栏挨紧排） */ const a = R(logo), b = R(st); if (Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2) > 4) P.push('logo 和“播放”标题不在一行'); }
  // 最后一行能滚到播放条上面
  return P;
}"""


def setup(pg, w, h, theme='dark'):
    pg.goto(B + '/play'); pg.wait_for_timeout(1800)
    pg.add_style_tag(content=HIDE)
    pg.evaluate(f"document.documentElement.dataset.theme = '{theme}'"); pg.wait_for_timeout(200)


def click_src(pg, name):
    loc = pg.locator(f'#play-src .ps-item[data-name="{name}"]')
    if loc.count(): loc.first.click(); pg.wait_for_timeout(500); return True
    return False


def open_dir(pg, parent, child):
    click_src(pg, parent)
    if pg.locator(f'#play-src .ps-item[data-name="{child}"]').count() == 0:
        t = pg.locator(f'#play-src .ps-item[data-name="{parent}"] .ps-tog')
        if t.count(): t.first.click(); pg.wait_for_timeout(300)
    return click_src(pg, child)


STATES = [
    ('空（没选列表）', lambda pg: pg.evaluate("1")),
    ('分组文件夹', lambda pg: click_src(pg, '音乐')),
    ('子文件夹', lambda pg: open_dir(pg, '剧集', '第1季')),
    ('400 个文件', lambda pg: click_src(pg, '很多文件（400 个）')),
    ('作品', lambda pg: pg.click('#play-src .ps-item[data-src="works"]')),
    ('最近播放', lambda pg: pg.click('#play-src .ps-item[data-src="recent"]')),
    ('我的收藏（空）', lambda pg: pg.click('#play-src .ps-item[data-src="favs"]')),
    ('搜索', lambda pg: (pg.fill('#play-q', '第'), pg.wait_for_timeout(700))),
    ('网格显示', lambda pg: (click_src(pg, '音乐'), pg.evaluate("S.ui = { ...(S.ui || {}), views: { ...(S.ui?.views || {}), 'd:音乐': 'grid' } }; renderPlay()"), pg.wait_for_timeout(800))),
    ('正在播放 + 播放条', lambda pg: (click_src(pg, '音乐'), pg.locator('.pl-rows .pl-row[data-i="2"] .pl-tt').dblclick(), pg.wait_for_timeout(800), pg.evaluate("qAudio.muted = true; pbMin(false, false)"), pg.wait_for_timeout(500))),
]


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        for (w, h) in SIZES:
            for theme in (('dark', 'light') if (w, h) in ((1440, 900), (2560, 1440)) else ('dark',)):
                for si, (sname, act) in enumerate(STATES):
                    pg = b.new_page(viewport={'width': w, 'height': h}); errs = []
                    pg.on('pageerror', lambda e: errs.append(str(e)))
                    pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errs.append(m.text))
                    setup(pg, w, h, theme)
                    try:
                        act(pg)
                    except Exception as e:
                        fails.append(f'{w}x{h} {theme} {sname}：操作失败 {str(e)[:120]}'); pg.close(); continue
                    pg.wait_for_timeout(400)
                    probs = pg.evaluate(PROBE, sname)
                    tag = f'{w}x{h} {theme} {sname}'
                    check(tag, not probs and not errs, '；'.join(probs + errs)[:600])
                    if SHOTS and (theme == 'dark' or si in (2, 9)):
                        pg.screenshot(path=os.path.join(OUT, f'{w}x{h}_{theme}_{si}.png'))
                    # 400 个文件：滚到底，最后一行在播放条 / 窗口里能完整看见
                    if sname == '400 个文件':
                        pg.evaluate("window.scrollTo(0, 1e7); document.querySelector('.pl-rows')?.scrollTo?.(0, 1e7)"); pg.wait_for_timeout(500)
                        bot = pg.evaluate("(() => { const r = [...document.querySelectorAll('.pl-rows .pl-row[data-i]')].pop(); if (!r) return null; const b = r.getBoundingClientRect(), pb = document.querySelector('.pbar'); const lim = pb && pb.offsetParent && getComputedStyle(pb).display !== 'none' ? pb.getBoundingClientRect().top : innerHeight; return [r.dataset.i, Math.round(b.bottom), Math.round(lim)]; })()")
                        check(f'{tag} 滚到底最后一行露出来', bot and bot[0] == '399' and bot[1] <= bot[2] + 1, str(bot))
                    pg.close()
        b.close()


def run_phone():
    from iphone import open_iphone
    with sync_playwright() as p:
        for sname, act in [('手机 列表', lambda pg: None), ('手机 分组文件夹', lambda pg: click_src(pg, '音乐')), ('手机 作品', lambda pg: pg.click('#play-src .ps-item[data-src="works"]'))]:
            br, pg = open_iphone(p, B + '/play'); errs = []  # 每种状态开一个新的（手机进了文件夹以后没有返回的历史）
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.wait_for_timeout(2500); pg.add_style_tag(content=HIDE)
            act(pg); pg.wait_for_timeout(800)
            probs = pg.evaluate(PROBE, sname)
            check(sname, not probs and not errs, '；'.join(probs + errs)[:400])
            if SHOTS: pg.screenshot(path=os.path.join(OUT, f'phone_{sname[3:]}.png'))
            br.close()


run()
for n in fails: print('✗', n)
fails_desk = len(fails)
run_phone()
for n in fails[fails_desk:]: print('✗', n)
print(f'通过 {len(notes)}，失败 {len(fails)}')
