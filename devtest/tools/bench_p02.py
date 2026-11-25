"""P02（2026-11-17 审查）：同一个无缓存的视频，找换装点走显卡 vs 走 CPU 的耗时（合成测试视频，临时缓存目录）。
cutpoints 自己会先看显卡忙不忙（gpu_free），忙就退回 CPU。用法：python -I bench_p02.py"""
import json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio'))
import cutpoints, videogen

if __name__ == '__main__':
    d = tempfile.mkdtemp(prefix="bench_p02_")  # GPU 助手的日志可能还被占着：不在结束时强删
    if True:
        v = os.path.join(d, 'clip.mp4')
        subprocess.run([videogen.FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=30:duration=20', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=20',
                        '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', v], check=True)
        for name, idle in (('批量 runner 推进时（修复后：显卡空就用）', lambda: True), ('修复前：runner 自己算成忙 → CPU', lambda: False)):
            cd = tempfile.mkdtemp(dir=d)
            cutpoints._cache.clear()
            t0 = time.time()
            r = cutpoints.analyze(v, videogen.FFMPEG, videogen._probe, cd, True, idle)
            print(json.dumps({'case': name, 'dev': r.get('dev'), 'cpu_why': r.get('cpu_why'), 'by': r.get('by'), 'took': r.get('took'), 'wall': round(time.time() - t0, 1)}, ensure_ascii=False), flush=True)
