"""字幕翻译，两种引擎：
- google：谷歌翻译的免费网页接口（translate.googleapis.com，无需 Key）。只把字幕文字发给谷歌，不发送音频或文件。
- local：本地的 Index-Translate-9B（bilibili Index 团队的翻译专用模型，150 种语言），用 llama.cpp 在显卡上跑，完全离线。
  第一次用时自动启动，闲置 10 分钟自动退出、释放显存。
都是几十句拼成一批发送，按换行拆回每一句；对不上时这一批逐句重发。"""
import contextlib, atexit, json, os, subprocess, threading, time, urllib.error, urllib.parse, urllib.request
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # 用 -I 启动时脚本所在的文件夹不在搜索路径里
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLAMA = config.LLAMA_SERVER
LOCAL_MODEL = config.models('Index-Translate-9B-GGUF', 'Index-Translate-9B.Q4_K_M.gguf')
LOCAL_PORT = 8093  # 和生图引擎（8091）分开
IDLE_EXIT = 600
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
# 本地模型的提示词里用中文写目标语言（官方推荐的写法）
LANG_ZH = {'zh-CN': '简体中文', 'zh-TW': '繁体中文', 'en': '英语', 'ja': '日语', 'ko': '韩语', 'fr': '法语', 'de': '德语', 'es': '西班牙语',
           'ru': '俄语', 'pt': '葡萄牙语', 'it': '意大利语', 'th': '泰语', 'vi': '越南语', 'id': '印尼语', 'ar': '阿拉伯语'}

URL = 'https://translate.googleapis.com/translate_a/single'
BATCH_CHARS = 1800


def _call(text, to, src='auto'):
    qs = urllib.parse.urlencode({'client': 'gtx', 'sl': src or 'auto', 'tl': to, 'dt': 't', 'dj': '1', 'ie': 'UTF-8', 'oe': 'UTF-8'})
    req = urllib.request.Request(URL + '?' + qs, urllib.parse.urlencode({'q': text}).encode('utf-8'),
                                 {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'谷歌翻译返回错误（{e.code}），请稍后再试')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f'无法连接谷歌翻译：{getattr(e, "reason", e)}（请检查网络或代理）')
    return ''.join(s.get('trans', '') for s in d.get('sentences') or []), d.get('src')


def local_available():
    return os.path.isfile(LLAMA) and os.path.isfile(LOCAL_MODEL)


KILL_PORT = lambda port, exe: False  # 由 server.py 换成：结束占着端口的残留进程
GPU_CTX = contextlib.nullcontext  # 由 server.py 换成“用显卡的这一段：生图先让开，用完前不开始新的生图”


class _Local:
    proc, last, lock = None, 0, threading.Lock()

    @classmethod
    def alive(cls):
        import netutil  # 没人在监听：直接判定没开，不再等 2 秒超时
        if not netutil.maybe_up(LOCAL_PORT):
            return False
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{LOCAL_PORT}/health', timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    @classmethod
    def ensure(cls):
        with cls.lock:
            cls.last = time.time()
            if cls.proc and cls.proc.poll() is None and cls.alive():
                return
            if not local_available():
                raise RuntimeError('未找到本地翻译模型（llama.cpp 或 Index-Translate-9B）')
            if not (cls.proc and cls.proc.poll() is None):
                if cls.alive():  # 上次没关掉的翻译模型（比如直接关了命令行窗口）还占着端口和显存：先结束掉
                    KILL_PORT(LOCAL_PORT, 'llama-server.exe')
                log = open(os.path.join(ROOT, 'studio', 'translate-engine.log'), 'w', encoding='utf-8', errors='replace')
                cls.proc = subprocess.Popen([LLAMA, '-m', LOCAL_MODEL, '-ngl', '99', '-c', '8192', '-np', '1', '--host', '127.0.0.1',
                                             '--port', str(LOCAL_PORT), '--jinja', '--chat-template-kwargs', '{"enable_thinking":false}'],
                                            cwd=os.path.dirname(LLAMA), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
                log.close()
                threading.Thread(target=cls.reaper, daemon=True).start()
            for _ in range(240):  # 加载模型约 5~15 秒
                if cls.proc.poll() is not None:
                    raise RuntimeError('本地翻译模型启动失败，请查看 studio/translate-engine.log')
                if cls.alive():
                    return
                time.sleep(0.5)
            raise RuntimeError('本地翻译模型启动超时')

    @classmethod
    def reaper(cls):  # 闲置一段时间就退出，把显存还给配音 / 换声
        while cls.proc and cls.proc.poll() is None:
            time.sleep(15)
            if time.time() - cls.last > IDLE_EXIT:
                cls.stop()

    @classmethod
    def stop(cls):
        p, cls.proc = cls.proc, None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=5)
            except Exception:
                try:
                    p.kill(); p.wait(timeout=5)  # 等它真的退出：下一次启动才能用这个端口
                except Exception:
                    pass


atexit.register(_Local.stop)


def _call_local(text, to):
    _Local.ensure()
    prompt = f'请将以下文本翻译为{LANG_ZH.get(to, to)}，直接输出翻译结果，不要进行任何解释。\n\n{text}'
    body = json.dumps({'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 4096,
                       'chat_template_kwargs': {'enable_thinking': False}}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f'http://127.0.0.1:{LOCAL_PORT}/v1/chat/completions', body, {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        raise RuntimeError(f'本地翻译出错：{e}')
    _Local.last = time.time()
    out = (d['choices'][0]['message'].get('content') or '').strip()
    if '</think>' in out:  # 万一模型还是输出了思考过程
        out = out.split('</think>', 1)[1].strip()
    return out


def translate_lines(lines, to, src='auto', progress=None, engine='google'):
    """逐句翻译。返回 (译文列表（和原文一一对应）, 识别出的原文语言代码；本地模型不识别语言时为 None)。"""
    out, detected, batch, size = [], None, [], 0
    limit = BATCH_CHARS if engine == 'google' else 900
    call = (lambda t: _call(t, to, src)) if engine == 'google' else (lambda t: (_call_local(t, to), None))

    def run(b):
        nonlocal detected
        txt, lang = call('\n'.join(b))
        detected = detected or lang
        parts = [p.strip() for p in txt.split('\n')]
        if len(parts) != len(b):  # 谷歌偶尔会合并 / 拆开换行：这一批逐句重来
            parts = [call(x)[0].strip() for x in b]
        out.extend(parts)
        if progress:
            progress(len(out), len(lines))
    for ln in lines:
        ln = ' '.join(str(ln).split())
        if batch and size + len(ln) > limit:
            run(batch); batch, size = [], 0
        batch.append(ln or '…'); size += len(ln) + 1
    if batch:
        run(batch)
    return out, detected


_plain = translate_lines


def translate_lines(lines, to, src='auto', progress=None, engine='google'):  # noqa: F811
    if engine == 'google':
        return _plain(lines, to, src, progress, engine)
    with GPU_CTX():  # 本地模型整段翻译期间占着显卡：中途不会被生图把模型赶出去
        return _plain(lines, to, src, progress, engine)


if __name__ == '__main__':
    print(translate_lines(['今天天气真不错。', '我们一起去河边走走吧。', 'How are you?'], 'en'))
