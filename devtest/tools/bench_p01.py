"""P01（2026-11-17 审查）：批量每段提交改视频时，原视频在内存里有几份。合成 32 MiB 素材（临时文件），模拟视频队列（只留住提交的数据，不跑引擎）。
量：Python 分配峰值（tracemalloc）、留在队列里的数据、从硬盘读的字节数、入队耗时。用法：python -I bench_p01.py"""
import json, os, sys, tempfile, time, tracemalloc, builtins
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio'))
os.environ['STUDIO_DEFER_DIRS'] = '1'
import server
from unittest.mock import patch

MB = 1 << 20


def run(nseg, path, rel):
    held, reads = [], [0]
    real_open = builtins.open

    class Counted:
        def __init__(self, f):
            self.f = f

        def read(self, *a):
            d = self.f.read(*a); reads[0] += len(d); return d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

        def __getattr__(self, k):
            return getattr(self.f, k)

    def op(p, mode='r', *a, **k):
        f = real_open(p, mode, *a, **k)
        return Counted(f) if os.path.normcase(str(p)) == os.path.normcase(path) and 'b' in mode else f

    def submit(b, img, ff, end, vid):  # 模拟视频队列：任务留住原视频（和 videogen.submit 一样：_vid + _redo）
        held.append((b, vid, (b, vid, img)))
        return {'id': str(len(held))}
    with patch.object(server, 'mats_path', lambda r: path), patch.object(server.videogen, 'submit', submit), patch('builtins.open', op):
        tracemalloc.start(); t0 = time.perf_counter()
        for k in range(nseg):
            server.video_edit_submit({'video': {'mats': rel}, 'edit': {'task': 'outfit', 'start': k, 'end': k + 1}}, 'n')
        dt = time.perf_counter() - t0
        cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    distinct = len({id(v) for _, v, _ in held})
    return {'segs': nseg, 'peak_MiB': round(peak / MB, 1), 'held_MiB': round(cur / MB, 1), 'copies': distinct, 'read_MiB': round(reads[0] / MB, 1), 'submit_s': round(dt, 3)}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'src.mp4')
        with open(p, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypmp42' + os.urandom(32 * MB - 16))
        for n in (1, 4, 16):
            server.__dict__.get('_SRC_SNAP', {}).clear()
            print(json.dumps(run(n, p, 'src.mp4'), ensure_ascii=False), flush=True)
