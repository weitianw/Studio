"""找适合换装 / 拼接的时间点（2026-11-05 用户要求）：全部在 CPU 上算，不占显卡（生成时显存几乎是满的，抢显存会让生成失败）。

对照网上的几种做法：剪映类“自动踩点”只看音乐；Davis & Agrawala 2018 “Visual Rhythm and Beat”= 动作突然减速；
AIST++ 的“动作节拍”= 全身关节速度的低谷；Endo 2024 的舞蹈分段模型没有公开，用不了。
用 @奶油乎乎 那段 A/B（拿“和音乐节拍对得多齐”当客观指标，随机时间点 0.52）：速度低谷 0.44（比随机还差：落在两拍中间），
动作最猛的一下 0.70、“动作刚做完”0.75（只看最强的 8 个，24 帧 / 秒；12 帧 / 秒只有 0.53 / 0.62）。所以：
1. 音乐节拍：Beat This!（ISMIR 2024，比经典做法准；经典做法在这段只找到一半的拍）；用不了时退回经典做法
2. 动作：DWPose（models/detect，和修脸修手同一套）每秒 24 帧找人体关键点，先在时间上平滑
3. 候选点：定格（一个动作刚做完、停住）、大动作（动作最猛的一下）、转身（背对镜头）；离节拍近的加分，离重拍近的再加分，0.12 秒内就对到拍上
结果按视频内容缓存（内存 + 小文件），同一个视频第二次直接出。"""
import hashlib, json, os, subprocess, sys, threading, time
import numpy as np

NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
BG_PRI = NO_WINDOW | (0x00004000 if os.name == 'nt' else 0)  # 后台提前分析：低一级的优先级（BELOW_NORMAL）
_cache, _lock, _busy = {}, threading.Lock(), {}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BT, _bt_lock = None, threading.Lock()
# 剪辑里正在播放（网页每 2 秒告诉一次，2026-11-11 用户：剪辑里播放卡）：后台提前分析先停下，不和播放抢显卡 / CPU；停播 2.5 秒后接着算。
# 用户点了按钮在等（hurry）时不停；一次分析最多让 2 分钟
CALM_F = os.path.join(ROOT, 'studio', 'tmp', 'cutpoints', 'calm')  # 显卡助手（另一个进程）看这个文件的修改时间
_calm = [0.0]
CALM_S, CALM_MAX = 2.5, 120


def calm():
    with _lock:
        if any(k in _hurry for k in _busy):  # 用户点了按钮在等：不停
            return
    _calm[0] = time.time()
    try:
        os.makedirs(os.path.dirname(CALM_F), exist_ok=True)
        with open(CALM_F, 'a'):
            pass
        os.utime(CALM_F, None)
    except OSError:
        pass


def _calm_wait(key, left):
    """正在播放就等一等；left = [还能让多少秒]"""
    while left[0] > 0 and time.time() - _calm[0] < CALM_S and key not in _hurry:
        time.sleep(0.2); left[0] -= 0.2


def _key(path):
    st = os.stat(path); h = hashlib.sha1(str(st.st_size).encode())
    with open(path, 'rb') as f:
        h.update(f.read(1 << 20)); f.seek(max(0, st.st_size - (1 << 20))); h.update(f.read(1 << 20))
    return h.hexdigest()[:20]


# ------------------------------------------------------------------ 音乐节拍
def _audio(path, ffmpeg, sr=22050):
    try:
        r = subprocess.run([ffmpeg, '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True, timeout=180, creationflags=NO_WINDOW)
        x = np.frombuffer(r.stdout, np.float32)
    except Exception:
        return None
    return x if x.size > sr and float(np.sqrt(np.mean(x ** 2))) > 1e-4 else None


def _onset(x, sr=22050, hop=512, n=2048):
    """谱通量起音强度（突出的起音，已除以标准差）、低频起音、每帧的响度（RMS）、每秒几帧"""
    nf = 1 + (x.size - n) // hop
    fr = np.lib.stride_tricks.as_strided(x, (nf, n), (x.strides[0] * hop, x.strides[0]))
    S = np.abs(np.fft.rfft(fr * np.hanning(n).astype(np.float32), axis=1))
    L = np.log1p(1000 * S)
    fq = np.fft.rfftfreq(n, 1 / sr)
    d = np.maximum(0, np.diff(L, axis=0))
    on = d[:, fq < 8000].mean(1); low = d[:, fq < 160].mean(1)  # 全频的起音强度；低频（鼓 / 贝斯）用来找重拍
    on = np.concatenate([[0], on]); low = np.concatenate([[0], low])
    k = np.ones(int(sr / hop)) / int(sr / hop)  # 减去 1 秒内的平均，留下突出的起音
    m = k.size // 2; on = np.maximum(0, on - np.convolve(np.pad(on, m, mode='reflect'), k, 'same')[m:m + on.size]); on[:2] = 0; sd = on.std() or 1; on = on / sd  # 两头用镜像补齐（不然开头会多出一拍）
    rms = np.sqrt(np.mean(fr.astype(np.float64) ** 2, axis=1)); rms = np.concatenate([[rms[0] if rms.size else 0], rms])
    return on, low, rms, sr / hop


def beats(x, sr=22050, hop=512, n=2048):
    """→ (节拍时间, 重拍时间, 每拍强度 0~1, BPM)。经典做法：谱通量起音强度 → 自相关估速度 → 动态规划（Ellis 2007）"""
    if x is None or x.size < n * 4:
        return [], [], [], 0
    on, low, _, fps = _onset(x, sr, hop, n)
    lags = np.arange(int(fps * 60 / 200), int(fps * 60 / 55) + 1)
    lags = lags[lags < on.size]
    ac = np.zeros(on.size)
    ac[lags] = [float(np.dot(on[:-L], on[L:])) for L in lags]  # 2026-11-14 审查：以前整段做 'full' 自相关（长度平方），只要 55～200 BPM 这几十个间隔
    if not lags.size:
        return [], [], [], 0
    bpm = 60 * fps / lags; w = np.exp(-0.5 * (np.log2(bpm / 120) / 0.9) ** 2)
    p = int(lags[np.argmax(ac[lags] * w)])  # 一拍有几帧
    cs, bk = on.copy(), -np.ones(on.size, int)
    for t in range(on.size):  # 动态规划：节拍落在起音上，相邻两拍的间隔接近 p
        a, b = t - 2 * p, t - p // 2
        if b <= 0:
            continue
        pr = np.arange(max(0, a), b)
        sc = cs[pr] - 100 * np.log((t - pr) / p) ** 2
        i = int(np.argmax(sc)); cs[t] = on[t] + sc[i]; bk[t] = pr[i]
    tail = cs[-p:] if cs.size > p else cs
    t = int(np.argmax(tail)) + cs.size - tail.size
    out = []
    while t >= 0:
        out.append(t); t = bk[t]
    out = np.array(out[::-1])
    if out.size:  # 开头 / 结尾很弱的拍（回溯时一路连到开头、或没有音乐的部分）：去掉（librosa 也这样）
        th = 0.25 * float(np.median(on[out])); a, b = 0, out.size
        while a < b and on[out[a]] < th:
            a += 1
        while b > a and on[out[b - 1]] < th:
            b -= 1
        out = out[a:b]
    if out.size < 4:
        return [], [], [], 0
    bt = (out * hop + n / 2) / sr  # 每一帧的中心
    st = on[out]; st = st / (np.percentile(st, 95) or 1)
    lw = low[out] / (low[out].max() or 1)
    ph = max(range(4), key=lambda q: float(np.mean(lw[q::4]) + 0.5 * np.mean(st[q::4] if st[q::4].size else [0])))  # 重拍：4 拍里哪一相位的低频最重
    return [round(float(v), 3) for v in bt], [round(float(v), 3) for v in bt[ph::4]], [round(float(min(1, v)), 3) for v in st], round(60 * (bt.size - 1) / float(bt[-1] - bt[0]), 1)


def accents(x, bt, db, sr=22050):
    """每一拍的音乐重音（2026-11-10 用户：换装段落一般卡在音乐上——重音、鼓点进来、突然停下）→ [{t, acc 0~1, db, chg}]。
    acc：这一拍附近（±50 毫秒）起音有多突出（按全曲 95% 分位归一）；db：是不是重拍；chg：段落变化（这一拍前后 1.5 秒响度差很多：鼓点进来 / 突然安静）"""
    if x is None or not len(bt) or x.size < 2048 * 4:
        return []
    on, low, rms, fps = _onset(x, sr)
    lo = low / (np.percentile(low, 95) or 1); top = np.percentile(on, 95) or 1
    dbs = np.array(db) if len(db) else np.zeros(0)
    out = []
    for t in bt:
        i = int(round(t * fps)); a, b = max(0, i - 2), min(on.size, i + 3)
        if a >= b:
            continue
        acc = float(min(1.0, 0.7 * on[a:b].max() / top + 0.3 * min(1.0, lo[a:b].max())))
        w = int(1.5 * fps); pre, post = rms[max(0, i - w):i], rms[i:i + w]
        r = (post.mean() + 1e-6) / (pre.mean() + 1e-6) if pre.size > fps * 0.5 and post.size > fps * 0.5 else 1.0
        out.append({'t': float(t), 'acc': acc, 'db': bool(dbs.size and np.min(np.abs(dbs - t)) < 0.02), 'chg': bool(r >= 2.0 or r <= 0.45)})  # 卡点舞里鼓点很密：只算明显的段落变化
    return out


def beats_bt(x, sr=22050, threads=None):
    """Beat This!（ISMIR 2024，tools/beat_this_lib + models/beat_this/final0.ckpt，CPU）→ (节拍, 重拍, BPM)；用不了时返回 None"""
    global _BT
    ck = os.path.join(ROOT, 'models', 'beat_this', 'final0.ckpt')
    if x is None or not os.path.isfile(ck):
        return None
    try:
        with _bt_lock:
            if _BT is None:
                lib = os.path.join(ROOT, 'tools', 'beat_this_lib')
                if lib not in sys.path:
                    sys.path.append(lib)
                from beat_this.inference import Audio2Beats
                _BT = Audio2Beats(ck, device='cpu', dbn=False)
            import torch
            old = torch.get_num_threads(); torch.set_num_threads(threads or THREADS)  # 只在这一下限制线程数（不影响 Studio 里别的用 torch 的地方）
            try:
                b, d = _BT(x, sr)
            finally:
                torch.set_num_threads(old)
    except Exception:
        return None
    b = [round(float(v), 3) for v in b]; d = [round(float(v), 3) for v in d]
    return (b, d, round(60 * (len(b) - 1) / (b[-1] - b[0]), 1)) if len(b) > 1 else ([], [], 0)


# ------------------------------------------------------------------ 动作
def _frames(path, ffmpeg, w, h, fps, pri=NO_WINDOW):
    k = 512 / max(w, h); W, H = max(2, int(w * k) // 2 * 2), max(2, int(h * k) // 2 * 2)
    p = subprocess.Popen([ffmpeg, '-v', 'error', '-threads', '2', '-i', path, '-an', '-threads', '2', '-vf', f'fps={fps},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         stdout=subprocess.PIPE, creationflags=pri)
    n = W * H * 3
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n:
                break
            yield np.frombuffer(b, np.uint8).reshape(H, W, 3)
    finally:
        p.kill()


THREADS = max(2, min(6, (os.cpu_count() or 8) // 5))  # 后台提前分析：32 线程的电脑用 6 个，不打扰别的事
FULL = max(2, (os.cpu_count() or 8) // 2)  # 点了按钮、正在等：用一半的线程（和修脸修手一样，大约是全部的物理核）
_hurry = set()  # 后台正在算、这时用户点了按钮：中途换成全速
BODY = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]  # 肩、肘、腕、髋、膝、踝（COCO 顺序）
BW = np.array([1, 1, 1, 1, 1.5, 1.5, 1, 1, 1, 1, 1.2, 1.2])  # 手腕、脚踝动得最明显：权重高一点


def track(path, ffmpeg, w, h, fps, threads=None, key=None):
    """逐帧的人体关键点 (N, 133, 3)；画面里没人的帧是 NaN。
    视频切成每 12 帧（半秒）一块，几块同时算（每块开头重新找人，块里跟着上一帧的关键点走——和以前一帧一帧算的结果一样）：
    姿势模型多开几个线程几乎不变快，同时算几块才快（2026-11-05 实测：16 秒的视频 17 秒 → 见 A/B 记录）。
    点了按钮 4 块同时算；后台提前分析 2 块；后台算到一半用户点了按钮：再加 2 个一起算"""
    import detect, queue, concurrent.futures as cfu
    from PIL import Image
    full = (threads or THREADS) >= FULL
    per = max(1, FULL // 4)  # 每个姿势模型会话的线程数
    det = detect.sessions(per, ('det',))['det']; pool = queue.Queue(); n_pose = [0]
    def add(n):
        for _ in range(n):
            pool.put(detect.sessions(per, ('pose',))['pose']); n_pose[0] += 1
    add(4 if full else 2)
    nan = np.full((133, 3), np.nan)
    def run(frames):
        P = pool.get()
        try:
            S = {'det': det, 'pose': P}; out, box = [], None
            for i, fr in enumerate(frames):
                im = Image.fromarray(fr)
                if box is None and i % 4 == 0:
                    ps = detect.persons(im, 0.3, S)
                    if ps:
                        box = max(ps, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                if box is None:
                    out.append(nan); continue
                kp = detect.keypoints(im, box, S); out.append(kp)
                body = kp[BODY]; ok = body[:, 2] > 0.3
                if ok.sum() >= 4:
                    xs, ys = body[ok, 0], body[ok, 1]; m = 0.15 * max(np.ptp(xs), np.ptp(ys), 20)
                    box = [xs.min() - m, ys.min() - m, xs.max() + m, ys.max() + m, 1.0]
            return out
        finally:
            pool.put(P)
    futs, chunk, left = [], [], [CALM_MAX]
    with cfu.ThreadPoolExecutor(4) as ex:
        for fr in _frames(path, ffmpeg, w, h, fps, NO_WINDOW if full else BG_PRI):
            if key and n_pose[0] < 4 and key in _hurry:  # 用户在等了：再加 2 个一起算
                add(4 - n_pose[0])
            chunk.append(fr)
            if len(chunk) == 12:
                if not full and key:
                    _calm_wait(key, left)
                futs.append(ex.submit(run, chunk)); chunk = []
                while sum(not f.done() for f in futs) > 8:  # 读得比算得快：等一等（最多 8 块在内存里，约 40MB）
                    next(f for f in futs if not f.done()).result()
        if chunk:
            futs.append(ex.submit(run, chunk))
        out = [k for f in futs for k in f.result()]
    return np.array(out) if out else np.zeros((0, 133, 3))


COMFY_PY = os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'python_embeded', 'python.exe')
_gpu = {'p': None, 'lock': threading.Lock()}


def gpu_free():
    """显卡闲着吗：利用率 < 25% 且空着 ≥ 3GB（找换装点在显卡上要约 1.2GB）"""
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                           capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
        u, used, tot = [float(x) for x in r.stdout.strip().splitlines()[0].split(',')]
        return u < 25 and tot - used >= 3000
    except Exception:
        return False


def track_gpu(path, ffmpeg, w, h, fps, tmp_dir, calm=None):
    """在显卡上算关键点（pose_gpu.py，用 ComfyUI 的 Python）；不行就返回 None（改用 CPU）"""
    if not os.path.isfile(COMFY_PY):
        return None
    import uuid
    os.makedirs(tmp_dir, exist_ok=True)  # 第一次用时缓存文件夹还没有
    out = os.path.join(tmp_dir, 'kp_' + uuid.uuid4().hex[:8] + '.npy')
    with _gpu['lock']:
        p = _gpu['p']
        try:
            if p is None or p.poll() is not None:
                log = open(os.path.join(tmp_dir, 'pose_gpu.log'), 'ab')
                p = _gpu['p'] = subprocess.Popen([COMFY_PY, '-s', os.path.join(ROOT, 'studio', 'pose_gpu.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                 stderr=log, creationflags=NO_WINDOW, text=True, encoding='utf-8')
                if not _readline(p, 90).get('ready'):
                    raise RuntimeError('显卡助手没有启动')
            p.stdin.write(json.dumps({'video': path, 'w': w, 'h': h, 'fps': fps, 'ffmpeg': ffmpeg, 'out': out, 'calm': calm, 'calm_s': CALM_S, 'calm_max': CALM_MAX}) + chr(10)); p.stdin.flush()
            r = _readline(p, 300 + (CALM_MAX if calm else 0))
            if not r.get('ok'):
                raise RuntimeError(r.get('error') or '显卡助手没有回复')
            return np.load(out)
        except Exception:
            try:
                p and p.kill()
            except Exception:
                pass
            _gpu['p'] = None
            return None
        finally:
            try:
                os.remove(out)
            except OSError:
                pass


def _readline(p, timeout):
    box = {}
    t = threading.Thread(target=lambda: box.setdefault('l', p.stdout.readline()), daemon=True); t.start(); t.join(timeout)
    if 'l' not in box or not box['l']:
        return {}
    try:
        return json.loads(box['l'])
    except ValueError:
        return {}


def _fill(a):  # 没找到人 / 关键点不可信的帧：用前后的补上
    a = a.copy(); bad = np.isnan(a)
    if bad.all():
        a[:] = 0
    elif bad.any():
        a[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), a[~bad])
    return a


def features(kp, fps):
    """关键点 → (动作速度, “动作刚做完”的强度, 背对镜头 0~1)。A/B（2026-11-05，@奶油乎乎 那段）：
    速度低谷（AIST++ 的动作节拍）落在两拍中间，和拍对得比随机还差，不用；动作最猛的一下、“动作刚做完”（前 0.3 秒姿势变化大、之后 0.25 秒几乎不动）都正好在拍上"""
    from scipy.signal import savgol_filter
    n = kp.shape[0]
    xy = kp[:, :, :2].astype(float).copy(); cf = np.nan_to_num(kp[:, :, 2], nan=0.0)
    xy[cf < 0.3] = np.nan
    for j in range(133):
        for c in (0, 1):
            xy[:, j, c] = _fill(xy[:, j, c])
    if n >= 7:
        xy = savgol_filter(xy, 7 if fps >= 20 else 5, 2, axis=0)  # 关键点先在时间上平滑（DWPose 每帧会抖一点）
    sc = np.linalg.norm((xy[:, 5] + xy[:, 6]) / 2 - (xy[:, 11] + xy[:, 12]) / 2, axis=1)
    sc = max(float(np.nanmedian(sc)) if np.isfinite(sc).any() else 0, 10.0)  # 躯干长：整段用一个数
    ok = cf[:, BODY] > 0.3
    d = np.linalg.norm(np.diff(xy[:, BODY], axis=0), axis=2) / sc * fps
    o2 = ok[1:] & ok[:-1]
    v = np.sqrt(np.sum(d ** 2 * BW * o2, 1) / np.maximum(1e-6, np.sum(BW * o2, 1))); v[o2.sum(1) < 4] = np.nan
    v = _fill(np.concatenate([[np.nan], v]) if v.size else np.zeros(n))
    g = np.exp(-0.5 * (np.arange(-3, 4) / 1.0) ** 2); g /= g.sum()
    v = np.convolve(np.pad(v, 3, mode='edge'), g, 'valid') if n >= 3 else v
    cen = (xy[:, 11] + xy[:, 12]) / 2; Q = (xy[:, BODY] - cen[:, None]) / sc
    a, b = max(1, int(round(0.3 * fps))), max(1, int(round(0.25 * fps))); ch = np.full(n, np.nan)
    for i in range(a, n - b):
        ch[i] = np.mean(np.linalg.norm(Q[i] - Q[i - a], axis=1)) - 1.5 * np.mean(np.linalg.norm(Q[i + b] - Q[i], axis=1))
    ch = np.nan_to_num(ch, nan=float(np.nanmin(ch)) if np.isfinite(ch).any() else 0.0)
    face = cf[:, [0, 1, 2]].mean(1); flip = (xy[:, 5, 0] - xy[:, 6, 0]) / sc; shv = np.minimum(cf[:, 5], cf[:, 6]) > 0.4  # 正面时人的左肩在画面右边
    back = np.where(shv, np.clip((0.45 - face) / 0.3, 0, 1) * 0.6 + np.where(flip < -0.08, 0.4, 0), 0.0)
    return v, ch, back


def diff_motion(path, ffmpeg, w, h, fps):  # 没有姿势模型时：画面变化量
    out, prev = [], None
    for fr in _frames(path, ffmpeg, w, h, fps):
        g = fr[::8, ::8].mean(2); out.append(float(np.abs(g - prev).mean()) if prev is not None else 0.0); prev = g
    return np.array(out)


# ------------------------------------------------------------------ 合起来
def points(ts, v, ch, back, bt, db, fps, acc=None):
    from scipy.signal import find_peaks
    if v.size < 8:
        return []
    out = []
    med = float(np.median(v)) or 1e-6
    p, _ = find_peaks(v, height=1.8 * med, distance=max(1, int(0.25 * fps)))
    for i in p:
        out.append({'t': ts[i], 'kind': 'swing', 'base': 0.85 * min(1.0, (v[i] / med - 1) / 3)})
    if ch is not None and np.ptp(ch) > 0:
        p, _ = find_peaks(ch, height=np.percentile(ch, 70), distance=max(1, int(0.3 * fps)))
        top = np.percentile(ch[p], 90) if p.size else 1
        for i in p:
            out.append({'t': ts[i], 'kind': 'hit', 'base': float(np.clip(ch[i] / (top or 1), 0, 1))})
    on = back > 0.55; i = 0  # 背对镜头的一段：取中间
    while i < on.size:
        if on[i]:
            j = i
            while j + 1 < on.size and on[j + 1]:
                j += 1
            if (j - i + 1) / fps >= 0.15:
                out.append({'t': ts[(i + j) // 2], 'kind': 'turn', 'base': 0.9})
            i = j + 1
        else:
            i += 1
    bt, db = np.array(bt), np.array(db)
    A = {round(a['t'], 3): a for a in (acc or [])}
    # 2026-11-10 用户：换装段落一般卡在音乐上（重音）或定格 / 大动作上，两者都卡上的最好。打分改成：
    # 只有动作 ≈ 0.6 × 动作强度；只有音乐 = 0.3 + 0.4 × 重音（重拍 +0.1，段落变化 +0.15）；动作正好在拍上再加 0.2 + 0.25 × 这一拍的重音
    for p in out:
        p['why'] = [{'hit': '一个动作刚做完、停住', 'swing': '动作最猛的一下', 'turn': '背对镜头'}[p['kind']]]
        p['score'] = p['base'] * (0.65 if p['kind'] == 'turn' else 0.6)
        if bt.size:
            k = int(np.argmin(np.abs(bt - p['t']))); d = abs(bt[k] - p['t'])
            near_db = db.size and float(np.min(np.abs(db - bt[k]))) < 0.02
            if d <= 0.12:
                a = A.get(round(float(bt[k]), 3), {}).get('acc', 0.5)
                p['t'] = float(bt[k]); p['sync'] = True; p['db'] = bool(near_db)
                p['score'] += 0.2 + 0.25 * a + (0.05 if near_db else 0)
                p['why'].append(('正好在重拍上' if near_db else '正好在节拍上') + ('（音乐重音）' if a >= 0.6 else ''))
    for a in (acc or []):  # 只有音乐的卡点：明显的重音、重拍上的重音、段落变化
        if a['acc'] >= 0.8 or a['chg'] or (a['db'] and a['acc'] >= 0.6):  # 卡点舞每一拍都有起音：只要突出的
            why = ['音乐段落变化（鼓点进来 / 突然安静）'] if a['chg'] else []
            why.append('音乐重音' + ('（重拍）' if a['db'] else ''))
            out.append({'t': a['t'], 'kind': 'beat', 'base': a['acc'], 'why': why, 'db': a['db'],
                        'score': 0.3 + 0.4 * a['acc'] + (0.1 if a['db'] else 0) + (0.15 if a['chg'] else 0)})
    out.sort(key=lambda p: (p['kind'] == 'beat', -p['score'])); keep = []  # 同一时刻有动作也有音乐：留动作那个（已经算了在拍上的分），音乐的理由合进去
    for p in out:  # 0.25 秒内只留分最高的，原因合在一起
        q = next((q for q in keep if abs(q['t'] - p['t']) < 0.25), None)
        if q:
            if p['kind'] == 'beat' and not q.get('sync') and q['kind'] != 'beat':  # 动作离拍稍远（0.12~0.25 秒）：算作差不多卡上
                q['score'] = max(q['score'], p['score']) + 0.1; q['sync'] = True; q['db'] = q.get('db') or p.get('db')
            q['why'] += [w for w in p['why'] if w not in q['why']]
            if p['kind'] == 'turn' and q['kind'] != 'turn':  # 合进来的有“背对镜头”：标成转身（最适合换装的理由）
                q['also'], q['kind'] = q['kind'], 'turn'
        else:
            keep.append(p)
    return sorted([{'t': round(float(p['t']), 3), 'kind': p['kind'], 'score': round(float(min(1.0, p['score'])), 3), 'why': p['why'], **({'also': p['also']} if p.get('also') else {}), **({'sync': True} if p.get('sync') else {}), **({'db': True} if p.get('db') else {})}
                   for p in keep if p['score'] >= 0.5], key=lambda p: p['t'])  # 只标突出的（以前 0.35：卡点舞 15 秒里标出 30 个，看不出哪个好）


VER = 4  # 算法改了就加一：旧的缓存不用（3：2026-11-10 加音乐重音、两者都卡上的加分）


def hurry(path):
    """后台正在算这个视频：让它换成全速（用户点了按钮在等）"""
    k = f'{_key(path)}v{VER}'
    with _lock:
        if k in _busy:
            _hurry.add(k); _calm[0] = 0.0
            try:
                os.remove(CALM_F)  # 显卡助手也别再等了
            except OSError:
                pass
            return True
    return False


def _analyze(path, ffmpeg, probe, cache_dir=None, bg=False, studio_idle=None):
    """→ {dur, fps, bpm, beats, downbeats, points:[{t, kind, score, why}], curve:[0~1], curve_fps, by, beat_by, took}；同一个视频算一次（内存 + cache_dir 里的小文件）"""
    k = f'{_key(path)}v{VER}'
    cf = os.path.join(cache_dir, k + '.json') if cache_dir else None
    while True:
        with _lock:
            if k in _cache:
                return _cache[k]
            ev = _busy.get(k)
            if not ev:
                if cf and os.path.isfile(cf):
                    try:
                        with open(cf, encoding='utf-8') as f:
                            _cache[k] = json.load(f)
                        return _cache[k]
                    except (OSError, ValueError):
                        pass
                ev = _busy[k] = threading.Event(); mine = True
                break
        if not bg:
            with _lock:
                _hurry.add(k)  # 后台在算、现在有人在等：让它换成全速
        ev.wait(600)  # 同一个视频正在算（比如后台提前分析）：等它算完
    try:
        t0 = time.time(); pr = probe(path) or {}
        w, h, fps0, dur = pr.get('width') or 0, pr.get('height') or 0, pr.get('fps') or 24, pr.get('duration') or 0
        if not w or not h:
            raise RuntimeError('读不出这段视频的画面')
        sf = 24 if dur <= 60 else 12 if dur <= 180 else 6  # 每秒 24 帧（A/B：比 12 帧准得多）；很长的视频少取一些
        x = _audio(path, ffmpeg) if pr.get('audio') else None
        thr = THREADS if bg else FULL
        r_bt = beats_bt(x, threads=thr)
        if r_bt is not None:
            bt, db, bpm = r_bt; beat_by = 'beat_this'
        else:
            bt, db, _, bpm = beats(x); beat_by = 'classic'
        import detect
        if detect.available('pose'):
            kp, why = None, ''
            if studio_idle is not None and not studio_idle():
                why = 'Studio 正在生成 / 配音'
            elif not gpu_free():
                why = '显卡正忙或显存不够'
            else:  # 显卡闲着（没有生成任务、利用率低、显存够）：在显卡上算，快很多
                kp = track_gpu(path, ffmpeg, w, h, sf, cache_dir or os.path.join(ROOT, 'studio', 'tmp', 'cutpoints'), CALM_F if bg and k not in _hurry else None)  # 不往原视频旁边写东西（2026-11-06：素材库里多出过 pose_gpu.log）
                why = '' if kp is not None else '显卡助手出错'
            dev = 'gpu'
            if kp is None:
                kp = track(path, ffmpeg, w, h, sf, thr, k); dev = 'cpu'
            v, ch, back = features(kp, sf); by = 'pose'
        else:
            v = diff_motion(path, ffmpeg, w, h, sf); ch, back, by = None, np.zeros(v.size), 'diff'
        ts = np.arange(v.size) / sf
        pts = points(ts, v, ch, back, bt, db, sf, accents(x, bt, db))
        for p in pts:  # 对到原视频的帧上
            p['t'] = round(round(p['t'] * fps0) / fps0, 3)
        mx = float(np.percentile(v, 98)) if v.size else 1
        r = {'dur': dur, 'fps': fps0, 'bpm': bpm, 'beats': bt, 'downbeats': db, 'points': pts, 'curve': [round(float(min(1, x_ / (mx or 1))), 3) for x_ in v[::2]],
             'curve_fps': sf / 2, 'by': by, 'beat_by': beat_by, 'dev': dev if by == 'pose' else 'cpu', 'cpu_why': why if by == 'pose' else '', 'took': round(time.time() - t0, 1)}
        with _lock:
            _cache[k] = r
            while len(_cache) > 30:
                _cache.pop(next(iter(_cache)))
        if cf:
            try:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cf, 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False)
                old = sorted((os.path.join(cache_dir, n) for n in os.listdir(cache_dir) if n.endswith('.json')), key=os.path.getmtime)
                for o in old[:-300]:  # 最多留 300 个（每个几 KB）
                    os.remove(o)
            except OSError:
                pass
        return r
    finally:
        with _lock:
            _busy.pop(k, None); _hurry.discard(k)
        ev.set()


# ------------------------------------------------------------------ 音乐段落（2026-11-14）
# All-In-One 音乐结构分析（allin1_run.py，单独进程、CPU）：每个点再记一个 sec = 这里是“音乐段落切换”的可能性。
# 15 秒的卡点舞通常整段只有一个段落（十一酱那段只找到一段），但切换的可能性在用户分段的 5.1 / 6.9 秒正好有小峰；
# 所以只当一个特征，交给按用户选段学出来的偏好去定权重（segpref.py），手写的推荐规则不变。旧的分析结果补算这一项，不用重算动作。
_sec_busy = {}
A1_LIB = os.path.join(ROOT, 'tools', 'allin1_lib', 'allin1_infer')


def sections(path, ffmpeg, threads, tmp_dir, bg=False):
    """→ {'sections': [[开始, 结束, 标签]…], 'act': […], 'fps': 50}；装不了 / 没有声音 / 出错时 None"""
    if not os.path.isdir(A1_LIB) or not os.path.isdir(os.path.join(ROOT, 'models', 'allin1')):
        return None
    import shutil, uuid
    d = os.path.join(tmp_dir, 'a1_' + uuid.uuid4().hex[:8]); os.makedirs(d, exist_ok=True)
    try:
        wav, out = os.path.join(d, 'a.wav'), os.path.join(d, 'r.json')
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', path, '-vn', '-ac', '2', '-ar', '44100', wav], check=True, capture_output=True, timeout=120, creationflags=NO_WINDOW)
        subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'studio', 'allin1_run.py'), wav, out, str(threads), d], capture_output=True, timeout=600,
                       creationflags=BG_PRI if bg else NO_WINDOW)
        with open(out, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _add_sec(r, path, ffmpeg, cache_dir, bg):
    if not r or r.get('sec_v') or not r.get('beats') or time.time() - (r.get('sec_try') or 0) < 6 * 3600:  # 已经补过 / 没有音乐 / 刚失败过（6 小时后再试）
        return r
    k = f'{_key(path)}v{VER}'
    with _lock:
        ev = _sec_busy.get(k)
        if ev is None:
            ev = _sec_busy[k] = threading.Event(); mine = True
        else:
            mine = False
    if not mine:
        ev.wait(600)
        return _cache.get(k, r)
    try:
        s = sections(path, ffmpeg, THREADS if bg else FULL, cache_dir or os.path.join(ROOT, 'studio', 'tmp', 'cutpoints'), bg)
        r = dict(r)
        if s is None:  # 没装 / 出错：先不记“补过”，过一阵再试
            r['sec_try'] = time.time()
        else:
            r['sec_v'] = 1
        if s and s.get('act'):
            act, fps = np.asarray(s['act'], np.float32), s.get('fps') or 50
            mx = float(act.max()) if act.size else 0
            pts = []
            for p in r.get('points') or []:
                i = int(round(p['t'] * fps)); w = int(0.15 * fps)
                v = float(act[max(0, i - w):i + w + 1].max()) if act.size else 0.0
                p = {**p, 'sec': round(v, 4)}
                if v >= 0.03 and mx and v >= 0.5 * mx and '音乐段落切换处' not in p['why']:
                    p['why'] = p['why'] + ['音乐段落切换处']
                pts.append(p)
            r['points'], r['sections'], r['sec_by'] = pts, s.get('sections') or [], 'allin1'
        with _lock:
            _cache[k] = r
        if cache_dir:
            try:
                with open(os.path.join(cache_dir, k + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False)
            except OSError:
                pass
        return r
    finally:
        with _lock:
            _sec_busy.pop(k, None)
        ev.set()


def analyze(path, ffmpeg, probe, cache_dir=None, bg=False, studio_idle=None):
    """→ _analyze 的结果，再补上音乐段落（sections / 每个点的 sec）"""
    return _add_sec(_analyze(path, ffmpeg, probe, cache_dir, bg, studio_idle), path, ffmpeg, cache_dir, bg)


def cached(path, cache_dir=None):
    """只取算好的结果（不算）：记录选段时用"""
    k = f'{_key(path)}v{VER}'
    with _lock:
        if k in _cache:
            return _cache[k]
    cf = os.path.join(cache_dir, k + '.json') if cache_dir else None
    if cf and os.path.isfile(cf):
        try:
            with open(cf, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return None
