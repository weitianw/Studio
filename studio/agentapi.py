"""给 Agent（Claude Code / Codex / DeepSeek…，经 agent_mcp.py 这个 MCP 服务）用的接口：/api/agent/*（2026-11-14 用户要求）。

隐私原则（照 CaMeL / ToolMinimize 的思路：靠技术挡住，不靠嘱咐模型）：
- 只回代号和数字：视频 = v_xxxx（素材库）/ w_xxxx（视频库里的成品），任务 = j_xxxx。代号 = HMAC(本机密钥, 真实名字)，
  反推不出文件名；密钥在 .data/agent.key，只有 Studio 读。
- 不回：文件名、标题、文件夹名、缩略图、画面、提示词全文、看图写的描述。出错信息里的路径 / 文件名 / @账号一律抹掉。
- 只收代号：Agent 给的视频、任务都按代号在本机找回真实的那一个。
- 能做的事只有下面这几个函数（列视频、找换装点、推荐分段、改衣、看进度、质检），每一次都记进 Studio 的活动记录。"""
import hashlib, hmac, os, re, secrets, threading, time

_ctx = {}           # setup() 给的：server 里的函数和目录
_map = {}           # 代号 → ('mats', 相对路径) / ('gallery', id) / ('job', 任务号)
_probe_cache = {}   # (路径, 修改时间) → {dur, w, h, audio}
_lock = threading.Lock()
from batch import PASS  # 质检过线和批量配方同一套（batch.py）


def setup(**kw):
    _ctx.update(kw)


def _key():
    p = _ctx['key_file']
    if not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(secrets.token_bytes(32))
    with open(p, 'rb') as f:
        return f.read()


def handle(kind, real, sp):
    h = hmac.new(_key(), f'{sp}|{kind}|{real}'.encode('utf-8'), hashlib.sha256).hexdigest()[:10]
    k = {'mats': 'v', 'gallery': 'w', 'job': 'j'}[kind] + '_' + h
    with _lock:
        _map[(sp, k)] = (kind, real)
    return k


_SCRUB = [re.compile(r'[A-Za-z]:[\\/][^\s，。；、）)]*'), re.compile(r'[^\s/\\：:，。]*\.(?:mp4|mov|m4v|webm|mkv|avi|png|jpe?g|webp|wav|mp3|json|safetensors|gguf)\b', re.I),
          re.compile(r'@[^\s_，。]+'), re.compile(r'[「“"][^」”"]{1,80}[」”"]')]


def scrub(s, n=160):
    """出错信息 / 进度文字：抹掉路径、文件名、@账号、引号里的名字"""
    s = str(s or '')
    for r in _SCRUB:
        s = r.sub('…', s)
    s = _SLASH.sub(lambda m: m.group(0) if re.fullmatch(r'[\d\s/…]+', m.group(0)) else '…', s)  # 带斜杠的片段（文件夹名）也抹掉；“第 3/6 步”这种留着
    return s[:n]


_SLASH = re.compile(r'[^\s：:，。；、（(「“"]*[/\\][^\s，。；、）)」”"]*')


def _resolve(h, sp, kinds):
    with _lock:
        r = _map.get((sp, h))
    if not r:  # Studio 重启过：重新列一遍就能找回
        if h.startswith('v_'):
            _mats(sp)
        elif h.startswith('w_'):
            _works(sp)
        elif h.startswith('j_'):
            _jobs(sp)
            _gal_jobs(sp)  # 重启前做完的任务：内存里没了，视频库里还记着它的任务号（F11）
        with _lock:
            r = _map.get((sp, h))
    if not r or r[0] not in kinds:
        raise ValueError('没有这个代号（先用 list_videos / job_status 取得代号）')
    return r


def _info(path):
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return {}
    k = (path, mt)
    if k not in _probe_cache:
        pr = _ctx['probe'](path) or {}
        _probe_cache[k] = {'dur': round(float(pr.get('duration') or 0), 2), 'w': pr.get('width') or 0, 'h': pr.get('height') or 0, 'audio': bool(pr.get('audio'))}
    return _probe_cache[k]


def _mats(sp):
    root = os.path.abspath(_ctx['mats_dir']); out = []
    for a, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if not d.startswith(('.', '_')) and not _ctx['mats_hide'](os.path.relpath(os.path.join(a, d), root), sp)]  # 只在私密空间显示的文件夹（server.MATS_PRIVATE）
        for f in fs:
            if os.path.splitext(f)[1].lower() in _ctx['video_ext']:
                p = os.path.join(a, f)
                out.append((os.path.getmtime(p), os.path.relpath(p, root).replace('\\', '/'), p))
    out.sort(reverse=True)
    return [(handle('mats', rel, sp), p, mt) for mt, rel, p in out]


def _works(sp):
    vg = _ctx['videogen']
    return [(handle('gallery', x['id'], sp), x) for x in vg.gallery(sp) if x.get('file')]


def _jobs(sp):
    vg = _ctx['videogen']
    return [(handle('job', j['id'], sp), j) for j in vg.list_jobs(sp)]


def _gal_jobs(sp):
    """视频库（持久记录）里每条成品对应的任务号也登记成代号：Studio 重启后，Agent 手上的旧任务代号照样能查结果、能重做（F11）。
    代号带着空间算，私密空间的任务在普通空间里解析不出来"""
    return [(handle('job', x['job'], sp), x) for x in _ctx['videogen'].gallery(sp) if x.get('job')]


# ------------------------------------------------------------------ 工具
def list_videos(sp, source='materials', limit=50, offset=0):
    limit, offset = max(1, min(200, int(limit or 50))), max(0, int(offset or 0))
    vg = _ctx['videogen']
    if source == 'results':
        items = _works(sp)
        page = items[offset:offset + limit]
        return {'total': len(items), 'videos': [{'id': h, 'kind': 'result', **_info(vg.vfile(sp, x['file'])), 'task': (x.get('edit') or {}).get('task') or 'generate',
                                                 'day': time.strftime('%Y-%m-%d', time.localtime(x.get('created') or 0)), **({'source': handle('gallery', x['src_vid'], sp)} if x.get('src_vid') else {})} for h, x in page]}
    items = _mats(sp)
    page = items[offset:offset + limit]
    return {'total': len(items), 'videos': [{'id': h, 'kind': 'material', **_info(p), 'day': time.strftime('%Y-%m-%d', time.localtime(mt))} for h, p, mt in page]}


def _path(h, sp):
    kind, real = _resolve(h, sp, ('mats', 'gallery'))
    vg = _ctx['videogen']
    if kind == 'mats':
        if _ctx['mats_hide'](real, sp):
            raise ValueError('找不到这个视频')
        return _ctx['mats_path'](real, any_space=True), {'mats': real}
    x = vg.gallery_get(real, sp)
    if not x:
        raise ValueError('这个视频已经不在视频库里了')
    return vg.vfile(sp, x['file']), {'gallery': real}


def cutpoints(sp, video):
    import cutpoints as C
    path, _ = _path(video, sp)
    r = C.analyze(path, _ctx['videogen'].FFMPEG, _ctx['videogen']._probe, _ctx['cp_dir'](sp), False, _ctx['idle'])
    _ctx['act'](f'Agent：找换装点（{video}）', 'video')
    return {'dur': r.get('dur'), 'bpm': r.get('bpm'), 'beats': len(r.get('beats') or []),
            'points': [{'t': p['t'], 'kind': p['kind'], 'score': p['score'], **({'on_beat': True} if p.get('sync') else {}), **({'downbeat': True} if p.get('db') else {})} for p in r.get('points') or []],
            'sections': [[a, b, lab] for a, b, lab in (r.get('sections') or [])]}


def recommend(sp, video):
    import cutpoints as C, segpref
    path, _ = _path(video, sp)
    cp = C.cached(path, _ctx['cp_dir'](sp)) or C.analyze(path, _ctx['videogen'].FFMPEG, _ctx['videogen']._probe, _ctx['cp_dir'](sp), False, _ctx['idle'])
    st = segpref.status(_ctx['segpref'](sp))
    segs = segpref.split(cp, cp.get('dur'), st.get('model') if st.get('use') == 'learned' else None)
    return {'dur': cp.get('dur'), 'segments': segs, 'by': st.get('use'), 'learned_from_videos': st.get('videos', 0)}


def edit_outfit(sp, video, instruction='', segments=None, viggle=None, seed=-1, size='720p'):
    """改衣：和网页上点“生成”一样的设置（默认值 = 应用默认：参考生成 + 动作跟随 + 加速 8 步；viggle = True 时 Viggle 重拍）"""
    vg = _ctx['videogen']
    path, ref = _path(video, sp)
    d = _info(path).get('dur') or 0
    segs = [[float(a), float(b)] for a, b in (segments or [[0, d]])]
    if not segs or any(not (0 <= a < b <= d + 0.05) for a, b in segs):
        raise ValueError(f'段落要在 0 到 {d} 秒之间，开头小于结尾')
    import batch
    instruction = str(instruction or '').strip()[:2000]
    if not instruction:
        raise ValueError('更换衣服时要写清换成什么衣服（instruction）')
    r = {'instruction': instruction, 'viggle': viggle if viggle in (True, False) else None, 'size': size if size in ('480p', '720p') else '720p'}
    segs = batch._cap(segs, r)  # 超过上限（Viggle 14 秒 / H3 150 秒）的切成几段（以前整段交上去，引擎截短，后面没改）
    out, vgs = [], False
    for i, (a, b) in enumerate(segs):  # 设置和批量配方、网页上点“生成”一样（batch.outfit_body）
        body, vgs = batch.outfit_body(ref, a, b, r, int(seed) + i if int(seed) >= 0 else -1, d)
        try:
            j = _ctx['submit'](body, sp)
            err = None if j and j.get('id') else scrub((j or {}).get('error') or '提交失败')
        except Exception as e:
            j, err = None, scrub(str(e) or '提交失败')
        if err:  # 前面几段已经排上了：照样把它们的代号交回去，标明从第几段起没交上（以前直接报错，调用方拿不到已排上的任务，重试会重复生成，审查 19）
            if not out:
                raise ValueError(err)
            _ctx['act'](f'Agent：改衣交了 {len(out)} 段，第 {i + 1} 段起没交上：{err}', 'video', 'warn')
            return {'jobs': out, 'viggle': vgs, 'segments': segs[:len(out)], 'failed_from': i, 'failed_segments': segs[i:], 'error': err}
        out.append(handle('job', j['id'], sp))
    _ctx['act'](f'Agent：改衣 {len(out)} 段（更换衣服{"，Viggle 重拍" if vgs else ""}，{video}）', 'video')
    return {'jobs': out, 'viggle': vgs, 'segments': segs}


def job_status(sp, jobs=None):
    """按请求的代号逐个对账（2026-11-17 审查 F09：以前查不到的代号直接不出现，等一个不存在的任务会得到 jobs=[]、当成“都做完了”）。
    查不到的明确给 state = missing，并列在 missing 里；不带 jobs 时列出现有的全部"""
    want = [str(h) for h in (jobs or [])]
    gal = {x.get('job'): x for x in _ctx['videogen'].gallery(sp) if x.get('job')}
    rows = {}
    for h, j in _jobs(sp):
        tm = j.get('timing') or {}
        x = gal.get(j['id'])
        rows[h] = {'id': h, 'state': j.get('state'), 'progress': j.get('progress'), 'stage': scrub(j.get('message'), 60), 'elapsed': round(time.time() - (j.get('created') or time.time())),
                   **({'error': scrub(j.get('error'))} if j.get('error') else {}), **({'result': handle('gallery', x['id'], sp)} if x else {}),
                   **({'stages': [[s.get('name'), round(s.get('sec') or 0)] for s in tm.get('stages') or []]} if j.get('state') == 'done' else {})}
    if not want:
        return {'jobs': list(rows.values())}
    out, missing = [], []
    done_before = None
    for h in want:
        if h in rows:
            out.append(rows[h]); continue
        if done_before is None:  # 不在内存里：重启前做完的，视频库里有它的成品
            done_before = {hh: x for hh, x in _gal_jobs(sp)}
        x = done_before.get(h)
        if x:
            out.append({'id': h, 'state': 'done', 'result': handle('gallery', x['id'], sp)})
        else:
            out.append({'id': h, 'state': 'missing', 'error': '查不到这个任务（代号不对、属于另一个空间，或 Studio 重启前没做完）'}); missing.append(h)
    return {'jobs': out, 'missing': missing}


def check_quality(sp, job):
    kind, real = _resolve(job, sp, ('job', 'gallery'))
    vg = _ctx['videogen']
    iid = real if kind == 'gallery' else next((x.get('id') for x in vg.gallery(sp) if x.get('job') == real), None)
    x = vg.gallery_get(iid, sp) if iid else None
    if not x:
        raise ValueError('这个任务还没有成品（还没做完或失败了）')
    e = x.get('edit') or {}
    r = vg.qc_run(sp, iid) or {}
    m = r.get('m') or {}
    import batch
    why = batch.judge(m, r.get('flags') or [], e.get('task') or 'outfit')  # 和批量配方同一套过线
    _ctx['act'](f'Agent：质检 {job}：{"通过" if not why else "不通过"}', 'video')
    return {'pass': not why, 'reasons': list(dict.fromkeys(why)), 'metrics': m, 'task': e.get('task'), 'thresholds': PASS}


def retry(sp, job, seed=-1):
    kind, real = _resolve(job, sp, ('job',))
    vg = _ctx['videogen']
    j = vg.jobs.get(real)
    redo = j.get('_redo') if j else None  # 还没做完的任务在内存里
    if redo:
        b, vid, img = redo
    else:  # 做完的：和网页上“重新生成”一样，从视频库里记下的设置取（以前只看内存，任务一结束就被清掉，2026-11-16 审查）
        iid = next((x.get('id') for x in vg.gallery(sp) if x.get('job') == real), None)
        if not iid:
            raise ValueError('这个任务没有成品（失败 / 取消的请重新提交）')
        b, img, vid = vg.redo_input(iid, sp)
    b = {**b, 'seed': int(seed) if int(seed) >= 0 else -1}
    nj = vg.submit(b, img, _ctx['ffmpeg'], None, vid)
    if not nj or not nj.get('id'):
        raise ValueError(scrub((nj or {}).get('error') or '提交失败'))
    _ctx['act'](f'Agent：重做 {job}', 'video')
    return {'job': handle('job', nj['id'], sp)}


# ------------------------------------------------------------------ 批量配方（batch.py）：Agent 只管挑视频和配方，生成 / 质检 / 重做 / 挑最好的 / 拼接都交给批量
def list_recipes(sp):
    import batch
    return {'recipes': [{'id': r['id'], 'name': r['name'], 'needs_instruction': not r.get('instruction'),
                         'segments': r['segs'], 'retry': r['retry'], 'splice': r['splice'], 'size': r['size']} for r in batch.recipes(sp)]}


def run_recipe(sp, videos, recipe, instruction=None):
    import batch
    items = []
    for h in videos or []:
        kind, real = _resolve(str(h), sp, ('mats', 'gallery'))
        items.append({'video': {kind: real}, 'label': str(h)})
    b = batch.create(sp, recipe, items, instruction)
    _ctx['act'](f'Agent：批量「{b["recipe"]["name"]}」{len(items)} 个视频', 'video')
    return {'batch': 'b_' + b['id'], 'videos': len(items)}


def batch_status(sp, bh):
    import batch
    b = batch.get(sp, str(bh or '')[2:]) if str(bh or '').startswith('b_') else None
    if not b:
        raise ValueError('没有这个批量代号')
    vids = []
    for it in b['items']:
        segs = []
        for s in it.get('segs') or []:
            best = s['tries'][s['best']] if s.get('best') is not None else None
            segs.append({'start': s['a'], 'end': s['b'], 'state': s['state'], 'tries': len(s['tries']),
                         **({'pass': bool(best.get('ok')), 'metrics': best.get('qc'), 'reasons': best.get('why'), 'result': handle('gallery', best['result'], sp)} if best and best.get('result') else {})})
        vids.append({'video': it['label'] if str(it.get('label', '')).startswith(('v_', 'w_')) else handle(*next(iter(it['video'].items())), sp), 'state': it['state'], 'segments': segs,
                     **({'spliced': handle('gallery', it['splice']['id'], sp)} if (it.get('splice') or {}).get('id') else {}), **({'error': scrub(it['error'])} if it.get('error') else {})})
    sm = batch.summary(b)  # 和网页、推送同一份计数（F02）：完整 / 缺段 / 没做出来、生成失败 / 质检没过 / 拼接失败分开
    for v, o in zip(vids, sm['items']):
        v['outcome'] = {k: o[k] for k in ('segs', 'pass', 'qc_fail', 'gen_fail', 'missing', 'splice_error')}
    return {'batch': bh, 'state': b['state'], 'recipe': b['recipe']['name'], 'note': scrub(b.get('note')), 'counts': sm['counts'], 'videos': vids}
