"""生视频（图生视频）：后台跑一个看不见的 ComfyUI，网页上是我们自己的“生视频”页。

- 引擎：tools/ComfyUI_windows_portable（官方便携版），只监听本机 127.0.0.1:8188，用到时才启动，闲置 30 分钟自动退出。
- 模型：MiniMax H3（FL2VA，首帧 → 视频，带声音）。Wan 2.2 I2V 2026-11-06 去掉了。
  工作流是 workflows/*.json（ComfyUI 的 API 格式），这里只填图片、提示词、尺寸、时长、种子这些。
- 显卡：和生图共用 imagegen.GPU（同一时间只做一件大事）；配音 / 识别要用显卡时等这一段视频做完。
  做完一段就让 ComfyUI 把模型从显存里放掉（/free），配音和生图马上能用。
- 私密空间：原图、成品都只放在私密空间自己的文件夹；ComfyUI 输入 / 输出文件夹里的临时文件做完立刻删掉。
"""
import base64, datetime, json, os, random, re, shutil, socket, struct, subprocess, threading, time, urllib.error, urllib.request, uuid
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import stages  # 任务计时（每一步用了多久）
import prompttrace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIO = os.path.join(ROOT, 'studio')
COMFY_DIR = config.COMFY_PORTABLE
COMFY_PY = os.path.join(COMFY_DIR, 'python_embeded', 'python.exe')
COMFY_MAIN = os.path.join(COMFY_DIR, 'ComfyUI', 'main.py')
MODELS_DIR = os.path.join(COMFY_DIR, 'ComfyUI', 'models')
WF_DIR = os.path.join(STUDIO, 'workflows')
PORT = 8188
IDLE_EXIT = 1800  # 2026-11-08：10 → 30 分钟。闲置时模型早已从显存 / 内存放掉（free_later），只留程序本身；隔一阵再生成不用重新启动（省 20~40 秒）
EXTRA_ARGS = []  # 测试用的 Studio 会加自己的数据库，避免和正在用的那个 ComfyUI 抢同一个文件
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LOG = os.path.join(STUDIO, 'comfy-engine.log')
DIRS = {'n': os.path.join(ROOT, 'outputs', 'videos'), 'v': os.path.join(ROOT, '.data', 'videos')}  # 每个空间各一份
WORK = {'n': os.path.join(ROOT, 'studio', 'tmp', 'comfy'), 'v': os.path.join(ROOT, '.data', 'tmp', 'comfy')}  # ComfyUI 的输入 / 输出（做完就清）

# 模型。files：需要的文件（相对 ComfyUI/models），缺了网页上显示“未下载”
MODELS = {
    'h3': {'name': 'MiniMax H3', 'base': 'MiniMax H3 官方完整版', 'wf': 'h3_i2v.json', 'fps': 24, 'audio': True,
           'tag': '官方原版，带声音；参考更准确', 'speed': '480p 5 秒约 6~10 分钟',
           'desc': 'MiniMax H3 官方完整版（int8）：只有首帧 / 关键帧时用 FL2VA，放入参考图 / 参考视频 / 参考音频时自动换成 Ref2VA；带立体声，默认 20 步，可叠官方加速 LoRA',
           'files': ['text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors', 'vae/minimax_h3_video_vae_fp16.safetensors',
                     'vae/minimax_h3_audio_vae_fp32.safetensors'],
           'diffusion': ['diffusion_models/minimax_h3_fl2va_int8_convrot.safetensors', 'diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors'],  # 官方完整版（H3_FULL）
           'defaults': {'steps': 20, 'seconds': 5, 'size': '480p'}},
}
# 高级参数：默认值 = 工作流里原来写死的值（不改就和以前完全一样）
TUNE = {'h3': {'sampler': 'res_multistep', 'scheduler': 'simple', 'shift': 12.0, 'ashift': 3.0, 'audio': True}}
MAX_SECONDS = {'h3': 15}
# H3 的提速 / 提质选项（2026-11-03 调研后加，默认值按 A/B 结果定）：
#   sparse：ComfyUI 自带的 BlockSparseAttention（社区工作流的建议：按 90% 稀疏、从 0 开始跑，否则会闪）；'off' = 不用
#   attn：'int8' = ModelAttentionBackend 的 comfy kitchen INT8 注意力；'off' = 默认
#   vae：'int8' = minimax_h3_video_vae_int8_convrot（官方模板默认）；'fp16' = 原来的
H3OPT = {'sparse': 'off', 'attn': 'off', 'vae': 'int8'}  # 2026-11-03 A/B：INT8 VAE 和原来的 PSNR 39.4 dB（看不出差别），解码快一倍 → 默认；稀疏注意力出的画面会不一样 → 网页上的“稀疏注意力”开关，默认关
H3_VAE_INT8 = 'vae/minimax_h3_video_vae_int8_convrot.safetensors'
# 底模 / 文字编码器：base = 'ref2va' / 'fl2va'（官方完整版 int8，没合并加速：步数由调用方给，默认 20 步）；te = 'int8' / 'nvfp4'
H3_FULL = {'ref2va': 'diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors', 'fl2va': 'diffusion_models/minimax_h3_fl2va_int8_convrot.safetensors'}
H3_TE = {'nvfp4': 'text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', 'int8': 'text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors'}


def _h3opt_in(b):
    """请求里的 H3 选项：网页只传 h3fast（稀疏注意力开关）；测试脚本可以传完整的 h3opt"""
    o = {}
    if isinstance(b.get('h3opt'), dict):
        x = b['h3opt']
        o = {k: v for k, v in (('sparse', x.get('sparse')), ('attn', x.get('attn')), ('vae', x.get('vae')), ('base', x.get('base')), ('te', x.get('te')))
             if v in {'sparse': ('off', 'vsa', 'sol-attn', 'sla'), 'attn': ('off', 'int8'), 'vae': ('fp16', 'int8'), 'base': ('ref2va', 'fl2va'), 'te': ('nvfp4', 'int8')}[k]}
    if b.get('h3fast') is True:
        o['sparse'] = 'vsa'
    return o or None


def h3opt(j):
    """这个任务用的 H3 选项：默认 H3OPT；测试时任务里可以带 _h3opt 覆盖"""
    o = {'base': None, 'te': None, **H3OPT, **(j.get('_h3opt') or {})}  # base / te 为 None = 不换工作流里原来的文件
    if o['vae'] == 'int8' and not _have(H3_VAE_INT8):
        o['vae'] = 'fp16'
    return o


def apply_h3opt(j, wf):
    """把 H3 选项接进工作流：稀疏注意力 / INT8 注意力接在采样用的模型上（BasicGuider '11' 前面），VAE 换文件"""
    if '11' not in wf or wf['11'].get('class_type') != 'BasicGuider':
        return
    o = h3opt(j)
    m = wf['11']['inputs']['model']
    if o['attn'] == 'int8':
        wf['h3ab'] = {'class_type': 'ModelAttentionBackend', 'inputs': {'model': m, 'attention': 'comfy kitchen attention'}}
        m = ['h3ab', 0]
    if o['sparse'] in ('vsa', 'sol-attn', 'sla'):
        # 参数照社区推荐的 Lokken 工作流：保留 10%、从 0 开始、前两块保持稠密、文字 / 声音 token 精确参与
        sel = {'selection': o['sparse'], 'selection.keep_percent': 10.0} if o['sparse'] != 'sol-attn' else {'selection': 'sol-attn', 'selection.tau': 1.3}
        wf['h3sa'] = {'class_type': 'BlockSparseAttention', 'inputs': {'model': m, **sel, 'start_percent': 0.0, 'end_percent': 1.0, 'dense_blocks': '0,1',
                                                                        'min_tokens': 12288, 'extra_tokens': 256, 'sink_conditioning': 'exact_kv_and_rows', 'verbose': False}}
        m = ['h3sa', 0]
    wf['11']['inputs']['model'] = m
    if o['vae'] == 'int8' and wf.get('5', {}).get('class_type') == 'VAELoader':
        wf['5']['inputs']['vae_name'] = os.path.basename(H3_VAE_INT8)
    h3n = {os.path.basename(f) for f in H3_FULL.values()} | {'__H3DIFF__'}
    for n in wf.values():  # 换底模 / 文字编码器（FL2VA ↔ Ref2VA；生视频时这里还是占位符，后面才换成文件名）
        if o['base'] in H3_FULL and n.get('class_type') == 'UNETLoader' and n['inputs'].get('unet_name') in h3n:
            n['inputs']['unet_name'] = os.path.basename(H3_FULL[o['base']])
        if o['te'] in H3_TE and n.get('class_type') == 'CLIPLoader' and n['inputs'].get('clip_name') in {os.path.basename(f) for f in H3_TE.values()}:
            n['inputs']['clip_name'] = os.path.basename(H3_TE[o['te']])
    j['h3opt_used'] = o
MAX_FRAMES = {'h3': 362}  # 帧数上限（H3 官方训练范围 124~362 帧）：改了帧率时按这个缩短时长
RES_STEP = {'h3': 32}  # 自定义分辨率的倍数：H3 32（潜空间要能按 2×2 切块）
# 插帧模型（ComfyUI 自带的 FrameInterpolate 节点）：RIFE 4.26 快、效果好；FILM 大动作更稳但慢约 4 倍；都没有时用 ffmpeg 的 minterpolate
INTERP = {'rife': 'frame_interpolation/rife_v4.26.safetensors', 'film': 'frame_interpolation/film_net_fp16.safetensors'}
INTERP_NAME = {'rife': 'RIFE 4.26', 'film': 'FILM', 'ff': 'ffmpeg'}
INTERP_MAX = 8e9  # 插帧后整段视频在内存里的大小（float32）超过这个就改用 ffmpeg


def interp_ok():
    return [k for k, f in INTERP.items() if _have(f)]


UPSCALER = 'upscale_models/RealESRGAN_x2plus.pth'  # 超分 2 倍（Real-ESRGAN x2plus，67MB）；没有或太大时用 ffmpeg 的 lanczos
UPSCALE_MAX = 6e9  # 超分后整段视频在内存里的大小（float32）超过这个就改用 ffmpeg，免得把内存挤爆
FFMPEG = config.FFMPEG
# 存进视频库的成品每 12 帧（24 fps 是半秒）一个关键帧：拖进度条直接就流畅，不用再另存一份播放副本
# （同样画质只大约 7%，播放副本要多占 60%～100%；2026-11-06 用户：存储焦虑）
GOP = ['-g', '12', '-keyint_min', '1']
FFPROBE = config.FFPROBE
# 采样器 / 调度器：引擎开着时从 /object_info 读（存一份）；还没读到时用这份
SAMPLERS = ['euler', 'euler_ancestral', 'heun', 'dpm_2', 'dpm_2_ancestral', 'lms', 'dpmpp_2s_ancestral', 'dpmpp_sde', 'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_3m_sde',
            'ddpm', 'lcm', 'ipndm', 'deis', 'res_multistep', 'res_multistep_ancestral', 'gradient_estimation', 'er_sde', 'sa_solver', 'ddim', 'uni_pc', 'uni_pc_bh2']
SCHEDULERS = ['simple', 'sgm_uniform', 'karras', 'exponential', 'ddim_uniform', 'beta', 'normal', 'linear_quadratic', 'kl_optimal']
_opts = {}


def _bypass(wf, ids):
    """不用某几个 LoRA 节点：把用到它输出的地方改成接它的输入（模型直接穿过去）。"""
    for nid in ids:
        if nid not in wf:
            continue
        src = wf[nid]['inputs'].get('model')
        del wf[nid]
        for node in wf.values():
            for k, v in node.get('inputs', {}).items():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) == nid:
                    node['inputs'][k] = src
SIZES = {'480p': 480, '576p': 576, '720p': 720}  # 短边；长边按原图比例，都是 16 的倍数


def act(msg, tag='', level='info'):  # 由 server.py 换成网页运行日志
    pass


GPU_PREPARE = None   # 由 server.py 设：做视频前把配音 / 翻译 / 提示词模型的显存放掉
OTHERS_WAITING = None  # 由 server.py 设：配音 / 生图 / 提示词有任务在等显卡（这时做完一段要把显存让出来）
space = lambda: 'n'  # 由 server.py 换成当前空间


def _have(f):  # 下载没成功时可能只留下一个几百字节的报错页：小于 1 MB 当作没有
    p = os.path.join(MODELS_DIR, f)
    return os.path.isfile(p) and os.path.getsize(p) > 1 << 20


def h3_diffusion():
    for f in MODELS['h3']['diffusion']:
        if _have(f):
            return f
    return None


def missing(key):
    m = MODELS[key]
    out = [f for f in m['files'] if not _have(f)]
    if key == 'h3' and not h3_diffusion():
        out.append(m['diffusion'][0])
    if not os.path.isfile(COMFY_PY):
        out.insert(0, 'ComfyUI 便携版')
    return [os.path.basename(x) for x in out]


def _busy_err(e):
    """引擎忙 / 连不上（超时、连接被重置）——不是它明确拒绝（HTTPError 是它回了错误码）"""
    return isinstance(e, (OSError, urllib.error.URLError)) and not isinstance(e, urllib.error.HTTPError)


def _engine_up():
    try:
        import netutil
        return netutil.maybe_up(PORT)
    except Exception:
        return True


def _seen(pid, secs=180):
    """提交时超时了：引擎多半已经收下（它忙的时候回话慢）。按编号在队列 / 记录里找，找到返回 True；引擎回话了但没有这一单返回 False"""
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            q = _http('/queue', timeout=10)
            ids = {str(x[1]) for k in ('queue_running', 'queue_pending') for x in (q.get(k) or []) if isinstance(x, (list, tuple)) and len(x) > 1}
            if pid in ids:
                return True
            h = _http(f'/history/{pid}', timeout=10)
            return isinstance(h, dict) and pid in h
        except Exception as e:
            if not _busy_err(e):
                return False
        time.sleep(3)
    return False


def _submit(wf, cid):
    """把工作流交给视频引擎，返回任务编号。编号自己定（uuid）：提交那一下超时（引擎正忙着载入别的模型），也认得出它收没收下"""
    pid = str(uuid.uuid4())
    try:
        r = _http('/prompt', {'prompt': wf, 'client_id': cid, 'prompt_id': pid}, timeout=30)
    except urllib.error.HTTPError as e:  # 它明确拒绝了（工作流有错）：带上它说的原因
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            body = ''
        raise RuntimeError('视频引擎未接受该任务：' + (body or str(e))[:300])
    except Exception as e:
        if _busy_err(e) and _seen(pid):
            return pid
        raise RuntimeError(f'视频引擎没有响应（{e}），请稍后重试')
    got = r.get('prompt_id') if isinstance(r, dict) else None
    if not got:
        raise RuntimeError('视频引擎未接受该任务：' + json.dumps(r, ensure_ascii=False)[:300])
    return str(got)


def _history(pid, st):
    """问这一单做完没有。引擎忙得回不了话时返回 None（接着等）；端口一分钟都没人在听才算引擎退出了。st：调用方留着的状态"""
    try:
        h = _http(f'/history/{pid}', timeout=10)
        st.pop('down', None)
        return h
    except Exception as e:
        if not _busy_err(e):
            raise
        if _engine_up():
            st.pop('down', None)
        elif time.time() - st.setdefault('down', time.time()) > 60:
            raise RuntimeError('视频引擎意外退出（通常是显存或内存不足），详情见 studio/comfy-engine.log')
        return None


def _drop(pid):
    """Studio 这边判失败了：引擎里的这一单也取消（还在排队就去掉，正在做就停下），不在后台白跑、挡着后面的任务"""
    if not pid:
        return
    try:
        _http(f'/api/jobs/{pid}/cancel', {}, timeout=10)
    except Exception:
        try:
            _http('/queue', {'delete': [pid]}, timeout=10)
        except Exception:
            pass


def _http(path, body=None, timeout=10):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', json.dumps(body).encode() if body is not None else None,
                                 {'Content-Type': 'application/json'} if body is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _combo(spec):  # object_info 里下拉框的选项：新格式 ["COMBO", {"options": [...]}]，旧格式 [[...]]
    if isinstance(spec, list) and spec:
        if isinstance(spec[0], list):
            return [str(x) for x in spec[0]]
        if len(spec) > 1 and isinstance(spec[1], dict) and isinstance(spec[1].get('options'), list):
            return [str(x) for x in spec[1]['options']]
    return []


def sampler_options():
    """(采样器列表, 调度器列表)：引擎开着时读一次真的，存到 WORK 里；没开时用存的那份或内置的。"""
    cache = os.path.join(WORK['n'], 'samplers.json')
    if not _opts.get('live') and Engine.alive():
        try:
            a = _http('/object_info/KSamplerSelect', timeout=3)['KSamplerSelect']['input']['required']['sampler_name']
            b = _http('/object_info/BasicScheduler', timeout=3)['BasicScheduler']['input']['required']['scheduler']
            s, c = _combo(a), _combo(b)
            if s and c:
                _opts.update(live=True, samplers=s, schedulers=c)
                os.makedirs(WORK['n'], exist_ok=True)
                with open(cache, 'w', encoding='utf-8') as f:
                    json.dump({'samplers': s, 'schedulers': c}, f)
        except Exception:
            pass
    if 'samplers' not in _opts:
        try:
            with open(cache, encoding='utf-8') as f:
                d = json.load(f)
            _opts.update(samplers=list(d['samplers']), schedulers=list(d['schedulers']))
        except (OSError, ValueError, KeyError, TypeError):
            _opts.update(samplers=SAMPLERS, schedulers=SCHEDULERS)
    return _opts['samplers'], _opts['schedulers']


def upscaler_ok():
    return _have(UPSCALER)


# AI 修复超分（SeedVR2 7B，ComfyUI 自带的节点，2026-11-06 A/B：docs/AB测试/超分修复_1106）：正常画面比 Real-ESRGAN 自然清晰得多；
# 但生成时已经变形的小脸会被放大成更明显的怪样子（修不了脸）；约 50 秒处理 1 秒视频。只在事后“超分 / 插帧”里手动选
SEEDVR = ('diffusion_models/seedvr2_7b_int8_convrot.safetensors', 'vae/seedvr2_ema_vae_fp16.safetensors')


def seedvr_ok():
    return all(_have(f) for f in SEEDVR)


def _seedvr(j, dst, work_in, work_out, tag, frames):
    pname = f'studio_{tag}_sv.mp4'
    shutil.copy(dst, os.path.join(work_in, pname))
    wf = {
        'lv': {'class_type': 'LoadVideo', 'inputs': {'file': pname}},
        'gc': {'class_type': 'GetVideoComponents', 'inputs': {'video': ['lv', 0]}},
        'rs': {'class_type': 'ResizeImageMaskNode', 'inputs': {'input': ['gc', 0], 'resize_type': 'scale by multiplier', 'resize_type.multiplier': 2.0, 'scale_method': 'lanczos'}},
        'pp': {'class_type': 'SeedVR2Preprocess', 'inputs': {'resized_images': ['rs', 0]}},
        'va': {'class_type': 'VAELoader', 'inputs': {'vae_name': os.path.basename(SEEDVR[1])}},
        'un': {'class_type': 'UNETLoader', 'inputs': {'unet_name': os.path.basename(SEEDVR[0]), 'weight_dtype': 'default'}},
        'en': {'class_type': 'VAEEncodeTiled', 'inputs': {'pixels': ['pp', 0], 'vae': ['va', 0], 'tile_size': 512, 'overlap': 128, 'temporal_size': 64, 'temporal_overlap': 8}},
        'ch': {'class_type': 'SeedVR2TemporalChunk', 'inputs': {'latent': ['en', 0], 'temporal_overlap': 2, 'chunking_mode': 'auto'}},
        'co': {'class_type': 'SeedVR2Conditioning', 'inputs': {'model': ['un', 0], 'vae_conditioning': ['ch', 0]}},
        'ks': {'class_type': 'KSampler', 'inputs': {'model': ['un', 0], 'positive': ['co', 0], 'negative': ['co', 1], 'latent_image': ['ch', 0], 'seed': 42, 'steps': 1, 'cfg': 1.0,
                                                     'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0}},
        'mg': {'class_type': 'SeedVR2TemporalMerge', 'inputs': {'latents': ['ks', 0], 'temporal_overlap': ['ch', 1]}},
        'de': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['mg', 0], 'vae': ['va', 0], 'tile_size': 512, 'overlap': 128, 'temporal_size': 64, 'temporal_overlap': 8}},
        'po': {'class_type': 'SeedVR2PostProcessing', 'inputs': {'images': ['de', 0], 'original_resized_images': ['rs', 0], 'color_correction_method': 'lab'}},
        'cv': {'class_type': 'CreateVideo', 'inputs': {'images': ['po', 0], 'fps': ['gc', 2]}},
        'sv': {'class_type': 'SaveVideo', 'inputs': {'video': ['cv', 0], 'filename_prefix': f'studio_{tag}_sv', 'format': 'mp4', 'codec': 'h264'}},
    }
    try:
        outs = _run_wf(j, wf, work_out, 'AI 修复超分中（SeedVR2，较慢）…', limit=max(1800, int(frames * 5)))
        got = [os.path.join(work_out, it.get('subfolder', ''), it['filename']) for o in outs.values() for k in ('videos', 'images', 'gifs')
               for it in (o.get(k) or []) if isinstance(it, dict) and it.get('type', 'output') == 'output' and str(it.get('filename', '')).lower().endswith('.mp4')]
        if not got:
            raise RuntimeError('AI 修复超分没有产生输出')
        os.replace(got[0], dst)
    finally:
        try:
            os.remove(os.path.join(work_in, pname))
        except OSError:
            pass


def lora_files():
    """ComfyUI\\models\\loras 里用户自己放的 LoRA（H3 加速这几个由程序自己管，不列出来）"""
    d = os.path.join(MODELS_DIR, 'loras'); own = set()
    import videoedit  # 改视频用的换人 / VFX LoRA 也由程序自己管
    # 特效编辑（VFX Edit）LoRA 例外：“自由修改”并进生视频以后（2026-11-04），要在生视频的 LoRA 里自己加它
    own |= {os.path.basename(f) for k, f in videoedit.FILES.items() if f.startswith('loras/') and k != 'vfx'}
    try:  # 生图人偶姿势用的 Qwen 2.1 LoRA（VNCCS PoseStudio）也放在这个文件夹里：不是视频的
        import q21
        own.add(q21.POSE_LORA)
    except Exception:
        pass
    try:
        return sorted(f for f in os.listdir(d) if f.lower().endswith(('.safetensors', '.pt', '.ckpt')) and f not in own and '_turbo_' not in f.lower())  # 加速 LoRA 要配合步数用，不当普通 LoRA 列出
    except OSError:
        return []


_KIND = {}  # 文件 → (大小, 修改时间, 类型)：只读一次文件头


def lora_kind(f):
    """LoRA 是给哪个视频模型的：'wan'（Wan 2.1 / 2.2 14B）、'h3'（MiniMax H3，社区微调版也算）、'other'（别的模型，比如 Wan 5B）、'?'（看不出来）。
    先看 Civitai 下载时记下的底模名，再看文件头：H3 的隐藏维度是 5376、层名是 mlp.fc / attn.out_proj；Wan 14B 是 5120、ffn / cross_attn；Wan 5B 是 3072。"""
    p = os.path.join(MODELS_DIR, 'loras', f)
    try:
        st = os.stat(p)
    except OSError:
        return '?'
    try:  # Civitai 记录（.civitai.json）后来才写进来时也要重新判断（以前只看 LoRA 文件本身，识别过的还一直显示“看不出来”）
        jm = os.path.getmtime(p + '.civitai.json')
    except OSError:
        jm = 0
    c = _KIND.get(f)
    if c and c[:3] == (st.st_size, st.st_mtime, jm):
        return c[3]
    kind = '?'
    try:
        with open(p + '.civitai.json', encoding='utf-8') as fh:
            base = (json.load(fh) or {}).get('base') or ''
        kind = 'h3' if 'minimax' in base.lower() or 'h3' in base.lower() else 'wan' if re.search(r'wan video (2\.2 i2v-a14b|14b)', base, re.I) else 'other' if base else '?'
    except (OSError, ValueError):
        pass
    if kind == '?' and f.lower().endswith('.safetensors'):
        try:
            with open(p, 'rb') as fh:
                n = int.from_bytes(fh.read(8), 'little')
                hd = json.loads(fh.read(n)) if 0 < n < 50_000_000 else {}
            hd.pop('__metadata__', None)
            dims = {d for v in hd.values() if isinstance(v, dict) for d in (v.get('shape') or [])}
            ks = ' '.join(list(hd)[:400])
            if 5376 in dims or re.search(r'mlp[._]fc|attn[._]out_proj|audio_patch', ks):
                kind = 'h3'
            elif 5120 in dims or re.search(r'cross_attn|self_attn|ffn[._]\d', ks):
                kind = 'wan' if 3072 not in dims else 'other'
            elif 3072 in dims:
                kind = 'other'
        except (OSError, ValueError):
            pass
    _KIND[f] = (st.st_size, st.st_mtime, jm, kind)
    return kind


class Engine:
    proc, last, lock = None, 0, threading.Lock()

    @classmethod
    def alive(cls):
        import socket, netutil  # 先快速看端口有没有人在听：没开时 Windows 上 HTTP 连接要等 2 秒才失败，页面就卡住了
        if not netutil.maybe_up(PORT):  # 2026-11-08：连没人监听的端口在这台电脑上也要等满 0.3 秒——先看监听列表（约 1 毫秒）
            return False
        try:
            socket.create_connection(('127.0.0.1', PORT), timeout=0.3).close()
        except OSError:
            return False
        return cls.state(quick=True) in ('ready', 'starting')

    STARTING_GRACE = 300  # 我们的 ComfyUI 起来不到 5 分钟、还不回话：当成启动中 / 正在载入大模型

    @classmethod
    def _owner(cls):
        """端口上监听的是不是我们的 ComfyUI：True / False（别的程序）/ None（查不了）。返回 (是不是, 进程起来了多少秒)"""
        try:
            import psutil
            for c in psutil.net_connections('tcp'):
                if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == PORT and c.pid:
                    p = psutil.Process(c.pid)
                    cmd = ' '.join(p.cmdline())
                    ours = os.path.normcase(COMFY_MAIN) in os.path.normcase(cmd) or os.path.normcase(p.exe() or '').startswith(os.path.normcase(COMFY_DIR))
                    return ours, time.time() - p.create_time()
        except Exception:
            pass
        return None, 0

    @classmethod
    def state(cls, quick=False):
        """视频引擎现在的状态（2026-11-17 审查 F17：以前端口能连上、两次状态请求都失败也算“正常”）：
        down 没开 / ready 就绪 / starting 我们的 ComfyUI、还没回话（启动中、载入大模型时 Python 被卡住）/
        unresponsive 我们的 ComfyUI、很久不回话 / foreign 端口被别的程序占着"""
        import socket, netutil
        if not netutil.maybe_up(PORT):
            return 'down'
        try:
            socket.create_connection(('127.0.0.1', PORT), timeout=0.3).close()
        except OSError:
            return 'down'
        try:
            d = _http('/system_stats', timeout=2)
            return 'ready' if isinstance(d, dict) and 'system' in d else 'foreign'  # 回了话、但不像 ComfyUI
        except urllib.error.HTTPError:
            return 'foreign'
        except Exception:
            pass
        ours, age = cls._owner()
        if ours is False:
            return 'foreign'
        if ours is None:  # 查不了是谁：照以前当成我们的、启动中（不去另起一个抢端口）
            return 'starting'
        if quick or age < cls.STARTING_GRACE:
            return 'starting'
        try:  # 起来很久了还不回话：再给一次长一点的机会
            d = _http('/system_stats', timeout=20)
            return 'ready' if isinstance(d, dict) and 'system' in d else 'foreign'
        except Exception:
            return 'unresponsive'

    @classmethod
    def ensure(cls):
        with cls.lock:
            cls.last = time.time()
            st = cls.state()
            if st == 'starting':  # 我们的 ComfyUI 正在启动 / 载入：等它，不另起一个去抢端口（另起的会马上退出）
                for _ in range(480):
                    time.sleep(0.5)
                    st = cls.state()
                    if st != 'starting':
                        break
            if st == 'ready':
                return
            if st == 'foreign':
                raise RuntimeError(f'视频引擎的端口 {PORT} 被别的程序占用了，ComfyUI 起不来（关掉占用的程序后再试）')
            if st == 'unresponsive':
                raise RuntimeError('视频引擎（ComfyUI）很久没有响应：可以在设置里重启视频引擎，或稍后再试')
            if st == 'starting':
                raise RuntimeError('视频引擎启动超时，请查看 studio/comfy-engine.log')
            if not os.path.isfile(COMFY_PY):
                raise RuntimeError('尚未安装 ComfyUI（tools/ComfyUI_windows_portable）')
            for d in WORK.values():
                os.makedirs(os.path.join(d, 'in'), exist_ok=True); os.makedirs(os.path.join(d, 'out'), exist_ok=True)
            sweep_work()  # 上次崩溃 / 强制退出留下的中间文件（可能有私密任务的）：引擎重新启动时清掉
            act('正在启动视频引擎（ComfyUI，首次约 20~40 秒）…', 'video')
            log = open(LOG, 'w', encoding='utf-8', errors='replace')
            # 输入 / 输出放在普通空间的临时文件夹；私密空间的任务把文件放到自己的文件夹，做完立刻搬走 / 删掉
            cls.proc = subprocess.Popen([COMFY_PY, '-s', COMFY_MAIN, '--windows-standalone-build', '--listen', '127.0.0.1', '--port', str(PORT),
                                         '--disable-auto-launch', '--input-directory', os.path.join(WORK['n'], 'in'),
                                         '--output-directory', os.path.join(WORK['n'], 'out'), *EXTRA_ARGS],
                                        # 不再加 --disable-mmap：新版 ComfyUI 默认开着 Dynamic VRAM，模型按需从文件映射读进显存，
                                        # 这个参数在那条路上不起作用；万一退回旧的载入方式，它反而会把整个模型复制进内存、更慢
                                        cwd=os.path.join(COMFY_DIR, 'ComfyUI'), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                                        # 输出用 UTF-8（2026-11-13）：有的节点打印表情符号（latent 放大节点的 ✅），GBK 写不进日志就报错、整单卡死
                                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
            log.close()
            threading.Thread(target=cls.reaper, daemon=True).start()
            for _ in range(240):
                if cls.proc.poll() is not None:
                    raise RuntimeError('视频引擎启动失败，请查看 studio/comfy-engine.log')
                if cls.state(quick=True) == 'ready':
                    act('视频引擎就绪', 'video', 'ok')
                    return
                time.sleep(0.5)
            raise RuntimeError('视频引擎启动超时，请查看 studio/comfy-engine.log')

    _later = None

    _hold = False  # 做完一段、模型还留在显存里（等下一段）：别的功能要用显卡时先放掉（free_idle）

    @classmethod
    def free_later(cls, secs=150):
        """做完一段、队列空了：模型先留着一会儿——改个参数马上再生成时不用重新载入（2026-11-11 用户：每段都多花约两分钟把模型重新搬进显存）。
        有配音 / 生图在等就先放显存；这段时间里别的功能要用显卡会先调 free_idle 把显存让出来；一直没有新的视频任务，再连内存一起放掉"""
        if OTHERS_WAITING and OTHERS_WAITING():
            cls.free(keep_ram=True)
        else:
            cls._hold = True
        t = cls._later = threading.Timer(secs, lambda: cls._later is t and not _busy() and cls.free())
        t.daemon = True; t.start()

    @classmethod
    def free_idle(cls):
        """别的功能（配音、换声、识别、AI 助手、生图）要用显卡：视频没在做、模型还留在显存里时，先把显存放掉（模型留在内存里）"""
        if cls._hold and not _busy():
            cls._hold = False
            cls.free(keep_ram=True)

    @classmethod
    def cancel_later(cls):
        cls._later = None

    @classmethod
    def free(cls, keep_ram=False):  # 把模型从显存里放掉（引擎还开着，下次不用重新启动）
        cls._hold = False
        # keep_ram：模型留在内存里（下一个任务是同一个模型时才这样，载入快）；否则连内存一起放掉——
        # Wan 两个模型约 40GB，一直占着内存会把整台电脑拖慢，换模型时更会把内存挤爆
        try:
            _http('/free', {'unload_models': True, 'free_memory': not keep_ram}, timeout=20)
        except Exception:
            pass

    @classmethod
    def stop(cls):
        p, cls.proc = cls.proc, None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    @classmethod
    def shutdown(cls):
        """应用关闭时：自己开的和 Studio 重启前留下的那个（按端口 + 命令行确认）都关掉"""
        cls.stop()
        try:
            import psutil
            for c in psutil.net_connections('tcp'):
                if c.laddr and c.laddr.port == PORT and c.status == psutil.CONN_LISTEN and c.pid:
                    pr = psutil.Process(c.pid)
                    if 'main.py' in ' '.join(pr.cmdline()) and f'--port {PORT}' in ' '.join(pr.cmdline()):
                        pr.kill()
        except Exception:
            pass

    @classmethod
    def restart(cls):
        """重启视频引擎（2026-11-10：显存地址空间不够 / VBAR 时用）。Studio 重启前开的那个 ComfyUI 不在 cls.proc 里：按端口找到，命令行确认是它再关"""
        cls.stop()
        try:
            import psutil
            for c in psutil.net_connections('tcp'):
                if c.laddr and c.laddr.port == PORT and c.status == psutil.CONN_LISTEN and c.pid:
                    pr = psutil.Process(c.pid); cl = ' '.join(pr.cmdline())
                    if 'main.py' in cl and f'--port {PORT}' in cl:
                        pr.terminate()
                        try:
                            pr.wait(15)
                        except Exception:
                            pr.kill()
        except Exception:
            pass
        for _ in range(20):
            if not cls.alive():
                break
            time.sleep(0.5)
        cls.ensure()

    @classmethod
    def reaper(cls):
        p = cls.proc
        while p and p.poll() is None and cls.proc is p:
            time.sleep(20)
            if time.time() - cls.last > IDLE_EXIT and not any(j['state'] in ('queued', 'running') for j in list(jobs.values())):
                act('视频引擎闲置 30 分钟，已退出（释放内存）', 'video')
                cls.stop()


def vram_item():
    return {'id': 'video', 'name': '视频引擎（ComfyUI）', 'mb': 0} if Engine.proc and Engine.proc.poll() is None else None


# ---------------------------------------------------------------- 进度：读 ComfyUI 的 WebSocket（标准库里没有，自己写一个最小的客户端）
def _ws_progress(client_id, on_msg, stop):
    try:
        s = socket.create_connection(('127.0.0.1', PORT), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f'GET /ws?clientId={client_id} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                   f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            d = s.recv(4096)
            if not d:  # 对端关了：以前 recv 一直返回 b'' 死循环空转（2026-11-15 审查）
                return
            buf += d
        buf = buf.split(b'\r\n\r\n', 1)[1]
        s.settimeout(1.0)

        def need(n):
            nonlocal buf
            while len(buf) < n:
                if stop():
                    raise EOFError
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    raise EOFError
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out
        while not stop():
            b1, b2 = need(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack('>H', need(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', need(8))[0]
            data = need(n)
            if op == 1:
                try:
                    on_msg(json.loads(data.decode('utf-8', 'replace')))
                except ValueError:
                    pass
            elif op == 8:
                break
        s.close()
    except Exception:
        pass


# ---------------------------------------------------------------- 任务
jobs = {}
_q, _qcv = [], threading.Condition()
_index_lock = threading.Lock()


_made = {}  # 建过的文件夹 → 什么时候确认过（2026-11-11 体检：视频库接口每条视频都要 os.makedirs 好几次，几百条就是几百毫秒）


def _mkdir(d):
    """os.makedirs(d, exist_ok=True)，30 秒内确认过的不再问硬盘（文件夹被手动删了，30 秒后会重新建）"""
    t = time.time()
    if t - _made.get(d, 0) > 30:
        os.makedirs(d, exist_ok=True)
        _made[d] = t


def videos_dir(sp):
    d = DIRS[sp]; _mkdir(d)
    return d


# ---- 文件怎么放（2026-11-06 用户：产出的文件夹里非常乱、很多重复的）
# 外面只放成品（生成的、拼好的、合并 / 修剪出来的视频），名字是“月-日 时.分 做了什么”；
# 其余的都放进 _辅助文件：完整原视频（按内容只存一份，几段共用）、对比用的原视频、缩略图、播放副本。
# 视频库里记的还是文件名，真正放在哪由 vfile 决定；老的文件还在外面时照样找得到（ensure_layout 会把它们挪进去）。
AUX = '_辅助文件'
AUX_SUB = {'src': '原视频', 'cmp': '对比用', 'thumb': '缩略图', 'scrub': '播放副本', 'raw': '未调色'}


def _aux_kind(name):
    n = name.lower()
    if n.endswith('.scrub.mp4'):
        return 'scrub'
    if n.startswith('src-') or '_full.' in n:
        return 'src'
    if n.endswith('_src.mp4') or n.startswith('cmp-'):
        return 'cmp'
    if n.endswith('_raw.mp4'):  # 自动调色前的原样（2026-11-10）
        return 'raw'
    if n.endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return 'thumb'
    return None


def vfile(sp, name, root=None):
    """视频库里记的文件名 → 硬盘上的位置。成品在外面，辅助文件在 _辅助文件/<类>/；老位置还有就用老位置。"""
    name = os.path.basename(str(name or '')); root = root or videos_dir(sp); k = _aux_kind(name)
    if not k:
        return os.path.join(root, name)
    p = os.path.join(root, AUX, AUX_SUB[k], name)
    if not os.path.exists(p):
        old = os.path.join(root, name)
        if os.path.exists(old):
            return old
        _mkdir(os.path.dirname(p))
    return p


_seek_cache = {}


def seekable(path):
    """关键帧够密（开头两个关键帧相隔不超过 0.7 秒）：拖进度条本来就流畅，不需要播放副本（结果按文件的修改时间 / 大小缓存）"""
    try:
        st = os.stat(path)
    except OSError:
        return False
    k = (path, st.st_mtime, st.st_size)
    if k in _seek_cache:
        return _seek_cache[k]
    root = next((r for r in DIRS.values() if os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(r)) + os.sep)), None)
    disk = _seek_disk(root) if root else {}
    dk = f'{os.path.basename(path)}|{int(st.st_mtime)}|{st.st_size}'
    if dk in disk:  # 以前判断过（存在这个空间的 _辅助文件/.seek.json 里）：不再读文件
        _seek_cache[k] = disk[dk]
        return disk[dk]
    ok = False
    try:
        # 只看开头 2 秒（几十毫秒）：头两个关键帧隔了多久；不超过 0.7 秒就算够密（12 帧 = 24 fps 的半秒）
        r = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-read_intervals', '%+2', '-skip_frame', 'nokey', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0', path],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
        ts = sorted(float(x) for x in r.stdout.split() if x.strip().replace('.', '', 1).lstrip('-').isdigit())
        ok = len(ts) >= 2 and ts[1] - ts[0] <= 0.7
    except Exception:
        ok = False
    if len(_seek_cache) > 2000:
        _seek_cache.clear()
    _seek_cache[k] = ok
    if root:
        disk[dk] = ok
        try:
            f = os.path.join(root, AUX, '.seek.json'); os.makedirs(os.path.dirname(f), exist_ok=True)
            tmp = f + f'.{uuid.uuid4().hex[:6]}.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(disk, fh, ensure_ascii=False)
            os.replace(tmp, f)
        except OSError:
            pass
    return ok


_seek_disk_c = {}


def _seek_disk(root):
    if root not in _seek_disk_c:
        try:
            with open(os.path.join(root, AUX, '.seek.json'), encoding='utf-8') as f:
                _seek_disk_c[root] = json.load(f)
        except (OSError, ValueError):
            _seek_disk_c[root] = {}
    return _seek_disk_c[root]


def scrub_file(path):
    """生成的视频的播放副本放哪：_辅助文件/播放副本/（老的副本还在原视频旁边就用老的）"""
    old = path + '.scrub.mp4'
    pp = os.path.normcase(os.path.abspath(path))
    for root in DIRS.values():
        r = os.path.normcase(os.path.abspath(root))
        if pp.startswith(r + os.sep):
            if os.path.exists(old):
                return old
            d = os.path.join(root, AUX, AUX_SUB['scrub']); _mkdir(d)
            return os.path.join(d, os.path.basename(path) + '.scrub.mp4')
    return old


TASK_LABEL = {'swap': '换人', 'head': '换头', 'outfit': '改衣', 'motion': '动作迁移'}


def nice_name(sp, label, ext='.mp4', t=None):
    """成品的文件名：“11-06 21.30 改衣.mp4”，重名时加 (2)、(3)…"""
    bad = '<>:"/\\|?*\n\r\t'
    label = ''.join('_' if c in bad else c for c in str(label or '视频')).strip()[:40] or '视频'
    stem = time.strftime('%m-%d %H.%M', time.localtime(t or time.time())) + ' ' + label
    root = videos_dir(sp); n = 1
    while True:
        name = stem + (f' ({n})' if n > 1 else '') + ext
        if not os.path.exists(os.path.join(root, name)):
            return name
        n += 1


def item_label(x):
    """这条成品“做了什么”：改衣 / 换人 / H3 生视频 / 改衣 拼接 …"""
    e = x.get('edit') or {}
    base = TASK_LABEL.get(e.get('task'), '改视频') if e else \
        ('修剪' if x.get('model') == 'cut' else (str(x.get('model_name') or x.get('model') or '').split('·')[0].strip() + ' 生视频').strip())
    tail = (' 拼接' if x.get('spliced_of') else ' 续接合并' if x.get('merged') else ' 修剪' if x.get('cut_of') and x.get('model') != 'cut' else '')
    if x.get('parts_post') and x.get('spliced_of'):  # 拼接用的片段事后调色 / 超分过（整段没处理）：写成“片段调色”，和整段调色分开（2026-11-11）
        tail += '（片段' + x['parts_post'].split(' · ')[0] + '）'
    if x.get('upscaled_of'):  # 事后超分 / 插帧：在原来的名字后面加上做了什么
        tail += ' ' + (x.get('post_label') or '后处理')
    return base + tail


POST_KEYS = ('upscaled_of', 'post_label', 'color')  # “这条是某条事后处理出来的”：只属于那一条，拼接 / 合并时不能抄给新的成品


def _parts_post(its):
    """拼接用到的片段做过的事后处理（调色 · 匹配原视频 / 超分 …），没有就是 ''"""
    return ' + '.join(dict.fromkeys(x['post_label'] for x in its if x.get('upscaled_of') and x.get('post_label')))


def _sha16(path=None, data=None):
    import hashlib
    h = hashlib.sha256()
    if data is not None:
        h.update(data)
    else:
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
    return h.hexdigest()[:16]


def save_source(sp, data, ext='mp4'):
    """完整原视频按内容存一份（src-<内容指纹>.mp4），同一个原视频的几段都用这一份"""
    name = f'src-{_sha16(data=data)}.{ext}'
    p = vfile(sp, name)
    if not os.path.isfile(p):
        tmp = p + f'.{uuid.uuid4().hex[:6]}.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, p)
    return name


FILE_KEYS = ('file', 'thumb', 'src_file', 'splice_src', 'raw_file')
_layout_done = set()


def ensure_layout(sp):
    """老的视频库整理一次（每个空间只做一次，记在 _辅助文件/.layout2）：
    ① 完整原视频：内容一样的只留一份（按整个文件的 SHA-256 比，确实一模一样才删），改名 src-<指纹>，挪进 _辅助文件/原视频；
    ② 拼好的视频用的“对比用原视频”：同一个原视频、同样尺寸帧率的只留一份；
    ③ 对比用原视频、缩略图、播放副本挪进 _辅助文件 对应的子文件夹；
    ④ 成品改成“月-日 时.分 做了什么”的名字（先建硬链接、写好视频库、再删老名字：中途断电也不会丢）；
    ⑤ 外面剩下的、视频库里没有的旧文件（1 小时前的）挪进 _辅助文件/未引用的文件，不删。
    整理前先把 index.json 备份到 _辅助文件。"""
    if sp in _layout_done:
        return
    root = videos_dir(sp); aux = os.path.join(root, AUX); mark = os.path.join(aux, '.layout2')
    if os.path.isfile(mark):
        _layout_done.add(sp); return
    with _index_lock:
        try:
            items = _index_load(sp)
        except IndexUnreadable:
            return  # 索引读不出：这次不整理（以前当成空库，整理完写回空列表——F01），下次再试
        items = [x for x in items if isinstance(x, dict)]
        os.makedirs(aux, exist_ok=True)
        if items:
            shutil.copyfile(_index_path(sp), os.path.join(aux, time.strftime('index.整理前备份-%Y%m%d-%H%M%S.json')))
        top = lambda n: os.path.join(root, os.path.basename(n))
        drop, links = [], []  # 视频库写好后再删的老文件；建了硬链接的（新名字, 老名字）
        def move(name, new=None):  # 外面的老文件挪到它该在的地方（新名字可选）；返回记进视频库的名字
            new = new or name; src = top(name)
            if not os.path.isfile(src):
                return name  # 已经不在外面了（挪过 / 本来就在 _辅助文件 里）
            k = _aux_kind(new)
            dst = os.path.join(aux, AUX_SUB[k], new) if k else os.path.join(root, new)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.abspath(dst) == os.path.abspath(src):
                return new
            if os.path.exists(dst):
                drop.append(src)
            else:
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                drop.append(src)
            for s0 in (src + '.scrub.mp4',):  # 播放副本跟着走
                if os.path.isfile(s0):
                    d0 = os.path.join(aux, AUX_SUB['scrub'], new + '.scrub.mp4'); os.makedirs(os.path.dirname(d0), exist_ok=True)
                    if not os.path.exists(d0):
                        try:
                            os.link(s0, d0)
                        except OSError:
                            shutil.copy2(s0, d0)
                    drop.append(s0)
            return new
        srcs, cmps = {}, {}
        for x in items:
            f = x.get('splice_src')
            if f and os.path.isfile(top(f)) and not f.startswith('src-'):
                try:
                    h = srcs.get(f) or _sha16(top(f)); srcs[f] = h
                    x['splice_src'] = move(f, f'src-{h}{os.path.splitext(f)[1] or ".mp4"}')
                except OSError:
                    pass
            f = x.get('src_file')
            if f and x.get('spliced_of') and x.get('grp') and os.path.isfile(top(f)):  # 拼好的视频：整段原视频按成品尺寸处理的那份，同一组只留一份
                k = f"cmp-{x['grp']}-{x.get('width')}x{x.get('height')}-{x.get('fps')}fps.mp4"
                x['src_file'] = move(f, k); cmps[k] = 1
            elif f:
                x['src_file'] = move(f)
            if x.get('thumb'):
                x['thumb'] = move(x['thumb'])
        for x in items:  # 成品改名
            f = x.get('file')
            if not f or not os.path.isfile(top(f)) or _aux_kind(f):
                continue
            if re.match(r'^\d\d-\d\d \d\d\.\d\d ', f):
                continue
            new = nice_name(sp, item_label(x), os.path.splitext(f)[1] or '.mp4', x.get('created'))
            try:
                os.link(top(f), os.path.join(root, new))
            except OSError:
                continue  # 建不了硬链接（极少）：这个就不改名
            links.append((new, f)); x['file'] = new
            s0 = top(f) + '.scrub.mp4'
            if os.path.isfile(s0):
                d0 = os.path.join(aux, AUX_SUB['scrub'], new + '.scrub.mp4'); os.makedirs(os.path.dirname(d0), exist_ok=True)
                if not os.path.exists(d0):
                    try:
                        os.link(s0, d0)
                    except OSError:
                        shutil.copy2(s0, d0)
                drop.append(s0)
            drop.append(top(f))
        tmp = _index_path(sp) + f'.{uuid.uuid4().hex[:6]}.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(items, fh, ensure_ascii=False)
        os.replace(tmp, _index_path(sp))
        for p in dict.fromkeys(drop):  # 视频库已经指向新位置：老文件可以删了（硬链接 / 复制过的；一模一样的原视频）
            try:
                os.remove(p)
            except OSError:
                pass
        used = {os.path.basename(str(x.get(k))) for x in items for k in FILE_KEYS if x.get(k)}
        old = time.time() - 3600; un = os.path.join(aux, '未引用的文件')
        for n in os.listdir(root):
            p = os.path.join(root, n)
            if not os.path.isfile(p) or n == 'index.json' or n.endswith('.tmp') or n in used or os.path.getmtime(p) > old:
                continue
            base = n[:-len('.scrub.mp4')] if n.endswith('.scrub.mp4') else n
            if base in used:
                continue
            os.makedirs(un, exist_ok=True)
            try:
                os.replace(p, os.path.join(un, n))
            except OSError:
                pass
        with open(mark, 'w', encoding='utf-8') as fh:
            fh.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    _layout_done.add(sp)


def _index_path(sp):
    return os.path.join(videos_dir(sp), 'index.json')


def _pending_path(sp):
    return os.path.join(videos_dir(sp), 'index.pending.jsonl')


class IndexUnreadable(ValueError):
    """视频库索引存在但读不出：不能当成空库写回（以前会把整个视频库覆盖成只剩新的一条，2026-11-17 审查 F01）"""


_index_warned = set()


def _index_load(sp):
    """写入用的原始索引：文件不存在 = 第一次建库（[]）；存在但读不出 / 内容不对 → IndexUnreadable。
    注意别用 gallery()：那是给界面看的，文件暂时找不到的条目会被滤掉，拿它写回会丢记录"""
    p = _index_path(sp)
    try:
        with open(p, encoding='utf-8') as f:
            items = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        raise IndexUnreadable(f'视频库索引读不出（{type(e).__name__}: {e}）：为保护已有记录暂不写入，新成品先记在 index.pending.jsonl，修好 index.json 后会自动并回') from e
    if not isinstance(items, list):
        raise IndexUnreadable('视频库索引内容不对（不是列表）：为保护已有记录暂不写入')
    return items


def _index_write(sp, items):
    tmp = _index_path(sp) + f'.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)
    os.replace(tmp, _index_path(sp))


def _pending_read(sp):
    try:
        with open(_pending_path(sp), encoding='utf-8') as f:
            out = []
            for line in f:
                try:
                    x = json.loads(line)
                    if isinstance(x, dict):
                        out.append(x)
                except ValueError:
                    pass
            return out
    except OSError:
        return []


def gallery(sp):
    """给界面 / 查询看的视频库（只留文件还在的）。写入一律用 _index_load"""
    try:
        items = _index_load(sp)
    except IndexUnreadable as e:
        items = []
        if sp not in _index_warned:
            _index_warned.add(sp)
            act(str(e), 'video', 'warn')
    items = [x for x in _pending_read(sp) if isinstance(x, dict)] + items  # 索引坏了时先记下的新成品也显示出来
    # 只留文件还在的：成品都在外面一层，列一次文件夹比每条问一次硬盘快得多（几百条视频时差几百毫秒）；辅助文件类的名字照旧一条条看
    root = videos_dir(sp)
    try:
        here = {e.name.lower() for e in os.scandir(root) if e.is_file()}  # Windows 的文件名不分大小写
    except OSError:
        here = None  # 列不出文件夹：逐条问（不能当成都不在）

    def ok(x):
        n = os.path.basename(str(x.get('file') or ''))
        if not n:
            return False
        if here is None or _aux_kind(n):
            return os.path.isfile(vfile(sp, n))
        return n.lower() in here
    seen = set()
    out = []
    for x in items:
        if isinstance(x, dict) and ok(x) and x.get('id') not in seen:
            seen.add(x.get('id')); out.append(x)
    return out


def gallery_get(gid, sp):
    return next((x for x in gallery(sp) if x.get('id') == gid), None) if gid else None


QC_FILE = os.path.join(ROOT, 'outputs', 'video-qc.json')  # 自动质检开关（两个空间共用；默认关）


def qc_on():
    try:
        with open(QC_FILE, encoding='utf-8') as f:
            return json.load(f).get('on') is True
    except (OSError, ValueError):
        return False


def qc_set(on):
    os.makedirs(os.path.dirname(QC_FILE), exist_ok=True)
    with open(QC_FILE, 'w', encoding='utf-8') as f:
        json.dump({'on': bool(on)}, f)


def _index_set(sp, iid, fields):
    """视频库里某一条加 / 改几个字段（量帧差、质检结果……）"""
    with _index_lock:
        try:
            items = _index_load(sp)  # 读不出 → IndexUnreadable（属于 ValueError，下面的 except 接住，不写）
            for x in items:
                if isinstance(x, dict) and x.get('id') == iid:
                    x.update(fields)
            tmp = _index_path(sp) + f'.{uuid.uuid4().hex[:6]}.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
            os.replace(tmp, _index_path(sp))
        except (OSError, ValueError):
            pass


def qc_run(sp, iid):
    """查一条（qc.py，CPU）：改视频和原视频对照；结果记进视频库的 qc"""
    import qc
    x = gallery_get(iid, sp)
    if not x:
        return None
    src = vfile(sp, x['src_file']) if x.get('edit') and x.get('src_file') and os.path.isfile(vfile(sp, x['src_file'])) else None
    lag = ensure_lag(iid, sp) if src else 0.0
    try:
        r = qc.check(vfile(sp, x['file']), FFMPEG, src, max(0.0, float(lag or 0)), face=(x.get('edit') or {}).get('task') == 'outfit')
    except Exception as e:
        r = {'v': 1, 'flags': [], 'skip': f'质检出错：{e}'[:200]}
    _index_set(sp, iid, {'qc': r})
    if r.get('flags'):
        act(f'自动质检：{len(r["flags"])} 处可能有问题（' + '、'.join(dict.fromkeys(f['msg'] for f in r['flags'])) + '）', 'video', 'warn')
    return r


def qc_later(sp, iid):
    if qc_on():
        threading.Thread(target=qc_run, args=(sp, iid), daemon=True).start()


def _gallery_add(sp, item):
    """新成品加进视频库：以原始索引为底（不是界面看的过滤后列表）；索引读不出时先记进 index.pending.jsonl 并报错（成品文件保留，可恢复）"""
    with _index_lock:
        try:
            items = _index_load(sp)
        except IndexUnreadable:
            with open(_pending_path(sp), 'a', encoding='utf-8') as f:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
            raise
        pend = _pending_read(sp)
        have = {x.get('id') for x in items if isinstance(x, dict)} | {item.get('id')}
        items = [item] + [x for x in pend if x.get('id') not in have] + items
        _index_write(sp, items)
        if pend:
            try:
                os.remove(_pending_path(sp))
            except OSError:
                pass
        _index_warned.discard(sp)


def gallery_delete(ids, sp):
    with _index_lock:
        allx = [x for x in _index_load(sp) if isinstance(x, dict)]  # 读不出就报错、什么都不删（以前当成空库，写回空列表）
        pend = _pending_read(sp)
        if pend and any(x.get('id') in ids for x in pend):  # 删的是索引坏时先记下的条目：从待并回的里去掉
            rest = [x for x in pend if x.get('id') not in ids]
            with open(_pending_path(sp), 'w', encoding='utf-8') as f:
                f.writelines(json.dumps(x, ensure_ascii=False) + '\n' for x in rest)
        keep = [x for x in allx if x.get('id') not in ids]
        # 完整原视频、拼接的对比用原视频是几条共用的（2026-11-06 起按内容只存一份）：还有别的条目在用就不删
        used = {os.path.basename(str(x.get(k))) for x in keep for k in FILE_KEYS if x.get(k)}
        stuck = []  # 成品视频删不掉（被占用）的条目：留在库里，报错（第二轮审查 9）
        for x in allx:
            if x.get('id') in ids:
                main = x.get('file')
                if main:
                    try:
                        os.remove(vfile(sp, main))
                    except FileNotFoundError:
                        pass
                    except OSError:
                        stuck.append(x); continue
                for f in (x.get(k) for k in FILE_KEYS):
                    if f and os.path.basename(f) not in used:
                        p = vfile(sp, f)
                        for g in (p, scrub_file(p)):  # 连同播放副本
                            try:
                                os.remove(g)
                            except OSError:
                                pass
        keep += stuck
        _index_write(sp, keep)
        qk = {str((x.get('edit') or {}).get('qshare')) for x in keep if (x.get('edit') or {}).get('qshare')}
        qd = os.path.join(videos_dir(sp), AUX, '共用衣服图')
        if os.path.isdir(qd):
            for n in os.listdir(qd):
                if n.endswith('.png') and n[:-4] not in qk and any((x.get('edit') or {}).get('qshare') == n[:-4] for x in allx):
                    try:
                        os.remove(os.path.join(qd, n))
                    except OSError:
                        pass
        used = {n for x in keep for n in ((x.get('redo') or {}).get('vid'), (x.get('redo') or {}).get('img')) if n}
        rd = os.path.join(videos_dir(sp), 'redo')
        if os.path.isdir(rd):
            for n in os.listdir(rd):
                if n not in used:
                    try:
                        os.remove(os.path.join(rd, n))
                    except OSError:
                        pass


def _redo_save(sp, b, vid, img):
    """改视频的成品：记下当时的请求，原视频 / 人物图按内容存到 videos/redo（同样的文件只存一份）"""
    import hashlib, videoedit
    rd = os.path.join(videos_dir(sp), 'redo'); os.makedirs(rd, exist_ok=True)
    def put(data, ext):
        if not data:
            return None
        n = hashlib.sha1(data).hexdigest()[:20] + '.' + ext
        p = os.path.join(rd, n)
        if not os.path.isfile(p):
            with open(p + '.tmp', 'wb') as f:
                f.write(data)
            os.replace(p + '.tmp', p)
        return n
    ik = 'png' if img and img[:8] == b'\x89PNG\r\n\x1a\n' else 'webp' if img and img[8:12] == b'WEBP' else 'jpg'
    return {'b': b, 'vid': put(vid, videoedit.video_kind(vid) or 'mp4') if vid else None, 'img': put(img, ik) if img else None}


def redo_prompt(iid, sp):
    """重新生成前弹出的提示词框里放什么：当时输入的原话（没有就用发出去的那句）"""
    rec = (gallery_get(iid, sp) or {}).get('redo') or {}
    r = rec.get('b') or {}
    e = r.get('edit') if isinstance(r.get('edit'), dict) else None
    # pv：弹窗里“查看完整提示词”用（2026-11-10 用户：以前只显示框里的原话、看不到模板）——当时的设置，按它拼出这次真正会发出去的内容
    # has_ref 和生成时一样：放了图才算
    pv = {'edit': e, 'seconds': r.get('seconds'), 'sent': r.get('prompt'),
          'has_ref': bool(rec.get('img'))} if e else None
    return {'prompt': str(r.get('prompt_input') if r.get('prompt_input') is not None else r.get('prompt') or ''), 'edit': bool(r.get('edit')),
            'start': (e or {}).get('start'), 'end': (e or {}).get('end'), 'tpl': (e or {}).get('tpl', True), 'pv': pv}


def redo_input(iid, sp, prompt=None, tpl=None):
    """重新生成：照这段成品当时的设置、原视频、片段和人物图再排一次（换一个随机种子）→ (请求, 人物图, 原视频)。
    prompt：弹出的提示词框里改过的提示词（2026-11-06 用户）；None = 不改
    tpl：弹窗里的「使用模板」（2026-11-11 用户：复制完整提示词来改时要能关掉模板，不然又被套进模板）；None = 按当时的"""
    x = gallery_get(iid, sp)
    r = (x or {}).get('redo')
    if not r or not r.get('vid'):
        raise ValueError('这段视频没有记下生成时的原视频和设置，无法重新生成（2026-11-05 之前生成的不支持）')
    rd = os.path.join(videos_dir(sp), 'redo')
    def get(n):
        if not n:
            return None
        p = os.path.join(rd, os.path.basename(n))
        if not os.path.isfile(p):
            raise ValueError('重新生成所需的原视频 / 人物图已不在了')
        with open(p, 'rb') as f:
            return f.read()
    b = {**r['b'], 'seed': -1}
    if prompt is not None:
        p = str(prompt)[:4000]
        old = r['b'].get('prompt_input') if r['b'].get('prompt_input') is not None else r['b'].get('prompt')
        if p.strip() != str(old or '').strip():  # 真的改了：原话和发出去的都换成新的
            b['prompt'] = b['prompt_input'] = p
            if isinstance(b.get('edit'), dict) and b['edit'].get('plang') == 'en' and re.search(r'[一-鿿]', p):
                b['edit'] = {**b['edit'], 'plang': 'zh'}  # 以前按英文模板生成、这次写的是中文：按中文模板（不然英文模板里夹中文）
    if isinstance(tpl, bool) and isinstance(b.get('edit'), dict) and b['edit'].get('tpl', True) is not tpl:
        b['edit'] = {**b['edit'], 'tpl': tpl}  # 只换模板开关：其余设置（跳过 Qwen 等）照当时的
        if not tpl and not str(b.get('prompt') or '').strip():
            raise ValueError('关掉模板时请填写完整的提示词')
    return b, get(r.get('img')), get(r['vid'])


def video_path(name, sp):
    name = os.path.basename(str(name))
    p = vfile(sp, name)
    return p if name and os.path.isfile(p) else None


def public(j):
    d = {k: v for k, v in j.items() if not k.startswith('_')}
    tr = getattr(j, 'track', None)
    d['timing'] = tr.export() if tr else None  # 计时：开始了多久、每一步用了几秒
    return d


def prep_result(jid, sp):
    """只准备的那一单做好的参考图和名字（data URL 太大，不放进任务列表）"""
    j = jobs.get(jid)
    return j.get('_prep') if j and j.get('space') == sp else None


def list_jobs(sp, limit=30):
    """排队 / 正在做的全部列出（不管有多少、多早），后面跟最新的已结束的 limit 条。
    2026-11-17 审查 F10：以前一共只给最新 30 条，批量一次排进几十单时，更早排的那些在列表和 Agent 里都查不到"""
    mine = sorted((j for j in jobs.values() if j['space'] == sp), key=lambda x: -x['created'])
    live = [j for j in mine if j['state'] in ('queued', 'running')]
    done = [j for j in mine if j['state'] not in ('queued', 'running')][:limit]
    return [public(j) for j in sorted(live + done, key=lambda x: -x['created'])]


def get_job(jid, sp):
    """按编号查一单（不受列表条数限制）"""
    j = jobs.get(jid)
    return public(j) if j and j.get('space') == sp else None


def _num(v, lo, hi, dflt, cast=float):  # 数字参数：空 / 不是数字 → 默认；超出范围 → 夹到范围里
    if v is None or v == '':
        return dflt
    try:
        x = cast(float(v))
    except (TypeError, ValueError, OverflowError):
        return dflt
    return max(lo, min(hi, x))


def _res(v, step=32):
    """自定义分辨率：'640'（短边，长边按原图比例）或 '832x480'。返回 None / ('s', 短边) / ('wh', 宽, 高)。
    step：取整的倍数（Wan 16、H3 32）。"""
    s = str(v or '').strip().lower().replace('×', 'x').replace('*', 'x').replace(' ', '')
    if not s:
        return None
    m = re.fullmatch(r'(\d{3,4})p?', s)
    if m:
        n = int(m.group(1))
        if not 256 <= n <= 1088:
            raise ValueError('自定义分辨率的短边须在 256 ~ 1088 之间')
        return ('s', max(256, round(n / step) * step))
    m = re.fullmatch(r'(\d{3,4})x(\d{3,4})', s)
    if not m:
        raise ValueError('自定义分辨率请填写为 640 或 832x480 的形式')
    w, h = (max(256, round(int(x) / step) * step) for x in m.groups())
    if max(w, h) > 1920 or w * h > 1_000_000:
        raise ValueError('自定义分辨率过大：最多约 100 万像素（如 1280x768）')
    return ('wh', w, h)


def _tune(key, b, steps):
    """高级参数：只认这个模型有的，夹到合理范围；没填的用默认（= 原来的行为）。"""
    d, out = TUNE[key], {}
    smp, sch = sampler_options()
    out['sampler'] = b.get('sampler') if b.get('sampler') in smp else d['sampler']
    out['scheduler'] = b.get('scheduler') if b.get('scheduler') in sch else d['scheduler']
    out['shift'] = round(_num(b.get('shift'), 0.5, 30.0, d['shift']), 2)
    out['ashift'] = round(_num(b.get('ashift'), 0.5, 30.0, d['ashift']), 2)
    out['audio'] = d['audio'] if b.get('audio') is None else bool(b.get('audio'))
    fps = _num(b.get('fps'), 8, 30, None, int)
    out['fps'] = fps if fps and fps != MODELS[key]['fps'] else None  # 不填 = 模型自己的（Wan 16 / H3 24）
    ix = _num(b.get('interp_x'), 1, 4, 2 if b.get('interp') else 1, int)  # 插帧倍数：1 = 不插，2~4 倍
    out['interp'], out['interp_x'], out['upscale'] = ix > 1, ix, bool(b.get('upscale'))
    out['interp_by'] = b.get('interp_by') if b.get('interp_by') in ('rife', 'film', 'ff') else 'rife'
    have, ls = set(lora_files()), []
    e = b.get('edit') if isinstance(b.get('edit'), dict) else {}
    lk = key
    for x in (b.get('loras') or [])[:4] if isinstance(b.get('loras'), list) else []:  # 自选 LoRA：最多 4 个，只要这个模型能用的（看不出来的也放行）
        if isinstance(x, dict) and x.get('name') in have and lora_kind(x['name']) in (lk, '?'):
            ls.append({'name': x['name'], 'w': round(_num(x.get('w'), -2.0, 3.0, 1.0), 2), 'on': x.get('on') if x.get('on') in ('both', 'high', 'low') else 'both'})
    out['loras'] = ls
    return out


# 生视频的底模（H3）：官方完整版 int8（只有首帧 / 关键帧时 FL2VA，用了参考图 / 视频 / 音频时 Ref2VA）+ int8 文字编码器，
# 没合并加速：默认 20 步，可叠官方加速 LoRA
GEN_BASES = ('official',)
OFFICIAL_STEPS = 20


def official_ok():
    return {k: _have(H3_FULL[k]) and _have(H3_TE['int8']) for k in ('fl2va', 'ref2va')}


def submit(b, image_bytes, ffmpeg, end_bytes=None, video_bytes=None, extra=None):
    """b：model、prompt、negative、seconds、size、steps、seed 和高级参数；image_bytes：首帧（PNG / JPG / WebP），end_bytes：尾帧（可选）。
    改视频（b['edit']）：video_bytes 是原视频，image_bytes 是人物图 / 衣服图（可选），见 videoedit.py。
    extra：H3 的更多条件（关键帧、开头片段、指定声音、参考图 / 视频 / 音频），见 h3extra.py。"""
    import h3extra  # 它也 import 本文件：放在这里
    edit = None
    redo_b = {k: v for k, v in b.items() if k not in ('video', 'init')} if b.get('edit') else None  # 重新生成用：原样的设置（原视频、人物图另外存）
    if b.get('edit'):
        import videoedit
        edit = videoedit.parse(b, video_bytes, image_bytes)
        b = {**b, 'model': 'h3', 'chain_of': None}
        end_bytes = None
    key = 'h3'  # Wan 2.2 去掉了（2026-11-06 用户）：只有 H3。旧记录里 model 是 wan 的，重新生成也走这里，按 H3 做（2026-11-17 审查 C02 清掉了 Wan 的生成分支）
    miss = missing(key)
    if miss:
        raise RuntimeError('以下文件尚未下载：' + '、'.join(miss))
    prompt = str(b.get('prompt') or '').strip()[:4000]
    if not prompt and edit and not edit.get('tpl', True) and not edit.get('own'):
        raise ValueError('关闭模板后，提示词将原样发送给模型，请写完整')
    if not prompt and not (edit and (edit['task'] in ('swap', 'head', 'motion') or (edit['task'] == 'outfit' and edit['ref'] and (edit['tpl'] or edit.get('method') in ('animate', 'bernini', 'ref'))))):
        raise ValueError('关闭模板后，提示词将原样发送给模型，请写完整' if edit and edit['task'] == 'outfit' and not edit['tpl']
                         else {'outfit': '请写明要换成的衣服（或放入一张衣服图）'}.get(edit and edit['task'], '请描述画面中要发生的内容'))
    if image_bytes is not None and len(image_bytes) < 100:
        image_bytes = None
    if not edit and b.get('chain_of') and image_bytes is None:  # 续接却没带首帧（网页总会带上最后一帧）：自己取那段的最后一帧，
        try:  # 以前会凭空生成一段不相关的再合并上去（2026-11-06 测试发现）
            image_bytes = base64.b64decode(last_frame(str(b['chain_of']), space(), ffmpeg)['data'].split(',', 1)[1])
        except (ValueError, OSError, KeyError):
            pass
    extra = extra if not edit else None  # 更多条件（关键帧、开头片段、声音、参考）只有 H3 有，见 h3extra.py
    if extra and extra.get('clip') and image_bytes:
        raise ValueError('开头片段和首帧都位于第 0 帧，只能二选一')
    if extra and extra.get('guide') and (image_bytes or extra.get('clip')):
        raise ValueError('引导视频从第 0 帧开始逐帧引导：与首帧、开头片段只能择一使用')
    import h3methods
    gbase = None if edit else 'official'  # 生视频只有官方原版；改视频的底模由 videoedit.parse 定
    # 做法 ①②：官方底模（生视频“官方原版”、改视频参考生成的“官方完整版”）默认用 ② 他的节点，其余是 ①，见 h3methods.py
    refs = bool(not edit and extra and extra.get('rvids'))  # 生视频放了参考视频（拿它的动作当参考）：自动时用 ①；改视频的参考生成也用 ②（2026-11-04 用户定）
    engine = h3methods.pick(b.get('engine'), gbase == 'official' or bool(edit and videoedit.is_ref(edit) and edit['base'] == 'full'), extra, refs)
    if edit and edit.get('ffguide') and edit.get('own') and not edit.get('ff_own'):  # 不经过 Qwen（没有第 0 帧换好的图）：锁不了，也就不用换慢的引擎（2026-11-06）
        edit['ffguide'] = False
    if edit and edit.get('ffguide') and videoedit.is_ref(edit):  # 首帧锁定：② 节点不支持“参考 + 首帧”（“T8 Hybrid path is disabled”），用 ①
        engine = '1'
    if edit and edit.get('recipe'):  # 换人 · 新做法 / 动作迁移：原视频走 AddGuide（逐帧引导），② 接不了，固定 ①
        edit['ffguide'] = False
        engine = '1'
    if edit and edit.get('vg'):  # 改衣 · Viggle 重拍：Viggle 自己的接法，只在 ① 原生节点上；尺寸由 videoedit.prepare 定（短边 480 / 736），不用自定义分辨率
        edit['ffguide'] = False
        engine = '1'
        b = {**b, 'res': ''}
    if edit and (edit.get('loc') or {}).get('native'):  # 局部修改（原生）只接在 ② 上（h3methods.to_t8 把采样换成原视频 latent + mask），① 上会变成没有 mask 的普通生成
        edit['ffguide'] = False
        engine = '2'
    if edit and videoedit.LOC_SIZE and (edit.get('loc') or {}).get('native') and (b.get('size') != videoedit.LOC_SIZE or b.get('res')):  # 局部修改（原生）：只在 480p 测过逐帧一致，720p 会中途变回原来的衣服
        b = {**b, 'size': videoedit.LOC_SIZE, 'res': ''}  # 自定义分辨率也不用
    h3o = _h3opt_in(b) or {}
    if gbase == 'official':  # 官方完整版：用了参考就是 Ref2VA，否则 FL2VA
        kind = 'ref2va' if h3extra.ref_mode(extra) else 'fl2va'
        if not official_ok()[kind]:
            raise RuntimeError(f'官方底模尚未放入：{os.path.basename(H3_FULL[kind])}、{os.path.basename(H3_TE["int8"])}')
        h3o = {**h3o, 'base': kind, 'te': 'int8'}
    m = MODELS[key]
    emax = videoedit.max_seconds(edit) if edit else MAX_SECONDS[key]  # 改视频：每种做法本身的硬上限（拖动条只到 10 / 15 秒，数字框能填到这里）
    secs = max(1 if edit else 2, min(emax, int(float(b.get('seconds') or m['defaults']['seconds']))))
    if edit:  # 改视频：记下选的确切时长（选段的结束点常是小数秒；secs 取整会少生成零点几秒，拼接时结尾又变回原视频，2026-11-05）
        try:
            edit['want'] = round(max(1.0, min(float(emax), float(b.get('seconds') or secs))), 3)
        except (TypeError, ValueError):
            edit['want'] = float(secs)
    slow = (edit and edit['base'] in ('official', 'full')) or gbase == 'official'  # 官方底模没合并加速：默认 20 步
    steps = max(1, min(40, int(float(b.get('steps') or (OFFICIAL_STEPS if slow else m['defaults']['steps'])))))
    if engine == '2':  # ② 用他的采样设置（视频 / 声音各 14 步），网页上不能改；测试脚本可以传 t8_steps（2026-11-10 试官方建议的 20–25 步）
        steps = max(4, min(40, int(b['t8_steps']))) if isinstance(b.get('t8_steps'), int) else h3methods.T8_STEPS
    # 加速 LoRA：生视频用了参考 = Ref2VA，否则 FL2VA；改视频都是 Ref2VA
    tkind = ('ref2v' if edit or h3extra.ref_mode(extra) else 'fl2v') if (edit and edit['base'] in ('official', 'full')) or gbase == 'official' else None
    # 2026-11-12 用户定：480p 一律不用加速 LoRA（装的两个都是 768p 版，480p 上动作跟不上、手糊；480p 不加速也够快）
    try:
        _r = _res(b.get('res'), RES_STEP[key]) if key in RES_STEP else None
    except ValueError:
        _r = None
    low = (min(_r[1], _r[2]) if _r[0] == 'wh' else _r[1]) <= 544 if _r else (b.get('size') if b.get('size') in SIZES else m['defaults']['size']) == '480p'
    turbo = _turbo_in(b, tkind) if not low else None
    if edit and edit.get('recipe'):  # 作者配方自带 DMD 8 步加速（作者示例都是这一套，和网页上的加速 LoRA 选项无关）
        turbo = dict(videoedit.DMD_TURBO)
    if edit and edit.get('task') == 'head' and edit.get('head_by') == 'fs':  # 换头 · 换脸 LoRA：作者工作流配官方加速 8 步（夜测 N3 同一套）；480p 照样不加速
        hd = [x for x in turbo_list() if x['kind'] == 'ref2v' and x['steps'] == 8 and x['hd']]
        turbo = None if low or not hd else {'lora': hd[-1]['file'], 'steps': 8, 'shift': hd[-1]['shift'], 'ashift': hd[-1]['ashift'], 'kind': 'ref2v'}
    if edit and edit.get('vg'):  # Viggle 重拍：自己的 6 步，不接加速 LoRA
        turbo = None
    if turbo:
        steps = turbo['steps']
    if edit and edit.get('vg'):
        steps = 6
    size = b.get('size') if b.get('size') in SIZES else m['defaults']['size']
    try:
        seed = int(b.get('seed', -1))
    except (TypeError, ValueError):
        seed = -1
    if seed < 0:
        seed = random.randint(0, 2 ** 31 - 1)
    sp = space()
    res = _res(b.get('res'), RES_STEP[key])
    if res:
        size = f'{res[1]}p' if res[0] == 's' else f'{res[1]}×{res[2]}'
    chain = gallery_get(str(b.get('chain_of') or ''), sp)  # 续接：接在哪段视频后面（做完再合成一段完整的）
    if end_bytes is not None and len(end_bytes) < 100:
        end_bytes = None
    tune = _tune(key, b, steps)
    if extra and (extra.get('audio') or extra.get('lock') is not None or (extra.get('guide') or {}).get('audio')):  # 指定了声音 / 锁定了原声：视频里要有声音
        tune['audio'] = True
    if edit:  # 改视频：照原视频的 24 fps；保留原声 / 不要声音时不解码模型生成的声音
        tune['fps'] = None
        tune['audio'] = edit['audio'] == 'gen' and tune['audio']
    fps = tune['fps'] or m['fps']
    if not edit:  # 帧率调高时帧数会超过模型能做的长度：缩短时长（改视频按原视频的帧率，长度上限见 videoedit.max_seconds）
        secs = max(2, min(secs, (MAX_FRAMES[key] - 1) // fps))
    j = stages.JobDict({'id': datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4], 'space': sp, 'state': 'queued', 'model': key,
         'model_name': (('MiniMax H3 · 官方精简' if edit.get('lite') else 'MiniMax H3 · 官方') if edit['base'] == 'full' else 'MiniMax H3 · 官方原版' if edit['base'] == 'official' else m['name']) if edit
         else ('MiniMax H3 · 官方完整版（' + ('Ref2VA' if h3extra.ref_mode(extra) else 'FL2VA') + '）' if gbase == 'official' else m['name']), 'engine': engine, 'base': gbase if not edit else edit['base'],
         'prompt': prompt, 'negative': '', 'seconds': secs, 'steps': steps, 'size': size, 'seed': seed,
         'created': time.time(), 'finished': None, 'progress': 0, 'message': '排队中', 'error': '', 'cancel': False, 'file': None,
         'src_id': b.get('src_id'),
         'res': res, 'chain_of': chain['id'] if chain else None, 'flf': end_bytes is not None, 'end_id': b.get('end_id') if end_bytes is not None else None,
         **tune, 'edit': edit, 'src_vid': b.get('src_vid') if edit else None, '_img': image_bytes, '_end': end_bytes, '_vid': video_bytes if edit else None, '_ffmpeg': ffmpeg,
         '_x': extra, 'h3x': h3extra.summary(extra), '_h3opt': h3o or None, '_turbo': turbo, 'turbo': turbo,
         '_redo': (redo_b, video_bytes, image_bytes) if edit and redo_b is not None else None})
    j['prompt_trace'] = prompttrace.new(b.get('prompt_input', b.get('prompt', '')))
    jobs[j['id']] = j
    with _qcv:
        _q.append(j); _qcv.notify()
    for old in sorted((x for x in list(jobs.values()) if x['state'] in ('done', 'error', 'cancelled')), key=lambda x: x['created'])[:-30]:
        jobs.pop(old['id'], None)
    return public(j)


def _qshare_path(sp, key):
    return os.path.join(videos_dir(sp), AUX, '共用衣服图', re.sub(r'[^0-9A-Za-z_-]', '', str(key))[:40] + '.png')


def qshare_get(sp, key):
    """多段改衣共用的衣服图（同一批第一段 Qwen 换好的）：有就返回 PNG 内容"""
    if not key:
        return None
    try:
        with open(_qshare_path(sp, key), 'rb') as f:
            return f.read()
    except OSError:
        return None


def qshare_put(sp, key, data):
    p = _qshare_path(sp, key); os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + f'.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, p)


TURBO_RE = re.compile(r'minimax_h3_(fl2v|ref2v)_turbo_(\d+)step', re.I)


def turbo_list():
    """loras 里的 lightx2v 官方加速 LoRA：kind = fl2v（生视频只有首帧 / 首尾帧，FL2VA）/ ref2v（用了参考、改视频，Ref2VA）；
    步数看文件名；768p 版作者推荐偏移 6 / 3，旧版 12 / 3（2026-11-06 A/B 用的就是这两套）"""
    d = os.path.join(MODELS_DIR, 'loras')
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    out = []
    for f in names:
        m = TURBO_RE.search(f)
        if not m or not f.lower().endswith('.safetensors'):
            continue
        hd, v = '768p' in f.lower(), re.search(r'_v(\d+(?:\.\d+)?)', f)
        out.append({'file': f, 'kind': m.group(1).lower(), 'steps': int(m.group(2)), 'shift': 6.0 if hd else 12.0, 'ashift': 3.0, 'ver': v.group(1) if v else '', 'hd': hd})
    return sorted(out, key=lambda x: (x['kind'], -x['steps'], x['ver']))  # 按钮从多步到少步排


def _turbo_in(b, kind):
    """加速 LoRA（默认不用）。网页发 turbo = {fl2v: 文件名, ref2v: 文件名}：按这次实际用的底模（kind：'fl2v' / 'ref2v'）挑对应的那个，
    步数、偏移跟着它。测试参数 h3turbo = {lora, steps, shift, ashift} 原样用（① ② 都接）"""
    t = b.get('h3turbo') if isinstance(b.get('h3turbo'), dict) else None
    if t:
        name = os.path.basename(str(t.get('lora') or ''))
        if not name or not _have('loras/' + name):
            raise ValueError('加速 LoRA 不存在：' + name)
        return {'lora': name, 'steps': int(_num(t.get('steps'), 1, 40, 8, int)), 'shift': float(_num(t.get('shift'), 0.5, 30.0, 12.0)), 'ashift': float(_num(t.get('ashift'), 0.5, 30.0, 3.0))}
    w = b.get('turbo') if isinstance(b.get('turbo'), dict) else {}
    name = os.path.basename(str(w.get(kind) or '')) if kind else ''
    if not name:
        return None  # 没选：不加速
    x = next((x for x in turbo_list() if x['file'] == name and x['kind'] == kind), None)
    if not x:
        raise ValueError('所选的加速 LoRA 不存在或不适用于当前底模：' + name)
    return {'lora': name, 'steps': x['steps'], 'shift': x['shift'], 'ashift': x['ashift'], 'kind': kind}


COLOR_LABEL = {'match': '匹配原视频', 'cold_white': '冷白', 'ref': '参考图'}


def submit_post(gid, sp, up, ix, ffmpeg, by=None, color=None):
    """已经生成好的视频再做一次超分 / 插帧（2026-11-06 用户：生成时没勾，事后想要高清 / 更流畅的版本不用重新生成）。
    排进视频队列（和生成一样等显卡空闲），做在副本上，原来那段不动；成品是一条新的，跟原来那段在同一个视频组里。"""
    x = gallery_get(gid, sp)
    if not x:
        raise ValueError('这段视频已不在视频库中')
    up, ix = ('seedvr' if up == 'seedvr' else bool(up)), (2 if int(ix or 1) >= 2 else 1)
    # 2026-11-09 调色（colorfix.py）：照原视频 / 冷白预设 / 照参考图；只改颜色，不用显卡
    col = None
    if isinstance(color, dict) and color.get('mode') in COLOR_LABEL:
        col = {'mode': color['mode'], 'strength': max(0.1, min(1.0, float(color.get('strength') or (0.8 if color['mode'] == 'ref' else 1.0))))}
        if col['mode'] == 'match' and not (x.get('src_file') and os.path.isfile(vfile(sp, x['src_file']))):
            raise ValueError('这段没有存原视频，无法照原视频调色')
        if col['mode'] == 'ref' and not color.get('ref'):
            raise ValueError('请先选择一张参考图')
    if not up and ix == 1 and not col:
        raise ValueError('请选择超分、插帧或调色')
    if up == 'seedvr' and not seedvr_ok():
        raise ValueError('AI 修复超分的模型（SeedVR2 7B）尚未下载')
    ok = interp_ok()
    by = (by if by in ok else 'rife' if 'rife' in ok else (ok[0] if ok else 'ff')) if ix > 1 else None
    lab = ' + '.join(([('AI 修复超分 ×2' if up == 'seedvr' else '超分 ×2')] if up else []) + (['插帧 ×2'] if ix > 1 else []) + ([f"调色 · {COLOR_LABEL[col['mode']]}"] if col else []))
    j = stages.JobDict({'id': datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4], 'space': sp, 'state': 'queued', 'model': 'post',
         'model_name': lab, 'prompt': x.get('prompt') or '', 'negative': '', 'seconds': x.get('seconds'), 'steps': None, 'size': x.get('size'), 'seed': x.get('seed'),
         'created': time.time(), 'finished': None, 'progress': 0, 'message': '排队中', 'error': '', 'cancel': False, 'file': None,
         'post': {'gid': gid, 'up': up, 'ix': ix, 'by': by, 'label': lab, 'color': col}, 'upscale': up is True, '_ffmpeg': ffmpeg,
         **({'_cref': color['ref']} if col and col['mode'] == 'ref' else {})})
    j['prompt_trace'] = prompttrace.new(x.get('prompt_input') or x.get('prompt') or '')
    jobs[j['id']] = j
    with _qcv:
        _q.append(j); _qcv.notify()
    return public(j)


def _mi_vf(fps, ix):
    """ffmpeg 插帧（模型做不了时）：末尾先多留几帧再插，时长不变"""
    return [f'tpad=stop_mode=clone:stop={ix}', f'minterpolate=fps={fps * ix}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1']


def _esrgan_chunks(j, dst, work_in, work_out, tag, w, h, pre_vf=None):
    """Real-ESRGAN x2 分段做：按内存上限把视频切成几段（按帧切，不丢不重），每段在视频引擎上放大，再按顺序接回去。
    pre_vf：切段前先用 ffmpeg 做的处理（插帧没用上模型时的 minterpolate）"""
    src = dst
    if pre_vf:
        src = os.path.join(work_in, f'studio_{tag}_pre.mp4')
        n0 = _probe(dst).get('frames') or 0
        _ff(j, ['-i', dst, '-vf', ','.join(pre_vf), *(['-frames:v', str(n0 * 2)] if n0 else []), '-an', '-c:v', 'libx264', '-crf', '12', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', src], '插帧')
    pv = _probe(src); n, F = pv.get('frames') or 0, pv.get('fps') or 24
    if not n:
        raise RuntimeError('无法读取帧数')
    per = max(16, int(UPSCALE_MAX / (w * h * 4 * 3 * 4)))
    parts, tmp = [], []
    try:
        for k, a in enumerate(range(0, n, per)):
            if j.get('cancel'):
                raise InterruptedError
            b = min(n, a + per)
            cin = f'studio_{tag}_c{k}.mp4'; tmp.append(os.path.join(work_in, cin))
            _ff(j, ['-i', src, '-vf', f'trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS', '-an', '-c:v', 'libx264', '-crf', '10', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', tmp[-1]], '分段')
            wf = {'l': {'class_type': 'LoadVideo', 'inputs': {'file': cin}}, 'g': {'class_type': 'GetVideoComponents', 'inputs': {'video': ['l', 0]}},
                  'u0': {'class_type': 'UpscaleModelLoader', 'inputs': {'model_name': os.path.basename(UPSCALER)}},
                  'u1': {'class_type': 'ImageUpscaleWithModel', 'inputs': {'upscale_model': ['u0', 0], 'image': ['g', 0]}},
                  'c': {'class_type': 'CreateVideo', 'inputs': {'images': ['u1', 0], 'fps': F}},
                  's': {'class_type': 'SaveVideo', 'inputs': {'video': ['c', 0], 'filename_prefix': f'studio_{tag}_c{k}u', 'format': 'mp4', 'codec': 'h264'}}}
            j['progress'] = round(100 * k / max(1, (n + per - 1) // per)); outs = _run_wf(j, wf, work_out, '超分中（分段进行）…')
            got = [os.path.join(work_out, it.get('subfolder', ''), it['filename']) for o in outs.values() for kk in ('videos', 'images')
                   for it in (o.get(kk) or []) if isinstance(it, dict) and it.get('type', 'output') == 'output' and str(it.get('filename', '')).lower().endswith('.mp4')]
            if not got:
                raise RuntimeError('超分没有产生输出')
            parts.append(got[0]); tmp.append(got[0])
        lst = os.path.join(work_in, f'studio_{tag}_list.txt'); tmp.append(lst)
        with open(lst, 'w', encoding='utf-8') as f:
            f.write(''.join(f"file '{x.replace(chr(92), '/')}'\n" for x in parts))
        out = dst + '.cat.mp4'
        _ff(j, ['-f', 'concat', '-safe', '0', '-i', lst, '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', out], '接回')
        os.replace(out, dst)
    finally:
        for x in tmp + ([src] if src != dst else []):
            try:
                os.remove(x)
            except OSError:
                pass


def _run_post(j):
    """submit_post 的任务：复制一份 → 模型超分 / 插帧（_post_fx，和生成时同一套）→ 模型做不了的交给 ffmpeg → 放回原声 → 存成新的一条"""
    sp, P = j['space'], j['post']
    x = gallery_get(P['gid'], sp)
    if not x:
        raise RuntimeError('这段视频已不在视频库中')
    if P['up'] or P['ix'] > 1:  # 只调色：用不着视频引擎
        Engine.ensure()
    work_in, work_out = os.path.join(WORK['n'], 'in'), os.path.join(WORK['n'], 'out')
    tag, src = j['id'], vfile(sp, x['file'])
    pr = _probe(src)
    fps, w, h, frames = pr.get('fps') or x.get('fps') or 24, pr.get('width') or x.get('width'), pr.get('height') or x.get('height'), pr.get('frames') or x.get('frames') or 0
    if not (w and h and frames):
        raise RuntimeError('无法读取视频信息')
    name = nice_name(sp, item_label({**x, 'upscaled_of': x['id'], 'post_label': P['label']}))
    dst = vfile(sp, name)
    shutil.copyfile(src, dst)
    ix, by = P['ix'], P['by'] or 'ff'
    try:
        j['message'], j['progress'] = ('超分中…' if P['up'] else '插帧中…'), 10
        rife, ff_up, up_lab = False, False, None
        if P['up'] == 'seedvr':  # AI 修复超分：先做它（之后要插帧的话交给下面）
            _seedvr(j, dst, work_in, work_out, tag, frames); up_lab = 'SeedVR2 7B'
            pv = _probe(dst); w, h = pv.get('width') or w * 2, pv.get('height') or h * 2
        # 先插帧（原尺寸：RIFE 放得下），再分段超分（Real-ESRGAN 一次只能放下约 300 帧 480p：以前长一点的视频会悄悄变成 Lanczos，2026-11-06 实测发现）
        if ix > 1:
            j['upscale'] = False
            rife, _, _ = _post_fx(j, dst, work_in, work_out, tag, fps, ix, by, w, h, frames)
        if j.get('cancel'):
            raise InterruptedError
        if P['up'] is True:
            if upscaler_ok():
                try:
                    _esrgan_chunks(j, dst, work_in, work_out, tag, w, h, pre_vf=None if (ix == 1 or rife) else _mi_vf(fps, ix))
                    up_lab = 'Real-ESRGAN x2'; rife = rife or ix > 1  # 插帧（模型做不了时的 ffmpeg 插帧）已经在分段前做完
                except InterruptedError:
                    raise
                except Exception as e:
                    act(f'分段超分未成功，已改用 Lanczos：{e}', tag, 'warn'); ff_up = True
            else:
                ff_up = True
            up_lab = up_lab or 'Lanczos x2'
        vf = ([*_mi_vf(fps, ix)] if ix > 1 and not rife else []) + (['scale=iw*2:ih*2:flags=lanczos'] if ff_up else [])
        if vf:  # 模型做不了的部分（显存不够 / 没装模型）：ffmpeg 做，和生成时一样
            j['message'], j['progress'] = '处理中…', 70
            tmp = vfile(sp, f'{tag}.pp.mp4'); n0 = _probe(dst).get('frames') if ix > 1 and not rife else 0
            try:
                _ff(j, ['-i', dst, '-vf', ','.join(vf), *(['-frames:v', str(n0 * ix)] if n0 else []), '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium',
                        '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', tmp], '后处理')
                os.replace(tmp, dst)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        if P.get('color'):  # 调色：放在超分 / 插帧之后（颜色是对最后的画面算的）
            j['message'], j['progress'] = '调色中…', 80
            import colorfix
            c, tmp, ref = P['color'], vfile(sp, f'{tag}.cf.mp4'), None
            try:
                if c['mode'] == 'ref':
                    ref = os.path.join(work_in, f'studio_{tag}_cref.png')
                    os.makedirs(work_in, exist_ok=True)
                    with open(ref, 'wb') as f:
                        f.write(j.pop('_cref'))
                colorfix.fix(FFMPEG, dst, tmp, 'preset' if c['mode'] == 'cold_white' else c['mode'], src=vfile(sp, x['src_file']) if c['mode'] == 'match' else None,
                             ref_image=ref, preset='cold_white', strength=c['strength'], work=work_in, ranges=x.get('spliced_rng'))  # 拼好的视频：只量、只调生成的那几段
                os.replace(tmp, dst)
            finally:
                for f in (tmp, ref):
                    try:
                        if f:
                            os.remove(f)
                    except OSError:
                        pass
        if pr.get('audio') and (P['up'] or P['ix'] > 1):  # 模型那一步只出画面：把原来的声音放回去（时长不变；只调色时声音本来就在）
            j['message'], j['progress'] = '放回声音…', 90
            tmp = vfile(sp, f'{tag}.mux.mp4')
            try:
                _ff(j, ['-i', dst, '-i', src, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'copy', '-movflags', '+faststart', tmp], '放回声音')
                os.replace(tmp, dst)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    except BaseException:
        try:
            os.remove(dst)
        except OSError:
            pass
        raise
    pm = _probe(dst)
    thumb = _thumb(j, dst, sp, f'{tag}.jpg')
    item = {k: v for k, v in x.items() if k not in ('id', 'file', 'thumb', 'scrub', 'redo', 'merged_id')}
    item.update({'id': uuid.uuid4().hex[:12], 'file': name, 'thumb': thumb, 'job': tag, 'created': time.time(), 'took': round(time.time() - j['_t0'], 1),
                 'upscaled_of': x['id'], 'post_label': P['label'], 'width': pm.get('width') or w, 'height': pm.get('height') or h,
                 'fps': round(pm.get('fps') or fps * ix, 2), 'frames': pm.get('frames'), 'duration': pm.get('duration') or x.get('duration'), 'audio': bool(pm.get('audio')),
                 'upscale': bool(P['up']) or bool(x.get('upscale')), 'upscale_by': up_lab or x.get('upscale_by'),
                 'interp': ix > 1 or bool(x.get('interp')), 'interp_x': (ix * int(x.get('interp_x') or 1)) if ix > 1 else x.get('interp_x'),
                 'interp_by': (INTERP_NAME.get(by if rife else 'ff') if ix > 1 else x.get('interp_by')),
                 **({'color': P['color']} if P.get('color') else {})})
    if x.get('spliced_rng'):  # 拼好的视频处理后时间不变：分段条照旧
        item['lag'], item['lag_v'] = 0.0, 2
    _gallery_add(sp, item)
    j['file'], j['gallery_id'] = name, item['id']


def release(j):
    """任务结束（做完 / 失败 / 取消，包括排队时就取消的）：放掉大的输入（原视频、图、H3 的更多条件、重做用的那份）。
    2026-11-17 审查 P06：以前排队时取消的任务不走这一步，原视频一直留在内存里。共享的原视频快照（P01）只是少一个引用，别的段照样用"""
    for k in ('_img', '_end', '_vid', '_x', '_ffmpeg', '_redo', '_cref'):
        j.pop(k, None)


def cancel(jid, sp):
    j = jobs.get(jid)
    if not j or j['space'] != sp:
        raise RuntimeError('任务不存在')
    j['cancel'] = True
    if j['state'] == 'queued':
        j['state'], j['message'] = 'cancelled', '已取消'
        j['finished'] = time.time()
        with _qcv:  # 按对象找（in / remove 会逐个比字典内容，连同里面的大块字节）
            _q[:] = [x for x in _q if x is not j]
        release(j)
    elif j['state'] == 'running':
        try:
            _http('/interrupt', {}, timeout=5)
        except Exception:
            pass


def _dims(img_bytes, short):
    """原图比例 → 视频尺寸（短边 = short，长边按比例，都是 32 的倍数）。"""
    w = h = 0
    if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', img_bytes[16:24])
    elif img_bytes[:4] == b'RIFF' and img_bytes[8:12] == b'WEBP':  # WebP：VP8X / VP8 / VP8L 三种头
        c = img_bytes[12:16]
        try:
            if c == b'VP8X':
                w, h = 1 + int.from_bytes(img_bytes[24:27], 'little'), 1 + int.from_bytes(img_bytes[27:30], 'little')
            elif c == b'VP8 ':
                w, h = struct.unpack('<HH', img_bytes[26:30]); w, h = w & 0x3FFF, h & 0x3FFF
            elif c == b'VP8L':
                v = int.from_bytes(img_bytes[21:25], 'little'); w, h = (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
        except struct.error:
            w = h = 0
    else:
        try:
            from io import BytesIO
            import struct as st
            f = BytesIO(img_bytes)
            f.read(2)
            while True:
                mk = f.read(2)
                if len(mk) < 2 or mk[0] != 0xFF:
                    break
                ln = st.unpack('>H', f.read(2))[0]
                if mk[1] in (0xC0, 0xC1, 0xC2):
                    f.read(1); h, w = st.unpack('>HH', f.read(4)); break
                f.read(ln - 2)
        except Exception:
            pass
    if not w or not h:
        w, h = 832, 480
    k = short / min(w, h)
    r32 = lambda v: max(256, int(round(v * k / 32)) * 32)  # 32 的倍数：H3 的潜空间要能按 2×2 切块（720 / 16 = 45 是奇数会报 shape 错）
    return r32(w), r32(h)


class _Vbar(RuntimeError):
    """ComfyUI 的显存地址空间不够（comfy-aimdo：VBAR allocation failed / Could not reserve Virtual Address space）。
    2026-11-10：引擎开了很久、用过的模型都缓存着（fp16 解码器、32GB 主模型、26GB 文字编码器……），再要载入 int8 解码器和动作跟随的模型时预留不到地址；
    实际显存是够的，ComfyUI 不会自己卸载，重试也一样。释放全部模型 / 重启引擎就好"""


def _is_vbar(msg):
    return 'vbar allocation' in msg.lower() or 'virtual address space' in msg.lower()


POSE_NODES = ('RTDETR_detect', 'SDPoseKeypointExtractor', 'SDPoseDrawKeypoints')  # 动作跟随：识别原视频姿势的几个节点（videoedit pp3~pp5）
SAMPLER_NODES = ('SamplerCustomAdvanced', 'SamplerCustom', 'KSampler', 'KSamplerAdvanced')


def step_name(nid, node):
    """视频引擎正在跑的节点 → 任务进度里显示的那一步（网页计时里每一步的名字也是它）；一闪而过的节点返回 None（不改）。
    引擎的模型载入节点只登记、不读文件（不到 1 秒），模型真正载入是在第一次用到它的那一步里（2026-11-11 实测）：
    文字编码器 → “理解提示词”那步，主模型 → 采样第 1 步（见 _run 里的 SAMPLER_NODES），动作识别模型 → “识别动作”那步。所以载入节点都不单独显示"""
    c, ins = node.get('class_type', ''), node.get('inputs') or {}
    if c in POSE_NODES:
        return '正在识别原视频的动作'
    if c in ('LoadVideo', 'GetVideoComponents'):
        return '正在读取原视频'
    if c.startswith('MiniMaxH3') and ('ToVideo' in c or 'Conditioning' in c):  # 实测：冷启动 55~77 秒（含载入 13.6 GB 文字编码器），模型已在内存里时约 18 秒
        ks = ' '.join(ins)
        return '正在载入文字编码器并理解提示词' + ('和参考视频' if 'ref_videos' in ks else '和图片' if ('ref_images' in ks or 'first_frame' in ks or 'last_frame' in ks) else '')
    if c in ('VAEDecode', 'MiniMaxH3AVDecodeT8'):
        return '正在解码视频'
    if c == 'VAEDecodeAudio':
        return '正在解码声音'
    if c == 'ImageUpscaleWithModel':
        return '超分中'
    if c == 'FrameInterpolate':
        return '插帧中'
    if c in ('CreateVideo', 'SaveVideo'):
        return '正在保存视频'
    return None


def _friendly(msg):  # 常见的 ComfyUI 报错换成看得懂的话，其余的截短
    low = msg.lower()
    if _is_vbar(msg):
        return '显存地址空间不够（VBAR）：请重试；仍失败请重启电脑'
    if 'safetensors' in low and ('corrupt' in low or 'header' in low):
        return '模型文件已损坏或未下载完整，请重新下载：' + msg.split('File path:')[-1].split('The safetensors')[0].strip().replace('\\', '/').split('/')[-1]
    if 'out of memory' in low or 'allocation on device' in low:
        return '显存不足：请降低清晰度或缩短时长后重试'
    return msg.strip().splitlines()[0][:200]


def _ff(j, args, what):
    """自己跑 ffmpeg（插帧 / 超分 / 合并）：能中途取消；出错给一句看得懂的话。"""
    p = subprocess.Popen([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    while True:
        try:
            _, err = p.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if j.get('cancel'):
                p.kill(); p.communicate()
                raise InterruptedError
    if p.returncode:
        raise RuntimeError(f'{what}失败：' + (err or b'').decode('utf-8', 'replace').strip()[-200:])


_probe_cache = {}  # (路径, 修改时间, 大小, 精确) → 结果（P04：同一个文件反复探测不再每次起进程）
_probe_lock = threading.Lock()


def _probe(path, exact=True):
    """视频的真实参数：宽高、帧率、帧数、时长、有没有声音（读不出来就是空的）。
    exact=True：逐包数帧数（-count_packets，要把整个文件读一遍）；exact=False：只看文件头（帧数按时长 × 帧率估），只要时长 / 宽高 / 有没有声音时用。
    结果按文件版本（修改时间 + 大小）缓存（2026-11-17 审查 P04）"""
    try:
        st = os.stat(path)
        key = (os.path.normcase(os.path.abspath(path)), st.st_mtime_ns, st.st_size, bool(exact))
    except OSError:
        return {}
    with _probe_lock:
        hit = _probe_cache.get(key) or (_probe_cache.get(key[:3] + (True,)) if not exact else None)  # 精确的结果也能当轻量的用
    if hit is not None:
        return dict(hit)
    r = _probe_run(path, exact)
    if r:
        with _probe_lock:
            if len(_probe_cache) > 512:
                _probe_cache.clear()
            _probe_cache[key] = r
    return dict(r)


def _probe_run(path, exact):
    try:
        r = subprocess.run([FFPROBE, '-v', 'error', *(['-count_packets'] if exact else []),
                            '-show_entries', 'stream=codec_type,width,height,avg_frame_rate,nb_read_packets,nb_frames:format=duration',
                            '-of', 'json', path], capture_output=True, timeout=60, creationflags=NO_WINDOW)
        d = json.loads(r.stdout or b'{}')
    except Exception:
        return {}
    ss = d.get('streams') or []
    v = next((s for s in ss if s.get('codec_type') == 'video'), {})
    a, _, b = (v.get('avg_frame_rate') or '0/1').partition('/')
    try:
        fps = float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    fdur = float((d.get('format') or {}).get('duration') or 0)
    if exact:
        n = int(v.get('nb_read_packets') or 0)
        dur = round(n / fps, 3) if n and fps else fdur
    else:  # 轻量：帧数用文件头里记的（没有就按时长 × 帧率估），时长用文件头里的
        n = int(v.get('nb_frames') or 0) or (int(round(fdur * fps)) if fdur and fps else 0)
        dur = round(fdur, 3)
    return {'width': v.get('width') or 0, 'height': v.get('height') or 0, 'fps': round(fps, 3), 'frames': n, 'duration': dur,
            'audio': any(s.get('codec_type') == 'audio' for s in ss), 'exact': bool(exact)}


def sweep_work(max_age=3 * 3600):
    """2026-11-14 审查：ComfyUI 只认一个输入 / 输出文件夹（普通空间的 WORK['n']），私密任务的中间文件正常做完就删，
    但崩溃 / 强制退出时会留下。引擎启动和 Studio 启动时，把这里超过 3 小时的 studio_* 文件删掉（正在跑的任务不会这么久没动过）"""
    now, n = time.time(), 0
    for d in (os.path.join(WORK['n'], 'in'), os.path.join(WORK['n'], 'out')):
        for a, _, fs in os.walk(d):
            for f in fs:
                p = os.path.join(a, f)
                try:
                    if f.startswith(('studio_', 'q21_', 'vgl_', 'pose_')) and now - os.path.getmtime(p) > max_age:
                        os.remove(p); n += 1
                except OSError:
                    pass
    return n


def _clean_in(work_in, tag):  # ComfyUI 输入文件夹里这次的东西（首帧、尾帧、改视频的原视频 / 人物图）
    for f in os.listdir(work_in) if os.path.isdir(work_in) else []:
        if f.startswith(f'studio_{tag}'):
            try:
                os.remove(os.path.join(work_in, f))
            except OSError:
                pass


def _thumb(j, path, sp, name):
    try:
        j['_ffmpeg']('-ss', '0', '-i', path, '-frames:v', '1', '-vf', 'scale=480:-2', vfile(sp, name))
        return name
    except Exception:
        return None


def last_frame(gid, sp, ffmpeg):
    """续接：取出这段视频的最后一帧（PNG，原尺寸），当作下一段的首帧。"""
    x = gallery_get(gid, sp)
    if not x:
        raise ValueError('该视频已不在视频库中')
    d = os.path.join(WORK[sp], 'in')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f'last_{uuid.uuid4().hex[:8]}.png')
    try:  # 从结尾前 1 秒开始解码，一直覆盖同一张图：留下的就是最后一帧
        ffmpeg('-sseof', '-1', '-i', vfile(sp, x['file']), '-an', '-update', '1', out)
        with open(out, 'rb') as f:
            data = f.read()
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    w, h = struct.unpack('>II', data[16:24]) if data[:8] == b'\x89PNG\r\n\x1a\n' else (0, 0)
    return {'data': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii'), 'width': w, 'height': h, 'id': x['id']}


def _merge(j, sp, item):
    """续接的这段做完：把前面的（整条链已经合成过的就用合成的）和这段拼成一段完整的。
    新一段的第一帧就是上一段的最后一帧，去掉不重复；帧率 / 尺寸不同时统一成大的；两段都有声音才保留声音。"""
    parent = gallery_get(j['chain_of'], sp)
    if not parent:
        return None
    head = parent if parent.get('merged') else (gallery_get(parent.get('merged_id'), sp) or parent)
    a, b = vfile(sp, head['file']), vfile(sp, item['file'])
    pa, pb = _probe(a), _probe(b)
    if not (pa.get('fps') and pb.get('fps') and pa.get('width') and pb.get('width')):
        raise RuntimeError('无法读取视频信息')
    F = max(pa['fps'], pb['fps'])
    W, H = (pa['width'], pa['height']) if pa['width'] * pa['height'] >= pb['width'] * pb['height'] else (pb['width'], pb['height'])
    norm = f'fps={F:g},scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
    aud = pa['audio'] and pb['audio']
    # 新一段的第一帧就是上一段的最后一帧：去掉它
    fc = f'[0:v]{norm}[va];[1:v]trim=start_frame=1,setpts=PTS-STARTPTS,{norm}[vb];'
    if aud:  # 声音按各自画面的长度补齐 / 截齐，第二段同样去掉第一帧那一点
        da, db = pa['duration'], pb['duration']
        fc += (f'[0:a]aresample=48000,apad=whole_dur={da:.4f},atrim=end={da:.4f},asetpts=PTS-STARTPTS[aa];'
               f'[1:a]aresample=48000,apad=whole_dur={db:.4f},atrim=start={1 / pb["fps"]:.5f}:end={db:.4f},asetpts=PTS-STARTPTS[ab];'
               '[va][aa][vb][ab]concat=n=2:v=1:a=1[v][a]')
    else:
        fc += '[va][vb]concat=n=2:v=1:a=0[v]'
    name = nice_name(sp, item_label({**item, 'merged': True}))
    out = vfile(sp, name)
    j['message'] = '合并中…'
    try:
        _ff(j, ['-i', a, '-i', b, '-filter_complex', fc, '-map', '[v]', *(['-map', '[a]', '-c:a', 'aac', '-b:a', '192k'] if aud else []),
                '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], '合并')
    except BaseException:
        try:
            os.remove(out)
        except OSError:
            pass
        raise
    pm = _probe(out)
    parts = (head.get('parts') or [head['id']]) + [item['id']]
    return {'id': uuid.uuid4().hex[:12], 'file': name, 'thumb': _thumb(j, out, sp, f"{j['id']}-merged.jpg"), 'job': j['id'], 'model': item['model'], 'model_name': item['model_name'],
            'merged': True, 'parts': parts, 'chain_of': parent['id'], 'prompt': item['prompt'], 'negative': item.get('negative', ''),
            'seconds': max(1, round(pm.get('duration') or 0)), 'duration': pm.get('duration'), 'size': item['size'], 'seed': item['seed'], 'steps': item['steps'],
            'width': pm.get('width') or W, 'height': pm.get('height') or H, 'fps': round(pm.get('fps') or F, 2), 'frames': pm.get('frames'), 'audio': bool(pm.get('audio')),
            'created': time.time(), 'took': round(time.time() - j['_t0'], 1), 'src_id': head.get('src_id')}


H3_LAG = 2 / 24  # H3 改视频的成品通常比原视频早 2 帧（2026-11-05 两段实测都是 2 帧）；量不出来时按这个


def motion_lag(a, b):
    """成品 a 和原视频 b 在时间上差几帧。第 2 版（2026-11-05）：直接比两边同一时刻的画面像不像（缩成 48×84 灰度、去掉亮度差），
    找最像的错位——背景、人的位置都算进去，动作少的视频也量得出来（第 1 版只比“动作量”，动作少时量不准）。
    返回 (秒, 把握)：正数 = 成品比原视频早（成品第 0 帧对应原视频的第 lag 秒）。没把握时返回 (None, 把握)。"""
    import numpy as np
    def fr(p):
        r = subprocess.run([FFMPEG, '-v', 'error', '-i', p, '-vf', 'setpts=PTS-STARTPTS,fps=24,scale=48:84,format=gray', '-f', 'rawvideo', '-'],
                           capture_output=True, timeout=300, creationflags=NO_WINDOW).stdout
        v = np.frombuffer(r, np.uint8).reshape(-1, 48 * 84).astype(np.float32)
        v = v - v.mean(1, keepdims=True)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-6)
    x, y = fr(a), fr(b)
    if len(x) < 24 or len(y) < 24:
        return None, 0.0
    sc = {}
    for k in range(-8, 9):
        i0, i1 = max(0, -k), min(len(x), len(y) - k)
        if i1 - i0 >= 16:
            sc[k] = float((x[i0:i1] * y[i0 + k:i1 + k]).sum(1).mean())
    k = max(sc, key=sc.get)
    conf = round(sc[k] - sc.get(0, sc[k]), 4)  # 比不错开时像多少
    if abs(k) >= 8 or (k and conf < 0.002):  # 在边上 / 几乎一样：没把握
        return None, conf
    return round(k / 24, 4), conf


def ensure_lag(gid, sp):
    """改视频成品的帧差（秒）：量过就直接用，没量过现在量一次并记进视频库。没存原视频的返回 0。"""
    it = gallery_get(gid, sp)
    if not it:
        return 0.0
    if it.get('lag') is not None and (it.get('lag_v') == 2 or it.get('spliced_of')):  # 第 1 版量的（动作少时不准）：重新量
        return float(it['lag'])
    d = videos_dir(sp)
    if not (it.get('edit') and it.get('src_file') and os.path.isfile(vfile(sp, it['src_file']))):
        return 0.0
    try:
        lag, conf = motion_lag(vfile(sp, it['file']), vfile(sp, it['src_file']))
    except Exception:
        lag, conf = None, 0.0
    if lag is None:  # 量不出来：H3 做的按通常的 2 帧；Wan Animate / Bernini 不错开
        lag = H3_LAG
    with _index_lock:
        try:
            items = _index_load(sp)  # 读不出 → IndexUnreadable（属于 ValueError，下面的 except 接住，不写）
            for x in items:
                if isinstance(x, dict) and x.get('id') == gid:
                    x['lag'], x['lag_c'], x['lag_v'] = round(lag, 4), conf, 2
            tmp = _index_path(sp) + f'.{uuid.uuid4().hex[:6]}.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
            os.replace(tmp, _index_path(sp))
        except (OSError, ValueError):
            pass
    return lag


def _src_key(path):
    """完整原视频是不是同一个：大小 + 开头 / 中间 / 结尾各 1 MB 的指纹（不用整个文件读一遍）"""
    import hashlib
    n = os.path.getsize(path); h = hashlib.sha1(str(n).encode())
    with open(path, 'rb') as f:
        for p in (0, max(0, n // 2 - 2 ** 19), max(0, n - 2 ** 20)):
            f.seek(p); h.update(f.read(2 ** 20))
    return h.hexdigest()[:16]


def _fix_splice_post(g):
    """以前的拼接视频抄了第一段的 upscaled_of（被当成那一段的调色版）：认出来、改成 parts_post（g 里就地改，返回要写回的）。
    认法：它的 upscaled_of 指向的不是拼接视频，或者和它用到的某个片段的 upscaled_of 一样（真正“整段调色”的那条指向的是拼接视频本身）。
    整段调色的那条（抄自这样的拼接视频）：parts_post 跟着补上"""
    by = {x['id']: x for x in g}
    fix = {}
    for x in g:
        if not (x.get('spliced_of') and x.get('upscaled_of')) or x.get('parts_post') is not None:
            continue
        o = by.get(x['upscaled_of'])
        pieces = [by.get(i) for i in x.get('spliced_ids') or []]
        if any(q and q.get('upscaled_of') == x['upscaled_of'] for q in pieces) or (o is not None and not o.get('spliced_of')):
            fix[x['id']] = {'drop': [k for k in POST_KEYS if k in x], 'parts': x.get('post_label') or '后处理'}
    for _ in range(5):  # 整段调色的（可能再调一次）：parts_post 跟着它的来源
        more = False
        for x in g:
            u = x.get('upscaled_of')
            if x.get('spliced_of') and u and x['id'] not in fix and x.get('parts_post') is None:
                src = fix.get(u) or ({'parts': by[u]['parts_post']} if u in by and by[u].get('parts_post') else None)
                if src:
                    fix[x['id']] = {'drop': [], 'parts': src['parts']}
                    more = True
        if not more:
            break
    for i, f in fix.items():
        for k in f['drop']:
            by[i].pop(k, None)
        by[i]['parts_post'] = f['parts']
    return fix


def ensure_groups(sp):
    """视频组（2026-11-06 用户：同一个原视频的所有片段、版本、拼接成品在缩略图里只占一格）：
    每条记一个 grp = 完整原视频的指纹（_src_key）。片段看自己留的 splice_src；拼好的视频跟着它用的片段走。
    以前的条目没有 grp：第一次打开时补算一次并写回 index.json（以后不再读文件）"""
    g = gallery(sp); d = videos_dir(sp); add = {}
    # 2026-11-10 用户：忘了按“拼接”生成的片段也要能拼回去。每一单改视频都为“重新生成”存了完整的原视频（videos/redo），
    # 片段的起点也是对它算的——没有 splice_src 的片段，用那份补上（只补一次）；整段改的没什么可拼，记 nosplice 不再看
    bf, rd = {}, os.path.join(d, 'redo')
    for x in g:
        e = x.get('edit') or {}
        rv = (x.get('redo') or {}).get('vid')
        if not e or x.get('splice_src') or x.get('spliced_of') or x.get('nosplice') or not rv:
            continue
        p = os.path.join(rd, os.path.basename(rv))
        if not os.path.isfile(p):
            continue
        try:
            T = _probe(p).get('duration') or 0
            s0, want = float(e.get('start') or 0), float(e.get('want') or x.get('duration') or 0)
            if s0 <= 0.05 and (not T or s0 + want >= T - 0.1):
                bf[x['id']] = None
                continue
            with open(p, 'rb') as f:
                bf[x['id']] = save_source(sp, f.read(), os.path.splitext(p)[1].lstrip('.') or 'mp4')
            x['splice_src'] = bf[x['id']]
        except (OSError, ValueError, TypeError):
            continue
    for x in g:
        if x.get('grp') or not x.get('splice_src'):
            continue
        try:
            add[x['id']] = _src_key(vfile(sp, x['splice_src']))
        except OSError:
            continue
    fixp = _fix_splice_post(g)
    have = {x['id']: x.get('grp') or add.get(x['id']) for x in g}
    for x in g:
        if not x.get('grp') and x.get('spliced_of'):
            k = next((have.get(i) for i in [x['spliced_of'], *(x.get('spliced_ids') or [])] if have.get(i)), None)
            if k:
                add[x['id']] = k
    if not add and not bf and not fixp:
        return g
    with _index_lock:
        try:
            items = _index_load(sp)  # 读不出 → IndexUnreadable（属于 ValueError，下面的 except 接住，不写）
            for x in items:
                if isinstance(x, dict) and x.get('id') in bf and not x.get('splice_src'):
                    if bf[x['id']]:
                        x['splice_src'] = bf[x['id']]
                    else:
                        x['nosplice'] = True
                if isinstance(x, dict) and x.get('id') in add and not x.get('grp'):
                    x['grp'] = add[x['id']]
                if isinstance(x, dict) and x.get('id') in fixp:
                    f = fixp[x['id']]
                    for k in f['drop']:
                        x.pop(k, None)
                    x['parts_post'] = f['parts']
            tmp = _index_path(sp) + f'.{uuid.uuid4().hex[:6]}.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
            os.replace(tmp, _index_path(sp))
        except (OSError, ValueError):
            pass
    return [{**x, 'grp': x.get('grp') or add.get(x['id'])} if add.get(x['id']) else x for x in g]


def splice_group(iid, sp):
    """和这段成品用的是同一个完整原视频（都选了“拼接”）的其他成品：可以一起拼回去（多段拼接，2026-11-05 用户要求）"""
    g = gallery(sp); d = videos_dir(sp)
    it = next((x for x in g if x.get('id') == iid), None)
    if not it or not it.get('splice_src') or not os.path.isfile(vfile(sp, it['splice_src'])):
        return []
    # 2026-11-06：条目上已经记了原视频指纹 grp（ensure_groups）：直接比，不用每次把每个片段的原视频读 3 MB（片段多时手机上点了要等好几秒，像没反应）
    gk = it.get('grp') or _src_key(vfile(sp, it['splice_src']))
    key, out = gk, []
    size = os.path.getsize(vfile(sp, it['splice_src']))
    for x in g:
        f = x.get('splice_src')
        if not f or x.get('spliced_of') or not os.path.isfile(vfile(sp, f)):
            continue
        try:
            if x['id'] == iid or (x.get('grp') == gk if x.get('grp') else os.path.getsize(vfile(sp, f)) == size and _src_key(vfile(sp, f)) == key):
                e = x.get('edit') or {}
                out.append({'id': x['id'], 'start': float(e.get('start') or 0), 'len': float(e.get('want') or x.get('duration') or 0),
                            'created': x.get('created'), 'thumb': x.get('thumb'), 'task': e.get('task'), 'exact': bool(e.get('exact'))})
        except OSError:
            continue
    return sorted(out, key=lambda y: (y['start'], -(y['created'] or 0)))


def _piece(it, sp, pg, T, F):
    """一段成品放在原视频的哪里：返回 (b0 原视频里从哪开始, gs 成品里从哪开始, gd 用多长, 选到结尾没有)"""
    ed = it.get('edit') or {}
    s0 = float(ed.get('start') or 0)
    gd = pg['duration'] or (pg['frames'] / F)
    want = float(ed.get('want') or 0)
    lag = max(-0.5, min(0.5, ensure_lag(it['id'], sp)))  # 按帧裁好的成品（exact）是 0；以前的成品按量出来的帧差（通常早 2 帧）
    b0, gs = s0 + lag, 0.0
    if b0 < 0:
        gs, b0 = -b0, 0.0
    gd -= gs
    if want > 0:
        if gd > want - (b0 - s0) + 0.5 / F:
            gd = max(1 / F, want - (b0 - s0))
        reach_end = s0 + want >= T - 0.05
    else:
        reach_end = T - (b0 + gd) < 0.75
    return b0, gs, gd, reach_end


TAIL_MIN = 0.25  # 最后一段后面剩下的原视频短于这个就不接（2026-11-11 用户：选到“结尾”时终点常差 1~2 帧，拼好后最后约 0.1 秒闪回原视频）


def _tiny_tail(x):
    """以前拼好的视频最后接了一小截（1~5 帧）原视频：再拼时重新做，不直接给旧的"""
    r = x.get('spliced_rng') or []
    t = (x.get('duration') or 0) - (r[-1][1] if r else 0)
    return x.get('splice_v', 1) < 2 and 0.04 < t < TAIL_MIN


def splice(iid, sp, ids=None):
    """改视频的成品拼回原视频：原视频 + 一段或几段成品（按时间排好，中间用原视频接上），存成新的一段。
    ids：多段拼接时一起拼的几段（都必须是同一个完整原视频）；没有就只拼 iid 这一段。"""
    ids = [x for x in dict.fromkeys([iid] + list(ids or []))]
    d = videos_dir(sp)
    # 同样这几段（同样的版本）已经拼过：直接给已有的那个，不再存一个一模一样的（2026-11-06：手机等别的入口也会重复拼）
    same = next((x for x in gallery(sp) if x.get('spliced_of') and not x.get('upscaled_of') and set(x.get('spliced_ids') or []) == set(ids) and not _tiny_tail(x)), None)
    if same:
        return {**same, 'existed': True}
    its = [gallery_get(x, sp) for x in ids]
    if not all(its):
        raise ValueError('找不到要拼接的视频')
    for it in its:
        if not it.get('splice_src'):
            raise ValueError('这段视频没有保留完整的原视频（选段时需选择“拼接”）')
    full = vfile(sp, its[0]['splice_src'])
    if not os.path.isfile(full):
        raise ValueError('完整的原视频已不在了')
    if len(its) > 1:
        k0 = its[0].get('grp') or _src_key(full)
        for it in its[1:]:
            p = vfile(sp, it['splice_src'])
            if not os.path.isfile(p) or (it.get('grp') or _src_key(p)) != k0:
                raise ValueError('这几段不是从同一个原视频生成的，不能拼在一起')
    pf = _probe(full)
    gens = [vfile(sp, it['file']) for it in its]
    pgs = [_probe(g) for g in gens]
    if not (pf.get('duration') and all(p.get('width') and p.get('fps') for p in pgs)):
        raise RuntimeError('无法读取视频信息')
    W, H, F = pgs[0]['width'], pgs[0]['height'], pgs[0]['fps']
    T = pf['duration']
    pcs = sorted([(*_piece(it, sp, pg, T, F), k) for k, (it, pg) in enumerate(zip(its, pgs))], key=lambda x: x[0])
    for (a0, _, g0, _, _), (a1, _, _, _, _) in zip(pcs, pcs[1:]):
        if a1 < a0 + g0 - 0.05:
            raise ValueError(f'有两段时间重叠（第 {a0:.2f} – {a0 + g0:.2f} 秒和第 {a1:.2f} 秒起），请只选其中一段')
    norm = f'fps={F:g},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1,format=yuv420p'
    aud = pf['audio'] or any(p['audio'] for p in pgs)
    # 声音（2026-11-05 用户要求）：原视频有声音就整条都用原视频的（一条连续的原声，不分段拼，接缝处不卡顿）；原视频没声音才用成品的
    orig = bool(pf['audio'])
    an = 'aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo'
    sil = lambda x: f'aevalsrc=0|0:s=48000:c=stereo:d={x:.4f},aformat=sample_fmts=fltp:channel_layouts=stereo'
    seg_a = aud and not orig
    fc, segs, c, n = [], [], 0.0, 0
    nv = {}  # 原视频要分成几段用：先 split
    def org(t0, t1):
        nonlocal n
        n += 1; lab = f'o{n}'
        fc.append(f'[0:v]setpts=PTS-STARTPTS,fps={F:g},trim={t0 - 0.25 / F:.5f}:{t1 - 0.25 / F:.5f},setpts=PTS-STARTPTS,{norm}[{lab}]' if t1 else f'[0:v]setpts=PTS-STARTPTS,fps={F:g},trim=start={t0 - 0.25 / F:.5f},setpts=PTS-STARTPTS,{norm}[{lab}]')  # 先在原视频自己的时间轴上转 24 fps 再按时间取（和改视频的窗口一样，2026-11-06）
        if seg_a:
            fc.append(f'{sil((t1 or T) - t0)}[a{lab}]')
        segs.append(lab)
    for b0, gs, gd, reach, k in pcs:
        if b0 - c > 0.04:
            org(c, b0)
        lab = f'g{k}'
        fc.append(f'[{k + 1}:v]trim={gs:.4f}:{gs + gd:.4f},setpts=PTS-STARTPTS,{norm}[{lab}]')
        if seg_a:
            fc.append(f'[{k + 1}:a]atrim={gs:.4f}:{gs + gd:.4f},asetpts=PTS-STARTPTS,{an},apad=whole_dur={gd:.4f},atrim=end={gd:.4f},asetpts=PTS-STARTPTS[a{lab}]'
                      if pgs[k]['audio'] else f'{sil(gd)}[a{lab}]')
        segs.append(lab); c = b0 + gd
    last_reach = pcs[-1][3]
    tail = T - c >= TAIL_MIN and not last_reach  # 只剩几帧：不接原视频，就停在生成的这段结尾（原声同样剪到这里）
    if tail:
        org(c, None)
    # 原视频要用好几次：先复制几份
    uses = sum(1 for x in fc if x.startswith('[0:v]'))
    if uses > 1:
        fc = [f'[0:v]split={uses}' + ''.join(f'[s{i}]' for i in range(uses))] + fc
        i = 0
        for k, x in enumerate(fc[1:], 1):
            if x.startswith('[0:v]'):
                fc[k] = f'[s{i}]' + x[5:]; i += 1
    fc.append(''.join(f'[{s_}]' + (f'[a{s_}]' if seg_a else '') for s_ in segs) + f'concat=n={len(segs)}:v=1:a={1 if seg_a else 0}[v]' + ('[a]' if seg_a else ''))
    te = T if tail else c
    if orig:  # 整条原声：长度和拼好的画面一样
        fc.append(f'[0:a]atrim=0:{te:.4f},asetpts=PTS-STARTPTS,{an},apad=whole_dur={te:.4f},atrim=end={te:.4f}[a]')
    it = its[0]
    tag = f"{it.get('job') or iid}-join-{uuid.uuid4().hex[:4]}"  # 缩略图等辅助文件用；成品本身用好认的名字
    clean = {k: v for k, v in it.items() if k not in POST_KEYS}
    pp = _parts_post(its)
    oname = nice_name(sp, item_label({**clean, 'spliced_of': iid, 'parts_post': pp}))
    out = vfile(sp, oname)
    j = {'cancel': False}
    try:
        _ff(j, ['-i', full, *sum((['-i', g] for g in gens), []), '-filter_complex', ';'.join(fc), '-map', '[v]', *(['-map', '[a]', '-c:a', 'aac', '-b:a', '192k'] if aud else []),
                '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], '拼接')
    except BaseException:
        try:
            os.remove(out)
        except OSError:
            pass
        raise
    thumb = None
    try:
        _ff(j, ['-ss', f'{min(pcs[0][0] + 0.2, max(0, te - 0.1)):.3f}', '-i', out, '-frames:v', '1', '-vf', 'scale=480:-2', vfile(sp, tag + '.jpg')], '缩略图')
        thumb = tag + '.jpg'
    except Exception:
        pass
    src_f = None  # 对比用的原视频：整段按成品的尺寸、帧率处理一份（滑动对比时每一帧都对得上）
    try:  # 同一个原视频、同样尺寸帧率的已经做过一份：直接共用（2026-11-06，以前每拼一次就多一份整段原视频）
        cn = f"cmp-{its[0].get('grp') or _src_key(full)}-{W}x{H}-{round(F, 2)}fps.mp4"
        if not os.path.isfile(vfile(sp, cn)):
            tmp = vfile(sp, cn) + '.tmp.mp4'
            _ff(j, ['-i', full, '-vf', norm, *(['-c:a', 'aac', '-b:a', '192k'] if pf['audio'] else ['-an']), '-c:v', 'libx264', *GOP, '-crf', '18', '-preset', 'veryfast',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp], '处理原视频')
            os.replace(tmp, vfile(sp, cn))
        src_f = cn
    except Exception:
        pass
    pm = _probe(out)
    item = {k: v for k, v in it.items() if k not in ('id', 'file', 'thumb', 'src_file', 'splice_src', 'merged_id', 'redo', 'raw_file', 'parts_post', *POST_KEYS)}  # 拼好的完整视频没有“重新生成”（点了只会重做那一段，2026-11-06）
    if pp:
        item['parts_post'] = pp
    if src_f:
        item['src_file'] = src_f
    item['lag'], item['lag_v'] = 0.0, 2  # 拼好的视频已经对齐了原视频
    item.update({'id': uuid.uuid4().hex[:12], 'file': oname, 'thumb': thumb, 'spliced_of': iid, 'spliced_ids': [its[p[4]]['id'] for p in pcs],
                 'spliced_rng': [[round(p[0], 3), round(p[0] + p[2], 3)] for p in pcs], 'splice_v': 2, 'created': time.time(), 'grp': its[0].get('grp') or _src_key(full),
                 'width': pm.get('width') or W, 'height': pm.get('height') or H, 'fps': round(pm.get('fps') or F, 2), 'frames': pm.get('frames'),
                 'duration': pm.get('duration'), 'seconds': max(1, round(pm.get('duration') or 0)), 'audio': bool(pm.get('audio'))})
    _gallery_add(sp, item)
    return item


def _cut_file(j, src, out, keep, F, crf='17'):
    """把 src 里 keep 的几段（秒，按帧对齐）按顺序接起来存成 out（画面 + 声音一起裁，帧准确）"""
    pv = _probe(src); has_a = bool(pv.get('audio')); h = 0.5 / F; n = len(keep); fc = []
    fc.append(f'[0:v]setpts=PTS-STARTPTS,split={n}' + ''.join(f'[i{k}]' for k in range(n)) if n > 1 else '[0:v]setpts=PTS-STARTPTS[i0]')
    if has_a:
        fc.append(f'[0:a]asetpts=PTS-STARTPTS,asplit={n}' + ''.join(f'[j{k}]' for k in range(n)) if n > 1 else '[0:a]asetpts=PTS-STARTPTS[j0]')
    for k, (a0, b0) in enumerate(keep):
        fc.append(f'[i{k}]trim=start={max(0, a0 - h):.5f}:end={b0 - h:.5f},setpts=PTS-STARTPTS[v{k}]')
        if has_a:
            fc.append(f'[j{k}]atrim=start={a0:.5f}:end={b0:.5f},asetpts=PTS-STARTPTS[a{k}]')
    fc.append(''.join(f'[v{k}]' + (f'[a{k}]' if has_a else '') for k in range(n)) + f'concat=n={n}:v=1:a={1 if has_a else 0}[v]' + ('[a]' if has_a else ''))
    _ff(j, ['-i', src, '-filter_complex', ';'.join(fc), '-map', '[v]', *(['-map', '[a]', '-c:a', 'aac', '-b:a', '192k'] if has_a else []),
            '-c:v', 'libx264', *GOP, '-crf', crf, '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], '修剪')


def cut_video(sp, cuts, gid=None, data=None, name=''):
    """修剪：去掉 cuts 里的几段（秒），剩下的按顺序接成一段新视频，放进视频库（原来的不动）。2026-11-05 用户要求。
    视频库里的一段（gid）：有对比用的原视频（src_file）的话同样裁掉，滑动对比照样对得上；拼接用的完整原视频不带过去（时间变了，不能再拼回去）。
    其他视频（改视频左边的原视频等）：data = 视频文件的内容。"""
    import videoedit
    d = videos_dir(sp); base = gallery_get(gid, sp) if gid else None
    tag = f"{(base or {}).get('job') or datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-cut-{uuid.uuid4().hex[:4]}"
    if base:
        src = vfile(sp, base['file'])
    elif data:
        src = vfile(sp, tag + '_in.' + (videoedit.video_kind(data) or 'mp4'))
        with open(src, 'wb') as f:
            f.write(data)
    else:
        raise ValueError('找不到要修剪的视频')
    try:
        pv = _probe(src); F, T = pv.get('fps') or 24, pv.get('duration') or 0
        if not T:
            raise RuntimeError('无法读取视频信息')
        fr = lambda t: max(0.0, min(T, round(float(t) * F) / F))  # 按帧对齐
        cs = sorted([(fr(a), fr(b)) for a, b in cuts if fr(b) > fr(a)])
        if not cs:
            raise ValueError('请先选择要删除的片段')
        m = []
        for a0, b0 in cs:  # 重叠的合并
            if m and a0 <= m[-1][1] + 0.5 / F:
                m[-1] = (m[-1][0], max(m[-1][1], b0))
            else:
                m.append((a0, b0))
        keep, c = [], 0.0
        for a0, b0 in m:
            if a0 - c >= 0.5 / F:
                keep.append((c, a0))
            c = b0
        if T - c >= 0.5 / F:
            keep.append((c, T))
        if not keep:
            raise ValueError('不能把整段视频都删掉')
        j = {'cancel': False}
        oname = nice_name(sp, item_label({**base, 'cut_of': gid}) if base else '修剪')
        out = vfile(sp, oname)
        _cut_file(j, src, out, keep, F)
        src_f = None
        if base and base.get('src_file') and os.path.isfile(vfile(sp, base['src_file'])):  # 对比用的原视频：同样裁
            try:
                ps = _probe(vfile(sp, base['src_file']))
                if abs((ps.get('duration') or 0) - T) < 0.25:
                    _cut_file(j, vfile(sp, base['src_file']), vfile(sp, tag + '_src.mp4'), keep, ps.get('fps') or F, '18')
                    src_f = tag + '_src.mp4'
            except Exception:
                src_f = None
    finally:
        if not base:
            try:
                os.remove(src)
            except OSError:
                pass
    thumb = None
    try:
        _ff(j, ['-ss', '0.2', '-i', out, '-frames:v', '1', '-vf', 'scale=480:-2', vfile(sp, tag + '.jpg')], '缩略图')
        thumb = tag + '.jpg'
    except Exception:
        pass
    pm = _probe(out)
    if base:
        item = {k: v for k, v in base.items() if k not in ('id', 'file', 'thumb', 'src_file', 'splice_src', 'merged_id', 'scrub', 'spliced_of', 'spliced_ids', 'spliced_rng', 'redo')}  # 帧差（lag）照旧：成品和对比用的原视频在同样的时间裁掉，错开多少不变
    else:
        item = {'model': 'cut', 'model_name': '修剪的视频', 'prompt': '', 'negative': '', 'seed': -1, 'steps': None, 'loras': [], 'src_name': str(name or '')[:120]}
    item.update({'id': uuid.uuid4().hex[:12], 'file': oname, 'thumb': thumb, 'cut_of': gid, 'cuts': [[round(a0, 3), round(b0, 3)] for a0, b0 in m], 'created': time.time(),
                 'width': pm.get('width'), 'height': pm.get('height'), 'fps': round(pm.get('fps') or F, 2), 'frames': pm.get('frames'), 'size': f"{pm.get('width')}×{pm.get('height')}",
                 'duration': pm.get('duration'), 'seconds': max(1, round(pm.get('duration') or 0)), 'audio': bool(pm.get('audio'))})
    if src_f:
        item['src_file'] = src_f
    elif base:
        item.pop('src_file', None)
    _gallery_add(sp, item)
    return item


def export_timeline(ids, sp, ffmpeg, xfade=0.0):
    """时间线导出：按顺序把几段拼成一段完整的视频，放进视频库。
    后一段是从前一段最后一帧接下去的（chain_of 正好是前一段）就去掉它重复的第一帧；不是就直接硬切（或按 xfade 秒交叉淡化）。
    画面本身不重新处理（不插帧、不调色），只统一帧率 / 尺寸后重新编码，和单段的画质一样。"""
    items = [gallery_get(str(i), sp) for i in ids]
    if len(items) < 2 or any(x is None for x in items):
        raise ValueError('时间线中至少需要两段，且每段都须仍在视频库中')
    if len(items) > 40:
        raise ValueError('每次最多拼接 40 段')
    paths = [vfile(sp, x['file']) for x in items]
    probes = [_probe(pa) for pa in paths]
    if not all(pr.get('fps') and pr.get('width') for pr in probes):
        raise ValueError('其中一段无法读取视频信息')
    F = max(pr['fps'] for pr in probes)
    big = max(probes, key=lambda pr: pr['width'] * pr['height']); W, H = big['width'], big['height']
    norm = f'fps={F:g},scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
    aud = all(pr['audio'] for pr in probes)
    xf = max(0.0, min(1.0, float(xfade or 0)))
    fc, durs = '', []
    for k, (x, pr) in enumerate(zip(items, probes)):
        drop = k > 0 and x.get('chain_of') == items[k - 1]['id'] and not xf  # 接得上：去掉重复的第一帧
        d = pr['duration'] - (1 / pr['fps'] if drop else 0)
        durs.append(d)
        fc += f'[{k}:v]' + ('trim=start_frame=1,setpts=PTS-STARTPTS,' if drop else '') + f'{norm}[v{k}];'
        if aud:
            st = f'start={1 / pr["fps"]:.5f}:' if drop else ''
            fc += f'[{k}:a]aresample=48000,apad=whole_dur={pr["duration"]:.4f},atrim={st}end={pr["duration"]:.4f},asetpts=PTS-STARTPTS[a{k}];'
    n = len(items)
    if xf:  # 交叉淡化：一段一段叠过去
        cur, acur, off = 'v0', 'a0', 0.0
        for k in range(1, n):
            off += durs[k - 1] - xf
            fc += f'[{cur}][v{k}]xfade=transition=fade:duration={xf:.3f}:offset={off:.4f}[x{k}];'
            if aud:
                fc += f'[{acur}][a{k}]acrossfade=d={xf:.3f}[y{k}];'
                acur = f'y{k}'
            cur = f'x{k}'
        vmap, amap = f'[{cur}]', f'[{acur}]'
        fc = fc.rstrip(';')
    else:
        fc += ''.join(f'[v{k}]' + (f'[a{k}]' if aud else '') for k in range(n)) + f'concat=n={n}:v=1:a={1 if aud else 0}[v]' + ('[a]' if aud else '')
        vmap, amap = '[v]', '[a]'
    gid = uuid.uuid4().hex[:12]
    name = nice_name(sp, '时间线导出')
    out = vfile(sp, name)
    j = {'_ffmpeg': ffmpeg, 'cancel': False}
    args = []
    for pa in paths:
        args += ['-i', pa]
    try:
        _ff(j, [*args, '-filter_complex', fc, '-map', vmap, *(['-map', amap, '-c:a', 'aac', '-b:a', '192k'] if aud else []),
                '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], '导出')
    except BaseException:
        try:
            os.remove(out)
        except OSError:
            pass
        raise
    pm = _probe(out)
    last = items[-1]
    item = {'id': gid, 'file': name, 'thumb': _thumb(j, out, sp, f'tl-{gid}.jpg'), 'model': last['model'], 'model_name': last['model_name'],
            'merged': True, 'timeline': True, 'parts': [x['id'] for x in items], 'prompt': ' → '.join(x.get('prompt', '')[:60] for x in items),
            'negative': '', 'seconds': max(1, round(pm.get('duration') or 0)), 'duration': pm.get('duration'), 'size': last.get('size'), 'seed': last.get('seed'),
            'steps': last.get('steps'), 'width': pm.get('width') or W, 'height': pm.get('height') or H, 'fps': round(pm.get('fps') or F, 2), 'frames': pm.get('frames'),
            'audio': bool(pm.get('audio')), 'created': time.time(), 'xfade': xf or None,
            'loras': [L for x in items for L in (x.get('loras') or [])][:8], 'src_id': items[0].get('src_id')}
    _gallery_add(sp, item)
    return item


def _prep_job(j):
    """一单的准备：裁原视频、（要的话）Qwen 换衣服、拼好工作流。返回 _Ctx；“只准备”（ed['prep']）做完返回 None"""
    import h3extra
    m = MODELS[j['model']]
    sp = j['space']
    Engine.ensure()
    sampler_options()  # 引擎开着：顺便读一次真的采样器 / 调度器列表
    work_in, work_out = os.path.join(WORK['n'], 'in'), os.path.join(WORK['n'], 'out')
    tag = j['id']
    in_name, end_name = f'studio_{tag}.png', f'studio_{tag}_end.png'
    if j.get('_img'):  # 改视频时人物图 / 衣服图可以没有
        with open(os.path.join(work_in, in_name), 'wb') as f:
            f.write(j['_img'])
    if j.get('_end'):
        with open(os.path.join(work_in, end_name), 'wb') as f:
            f.write(j['_end'])
    ed, src_name, src_audio = j.get('edit'), None, False
    try:
        if ed:  # 改视频：先把原视频裁成要的那段（24 fps、目标尺寸、17k+5 帧），工作流在 videoedit.py 里拼
            import videoedit
            videoedit._tl.sp = sp  # 用这个空间默认的那套模板（Qwen 改图那句和 H3 提示词都跟着它）
            w, h, frames, src_name, src_audio = videoedit.prepare(j, work_in, tag)
            fps = videoedit.FPS
            if ed.get('recipe') and j.get('_img') and not ed.get('ref_desc'):  # 换人 · 新做法 / 动作迁移：看人物图写清这个人（作者模板里的 {details}），动作迁移再写图里的场景
                j['message'] = '正在看人物图写清人物的样子…'
                t0 = time.time()
                Engine.free()  # 视频引擎先把显存让出来（AI 助手要载入；以前没放，H3 还占着显存，2026-11-16 审查）
                try:
                    who, env = videoedit.describe_ref(j['_img'], scene=ed['recipe'] == 'motion')
                except Exception as ex:
                    act(f'看人物图写人物的样子没有成功（{ex}），提示词里只写“人物图中的人”', 'video', 'warn'); who, env = None, None
                ed['ref_desc'], ed['ref_env'] = who, env
                prompttrace.add(j['prompt_trace'], '人物图（看图写的样子）', (who or '（没写成，按人物图）') + ('' if ed['recipe'] != 'motion' else '；场景：' + (env or '人物图里没有场景，沿用原视频的')))
                act(f'人物图看图写成：{(who or "（没写成）")[:80]}…（{time.time() - t0:.0f} 秒）', 'video')
            if ed['task'] == 'outfit' and ed.get('method') == 'ref':  # 改衣“参考生成”：人物换好衣服的图当 <Picture 1>，原视频当 <Video 1>（laowang A4 的做法）
                shared = None if ed.get('own') else qshare_get(sp, ed.get('qshare'))
                if shared:  # 多段共用一张（2026-11-06）：同一批前面那段已经换好衣服的图，直接用，几段的衣服一样
                    with open(os.path.join(work_in, in_name), 'wb') as f:
                        f.write(shared)
                    ed['qshared'] = True
                    prompttrace.add(j['prompt_trace'], '参考图改图', '（共用同一批第一段换好衣服的图）')
                    if ed.get('ffguide'):  # 锁定要的是这一段自己第 0 帧换好的图：共用的图对不上这一段的开头
                        j['warn'] = '首帧锁定未生效：这一段用的是共用的衣服图（取自第一段的画面）'
                        act(j['warn'], 'video', 'warn')
                elif not ed.get('own'):  # 没上传换好衣服的图：挑一帧脸看得清的画面，用 Qwen 改图换衣服
                    import outfit2, imagegen
                    pre = os.path.join(work_in, f'studio_{tag}')
                    f0 = pre + '_f0.png'
                    j['message'] = '正在选取人物清晰的一帧…'
                    _i, qw, qh = videoedit.pick_frame(os.path.join(work_in, src_name), f0, pre, j, work_in, tag); ed['pick_idx'] = _i  # 原分辨率的一帧（长边最多 1280），Qwen 按这个尺寸改，脸更像本人
                    if ed.get('ffguide') and _i != 0:  # 首帧锁定要用第 0 帧当参考：开头认不出脸时用的是后面的帧，锁定用不上（2026-11-06：以前悄悄跳过）
                        j['warn'] = f'首帧锁定未生效：视频开头认不出人脸，参考图取自第 {_i / videoedit.FPS:.1f} 秒的画面'
                        act(j['warn'], 'video', 'warn')
                    refs = None
                    if j.get('_img'):  # 放了衣服图：只抠出衣服（图里的模特不要），当改图的图 2
                        j['message'] = '正在从衣服图中抠出衣服…'
                        from PIL import Image as _Im
                        import io as _io
                        iw, ih = _Im.open(_io.BytesIO(j['_img'])).size
                        cl = outfit2.cloth_only(in_name, f'studio_{tag}_cloth', iw, ih, work_out) or j['_img']
                        refs = ['data:image/png;base64,' + base64.b64encode(cl).decode()]
                    j['message'], j['progress'] = '正在为人物更换衣服（Qwen 改图）…', 0
                    Engine.free()  # 视频引擎先把显存让出来
                    xq = (ed.get('xt') or {}).get('qimg')  # 测试用（2026-11-13）：直接用给定的改好的图，当作 Qwen 改的这一帧（同一张图比较 H3 / Viggle、v23 / 2.1）
                    if isinstance(xq, str) and os.path.isfile(xq):
                        with open(xq, 'rb') as fh:
                            img = fh.read()
                        prompttrace.add(j['prompt_trace'], '参考图改图', '（测试：给定的图 ' + os.path.basename(xq) + '）')
                    else:
                        with open(f0, 'rb') as fh:
                            ep = outfit2.edit_prompt(videoedit.edit_desc(j['prompt']), ed.get('target'), bool(refs)) if ed.get('tpl', True) or videoedit._structured(j['prompt']) else j['prompt']
                            prompttrace.add(j['prompt_trace'], '参考图改图', ep)
                            img = imagegen.edit_once(fh.read(), ep, qw or w, qh or h, j['seed'] % 2 ** 31, sp, refs=refs, note='改衣（参考生成）为人物更换的衣服')
                    imagegen.Engine.stop()  # 改图引擎关掉，显存还给视频引擎
                    if j['cancel']:
                        raise InterruptedError
                    with open(os.path.join(work_in, in_name), 'wb') as f:
                        f.write(img)
                    ed['qwen_done'] = True  # 这张图是 Qwen 换好衣服的（首帧锁定只用这种）
                    if ed.get('prep'):  # 只准备：改好的图交回网页（/api/video/jobs/<id>/prep），不生成视频
                        mime = 'image/png' if img[:4] == b'\x89PNG' else 'image/jpeg'
                        j['_prep'] = {'image': f'data:{mime};base64,' + base64.b64encode(img).decode()}
                        j['prep'] = {}
                        _clean_in(work_in, tag)  # 裁好的原视频、挑的那一帧：用不上了
                        return
                    if ed.get('qshare'):  # 多段共用：存下来给同一批后面几段（以及之后重新生成这几段时）用
                        qshare_put(sp, ed['qshare'], img)
                    Engine.ensure()
                # 直接用作参考图但没放图：跳过 Qwen，H3 只拿原视频 + 提示词（模板里去掉了 <Picture 1>，见 videoedit._nopic）
                wf = videoedit.build(j, w, h, frames, src_name, src_audio, None if ed.get('own') and not j.get('_img') else in_name)
            else:
                wf = videoedit.build(j, w, h, frames, src_name, src_audio, in_name if j.get('_img') else None)
            wf['16']['inputs']['filename_prefix'] = f'studio_{tag}'
            for n in wf.values():  # 局部生成测试：mask 视频（还有 _mask_raw / _cloth / _prot / _gcloth）
                fp = (n.get('inputs') or {}).get('filename_prefix') if isinstance(n, dict) and n.get('class_type') == 'SaveVideo' else None
                if isinstance(fp, str) and fp.startswith('__PREFIX___mask'):
                    n['inputs']['filename_prefix'] = f'studio_{tag}' + fp[len('__PREFIX__'):]
        else:
            res = j.get('res')
            if res and res[0] == 'wh':
                w, h = res[1], res[2]
            else:  # 比例跟首帧；H3 没有首帧时跟第一张关键帧 / 参考图，或者开头片段，都没有就是 16:9 左右（832 × 480 的比例）
                short = res[1] if res else SIZES[j['size']]
                ab = j.get('_img') or (None if (j.get('_x') or {}).get('guide') else h3extra.aspect_bytes(j.get('_x')))  # 有引导视频：比例跟它
                cd = None if ab else h3extra.clip_dims(j, work_in, tag)
                w, h = _dims(ab, short) if ab else _dims(b'', short) if not cd else (max(256, int(round(v * short / min(cd) / 32)) * 32) for v in cd)
            fps = j.get('fps') or m['fps']
            frames = j['seconds'] * fps + 1
            frames = max(22, round((frames - 5) / 17) * 17 + 5)  # H3：帧数是 17k+5，取最近的（5 秒 → 124 帧 ≈ 5.2 秒，不再缩成 4.5 秒）
            with open(os.path.join(WF_DIR, m['wf']), encoding='utf-8') as f:
                wf = f.read()
            rep = {'__IMAGE__': in_name, '__PROMPT__': json.dumps(j['prompt'])[1:-1], '__NEG__': json.dumps(j['negative'])[1:-1], '__PREFIX__': f'studio_{tag}'}
            for k, v in rep.items():
                wf = wf.replace(k, v)
            wf = json.loads(wf)
            if not j.get('_img'):  # H3 没有首帧：去掉首帧（只按文字 / 参考 / 关键帧生成）
                wf.pop('1', None); wf['7']['inputs'].pop('first_frame', None)
    except BaseException:
        _clean_in(work_in, tag)
        raise
    t = TUNE[j['model']]
    nums = {'__W__': w, '__H__': h, '__FRAMES__': frames, '__SEED__': j['seed'], '__STEPS__': j['steps'], '__FPS__': fps, '__SECONDS__': j['seconds'],
            '__SAMPLER__': j.get('sampler') or t['sampler'], '__SCHEDULER__': j.get('scheduler') or t['scheduler'], '__SHIFT__': j.get('shift') or t['shift'],
            '__CFG__': j.get('cfg') or t.get('cfg', 1.0), '__SPLIT__': j.get('split') or max(1, j['steps'] // 2)}
    nums['__H3DIFF__'] = h3_diffusion() and os.path.basename(h3_diffusion())
    nums['__TURBO_W__'] = 1.0
    _bypass(wf, ['20', '21', '30'])  # 工作流模板里预留的 LoRA 节点：不用
    # 自选 LoRA：H3 接在采样偏移 17 前面——
    # 要在下面去掉 17 之前接：去掉 17 时用到它的地方会改接 LoRA（以前先去掉 17 再接，H3 生视频加 LoRA 会报 KeyError '17'，2026-11-04 修）
    tb = j.get('_turbo')
    if tb and '17' in wf:  # 测试：加速 LoRA（接在采样偏移前面，和自选 LoRA 一样的位置）
        wf['e34'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': wf['17']['inputs']['model'], 'lora_name': tb['lora'], 'strength_model': 1.0}}
        wf['17']['inputs']['model'] = ['e34', 0]
    for n, L in enumerate(j.get('loras') or []):
        for k, cid in enumerate(['17']):
            nid = f'9{n}{k}'
            wf[nid] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': wf[cid]['inputs']['model'], 'lora_name': L['name'], 'strength_model': L['w']}}
            wf[cid]['inputs']['model'] = [nid, 0]
    nums['__ASHIFT__'] = j.get('ashift') or t.get('ashift', 3.0)
    if tb and '17' in wf:  # 加速 LoRA：用它的偏移（放在这里：上面那行会把声音偏移改回默认）
        nums['__SHIFT__'], nums['__ASHIFT__'] = tb['shift'], tb['ashift']
    if nums['__SHIFT__'] == t['shift'] and nums['__ASHIFT__'] == t['ashift']:
        _bypass(wf, ['17'])  # 采样偏移没改：不加这个节点，和原来完全一样
    cv = next(n for n in wf.values() if n['class_type'] == 'CreateVideo')
    if not j.get('audio', True):  # 不要声音：不解码声音，视频里也不放
        wf.pop('14', None); cv['inputs'].pop('audio', None)
    if j.get('_end'):  # 首尾帧：H3 的 MiniMaxH3ImageToVideo 本身就有 last_frame
        wf['40'] = {'class_type': 'LoadImage', 'inputs': {'image': end_name}}
        wf['7']['inputs']['last_frame'] = ['40', 0]
    apply_h3opt(j, wf)  # H3：稀疏注意力 / INT8 注意力 / INT8 VAE（见 H3OPT）
    if j.get('_x'):  # H3 的更多条件：关键帧、开头片段、指定声音、参考模式（见 h3extra.py）
        try:
            h3extra.apply(j, wf, work_in, tag, w, h, frames, fps)
        except BaseException:
            _clean_in(work_in, tag)
            raise
    # 插帧：能用模型就在工作流里做（解码之后、超分之前，按原分辨率插），帧率正好乘倍数——动作速度不变；太大或没有模型时交给 ffmpeg
    ix = j.get('interp_x') or (2 if j.get('interp') else 1)
    by = j.get('interp_by') or 'rife'
    if ix > 1 and by != 'ff':
        by = by if _have(INTERP[by]) else next(iter(interp_ok()), 'ff')
    if ix > 1 and by != 'ff' and frames * ix * w * h * 12 > INTERP_MAX:
        by = 'ff'
    post = False  # 以前“贴回原视频”的做法（保真替换 / 参考编辑）要把插帧、超分放到贴回之后；那两个做法去掉了
    rife = ix > 1 and by != 'ff'
    if rife:
        wf['60'] = {'class_type': 'FrameInterpolationModelLoader', 'inputs': {'model_name': os.path.basename(INTERP[by])}}
        wf['61'] = {'class_type': 'FrameInterpolate', 'inputs': {'interp_model': ['60', 0], 'images': cv['inputs']['images'], 'multiplier': ix}}
        cv['inputs']['images'] = ['61', 0]
    up, ff_up = None, False
    if j.get('upscale') and not post:  # 超分：能用模型就在工作流里放大每一帧（解码之后、合成视频之前）；太大或没有模型就交给 ffmpeg
        if upscaler_ok() and frames * (ix if rife else 1) * w * h * 4 * 3 * 4 <= UPSCALE_MAX:
            wf['50'] = {'class_type': 'UpscaleModelLoader', 'inputs': {'model_name': os.path.basename(UPSCALER)}}
            wf['51'] = {'class_type': 'ImageUpscaleWithModel', 'inputs': {'upscale_model': ['50', 0], 'image': cv['inputs']['images']}}
            cv['inputs']['images'] = ['51', 0]
            up = 'Real-ESRGAN x2'
        else:
            up, ff_up = 'Lanczos x2', True
    for node in wf.values():
        for k, v in list(node.get('inputs', {}).items()):
            if isinstance(v, str) and v in nums:
                node['inputs'][k] = nums[v]
    if rife:
        cv['inputs']['fps'] = fps * ix
    if j.get('engine') == '2':  # ② 他的节点：条件 → 采样 → 解码这一段换成 T8（见 h3methods.py）
        import h3methods
        try:
            tb = j.get('_turbo')
            wf = h3methods.to_t8(wf, vae_int8=h3opt(j)['vae'] == 'int8', **({'keep_lora': tb['lora'], 'steps': tb['steps'], 'shift': tb['shift'], 'ashift': tb['ashift']} if tb else {'steps': j['steps']} if j['steps'] != h3methods.T8_STEPS else {}))
        except BaseException:
            _clean_in(work_in, tag)
            raise
    return _Ctx(m=m, sp=sp, tag=tag, ed=ed, wf=wf, work_in=work_in, work_out=work_out, src_name=src_name, src_audio=src_audio, w=w, h=h, frames=frames, fps=fps, nums=nums, tb=tb, ix=ix, by=by, post=post, rife=rife, up=up, ff_up=ff_up)


def _exec_one(j, c):
    """把一单的工作流交给视频引擎，等它做完，返回 outputs（显存地址空间不够时自动释放 / 重启后重试）"""
    wf = c.wf
    cid = uuid.uuid4().hex
    total = {'v': 0, 'max': 1}
    cur = {'cls': ''}
    seen = {'t': time.time(), 'chk': 0.0}  # 2026-11-14 审查：最后一次收到引擎进度消息的时间（超过 10 分钟没动静就去问引擎队列里还有没有这一单）

    def on_msg(msg):
        seen['t'] = time.time()
        if msg.get('type') == 'progress':
            d = msg.get('data') or {}
            total['v'], total['max'] = d.get('value', 0), max(1, d.get('max', 1))
            j['progress'] = round(100 * total['v'] / total['max'])
            c = cur['cls']
            if c in SAMPLER_NODES:  # value = 已经做完几步：显示正在做的那一步
                j['message'] = f"正在生成 · 第 {min(total['v'] + 1, total['max'])}/{total['max']} 步"
            elif c.startswith('SAM3'):
                j['message'] = f"{cur.get('sam', '正在识别衣服')}… {j['progress']}%"
            else:  # 识别动作、超分、插帧、解码……：沿用这一步的名字，加百分比
                j['message'] = f"{cur.get('step') or '正在处理'}… {j['progress']}%"
        elif msg.get('type') == 'executing' and (msg.get('data') or {}).get('node'):
            nid = str(msg['data']['node'])
            node = wf.get(nid, {})
            nm = cur['cls'] = node.get('class_type', '')
            if nm in ('SAM3_VideoTrack', 'SAM3_Detect'):  # 改衣：逐帧找衣服（e22）/ 找脸、头发、手（e41）/ 生成后去毛边（e45）——进度是帧数，不是采样步数（SAM3_TrackToMask 不改提示）
                cur['sam'] = {'e41': '正在识别脸、头发和手', 'e45': '正在去除毛边', 'o2rsp': '正在识别原视频中的人物', 'o2rsf': '正在识别原视频中的脸部', 'o2rop': '正在识别生成结果中的人物'}.get(nid, '正在识别衣服')
                j['message'], j['progress'] = cur['sam'] + '…', 0
                return
            if nm in SAMPLER_NODES:  # 第 1 步开始前，引擎先把主模型搬进显存（实测 75~115 秒，docs/AB测试/载入速度_1111）：这段时间算在第 1 步里
                j['message'], j['progress'] = f"正在把主模型载入显存 · 第 1/{j.get('steps') or '?'} 步", 0
                return
            step = step_name(nid, node)
            if step:
                cur['step'] = step
                j['message'], j['progress'] = step + '…', 0
    done = {'v': False}
    th = threading.Thread(target=_ws_progress, args=(cid, on_msg, lambda: done['v']), daemon=True)
    th.start()
    try:
        prompttrace.capture_workflow(j, wf)
        for attempt in range(3):  # 显存地址空间不够（VBAR）：第 1 次释放全部模型重试，第 2 次重启引擎重试
            pid = None
            try:
                pid = _submit(wf, cid)
                j['message'] = '已交给视频引擎，等待开始…'
                last_int, hst = 0.0, {}
                while True:
                    time.sleep(1.5)
                    Engine.last = time.time()
                    if j['cancel'] and time.time() - last_int > 5:  # 取消了还在跑（比如点取消时还在载入模型，ComfyUI 没理那次中断）：每 5 秒再中断一次，直到真的停下
                        last_int = time.time()
                        try:
                            _http('/interrupt', {}, timeout=5)
                        except Exception:
                            pass
                    hist = _history(pid, hst)  # 引擎忙得回不了话（载入大模型时常见）：None，接着等
                    if isinstance(hist, dict) and pid in hist:
                        st = hist[pid].get('status') or {}
                        if j['cancel']:  # 取消时 ComfyUI 把被中断的任务记成 error（只有 execution_interrupted）：按取消处理
                            raise InterruptedError
                        if st.get('status_str') == 'error' or (st.get('completed') is False and any(x[0] == 'execution_error' for x in st.get('messages', []))):
                            err = next((x[1] for x in st.get('messages', []) if x[0] == 'execution_error'), {})
                            m_ = str(err.get('exception_message') or err)
                            if _is_vbar(m_):
                                raise _Vbar(m_)
                            raise RuntimeError(_friendly(m_))
                        if st.get('completed') or hist[pid].get('outputs'):
                            outs = hist[pid].get('outputs') or {}
                            break
                    if Engine.proc and Engine.proc.poll() is not None and not Engine.alive():  # 记着的进程没了、端口上也没人：真的退出了
                        raise RuntimeError('视频引擎意外退出（通常是显存或内存不足），详情见 studio/comfy-engine.log')
                    if time.time() - seen['t'] > 600 and time.time() - seen['chk'] > 60:  # 10 分钟没有任何进度消息：引擎队列里还有这一单就接着等（慢的一步），没有了就是丢了
                        seen['chk'] = time.time()
                        try:
                            q = _http('/queue', timeout=10) or {}
                            inq = any(isinstance(x, list) and len(x) > 1 and x[1] == pid for k in ('queue_running', 'queue_pending') for x in q.get(k) or [])
                            if not inq and not (isinstance(hist, dict) and pid in hist):
                                raise RuntimeError('视频引擎里找不到这一单了（可能被别的程序清掉了队列），请重新生成')
                        except RuntimeError:
                            raise
                        except Exception:
                            pass  # 引擎忙得回不了话：接着等
                break
            except _Vbar:
                if attempt == 2:
                    raise RuntimeError('显存地址空间不够（VBAR）：已自动释放模型、重启视频引擎后仍失败，请重启电脑后再试')
                if attempt == 0:
                    act('视频引擎的显存地址空间不够（VBAR），释放全部模型后重试', 'video', 'warn')
                    j['message'] = '显存地址空间不够，正在释放模型后重试…'
                    Engine.free()
                else:
                    act('释放模型后仍不够，重启视频引擎后重试', 'video', 'warn')
                    j['message'] = '正在重启视频引擎后重试…'
                    Engine.restart()
            except InterruptedError:
                raise
            except Exception:
                _drop(pid)  # Studio 判失败了（不是取消）：引擎里这一单也取消，不在后台白跑、挡着后面的
                raise
    finally:
        done['v'] = True
    return outs


def _finish(j, c, outs):
    """做完之后的收尾（_finish_body）；中途出错时把已经放进视频库文件夹、却还没登记的文件删掉（以前留下没人认领的视频，2026-11-16 审查）"""
    j['_made'] = []
    try:
        return _finish_body(j, c, outs)
    except BaseException:
        for p in j.get('_made') or []:
            try:
                os.remove(p)
            except OSError:
                pass
        raise
    finally:
        j.pop('_made', None)


def _finish_body(j, c, outs):
    """引擎做完之后：拿到成品文件、配原声、插帧 / 超分、裁成选的那一段、调色、存进视频库"""
    m, sp, tag, ed, work_in, work_out, src_name, src_audio, w, h, frames, fps = c.m, c.sp, c.tag, c.ed, c.work_in, c.work_out, c.src_name, c.src_audio, c.w, c.h, c.frames, c.fps
    nums, tb, ix, by, post, rife, up, ff_up = c.nums, c.tb, c.ix, c.by, c.post, c.rife, c.up, c.ff_up
    if ed:
        import videoedit
    files = []
    for o in outs.values():
        for key in ('gifs', 'videos', 'images', 'animated'):
            for it in o.get(key, []) or []:
                # 只要保存出来的成品：改视频的 LoadVideo 也会在 outputs 里报一条（type = input，是原视频本身，不在输出目录）
                if isinstance(it, dict) and it.get('type', 'output') == 'output' and it.get('filename', '').lower().endswith(('.mp4', '.webm', '.mov')):
                    files.append(os.path.join(work_out, it.get('subfolder', ''), it['filename']))
    if j['cancel']:
        raise InterruptedError
    masks = [f for f in files if os.path.basename(f).startswith(f'studio_{tag}_mask')]
    files = [f for f in files if f not in masks]
    if not files:
        raise RuntimeError('生成已完成，但未找到视频文件')
    src = files[0]
    for mf in masks:  # 局部生成测试（edit.loc.dump）：mask 另存一份 <任务>_mask.mp4（分析用；_mask_raw 等是 11-12 测接缝用的）
        sfx = re.match(r'(_[a-z]+)?_\d+_?\.', os.path.basename(mf)[len(f'studio_{tag}_mask'):])
        try:
            shutil.copyfile(mf, vfile(sp, f'{tag}_mask{(sfx.group(1) or "") if sfx else ""}.mp4'))
        except OSError:
            pass
    name = nice_name(sp, item_label({'edit': ed, 'model': j['model'], 'model_name': j['model_name']}))  # “11-06 21.30 改衣.mp4”（2026-11-06）
    dst = vfile(sp, name)
    os.replace(src, dst)
    j['_made'].append(dst)
    if post and (ix > 1 or j.get('upscale')):  # 贴回之后再插帧 / 超分（模型做；不行就交给下面的 ffmpeg）
        rife, ff_up, up = _post_fx(j, dst, work_in, work_out, tag, fps, ix, by, w, h, frames)
        if not rife and ix > 1:
            by = 'ff'
    if ed:  # 查问题用：模型刚做完（配声音、裁剪之前）有多少帧
        ed['raw_frames'] = _probe(dst).get('frames')
    if ed and ed['audio'] == 'keep' and src_audio:  # 改视频保留原声：成品里放原视频那一段的声音
        j['message'], j['progress'] = '正在恢复原声…', 100
        videoedit.mux_audio(j, dst, os.path.join(work_in, src_name))
    # 后处理（ffmpeg）：插帧 2 倍——帧率跟着翻倍、时长不变，不会变成慢动作；超分没用上模型时在这里用 lanczos 放大
    # 末尾先多留两帧（tpad）再插，输出正好 2 倍帧数：时长和原来完全一样（不然最后一帧的那段会被吃掉）
    vf = ([f'tpad=stop_mode=clone:stop={ix}', f'minterpolate=fps={fps * ix}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'] if ix > 1 and not rife else []) + (['scale=iw*2:ih*2:flags=lanczos'] if ff_up else [])
    if vf:
        ffi = ix > 1 and not rife
        j['message'], j['progress'] = ('插帧中…' if ffi else '超分中…'), 100
        tmp = vfile(sp, f'{tag}.pp.mp4')
        n0 = _probe(dst).get('frames') if ffi else 0
        try:
            _ff(j, ['-i', dst, '-vf', ','.join(vf), *(['-frames:v', str(n0 * ix)] if n0 else []),
                    '-c:v', 'libx264', *GOP, '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', tmp],
                '插帧' if ffi else '超分')
            os.replace(tmp, dst)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            try:  # 取消了：这段也不要了
                if j.get('cancel'):
                    os.remove(dst)
            except OSError:
                pass
            raise
    trimmed = None  # 改视频（H3）：裁成正好选的那一段（选多长就是多长，每一帧都是生成的，2026-11-05）
    if ed and ed.get('win') is not None and src_name and os.path.isfile(os.path.join(work_in, src_name)):
        j['message'], j['progress'] = '正在裁成选的那一段…', 100
        try:
            trimmed = videoedit.exact_trim(j, dst, os.path.join(work_in, src_name))
        except Exception as ex:
            if j.get('cancel'):
                raise
            j['warn'] = f'没能裁成正好选的那一段（{ex}），保留了生成的整段'
    raw_file = None
    if ed and ed.get('cmatch') and src_name and os.path.isfile(os.path.join(work_in, src_name)) and not j.get('cancel'):
        # 自动匹配原视频色调（2026-11-10 用户：H3 的成品偏暗、肤色偏红）：只改颜色；调色前的那份留在 _辅助文件/未调色
        j['message'], j['progress'] = '正在匹配原视频色调…', 100
        import colorfix
        tmp = dst + '.cm.mp4'
        try:
            raw_file = f'{tag}_raw.mp4'
            shutil.copyfile(dst, vfile(sp, raw_file)); j['_made'].append(vfile(sp, raw_file))
            colorfix.fix(FFMPEG, dst, tmp, 'match', src=os.path.join(work_in, src_name), work=work_in)
            os.replace(tmp, dst)
        except Exception as ex:
            if raw_file:  # 调色没成：未调色的副本也不要了（以前留着）
                try:
                    os.remove(vfile(sp, raw_file))
                except OSError:
                    pass
            raw_file = None
            j['warn'] = f'匹配原视频色调没有成功（{ex}），保留了原样'
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    pr = _probe(dst)
    thumb = _thumb(j, dst, sp, f'{tag}.jpg')
    item = {'id': uuid.uuid4().hex[:12], 'file': name, 'thumb': thumb, 'job': tag, 'model': j['model'], 'model_name': j['model_name'],
            'prompt': j['prompt'], 'prompt_trace': prompttrace.snapshot(j), 'negative': j['negative'], 'seconds': j['seconds'], 'steps': j['steps'], 'size': j['size'], 'seed': j['seed'],
            'width': pr.get('width') or w, 'height': pr.get('height') or h, 'fps': round(pr.get('fps') or fps * ix, 2), 'gen_fps': fps,
            'frames': pr.get('frames') or frames, 'duration': pr.get('duration'), 'gen_size': f'{w}×{h}', 'res': j.get('res'),
            'audio': bool(pr['audio']) if 'audio' in pr else (m['audio'] and j.get('audio', True)), 'created': time.time(), 'took': round(time.time() - j['_t0'], 1), 'src_id': j.get('src_id'),
            'sampler': nums['__SAMPLER__'], 'scheduler': nums['__SCHEDULER__'],
            # 这次真正用的偏移：② 秋叶节点用它自己的（12 / 3，开了加速按 LoRA 的），① 按工作流里的（2026-11-06：以前 ② 也记成填的值）
            'shift': (tb['shift'] if tb else 12.0) if j.get('engine') == '2' else nums['__SHIFT__'],
            'ashift': (tb['ashift'] if tb else 3.0) if j.get('engine') == '2' else nums['__ASHIFT__'],
            'turbo': {'lora': tb['lora'], 'kind': tb.get('kind')} if tb else None,
            'interp': bool(j.get('interp')), 'interp_x': ix, 'interp_by': (INTERP_NAME[by] if ix > 1 else None), 'loras': j.get('loras') or [], 'upscale': up, 'flf': bool(j.get('_end')), 'end_id': j.get('end_id'), 'chain_of': j.get('chain_of'), 'h3x': j.get('h3x'), 'h3opt': j.get('h3opt_used'),
            'base': j.get('base'), 'engine': j.get('engine'),
            **({'edit': {**{k: ed[k] for k in ('task', 'swap_by', 'target', 'audio', 'start')}, 'want': ed.get('want'), 'win': ed.get('win'), 'exact': bool(trimmed), 'trim': ed.get('trim'), 'raw_frames': ed.get('raw_frames'), 'base': ed.get('base', 'full'), 'ref': ed.get('ref', False), 'tpl': ed.get('tpl', True),
                             'method': ed.get('method'), 'own': ed.get('own', False), 'splice': bool(ed.get('splice')), 'qshare': ed.get('qshare'), 'qshared': bool(ed.get('qshared')),
                             # 详情里要看得出来（2026-11-08）：以前没存，首帧锁定在详情里永远显示不出来
                             'ffguide': bool(ed.get('ffguide')), 'cmatch': bool(raw_file), 'pose': bool(ed.get('pose')), 'plang': ed.get('plang'), 'qwen': bool(ed.get('qwen_done')), 'pick_idx': ed.get('pick_idx'),
                             'recipe': ed.get('recipe'), 'ref_desc': ed.get('ref_desc'), 'ref_env': ed.get('ref_env'), 'loc': ed.get('loc'), 'head_by': ed.get('head_by'), 'vg': bool(ed.get('vg'))}, 'src_vid': j.get('src_vid')} if ed else {})}
    if raw_file:
        item['raw_file'] = raw_file  # 自动调色前的原样（_辅助文件/未调色）
    if ed and ed.get('splice') and j.get('_vid'):  # 选段时选了拼接：留一份完整的原视频，成品可以拼回去
        try:
            fn = save_source(sp, j['_vid'], videoedit.video_kind(j['_vid']) or 'mp4')  # 按内容存一份：同一个原视频的几段共用（2026-11-06，以前每段各存一份）
            item['splice_src'] = fn
            item['grp'] = _src_key(vfile(sp, fn))  # 视频组：同一个原视频的片段归在一起（ensure_groups）
        except OSError:
            pass
    if ed and j.get('_redo'):  # 重新生成：存下这次的设置、原视频和人物图（同样的文件只存一份，几段共用）
        try:
            item['redo'] = _redo_save(sp, *j['_redo'])
        except OSError:
            pass
    if ed and src_name and os.path.isfile(os.path.join(work_in, src_name)):  # 对比用的原视频：处理过的那份（起点、帧率、尺寸和成品一致）
        try:
            shutil.copyfile(os.path.join(work_in, src_name), vfile(sp, f'{tag}_src.mp4'))
            item['src_file'] = f'{tag}_src.mp4'
        except OSError:
            pass
        if trimmed:  # 已经按帧差裁好、对齐了：对比、拼接都不用再错开
            item['lag'], item['lag_c'], item['lag_v'] = 0.0, trimmed[1], 2
        elif item.get('src_file'):  # 做完后在后台量一下成品和原视频差几帧（对比、拼接时对齐用）
            threading.Thread(target=lambda iid=item['id'], s=sp: (time.sleep(3), ensure_lag(iid, s)), daemon=True).start()
    merged = None
    if j.get('chain_of'):
        try:
            merged = _merge(j, sp, item)
        except InterruptedError:  # 合并时取消：这一段照样留下，只是不合并
            j['warn'] = '已取消合并，此段已保存'
        except Exception as e:  # 合并失败不影响这一段
            j['warn'] = '此段已完成，但与前面的片段合并失败：' + str(e)[:200]
            act(j['warn'], 'video', 'warn')
        if merged:
            item['merged_id'] = merged['id']
    _gallery_add(sp, item)
    if merged:
        _gallery_add(sp, merged)
    j['file'], j['item'] = name, (merged or item)['id']
    qc_later(sp, item['id'])  # 自动质检（设置里开了才查）


def _cleanup(j, c):
    """ComfyUI 输入 / 输出文件夹里这一单的东西都删掉（私密空间的尤其不能留）"""
    work_in, work_out, tag = c.work_in, c.work_out, c.tag
    for f in os.listdir(work_out) if os.path.isdir(work_out) else []:  # ComfyUI 输出文件夹里这次的东西（私密空间的尤其不能留）
        if f.startswith(f'studio_{tag}'):
            try:
                os.remove(os.path.join(work_out, f))
            except OSError:
                pass
    _clean_in(work_in, tag)



def _run(j):
    c = _prep_job(j)
    if c is None:
        return
    try:
        _finish(j, c, _exec_one(j, c))
    finally:
        _cleanup(j, c)


_Ctx = type('_Ctx', (), {'__init__': lambda self, **kw: self.__dict__.update(kw)})



# ---------------------------------------------------------------- 找回没收进视频库的成品
# 2026-11-12：视频引擎载入模型时忙得回不了话，旧版 Studio 等 10 秒就判失败——引擎照样做完，成品却没人收（现在不会再这样判，见 _submit / _history）。
# 这里把这种成品找回来：设置照同一次提交（任务号前 15 位相同 = 同一秒提交的几段）里已经进了视频库的那一段，
# 起点用成品和完整原视频逐帧比出来，再走和正常生成一模一样的收尾（_finish：配原声、裁成选的那一段、调色、缩略图、视频组、重新生成）
_adopt = {'tried': set(), 'busy': False}
_ADOPT_RE = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{4}$')


def _gray_frames(path, w=48, h=84):
    """视频 → 24 fps、w×h 灰度的逐帧数组（找回时对齐起点用）"""
    import numpy as np
    r = subprocess.run([FFMPEG, '-v', 'error', '-i', path, '-vf', f'fps=24,scale={w}:{h},format=gray', '-f', 'rawvideo', '-'],
                       capture_output=True, timeout=600, creationflags=NO_WINDOW)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (w * h)
    a = a[:n * w * h].reshape(n, h, w).astype(np.float32)
    a -= a.mean(axis=(1, 2), keepdims=True)  # 每帧减掉平均亮度、除以对比度：生成的整体偏暗也不影响对齐
    a /= a.std(axis=(1, 2), keepdims=True) + 1e-3
    return a


def align_start(gen_path, full_path):
    """生成的窗口（prepare 裁出来的那段，24 fps）在完整原视频里从第几帧开始：逐个偏移比，差最小的那个。返回 (窗口起点秒, 把握)"""
    import numpy as np
    g, f = _gray_frames(gen_path), _gray_frames(full_path)
    n = len(g)
    if not n or len(f) < n:
        return None, 0.0
    errs = np.array([float(((f[o:o + n] - g) ** 2).mean()) for o in range(len(f) - n + 1)])
    o = int(errs.argmin())
    rest = np.delete(errs, range(max(0, o - 3), o + 4))
    conf = float((np.median(rest) - errs[o]) / (np.median(rest) + 1e-6)) if rest.size else 0.0
    return (o - round(H3_LAG * 24)) / 24, conf  # 成品通常早 2 帧：窗口起点比最像的那一帧早 2 帧


def adopt_orphans(sp):
    """在后台找回引擎做完、但没收进视频库的成品（见上）。同一时间只跑一个；每个任务号只试一次"""
    if _adopt['busy'] or not Engine.alive():
        return
    _adopt['busy'] = True
    threading.Thread(target=_adopt_run, args=(sp,), daemon=True).start()


def _adopt_run(sp):
    try:
        try:
            hist = _http('/history?max_items=64', timeout=15)
        except Exception:
            return
        if not isinstance(hist, dict):
            return
        work_out = os.path.join(WORK['n'], 'out')
        g = gallery(sp)
        have = {x.get('job') for x in g}
        for pid, h in hist.items():
            try:
                wf = (h.get('prompt') or [None, None, {}])[2] or {}
                pre = next((n['inputs'].get('filename_prefix') for n in wf.values() if isinstance(n, dict) and n.get('class_type') == 'SaveVideo'), '') or ''
                tag = pre[len('studio_'):] if pre.startswith('studio_') else ''
                if not _ADOPT_RE.match(tag) or tag in have or tag in _adopt['tried']:
                    continue
                if (jobs.get(tag) or {}).get('state') in ('queued', 'running', 'done'):
                    continue  # 这次开着的 Studio 自己在管
                if (h.get('status') or {}).get('status_str') != 'success':
                    continue
                files = [os.path.join(work_out, it.get('subfolder', ''), it['filename']) for o in (h.get('outputs') or {}).values()
                         for it in (o.get('images') or o.get('videos') or o.get('gifs') or []) if isinstance(it, dict) and str(it.get('filename', '')).endswith('.mp4')]
                files = [f for f in files if os.path.isfile(f)]
                sib = next((x for x in g if str(x.get('job') or '')[:15] == tag[:15] and x.get('edit') and (x.get('redo') or {}).get('vid')), None)
                if not files or not sib:
                    continue  # 成品已经不在了 / 这个空间里没有同一次提交的另一段（别的空间的，或者补不全设置）
                _adopt['tried'].add(tag)
                _adopt_one(sp, tag, pid, h, wf, files[0], sib)
            except Exception as e:
                act(f'找回没收进视频库的成品失败（{tag or pid}）：{e}', 'video', 'warn')
    finally:
        _adopt['busy'] = False


def _adopt_one(sp, tag, pid, h, wf, out_file, sib):
    import math, videoedit
    b0, img, vid = redo_input(sib['id'], sp)  # 同一次提交那一段当时的请求、人物图、完整原视频
    rd = os.path.join(videos_dir(sp), 'redo', os.path.basename(sib['redo']['vid']))
    ws, conf = align_start(out_file, rd)
    if ws is None or conf < 0.15:
        raise RuntimeError(f'没能在原视频里对上这一段（把握 {conf:.2f}）')
    t8 = next((n['inputs'] for n in wf.values() if isinstance(n, dict) and n.get('class_type') in ('MiniMaxH3AudioConditioningT8', 'MiniMaxH3ReferenceToVideo')), {})
    vgc = next((n['inputs'] for n in wf.values() if isinstance(n, dict) and n.get('class_type') == 'RemakeConditioning'), {})  # Viggle：帧数在这里（以前只看 H3 节点，读成 0，2026-11-16 审查）
    frames = int(vgc.get('frames') or t8.get('length') or 0)
    seed = next((n['inputs'].get('noise_seed') for n in wf.values() if isinstance(n, dict) and n.get('class_type') == 'RandomNoise'), None)
    s0 = round(max(0.0, ws) + 3 / videoedit.FPS, 4)
    # 选段多长：窗口能装下的最长（成品里每一帧都是生成的）；同一次提交的另一段正好接在后面时，就到它的起点为止
    wmax = math.floor((frames - 3) / videoedit.FPS * 1000) / 1000  # 往下取整：往上取一点就多出一档（17 帧）
    want = wmax
    se = float((sib.get('edit') or {}).get('start') or 0)
    if s0 < se < s0 + wmax + 0.05 and se - s0 > wmax - 0.75:
        want = min(wmax, math.floor((se - s0) * 1000) / 1000)
    b = {**b0, 'seed': seed if isinstance(seed, int) else b0.get('seed', -1), 'seconds': want, 'edit': {**b0['edit'], 'start': s0, 'end': round(s0 + want, 3)}}
    edit = videoedit.parse(b, vid, img)
    edit['want'] = want
    j = {'id': tag, 'space': sp, 'state': 'running', 'model': 'h3', 'model_name': sib.get('model_name'), 'engine': sib.get('engine'), 'base': sib.get('base'),
         'prompt': sib.get('prompt') or '', 'negative': '', 'seconds': max(1, int(want)), 'steps': sib.get('steps'), 'size': sib.get('size'), 'seed': b['seed'],
         'res': sib.get('res'), 'edit': edit, 'src_vid': sib.get('src_vid'), 'src_id': sib.get('src_id'), '_img': img, '_vid': vid, 'cancel': False,
         'loras': sib.get('loras') or [], 'interp': False, 'upscale': None, 'h3opt_used': sib.get('h3opt'), 'chain_of': None,
         '_redo': (b, vid, img), 'message': '', 'progress': 0,
         '_ffmpeg': lambda *a: subprocess.run([FFMPEG, '-y', '-v', 'error', *a], check=True, capture_output=True, timeout=120, creationflags=NO_WINDOW)}  # 缩略图用
    for k in ('pick_idx',):
        if (sib.get('edit') or {}).get(k) is not None:
            edit[k] = sib['edit'][k]
    if (sib.get('edit') or {}).get('qwen'):
        edit['qwen_done'] = True
    import prompttrace
    j['prompt_trace'] = prompttrace.new(b.get('prompt_input', b.get('prompt', '')))
    prompttrace.capture_workflow(j, wf)
    msgs = (h.get('status') or {}).get('messages') or []
    ts = [m[1].get('timestamp') for m in msgs if isinstance(m, list) and len(m) > 1 and isinstance(m[1], dict) and m[1].get('timestamp')]
    j['_t0'] = (min(ts) / 1000) if ts else time.time()
    end_t = (max(ts) / 1000) if ts else time.time()
    work_in, work_out = os.path.join(WORK['n'], 'in'), os.path.join(WORK['n'], 'out')
    w, hh, fr, src_name, src_audio = videoedit.prepare(j, work_in, tag)  # 按同样的规则重新裁一份原视频片段（配原声、裁段、对比都要它）
    if fr != frames:
        _clean_in(work_in, tag)
        raise RuntimeError(f'裁出来的长度对不上（{fr} 帧，成品 {frames} 帧）')
    tb = ({'lora': (sib.get('turbo') or {}).get('lora'), 'kind': (sib.get('turbo') or {}).get('kind'), 'shift': sib.get('shift'), 'ashift': sib.get('ashift')}
          if sib.get('turbo') else None)
    nums = {'__SAMPLER__': sib.get('sampler'), '__SCHEDULER__': sib.get('scheduler'), '__SHIFT__': sib.get('shift'), '__ASHIFT__': sib.get('ashift')}
    c = _Ctx(m=MODELS['h3'], sp=sp, tag=tag, ed=edit, wf=wf, work_in=work_in, work_out=work_out, src_name=src_name, src_audio=src_audio,
             w=w, h=hh, frames=frames, fps=videoedit.FPS, nums=nums, tb=tb, ix=1, by='rife', post=False, rife=False, up=None, ff_up=False)
    outs = h.get('outputs') or {}
    try:
        _finish(j, c, outs)
    finally:
        _cleanup(j, c)
    it = gallery_get(j.get('item'), sp)
    if it:  # “用时”按引擎里真正生成的时间（不算 Studio 误判之后到现在这段）
        _index_set(sp, it['id'], {'took': round(end_t - j['_t0'], 1), 'adopted': True})
    act(f'已找回一段没收进视频库的成品（{s0:.1f}–{s0 + want:.1f} 秒，对齐把握 {conf:.2f}）', 'video', 'ok')


_last_model = None


def _run_wf(j, wf, work_out, msg, limit=1800):
    """在视频引擎上跑一个辅助工作流（超分、插帧、AI 修复……），等它做完，返回 outputs。能取消（原来在 outfit3.py，2026-11-06 去掉 Wan 后挪到这里）"""
    j['message'], j['progress'] = msg, 0
    prompttrace.capture_workflow(j, wf)
    pid = _submit(wf, uuid.uuid4().hex)
    try:
        return _wait_wf(j, pid, msg, limit)
    except BaseException:
        _drop(pid)  # 超时 / 出错 / 取消：引擎里这一单也取消（以前超时后它还在跑，挡着后面的任务、占着显存，2026-11-16 审查）
        raise


def _wait_wf(j, pid, msg, limit):
    t0, hst = time.time(), {}
    while time.time() - t0 < limit:
        time.sleep(1)
        Engine.last = time.time()
        if j.get('cancel'):
            raise InterruptedError
        h = _history(pid, hst)
        if isinstance(h, dict) and pid in h:
            st = h[pid].get('status') or {}
            if st.get('status_str') == 'error':
                err = next((x[1] for x in st.get('messages', []) if x[0] == 'execution_error'), {})
                raise RuntimeError(_friendly(str(err.get('exception_message') or err)))
            if st.get('completed') or h[pid].get('outputs'):
                return h[pid].get('outputs') or {}
        if Engine.proc and Engine.proc.poll() is not None and not Engine.alive():
            raise RuntimeError('视频引擎意外退出（通常是显存或内存不足），详情见 studio/comfy-engine.log')
    raise RuntimeError(msg.rstrip('…') + '超时')


def _post_fx(j, dst, work_in, work_out, tag, fps, ix, by, w, h, frames):
    """在已经贴回好的成品上用模型插帧（RIFE / FILM）、超分（Real-ESRGAN）。返回 (插帧用了模型, 超分还要 ffmpeg 做, 超分说明)"""
    want_up = bool(j.get('upscale'))
    m_up = want_up and upscaler_ok() and frames * max(1, ix) * w * h * 4 * 3 * 4 <= UPSCALE_MAX
    m_ix = ix if ix > 1 and by != 'ff' and frames * ix * w * h * 12 * (4 if m_up else 1) <= INTERP_MAX else 1
    if not m_up and m_ix == 1:
        return False, want_up, ('Lanczos x2' if want_up else None)
    pname = f'studio_{tag}_pp.mp4'
    shutil.copy(dst, os.path.join(work_in, pname))
    wf = {'l': {'class_type': 'LoadVideo', 'inputs': {'file': pname}}, 'g': {'class_type': 'GetVideoComponents', 'inputs': {'video': ['l', 0]}}}
    img = ['g', 0]
    if m_up:
        wf['u0'] = {'class_type': 'UpscaleModelLoader', 'inputs': {'model_name': os.path.basename(UPSCALER)}}
        wf['u1'] = {'class_type': 'ImageUpscaleWithModel', 'inputs': {'upscale_model': ['u0', 0], 'image': img}}
        img = ['u1', 0]
    if m_ix > 1:
        wf['r0'] = {'class_type': 'FrameInterpolationModelLoader', 'inputs': {'model_name': os.path.basename(INTERP[by])}}
        wf['r1'] = {'class_type': 'FrameInterpolate', 'inputs': {'interp_model': ['r0', 0], 'images': img, 'multiplier': m_ix}}
        img = ['r1', 0]
    wf['c'] = {'class_type': 'CreateVideo', 'inputs': {'images': img, 'fps': fps * m_ix}}
    wf['s'] = {'class_type': 'SaveVideo', 'inputs': {'video': ['c', 0], 'filename_prefix': f'studio_{tag}_pp', 'format': 'mp4', 'codec': 'h264'}}
    try:
        outs = _run_wf(j, wf, work_out, '插帧中…' if m_ix > 1 else '超分中…')
        got = [os.path.join(work_out, it.get('subfolder', ''), it['filename']) for o in outs.values() for k in ('videos', 'images', 'gifs')
               for it in (o.get(k) or []) if isinstance(it, dict) and it.get('type', 'output') == 'output' and str(it.get('filename', '')).lower().endswith('.mp4')]
        if not got:
            raise RuntimeError('未产生输出')
        os.replace(got[0], dst)
        return m_ix > 1, want_up and not m_up, ('Real-ESRGAN x2' if m_up else 'Lanczos x2' if want_up else None)
    except InterruptedError:
        raise
    except Exception as e:  # 模型做不了：交给 ffmpeg
        act(f'贴回后插帧 / 超分未成功，已改用 ffmpeg：{e}', tag, 'warn')
        return False, want_up, ('Lanczos x2' if want_up else None)
    finally:
        try:
            os.remove(os.path.join(work_in, pname))
        except OSError:
            pass


def _busy():
    return any(x['state'] in ('queued', 'running') for x in list(jobs.values()))


def _pick():
    """下一个任务：队列里有和上一个同模型的，先做它（保持各自的先后顺序）；没有就按顺序"""
    head = next((k for k, x in enumerate(_q) if x['state'] != 'cancelled'), None)  # 最早的、没取消的那个（第二轮审查 8：以前队首是已取消的就不看了）
    if head is not None and time.time() - (_q[head].get('created') or time.time()) > 1800:  # 等了 30 分钟以上：先做它，不再让同模型的插队（审查 29）
        return _q.pop(head)
    for k, x in enumerate(_q):
        if x['state'] != 'cancelled' and x['model'] == _last_model:
            return _q.pop(k)
    return _q.pop(0)


def worker(take_gpu, release_gpu, stop_image):  # take_gpu(j)：等配音用完并拿到生图那把锁（imagegen._take_gpu），拿到返回 True
    while True:
        with _qcv:
            while not _q:
                _qcv.wait()
            j = _pick()
        if j['state'] == 'cancelled':
            release(j)
            continue
        try:
            j['message'] = '正在等待显卡空闲…'
            if not take_gpu(j):
                raise InterruptedError
            try:
                j['state'], j['_t0'] = 'running', time.time()
                stop_image()
                if GPU_PREPARE:
                    GPU_PREPARE()
                Engine.cancel_later()
                try:
                    global _last_model
                    if _last_model and _last_model != j['model']:
                        Engine.free()  # 换模型：先把上一个模型从内存里也放掉，两个大模型同时在内存里会把内存挤爆
                    _last_model = j['model']
                    _run_post(j) if j.get('post') else _run(j)
                finally:
                    with _qcv:  # 队列里下一个还是这个模型：模型留在内存里，下一段载入快；否则全部放掉
                        same_next = any(x['state'] != 'cancelled' and x['model'] == j['model'] for x in _q)
                    if same_next:  # 下一段还是视频：模型留在显存里直接接着做（以前每段都放掉、下一段再花一两分钟搬回来）；有配音 / 生图在等才让出来
                        if OTHERS_WAITING and OTHERS_WAITING():
                            Engine.free(keep_ram=True)
                        else:
                            Engine._hold = True
                    else:
                        Engine.free_later()
            finally:
                release_gpu()
            j['state'], j['message'], j['progress'] = 'done', '完成', 100
        except InterruptedError:
            j['state'], j['message'] = 'cancelled', '已取消'
        except Exception as e:
            j['state'], j['error'], j['message'] = 'error', str(e)[:500], '失败'
        j['finished'] = time.time()
        release(j)
