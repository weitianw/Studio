"""找换装点：在显卡上算人体关键点的小助手进程（2026-11-05）。用 ComfyUI 自带的 Python 跑（有显卡版 torch），由 cutpoints.py 启动。
做法和 cutpoints.track（CPU）完全一样：每 12 帧（半秒）一块，块开头找人、块里跟着上一帧的关键点走；只是 4 块一起送进姿势模型（显存约 1.2GB）。
一行一个请求（JSON）：{video, w, h, fps, ffmpeg, out} → 一行回复 {ok, n, sec} 或 {error}；3 分钟没有请求就退出（释放显存）。"""
import json, os, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch
from PIL import Image
import detect, onnx_torch

NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
BODY = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
IDLE = 180


def frames(path, ffmpeg, w, h, fps):  # 和 cutpoints._frames 一样
    k = 512 / max(w, h); W, H = max(2, int(w * k) // 2 * 2), max(2, int(h * k) // 2 * 2)
    p = subprocess.Popen([ffmpeg, '-v', 'error', '-threads', '2', '-i', path, '-an', '-threads', '2', '-vf', f'fps={fps},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         stdout=subprocess.PIPE, creationflags=NO_WINDOW)
    n = W * H * 3
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n:
                break
            yield np.frombuffer(b, np.uint8).reshape(H, W, 3)
    finally:
        p.kill()


def run_group(S, chunks):
    """几块（每块最多 12 帧）一起：一步一帧，各块的这一帧凑成一批送进姿势模型"""
    out = [[] for _ in chunks]; box = [None] * len(chunks)
    for i in range(max(len(c) for c in chunks)):
        pre, who = [], []
        for c, fr in enumerate(chunks):
            if i >= len(fr):
                continue
            im = Image.fromarray(fr[i])
            if box[c] is None and i % 4 == 0:
                ps = detect.persons(im, 0.3, S)
                if ps:
                    box[c] = max(ps, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            if box[c] is None:
                out[c].append(np.full((133, 3), np.nan)); continue
            a, g = detect.kp_pre(im, box[c]); pre.append((a, g)); who.append(c)
        if not who:
            continue
        sx, sy = S['pose'].run(None, {'input': np.stack([a for a, _ in pre])})
        for k, c in enumerate(who):
            kp = detect.kp_post(sx[k], sy[k], pre[k][1]); out[c].append(kp)
            body = kp[BODY]; ok = body[:, 2] > 0.3
            if ok.sum() >= 4:
                xs, ys = body[ok, 0], body[ok, 1]; m = 0.15 * max(np.ptp(xs), np.ptp(ys), 20)
                box[c] = [xs.min() - m, ys.min() - m, xs.max() + m, ys.max() + m, 1.0]
    return [k for o in out for k in o]


def main():
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'detect')
    S = {'det': onnx_torch.Session(os.path.join(d, 'yolox_l.onnx')), 'pose': onnx_torch.Session(os.path.join(d, 'dw-ll_ucoco_384.onnx'))}
    print(json.dumps({'ready': True}), flush=True)
    last = [time.time()]
    def idle():  # 3 分钟没有请求：退出，显存还给别人
        while True:
            time.sleep(5)
            if time.time() - last[0] > IDLE:
                os._exit(0)
    threading.Thread(target=idle, daemon=True).start()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        last[0] = time.time()
        try:
            q = json.loads(line)
            if q.get('quit'):
                break
            t0 = time.time(); allk, grp, ch = [], [], []
            cf, left = q.get('calm'), [float(q.get('calm_max') or 120)]
            def calm_wait():  # 后台提前分析时：剪辑里正在播放就先停（看 cutpoints.CALM_F 的修改时间），最多让 calm_max 秒
                while cf and left[0] > 0:
                    try:
                        if time.time() - os.path.getmtime(cf) >= float(q.get('calm_s') or 2.5):
                            return
                    except OSError:
                        return
                    time.sleep(0.2); left[0] -= 0.2
            for fr in frames(q['video'], q['ffmpeg'], q['w'], q['h'], q['fps']):
                ch.append(fr)
                if len(ch) == 12:
                    grp.append(ch); ch = []
                    if len(grp) == 4:
                        calm_wait(); allk += run_group(S, grp); grp = []
            if ch:
                grp.append(ch)
            if grp:
                allk += run_group(S, grp)
            np.save(q['out'], np.array(allk) if allk else np.zeros((0, 133, 3)))
            print(json.dumps({'ok': True, 'n': len(allk), 'sec': round(time.time() - t0, 2)}), flush=True)
        except Exception as e:
            print(json.dumps({'error': f'{type(e).__name__}: {e}'}), flush=True)
        finally:
            torch.cuda.empty_cache()
        last[0] = time.time()


if __name__ == '__main__':
    main()
