"""F12（2026-11-17 审查）：音源同名替换后缓存要刷新；签名和列表一起更新；刷新期间切换空间时不记另一边的签名。
接口回应用测试自己编的（page.route），不碰真实音源库。用法：python lib_watch_cache.py"""
import json, os, sys, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


def item(path, mtime, size=100):
    return {'path': path, 'name': path, 'mtime': mtime, 'size': size, 'dur': 10, 'folder': ''}


if __name__ == '__main__':
    state = {'lib': {'sig': 's1', 'items': [item('a.mp3', 1), item('b.mp3', 1)]}, 'delay': 0}

    def lib(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(state['lib']))

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/'); pg.wait_for_timeout(2500)
        pg.route('**/api/play/library?*', lib)
        pg.route('**/api/play/images?*', lambda r: r.fulfill(status=200, content_type='application/json', body='{"same": true}'))
        pg.evaluate("libCache = [{path: 'a.mp3', name: 'a.mp3', mtime: 1, size: 100, dur: 10, folder: ''}, {path: 'b.mp3', name: 'b.mp3', mtime: 1, size: 100, dur: 10, folder: ''}]; libWatch.ls = 's1'; IMGCACHE = []")
        # ① 同名替换：路径一样，修改时间 1 → 2
        state['lib'] = {'sig': 's2', 'items': [item('a.mp3', 2, 200), item('b.mp3', 1)]}
        r = pg.evaluate("libWatch(true)")
        st = pg.evaluate("({ sig: libWatch.ls, m: libCache.find(x => x.path === 'a.mp3').mtime, n: libCache.length })")
        check(f'同名替换：缓存跟着更新（mtime {st["m"]}，签名 {st["sig"]}）', r is True and st['m'] == 2 and st['sig'] == 's2', st)
        state['lib'] = {'same': True, 'sig': 's2'}
        check('之后服务器回 same：保持新的', pg.evaluate("libWatch(true)") is False and pg.evaluate("libCache.find(x => x.path === 'a.mp3').mtime") == 2)
        # ② 增删
        state['lib'] = {'sig': 's3', 'items': [item('a.mp3', 2, 200), item('c.mp3', 5)]}
        pg.evaluate("libWatch(true)")
        check('增删：b 没了、c 来了', pg.evaluate("libCache.map(x => x.path).join()") == 'a.mp3,c.mp3' and pg.evaluate("libWatch.ls") == 's3')
        # ③ 刷新期间切换空间：结果和签名都不用
        state['lib'] = {'sig': 'OTHER', 'items': [item('x.mp3', 9)]}
        # 回应晚 1 秒到（在网页里包一层 api 延迟），这期间切换空间（VGEN 变了）
        pg.evaluate("window.__api = api; api = (...a) => window.__api(...a).then(r => new Promise(ok => setTimeout(() => ok(r), 1000))); window.__p = libWatch(true); setTimeout(() => { VGEN++; }, 200)")
        r = pg.evaluate("window.__p.then(v => { api = window.__api; return v; })")
        st = pg.evaluate("({ sig: libWatch.ls, paths: libCache.map(x => x.path).join() })")
        check(f'刷新期间切换空间：不记另一边的签名和列表（{st}）', r is None and st['sig'] == 's3' and st['paths'] == 'a.mp3,c.mp3', st)
        check('没有页面报错', not errs, errs)
        b.close()
    print(f'通过 {ok}，失败 {bad}')
