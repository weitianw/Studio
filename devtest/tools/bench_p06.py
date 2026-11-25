"""P06 测量：连续排 N 个带大输入的任务再全部取消（不起 worker、不用显卡），看还占着多少内存。
用法：python -I bench_p06.py <studio 目录>   （对比修复前后：传旧版代码的导出目录）"""
import gc, os, sys, time, tracemalloc
sys.path.insert(0, os.path.abspath(sys.argv[1]))
import videogen, imagegen

MB = 1 << 20


def run(n, size):
    videogen.jobs.clear(); videogen._q.clear(); imagegen.jobs.clear(); imagegen.queue.clear()
    gc.collect(); tracemalloc.start(); base = tracemalloc.get_traced_memory()[0]
    for i in range(n):
        vid, img = os.urandom(size), os.urandom(size // 8)
        j = {'id': f'v{i}', 'space': 'n', 'state': 'queued', 'model': 'm', '_vid': vid, '_img': img, '_redo': ({}, vid, img)}
        videogen.jobs[j['id']] = j; videogen._q.append(j)
        g = {'id': f'g{i}', 'space': 'n', 'state': 'queued', 'done': 0, '_init': os.urandom(size // 4), '_mask': os.urandom(size // 16)}
        imagegen.jobs[g['id']] = g; imagegen.queue.append(g['id'])
    peak = tracemalloc.get_traced_memory()[0] - base
    t = time.perf_counter()
    for i in range(n):
        videogen.cancel(f'v{i}', 'n'); imagegen.cancel(f'g{i}', 'n')
    dt = time.perf_counter() - t
    gc.collect(); left = tracemalloc.get_traced_memory()[0] - base; tracemalloc.stop()
    held = sum(1 for j in list(videogen.jobs.values()) + list(imagegen.jobs.values()) if any(k in j for k in ('_vid', '_img', '_redo', '_init', '_mask')))
    return peak / MB, left / MB, held, len(videogen._q), dt


for n in (4, 16, 30):
    p, l, h, q, dt = run(n, 8 * MB)
    print(f'N={n:2d} 排队后 {p:7.1f} MiB  全部取消后仍占 {l:7.1f} MiB  仍带大输入的任务 {h:2d}  视频队列残留 {q:2d}  取消耗时 {dt*1000:.2f} ms')
