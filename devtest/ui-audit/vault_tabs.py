"""F20（2026-11-17 审查）：同一浏览器里，私密页 A 开着时打开普通页 B——A 保持有效，B 在普通空间、读不到 A 的内容；
A 主动退出 / 失效时 B 不受影响。测试 Studio 的私密空间密钥是 testky（测试数据）。不截图。用法：python vault_tabs.py"""
import json, os, sys
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


LIST = "(sp) => fetch('/api/video/gallery', { headers: { 'X-Space': sp } }).then(async r => ({ code: r.status, n: r.ok ? (await r.json()).length : -1, ids: r.ok ? (await r.clone().json().catch(() => [])) : [] }))"

if __name__ == '__main__':
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EXE, args=['--mute-audio'])
        ctx = b.new_context(viewport={'width': 1280, 'height': 800})  # 同一个浏览器配置：Cookie 共用
        A = ctx.new_page(); errs = []; A.on('pageerror', lambda e: errs.append('A ' + str(e)))
        A.goto(B + '/'); A.wait_for_timeout(2500)
        normal = A.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'n' } }).then(r => r.json())")
        r = A.evaluate("fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'testky' }) }).then(r => r.status)")
        check('A 用测试密钥进私密空间', r == 200, r)
        A.evaluate("vaultEnter && vaultEnter()"); A.wait_for_timeout(1500)
        check('A 现在在私密空间', A.evaluate("VAULT") is True)
        priv = A.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'v' } }).then(r => r.json())")
        Bp = ctx.new_page(); Bp.on('pageerror', lambda e: errs.append('B ' + str(e)))
        Bp.goto(B + '/'); Bp.wait_for_timeout(3000)
        check('B 打开后在普通空间', Bp.evaluate("VAULT") is False)
        st = A.evaluate("fetch('/api/vault/status').then(r => r.json())")
        a_ok = A.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'v' } }).then(r => r.status)")
        check(f'A 的私密会话没被 B 撤掉（{st}，{a_ok}）', st.get('vault') is True and a_ok == 200)
        bl = Bp.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'n' } }).then(r => r.json())")
        pid = {x.get('id') for x in priv}
        check(f'B 拿到的是普通空间的列表（{len(bl)} 条），没有 A 的私密作品', [x.get('id') for x in bl] == [x.get('id') for x in normal] and not (pid & {x.get('id') for x in bl}))
        Bp.bring_to_front(); Bp.evaluate("dispatchEvent(new Event('focus'))"); Bp.wait_for_timeout(1500)
        check('B 切到前台：不会自动进私密空间', Bp.evaluate("VAULT") is False)
        f = next((x.get('file') for x in bl if x.get('file')), None)
        if f:
            code = Bp.evaluate("(f) => fetch('/media/video/' + encodeURIComponent(f), { headers: { Range: 'bytes=0-15' } }).then(r => r.status)", f)
            check(f'B 里普通作品的媒体照样能读（{code}）', code in (200, 206))
        pf = next((x.get('file') for x in priv if x.get('file')), None)
        if pf and pf not in {x.get('file') for x in bl}:
            code = Bp.evaluate("(f) => fetch('/api/video/gallery', { headers: { 'X-Space': 'n' } }).then(r => r.json()).then(l => l.some(x => x.file === f))", pf)
            check('B 的接口里查不到 A 的私密文件', code is False)
        # A 主动退出：B 不受影响
        A.bring_to_front(); A.evaluate("vaultLock()"); A.wait_for_timeout(1500)
        check('A 退出私密空间', A.evaluate("VAULT") is False)
        r = Bp.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'n' } }).then(r => r.status)")
        check('A 退出后 B 照常（普通空间）', r == 200 and Bp.evaluate("VAULT") is False)
        # 凭证失效：A 再进、然后服务器那边失效（模拟：清掉服务器端的会话），A 的私密请求得到 vault expired，B 照常
        A.evaluate("fetch('/api/vault/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'testky' }) })"); A.evaluate("vaultEnter()"); A.wait_for_timeout(1000)
        Bp.evaluate("fetch('/api/vault/lock', { method: 'POST' })")  # 任何一处主动锁定 = 这个浏览器的私密会话失效
        A.wait_for_timeout(500)
        r = A.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'v' } }).then(async r => [r.status, (await r.json()).error])")
        check(f'凭证失效后 A 的私密请求被拒（{r}）', r[0] == 409 and r[1] == 'vault expired')
        check('B 仍然正常', Bp.evaluate("fetch('/api/video/gallery', { headers: { 'X-Space': 'n' } }).then(r => r.status)") == 200)
        check('没有页面报错', not errs, errs)
        b.close()
    print(f'通过 {ok}，失败 {bad}')
