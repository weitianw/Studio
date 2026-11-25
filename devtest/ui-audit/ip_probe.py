"""在模拟 iPhone 上执行一段 JS（调试用）：python ip_probe.py 页面id "JS 表达式" [截图名]"""
import json, os, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone import open_iphone, hide
pid, js = sys.argv[1], sys.argv[2]
shot = sys.argv[3] if len(sys.argv) > 3 else ''
with sync_playwright() as p:
    br, pg = open_iphone(p, 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PHONE_PORT', '7898') + '/')
    pg.evaluate(f"typeof go === 'function' ? go({pid!r}) : 0"); pg.wait_for_timeout(1800); hide(pg)
    print(json.dumps(pg.evaluate(js), ensure_ascii=False, indent=1))
    if shot:
        pg.wait_for_timeout(500); pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots_iphone', shot + '.png'))
    br.close()
