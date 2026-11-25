r"""改录音（腾讯 AuK-Flash，audio.cpp 跑，2026-11-03 加）：一句话改一段录音——换掉、加上、删掉某几个字，声音和语气照原来的。
指令按 AuK 官方 Cookbook 的写法（中文）：把‘原文’改成‘新文’ / 在‘锚点’后面加上‘内容’ / 删掉‘内容’；也可以直接写其它编辑指令（比如“语速放慢一点”）。
不进配音引擎（8080，正在用的 Studio 共用）：每次用 audiocpp_cli 单独跑一遍（载入约十几秒），用完显存就还回去。"""
import datetime, json, os, subprocess, threading, time, uuid, wave

import stages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, 'audio.cpp', 'audiocpp_cli.exe')
MODEL_DIR = os.path.join(ROOT, 'models', 'AuK-Base-and-Flash-GGUF')
FILES = ['auk-base-q8_0.gguf', 'qwen2.5-omni-3b-q8_0.gguf', 'auk-vae-f32.gguf', 'config/auk-flash.yaml', 'tokenizer/tokenizer.json']
FFMPEG = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
VARIANT = 'base'  # base（32 步 + 引导，一次约 8 秒）/ flash（4 步，约 5 秒）。2026-11-03 A/B：把‘一盏路灯’改成‘两盏红灯笼’，base 3/3 对，flash 只有 2/6（会说成“一两盏”“一盏盏”）
jobs = {}
GPU = None  # server.py 换成 gpu_audio（2026-11-14 审查：以前直接用 imagegen.audio_gpu，跳过了“提示词模型先退出”）
_lock = threading.Lock()  # 一次只改一段（显存）


def missing():
    return [f for f in FILES if not os.path.isfile(os.path.join(MODEL_DIR, f))]


def ok():
    return os.path.isfile(CLI) and not missing()


def instruction(kind, a='', b=''):
    """网页上的三种改法 → AuK 官方中文模板"""
    a, b = (a or '').strip(), (b or '').strip()
    n = {'replace': 'AE_REPLACE', 'insert_after': 'AE_AFTER', 'insert_before': 'AE_BEFORE', 'remove': 'AE_REMOVE'}.get(kind)
    if n:  # 模板套里的写法（默认就是 AuK 官方的中文模板）
        import tplstore
        return tplstore.fmt(tplstore.T(n), a=a, b=b)
    return a  # 自己写的指令


def _dur(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def guess_seconds(src_sec, kind, a, b):
    """输出时长：AuK 要给定。按字数变化估（中文约每秒 4 个字），至少 1 秒"""
    n = lambda s: len((s or '').strip())
    d = {'replace': (n(b) - n(a)) / 4.0 + 0.3, 'insert_after': n(b) / 4.0 + 0.3, 'insert_before': n(b) / 4.0 + 0.3, 'remove': -n(a) / 4.0}.get(kind, 0.0)  # 加字时多留一点（太紧会吞字）
    return round(max(1.0, src_sec + d), 2)


def _read(path):
    import numpy as np
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768, w.getframerate()


def _write(path, x, sr):
    import numpy as np
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def _env(x, sr, hop=240, win=960):
    """10 ms 一帧的对数频带能量（8 kHz 以下）——用来找改过的那一段"""
    import numpy as np
    n = max(1, (len(x) - win) // hop + 1)
    fr = np.stack([x[i * hop:i * hop + win] for i in range(n)]) * np.hanning(win)
    S = np.abs(np.fft.rfft(fr, axis=1)); f = np.fft.rfftfreq(win, 1 / sr)
    edges = np.concatenate([[100, 200, 300, 450, 600, 800, 1000], np.linspace(1300, 7600, 15)])
    return np.log(np.stack([S[:, (f >= a) & (f < b)].mean(1) for a, b in zip(edges[:-1], edges[1:])], 1) + 1e-5)


def splice(orig_path, gen_path, dst):
    """只换改过的那一段：没改的地方用原录音（音质、底噪一点不变），改过的地方用 AuK 的结果，两头交叉淡化。
    AuK 输出里没改的部分和原录音几乎逐帧对齐（前面从头对齐，后面从尾对齐），从两头找第一处持续 0.3 秒对不上的地方就是改动范围。
    找不到（比如整体改了语速、情绪）就整段用 AuK 的。返回 (是否拼接, 改动起点秒, 改动终点秒)"""
    import numpy as np
    a, sr = _read(orig_path); b, sr2 = _read(gen_path)
    if sr != sr2 or len(a) < sr or len(b) < sr // 2:
        return False, 0, 0
    A, B = _env(a, sr), _env(b, sr)
    hop, thr, need = 240 / sr, 0.8, 30  # 10 ms 一帧；对不上要连着 0.3 秒才算
    sm = lambda v: np.convolve(v, np.ones(5) / 5, 'same')

    def first_bad(d):
        bad = sm(d) > thr
        run = 0
        for i, x in enumerate(bad):
            run = run + 1 if x else 0
            if run >= need:
                return i - need + 1
        return len(d)
    k = min(len(A), len(B))
    s = first_bad(np.abs(A[:k] - B[:k]).mean(1))
    e = first_bad(np.abs(A[::-1][:k] - B[::-1][:k]).mean(1))
    s_t, e_t = s * hop, e * hop  # 头部对得上的秒数、尾部对得上的秒数
    lb, la = len(b) / sr, len(a) / sr
    if s_t < 0.15 and e_t < 0.15 or s_t + e_t > min(la, lb) - 0.05:  # 头尾都对不上 / 根本没改出东西
        return False, 0, 0
    back, fade = 0.08, 0.04  # 交界往回退一点（还在对得上的地方），40 ms 等功率淡化
    s0 = max(0.0, s_t - back); e0 = max(0.0, e_t - back)
    i0, j0 = int(s0 * sr), int(e0 * sr)  # 原录音 / 生成结果：前面切在 i0，后面各自从尾部往回 j0
    gseg = b[i0:len(b) - j0] if j0 else b[i0:]
    head, tail = a[:i0], (a[len(a) - j0:] if j0 else a[:0])
    rms = lambda x: float(np.sqrt(np.mean(x ** 2)) + 1e-6)
    ref = np.concatenate([a[:i0], tail]); gref = np.concatenate([b[:i0], b[len(b) - j0:] if j0 else b[:0]])
    if len(ref) > sr // 4:  # 响度对齐（AuK 输出整体音量可能略有差别）
        gseg = gseg * min(2.0, max(0.5, rms(ref) / rms(gref)))
    nf = int(fade * sr)

    def xjoin(x, y):
        if not len(x):
            return y
        if not len(y):
            return x
        n = min(nf, len(x), len(y))
        t = np.linspace(0, np.pi / 2, n)
        return np.concatenate([x[:-n], x[-n:] * np.cos(t) + y[:n] * np.sin(t), y[n:]])
    out = xjoin(xjoin(head, gseg), tail)
    _write(dst, out, sr)
    return True, round(s_t, 2), round(lb - e_t, 2)


def prep(job_dir, src_path):
    """原录音只解码一次，同时写出 24 kHz（拼接用）和 16 kHz（给 AuK）两份。返回 (24k, 16k) 路径。
    2026-11-17 审查 P08：以前为了测时长先转一份 24 kHz 再删掉，进 run() 又各转一遍 24k / 16k，长录音解码三次"""
    wav_in, wav16 = os.path.join(job_dir, 'input.wav'), os.path.join(job_dir, 'input16.wav')
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-i', src_path, '-ac', '1', '-ar', '24000', wav_in, '-ac', '1', '-ar', '16000', wav16],
                   check=True, capture_output=True, creationflags=NO_WINDOW)
    return wav_in, wav16


def run(job_dir, src_path, inst, seconds, seed=-1, job=None, variant=None):
    """跑一次：原录音转成 24 kHz（拼接用）和 16 kHz（给 AuK——这个 audio.cpp 没带 soxr，AuK 不肯自己重采样），
    交给 audiocpp_cli；最后只把改过的那一段拼回原录音（AuK 吃 16 kHz，出来的声音 8 kHz 以上是空的，没改的地方用原录音就不发闷）。返回输出 wav 路径"""
    wav_in, wav16 = os.path.join(job_dir, 'input.wav'), os.path.join(job_dir, 'input16.wav')
    if not (os.path.isfile(wav_in) and os.path.isfile(wav16)):  # submit 里已经 prep 过就直接用
        wav_in, wav16 = prep(job_dir, src_path)
    gen = os.path.join(job_dir, 'auk.wav')
    out = os.path.join(job_dir, 'output.wav')
    if job is not None:
        job['message'] = '正在载入 AuK 并修改录音…'
    args = [CLI, '--task', 'tts', '--family', 'auk', '--model', MODEL_DIR, '--backend', 'cuda',  # 选项要带 auk. 前缀，--model 是模型文件夹
            '--session-option', f'auk.variant={variant or VARIANT}', '--session-option', f'auk.model_gguf=auk-{variant or VARIANT}-q8_0.gguf', '--session-option', 'auk.qwen_gguf=qwen2.5-omni-3b-q8_0.gguf',
            '--session-option', 'auk.vae_gguf=auk-vae-f32.gguf', '--session-option', 'auk.mem_saver=true',
            '--voice-ref', wav16, '--text', inst, '--request-option', f'duration_sec={seconds}', '--request-option', f'seed={seed}', '--out', gen]
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW, timeout=900, cwd=os.path.dirname(CLI))
    if r.returncode or not os.path.isfile(gen):
        raise RuntimeError('AuK 修改失败：' + ((r.stderr or r.stdout or '')[-400:]).strip())
    try:
        ok, a, b = splice(wav_in, gen, out)
    except Exception:
        ok = False
    if not ok:
        os.replace(gen, out)
    else:
        os.remove(gen)
        if job is not None:
            job['changed'] = [a, b]  # 改动的大概范围（秒，按改好的录音算）
    try:
        os.remove(wav16)
    except OSError:
        pass
    return out


def submit(src_bytes, ext, kind, a, b, seconds=None, seed=-1, root=None):
    """新建一个改录音任务（后台线程跑），返回任务"""
    inst = instruction(kind, a, b)
    if not inst:
        raise ValueError('请写明修改方式')
    if kind in ('replace', 'insert_after', 'insert_before', 'remove') and not (a or '').strip():
        raise ValueError('请写明原录音中要修改的文字')
    if kind in ('replace', 'insert_after', 'insert_before') and not (b or '').strip():
        raise ValueError('请写明要替换为 / 添加的文字')
    jid = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
    d = os.path.join(root, jid)
    os.makedirs(d)
    src = os.path.join(d, 'source.' + (ext or 'wav'))
    with open(src, 'wb') as f:
        f.write(src_bytes)
    j = stages.JobDict({'id': jid, 'state': 'queued', 'message': '排队中', 'kind': kind, 'a': a, 'b': b, 'instruction': inst, 'created': time.time(),
                        'finished': None, 'error': '', 'seconds': None, 'src_seconds': None, '_dir': d, '_src': src, '_seed': seed, '_want': seconds})
    jobs[jid] = j
    _save(j)  # 2026-11-14 审查：排队时就写一份记录（以前做完才写：中途重启 / 崩溃后记录没了，上传的录音却还在）

    def work():
        with _lock:
            j['state'], j['message'] = 'running', '正在准备录音…'
            try:
                wav, _ = prep(d, src)  # 这一份 24 kHz 测完时长留着，run() 拼接时直接用
                j['src_seconds'] = round(_dur(wav), 2)
                secs = j['_want'] or guess_seconds(j['src_seconds'], kind, a, b)
                import imagegen
                j['message'] = '等待显卡空闲…'
                with (GPU() if GPU else imagegen.audio_gpu()):  # 和配音 / 识别一样（server.gpu_audio：提示词模型先退出，生图、生视频让开），用完之前不开始新的
                    out = run(d, src, inst, secs, j['_seed'], j)
                j['seconds'] = round(_dur(out), 2)
                j['message'], j['state'] = '完成', 'done'
            except Exception as e:
                j['error'], j['message'], j['state'] = str(e)[:500], '失败', 'error'
            j['finished'] = time.time()
            _save(j)
    threading.Thread(target=work, daemon=True).start()
    return j


def _save(j):
    """做完 / 失败后把记录写进任务文件夹（meta.json）：重启应用后记录还在"""
    p = os.path.join(j['_dir'], 'meta.json'); tmp = p + '.tmp'
    try:  # 先写临时文件再换上（审查 21：以前直接覆盖，中途退出 / 写失败留下坏 JSON，启动时这条记录就没了）
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({**{k: v for k, v in j.items() if not k.startswith('_')}, 'timing': j.track.export()}, f, ensure_ascii=False)
        os.replace(tmp, p)
    except (OSError, TypeError, ValueError) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print(f'改录音：记录没能保存（{e}）', flush=True)


_loaded = set()


def load(root, space):
    """读回这个空间以前的记录（每个文件夹里的 meta.json），每个文件夹只读一次"""
    if root in _loaded or not os.path.isdir(root):
        return
    _loaded.add(root)
    for jid in os.listdir(root):
        d = os.path.join(root, jid)
        try:
            with open(os.path.join(d, 'meta.json'), encoding='utf-8') as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if jid in jobs:
            continue
        if m.get('state') not in ('done', 'error'):  # 上次没做完（程序被关掉 / 崩溃）：记成中断，留着能看、能删
            m.update(state='error', message='上次未完成（程序被关闭）', error=m.get('error') or '上次未完成（程序被关闭）')
        t = m.pop('timing', None)
        j = stages.JobDict({**m, '_dir': d, '_space': space})
        j['_timing'] = t
        jobs[jid] = j


def public(j):
    if j.get('_timing') is not None:  # 从 meta.json 读回来的：用当时记下的分步用时
        return {**{k: v for k, v in j.items() if not k.startswith('_')}, 'timing': j['_timing']}
    d = {k: v for k, v in j.items() if not k.startswith('_')}
    d['timing'] = j.track.export()
    return d


# 2026-11-09 模板套：四种改法登记到 tplstore（默认是 AuK 官方的中文模板，改了可能不如官方写法稳）
import tplstore
for _k, _l, _n, _t in [('ae_replace', '替换', 'AE_REPLACE', '把‘{a}’改成‘{b}’'), ('ae_after', '在后面加上', 'AE_AFTER', '在‘{a}’后面加上‘{b}’'),
                       ('ae_before', '在前面加上', 'AE_BEFORE', '在‘{a}’前面加上‘{b}’'), ('ae_remove', '删除', 'AE_REMOVE', '删掉‘{a}’')]:
    tplstore.register('aedit', _k, _l, [(_n, 'zh')], {'pos': {_n: _t}}, {'a': '原录音里的文字', 'b': '新的文字'}, '改录音指令')
