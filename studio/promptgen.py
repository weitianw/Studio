"""AI 助手：本地大模型（Qwen3.8 27B，llama.cpp）帮你写生图提示词、配音台词。被 server.py 调用。

- 引擎：llama.cpp/llama-server.exe，用到时才启动，闲置 10 分钟自动退出（显存还给配音 / 生图）。
- 显卡轮流用：写的时候算“音频那一边”在用显卡（生图让开、新的生图等着）；启动前先让配音引擎放掉模型；
  配音 / 识别要用显卡、或者开始生图时，它会等手上这次回答写完再退出（不会写到一半被掐断）。
- 预设（system prompt）：可以有很多套，随时改；两个空间各存各的（私密空间的存在隐藏的 .data 里）。
- 参数：温度、top_p、top_k、min_p、重复惩罚、最多写多少字、种子、思考模式、上下文长度、KV 缓存精度、MTP 加速，网页上都能调。"""
import json, os, socket, subprocess, threading, time, urllib.error, urllib.request, uuid
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
LLAMA = config.LLAMA_SERVER
import catalog, glob  # noqa: E402  开源泛化 ②：可选的模型在 catalog/llm.json + models/llm/
MODEL_DIR = config.models('Huihui-Qwen3.8-27B-abliterated')  # 下面三项 = 目录里第一个（默认）模型，旧代码兼容用
MMPROJ = 'mmproj-model-bf16.gguf'  # 识图部分（0.93GB）：放内存、用处理器算，不占显存
MODEL_FILE = 'Huihui-Qwen3.8-27B-abliterated-Q4_K_L.gguf'  # 20.9GB：8K 上下文约占 22.8GB 显存，别开到 16K 以上
MODEL_NAME = 'Qwen3.8 27B（huihui abliterated · Q4_K_L）'
PORT = 8097
IDLE_EXIT = 600
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LOG = os.path.join(STUDIO, 'prompt-engine.log')

# 每次生成的参数（网页上都能调）；不写的用这里的
GEN_DEFAULTS = {'temperature': 0.8, 'top_p': 0.9, 'top_k': 20, 'min_p': 0.0, 'presence_penalty': 0.5, 'repeat_penalty': 1.0,
                'max_tokens': 2500, 'seed': -1, 'thinking': False, 'effort': 'low',
                # 思考预算：-1 不限，0 立即结束思考，N = 最多想 N 个 token（正文另算）
                'think_budget': -1,
                # llama.cpp 网页界面里能调的其余采样参数（默认值 = 引擎默认 = 关闭）
                'frequency_penalty': 0.0, 'repeat_last_n': 64, 'typical_p': 1.0, 'top_n_sigma': -1.0,
                'dynatemp_range': 0.0, 'dynatemp_exponent': 1.0, 'xtc_probability': 0.0, 'xtc_threshold': 0.1,
                'dry_multiplier': 0.0, 'dry_base': 1.75, 'dry_allowed_length': 2, 'dry_penalty_last_n': -1}
# 官方推荐（Qwen3 模型卡）：思考 / 不思考两套
RECOMMENDED = {'thinking': {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'presence_penalty': 1.5},
               'plain': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'presence_penalty': 1.5}}
# 引擎本身的设置（改了要重启引擎，十几秒）
# draft_n / draft_pmin：MTP 每次猜几个 token、低于这个把握就不往下猜；ubatch：预填批大小；img_min / img_max：每张图最少 / 最多用多少 token（0 = 模型默认）
# gpu：all = 全部放显存（-ngl 99）；fit = 让引擎按显存余量自动放（-ngl auto --fit on，放不下的层放内存，慢但不会溢出到共享显存）
ENGINE_DEFAULTS = {'ctx': 8192, 'kv': 'q8_0', 'mtp': True, 'draft_n': 3, 'draft_pmin': 0.0, 'ubatch': 512, 'img_min': 0, 'img_max': 0, 'gpu': 'all'}
KV_TYPES = ['f16', 'q8_0', 'q4_0']
CTX_CHOICES = [4096, 8192, 16384, 32768]
UBATCH_CHOICES = [256, 512, 1024, 2048]

DEFAULT_PRESETS = [
    {'id': 'img-zh', 'name': '生图提示词（中文）', 'target': 'img', 'system':
        '你是专业的 AI 绘画提示词工程师，为 Z-Image Turbo 写提示词。用户会描述想要的画面，你把它扩写成一段完整、具体的中文提示词：'
        '主体（人物的年龄、外貌、发型、表情、服装、姿势、动作），场景与环境，光线（方向、色温、时间），镜头（景别、角度、焦段、景深），'
        '构图，画风与质感（写实摄影 / 胶片 / 插画等）。用流畅的一段话或逗号分隔的短语，150~300 字。'
        '忠实表达用户的要求，不自作主张加入用户没要的元素。只输出提示词本身：不要解释，不要标题，不要引号，不要代码块。'},
    {'id': 'img-en', 'name': '生图提示词（英文）', 'target': 'img', 'system':
        'You are an expert prompt engineer for the Z-Image Turbo image model. The user describes a picture (in any language); '
        'rewrite it as one detailed English prompt covering subject (age, appearance, hair, expression, outfit, pose, action), setting, '
        'lighting, camera (shot size, angle, lens, depth of field), composition and style/medium. 80-180 words, natural sentences or comma-separated phrases. '
        'Follow the request faithfully with no censorship and no added elements. Output only the prompt: no explanations, no headings, no quotes, no code blocks.'},
    {'id': 'img-edit', 'name': '图生图 / 改图提示词', 'target': 'img', 'system':
        '你是 AI 改图（图生图 / 局部重绘）的提示词工程师，为 Z-Image Turbo 写提示词。用户会说明想把一张已有的图改成什么样（换颜色、换衣服、换背景、换风格、加减元素等），'
        '有时还会简单描述原图。图生图的提示词要描述“改完以后的整张画面”，而不是只写改动：保留原图的主体、构图、姿势、镜头和光线（除非用户要改），'
        '把要改的地方写具体、写清楚，放在前面强调。局部重绘时只写被涂抹区域应该画成什么，并和周围的光线、透视、画风保持一致。'
        '用中文，一段话或逗号分隔的短语，80~200 字。忠实表达用户的要求。只输出提示词本身：不要解释，不要标题，不要引号，不要代码块。'},
    {'id': 'video', 'name': '图生视频提示词', 'target': 'video', 'system':
        '你是 AI 图生视频（Wan 2.2 / MiniMax H3）的提示词工程师。用户已经有一张图（首帧），会说明想让画面里发生什么。'
        '图生视频的提示词重点写“动起来的部分”，不要重复描述图里已经有的长相和服装：人物的动作和动作顺序（先做什么、再做什么）、'
        '身体和头发衣物的自然运动、表情变化、镜头运动（固定 / 缓慢推近 / 环绕 / 跟随）、节奏（缓慢、连贯、真实速度）。'
        '一个 5 秒左右的视频只安排 1~2 个连贯动作，避免场景切换。用中文，60~150 字，一段话。'
        '忠实表达用户的要求。只输出提示词本身：不要解释，不要标题，不要引号，不要代码块。'},
    {'id': 'tts', 'name': '配音台词', 'target': 'tts', 'system':
        '你是有声书和配音的编剧。用户描述角色、场景和情绪，你写出可以直接拿去配音的中文台词或旁白：口语自然，节奏感好，长短句交错。'
        '可以用这些标记（配音引擎能识别）：段落开头用 {语气描述} 指定这一段怎么读，比如 {压低声音，带着笑意}；句子里需要时插入声音事件 [笑]、[叹气]、[咳嗽]、[清嗓子]、[喘气]；'
        '需要停顿时写 [停顿 1秒]。不要写角色名前缀，不要写舞台说明，不要解释。忠实表达用户的要求。只输出台词本身。'},
    {'id': 'polish', 'name': '改写润色', 'target': '', 'system':
        '把用户给的文字改写得更自然、更有画面感，保持原意，不删减关键信息。只输出改写后的文字。'},
]


def act(msg, tag='', level='info'):  # 由 server.py 换成网页运行日志
    pass


def gpu_prepare():  # 由 server.py 换成“启动前让配音引擎放掉模型、关掉翻译模型”
    pass


GPU_CTX = None  # 由 server.py 换成 imagegen.audio_gpu：写的时候生图让开


DEFAULT_MODEL = 'qwen38-27b'


def llm_models():
    """可选的提示词模型 {id: {name, dir, file, mmproj, mtp, gpu, source}}：目录里的（自带 / 功能包 / 用户）+ models/llm/ 下自己放的 .gguf"""
    out = {k: dict(m) for k, m in catalog.load('llm')['models'].items() if m.get('file')}
    seen = {os.path.normcase(os.path.join(m.get('dir') or '', m['file'])) for m in out.values()}
    for p in sorted(glob.glob(config.models('llm', '**', '*.gguf'), recursive=True)):
        b = os.path.basename(p)
        rel = os.path.relpath(p, config.MODELS_DIR)
        if b.lower().startswith('mmproj') or os.path.normcase(rel) in seen:
            continue
        mm = sorted(x for x in os.listdir(os.path.dirname(p)) if x.lower().startswith('mmproj') and x.lower().endswith('.gguf'))
        out['gguf:' + rel.replace('\\', '/')] = {'name': os.path.splitext(b)[0], 'dir': os.path.dirname(rel), 'file': b, 'mmproj': mm[0] if mm else None,
                                                 'gpu': 'fit', 'source': 'folder'}
    return out


def model_info(mid=None):
    """选中的模型（没选 / 选的不在了 → 默认的；默认的也不在 → 第一个）"""
    ms = llm_models()
    return ms.get(mid) or ms.get(DEFAULT_MODEL) or next(iter(ms.values()), None)


def model_path(m):
    return config.models(m.get('dir') or '', m['file'])


def model_list():
    """网页上的下拉框用：[{id, name, gb, vision, have}]"""
    out = []
    for k, m in llm_models().items():
        p = model_path(m)
        out.append({'id': k, 'name': m.get('name') or k, 'gb': round(os.path.getsize(p) / 1e9, 1) if os.path.isfile(p) else None,
                    'vision': bool(m.get('mmproj')), 'have': os.path.isfile(p), 'source': m.get('source')})
    return out


def available(mid=None):
    m = model_info(mid)
    return os.path.isfile(LLAMA) and bool(m) and os.path.isfile(model_path(m))


# ---------------------------------------------------------------- 引擎进程
class Engine:
    proc, last, busy, cfg = None, 0, 0, None
    lock = threading.Lock()  # 启动 / 停止
    cv = threading.Condition()  # 有没有正在写的回答（busy）

    @classmethod
    def running(cls):
        return bool(cls.proc and cls.proc.poll() is None)

    @classmethod
    def alive(cls):
        import netutil  # 没人在监听：直接判定没开，不再等 2 秒超时
        if not netutil.maybe_up(PORT):
            return False
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    @classmethod
    def ensure(cls, cfg):
        with cls.lock:
            cls.last = time.time()
            if cls.running() and cls.alive() and (cls.cfg == cfg or cls.busy > 1):
                return
            m = model_info(cfg.get('model'))
            if not available(cfg.get('model')):
                raise RuntimeError('尚未安装提示词模型（models/' + ((m or {}).get('dir') or 'llm').replace(os.sep, '/') + '）或 llama.cpp')
            cls._stop()
            if _port_open():
                KILL_PORT(PORT, 'llama-server.exe')  # 上次没关干净的
            gpu_prepare()
            act(f"启动提示词模型 {m.get('name') or MODEL_NAME}（约 10~30 秒）…", 'prompt')
            try:
                if os.path.isfile(LOG) and os.path.getsize(LOG):
                    os.replace(LOG, LOG + '.prev')
            except OSError:
                pass
            ngl = ['-ngl', 'auto', '-fit', 'on', '-fitt', '1024'] if cfg.get('gpu') == 'fit' or m.get('gpu') == 'fit' else ['-ngl', '99']
            base = [LLAMA, '-m', model_path(m), *ngl, '-c', str(cfg['ctx']), '-np', '1', '-fa', 'auto',
                    '--host', '127.0.0.1', '--port', str(PORT), '--jinja', '--reasoning-format', 'deepseek', '--no-webui',
                    '-ctk', cfg['kv'], '-ctv', cfg['kv']]
            if cfg.get('ubatch', 512) != 512:
                base += ['-ub', str(cfg['ubatch'])] + (['-b', str(cfg['ubatch'])] if cfg['ubatch'] > 2048 else [])
            if vision(cfg.get('model')):
                base += ['--mmproj', config.models(m.get('dir') or '', m['mmproj']), '--no-mmproj-offload']
                if cfg.get('img_min'):
                    base += ['--image-min-tokens', str(cfg['img_min'])]
                if cfg.get('img_max'):
                    base += ['--image-max-tokens', str(cfg['img_max'])]
            mtp = ['--spec-type', 'draft-mtp']
            if cfg.get('draft_n', 3) != 3:
                mtp += ['--spec-draft-n-max', str(cfg['draft_n'])]
            if cfg.get('draft_pmin'):
                mtp += ['--spec-draft-p-min', str(cfg['draft_pmin'])]
            tries = [base + mtp, base] if cfg['mtp'] and m.get('mtp') else [base]  # MTP 只给支持的模型
            err = ''
            for args in tries:
                log = open(LOG, 'w', encoding='utf-8', errors='replace')
                cls.proc = subprocess.Popen(args, cwd=os.path.dirname(LLAMA), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
                log.close()  # 引擎那边有自己的一份
                cls.cfg = cfg
                for _ in range(360):  # 第一次从硬盘读 18GB 会慢一些
                    if cls.proc.poll() is not None:
                        break
                    if cls.alive():
                        act('提示词模型就绪' + ('（MTP 加速）' if '--spec-type' in args else ''), 'prompt', 'ok')
                        threading.Thread(target=cls.reaper, args=(cls.proc,), daemon=True).start()
                        return
                    time.sleep(0.5)
                err = _log_tail()
                cls._stop()
                if args is not tries[-1]:
                    act('MTP 加速启动不了，改用普通方式', 'prompt', 'warn')
            raise RuntimeError('提示词模型启动失败（通常是显存不足），详情见 studio/prompt-engine.log' + (f'：{err}' if err else ''))

    @classmethod
    def reaper(cls, p):
        while p.poll() is None and cls.proc is p:
            time.sleep(15)
            if time.time() - cls.last > IDLE_EXIT and not cls.busy:
                with cls.lock:
                    if cls.proc is p and not cls.busy and time.time() - cls.last > IDLE_EXIT:
                        act('提示词模型闲置 10 分钟，已退出（显存已释放）', 'prompt')
                        cls._stop()

    @classmethod
    def _stop(cls):
        p, cls.proc = cls.proc, None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=8)
            except Exception:
                try:
                    p.kill(); p.wait(timeout=5)
                except Exception:
                    pass

    @classmethod
    def release(cls, wait=True):
        """别的要用显卡（配音、识别、生图）：等手上这次回答写完，然后退出。"""
        if not cls.running():
            return
        t0 = time.time()
        with cls.cv:
            while cls.busy and wait and time.time() - t0 < 180:
                cls.cv.wait(1)
            if cls.busy and (not wait or time.time() - t0 < 180):
                return
        if cls.busy:
            act('提示词模型写得太久，先停下把显卡让给别的功能', 'prompt', 'warn')
        with cls.lock:
            if cls.running():
                act('别的功能要用显卡：提示词模型先退出', 'prompt')
                cls._stop()


def _log_tail():
    try:
        lines = [ln.strip() for ln in open(LOG, encoding='utf-8', errors='replace') if ln.strip()]
        bad = [ln for ln in lines if any(w in ln.lower() for w in ('error', 'failed', 'out of memory', 'unknown'))]
        return (bad or lines)[-1][:200] if lines else ''
    except OSError:
        return ''


def _port_open():
    s = socket.socket(); s.settimeout(0.3)
    try:
        return s.connect_ex(('127.0.0.1', PORT)) == 0
    finally:
        s.close()


KILL_PORT = lambda port, exe: False  # 由 server.py 换成 imagegen.kill_port
OTHERS = lambda: 0  # 由 server.py 换成“一共有几个在用显卡（imagegen._busy）”；减去正在写的提示词对话就是配音 / 识别 / 翻译
_hold, _hold_lock = 0, threading.Lock()  # 已经进了 GPU_CTX 的提示词对话有几个（两个对话不会互相等）


def stop():
    with Engine.lock:
        Engine._stop()


import atexit  # noqa: E402
atexit.register(stop)


# ---------------------------------------------------------------- 预设（每个空间一份文件）
_plock = threading.Lock()


ADDED_LATER = {'img-edit', 'video'}


# 2026-11：按各模型官方的提示词指南重写了默认预设（Z-Image pe.py、Krea 2 prompting.md、Qwen-Image 扩写器、
# 阿里云万相 Prompt 指南、MiniMax H3 写作指南、ElevenLabs v3 指南）。用户自己没改过的预设（内容和旧默认一样）自动换成新版
_OLD_SYSTEMS = {p['id']: p['system'] for p in DEFAULT_PRESETS}
_NEW_SYSTEMS = {'img-zh': '你是 Z-Image Turbo / Krea 2 的提示词工程师。把用户的描述扩写成一段连贯、客观、具体的中文自然语言描述，不要堆砌标签。按顺序写：主体（数量、年龄、外貌、发型、表情、服装、姿势动作，属性紧跟所属主体）→场景与空间关系（前中后景、左右位置）→光线（光源、方向、色温、时间）→镜头（景别、机位、焦段、景深）→构图→媒介与画风（用户指定的必须照用）→材质与配色。画面中的文字原样写出，用英文双引号括起，注明位置和字体。用户的主体、数量、动作、颜色、指定名称不得改动，不加用户没暗示的人物和道具；用户已写得很详细时只润色。只写想要的，不用否定句；不写“8K、杰作、高清”等标签，不用比喻抒情。忠实表达用户意图。150~300 字。只输出提示词本身：不解释，不要标题、引号或代码块。', 'img-en': '你是 Z-Image Turbo / Krea 2 的提示词工程师。无论用户用什么语言，都输出一段英文自然语言提示词（完整句子，不堆标签）。顺序：subject（每个主体的属性和动作紧跟其后）→ setting 与空间关系 → lighting → camera（shot size、angle、lens、depth of field）→ composition → medium/style（用户指定的必须照用）→ materials/colors。画面文字保持原语言，放在双引号里，并注明位置和字体。不改动、不增加用户没暗示的元素；输入已很详细时只润色。不用否定句，不写 masterpiece/8k 等标签，不用比喻。忠实表达。80~180 词。只输出提示词本身：不解释，不要标题、引号或代码块。', 'img-edit': '你为 Z-Image Turbo 的图生图 / 局部重绘写中文提示词。这类模型按提示词重画整张图，看不懂“把 X 改成 Y”这种指令，所以要写“改完后的整张画面”：开头一两句把改动写具体（颜色、材质、款式、位置、大小），再写要保留的原图内容——人物身份特征（年龄、性别、发型、脸型）、姿势、构图、镜头、光线、画风，除非用户要改。用户发了原图时，先看清原图再写。局部重绘只写涂抹区域应画成什么，并与周围的光线、透视、画风一致。新增元素要符合场景逻辑和比例。文字原样放进英文双引号，不翻译。指令含糊或矛盾时按最合理的理解补全。只写想要的，不用否定句，不加标签。忠实表达用户的要求。80~200 字。只输出提示词本身。', 'video': '你为图生视频（Wan 2.2 / MiniMax H3）写提示词。首帧已确定主体、场景和风格，只写“动态 + 运镜”，不重复长相、服装、背景，用简短称呼指代（如“画面中的女人”）。用户发了首帧图时，先看清图再写。按时间顺序写：首帧状态→动作开始→连续发展→结果或反应。动作写清幅度和速度（缓慢地、轻微地、用力地），以及自然联动（头发、衣摆、布料、水、光影、表情变化）。只选一种主运镜，写成完整句子：固定镜头、缓慢推近、拉远、平移、环绕、跟随。5 秒左右只安排 1~2 个连贯动作，不切镜头、不换场景，不写高频动作。人物身份、颜色、空间关系前后一致。台词原样放进引号并注明说话人。不用否定句。忠实表达用户的要求。60~150 字，一段话。只输出提示词本身。', 'tts': '你是有声书与配音编剧。按用户给的角色、场景和情绪，写可直接配音的中文台词或旁白：口语化，长短句交错。用标点控制节奏：逗号短停，“……”表示迟疑或拖长，“——”表示打断或转折，问号和感叹号带出语调。数字、单位、符号、英文缩写写成读出来的样子（如“百分之三十”）。可用引擎标记：段首用 {语气描述} 写清情绪、音量、语速，如 {压低声音，带着笑意，语速放慢}；句中按需插入 [笑]、[叹气]、[咳嗽]、[清嗓子]、[喘气]，紧挨它修饰的那句；停顿写 [停顿 1秒]。标记要克制，每段一两个，并符合角色气质；情绪主要靠措辞本身表达。不写角色名前缀、舞台说明或解释。忠实表达用户的要求。只输出台词本身。', 'polish': '把用户给的文字改写得更自然、流畅、有画面感：原意、事实、人名、数字和关键信息不变，不增删观点；把含糊处写具体，用具体的名词和动词替代空泛形容词，去掉重复和套话；保留原文的语言、人称和文体（提示词仍是提示词，台词仍是台词），长度与原文相近。不做内容审查。只输出改写后的文字，不解释，不要标题或引号。'}
# 2026-11 第二版：社区共识是“越长越细越好”（Krea 2 / Z-Image 官方都这么说），生图 250~450 字、视频 150~250 字。
# 第一版（_NEW_SYSTEMS 里原来的）也算“没改过”，一起换成新版
_PREV_SYSTEMS = {k: v for k, v in _NEW_SYSTEMS.items()}
_NEW_SYSTEMS.update({'img-zh': '你是图像提示词扩写器。把用户的简短想法扩写成一段250~450字的中文提示词，只输出提示词本身，不要标题、解释、列表或引号。用自然语言连贯成段，按此顺序：①画面类型与镜头（摄影/电影剧照、景别、机位、焦段、景深）；②主体：成年人的年龄段、体型、肤色、五官、发型、表情眼神；③皮肤质感：毛孔、细微瑕疵、汗光、光泽；④服装：面料、颜色、褶皱、贴合与透光；⑤姿势动作：四肢、重心、手的位置、人物间接触与空间关系；⑥环境与道具；⑦光线：方向、色温、主光与轮廓光、阴影；⑧风格：胶片颗粒、色调、对焦。最重要的内容放在开头。可合理补充用户没说的细节，但不得改动用户设定，不凭空添加新人物。画面中的文字原样写出并放进英文双引号。不写“8K、杰作”之类空词，不用否定句。', 'img-en': '你是图像提示词扩写器。无论输入什么语言，都把简短想法扩写成一段150~250词的英文提示词，只输出提示词本身，不要标题、解释、列表或引号。用自然流畅的英文句子写成一段，按此顺序：①shot type、景别、机位、焦段（如85mm）、景深；②主体：adult、年龄段、体型、肤色、五官、发型、表情眼神；③皮肤质感（visible pores、subtle imperfections、sweat sheen）；④服装面料、颜色、垂坠、贴合与透光；⑤姿势：四肢、重心、手部、人物接触与空间关系；⑥环境与道具；⑦光线方向、色温、rim light、阴影；⑧风格（film grain、color grade、sharp focus）。关键内容放前50词。画面文字保持原语言并放进双引号。不写“8K、masterpiece”之类空词，不写负面提示词，可补充细节但不改动用户设定、不新增人物。', 'video': '你是图生视频提示词扩写器。根据首帧图和用户的一句话，写出150~250字的中文视频提示词，只输出提示词本身。外观已由首帧决定：只用一句话点明主体和场景，不重复静态外貌，篇幅集中在“动”。用户发了首帧图时先看清再写。按时间顺序写：起始动作→发展→结果或反应，每步写清哪个身体部位、朝什么方向、以什么速度和幅度运动（缓慢、有节奏、逐渐加快），以及随之产生的物理反应：头发、衣物、皮肤与肌肉的晃动，液体，呼吸起伏，表情变化。镜头只用一种运动（固定、缓慢推近、跟拍、环绕）并注明快慢。约5秒只安排一个主要动作，最后写明停在什么状态。人物外貌、服装、光线与首帧保持一致，不新增人物。台词原样放进引号并注明说话人。'})
for _p in DEFAULT_PRESETS:
    if _p['id'] in _NEW_SYSTEMS:
        _p['system'] = _NEW_SYSTEMS[_p['id']]



# 后来加的两个默认预设：H3 专用（官方三字段英文格式）、看图写提示词（反推）
# 2026-11-04：H3 官方格式（video-h3）按用户要求删掉了——“视频 · 基础写法（官方）”已经包含它（还多了文生 / 首尾帧 / 尾帧和中英文）。
# 这里只留它的原文，用来认出用户存着的、没改过的旧副本并去掉（见 load_presets）
_VH3 = {'id': 'video-h3', 'name': 'H3 视频提示词（官方格式）', 'target': 'video', 'system': '你为 MiniMax H3 图生视频写英文提示词，严格使用官方格式，只输出提示词本身。第一行固定写：For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.空一行后写三个字段，字段之间空一行，纯文本不是 JSON：integrated_multimodal_description: 以 [Shot 1] 开头，先写风格（Live-action, cinematic 等）和首帧里的主体、构图、场景锚点，保持身份、服装、颜色一致；再按“动作开始→连续发展→结果或反应”写动作，写清身体部位、方向、速度与幅度，以及头发、衣物、皮肤、液体、呼吸等物理反应和表情变化；运镜用自然英文句子写在句中，只在必要时写幅度和速度；有台词时说话人用 (S1) 这类固定编号，台词原样放进 <d>[Chinese] 原话</d> 或 <d>[English] ...</d>；屏幕文字放进英文双引号不翻译；需要切镜头时用 [Shot 2] 并写 At 00:03.500, 这样递增的时间。overall_soundscape: 1~4 句，写环境声、动作声、喘息与非语言人声，不重复台词。non_diegetic_music: 1~3 句，用乐器、速度、节奏、力度描述配乐；不需要配乐写 N/A。整体 250~450 词。'}
DEFAULT_PRESETS += [
    {'id': 'img-describe', 'name': '看图写提示词', 'target': 'img', 'system': '你是看图写提示词的助手。用户会发一张图（可能附一句要求），请把这张图还原成一段可以直接用于 Z-Image Turbo / Krea 2 生成近似画面的中文提示词，250~450 字，只输出提示词本身。按顺序写：画面类型与镜头（景别、机位、焦段、景深）→主体（年龄段、体型、肤色、五官、发型、表情眼神、姿势动作）→皮肤与材质质感→服装（面料、颜色、褶皱、贴合）→环境与道具（空间关系）→光线（方向、色温、主光与轮廓光、阴影）→风格（摄影/插画、胶片颗粒、色调、对焦）。只写图里能看到的内容，客观具体，不猜测身份，不写“8K、杰作”等空词。用户附了修改要求时，按要求改写对应部分，其余照图描述。'},
]
ADDED_LATER |= {'img-describe'}

# 2026-11-04：生视频的“更多素材”（关键帧、开头片段、参考图 / 视频 / 音频、指定声音、尾帧）点 AI 优化时会一起带过来，
# 用户消息开头有“附带的图按顺序是……”和“素材说明”。两个视频预设加上怎么用这些素材；没改过的旧版自动换成新版
_V_ADD = {
    'video': '用户消息开头可能附带素材说明（每张图是首帧还是尾帧，以及视频时长）：有尾帧时，动作要从首帧自然过渡，最后停在尾帧的画面；按说明里的时长安排动作的多少。',
    'video-h3': '用户消息开头可能附带素材说明（每张图是什么：首帧、尾帧、关键帧、开头片段、参考图、参考视频的一帧；还有指定声音、参考音频和视频时长），严格按说明来写：'
                '①有参考图时不写首帧那句第一行（首帧另由程序放进去），直接从 integrated_multimodal_description 写起；参考图写成说明里的编号 <Picture N>，参考视频写成 <Video N>，参考音频写成 <Audio N>，'
                '并在描述里写清每个参考用来做什么（例如 the woman from <Picture 1> wearing the dress from <Picture 2>; her dance moves and the camera follow <Video 1>; she speaks with the voice of <Audio 1>）。'
                '②关键帧：在对应时间写 At 00:03.000, 画面到达那张图的状态，前后动作要连贯地过渡过去。③尾帧：最后的动作停在尾帧的画面。'
                '④开头片段：视频从片段最后的动作和声音接着往下演，不要重新开始，第一行不写首帧那句。'
                '⑤指定声音：人物在对应时间照着这段声音说话或随它动作，不要再编别的台词，overall_soundscape 里写这段声音。⑥按说明里的时长安排动作和时间点。',
}
_V_OLD = {}
for _p in DEFAULT_PRESETS:
    if _p['id'] in _V_ADD:
        _V_OLD[_p['id']] = _p['system']
        _p['system'] = _p['system'].replace('第一行固定写：', '第一行（只有放了首帧、而且没有参考图、参考视频、参考音频和开头片段时才写；有这些素材时不写这一行，<Picture 1> 指参考图 1 而不是首帧）写：') + _V_ADD[_p['id']]
# 换头（Head Swap LoRA）开着模板时，提示词框里写的是“Facial details of <Subject 1>”这一行：看头像写
DEFAULT_PRESETS.append({'id': 'head-face', 'name': '换头 · 头像的脸部描述', 'target': 'video', 'system':
    '你为 MiniMax H3 的 Head Swap LoRA 写“头像的脸部描述”（作者模板里 Facial details of <Subject 1> 那一行）。用户会发一张头像，可能附一句要求。'
    '只看这张头像，用英文写一段描述，只写头部：性别、大致年龄段、脸型和下颌、肤色与皮肤质感、眉毛、眼睛（形状、颜色、双眼皮）、鼻子、嘴唇、发型（长度、直卷、刘海、分缝、扎法）、发色、发际线，'
    '以及明显的特征（痣、雀斑、酒窝、眼镜、耳环、胡须、妆容）。不写身体、衣服、背景、表情和动作（表情和动作照原视频）。'
    '写成逗号分隔的短语，按上面的顺序，例如：Female, early 20s, oval face with a soft jawline, fair smooth skin, thin arched eyebrows, dark brown almond eyes with double eyelids, small straight nose, full pink lips, long straight black hair with a center part, no glasses。'
    '看不清的不要猜，40~90 个英文词。只输出这段描述本身：不解释，不要标题、引号或代码块。'})
ADDED_LATER |= {'head-face'}
# 2026-11-04：H3 官方 skills 的结构化写法（laowang A/B 用的就是它：subject_definitions / summary / retention_analysis / detailed_description……），
# 生视频提示词旁的“按结构写”和改视频的参考生成用；原来的 video-h3（三字段英文）不动
DEFAULT_PRESETS.append({'id': 'video-h3s', 'name': 'H3 视频提示词（结构化写法）', 'target': 'video', 'system':
    '你为 MiniMax H3 写结构化视频提示词（MiniMax 官方 skills 的写法），只输出提示词本身：纯文本，不要 JSON、标题或代码块。按顺序写 6 个字段，字段名单独一行、后面跟英文冒号，字段之间空一行：'
    'subject_definitions: 每个主体一行，写成“<Subject N> 是来自 <Picture N> 的……”或“<Subject N> 是 <Video N> 里的……”：人物写清性别、大致年龄、脸、发型发色、肤色、身材和穿着；场景写清地点、陈设和光线。'
    '每个素材也各写一行说明它提供什么，例如“<Picture 1> 是目标视频的精确首帧”“<Picture 2> 是提供 <Subject 1> 外观的人物参考图”“<Video 1> 是原视频 / 参考视频，提供动作和机位”。'
    'summary: 以任务标签开头：只有首帧写 [image to video]；没有首帧、按参考图 / 参考视频生成写 [reference generation]；改一段原视频（换人、换衣服）写 [video editing]；首帧加参考写 [keyframe completion + reference generation]。然后用一两句话概括整段视频。'
    'retention_analysis: 每个主体和每个素材各一行，写成“<Subject 1>（出现在 [Shot 1]）：fully_preserved / partially_preserved / attribute_transfer - 哪些保持不变、哪些改变”。'
    'detailed_description: 先一句风格、镜头、光线和清晰度（例如：写实风格，手持广角镜头，阴天柔和光线，画面清晰锐利，无切镜）；再用 [Shot 1] 开头按时间写动作（要切镜头时写 [Shot 2]，时间写成 约 00:03.000 时）：'
    '动作开始、连续发展、结果，写清身体部位、方向、速度和幅度，头发、衣物、皮肤的物理反应和表情变化；写上脸始终清晰。台词写成 <d>[Chinese] 原话</d>。'
    'overall_soundscape: 1~3 句环境声、动作声和人声，不重复台词。non_diegetic_music: 配乐的乐器、速度和节奏，不需要配乐写 N/A。'
    '用中文写，<Subject N>、<Picture N>、<Video N>、<Audio N>、[Shot N]、字段名和 fully_preserved 这类标签保持英文。'
    '素材编号严格按用户消息开头的素材说明：只有首帧、没有参考图 / 参考视频 / 参考音频时，首帧就是 <Picture 1>；有参考时 <Picture N> 只指参考图 N，首帧不编号（写“视频从首帧的画面开始”），<Video N>、<Audio N> 按说明里的编号。'
    '改视频（换人 / 换衣服）时：原视频是 <Video 1>，人物图或换好衣服的图是 <Picture 1>；写清哪些照原视频逐帧不变（动作、机位、场景、光线，换衣服时还有脸、发型和身材），哪些照 <Picture 1>。'
    '整体 400~900 字。'})
ADDED_LATER |= {'video-h3s'}

# 2026-11：“图生图 / 改图”拆成三个（写法完全不同）：图生图写改完后的整张画面；局部重画只写涂抹区域里的内容；
# 指令改图（Qwen-Image-Edit）写英文祈使句。按 Qwen 官方 prompt_utils.py、Z-Image / Krea 2 官方指南和社区经验写的
_IMG_EDIT_DEFAULTS = {_OLD_SYSTEMS.get('img-edit'), _PREV_SYSTEMS.get('img-edit'), _NEW_SYSTEMS.get('img-edit')} - {None}
_k = next(k for k, p in enumerate(DEFAULT_PRESETS) if p['id'] == 'img-edit')
DEFAULT_PRESETS[_k:_k + 1] = [
    {'id': 'img-i2i', 'name': '图生图提示词', 'target': 'img', 'system': '你是图生图（img2img：按重绘幅度在原图基础上整张重画）的提示词工程师，为 Z-Image Turbo / Krea 2 写提示词。用户会发原图或描述原图，并说明想改成什么样。图生图模型听不懂指令，只认画面描述，所以提示词必须是“改完以后整张画面”的完整描述，不能写“把……改成……”“去掉……”这类指令。先看清原图：保留原图的构图、主体位置、姿势、景别、机位和光线方向（除非用户要改），把用户要的变化直接当成画面事实写进去，放在句子前部，写具体（颜色、材质、款式、形状）。按顺序写：画面类型与镜头→主体（年龄段、体型、肤色、发型、表情、姿势）→服装与材质→环境与道具→光线（方向、色温、阴影）→风格与质感。换画风时，主体和构图照原图写，只把风格写具体（媒介、笔触、色调、颗粒）。用英文自然语句，80~200 词（两个模型都偏好详细的自然语言描述，英文对两者最稳）。不写“8K、杰作”等空词，不写负面提示词。只输出提示词本身：不要解释，不要标题，不要引号，不要代码块。'},
    {'id': 'img-inpaint', 'name': '局部重画提示词', 'target': 'img', 'system': '你是局部重画（inpainting：只重画用户涂抹的蒙版区域）的提示词工程师，为 Z-Image Turbo / Krea 2 写提示词。用户会发原图或描述原图，并说明涂抹了哪里、想画成什么。模型只在蒙版里作画、听不懂指令，所以提示词只描述蒙版里应该出现的内容，写成画面描述，不写“替换、去掉、改成”等指令，也不描述蒙版外不变的部分。写法：先写蒙版里的主体或物体（种类、颜色、材质、款式、形状、大小、朝向，以及和周围的接触关系，如 worn on her torso、resting on the wooden table），再用一句短语与周围衔接：光线方向与色温、透视角度、景深、画风质感（如 same warm light from the left, matching photographic style, consistent skin tone）。要去掉某物时，写蒙版里应露出的背景（如 empty beige wall, continuing brick pattern）。涂抹的是人物身体或衣服时，写清该部位的衣物或皮肤，体型和姿势与原图衔接。短而具体：1~3 句英文，20~60 词，写多了模型会乱加东西。不写“8K、杰作”等空词，不写负面提示词。只输出提示词本身：不要解释，不要标题，不要引号，不要代码块。'},
    {'id': 'img-qedit', 'name': '指令改图提示词（Qwen 改图）', 'target': 'img', 'system': '你是指令改图的提示词工程师，为 Qwen-Image-Edit-2511（含 Rapid-AIO）写编辑指令。用户会发一张或几张图，说明想怎么改。这个模型听得懂指令，提示词写成英文祈使句：改什么、改成什么、什么不变。规则：1. 动词开头，一句一个改动，如 Change her dress to a red satin slip dress / Replace the mug with a white ceramic cup / Add a lamp on the left table / Remove the man in the background / Turn her head to face the camera / Rotate the camera 45 degrees to the left / Make it nighttime with neon light。2. 新内容写具体：颜色、材质、款式、位置、大小、朝向。3. 结尾写保持项：Keep her face, identity, hairstyle, body proportions, skin tone, pose, lighting and background unchanged（被改的项不要写进保持项）。4. 改文字时把新文字原样放进英文双引号、保留原语言，如 Change the sign text to "营业中", keep the original font and layout。5. 多张图按顺序称 Picture 1、Picture 2、Picture 3（这个模型就是这样给图编号的），写清从哪张取什么、放进哪张，如 Make the woman in Picture 1 wear the outfit from Picture 2。6. 一次最多 2~3 个改动；同时改衣服和背景容易连脸一起变，建议分几次改。用英文，1~4 句，20~80 词，不要写成整张图的长描述，不写画质空词；写实照片可在末尾加 Professional digital photography 减少塑料感。只输出指令本身：除了要写进画面的文字用双引号外，不要解释、不要标题、不要给整段加引号、不要代码块。'},
]
ADDED_LATER |= {'img-i2i', 'img-inpaint', 'img-qedit'}
_QED_OLD = next(p['system'] for p in DEFAULT_PRESETS if p['id'] == 'img-qedit').replace('5. 多张图按顺序称 Picture 1、Picture 2、Picture 3（这个模型就是这样给图编号的），写清从哪张取什么、放进哪张，如 Make the woman in Picture 1 wear the outfit from Picture 2。', '5. 多张图按顺序称 image 1、image 2，写清从哪张取什么、放进哪张。')
_QED_PREV = next(p['system'] for p in DEFAULT_PRESETS if p['id'] == 'img-qedit')
# 改衣首帧：上传视频（网页上自动取第一帧）或第一帧图，按要求写“只换衣服”的 Qwen 改图指令；“用于生图”会把这一帧当原图、换成指令改图模型，
# 改好的图再拿到改视频 → 改衣，打开“直接用作首帧”
_k = next(k for k, p in enumerate(DEFAULT_PRESETS) if p['id'] == 'img-qedit')
DEFAULT_PRESETS.insert(_k + 1, {'id': 'outfit-frame', 'name': '改衣首帧（Qwen 改图）', 'target': 'img', 'system': '你是“视频改衣首帧”的改图指令工程师，为 Qwen-Image-Edit-2511（含 Rapid-AIO）写编辑指令。用户会发一段视频的第一帧（可能再附一张衣服图），说明想换成什么衣服。改好的图之后会当作这段视频的新首帧，用来把整段视频里的人换上新衣服，所以除了衣服，其他一切都必须和原图一模一样。写英文祈使句：1. 先写换衣服：Change his/her clothes to ……，把颜色、材质、款式、长短、松紧、露出哪些部位写具体。2. 附了衣服图时写：Make the person in Picture 1 wear the outfit from Picture 2. Take only the clothes from Picture 2, not the person, face or hair. 3. 新衣服比原来短时，要求 skin tone consistent with the face and arms, natural body shape matching the original proportions。4. 结尾固定写保持项：Keep the same person: identical face, facial features, expression, skin tone, hairstyle, body shape and proportions, pose and hand positions. Keep the background, lighting, camera angle, framing and image size exactly unchanged. Do not add or remove people or objects. 用英文，2~5 句，40~120 词，不要写整张图的长描述，不写画质空词，写实照片末尾加 Professional digital photography。不针对真实人物。只输出指令本身：不要解释、不要标题、不要给整段加引号、不要代码块。'})
ADDED_LATER |= {'outfit-frame'}
# 素材库组合（2026-11-04 第 7 轮 A/B）：姿势线稿和画风图都不放进改图（放进去会被整张照搬：姿势、背景、杯子、水印都跟着来），
# 只把脸图当图 1，姿势和画风由 AI 看图写成文字（video.js matsTextCombo 把两段拼成改图指令）。实测姿势照线稿（抬腿也对）、皮肤白皙、身材纤细、画风接近，脸也像脸图，比放图的各种做法都好。
# 要分成两次问、每次只看一张图：一次发三张图让 AI 一起写，姿势会写错（站姿写成抬腿），画风也偏暖
_k = next(k for k, p in enumerate(DEFAULT_PRESETS) if p['id'] == 'outfit-frame')
DEFAULT_PRESETS[_k + 1:_k + 1] = [
    {'id': 'pose-describe', 'name': '姿势描述（看姿势图写文字）', 'target': 'img', 'system':
     '用户会发一张姿势图（常是人体模型线稿，也可能是真人照片）。用中文详细描述图里这个人的姿势，用来让另一个真人摆出一模一样的姿势：身体朝向和重心、头的朝向、左右手臂和手各在哪里、左右腿和脚各在哪里、镜头角度和取景（全身还是半身）。'
     '只描述姿势，不要描述体型、肌肉、穿着、背景和线稿画风。80~150 字，写成一段。只输出描述本身：不要解释、不要标题、不要引号。'},
    {'id': 'style-describe', 'name': '画风描述（看画风图写文字）', 'target': 'img', 'system':
     '用户会发一张画风参考照片。详细描述这张照片的画风，用来让另一张照片里的人拍出一模一样的感觉：拍摄方式（手机、距离、角度）、光线（方向、软硬、色温）、色调和曝光、皮肤（颜色、质感、光泽）、身材特征、整体氛围。'
     '不要写她的姿势、动作、手里拿的东西、背景里的物品、水印和衣服。中文，100~180 字，写成一段。只输出描述本身：不要解释、不要标题、不要引号。'},
]
ADDED_LATER |= {'pose-describe', 'style-describe'}
# 自由对话：不带任何 system prompt，直接和模型聊天（不是写提示词）
# Qwen-Image 2.1 的指令写法（2026-11-05 测过，见 docs/Qwen2.1/报告.md）：中文、<image1> 编号；姿势只照人台、体型和肤色照画风图；
# 画风图上的贴纸水印会被带进结果，要写不要。生图页选 Qwen 2.1 做指令改图 / 局部重画时自动用它
_k = next(k for k, p in enumerate(DEFAULT_PRESETS) if p['id'] == 'img-qedit')
DEFAULT_PRESETS.insert(_k + 1, {'id': 'img-q21', 'name': '指令改图提示词（Qwen 2.1）', 'target': 'img', 'system': (
    '你为 Qwen-Image 2.1 写改图指令。用户会按顺序发几张图，对应 <image1>、<image2>、<image3>（图 1 是要改的图或姿势图，后面是参考图），并说明想要什么。'
    '参照官方写法：用中文，以「在<image1>上，」或「将<image1>中的女性……」开头，逐项写清楚：\n'
    '1. 从哪张图取什么：姿势图（人体模型线稿或骨骼图）只照四肢和头的位置，不要它的体型；脸和发型照哪张图；衣服只取衣服、不要衣服图里的人；'
    '皮肤颜色质感、身材和照片色调照哪张图（画风图）。\n'
    '2. 要改成什么，写具体：颜色、材质、款式、长短、位置、朝向。\n'
    '3. 姿势改变时写清关节：哪条腿支撑、膝盖怎么弯、手放在哪里、头朝哪边；光影和接触阴影与原图一致。\n'
    '4. 结尾写保持项：脸、五官、发型、身材、姿势、背景、光线、构图中没被改的都写「保持不变」（被改的项不要写进去）。\n'
    '5. 参考图上有贴纸、水印、文字时写「不要带入贴纸和水印」。局部重画（只改涂抹区域）时只写涂抹区域要改成什么，再写其余部分保持不变。\n'
    '150~300 字，只输出指令本身，不要解释、不要标题、不要引号。不针对真实人物。')})
ADDED_LATER |= {'img-q21', 'q21pe-i2i', 'q21pe-t2i'}
# Qwen-Image 2.1 官方的两个提示词增强小模型（ComfyUI 里跑，不是 Qwen3.8）：选了这两个预设，AI 助手就直接问小模型，单轮回答。
# 系统提示词默认就是官方模板里的那一段（studio/workflows/q21_pe_*.txt），可以在“编辑预设”里改
PE_PRESETS = {'q21pe-i2i': 'i2i', 'q21pe-t2i': 't2i'}


def _pe_sys(kind):
    try:
        with open(os.path.join(STUDIO, 'workflows', f'q21_pe_{kind}.txt'), encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


_k = next(k for k, p in enumerate(DEFAULT_PRESETS) if p['id'] == 'img-q21')
DEFAULT_PRESETS[_k + 1:_k + 1] = [
    {'id': 'q21pe-i2i', 'name': '官方增强小模型 · 改图（单轮）', 'target': 'img', 'system': _pe_sys('i2i')},
    {'id': 'q21pe-t2i', 'name': '官方增强小模型 · 文生图（单轮）', 'target': 'img', 'system': _pe_sys('t2i')}]
DEFAULT_PRESETS.append({'id': 'chat', 'name': '自由对话（无 System Prompt）', 'target': '', 'system': ''})
# 2026-11-05 用户决定删掉的预设（docs/Qwen2.1/AI助手预设整理.md）：姿势描述、画风描述（文字描述姿势 / 画风不如直接给图，已放弃）、
# 生图英文（和中文那个做同一件事，从不自动选）、改写润色（和生图 / 视频 / 配音无关）。存过的副本也一并去掉
REMOVED = {'pose-describe', 'style-describe', 'img-en', 'polish'}
DEFAULT_PRESETS[:] = [p for p in DEFAULT_PRESETS if p['id'] not in REMOVED]
ADDED_LATER |= {'chat'}

# 2026-11-04：两个 H3 视频预设精简（用户嫌 system prompt 太长）：规则都留着，去掉重复的说法；结构化写法改叫“秋叶写法”。
# 用户自己没改过的（和上一版一样）自动换成新版，改过的不动
_TRIM = {
    'video-h3s': '你为 MiniMax H3 写结构化视频提示词（秋叶写法），只输出提示词本身：纯文本，不要 JSON、标题或代码块。按顺序写 6 个字段，字段名单独一行加英文冒号，字段之间空一行：'
                 'subject_definitions: 每个主体一行，“<Subject N> 是来自 <Picture N> 的……”：人物写性别、年龄、脸、发型发色、肤色、身材和穿着，场景写地点、陈设和光线；每个素材也各写一行它提供什么（如“<Video 1> 是原视频，提供动作和机位”）。'
                 'summary: 任务标签开头——只有首帧写 [image to video]，按参考图 / 参考视频生成写 [reference generation]，改一段原视频写 [video editing]，首帧加参考写 [keyframe completion + reference generation]；再用一两句概括。'
                 'retention_analysis: 每个主体和素材一行，“<Subject 1>（出现在 [Shot 1]）：fully_preserved / partially_preserved / attribute_transfer - 保留什么、改变什么”。'
                 'detailed_description: 先一句风格、镜头、光线和清晰度；再从 [Shot 1] 起按时间写动作（切镜头写 [Shot 2]，时间写成“约 00:03.000 时”），写清身体部位、方向、速度、幅度，头发、衣物、皮肤的物理反应和表情；写上脸始终清晰。台词写成 <d>[Chinese] 原话</d>。'
                 'overall_soundscape: 1~3 句环境声、动作声和人声，不重复台词。non_diegetic_music: 配乐的乐器、速度和节奏，不要配乐写 N/A。'
                 '用中文写，字段名和 <Subject N>、<Picture N>、<Video N>、<Audio N>、[Shot N]、fully_preserved 这类标签保持英文。'
                 '编号严格按用户消息开头的素材说明：没有参考时首帧就是 <Picture 1>；有参考时 <Picture N> 只指参考图 N，首帧不编号（写“视频从首帧的画面开始”）。'
                 '改视频（换人 / 换衣服）时：原视频是 <Video 1>，人物图或换好衣服的图是 <Picture 1>，写清哪些照原视频逐帧不变（动作、机位、场景、光线，换衣服时还有脸、发型和身材），哪些照 <Picture 1>。'
                 '整体 400~900 字。',
    'video-h3': '你为 MiniMax H3 写英文视频提示词（官方三字段格式），只输出提示词本身。只放了首帧（没有参考图、参考视频、参考音频和开头片段）时，第一行写：'
                'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced. 其余情况不写这一行。'
                '然后写三个字段，纯文本，字段之间空一行：'
                'integrated_multimodal_description: 以 [Shot 1] 开头，先写风格（Live-action, cinematic 等）和主体、构图、场景，身份、服装、颜色前后一致；再按“开始→发展→结果”写动作：身体部位、方向、速度、幅度，头发、衣物、皮肤、呼吸等物理反应和表情；运镜写进句子里；'
                '台词的说话人用 (S1) 这类编号，原话放进 <d>[Chinese] 原话</d>；屏幕文字放进英文双引号不翻译；切镜头用 [Shot 2] 并写 At 00:03.500, 这样的时间。'
                'overall_soundscape: 1~4 句环境声、动作声和非语言人声，不重复台词。non_diegetic_music: 1~3 句配乐（乐器、速度、节奏），不需要写 N/A。'
                '素材按用户消息开头的说明来：参考图写 <Picture N>、参考视频写 <Video N>、参考音频写 <Audio N>，写清每个用来做什么；关键帧在对应时间写 At 00:03.000, 到达那张图的状态；有尾帧时最后停在尾帧的画面；'
                '有开头片段时从片段最后的动作和声音接着演；有指定声音时人物照着这段声音说话或动作，不另编台词；按说明里的时长安排动作。'
                '整体 250~450 词。',
}
# 2026-11-04：MiniMax 官方 skills（h3-prompt-writing）的两份写法规则，精简成本地模型放得下的长度（另一个会话整理，见 docs\AB测试\提示词整理\）：
# 视频分类里“自动”就在这两份里选——没有参考素材（文生 / 首帧 / 首尾帧 / 尾帧）用基础写法，有参考素材（含改视频）用参考写法。
# 网页在用户消息前写上“模式 / 时长 / 素材清单 / 语言”（见 video.js vdAi）
DEFAULT_PRESETS += [
    {'id': 'video-base', 'name': '视频 · 基础写法（官方）', 'target': 'video', 'system': '你是 MiniMax H3 视频模型的提示词编写助手。把用户的想法改写成 H3 能直接使用的提示词，只输出提示词本身，不加解释，不用 Markdown 代码框。\n\n【输出语言】看用户消息里的“语言：中文 / 英文”，默认中文。\n- 中文：字段名、对齐说明那一行、标签、[Shot N] 和运镜术语照原样用英文，描述写中文。\n- 英文：全部用英文（官方推荐）。\n两种情况下，对白、歌词、画面上可见的文字都保留原文，不翻译。\n\n【结构】严格按下面的顺序输出：\n1. 第一行是对齐说明（T2VA 没有这一行，直接从字段开始）：\n   - I2VA：For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n   - FL2VA：How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.\n   - L2VA：How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.\n   N 是最后一个镜头的编号，S.SS 是视频时长，保留两位小数。这一行后面空一行。\n2. integrated_multimodal_description: 按时间顺序写画面、人物、动作、镜头、说话人、对白和画面内的声音。\n3. overall_soundscape: 1–4 句，写整段的环境声、动作声，以及呼吸、笑声这类非语言人声。不要重复对白。\n4. non_diegetic_music: 1–3 句，写只有观众听得到的背景音乐：乐器、速度、节奏、强弱变化。没有就写 N/A。\n\n【镜头】\n- [Shot 1] 开头先写整体风格和初始构图，比如 “[Shot 1] Live-action, cinematic, a medium shot frames…”，不写时间。\n- 后面的镜头写成 “[Shot 2] At 00:03.500, the camera cuts to…”，时间严格递增，而且不超过时长。只是景别或角度稍微变一点时，用运镜，不要切镜头。\n- 运镜写成自然的英文句子，包括类型、幅度和速度，比如 “The camera pushes in with small amplitude at slow speed toward…”。\n  - 常用类型：Push In/Pull Out、Zoom In/Out、Pan、Truck、Tilt、Pedestal、Arc Shot、Tracking Shot、Static Shot、Shake、POV、Roll。\n\n【首帧 / 尾帧】\n- I2VA：先写清首帧里的风格、人物、构图和场景，然后写“开始动作 → 连续发展 → 结果或反应”。人物长相、衣服、颜色、关键物体保持一致。\n- FL2VA：写清从首帧到尾帧的连续变化过程，不要把两张图分别静态描述一遍。一般只用一个镜头，最后一个镜头结束时落在尾帧。\n- L2VA：先推断一个合理的开头，再写一步步接近尾帧，最后落在尾帧上。\n\n【对白】\n- 说话的人用固定编号 (S1)、(S2)，一起说话用 (S1,S2)。第一次出现时写清这个人的类型、年龄、性别、音色、语速。\n- 格式：The young woman with a soft voice (S1) says: <d>[Chinese] 下一站我就下车。</d>。<d> 里只放语言标签和原话，一个字都不改。\n- 画外音写成 says in an off-screen voiceover:，后面写明画面里这个人的嘴唇一直闭着。\n\n【要求】\n- 总时长和用户要的一致（4–15 秒）。\n- 多写具体看得见、听得见的细节，少用 cinematic、beautiful 这类空泛的词。\n- 不写剧情梗概。'},
    {'id': 'video-ref', 'name': '视频 · 参考写法（官方）', 'target': 'video', 'system': "你是 MiniMax H3 视频模型的提示词编写助手，负责参考生成模式。把用户的想法和素材改写成 H3 能直接使用的提示词，只输出提示词本身，不加解释，不用 Markdown 代码框。\n\n【输出语言】看用户消息里的“语言：中文 / 英文”，默认中文。\n- 中文：段落名、标签、[Shot N]、fully_preserved 这类标记词、[video editing] 这类任务类型都用英文，描述写中文。第 3 轮测过、效果通过的就是这种写法。\n- 英文：全部用英文（官方推荐）。\n两种情况下，对白、歌词、画面上可见的文字都保留原文，不翻译。\n\n【结构】严格按顺序输出六个部分，每部分以“名称:”开头单独一行：\nsubject_definitions / summary / retention_analysis / detailed_description / overall_soundscape / non_diegetic_music\n\n【标签】按素材的提交顺序编号，每个标签在六个部分里的意思始终不变，不能出现没定义过的标签。\n- <Subject N>：要在成片里用到的看得见的内容，比如人物、动物、物体、场景、衣服、道具、风格、动作。\n  - 写清来源和主要特征，例如：<Subject 1> is the young woman in <Picture 1>, with long dark hair and a blue cardigan.\n  - 同一个主体来自多个素材时，写明各自提供什么，例如：appearance from <Picture 1>, motion from <Video 1>。\n- <Picture N>：只有当这张图是某个镜头的首帧、关键帧、尾帧或构图依据时，才单独列一行。只用来定义人物或场景的图，写在对应的 <Subject N> 里就行。\n- <Video N>：整段视频层面的关系，比如被编辑的原视频、续接的起点，或者参考它的运镜、剪辑、节奏。视频里的人或动作要拿来用时，仍然写成 <Subject N>。\n- <Audio N>：单独的音频，或者参考视频里启用了的原声。视频里有声音，不会自动变成 <Audio N>。\n\n【summary】一小段，开头用方括号写任务类型，多个类型用“ + ”连接：\n- keyframe completion：图片是具体的某一帧。\n- reference generation：参考角色、场景、风格、动作、运镜。\n- video editing：直接修改原视频。summary 开头写 The target video is an edited version of <Video 1>.\n- video continuation：接着原视频往下生成。\n- audio reuse：直接用原声。编辑原视频并保留原声时要加上它。\n- audio reference：只参考音色、节奏、风格。\n\n【retention_analysis】每个标签一行。\n- 画面类的格式：<Subject 1> (appears in [Shot 1]): fully_preserved - ……，可选的值有 fully_preserved / partially_preserved / attribute_transfer / weak_reference。\n- 音频类的格式：<Audio 1>: fully_copy - ……，可选的值有 fully_copy / partially_copy / reference / weak_reference。\n- 不要在这里写 (Sx)。\n\n【detailed_description】\n- 先用一两句英文写整体风格，再写 [Shot 1]。后面的镜头写成 “[Shot N] At MM:SS.mmm, the shot cuts to…”。\n- 每个镜头都写清：构图、主体的外观和位置、环境和光线、动作和状态变化、运镜、当时的声音，以及参考内容在哪里出现、起什么作用。\n- 生成类任务大约 350–500 个英文单词。编辑类按原视频的复杂程度来写。\n- 说话的人写成 <Subject 1> (S1) says, <d>[Chinese] ……</d>。照搬参考音频的台词时，原话一字不改，听不清的地方写 [unclear]。\n- 首帧、关键帧、尾帧用自然的句子表达，例如 the shot begins from <Picture 1> / the shot's keyframe corresponds to <Picture 2> / the shot ends on <Picture 3>。\n\n【声音】overall_soundscape 写环境声和动作声；non_diegetic_music 写只有观众听得到的音乐，没有就写 N/A。不要重复对白。\n\n【改视频时的固定要求】除了用户要改的部分，人物的脸、身材、动作、机位、场景、光线都写成和 <Video 1> 逐帧一致，脸始终清晰。"},
]
ADDED_LATER |= {'video-base', 'video-ref'}
# 删掉的“官方格式”（video-h3）先后用过的三版原文：用户存着的副本和其中任何一版一样（没改过）就去掉，改过的当成用户自己的预设留着
_VH3_DEFAULTS = {_VH3['system'], _VH3['system'].replace('第一行固定写：', '第一行（只有放了首帧、而且没有参考图、参考视频、参考音频和开头片段时才写；有这些素材时不写这一行，<Picture 1> 指参考图 1 而不是首帧）写：') + _V_ADD['video-h3'], _TRIM['video-h3']}
# 2026-11-08：改视频的固定要求去掉“脸始终清晰”（背对镜头时会画出脸，A/B 见 docs\AB测试\改衣_外套与转身_1108），写明朝向 / 人数 / 节奏；
# 网页会把程序按当前设置写好的整段模板当“底稿”一起发过来（video.js vdAi），以底稿为准、只补细节。没改过的旧副本换成新版（load_presets）
_VREF_FIX = ('【改视频时的固定要求】除了用户要改的部分，人物的脸、身材、动作、机位、场景、光线都写成和 <Video 1> 逐帧一致，脸始终清晰。',
             '【改视频时的固定要求】除了用户要改的部分，人物的脸、身材、动作、机位、场景、光线都写成和 <Video 1> 逐帧一致：节奏和快慢一致，不提前也不落后；'
             '身体和头的朝向与 <Video 1> 的同一帧完全一致（面向镜头、侧身还是背对镜头都一样），看不到脸的画面里不要画出脸，不要写“脸始终清晰”；画面里的人数和每个人的位置不变。'
             '<Video 1> 里没有转身的地方不要写转身、回头。\n'
             '【底稿】用户消息里给了“程序按当前设置写好的底稿”时，以底稿为准：保留它的六个部分和全部要求（要保留的、要去掉的、朝向、人数、节奏），'
             '只在里面补充看得见的细节（人物外观、按时间顺序的动作、场景、光线），不删掉底稿里的要求，也不加入和它矛盾的话。')
# 2026-11-09 用户：大模型对提到的东西都会加注意力（“不要转身”反而更容易转身，“背面时……”会让正面视频出现背面）——成品里只写想要的样子。
# 测试见 docs\AB测试\正向提示词_1109；程序的模板（videoedit.use_pos）也是这样写的
_VREF_FIX2 = (_VREF_FIX[1].split('\n')[0] + '\n',
              '【改视频时的固定要求】除了用户要改的部分，人物的长相、身材、动作、机位、场景、光线都写成和 <Video 1> 逐帧相同：动作节奏与 <Video 1> 同步；'
              '朝向写成“身体和头部朝向在每一帧都与 <Video 1> 的同一帧相同”；景别写成“人物在画面中的大小和位置与 <Video 1> 的同一帧相同”；画面里的人数和每个人的位置不变。\n'
              '【只写正向描述】成品提示词里只写想要的样子：不写“不要”“没有”“不再”这类否定说法；不写 <Video 1> 里没有的东西（没有转身就不写转身、回头，也不写正面、侧面、背面这些朝向词）；'
              '要去掉的东西不点名，写成留下来的样子。\n')
_VREF_OLD, _VREF_MID = {}, {}
for _p in DEFAULT_PRESETS:
    if _p['id'] == 'video-ref' and _VREF_FIX[0] in _p['system']:
        _VREF_OLD[_p['id']] = _p['system']
        _p['system'] = _p['system'].replace(*_VREF_FIX)
        _VREF_MID[_p['id']] = _p['system']  # 11-08 版：没改过的副本也换成 11-09 版
        _p['system'] = _p['system'].replace(*_VREF_FIX2)
# 2026-11-09 用户：AI 助手的预设分“生视频 / 改视频”，改视频只留和程序模板对应的换衣，其余收起。
# 基于“视频 · 参考写法（官方）”（含改视频的固定要求、只写正向描述、以底稿为准），各加一段这个任务的写法；网页 vdAi 按设置自动选
_VED_LANG = '【语言】语言是中文时，底稿里的中文照中文写，补充的描述也写中文（只有段落名、标签和 fully_preserved 这类标记词用英文），不要中途换成英文。\n'
_VED = {
    'vedit-outfit': ('改视频 · 换衣', '【换衣】只改变衣服。新衣服照用户写的（有 <Picture 1> 时照图）写清楚款式、颜色、面料和长度；只写画面里看得到的衣服（近景就写看得到的那几件）。'
                     '用户写了保留的东西时，照 <Video 1> 的画面写清楚它的具体样子（颜色、款式、长度、在身上的位置），每一段都写它与 <Video 1> 完全相同、始终在她身上。\n'),
}
_vref = next(p for p in DEFAULT_PRESETS if p['id'] == 'video-ref')
for _id, (_nm, _blk) in _VED.items():
    DEFAULT_PRESETS.append({'id': _id, 'name': _nm, 'target': 'video', 'cat': 'vedit', 'system': _vref['system'] + '\n\n' + _VED_LANG + _blk})
ADDED_LATER |= set(_VED)
_TRIM_OLD = {}
_RENAME = {'video-h3s': ('H3 视频提示词（秋叶写法）', 'H3 视频提示词（结构化写法）')}  # 2026-11-08 用户：不再叫“秋叶写法”
for _p in DEFAULT_PRESETS:
    if _p['id'] in _TRIM:
        _TRIM_OLD[_p['id']] = _p['system']
        _p['system'] = _TRIM[_p['id']]
    if _p['id'] in _RENAME:
        _p['name'] = _RENAME[_p['id']][1]


def load_presets(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, list) and d:
            for x in d:  # 精简过的 H3 视频预设（2026-11-04）：没改过的换成新版；名字没改过的跟着改名
                if isinstance(x, dict) and x.get('id') in _TRIM_OLD and x.get('system') == _TRIM_OLD[x['id']]:
                    x['system'] = _TRIM[x['id']]
                if isinstance(x, dict) and x.get('id') in _RENAME and x.get('name') == _RENAME[x['id']][0]:
                    x['name'] = _RENAME[x['id']][1]
            for x in d:  # 视频预设加了“素材说明”的写法（2026-11-04）：没改过的（和上一版一样）换成新版；更早的版本先在下面换成上一版，再换一次
                if isinstance(x, dict) and x.get('id') in _V_OLD and x.get('system') in (_V_OLD[x['id']], _OLD_SYSTEMS.get(x['id']), _PREV_SYSTEMS.get(x['id'])):
                    x['system'] = next(p['system'] for p in DEFAULT_PRESETS if p['id'] == x['id'])
            for x in d:  # 没改过的旧默认预设：换成新版
                if isinstance(x, dict) and x.get('id') in _NEW_SYSTEMS and x.get('system') in (_OLD_SYSTEMS.get(x.get('id')), _PREV_SYSTEMS.get(x.get('id'))):
                    x['system'] = _NEW_SYSTEMS[x['id']]
            d = [x for x in d if not (isinstance(x, dict) and x.get('id') == 'img-edit' and x.get('system') in _IMG_EDIT_DEFAULTS)]
            d = [x for x in d if not (isinstance(x, dict) and x.get('id') == 'video-h3' and x.get('system') in _VH3_DEFAULTS)]  # 删掉的“官方格式”：没改过的旧副本去掉
            for x in d:  # 参考写法去掉“脸始终清晰”、加底稿说明（2026-11-08）：没改过的旧副本换成新版
                if isinstance(x, dict) and x.get('id') in _VREF_OLD and x.get('system') in (_VREF_OLD[x['id']], _VREF_MID.get(x['id'])):
                    x['system'] = next(p['system'] for p in DEFAULT_PRESETS if p['id'] == x['id'])
            for x in d:  # 指令改图预设的旧写法（image 1）：没改过的换成新版（Picture 1）
                if isinstance(x, dict) and x.get('id') == 'img-qedit' and isinstance(x.get('system'), str) and x['system'] in (_QED_OLD, _QED_PREV):
                    x['system'] = next(p['system'] for p in DEFAULT_PRESETS if p['id'] == 'img-qedit')  # 没改过的旧“图生图 / 改图”：换成拆开的三个
            have = {x.get('id') for x in d if isinstance(x, dict)}
            d = [x for x in d if not (isinstance(x, dict) and x.get('id') in REMOVED)]
            for k, dp in enumerate(DEFAULT_PRESETS):  # 后来新加的默认预设（比如“图生图”）：自己保存过预设的也补上
                if dp['id'] in ADDED_LATER and dp['id'] not in have:
                    d.insert(min(k, len(d)), dict(dp))
            return d
    except (OSError, ValueError):
        pass
    return [dict(p) for p in DEFAULT_PRESETS]

PRESET_CATS = ('img', 'edit', 'video', 'vedit', 'describe', 'tts', 'polish', 'chat')  # vedit：改视频（2026-11-09 从“视频”分出来）


def save_presets(path, items, write_json):
    clean = []
    for p in (items if isinstance(items, list) else [])[:100]:
        if not isinstance(p, dict):
            continue
        name = str(p.get('name') or '').strip()[:40]
        system = str(p.get('system') or '').strip()[:16000]  # 官方增强小模型的系统提示词约 1.1 万字
        if not name:  # system 可以为空 = 不带 system prompt，直接对话
            continue
        clean.append({'id': str(p.get('id') or uuid.uuid4().hex[:8])[:40], 'name': name, 'target': p.get('target') if p.get('target') in ('img', 'tts', 'video') else '',
                      'system': system, **({'cat': p['cat']} if p.get('cat') in PRESET_CATS else {})})  # cat：编辑预设里选的主要用途（7 类，见 app.js PG_CATS）
    if not clean:
        raise ValueError('至少需保留一个预设')
    with _plock:
        write_json(path, clean, indent=1)
    return clean


# ---------------------------------------------------------------- 生成（流式）
def clamp_params(p):
    p = p if isinstance(p, dict) else {}
    ok = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float('inf')
    num = lambda k, lo, hi, kind=float: max(lo, min(hi, kind(p[k]))) if ok(p.get(k)) else GEN_DEFAULTS[k]
    out = {'temperature': num('temperature', 0.0, 2.0), 'top_p': num('top_p', 0.0, 1.0), 'top_k': num('top_k', 0, 200, int), 'min_p': num('min_p', 0.0, 1.0),
           'presence_penalty': num('presence_penalty', -2.0, 2.0), 'repeat_penalty': num('repeat_penalty', 0.5, 2.0), 'max_tokens': num('max_tokens', 16, 8192, int),
           'seed': num('seed', -1, 2 ** 31 - 1, int), 'thinking': bool(p.get('thinking', GEN_DEFAULTS['thinking'])),
           'effort': p.get('effort') if p.get('effort') in ('low', 'medium', 'xhigh') else GEN_DEFAULTS['effort'],
           'think_budget': num('think_budget', -1, 16384, int),
           'frequency_penalty': num('frequency_penalty', -2.0, 2.0), 'repeat_last_n': num('repeat_last_n', -1, 8192, int),
           'typical_p': num('typical_p', 0.0, 1.0), 'top_n_sigma': num('top_n_sigma', -1.0, 5.0),
           'dynatemp_range': num('dynatemp_range', 0.0, 2.0), 'dynatemp_exponent': num('dynatemp_exponent', 0.0, 5.0),
           'xtc_probability': num('xtc_probability', 0.0, 1.0), 'xtc_threshold': num('xtc_threshold', 0.0, 0.5),
           'dry_multiplier': num('dry_multiplier', 0.0, 5.0), 'dry_base': num('dry_base', 1.0, 4.0),
           'dry_allowed_length': num('dry_allowed_length', 1, 20, int), 'dry_penalty_last_n': num('dry_penalty_last_n', -1, 8192, int)}
    return out


def clamp_engine(c):
    c = c if isinstance(c, dict) else {}
    E = ENGINE_DEFAULTS
    ok = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v == v
    num = lambda k, lo, hi, kind=int: max(lo, min(hi, kind(c[k]))) if ok(c.get(k)) else E[k]
    ctx = c.get('ctx') if isinstance(c.get('ctx'), int) else E['ctx']
    img_min, img_max = num('img_min', 0, 16384), num('img_max', 0, 16384)
    if img_max and img_min > img_max:
        img_min = img_max
    return {'ctx': max(2048, min(CTX_CHOICES[-1], ctx // 1024 * 1024)), 'kv': c.get('kv') if c.get('kv') in KV_TYPES else E['kv'],
            'mtp': bool(c.get('mtp', E['mtp'])), 'draft_n': num('draft_n', 1, 8), 'draft_pmin': round(num('draft_pmin', 0.0, 1.0, float), 2),
            'ubatch': c.get('ubatch') if c.get('ubatch') in UBATCH_CHOICES else E['ubatch'], 'img_min': img_min, 'img_max': img_max,
            'gpu': c.get('gpu') if c.get('gpu') in ('all', 'fit') else E['gpu'],
            'model': c.get('model') if c.get('model') in llm_models() else DEFAULT_MODEL}


def vision(mid=None):
    m = model_info(mid)
    return bool(m and m.get('mmproj') and os.path.isfile(config.models(m.get('dir') or '', m['mmproj'])))


MAX_IMAGES = 4  # 一条消息最多带几张图（多图改图最多 3 张，再留一张余量）
MAX_VIDEO_FRAMES = 8  # 看整段视频时一条消息最多几帧（网页默认均匀取 6 帧）


def _imgs(m):
    """一条消息带的图：新的是 images 列表，旧的是 image 一张"""
    raw = m.get('images') if isinstance(m.get('images'), list) else [m.get('image')]
    many = isinstance(m.get('video'), dict) or isinstance(m.get('labels'), list)  # 整段视频 / 生视频的素材：最多 8 张
    return [x for x in raw if isinstance(x, str) and x.startswith('data:image/') and len(x) < 8_000_000][:MAX_VIDEO_FRAMES if many else MAX_IMAGES]


def _mats(m, n_img):
    """生视频带来的素材：图按顺序各是什么（labels），再加上声音、时长这些文字说明（mats）"""
    lab = [str(x)[:300] for x in m.get('labels')] if isinstance(m.get('labels'), list) else []
    head = []
    if lab and n_img:
        head.append('附带的图按顺序是：' + '；'.join(f'图 {i + 1} = {t}' for i, t in enumerate(lab[:n_img]) if t))
    if isinstance(m.get('mats'), str) and m['mats'].strip():
        head.append(m['mats'].strip()[:3000])
    return ('【' + '\n'.join(head) + '】\n') if head else ''


def _content(m, keep_img):
    """一条消息 → 发给模型的内容。只有最新那条消息的图真的发过去（省显存），更早的图换成“[图片]”。
    多张图按顺序发，模型看到的是第 1、2、3 张（和多图改图的 Picture 1 / 2 / 3 对应）"""
    text = str(m.get('content') or '')[:20000]
    imgs = _imgs(m)
    if imgs and keep_img and vision():
        parts = [{'type': 'image_url', 'image_url': {'url': u}} for u in imgs]
        v = m.get('video') if isinstance(m.get('video'), dict) else None
        if v:  # 整段视频：告诉模型这是同一段视频按时间顺序抽的几帧，各在第几秒
            ts = [t for t in (v.get('times') or []) if isinstance(t, (int, float))][:len(imgs)]
            dur = v.get('dur') if isinstance(v.get('dur'), (int, float)) else None
            text = (f'（这是一段{f" {dur:.1f} 秒的" if dur else ""}视频按时间顺序均匀抽出的 {len(imgs)} 帧' + (f'，分别在第 ' + '、'.join(f'{t:g}' for t in ts) + ' 秒' if ts else '')
                    + '。请把它们当成连续的一段视频来理解：人物、动作、镜头怎么变化。）\n' + text)
            return [{'type': 'image_url', 'image_url': {'url': u}} for u in imgs] + [{'type': 'text', 'text': text or '请描述这段视频'}]
        if isinstance(m.get('labels'), list):  # 生视频的素材：每张图是什么都写清楚
            return parts + [{'type': 'text', 'text': _mats(m, len(imgs)) + (text or '请按这些素材写视频提示词')}]
        if len(imgs) > 1:  # 告诉模型图的顺序，提示词里才好说“图 1 的人、图 2 的衣服”
            text = f'（共 {len(imgs)} 张图，按顺序是图 1、图 2' + ('、图 3' if len(imgs) > 2 else '') + ('、图 4' if len(imgs) > 3 else '') + '）\n' + text
        return parts + [{'type': 'text', 'text': text or ('请描述这张图' if len(imgs) == 1 else '请描述这几张图')}]
    n = len(imgs) or (1 if m.get('had_image') else 0)
    text = _mats(m, 0) + text  # 没发图（模型不识图 / 较早的消息）：素材的文字说明照样带上
    return (('[图片] ' if n <= 1 else f'[{n} 张图片] ') + text) if n else text


def build_messages(messages, system):
    """Preview and inference share the same message preparation, without loading a model."""
    rows = [m for m in messages[-40:] if m.get('role') in ('user', 'assistant') and (m.get('content') or m.get('image') or m.get('images'))]
    last_img = max([i for i, m in enumerate(rows) if m.get('role') == 'user' and _imgs(m)], default=-1)
    msgs = ([{'role': 'system', 'content': system}] if system else []) + [
        {'role': m['role'], 'content': _content(m, i == last_img)} for i, m in enumerate(rows)]
    if not msgs or msgs[-1]['role'] != 'user':
        raise ValueError('请先写明您想要的内容')
    return msgs


def chat_stream(messages, system, params, engine_cfg, cancel, own_gpu=False):
    """边写边返回：('reasoning' | 'text', 片段)；最后一个是 ('done', 统计)。cancel() 返回 True 时停下。
    own_gpu：调用的地方已经拿着显卡（视频任务里看图写保留的衣物，2026-11-10）——不再进 GPU_CTX、不等配音：
    视频任务拿着生图那把锁，GPU_CTX 里的“让生图让开”会等这把锁，自己等自己就卡死了"""
    msgs = build_messages(messages, system)
    global _hold
    counted, held = False, False
    try:
        with (GPU_CTX() if GPU_CTX and not own_gpu else _null()):
            with _hold_lock:
                _hold += 1
            held = True
            # 2) 配音 / 识别 / 翻译正在用显卡：等它们用完再载入（不然 18GB 的模型挤进去，两边都可能显存不够）。
            #    等的时候还不算“正在写”：配音那边要用显卡时不会反过来等这里
            t0, told = time.time(), False
            while True:
                with Engine.cv:  # 看一眼和占上放在一起，中间不会被配音插进来
                    if own_gpu or OTHERS() - _hold <= 0:
                        Engine.busy += 1
                        counted = True
                        break
                if cancel() or time.time() - t0 > 1800:
                    raise RuntimeError('配音 / 识别持续占用显卡，请稍后再试')
                if not told:
                    told = True
                    yield 'wait', '配音 / 识别正在用显卡，等它用完…'
                else:
                    yield 'ping', None  # 每秒发一下：网页关了能马上发现，不会白占着显卡等半小时
                time.sleep(1)
            Engine.ensure(engine_cfg)
            Engine.last = time.time()
            body = {'messages': msgs, 'stream': True, 'temperature': params['temperature'], 'top_p': params['top_p'], 'top_k': params['top_k'],
                    'min_p': params['min_p'], 'presence_penalty': params['presence_penalty'], 'repeat_penalty': params['repeat_penalty'],
                    'max_tokens': params['max_tokens'], 'chat_template_kwargs': {'enable_thinking': params['thinking']}}
            # 其余采样参数：和引擎默认不一样的才发
            for k in ('frequency_penalty', 'repeat_last_n', 'typical_p', 'top_n_sigma', 'dynatemp_range', 'dynatemp_exponent',
                      'xtc_probability', 'xtc_threshold', 'dry_multiplier', 'dry_base', 'dry_allowed_length', 'dry_penalty_last_n'):
                if params.get(k, GEN_DEFAULTS[k]) != GEN_DEFAULTS[k] or (k.startswith('dry_') and params.get('dry_multiplier')):
                    body[k] = params[k]
            if params['thinking']:  # 推理过程也算在 max_tokens 里：另外给推理留 预算（不限时 3000），不挤占正文（不超过上下文长度）
                tb = params.get('think_budget', -1)
                body['max_tokens'] = min(params['max_tokens'] + (tb if tb >= 0 else 3000), max(1024, int(engine_cfg.get('ctx', 8192)) - 1500))
                body['chat_template_kwargs']['reasoning_effort'] = params['effort']
                if tb >= 0:
                    body['thinking_budget_tokens'] = body['reasoning_budget_tokens'] = tb
            if params['seed'] >= 0:
                body['seed'] = params['seed']
            req = urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions', json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         {'Content-Type': 'application/json'})
            t0, n, rs, tm = time.time(), 0, False, {}
            with urllib.request.urlopen(req, timeout=900) as r:
                for raw in r:
                    if cancel():
                        break
                    line = raw.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        break
                    try:
                        d = json.loads(data)
                    except ValueError:
                        continue
                    if isinstance(d.get('timings'), dict):  # 最后一块带速度统计
                        tm = d['timings']
                    delta = (d.get('choices') or [{}])[0].get('delta') or {}
                    r = delta.get('reasoning_content')
                    if r and (rs or r.strip()):  # 关着思考时模板也常先发一个换行：开头的空白不算思考（网页会多出一个空的“思考过程”）
                        rs = True
                        yield 'reasoning', r
                    if delta.get('content'):
                        n += 1
                        yield 'text', delta['content']
                    Engine.last = time.time()
            st = {'seconds': round(time.time() - t0, 1), 'chunks': n}
            g = lambda k: tm.get(k) if isinstance(tm.get(k), (int, float)) else None
            if g('predicted_per_second'):
                st['tps'] = round(g('predicted_per_second'), 1)
            if g('prompt_per_second') and (g('prompt_n') or 0) > 32:
                st['pps'] = round(g('prompt_per_second'))
            if g('draft_n'):
                st['mtp'] = round(100 * (g('draft_n_accepted') or 0) / g('draft_n'))
            yield 'done', st
    finally:
        Engine.last = time.time()
        if counted:
            with Engine.cv:
                Engine.busy -= 1
                Engine.cv.notify_all()
        if held:
            with _hold_lock:
                _hold -= 1


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def vram_item():
    if not Engine.running():
        return None
    return {'id': 'prompt', 'name': '提示词模型（Qwen3.8 27B）', 'mb': 18500 + Engine.cfg['ctx'] // 32 if Engine.cfg else 18500}
