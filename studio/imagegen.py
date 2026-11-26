"""生图（stable-diffusion.cpp · Z-Image Turbo）：模型、生图引擎进程、任务队列、图库。被 server.py 调用。

- 引擎：tools/sd.cpp/sd-server.exe，用到时才启动，闲置 5 分钟自动退出（显存还给配音 / 换声）；换模型 = 重启引擎（十几秒）。
- 显卡轮流用：生图前先让配音引擎把模型从显存里放掉；配音 / 换声 / 识别 / 本地翻译要用显卡时，等手上这张图画完，生图引擎让出来，
  这个任务剩下的几张排回队首，等那边用完显卡再自动接着画。
- 图库：普通空间存 outputs/images，私密空间存 .data/images，各自一份 index.json，互相看不到。
- 一次任务可以出 1~4 张；每张画完马上存进图库，中途取消也保留已经画好的。"""
import atexit, base64, contextlib, datetime, json, os, random, re, socket, subprocess, threading, time, urllib.error, urllib.request, uuid
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import stages  # 任务计时（每一步用了多久）
import prompttrace

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
SD_DIR = config.SD_DIR  # STUDIO_SD_DIR：测试新版 sd.cpp 用
SD_EXE = os.path.join(SD_DIR, 'sd-server.exe')
MODEL_DIR = config.models('Z-Image')
PORT = 8091
IDLE_EXIT = 300
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

# 模型。base：基于哪个架构（网页按它分组）；speed：1024×1024 一张大约多久（实测）；tag：一句话特点
# 指令改图（sd.cpp）；其余模型（Z-Image、Krea 2、Qwen-Image 2.1、MOSS、H3-Image）跑在 ComfyUI 上，见 q21.MODELS
MODELS = {
    # 指令改图：上传一张图 + 一句话（“把裙子换成红色”），只改说到的部分，人物、背景、光线保持不变。
    # Phr00t 的 Qwen-Image-Edit-Rapid-AIO v23（SFW 版）：100% 基于 Qwen-Image-Edit-2511，
    # 合并了皮肤 / 写实 LoRA 和 4~8 步加速（不再另加 Lightning LoRA）。作者推荐 CFG 1、4 步、euler_ancestral + beta。
    # Q8_0（22GB）+ Qwen2.5-VL-7B 看图的文本编码器（8GB）：显存放不下，一部分放在内存里（--offload-to-cpu）；2511 底座要加 qwen_image_zero_cond_t=true
    'qedit': {'name': 'Qwen 改图 Rapid AIO v23', 'file': 'Qwen-Rapid-SFW-v23_Q8_0.gguf', 'dir': 'QwenEdit', 'base': 'Qwen 指令改图', 'speed': '约 30~60 秒', 'tag': '一句话改图',
              'llm': 'Qwen2.5-VL-7B-Instruct.Q8_0.gguf', 'vision': 'Qwen2.5-VL-7B-Instruct.mmproj-Q8_0.gguf', 'vae': 'qwen_image_vae.safetensors', 'family': 'qedit', 'edit': True,
              'args': ['--offload-to-cpu', '--max-vram', '-3', '--model-args', 'qwen_image_zero_cond_t=true'],  # --max-vram -3：始终留 3GB 显存给出图那一步（以前权重把显卡塞满，桌面程序再占一点就出不了图）
              'desc': 'Phr00t 的 Qwen-Image-Edit-Rapid-AIO v23 SFW 版（基于阿里 Qwen-Image-Edit-2511，合并了皮肤写实 LoRA、自带加速）：上传一张图，用一句话说明如何修改（换衣服、换姿势、换背景、增减物品），只修改提及的部分，长相和画风保持一致',
              'defaults': {'steps': 4, 'cfg': 1.0, 'sampler': 'euler_a', 'scheduler': 'beta'}},
}
import q21  # noqa: E402  Qwen-Image 2.1：跑在应用的 ComfyUI 上（backend = comfy，不走 sd.cpp），见 q21.py
MODELS.update(q21.MODELS)


def reload_models():
    """开源泛化 ②：模型目录改了（模型页加 / 改 / 藏了模型）以后重新读：ComfyUI 的那些换成新的，sd.cpp 的不动。返回 ComfyUI 模型数"""
    q21.load_catalog()
    for k in [k for k, m in MODELS.items() if m.get('backend') == 'comfy' and k not in q21.MODELS]:
        MODELS.pop(k)
    MODELS.update(q21.MODELS)
    return len(q21.MODELS)


def comfy(key):
    return (MODELS.get(key) or {}).get('backend') == 'comfy'


CONTROLNET = config.models('Z-Image', 'controlnet', 'Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors')  # 只给 Z-Image Turbo 系用
LLM = 'Qwen3-4B-Q8_0.gguf'  # sd.cpp 模型没写 llm 时的默认文本编码器
VAE = 'ae.safetensors'
# Turbo 是蒸馏模型：8 步左右、CFG 1 最好（CFG 调到 1 以上负面提示词才起作用，同时也会慢一倍）
DEFAULTS = {'steps': 8, 'cfg': 1.0, 'sampler': '', 'scheduler': '', 'flow_shift': None, 'eta': None, 'strength': 0.72,  # 实测：0.6 以下几乎不变，0.7 左右改颜色和细节、保留构图
            'hires': {'enabled': False, 'upscaler': 'Latent', 'scale': 1.5, 'steps': 0, 'denoise': 0.5, 'target_width': 0, 'target_height': 0}, 'vae_tiling': False,
            'vae_tile': {'size': 256, 'overlap': 0.5},
            # 采样细节（都走 extra_sample_args / guidance，留空 = 引擎默认）
            'noise_sampler': '', 'beta_alpha': None, 'beta_beta': None, 'extra_args': '',
            'apg': {'enabled': False, 'eta': 1.0, 'momentum': 0.0, 'norm_threshold': 5.0},
            'slg': {'scale': 0.0, 'layers': [7, 8, 9], 'start': 0.01, 'end': 0.2}, 'guidance': None,
            # 引擎启动参数（变了要重启引擎）：随机数生成器（cpu = 和 ComfyUI 同种子同图）、SageAttention
            'rng': 'cuda', 'sage': False,
            'cache_mode': '', 'cache_option': '', 'format': 'png', 'quality': 92, 'meta': True}
RNGS = ['cuda', 'cpu', 'std_default']
NOISE_SAMPLERS = ['iid', 'brownian_tree']


def model_defaults(key):
    """这个模型的推荐参数（通用默认 + 模型自己的）。"""
    return {**DEFAULTS, **(MODELS.get(key, {}).get('defaults') or {})}


LORA_DIR = os.path.join(MODEL_DIR, 'loras')


def lora_dir(key):  # 每种模型各用各的 LoRA（Z-Image 的 LoRA 不能给 Krea 2 用）；Qwen 2.1 的在 ComfyUI/models/loras/Qwen21（两个版本共用）
    if comfy(key):
        return q21.lora_dir(key)
    return os.path.join(model_dir(key), 'loras') if (MODELS.get(key) or {}).get('dir') else LORA_DIR            # 放 LoRA（.safetensors / .gguf）
UPSCALE_DIR = config.models('upscalers')  # 放放大模型（ESRGAN，比如 RealESRGAN_x4plus.pth）
# 引擎支持的采样器、调度器、加速缓存（引擎开着时以它报的为准，见 capabilities()）
SAMPLERS = ['euler', 'euler_a', 'heun', 'dpm2', 'dpm++2s_a', 'dpm++2m', 'dpm++2mv2', 'ipndm', 'ipndm_v', 'lcm', 'ddim_trailing', 'tcd', 'res_multistep',
            'res_2s', 'er_sde', 'euler_cfg_pp', 'euler_a_cfg_pp', 'euler_ge', 'dpm++2m_sde', 'dpm++2m_sde_bt', 'lms']
SCHEDULERS = ['discrete', 'karras', 'exponential', 'ays', 'gits', 'sgm_uniform', 'simple', 'smoothstep', 'kl_optimal', 'lcm', 'bong_tangent',
              'logit_normal', 'flux', 'beta']
CACHE_MODES = ['easycache', 'dbcache', 'taylorseer', 'cache-dit', 'spectrum']
HIRES_BUILTIN = ['Latent', 'Latent (nearest)', 'Latent (nearest-exact)', 'Latent (antialiased)', 'Latent (bicubic)', 'Latent (bicubic antialiased)', 'Lanczos', 'Nearest']
FORMATS = {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}
for _d in (LORA_DIR, UPSCALE_DIR):
    os.makedirs(_d, exist_ok=True)


def default_model():
    # 默认 Z-Image Turbo 官方原版；没装就取第一个装好的文生图模型（指令改图 qedit 要先放图，不当默认）
    order = ['zit-official'] + [k for k in MODELS if k != 'zit-official']
    return next((k for k in order if k in MODELS and not MODELS[k].get('edit') and not missing_files(k)),
                next((k for k in MODELS if not missing_files(k)), 'zit-official' if 'zit-official' in MODELS else next(iter(MODELS))))


def _model_files(d, exts):
    try:
        return sorted(f for f in os.listdir(d) if f.lower().endswith(exts) and os.path.isfile(os.path.join(d, f)))
    except OSError:
        return []


def loras(key=None):
    """这个模型能用的 LoRA（Z-Image 系在 models/Z-Image/loras，Krea 2 系在 models/Krea2/loras）。"""
    d = lora_dir(key) if key else LORA_DIR
    hide = {(MODELS.get(key) or {}).get('lightning')}  # 自动加的加速 LoRA 不出现在列表里
    return [{'name': os.path.splitext(f)[0], 'file': f} for f in _model_files(d, ('.safetensors', '.gguf', '.ckpt', '.pt')) if f not in hide]


def _lora_path(key, file):
    """发给引擎的 LoRA 名字：引擎按 --lora-model-dir 里扫描到的相对路径查（绝对路径会被拒）。引擎报过就用它报的。"""
    stem = os.path.splitext(file)[0]
    for x in ((_caps.get(key) or {}).get('loras') or []):
        p = x.get('path') if isinstance(x, dict) else x
        if isinstance(p, str) and (p == file or os.path.splitext(os.path.basename(p))[0] == stem):
            return p
    return file


def upscale_models():
    return [os.path.splitext(f)[0] for f in _model_files(UPSCALE_DIR, ('.pth', '.safetensors', '.gguf'))]


_caps = {}


_caps_fail = {}


def _allowed(key, base):
    """采样器 / 调度器能选哪些：内置的 + 引擎自己报上来的（网页下拉框里的就是这些）。"""
    out = set(base)
    for c in list(_caps.values()):
        if isinstance(c, dict):
            out.update(x for x in (c.get(key) or []) if isinstance(x, str))
    return out


def _lora_meta(key):  # Civitai 下载时记下的触发词、推荐强度：{LoRA 名字（不带扩展名）: {...}}
    try:
        import civitai
        return {os.path.splitext(f)[0]: v for f, v in civitai.meta_for(lora_dir(key)).items()}
    except Exception:
        return {}


def _detail_caps():
    try:
        import detect
        return {k: detect.available(k) for k in ('face', 'hand')}
    except Exception:
        return {}


def capabilities():
    """网页上能选的东西：采样器、调度器、加速缓存、LoRA、高清修复的放大方式、能不能单独放大。引擎开着时问它（以它为准）。"""
    out = {'samplers': SAMPLERS, 'schedulers': SCHEDULERS, 'cache_modes': CACHE_MODES, 'loras': [x['name'] for x in loras()],
           'loras_by_model': {k: [x['name'] for x in loras(k)] for k in MODELS},
           'lora_dirs': {k: os.path.relpath(lora_dir(k), ROOT) for k in MODELS},
           'rngs': RNGS, 'noise_samplers': NOISE_SAMPLERS,
           'upscalers': HIRES_BUILTIN + upscale_models(), 'upscale': bool(upscale_models()), 'formats': list(FORMATS),
           'features': ['init_image', 'mask_image', 'lora', 'hires', 'vae_tiling', 'cache'], 'live': False,
           'detail': _detail_caps(),
           'lora_meta': {k: _lora_meta(k) for k in MODELS},
           # 每个模型的引擎功能开关（载入过一次才知道）：网页按它显示 / 隐藏 SLG、蒸馏引导等
           'features_by_model': {k: c['generation_features'] for k, c in list(_caps.items()) if isinstance(c, dict) and isinstance(c.get('generation_features'), dict)}}
    if Engine.running() and Engine.model:
        c = _caps.get(Engine.model)
        if c is None and time.time() - _caps_fail.get(Engine.model, 0) > 60:  # 问不到：一分钟内不再问（不然每次打开生图页都要等 5 秒）
            try:
                c = _http('/sdcpp/v1/capabilities', timeout=5)
                _caps[Engine.model] = c
            except Exception:
                c = None; _caps_fail[Engine.model] = time.time()
        if c:
            out['samplers'] = c.get('samplers') or out['samplers']
            out['schedulers'] = c.get('schedulers') or out['schedulers']
            out['upscale'] = bool(c.get('upscale'))
            feats = c.get('generation_features') or (c.get('features_by_mode') or {}).get('img_gen') or c.get('features') or {}
            if isinstance(feats, dict):
                out['features'] = [k for k, v in feats.items() if v]
                out['features_by_model'][Engine.model] = feats
            out['live'] = True
    return out


def act(msg, tag='', level='info'):  # 由 server.py 换成网页运行日志
    pass


def space():  # 由 server.py 换成“当前请求在哪个空间”
    return 'n'


def gpu_free():  # 由 server.py 换成“让配音引擎把模型从显存里放掉”
    pass


def set_space(sp):  # 由 server.py 换成“这个线程之后都算在哪个空间”（日志才不会把私密空间的生图记到普通空间）
    pass


DIRS = {'n': os.path.join(ROOT, 'outputs', 'images'), 'v': os.path.join(ROOT, '.data', 'images')}


q21.LOG_DIR = lambda sp: images_dir(sp)  # 提示词增强的后台记录：存在这个空间的图片文件夹里
XFOLDER = '提取的衣服'  # 素材库里放“先提取衣服”结果的文件夹（2026-11-17 用户；生图图库里的图也能放进来）
MATS_LINK = None  # server 设：MATS_LINK(源文件, 文件名) → (素材库相对路径, 原来就有)。只给普通空间用（素材库不分空间）


def save_extract(j, img, meta):
    """“先提取衣服”提取出来的衣服：存进这个任务所在空间的生图图库（kind = extract，角标“衣服”），普通空间再硬链接进素材库/提取的衣服"""
    sp = j['space']
    iid = uuid.uuid4().hex[:12]
    name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + iid[:6] + '.png'
    path = os.path.join(images_dir(sp), name)
    with open(path, 'wb') as f:
        f.write(img)
    rec = {'id': iid, 'file': name, 'prompt': '提取衣服', 'model': j['model'], 'model_name': j.get('model_name'), 'job': j['id'], 'created': time.time(),
           'size': len(img), 'kind': 'extract', 'xsrc': meta['sha1'], 'width': meta['w'], 'height': meta['h'], 'seconds': meta['sec']}
    gallery_add(sp, rec)
    if sp != 'v' and MATS_LINK:
        MATS_LINK(path, name)
    act('提取出来的衣服已存进图库' + ('' if sp == 'v' else f'和素材库「{XFOLDER}」'), 'img', 'ok')
    return rec


def find_extract(j, key, sha1):
    """图库里以前提取过的同一张参考图（同一个模型）：返回 PNG，没有返回 None"""
    for x in gallery(j['space']):
        if x.get('kind') == 'extract' and x.get('xsrc') == sha1 and x.get('model') == key:
            try:
                with open(os.path.join(images_dir(j['space']), x['file']), 'rb') as f:
                    return f.read()
            except OSError:
                pass
    return None


q21.SAVE_EXTRACT, q21.FIND_EXTRACT = save_extract, find_extract


def images_dir(sp=None):
    d = DIRS['v' if (sp or space()) == 'v' else 'n']
    os.makedirs(d, exist_ok=True)
    return d


def model_dir(key):
    m = MODELS.get(key) or {}
    return config.models(m['dir']) if m.get('dir') else MODEL_DIR


def model_files(key):
    """这个模型要用到的三个文件：扩散模型、文本编码器、VAE（Z-Image 系的共用同一套编码器和 VAE）。"""
    m = MODELS.get(key) or {}
    return m.get('file'), m.get('llm', LLM), m.get('vae', VAE)


def controlnet_ok(key):
    return (MODELS.get(key) or {}).get('base') == 'Z-Image Turbo' and os.path.isfile(CONTROLNET)


def model_gb(key):
    """扩散模型文件多大（GB，网页上显示）。"""
    if comfy(key):
        return q21.model_gb(key)
    try:
        return round(os.path.getsize(os.path.join(model_dir(key), MODELS[key]['file'])) / 1e9, 1)
    except (OSError, KeyError):
        return None


def missing_files(key):
    if comfy(key):
        return q21.missing(key)
    m = MODELS.get(key)
    need = ([f for f in model_files(key) if f] + [f for f in (m.get('vision'),) if f] + ([os.path.join('loras', m['lightning'])] if m.get('lightning') else [])) if m else [LLM, VAE]
    out = [f for f in need if not os.path.isfile(os.path.join(model_dir(key), f))]
    if not os.path.isfile(SD_EXE):
        out.insert(0, 'tools/sd.cpp/sd-server.exe')
    return out


# ---------------------------------------------------------------- 图库（index.json）
_glock = threading.Lock()


def _index_path(sp):
    return os.path.join(images_dir(sp), 'index.json')


def _read_index(sp):
    p = _index_path(sp)
    for k in range(5):
        try:
            with open(p, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:  # 还没有记录：新的文件夹（第一张图写好、还没记进来时也是这样，不能按图重建）
            return []
        except ValueError:  # 文件坏了（比如写到一半断电）：坏的留一份，按文件夹里的图重建，不会把以前的图都丢掉
            try:
                os.replace(p, p + '.bad')
            except OSError:
                pass
            return _rebuild_index(sp, '图库记录损坏')
        except OSError:
            if k == 4:
                raise
            time.sleep(0.2)


def _rebuild_index(sp, why):
    d, out = images_dir(sp), []
    for name in sorted(os.listdir(d), reverse=True):
        fp = os.path.join(d, name)
        if not name.lower().endswith(('.png', '.jpg', '.webp')) or not os.path.isfile(fp):
            continue
        with open(fp, 'rb') as f:
            w, h = _img_size(f.read(65536), 1024, 1024)
        out.append({'id': uuid.uuid4().hex[:12], 'file': name, 'prompt': '', 'model': '', 'model_name': '', 'width': w, 'height': h,
                    'seed': None, 'steps': None, 'job': '', 'created': os.path.getmtime(fp), 'seconds': None, 'size': os.path.getsize(fp)})
    act(f'{why}，已按文件夹里的 {len(out)} 张图重建（提示词等信息丢失）', 'img', 'warn')
    _write_index(sp, out)
    return out


def _write_index(sp, items):
    p = _index_path(sp)
    tmp = p + '.' + uuid.uuid4().hex[:6] + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)
        f.flush(); os.fsync(f.fileno())
    for k in range(10):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:  # 别的程序（杀毒、同步）正好打开着：稍等再换
            if k == 9:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.1)


def gallery(sp=None):
    sp = sp or space()
    d = images_dir(sp)
    with _glock:
        items, seen, alive = _read_index(sp), set(), []
        try:  # 列一次文件夹，不用每张图问一次硬盘（2026-11-11 体检：几千张图时差几百毫秒）；Windows 的文件名不分大小写
            here = {e.name.lower() for e in os.scandir(d) if e.is_file()}
        except OSError:
            here = None

        def ok(f):
            f = str(f or '')
            if here is None or os.sep in f or '/' in f:
                return os.path.isfile(os.path.join(d, f))
            return f.lower() in here
        for x in items:  # 在文件夹里手动删掉的图：列表里也去掉；同一个文件记了两条的只留一条
            if x.get('file') not in seen and ok(x['file']):
                seen.add(x['file']); alive.append(x)
        if len(alive) != len(items):
            _write_index(sp, alive)
    return alive


def gallery_add(sp, rec):
    with _glock:
        items = [x for x in _read_index(sp) if x.get('file') != rec['file']]  # 同一个文件不会记两条
        items.insert(0, rec)
        _write_index(sp, items)


def gallery_delete(ids, sp=None):
    sp = sp or space()
    d, ids = images_dir(sp), set(ids)
    with _glock:
        items = _read_index(sp)
        left = {x.get('src_file') for x in items if x['id'] not in ids}  # 对比用的原图同一个任务的几张图共用：没人用了才删
        stuck = set()  # 主图删不掉（被占用）的：记录留着，报错（第二轮审查 9：以前照样从图库里拿掉，文件却还在）
        for x in items:
            if x['id'] in ids:
                main = os.path.join(d, x['file'])
                try:
                    os.remove(main)
                except FileNotFoundError:
                    pass
                except OSError:
                    stuck.add(x['id']); continue
                for fp in ([os.path.join(d, '_orig', x['orig'])] if x.get('orig') else []) + \
                        ([os.path.join(d, '_orig', os.path.basename(x['src_file']))] if x.get('src_file') and x['src_file'] not in left else []):
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
        _write_index(sp, [x for x in items if x['id'] not in ids or x['id'] in stuck])
    if stuck:
        raise RuntimeError(f'有 {len(stuck)} 张图删不掉（文件可能正被别的程序打开），其余已删除')


_HASHES = {}  # (路径, 修改时间, 大小) → sha1


def find_by_hash(size, sha, sp=None):
    """上传的图是不是图库里生成过的那张（按大小 + sha1 对）：是就返回那一条（2026-11-11 用户：视频页放了生成的图，要一键带上当时的提示词）"""
    import hashlib
    d = images_dir(sp or space())
    for x in gallery(sp):
        p = os.path.join(d, x['file'])
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size != size:
            continue
        k = (p, st.st_mtime, st.st_size)
        if k not in _HASHES:
            with open(p, 'rb') as f:
                _HASHES[k] = hashlib.sha1(f.read()).hexdigest()
        if _HASHES[k] == sha:
            return x
    return None


def gallery_get(iid, sp=None):
    return next((x for x in gallery(sp) if x['id'] == iid), None)


def _orig_dir(sp):
    d = os.path.join(images_dir(sp), '_orig'); os.makedirs(d, exist_ok=True); return d


def image_path(name, sp=None):
    """/media/img/<文件名>：只认当前空间图库文件夹里的文件（orig- 开头的是细化前的原图，在 _orig 里）"""
    b = os.path.basename(name)
    p = os.path.join(_orig_dir(sp) if b.startswith(('orig-', 'src-')) else images_dir(sp), b)
    return p if os.path.isfile(p) and p.lower().endswith(tuple(FORMATS.values())) else None


# ---------------------------------------------------------------- 引擎进程
def _http(path, payload=None, timeout=30, method=None):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', data=data, method=method or ('POST' if data is not None else 'GET'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        try:
            j = json.loads(body)
            msg = (j.get('error') or {}).get('message') if isinstance(j.get('error'), dict) else j.get('error')
        except ValueError:
            msg = body[:200]
        raise RuntimeError(f'生图引擎返回错误（{e.code}）：{msg or body[:200]}')
    except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as e:
        if Engine.proc and Engine.proc.poll() is not None:
            raise RuntimeError('生图引擎意外退出（多半是显存不足），详情请见 studio/image-engine.log')
        raise RuntimeError(f'无法连接生图引擎：{getattr(e, "reason", e)}')


def _port_open(port=None):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(('127.0.0.1', port or PORT)) == 0
    finally:
        s.close()


def kill_orphan():
    """上次没关干净的生图引擎（比如工作室被强行结束）：还占着端口和十几 GB 显存，找到占这个端口的 sd-server 结束掉。"""
    if Engine.running() or not _port_open():
        return
    if kill_port(PORT, 'sd-server.exe'):
        act('已结束上次未关闭的生图引擎（显存已释放）', 'img')


def kill_port(port, exe):
    """结束占着这个端口、并且程序名是 exe 的进程（别的程序不会误杀）。端口空出来了返回 True。"""
    try:
        out = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW, timeout=10).stdout
    except Exception:
        return False
    # 在监听的那一行：对方地址是 0.0.0.0:0（状态那一列在非英文系统里会被翻译，不靠它）
    pids = {f[-1] for f in (ln.split() for ln in out.splitlines()) if len(f) >= 5 and f[0] == 'TCP' and f[1].endswith(f':{port}') and f[2].endswith(':0')}
    for pid in pids:
        subprocess.run(['taskkill', '/f', '/fi', f'PID eq {pid}', '/fi', f'IMAGENAME eq {exe}'], capture_output=True, creationflags=NO_WINDOW)
    for _ in range(20):
        if not _port_open(port):
            return bool(pids)
        time.sleep(0.25)
    return False


class Aborted(Exception):
    pass


class Engine:
    proc, model, last, lock, ups, opts = None, None, 0, threading.Lock(), False, None

    @classmethod
    def ready(cls):
        try:
            return _http('/sdcpp/v1/models/status', timeout=2).get('state') == 'ready'
        except Exception:
            return False

    @classmethod
    def running(cls):
        return bool(cls.proc and cls.proc.poll() is None)

    @classmethod
    def ensure(cls, key, abort=None, opts=None):
        """opts：引擎启动参数 {'rng': 'cuda'|'cpu'|'std_default', 'sage': bool}，和正在跑的不一样就重启。"""
        opts = {'rng': (opts or {}).get('rng') if (opts or {}).get('rng') in RNGS else DEFAULTS['rng'], 'sage': bool((opts or {}).get('sage')), 'cn': bool((opts or {}).get('cn')) and controlnet_ok(key)}
        with cls.lock:
            cls.last = time.time()
            if cls.running() and cls.model == key and cls.ready() and cls.ups == bool(upscale_models()) and cls.opts == opts:
                return
            miss = missing_files(key)
            if miss:
                raise RuntimeError('缺少生图文件：' + '、'.join(miss))
            cls.stop()
            kill_orphan()
            if _port_open():
                raise RuntimeError(f'端口 {PORT} 已被其他程序占用，生图引擎无法启动')
            act(f"启动生图引擎，载入 {MODELS[key]['name']}（首次约 10~30 秒）…", 'img')
            lp = os.path.join(STUDIO, 'image-engine.log')
            try:  # 上一次的日志留一份（引擎崩溃后再试一次，不会把崩溃原因冲掉）
                if os.path.isfile(lp) and os.path.getsize(lp):
                    os.replace(lp, lp + '.prev')
            except OSError:
                pass
            log = open(lp, 'w', encoding='utf-8', errors='replace')
            j = lambda f: os.path.join(model_dir(key), f)
            mf, ml, mv = model_files(key)
            args = [SD_EXE, '--diffusion-model', j(mf), '--llm', j(ml), '--vae', j(mv),
                    '--listen-ip', '127.0.0.1', '--listen-port', str(PORT), '--cfg-scale', str(DEFAULTS['cfg']),  # 注意力加速默认自动开
                    '--lora-model-dir', lora_dir(key), '--hires-upscalers-dir', UPSCALE_DIR] + list(MODELS[key].get('args') or [])
            if MODELS[key].get('vision'):  # 指令改图：看图用的视觉编码器
                args += ['--llm_vision', j(MODELS[key]['vision'])]
            if opts['cn']:  # 按参考图摆姿势 / 照线稿画：载入 ControlNet（多占约 6GB 显存，所以只在用到时才载入）
                args += ['--control-net', CONTROLNET]
            if opts['rng'] != 'cuda':  # cpu = 和 ComfyUI 同一个种子出同一张图
                args += ['--rng', opts['rng'], '--sampler-rng', opts['rng']]
            if opts['sage']:
                args += ['--sage-attn']
            cls.opts = opts
            ups = _model_files(UPSCALE_DIR, ('.pth', '.safetensors', '.gguf'))
            if ups:
                args += ['--upscale-model', os.path.join(UPSCALE_DIR, ups[0])]  # “放大”用的 ESRGAN
            cls.ups = bool(ups)
            _caps.pop(key, None)
            cls.proc = subprocess.Popen(args, cwd=SD_DIR, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            log.close()  # 引擎那边有自己的一份
            cls.model = key
            threading.Thread(target=cls.reaper, args=(cls.proc,), daemon=True).start()
            for _ in range(600):  # 最多等 5 分钟（第一次从硬盘读 12GB 的模型会慢一些）
                if cls.proc.poll() is not None:
                    cls.proc = None
                    raise RuntimeError('生图引擎启动失败，请查看 studio/image-engine.log')
                if cls.ready():
                    act('生图引擎就绪' + ('（随机数：' + opts['rng'] + '）' if opts['rng'] != 'cuda' else '') + ('（SageAttention）' if opts['sage'] else '') + ('（ControlNet）' if opts['cn'] else ''), 'img', 'ok')
                    try:  # 记下引擎报的功能和 LoRA 名字（LoRA 要按它报的名字发）
                        _caps[key] = _http('/sdcpp/v1/capabilities', timeout=5)
                    except Exception:
                        pass
                    return
                if abort and abort():
                    raise Aborted()
                time.sleep(0.5)
            cls.stop()
            raise RuntimeError('生图引擎启动超时')

    @classmethod
    def reaper(cls, p):  # 闲置一段时间就退出，显存还给配音 / 换声
        while p.poll() is None and cls.proc is p:
            time.sleep(10)
            if time.time() - cls.last > IDLE_EXIT and GPU.acquire(blocking=False):  # 拿到锁再关：不会把刚准备好、马上要画的引擎关掉
                try:
                    if time.time() - cls.last > IDLE_EXIT and cls.proc is p:
                        act('生图引擎闲置 5 分钟，已退出（显存已释放）', 'img')
                        cls.stop()
                finally:
                    GPU.release()

    @classmethod
    def stop(cls):
        p, cls.proc, cls.model = cls.proc, None, None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=8)
            except Exception:
                try:
                    p.kill(); p.wait(timeout=5)  # 等它真的退出：下一次启动才能用这个端口
                except Exception:
                    pass


atexit.register(Engine.stop)

# 显卡同一时间只给一边用：生图任务拿着 GPU 这把锁；配音那边用显卡的整段时间记在 _busy 里，
# 这期间不开始新的生图；正在画的任务画完手上这张就让出来（WANT），剩下的几张等那边用完再接着画
GPU = threading.Lock()
WANT = threading.Event()
_busy = 0
_bcv = threading.Condition()


OTHER_GPU = None  # 由 server.py 设：视频引擎空闲、模型还留在显存里时把显存放掉（videogen.Engine.free_idle）


def yield_gpu():
    """配音 / 换声 / 识别马上要用显卡：生图引擎还开着的话，等手上这张画完就关掉（不在画的中途关）。"""
    if OTHER_GPU:
        try:
            OTHER_GPU()
        except Exception:
            pass
    if not (Engine.running() or GPU.locked()):
        return
    WANT.set()
    try:
        with GPU:
            if Engine.running():
                act('配音需要使用显卡：生图引擎先退出（其余图片待配音完成后自动继续生成）', 'img')
                Engine.stop()
    finally:
        WANT.clear()


@contextlib.contextmanager
def audio_gpu():
    """配音 / 换声 / 识别 / 本地翻译用显卡的这一整段：先让生图让开，用完之前不开始新的生图（可以嵌套）。"""
    global _busy
    with _bcv:
        _busy += 1
    try:
        yield_gpu()
        yield
    finally:
        with _bcv:
            _busy -= 1
            _bcv.notify_all()


def _take_gpu(j):
    """生图任务拿显卡：等配音那边用完（期间可以取消）。拿到返回 True。"""
    while True:
        with _bcv:
            while _busy and not j['cancel']:
                j['message'] = '等待配音 / 提示词模型释放显卡…'
                _bcv.wait(1)
        if j['cancel']:
            return False
        GPU.acquire()
        if j['cancel']:  # 排队等锁期间被取消了
            GPU.release()
            return False
        if not _busy and not WANT.is_set():
            return True
        GPU.release()  # 拿锁的这一下配音那边又开始用了：再等
        time.sleep(0.2)


def vram_item():
    if not Engine.running() or not Engine.model:
        return None
    md = model_dir(Engine.model)
    mb = sum(os.path.getsize(os.path.join(md, f)) for f in model_files(Engine.model) if f and os.path.isfile(os.path.join(md, f))) / 2 ** 20
    return {'id': 'imagegen', 'name': '生图 · ' + MODELS.get(Engine.model, {}).get('name', Engine.model), 'mb': round(mb * 1.1)}


# ---------------------------------------------------------------- 任务
jobs = {}        # id -> dict
queue = []       # 等待中的任务 id
_qcv = threading.Condition()


def _clamp_size(v, dflt):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = dflt
    return max(512, min(2048, v // 16 * 16))


def _num(v, lo, hi, dflt, kind=float):
    try:
        x = kind(v)
    except (TypeError, ValueError):
        return dflt
    return max(lo, min(hi, x))


def _image_b64(v, sp, what):
    """图生图 / 局部重画的图：{'gallery': 图库 id}（只认当前空间的）或者 data URL / base64。返回 base64。"""
    if isinstance(v, dict) and v.get('gallery'):
        x = gallery_get(str(v['gallery']), sp)
        if not x:
            raise ValueError(f'{what}在图库中已找不到')
        with open(os.path.join(images_dir(sp), x['file']), 'rb') as f:
            return base64.b64encode(f.read()).decode('ascii')
    data = v.get('data') if isinstance(v, dict) else v
    if not isinstance(data, str) or not data:
        raise ValueError(f'缺少{what}')
    data = data.split(',', 1)[1] if data.startswith('data:') else data
    if len(data) > 40_000_000:
        raise ValueError(f'{what}过大（上限约 30MB）')
    try:
        head = base64.b64decode(data[:64] + '=' * (-len(data[:64]) % 4))
    except ValueError:
        raise ValueError(f'{what}不是图片')
    if not (head.startswith(b'\x89PNG') or head.startswith(b'\xff\xd8') or head[8:12] == b'WEBP'):
        raise ValueError(f'{what}只支持 PNG / JPG / WebP')
    try:
        w, h = _img_size(base64.b64decode(data[:200000] + '=' * (-len(data[:200000]) % 4), validate=False), 0, 0)
    except ValueError:
        w = h = 0
    if w * h > 64_000_000:
        raise ValueError(f'{what}过大（{w} × {h}）')
    return data


def build_job(b, sp):
    """网页传来的生图设置 → 检查过的任务 dict（还没进队列）"""
    kind = 'upscale' if b.get('kind') == 'upscale' else 'gen'
    key = b.get('model') if b.get('model') in MODELS else default_model()
    miss = missing_files(key)
    if miss:
        raise ValueError('缺少生图文件：' + '、'.join(miss))
    j = stages.JobDict({'id': datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4], 'space': sp, 'state': 'queued', 'kind': kind,
         'model': key, 'model_name': MODELS[key]['name'], 'done': 0, 'step': 0, 'total': 0, 'images': [], 'error': '', 'message': '排队中',
         'created': time.time(), 'finished': None, 'cancel': False, 'preview': None, 'sd_id': None, 'cancel_sent': None})
    if kind == 'upscale':  # 把图库里的一张图放大（ESRGAN，不重新画）
        if not upscale_models():
            raise ValueError('尚无放大模型（请在 models/upscalers 中放入一个 ESRGAN 模型）')
        src = gallery_get(str(b.get('id') or ''), sp)
        if not src:
            raise ValueError('图库中找不到该图片')
        rep = int(_num(b.get('repeats'), 1, 2, 1, int))
        edge = max(int(src.get('width') or 1024), int(src.get('height') or 1024))
        while rep > 1 and edge * 4 ** rep > 8192:
            rep -= 1
        if edge * 4 > 8192:
            raise ValueError(f'该图片尺寸已很大（最长边 {edge}），再放大 4 倍将超过 8192')
        j.update(prompt=src.get('prompt', ''), src=src['id'], repeats=rep, count=1,
                 width=src.get('width'), height=src.get('height'), steps=0, seed=src.get('seed'))
        j['_init'] = _image_b64({'gallery': src['id']}, sp, '原图')
    else:
        prompt = str(b.get('prompt') or '').strip()
        if not prompt and comfy(key) and isinstance(b.get('pose'), dict) and b['pose'].get('data'):
            prompt = q21.pose_prompt()  # 3D 人偶摆姿势：不写也行（固定指令，模板套里可改）
        if not prompt:
            raise ValueError('请描述要生成的画面')
        try:
            seed = int(b.get('seed'))
        except (TypeError, ValueError):
            seed = -1
        if seed < 0:
            seed = random.randint(0, 2 ** 31 - 1)
        mode = b.get('mode') if b.get('mode') in ('txt', 'img', 'inpaint', 'edit') else 'txt'
        if comfy(key):  # Qwen 2.1：没放图 = 文生图；放了图 = 指令改图，或在图上涂抹后局部重画
            mode = 'txt' if not b.get('init') else ('inpaint' if mode == 'inpaint' else 'edit')
            if mode not in (MODELS[key].get('modes') or ['txt']):
                raise ValueError(MODELS[key]['name'] + ' 只能文生图，改图请换成 Qwen 2.1 高质量或快速')
        elif MODELS[key].get('edit'):
            mode = 'edit'  # 指令改图模型只有这一种用法
        elif mode == 'edit':
            raise ValueError('该模型不支持按指令改图，请改用“Qwen 指令改图”')
        if mode == 'edit' and not b.get('init'):
            raise ValueError('指令改图需要先添加一张图片')
        d = model_defaults(key)
        hb = b.get('hires') if isinstance(b.get('hires'), dict) else {}
        up_ok = HIRES_BUILTIN + upscale_models()
        lora_names = {x['name']: x['file'] for x in loras(key)}  # 只认这个模型自己 LoRA 文件夹里的
        lo = []
        for x in (b.get('loras') or [])[:8]:
            if isinstance(x, dict) and x.get('name') in lora_names:
                lo.append({'name': x['name'], 'file': lora_names[x['name']], 'weight': _num(x.get('weight'), -3.0, 3.0, 1.0)})
        cache_opt = str(b.get('cache_option') or '').strip()[:200]
        if cache_opt and not re.fullmatch(r'[\w.\-=,\s]+', cache_opt):
            raise ValueError('加速缓存的参数须为 key=value 格式，以逗号分隔')
        fmt = b.get('format') if b.get('format') in FORMATS else d['format']
        extra = str(b.get('extra_args') or '').strip()[:300]
        if extra and not re.fullmatch(r'\s*[A-Za-z_][\w]*\s*=\s*[\w.\-]+\s*(,\s*[A-Za-z_][\w]*\s*=\s*[\w.\-]+\s*)*', extra):
            raise ValueError('其他采样参数须为 key=value 格式，以逗号分隔')
        ab, sg, vt = (b.get(k) if isinstance(b.get(k), dict) else {} for k in ('apg', 'slg', 'vae_tile'))
        try:
            layers = sorted({int(x) for x in (sg.get('layers') if isinstance(sg.get('layers'), list) else DEFAULTS['slg']['layers'])[:16] if 0 <= int(x) <= 99})
        except (TypeError, ValueError):
            raise ValueError('跳层引导的层号须为 0~99 的整数')
        opt_f = lambda v, lo_, hi_: None if v in (None, '') else round(_num(v, lo_, hi_, lo_), 3)
        tw, th = (int(_num(hb.get(k), 0, 4096, 0, int)) for k in ('target_width', 'target_height'))
        tw, th = (0, 0) if not (tw and th) else (max(512, tw // 16 * 16), max(512, th // 16 * 16))
        ctl = b.get('control') if isinstance(b.get('control'), dict) and b['control'].get('image') else None
        if ctl and not controlnet_ok(key):
            raise ValueError('参考图控制（ControlNet）目前仅支持 Z-Image Turbo 系列模型' if os.path.isfile(CONTROLNET) else '尚无 ControlNet 模型')
        j['engine_opts'] = {'rng': b.get('rng') if b.get('rng') in RNGS else d['rng'], 'sage': bool(b.get('sage')), 'cn': bool(ctl)}
        j.update(mode=mode, prompt=prompt[:4000], negative=str(b.get('negative') or '').strip()[:2000],
                 width=_clamp_size(b.get('width'), 1024), height=_clamp_size(b.get('height'), 1024),
                 steps=int(_num(b.get('steps'), 1, 60, d['steps'], int)), cfg=round(_num(b.get('cfg'), 0.0, 20.0, d['cfg']), 2), seed=seed,
                 count=int(_num(b.get('count'), 1, 4, 1, int)),
                 sampler=b.get('sampler') if b.get('sampler') in _allowed('samplers', SAMPLERS) else '', scheduler=b.get('scheduler') if b.get('scheduler') in _allowed('schedulers', SCHEDULERS) else '',
                 flow_shift=None if b.get('flow_shift') in (None, '') else round(_num(b.get('flow_shift'), 0.0, 20.0, 3.0), 3),
                 eta=None if b.get('eta') in (None, '') else round(_num(b.get('eta'), 0.0, 2.0, 1.0), 3),
                 strength=round(_num(b.get('strength'), 0.05, 1.0, d['strength']), 3) if mode != 'txt' else None,
                 hires={'enabled': bool(hb.get('enabled')), 'upscaler': hb.get('upscaler') if hb.get('upscaler') in up_ok else 'Latent',
                        'scale': round(_num(hb.get('scale'), 1.0, 3.0, 1.5), 2), 'steps': int(_num(hb.get('steps'), 0, 60, 0, int)),
                        'denoise': round(_num(hb.get('denoise'), 0.01, 1.0, 0.5), 3), 'target_width': tw, 'target_height': th},
                 noise_sampler=b.get('noise_sampler') if b.get('noise_sampler') in NOISE_SAMPLERS else '',
                 beta_alpha=opt_f(b.get('beta_alpha'), 0.1, 2.0), beta_beta=opt_f(b.get('beta_beta'), 0.1, 2.0), extra_args=extra,
                 apg={'enabled': bool(ab.get('enabled')), 'eta': round(_num(ab.get('eta'), 0.0, 1.0, 1.0), 3),
                      'momentum': round(_num(ab.get('momentum'), -1.0, 1.0, 0.0), 3), 'norm_threshold': round(_num(ab.get('norm_threshold'), 0.0, 50.0, 5.0), 2)},
                 slg={'scale': round(_num(sg.get('scale'), 0.0, 5.0, 0.0), 2), 'layers': layers or [7, 8, 9],
                      'start': round(_num(sg.get('start'), 0.0, 1.0, 0.01), 3), 'end': round(_num(sg.get('end'), 0.0, 1.0, 0.2), 3)},
                 guidance=opt_f(b.get('guidance'), 0.0, 10.0),
                 vae_tile={'size': int(_num(vt.get('size'), 128, 1024, 256, int)) // 64 * 64, 'overlap': round(_num(vt.get('overlap'), 0.0, 0.9, 0.5), 2)},
                 rng=j['engine_opts']['rng'], sage=j['engine_opts']['sage'],
                 vae_tiling=bool(b.get('vae_tiling')), cache_mode=b.get('cache_mode') if b.get('cache_mode') in CACHE_MODES else '', cache_option=cache_opt,
                 loras=lo, format=fmt, quality=int(_num(b.get('quality'), 1, 100, d['quality'], int)), meta=bool(b.get('meta', d['meta'])),
                 src=str(b['init']['gallery']) if mode != 'txt' and isinstance(b.get('init'), dict) and b['init'].get('gallery') else None)
        dt = b.get('detail') if isinstance(b.get('detail'), dict) else {}
        if any(dt.get(k) for k in ('face', 'hand')):  # 自动细化（修脸 / 修手）：默认关
            j['detail'] = {'face': bool(dt.get('face')), 'hand': bool(dt.get('hand')),
                           'strength': round(_num(dt.get('strength'), 0.1, 0.8, 0.35), 2), 'strength2': round(_num(dt.get('strength2'), 0.1, 0.8, 0.45), 2),
                           'prompt': str(dt.get('prompt') or '').strip()[:1000], 'keep': dt.get('keep') is not False}
        if mode != 'txt':
            j['_init'] = _image_b64(b.get('init'), sp, '原图')
        if (mode == 'edit' or (mode == 'inpaint' and comfy(key))) and isinstance(b.get('refs'), list) and b['refs']:  # 多图改图：原图是图 1，再加最多 2 张参考图（图 2、图 3），比如“让图 1 的人穿上图 2 的衣服”
            j['_refs'] = [_image_b64(r, sp, f'参考图 {k + 2}') for k, r in enumerate(b['refs'][:2])]
            j['refs'] = len(j['_refs'])
        if mode == 'edit':
            j['size_free'] = bool(b.get('size_free'))  # 指令改图自选了出图尺寸（不跟图 1）
            if comfy(key) and isinstance(b.get('pose'), dict) and b['pose'].get('data'):  # 3D 人偶摆姿势（Fisher）：人偶图
                if not q21.pose_ok():
                    raise ValueError('缺少 3D 人偶摆姿势的 LoRA（ComfyUI/models/loras/' + q21.POSE_LORA + '）')
                j['_pose'] = _image_b64(b['pose'], sp, '人偶姿势图')
                j['pose'] = True
                j['pose_w'] = round(_num(b.get('pose_w'), 0.3, 1.5, 1.0), 2)  # 姿势 LoRA 强度（默认 1，作者的设置）
        if mode == 'edit':  # 改图后处理（editfix.py，默认都关）：face_ref = 按第几张参考图（0 = 图 2，1 = 图 3）精修脸；keep_face = 贴回原图的脸并校正肤色
            fr = b.get('face_ref')
            if isinstance(fr, int) and not isinstance(fr, bool) and 0 <= fr < len(j.get('_refs') or []) and not comfy(key):  # Qwen 2.1 不做“按参考脸修脸”（实测 2.1 的脸本来就更像，修完反而变差）
                j['face_ref'] = fr
            elif b.get('keep_face'):
                j['keep_face'] = True
        if mode == 'inpaint':
            j['_mask'] = _image_b64(b.get('mask'), sp, '要重画的范围')
            j['crop'] = bool(b.get('crop'))  # 只把涂抹的那一块放大后重画（细节更多），框外不动
        if ctl:  # 参考图控制：pose = 从参考图里认出人的骨架，照这个姿势画；canny = 照参考图的线条轮廓画
            kind = ctl.get('type') if ctl.get('type') in ('pose', 'canny') else 'pose'
            raw = _image_b64(ctl['image'], sp, '参考图')
            j['_ctl'] = _control_image(raw, kind, j['width'], j['height'])
            j['control'] = {'type': kind, 'strength': round(_num(ctl.get('strength'), 0.1, 1.5, 0.7), 2)}
    if kind == 'gen' and comfy(key):  # Qwen 2.1：步数、采样器按 q21.SETTINGS（作者的设置），提示词增强三档（默认关）
        q_over = q21.clean_over(b.get('q_over'), j['mode'])  # 2026-11-23：网页上改过的步数 / CFG / 采样器 / 调度器 / 像素（没改的用推荐设置）
        stq = {**q21.SETTINGS[key][j['mode']], **q_over}
        j.update(q_over=q_over, steps=stq['steps'], sampler=stq['sampler'], scheduler=stq['scheduler'], cfg=stq.get('cfg', 1.0), loras=j.get('loras', [])[:4], hires={'enabled': False}, detail=None,
                 enhance=b.get('enhance') if b.get('enhance') in q21.ENHANCE else 'off', control=None, emph=b.get('emph') is True,  # emph：强调主要改动（2026-11-10，默认关）
                 pe_model=b.get('pe_model') if b.get('pe_model') in q21.PE_SETS else 'official',  # 增强小模型 / 文本编码器用哪个版本（2026-11-15，默认官方）
                 te_model=b.get('te_model') if b.get('te_model') in q21.TE_SETS else 'official',
                 # 局部重画的边缘处理（q21.wf_local）：2026-11-16 用户同意改成默认（A/B：docs/AB测试/局部重画边缘_1116）。请求里带 inp_edge 时按请求（测试用，[] = 旧做法）
                 inp_edge=[x for x in b['inp_edge'] if x in ('hard', 'dd', 'grow', 'dbg', 'b8')] if isinstance(b.get('inp_edge'), list) else list(q21.EDGE_DEFAULT),
                 ref_extract=b.get('ref_extract') is True and bool(j.get('_refs')),  # 参考图先提取衣服（2026-11-16，默认关，见 q21.extract_refs）  # 局部重画的边缘处理（2026-11-16 在测，默认不开，见 q21.wf_local）
                 refine=b.get('refine') is True and j['mode'] == 'txt' and bool(MODELS[key].get('refine')))  # 二采：Krea 2 润色（2026-11-23 用户要的，默认关，见 q21.wf_refine）
        if j['refine'] and q21.refine_missing():
            raise ValueError('二采缺少文件：' + '、'.join(q21.refine_missing()))
        j.pop('_ctl', None); j.pop('detail', None)
    j['prompt_trace'] = prompttrace.new(b.get('prompt_input', b.get('prompt', '')))
    return j


def submit(b, sp):
    j = build_job(b, sp)
    with _qcv:
        jobs[j['id']] = j
        queue.append(j['id'])
        _qcv.notify()
        for old in sorted((x for x in list(jobs.values()) if x['state'] in ('done', 'error', 'cancelled')), key=lambda x: x['created'])[:-30]:
            jobs.pop(old['id'], None)  # 只留最近 30 个结束的任务（图本身在图库里）
    return public(j)


def edit_once(init_png, prompt, width, height, seed, sp, refs=None, abort=None, note=None):
    """改衣（整体重绘 / 保真替换）用：在调用方已经拿着显卡（生视频任务拿着 GPU 锁）的情况下，用 Qwen 指令改图改一张图，返回图片字节。
    不进生图队列；note 给了就存进图库（生图页“本次生成”、作品里都看得到，备注写着是哪个改衣任务用的）。
    用完不关引擎（调用方接着要用显卡时自己 Engine.stop()）。refs：再加的参考图（图 2、图 3）的 data URL。"""
    data = 'data:image/png;base64,' + base64.b64encode(init_png).decode()
    b = {'model': 'qedit', 'mode': 'edit', 'prompt': prompt, 'init': {'data': data}, 'width': width, 'height': height, 'seed': seed, 'count': 1}
    if refs:
        b['refs'] = [{'data': r} for r in refs]
    j = build_job(b, sp)
    Engine.ensure('qedit', abort=abort, opts=j.get('engine_opts'))
    Engine.last = time.time()
    t0 = time.time()
    img = _gen_wait(j, _request(j, j['seed']), limit=600)
    Engine.last = time.time()
    if img is None:
        raise InterruptedError
    if note:
        try:
            iid = uuid.uuid4().hex[:12]
            name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + iid[:6] + '.png'
            with open(os.path.join(images_dir(sp), name), 'wb') as f:
                f.write(img)
            w, h = _img_size(img, width, height)
            gallery_add(sp, {'id': iid, 'file': name, 'prompt': prompt, 'prompt_trace': prompttrace.snapshot(j), 'model': 'qedit', 'model_name': MODELS['qedit']['name'], 'job': '', 'created': time.time(),
                             'size': len(img), 'seed': j['seed'], 'width': w, 'height': h, 'seconds': round(time.time() - t0, 1), 'mode': 'edit', 'note': note,
                             **{k: j.get(k) for k in ('steps', 'cfg', 'sampler', 'scheduler')}})
        except Exception as e:  # 存不进图库不影响改衣本身
            act(f'改衣所用的改图未能存入图库：{e}', 'img', 'warn')
    return img


def _control_image(b64, kind, w, h):
    """ControlNet 的控制图：先按生成尺寸“铺满再居中裁切”，姿势模式再换成骨架图"""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    im = im.crop((l, t, l + w, t + h))
    if kind == 'pose':
        import detect
        if not detect.available('pose'):
            raise ValueError('缺少姿势识别模型（models/detect）')
        if not detect.persons(im):
            raise ValueError('参考图中未识别到人物，请换一张人物更完整的图片')
        im = detect.pose_map(im)
    out = io.BytesIO(); im.save(out, 'PNG')
    return base64.b64encode(out.getvalue()).decode()


def public(j, full=False):
    d = {k: v for k, v in j.items() if k not in ('cancel', 'preview') and not k.startswith('_')}  # 原图 / 遮罩不发给网页
    tr = getattr(j, 'track', None)
    d['timing'] = tr.export() if tr else None  # 计时：开始了多久、每一步用了几秒
    with _qcv:
        d['queue_pos'] = queue.index(j['id']) + 1 if j['id'] in queue else 0
    if full:
        d['preview'] = j.get('preview')
    return d


def list_jobs(sp):
    with _qcv:
        mine = [j for j in jobs.values() if j['space'] == sp]
    return [public(j) for j in sorted(mine, key=lambda x: -x['created'])]


def release(j):
    """任务结束（做完 / 失败 / 取消，包括排队时就取消的）：放掉大的输入（原图、遮罩、参考图……）。
    2026-11-17 审查 P06：以前排队时取消的任务不走这一步，原图一直留在内存里，直到被挤出最近 30 条"""
    for k in ('_init', '_mask', '_ctl', '_refs'):
        j.pop(k, None)


def cancel(jid, sp):
    j = jobs.get(jid)
    if not j or j['space'] != sp:
        return None
    j['cancel'] = True
    with _qcv:
        if jid in queue:
            queue.remove(jid)
            j['state'], j['finished'] = 'cancelled', time.time()
            j['message'] = '已取消' + (f"（已生成 {j['done']} 张）" if j['done'] else '')
            release(j)
    _send_cancel(j)  # 还没开始画（在载入模型）的话，画的循环里会再发一次
    return public(j)


def _send_cancel(j):
    sid = j.get('sd_id')
    if j['state'] == 'running' and sid and j.get('cancel_sent') != sid:
        j['cancel_sent'] = sid
        try:
            _http(f'/sdcpp/v1/jobs/{sid}/cancel', {}, timeout=5)
        except Exception as e:
            act('取消指令未能送达生图引擎：' + str(e), 'img', 'warn')


def _request(j, seed):
    """一张图的生成请求（sd-server 原生接口）：没设置的参数不发，用引擎 / 模型自己的默认值。"""
    sp = {'sample_steps': j['steps'], 'guidance': {'txt_cfg': j['cfg']}}
    if j.get('sampler'):
        sp['sample_method'] = j['sampler']
    if j.get('scheduler'):
        sp['scheduler'] = j['scheduler']
    if j.get('flow_shift') is not None:
        sp['flow_shift'] = j['flow_shift']
    if j.get('eta') is not None:
        sp['eta'] = j['eta']
    ex = []  # extra_sample_args：key=value，逗号分开
    if j.get('noise_sampler'):
        ex.append('noise_sampler=' + j['noise_sampler'])
    if j.get('scheduler') == 'beta':
        ex += [f'{k}={j[f"beta_{k}"]}' for k in ('alpha', 'beta') if j.get(f'beta_{k}') is not None]
    apg = j.get('apg') or {}
    if apg.get('enabled') and j['cfg'] > 1:  # APG 只在用 CFG 时有意义
        ex += [f"apg_eta={apg['eta']}", f"apg_momentum={apg['momentum']}", f"apg_norm_threshold={apg['norm_threshold']}"]
    if j.get('extra_args'):
        ex += [x.strip().replace(' ', '') for x in j['extra_args'].split(',') if x.strip()]
    if ex:
        sp['extra_sample_args'] = ','.join(ex)
    slg = j.get('slg') or {}
    if slg.get('scale'):
        sp['guidance']['slg'] = {'scale': slg['scale'], 'layers': slg['layers'], 'layer_start': slg['start'], 'layer_end': slg['end']}
    if j.get('guidance') is not None:
        sp['guidance']['distilled_guidance'] = j['guidance']
    req = {'prompt': j['prompt'], 'negative_prompt': j.get('negative') or '', 'width': j['width'], 'height': j['height'], 'seed': seed, 'batch_count': 1,
           'sample_params': sp, 'embed_image_metadata': bool(j.get('meta')), 'output_format': j['format'], 'output_compression': j['quality']}
    if j.get('mode') in ('img', 'inpaint'):
        req['init_image'], req['strength'] = j['_init'], j['strength']
    if j.get('mode') == 'edit':  # 指令改图：原图作为参考图，按尺寸重画；多张时按顺序就是提示词里的 Picture 1、Picture 2……
        req['ref_images'] = [j['_init']] + list(j.get('_refs') or [])
        if j.get('_refs'):
            req['increase_ref_index'] = True
    if j.get('_ctl'):
        req['control_image'], req['control_strength'] = j['_ctl'], j['control']['strength']
    if j.get('mode') == 'inpaint':
        req['mask_image'] = j['_mask']
    hr = j.get('hires') or {}
    if hr.get('enabled'):
        req['hires'] = {'enabled': True, 'upscaler': hr['upscaler'], 'scale': hr['scale'], 'steps': hr['steps'], 'denoising_strength': hr['denoise']}
        if hr.get('target_width') and hr.get('target_height'):  # 按尺寸放大（不按倍数）
            req['hires'].update(target_width=hr['target_width'], target_height=hr['target_height'])
    if j.get('vae_tiling'):
        vt = j.get('vae_tile') or DEFAULTS['vae_tile']
        req['vae_tiling_params'] = {'enabled': True, 'tile_size_w': vt['size'], 'tile_size_h': vt['size'], 'target_overlap': vt['overlap']}
    if j.get('cache_mode'):
        req['cache_mode'], req['cache_option'] = j['cache_mode'], j.get('cache_option') or ''
    if j.get('loras'):  # 引擎按 LoRA 文件夹里的相对名字查（绝对路径会被拒）
        req['lora'] = [{'path': _lora_path(j['model'], x['file']), 'multiplier': x['weight']} for x in j['loras']]
    lt = (MODELS.get(j['model']) or {}).get('lightning')
    if lt and j.get('lightning', True):  # 指令改图的 4 步加速 LoRA：自动加
        req['lora'] = [{'path': _lora_path(j['model'], lt), 'multiplier': 1.0}] + req.get('lora', [])
    return req


def _img_size(data, w, h):
    """图片实际的宽高（高清修复 / 放大后和请求的不一样）：看 PNG / WebP / JPG 的文件头。"""
    try:
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        if data[8:12] == b'WEBP':
            if data[12:16] == b'VP8X':
                return 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
            if data[12:16] == b'VP8 ':
                return int.from_bytes(data[26:28], 'little') & 0x3fff, int.from_bytes(data[28:30], 'little') & 0x3fff
        if data[:2] == b'\xff\xd8':
            i = 2
            while i < len(data) - 9 and data[i] == 0xff:
                m, ln = data[i + 1], int.from_bytes(data[i + 2:i + 4], 'big')
                if m in (0xc0, 0xc1, 0xc2):
                    return int.from_bytes(data[i + 7:i + 9], 'big'), int.from_bytes(data[i + 5:i + 7], 'big')
                i += 2 + ln
    except Exception:
        pass
    return w, h


DETAIL_NAME = {'face': '脸', 'hand': '手'}


def _gen_wait(j, req, limit=300):
    """发一张图给引擎并等它画完，返回图片字节（取消了返回 None）"""
    prompttrace.capture_image(j, req)
    r = _http('/sdcpp/v1/img_gen', req, timeout=30)
    sd_id, t0 = r['id'], time.time()
    j['sd_id'] = sd_id
    while True:
        if j['cancel']:
            _send_cancel(j)
        time.sleep(0.3)
        st = _http(f'/sdcpp/v1/jobs/{sd_id}', timeout=30)
        if st.get('status') in ('completed', 'failed', 'cancelled'):
            break
        if time.time() - t0 > limit:
            raise RuntimeError('某处细化耗时过长，已放弃')
    j['sd_id'] = None
    if st['status'] == 'cancelled':
        return None
    if st['status'] == 'failed':
        raise RuntimeError((st.get('error') or {}).get('message') or '细化失败')
    return base64.b64decode(st['result']['images'][0]['b64_json'])


def _detail(j, img, seed):
    """自动细化（ADetailer 的做法）：找出脸 / 手 / 身体部位 → 每处连同四周裁下来、放大到约 1024 → 只重画框里的部分（低重绘强度，
    长相、姿势、颜色都不变，只补细节）→ 缩回原大小、边缘羽化后贴回去。框外面的像素一点不动。
    区域本来就够大（放大不到 1.15 倍）的跳过——重画也画不出更多细节。返回 (新图字节, {'脸': 1, …})，什么都没改时返回 (None, {})"""
    import io
    import detect
    from PIL import Image, ImageDraw, ImageFilter, PngImagePlugin
    dt = j['detail']
    im0 = Image.open(io.BytesIO(img)); info = dict(im0.info); base = im0.convert('RGB'); W, H = base.size
    regions = []
    if (dt['face'] or dt['hand']) and detect.available('face'):
        f, h = detect.faces_hands(base)
        regions += [('face', b) for b in f] if dt['face'] else []
        regions += [('hand', b) for b in h] if dt['hand'] else []
    regions = [r for r in regions if min(r[1][2] - r[1][0], r[1][3] - r[1][1]) >= 10]
    regions.sort(key=lambda r: -(r[1][2] - r[1][0]) * (r[1][3] - r[1][1]))
    regions = regions[:10]
    out, done = base.copy(), {}
    for n, (kind, b) in enumerate(regions):
        if j['cancel']:
            break
        j['message'] = f"细化{DETAIL_NAME[kind]}（{n + 1}/{len(regions)}）"
        x1, y1, x2, y2 = b[:4]
        bw, bh = x2 - x1, y2 - y1
        pad = max(24.0, 0.4 * max(bw, bh))
        cx1, cy1, cx2, cy2 = int(max(0, x1 - pad)), int(max(0, y1 - pad)), int(min(W, x2 + pad)), int(min(H, y2 + pad))
        cw, ch = cx2 - cx1, cy2 - cy1
        sc = min(4.0, 1024 / max(cw, ch))
        if sc < 1.15:
            continue
        gw, gh = max(256, round(cw * sc / 16) * 16), max(256, round(ch * sc / 16) * 16)
        crop = base.crop((cx1, cy1, cx2, cy2)).resize((gw, gh), Image.LANCZOS)
        # 重画范围：框（脸用椭圆）稍微放大一点，边缘模糊
        m = Image.new('L', (gw, gh), 0); dr = ImageDraw.Draw(m)
        e = 0.06 * max(bw, bh)
        mb = [(x1 - e - cx1) * gw / cw, (y1 - e - cy1) * gh / ch, (x2 + e - cx1) * gw / cw, (y2 + e - cy1) * gh / ch]
        (dr.ellipse if kind == 'face' else dr.rectangle)(mb, fill=255)
        m = m.filter(ImageFilter.GaussianBlur(max(4, gw * 0.012)))
        st = dt['strength'] if kind == 'face' else dt['strength2']
        req = _request(j, seed)
        bi, bm = io.BytesIO(), io.BytesIO(); crop.save(bi, 'PNG'); m.save(bm, 'PNG')
        req.update(width=gw, height=gh, strength=st, output_format='png', embed_image_metadata=False, batch_count=1,
                   init_image=base64.b64encode(bi.getvalue()).decode(), mask_image=base64.b64encode(bm.getvalue()).decode())
        req.pop('hires', None)
        if dt['prompt']:
            req['prompt'] = dt['prompt']
        # 图生图只走“步数 × 重绘强度”那么多步：按强度把步数放大，实际画的步数和原图差不多（最多 40）
        req['sample_params'] = {**req['sample_params'], 'sample_steps': min(40, max(j['steps'], int(-(-j['steps'] // st))))}
        res = _gen_wait(j, req)
        if res is None:
            break
        r = Image.open(io.BytesIO(res)).convert('RGB').resize((cw, ch), Image.LANCZOS)
        pm = m.resize((cw, ch), Image.LANCZOS)  # 贴回去：同一个羽化范围，框外完全保留原图
        out.paste(r, (cx1, cy1), pm)
        done[DETAIL_NAME[kind]] = done.get(DETAIL_NAME[kind], 0) + 1
    if not done:
        return None, {}
    buf, fmt = io.BytesIO(), j['format']
    if fmt == 'png':
        pi = PngImagePlugin.PngInfo()
        for k, v in info.items():  # 保留写进图里的参数（如果开了“写入参数”）
            if isinstance(v, str):
                pi.add_text(k, v)
        out.save(buf, 'PNG', pnginfo=pi)
    elif fmt == 'jpeg':
        out.save(buf, 'JPEG', quality=j['quality'], exif=info.get('exif') or b'')
    else:
        out.save(buf, 'WEBP', quality=j['quality'], exif=info.get('exif') or b'')
    return buf.getvalue(), done


def _editfix(j, img, seed):
    """改图后处理（editfix.py）：face_ref = 把脸裁下来放大，照着参考脸重画再贴回；keep_face = 贴回原图的脸 + 皮肤校色。
    返回 (新图字节（按任务的图片格式）, 名称)，什么都没改时返回 (None, '')"""
    import io
    import editfix
    from PIL import Image, PngImagePlugin
    info = dict(Image.open(io.BytesIO(img)).info)
    if j.get('face_ref') is not None:
        j['message'] = '脸部精修：找脸'
        crop, ci = editfix.face_crop(img)
        if not crop:
            return None, ''
        face = editfix.ref_face(base64.b64decode(j['_refs'][j['face_ref']]))
        req = _request(j, seed)
        req.update(prompt=__import__('tplstore').T('IMG_REFINE'), negative_prompt='', width=1024, height=1024, batch_count=1, output_format='png', embed_image_metadata=False,
                   ref_images=[base64.b64encode(crop).decode(), base64.b64encode(face).decode()], increase_ref_index=True)
        req.pop('hires', None)
        j['message'] = '脸部精修：照着参考脸重画'
        res = _gen_wait(j, req)
        if res is None:
            return None, ''
        out, what = editfix.face_paste(img, res, ci), '脸部精修'
    else:
        j['message'] = '保留原脸、校正肤色'
        out, what = editfix.keep_face(base64.b64decode(j['_init']), img), '保留原脸'
        if not out:
            return None, ''
    im, buf, fmt = Image.open(io.BytesIO(out)), io.BytesIO(), j['format']
    if fmt == 'png':
        pi = PngImagePlugin.PngInfo()
        for k, v in info.items():
            if isinstance(v, str):
                pi.add_text(k, v)
        im.save(buf, 'PNG', pnginfo=pi)
    else:
        im.save(buf, 'JPEG' if fmt == 'jpeg' else 'WEBP', quality=j['quality'], exif=info.get('exif') or b'')
    return buf.getvalue(), what


def _inpaint_crop(j, seed):
    """局部重画“只画涂抹的地方”：按涂抹范围（加一圈边）裁下来，放大到约 1024 再重画，缩回去按遮罩贴回原图。
    涂抹范围本来就很大（放大不到 1.15 倍）时返回 None，照普通的局部重画来"""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    base = Image.open(io.BytesIO(base64.b64decode(j['_init']))).convert('RGB')
    m = Image.open(io.BytesIO(base64.b64decode(j['_mask']))).convert('L').resize(base.size)
    a = np.asarray(m) > 127
    if not a.any():
        return None
    ys, xs = np.where(a)
    x1, y1, x2, y2 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    W, H = base.size
    pad = max(32.0, 0.35 * max(x2 - x1, y2 - y1))
    cx1, cy1, cx2, cy2 = int(max(0, x1 - pad)), int(max(0, y1 - pad)), int(min(W, x2 + pad)), int(min(H, y2 + pad))
    cw, ch = cx2 - cx1, cy2 - cy1
    sc = min(4.0, 1024 / max(cw, ch))
    if sc < 1.15:
        return None
    gw, gh = max(256, round(cw * sc / 16) * 16), max(256, round(ch * sc / 16) * 16)
    crop = base.crop((cx1, cy1, cx2, cy2)).resize((gw, gh), Image.LANCZOS)
    mc = m.crop((cx1, cy1, cx2, cy2)).resize((gw, gh), Image.LANCZOS)
    req = _request(j, seed)
    bi, bm = io.BytesIO(), io.BytesIO(); crop.save(bi, 'PNG'); mc.save(bm, 'PNG')
    req.update(width=gw, height=gh, output_format='png', embed_image_metadata=False, batch_count=1,
               init_image=base64.b64encode(bi.getvalue()).decode(), mask_image=base64.b64encode(bm.getvalue()).decode())
    req.pop('hires', None)
    j['message'] = '正在放大并细化涂抹区域…'
    res = _gen_wait(j, req, limit=900)
    if res is None:
        return b''
    r = Image.open(io.BytesIO(res)).convert('RGB').resize((cw, ch), Image.LANCZOS)
    pm = m.crop((cx1, cy1, cx2, cy2)).filter(ImageFilter.GaussianBlur(max(2, min(cw, ch) * 0.01)))
    out = base.copy(); out.paste(r, (cx1, cy1), pm)
    buf = io.BytesIO()
    fmt = j['format']
    out.save(buf, 'PNG' if fmt == 'png' else 'JPEG' if fmt == 'jpeg' else 'WEBP', **({} if fmt == 'png' else {'quality': j['quality']}))
    return buf.getvalue()


def _save(j, img, ext, extra):
    """存一张图进图库（同一个任务的几张图记着同一个 job，可以按批删除）。"""
    iid = uuid.uuid4().hex[:12]
    name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + iid[:6] + ext
    with open(os.path.join(images_dir(j['space']), name), 'wb') as f:
        f.write(img)
    orig = extra.pop('_orig', None)
    if j.get('_init') and 'src_file' not in extra:  # 对比用的原图（图生图 / 改图 / 局部重画 / 放大）：同一个任务只存一份
        if not j.get('_src_file'):
            try:
                raw = base64.b64decode(j['_init'])
                sx = '.png' if raw[:4] == b'\x89PNG' else '.webp' if raw[8:12] == b'WEBP' else '.jpg'
                j['_src_file'] = f"src-{j['id']}{sx}"
                with open(os.path.join(_orig_dir(j['space']), j['_src_file']), 'wb') as f:
                    f.write(raw)
            except (OSError, ValueError):
                j['_src_file'] = None
        if j.get('_src_file'):
            extra['src_file'] = j['_src_file']
    if orig:  # 细化前的原图：放进 _orig，详情里可以对比 / 换回去
        extra['orig'] = 'orig-' + name
        with open(os.path.join(_orig_dir(j['space']), extra['orig']), 'wb') as f:
            f.write(orig)
    rec = {'id': iid, 'file': name, 'prompt': j['prompt'], 'prompt_trace': prompttrace.snapshot(j), 'model': j['model'], 'model_name': j['model_name'], 'job': j['id'],
           'created': time.time(), 'size': len(img), **extra}
    gallery_add(j['space'], rec)
    j['images'].append(iid)
    act(f"已生成第 {len(j['images'])} 张（{rec.get('seconds')} 秒）", 'img', 'ok')
    return rec


def _run_upscale(j):
    """放大：ESRGAN 每次 ×4（可以连做两次），不重新画；结果作为一张新图存进图库。"""
    j['message'], j['state'], t0 = '正在放大…', 'running', time.time()
    r = _http('/sdcpp/v1/upscale', {'image': j['_init'], 'repeats': j['repeats'], 'output_format': 'png'}, timeout=600)
    img = base64.b64decode(r['images'][0]['b64_json'])
    w, h = _img_size(img, r.get('width'), r.get('height'))
    _save(j, img, '.png', {'kind': 'upscale', 'src': j['src'], 'seed': j.get('seed'), 'width': w, 'height': h,
                           'seconds': round(time.time() - t0, 1), 'upscaler': r.get('upscaler'), 'scale': (r.get('scale') or 4) ** j['repeats']})
    j['done'] = 1


def _run(j):
    """画这个任务剩下的图。配音要用显卡时画完手上这张就返回 'yield'（剩下的排回队首）。"""
    if not _take_gpu(j):
        return
    try:
        if j['cancel']:
            return
        if WANT.is_set() or _busy:  # 刚拿到显卡配音那边又要用了：先别腾显存、载模型
            return 'yield'
        j['state'], j['message'] = 'running', '正在准备显卡…'
        gpu_free()
        if comfy(j['model']):  # Qwen 2.1：关掉 sd.cpp 把显存让出来，交给 ComfyUI（和生视频同一个引擎）
            Engine.stop()
            return _run_q21(j)
        j['message'] = '正在载入模型…'
        try:
            Engine.ensure(j['model'], abort=lambda: j['cancel'] or WANT.is_set(), opts=j.get('engine_opts') or (Engine.opts if j['kind'] == 'upscale' else None))
        except Aborted:
            return None if j['cancel'] else 'yield'
        if j['kind'] == 'upscale':
            return _run_upscale(j)
        for k in range(j['done'], j['count']):
            if j['cancel']:
                break
            if WANT.is_set():
                return 'yield'
            Engine.last = time.time()
            j['message'] = f"正在生成第 {k + 1}/{j['count']} 张" if j['count'] > 1 else '正在生成'
            j['step'], j['total'], j['preview'] = 0, j['steps'], None
            seed = (j['seed'] + k) % 2 ** 31
            if j.get('mode') == 'inpaint' and j.get('crop'):
                t0 = time.time()
                ci = _inpaint_crop(j, seed)
                if ci == b'':
                    break
                if ci:
                    w, h = _img_size(ci, j['width'], j['height'])
                    _save(j, ci, FORMATS[j['format']], {'seed': seed, 'width': w, 'height': h, 'seconds': round(time.time() - t0, 1), 'crop': True,
                          **{k2: j.get(k2) for k2 in ('mode', 'negative', 'steps', 'cfg', 'sampler', 'scheduler', 'strength', 'src', 'format', 'quality', 'meta')},
                          'loras': [{'name': x['name'], 'weight': x['weight']} for x in j.get('loras') or []]})
                    j['done'] = k + 1
                    continue
            req = _request(j, seed)
            prompttrace.capture_image(j, req)
            try:  # 每一步给一张很粗的预览（不额外占显存）；引擎不认这个参数就不要预览
                r = _http('/sdcpp/v1/img_gen', {**req, 'preview': 'proj', 'preview_interval': 1}, timeout=30)
            except RuntimeError as e:
                if '（400）' not in str(e):
                    raise
                r = _http('/sdcpp/v1/img_gen', req, timeout=30)
            sd_id, t0 = r['id'], time.time()
            j['sd_id'] = sd_id
            while True:
                if j['cancel']:
                    _send_cancel(j)
                time.sleep(0.4)
                s = _http(f'/sdcpp/v1/jobs/{sd_id}', timeout=30)
                pv = s.get('preview') or {}
                if pv.get('total_steps'):
                    j['step'], j['total'] = pv.get('step', 0), pv['total_steps']
                if pv.get('b64_json'):
                    j['preview'] = pv['b64_json']
                if s.get('status') in ('completed', 'failed', 'cancelled'):
                    break
                if time.time() - t0 > 900:
                    raise RuntimeError('本张图片生成超过 15 分钟仍未完成，已放弃')
            j['sd_id'] = None
            if s['status'] == 'cancelled':
                break
            if s['status'] == 'failed':
                raise RuntimeError((s.get('error') or {}).get('message') or '生成失败')
            img = base64.b64decode(s['result']['images'][0]['b64_json'])
            w, h = _img_size(img, j['width'], j['height'])
            det, orig, fx = {}, None, None
            if j.get('detail'):
                try:
                    new, det = _detail(j, img, seed)
                    if new:
                        orig, img = (img if j['detail'].get('keep', True) else None), new
                except Exception as e:  # 细化出错：保留原图，不让整张图白画
                    act('自动细化失败，保留原图：' + str(e)[:200], 'img', 'warn')
                j['sd_id'] = None
            if j.get('face_ref') is not None or j.get('keep_face'):
                try:
                    new, what = _editfix(j, img, seed)
                    if new:
                        orig, img, fx = orig or img, new, what
                except Exception as e:  # 后处理出错：保留原图
                    act('改图后处理失败，保留原图：' + str(e)[:200], 'img', 'warn')
                j['sd_id'] = None
            _save(j, img, FORMATS[j['format']], {'seed': seed, 'width': w, 'height': h, 'base_width': j['width'], 'base_height': j['height'], 'seconds': round(time.time() - t0, 1),
                  **{k2: j.get(k2) for k2 in ('mode', 'negative', 'steps', 'cfg', 'sampler', 'scheduler', 'flow_shift', 'eta', 'strength', 'src', 'control', 'refs',
                                              'hires', 'vae_tiling', 'cache_mode', 'cache_option', 'format', 'quality', 'meta',
                                              'noise_sampler', 'beta_alpha', 'beta_beta', 'extra_args', 'apg', 'slg', 'guidance', 'rng', 'sage')},
                  'loras': [{'name': x['name'], 'weight': x['weight']} for x in j.get('loras') or []],
                  **({'detail': {**{k2: v for k2, v in j['detail'].items() if k2 != 'keep'}, 'done': det}} if j.get('detail') else {}), **({'editfix': fx} if fx else {}), **({'_orig': orig} if orig else {})})
            j['done'] = k + 1
    finally:
        if j.get('sd_id'):  # 出错 / 超时退出时引擎可能还在画这张：叫它停下，别占着显卡
            try:
                _http(f"/sdcpp/v1/jobs/{j['sd_id']}/cancel", {}, timeout=5)
            except Exception:
                pass
            j['sd_id'] = None
        Engine.last = time.time()
        if not j.get('_gpu_gone'):
            GPU.release()
        j.pop('_gpu_gone', None)


def _run_q21(j):
    """Qwen 2.1 的任务（q21.run）。“AI 助手写提示词”那一步要把显卡锁临时还回去（本地 AI 助手要用显卡），再拿回来；
    取消时没拿回来，就记下 _gpu_gone，_run 结束时不再重复释放"""
    q21.act = act

    def save(img, ext, extra):
        if j.get('keep_face'):  # 改图后处理“保留原脸”：贴回原图的脸 + 皮肤校色（只用 PIL，不占显卡）
            try:
                new, what = _editfix(j, img, extra.get('seed'))
                if new:
                    extra, img = {**extra, 'editfix': what, '_orig': img}, new
            except Exception as e:
                act('改图后处理失败，保留原图：' + str(e)[:200], 'img', 'warn')
        return _save(j, img, ext, extra)

    def release():
        j['_gpu_gone'] = True
        GPU.release()

    def take():
        ok = _take_gpu(j)
        if ok:
            j['_gpu_gone'] = False
        return ok
    return q21.run(j, {'save': save, 'release': release, 'take': take, 'want': WANT.is_set})


def _q21_gpu(j):
    """“先增强”和 AI 助手里用官方增强小模型：在请求的线程里拿显卡锁，关掉 sd.cpp、放掉配音的显存。返回 hooks（release / take）"""
    if not _take_gpu(j):
        raise RuntimeError('已取消')
    j['_held'] = True
    gpu_free()
    Engine.stop()

    def release():
        if j.get('_held'):
            j['_held'] = False
            GPU.release()

    def take():
        ok = _take_gpu(j)
        j['_held'] = ok
        return ok
    return {'release': release, 'take': take, 'want': lambda: False}


def q21_preview(b, sp):
    """生图页“先增强”：按生图的设置只跑提示词增强，返回 {'prompt', 'note'}，不出图、不进队列"""
    j = build_job(b, sp)
    if not comfy(j['model']) or j.get('enhance', 'off') == 'off':
        raise ValueError('请先选择 Qwen 2.1 模型，并打开提示词增强')
    hooks = _q21_gpu(j)
    try:
        q21.act = act
        return q21.preview(j, hooks)
    finally:
        hooks['release']()


def sam_select(b, sp):
    """局部重画的「智能选取」：b = {key, x, y, image?}（image = {gallery: id} 或 {data}；同一张图第二次起只带 key）。
    在请求的线程里拿显卡锁（正在出图时等它画完手上这张），返回 {mask, area} 或 {need: 'image'}"""
    key = str(b.get('key') or '')[:80]
    if not key:
        raise ValueError('缺少 key')
    key = f'{sp}:{key}'  # 普通空间和私密空间各管各的
    img = b.get('image')
    data = _image_b64(img, sp, '原图') if img else None
    j = {'id': 'sam', 'cancel': False, 'message': '', 'space': sp}
    hooks = _q21_gpu(j)
    try:
        if b.get('prep'):  # 放图后先分析（不点）
            return q21.sam_prep(key, data)
        return q21.sam_select(key, _num(b.get('x'), 0.0, 1.0, 0.5), _num(b.get('y'), 0.0, 1.0, 0.5), data, int(_num(b.get('level'), 0, 20, 0, int)))
    except q21.NeedImage:
        return {'need': 'image'}
    finally:
        hooks['release']()


def q21_pe_chat(kind, system, text, images, sp):
    """AI 助手里直接和官方增强小模型对话（单轮）"""
    j = {'id': 'pechat', 'cancel': False, 'message': '', 'space': sp}
    hooks = _q21_gpu(j)
    try:
        return q21.pe_chat(kind, system, text, images, sp)
    finally:
        hooks['release']()


def worker():
    while True:
        with _qcv:
            while not queue:
                _qcv.wait()
            # 排队：和现在已载入的模型相同的任务先画（换模型要重启引擎、重新读十几 GB），同模型之间保持先后顺序
            cur = Engine.model if Engine.proc and Engine.proc.poll() is None else None
            k = next((n for n, x in enumerate(queue) if jobs.get(x, {}).get('state') == 'queued' and jobs[x].get('model') == cur), 0) if cur else 0
            h0 = next((n for n, x in enumerate(queue) if jobs.get(x, {}).get('state') == 'queued'), 0)  # 最早的、还在排队的（取消了的不算）
            if k and k != h0 and time.time() - (jobs.get(queue[h0], {}).get('created') or time.time()) > 900:  # 它等了 15 分钟以上：不再让同模型插队（审查 29）
                k = h0
            jid = queue.pop(k)
        j = jobs.get(jid)
        if not j or j['state'] != 'queued':
            continue
        set_space(j['space'])
        try:
            if _run(j) == 'yield' and not j['cancel']:  # 配音要用显卡：剩下的图排回最前面，等它用完接着画
                j['state'], j['message'], j['step'], j['preview'], j['sd_id'] = 'queued', '配音正在使用显卡，释放后将自动继续生成', 0, None, None
                with _qcv:
                    queue.insert(0, jid)
                continue
            j['state'] = 'cancelled' if j['cancel'] and j['done'] < j['count'] else 'done'
            j['message'] = ('已取消' + (f"（已生成 {j['done']} 张）" if j['done'] else '')) if j['state'] == 'cancelled' else '完成'
        except Exception as e:
            j['state'], j['error'], j['message'] = 'error', str(e), '生成失败'
            act('生图失败：' + str(e), 'img', 'error')
        j['finished'], j['preview'], j['step'] = time.time(), None, 0
        release(j)


threading.Thread(target=worker, daemon=True).start()
