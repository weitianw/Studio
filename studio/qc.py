"""生视频 / 改视频的自动质检（2026-11-06 用户要求：做成开关，开了才对每一段自动查，不开什么都不变）。

全部在 CPU 上跑（detect.py 的 ONNX 模型），不占显卡、不挡生成队列；5 秒的一段约 10～20 秒。每秒取 3 帧，查：
- 人少了：原视频这一刻有、成品里没有（改视频）
- 动作跑偏：同一个人的身体关键点和原视频差得多（改视频；已按成品和原视频的帧差对齐）
- 长相变了：原视频和成品同一时刻、同一个人的正脸都看得清，人脸识别（ArcFace）相似度却很低（改视频）。
  注意：30～50 像素的小脸上嘴、鼻子那种变形，关键点和人脸识别都认不出（2026-11-06 实测），所以不报“脸变形”，免得乱报
连续两帧以上才算（单独一帧的误报不报）。结果记在视频库这一条的 qc 里：{v, flags: [{a, b, kind, msg}], took}。
"""
import os, subprocess, threading, time
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import numpy as np
from PIL import Image

FPS = 3
KIND_MSG = {'person': '人物不见了', 'drift': '动作和原视频差得多', 'face': '长相和原视频差别大'}
ARC = config.comfy('ComfyUI', 'models', 'insightface', 'models', 'buffalo_l', 'w600k_r50.onnx')
ARC_T = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)
_arc = None
_lock = threading.Lock()  # 一次只查一段（CPU 占用不叠加）


def _frames(ffmpeg, path, start=0.0, dur=None):
    """按 FPS 取帧（原尺寸）：[(秒, PIL 图)]"""
    import io, struct
    # 帧从管道里读（BMP 头里有长度），不落盘（以前写在系统临时目录：私密画面会留在 .data 外，2026-11-16 审查）
    args = [ffmpeg, '-v', 'error', '-ss', f'{max(0.0, start):.3f}', '-i', path] + (['-t', f'{dur:.3f}'] if dur else []) + ['-vf', f'fps={FPS}', '-f', 'image2pipe', '-c:v', 'bmp', '-']
    raw = subprocess.run(args, capture_output=True, timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    out, k = [], 0
    while k + 6 <= len(raw) and raw[k:k + 2] == b'BM':
        n = struct.unpack_from('<I', raw, k + 2)[0]
        if n <= 0 or k + n > len(raw):
            break
        with Image.open(io.BytesIO(raw[k:k + n])) as im:
            out.append((len(out) / FPS, im.convert('RGB').copy()))
        k += n
    return out


def _people(img):
    """[(人体框, 133 个关键点)]，按框的中心从左到右排"""
    import detect
    ps = [p for p in detect.persons(img) if p[4] > 0.5]
    ps.sort(key=lambda b: (b[0] + b[2]) / 2)
    return [(p, detect.keypoints(img, p)) for p in ps]


def _body(k, box):
    """身体 17 点，按人体框归一化（位置 + 大小无关），只用看得清的点"""
    w, h = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    b = k[:17]
    return np.stack([(b[:, 0] - box[0]) / w, (b[:, 1] - box[1]) / h, b[:, 2]], 1)


def _face_ok(k, thr=0.45):
    f = k[23:91]
    return float(np.mean(f[:, 2])) >= thr


def _face_px(k):
    f = k[23:91]; f = f[f[:, 2] > 0.3]
    return float(max(f[:, 0].max() - f[:, 0].min(), f[:, 1].max() - f[:, 1].min())) if len(f) >= 12 else 0.0


def _runs(hits, kind):
    """连续 2 个取样点以上的才报：[(起, 止)]"""
    out, cur = [], []
    for t in sorted(hits):
        if cur and t - cur[-1] > 1.5 / FPS:
            if len(cur) >= 2:
                out.append((cur[0], cur[-1] + 1 / FPS))
            cur = []
        cur.append(t)
    if len(cur) >= 2:
        out.append((cur[0], cur[-1] + 1 / FPS))
    return [{'a': round(a, 1), 'b': round(b, 1), 'kind': kind, 'msg': KIND_MSG[kind]} for a, b in out]


def check(res_path, ffmpeg, src_path=None, lag=0.0, face=True):
    """查一段成品。src_path：对比用的原视频（和成品起点、尺寸一致，lag = 成品比它早多少秒）"""
    import detect
    if not detect.available('pose'):
        return {'v': 1, 'flags': [], 'skip': '缺少检测模型'}
    t0 = time.time()
    with _lock:
        R = _frames(ffmpeg, res_path)
        S = dict((round(t, 2), im) for t, im in _frames(ffmpeg, src_path, max(0.0, lag))) if src_path else {}
        hit = {k: [] for k in KIND_MSG}
        M = {'sim': [], 'fl': [], 'bl': [], 'drift': []}  # 2026-11-14 数字小结（Agent 按数字判断好坏，看不到画面）：脸相似、脸 / 背景亮度差、动作差
        for t, im in R:
            rp = _people(im)
            sm = S.get(round(t, 2))
            if sm is not None:
                if sm.size != im.size:
                    sm = sm.resize(im.size, Image.LANCZOS)
                sp = _people(sm)
                _light(M, im, sm, rp, sp)
                if len(rp) < len(sp):
                    hit['person'].append(t)
                for (rb, rk), (sb, sk) in zip(rp, sp):  # 左右顺序一一对上（人数一样时）
                    if len(rp) != len(sp):
                        break
                    a, b = _body(rk, rb), _body(sk, sb)
                    vis = (a[:, 2] > 0.4) & (b[:, 2] > 0.4)
                    dv = float(np.mean(np.hypot(a[vis, 0] - b[vis, 0], a[vis, 1] - b[vis, 1]))) if vis.sum() >= 8 else None
                    if dv is not None:
                        M['drift'].append(dv)
                    if dv is not None and dv > 0.16:
                        hit['drift'].append(t)
                    if face and _face_ok(sk, 0.8) and _face_ok(rk, 0.8) and min(_face_px(sk), _face_px(rk)) >= 30:  # face：换人 / 换头本来就换脸，不比  # 两边都是看得清的正脸才比（手挡住、侧脸时跳过）
                        ea, eb = _emb(im, rk), _emb(sm, sk)
                        if ea is not None and eb is not None:
                            M['sim'].append(float(ea @ eb))
                        if ea is not None and eb is not None and float(ea @ eb) < 0.3:
                            hit['face'].append(t)
        flags = sum((_runs(v, k) for k, v in hit.items()), [])
    flags.sort(key=lambda f: f['a'])
    avg = lambda v, r=3: round(float(np.mean(v)), r) if v else None
    m = {'face_sim': avg(M['sim']), 'face_dL': avg(M['fl'], 1), 'bg_dL': avg(M['bl'], 1), 'drift': avg(M['drift'])} if S else None
    return {'v': 1, 'flags': flags, 'n': len(R), 'took': round(time.time() - t0, 1), **({'m': m} if m else {})}


def _L(img):
    """CIE L*（0~100）：sRGB → 线性 → 亮度 Y → L*（只要亮度差，不用 cv2）"""
    a = np.asarray(img.convert('RGB'), np.float32) / 255
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    y = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def _light(M, im, sm, rp, sp):
    """脸：原视频里每张脸（关键点框）里成品 − 原视频的亮度；背景：画面上方 20% + 左右各 10%、去掉两边的人体框"""
    Lg, Ls = _L(im), _L(sm); H, W = Ls.shape
    for _, k in sp:
        f = k[23:91]; f = f[f[:, 2] > 0.3]
        if len(f) < 12:
            continue
        x0, y0, x1, y1 = f[:, 0].min(), f[:, 1].min(), f[:, 0].max(), f[:, 1].max()
        if x1 - x0 < 20:
            continue
        xa, ya, xb, yb = (int(np.clip(v, 0, lim)) for v, lim in ((x0, W), (y0, H), (x1, W), (y1, H)))
        if xb > xa + 4 and yb > ya + 4:
            M['fl'].append(float((Lg[ya:yb, xa:xb] - Ls[ya:yb, xa:xb]).mean()))
    reg = np.zeros((H, W), bool); reg[:int(H * .2)] = True; reg[:, :int(W * .1)] = True; reg[:, -int(W * .1):] = True
    for b, _ in list(rp) + list(sp):
        pw, ph = (b[2] - b[0]) * .05, (b[3] - b[1]) * .05
        reg[max(0, int(b[1] - ph)):int(b[3] + ph), max(0, int(b[0] - pw)):int(b[2] + pw)] = False
    if reg.sum() > 500:
        M['bl'].append(float((Lg[reg] - Ls[reg]).mean()))


def _emb(img, k):
    """一张脸的 ArcFace 特征（按 DWPose 脸部 5 个点对齐成 112×112）；模型不在返回 None"""
    global _arc
    f = k[23:91]
    if not os.path.isfile(ARC):
        return None
    p = np.array([f[36:42, :2].mean(0), f[42:48, :2].mean(0), f[30, :2], f[48, :2], f[54, :2]], np.float32)
    mu_s, mu_d = p.mean(0), ARC_T.mean(0); a, b = p - mu_s, ARC_T - mu_d
    U, S, Vt = np.linalg.svd(b.T @ a / 5); d = np.sign(np.linalg.det(U @ Vt)); D = np.diag([1, d])
    R = U @ D @ Vt; sc = (S * np.diag(D)).sum() / (a ** 2).sum() * 5; t = mu_d - sc * R @ mu_s
    Ai = np.linalg.inv(np.vstack([np.hstack([sc * R, t[:, None]]), [0, 0, 1]]))[:2]
    x = (np.asarray(img.transform((112, 112), Image.AFFINE, tuple(Ai.flatten()), Image.BILINEAR), np.float32) - 127.5) / 127.5
    if _arc is None:
        import onnxruntime as ort
        o = ort.SessionOptions(); o.intra_op_num_threads = 4
        _arc = ort.InferenceSession(ARC, o, providers=['CPUExecutionProvider'])
    e = _arc.run(None, {_arc.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0]
    return e / (np.linalg.norm(e) + 1e-6)
