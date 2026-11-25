"""语音转文字（Qwen3-ASR / Whisper）与大模型校对。被 server.py 调用。"""
import contextlib, datetime, difflib, hashlib, json, os, re, subprocess, sys, threading, time, traceback, urllib.error, urllib.request, uuid

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
PYLIB = os.path.join(STUDIO, 'pylib')
SETTINGS = os.path.join(STUDIO, 'settings.json')
STT_DIR = os.path.join(ROOT, 'outputs', 'stt')
FFMPEG = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
if not os.environ.get('STUDIO_DEFER_DIRS'):  # 测试启动器改好路径后自己建（F05）
    os.makedirs(STT_DIR, exist_ok=True)


GPU_CTX = contextlib.nullcontext  # 由 server.py 换成“用显卡的这一段：生图先让开，用完前不开始新的生图”
SET_SPACE = lambda sp: None  # 由 server.py 换成：设置当前线程所在的空间


def act(msg, tag='', level='info'):  # 由 server.py 替换成网页运行日志
    pass

DEFAULT_SETTINGS = {
    'llm_provider': 'anthropic',        # anthropic | openai_compat | local（本地提示词模型，离线）
    'anthropic_api_key': '',
    'anthropic_model': 'claude-opus-5-5',
    'openai_base_url': '',
    'openai_api_key': '',
    'openai_model': '',
    'whisper_exe': 'D:/App/PotPlayer/Engine/Faster-Whisper-XXL/faster-whisper-xxl.exe',
    'whisper_model_dir': 'D:/App/PotPlayer/Model',
    'whisper_model': 'large-v3-turbo',
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.load(open(SETTINGS, encoding='utf-8')))
    except (OSError, ValueError):
        pass
    return s


_settings_lock = threading.Lock()  # 2026-11-17 审查 F19：两个请求同时改不同的设置，以前读改写没锁、共用一个 .tmp，可能丢一个


def save_settings(new):
    with _settings_lock:
        return _save_settings(new)


def _save_settings(new):
    s = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in new and new[k] is not None:
            v = str(new[k]).strip()
            if k in ('whisper_exe', 'whisper_model_dir') and v.startswith(('\\', '//')):
                continue  # 只用这台电脑上的 Whisper，不接受网络路径
            if k == 'whisper_exe' and v and not v.lower().endswith('.exe'):
                continue
            s[k] = v
    tmp = f'{SETTINGS}.{uuid.uuid4().hex[:6]}.tmp'  # 先写临时文件再替换：写到一半出错也不会把密钥、设置清空（每次一个名字）
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return s


def public_settings():
    """给网页看的设置：不回传完整密钥。"""
    s = load_settings()
    out = {k: v for k, v in s.items() if not k.endswith('api_key')}
    for k in ('anthropic_api_key', 'openai_api_key'):
        out[k + '_set'] = bool(s[k])
        out[k + '_hint'] = (s[k][:7] + '…' + s[k][-4:]) if len(s[k]) > 14 else ''
    out['whisper_available'] = whisper_available(s)
    return out


def whisper_available(s=None):
    s = s or load_settings()
    return os.path.isfile(s['whisper_exe']) and os.path.isdir(os.path.join(s['whisper_model_dir'], 'faster-whisper-' + s['whisper_model']))


def ffmpeg(*args):
    p = subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError('ffmpeg 处理失败：' + p.stderr[-300:])


def media_seconds(path):
    p = subprocess.run([FFMPEG.replace('ffmpeg.exe', 'ffprobe.exe'), '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', path], capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def media_fp(path):
    """文件指纹：大小 + 开头和结尾各 1MB 的 SHA-1。同一个文件不管放在哪、叫什么名字都一样（几 GB 的视频也只读 2MB）。"""
    n = os.path.getsize(path)
    h = hashlib.sha1(str(n).encode())
    with open(path, 'rb') as f:
        h.update(f.read(1 << 20))
        if n > 2 << 20:
            f.seek(-(1 << 20), 2)
            h.update(f.read(1 << 20))
        elif n > 1 << 20:  # 2026-11-14 审查：1～2 MB 的文件以前后半段不算进去（后半段不一样也会当成同一个）；超过 2 MB 的算法不变，旧缓存照样能用
            h.update(f.read())
    return h.hexdigest()


def srt_sents(path):
    """Whisper 的 .srt → 字幕句 [{'s','e','text'}]"""
    out = []
    ts = lambda x: sum(float(v) * k for v, k in zip(x.replace(',', '.').split(':'), (3600, 60, 1)))
    for block in re.split(r'\n\s*\n', open(path, encoding='utf-8', errors='replace').read().strip()):
        m = re.search(r'([\d:,.]+)\s*-->\s*([\d:,.]+)\s*\n(.*)', block, re.S)
        if m:
            t = ' '.join(m.group(3).split())
            if t:
                out.append({'s': round(ts(m.group(1)), 3), 'e': round(ts(m.group(2)), 3), 'text': t})
    return out


# ================================================================ 转写任务
stt_jobs = {}
WHISPER_COMPUTE = ['float32', 'float16', 'int8_float16', 'auto']


def clean_opts(o):
    """转写选项（网页传来的）：prompt = 专有名词 / 背景（两个引擎都用），其余只对 Whisper 有效。"""
    o = o if isinstance(o, dict) else {}
    num = lambda k, lo, hi, d: max(lo, min(hi, int(o[k]))) if isinstance(o.get(k), (int, float)) and not isinstance(o.get(k), bool) and abs(o[k]) < 1e9 else d
    return {'prompt': ' '.join(str(o.get('prompt') or '').split())[:600], 'hotwords': ' '.join(str(o.get('hotwords') or '').split())[:300],
            'vocal': bool(o.get('vocal')), 'batched': bool(o.get('batched')), 'batch_size': num('batch_size', 1, 32, 8),
            'split': o.get('split') if o.get('split') in ('sentence', 'asia') else '', 'max_line_width': num('max_line_width', 0, 200, 0),
            'max_line_count': num('max_line_count', 0, 10, 0),
            'compute': o.get('compute') if o.get('compute') in WHISPER_COMPUTE else 'float32'}


import stages  # 任务计时（每一步用了多久）


class SttJob(stages.Tracked):
    def __init__(self, src_path, filename, engine_name, language, transcribe_fn, root=None, space='n', opts=None):
        self.id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.opts = clean_opts(opts)  # 专有名词提示、Whisper 的人声提取 / 批量 / 断句 / 精度
        self.space = space  # 'v' = 私密空间：存在单独的目录，普通界面看不到
        self.dir = os.path.join(root or STT_DIR, self.id)
        os.makedirs(self.dir)
        self.src, self.filename, self.engine, self.language = src_path, filename, engine_name, language
        self.transcribe_fn = transcribe_fn
        self.state, self.message, self.error = 'running', '正在准备音频', ''
        self.created, self.finished, self.duration = time.time(), None, None
        self.text, self.corrected, self.has_srt = '', '', False
        self.fp, self.has_subs = None, False  # 文件指纹 + 带时间的字幕：播放页放同一个文件时直接用这份字幕
        stt_jobs[self.id] = self  # 先登记再开始，日志才能认出它属于哪个空间
        self.save()  # 开始前先存一份（2026-11-17 审查 F14：以前做完才第一次写 stt.json，中途被关掉整条历史就没了）
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        SET_SPACE(self.space)  # 这个线程里的日志、缓存算在任务所在的空间
        try:
            wav = os.path.join(self.dir, 'audio16k.wav')
            try:
                self.fp = media_fp(self.src)
            except OSError:
                pass
            act(f'转写 {self.filename}：提取音频并转成 16kHz 单声道', self.id)
            ffmpeg('-i', self.src, '-vn', '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', wav)
            self.duration = media_seconds(wav)
            self.save()  # 音频准备好了：识别时被关掉，重启后也能看到这条（中断）
            act(f'音频时长 {(self.duration or 0) / 60:.1f} 分钟，开始识别（{"Whisper large-v3-turbo" if self.engine == "whisper" else "Qwen3-ASR 1.7B"}）', self.id)
            t0 = time.time()
            if self.engine == 'whisper':
                self.message = '正在用 Whisper 识别（较慢）'
                with GPU_CTX():  # Whisper 是单独的进程：也要先让生图把显卡让出来
                    self.text = self.run_whisper(wav)
            else:
                self.message = '正在用 Qwen3-ASR 识别'
                with GPU_CTX():
                    res = self.transcribe_fn(wav, self.id, self.language)
                if isinstance(res, tuple):  # (文字, 带时间的字幕)
                    self.text, subs = res
                    if subs and subs.get('sents'):
                        json.dump(subs, open(os.path.join(self.dir, 'subs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
                        self.has_subs = True
                else:
                    self.text = res
            act(f'识别完成：{len(self.text)} 字，用时 {time.time() - t0:.1f} 秒', self.id, 'ok')
            with open(os.path.join(self.dir, 'transcript.txt'), 'w', encoding='utf-8') as f:
                f.write(self.text)
            self.state, self.message = 'done', '完成'
        except Exception as e:
            if self.space != 'v':  # 私密空间的出错信息不打印到日志
                traceback.print_exc()
            self.state, self.error, self.message = 'error', str(e), '出错：' + str(e)
            act('出错：' + str(e), self.id, 'error')
        finally:
            for f in (self.src, os.path.join(self.dir, 'audio16k.wav')):  # 16k 临时 wav 出错时也删（以前只在成功时删，2026-11-15 审查）
                try:
                    os.remove(f)
                except OSError:
                    pass
        self.finished = time.time()
        self.save()

    def run_whisper(self, wav):
        s, o = load_settings(), getattr(self, 'opts', None) or clean_opts(None)
        # RTX 50 系上 Faster-Whisper-XXL 自带的旧 cuBLAS 不支持 float16/int8，默认用 float32（可以在高级选项里换）
        args = [s['whisper_exe'], wav, '--model', s['whisper_model'], '--model_dir', s['whisper_model_dir'],
                '--device', 'cuda', '--compute_type', o['compute'], '--output_dir', self.dir,
                '--output_format', 'txt', 'srt', '--beep_off']
        if self.language and self.language != 'auto':
            args += ['-l', self.language]
        if o['prompt']:  # 人名、术语、背景：减少同音字和专名错误
            args += ['--initial_prompt', o['prompt']]
        if o['hotwords']:
            args += ['--hotwords', o['hotwords']]
        if o['vocal']:  # 先分离掉背景音乐（第一次用会自动下载 MDX 模型）
            args += ['--ff_vocal_extract', 'mdx_kim2']
        if o['batched']:
            args += ['--batched', '--batch_size', str(o['batch_size'])]
        if o['split'] == 'sentence':
            args += ['--sentence']
        elif o['split'] == 'asia':
            args += ['--standard_asia']
        if o['max_line_width']:
            args += ['--max_line_width', str(o['max_line_width'])]
            if o.get('max_line_count'):  # 只在限定了每行字数时有效
                args += ['--max_line_count', str(o['max_line_count'])]
        try:  # 正常远快于实时；卡住时不能一直占着显卡（生图会一直等）
            p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW,
                               timeout=max(1800, (self.duration or 0) * 2))
        except subprocess.TimeoutExpired:
            raise RuntimeError('Whisper 长时间未完成，已停止（可改用 Qwen3-ASR 尝试）')
        txt = os.path.join(self.dir, 'audio16k.txt')
        if not os.path.exists(txt):  # XXL 版有时写完文件后退出码仍非 0，以输出文件为准
            raise RuntimeError('Whisper 运行失败：' + (p.stderr or p.stdout)[-400:])
        raw = open(txt, encoding='utf-8', errors='replace').read()
        os.remove(txt)
        lines = [re.sub(r'^\s*\[[\d:.]+\s*-->\s*[\d:.]+\]\s*', '', ln).strip() for ln in raw.splitlines()]
        text = '\n'.join(ln for ln in lines if ln)
        srt = os.path.join(self.dir, 'audio16k.srt')
        if os.path.exists(srt):
            os.replace(srt, os.path.join(self.dir, 'transcript.srt'))
            self.has_srt = True
            sents = srt_sents(os.path.join(self.dir, 'transcript.srt'))
            if sents:
                json.dump({'sents': sents, 'language': self.language if self.language != 'auto' else None},
                          open(os.path.join(self.dir, 'subs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
                self.has_subs = True
        return text

    def save(self):
        p = os.path.join(self.dir, 'stt.json')
        tmp = f'{p}.{uuid.uuid4().hex[:6]}.tmp'  # 原子写入：中途断掉不会留下半个记录
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.summary(full=True), f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)

    def summary(self, full=False):
        d = {'id': self.id, 'filename': self.filename, 'engine': self.engine, 'state': self.state, 'message': self.message,
             'error': self.error, 'created': self.created, 'finished': self.finished, 'duration': self.duration,
             'has_srt': self.has_srt, 'chars': len(self.text), 'language': self.language, 'fp': self.fp, 'has_subs': self.has_subs, 'timing': self.timing()}
        if full:
            d['text'], d['corrected'] = self.text, self.corrected
        return d


def load_old_stt(root=None, space='n'):
    root = root or STT_DIR
    os.makedirs(root, exist_ok=True)
    for name in sorted(os.listdir(root)):
        try:
            d = json.load(open(os.path.join(root, name, 'stt.json'), encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or not d.get('id'):  # 2026-11-14 审查：结构不对的记录（比如 {}）以前会让启动直接报错
            continue
        j = SttJob.__new__(SttJob)
        j.__dict__.update({k: d.get(k) for k in ('id', 'filename', 'engine', 'state', 'message', 'error', 'created', 'finished',
                                                  'duration', 'has_srt', 'language', 'fp', 'has_subs')})
        j.dir, j.text, j.corrected, j.src = os.path.join(root, d['id']), d.get('text', ''), d.get('corrected', ''), ''
        j.space = space
        if j.state == 'running':
            j.state, j.message = 'error', '上次未完成（程序被关闭）'
            j.finished = j.finished or d.get('created')
        j.restore_timing(d.get('timing'), j.created, j.finished)  # 计时用存下来的，不重新开始（F13）
        stt_jobs[j.id] = j


# ================================================================ 大模型校对
SYSTEM_PROMPT = """你是中文语音识别（ASR）转写稿的校对员。转写稿由语音识别自动生成，会有识别错误。

你的任务：只修正明显的识别错误，主要是——
1. 同音字、近音字错误（例如“林州”应为“林舟”、“在”与“再”混用）；
2. 人名、地名、专有名词、术语的错误写法（请结合上下文和用户提供的背景信息判断）；
3. 明显错误或缺失的标点、断句。

必须遵守：
- 不要改写、润色、精简或扩写，不要改变说话人的口语风格和用词习惯（“嗯”“啊”“就是”等口头语保留）；
- 不要增删内容，不要合并或调换句子顺序；
- 拿不准的地方保持原样；
- 只输出校对后的正文，不要解释，不要加任何标题、引号或标记。"""


def split_for_llm(text, size=1500):
    parts, cur = [], ''
    for piece in re.split(r'(?<=[。！？!?\n])', text):
        if cur and len(cur) + len(piece) > size:
            parts.append(cur); cur = ''
        cur += piece
    if cur:
        parts.append(cur)
    return parts


def build_user_message(chunk, context, background):
    msg = ''
    if background.strip():
        msg += f'【背景信息（人名、术语等，供参考）】\n{background.strip()}\n\n'
    if context:
        msg += f'【上文（只用于理解上下文，不要输出这部分）】\n{context}\n\n'
    msg += f'【待校对的转写稿】\n{chunk}\n\n请只输出“待校对的转写稿”校对后的全文。'
    return msg


def call_anthropic(s, system, user):
    if PYLIB not in sys.path:
        sys.path.insert(0, PYLIB)
    import anthropic
    if not s['anthropic_api_key']:
        raise RuntimeError('尚未填写 Claude 的 API Key（右上角“AI 校对设置”）')
    client = anthropic.Anthropic(api_key=s['anthropic_api_key'])
    model = s['anthropic_model'] or 'claude-opus-5-5'
    kw = dict(model=model, max_tokens=64000, system=system, messages=[{'role': 'user', 'content': user}],
              output_config={'effort': 'medium'})
    try:
        if model.startswith('claude-haiku'):
            with client.messages.stream(**kw) as stream:  # Haiku 没有服务端拒答回退
                msg = stream.get_final_message()
        else:
            # 遇到安全分类器误拒时，由服务端自动换到推荐的备用模型重试
            with client.beta.messages.stream(betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'}, **kw) as stream:
                msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise RuntimeError('Claude API Key 无效，请检查设置')
    except anthropic.PermissionDeniedError:
        raise RuntimeError('该 API Key 没有调用此模型的权限')
    except anthropic.NotFoundError:
        raise RuntimeError(f'找不到模型 {model}，请检查模型名')
    except anthropic.RateLimitError:
        raise RuntimeError('请求太频繁或额度不足，请稍后再试')
    except anthropic.APIStatusError as e:
        raise RuntimeError(f'Claude 接口错误（{e.status_code}）：{e.message}')
    except anthropic.APIConnectionError:
        raise RuntimeError('无法连接 Claude 接口，请检查网络或代理')
    if msg.stop_reason == 'refusal':
        raise RuntimeError('Claude 拒绝处理这段内容')
    if msg.stop_reason == 'max_tokens':
        raise RuntimeError('输出被截断，请缩短文本后再试')
    return ''.join(b.text for b in msg.content if b.type == 'text').strip()


def call_openai_compat(s, system, user):
    base = (s['openai_base_url'] or '').rstrip('/')
    if not base or not s['openai_model']:
        raise RuntimeError('请先在“AI 校对设置”里填写接口地址和模型名')
    body = json.dumps({'model': s['openai_model'], 'temperature': 0.2, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]},
                      ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if s['openai_api_key']:
        headers['Authorization'] = 'Bearer ' + s['openai_api_key']
    req = urllib.request.Request(base + '/chat/completions', body, headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'接口返回错误（{e.code}）：{e.read().decode("utf-8", "replace")[:300]}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'无法连接接口：{e.reason}')
    return (data['choices'][0]['message']['content'] or '').strip()


LOCAL_CHAT = None  # 由 server.py 换成：用本地提示词模型（Qwen3.8 27B）写一次回答 (system, user) -> 文字
LOCAL_NAME = '本地 Qwen3.8 27B'


def call_local(s, system, user):
    if not LOCAL_CHAT:
        raise RuntimeError('本地提示词模型不可用')
    return (LOCAL_CHAT(system, user) or '').strip()


def correct_text(text, background='', tag=''):
    s = load_settings()
    prov = s['llm_provider']
    call = call_anthropic if prov == 'anthropic' else call_local if prov == 'local' else call_openai_compat
    name = ('Claude · ' + s['anthropic_model']) if prov == 'anthropic' else LOCAL_NAME if prov == 'local' else s['openai_model']
    parts, out, prev = split_for_llm(text), [], ''
    act(f'AI 校对：{name}，共 {len(text)} 字，分 {len(parts)} 段发送', tag)
    for k, chunk in enumerate(parts, 1):
        t0 = time.time()
        act(f'→ 发送第 {k}/{len(parts)} 段（{len(chunk)} 字）…', tag)
        fixed = call(s, tplstore.T('STT_SYS'), build_user_message(chunk, prev[-200:], background))
        act(f'← 第 {k} 段返回，用时 {time.time() - t0:.1f} 秒', tag)
        out.append(fixed)
        prev = chunk
    return ''.join(out)


def diff_ops(a, b):
    """字符级差异，供网页高亮：[['eq'|'del'|'ins', 文本], ...]"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            ops.append(['eq', a[i1:i2]])
        else:
            if i2 > i1:
                ops.append(['del', a[i1:i2]])
            if j2 > j1:
                ops.append(['ins', b[j1:j2]])
    return ops


def copy_prompt(text, background=''):
    """给“复制给 AI”按钮用：一段可以直接粘贴到任意聊天 AI 的完整提示词。"""
    return tplstore.T('STT_SYS') + '\n\n' + build_user_message(text, '', background)


# 2026-11-09 模板套：AI 校对的系统指令登记到 tplstore
import tplstore
tplstore.register('stt', 'stt_sys', '系统指令', [('STT_SYS', 'zh')], {'pos': {'STT_SYS': SYSTEM_PROMPT}}, group='AI 校对', sys=True)
