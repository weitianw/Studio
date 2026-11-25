"""P08 测量：改录音准备阶段（不跑 AuK、不用显卡）。合成一段长录音（mp3），比较
修复前：转 24k 测时长再删 → 再转 24k → 再转 16k（3 次解码）；修复后：audioedit.prep 一次解码出两份。
看耗时、临时写入量、输出时长，以及两种做法的采样是否一致。用法：python -I bench_p08.py [分钟数...]"""
import os, subprocess, sys, tempfile, time, wave
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio'))
import audioedit
FF = audioedit.FFMPEG


def conv(src, dst, sr):
    subprocess.run([FF, '-v', 'error', '-y', '-i', src, '-ac', '1', '-ar', str(sr), dst], check=True, capture_output=True)
    return os.path.getsize(dst)


def frames(p):
    with wave.open(p) as w:
        return w.getnframes(), w.getframerate(), w.readframes(w.getnframes())


for mins in [float(x) for x in sys.argv[1:]] or [1, 10, 30]:
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'src.mp3')
        subprocess.run([FF, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=f=220:sample_rate=44100:duration={mins*60}', '-f', 'lavfi', '-i', f'anoisesrc=d={mins*60}:a=0.05:r=44100',
                        '-filter_complex', 'amix=2', '-ac', '2', '-b:a', '192k', src], check=True, capture_output=True)
        old, new = os.path.join(d, 'old'), os.path.join(d, 'new'); os.mkdir(old); os.mkdir(new)
        best = {}
        for k in range(3):
            t = time.perf_counter(); w = conv(src, os.path.join(old, 'probe.wav'), 24000); audioedit._dur(os.path.join(old, 'probe.wav')); os.remove(os.path.join(old, 'probe.wav'))
            w += conv(src, os.path.join(old, 'input.wav'), 24000) + conv(src, os.path.join(old, 'input16.wav'), 16000); to = time.perf_counter() - t
            t = time.perf_counter(); a, b = audioedit.prep(new, src); audioedit._dur(a); tn = time.perf_counter() - t
            wn = os.path.getsize(a) + os.path.getsize(b)
            best = {'to': min(best.get('to', 1e9), to), 'tn': min(best.get('tn', 1e9), tn), 'wo': w, 'wn': wn}
        same = all(frames(os.path.join(old, f)) == frames(os.path.join(new, f)) for f in ('input.wav', 'input16.wav'))
        n24, sr24, _ = frames(os.path.join(new, 'input.wav')); n16, sr16, _ = frames(os.path.join(new, 'input16.wav'))
        print(f'{mins:>4g} 分钟  修复前 {best["to"]:.2f} s / 写 {best["wo"]/2**20:.1f} MiB / 3 次解码   修复后 {best["tn"]:.2f} s / 写 {best["wn"]/2**20:.1f} MiB / 1 次解码   '
              f'时长 {n24/sr24:.2f}s·{n16/sr16:.2f}s  采样与修复前一致 {same}')
