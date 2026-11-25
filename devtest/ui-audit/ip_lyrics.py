"""全屏播放的字幕（2026-11-16 用户：正在播的那句不要高亮框了——别的句子已经模糊；逐行 / 段落 / 全文放到右上角的“⋯”里）。
模拟 iPhone 16 Pro Max：字幕接口换成测试自己编的几句（测试数据里没有字幕），放一首测试音频（静音）、打开全屏播放的字幕，
三种排版各截一张图（shots_iphone/lyrics），量正在播那句的底色 / 边框，和“⋯”里有没有排版。用法：python ip_lyrics.py"""
import os, sys, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'shots_iphone', 'lyrics'); os.makedirs(OUT, exist_ok=True)
PH = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/'
ok = bad = 0


def check(name, cond, info=''):
    global ok, bad
    if cond:
        ok += 1; print('  ' + name)
    else:
        bad += 1; print('✗ ' + name, info)


LINES = ['这是测试用的第一句字幕', '第二句稍微长一点，看看换行以后是什么样子', '第三句', '停顿之后的第四句', '第五句，正在播的应该是这句',
         '第六句', '第七句也是测试文字', '第八句', '第九句', '最后一句']
SENTS = [{'s': i * 4.0 + (3 if i >= 3 else 0), 'e': i * 4.0 + 3.2 + (3 if i >= 3 else 0), 'text': t} for i, t in enumerate(LINES)]
CUR = r"""() => { const on = document.querySelector('#np-right .sub.on'); if (!on) return null; const c = getComputedStyle(on);
  return { text: on.textContent.trim().slice(0, 12), bg: c.backgroundColor, shadow: c.boxShadow, outline: c.outlineStyle + ' ' + c.outlineWidth, border: c.borderTopWidth + ' ' + c.borderTopStyle,
    tools: (() => { const t = document.querySelector('#np-right .subs-tools [data-mode]'); return t ? getComputedStyle(t).display : 'none'; })(), other: getComputedStyle(document.querySelector('#np-right .sub:not(.on)')).filter }; }"""

if __name__ == '__main__':
    with sync_playwright() as p:
        br, pg = open_iphone(p, PH)
        pg.route('**/api/play/subs?**', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'state': 'done', 'sents': SENTS, 'language': 'zh'}, ensure_ascii=False)))
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.evaluate("S.muted = true; document.addEventListener('play', e => { e.target.muted = true; }, true)")
        pg.evaluate("go('play')"); pg.wait_for_timeout(1600); hide(pg)
        pg.evaluate("[...document.querySelectorAll('#play-src *')].find(x => x.children.length < 4 && /很多文件/.test(x.textContent))?.click()"); pg.wait_for_timeout(1800)
        pg.evaluate("document.querySelector('#play-list .pl-row[data-i] .pl-main')?.click()"); pg.wait_for_timeout(1500)
        pg.evaluate("npOpen()"); pg.wait_for_timeout(1000)
        pg.evaluate("npSetView('subs')"); pg.wait_for_timeout(1500)
        pg.evaluate("(() => { const a = PB.a; a.pause(); Object.defineProperty(a, 'currentTime', { get: () => 20, set: v => { window.__t = v; }, configurable: true }); a.dispatchEvent(new Event('timeupdate')); })()"); pg.wait_for_timeout(800)
        for m in ['line', 'para', 'full']:
            pg.evaluate(f"document.querySelector('#np-right [data-mode] [data-m=\"{m}\"]')?.click()"); pg.wait_for_timeout(700)
            pg.evaluate("PB.a.dispatchEvent(new Event('timeupdate'))"); pg.wait_for_timeout(500)
            r = pg.evaluate(CUR); print('  ', m, json.dumps(r, ensure_ascii=False))
            check(f'{m}：正在播的那句没有底色框 / 边框', r and r['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and r['shadow'] == 'none' and not r['outline'].startswith('solid') and r['border'].startswith('0px'), r)
            check(f'{m}：字幕上面不再有“逐行 / 段落 / 全文”', r and r['tools'] == 'none', r and r['tools'])
            pg.screenshot(path=os.path.join(OUT, f'{m}.png'))
        rg = pg.evaluate("(() => { const b = document.querySelector('#np-right [data-regen]'); const r = b?.getBoundingClientRect(); return b && r.width ? [Math.round(r.width), Math.round(r.height)] : null; })()")
        check('字幕上面有“重新生成”（2026-11-17）、不折行', rg and rg[1] <= 48, rg)
        us = pg.evaluate("(() => { const e = document.querySelector('#np-right .sub'); const c = getComputedStyle(e); return [c.webkitUserSelect || c.userSelect, c.webkitTouchCallout]; })()")
        check('字幕不能选中文字（2026-11-17：粉色光标 / 选中边）', us[0] == 'none', us)
        sub = pg.query_selector('#np-right .sub[data-i="2"]'); r = sub.bounding_box(); pg.touchscreen.tap(r['x'] + 20, r['y'] + r['height'] / 2); pg.wait_for_timeout(600)
        check('点一句字幕还能跳过去', abs((pg.evaluate('window.__t') or 0) - SENTS[2]['s']) < 0.5 or pg.evaluate("document.querySelector('#np-right .sub[data-i=\"2\"]').classList.contains('on')"), pg.evaluate('window.__t'))
        pg.evaluate("document.querySelector('#np-right [data-mode] [data-m=\"line\"]')?.click()"); pg.wait_for_timeout(700)
        L = "(() => { const o = document.querySelector('#np-right .sub:not(.on)'), c = getComputedStyle(o), on = getComputedStyle(document.querySelector('#np-right .sub.on')); return { filter: c.filter, color: c.color, shadow: c.textShadow, onFilter: on.filter, browsing: document.querySelector('#np-right .subs').classList.contains('browsing') }; })()"
        pg.wait_for_timeout(2800); st = pg.evaluate(L); print('  模糊', st)
        check('逐行：句子不用 filter（iPhone 图层边缘的粉色线，2026-11-17）', st['filter'] == 'none' and st['onFilter'] == 'none', st)
        check('逐行：不在播的句子还是模糊的（文字阴影）', 'rgba(0, 0, 0, 0)' in st['color'] and 'px' in st['shadow'], st)
        box = pg.query_selector('#np-right .subs').bounding_box()
        pg.touchscreen.tap(box['x'] + 5, box['y'] + box['height'] / 2)
        pg.evaluate("(() => { const l = document.querySelector('#np-right .subs'); const ev = n => { const e = new Event(n, { bubbles: true }); Object.defineProperty(e, 'touches', { value: [] }); Object.defineProperty(e, 'changedTouches', { value: [] }); return e; }; l.dispatchEvent(ev('touchstart')); l.dispatchEvent(ev('touchmove')); })()"); pg.wait_for_timeout(600)
        st2 = pg.evaluate(L); pg.screenshot(path=os.path.join(OUT, 'browsing.png'))
        check('滑动查看时：全部清楚（不透明的字、没有模糊影子）', st2['browsing'] and 'rgba(0, 0, 0, 0)' not in st2['color'] and st2['shadow'] == 'none', st2)
        pg.wait_for_timeout(2800)
        st3 = pg.evaluate(L)
        check('点一句字幕不算在滑（不会全部变清楚）', not st['browsing'], st)
        check('停手 2.5 秒后：恢复模糊', not st3['browsing'] and 'rgba(0, 0, 0, 0)' in st3['color'], st3)
        b = pg.query_selector('#np-more'); bb = b and b.bounding_box()
        if bb:
            pg.touchscreen.tap(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2); pg.wait_for_timeout(900)
            labs = pg.evaluate("[...document.querySelectorAll('.ph-sheet button, .pop button, .np-more-pop button')].map(b => (b.title || b.textContent).trim()).filter(Boolean)")
            check('右上角“⋯”里有 逐行 / 段落 / 全文', all(x in labs for x in ['逐行', '段落', '全文']), labs)
            pg.screenshot(path=os.path.join(OUT, 'more.png'))
            pg.evaluate("[...document.querySelectorAll('.ph-sheet button, .pop button')].find(b => (b.title || b.textContent).trim() === '段落')?.click()"); pg.wait_for_timeout(800)
            check('在“⋯”里点“段落”：字幕换成段落排版', pg.evaluate("!!document.querySelector('#np-right .subs.para-mode, #np-right .para')"))
        else:
            check('找到右上角的“⋯”', False, pg.evaluate("[...document.querySelectorAll('#np button')].filter(b => b.offsetParent).map(b => b.id || b.className).slice(0, 20)"))
        check('没有页面报错', not errs, errs[:3])
        br.close()
    print(f'{ok}/{ok + bad} 通过')
