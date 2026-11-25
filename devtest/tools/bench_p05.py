"""P05（2026-11-17 审查）：音源 / 图片列表请求扫几次全库、接口耗时。合成 400 个文件的临时音源库（不碰真实音源库）。
模拟网页：每 20 秒同时问一次音源列表和图片列表（带上次的指纹）；量全库遍历次数和每次请求的耗时（50 次，P50 / P95）。用法：python -I bench_p05.py"""
import json, os, statistics, sys, tempfile, threading, time
from unittest.mock import patch
STUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio')
sys.path.insert(0, STUDIO)
os.environ['STUDIO_DEFER_DIRS'] = '1'
import server


def call(p, q):
    h = object.__new__(server.Handler)
    h.headers = {}
    out = {}
    h.send_json = lambda d, code=200, **k: out.update(d=d)
    h.play_lib_api('GET', p, q)
    return out['d']


if __name__ == '__main__':
    d = tempfile.mkdtemp(prefix='bench_p05_')
    for k in range(400):
        sub = os.path.join(d, f'专辑{k // 40}', f'碟{k % 3}')
        os.makedirs(sub, exist_ok=True)
        open(os.path.join(sub, f'曲目{k}.mp3' if k % 5 else f'封面{k}.jpg'), 'wb').write(b'x' * 10)
    walks = [0]
    real_walk = os.walk

    def walk(*a, **k):
        walks[0] += 1
        return real_walk(*a, **k)
    with patch.object(server, 'lib_root', lambda: d), patch.object(server.os, 'walk', walk):
        server._lib_cache.clear()
        # ① 网页刷新：同时问两个（fresh=1）
        res = {}
        ts = [threading.Thread(target=lambda p=p: res.update({p[0]: call(p, {'fresh': '1', 'sig': '0'})})) for p in (['library'], ['images'])]
        t0 = time.perf_counter(); [t.start() for t in ts]; [t.join() for t in ts]; first = time.perf_counter() - t0
        n_first = walks[0]
        sig_l, sig_i = res['library']['sig'], res['images']['sig']
        # ② 之后每 20 秒带着指纹来（缓存期内）：50 次
        lat = []
        for _ in range(50):
            t0 = time.perf_counter()
            r1 = call(['library'], {'sig': sig_l}); r2 = call(['images'], {'sig': sig_i})
            lat.append((time.perf_counter() - t0) * 1000)
        lat.sort()
        print(json.dumps({'files': 400, 'walks_on_refresh(2 concurrent fresh)': n_first, 'refresh_ms': round(first * 1000, 1),
                          'same_on_poll': bool(r1.get('same') and r2.get('same')), 'poll_pair_ms_p50': round(statistics.median(lat), 2),
                          'poll_pair_ms_p95': round(lat[int(len(lat) * .95) - 1], 2), 'walks_total': walks[0]}, ensure_ascii=True))
