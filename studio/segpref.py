"""推荐分段 + 按用户自己的选段学偏好（2026-11-14 用户：推荐分段要贴近个人偏好，数据不能给大模型看）。

做法照 PHD-GIFs（Garcia del Molino & Gygli, ACM MM 2018，“按用户以前选过什么来推荐片段”）：
- 每次用户带着选段提交改视频，记下这段视频每个候选点的特征（卡点 / 定格 / 大动作 / 转身、在不在拍上、重拍、音乐段落切换……）
  和用户最后选的段落（segpref.jsonl，按空间分开；只有数字，没有文件名和画面）。
- 学：每个候选点“有没有被当成段落的开头 / 结尾”做二分类（逻辑回归，本地几毫秒），再用同一套动态规划挑段落；
  段落长度的偏好也按用户选过的段落长度来定。
- 只有在留一法验证（每次留出一个视频、用别的学）里比手写规则更贴近用户的选段时才用学出来的；不够 6 个视频、或者没更好，就用手写规则。
split() 和网页以前的 veCpSplit 是同一套规则（2026-11-10 定的），现在只在这里算。"""
import json, math, os, threading, time
import numpy as np

KINDS = ('beat', 'hit', 'swing', 'turn')
MIN_VIDEOS = 6        # 至少这么多个视频的选段才开始学
MARGIN = 0.03         # 学出来的要比规则至少好这么多（时间重合度）才换
TOL = 0.2             # 段落边界离候选点这么近算“选了这个点”
_lock = threading.Lock()
_model = {}           # 每个文件一份：{'mtime', 'm'}


# ------------------------------------------------------------------ 分段（规则，和以前网页上的一样）
def _rule_scores(pts):
    return [p['score'] + (0.1 if p.get('sync') else 0) + (0.35 if p.get('db') else 0) for p in pts]


def split(cp, dur=None, model=None):
    """cp = cutpoints.analyze 的结果 → [[开始, 结束], …]（结尾等于视频长度 = 换到结尾）；model 给了就用学出来的分数和段落长度"""
    d = float(dur or cp.get('dur') or 0)
    P0 = [p for p in cp.get('points') or [] if 0.5 <= p['t'] <= d - 0.3]
    S = model_scores(model, P0, d) if model else _rule_scores(P0)
    P = [{'t': p['t'], 's': s} for p, s in zip(P0, S)]
    if d > 3:
        P.append({'t': d, 's': (model or {}).get('end_s', 1.3), 'end': True})  # 换到视频结尾：只有开头一个接缝
    L0 = (model or {}).get('len', 4.5); lo, hi = (model or {}).get('lo', 2.5), (model or {}).get('hi', 8.0)
    C = []
    for a in P:
        if a.get('end'):
            continue
        for b in P:
            L = b['t'] - a['t']
            if lo <= L <= hi:
                C.append((a['t'], b['t'], a['s'] + b['s'] + 0.4 * (1 - min(1, abs(L - L0) / 3))))
    per = (model or {}).get('per', 5.0)
    N = max(1, min(6, round(d / per)))
    C.sort(key=lambda c: c[0])
    n = len(C)
    if not n:
        return []
    f = [[c[2] for c in C]]; bk = [[-1] * n]
    for k in range(1, N):
        fk, bkk = [], []
        for i, c in enumerate(C):
            best, bi = -math.inf, -1
            for j in range(n):
                if C[j][1] + 1.2 <= c[0] and f[k - 1][j] > best:
                    best, bi = f[k - 1][j], j
            fk.append(-math.inf if bi < 0 else best + c[2]); bkk.append(bi)
        f.append(fk); bk.append(bkk)
    for k in range(N - 1, -1, -1):  # 放不下 N 段时少分几段
        i = max(range(n), key=lambda j: f[k][j])
        if not math.isfinite(f[k][i]):
            continue
        pick = []
        q = k
        while q >= 0 and i >= 0:
            pick.insert(0, C[i]); i = bk[q][i]; q -= 1
        return [[round(a, 3), round(min(d, b), 3)] for a, b, _ in pick]
    return []


# ------------------------------------------------------------------ 特征 / 记录
def feat(p, d):
    why = ' '.join(p.get('why') or [])
    sec = float(p.get('sec') or 0)
    return [1.0, float(p.get('score') or 0), 1.0 if p.get('sync') else 0.0, 1.0 if p.get('db') else 0.0,
            *[1.0 if p.get('kind') == k else 0.0 for k in KINDS],
            1.0 if '段落变化' in why else 0.0, min(1.0, sec / 0.05), 1.0 if p.get('also') else 0.0,
            min(1.0, p['t'] / max(d, 1e-6))]


def record(fn, cp, segs, rec=None, extra=None):
    """一次提交 = 一行：视频指纹、时长、候选点（只有数字和类别）、用户选的段落、当时推荐的段落"""
    d = float(cp.get('dur') or 0)
    segs = [[round(float(a), 3), round(float(b), 3)] for a, b in segs if b - a > 0.3]
    if not segs or not d or (len(segs) == 1 and segs[0][0] < 0.3 and segs[0][1] > d - 0.3):  # 整段都改：不是在挑换装点
        return False
    row = {'ts': round(time.time()), 'key': cp.get('_key'), 'dur': round(d, 3), 'segs': segs, 'rec': rec or None,
           'points': [{k: p[k] for k in ('t', 'kind', 'score', 'sync', 'db', 'also', 'sec') if k in p} | {'why': [w for w in p.get('why') or [] if '段落变化' in w][:1]} for p in cp.get('points') or []],
           **(extra or {})}
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    with _lock:
        rows = _read(fn)
        rows = [r for r in rows if not (row['key'] and r.get('key') == row['key'] and r.get('segs') == segs)]  # 同一视频同样的选段只记一次（生成几个版本时会提交几次）
        rows.append(row)
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows[-500:]))
        _model.pop(fn, None)
    return True


def _read(fn):
    try:
        with open(fn, encoding='utf-8') as f:
            return [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return []


def _latest(rows):
    """同一个视频只用最后一次的选段（改了主意以最后为准）"""
    by = {}
    for r in rows:
        by[r.get('key') or id(r)] = r
    return list(by.values())


# ------------------------------------------------------------------ 学
def _labels(r):
    d = r['dur']; bounds = []
    for a, b in r['segs']:
        bounds.append(a)
        if b < d - 0.3:
            bounds.append(b)
    pts = [p for p in r['points'] if 0.5 <= p['t'] <= d - 0.3]
    return pts, [1.0 if any(abs(p['t'] - x) <= TOL for x in bounds) else 0.0 for p in pts]


def _fit(rows, l2=1.0, it=400):
    X, Y = [], []
    for r in rows:
        pts, y = _labels(r)
        X += [feat(p, r['dur']) for p in pts]; Y += y
    if not X or sum(Y) < 3:
        return None
    X, Y = np.asarray(X), np.asarray(Y)
    w = np.zeros(X.shape[1]); pos = Y.mean()
    sw = np.where(Y > 0, 0.5 / max(pos, 1e-3), 0.5 / max(1 - pos, 1e-3))  # 选中的点很少：两类各占一半的权重
    for _ in range(it):  # 牛顿法（特征只有十几个）
        z = 1 / (1 + np.exp(-X @ w)); g = X.T @ (sw * (z - Y)) + l2 * np.r_[0, w[1:]]
        H = (X * (sw * z * (1 - z))[:, None]).T @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(H + 1e-6 * np.eye(len(w)), g); w -= step
        if np.abs(step).max() < 1e-6:
            break
    lens = [b - a for r in rows for a, b in r['segs'] if b < r['dur'] - 0.3 or a > 0.3]
    ends = [1.0 if r['segs'][-1][1] >= r['dur'] - 0.3 else 0.0 for r in rows]
    L = float(np.median(lens)) if len(lens) >= 4 else 4.5
    gaps = [r['dur'] / max(1, len(r['segs'])) for r in rows]
    return {'w': [round(float(v), 4) for v in w], 'len': round(min(8.0, max(2.5, L)), 2), 'lo': round(max(1.5, min(2.5, L * 0.5)), 2), 'hi': round(max(8.0, L * 1.6), 2),
            'per': round(float(np.median(gaps)), 2) if gaps else 5.0, 'end_s': round(0.6 + 1.2 * float(np.mean(ends)), 2)}


def model_scores(m, pts, d):
    w = np.asarray(m['w'])
    return [float(1.8 / (1 + math.exp(-float(np.dot(w, feat(p, d)))))) for p in pts]


def overlap(a, b, d):
    """两组段落在时间上的重合度（交集 / 并集）"""
    def mask(s):
        x = np.zeros(int(d * 20) + 2, bool)
        for u, v in s:
            x[int(u * 20):int(v * 20)] = True
        return x
    A, B = mask(a), mask(b)
    un = (A | B).sum()
    return float((A & B).sum() / un) if un else 1.0


def status(fn):
    """→ {'videos', 'use', 'rule', 'learned', 'model'}：留一法比较规则和学出来的（结果按文件修改时间缓存）"""
    try:
        mt = os.path.getmtime(fn)
    except OSError:
        return {'videos': 0, 'use': 'rule', 'need': MIN_VIDEOS}
    with _lock:
        c = _model.get(fn)
        if c and c['mtime'] == mt:
            return c['m']
    rows = [r for r in _latest(_read(fn)) if r.get('points') and r.get('segs')][-200:]  # 学最近 200 个视频；验证最近 40 个（记录多了也只要一两秒）
    out = {'videos': len(rows), 'use': 'rule', 'need': MIN_VIDEOS}
    if len(rows) >= MIN_VIDEOS:
        ro, lo = [], []
        for i in range(max(0, len(rows) - 40), len(rows)):
            r = rows[i]
            m = _fit(rows[:i] + rows[i + 1:])
            cp = {'dur': r['dur'], 'points': r['points']}
            ro.append(overlap(split(cp), r['segs'], r['dur']))
            lo.append(overlap(split(cp, model=m), r['segs'], r['dur']) if m else ro[-1])
        out.update(rule=round(float(np.mean(ro)), 3), learned=round(float(np.mean(lo)), 3))
        m = _fit(rows)
        if m and out['learned'] >= out['rule'] + MARGIN:
            out.update(use='learned', model=m)
    with _lock:
        _model[fn] = {'mtime': mt, 'm': out}
    return out
