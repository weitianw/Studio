"""批量配方（2026-11-14 用户要求）：选好一批视频 + 一个配方（一整套设置），后台自己跑完：分段 → 生成 → 质检 → 不过就换种子重做 → 挑最好的 → 拼回原视频 → 推送到手机。
你只在最后看每个视频的最终版（通过 / 重做 / 换一版）。和 HandBrake 的“预设 + 队列”是一个意思；Agent（agentapi / agent_mcp）也调用这里，不另起一套。

- 配方：内置几套（只读）+ 自己存的（每个空间各一份：outputs/batch-recipes.json、.data/batch-recipes.json）。
- 一次批量 = 一个 json（outputs/batches/、.data/batches/）：视频、每段的每一次尝试（任务号、种子、质检数字、分数）、选中的那次、拼接结果。
  Studio 重启后接着跑（已经交给视频引擎的那一单按视频库里的成品认回来；认不回来的重新做）。
- 一个后台线程按顺序推进；生成排进视频队列（和网页上点“生成”一样的设置），质检在 CPU 上做，和下一段的生成同时进行。"""
import json, os, random, threading, time, uuid

_ctx = {}
_lock = threading.RLock()
_wake = threading.Event()
PASS = {'face_sim': 0.75, 'face_dL': 6.0, 'bg_dL': 6.0, 'drift': 0.06}  # 改衣过线（11-13 实测：好的 Viggle 脸 0.80–0.84、亮度差约 −3；H3 精简约 −15）
BUILTIN = [  # 一套内置的（应用默认）：更换衣服默认参考生成（Viggle 重拍在配方里选）；别的都是自己另存的
    {'id': 'default', 'name': '默认', 'builtin': True, 'instruction': '', 'viggle': None, 'size': '720p', 'segs': 'recommend', 'retry': 2, 'splice': True},
]
KEYS = ('name', 'instruction', 'viggle', 'size', 'segs', 'retry', 'splice')


def setup(**kw):
    """server.py 给：submit(body, sp)、set_space(sp)、videogen、cutpoints_for(path, sp)、mats_path、notify(title, body, url)、act、dirs(sp) → (配方文件, 批量文件夹)"""
    _ctx.update(kw)
    if not _ctx.get('_th'):
        _ctx['_th'] = threading.Thread(target=_runner, daemon=True)
        _ctx['_th'].start()


# ------------------------------------------------------------------ 配方
def _clean_recipe(r):
    r = {k: r.get(k) for k in KEYS}
    r['name'] = str(r.get('name') or '我的配方').strip()[:40]
    r['instruction'] = str(r.get('instruction') or '').strip()[:2000]
    r['viggle'] = r['viggle'] if r.get('viggle') in (True, False) else None
    r['size'] = r['size'] if r.get('size') in ('480p', '720p') else '720p'
    r['segs'] = r['segs'] if r.get('segs') in ('recommend', 'whole') else 'recommend'
    r['retry'] = max(0, min(3, int(r.get('retry') if isinstance(r.get('retry'), (int, float)) else 2)))
    r['splice'] = r.get('splice') is not False
    return r


def _rj(p, d):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _wj(p, v):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + f'.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(v, f, ensure_ascii=False)
    os.replace(tmp, p)


def recipes(sp):
    mine = [x for x in _rj(_ctx['dirs'](sp)[0], []) if isinstance(x, dict) and x.get('id')]
    return [dict(x) for x in BUILTIN] + mine


def recipe_get(sp, rid):
    return next((x for x in recipes(sp) if x.get('id') == rid), None)


def recipe_save(sp, r):
    fn = _ctx['dirs'](sp)[0]
    with _lock:
        mine = [x for x in _rj(fn, []) if isinstance(x, dict) and x.get('id')]
        rid = str(r.get('id') or '')
        if any(b['id'] == rid for b in BUILTIN) or not rid:
            rid = 'r' + uuid.uuid4().hex[:8]  # 内置的另存为一份新的
        x = {'id': rid, **_clean_recipe(r)}
        mine = [y for y in mine if y['id'] != rid] + [x]
        _wj(fn, mine[-50:])
    return x


def recipe_delete(sp, rid):
    fn = _ctx['dirs'](sp)[0]
    with _lock:
        _wj(fn, [x for x in _rj(fn, []) if isinstance(x, dict) and x.get('id') != rid])


# ------------------------------------------------------------------ 一次批量
def _path(sp, bid):
    return os.path.join(_ctx['dirs'](sp)[1], bid + '.json')


def _all_ids(sp):
    d = _ctx['dirs'](sp)[1]
    return sorted((f[:-5] for f in os.listdir(d) if f.endswith('.json')), reverse=True) if os.path.isdir(d) else []


def _ok_id(bid):
    return bool(bid) and len(bid) < 64 and all(c.isascii() and (c.isalnum() or c == '-') for c in bid)


def get(sp, bid):
    return _rj(_path(sp, bid), None) if _ok_id(bid) else None


def _put(sp, b):
    b['updated'] = time.time()
    _wj(_path(sp, b['id']), b)


def listing(sp, limit=30, offset=0):
    """批量列表：正在跑的（不管多早开的）都在前面，后面是按时间倒序的历史（分页）。
    2026-11-17 审查 F10：以前只给最新 30 条，更早开的还在跑的那次看不到"""
    act_ids = [bid for bid in sorted(active_ids(sp), reverse=True)]
    out, seen = [], set()
    for bid in act_ids:
        b = get(sp, bid)
        if b and b.get('state') == 'running':
            out.append(b); seen.add(bid)
    hist = [bid for bid in _all_ids(sp) if bid not in seen]
    for bid in hist[offset:offset + limit]:
        b = get(sp, bid)
        if b:
            out.append(b)
    return out


# 正在跑的批量（每个空间一份，只在内存里）：启动后第一次用时扫一遍全部记录建起来，之后开新的 / 重做 / 换版时加进来、做完时拿掉。
# runner 只推进这里面的，不再每 8 秒读最新 300 份（F10 / P03：以前更早开的永远不推进，还要读几百个文件）
_active = {}


def active_ids(sp):
    with _lock:
        if sp not in _active:
            ids = set()
            for bid in _all_ids(sp):
                b = get(sp, bid)
                if b and b.get('state') == 'running':
                    ids.add(bid)
            _active[sp] = ids
        return set(_active[sp])


def _mark_active(sp, bid, on=True):
    with _lock:
        if sp not in _active:
            active_ids(sp)
        (_active[sp].add if on else _active[sp].discard)(bid)


def create(sp, recipe, items, instruction=None):
    """recipe：配方 id 或者整套设置；items：[{video: {mats: 相对路径} / {gallery: id}, label, dur, segs: [[a, b], …] 可选}]"""
    r = recipe_get(sp, recipe) if isinstance(recipe, str) else recipe
    if not isinstance(r, dict):
        raise ValueError('没有这个配方')
    r = {'id': r.get('id'), **_clean_recipe(r)}
    if instruction is not None and str(instruction).strip():
        r['instruction'] = str(instruction).strip()[:2000]
    if not r['instruction']:
        raise ValueError('更换衣服要写清楚换成什么衣服')
    its = []
    for it in items or []:
        v = it.get('video') if isinstance(it.get('video'), dict) else {}
        ref = {'mats': str(v['mats'])} if v.get('mats') else {'gallery': str(v['gallery'])} if v.get('gallery') else None
        if not ref:
            continue
        segs = _cap([[round(float(a), 3), round(float(c), 3)] for a, c in (it.get('segs') or []) if float(c) - float(a) >= 0.5], r) or None
        its.append({'video': ref, 'label': str(it.get('label') or '')[:120], 'dur': float(it.get('dur') or 0) or None, 'segs': None if segs is None else [{'a': a, 'b': c, 'tries': [], 'best': None, 'state': 'wait'} for a, c in segs],
                    'state': 'wait', 'splice': None, 'error': ''})
    if not its:
        raise ValueError('请先添加视频')
    b = {'id': time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4], 'space': sp, 'created': time.time(), 'recipe': r, 'items': its, 'state': 'running', 'note': ''}
    _put(sp, b)
    _mark_active(sp, b['id'])
    _ctx['act'](f'批量：开始「{r["name"]}」，{len(its)} 个视频', 'video')
    _wake.set()
    return b


BUSY = [0]  # runner 正在推进（找换装点 / 质检 / 拼接）：重启前的忙碌检查要算上
_cancel_req = set()  # 取消时 runner 正在推进这一条：先记下，runner 存盘前照着取消
_claimed = set()     # runner 正在处理（锁外）的批量 (sp, bid)
_ops = {}            # 这期间用户的重做 / 换版：(sp, bid) → [函数(b)]，runner 提交前按顺序应用


def _change(sp, bid, fn):
    """改一条批量：runner 没在处理就直接改；正在处理就排队（它提交前应用），返回改完的样子"""
    with _lock:
        b = get(sp, bid)
        if not b:
            raise ValueError('没有这次批量')
        fn(b)  # 先在副本上试一遍：参数不对在这里就报错
        if (sp, bid) in _claimed:
            _ops.setdefault((sp, bid), []).append(fn)
        else:
            _put(sp, b)
        if b.get('state') == 'running':
            _mark_active(sp, bid)
    _wake.set()
    return b


def _apply_cancel(b):
    vg = _ctx['videogen']
    for it in b['items']:
        for s in it.get('segs') or []:
            for t in s['tries']:
                j = vg.jobs.get(t.get('job'))
                if j and j.get('state') in ('queued', 'running'):
                    j['cancel'] = True
            if s['state'] in ('wait', 'run'):
                s['state'] = 'cancelled'
        if it['state'] not in ('done', 'partial', 'fail'):
            it['state'] = 'cancelled'
    b['state'] = 'cancelled'
    return b


def cancel(sp, bid):
    with _lock:  # 锁只在领取 / 提交时被 runner 拿着，这里不会等几十秒
        b = get(sp, bid)
        if not b:
            raise ValueError('没有这次批量')
        _apply_cancel(b)  # 视频任务现在就停
        if (sp, bid) in _claimed:  # runner 正在处理这条：记下，它提交前照着取消
            _cancel_req.add((sp, bid))
        else:
            _put(sp, b)
        _mark_active(sp, bid, False)
        return b


def delete(sp, bid):
    if not _ok_id(bid):  # 编号不对就不删（以前拿不到记录照样拼路径删：../ 能删到项目里的文件，2026-11-16 审查）
        raise ValueError('没有这次批量')
    b = get(sp, bid)
    if b and b['state'] == 'running':
        raise ValueError('还在跑：先停下再删除这条记录（做好的视频在视频库里，不会删）')
    try:
        os.remove(_path(sp, bid))
    except OSError:
        pass


def redo(sp, bid, i, k):
    """审片时“重做”：这一段再做一次（同样的设置，新种子），做完重新挑最好的（缺的段也这样补）"""
    i, k = int(i), int(k)

    def fn(b):
        s = b['items'][i]['segs'][k]
        s['state'], s['extra'] = 'wait', int(s.get('extra') or 0) + 1
        b['items'][i]['state'], b['items'][i]['splice'] = 'run', None
        b['state'] = 'running'
    return _change(sp, bid, fn)


def pick(sp, bid, i, k, t):
    """审片时换一版：这一段用第 t 次尝试的结果，重新拼接"""
    i, k, t = int(i), int(k), int(t)

    def fn(b):
        s = b['items'][i]['segs'][k]
        if not (0 <= t < len(s['tries'])) or not s['tries'][t].get('result'):
            raise ValueError('这一次没有成品')
        s['best'] = t
        it = b['items'][i]
        it['splice'] = None
        if it['state'] in ('done', 'partial', 'cancelled', 'fail'):  # 取消过的视频换了一版也要重新拼（以前推进器跳过它，选了等于没选，审查 18）
            it['state'] = 'run'
        b['state'] = 'running'
    return _change(sp, bid, fn)


# ------------------------------------------------------------------ 推进
def outfit_body(ref, a, c, r, seed, dur):
    """和网页上点“生成”一样的改衣设置（应用默认：参考生成 + 动作跟随 + 720p 加速 8 步；配方里可选 Viggle 重拍）"""
    import videoedit
    vg = _ctx['videogen']
    vgs = bool(r.get('viggle')) and videoedit.vg_ok()
    turbo = None
    if r['size'] == '720p' and not vgs:
        turbo = next((t['file'] for t in vg.turbo_list() or [] if t.get('kind') == 'ref2v' and t.get('steps') == 8 and t.get('hd')), None)
    end = round(min(c, dur or c), 3)
    edit = {'task': 'outfit', 'swap_by': 'v11', 'target': '', 'audio': 'keep', 'start': round(a, 3), 'end': end, 'follow': False,
            'base': 'lite', 'tpl': True, 'method': 'ref', 'own': False, 'splice': True, 'plang': 'zh', 'ffguide': False,
            'pose': not vgs, 'emph': True, 'vg': vgs, 'locon': False, 'head_by': 'fs'}
    return {'model': 'h3', 'edit': edit, 'video': dict(ref), 'prompt': r['instruction'], 'prompt_input': r['instruction'], 'seconds': round(end - a, 3), 'size': r['size'], 'res': '',
            'seed': seed, 'engine': 'auto', 'interp': False, 'interp_x': 1, 'interp_by': 'rife', 'upscale': False, 'loras': [], **({'turbo': {'ref2v': turbo}} if turbo else {})}, vgs


def seg_max(r):
    """每段最多几秒：Viggle 14 秒、H3 150 秒（引擎会把更长的截短）"""
    return 14.0 if r.get('viggle') else 150.0


def _cap(segs, r):
    """超过上限的段切成几段（以前只截掉尾巴，超出的部分没改却算做好；2026-11-16 起手动给的段、Agent 改衣也走这里）"""
    mx = seg_max(r)
    return [[round(a + k * mx, 3), round(min(c, a + (k + 1) * mx), 3)] for a, c in segs for k in range(max(1, -(-int((c - a) * 1000) // int(mx * 1000))))]


def score(m, flags):
    """质检分数（越大越好）：脸像不像 − 亮度差 − 动作差 − 报出的问题"""
    m = m or {}
    fs = m.get('face_sim')  # 0 也是真实的分数（以前 `or 0.6` 把 0 当成 0.6）
    return round((0.6 if fs is None else fs) - abs(m.get('face_dL') or 0) / 20 - abs(m.get('bg_dL') or 0) / 30 - (m.get('drift') or 0) * 2 - 0.2 * len(flags or []), 4)


def judge(m, flags, task='outfit'):
    m = m or {}
    why = [f['msg'] for f in flags or []]
    if not any(m.get(k) is not None for k in PASS):  # 质检出错 / 跳过 / 没量出数字：不能当成通过（以前空结果 = 没问题 = 通过，2026-11-16 审查）
        why.append(f"质检没有结果（{m.get('skip')}）" if m.get('skip') else '质检没有结果')
    if task == 'outfit' and m.get('face_sim') is not None and m['face_sim'] < PASS['face_sim']:
        why.append(f"脸和原视频不够像（{m['face_sim']}，要 ≥ {PASS['face_sim']}）")
    for k, n in (('face_dL', '脸'), ('bg_dL', '背景')):
        if m.get(k) is not None and abs(m[k]) > PASS[k]:
            why.append(f"{n}亮度和原视频差 {m[k]}（要在 ±{PASS[k]} 以内）")
    if m.get('drift') is not None and m['drift'] > PASS['drift']:
        why.append(f"动作和原视频差 {m['drift']}（要 ≤ {PASS['drift']}）")
    return list(dict.fromkeys(why))


def _path_of(sp, ref):
    vg = _ctx['videogen']
    if ref.get('mats'):
        return _ctx['mats_path'](ref['mats'])
    x = vg.gallery_get(ref['gallery'], sp)
    return vg.vfile(sp, x['file']) if x else None


def _step(sp, b):
    """推进一次批量：返回 True = 有改动"""
    vg, r, ch = _ctx['videogen'], b['recipe'], False
    gal = None
    for i, it in enumerate(b['items']):
        if it['state'] in ('done', 'partial', 'fail', 'cancelled'):
            continue
        path = _path_of(sp, it['video'])
        if not path or not os.path.isfile(path):
            it['state'], it['error'] = 'fail', '找不到这个视频了'; ch = True; continue
        if it.get('dur') is None:
            it['dur'] = round(float((vg._probe(path, exact=False) or {}).get('duration') or 0), 3)  # 只要时长：轻量探测（P04）; ch = True
        if it['segs'] is None:  # 推荐分段 / 整段
            it['state'] = 'run'
            if r['segs'] == 'whole':
                segs = [[0.0, it['dur']]]
            else:
                try:
                    segs = _ctx['split_for'](path, sp, it['dur'])
                except Exception as e:
                    segs, it['error'] = [], f'找换装点失败：{e}'[:200]
                segs = segs or [[0.0, it['dur']]]
            segs = _cap(segs, r)
            it['segs'] = [{'a': a, 'b': c, 'tries': [], 'best': None, 'state': 'wait'} for a, c in segs]
            ch = True
            return True  # 找换装点会花些时间：存一下再接着走
        it['state'] = 'run'
        for k, s in enumerate(it['segs']):
            if s['state'] in ('done', 'fail', 'cancelled'):
                continue
            if s['state'] == 'wait':  # 交给视频队列
                seed = random.randrange(1, 2 ** 31)
                body, vgs = outfit_body(it['video'], s['a'], s['b'], r, seed, it['dur'])
                try:
                    j = _ctx['submit'](body, sp)
                except Exception as e:
                    j = {'error': str(e)}
                if not j or not j.get('id'):
                    s['tries'].append({'job': None, 'seed': seed, 'state': 'error', 'error': str((j or {}).get('error') or '提交失败')[:200]})
                    _next(s, r)  # 和“没过质检”一样：还能重做就再排，不能就挑已有成品里最好的（以前直接判失败，把做好的片扔掉）
                else:
                    s['tries'].append({'job': j['id'], 'seed': seed, 'state': 'run', 'viggle': vgs}); s['state'] = 'run'
                ch = True
                continue
            t = s['tries'][-1]  # 正在做的那一次
            j = vg.jobs.get(t['job'])
            st = j.get('state') if j else None
            if st in ('queued', 'running'):
                continue
            gal = gal if gal is not None else {x.get('job'): x for x in vg.gallery(sp) if x.get('job')}
            x = gal.get(t['job'])
            if x is None and st == 'done':
                gal = {x_.get('job'): x_ for x_ in vg.gallery(sp) if x_.get('job')}; x = gal.get(t['job'])
            if x is None:  # 失败 / 取消 / Studio 重启后找不回来
                if st == 'cancelled' or b['state'] == 'cancelled':
                    t['state'], s['state'] = 'cancelled', 'cancelled'
                else:
                    t['state'], t['error'] = 'error', str((j or {}).get('error') or '没有成品（可能 Studio 重启过）')[:200]
                    _next(s, r)
                ch = True
                continue
            q = vg.qc_run(sp, x['id']) or {}  # CPU 上做（10~30 秒），这时视频引擎已经在做下一单
            m, fl = q.get('m') or {}, q.get('flags') or []
            why = judge(m, fl)
            t.update(state='done', result=x['id'], file=x.get('file'), qc=m, flags=[f['msg'] for f in fl], why=why, score=score(m, fl), ok=not why)
            if not why:
                s['best'], s['state'] = len(s['tries']) - 1, 'done'
            else:
                _next(s, r)
            ch = True
        if all(s['state'] in ('done', 'fail', 'cancelled') for s in it['segs']):
            good = [s for s in it['segs'] if s.get('best') is not None]
            if r['splice'] and good and it['splice'] is None:
                ids = [s['tries'][s['best']]['result'] for s in sorted(good, key=lambda s: s['a'])]
                try:
                    x = vg.splice(ids[0], sp, ids[1:])
                    it['splice'] = {'state': 'done', 'id': (x or {}).get('id'), 'file': (x or {}).get('file')}
                except Exception as e:
                    it['splice'] = {'state': 'error', 'error': str(e)[:200]}
            it['state'] = item_outcome(it)['state']  # 缺段 / 拼接失败 → partial（以前只要有一段成了就算“做好”）
            ch = True
    if b['state'] == 'running' and all(it['state'] in ('done', 'partial', 'fail', 'cancelled') for it in b['items']):
        b['state'] = 'done'
        sm = summary(b)
        b['note'], b['counts'] = sm['text'], sm['counts']
        _ctx['act'](f'批量「{r["name"]}」做完：{b["note"]}' if sp != 'v' else '批量做完了', 'video')
        try:
            t, body = push_text(sp, sm)
            _ctx['notify'](t, body, '/batch')
        except Exception:
            pass
        ch = True
    return ch


def _fmt_s(x):
    x = float(x or 0)
    return f'{int(x // 60)}:{x % 60:04.1f}' if x >= 60 else f'{x:.1f} 秒'


def item_outcome(it):
    """一个视频的结果（2026-11-17 审查 F02）：生成失败、质检没过、拼接失败分开算；缺了哪段写清楚。
    state：done = 每段都有成品（拼接也成了）；partial = 有成品但缺段 / 拼接失败（做好的保留，缺的段可以重做）；fail = 一段成品都没有"""
    segs = it.get('segs') or []
    gen_fail = [s for s in segs if s.get('best') is None and s['state'] in ('fail', 'cancelled')]  # 取消掉、没出成品的段也算缺（审查 18）
    good = [s for s in segs if s.get('best') is not None]
    qc_fail = [s for s in good if not s['tries'][s['best']].get('ok')]
    splice_err = (it.get('splice') or {}).get('state') == 'error'
    if it.get('state') == 'cancelled':
        st = 'cancelled'
    elif not good:
        st = 'fail'
    elif gen_fail or splice_err:
        st = 'partial'
    else:
        st = 'done'
    return {'state': st, 'segs': len(segs), 'pass': len(good) - len(qc_fail), 'qc_fail': len(qc_fail), 'gen_fail': len(gen_fail),
            'missing': [[s['a'], s['b']] for s in gen_fail], 'splice_error': splice_err}


def summary(b):
    """一次批量的计数和一句话：网页、Agent、推送都用这一份"""
    outs = [item_outcome(it) for it in b['items']]
    c = {'videos': len(outs), 'complete': sum(o['state'] == 'done' for o in outs), 'partial': sum(o['state'] == 'partial' for o in outs),
         'failed': sum(o['state'] == 'fail' for o in outs), 'cancelled': sum(o['state'] == 'cancelled' for o in outs),
         'splice_failed': sum(o['splice_error'] for o in outs), 'segments': sum(o['segs'] for o in outs), 'seg_pass': sum(o['pass'] for o in outs),
         'seg_qc_fail': sum(o['qc_fail'] for o in outs), 'seg_gen_fail': sum(o['gen_fail'] for o in outs)}
    miss = [f"第 {i + 1} 个缺 " + '、'.join(f'{_fmt_s(a)}–{_fmt_s(z)}' for a, z in o['missing']) for i, o in enumerate(outs) if o['missing']]
    t = f"{c['complete']}/{c['videos']} 个视频完整做好"
    if c['partial']:
        t += f"，{c['partial']} 个不完整（做好的部分已保留）"
    if c['failed']:
        t += f"，{c['failed']} 个没做出来"
    t += f"；{c['seg_pass']}/{c['segments']} 段质检通过"
    if c['seg_qc_fail']:
        t += f"，{c['seg_qc_fail']} 段没过质检（用了分数最高的一版）"
    if c['seg_gen_fail']:
        t += f"，{c['seg_gen_fail']} 段生成失败（可重做）"
    if c['splice_failed']:
        t += f"，{c['splice_failed']} 个拼接失败"
    if miss:
        t += '。' + '；'.join(miss)
    return {'counts': c, 'text': t, 'items': outs}


def push_text(sp, sm):
    """推送的标题和正文。私密空间和别的任务一样：不说是什么、不报数字（F21；以前批量通知会带上视频数 / 段数 / 质检数）"""
    c = sm['counts']
    if sp == 'v':
        return 'Studio', ('有任务失败' if not c['complete'] and not c['partial'] else '有任务已完成')
    title = '批量做完了' if c['complete'] == c['videos'] else '批量做完了（有缺的）'
    return title, sm['text']


def _next(s, r):
    """这一次没过：还能重做就再排一次，不能就挑分数最好的那次（都没成品就算失败）"""
    if len(s['tries']) < 1 + r['retry'] + int(s.get('extra') or 0):
        s['state'] = 'wait'
        return
    done = [(t.get('score') if t.get('score') is not None else -9, n) for n, t in enumerate(s['tries']) if t.get('result')]
    if done:
        s['best'], s['state'] = max(done)[1], 'done'
    else:
        s['state'] = 'fail'


def _runner():
    while True:
        _wake.wait(8); _wake.clear()
        for sp in ('n', 'v'):
            try:
                ids = sorted(active_ids(sp))
            except Exception:
                continue
            for bid in ids:
                try:
                    tick(sp, bid)
                except Exception as e:  # 写盘失败（权限、文件被占用）等：记一笔，下一轮再试；以前异常逃出来，后台线程就停了，所有批量都不再推进（审查 6）
                    try:
                        _ctx['act'](f'批量推进出错（稍后重试）：{e}', 'video', 'warn')
                    except Exception:
                        pass


def tick(sp, bid):
    """推进一条：锁内领取 → 锁外处理（质检 / 拼接 / 通知可能几十秒，不挡别的批量和用户操作）→ 锁内提交（应用这期间的取消 / 重做 / 换版）"""
    key = (sp, bid)
    with _lock:
        b = get(sp, bid)
        if not b or b.get('state') != 'running':
            _mark_active(sp, bid, False)
            return False
        _claimed.add(key)
    ch, err = False, None
    try:
        _ctx['set_space'](sp)
        BUSY[0] += 1
        try:
            ch = _step(sp, b)
        finally:
            BUSY[0] -= 1
    except Exception as e:
        err = e
    with _lock:
        try:
            ops = list(_ops.get(key, []))  # 处理期间用户点的重做 / 换版：写盘成功之后才从待办里拿掉（第二轮审查 5：以前先拿掉，写盘失败就丢了）
            for fn in ops:
                try:
                    fn(b); ch = True
                except Exception:
                    pass
            cancel = key in _cancel_req
            if cancel:
                _apply_cancel(b); ch = True
            if err is not None:
                b['note'] = f'出错：{err}'[:200]; ch = True
                _ctx['act'](f'批量出错：{err}', 'video', 'warn')
            if ch:
                _put(sp, b)  # 写盘失败会抛出去：待办和取消都还在，下一轮从磁盘重新读、再应用一次
            left = [x for x in _ops.get(key, []) if x not in ops]
            if left:
                _ops[key] = left
            else:
                _ops.pop(key, None)
            if cancel:
                _cancel_req.discard(key)
            if b.get('state') != 'running':
                _mark_active(sp, bid, False)
        finally:
            _claimed.discard(key)
    return ch
