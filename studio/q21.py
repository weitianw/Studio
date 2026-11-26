"""Qwen-Image 2.1（阿里，2026-09；ComfyUI 原生节点）：文生图 / 指令改图 / 局部重画。被 imagegen.py 调用。

- 参数照老王论坛作者的截图（测试和对比见 docs/Qwen2.1/报告.md）；工作流在 docs/Qwen2.1/脚本/q21.py 测通后搬到这里。
- 跑在应用的 ComfyUI 上（videogen.Engine，端口 8188，和生视频、改衣同一个）。显卡锁由 imagegen._run 拿着，这里只在
  「AI 助手写提示词」那一步临时还回去（本地 AI 助手要用显卡）。
- 提示词增强（增强小模型跑在 ComfyUI 的 TextGenerate 节点；AI 助手是本地 Qwen3.8）。网页上是“写提示词：关 / 官方 / 助手”：
    off      不增强，原话直接给模型
    pe       官方增强：写得更细（姿势关节、光影、保持项）
    ai       AI 助手直接写：不用增强小模型，AI 助手看图按官方增强的写法自己写
"""
import base64, hashlib, io, json, os, random, re, threading, time, uuid
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import videogen as V

HERE = os.path.dirname(os.path.abspath(__file__))
# 生图模型的表（开源泛化 ② 起从 studio/catalog/image.json + 功能包 + studio/user-models.json 读，见 catalog.py）。
# 表的名字和格式照旧（UNET / FAMILY / TXT_ONLY / SETTINGS / MODELS，TE / VAE 是 Qwen 2.1 的文本编码器和 VAE），别的代码不用改；
# 模型自己写了 te / vae 的放在 MODEL_TXT，用 txt_files(key) 取
import catalog  # noqa: E402
UNET, FAMILY, TXT_ONLY, SETTINGS, MODELS, MODEL_TXT, FAMILIES = {}, {}, {}, {}, {}, {}, {}
TE = VAE = None
_SHOW = ('name', 'base', 'speed', 'tag', 'family', 'modes', 'desc', 'defaults', 'refine', 'fixed_loras', 'source')


def load_catalog():
    """（重新）读模型目录，原地更新上面这几张表（别的模块拿着的引用照样有效）。返回模型数"""
    global TE, VAE
    c = catalog.load('image')
    fams = c['families']
    FAMILIES.clear(); FAMILIES.update(fams)
    TE, VAE = (fams.get('q21') or {}).get('te'), (fams.get('q21') or {}).get('vae')
    TXT_ONLY.clear(); TXT_ONLY.update({f: {'te': v['te'], 'type': v['type'], 'vae': v['vae']} for f, v in fams.items() if v.get('type')})
    for d in (UNET, FAMILY, SETTINGS, MODELS, MODEL_TXT):
        d.clear()
    for k, m in c['models'].items():
        fam = m.get('family')
        if fam not in fams or not m.get('unet'):
            continue
        UNET[k], FAMILY[k] = m['unet'], fam
        SETTINGS[k] = {mode: {a: (tuple(b) if a == 'slg' and isinstance(b, list) else b) for a, b in s.items()} for mode, s in m['settings'].items()}
        e = {x: m[x] for x in _SHOW if x in m}
        if 'fixed_loras' in e:
            e['fixed_loras'] = [tuple(x) for x in e['fixed_loras']]
        MODELS[k] = {**e, 'backend': 'comfy'}
        if m.get('te') or m.get('vae'):
            MODEL_TXT[k] = {x: m[x] for x in ('te', 'vae') if m.get(x)}
    return len(MODELS)


def txt_files(key):
    """这个模型实际用的文本编码器 / VAE / CLIPLoader 类型：family 默认的，模型自己写了的优先"""
    fam = FAMILY.get(key)
    base = dict(TXT_ONLY.get(fam) or {'te': TE, 'vae': VAE, 'type': 'qwen_image'})
    base.update(MODEL_TXT.get(key) or {})
    return base


load_catalog()
# Z-Image 的 LoRA 和 sd.cpp 版共用 models\Z-Image\loras（ComfyUI 的 extra_model_paths.yaml 把它加进 loras，名字不带子文件夹）；Krea 2 的同样在 models\Krea2\loras
ZIMG_LORA_DIR = config.models('Z-Image', 'loras')
KREA_LORA_DIR = config.models('Krea2', 'loras')
BARE_LORA = {'zimg': ZIMG_LORA_DIR, 'krea2': KREA_LORA_DIR}  # 这几个底子的 LoRA 不在 ComfyUI/models/loras 里，名字不带子文件夹
# 二采（Krea 2 润色）：作者的 5 个 Krea 2 LoRA（models\Krea2\loras）
REFINE_LORAS = [('Krea_2_zidiusArt_Melancholy.safetensors', 0.35), ('TJFilmStyleKrea2_V2.safetensors', 1.0), ('realism_engine_krea2_v3.1.safetensors', 0.45),
                ('krea2-Cc-MJ-影视柔光.safetensors', 0.6), ('grainscape_krea2.safetensors', 0.7)]
H3IMG_NODE = os.path.join(os.path.dirname(V.MODELS_DIR), 'comfy_extras', 'nodes_minimax_h3.py')  # H3-Image 的节点：ComfyUI 2026-11-15 之后的版本才有
PE = {'i2i': r'Qwen_VL\qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors',
      't2i': r'Qwen_VL\qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors'}
# 提示词增强小模型 / 文本编码器的可选版本：'official' = 官方模型（默认）
PE_SETS = {'official': PE}
TE_SETS = {'official': TE}


def pe_set(j):
    """这个任务用哪套增强小模型：显式给了 pe_model 就用它；其余官方"""
    j = j or {}
    return j.get('pe_model') if j.get('pe_model') in PE_SETS else 'official'


def pe_name(j, kind):
    return PE_SETS[pe_set(j)][kind]


def te_name(j):
    return TE_SETS.get((j or {}).get('te_model') or 'official', TE)


POSE_LORA = 'VNCCS_QI2_PoseStudioV1.1.safetensors'  # Fisher Pose 用的 VNCCS PoseStudio LoRA（强度 1）：人偶图当图 1、人物当图 2
LORA_SUB = 'Qwen21'  # 用户自己的 Qwen 2.1 LoRA：ComfyUI/models/loras/Qwen21（Civitai 商店下载也放这里）
LORA_SUBS = {'q21': LORA_SUB, 'moss': 'MOSS', 'h3img': 'H3_Image'}  # 每个底子一个 LoRA 文件夹（ComfyUI/models/loras/…）
POSE_PROMPT = 'Draw character from image2.'  # Fisher 单人自由姿势的固定指令（LoRA 训练时的触发写法）
POSE_STEPS = 25  # Fisher 文档推荐：25 步、euler、simple、CFG 1
SAM = 'sam3.1_multiplex_fp16.safetensors'  # 面部重绘自动找脸（改衣也用它）

# 每个模型、每种用法的设置（作者截图；快速版按 Ray 模型页：euler_ancestral、30 步）
#   txt：200 万像素、30 步；edit：300 万像素、50 步，参考图先缩到 200 万像素、改图节点按 1280 看；
#   inpaint：按涂抹范围外扩 1.5 倍裁剪、放大到 1536、40 步、降噪 1.0，画完拼回
REF_MP, REF_RES = 2.0, 1280
# 2026-11-23 用户：设置不要都固定死，默认用推荐的，想改的时候能改（步数、像素等）。网页上改了的几项放在 j['q_over']，跑的时候盖在 SETTINGS 上
Q_SAMPLERS = ['euler', 'euler_ancestral', 'er_sde', 'res_multistep', 'heun', 'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_sde', 'dpmpp_3m_sde', 'uni_pc', 'lcm', 'ddim', 'gradient_estimation']
Q_SCHEDULERS = ['simple', 'beta', 'normal', 'karras', 'exponential', 'sgm_uniform', 'ddim_uniform', 'linear_quadratic', 'kl_optimal']


def clean_over(o, mode):
    """网页传来的改动只留合法的：steps 1~100、cfg 0~20、采样器 / 调度器在列表里、mp（百万像素）0.25~6 或 'page'（按网页选的尺寸）；局部重画不改像素"""
    out = {}
    if not isinstance(o, dict):
        return out
    try:
        if o.get('steps') not in (None, ''):
            out['steps'] = max(1, min(100, int(o['steps'])))
        if o.get('cfg') not in (None, ''):
            out['cfg'] = round(max(0.0, min(20.0, float(o['cfg']))), 2)
        if o.get('mp') == 'page' and mode == 'txt':
            out['mp'] = 'page'  # 按网页选的尺寸（跑的时候换成 None；记录里留着 page，复用时才填得回去，第二轮审查 6）
        elif o.get('mp') not in (None, '') and mode in ('txt', 'edit'):
            out['mp'] = round(max(0.25, min(6.0, float(o['mp']))), 2)
    except (TypeError, ValueError):
        pass
    if o.get('sampler') in Q_SAMPLERS:
        out['sampler'] = o['sampler']
    if o.get('scheduler') in Q_SCHEDULERS:
        out['scheduler'] = o['scheduler']
    return out
ENHANCE = ('off', 'pe', 'ai')
WITH_AI = ('ai',)  # 要 AI 助手的几档：ai = 不用增强小模型，它看图直接写


CHAT = None      # 由 server.py 设：CHAT(system, user, images) → 本地 AI 助手（Qwen3.8）写一次回答
RELEASE = None   # 由 server.py 设：AI 助手用完立刻放掉显存


def act(msg, tag='img', level='info'):  # 由 imagegen 换成网页运行日志
    pass


def _path(folder, rel):
    return os.path.join(V.MODELS_DIR, folder, rel)


def missing(key):
    if FAMILY.get(key) == 'ckpt':  # 通用 Checkpoint：一个文件（自带文本编码器和 VAE）
        need = [('checkpoints', UNET[key], 'Checkpoint')] + ([('vae', MODEL_TXT[key]['vae'], 'VAE')] if MODEL_TXT.get(key, {}).get('vae') else [])
        return [n + '（ComfyUI/models/' + f + '/' + r.replace('\\', '/') + '）' for f, r, n in need if not V._have(_path(f, r))]
    t = TXT_ONLY.get(FAMILY.get(key))
    tf = txt_files(key)
    need = [('diffusion_models', UNET[key], '主模型'), ('text_encoders', tf['te'], '文本编码器' if t else '文本编码器 qwen3vl_8b'), ('vae', tf['vae'], 'VAE')]
    out = [n + '（ComfyUI/models/' + f + '/' + r.replace('\\', '/') + '）' for f, r, n in need if not V._have(_path(f, r))]
    if FAMILY.get(key) == 'h3img' and not h3img_node():
        out.append('新版 ComfyUI（H3-Image 的节点 2026-11-15 才加入，请先更新 ComfyUI）')
    return out


_H3N = {}


def h3img_node():
    """ComfyUI 里有没有 H3-Image 的节点（MiniMaxH3ImageConditioning）。同名文件 nodes_minimax_h3.py 旧版就有（H3 视频），要看里面有没有这个节点；按文件修改时间缓存"""
    try:
        mt = os.path.getmtime(H3IMG_NODE)
    except OSError:
        return False
    if _H3N.get('mt') != mt:
        with open(H3IMG_NODE, encoding='utf-8', errors='replace') as f:
            _H3N.update(mt=mt, ok='MiniMaxH3ImageConditioning' in f.read())
    return _H3N['ok']


def lora_sub(key=None):
    f = FAMILY.get(key)
    if 'lora_sub' in (FAMILIES.get(f) or {}):  # 目录里给了这个底子的 LoRA 文件夹（ComfyUI/models/loras/<它>，'' = loras 根目录）
        return FAMILIES[f]['lora_sub']
    return '' if f in BARE_LORA else LORA_SUBS.get(f, LORA_SUB)


def lora_dir(key=None):
    return BARE_LORA.get(FAMILY.get(key)) or _path('loras', lora_sub(key))


def pose_renumber(text, n=3):
    """放了 3D 人偶姿势时人偶图是图 1：用户照网页上的编号写的「图1 / 图 2 / image3 / 第2张图」都往后挪一位。
    n = 网页上的图数（原图 + 参考图）。用户已经按模型的编号写了（提到的编号比网页上的图多，或「图1」挨着姿势 / 人偶）时不挪"""
    nums = [int(x) for x in re.findall(r'(?:图|image|第)\s*([1-9])(?![0-9])', text, flags=re.I)] + ['一二三'.index(x) + 1 for x in re.findall(r'第\s*([一二三])\s*张', text)]
    if any(k > n for k in nums) or re.search(r'(图\s*1|image\s*1|第\s*[1一]\s*张)(?![0-9]).{0,10}(姿势|人偶|骨架|pose|mannequin)|(姿势|人偶|pose|mannequin).{0,6}(图\s*1|image\s*1)(?![0-9])', text, flags=re.I):
        return text
    t = re.sub(r'(图\s*)([1-9])(?![0-9])', lambda m: m.group(1) + str(int(m.group(2)) + 1), text)
    t = re.sub(r'(第\s*)([1-9])(\s*张)', lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), t)
    t = re.sub(r'(第\s*)([一二三])(\s*张)', lambda m: m.group(1) + '二三四'['一二三'.index(m.group(2))] + m.group(3), t)
    return re.sub(r'((?<![A-Za-z])<?image\s*)([1-9])(?![0-9])', lambda m: m.group(1) + str(int(m.group(2)) + 1), t, flags=re.I)


def pose_ok():
    return V._have(_path('loras', POSE_LORA))


def pe_ok(kind='i2i', pm=None):
    return V._have(_path('text_encoders', PE_SETS.get(pm or 'official', PE)[kind]))


def model_gb(key):
    try:
        return round(os.path.getsize(_path('checkpoints' if FAMILY.get(key) == 'ckpt' else 'diffusion_models', UNET[key])) / 1e9, 1)
    except OSError:
        return None


_SP = {}


def _system(kind):
    if kind not in _SP:
        with open(os.path.join(HERE, 'workflows', f'q21_pe_{kind}.txt'), encoding='utf-8') as f:
            _SP[kind] = f.read()
    return _SP[kind]


def size_for(mp, w, h, step=32):
    """按百万像素和宽高比算出图尺寸（32 的倍数）"""
    a = w / max(1, h)
    W = (mp * 1e6 * a) ** 0.5
    return int(round(W / step) * step), int(round(W / a / step) * step)


# ---------------------------------------------------------------- 工作流
def _base(wf, key, loras=(), te=None):
    """loras：[(ComfyUI 里的 LoRA 名字, 强度)]，依次串上（姿势 LoRA、用户选的 LoRA）"""
    wf['u'] = {'class_type': 'UNETLoader', 'inputs': {'unet_name': UNET[key], 'weight_dtype': 'default'}}
    tf = txt_files(key)
    wf['c'] = {'class_type': 'CLIPLoader', 'inputs': {'clip_name': tf['te'] if te in (None, TE) else te, 'type': 'qwen_image', 'device': 'default'}}
    wf['v'] = {'class_type': 'VAELoader', 'inputs': {'vae_name': tf['vae']}}
    mdl = ['u', 0]
    for i, (name, w) in enumerate(loras or ()):
        wf[f'lo{i}'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': mdl, 'lora_name': name, 'strength_model': float(w)}}
        mdl = [f'lo{i}', 0]
    wf['cache'] = {'class_type': 'QwenImage21Cache', 'inputs': {'model': mdl, 'device': 'auto', 'dtype': 'default'}}


def _refs(wf, names, first=1):
    """参考图：先 lanczos 缩到 200 万像素（作者截图），返回 {images.image_N: 节点}"""
    out = {}
    for i, n in enumerate(names, first):
        wf[f'l{i}'] = {'class_type': 'LoadImage', 'inputs': {'image': n}}
        wf[f's{i}'] = {'class_type': 'ImageScaleToTotalPixels', 'inputs': {'image': [f'l{i}', 0], 'upscale_method': 'lanczos', 'megapixels': REF_MP, 'resolution_steps': 1}}
        out[f'images.image_{i}'] = [f's{i}', 0]
    return out


def wf_enhance(kind, names, prompt, seed, system=None, pe=None):
    """只跑官方提示词增强（官方模板的系统提示词和采样参数），输出在 PreviewAny「pv」里。system：换一套系统提示词（AI 助手里直接和小模型对话时）"""
    wf = {}
    imgs = _refs(wf, names) if kind == 'i2i' and names else {}
    tg = {'clip': ['pc', 0], 'prompt': prompt, 'system_prompt': system if system is not None else _system(kind), 'max_length': 4096, 'sampling_mode': 'on',
          'sampling_mode.temperature': 1.0, 'sampling_mode.top_k': 20, 'sampling_mode.top_p': 0.95, 'sampling_mode.min_p': 0.0,
          'sampling_mode.repetition_penalty': 1.0, 'sampling_mode.seed': seed % (2 ** 63), 'sampling_mode.presence_penalty': 0.0 if kind == 'i2i' else 1.5,
          'thinking': False, 'use_default_template': True, 'mtp': 'auto'}
    wf['pc'] = {'class_type': 'CLIPLoader', 'inputs': {'clip_name': pe or PE[kind], 'type': 'qwen_image', 'device': 'default'}}
    if imgs:
        wf['bt'] = {'class_type': 'BatchImagesNode', 'inputs': {f'images.image{i}': v for i, v in enumerate(imgs.values())}}  # 前缀式自动增长：image0、image1…
        tg['image'] = ['bt', 0]
    wf['tg'] = {'class_type': 'TextGenerate', 'inputs': tg}
    wf['pv'] = {'class_type': 'PreviewAny', 'inputs': {'source': ['tg', 0]}}
    return wf


def wf_gen(key, names, prompt, seed, w, h, st, prefix, loras=(), te=None):
    """文生图（names 为空）/ 指令改图（names = 图 1、图 2、图 3）。loras：3D 人偶摆姿势的 PoseStudio LoRA、用户选的 LoRA"""
    wf = {}
    _base(wf, key, loras, te)
    imgs = _refs(wf, names)
    wf['e'] = {'class_type': 'TextEncodeQwenImage21', 'inputs': {'clip': ['c', 0], 'prompt': prompt, 'negative_prompt': '', 'resolution': REF_RES, 'vae': ['v', 0], **imgs}}
    wf['lat'] = {'class_type': 'EmptyLatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}}
    wf['k'] = {'class_type': 'KSampler', 'inputs': {'model': ['cache', 0], 'positive': ['e', 0], 'negative': ['e', 1], 'latent_image': ['lat', 0], 'seed': seed % (2 ** 63),
                                                   'steps': st['steps'], 'cfg': st.get('cfg', 1.0), 'sampler_name': st['sampler'], 'scheduler': st['scheduler'], 'denoise': 1.0}}
    wf['d'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k', 0], 'vae': ['v', 0]}}
    wf['o'] = {'class_type': 'SaveImage', 'inputs': {'images': ['d', 0], 'filename_prefix': prefix}}
    return wf


def wf_txt_other(key, prompt, seed, w, h, st, prefix, loras=()):
    """MOSS / H3-Image 的文生图（照 ComfyUI 官方模板：image_moss_image_t2i.json；H3-Image 用 MiniMaxH3ImageConditioning，自带空白 latent）"""
    fam = FAMILY[key]
    t = txt_files(key)
    wf = {'u': {'class_type': 'UNETLoader', 'inputs': {'unet_name': UNET[key], 'weight_dtype': 'default'}},
          'c': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': t['te'], 'type': t['type'], 'device': 'default'}},
          'v': {'class_type': 'VAELoader', 'inputs': {'vae_name': t['vae']}}}
    mdl = ['u', 0]
    if st.get('shift'):  # MOSS 写真：AuraFlow 偏移（作者 5）
        wf['ms'] = {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': mdl, 'shift': st['shift']}}
        mdl = ['ms', 0]
    for i, (name, wt) in enumerate(list(MODELS.get(key, {}).get('fixed_loras') or ()) + list(loras or ())):  # 固定的那套在前（作者的顺序），用户选的接在后面
        wf[f'lo{i}'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': mdl, 'lora_name': name, 'strength_model': float(wt)}}
        mdl = [f'lo{i}', 0]
    if st.get('slg'):  # 跳层引导（作者：单层 22，前 50%）
        sl, s0, s1 = st['slg']
        wf['slg'] = {'class_type': 'SkipLayerGuidanceDiTSimple', 'inputs': {'model': mdl, 'double_layers': '', 'single_layers': sl, 'start_percent': s0, 'end_percent': s1}}
        mdl = ['slg', 0]
    if fam == 'h3img':
        wf['p'] = {'class_type': 'MiniMaxH3ImageConditioning', 'inputs': {'clip': ['c', 0], 'vae': ['v', 0], 'prompt': prompt, 'width': w, 'height': h}}
        wf['n'] = {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['p', 0]}}
        lat = ['p', 1]
    elif fam == 'krea2':  # 官方 Text to Image (Krea-2 Turbo)：负面置零、普通空白 latent
        wf['p'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['c', 0], 'text': prompt}}
        wf['n'] = {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['p', 0]}}
        wf['lat'] = {'class_type': 'EmptyLatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}}
        lat = ['lat', 0]
    elif fam == 'zimg':  # 官方 image_z_image_turbo.json
        wf['ms'] = {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': mdl, 'shift': 3}}
        mdl = ['ms', 0]
        wf['p'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['c', 0], 'text': prompt}}
        wf['n'] = {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['p', 0]}}
        wf['lat'] = {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}}
        lat = ['lat', 0]
    else:
        wf['p'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['c', 0], 'text': prompt}}
        wf['n'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['c', 0], 'text': ''}}
        wf['lat'] = {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}}
        lat = ['lat', 0]
    wf['k'] = {'class_type': 'KSampler', 'inputs': {'model': mdl, 'positive': ['p', 0], 'negative': ['n', 0], 'latent_image': lat, 'seed': seed % (2 ** 63),
                                                   'steps': st['steps'], 'cfg': st.get('cfg', 1.0), 'sampler_name': st['sampler'], 'scheduler': st['scheduler'], 'denoise': 1.0}}
    wf['d'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k', 0], 'vae': ['v', 0]}}
    wf['o'] = {'class_type': 'SaveImage', 'inputs': {'images': ['d', 0], 'filename_prefix': prefix}}
    return wf


def wf_ckpt(key, prompt, seed, w, h, st, prefix, loras=()):
    """通用 Checkpoint（SD 1.5 / SDXL / Pony 这类一个文件里带文本编码器和 VAE 的模型，开源泛化 ②）：ComfyUI 默认的文生图工作流。
    LoRA 用 LoraLoader（同时接模型和文本编码器）；模型自己写了 vae 时换成单独的 VAE；负面提示词在 st['negative']"""
    wf = {'ck': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': UNET[key]}}}
    mdl, clip, vae = ['ck', 0], ['ck', 1], ['ck', 2]
    for i, (name, wt) in enumerate(list(MODELS.get(key, {}).get('fixed_loras') or ()) + list(loras or ())):
        wf[f'lo{i}'] = {'class_type': 'LoraLoader', 'inputs': {'model': mdl, 'clip': clip, 'lora_name': name, 'strength_model': float(wt), 'strength_clip': float(wt)}}
        mdl, clip = [f'lo{i}', 0], [f'lo{i}', 1]
    if MODEL_TXT.get(key, {}).get('vae'):
        wf['v'] = {'class_type': 'VAELoader', 'inputs': {'vae_name': MODEL_TXT[key]['vae']}}
        vae = ['v', 0]
    wf['p'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': clip, 'text': prompt}}
    wf['n'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': clip, 'text': st.get('negative') or ''}}
    wf['lat'] = {'class_type': 'EmptyLatentImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1}}
    wf['k'] = {'class_type': 'KSampler', 'inputs': {'model': mdl, 'positive': ['p', 0], 'negative': ['n', 0], 'latent_image': ['lat', 0], 'seed': seed % (2 ** 63),
                                                   'steps': st['steps'], 'cfg': st.get('cfg', 7.0), 'sampler_name': st['sampler'], 'scheduler': st['scheduler'], 'denoise': 1.0}}
    wf['d'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k', 0], 'vae': vae}}
    wf['o'] = {'class_type': 'SaveImage', 'inputs': {'images': ['d', 0], 'filename_prefix': prefix}}
    return wf


REBALANCE_NODE = os.path.join(os.path.dirname(V.MODELS_DIR), 'custom_nodes', 'comfyui-krea2-conditioning')  # ConditioningKrea2Rebalance（Apache-2.0，作者包里带的）


def refine_missing():
    """二采要的文件：Krea 2 Turbo 三件套 + 作者的 5 个 LoRA"""
    t = TXT_ONLY['krea2']
    need = [_path('diffusion_models', UNET['krea2']), _path('text_encoders', t['te']), _path('vae', t['vae'])] + [os.path.join(KREA_LORA_DIR, n) for n, _ in REFINE_LORAS]
    return [os.path.basename(p) for p in need if not V._have(p)]


def wf_refine(img_name, prompt, seed, prefix):
    """二采（老王论坛 MOSS × Krea2 双采作者的流程）：一采的图 → Krea 2 Turbo + 5 个 LoRA；正面过 ConditioningKrea2Rebalance（balanced），负面置零；
    KSamplerAdvanced 8 步、从第 6 步开始（只重画最后 2 步，约改 25%）、CFG 1、er_sde + beta。构图、人物不变，只改光影、肤质、胶片感。
    A/B（docs/AB测试/MOSS_Krea2双采_1121）：皮肤更光滑；画面里的中文字会被改花、脸会往东亚甜美偏"""
    t = TXT_ONLY['krea2']
    wf = {'u': {'class_type': 'UNETLoader', 'inputs': {'unet_name': UNET['krea2'], 'weight_dtype': 'default'}},
          'c': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': t['te'], 'type': 'krea2', 'device': 'default'}},
          'v': {'class_type': 'VAELoader', 'inputs': {'vae_name': t['vae']}},
          'li': {'class_type': 'LoadImage', 'inputs': {'image': img_name}}}
    mdl = ['u', 0]
    for i, (n, s) in enumerate(REFINE_LORAS):
        wf[f'lo{i}'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': mdl, 'lora_name': n, 'strength_model': s}}
        mdl = [f'lo{i}', 0]
    wf['p'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['c', 0], 'text': prompt}}
    pos = ['p', 0]
    if os.path.isdir(REBALANCE_NODE):
        wf['rb'] = {'class_type': 'ConditioningKrea2Rebalance', 'inputs': {'conditioning': pos, 'preset': 'balanced', 'per_layer_weights': '1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.5, 5.0, 1.1, 4.0, 1.0',
                                                                           'multiplier': 1.0, 'renormalize': True}}
        pos = ['rb', 0]
    wf['n'] = {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['p', 0]}}
    wf['en'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['li', 0], 'vae': ['v', 0]}}
    wf['k'] = {'class_type': 'KSamplerAdvanced', 'inputs': {'model': mdl, 'add_noise': 'enable', 'noise_seed': seed % (2 ** 63), 'steps': 8, 'cfg': 1.0, 'sampler_name': 'er_sde',
                                                           'scheduler': 'beta', 'positive': pos, 'negative': ['n', 0], 'latent_image': ['en', 0],
                                                           'start_at_step': 6, 'end_at_step': 10000, 'return_with_leftover_noise': 'disable'}}
    wf['d'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k', 0], 'vae': ['v', 0]}}
    wf['o'] = {'class_type': 'SaveImage', 'inputs': {'images': ['d', 0], 'filename_prefix': prefix}}
    return wf


INPAINT_LEAD = '把图 1 中的灰色区域重画，与周围的皮肤、衣服、头发和光线自然衔接：'


# 参考图先提取衣服（2026-11-16 用户要的选项，默认关）：参考图是穿在人身上的衣服照片时，模型会照着照片里模特的肤色画镂空 / 露肤处
# （A/B：参考图模特的皮肤 L≈46，人物 L≈64，成品镂空处偏橙黄；只在提示词里写肤色没用）。先用指令改图把衣服提取成白底商品图，再拿它当参考
X_PROMPT = '把图1中人物身上穿的衣服单独提取出来，平铺展示在纯白色背景上，像服装商品图：完整保留衣服的颜色、面料质感、图案、镂空和结构细节，画面里没有人。'
_XCACHE = {}  # (模型, 参考图 sha1) → 提取好的 PNG（内存里先找），最多 6 张
# 2026-11-17 用户：提取出来的衣服也要进生图图库（普通空间再放进素材库/提取的衣服）。imagegen 设这两个：
SAVE_EXTRACT = None  # SAVE_EXTRACT(j, png, {sha1, w, h, sec})：存进这个任务所在空间的图库
FIND_EXTRACT = None  # FIND_EXTRACT(j, 模型, sha1) → 图库里以前提取过的 PNG 或 None（重启后也不用再提取）


def extract_refs(j, key, names, work_in, te=None):
    """把 names[1:]（参考图）换成提取出来的衣服图（就地覆盖 ComfyUI 输入文件夹里的那张）；同一张图只提取一次"""
    from PIL import Image
    work_out = os.path.join(V.WORK['n'], 'out')
    for i, n in enumerate(names[1:], 2):
        p = os.path.join(work_in, n)
        with open(p, 'rb') as f:
            ck = (key, hashlib.sha1(f.read()).hexdigest())
        if ck not in _XCACHE and FIND_EXTRACT:
            got = FIND_EXTRACT(j, key, ck[1])
            if got:
                _XCACHE[ck] = got
        if ck not in _XCACHE:
            if j.get('cancel'):
                raise Cancelled
            t0 = time.time()
            st = dict(SETTINGS[key]['edit'])
            w, h = size_for(st['mp'], *Image.open(p).size)
            label = f'正在提取图 {i} 的衣服'
            j['message'], j['step'], j['total'] = label + '…', 0, st['steps']
            outs = _submit(j, wf_gen(key, [n], X_PROMPT, 1234, w, h, st, f'studio_x_{ck[1][:10]}', (), te), label)
            it = ((outs.get('o') or {}).get('images') or [None])[0]
            if not it:
                raise RuntimeError('提取衣服时 ComfyUI 没有输出图片')
            fp = os.path.join(work_out, it.get('subfolder', ''), it['filename'])
            im = Image.open(fp).convert('RGBA')
            flat = Image.new('RGBA', im.size, (255, 255, 255, 255)); flat.alpha_composite(im)  # 2.1 的输出带透明通道：铺在白底上
            b = io.BytesIO(); flat.convert('RGB').save(b, 'PNG')
            try:
                os.remove(fp)
            except OSError:
                pass
            _XCACHE[ck] = b.getvalue()
            if SAVE_EXTRACT:
                try:
                    SAVE_EXTRACT(j, _XCACHE[ck], {'sha1': ck[1], 'w': flat.width, 'h': flat.height, 'sec': round(time.time() - t0, 1)})
                except Exception as e:  # 存不进图库不影响这次生成
                    act(f'提取的衣服没能存进图库：{e}', 'img', 'warn')
            while len(_XCACHE) > 6:
                _XCACHE.pop(next(iter(_XCACHE)))
        with open(p, 'wb') as f:
            f.write(_XCACHE[ck])
    j['ref_extracted'] = len(names) - 1


def auto_grow(mask_path, st, blend=32, cells=2.2):
    """局部重画遮罩外扩多少像素（原图像素）：约 2.2 格潜空间格子（2026-11-16 A/B：边离原来的东西不到两格，原来的边会从边上那格漏进来）。
    一格 = 8 ÷ 裁剪缩放比例；裁剪大小照 InpaintCropImproved 的算法（外扩 blend 后的范围 × crop 倍，裁到图内，按长边缩放到 res）"""
    from PIL import Image
    m = Image.open(mask_path).convert('L').point(lambda v: 255 if v > 127 else 0)
    box = m.getbbox()
    if not box:
        return 0
    W, H = m.size
    x0, y0, x1, y1 = box[0] - blend, box[1] - blend, box[2] + blend, box[3] + blend
    gx, gy = (x1 - x0) * (st['crop'] - 1) / 2, (y1 - y0) * (st['crop'] - 1) / 2
    long = max(min(W, x1 + gx) - max(0, x0 - gx), min(H, y1 + gy) - max(0, y0 - gy))
    return int(min(96, max(4, round(cells * 8 * long / st['res']))))


EDGE_DEFAULT = ('hard', 'dd', 'grow')  # 局部重画默认的边缘处理（2026-11-16 用户同意；整件换衣、只涂一部分改都测过）


def wf_local(key, src, mask, refs, prompt, seed, st, prefix, grey=True, loras=(), te=None, edge=(), grow=0):
    """局部重画（作者「局部图像编辑」）：按涂抹范围外扩 1.5 倍裁剪、放大到 1536；图 1 = 裁剪图（涂抹处涂成灰色，
    不涂灰时模型会照抄图 1、几乎不变），图 2、图 3 = 参考图；只在涂抹范围里重画（降噪 1.0），再拼回原图。
    edge（2026-11-16 用户：边上有锯齿、接缝接不上、里面的皮肤和外面不一样；默认 EDGE_DEFAULT）：
      'hard' = 只把涂抹的地方涂灰（裁剪节点给的遮罩已经外扩 32 像素再羽化：外面那圈好好的皮肤也被半涂灰、重新画）；
      'dd'   = Differential Diffusion（ComfyUI 自带）：羽化的那圈按深浅逐步重画，边缘渐变过渡，不是 8 像素一格的硬边
    grow：遮罩先外扩多少像素（auto_grow 算）。用 ComfyUI 自带的 GrowMask（方形核，一圈一像素）：
      裁剪节点的 mask_expand_pixels 不是真的像素数（核大小 = ceil(N/4×1.5+1)，填 32 只外扩约 6 像素，2026-11-16 实测出图边上又有印子）"""
    res = st['res']
    wf = {}
    _base(wf, key, loras, te)
    wf['T'] = {'class_type': 'LoadImage', 'inputs': {'image': src}}
    wf['M'] = {'class_type': 'LoadImage', 'inputs': {'image': mask}}
    wf['mk'] = {'class_type': 'ImageToMask', 'inputs': {'image': ['M', 0], 'channel': 'red'}}
    mk = ['mk', 0]
    if grow:
        wf['gw'] = {'class_type': 'GrowMask', 'inputs': {'mask': mk, 'expand': int(grow), 'tapered_corners': False}}
        mk = ['gw', 0]
    wf['cr'] = {'class_type': 'InpaintCropImproved', 'inputs': {
        'image': ['T', 0], 'mask': mk, 'downscale_algorithm': 'lanczos', 'upscale_algorithm': 'lanczos', 'preresize': False,
        'preresize_mode': 'ensure minimum resolution', 'preresize_min_width': 1024, 'preresize_min_height': 1024, 'preresize_max_width': 16384, 'preresize_max_height': 16384,
        'mask_fill_holes': True, 'mask_expand_pixels': 0, 'mask_invert': False, 'mask_blend_pixels': 8 if 'b8' in edge else 32, 'mask_hipass_filter': 0.1, 'extend_for_outpainting': False,
        'extend_up_factor': 1.0, 'extend_down_factor': 1.0, 'extend_left_factor': 1.0, 'extend_right_factor': 1.0, 'context_from_mask_extend_factor': st['crop'],
        'output_resize_to_target_size': True, 'output_target_width': res, 'output_target_height': res, 'output_padding': '32', 'device_mode': 'gpu (much faster)'}}
    ref1 = ['cr', 1]
    if grey:
        wf['g'] = {'class_type': 'EmptyImage', 'inputs': {'width': res, 'height': res, 'batch_size': 1, 'color': 0x808080}}
        gmask = ['cr', 2]
        if 'hard' in edge:  # 外扩 32、羽化 σ16 的遮罩：≥0.97 的地方约等于原来涂抹的范围
            wf['hm'] = {'class_type': 'ThresholdMask', 'inputs': {'mask': ['cr', 2], 'value': 0.97}}
            gmask = ['hm', 0]
        wf['gm'] = {'class_type': 'ImageCompositeMasked', 'inputs': {'destination': ['cr', 1], 'source': ['g', 0], 'x': 0, 'y': 0, 'resize_source': True, 'mask': gmask}}
        ref1 = ['gm', 0]
    imgs = {'images.image_1': ref1, **_refs(wf, refs, first=2)}
    wf['e'] = {'class_type': 'TextEncodeQwenImage21', 'inputs': {'clip': ['c', 0], 'prompt': prompt, 'negative_prompt': '', 'resolution': res, 'vae': ['v', 0], **imgs}}
    wf['ve'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['cr', 1], 'vae': ['v', 0]}}
    wf['nm'] = {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': ['ve', 0], 'mask': ['cr', 2]}}
    model = ['cache', 0]
    if 'dd' in edge:
        wf['dd'] = {'class_type': 'DifferentialDiffusion', 'inputs': {'model': ['cache', 0], 'strength': 1.0}}
        model = ['dd', 0]
    wf['k'] = {'class_type': 'KSampler', 'inputs': {'model': model, 'positive': ['e', 0], 'negative': ['e', 1], 'latent_image': ['nm', 0], 'seed': seed % (2 ** 63),
                                                   'steps': st['steps'], 'cfg': st.get('cfg', 1.0), 'sampler_name': st['sampler'], 'scheduler': st['scheduler'], 'denoise': st['denoise']}}
    wf['d'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k', 0], 'vae': ['v', 0]}}
    wf['sti'] = {'class_type': 'InpaintStitchImproved', 'inputs': {'stitcher': ['cr', 0], 'inpainted_image': ['d', 0]}}
    wf['o'] = {'class_type': 'SaveImage', 'inputs': {'images': ['sti', 0], 'filename_prefix': prefix}}
    if 'dbg' in edge:  # 测试用：另存拼回之前的三张（画出来的裁剪图、原图裁剪、裁剪处的遮罩），在 ComfyUI 的输出文件夹里
        wf['dbg_mi'] = {'class_type': 'MaskToImage', 'inputs': {'mask': ['cr', 2]}}
        for k, src_ in (('d', ['d', 0]), ('o', ['cr', 1]), ('m', ['dbg_mi', 0])):
            wf['dbg_' + k] = {'class_type': 'SaveImage', 'inputs': {'images': src_, 'filename_prefix': prefix + '_dbg' + k}}
    return wf


# ---------------------------------------------------------------- 提示词增强
_REFUSE = re.compile(r"I\s+(?:can(?:no|')t|won't|am unable)|cannot (?:fulfill|assist|help|include|describe)|unable to (?:fulfill|comply)|无法(?:满足|完成|提供|生成)|不能(?:满足|提供|生成)|抱歉"
                     # 官方增强的另几种拒绝写法（“我不能执行这条编辑指令”“无法按照……进行改写”“无法将图中人物编辑为……”）：以前没认出来，拒绝的话被当成提示词去生成（A/B 11-15）
                     r"|(?:不能|无法|不会)(?:执行|按照|将|对|把|为|帮|进行|处理|实现)|一律拒绝|拒绝(?:执行|生成|处理|这|该|此)|cannot be (?:executed|performed)|(?:can't|cannot|won't) (?:edit|generate|create|produce)", re.I)


def parse_enhanced(raw):
    """增强节点输出多半是 JSON（rewritten_prompt）；返回 (正文, 问题)。问题：'' = 正常；'refused' = 拒绝；'junk' = 乱码"""
    s = (raw or '').strip()
    try:
        d = json.loads(s)
        if isinstance(d, dict):  # 官方多半是 rewritten_prompt；偶尔换个键（rewritten_instruction / output / 答案……）：取最长的那段文字
            vs = [v for v in d.values() if isinstance(v, str)]
            s = str(d.get('rewritten_prompt') or d.get('prompt') or (max(vs, key=len) if vs else s))
    except ValueError:
        m = (re.search(r'"rewritten_prompt"\s*:\s*"(.*?)"\s*,\s*"', s, re.S)
             or re.match(r'\{\s*"[^"]{1,40}"\s*:\s*"(.*?)(?:"\s*[,}].*)?$', s, re.S))  # 没写完或多了东西的 JSON：取第一个值
        if m:
            s = m.group(1).replace('\\n', '\n').replace('\\"', '"')
    s = s.strip()
    if len(s) > 2 and s[0] in '"“「' and s[-1] in '"”」':  # 小模型有时把整段用引号包起来（2026-11-06）
        s = s[1:-1].strip()
    if _REFUSE.search(s[:300]):
        return s, 'refused'
    if len(re.findall(r'[一-鿿]|[A-Za-z]{2,}', s)) < 20 or s.count('"') > len(s) / 10:
        return s, 'junk'
    return s, ''


# 开了“强调主要改动”（j['emph']，默认关）时：主要改动写在指令的最前面和最后面，并让 AI 助手额外写一行“主要改动：”
# 助手直接写（或增强拒绝时）用官方增强的整份系统指令（workflows/q21_pe_*.txt）
AI_I2I_DETAIL = ('\n改图时，要改成的新内容一定写具体、写满：衣服写颜色、材质、款式、剪裁、细节和穿在身上的样子（贴身还是宽松、长度、露出哪里）；'
                 '姿势写四肢、手的位置和重心；新加的物品写大小、位置和与人物的接触。用户只给了大致方向时，替他选定一个具体、好看的方案写出来。正文约 300~500 字。')  # 2026-11-15 用户：改图写得太短、没细节
EMPH_ADD_AI = ('\n\nAfter the description, on a new last line, write 「主要改动：」 followed by one or two plain sentences stating only the requested change itself '
               "(physically plausible; for left/right use the person's own side and note which side of the frame it is on).")
EMPH_ADD = ('\n4. 最后另起一行，以「主要改动：」开头，用一两句话写出这次要改的内容本身（不写保持不变的部分）：直白、具体，'
            '符合真实的物理（比如衣服被拉动时，周围的布料也跟着移动）；说到左右时按人物自己的左右写，并在括号里注明在画面的哪一边（人物的左侧在画面右侧）。')
# 2026-11-16 用户：局部重画时 AI 助手照官方改图的写法，写了一大段涂抹以外的东西（保持姿势、脸、背景……），
# 字数被占掉、涂抹区域反而写得少，还要手动删。局部重画单独一套：只写灰色区域里画什么 + 一两句衔接（局部重画的通常写法，ComfyUI / Flux Fill 社区都这么写）
AI_INPAINT = (
    '你为 Qwen-Image 2.1 的「局部重画」写一条指令。工作方式：程序把用户涂抹的区域连同周围一圈裁出来作为图 1，涂抹的部分涂成灰色；'
    '模型只重画灰色区域，灰色以外的部分原样保留、再拼回原图。所以：\n'
    '1. 只写灰色区域里要画成什么。不写、也不要求保持涂抹以外的任何东西（脸、发型、姿势、身材、背景、构图、光线都会自动保留，写了只占篇幅）。\n'
    '2. 固定以「将图1中的灰色区域重画为」开头，后面直接写内容。\n'
    '3. 把这一块写具体、写满：是什么，形状、大小和位置（在身体或画面的哪个部位），颜色，材质和质感，细节（褶皱、纹理、边缘、透明度、高光），'
    '和身体或物体怎么贴合（贴身还是宽松、垂下还是绷紧、遮住哪里、露出哪里）。用户只给了大致方向时，替他选定一个具体、好看的方案写出来。\n'
    '4. 最后用一两句写和周围的衔接：与相邻的皮肤肤色、光线方向和明暗、透视角度、清晰度一致，边缘自然过渡。只写衔接，不写别处的内容。\n'
    '5. 用户提到图 2、图 3（参考图）时，写明取参考图里的哪样东西（例如「图2中那件上衣的颜色、面料和款式」），按图号称呼。\n'
    '6. 附图里第一张是原图：红线（外侧一圈白边）圈住的范围就是要重画的区域，用它判断这块在身体的哪个部位、周围是什么；'
    '线只是标记，范围里的颜色就是原图本来的颜色；不要描述这条线。\n'
    '7. 只输出指令正文：中文，一段话，约 80~220 字；不要标题、解释、JSON，不要「8K、杰作」之类的空词。')
# 2026-11-16 夜测（docs/AB测试/动作复刻_1116）：文生图时 AI 助手直接写（或官方增强拒绝时）不再照官方文生图增强的整份写法（英文、长、动作和视角常写错），
# 改用这份「动作拆开写」：机位（自拍才写自拍）→ 人物 → 朝向（「背对人群」= 人群在身后）→ 两只手分别写 → 衣着（按常理穿着）→ 环境 → 真实感；中文、200~350 字。
# 用户那句「前置自拍、背对人群」：原来的写法 Qwen / MOSS 都画成手里拿着手机，这份能画成真正的前置自拍；普通题不比原来差
AI_T2I = (
    '你为文生图模型写一段画面描述。用户的原话通常很短，但里面的动作、手和拍摄视角常常很具体——模型最容易画错的正是这些。你要把它写成模型能逐项照做的描述。\n'
    '按下面的顺序写成一段连续的话（不分条、不加标题）：\n'
    '1. 照片类型与机位：谁在拍、用什么拍——用户说了自拍才写自拍（前置摄像头自拍 / 对镜自拍）；用户没说自拍时就写“旁人拍摄的照片”，人物双手空着；这时整段都不要出现“手机”两个字（写了模型会把手机画进画面），站在镜子前也不等于对镜自拍；镜头离身体多远、从什么角度（平视、俯拍、仰拍），取景到哪里（头到腰 / 全身），竖幅。前置自拍要写明：手机就在镜头的位置（画面里只看得到举手机的手臂），举手机的那只手臂伸向镜头、前臂出现在画面边缘，脸离镜头近、有一点广角透视；对镜自拍要写明手机出现在镜子里。\n'
    '2. 人物：明确成年（例如二十岁出头），民族与长相、发型发色、身材、表情和视线（看镜头 / 看手机屏幕 / 回头看）。\n'
    '3. 身体朝向与姿势：先判断人物朝着哪里——用户说“背对着某样东西”（人群、大海、窗户……）是指那样东西在人物身后，人物本身面向镜头；只有用户明确说“背对镜头 / 背影 / 回头看”时才写背对镜头。自拍时人物面向镜头。再写头转向哪边，站、坐还是跪，重心在哪。\n'
    '4. 两只手分开写：每只手写明是人物自己的左手还是右手（括号里注明在画面的哪一侧），在什么位置、碰到什么、手指怎么摆（几根手指、伸进 / 捏住 / 拉下 / 撩起、往哪个方向用力），以及对衣物造成的结果（布料被拉低多少、哪里绷紧、哪里起皱）。同一只手只做一件事：举手机的手不能同时去拉衣服。\n'
    '5. 衣着：每件衣物的颜色、材质、款式，按场景的常理穿着并写出来。\n'
    '6. 环境与光线：在哪里、背景里有什么（人群、街道、家具……）、远近和虚化、时间和光从哪边来。\n'
    '7. 真实感：原相机直出的照片质感，轻微噪点和自然的皮肤纹理。\n'
    '规则：只写画面里看得到的东西，全部用肯定的说法写；用户原话里的每个动作都要写到，不加用户没说的动作；不写“8K、杰作”之类的空词。只输出描述正文，约 200~350 字。')
_LR = re.compile(r'[左右]')


def _mask_preview(src, mask, side=1280):
    """给 AI 助手看的原图：沿涂抹范围的边缘画一圈红线、外侧一圈白边（助手原来只看到原图，不知道涂了哪里）。
    2026-11-16 用户：原来整块盖半透明红色，整件衣服都涂上时助手把衣服写成“粉色衣服”——范围里要保持原图的颜色，只描边"""
    from PIL import Image, ImageChops, ImageFilter
    im = Image.open(src).convert('RGB'); im.thumbnail((side, side))
    m = Image.open(mask).convert('L').resize(im.size).point(lambda v: 255 if v > 127 else 0)
    k = max(5, round(max(im.size) / 200)) | 1  # 线宽：长边 1280 时约 6 像素（滤波核要奇数）
    out = m.filter(ImageFilter.MaxFilter(k))
    im.paste((255, 255, 255), mask=ImageChops.subtract(m.filter(ImageFilter.MaxFilter(k + 6)), out))  # 白边：红色衣服 / 皮肤上也看得清
    im.paste((255, 30, 50), mask=ImageChops.subtract(out, m.filter(ImageFilter.MinFilter(k))))
    b = io.BytesIO(); im.save(b, 'JPEG', quality=90)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


def _emph(prompt, main):
    main = (main or '').strip().rstrip('。.')
    if not main:
        return prompt
    if _LR.search(main) and '画面' not in main:
        main += '（这里说的左右都是人物自己的左右：人物的左侧在画面右侧，右侧在画面左侧）'
    return f'主要改动（一定要做到）：{main}。\n{prompt.strip()}\n再次强调主要改动：{main}。'


def _data_url(path, side=1280):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    im.thumbnail((side, side))
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=90)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


# ---------------------------------------------------------------- 后台记录（提示词增强 / AI 助手里直接用小模型）
LOG_DIR = None   # 由 imagegen 设：LOG_DIR(sp) → 这个空间的图片文件夹（私密空间的记录存在私密空间里）
LOG_MAX = 200
_log_lock = threading.Lock()


def _log_file(sp):
    return os.path.join(LOG_DIR(sp), 'q21-prompt-log.jsonl') if LOG_DIR else None


def _thumb(path, side=240):
    try:
        from PIL import Image
        im = Image.open(path).convert('RGB'); im.thumbnail((side, side))
        b = io.BytesIO(); im.save(b, 'JPEG', quality=80)
        return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


def log_add(sp, rec):
    fp = _log_file(sp)
    if not fp:
        return
    rec = {'id': uuid.uuid4().hex[:10], 'time': time.time(), **rec}
    with _log_lock:
        try:
            rows = read_log(sp, raw=True)
            rows.append(json.dumps(rec, ensure_ascii=False))
            with open(fp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(rows[-LOG_MAX:]) + '\n')
        except OSError:
            pass


def read_log(sp, raw=False):
    fp = _log_file(sp)
    if not fp or not os.path.isfile(fp):
        return []
    with open(fp, encoding='utf-8') as f:
        rows = [ln.strip() for ln in f if ln.strip()]
    if raw:
        return rows
    out = []
    for ln in rows:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out[::-1]


def _rid(ln):
    try:
        return json.loads(ln).get('id')
    except (ValueError, AttributeError):
        return None


def clear_log(sp, rid=None):
    fp = _log_file(sp)
    if not fp or not os.path.isfile(fp):
        return
    with _log_lock:
        if rid:
            rows = [ln for ln in read_log(sp, raw=True) if _rid(ln) != rid]  # 坏掉的行留着、不挡着删别的（以前一行坏了就删不掉单条，2026-11-16 审查）
            with open(fp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(rows) + ('\n' if rows else ''))
        else:
            os.remove(fp)


# ---------------------------------------------------------------- 跑任务
class Cancelled(Exception):
    pass


def _submit(j, wf, label):
    """提交一个工作流、等完成（取消时中断 ComfyUI），进度写进 j；返回 history 里的 outputs"""
    cid = uuid.uuid4().hex
    done = {'v': False}
    cur = {'cls': ''}

    def on_msg(msg):
        if msg.get('type') == 'progress':
            d = msg.get('data') or {}
            if cur['cls'] in ('KSampler', 'KSamplerAdvanced'):  # 二采用的是 KSamplerAdvanced（审查 16）
                j['step'], j['total'] = d.get('value', 0), max(1, d.get('max', 1))
                j['message'] = f"{label} · 第 {j['step']}/{j['total']} 步"
        elif msg.get('type') == 'executing' and (msg.get('data') or {}).get('node'):
            cls = cur['cls'] = wf.get(str(msg['data']['node']), {}).get('class_type', '')
            if cls == 'TextGenerate':
                j['message'] = '正在增强提示词…'
            elif 'Loader' in cls:
                j['message'] = '正在载入模型…'
            elif cls == 'VAEDecode':
                j['message'] = '正在解码…'
            elif cls.startswith('Inpaint'):
                j['message'] = '正在裁剪 / 拼回涂抹区域…'
    th = threading.Thread(target=V._ws_progress, args=(cid, on_msg, lambda: done['v']), daemon=True)
    th.start()
    try:
        pid = None
        pid = V._submit(wf, cid)  # 编号自己定：引擎忙时提交超时也认得出（2026-11-12，见 videogen._submit）
        last_int, t0, hst = 0.0, time.time(), {}
        while True:
            time.sleep(1)
            V.Engine.last = time.time()
            if j['cancel'] and time.time() - last_int > 5:
                last_int = time.time()
                try:
                    V._http('/interrupt', {}, timeout=5)
                except Exception:
                    pass
            hist = V._history(pid, hst)  # 引擎忙得回不了话：None，接着等
            if isinstance(hist, dict) and pid in hist:
                st = hist[pid].get('status') or {}
                if j['cancel']:
                    raise Cancelled
                if st.get('status_str') == 'error' or (st.get('completed') is False):
                    err = next((x[1] for x in st.get('messages', []) if x[0] == 'execution_error'), {}) or {}
                    raise RuntimeError(V._friendly(str(err.get('exception_message') or 'ComfyUI 报错')))
                if st.get('completed'):
                    return hist[pid].get('outputs') or {}
            if time.time() - t0 > 1800:
                raise RuntimeError('超过 30 分钟仍未完成，已放弃')
    except Cancelled:
        raise
    except Exception:
        V._drop(pid)  # 这边判失败了：引擎里这一单也取消，不在后台白跑
        raise
    finally:
        done['v'] = True


def _enhance(j, kind, names, prompt, seed, system=None):
    outs = _submit(j, wf_enhance(kind, names, prompt, seed, system, pe_name(j, kind)), '增强提示词')
    t = (outs.get('pv') or {}).get('text')
    return (t[0] if isinstance(t, list) and t else t) or ''


def prepare_prompt(j, kind, mode, names, work_in, hooks, source):
    """提示词增强（j['enhance'] 见 ENHANCE）。返回 (最终提示词, 说明, 增强后的原文)，并记一条后台记录。
    要 AI 助手的几档（WITH_AI）临时还显卡锁（本地 AI 助手要用显卡），用完再拿回来"""
    user, enh, note, t0 = j['prompt'], j.get('enhance') or 'off', '', time.time()
    if enh == 'ai':  # AI 助手直接写：不跑增强小模型
        raw, enh_text, bad = '', '', 'skipped'
    else:
        raw = _enhance(j, kind, names, user, j['seed'])
        enh_text, bad = parse_enhanced(raw)
    pe_nm = '官方增强'
    rec = {'source': source, 'model': j.get('model_name') or j.get('model'), 'mode': mode, 'enhance': enh, 'user': user, 'pe_kind': kind,
           'pe_raw': raw, 'pe_text': enh_text, 'pe_bad': bad, 'pe_sec': round(time.time() - t0, 1),
           'images': [x for x in (_thumb(os.path.join(work_in, n)) for n in names[:3]) if x]}
    prompt = user
    emph = bool(j.get('emph')) and mode in ('edit', 'inpaint')
    if enh not in WITH_AI:  # pe：只用增强小模型
        if bad:
            note = pe_nm + ('拒绝了这个请求' if bad == 'refused' else '输出了乱码') + '，已按原话生成（可改用「助手」）'
        else:
            prompt = _emph(enh_text, user) if emph else enh_text
    else:  # 本地 AI 助手（ai）：看图自己写。它要用显卡：先把 ComfyUI 的显存放掉、把锁还回去
        if not CHAT:
            raise RuntimeError('后台版本过旧：缺少 AI 助手接口，请重启 Studio')
        V.Engine.free(keep_ram=True)
        hooks['release']()
        t1 = time.time()
        try:
            j['message'] = '正在用 AI 助手写提示词（首次需载入约 10~30 秒）…'
            task = ('文生图' if mode == 'txt' else f'改图，共 {len(names)} 张图（按顺序是图 1' + ''.join(f'、图 {i}' for i in range(2, len(names) + 1)) + '）'
                    + ('；局部重画：图 1 的涂抹区域会被重画' if mode == 'inpaint' else ''))
            imgs = [_data_url(os.path.join(work_in, n)) for n in names[:3]]
            mk = j.get('_mask_path') if mode == 'inpaint' else None
            if mk and names and os.path.isfile(mk):  # 局部重画：原图上用红线圈出涂抹的地方给助手看
                try:
                    imgs[0] = _mask_preview(os.path.join(work_in, names[0]), mk)
                except Exception:
                    pass
            if mode == 'inpaint':  # 局部重画单独一套（2026-11-16）：只写灰色区域画什么 + 衔接；增强写好了的，当参考材料给它
                sysm = tplstore.T('IMG_AI_INPAINT') + (EMPH_ADD if emph else '')
                msg = (f'【任务】局部重画，共 {len(names)} 张图：图 1 是原图（红线圈住的 = 涂抹要重画的区域）'
                       + ''.join(f'，图 {i} 是参考图' for i in range(2, len(names) + 1)) + f'\n\n【用户原话】\n{user}'
                       + (f'\n\n【增强小模型写的指令（只作参考：取其中关于涂抹区域的细节，涂抹以外的内容和保持项都不要）】\n{enh_text}' if not bad and enh_text else ''))
            elif kind == 't2i':  # 文生图：系统指令「文生图 · 助手直接写」，默认 = 官方增强的整份系统指令；另一个版本「动作拆开写」
                sysm = tplstore.T('IMG_AI_T2I') + (EMPH_ADD_AI if emph else '')
                msg = f'[Task] {task}\n\n{user}'
                cur = tplstore.get(tplstore.space())
                ver = cur['vers'].get('img_ai_t2i') or {}
                if ver.get('own') or ver.get('id'):  # 不是默认的版本：记下来（详情、后台记录里看得到）
                    j['enh_ver'] = rec['enh_ver'] = cur['name'] if ver.get('own') else ver.get('label')
            else:  # 改图：照官方增强的整份系统指令写（2026-11-15 用户：助手写得太短、没细节）
                sysm = _system(kind) + (AI_I2I_DETAIL if kind == 'i2i' else '') + (EMPH_ADD_AI if emph else '')
                msg = (f'[Task] {task}' + ('；局部重画：只写涂抹区域里要画成什么，以及和周围衔接（姿势、肤色、光线一致），不写涂抹区域以外的保持项' if mode == 'inpaint' else '')
                       + f'\n\n{user}')
            rest = (CHAT(sysm, msg, imgs) or '').strip()
            if rest.lstrip().startswith('{'):
                rest = parse_enhanced(rest)[0]  # 照官方写法时偶尔包成 JSON：取正文
        finally:
            if RELEASE:
                try:
                    RELEASE()
                except Exception:
                    pass
            if not hooks['take']():
                raise Cancelled
        rec.update(rs_system=sysm, rs_input=msg, rs_text=rest, rs_sec=round(time.time() - t1, 1))
        if len(rest) < 8:
            log_add(j['space'], {**rec, 'final': '', 'note': 'AI 助手没有写出指令'})
            raise RuntimeError('AI 助手没有写出指令，请重试，或把提示词增强改为「关」')
        if mode == 'inpaint' and '灰色' not in rest:  # 没写明重画灰色区域时模型会把灰色照抄下来（夜间测试 11-11）：补上开头那句
            rest = INPAINT_LEAD + rest
        prompt = rest
        if emph:  # AI 助手写的“主要改动：”那一行拿出来，放到最前面和最后面（没写就用用户原话）
            m = re.search(r'(?:^|\n)\s*主要改动[:：]\s*(.+?)\s*$', rest, re.S)
            prompt = _emph(rest[:m.start()] if m else rest, m.group(1) if m else user)
        if bad and bad != 'skipped':
            note = pe_nm + ('拒绝了这个请求' if bad == 'refused' else '输出了乱码') + '，指令由 AI 助手看图写'
    log_add(j['space'], {**rec, 'final': prompt, 'note': note})
    return prompt, note, enh_text


def _inputs(j, tag, work_in, made):
    """把任务里的图（原图、参考图、遮罩）写进 ComfyUI 的输入文件夹：返回 (图名列表, 遮罩名, 原图尺寸)"""
    from PIL import Image

    def put(b64, name):
        p = os.path.join(work_in, f'studio_{tag}_{name}.png')
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') and name != 'mask' else 'RGB')
        im.save(p, 'PNG')
        made.append(p)
        return os.path.basename(p), im.size
    names, size0 = [], None
    if j['mode'] != 'txt':
        n, size0 = put(j['_init'], 'src')
        names.append(n)
        for k, r in enumerate(j.get('_refs') or []):
            names.append(put(r, f'ref{k + 2}')[0])
    mask = put(j['_mask'], 'mask')[0] if j['mode'] == 'inpaint' else None
    return names, mask, size0


def preview(j, hooks):
    """生图页的“先增强”：只增强，不出图。返回 {'prompt', 'note'}（显卡锁由调用方拿着）"""
    tag = 'q21p_' + uuid.uuid4().hex[:8]
    work_in = os.path.join(V.WORK['n'], 'in'); os.makedirs(work_in, exist_ok=True)
    made = []
    try:
        V.Engine.cancel_later()
        kind = 't2i' if j['mode'] == 'txt' else 'i2i'
        if j.get('enhance') != 'ai':  # 助手直接写：用不到 ComfyUI，不启动
            V.Engine.ensure()
            if not pe_ok(kind, pe_set(j)):
                raise RuntimeError('没有提示词增强模型（ComfyUI/models/text_encoders/' + pe_name(j, kind).replace('\\', '/') + '）')
        names, _m, _s = _inputs(j, tag, work_in, made)
        j['_mask_path'] = os.path.join(work_in, _m) if _m else None  # 局部重画：给 AI 助手看涂了哪里
        prompt, note, _e = prepare_prompt(j, kind, j['mode'], names, work_in, hooks, '先增强')
        return {'prompt': prompt, 'note': note}
    finally:
        for f in made:
            try:
                os.remove(f)
            except OSError:
                pass
        V.Engine.free_later()


def pe_chat(kind, system, text, images, sp, seed=None):
    """AI 助手里直接和官方增强小模型对话（单轮）：images = data URL 列表。返回小模型的原话（显卡锁由调用方拿着）"""
    tag = 'q21c_' + uuid.uuid4().hex[:8]
    work_in = os.path.join(V.WORK['n'], 'in'); os.makedirs(work_in, exist_ok=True)
    made, names = [], []
    try:
        if not pe_ok(kind):
            raise RuntimeError('没有提示词增强模型（ComfyUI/models/text_encoders/' + PE[kind].replace('\\', '/') + '）')
        V.Engine.cancel_later()
        V.Engine.ensure()
        from PIL import Image
        for k, u in enumerate((images or [])[:3]):
            try:
                im = Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert('RGB')
            except Exception:
                continue
            p = os.path.join(work_in, f'studio_{tag}_{k}.png'); im.save(p, 'PNG'); made.append(p); names.append(os.path.basename(p))
        j = {'cancel': False, 'message': '', 'step': 0, 'total': 0}
        t0 = time.time()
        raw = _enhance(j, kind, names, text, seed if seed is not None else random.randint(0, 2 ** 31 - 1), system)
        log_add(sp, {'source': 'AI 助手', 'model': '官方增强小模型（' + ('改图' if kind == 'i2i' else '文生图') + '）', 'mode': kind, 'enhance': 'chat', 'user': text,
                     'pe_kind': kind, 'pe_system': system if system != _system(kind) else None, 'pe_raw': raw, 'pe_text': parse_enhanced(raw)[0],
                     'pe_bad': parse_enhanced(raw)[1], 'pe_sec': round(time.time() - t0, 1), 'images': [x for x in (_thumb(f) for f in made) if x], 'final': ''})
        return raw
    finally:
        for f in made:
            try:
                os.remove(f)
            except OSError:
                pass
        V.Engine.free_later()


_SAM_IMG = {}  # 智能选取用的原图：网页给的 key → (ComfyUI 输入文件夹里的文件名, 宽, 高)；同一张图连点几下不用每次重传
SAM_SIDE = 1536  # 送给 SAM3 的图最长边（它内部按 1008 算，再大没用、只是传得慢）


class NeedImage(Exception):
    """这张图还没传过（或已清掉）：网页要带上图再请求一次"""


# 2026-11-17 审查 F03：智能选取的原图以前一律存在普通空间的 ComfyUI 输入文件夹里（私密空间的图也是），最多留 4 张、一直不删；
# 同一个 key 换图时旧文件的记录被覆盖、文件永远留着。现在：
# - 私密空间的原图放在私密空间自己的临时文件夹（WORK['v']/sam），每次交给 ComfyUI 时临时复制进输入文件夹、用完立刻删
# - 换图 / 淘汰时删掉旧文件；正在被 SAM 用着的文件等用完再删
# - 私密空间退出（没有私密会话了）时私密的全部清掉；Studio 启动时清掉上次留下的
_SAM_LOCK = threading.RLock()
_SAM_BUSY = {}    # 正在被 ComfyUI 读的文件（绝对路径）→ 次数
_SAM_DROP = set()  # 等用完再删的
SAM_KEEP = 4


def _sam_sp(key):
    return 'v' if str(key).startswith('v:') else 'n'


def _sam_dir(sp):
    d = os.path.join(V.WORK['v'], 'sam') if sp == 'v' else os.path.join(V.WORK['n'], 'in')
    os.makedirs(d, exist_ok=True)
    return d


def _sam_rm(path):
    with _SAM_LOCK:
        if _SAM_BUSY.get(path):
            _SAM_DROP.add(path); return
        _SAM_DROP.discard(path)
    try:
        os.remove(path)
    except OSError:
        pass


def _sam_forget(key):
    with _SAM_LOCK:
        old = _SAM_IMG.pop(key, None)
        _SAM_PART.pop(key, None)
    if old:
        _sam_rm(old[3])


def sam_put(key, b64):
    """存下智能选取用的原图（缩到最长边 SAM_SIDE），最多留 4 张；返回 (文件名, 宽, 高, 路径)"""
    from PIL import Image
    sp = _sam_sp(key)
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    im.thumbnail((SAM_SIDE, SAM_SIDE))
    name = 'studio_sam_' + uuid.uuid4().hex[:10] + '.png'
    path = os.path.join(_sam_dir(sp), name)
    im.save(path, 'PNG')
    with _SAM_LOCK:
        _sam_forget(key)  # 同一个 key 换了图：旧文件删掉、旧部件作废
        _SAM_IMG[key] = (name, im.width, im.height, path)
        while len(_SAM_IMG) > SAM_KEEP:  # 只留最近 4 张，删掉自己放进去的旧文件
            _sam_forget(next(iter(_SAM_IMG)))
        return _SAM_IMG[key]


def sam_forget_space(sp):
    """私密空间退出时：私密的原图、部件全部清掉"""
    with _SAM_LOCK:
        for k in [k for k in _SAM_IMG if _sam_sp(k) == sp]:
            _sam_forget(k)
        for k in [k for k in _SAM_PART if _sam_sp(k) == sp]:
            _SAM_PART.pop(k, None)


def sam_purge():
    """Studio 启动时：上次留下的智能选取原图（内存里的记录已经没了，再也用不到）删掉"""
    for sp in ('n', 'v'):
        d = os.path.join(V.WORK['v'], 'sam') if sp == 'v' else os.path.join(V.WORK['n'], 'in')
        for f in os.listdir(d) if os.path.isdir(d) else []:
            if f.startswith(('studio_sam_', 'studio_samv_')):
                try:
                    os.remove(os.path.join(d, f))
                except OSError:
                    pass


class _sam_staged:
    """交给 ComfyUI 的文件名：普通空间直接用（用着时不删）；私密空间的临时复制进输入文件夹，用完立刻删"""
    def __init__(self, ent):
        self.path = ent[3]
        self.copy = None

    def __enter__(self):
        import shutil
        with _SAM_LOCK:
            _SAM_BUSY[self.path] = _SAM_BUSY.get(self.path, 0) + 1
        work_in = _sam_dir('n')
        if os.path.normcase(os.path.dirname(self.path)) == os.path.normcase(work_in):
            return os.path.basename(self.path)
        name = 'studio_samv_' + uuid.uuid4().hex[:10] + '.png'
        self.copy = os.path.join(work_in, name)
        shutil.copyfile(self.path, self.copy)
        return name

    def __exit__(self, *a):
        if self.copy:
            try:
                os.remove(self.copy)
            except OSError:
                pass
        with _SAM_LOCK:
            n = _SAM_BUSY.get(self.path, 1) - 1
            if n <= 0:
                _SAM_BUSY.pop(self.path, None)
            else:
                _SAM_BUSY[self.path] = n
            drop = n <= 0 and self.path in _SAM_DROP
        if drop:
            _sam_rm(self.path)


def wf_sam_point(img_name, x, y, prefix):
    """SAM3 点选（ComfyUI 原生 SAM3_Detect 的点提示：走 SAM 解码器，自带两轮细化）：返回整块物体的遮罩（白 = 选中）"""
    return {'l': {'class_type': 'LoadImage', 'inputs': {'image': img_name}},
            's': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM}},
            'p': {'class_type': 'PrimitiveString', 'inputs': {'value': json.dumps([{'x': int(x), 'y': int(y)}])}},
            'd': {'class_type': 'SAM3_Detect', 'inputs': {'model': ['s', 0], 'image': ['l', 0], 'positive_coords': ['p', 0], 'threshold': 0.5,
                                                         'refine_iterations': 2, 'individual_masks': False}},
            'mi': {'class_type': 'MaskToImage', 'inputs': {'mask': ['d', 0]}},
            'mo': {'class_type': 'SaveImage', 'inputs': {'images': ['mi', 0], 'filename_prefix': prefix}}}


# 先按这些类别把图里的“部件”都找出来（一张图只找一次、存着），点的时候取包含这一点的最小的那块：点毛衣只选毛衣，点头发只选头发。
# 只用一个点时 SAM 默认给最大的那个物体（点毛衣会选中整个人）——同一处再点一下才放大到整个物体（Photoshop「对象选择」的做法）
SAM_PARTS = 'clothing:6, hair:2, face:2, hand:4, shoes:2, bag:2, hat:2, glasses:2'
_SAM_PART = {}  # key → [遮罩（numpy bool，SAM_SIDE 尺寸）, ...]


def _sam_run(wf, prefix):
    """提交一个 SAM3 工作流，返回保存下来的遮罩（numpy bool 列表，用完删文件）"""
    import numpy as np
    from PIL import Image
    work_out = os.path.join(V.WORK['n'], 'out')
    pid, t0, hst = V._submit(wf, uuid.uuid4().hex), time.time(), {}
    while True:
        time.sleep(0.12)  # 点一下就要出结果：比生图那边（每秒一次）查得勤
        hist = V._history(pid, hst)
        if isinstance(hist, dict) and pid in hist:
            st = hist[pid].get('status') or {}
            if st.get('status_str') == 'error':
                err = next((m[1] for m in st.get('messages', []) if m[0] == 'execution_error'), {}) or {}
                raise RuntimeError(V._friendly(str(err.get('exception_message') or 'SAM3 报错')))
            if st.get('completed'):
                out = []
                for it in ((hist[pid].get('outputs') or {}).get('mo') or {}).get('images') or []:
                    fp = os.path.join(work_out, it.get('subfolder', ''), it['filename'])
                    try:
                        out.append(np.array(Image.open(fp).convert('L')) > 127)
                    finally:
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
                return out
        if time.time() - t0 > 180:
            V._drop(pid)
            raise RuntimeError('SAM3 超过 3 分钟没有结果')


def wf_sam_parts(img_name, prefix):
    """按 SAM_PARTS 找出图里的衣服、头发、脸、手……，每个一张遮罩"""
    return {'l': {'class_type': 'LoadImage', 'inputs': {'image': img_name}},
            's': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM}},
            't': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['s', 1], 'text': SAM_PARTS}},
            'd': {'class_type': 'SAM3_Detect', 'inputs': {'model': ['s', 0], 'image': ['l', 0], 'conditioning': ['t', 0], 'threshold': 0.4,
                                                         'refine_iterations': 2, 'individual_masks': True}},
            'mi': {'class_type': 'MaskToImage', 'inputs': {'mask': ['d', 0]}},
            'mo': {'class_type': 'SaveImage', 'inputs': {'images': ['mi', 0], 'filename_prefix': prefix}}}


def _sam_parts(key):
    """把这张图的部件找出来存着（显卡锁由调用方拿着）"""
    ent = _SAM_IMG[key]
    _, w, h, _ = ent
    V.Engine.ensure()
    with _sam_staged(ent) as name:
        parts = [m for m in _sam_run(wf_sam_parts(name, 'studio_samp_' + uuid.uuid4().hex[:8]), '') if m.shape == (h, w) and m.any()]
    if _SAM_IMG.get(key) is ent:  # 跑的时候图被换掉了：结果作废
        _SAM_PART[key] = parts
    for k2 in [k2 for k2 in _SAM_PART if k2 not in _SAM_IMG]:
        _SAM_PART.pop(k2, None)


def sam_prep(key, b64=None):
    """网页放了图、智能选取开着时先跑一遍（不用等第一次点）：存图 + 找部件。已经做过就直接返回"""
    if b64:
        sam_put(key, b64)
    ent = _SAM_IMG.get(key)
    if not ent or not os.path.isfile(ent[3]):
        raise NeedImage()
    if key not in _SAM_PART or b64:
        V.Engine.cancel_later()
        try:
            _sam_parts(key)
        finally:
            V.Engine.free_later()
    return {'ok': True, 'parts': len(_SAM_PART.get(key) or [])}


def sam_select(key, x, y, b64=None, level=0):
    """局部重画的「智能选取」（2026-11-16 用户）：在原图上点一下（x、y 是 0~1 的相对位置），返回 {'mask': PNG data URL, 'area': 占比, 'level', 'levels'}。
    候选 = 包含这一点的部件（小到大）+ 点选的整个物体；level 0 = 最小的，同一处再点一下（level + 1）= 大一圈。显卡锁由调用方拿着。图没传过时抛 NeedImage"""
    import numpy as np
    from PIL import Image
    if b64:
        sam_put(key, b64)
    ent = _SAM_IMG.get(key)
    if not ent or not os.path.isfile(ent[3]):
        raise NeedImage()
    _, w, h, _ = ent
    px, py = int(min(max(float(x), 0.0), 1.0) * (w - 1)), int(min(max(float(y), 0.0), 1.0) * (h - 1))
    V.Engine.cancel_later()
    try:
        if key not in _SAM_PART or b64:  # 这张图第一次点：先把部件都找出来（几秒），以后点别处就不用再跑（网页放图后会先 sam_prep 好）
            _sam_parts(key)
        cands = sorted((m for m in (_SAM_PART.get(key) or []) if m[py, px]), key=lambda m: int(m.sum()))
        level = max(0, int(level))
        pointed = level >= len(cands)
        if level >= len(cands):  # 部件里没有、或已经是最大的部件：用点选（整个物体）
            V.Engine.ensure()
            with _sam_staged(ent) as name:
                pm = _sam_run(wf_sam_point(name, px, py, 'studio_sam_' + uuid.uuid4().hex[:8]), '')
            pm = pm[0] if pm and pm[0].shape == (h, w) else None
            if pm is not None and pm.any() and not any((m & pm).sum() / max(1, (m | pm).sum()) > 0.9 for m in cands):  # 和已有的差不多就不另算一级
                cands.append(pm)
        if not cands:
            return {'mask': None, 'area': 0, 'level': 0, 'levels': 0}
        lv = min(level, len(cands) - 1)
        m = Image.fromarray((cands[lv] * 255).astype(np.uint8))
        b = io.BytesIO(); m.save(b, 'PNG')
        return {'mask': 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode(), 'area': round(float(cands[lv].mean()), 4), 'level': lv, 'levels': len(cands) + (0 if pointed else 1)}  # 还没点选过：可能还有更大的一级（整个物体）
    finally:
        V.Engine.free_later()


def run(j, hooks):
    """imagegen._run 拿着显卡锁时调用。hooks：save(img, ext, extra)、release()（还显卡锁）、take()（再拿，取消了返回 False）、
    want()（配音要用显卡了吗：是的话画完这张返回 'yield'）。
    j 里：model、mode（txt / edit / inpaint）、prompt、seed、count、width / height、_init、_refs、_mask、enhance、format、quality"""
    key, mode = j['model'], j['mode']
    st = dict(SETTINGS[key][mode])
    st.update(j.get('q_over') or {})  # 用户改过的几项（clean_over 已经检查过）
    if st.get('mp') == 'page':
        st['mp'] = None
    tag = 'q21_' + j['id'][-12:].replace('-', '')
    work_in, work_out = os.path.join(V.WORK['n'], 'in'), os.path.join(V.WORK['n'], 'out')
    os.makedirs(work_in, exist_ok=True); os.makedirs(work_out, exist_ok=True)
    made = []

    def put(b64, name):
        p = os.path.join(work_in, f'studio_{tag}_{name}.png')
        from PIL import Image
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') and name != 'mask' else 'RGB')
        im.save(p, 'PNG')
        made.append(p)
        return os.path.basename(p), im.size

    try:
        V.Engine.cancel_later()
        j['message'] = '正在启动 ComfyUI…'
        V.Engine.ensure()
        names, size0 = [], None
        if mode != 'txt':
            n, size0 = put(j['_init'], 'src')
            names.append(n)
            for k, r in enumerate(j.get('_refs') or []):
                names.append(put(r, f'ref{k + 2}')[0])
        mask = put(j['_mask'], 'mask')[0] if mode == 'inpaint' else None
        j['_mask_path'] = os.path.join(work_in, mask) if mask else None  # 局部重画：给 AI 助手看涂了哪里
        pose = mode == 'edit' and j.get('_pose')
        if j.get('ref_extract') and mode in ('edit', 'inpaint') and len(names) > 1 and not pose:  # 参考图先提取衣服（AI 助手写提示词时看到的也是提取后的）
            extract_refs(j, key, names, work_in, te_name(j))
        if pose:  # 3D 人偶摆姿势（Fisher）：人偶图当图 1，原图的人当图 2；出图比例默认跟人偶图
            pn, psize = put(j['_pose'], 'pose')
            names.insert(0, pn); size0 = psize
            st['steps'] = POSE_STEPS
        if mode == 'txt':
            w, h = size_for(st['mp'], j['width'], j['height'], 16) if st.get('mp') else (j['width'] // 16 * 16, j['height'] // 16 * 16)  # 按 16 对齐（和网页自定义尺寸一样；以前按 32，1040 会变成 1024）
        elif mode == 'edit':  # 默认和图 1 的宽高比一样；网页上自选了尺寸（size_free）时按那个比例
            w, h = size_for(st['mp'], *((j['width'], j['height']) if j.get('size_free') else size0), 16)
        else:
            w, h = size0
        user = j['prompt']
        prompt, enh, note = user, j.get('enhance') or 'off', ''
        if pose:  # 固定指令（LoRA 认这句）+ 用户补充的话；提示词增强不用（会把固定指令改掉）
            extra = pose_renumber(user.strip(), len(names) - 1) if user.strip() and user.strip() not in (POSE_PROMPT, pose_prompt()) else ''
            prompt = user = pose_prompt() + ('\n' + extra if extra else '')
            enh = 'off'
        kind = 't2i' if mode == 'txt' else 'i2i'
        if enh not in ('off', 'ai') and not pe_ok(kind, pe_set(j)):
            enh, note = 'off', '没有提示词增强模型，已按原话生成'
        enh_text = None
        if j.get('prompt_used'):  # 让过显卡（配音要用）之后接着画：提示词上次已经增强好了
            prompt, enh, note, enh_text = j['prompt_used'], j.get('enhance_used') or enh, j.get('enhance_note') or '', j.get('_enh_text')
        elif enh != 'off':
            prompt, note, enh_text = prepare_prompt(j, kind, mode, names, work_in, hooks, '生图')
            V.Engine.ensure()
        if mode == 'inpaint' and not j.get('prompt_used') and prompt.strip() == user.strip() and '灰色' not in prompt:
            prompt = INPAINT_LEAD + prompt  # 按原话画时：只写改动的话，模型会把涂成灰色的图 1 照抄下来（成品里一块灰），要写明重画灰色区域（夜间测试 11-11）
        j['prompt_used'], j['enhance_used'], j['enhance_note'], j['_enh_text'] = prompt, enh, note, enh_text
        if note:
            act(note, 'img', 'warn')
        j['total'] = st['steps']
        edge = tuple(j.get('inp_edge') or ())
        grow = auto_grow(j['_mask_path'], st) if mode == 'inpaint' and 'grow' in edge and j.get('_mask_path') else 0
        if grow:
            j['inp_grow'] = grow
        start = j['done']
        for k in range(start, j['count']):
            if j['cancel']:
                break
            if k > start and hooks.get('want') and hooks['want']():  # 配音 / 识别要用显卡：画完手上这张就让出来，剩下的排回队首
                return 'yield'
            seed = (j['seed'] + k) % 2 ** 31
            j['step'], j['preview'] = 0, None
            label = f"正在生成第 {k + 1}/{j['count']} 张" if j['count'] > 1 else '正在生成'
            j['message'] = label
            t0 = time.time()
            pre = f'studio_{tag}_{k}'
            los = ([(POSE_LORA, j.get('pose_w', 1.0))] if pose else []) + [(os.path.join(lora_sub(key), x['file']), x['weight']) for x in j.get('loras') or []]
            te = te_name(j)
            wf = (wf_ckpt(key, prompt, seed, w, h, st, pre, los) if FAMILY.get(key) == 'ckpt'
                  else wf_txt_other(key, prompt, seed, w, h, st, pre, los) if key in FAMILY and FAMILY[key] in TXT_ONLY
                  else wf_gen(key, [], prompt, seed, w, h, st, pre, los, te) if mode == 'txt' else wf_gen(key, names, prompt, seed, w, h, st, pre, los, te) if mode == 'edit'
                  else wf_local(key, names[0], mask, names[1:], prompt, seed, st, pre, loras=los, te=te, edge=edge, grow=grow))
            outs = _submit(j, wf, label)
            it = ((outs.get('o') or {}).get('images') or [None])[0]
            if not it:
                raise RuntimeError('ComfyUI 没有输出图片')
            fp = os.path.join(work_out, it.get('subfolder', ''), it['filename'])
            from PIL import Image
            im = Image.open(fp)
            im.load()
            fmt = j.get('format') or 'png'
            buf = io.BytesIO()
            (im.convert('RGB') if fmt != 'png' else im).save(buf, 'PNG' if fmt == 'png' else 'JPEG' if fmt == 'jpeg' else 'WEBP', **({} if fmt == 'png' else {'quality': j.get('quality') or 92}))
            try:
                os.remove(fp)
            except OSError:
                pass
            extra = {'seed': seed, 'width': im.width, 'height': im.height, 'seconds': round(time.time() - t0, 1), 'mode': mode, 'steps': st['steps'], 'cfg': st.get('cfg', 1.0),
                     'sampler': st['sampler'], 'scheduler': st['scheduler'], 'src': j.get('src'), 'refs': j.get('refs'), 'format': fmt,
                     'enhance': enh, 'enh_ver': j.get('enh_ver'), 'prompt_used': prompt if prompt != j['prompt'] else None, 'enhance_note': note or None, 'pose': True if pose else None,
                     'enhanced_raw': enh_text if enh != 'off' and enh_text and enh_text != prompt else None,
                     'loras': j.get('loras') or None, 'q_over': j.get('q_over') or None}
            out = buf.getvalue()
            rec1 = hooks['save'](out, {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}[fmt], {k2: v for k2, v in extra.items() if v is not None})
            if j.get('refine') and mode == 'txt' and MODELS.get(key, {}).get('refine'):  # 二采：一采的图交给 Krea 2 润色，另存一张（作者：一采二采各有好的时候，两张都留着挑）
                try:
                    j['message'] = label + ' · 二采（Krea 2 润色）'
                    rn = os.path.join(work_in, f'{pre}_r.png'); im.convert('RGB').save(rn, 'PNG'); made.append(rn)
                    t1 = time.time()
                    ro = _submit(j, wf_refine(os.path.basename(rn), prompt, seed, pre + '_r'), j['message'])
                    it2 = ((ro.get('o') or {}).get('images') or [None])[0]
                    if not it2:
                        raise RuntimeError('ComfyUI 没有输出图片')
                    fp2 = os.path.join(work_out, it2.get('subfolder', ''), it2['filename'])
                    im2 = Image.open(fp2); im2.load()
                    b2 = io.BytesIO()
                    (im2.convert('RGB') if fmt != 'png' else im2).save(b2, 'PNG' if fmt == 'png' else 'JPEG' if fmt == 'jpeg' else 'WEBP', **({} if fmt == 'png' else {'quality': j.get('quality') or 92}))
                    try:
                        os.remove(fp2)
                    except OSError:
                        pass
                    ex2 = {**extra, 'refine': 'krea2', 'refine_of': (rec1 or {}).get('id'), 'seconds': round(time.time() - t1, 1), 'width': im2.width, 'height': im2.height,
                           'steps': 8, 'refine_start': 6, 'cfg': 1.0, 'sampler': 'er_sde', 'scheduler': 'beta'}
                    hooks['save'](b2.getvalue(), {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}[fmt], {k2: v for k2, v in ex2.items() if v is not None})
                except Cancelled:
                    raise
                except Exception as e:
                    act('二采失败，一采的图已保存：' + str(e)[:200], 'img', 'warn')
                    j['warn'] = '二采失败，只保存了一采：' + str(e)[:160]  # 任务上也标出来（审查 16）
            j['done'] = k + 1
    except Cancelled:
        pass
    finally:
        for p in made:
            try:
                os.remove(p)
            except OSError:
                pass
        V.Engine.free_later()


# 2026-11-09 模板套：两段固定文字登记到 tplstore
import tplstore
tplstore.register('img', 'img_pose', '固定指令', [('IMG_POSE', 'en')], {'pos': {'IMG_POSE': POSE_PROMPT}}, group='人偶摆姿势')
tplstore.register('img', 'img_ai_t2i', '文生图 · 助手直接写', [('IMG_AI_T2I', '')], {'pos': {'IMG_AI_T2I': _system('t2i')}}, group='提示词增强', sys=True,
                  versions=[('', '官方写法', None), ('act', '动作拆开写', {'IMG_AI_T2I': AI_T2I})], stale={'IMG_AI_T2I': ['']})  # 助手直接写 / 官方增强拒绝时（2026-11-16）
tplstore.register('img', 'img_ai_inpaint', '局部重画', [('IMG_AI_INPAINT', 'zh')], {'pos': {'IMG_AI_INPAINT': AI_INPAINT}}, group='提示词增强', sys=True)  # 局部重画时用到 AI 助手的几档都用它（2026-11-16）


def pose_prompt():
    return tplstore.T('IMG_POSE')
