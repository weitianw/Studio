"""H3 的“做法”（用哪套节点跑）：同一个功能可以换做法，网页“高级参数”里切换。
- ① 我们的 ComfyUI + 原生节点：工作流在 videogen / videoedit / h3extra 里拼
- ② 秋叶节点（laowang / 秋叶的 T8 条件、多速率采样、Sage 注意力，“质量稳定优先流”，装在我们的 ComfyUI 里）：
     先照 ① 拼好工作流，再用 to_t8() 把“条件 → 采样 → 解码”这一段换成他的节点；读图读视频、存视频这些不动
- ③ 秋叶 ComfyUI：直接调用他的整合包（8288 端口）：每条前要重启，app 里没有接（第 3 轮测下来和 ② 几乎逐帧一样）

默认（engine = 'auto'）：官方底模（生视频“官方原版”、改视频“官方完整版”）+ ② 能用 → ②；其余都是 ①。
（2026-11-04 laowang A/B 第 3 轮：② ≈ ③ ≈ ①，② 比 ① 快一倍——参考类约 14 分钟，① 要 23–26 分钟；见 docs\\AB测试\\第3轮\\打分表.md）
② 接不了的条件（参考 + 关键帧、开头片段、引导视频、从第几秒开始的指定声音）：auto 时自动用 ①，任务里记着用的是哪个。
没有参考时的中间关键帧可以走 ②（T8 条件后面串原生 AddGuide）。"""
import copy, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, 'workflows', 'methods')
NODES = os.path.join(os.path.dirname(HERE), 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'custom_nodes')
T8_PACKS = ('comfyui-minimax-h3-audio-T8', 'reservedvram', 'comfyui-kjnodes')  # ② 要的节点包（videohelpersuite 也装了，但 app 不用它）
ENGINES = {
    '1': {'name': '① 原生节点', 'short': '原生'},
    '2': {'name': '② 秋叶节点', 'short': '秋叶节点'},
    '3': {'name': '③ 秋叶 ComfyUI', 'short': '秋叶 ComfyUI', 'url': 'http://127.0.0.1:8288', 'restart': True},
}
FUNCS = ('i2v', 'ref', 'swap_ref', 'outfit_ref')
T8_STEPS = 14  # 他的采样设置：视频 / 声音各 14 步，偏移 12 / 3（保留他的值）


def templates(engine):
    """（③ 用）这个做法放好了哪些功能的模板（工作流 + 参数对照都在）"""
    d = os.path.join(DIR, engine)
    return [f for f in FUNCS if os.path.isfile(os.path.join(d, f + '.json')) and os.path.isfile(os.path.join(d, f + '.map.json'))]


def ready(engine):
    if engine == '1':
        return True
    if engine == '2':
        return all(os.path.isdir(os.path.join(NODES, p)) for p in T8_PACKS)
    return bool(templates(engine)) and RUNNERS.get(engine) is not None


def status():
    return [{'key': k, 'name': v['name'], 'short': v['short'], 'ready': ready(k)} for k, v in ENGINES.items()]


def unsupported(extra):
    """② 接不了的条件 → 原因（None = 都能接）。
    中间的关键帧：没有参考时可以（T8 条件后面再串原生 AddGuide，2026-11-04 测过：钉住的那帧 39.6 dB、前后没跳变）；
    有参考图 / 参考视频 / 参考音频时不行（T8 会把首尾帧打包成参考，后加的关键帧可能对不上，没测）"""
    x = extra or {}
    if x.get('keys') and (x.get('refs') or x.get('rvids') or x.get('raudios')):
        return '参考 + 关键帧'
    if x.get('clip'):
        return '开头片段'
    if x.get('guide'):
        return '引导视频'
    if x.get('audio') and float(x['audio'].get('start') or 0) > 0:
        return '从中间开始的指定声音'
    return None


def pick(req, official, extra, refs=False):
    """请求里的做法 → '1' / '2'。auto：官方底模 + 没有参考视频 + ② 能用 + 条件都接得上 → ②，否则 ①。
    refs = 生视频里放了参考视频（拿它的动作当参考）：自动用 ①——用户看了第 3 轮同框对比，只有“多参考 + 动作”是原生节点 + 官方底模最好、节奏和参考视频对得上（2026-11-04）。
    其余全部是 ②：首帧、首尾帧、只有参考图 / 参考音频，以及改视频的换人 · 审美优先、改衣 · 参考生成。手动选的照旧优先。
    明说要 ② 但接不了：报错（不悄悄换成 ①，免得以为跑的是 ② 其实是 ①）"""
    v = str(req or 'auto')
    if v == 'auto':
        return '2' if official and not refs and ready('2') and not unsupported(extra) else '1'
    if v not in ENGINES:
        raise ValueError('不存在该做法')
    if v == '3':
        raise ValueError('③ 尚未接入本应用')
    if not ready(v):
        raise ValueError(f'{ENGINES[v]["name"]}尚未接入')
    if v == '2':
        if not official:
            raise ValueError('② 秋叶节点仅适用于官方底模（生视频“官方原版”、改视频参考生成的“官方完整版”）')
        why = unsupported(extra)
        if why:
            raise ValueError(f'② 不支持{why}：请改用 ①')
    return v


class Unsupported(RuntimeError):
    pass


def _src(wf, ref):
    return wf.get(str(ref[0]), {}) if isinstance(ref, list) else {}


def _rewire(wf, nid, to):
    for n in wf.values():
        for k, v in n.get('inputs', {}).items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == nid:
                n['inputs'][k] = to(v[1])


def to_t8(wf, keep_lora=None, steps=None, shift=None, ashift=None, vae_int8=False):  # 后几个：测试用（加速 LoRA 留着、用它的步数 / 偏移）
    """把 ① 拼好的 H3 工作流（7 条件、11 引导、12 采样、13 / 14 解码）换成 ② 他的节点；其余节点不动。
    7 可以是 MiniMaxH3ImageToVideo（首帧 / 首尾帧）或 MiniMaxH3ReferenceToVideo（参考类，首尾帧走 AddGuide）。"""
    wf = copy.deepcopy(wf)
    C, G, S = wf['7'], wf['11'], wf['12']
    ci = C['inputs']
    t8 = {'clip': ci['clip'], 'video_vae': ci['vae'], 'audio_vae': ci.get('audio_vae') or ['6', 0], 'prompt': ci['prompt'],
          'width': ci['width'], 'height': ci['height'], 'length': ci['length'], 'audio_mode': 'native', 'audio_denoise_strength': 1.0,
          'add_source_as_reference': False, 'prompt_primary_audio_ordinal': 0, 'strict_prompt_tags': True, 'ref_image_size': ci.get('ref_image_size') or 'match',
          # 参考视频长度：official_2_to_15s 只多一道检查（不在 2~15 秒就报错），别的处理一样；改视频能做到 15 秒以上，所以不用这道检查
          'reference_video_policy': 'model_minimum'}
    for k, v in ci.items():
        if k.split('.')[0] in ('ref_images', 'ref_videos', 'ref_audios', 'ref_video_audios'):
            t8[k] = v
    for k in ('first_frame', 'last_frame'):
        if ci.get(k):
            t8[k] = ci[k]
    # AddGuide 链：第 0 帧 / 最后一帧的单张图 → 首帧 / 尾帧；第 0 帧的声音 → 原声驱动（lock_source）；
    # 中间的单张图（关键帧，没有参考时）→ 留着，串在 T8 条件后面；别的接不了
    refs = any(k.startswith('ref_') for k in t8 if k != 'ref_image_size')
    pos, keys = G['inputs']['conditioning'], []
    while isinstance(pos, list) and str(pos[0]) != '7':
        nid = str(pos[0])
        g = wf[nid]
        if g.get('class_type') != 'MiniMaxH3AddGuide':
            raise Unsupported(f'② 不支持该节点：{g.get("class_type")}')
        gi, idx = g['inputs'], g['inputs'].get('frame_idx')
        if gi.get('image'):
            if _src(wf, gi['image']).get('class_type') != 'LoadImage':
                raise Unsupported('② 不支持逐帧引导（开头片段 / 引导视频）')
            if idx in (0, -1) and not ('first_frame' if idx == 0 else 'last_frame') in t8:
                t8['first_frame' if idx == 0 else 'last_frame'] = gi['image']
            elif refs:
                raise Unsupported('② 不支持参考 + 关键帧')
            elif not gi.get('audio'):
                keys.append(nid)
                pos = gi['positive']
                continue
            else:
                raise Unsupported('② 不支持带声音的关键帧')
        if gi.get('audio'):
            if idx != 0:
                raise Unsupported('② 不支持从中间开始的指定声音')
            t8['drive_audio'], t8['audio_mode'] = gi['audio'], 'lock_source'
        del wf[nid]
        pos = gi['positive']
    first, last = 'first_frame' in t8, 'last_frame' in t8
    t8['task_type'] = ('Hybrid' if first or last else 'Ref2VA') if refs else 'FL2VA' if first and last else 'I2VA' if first else 'L2VA' if last else 'T2VA'
    wf['7'] = {'class_type': 'MiniMaxH3AudioConditioningT8', 'inputs': t8}
    # 模型：去掉 ① 的采样偏移 / 注意力补丁 / 加速 LoRA（他的采样器自己设偏移、不用加速 LoRA），保留自选 LoRA
    for nid, n in list(wf.items()):
        ct = n.get('class_type')
        if ct in ('MiniMaxH3SigmaShift', 'ModelAttentionBackend', 'BlockSparseAttention') or (ct == 'LoraLoaderModelOnly' and 'turbo' in str(n['inputs'].get('lora_name', '')).lower() and n['inputs'].get('lora_name') != keep_lora):
            src = n['inputs']['model']
            _rewire(wf, nid, lambda _o, s=src: s)
            del wf[nid]
    # 再接他的显存设置 + Sage 注意力 + 多速率采样
    wf['t44'] = {'class_type': 'ReservedVRAMSetter', 'inputs': {'reserved': 1, 'mode': 'manual', 'seed': 1004577797905923, 'auto_max_reserved': 0,
                                                                'clean_gpu_before': True, 'anything': G['inputs']['model']}}
    wf['t47'] = {'class_type': 'MiniMaxH3MemoryEfficientSageAttentionPatch', 'inputs': {'model': ['t44', 0]}}
    wf['t55'] = {'class_type': 'MiniMaxH3MultiRateSamplerEXPT8', 'inputs': {'model': ['t47', 0], 'av_latent': ['7', 1], 'video_steps': steps or T8_STEPS,
                                                                           'audio_steps': steps or T8_STEPS, 'shift_video': shift or 12, 'shift_audio': ashift or 3}}
    cond = ['7', 0]
    for nid in reversed(keys):  # 关键帧：按原来的顺序串在 T8 条件后面（照秋叶那边测过的接法：latent 接 T8 的 av_latent，vae 接视频 VAE）
        wf[nid]['inputs'].update(positive=cond, latent=['7', 1], vae=t8['video_vae'])
        cond = [nid, 0]
    G['inputs'].update(model=['t55', 0], conditioning=cond)
    S['inputs'].update(sampler=['t55', 1], sigmas=['t55', 2], latent_image=['7', 1])
    if wf.get('ln2', {}).get('class_type') == 'MiniMaxH3SourceAVPrepareT8':  # 局部修改测试（videoedit native）：采样从原视频的 latent + mask 开始
        wf['ln2']['inputs']['audio_latent'] = ['7', 1]
        S['inputs']['latent_image'] = ['ln2', 0]
        wf['t55']['inputs']['av_latent'] = ['ln2', 0]
    # 视频 VAE：以前固定 fp16（他测的是这个，int8 没在他的解码节点上测过）；2026-11-10 用户：改视频也要用上 int8——
    # 设置里是 int8（H3OPT 默认）就用 int8（vae_int8，videogen 按 h3opt 传进来），否则 fp16
    vae = _src(wf, t8['video_vae'])
    if vae.get('class_type') == 'VAELoader':
        vae['inputs']['vae_name'] = 'minimax_h3_video_vae_int8_convrot.safetensors' if vae_int8 else 'minimax_h3_video_vae_fp16.safetensors'
    # 解码：VAEDecode / VAEDecodeAudio → 他的 AV 解码（一个节点出画面 + 声音）
    wf['t57'] = {'class_type': 'MiniMaxH3AVDecodeT8', 'inputs': {'av_latent': ['12', 0], 'video_vae': t8['video_vae'], 'audio_vae': t8['audio_vae']}}
    dec = {nid: (0 if n['class_type'] == 'VAEDecode' else 1) for nid, n in wf.items()
           if n.get('class_type') in ('VAEDecode', 'VAEDecodeAudio') and n['inputs'].get('samples') == ['12', 0]}
    for nid, o in dec.items():
        _rewire(wf, nid, lambda _o, o=o: ['t57', o])
        del wf[nid]
    return _prune(wf)


def _prune(wf):
    """只留存成品要用到的节点（换下来的 ① 的采样器、调度器之类去掉）"""
    keep, todo = set(), [k for k, n in wf.items() if n.get('class_type') in ('SaveVideo', 'SaveImage', 'VHS_VideoCombine', 'PreviewImage')]
    while todo:
        k = todo.pop()
        if k in keep or k not in wf:
            continue
        keep.add(k)
        for v in wf[k].get('inputs', {}).values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                todo.append(v[0])
    return {k: v for k, v in wf.items() if k in keep}


def load(engine, func):
    with open(os.path.join(DIR, engine, func + '.json'), encoding='utf-8') as f:
        wf = json.load(f)
    with open(os.path.join(DIR, engine, func + '.map.json'), encoding='utf-8') as f:
        mp = json.load(f)
    return wf, mp


def fill(wf, mp, values):
    """按参数对照把值填进模板（不改原模板）；对照里没有的参数跳过，对照里有、工作流里没这个节点的报错"""
    out = copy.deepcopy(wf)
    for k, v in values.items():
        for node, inp in mp.get(k) or []:
            if node not in out:
                raise KeyError(f'参数对照中的节点 {node} 在工作流中不存在（{k}）')
            out[node].setdefault('inputs', {})[inp] = v
    return out


RUNNERS = {'3': None}  # ③ 没有接进 app
