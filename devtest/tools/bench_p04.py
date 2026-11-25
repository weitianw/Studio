"""P04（2026-11-17 审查）：探测 / 取帧起几个进程、多久；照原视频调色取到的帧和结果是否和以前一样。
合成测试视频（短 6 秒 / 长 90 秒，临时目录）。修复前的 colorfix 从命令行给路径（git show c400ee5:studio/colorfix.py）。用法：python -I bench_p04.py 旧colorfix.py"""
import importlib.util, json, os, subprocess, sys, tempfile, time
STUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio')
sys.path.insert(0, STUDIO)
import numpy as np
import videogen


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def counted(fn):
    n = [0]; real = subprocess.run

    def run(*a, **k):
        n[0] += 1; return real(*a, **k)
    subprocess.run = run
    try:
        t0 = time.perf_counter(); r = fn(); return r, n[0], round(time.perf_counter() - t0, 2)
    finally:
        subprocess.run = real


def clip(d, name, sec, color):
    p = os.path.join(d, name)
    subprocess.run([videogen.FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=640x360:rate=24:duration={sec}', '-vf', f'colorbalance=rs={color}',
                    '-c:v', 'libx264', '-g', '48', '-pix_fmt', 'yuv420p', p], check=True)
    return p


if __name__ == '__main__':
    old, new = load(sys.argv[1], 'cf_old'), load(os.path.join(STUDIO, 'colorfix.py'), 'cf_new')
    d = tempfile.mkdtemp(prefix='bench_p04_')
    for label, sec in (('短 6 秒', 6), ('长 90 秒', 90)):
        gen, src = clip(d, f'gen{sec}.mp4', sec, 0.3), clip(d, f'src{sec}.mp4', sec, 0.0)
        res = {}
        for tag, m in (('before', old), ('after', new)):
            m.__dict__.get('_dur_cache', {}).clear()
            (fs, n, t) = counted(lambda: (m.frames(videogen.FFMPEG, gen), m.frames(videogen.FFMPEG, src)))
            lut = m.transform('match', [m.rgb2lab(x) for x in fs[1]], [m.rgb2lab(x) for x in fs[0]])
            res[tag] = {'procs': n, 'sec': t, 'frames': [len(fs[0]), len(fs[1])], 'f': fs, 'lut': lut}
        same = all(np.allclose(a, b, atol=1 / 255) for x, y in zip(res['before']['f'], res['after']['f']) for a, b in zip(x, y))
        grid = np.random.default_rng(0).uniform([0, -60, -60], [100, 60, 60], (500, 3))  # 同一批 Lab 颜色，比较两边算出来的调色
        fo, fn_ = res['before']['lut'], res['after']['lut']
        lut_same = bool(np.allclose(fo(grid), fn_(grid), atol=1e-6)) if callable(fo) else bool(np.allclose(np.asarray(fo), np.asarray(fn_), atol=1e-6))
        print(json.dumps({'clip': label, 'color_match_procs': [res['before']['procs'], res['after']['procs']], 'sec': [res['before']['sec'], res['after']['sec']],
                          'frames': res['after']['frames'], 'same_frames': bool(same), 'same_lut': lut_same}, ensure_ascii=True))
        # 探测：批量 / 视频库里同一个文件问 5 次时长
        videogen._probe_cache.clear()
        _, n_exact, t_exact = counted(lambda: [videogen._probe_run(gen, True) for _ in range(5)])  # 以前：每次都逐包数一遍
        _, n_new, t_new = counted(lambda: [videogen._probe(gen, exact=False) for _ in range(5)])
        print(json.dumps({'clip': label, 'probe_5x_procs': [n_exact, n_new], 'sec': [t_exact, t_new],
                          'dur_exact_vs_light': [videogen._probe(gen)['duration'], videogen._probe(gen, exact=False)['duration']]}, ensure_ascii=True))
