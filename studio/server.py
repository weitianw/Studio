"""AI 配音工作室：本地网页 + 音色库 + 长文本任务。audio.cpp 在后台当推理引擎（不做任何修改）。

只用 Python 标准库。启动：python -I studio/server.py
"""
import array, base64, contextlib, datetime, difflib, http.client, http.server, json, os, re, shutil, socketserver, subprocess, sys, threading, time
import tempfile, traceback, unicodedata, urllib.error, urllib.parse, urllib.request, uuid, wave, webbrowser

# Windows 终端默认是 GBK，打印 ✓ 等字符会抛错并中断任务：统一改成 UTF-8 并替换无法显示的字符
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIO = os.path.join(ROOT, 'studio')
WEB = os.path.join(STUDIO, 'web')
SPECS = os.path.join(STUDIO, 'specs')
PROFILES = os.path.join(STUDIO, 'profiles')
TMP = os.path.join(STUDIO, 'tmp')
JOBS = os.path.join(ROOT, 'outputs', 'studio')
LIB = os.path.join(ROOT, 'voice-library')
PROMPTS = os.path.join(LIB, 'prompt_text')
META = os.path.join(LIB, 'voices.json')
FFMPEG = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
FFPROBE = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffprobe.exe')
ENGINE_EXE = os.path.join(ROOT, 'audio.cpp', 'audiocpp_server.exe')
ENGINE = 'http://127.0.0.1:8080'
PORT = 7860
if '--port' in sys.argv:  # 开发测试用：和正在用的那个错开端口
    PORT = int(sys.argv[sys.argv.index('--port') + 1])
POTPLAYER = r'D:\App\PotPlayer\PotPlayerMini64.exe'
ASR_MODEL = 'asr'
BAD_CER = 0.2
DEFAULT_SAMPLE = '你好，很高兴认识你。今天的天气不错，我们一起去河边走走吧，顺便聊聊最近发生的事情。'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
# 后台慢慢做的事（播放副本）：低一级的优先级，界面和播放器先用 CPU（2026-11-11 用户：剪辑里播放卡——刚打开的视频后台在转码，占满了所有核）
BG_PRI = NO_WINDOW | (getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0) if os.name == 'nt' else 0)
BG_THREADS = str(max(2, (os.cpu_count() or 8) // 2))

# 私密空间：输入密钥后进入，作品 / 历史记录 / 语音转文字 / 新建的音色都单独存放在隐藏的 .data 里，和普通界面互相看不到
DATA = os.path.join(ROOT, '.data')
LIBRARY = os.path.join(DATA, 'library')          # 播放页的音源
if '--library' in sys.argv:  # 开发测试用：指向一个单独的测试音源目录，不碰真实音源库
    LIBRARY = os.path.abspath(sys.argv[sys.argv.index('--library') + 1])
COVERS = os.path.join(DATA, 'covers')            # 从音频/视频里取出的封面缓存
SEGPREF_V = os.path.join(DATA, 'segpref.jsonl')  # 推荐分段学偏好用的选段记录（segpref.py，只有数字）：私密空间
SEGPREF_N = os.path.join(ROOT, 'outputs', 'segpref.jsonl')  # 普通空间
BATCH_V, BATCH_N = os.path.join(DATA, 'batches'), os.path.join(ROOT, 'outputs', 'batches')  # 批量配方：一次批量一个 json（batch.py）
RECIPES_V, RECIPES_N = os.path.join(DATA, 'batch-recipes.json'), os.path.join(ROOT, 'outputs', 'batch-recipes.json')  # 自己存的配方
PSUBS = os.path.join(DATA, 'subs')               # 播放页生成的字幕缓存
VJOBS = os.path.join(DATA, 'studio')             # 私密空间的作品与历史记录
VLIB = os.path.join(DATA, 'voices')              # 私密空间里新建的音色
VSTT = os.path.join(DATA, 'stt')
VTMP = os.path.join(DATA, 'tmp')                 # 私密空间的临时文件（上传的录音、试听、截取的片段…）
VPREFS = os.path.join(DATA, 'ui.json')           # 私密空间的界面设置（播放进度、文件夹排序、配音页的文字…），不放进浏览器的本地存储
VAULT_TOKENS = os.path.join(DATA, '.sessions.json')
FAVS = os.path.join(DATA, 'favorites.json')  # 播放页“我的收藏”：只记 key，不移动文件
# 普通界面的播放页：读取另一个（不隐藏的）文件夹；封面 / 字幕缓存和收藏也和私密空间分开放
PUBLIB = os.path.join(ROOT, '音源库')
if '--publib' in sys.argv:  # 开发测试用
    PUBLIB = os.path.abspath(sys.argv[sys.argv.index('--publib') + 1])
PCACHE = os.path.join(ROOT, 'outputs', 'play-cache')
PCOVERS, PPSUBS = os.path.join(PCACHE, 'covers'), os.path.join(PCACHE, 'subs')
PFAVS = os.path.join(ROOT, 'outputs', 'favorites.json')
PROMPT_DIR = os.path.join(ROOT, 'outputs')  # AI 助手：普通空间的预设、引擎设置
if not os.environ.get('STUDIO_DEFER_DIRS'):  # 测试启动器先改好路径再自己建（2026-11-17 审查 F05：以前一导入就在正式目录里建文件夹）
    for d in (TMP, JOBS, LIB, DATA, VJOBS, VLIB, VSTT, VTMP, COVERS, PSUBS, PUBLIB, PCOVERS, PPSUBS):
        os.makedirs(d, exist_ok=True)
CTX = threading.local()  # 每个请求 / 任务线程当前所在的数据空间：'n' 普通，'v' 私密


def space():
    return getattr(CTX, 'space', 'n')


def _mt(p):
    try:
        return int(os.path.getmtime(p) * 1000)
    except OSError:
        return 0


def space_rev():
    """当前空间里各类内容的“版本”：网页定时看一眼，变了就刷新当前页面（手机上生成的图，电脑上不用重新进就能看到）。"""
    sp = space()
    h = lambda *xs: format(hash(tuple(xs)) & 0xffffffff, 'x')
    js = [j for j in list(jobs.values()) if getattr(j, 'space', 'n') == sp]
    ij = [j for j in list(imagegen.jobs.values()) if j.get('space') == sp]
    vj = [j for j in list(videogen.jobs.values()) if j.get('space') == sp]
    sj = [j for j in list(stt.stt_jobs.values()) if getattr(j, 'space', 'n') == sp]
    return {
        'jobs': h(*((j.id, j.state, getattr(j, 'saved', False), j.title, getattr(j, 'finished', None)) for j in js)),
        'img': h(_mt(imagegen._index_path(sp)), *((j['id'], j['state'], j['done']) for j in ij)),
        'video': h(_mt(videogen._index_path(sp)), *((j['id'], j['state'], j.get('finished')) for j in vj)),
        'voices': h(_mt(os.path.join(VLIB if sp == 'v' else LIB, 'voices.json'))),
        'stt': h(*((j.id, j.state, getattr(j, 'finished', None)) for j in sj)),
        'play': h(_mt(favs_file()), _mt(tags_file()), _mt(order_file())),
    }


def print_tb():  # 出错的详细信息：私密空间里的不打印（会写进 app-server.log，可能带私密的文件名、文字）
    if space() != 'v':
        traceback.print_exc()


def tmp_dir():
    return VTMP if space() == 'v' else TMP


# 播放页按所在空间取各自的文件夹
def lib_root():
    return LIBRARY if space() == 'v' else PUBLIB


def covers_dir():
    return COVERS if space() == 'v' else PCOVERS


def psubs_dir():
    return PSUBS if space() == 'v' else PPSUBS


def favs_file():
    return FAVS if space() == 'v' else PFAVS


def recent_file():  # 播放页“最近播放”：两个空间各记各的
    return os.path.join(DATA if space() == 'v' else os.path.join(ROOT, 'outputs'), 'recent.json')


def tags_file():  # 播放页的标签：{key: [标签, …]}
    return os.path.join(DATA if space() == 'v' else os.path.join(ROOT, 'outputs'), 'tags.json')


def order_file():  # 播放页左边文件夹 / 标签的自定义顺序：{分组: [名字, …]}
    return os.path.join(DATA if space() == 'v' else os.path.join(ROOT, 'outputs'), 'src-order.json')


def jobs_root(sp=None):
    return VJOBS if (sp or space()) == 'v' else JOBS
sys.path.insert(0, STUDIO)
import stt  # noqa: E402  语音转文字 + 大模型校对
BOOT_ID = str(int(time.time() * 1000))  # 这次启动的编号：网页发现它变了 = Studio 重启过（代码可能更新了），下次回到前台时自动刷新（2026-11-08）
import hashlib, hmac  # noqa: E402
# 桌面应用启动后台时给的口令（环境变量；设置里“重启 Studio”时新进程继承下来）。没有 = 不是桌面应用启动的，谁也不能远程关它（F04）
OWNER_TOKEN = os.environ.get('STUDIO_OWNER_TOKEN', '')
OWNER_TAG = hashlib.sha256(OWNER_TOKEN.encode()).hexdigest()[:16] if OWNER_TOKEN else ''
import stages  # noqa: E402  任务计时（每一步用了多久）
import audioedit  # noqa: E402  改录音（AuK-Flash：换掉 / 加上 / 删掉录音里的几个字）
import translate  # noqa: E402  播放页字幕翻译（谷歌翻译）
import remote  # noqa: E402  手机访问（Tailscale + 配对码）
import push  # noqa: E402  手机推送：生成完成 / 失败时通知（2026-11-06）
import passkey  # noqa: E402  私密空间用面容 ID 解锁（2026-11-06）
import vaultrc  # noqa: E402  私密空间里用电脑控制手机正在播放的内容（2026-11-16，只在内存里）
import imagegen  # noqa: E402  生图（stable-diffusion.cpp · Z-Image Turbo）
import promptgen  # noqa: E402
import civitai  # noqa: E402  Civitai：搜 LoRA、一键下载
import videogen  # noqa: E402  生视频（后台的 ComfyUI：Wan 2.2 / MiniMax H3）  AI 助手（llama.cpp · Qwen3.8 27B 无审查）
import tplstore  # noqa: E402  模板套（各页面套在提示词外面的固定文字，用户可自建、定默认）
import videoedit  # noqa: E402  改视频（H3 参考模式：换人 / 换衣服 / 自由修改）
import h3extra  # noqa: E402  生视频 · H3 的更多条件（关键帧、开头片段、指定声音、参考图 / 视频 / 音频）
import h3methods  # noqa: E402  H3 的做法 ①②③（跑在哪套 ComfyUI、用哪份工作流）
import libmeta  # noqa: E402  播放页歌曲表的时长 / 作者（ffprobe，后台读、按空间缓存，2026-11-17）
# 素材库：用户自己放素材的文件夹（视频、图片、声音）。生视频 / 改视频选素材时除了生成过的，还能从这里选；只读，不往里写
MATS_DIR = os.environ.get('STUDIO_MATERIALS') or os.path.join(ROOT, '素材库')
MATS_EXT = {'video': ('.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv'), 'image': ('.png', '.jpg', '.jpeg', '.webp'), 'audio': ('.wav', '.mp3', '.m4a', '.flac', '.ogg')}


def mats_path(rel, any_space=False):
    """素材库里的相对路径 → 绝对路径（不许跑出素材库）"""
    root = os.path.abspath(MATS_DIR)
    path = os.path.abspath(os.path.join(root, *[x for x in str(rel or '').replace('\\', '/').split('/') if x not in ('', '.', '..')]))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError('不能使用素材库以外的文件')
    if not any_space and mats_hide(os.path.relpath(path, root)):  # 只在私密空间显示的文件夹：普通空间里当它不存在
        raise ValueError('素材库中找不到该文件')
    return path


# 只在私密空间里显示的素材库文件夹：普通空间里列表、搜索、标签、“移动到…”、取文件、Agent 都看不到
MATS_PRIVATE = ('视频截图/私密空间',)  # 视频截图/私密空间：私密空间里生成的视频截下的图（frames.py，2026-11-19）


def mats_private(rel):
    r = str(rel or '').replace('\\', '/').strip('/').lower()
    return any(r == p or r.startswith(p + '/') for p in (x.lower() for x in MATS_PRIVATE))


def mats_hid_dir(top, name):
    """os.walk / scandir 里的子文件夹（top 下的 name）在当前空间要不要跳过"""
    return mats_hide(os.path.relpath(os.path.join(top, name), os.path.abspath(MATS_DIR)))


def mats_hide(rel, sp=None):
    """这个素材库相对路径在当前（或 sp）空间里要不要藏起来"""
    return (sp or space()) != 'v' and mats_private(rel)


import frames  # noqa: E402  视频截一帧 → 素材库（2026-11-19 用户）
frames.init(MATS_DIR, FFMPEG, FFPROBE)


def builtin_loras():
    """软件自己会用到的 LoRA：文件名 → 用在哪（我的下载里收进“软件内置使用”，2026-11-06 用户要求）。
    只算软件自己加载的（某个做法自动用 / 软件自己的开关，包括 2026-11-06 起表单里的“加速”）；要在高级参数里手动选的（VFX……）不算"""
    out = {}
    def put(f, role):
        if f:
            out[os.path.basename(f)] = role
    try:
        import videoedit
        F = videoedit.FILES
        put(F.get('cs11'), '改视频 · 换人（新版，默认自动用）')
        put(F.get('motion'), '改视频 · 动作迁移（自动用）')
        put(F.get('dmd'), '改视频 · 换人新版 / 动作迁移 · DMD 8 步加速（自动用）')
        put(F.get('faceswap'), '改视频 · 换头（换脸 LoRA，默认自动用）')
    except Exception:
        pass
    for x in videogen.turbo_list():  # 加速（官方底模时生视频 / 改视频表单里的“加速”开关）
        put(x['file'], f"{'生视频 · 首帧' if x['kind'] == 'fl2v' else '参考模式 / 改视频'} · 加速 {x['steps']} 步（“加速”选项）")
    try:
        import q21
        put(q21.POSE_LORA, '生图 · 人偶姿势（自动用）')
    except Exception:
        pass
    return out


def mats_inline(x, depth=0):
    """请求里的 {mats: 相对路径}（从素材库选的）→ {data: data URL}，后面的代码照常处理"""
    if depth > 6:
        return x
    if isinstance(x, dict):
        if isinstance(x.get('mats'), str) and len(x) <= 2:
            path = mats_path(x['mats'])
            if not os.path.isfile(path):
                raise ValueError('素材库中找不到该文件：' + x['mats'])
            if os.path.getsize(path) > 80 * 1048576:
                raise ValueError('素材库中的该文件过大（上限约 80MB）：' + x['mats'])
            ext = os.path.splitext(path)[1].lower()
            mime = 'video/mp4' if ext in MATS_EXT['video'] else 'audio/' + ext[1:] if ext in MATS_EXT['audio'] else 'image/png' if ext == '.png' else 'image/jpeg'
            with open(path, 'rb') as f:
                return {'data': f'data:{mime};base64,' + base64.b64encode(f.read()).decode(), **({'audio': x['audio']} if 'audio' in x else {})}
        return {k: mats_inline(v, depth + 1) for k, v in x.items()}
    if isinstance(x, list):
        return [mats_inline(v, depth + 1) for v in x]
    return x


_MATS_IDX = {'key': None, 'map': {}}


FR_LOCAL = set()  # 网页自己取帧存进素材库的图（相对路径）：这次运行里可以撤销
_MATS_GAL, MATS_GEN = {}, [0]  # /api/mats/gallery 的结果缓存；MATS_GEN：素材库里删改过几次


def mats_index():
    """素材库/gallery/index.json（三个素材站整理来的姿势 / 衣服 / 脸）→ {素材库相对路径: 条目}；文件改了才重读"""
    p = os.path.join(MATS_DIR, 'gallery', 'index.json')
    try:
        st = os.stat(p)
    except OSError:
        return {}
    if _MATS_IDX['key'] != (st.st_mtime, st.st_size):
        try:
            with open(p, encoding='utf-8') as f:
                items = json.load(f).get('items') or []
            _MATS_IDX['map'] = {f"gallery/{x['lib']}/{x['rel']}": x for x in items if x.get('lib') and x.get('rel')}
        except Exception:
            _MATS_IDX['map'] = {}
        _MATS_IDX['key'] = (st.st_mtime, st.st_size)
    return _MATS_IDX['map']


def mats_tag(name):
    """素材文件名的标签：开头是 @ 时取 @ 到第一个下划线之间（没有下划线就到扩展名为止），否则 None"""
    if not name.startswith('@'):
        return None
    stem = os.path.splitext(name)[0][1:]
    t = stem.split('_', 1)[0].strip()
    return t or None


def mats_added(st_):
    """加入素材库的时间：Windows 上是文件的创建时间（复制 / 移进来时就是那一刻；修改时间会保留原文件的）"""
    return getattr(st_, 'st_birthtime', None) or st_.st_ctime


def mats_label(rel):
    """素材在列表里显示的名字：素材站来的用中文名（姿势：编号 名字 · 角度；衣服：编号 · 关键词），别的就是文件名"""
    x = mats_index().get(rel)
    if not x:
        return None
    if x['lib'] == '姿势':
        return f"{x.get('pose', '')} {x.get('name', '')} · {x.get('angle', '')}".strip()
    if x['lib'] == '衣服':
        return f"{x.get('id', '')} · {x.get('keywords', '')}".strip(' ·')
    return ' · '.join(v for v in (x.get('hair'), x.get('style')) if v) or None


MATS_SET_FILE = '.post.json'  # 文件夹里有它 = 一个图集（视频截图的图集，frames.py）：素材库里整个文件夹显示成一格


def mats_set(d, rel):
    """图集文件夹 → 素材库里的一格：{set: True, rel: 文件夹, cover: 第一张图, items: [{rel, live}], n, live}；不是图集返回 None"""
    if not os.path.isfile(os.path.join(d, MATS_SET_FILE)):
        return None
    try:
        names = sorted(e.name for e in os.scandir(d) if e.is_file() and not e.name.startswith('.'))
        st_ = os.stat(d)
    except OSError:
        return None
    vids = {os.path.splitext(n)[0]: n for n in names if n.lower().endswith(MATS_EXT['video'])}
    items = [{'rel': rel + '/' + n, 'live': rel + '/' + vids[os.path.splitext(n)[0]] if os.path.splitext(n)[0] in vids else None}
             for n in names if n.lower().endswith(MATS_EXT['image'])]
    if not items:
        return None
    try:
        info = json.load(open(os.path.join(d, MATS_SET_FILE), encoding='utf-8'))
    except (OSError, ValueError):
        info = {}
    return {'set': True, 'name': os.path.basename(d), 'rel': rel, 'cover': items[0]['rel'], 'items': items, 'n': len(items),
            'live': sum(1 for x in items if x['live']), 'kind': 'image', 'label': os.path.basename(d), 'desc': info.get('desc') or '',
            'mtime': st_.st_mtime, 'added': mats_added(st_), 'size': 0, **({'video': info.get('video')} if info.get('kind') == 'frames' and isinstance(info.get('video'), dict) else {})}  # 视频截图的图集：来源视频


def mats_thumb(path):
    """素材库图片的缩略图：素材站整理来的有现成的（同一层的 .thumbs 里，同样的相对路径、扩展名可能不同），没有就现做一张"""
    root = os.path.abspath(MATS_DIR)
    parts = os.path.relpath(path, root).split(os.sep)
    for i in range(1, len(parts)):  # 从下往上找：<某一层>/.thumbs/<剩下的路径>
        base = os.path.join(root, *parts[:len(parts) - i], '.thumbs', *parts[len(parts) - i:])
        stem = os.path.splitext(base)[0]
        for ext in ('.webp', '.jpg', '.jpeg', '.png'):
            if os.path.isfile(stem + ext):
                return stem + ext
    return thumb_for(path)


def mats_test_ro():
    """测试用的 Studio（devtest/run.py 带 --library）读的是真的素材库：一律不往里写 / 不移动 / 不删（审查 4；2026-11-17 测试时写进去过一次）"""
    return '--library' in sys.argv and os.path.abspath(MATS_DIR) == os.path.abspath(os.path.join(ROOT, '素材库'))


def mats_link(src, name, folder=None):
    """把一张图放进素材库的某个文件夹（默认“提取的衣服”）：硬链接（不多占空间，删一边另一边还在），不同盘时复制。返回 (相对路径, 原来就有)"""
    folder = folder or imagegen.XFOLDER
    if mats_test_ro():  # 测试用的 Studio 读的是真的素材库：不往里写
        return folder + '/' + os.path.basename(name), False
    d = mats_path(folder)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(name))
    had = os.path.exists(dst)
    if not had:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)
        MATS_GEN[0] += 1  # 素材库变了：列表重新查
    return folder + '/' + os.path.basename(name), had


def mats_edit(op, b):
    """素材库页面里整理文件：mkdir {dir, name} / move {items: [相对路径], to: 文件夹} / delete {items}（进回收站）。
    gallery（姿势 / 衣服 / 脸，有清单对着）和素材库根目录本身不许动；重名时自动加 (2)、(3)…"""
    root = os.path.abspath(MATS_DIR)
    if mats_test_ro():
        raise RuntimeError('测试用的 Studio 不改动真的素材库')
    rel = lambda p: os.path.relpath(p, root).replace('\\', '/')
    def guard(p, what):
        r = rel(p)
        if p == root:
            raise RuntimeError(f'不能{what}素材库根目录')
        if r == 'gallery' or r.startswith('gallery/'):
            raise RuntimeError(f'gallery（姿势 / 衣服 / 脸）中的内容不能{what}')
        if not os.path.exists(p):
            raise RuntimeError('找不到：' + r)
    def free(d, name, is_file):
        stem, ext = os.path.splitext(name) if is_file else (name, '')
        out, k = name, 2
        while os.path.exists(os.path.join(d, out)):
            out, k = f'{stem} ({k}){ext}', k + 1
        return out
    if op == 'mkdir':
        d = mats_path(b.get('dir') or '')
        name = str(b.get('name') or '').strip().strip('.')
        if not name or any(c in name for c in '\\/:*?"<>|') or name in ('.', '..'):
            raise RuntimeError('文件夹名称不能为空，也不能包含 \\ / : * ? " < > |')
        if rel(d) == 'gallery' or rel(d).startswith('gallery/'):
            raise RuntimeError('不能在 gallery 中新建文件夹')
        if os.path.exists(os.path.join(d, name)):
            raise RuntimeError('已有同名的文件夹或文件：' + name)
        os.makedirs(os.path.join(d, name))
        return {'ok': True, 'rel': rel(os.path.join(d, name))}
    items = [mats_path(x) for x in (b.get('items') or []) if isinstance(x, str) and x]
    if not items:
        raise RuntimeError('没有选择任何项目')
    for p in items:
        guard(p, '移动' if op == 'move' else '删除')
    if op == 'delete':
        done = 0
        for p in items:
            r0 = rel(p)
            to_recycle_bin(p)
            if r0.lower().endswith(MATS_EXT['image']):
                frames.remove_image(r0)  # 删的是一张视频截图：视频那边的记录也去掉
            done += 1
        return {'ok': True, 'n': done}
    to = mats_path(b.get('to') or '')
    if not os.path.isdir(to):
        raise RuntimeError('目标文件夹不存在')
    if rel(to) == 'gallery' or rel(to).startswith('gallery/'):
        raise RuntimeError('不能移入 gallery')
    moved = 0
    for p in items:  # 私密的东西不能挪到普通文件夹里（私密靠固定的文件夹路径认，挪出来就露在普通空间了，审查 9）
        rp = rel(p).lower()
        if mats_private(rp) and not mats_private(rel(to)):
            raise RuntimeError(f'「{os.path.basename(p)}」是私密的，只能移到私密文件夹里')
        if os.path.isdir(p) and any(x.lower().startswith(rp + '/') for x in MATS_PRIVATE):
            raise RuntimeError(f'「{os.path.basename(p)}」里面有私密文件夹，不能整个移动')
    for p in items:
        if os.path.dirname(p) == to:
            continue  # 本来就在这里
        if os.path.isdir(p) and (to == p or to.startswith(p + os.sep)):
            raise RuntimeError(f'不能把文件夹「{os.path.basename(p)}」移到它自己里面')
        dst = os.path.join(to, free(to, os.path.basename(p), os.path.isfile(p)))
        shutil.move(p, dst)
        try:
            frames.on_move(rel(p), rel(dst))  # 视频 / 截图 / 图集挪了地方：截图记录跟着改
        except (OSError, ValueError):
            pass
        moved += 1
    return {'ok': True, 'n': moved}


@contextlib.contextmanager
def gpu_audio():
    """配音 / 换声 / 识别 / 本地翻译 / 去背景声用显卡的这一整段：提示词模型先退出（等它写完手上这次），生图让开、不开始新的。"""
    promptgen.Engine.release()
    with imagegen.audio_gpu():
        yield


audioedit.GPU = gpu_audio  # 改录音也走这一整套（见 audioedit.GPU）
lock = threading.RLock()
import hashlib, secrets  # noqa: E402
import vaultkey  # noqa: E402  私密空间密钥的本机校验记录（F08）
VAULT_REC = os.path.join(DATA, 'vault-key.json')  # 这个安装自己的记录（scrypt + 随机盐；不进 Git）
# 旧版：所有安装共用、写在源码里的不加盐哈希。只用于老用户第一次解锁时迁移到 VAULT_REC；有了记录（或这是没有私密数据的新安装）就不再接受
VAULT_KEY_SHA = 'd1727ea4d5c00f8456544b55d80a220a3b7a6e9e783b1f449e97f5c3769beb68'


def vault_legacy_allowed():
    """旧哈希只给“已经在用私密空间的老安装”迁移用：私密空间里已有作品 / 任务 / 转写"""
    for d in (VLIB, VJOBS, VSTT):
        try:
            if os.path.isdir(d) and any(True for _ in os.scandir(d)):
                return True
        except OSError:
            pass
    return False


def vault_check(key):
    return vaultkey.check(VAULT_REC, key, VAULT_KEY_SHA, vault_legacy_allowed, lambda m: act(m, 'system'))

# ---------------------------------------------------------------- 运行日志（网页实时显示每一步）
import collections, itertools  # noqa: E402
ACT = collections.deque(maxlen=800)
ACT_SEQ = itertools.count(1)


def act(msg, tag='', level='info'):
    j = jobs.get(tag) if tag else None  # 属于某个任务的日志（包括引擎调用细节）一并存进任务
    sj = stt.stt_jobs.get(tag) if tag and j is None else None
    sp = getattr(j, 'space', None) or getattr(sj, 'space', None) or space()
    e = {'seq': next(ACT_SEQ), 't': time.time(), 'msg': msg, 'tag': tag, 'level': level, 'space': sp}
    ACT.append(e)
    if j is not None:
        j.logs = (getattr(j, 'logs', []) + [e])[-400:]
    try:
        if sp != 'v':
            print(time.strftime('%H:%M:%S'), msg, flush=True)
    except Exception:
        pass  # 日志打印失败绝不能影响生成
    return e


# ================================================================ 引擎
engine_lock = threading.RLock()


GPU_PATHS = ('/v1/audio/speech', '/v1/tasks/run', '/v1/audio/transcriptions', '/v1/audio/transcriptions/details')


def engine(path, payload=None, timeout=900):
    if path in GPU_PATHS:  # 用显卡的这一段：生图先让开，用完前不开始新的生图
        with gpu_audio():
            return _engine_retry(path, payload, timeout)
    return _engine_retry(path, payload, timeout)


def _engine_retry(path, payload, timeout):
    try:
        return _engine(path, payload, timeout)
    except (urllib.error.URLError, ConnectionError):
        # 引擎进程意外退出（例如内存不足时崩溃）：自动重启一次再重试，不让整个任务直接失败
        with engine_lock:
            if not engine_alive():  # 已经被别的请求重启好了的话直接重试
                act('推理引擎意外退出，正在自动重启（约 10 秒）…', '', 'warn')
                try:
                    start_engine()
                except SystemExit as se:
                    raise RuntimeError(str(se))
        return _engine(path, payload, timeout)


def _engine(path, payload=None, timeout=900):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(ENGINE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        try:
            body = json.loads(body)['error']['message']
        except Exception:
            pass
        raise RuntimeError(f'引擎返回错误：{body}')


def engine_alive():
    import netutil  # 没人在监听：直接判定没开，不再等 2 秒超时（每 5 秒一次的状态请求就靠它）
    if not netutil.maybe_up(urllib.parse.urlsplit(ENGINE).port or 80):
        return False
    try:
        _engine('/health', timeout=2)
        return True
    except Exception:
        return False


def _so_norm(d):
    return {str(k): str(v).lower() for k, v in (d or {}).items()} if isinstance(d, dict) else {}


def engine_config_matches():
    """正在跑的引擎和 server.json 一致吗：模型 id 一样，并且每个模型的会话参数（性能模式、LoRA……）也一样。"""
    try:
        data = json.loads(engine('/v1/models?include_session_options=true')[0])['data']
    except Exception:
        return False
    cfg = {m['id']: m for m in server_cfg().get('models', [])}
    if {m['id'] for m in data} != set(cfg):
        return False
    return all(_so_norm(m.get('session_options')) == _so_norm(cfg[m['id']].get('session_options')) for m in data if 'session_options' in m)


_SRC_SNAP = {}  # (路径, 修改时间, 大小) → [bytes, 最近一次用的时间]：同一个原视频排进好几段时共用一份（P01）
_SRC_LOCK = threading.Lock()


def src_snapshot(path):
    """原视频的一份快照（bytes）。同一个文件（同样的修改时间和大小）排进好几段时给同一个对象，不再每段复制一份；
    排队期间文件被移动 / 替换，已经排上的照样用它们拿到的快照。没有任务再用（只剩这里引用）的快照过 1 分钟就放掉"""
    st = os.stat(path)
    key = (os.path.normcase(os.path.abspath(path)), st.st_mtime_ns, st.st_size)
    now = time.time()
    with _SRC_LOCK:
        for k in [k for k, (d, t) in _SRC_SNAP.items() if k != key and sys.getrefcount(d) <= 3 and now - t > 60]:
            _SRC_SNAP.pop(k, None)
        ent = _SRC_SNAP.get(key)
        if ent:
            ent[1] = now
            return ent[0]
    with open(path, 'rb') as f:
        data = f.read()
    with _SRC_LOCK:
        ent = _SRC_SNAP.setdefault(key, [data, now])  # 两个线程同时读了：用先放进去的那份
        return ent[0]


def video_edit_submit(b, sp):
    """后台提交一单改视频（批量配方、Agent 用）：和 /api/video/jobs 改视频那一段一样。
    2026-11-17 审查 P01：以前素材库的原视频先读成 Base64 文字、再解码成每段各自的一份（文字也留在任务里）——
    32 MB 的素材分 16 段，提交路上就留住约 1.2 GB。现在素材库 / 视频库的原视频直接读成共享的快照（src_snapshot），请求里只留路径"""
    v = b.get('video') if isinstance(b.get('video'), dict) else {}
    vid = None
    if v.get('mats') and isinstance(v.get('mats'), str):
        path = mats_path(v['mats'])
        if not os.path.isfile(path):
            raise ValueError('素材库中找不到该文件：' + v['mats'])
        if os.path.getsize(path) > 80 * 1048576:
            raise ValueError('素材库中的该文件过大（上限约 80MB）：' + v['mats'])
        vid = src_snapshot(path)
        b = {**mats_inline({k: x for k, x in b.items() if k != 'video'}), 'video': {'mats': v['mats']}}
    else:
        b = mats_inline(b); v = b.get('video') if isinstance(b.get('video'), dict) else {}
        if v.get('gallery'):
            x = videogen.gallery_get(str(v['gallery']), sp)
            if not x:
                raise ValueError('视频库中已找不到原视频')
            b['src_vid'] = x['id']
            vid = src_snapshot(videogen.vfile(sp, x['file']))
        elif isinstance(v.get('data'), str):
            vid = base64.b64decode(v['data'].split(',', 1)[1])
    return videogen.submit(b, None, ffmpeg, None, vid)


def batch_split(path, sp, dur):
    """批量配方的“推荐分段”：和网页上点“推荐分段”一样（够了的话按用户自己的选段学出来的偏好）"""
    import cutpoints, segpref
    cd = os.path.join(VTMP if sp == 'v' else TMP, 'cutpoints')
    # 显卡空不空只看真正在用显卡的任务（gpu_busy）；以前用 busy_work，批量自己正在推进（BUSY）也算忙，结果总落到 CPU 上慢慢算（P02）
    cp = cutpoints.cached(path, cd) or cutpoints.analyze(path, videogen.FFMPEG, videogen._probe, cd, True, lambda: not gpu_busy())
    st = segpref.status(SEGPREF_V if sp == 'v' else SEGPREF_N)
    return segpref.split(cp, dur or cp.get('dur'), st.get('model') if st.get('use') == 'learned' else None)


def kill_ours(*names, port=None):
    """结束程序文件在本项目里的这些进程（2026-11-14 审查：以前 taskkill /im 按名字全杀，会连别的程序、测试实例的同名进程一起结束）。
    port：只结束在这个端口上监听的那个（2026-11-16 审查：同一个项目里的测试实例也是本项目的程序，只看路径会误杀）"""
    import psutil
    root = os.path.normcase(os.path.abspath(ROOT)) + os.sep
    for p in psutil.process_iter(['name', 'exe']):
        try:
            if (p.info['name'] or '').lower() in names and os.path.normcase(p.info['exe'] or '').startswith(root):
                if port and not any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port for c in p.net_connections('tcp')):
                    continue
                p.kill()
        except (psutil.Error, OSError):
            pass


ENGINE_SHARED = False  # 测试实例设为 True：8080 的配音引擎是借正式 Studio 的，不重启、不关（2026-11-17 审查 F05）
ENGINE_OWNED = False   # 这个进程自己启动的引擎（借来的不算）


def start_engine():
    global ENGINE_OWNED
    if engine_alive():
        if engine_config_matches():
            return None
        if ENGINE_SHARED and not ENGINE_OWNED:  # 借用的引擎：配置不一样也不动它（以前测试实例会把正式 Studio 的引擎重启掉）
            print('配音引擎是借用的（和正式 Studio 共用）：配置不同也不重启', flush=True)
            return None
        print('引擎配置已更新，正在重启引擎……')
        kill_ours('audiocpp_server.exe', port=urllib.parse.urlsplit(ENGINE).port)
        for _ in range(20):
            if not engine_alive():
                break
            time.sleep(0.5)
    lp = os.path.join(STUDIO, 'engine.log')
    try:  # 上一次的日志留一份：崩溃后自动重启，不会把崩溃原因冲掉
        if os.path.isfile(lp) and os.path.getsize(lp):
            os.replace(lp, lp + '.prev')
    except OSError:
        pass
    log = open(lp, 'w', encoding='utf-8')
    p = subprocess.Popen([ENGINE_EXE, '--config', server_cfg_file(), '--ui', '--idle-unload-ms', '900000'],
                         cwd=os.path.join(ROOT, 'audio.cpp'), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    log.close()
    ENGINE_OWNED = True
    for _ in range(120):
        if engine_alive():
            return p
        if p.poll() is not None:
            break
        time.sleep(0.5)
    sys.exit('audio.cpp 引擎启动失败，请查看 studio/engine.log')


def transcribe(wav_path, tag='', language=None):
    act('语音识别中（Qwen3-ASR）…', tag)
    body, _ = engine('/v1/audio/transcriptions', {'model': ASR_MODEL, 'audio': wav_path.replace('\\', '/'),
                                                  **({'options': {'language': language}} if language else {})})
    return json.loads(body.decode('utf-8')).get('text', '').strip()


# ---------------------------------------------------------------- 带时间戳的字幕（Qwen3-ASR + Qwen3-ForcedAligner）
SENT_END = '。！？!?；;…'
WORD_CH = re.compile(r'[^\W_]')  # 字母 / 数字 / 汉字 / 假名 / 韩文 / 西里尔字母……（以前只认汉字和英文，日文假名、韩文的时间会错位）


def transcribe_ts(wav16, tag='', language=None):
    """识别并返回逐字时间戳：(带标点的文字, [{'c': 字, 's': 秒, 'e': 秒}, ...])"""
    body, _ = engine('/v1/audio/transcriptions/details', {'model': ASR_MODEL, 'audio': wav16.replace('\\', '/'),
                                                         'options': {'return_timestamps': True, 'preserve_punctuation': True, **({'language': language} if language else {})}})
    r = json.loads(body.decode('utf-8'))
    sr = r.get('sample_rate') or 16000
    chars = []
    for w in r.get('words') or []:
        tok, s, e = w.get('word', ''), w['start_sample'] / sr, w['end_sample'] / sr
        cs = [c for c in tok if WORD_CH.match(c)] or ([tok] if tok.strip() else [])
        for k, c in enumerate(cs):  # 英文单词按字母平分时长
            chars.append({'c': c, 's': s + (e - s) * k / len(cs), 'e': s + (e - s) * (k + 1) / len(cs)})
    return r.get('text', ''), chars, r.get('language') or language


def make_sentences(text, chars, soft_max=26, gap_break=0.9):
    """把带标点的文字和逐字时间戳对齐，切成字幕句：句号/问号等处断句；太长时在逗号处断；长时间停顿也断。"""
    sents, cur, k = [], None, 0

    def flush():
        nonlocal cur
        if cur and WORD_CH.search(cur['text']):
            cur['text'] = cur['text'].strip(' ，,、')
            sents.append(cur)
        cur = None
    for ch in text:
        if WORD_CH.match(ch):
            if k >= len(chars):
                if cur:
                    cur['text'] += ch
                continue
            t = chars[k]; k += 1
            if cur and t['s'] - cur['e'] > gap_break and len(cur['text']) >= 4:
                flush()
            if not cur:
                cur = {'s': t['s'], 'e': t['e'], 'text': ''}
            cur['text'] += ch
            cur['e'] = max(cur['e'], t['e'])
        else:
            if cur:
                cur['text'] += ch
                if ch in SENT_END or (ch in '，,' and len(cur['text']) >= soft_max):
                    flush()
    flush()
    for t in chars[k:]:  # 标点文字比时间戳短（极少见）：剩下的字按停顿成句
        if not cur or t['s'] - cur['e'] > gap_break:
            flush(); cur = {'s': t['s'], 'e': t['e'], 'text': ''}
        cur['text'] += t['c']; cur['e'] = t['e']
    flush()
    return [{'s': round(x['s'], 3), 'e': round(x['e'], 3), 'text': x['text']} for x in sents]


ASR_SPEED = [0.05]  # 识别 1 秒音频大约要几秒（每次识别完按实际用时更新；给“正在生成字幕”的进度估时间用）


def compute_subs(wav_path, out_json, tag='', language=None, prog=None):
    """prog（可选的 dict）：写进 dur（音频秒数）、t1（开始识别的时间）、eta（预计识别要几秒），给前台估进度用"""
    tmp16 = out_json + '.16k.wav'
    ffmpeg('-i', wav_path, '-ac', '1', '-ar', '16000', tmp16)
    try:
        act('生成字幕：识别文字并对齐每个字的时间…', tag)
        t0 = time.time()
        dur = max(0.0, (os.path.getsize(tmp16) - 44) / 32000)  # 16 kHz 单声道 16 位：每秒 32000 字节
        if prog is not None:
            prog.update(dur=dur, t1=t0, eta=max(2.0, dur * ASR_SPEED[0]))
        text, chars, lang = transcribe_ts(tmp16, tag, language)
        if dur > 20:  # 太短的不算（固定开销占大头，会把速度估得很慢）
            ASR_SPEED[0] = ASR_SPEED[0] * .6 + (time.time() - t0) / dur * .4
    finally:
        os.remove(tmp16)
    d = {'sents': make_sentences(text, chars), 'chars': chars, 'language': lang}
    write_json(out_json, d)  # 先写临时文件再换：别的请求不会读到写了一半的
    act(f'字幕完成：{len(d["sents"])} 句，用时 {time.time() - t0:.1f} 秒', tag, 'ok')
    return d


subs_state = {}  # 上传后的后台字幕任务：文件名 -> 'running' | 'error:…'


def start_upload_subs(name, tag='', cache=None):
    """上传后的字幕。cache = 按文件内容算的缓存路径：同一段录音再上传，直接用上次的字幕，不用重新识别。"""
    path, out = os.path.join(tmp_dir(), name), os.path.join(tmp_dir(), name + '.subs.json')
    if cache and os.path.isfile(cache):
        shutil.copyfile(cache, out)
        return
    subs_state[name] = 'running'
    sp = space()

    def work():
        CTX.space = sp
        try:
            compute_subs(path, out, tag)
            if cache:
                shutil.copyfile(out, cache)
            subs_state.pop(name, None)
        except Exception as e:
            subs_state[name] = 'error:' + str(e)
    threading.Thread(target=work, daemon=True).start()


def pair_subs(src_sents, out_chars, pad=0.12):
    """换声和原录音时间轴相同：按原录音每句的时间窗，取出换声结果里落在这段时间的字，做成一一对应的句子。"""
    out = []
    for s in src_sents:
        txt = ''.join(c['c'] for c in out_chars if s['s'] - pad <= (c['s'] + c['e']) / 2 < s['e'] + pad)
        out.append({'s': s['s'], 'e': s['e'], 'text': txt})
    return out


def wav_seconds(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes() / w.getframerate()


# ================================================================ 模型目录（来自 audio.cpp 官方 model_specs）
def read_json(path, default=None):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, obj, **kw):
    tmp = f'{path}.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
    for k in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows：别的线程正好打开着这个文件
            if k == 9:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.05)


def family_spec(family):
    return read_json(os.path.join(SPECS, family + '.json'), {}) or {}


def family_profile(family):
    common = read_json(os.path.join(PROFILES, '_common.json'), {})
    prof = read_json(os.path.join(PROFILES, family + '.json'), {}) or {}
    merged = dict(prof)
    merged['options_zh'] = {**common.get('options_zh', {}), **prof.get('options_zh', {})}
    merged['hidden_options'] = sorted(set(common.get('hidden_options', [])) | set(prof.get('hidden_options', [])))
    return merged


ROLE_NAMES = ('clone', 'direct', 'design', 'preset')
FAMILY_ORDER = ['breeze_tts', 'index_tts2', 'qwen3_tts']


def list_models():
    """把引擎里的模型按家族分组成“逻辑模型”。同一家族的多个官方变体（如 Qwen3 的 Base / VoiceDesign /
    CustomVoice）按 profile 里的 variants 关键字分配到不同用途。没有 profile 的新模型按 spec 自动推断。"""
    data = json.loads(engine('/v1/models')[0])
    groups = {}
    for m in data['data']:
        if m['task'] in ('tts', 'clon', 'vdes'):
            groups.setdefault(m['family'], []).append(m)
    out = []
    for fam, ms in groups.items():
        spec, prof = family_spec(fam), family_profile(fam)
        opts = spec.get('options', {}).get('request', [])
        names = {o['name'] for o in opts}
        roles = prof.get('roles') or {
            'clone': 'clone' in spec.get('tasks', []) or 'reference_text' in names,
            'direct': 'instruct' in names and 'clone' in spec.get('tasks', []),
            'design': 'design' in spec.get('tasks', []), 'preset': False}
        vmap = prof.get('variants')
        variants = {}
        for role in ROLE_NAMES:
            if not roles.get(role):
                continue
            if vmap:
                kw = vmap.get(role) or (vmap.get('clone') if role == 'direct' else None)
                cand = [m for m in ms if kw and kw in os.path.basename(m['path']).lower()]
            else:
                cand = ms
            if cand:
                variants[role] = cand[0]['id']
        if not variants:
            continue
        out.append({
            'key': fam, 'family': fam, 'ids': [m['id'] for m in ms], 'variants': variants,
            'roles': {r: r in variants for r in ROLE_NAMES},
            'display_name': prof.get('label') or spec.get('display_name', fam),
            'description': spec.get('description', ''), 'languages': spec.get('languages', []),
            'options': opts, 'profile': prof, 'loaded': any(m.get('loaded') for m in ms),
        })
    out.sort(key=lambda g: FAMILY_ORDER.index(g['key']) if g['key'] in FAMILY_ORDER else 99)
    return out


def model_info(key):
    for m in list_models():
        if m['key'] == key or key in m['ids']:
            return m
    raise RuntimeError('引擎中没有该模型：' + str(key))


def pick_mode(model, voice, preset, instruct, emotion_vector, emotion_auto=False):
    if preset:
        return 'preset'
    if voice:
        auto = emotion_auto and model.get('family') == 'index_tts2'  # 情绪跟随正文：不写情绪也走导演模式
        return 'direct' if (instruct or emotion_vector or auto) and model['roles']['direct'] else 'clone'
    return 'design'


def build_request(model, text, voice, instruct, user_opts, seed, preset=None, emotion_vector=None, emotion_auto=False):
    """把网页的选择翻译成该模型官方支持的请求：只传 spec 里声明过的参数，其余一律用官方默认。"""
    fam, prof = model['family'], model['profile']
    d = prof.get('defaults', {})
    instruct = (instruct or '').strip()
    mode = pick_mode(model, voice, preset, instruct, emotion_vector, emotion_auto)
    if mode not in model['variants']:
        raise RuntimeError(f"{model['display_name']} 不支持此用法（{mode}），请更换模型或先选择音色")
    allowed = {o['name'] for o in model['options']}
    opts = {k: v for k, v in (user_opts or {}).items() if k in allowed and v not in (None, '')}
    for o in model['options']:  # 数值参数按 spec 的范围夹住；引擎要求大于 0 的几项不允许 0（否则整段生成失败）
        k = o['name']
        if k not in opts or o.get('type') not in ('float', 'int'):
            continue
        try:
            v = float(opts[k])
        except (TypeError, ValueError):
            raise RuntimeError(f'参数 {k} 须为数字')
        pos = 0.01 if k == 'top_p' else 0.05 if ('temperature' in k or k == 'duration_scale') else None
        lo = [x for x in (o.get('min'), pos) if x is not None]
        if lo:
            v = max(float(max(lo)), v)
        if o.get('max') is not None:
            v = min(float(o['max']), v)
        if k in ('top_p', 'emotion_alpha'):
            v = min(1.0, max(0.0, v))
        opts[k] = int(round(v)) if o['type'] == 'int' else v
    opts['seed'] = int(seed)
    if fam == 'breeze_tts':
        if mode == 'clone':
            # 官方纯克隆模板不带指令。audio.cpp 总会给条件分支加默认指令，但它的 CFG 对照分支正好是官方纯克隆提示，
            # guidance_scale=0 时输出 = 对照分支，等价于官方 Voice Clone。
            opts['guidance_scale'] = d.get('clone_guidance', 0)
            opts.pop('instruct', None)
        else:
            opts.setdefault('guidance_scale', d.get(mode + '_guidance', 4))
            opts['instruct'] = instruct
    elif fam == 'index_tts2':
        for k in ('emotion_vector', 'use_emotion_text', 'emotion_text'):
            opts.pop(k, None)
        if mode == 'direct':
            if emotion_vector:
                opts['emotion_vector'] = ','.join(f'{float(x):.3f}' for x in emotion_vector)
            elif instruct:
                opts['use_emotion_text'] = True
                opts['emotion_text'] = instruct
            else:  # 情绪跟随正文：官方用法 use_emo_text=true 且不给情绪文字 = 按要读的正文自己推断情绪
                opts['use_emotion_text'] = True
            opts.setdefault('emotion_alpha', d.get('direct_emotion_alpha', 0.6))
        else:
            opts.pop('emotion_alpha', None)
    elif fam == 'qwen3_tts':
        opts.pop('instruct', None)
        if mode in ('design', 'preset') and instruct:
            opts['instruct'] = instruct
        if mode == 'preset':
            opts['voice_id'] = preset
        if mode != 'clone':
            opts.pop('x_vector_only_mode', None)
    elif instruct and 'instruct' in allowed and mode != 'clone':
        opts['instruct'] = instruct
    text = mark_interjections(text, prof.get('question_interjections'))
    if 'text_chunk_size' in allowed:
        opts['text_chunk_size'] = max(600, len(text) + 50)  # 网页已按句子切好，避免引擎再切一次
    payload = {'model': model['variants'][mode], 'input': text, 'options': opts}
    if mode in ('clone', 'direct'):
        payload['voice_ref'] = voice['wav']
        if ('reference_text' in allowed or fam == 'breeze_tts') and not opts.get('x_vector_only_mode'):  # 只用音色特征时不需要参考文本
            payload['reference_text'] = voice['transcript']
    return payload, mode


def speak(payload, out_path, tag=''):
    mid = payload['model']
    try:
        info = next((m for m in json.loads(engine('/v1/models', timeout=5)[0])['data'] if m['id'] == mid), {})
        if not info.get('loaded'):
            act(f'正在将模型 {mid} 载入显卡（首次约 5~20 秒，显存不足时会先卸载另一个模型）…', tag)
    except Exception:
        pass
    o = payload.get('options', {})
    bits = [f'模型 {mid}', f"{len(payload['input'])} 字", f"seed {o.get('seed')}"]
    if 'guidance_scale' in o:
        bits.append(f"guidance {o['guidance_scale']}")
    if o.get('instruct'):
        bits.append('指令「' + o['instruct'][:30] + '」')
    if o.get('emotion_text'):
        bits.append('情绪「' + o['emotion_text'][:20] + f"」强度 {o.get('emotion_alpha')}")
    if o.get('emotion_vector'):
        bits.append('情绪向量 ' + o['emotion_vector'])
    if o.get('voice_id'):
        bits.append('预设 ' + o['voice_id'])
    marks = re.findall(r'<[^|<>\n]{1,20}\|[^<>\n]{1,60}>', payload['input'])
    if marks:
        bits.append('读音标注 ' + ' '.join(marks[:6]) + (' …' if len(marks) > 6 else ''))
    act('→ 引擎生成：' + ' · '.join(bits), tag)
    t0 = time.time()
    body, ctype = engine('/v1/audio/speech', payload)
    if 'json' in ctype:
        raise RuntimeError(body.decode('utf-8', 'replace')[:300])
    with open(out_path, 'wb') as f:
        f.write(body)
    dt, dur = time.time() - t0, wav_seconds(out_path)
    act(f'← 完成：{dur:.1f} 秒音频，用时 {dt:.1f} 秒（{dur / max(dt, 0.01):.1f}× 实时）', tag)


# ================================================================ 文本
TAG_RE = re.compile(r'[\[(（][^\]\)）\n]{1,12}[\])）]')
PRON_RE = re.compile(r'<([^|<>\n]{1,20})\|[^<>\n]{1,60}>')  # IndexTTS-2.5 读音标注 <文字|拼音>
PAUSE_RE = re.compile(r'[\[［]\s*(?:停顿|停|pause)\s*([0-9]+(?:\.[0-9]+)?)?\s*(?:秒|s)?\s*[\]］]', re.I)
DEFAULT_PAUSE_TAG = 0.8
DIRECTION_RE = re.compile(r'^\s*[{｛]([^}｝\n]{1,120})[}｝]\s*')


def mark_interjections(text, table):
    """单独的疑问语气词（句首或标点后、紧跟问号）→ <嗯|ng2> 这类官方读音标注。已手动标注的不会重复处理。"""
    if not table:
        return text
    chars = ''.join(re.escape(k) for k in table)
    return re.sub(r'(^|[\s，,。.！!？?；;：:、“”‘’"\'「」『』（）()…—])([' + chars + r'])(?=[？?])',
                  lambda m: f'{m.group(1)}<{m.group(2)}|{table[m.group(2)]}>', text)


def strip_tags(s):
    return TAG_RE.sub('', PRON_RE.sub(lambda m: m.group(1), s))


CN_DIG = {'零': 0, '〇': 0, '一': 1, '幺': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
CN_UNIT = {'十': 10, '百': 100, '千': 1000}
CN_NUM_RE = re.compile('[零〇一幺二两三四五六七八九十百千万亿]+')


def cn2num(t):
    """中文数字 → 整数：一千二百三十一亿二千三百一十二万三千一百二十三 → 123123123123"""
    for big, k in (('亿', 10 ** 8), ('万', 10 ** 4)):
        if big in t:
            a, b = t.split(big, 1)
            return (cn2num(a) or 1) * k + (cn2num(b) if b else 0)
    sec = num = 0
    for ch in t:
        if ch in CN_DIG:
            num = CN_DIG[ch]
        elif ch in CN_UNIT:
            sec += (num or 1) * CN_UNIT[ch]; num = 0
    return sec + num


def norm(s):
    """比对“有没有读错”之前：去掉标记和标点，数字统一成阿拉伯数字（原文写 123、识别出“幺二三”或“一百二十三”都算对）"""
    s = unicodedata.normalize('NFKC', strip_tags(s)).lower()
    s = re.sub(r'(\d+(?:\.\d+)?)([十百千万亿]+)', lambda m: num_unit(m.group(1), m.group(2)), s)  # 3万 → 30000（ASR 读成“三万”）
    s = re.sub(r'百分之', '', s)  # 50% ↔ 百分之五十（% 会被去掉）
    s = CN_NUM_RE.sub(lambda m: str(cn2num(m.group())) if any(u in m.group() for u in '十百千万亿') else ''.join(str(CN_DIG[c]) for c in m.group()), s)
    s = re.sub(r'(?<=\d)点(?=\d)', '', s)  # 三点五 → 35，和原文 3.5（去掉小数点后）一样
    return re.sub(r'[^一-鿿0-9a-z]', '', s)


def num_unit(n, units):
    v = float(n)
    for u in units:
        v *= CN_UNIT.get(u) or {'万': 10000, '亿': 100000000}.get(u, 1)
    return str(int(v)) if v == int(v) else str(v)


def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0
    sm = difflib.SequenceMatcher(None, r, h, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != 'equal') / len(r)


def split_script(text, maxlen):
    """按段落和句子切分，尽量让一整段一起生成（保持语气连贯），太长才在句末切开。
    段首 {指令} 只作用于该段落。返回 [{text, direction, end}]，end: 'sent' | 'para'。"""
    segs = []
    for para in re.split(r'\n+', text):
        para = para.strip()
        direction = ''
        m = DIRECTION_RE.match(para)
        if m:
            direction, para = m.group(1).strip(), para[m.end():].strip()
        # [停顿 1秒] 在这里把文字切开，由网页插入精确时长的静音（所有模型通用，标记本身不会发给模型）
        pieces, pos = [], 0
        for pm in PAUSE_RE.finditer(para):
            pieces.append((para[pos:pm.start()], float(pm.group(1) or DEFAULT_PAUSE_TAG)))
            pos = pm.end()
        pieces.append((para[pos:], None))
        para_segs = []
        for k, (piece, pause) in enumerate(pieces):
            piece = piece.strip()
            if not norm(piece):
                if pause and para_segs:  # 连续的停顿标记：时长累加到前一段
                    para_segs[-1]['pause'] = para_segs[-1].get('pause', 0) + pause
                    para_segs[-1]['end'] = 'pause'
                elif pause and segs:
                    segs[-1]['pause'] = segs[-1].get('pause', 0) + pause
                    segs[-1]['end'] = 'pause'
                continue
            sents = re.findall(r'[^。！？!?；;…]+[。！？!?；;…]*[”’」』"）)\]]?', piece) or [piece]
            cur, out = '', []
            for s in sents:
                if cur and len(cur) + len(s) > maxlen:
                    out.append(cur); cur = ''
                while len(s) > maxlen:
                    cut = max(s.rfind(c, 0, maxlen) for c in '，,、：:') + 1 or maxlen
                    out.append(s[:cut]); s = s[cut:]
                cur += s
            if cur:
                out.append(cur)
            for i, s in enumerate(out):
                para_segs.append({'text': s, 'direction': direction, 'end': 'sent'})
            if pause:
                para_segs[-1].update(end='pause', pause=pause)
        if para_segs:
            last = para_segs[-1]
            if last['end'] != 'pause':
                last['end'] = 'para'
            else:
                last['para_end'] = True
        segs += para_segs
    return segs


# ================================================================ 音频拼接
def trimmed_frames(path, thresh_db=-45.0, pad_ms=80):
    """读取 16-bit 单声道 WAV，去掉首尾静音（保留少量余量），返回 (params, bytes)。"""
    with wave.open(path, 'rb') as w:
        params, raw = w.getparams(), w.readframes(w.getnframes())
    if params.sampwidth != 2:
        return params, raw
    a = array.array('h', raw)
    rate, ch = params.framerate, params.nchannels
    thresh = 32768 * 10 ** (thresh_db / 20)
    win = max(1, rate // 100) * ch  # 10ms
    def loud(i):
        blk = a[i:i + win]
        return blk and max(abs(min(blk)), abs(max(blk))) > thresh
    start = 0
    while start < len(a) and not loud(start):
        start += win
    end = len(a)
    while end > start and not loud(max(start, end - win)):
        end -= win
    pad = int(rate * pad_ms / 1000) * ch
    start, end = max(0, start - pad), min(len(a), end + pad)
    return params, a[start:end].tobytes()


def merge_segments(paths_and_pauses, out_wav):
    with wave.open(out_wav, 'wb') as out:
        for k, (path, pause) in enumerate(paths_and_pauses):
            params, frames = trimmed_frames(path)
            if k == 0:
                out.setparams(params)
            out.writeframes(frames)
            if pause > 0 and k < len(paths_and_pauses) - 1:
                out.writeframes(b'\0' * int(params.framerate * pause) * params.sampwidth * params.nchannels)


def ffmpeg(*args):
    p = subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError('ffmpeg 处理失败：' + p.stderr[-300:])


# ---------------------------------------------------------------- 人声分离（去掉背景音乐 / 音效，只留说话声）
SEP_CLI = os.path.join(ROOT, 'audio.cpp', 'audiocpp_cli.exe')
SEP_MODEL = os.path.join(ROOT, 'models', 'Mel-Band-RoFormer-GGUF', 'mel-band-roformer-f16.gguf')
sep_lock = threading.Lock()


def separate_vocals(src, tag=''):
    """用 audio.cpp 的 Mel-Band RoFormer 把 src 拆为人声 / 伴奏，人声转成 24kHz 单声道放进 TMP，返回文件名。
    单独起一个命令行进程（几秒就完），不占推理引擎里已经载入的模型；显卡不行时退回 CPU。"""
    if not os.path.isfile(SEP_MODEL):
        raise RuntimeError('缺少人声分离模型：models/Mel-Band-RoFormer-GGUF/mel-band-roformer-f16.gguf')
    work = os.path.join(tmp_dir(), 'sep_' + uuid.uuid4().hex[:10])
    os.makedirs(work)
    try:
        with sep_lock, gpu_audio():
            inp = os.path.join(work, 'in.wav')
            ffmpeg('-i', src, '-ac', '2', '-ar', '44100', '-sample_fmt', 's16', inp)
            act('去除背景声（Mel-Band RoFormer 人声分离）…', tag)
            err = ''
            for backend in ('cuda', 'cpu'):
                r = subprocess.run([SEP_CLI, '--task', 'sep', '--family', 'mel_band_roformer', '--model', SEP_MODEL, '--backend', backend,
                                    '--audio', inp, '--out-dir', work], cwd=os.path.dirname(SEP_CLI), capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', creationflags=NO_WINDOW, timeout=600)
                if r.returncode == 0 and os.path.isfile(os.path.join(work, 'vocals.wav')):
                    break
                err = (r.stderr or r.stdout)[-300:]
            else:
                raise RuntimeError('人声分离失败：' + err)
        name = f'vox_{uuid.uuid4().hex[:10]}.wav'
        ffmpeg('-i', os.path.join(work, 'vocals.wav'), '-ac', '1', '-ar', '24000', '-sample_fmt', 's16', os.path.join(tmp_dir(), name))
        act('已去除背景声', tag, 'ok')
        return name
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ================================================================ 音色库
def load_meta(lib=LIB):
    with lock:
        return _load_meta(lib)


def _load_meta(lib):
    META, PROMPTS = os.path.join(lib, 'voices.json'), os.path.join(lib, 'prompt_text')
    meta = read_json(META, {}) or {}
    prompts = {}
    if os.path.exists(PROMPTS):
        for line in open(PROMPTS, encoding='utf-8-sig'):
            if '|' in line:
                k, v = line.rstrip('\n').split('|', 1)
                prompts[k.strip()] = v.strip()
    changed = False
    for vid, tr in prompts.items():  # 兼容旧方式添加的音色
        if vid not in meta and os.path.exists(os.path.join(lib, vid + '.wav')):
            meta[vid] = {'name': vid, 'description': '', 'source': 'clone', 'created': os.path.getmtime(os.path.join(lib, vid + '.wav'))}
            changed = True
        if vid in meta and not meta[vid].get('transcript'):
            meta[vid]['transcript'] = tr
    for vid in list(meta):
        if not os.path.exists(os.path.join(lib, vid + '.wav')):
            del meta[vid]; changed = True
    if changed:
        save_meta(meta, lib)
    return meta


def save_meta(meta, lib=LIB):
    with lock:
        META, PROMPTS = os.path.join(lib, 'voices.json'), os.path.join(lib, 'prompt_text')
        write_json(META, meta, indent=2)
        tmp = f'{PROMPTS}.{uuid.uuid4().hex[:6]}.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:  # audio.cpp 原版界面也能读到这些音色
            for vid, m in meta.items():
                f.write(f"{vid}|{m.get('transcript', '').replace(chr(10), ' ')}\n")
        os.replace(tmp, PROMPTS)


def voice_libs():
    return [LIB, VLIB] if space() == 'v' else [LIB]


def voice_lib_of(vid):
    for lib in voice_libs():
        if vid in load_meta(lib):
            return lib
    return None


def get_voice(vid):
    for lib in voice_libs():
        m = load_meta(lib).get(vid)
        if m:
            return {'id': vid, 'wav': os.path.join(lib, vid + '.wav').replace('\\', '/'), **m}
    raise RuntimeError('音色不存在：' + str(vid))


# ================================================================ 任务
jobs = {}
job_queue = []
job_cv = threading.Condition()


class Cancelled(Exception):
    pass


class Job(stages.Tracked):
    def __init__(self, params):
        self.id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.space = space()
        self.dir = os.path.join(jobs_root(), self.id)
        self.params = params
        try:
            maxlen = max(20, min(2000, int(float(params.get('maxlen') or 200))))
        except (TypeError, ValueError):
            maxlen = 200
        self.segments = split_script(params['text'], maxlen)
        os.makedirs(os.path.join(self.dir, 'seg'))
        for i, s in enumerate(self.segments):
            s.update(index=i, status='waiting', cer=None, asr='', attempts=0, seconds=0, mode='')
        self.state, self.message, self.error = 'queued', '排队中', ''
        self.created, self.finished, self.duration = time.time(), None, None
        first = strip_tags(DIRECTION_RE.sub('', params['text'])).strip().splitlines()
        self.title = (params.get('title') or (first[0] if first else '') or '未命名')[:28]
        self.cancel = False
        self.saved = False  # 手动“保存到作品”后为 True；未保存的只出现在历史记录里

    def seg_path(self, i):
        return os.path.join(self.dir, 'seg', f'{i:04d}.wav')

    def render(self, i, attempt, model, voice):
        seg = self.segments[i]
        p = self.params
        instruct = '，'.join(x for x in (p.get('instruct', '').strip(), seg['direction']) if x)
        seed = int(p.get('seed') or 0) + (0 if attempt == 0 else 7919 * attempt + i)
        payload, seg['mode'] = build_request(model, seg['text'], voice, instruct, p.get('options'), seed,
                                             p.get('preset'), p.get('emotion_vector'), bool(p.get('emotion_auto')))
        out = self.seg_path(i) if attempt == 0 else os.path.join(self.dir, 'seg', f'{i:04d}_try{attempt}.wav')
        seg['status'] = 'generating'
        speak(payload, out, self.id)
        seg['attempts'] += 1
        if not p.get('check', True):
            if out != self.seg_path(i):
                os.replace(out, self.seg_path(i))
            seg.update(status='done', seconds=wav_seconds(self.seg_path(i)))
            return
        seg['status'] = 'checking'
        hyp = transcribe(out, self.id)
        c = cer(seg['text'], hyp)
        self.log(f'核对第 {i + 1} 段：字错率 {c:.1%}' + ('  ✓' if c <= self.bad_cer() else '  ✗ 可能读错') + f'｜识别结果：{hyp[:40]}', 'ok' if c <= self.bad_cer() else 'warn')
        if attempt == 0 or seg['cer'] is None or c < seg['cer']:
            if out != self.seg_path(i):
                os.replace(out, self.seg_path(i))
            seg.update(cer=c, asr=hyp, seconds=wav_seconds(self.seg_path(i)))
        elif os.path.exists(out):
            os.remove(out)
        seg['status'] = 'done' if seg['cer'] <= self.bad_cer() else 'warn'

    def bad_cer(self):
        # 网页里的“通过标准”：准确率达到多少算通过（= 1 - 允许的字错率）；没设置就用默认
        v = self.params.get('bad_cer')
        return float(v) if v is not None else (VC_BAD_CER if self.params.get('kind') == 'vc' else BAD_CER)

    def log(self, msg, level='info'):
        act(msg, self.id, level)

    def merge(self, publish=True):
        p = self.params
        self.log(f'拼接 {len(self.segments)} 段：去除每段首尾多余静音，句间停顿 {p.get("pause", 0.35)} 秒、段落停顿 {p.get("pause_para", 0.8)} 秒')
        pause_s, pause_p = float(p.get('pause', 0.35)), float(p.get('pause_para', 0.8))
        final = os.path.join(self.dir, 'output.wav')
        def gap(s):
            if s['end'] == 'pause':  # 用户写的 [停顿 N秒]；若同时是段落结尾，取两者较长的
                return max(float(s.get('pause', DEFAULT_PAUSE_TAG)), pause_p if s.get('para_end') else 0)
            return pause_p if s['end'] == 'para' else pause_s
        tw, tm = final[:-4] + '.new.wav', os.path.join(self.dir, 'output.new.mp3')
        merge_segments([(self.seg_path(i), gap(s)) for i, s in enumerate(self.segments)], tw)
        self.log('导出 MP3（192 kbps）')
        ffmpeg('-i', tw, '-b:a', '192k', tm)
        dur = wav_seconds(tw)
        self.log(f'成品时长 {dur / 60:.1f} 分钟', 'ok')
        return publish_merge(self, tw, tm, dur, publish)

    def run(self):
        try:
            self.state = 'running'
            self.log(f"开始：{self.params.get('model_name', self.params['model'])} · 音色 {self.params.get('voice_name') or '（描述生成）'} · 共 {len(self.segments)} 段")
            model = model_info(self.params['model'])
            voice = get_voice(self.params['voice']) if self.params.get('voice') else None
            retries = max(0, min(10, int(self.params.get('retries', 2)))) if self.params.get('check', True) else 0
            n = len(self.segments)
            for i in range(n):
                if self.cancel:
                    raise Cancelled()
                self.message = f'正在生成第 {i + 1}/{n} 段'
                self.log(f'第 {i + 1}/{n} 段：{self.segments[i]["text"][:28]}…' + (f'（语气：{self.segments[i]["direction"]}）' if self.segments[i]['direction'] else ''))
                self.render(i, 0, model, voice)
                if self.cancel:
                    raise Cancelled()
                for a in range(1, retries + 1):
                    if self.segments[i]['status'] != 'warn' or self.cancel:
                        break
                    self.message = f'第 {i + 1} 段可能读错，自动重做（第 {a} 次）'
                    self.log(f'第 {i + 1} 段更换随机种子重做（第 {a} 次）', 'warn')
                    self.render(i, a, model, voice)
                self.save()  # 每段存一次进度
            if self.cancel:
                raise Cancelled()
            self.message = '正在拼接音频'
            self.merge()
            self.state, self.message = 'done', '完成'
            self.log(f'全部完成，总用时 {time.time() - self.created:.0f} 秒', 'ok')
        except Cancelled:
            self.state, self.message = 'error', '已取消'
            self.log(f'已取消（已生成 {sum(s["status"] in ("done", "warn") for s in self.segments)}/{len(self.segments)} 段）', 'warn')
        except Exception as e:
            self.state, self.error = 'error', str(e)
            self.message = '出错：' + str(e)
            self.log('出错：' + str(e), 'error')
            print_tb()
        self.finished = time.time()
        self.save()

    def redo(self, i, text=None, direction=None):
        """手动重做一段。2026-11-17 审查 F07：以前新 WAV 先替换旧的，合并 / 导出 MP3 / 写记录失败时只回滚字典，
        留下“文字是旧的、声音是新的、成品半新半旧”。现在：这段的文件先备份，成品在临时文件里做好再和记录一起发布（redo_finish），
        任何一步失败，这一段的文件、成品、字典、记录都回到原样"""
        seg = self.segments[i]
        old = dict(seg)
        files = [f for f in (self.seg_path(i), self.seg_path(i)[:-4] + '_best.wav') if os.path.isfile(f)]
        baks = []
        for f in files:
            shutil.copy2(f, f + '.redo-bak'); baks.append(f)
        try:
            self._redo(seg, i, text, direction)
        except BadRequest:  # 这一段重做好了，只是别的段还缺：不回退
            drop_baks(baks)
            raise
        except BaseException:
            for f in baks:
                try:
                    os.replace(f + '.redo-bak', f)
                except OSError:
                    pass
            for f in (self.seg_path(i), self.seg_path(i)[:-4] + '_best.wav', os.path.join(self.dir, 'output.new.wav'), os.path.join(self.dir, 'output.new.mp3')):  # 这次新生成、原来没有的文件
                if os.path.isfile(f) and f not in files:
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            seg.clear(); seg.update(old)
            try:
                self.save()
            except Exception:
                pass
            raise
        drop_baks(baks)

    def _redo(self, seg, i, text, direction):
        if isinstance(text, str) and text.strip():
            seg['text'] = text.strip()
        if isinstance(direction, str):
            seg['direction'] = direction.strip()
        model = model_info(self.params['model'])
        voice = get_voice(self.params['voice']) if self.params.get('voice') else None
        seg['cer'] = None
        self.log(f'手动重做第 {i + 1} 段')
        self.render(i, seg['attempts'] + 1, model, voice)
        redo_finish(self, ['subs_play'])

    def save(self):
        write_json(os.path.join(self.dir, 'job.json'), self.summary(full=True), indent=1)

    def summary(self, full=False):
        segs = self.segments
        d = {'id': self.id, 'kind': self.params.get('kind', 'tts'), 'title': self.title, 'state': self.state, 'message': self.message, 'error': self.error,
             'created': self.created, 'finished': self.finished, 'total': len(segs),
             'done': sum(s['status'] in ('done', 'warn') for s in segs), 'warn': sum(s['status'] == 'warn' for s in segs),
             'duration': self.duration, 'voice': self.params.get('voice'), 'voice_name': self.params.get('voice_name', ''),
             'model': self.params.get('model'), 'model_name': self.params.get('model_name', ''),
             'modes': sorted({s.get('mode') for s in segs if s.get('mode')}), 'saved': getattr(self, 'saved', False), 'has_output': os.path.exists(os.path.join(self.dir, 'output.mp3')),
             'timing': self.timing()}
        if full:
            d['segments'] = segs
            d['params'] = self.params
            d['logs'] = getattr(self, 'logs', [])
        return d


# ================================================================ 换声（语音转换，Seed-VC 等）
def list_vc_models():
    data = json.loads(engine('/v1/models')[0])
    out = []
    for m in data['data']:
        if m['task'] != 'vc':
            continue
        spec, prof = family_spec(m['family']), family_profile(m['family'])
        out.append({'key': m['id'], 'ids': [m['id']], 'family': m['family'], 'loaded': m.get('loaded', False),
                    'display_name': prof.get('label') or spec.get('display_name', m['family']),
                    'description': prof.get('description') or spec.get('description', ''),
                    'options': spec.get('options', {}).get('request', []), 'profile': prof})
    return out


VC_BAD_CER = 0.1  # 换声不改文字，原录音和结果的识别差异超过 10% 就当作吞字/变字，换种子重做


def vc_model_info(key):
    for m in list_vc_models():
        if m['key'] == key:
            return m
    raise RuntimeError('引擎中没有该换声模型：' + str(key))


def read_pcm16(path):
    with wave.open(path, 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise RuntimeError('需要 16 位单声道 WAV')
        return w.getframerate(), array.array('h', w.readframes(w.getnframes()))


def vc_chunk_plan(path, max_s, min_s):
    """在原录音最安静的地方下刀：每块不超过 max_s 秒，在 [min_s, max_s] 范围里找 0.3 秒窗口内能量最低的位置。
    只切不删，拼回去后时间轴和原录音完全一致。"""
    rate, a = read_pcm16(path)
    hop = rate // 100  # 10ms
    n = len(a) // hop
    eng = [0] * n
    for i in range(n):
        blk = a[i * hop:(i + 1) * hop]
        eng[i] = max(abs(min(blk)), abs(max(blk))) if blk else 0
    win = 30
    pref = [0]
    for e in eng:
        pref.append(pref[-1] + e)
    total = len(a) / rate
    cuts, start = [], 0.0
    while total - start > max_s:
        lo, hi = int((start + min_s) * 100), int((start + max_s) * 100) - win
        best = min(range(lo, max(lo + 1, hi)), key=lambda i: pref[i + win] - pref[i])
        cut = (best + win // 2) / 100
        cuts.append((start, cut))
        start = cut
    cuts.append((start, total))
    return rate, cuts


def write_slice(src_rate, a, t0, t1, out):
    i0, i1 = int(t0 * src_rate), int(t1 * src_rate)
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(src_rate)
        w.writeframes(a[i0:i1].tobytes())


class VcJob(Job):
    """换声任务：沿用配音任务的队列、日志、取消、作品/历史记录；“段”= 原录音按停顿切开的一块。"""

    def __init__(self, params):
        self.id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.space = space()
        self.dir = os.path.join(jobs_root(), self.id)
        self.params = params
        src = os.path.join(tmp_dir(), os.path.basename(params.get('source') or ''))
        if not os.path.isfile(src):
            raise RuntimeError('上传的音频已失效，请重新上传')
        os.makedirs(os.path.join(self.dir, 'seg'))
        shutil.copyfile(src, os.path.join(self.dir, 'source.wav'))  # 复制：同一段录音可以接着换成别的音色
        self.segments = []
        self.state, self.message, self.error = 'queued', '排队中', ''
        self.created, self.finished, self.duration = time.time(), None, None
        self.title = (params.get('title') or os.path.splitext(params.get('filename') or '')[0] or '换声')[:28]
        self.cancel, self.saved = False, False
        try:
            self.plan()
        except Exception:
            shutil.rmtree(self.dir, ignore_errors=True)
            raise

    def plan(self):
        p = self.params
        prof = family_profile(vc_model_info(p.get('model') or 'seedvc')['family'])
        if p.get('split', True):
            max_s = max(2.0, min(60.0, float(p.get('chunk') or prof.get('chunk_seconds') or 10)))
        else:  # 关闭智能分段：整段一次转换；超过显存上限（实测 5 分钟）才不得不切开
            max_s = float(prof.get('whole_max_seconds') or 300)
        self.max_s = max_s
        ctx = float(prof.get('context_seconds', 1.0))
        max_s = max(4.0, max_s)
        rate, cuts = vc_chunk_plan(os.path.join(self.dir, 'source.wav'), max_s, max(3.0, max_s * 0.45))
        _, a = read_pcm16(os.path.join(self.dir, 'source.wav'))
        total = len(a) / rate
        self.segments = []
        for i, (t0, t1) in enumerate(cuts):
            # 前后各多送 ctx 秒原录音当上下文（块开头/结尾的字才转得准），转完再按时间精确裁掉
            c0, c1 = max(0.0, t0 - ctx), min(total, t1 + ctx)
            write_slice(rate, a, c0, c1, self.src_path(i))
            self.segments.append({'index': i, 'text': f'{fmt_clock(t0)} – {fmt_clock(t1)}', 'start': t0, 'end': t1,
                                  'ctx_pre': t0 - c0, 'ctx_post': c1 - t1,
                                  'direction': '', 'end_kind': 'chunk', 'status': 'waiting', 'cer': None, 'asr': '',
                                  'attempts': 0, 'seconds': 0, 'mode': 'vc'})

    def src_path(self, i):
        return os.path.join(self.dir, 'seg', f'src_{i:04d}.wav')

    def render(self, i, attempt, model, voice):
        seg, p = self.segments[i], self.params
        seed = int(p.get('seed') or 0) + (0 if attempt == 0 else 7919 * attempt + i)
        allowed = {o['name'] for o in model['options']}
        opts = {k: v for k, v in (p.get('options') or {}).items() if k in allowed and v not in (None, '') and k != 'seed'}
        for k, v in (model['profile'].get('defaults') or {}).items():
            opts.setdefault(k, v)
        req = {'audio': self.src_path(i).replace('\\', '/'), 'voice_ref': voice['wav'], 'seed': seed, 'options': opts}
        seg['status'] = 'generating'
        if attempt == 0:
            self.log(f'→ 引擎换声：模型 {model["key"]} · 第 {i + 1}/{len(self.segments)} 块（{seg["end"] - seg["start"]:.1f} 秒）· seed {seed}'
                     + (' · ' + ' '.join(f'{k}={v}' for k, v in opts.items()) if opts else ''))
        t0 = time.time()
        try:
            body, _ = engine('/v1/tasks/run', {'model': model['key'], 'request': req})
        except RuntimeError as e:
            if 'already prepared for route' not in str(e):
                raise
            # 引擎里 Seed-VC 一次只能准备一条路线：换路线时先卸载再自动重新载入
            self.log('切换转换路线：先卸载模型再重新载入（约 5 秒）…')
            engine('/v1/tasks/unload_models', {'model_ids': [model['key']]})
            body, _ = engine('/v1/tasks/run', {'model': model['key'], 'request': req})
        res = json.loads(body.decode('utf-8'))
        res = res.get('result', res)
        raw_path = self.seg_path(i)[:-4] + '_ctx.wav'
        with open(raw_path, 'wb') as f:
            f.write(base64.b64decode(res['audio']))
        # 裁掉上下文：输出和输入等长（或按 duration_scale 等比例），按比例换算位置
        with wave.open(raw_path, 'rb') as w:
            params, n = w.getparams(), w.getnframes()
            span = seg['ctx_pre'] + (seg['end'] - seg['start']) + seg['ctx_post']
            i0, i1 = round(seg['ctx_pre'] / span * n), round((span - seg['ctx_post']) / span * n)
            w.setpos(i0)
            frames = w.readframes(max(0, i1 - i0))
        with wave.open(self.seg_path(i), 'wb') as w:
            w.setparams(params)
            w.writeframes(frames)
        os.remove(raw_path)
        seg['attempts'] += 1
        dt = time.time() - t0
        self.log(f'← 第 {i + 1} 块完成：{wav_seconds(self.seg_path(i)):.1f} 秒，用时 {dt:.1f} 秒')
        if not p.get('check', True):
            seg.update(status='done', seconds=wav_seconds(self.seg_path(i)))
            return
        # 核对：原录音这一块和换声结果各识别一遍，比较有没有吞字、变字（不比较音色）
        seg['status'] = 'checking'
        if not seg.get('src_asr'):
            seg['src_asr'] = self.asr_of(self.src_path(i), seg['ctx_pre'], seg['end'] - seg['start'])
        hyp = self.asr_of(self.seg_path(i))
        c = cer(seg['src_asr'], hyp) if norm(seg['src_asr']) else 0.0
        self.log(f'核对第 {i + 1} 块：与原录音相差 {c:.1%}' + ('  ✓' if c <= self.bad_cer() else '  ✗ 可能吞字或变字') + f'｜识别结果：{hyp[:40]}',
                 'ok' if c <= self.bad_cer() else 'warn')
        best = self.seg_path(i)[:-4] + '_best.wav'
        if attempt == 0 or seg['cer'] is None or c < seg['cer']:
            shutil.copyfile(self.seg_path(i), best)
            seg.update(cer=c, asr=hyp)
        else:
            shutil.copyfile(best, self.seg_path(i))  # 这次更差：恢复之前更好的那次
        seg.update(status='done' if seg['cer'] <= self.bad_cer() else 'warn', seconds=wav_seconds(self.seg_path(i)))

    def asr_of(self, path, start=None, dur=None):
        tmp16 = os.path.join(self.dir, 'seg', 'asr16.wav')
        ffmpeg(*(['-ss', f'{start:.3f}', '-t', f'{dur:.3f}'] if start is not None else []), '-i', path, '-ac', '1', '-ar', '16000', tmp16)
        try:
            return transcribe(tmp16, self.id)
        finally:
            os.remove(tmp16)

    def merge(self, publish=True):
        self.log(f'按原时间轴拼接 {len(self.segments)} 块（接缝处 10 毫秒淡入淡出，避免咔哒声）')
        final = os.path.join(self.dir, 'output.wav')
        tw, tm = final[:-4] + '.new.wav', os.path.join(self.dir, 'output.new.mp3')
        with wave.open(tw, 'wb') as out:
            for k, s in enumerate(self.segments):
                with wave.open(self.seg_path(k), 'rb') as w:
                    params, raw = w.getparams(), w.readframes(w.getnframes())
                a = array.array('h', raw)
                f = min(len(a) // 4, params.framerate // 100)
                for j in range(f):
                    a[j] = int(a[j] * j / f)
                    a[-1 - j] = int(a[-1 - j] * j / f)
                if k == 0:
                    out.setparams(params)
                out.writeframes(a.tobytes())
        self.log('导出 MP3（192 kbps）')
        ffmpeg('-i', tw, '-b:a', '192k', tm)
        dur = wav_seconds(tw)
        self.log(f'成品时长 {dur / 60:.1f} 分钟（原录音 {self.segments[-1]["end"] / 60:.1f} 分钟）', 'ok')
        return publish_merge(self, tw, tm, dur, publish)

    def run(self):
        try:
            self.state = 'running'
            p = self.params
            model = vc_model_info(p['model'])
            voice = get_voice(p['voice'])
            n = len(self.segments)
            retries = max(0, min(10, int(p.get('retries', 2)))) if p.get('check', True) else 0
            self.log(f"开始换声：{p.get('model_name')} · 目标音色 {p.get('voice_name')} · 原录音 {fmt_clock(self.segments[-1]['end'])}，在停顿处切成 {n} 块（{'智能分段：' if p.get('split', True) else '整段转换：'}每块不超过 {getattr(self, 'max_s', 10):.0f} 秒，前后各带 1 秒上下文）")
            for i in range(n):
                if self.cancel:
                    raise Cancelled()
                self.message = f'正在转换第 {i + 1}/{n} 块'
                self.render(i, 0, model, voice)
                for a in range(1, retries + 1):
                    if self.segments[i]['status'] != 'warn' or self.cancel:
                        break
                    self.message = f'第 {i + 1} 块可能吞字，自动重做（第 {a} 次）'
                    self.log(f'第 {i + 1} 块更换随机种子重做（第 {a} 次）', 'warn')
                    self.render(i, a, model, voice)
            if self.cancel:
                raise Cancelled()
            self.message = '正在拼接音频'
            self.merge()
            self.state, self.message = 'done', '完成'
            self.log(f'全部完成，总用时 {time.time() - self.created:.0f} 秒', 'ok')
        except Cancelled:
            self.state, self.message = 'error', '已取消'
            self.log(f'已取消（已转换 {sum(s["status"] in ("done", "warn") for s in self.segments)}/{len(self.segments)} 块）', 'warn')
        except Exception as e:
            self.state, self.error = 'error', str(e)
            self.message = '出错：' + str(e)
            self.log('出错：' + str(e), 'error')
            print_tb()
        self.finished = time.time()
        self.save()
        if self.state == 'done':
            self.make_subs()  # 成品已经可以听了；字幕在后面补上（对比页用）

    def subs_files(self):
        return os.path.join(self.dir, 'subs_src.json'), os.path.join(self.dir, 'subs_out.json')

    def make_subs(self):
        """原录音和换声结果各做一份逐字时间戳。上传时已经做好的原录音字幕直接拿来用。失败不影响成品。"""
        src_j, out_j = self.subs_files()
        self.subs = 'running'
        try:
            if not os.path.isfile(src_j):
                up = os.path.join(tmp_dir(), os.path.basename(self.params.get('source', '')) + '.subs.json')
                for _ in range(120):  # 上传时的字幕还在做：等它做完
                    if os.path.isfile(up) or not str(subs_state.get(os.path.basename(self.params.get('source', '')), '')).startswith('running'):
                        break
                    time.sleep(1)
                if os.path.isfile(up):
                    shutil.copyfile(up, src_j)
                else:
                    compute_subs(os.path.join(self.dir, 'source.wav'), src_j, self.id)
            if not os.path.isfile(out_j) and os.path.isfile(os.path.join(self.dir, 'output.wav')):
                self.log('生成换声结果的字幕（用于对比）')
                # 用原录音识别出的语言：短句、气声多时自动判断容易误判成别的语言
                compute_subs(os.path.join(self.dir, 'output.wav'), out_j, self.id, read_json(src_j, {}).get('language'))
            self.subs = 'done'
        except Exception as e:
            self.subs = 'error:' + str(e)
            self.log('字幕生成失败（不影响成品）：' + str(e), 'warn')

    def _redo(self, seg, i, text, direction):  # 外面的 redo（失败时回退这一块）在 Job 里
        seg['cer'] = None  # 手动重做：直接采用新的这一次
        self.log(f'手动重做第 {i + 1} 块（更换随机种子）')
        self.render(i, seg['attempts'] + 1, vc_model_info(self.params['model']), get_voice(self.params['voice']))
        redo_finish(self, [os.path.basename(self.subs_files()[1])[:-5]])  # 成品变了，换声字幕下次打开对比时重新生成


def drop_baks(paths):
    for f in paths:
        try:
            os.remove(f + '.redo-bak')
        except OSError:
            pass


class swap_in:
    """把做好的临时文件换成正式文件（旧的先挪成 .redo-old）；调用 undo() 换回旧的，commit() 删掉旧的"""
    def __init__(self, d, pairs):
        self.done = []
        try:
            for tmp, name in pairs:
                dst = os.path.join(d, name)
                old = dst + '.redo-old'
                had = os.path.exists(dst)
                if had:
                    os.replace(dst, old)
                self.done.append((dst, old, had))
                os.replace(tmp, dst)
        except BaseException:
            self()
            for tmp, _ in pairs:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    def __call__(self):
        for dst, old, had in reversed(self.done):
            try:
                if had:
                    os.replace(old, dst)
                elif os.path.exists(dst):
                    os.remove(dst)
            except OSError:
                pass
        self.done = []

    def commit(self):
        for dst, old, had in self.done:
            if had:
                try:
                    os.remove(old)
                except OSError:
                    pass
        self.done = []


def publish_merge(job, tw, tm, dur, publish):
    """拼接的结果：publish=True（正常生成）直接换成正式成品；False（单段重做）交给调用的一起发布"""
    if not publish:
        return tw, tm, dur
    swap_in(job.dir, [(tw, 'output.wav'), (tm, 'output.mp3')]).commit()
    job.duration = dur
    return tw, tm, dur


def redo_finish(job, subs):
    """单独重做一段之后：所有段都有了才重新合成成品（失败 / 取消的任务有的段根本没生成过，合不起来）；
    成品变了，旧的字幕和它的翻译（<名字>.json / <名字>.tr-*.json）一起删掉，下次播放时重新生成。"""
    ready = all(s.get('status') in ('done', 'warn') for s in job.segments)
    if ready:
        tw, tm, dur = job.merge(publish=False)  # 新成品先在临时文件里做好（失败时旧成品原封不动）
        before = (job.duration, job.finished, job.state, job.message, job.error)
        undo = swap_in(job.dir, [(tw, 'output.wav'), (tm, 'output.mp3')])
        try:
            job.duration, job.finished = dur, time.time()  # 网页按 finished 换掉缓存的音频地址
            if job.state != 'done':  # 原来失败 / 取消的任务，补齐以后就算完成了
                job.state, job.message, job.error = 'done', '完成', ''
            job.save()
        except BaseException:
            undo()
            job.duration, job.finished, job.state, job.message, job.error = before
            raise
        undo.commit()
        for f in os.listdir(job.dir):  # 成品已经换好：旧字幕和它的翻译作废
            if any(f == n + '.json' or f.startswith(n + '.tr-') for n in subs):
                try:
                    os.remove(os.path.join(job.dir, f))
                except OSError:
                    pass
        return
    job.save()
    if not ready:
        raise BadRequest('该段已重做完成；但仍有其他段未生成成功，暂时无法合成完整的成品。可将其余各段也重做一遍。')


def fmt_clock(sec):
    sec = int(round(sec))
    return f'{sec // 60}:{sec % 60:02d}' if sec < 3600 else f'{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}'


def job_worker():
    while True:
        with job_cv:
            while not job_queue:
                job_cv.wait()
            job = job_queue.pop(0)
        CTX.space = getattr(job, 'space', 'n')  # 任务在自己的空间里运行（找音色、存文件）
        try:
            with gpu_audio():  # 整个配音 / 换声任务期间都不开始新的生图（不然每一段都要和生图互相赶出显存）
                job.run()
        except Exception as e:
            print_tb()
            try:
                job.state, job.error, job.message, job.finished = 'error', str(e), '出错：' + str(e), time.time()
            except Exception:
                pass


def load_old_jobs():
    for sp, root in (('n', JOBS), ('v', VJOBS)):
        for name in sorted(os.listdir(root)):
            load_job(sp, root, name)


def load_job(sp, root, name):
    try:  # 一个坏掉的 job.json 不能让整个程序起不来
        d = read_json(os.path.join(root, name, 'job.json'))
        if not isinstance(d, dict) or not isinstance(d.get('params'), dict):
            return
        cls = VcJob if d['params'].get('kind') == 'vc' else Job
        j = cls.__new__(cls)
        j.space = sp
        j.id, j.dir, j.params, j.segments = name, os.path.join(root, name), d['params'], list(d.get('segments') or [])
        j.state, j.message, j.error = d.get('state', 'error'), d.get('message', ''), d.get('error', '')
        j.created, j.finished, j.title, j.duration, j.cancel = d.get('created') or 0, d.get('finished'), d.get('title') or name, d.get('duration'), False
        j.logs = d.get('logs', [])
        j.saved = d.get('saved', False)
        if j.state in ('queued', 'running'):
            j.state, j.message = 'error', '上次未完成（程序被关闭）'
            j.finished = j.finished or j.created
        for sg in j.segments:  # 生成到一半被关：这一段算失败（可以单独重做）
            if isinstance(sg, dict) and sg.get('status') in ('generating', 'checking', 'waiting'):
                sg['status'] = 'error'
        j.restore_timing(d.get('timing'), j.created, j.finished)  # 计时用存下来的，不从现在重新开始（F13）
        jobs[j.id] = j
    except Exception:
        print_tb()


def job_visible(jid):
    j = jobs.get(jid)
    return j is not None and getattr(j, 'space', 'n') == space()


def cookie_val(cookie, name):
    for part in (cookie or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == name:
            return v
    return ''


VTOKS = {}  # 私密空间的登录凭证 -> {'remote': 是不是手机上发的, 'last': 最近一次用}：只在内存里，重启即失效
REMOTE_IDLE = 1800  # 手机上的私密空间：30 分钟没有任何请求（比如关了 Safari）就自动失效
_vfail = {}  # 输错密钥的记录：地址 -> [时间…]


def vault_ok(cookie):
    tok = cookie_val(cookie, 'vault')
    t = VTOKS.get(tok) if tok else None
    if not t:
        return False
    if t['remote'] and time.time() - t['last'] > REMOTE_IDLE:
        VTOKS.pop(tok, None)
        return False
    t['last'] = time.time()
    return True


# 播放页认得的格式。NATIVE 里的浏览器能直接放；其余的（avi、wmv、rmvb、ape……）第一次播放时用 ffmpeg 转一份能放的，存在缓存里
NATIVE_EXT = {'.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.opus', '.mp4', '.mov', '.m4v', '.webm', '.mkv'}
VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.wmv', '.flv', '.ts', '.m2ts', '.mts', '.mpg', '.mpeg', '.vob', '.3gp', '.rmvb', '.rm', '.f4v', '.asf'}
AUDIO_EXT = NATIVE_EXT | VIDEO_EXT | {'.wma', '.ape', '.wv', '.amr', '.ac3', '.dts', '.mka', '.aiff', '.aif', '.tta'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif'}
_lib_cache = {}  # 文件夹 -> {'t': 扫描时间, 'data': 结果}


def longp(path):
    """Windows 路径超过 260 个字符时，普通写法打不开文件；加上 \\\\?\\ 前缀就能打开。"""
    if os.name == 'nt' and len(path) >= 240 and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path


def lib_path(rel):
    root = lib_root()
    path = os.path.normpath(os.path.join(root, *rel.split('/')))
    if not path.startswith(root + os.sep) or not os.path.isfile(longp(path)):
        raise RuntimeError('文件不存在')
    return longp(path)


cover_sem = threading.Semaphore(4)  # 2026-11-08：2 → 4（素材库一个文件夹几十个视频，第一次打开时封面做得快一点；ffmpeg 只用 CPU，不占显卡）
film_sem = threading.Semaphore(2)


def film_for(path, n, h=72):
    """剪辑条上的一排小画面（n 张，每张高 h，横着拼成一张 jpg），缓存在封面缓存里。
    以前在浏览器里用一个隐藏的播放器来回跳着截：4K / HEVC 的视频很慢，生成视频时显卡占满就一直出不来（2026-11-08 用户）。
    这里用 ffmpeg（只用 CPU），几张同时截，一般 1 秒内做好。"""
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    n = max(3, min(60, int(n))); h = max(36, min(160, int(h)))
    st = os.stat(path)
    key = hashlib.sha1(f'film|{path}|{st.st_mtime}|{st.st_size}|{n}|{h}'.encode('utf-8')).hexdigest()
    jpg = os.path.join(covers_dir(), key + '.f.jpg')
    if os.path.isfile(jpg):
        return jpg
    with film_sem:
        if os.path.isfile(jpg):
            return jpg
        try:
            dur = float(subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                       capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout.strip() or 0)
        except Exception:
            dur = 0
        if dur <= 0:
            return None
        tag = uuid.uuid4().hex[:6]
        outs = [f'{jpg}.{tag}.{i}.jpg' for i in range(n)]
        def one(i):
            t = min(max(0.0, dur - 0.05), (i + 0.5) * dur / n)
            _grab(['-ss', f'{t:.3f}', '-i', path, '-an', '-map', '0:v:0', '-frames:v', '1', '-vf', f'scale=-2:{h}', '-q:v', '4', outs[i]])
        with ThreadPoolExecutor(max_workers=min(12, n)) as ex:
            list(ex.map(one, range(n)))
        try:
            ims = [Image.open(o).convert('RGB') if os.path.isfile(o) and os.path.getsize(o) > 0 else None for o in outs]
            ok = [im for im in ims if im]
            if not ok:
                return None
            fw = ok[0].width
            strip = Image.new('RGB', (fw * n, h), (24, 24, 26))
            last = ok[0]
            for i, im in enumerate(ims):  # 个别没截到（片尾等）：用前一张补上
                last = im or last
                strip.paste(last.resize((fw, h)) if last.size != (fw, h) else last, (i * fw, 0))
            tmp = f'{jpg}.{tag}.tmp.jpg'
            strip.save(tmp, 'JPEG', quality=72)
            for im in ok:
                im.close()
            os.replace(tmp, jpg)
            return jpg
        finally:
            for o in outs:
                try:
                    os.remove(o)
                except OSError:
                    pass


def _grab(args):
    """跑一次 ffmpeg 取一帧；返回 True = 正常跑完（不管有没有取到），False = 超时 / 出错（下次再试）。"""
    try:
        subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y'] + args, capture_output=True, timeout=90, creationflags=NO_WINDOW)
        return True
    except Exception:
        return False


def cover_for(path):
    """封面：音频取自带的封面图（没有就显示默认图标）；视频取开头附近一帧（自动跳过黑屏）。缓存成 jpg。
    真没有封面才记下来不再尝试；超时之类的临时失败下次还会再试。"""
    st = os.stat(path)
    h = hashlib.sha1(f'{path}|{st.st_mtime}|{st.st_size}'.encode('utf-8')).hexdigest()
    video = os.path.splitext(path)[1].lower() in VIDEO_EXT
    # 视频封面保留原来的长宽比（网格里按长方形显示）；音频封面裁成正方形
    jpg = os.path.join(covers_dir(), h + ('.w.jpg' if video else '.jpg'))
    if os.path.isfile(jpg):
        return jpg
    none = os.path.join(covers_dir(), h + '.v2.none')
    if os.path.isfile(none):
        return None
    with cover_sem:
        if os.path.isfile(jpg):
            return jpg
        tmp = f'{jpg}.{uuid.uuid4().hex[:6]}.tmp.jpg'
        fit = 'scale=640:640:force_original_aspect_ratio=decrease' if video else 'scale=600:600:force_original_aspect_ratio=increase,crop=600:600'
        sq = ['-frames:v', '1', '-vf', fit, tmp]
        tries = []
        if video:  # 第 3 秒附近挑一帧不黑的；视频太短（不到 3 秒）就从头取
            tries += [['-ss', '3', '-i', path, '-an', '-map', '0:v:0', '-vf', 'thumbnail=30,' + fit, '-frames:v', '1', tmp],
                      ['-i', path, '-an', '-map', '0:v:0'] + sq]
        else:
            tries.append(['-i', path, '-an', '-map', '0:v:0'] + sq)  # 音频自带的封面图
        clean = True
        for a in tries:
            clean = _grab(a) and clean
            if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                break
        if video and os.path.isfile(tmp) and 0 < os.path.getsize(tmp) < 5000:  # 取到的几乎是纯色（片头黑屏）：往后几个位置再取，留内容最多的一张
            try:
                dur = float(subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout.strip() or 0)
            except Exception:
                dur = 0
            for at in ((.15, 1 / 3, .55) if dur > 6 else ()):
                alt = tmp + '.2.jpg'
                _grab(['-ss', f'{dur * at:.1f}', '-i', path, '-an', '-map', '0:v:0', '-frames:v', '1', '-vf', fit, alt])
                if os.path.isfile(alt) and os.path.getsize(alt) > os.path.getsize(tmp):
                    os.replace(alt, tmp)
                elif os.path.isfile(alt):
                    os.remove(alt)
                if os.path.getsize(tmp) >= 5000:
                    break
        if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, jpg)
            if video:  # 以前裁成正方形的旧封面用不上了
                try:
                    os.remove(os.path.join(covers_dir(), h + '.jpg'))
                except OSError:
                    pass
            return jpg
        try:
            os.remove(tmp)
        except OSError:
            pass
        if clean:
            open(none, 'w').close()
        return None


def image_info(path):
    """看图时的文件信息：尺寸、大小、修改时间，照片的话再加拍摄时间、相机、镜头、光圈快门 ISO。"""
    st = os.stat(path)
    out = {'size': st.st_size, 'mtime': st.st_mtime, 'ext': os.path.splitext(path)[1][1:].upper()}
    try:
        from PIL import Image, ExifTags
        with Image.open(path) as im:
            out['w'], out['h'] = im.size
            if getattr(im, 'n_frames', 1) > 1:
                out['frames'] = im.n_frames
            ex = im.getexif()
            if ex:
                tags = dict(ex)
                try:
                    tags.update(ex.get_ifd(0x8769))  # 拍摄参数在 Exif 子目录里
                except Exception:
                    pass
                T = {ExifTags.TAGS.get(k, k): v for k, v in tags.items()}
                num = lambda v: float(v) if v not in (None, '') else None
                if T.get('DateTimeOriginal') or T.get('DateTime'):
                    out['taken'] = str(T.get('DateTimeOriginal') or T.get('DateTime')).strip('\x00 ')
                cam = ' '.join(str(T.get(k, '')).strip('\x00 ') for k in ('Make', 'Model')).strip()
                if cam:
                    out['camera'] = cam
                if T.get('LensModel'):
                    out['lens'] = str(T['LensModel']).strip('\x00 ')
                shot = []
                if T.get('FNumber'):
                    shot.append(f'f/{num(T["FNumber"]):g}')
                if T.get('ExposureTime'):
                    e = num(T['ExposureTime'])
                    shot.append(f'1/{round(1 / e)}s' if e and e < 1 else f'{e:g}s')
                if T.get('ISOSpeedRatings'):
                    shot.append(f'ISO {T["ISOSpeedRatings"]}')
                if T.get('FocalLength'):
                    shot.append(f'{num(T["FocalLength"]):g}mm')
                if shot:
                    out['shot'] = '  '.join(shot)
    except Exception:
        pass
    return out


play_subs_state = {}  # key -> 'running' | 'error:…'
play_subs_prog = {}  # 字幕缓存路径 -> {'gen': 第几次, 't0', 'dur', 't1', 'eta'}：进度（估的）和取消（2026-11-18 用户：正在生成字幕要能取消、要有进度）


SUBS_LOCK = threading.Lock()  # 换字幕（导入 / 重新识别 / 从语音转文字拿）和写译文缓存互斥：译文写之前核对的那一版字幕不会在中间被换掉（第二轮审查 4）


def subs_drop_tr(out):
    """字幕变了：旧的译文作废（调用时要拿着 SUBS_LOCK）"""
    d = os.path.dirname(out)
    for old in os.listdir(d):
        if old.startswith(os.path.basename(out)[:-5] + '.tr-'):
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass


def play_subs_pct(out):
    """估计的进度 0~1：转格式算前 5%，识别按“音频长度 × 这台机器上次的速度”估；超过预计时间就慢慢逼近 98%，等真的做完"""
    g = play_subs_prog.get(out) or {}
    if not g.get('t1'):
        return 0.02
    x = (time.time() - g['t1']) / max(1.0, g.get('eta') or 1)
    return round(min(.98, .05 + (.85 * x if x < 1 else .9 + .08 * (1 - 1 / x))), 3)
tr_state = {}  # 翻译缓存路径 -> 'running:已完成/总数' | 'error:…'
_fp_cache = {}


def lib_fp(path):
    st = os.stat(path)
    k = (path, st.st_mtime, st.st_size)
    if k not in _fp_cache:
        _fp_cache[k] = stt.media_fp(path)
    return _fp_cache[k]


def stt_subs_for(path):
    """语音转文字里转过同一个文件（按文件指纹认）：返回那份带时间的字幕，播放页直接用，不用再识别一遍。"""
    try:
        fp = lib_fp(path)
    except OSError:
        return None
    for j in sorted(stt.stt_jobs.values(), key=lambda j: -(j.created or 0)):
        if getattr(j, 'space', 'n') == space() and getattr(j, 'fp', None) == fp and getattr(j, 'has_subs', False):
            f = os.path.join(j.dir, 'subs.json')
            if os.path.isfile(f):
                return f
    return None


def realign_text(new_text, chars):
    """把改过的文字套到原来识别出的逐字时间上：没改的字用原来的时间；改掉的字平分原来那几个字的时间；
    新加的字夹在前后两个字之间。不用再跑一遍模型，改完立刻生效。"""
    import difflib
    old = ''.join(c['c'] for c in chars)
    new = [ch for ch in new_text if WORD_CH.match(ch)]
    out = [None] * len(new)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, ''.join(new), autojunk=False).get_opcodes():
        if op == 'equal':
            for k in range(j2 - j1):
                c = chars[i1 + k]; out[j1 + k] = {'c': new[j1 + k], 's': c['s'], 'e': c['e']}
        elif op == 'replace':
            s0, e0, n = chars[i1]['s'], chars[i2 - 1]['e'], j2 - j1
            for k in range(n):
                out[j1 + k] = {'c': new[j1 + k], 's': s0 + (e0 - s0) * k / n, 'e': s0 + (e0 - s0) * (k + 1) / n}
    # 新加的字（insert）：前后都有时间的，夹在中间平分
    k = 0
    while k < len(out):
        if out[k] is None:
            m = k
            while m < len(out) and out[m] is None:
                m += 1
            a = out[k - 1]['e'] if k > 0 else (out[m]['s'] if m < len(out) else 0)
            b = out[m]['s'] if m < len(out) else a + .25 * (m - k)
            for q in range(k, m):
                out[q] = {'c': new[q], 's': a + (b - a) * (q - k) / (m - k), 'e': a + (b - a) * (q - k + 1) / (m - k)}
            k = m
        else:
            k += 1
    return out


def stt_resubs(j):
    """语音转文字里改了文字：字幕跟着改（原始识别结果另存一份，以后每次都从它重新对齐）。"""
    f, orig = os.path.join(j.dir, 'subs.json'), os.path.join(j.dir, 'subs_asr.json')
    if not os.path.isfile(f):
        return
    if not os.path.isfile(orig):
        shutil.copyfile(f, orig)
    d = read_json(orig, {})
    if not d.get('chars'):
        return  # Whisper 的字幕没有逐字时间，没法对齐
    chars = realign_text(j.text, d['chars'])
    write_json(f, {**d, 'sents': make_sentences(j.text, chars), 'chars': chars, 'edited': True})


VRAM_NAMES = {'breeze': 'Breeze TTS 2', 'indextts': 'IndexTTS-2.5', 'qwen3-base': 'Qwen3-TTS 克隆', 'qwen3-design': 'Qwen3-TTS 音色设计',
              'qwen3-custom': 'Qwen3-TTS 预设音色', 'seedvc': 'Seed-VC 换声', 'asr': '语音识别 + 对齐'}


def vram_info():
    """显存面板：显卡总用量（nvidia-smi）+ 本程序加载的每个模型（按模型文件大小估算，和实际占用相差不大）。"""
    used = total = None
    try:
        p = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                           capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
        used, total = [int(x) for x in p.stdout.strip().splitlines()[0].split(',')]
    except Exception:
        pass
    items = []
    try:
        cfg = {m['id']: m for m in server_cfg().get('models', [])}
        for m in json.loads(engine('/v1/models')[0])['data']:
            if not m.get('loaded'):
                continue
            mb = os.path.getsize(m['path']) / 2 ** 20 if os.path.isfile(m.get('path', '')) else 0
            for v in ((cfg.get(m['id'], {}).get('session_options') or {}).values()):  # 语音识别还会带上对齐模型
                if isinstance(v, str) and v.endswith('.gguf') and os.path.isfile(v):
                    mb += os.path.getsize(v) / 2 ** 20
            items.append({'id': m['id'], 'name': VRAM_NAMES.get(m['id'], m['id']), 'mb': round(mb * 1.08)})
    except Exception:
        pass
    if translate._Local.proc and translate._Local.proc.poll() is None:
        items.append({'id': 'translate', 'name': '本地翻译', 'mb': round(os.path.getsize(translate.LOCAL_MODEL) / 2 ** 20 * 1.1)})
    for it in (imagegen.vram_item(), promptgen.vram_item(), videogen.vram_item()):  # 2026-11-14 审查：以前漏了视频引擎（“释放全部”也就放不掉视频模型）
        if it:
            items.append(it)
    return {'used': used, 'total': total, 'items': items}


# ---- 网页文件：压缩 + 缓存（2026-11-08 性能检查）----
# 以前所有网页文件都是 no-store、不压缩：每次打开 / 刷新都要重新下 1.9 MB（手机走 Tailscale 时约 1 秒，网差时好几秒）。
# 现在：首页里引用的 /static 文件地址带上版本号（文件的修改时间）→ 浏览器一直用缓存，文件改了地址就变、自动拿新的；
# 不带版本号的照常每次问一下（ETag，没变就回 304，不传内容）；文字类的（js / css / html / svg / json）压缩后再发。
STATIC_TEXT = ('.js', '.mjs', '.css', '.html', '.svg', '.json', '.webmanifest', '.txt')
_gz_cache, _gz_lock = {}, threading.Lock()


def gz_bytes(key, raw):
    """压缩后的内容（按 key 缓存；key 里带着修改时间，文件改了自然换一份）"""
    import gzip
    with _gz_lock:
        hit = _gz_cache.get(key)
    if hit is not None:
        return hit
    z = gzip.compress(raw, 6)
    with _gz_lock:
        if len(_gz_cache) > 400:
            _gz_cache.clear()
        _gz_cache[key] = z
    return z


def static_ver(path):
    try:
        st = os.stat(path)
        return format(st.st_mtime_ns // 1000, 'x') + format(st.st_size, 'x')
    except OSError:
        return ''


_INDEX_RE = re.compile(r'((?:src|href)=")/static/([^"?#]+)(")')


def index_html(name='index.html'):
    """首页：引用的 /static 文件加上 ?v=版本号（每次请求都现算，只是 stat 二十几个文件，约 0.1 毫秒）"""
    with open(os.path.join(WEB, name), 'rb') as f:
        html = f.read().decode('utf-8')
    return _INDEX_RE.sub(lambda m: f'{m.group(1)}/static/{m.group(2)}?v={static_ver(os.path.join(WEB, *m.group(2).split("/")))}{m.group(3)}', html).encode('utf-8')


_vram_c = {'t': 0.0, 'v': None}
_vram_lock = threading.Lock()


def vram_info_cached(ttl=3.0):
    """侧栏的显存条每 5 秒问一次（电脑、手机各一份）：3 秒内的结果直接复用，不再每次都起一个 nvidia-smi 进程。释放模型后（POST）总是现查"""
    with _vram_lock:
        if _vram_c['v'] is not None and time.time() - _vram_c['t'] < ttl:
            return _vram_c['v']
    v = vram_info()
    with _vram_lock:
        _vram_c['t'], _vram_c['v'] = time.time(), v
    return v


def gpu_free_for_images():
    """生图前：配音引擎里载入的模型、本地翻译模型、提示词模型都先从显存里放掉（下次用到时自动重新载入）"""
    videogen.Engine.free_idle()  # 视频做完还留在显存里的模型（等下一段用的）：先让出来
    translate._Local.stop()
    promptgen.Engine.release()
    try:
        ids = [m['id'] for m in json.loads(engine('/v1/models', timeout=5)[0])['data'] if m.get('loaded')]
        if ids:
            act('生图前先释放配音模型的显存：' + '、'.join(VRAM_NAMES.get(i, i) for i in ids), 'img')
            engine('/v1/tasks/unload_models', {'model_ids': ids}, timeout=60)
            time.sleep(.5)
    except Exception as e:
        act('释放配音模型显存失败（继续生图）：' + str(e), 'img', 'warn')


def gpu_free_for_prompt():
    """提示词模型启动前（它要 18GB 左右）：配音引擎里的模型、本地翻译模型先放掉"""
    translate._Local.stop()
    try:
        ids = [m['id'] for m in json.loads(engine('/v1/models', timeout=5)[0])['data'] if m.get('loaded')]
        if ids:
            act('提示词模型启动前先释放配音模型的显存：' + '、'.join(VRAM_NAMES.get(i, i) for i in ids), 'prompt')
            engine('/v1/tasks/unload_models', {'model_ids': ids}, timeout=60)
            time.sleep(.5)
    except Exception as e:
        act('释放配音模型显存失败：' + str(e), 'prompt', 'warn')


def transcribe_stt(wav16, tag='stt', language=None):
    """语音转文字页（Qwen3-ASR）：同时拿到逐字时间，存一份字幕给播放页用；对齐失败时退回普通识别。language：页面上选的语言（auto = 自动）"""
    language = language if language and language != 'auto' else None
    try:
        text, chars, lang = transcribe_ts(wav16, tag, language)
        return text.strip(), {'sents': make_sentences(text, chars), 'chars': chars, 'language': lang}
    except Exception as e:
        act(f'带时间戳识别失败，改用普通识别：{e}', tag, 'warn')
        return transcribe(wav16, tag, language), None


def local_chat(system, user):
    """用本地提示词模型写一次回答（AI 校对选“本地模型”时用）：低温度，不思考。"""
    ef = os.path.join(PROMPT_DIR, 'prompt-engine.json')
    params = promptgen.clamp_params({'temperature': 0.2, 'top_p': 0.9, 'top_k': 20, 'presence_penalty': 0.0, 'max_tokens': 8192, 'thinking': False})
    out = []
    for kind, val in promptgen.chat_stream([{'role': 'user', 'content': user}], system, params, promptgen.clamp_engine(read_json(ef, {}) or {}), lambda: False):
        if kind == 'text':
            out.append(val)
    return ''.join(out)


stt.LOCAL_CHAT = local_chat


def local_chat_img(system, user, images):
    """同 local_chat，带图（看图写文字用）"""
    ef = os.path.join(PROMPT_DIR, 'prompt-engine.json')
    params = promptgen.clamp_params({'temperature': 0.2, 'top_p': 0.9, 'top_k': 20, 'presence_penalty': 0.0, 'max_tokens': 400, 'thinking': False})
    out = []
    for kind, val in promptgen.chat_stream([{'role': 'user', 'content': user, 'images': images}], system, params, promptgen.clamp_engine(read_json(ef, {}) or {}), lambda: False, own_gpu=True):  # 在视频任务里调用：任务已拿着显卡
        if kind == 'text':
            out.append(val)
    return ''.join(out)


videoedit.DESCRIBE, videoedit.DESCRIBE_RELEASE = local_chat_img, lambda: promptgen.Engine.release(wait=True)
videoedit.DESCRIBE_OK = lambda: promptgen.available() and promptgen.vision()
# 提示词翻成英文（生视频的“提示词语言 = 英文”）：本地提示词模型翻，翻完让出显存；缓存放在 AI 助手的设置旁边（见 ptrans.py）
import ptrans
ptrans.CHAT = local_chat
ptrans.RELEASE = lambda: promptgen.Engine.release(wait=True)
ptrans.CACHE = lambda: os.path.join(DATA if space() == 'v' else PROMPT_DIR, 'prompt-translate-cache.json')  # 两个空间各一份（私密的在 .data 里）


def q21_chat(system, user, images):
    """Qwen 2.1「AI 助手写提示词」：本地 AI 助手（Qwen3.8）看图按原话写一次（低温度、不思考）。显卡锁由生图任务临时还回来"""
    ef = os.path.join(PROMPT_DIR, 'prompt-engine.json')
    params = promptgen.clamp_params({'temperature': 0.3, 'top_p': 0.8, 'top_k': 20, 'presence_penalty': 0.0, 'max_tokens': 2000, 'thinking': False})
    out = []
    for kind, val in promptgen.chat_stream([{'role': 'user', 'content': user, 'images': images or []}], system, params,
                                           promptgen.clamp_engine(read_json(ef, {}) or {}), lambda: False):
        if kind == 'text':
            out.append(val)
    return ''.join(out)


imagegen.q21.CHAT = q21_chat
import fisher  # noqa: E402  Fisher Pose 3D 人偶编辑器的接口
fisher.DATA_ROOT = lambda sp: os.path.dirname(imagegen.images_dir(sp))  # 普通空间 outputs/fisher，私密空间 .data/fisher
imagegen.q21.RELEASE = lambda: promptgen.Engine.release(wait=True)


# ---------------------------------------------------------------- 配音引擎的会话参数（性能模式 / Qwen3 LoRA）：写进 server.json，引擎重启后生效
TTS_ENGINE_OPTS = {  # 网页上的名字 -> (server.json 里哪些模型, 会话参数名, 允许的值 / 类型, 默认)
    'breeze_perf': (('breeze',), 'breeze_tts.perf_mode', ('off', 'cuda_perf'), 'off'),
    'breeze_fusion': (('breeze',), 'breeze_tts.round_bf16_fusion', bool, False),
    'qwen3_perf': (('qwen3-base', 'qwen3-design', 'qwen3-custom'), 'qwen3_tts.perf_mode', ('off', 'flash_attention', 'cuda_perf'), 'off'),
    'qwen3_lora': (('qwen3-base', 'qwen3-design', 'qwen3-custom'), 'qwen3_tts.lora', str, ''),
    'qwen3_lora_scale': (('qwen3-base', 'qwen3-design', 'qwen3-custom'), 'qwen3_tts.lora_scale', float, 1.0),
}


def tts_engine_opts():
    cfg = {m['id']: m for m in server_cfg().get('models', [])}
    out = {}
    for k, (ids, name, kind, dflt) in TTS_ENGINE_OPTS.items():
        v = ((cfg.get(ids[0]) or {}).get('session_options') or {}).get(name, dflt)
        out[k] = str(v).lower() == 'true' if kind is bool else float(v) if kind is float else str(v)
    return out


SERVER_CFG = os.path.join(ROOT, 'server.json')  # 配音引擎的默认配置（进 git；devtest/run.py 会改到测试目录里的一份）
# 2026-11-17 审查 C05：网页上改的会话参数（性能模式、Qwen3 LoRA……）以前直接写回 server.json（受 git 跟踪的默认文件）。
# 现在写进旁边的 server.local.json（本机覆盖，不进 git）：{"models": {"<模型 id>": {"session_options": {"参数": 值, "要去掉的参数": null}}}}；
# 引擎启动时把两份合成 server.effective.json 再交给它。没有本机覆盖时引擎照旧直接读 server.json。
# 以前改过的值已经在 server.json 里，照样生效（等于迁移成了这台电脑的默认）；以后再改只动本机覆盖。


def _cfg_paths():
    b = SERVER_CFG[:-5] if SERVER_CFG.lower().endswith('.json') else SERVER_CFG
    return b + '.local.json', b + '.effective.json'


def _cfg_local():
    d = read_json(_cfg_paths()[0], {}) or {}
    m = d.get('models') if isinstance(d, dict) else None
    return {str(k): v for k, v in m.items() if isinstance(v, dict)} if isinstance(m, dict) else {}


def server_cfg():
    """配音引擎实际用的配置：server.json（默认）+ server.local.json（本机覆盖的会话参数）"""
    cfg = read_json(SERVER_CFG, {}) or {}
    over = _cfg_local()
    for m in cfg.get('models', []):
        o = (over.get(m.get('id')) or {}).get('session_options')
        if not isinstance(o, dict):
            continue
        so = dict(m.get('session_options') or {})
        for k, v in o.items():
            if v is None:
                so.pop(k, None)
            else:
                so[k] = v
        if so:
            m['session_options'] = so
        else:
            m.pop('session_options', None)
    return cfg


def server_cfg_file():
    """给引擎的 --config：有本机覆盖就合成一份 server.effective.json，没有就是 server.json"""
    loc, eff = _cfg_paths()
    if not _cfg_local():
        return SERVER_CFG
    write_json(eff, server_cfg(), indent=2)
    return eff


def set_tts_engine_opts(b):
    """改配音引擎的会话参数：校验后写进本机覆盖 server.local.json（只记和 server.json 默认不同的），不动受跟踪的 server.json。返回改了没有。"""
    base = {m['id']: m for m in (read_json(SERVER_CFG, {}) or {}).get('models', [])}
    cfg = server_cfg()
    byid, changed = {m['id']: m for m in cfg.get('models', [])}, False
    for k, (ids, name, kind, dflt) in TTS_ENGINE_OPTS.items():
        if k not in b:
            continue
        v = b[k]
        if kind is bool:
            v = bool(v)
        elif kind is float:
            try:
                v = round(max(0.0, min(2.0, float(v))), 2)
            except (TypeError, ValueError):
                raise ValueError('LoRA 强度须为 0~2 之间的数字')
        elif kind is str:
            v = str(v or '').strip().strip('"')
            if v and (v.startswith(('\\\\', '//')) or not os.path.exists(v)):
                raise ValueError('找不到该 LoRA 路径（须为本机上的文件夹或文件）')
            v = v.replace('\\', '/')
        elif v not in kind:
            raise ValueError('参数有误：' + k)
        for mid in ids:
            m = byid.get(mid)
            if not m:
                continue
            so = dict(m.get('session_options') or {})
            if v == dflt or v == '':
                so.pop(name, None)
            else:
                so[name] = ('true' if v else 'false') if kind is bool else str(v) if kind is float else v
            if so != (m.get('session_options') or {}):
                changed = True
                if so:
                    m['session_options'] = so
                else:
                    m.pop('session_options', None)
    if changed:
        over = _cfg_local()
        for mid, m in byid.items():  # 合成后的会话参数和默认比，只把不一样的记进本机覆盖
            want, dflt = m.get('session_options') or {}, (base.get(mid) or {}).get('session_options') or {}
            diff = {k: v for k, v in want.items() if dflt.get(k) != v}
            diff.update({k: None for k in dflt if k not in want})
            ent = {k: v for k, v in (over.get(mid) or {}).items() if k != 'session_options'}
            if diff:
                ent['session_options'] = diff
            if ent:
                over[mid] = ent
            else:
                over.pop(mid, None)
        loc = _cfg_paths()[0]
        if over:
            write_json(loc, {'models': over}, indent=2)
        elif os.path.isfile(loc):
            os.remove(loc)
    return changed


def play_subs_target(key):
    """播放页字幕：key 是 lib:<相对路径> 或 job:<任务id>。返回 (音频路径, 字幕缓存路径)。"""
    if key.startswith('lib:'):
        path = lib_path(key[4:])
        st = os.stat(path)
        return path, os.path.join(psubs_dir(), hashlib.sha1(f'{path}|{st.st_mtime}|{st.st_size}'.encode('utf-8')).hexdigest() + '.json')
    if key.startswith('job:') and job_visible(key[4:]):
        j = jobs[key[4:]]
        out = os.path.join(j.dir, 'subs_out.json')
        return os.path.join(j.dir, 'output.wav'), out if isinstance(j, VcJob) else os.path.join(j.dir, 'subs_play.json')
    raise RuntimeError('找不到该音频')


def _sys_attr(path, mask):
    """Windows 文件属性里有没有 mask（2 = 隐藏，4 = 系统）。path 可以带 \\\\?\\ 前缀"""
    try:
        return bool(getattr(os.stat(path), 'st_file_attributes', 0) & mask)
    except OSError:
        return False


_lib_locks = {}


def scan_library(fresh=False):
    """播放页的音源：.data/library 下所有音频 / 视频（视频只放声音），按第一层文件夹分组。10 秒内复用扫描结果。"""
    return lib_snapshot(fresh)['data']


def lib_snapshot(fresh=False):
    """一次扫描同时给出音源列表、图片列表和它们的指纹（2026-11-17 审查 P05：以前网页同时问音源和图片，缓存过期时各扫一遍全库；
    每次请求还要把整个列表序列化一遍算指纹）。同一个空间正在扫时，后来的请求等它扫完、直接用这份"""
    LIBRARY = lib_root()  # 本次扫描的文件夹（普通界面 / 私密空间各一个）
    asked = time.time()
    c = _lib_cache.get(LIBRARY)
    if c and not fresh and asked - c['t'] < 10:  # 10 秒内复用（网页每 20 秒来看一次有没有新文件）
        return c
    with lock:
        lk = _lib_locks.setdefault(LIBRARY, threading.Lock())
    with lk:
        c = _lib_cache.get(LIBRARY)
        if c and (c['t'] >= asked or (not fresh and time.time() - c['t'] < 10)):  # 等的时候别的请求刚扫完：用它的
            return c
        return _scan_now(LIBRARY)


def _scan_now(LIBRARY):
    items, images, seen = [], [], set()
    # followlinks：文件夹里如果是“目录联接 / 符号链接”指向别处的文件夹，也要进去扫；seen 防止链接绕成死循环
    for dirpath, dirnames, files in os.walk(('\\\\?\\' + os.path.abspath(LIBRARY)) if os.name == 'nt' else LIBRARY, followlinks=True):
        try:
            real = os.path.realpath(dirpath)
        except OSError:
            real = dirpath
        if real in seen:
            dirnames[:] = []
            continue
        seen.add(real)
        # 不进系统文件夹（回收站、.开头的隐藏文件夹等）
        dirnames[:] = [d for d in dirnames if not d.startswith(('.', '$')) and d != 'System Volume Information' and not _sys_attr(os.path.join(dirpath, d), 4)]
        raw = dirpath
        dirpath = dirpath[4:] if dirpath.startswith('\\\\?\\') else dirpath
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in AUDIO_EXT and ext not in IMAGE_EXT:
                continue
            # 隐藏 / 系统文件不算：Windows Media Player 等软件会在音乐文件夹里悄悄放隐藏的 Folder.jpg、AlbumArtSmall.jpg，
            # 资源管理器里看不到，这里也不该显示；苹果电脑拷过来的 ._xxx 也一样
            if f.startswith('.') or _sys_attr(os.path.join(raw, f), 2 | 4):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, LIBRARY).replace('\\', '/')
            parts = rel.split('/')
            try:
                st = os.stat(longp(full))
            except OSError:
                continue
            if ext in IMAGE_EXT:
                images.append({'path': rel, 'name': os.path.splitext(f)[0], 'ext': ext[1:], 'dir': '/'.join(parts[:-1]) or '未分类', 'size': st.st_size, 'mtime': st.st_mtime})
                continue
            items.append({'path': rel, 'name': os.path.splitext(f)[0], 'ext': ext[1:], 'folder': parts[0] if len(parts) > 1 else '未分类',
                          'sub': '/'.join(parts[1:-1]), 'dir': '/'.join(parts[:-1]) or '未分类',  # dir：完整的文件夹路径，网页按它建文件夹树
                          'size': st.st_size, 'mtime': st.st_mtime, 'video': ext in VIDEO_EXT, 'conv': ext not in NATIVE_EXT})
    items.sort(key=lambda x: (x['dir'], x['name']))
    images.sort(key=lambda x: (x['dir'], x['name']))
    # 时长 / 作者：缓存里有的直接填上，缺的后台读，读完把这份扫描作废（网页下次轮询时指纹变了就重画）
    libmeta.fill(items, LIBRARY, os.path.join(PCOVERS if LIBRARY == PUBLIB else COVERS, 'libmeta.json'), FFPROBE,
                 on_done=lambda: _lib_cache.pop(LIBRARY, None))
    sig = lambda v: hashlib.sha1(json.dumps(v, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:20]
    c = _lib_cache[LIBRARY] = {'t': time.time(), 'data': items, 'images': images, 'sig': sig(items), 'isig': sig(images)}
    return c


def lib_target(rel, is_dir):
    """播放页右键菜单要操作的文件 / 文件夹（必须在当前音源库里）。'未分类' = 音源库本身（直接放在里面的文件）。"""
    root = lib_root()
    if is_dir and rel in ('', '未分类'):
        return root
    path = os.path.normpath(os.path.join(root, *rel.split('/')))
    if not path.startswith(root + os.sep):
        raise RuntimeError('不在音源库中')
    if not (os.path.isdir(longp(path)) if is_dir else os.path.isfile(longp(path))):
        raise RuntimeError('文件夹不存在' if is_dir else '文件不存在')
    return path


def reveal(path, is_dir):
    """在资源管理器里打开：文件夹 → 打开这个文件夹；文件 → 打开所在文件夹并选中它。"""
    if is_dir:
        os.startfile(path)
        return
    import ctypes
    sh = ctypes.windll.shell32
    sh.ILCreateFromPathW.restype = ctypes.c_void_p
    sh.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
    sh.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    ctypes.windll.ole32.CoInitialize(None)
    pidl = sh.ILCreateFromPathW(path)
    if not pidl:
        os.startfile(os.path.dirname(path))
        return
    try:
        sh.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
    finally:
        sh.ILFree(ctypes.c_void_p(pidl))


def to_recycle_bin(path):
    """删除 = 移到回收站（还能从回收站还原），不是彻底删除。
    Windows 的回收站放不下路径超过 260 个字符的文件：这种情况系统会直接彻底删掉、不提示。所以先检查路径长度，
    太长就不删（让你在资源管理器里自己处理）；另外加上“要彻底删除时先问一下”，回收站满了、U 盘这类没有回收站的地方也不会悄悄删掉。"""
    import ctypes
    from ctypes import wintypes
    longest = len(os.path.abspath(path))
    if os.path.isdir(longp(path)):
        for dp, dns, fns in os.walk(longp(path)):
            for n in dns + fns:
                longest = max(longest, len(os.path.join(dp, n)) - (4 if dp.startswith('\\\\?\\') else 0))
    if longest >= 259:
        raise RuntimeError('路径过长，无法放入 Windows 回收站（为避免被彻底删除，未执行删除）。可右键选择“在资源管理器中显示”后手动处理')

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', ctypes.c_void_p), ('pTo', ctypes.c_void_p),
                    ('fFlags', ctypes.c_uint16), ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', ctypes.c_void_p)]
    buf = ctypes.create_unicode_buffer(os.path.abspath(path) + chr(0))  # 路径结尾要两个 0（buffer 自己会再补一个）
    op = SHFILEOPSTRUCTW(None, 3, ctypes.cast(buf, ctypes.c_void_p), None, 0x40 | 0x10 | 0x4 | 0x400 | 0x4000, False, None, None)  # FO_DELETE；进回收站、不弹确认和进度；要彻底删除时先问
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r or op.fAnyOperationsAborted or os.path.exists(longp(path)):
        raise RuntimeError('删除失败（文件可能正在被使用，或路径过长）')


# ---- 播放副本（拖动进度条时画面能跟着）：每 4 帧一个关键帧；做好前先给原文件，后台去做
_scrub_q, _scrub_lock, _scrub_busy = [], threading.Lock(), set()


def scrub_path(path, beside):
    if beside:  # 生成的视频：放在它那个空间的 _辅助文件/播放副本 里（2026-11-06；老的副本还在旁边就用老的）
        return videogen.scrub_file(path)
    st = os.stat(path)
    return os.path.join(covers_dir(), hashlib.sha1(f'scrub|{path}|{st.st_mtime}|{st.st_size}'.encode('utf-8')).hexdigest() + '.scrub.mp4')


def scrub_for(path, beside=False):
    """播放副本做好了就返回副本，没做好返回原文件并放进后台队列"""
    if beside and videogen.seekable(path):  # 生成的视频本身关键帧就够密（2026-11-06 起的成品）：直接放原文件，不另存副本
        return path
    try:
        out = scrub_path(path, beside)
        if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(path):
            return out
        if os.path.getsize(path) > 800 * 1024 * 1024 or path.endswith('.scrub.mp4'):
            return path
    except OSError:
        return path
    scrub_queue([(path, beside)], front=True)
    return path


def scrub_prefetch(paths):
    """素材库里的视频提前做播放副本（2026-11-11 用户：剪辑里播放卡——手机拍的视频多是 4K / HEVC，副本没做好时放的是原文件，后台还同时在转码）。
    排在用户正在看的后面；有生成 / 配音任务时先不做；低一级的优先级"""
    todo = []
    for p in paths:
        try:
            out = scrub_path(p, False)
            if not (os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(p)) and os.path.getsize(p) <= 800 * 1024 * 1024:
                todo.append((p, False, True))
        except OSError:
            pass
    if todo:
        scrub_queue(todo)


_scrub_sp = {}  # 排队的视频是哪个空间的（播放副本放进那个空间的缓存）


def scrub_queue(items, front=False):
    start = False
    with _scrub_lock:
        for it in items:
            if front and it[0] in _scrub_busy:  # 已经排着（提前做的）：挪到最前面
                for k, x in enumerate(_scrub_q):
                    if x[0] == it[0]:
                        _scrub_q.insert(0, _scrub_q.pop(k)); break
            elif it[0] not in _scrub_busy:
                _scrub_busy.add(it[0]); _scrub_q.insert(0, it) if front else _scrub_q.append(it)
            _scrub_sp.setdefault(it[0], space())  # 2026-11-14 审查：后台线程不知道是哪个空间，私密的播放副本曾写进普通空间的缓存
        if _scrub_q and not getattr(scrub_queue, 'run', False):
            scrub_queue.run = start = True
    if start:
        threading.Thread(target=_scrub_worker, daemon=True).start()


def _scrub_worker():
    while True:
        with _scrub_lock:
            if not _scrub_q:
                scrub_queue.run = False
                return
            path, beside, *pre = _scrub_q.pop(0)
        try:
            while pre and busy_work():  # 提前做的：生成 / 配音时先等着（用户点开的视频会插到前面，不用等）
                time.sleep(5)
                with _scrub_lock:
                    if _scrub_q and not _scrub_q[0][2:]:  # 有用户正在看的排进来了：先做那个，这个放回去
                        _scrub_q.append((path, beside, True)); path = None; break
            if path is None:
                continue
            CTX.space = _scrub_sp.get(path, 'n')
            out = scrub_path(path, beside)
            if not (os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(path)):
                tmp = out + f'.{uuid.uuid4().hex[:6]}.tmp.mp4'
                r = subprocess.run([FFMPEG, '-v', 'error', '-y', '-threads', BG_THREADS, '-i', path, '-map', '0:v:0', '-map', '0:a:0?',  # 解码也只用一半的线程
                                    '-vf', "scale='if(gt(iw,ih),trunc(min(1920,iw)/2)*2,-2)':'if(gt(iw,ih),-2,trunc(min(1920,ih)/2)*2)'",
                                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-tune', 'fastdecode', '-x264-params', 'keyint=4:min-keyint=1:scenecut=0', '-threads', BG_THREADS,
                                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', tmp],
                                   creationflags=BG_PRI, timeout=900, capture_output=True)
                if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 1000:
                    os.replace(tmp, out)
                else:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        except Exception:
            pass
        finally:
            with _scrub_lock:
                _scrub_busy.discard(path)
                if path not in _scrub_busy:
                    _scrub_sp.pop(path, None)


def thumb_for(path):
    """图片的小缩略图（最长边 480，jpg），缓存在封面缓存旁边；转不出来就返回原图。"""
    st = os.stat(path)
    h = hashlib.sha1(f'thumb|{path}|{st.st_mtime}|{st.st_size}'.encode('utf-8')).hexdigest()
    jpg = os.path.join(covers_dir(), h + '.t.jpg')
    if os.path.isfile(jpg):
        return jpg
    if st.st_size < 200 * 1024 and not path.lower().endswith(('.bmp', '.avif')):
        return path  # 本来就很小：直接用原图
    with cover_sem:
        if not os.path.isfile(jpg):
            tmp = f'{jpg}.{uuid.uuid4().hex[:6]}.tmp.jpg'
            try:
                subprocess.run([FFMPEG, '-v', 'error', '-y', '-i', path, '-frames:v', '1', '-vf', "scale='if(gt(iw,ih),min(480,iw),-2)':'if(gt(iw,ih),-2,min(480,ih))'",
                                '-q:v', '5', tmp], creationflags=NO_WINDOW, timeout=30, capture_output=True)
                if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    os.replace(tmp, jpg)
            except Exception:
                pass
            finally:
                if os.path.isfile(tmp):
                    os.remove(tmp)
    return jpg if os.path.isfile(jpg) else path


# 浏览器放不了的格式：第一次播放时转一份（视频是 H.264 就只换个封装，几秒钟；不是就用显卡重新编码），以后直接用缓存
_conv = {}  # (空间, 相对路径) -> {'state': running/done/error, 'p': 0~100, 'file': 缓存文件名, 'err': ''}
_conv_lock = threading.Lock()


def conv_dir():
    d = os.path.join(os.path.dirname(covers_dir()), 'converted')
    os.makedirs(d, exist_ok=True)
    return d


def conv_name(path, video):
    st = os.stat(path)
    return hashlib.sha1(f'conv|{path}|{st.st_mtime}|{st.st_size}'.encode('utf-8')).hexdigest()[:24] + ('.mp4' if video else '.m4a')


def conv_status(rel):
    path = lib_path(rel)
    video = os.path.splitext(path)[1].lower() in VIDEO_EXT
    name = conv_name(path, video)
    key = (space(), rel)
    if os.path.isfile(os.path.join(conv_dir(), name)):
        return {'state': 'done', 'p': 100, 'url': '/media/conv/' + name}
    with _conv_lock:
        j = _conv.get(key)
        if j and j['state'] == 'error':
            return {'state': 'error', 'err': j.get('err', '')}
        return {'state': 'running', 'p': j['p']} if j else {'state': 'none'}


def conv_start(rel):
    path = lib_path(rel)
    video = os.path.splitext(path)[1].lower() in VIDEO_EXT
    out = os.path.join(conv_dir(), conv_name(path, video))
    key = (space(), rel)
    with _conv_lock:
        if os.path.isfile(out) or (_conv.get(key) or {}).get('state') == 'running':
            return
        _conv[key] = j = {'state': 'running', 'p': 0}

    def run():
        tmp = out + '.part' + os.path.splitext(out)[1]
        try:
            probe = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'stream=codec_type,codec_name:format=duration', '-of', 'json', path],
                                   capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW, timeout=60)
            info = json.loads(probe.stdout or '{}')
            dur = float((info.get('format') or {}).get('duration') or 0)
            vs = [x['codec_name'] for x in info.get('streams', []) if x.get('codec_type') == 'video']
            ac = [x['codec_name'] for x in info.get('streams', []) if x.get('codec_type') == 'audio']
            a_args = ['-c:a', 'copy'] if ac and ac[0] == 'aac' else ['-c:a', 'aac', '-b:a', '192k']
            tries = []
            if video and vs:
                if vs[0] == 'h264' and os.path.splitext(path)[1].lower() not in NATIVE_EXT:  # 只是容器不对：换个容器就行
                    tries.append(['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'copy'] + a_args)
                tries.append(['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'h264_nvenc', '-preset', 'p5', '-cq', '22', '-pix_fmt', 'yuv420p'] + a_args)
                tries.append(['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p'] + a_args)
            else:
                tries.append(['-vn', '-map', '0:a:0'] + a_args)
            err = ''
            for args in tries:
                ef = tempfile.TemporaryFile(mode='w+', encoding='utf-8', errors='replace')
                p = subprocess.Popen([FFMPEG, '-v', 'error', '-y', '-i', path] + args + ['-movflags', '+faststart', '-progress', 'pipe:1', '-nostats', tmp],
                                     stdout=subprocess.PIPE, stderr=ef, text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
                for line in p.stdout:
                    if line.startswith('out_time_us=') and dur > 0:
                        try:
                            j['p'] = max(0, min(99, int(int(line.split('=')[1]) / 1e6 / dur * 100)))
                        except ValueError:
                            pass
                p.wait()
                ef.seek(0); err = (ef.read() or '')[-400:]; ef.close()
                if p.wait() == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    os.replace(tmp, out)
                    break
            if os.path.isfile(out):
                j['state'] = 'done'; j['p'] = 100
            else:
                j['state'] = 'error'; j['err'] = err.strip().splitlines()[-1] if err.strip() else '转换失败'
        except Exception as e:  # noqa: BLE001
            j['state'] = 'error'; j['err'] = str(e)
        finally:
            if os.path.isfile(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    threading.Thread(target=run, daemon=True).start()


# ================================================================ HTTP
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.bin': 'application/octet-stream',
        '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.flac': 'audio/flac', '.ogg': 'audio/ogg', '.opus': 'audio/ogg',
        '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/webm', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.json': 'application/json', '.png': 'image/png',
        '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp', '.avif': 'image/avif'}


def safe_ext(fname):
    e = os.path.splitext(str(fname))[1].lower()
    return e if re.fullmatch(r'\.[a-z0-9]{1,8}', e) else '.bin'


_PATH_RE = re.compile(r"""[A-Za-z]:[\\/][^\s'"<>|]*""")  # 错误里的 D:\... / C:/... 路径


def public_error(e):
    """给网页看的错误：不带电脑上的路径；看不懂的 Python 报错换成一句话（详细的在日志里）。"""
    msg = str(e) or e.__class__.__name__
    if isinstance(e, (TypeError, KeyError, IndexError, AttributeError)) or re.search(r'invalid literal|not iterable|object has no|unhashable|expected str|out of range|NoneType', msg):
        return '请求内容有误（参数类型或编号不正确）'
    if re.search(r'Invalid data found|Error opening input|moov atom|could not find codec|Output file .* does not contain', msg):
        return '文件已损坏，或不是音频 / 视频'
    return _PATH_RE.sub('…', msg)[:500]


class BadRequest(Exception):
    """请求本身有问题（参数不对、格式不对）：回 400 和这段说明，不当成程序出错。"""


class _MediaMiss(Exception):
    """media() 在私密空间里没找到（还没回应）"""


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 300  # 半开的连接（手机突然断网）不会永远占着一个线程；字幕流 / 提示词流自己另设
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200, headers=None):
        if code == 404 and getattr(self, '_probe404', False):  # 媒体先在私密空间找、没找到：还没往外写，换普通空间再找（见 media）
            raise _MediaMiss()
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        gz = len(body) > 8192 and 'gzip' in (self.headers.get('Accept-Encoding') or '')  # 大的列表（音源库、视频库…）压缩后再发：手机上省流量、快很多
        if gz:
            import gzip
            body = gzip.compress(body, 5)
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if gz:
            self.send_header('Content-Encoding', 'gzip'); self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Studio-Boot', BOOT_ID)
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path, raw=None, immutable=False):
        """网页文件：带版本号的长期缓存；其余每次问一下（ETag）。raw：已经生成好的内容（首页）"""
        if raw is None:
            if not os.path.isfile(path):
                return self.send_json({'error': '文件不存在'}, 404)
            st = os.stat(path)
            tag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        else:
            tag = '"' + hashlib.sha1(raw).hexdigest()[:20] + '"'
        cc = 'public, max-age=31536000, immutable' if immutable else 'no-cache'
        if self.headers.get('If-None-Match') == tag:
            self.send_response(304); self.send_header('ETag', tag); self.send_header('Cache-Control', cc); self.end_headers()
            return
        if raw is None:
            with open(path, 'rb') as f:
                raw = f.read()
        ext = os.path.splitext(path)[1].lower()
        body, enc = raw, None
        if ext in STATIC_TEXT and len(raw) > 1024 and 'gzip' in (self.headers.get('Accept-Encoding') or ''):
            body, enc = gz_bytes((path, tag), raw), 'gzip'
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cc); self.send_header('ETag', tag)
        if enc:
            self.send_header('Content-Encoding', enc); self.send_header('Vary', 'Accept-Encoding')
        self.end_headers()
        self.wfile.write(body)

    def send_scrub(self, path, q, beside, cache):
        """播放副本的固定版本地址（2026-11-17 审查 F15）：以前同一个 ?scrub=1 地址，副本没做好时给原片、做好后给副本，
        一次播放里后面的 Range 请求可能取自另一个文件（播到一半卡住 / 花屏）。现在不带版本的先 302 到带版本的地址
        （sv=o… 原片 / sv=c… 副本，跳转本身不缓存）；带版本的地址永远给同一个文件：正在放的接着放、能拖动，新开的播放用已经做好的副本"""
        sv = str(q.get('sv') or '')
        if not sv:
            target = scrub_for(path, beside)  # 副本好了给副本，没好给原片（并排进后台去做）
            try:
                ver = ('c' if os.path.normcase(target) != os.path.normcase(path) else 'o') + str(int(os.path.getmtime(target)))
            except OSError:
                return self.send_file(path, cache=cache)
            sep = '&' if '?' in self.path else '?'
            self.send_response(302)
            self.send_header('Location', self.path + sep + 'sv=' + ver)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if sv.startswith('c'):
            try:
                copy = scrub_path(path, beside) if not (beside and videogen.seekable(path)) else path
                if os.path.isfile(copy) and str(int(os.path.getmtime(copy))) == sv[1:]:
                    return self.send_file(copy, cache=cache)
            except OSError:
                pass
            rg = (self.headers.get('Range') or '').replace(' ', '')
            if rg and not rg.startswith('bytes=0-'):  # 副本放到一半没了 / 换过：中途的 Range 不能改从原片取字节（拼起来会卡住 / 花屏，第二轮审查 10），让播放器报错重新加载
                self.send_response(410); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', '0'); self.end_headers()
                return
        return self.send_file(path, cache=cache)  # sv=o…；或副本没了、但这是从头开始的请求：原片

    def send_file(self, path, download_name=None, cache=None):
        path = longp(path)
        if not os.path.isfile(path):
            return self.send_json({'error': '文件不存在'}, 404)
        size = os.path.getsize(path)
        start, end = 0, size - 1
        m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if m and size:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:  # bytes=-N：最后 N 字节
                start = max(0, size - int(m.group(2) or 0))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        m = m if size else None  # 空文件：普通 200
        self.send_response(206 if m else 200)
        self.send_header('Content-Type', MIME.get(os.path.splitext(path)[1].lower(), 'application/octet-stream'))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if m:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Cache-Control', cache or 'no-store')
        if download_name:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
        self.end_headers()
        with open(path, 'rb') as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))  # 1MB 一块：高码率视频（100 Mbit/s）每秒只需写十几次
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def body(self):
        # 请求体只读一次并缓存。必须在处理前读完：否则没读的字节会留在长连接里，
        # 下一个请求被解析成“{}GET …”而返回 501（取消任务后卡片闪没就是这个原因）
        if not hasattr(self, '_body'):
            n = int(self.headers.get('Content-Length') or 0)
            if n < 0:
                self.close_connection = True
                raise BadRequest('请求长度有误')
            if n > 100 << 20:  # 不是上传文件的请求：最多 100MB（图生图的原图也够了）
                self.close_connection = True
                raise BadRequest('请求过大')
            self._body = self.rfile.read(n) if n else b''
        return self._body

    def save_body(self, path, limit=32 << 30):
        """上传的文件（请求头带 X-Filename）：按 1MB 一块直接写进 path，返回内容的 sha1。
        带 X-Lib-Path：不传文件内容，直接从当前空间的音源库里复制那个文件（“从音源库选”，手机上不用先下载再上传）。"""
        n = int(self.headers.get('Content-Length') or 0)
        if n < 0:
            self.close_connection = True
            raise BadRequest('请求长度有误')
        lp = self.headers.get('X-Lib-Path')
        if lp:
            if n:
                self.rfile.read(n)
            self._body = b''
            src = lib_target(urllib.parse.unquote(lp), False)
            h = hashlib.sha1()
            with open(longp(src), 'rb') as fi, open(path, 'wb') as f:
                for chunk in iter(lambda: fi.read(1 << 20), b''):
                    f.write(chunk); h.update(chunk)
            return h.hexdigest()
        if n > limit:
            self.close_connection = True
            raise RuntimeError('文件过大（超过 32 GB）')
        h, left = hashlib.sha1(), n
        with open(path, 'wb') as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk); h.update(chunk); left -= len(chunk)
        self._body = b''  # 已经读完了
        if left:
            raise RuntimeError('上传未完成，请重试')
        return h.hexdigest()

    def jbody(self):
        b = self.body()
        try:
            v = json.loads(b.decode('utf-8')) if b else {}
        except (ValueError, UnicodeDecodeError):
            raise BadRequest('请求内容不是有效的 JSON')
        if not isinstance(v, dict):
            raise BadRequest('请求内容格式有误')
        return v

    def route(self, method):
        u = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in u.path.strip('/').split('/') if p]
        q = dict(urllib.parse.parse_qsl(u.query))
        self.__dict__.pop('_body', None)  # 同一连接上的新请求
        CTX.space = 'v' if vault_ok(self.headers.get('Cookie', '')) else 'n'
        # 手机（通过 Tailscale 来的请求）：必须是配对过的设备；只能用播放相关的功能；进不了私密空间
        # 经过 Tailscale 的 https 转发（tailscale serve）进来的也算远程：它会带上这些头，就算转发到了本机地址也照样要配对
        self.remote = self.client_address[0] not in ('127.0.0.1', '::1') or any(self.headers.get(h) for h in ('Tailscale-User-Login', 'Tailscale-Headers-Info', 'X-Forwarded-For'))
        upload = bool(self.headers.get('X-Filename') or self.headers.get('X-Lib-Path'))
        try:
            # 只接受本机地址打开的页面发来的请求：别的网站（包括把域名解析到 127.0.0.1 的那种）不能偷偷调用这里的接口
            host = (self.headers.get('Host') or '').lower()
            hname = host[1:].split(']')[0] if host.startswith('[') else host.rsplit(':', 1)[0]
            origin = self.headers.get('Origin')
            bad = (not self.remote and hname not in ('127.0.0.1', 'localhost', '::1')) or \
                  (method != 'GET' and origin is not None and urllib.parse.urlparse(origin).netloc.lower() != host)
            if bad:
                self.close_connection = True
                return self.send_json({'error': '拒绝来自其他网站的请求'}, 403)
            if not upload and not self.remote:  # 上传的文件由各接口自己边收边写；手机的先查配对再读
                self.body()
            if self.remote and not remote.load().get('enabled'):  # 手机访问关了：Tailscale 的 HTTPS 转发（serve）还指着本机时也一律不接（审查 5）
                self.close_connection = True
                return self.send_json({'error': '手机访问已关闭'}, 403)
            if self.remote:
                if remote.match(method, parts, remote.PUBLIC):
                    CTX.space = 'n'
                else:
                    _dev = remote.device_of(self.headers.get('Cookie', ''))
                    if _dev:
                        push.SEEN[_dev['id']] = time.time()  # 手机正开着 Studio：做完了不用推送
                    if not _dev:
                        tok = remote.redeem(q['it']) if method == 'GET' and q.get('it') else None
                        if tok:  # 主屏幕应用第一次打开：换成它自己的登录信息，再回到同一页（地址里不再带令牌）
                            self.close_connection = True
                            self.send_response(302); self.send_header('Location', '/' + '/'.join(parts) if parts else '/play')
                            self.send_header('Set-Cookie', f'dev={tok}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax')
                            self.send_header('Content-Length', '0'); self.end_headers()
                            return
                        CTX.space = 'n'
                        self.close_connection = True  # 没读请求体：这条连接不再复用
                        if method == 'GET' and (not parts or parts[0] in ('play', 'tts', 'works', 'vc', 'voices', 'stt', 'help', 'img', 'prompt', 'video', 'audioedit', 'mats', 'settings', 'batch')):
                            self.send_response(302); self.send_header('Location', '/pair'); self.send_header('Content-Length', '0'); self.end_headers()
                            return
                        return self.send_json({'error': '此设备尚未配对'}, 401)
                    if remote.pc_only(method, parts):
                        self.close_connection = True
                        return self.send_json({'error': '此功能仅可在电脑上使用'}, 403)
                if not upload:
                    self.body()
            if self.headers.get('X-Space') == 'v' and space() != 'v' and parts[:1] == ['api'] and parts[1:2] != ['vault']:
                return self.send_json({'error': 'vault expired'}, 409)
            if self.headers.get('X-Space') == 'n' and space() == 'v' and parts[:1] == ['api'] and parts[1:2] != ['vault']:
                # 页面在普通空间，凭证却是私密空间的（同一浏览器的别的标签页进了私密空间，Cookie 是共用的）：按普通空间处理这个请求，
                # 不给私密内容（2026-11-17 审查 F20：以前回 409，新标签页只好把私密空间退掉，连带把别的标签页的私密会话也撤了）
                CTX.space = 'n'
            self.dispatch(method, parts, q)
        except (ConnectionError, BrokenPipeError):
            pass
        except BadRequest as e:
            self.send_json({'error': str(e)}, 400)
        except Exception as e:
            print_tb()
            try:
                self.send_json({'error': public_error(e)}, 400 if isinstance(e, (RuntimeError, ValueError, TypeError, KeyError, IndexError, AttributeError)) else 500)
            except Exception:
                pass
        finally:
            if upload and not hasattr(self, '_body'):  # 上传没被读走（被拒绝了 / 出错了）：这条连接不能再用
                self.close_connection = True

    do_GET = lambda self: self.route('GET')
    do_POST = lambda self: self.route('POST')
    do_DELETE = lambda self: self.route('DELETE')
    do_PATCH = lambda self: self.route('PATCH')

    def dispatch(self, method, p, q):
        if (p[:1] in (['extensions'], ['fisher_pose'], ['view']) or p[:2] == ['upload', 'image']) and fisher.handle(self, method, p, q, space()):
            return  # Fisher Pose 的 3D 人偶编辑器（生图页里用 iframe 打开）要的接口，见 fisher.py
        if method == 'GET' and (not p or (len(p) == 1 and p[0] in ('tts', 'vc', 'voices', 'works', 'stt', 'help', 'play', 'img', 'prompt', 'video', 'audioedit', 'mats', 'settings', 'batch'))):
            return self.send_static(os.path.join(WEB, 'index.html'), raw=index_html())
        if method == 'GET' and p == ['pair']:
            return self.send_file(os.path.join(WEB, 'pair.html'))
        if method == 'GET' and p == ['sw.js']:  # 推送用的 service worker：只管收推送、点通知打开页面，不缓存任何东西
            with open(os.path.join(WEB, 'sw.js'), 'rb') as f:
                body = f.read()
            self.send_response(200); self.send_header('Content-Type', 'application/javascript; charset=utf-8'); self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if method == 'GET' and p == ['manifest.webmanifest']:  # 添加到主屏幕：启动地址里带上这台设备的安装令牌
            it = q.get('it', '')
            start = '/play' + (('?it=' + urllib.parse.quote(it)) if re.fullmatch(r'[A-Za-z0-9_-]{16,64}', it) else '')
            body = json.dumps({'name': 'Studio', 'short_name': 'Studio', 'id': '/play', 'start_url': start, 'scope': '/', 'display': 'standalone',
                               'background_color': '#161618', 'theme_color': '#161618', 'lang': 'zh-CN',
                               'icons': [{'src': '/static/app-icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'}]}, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/manifest+json'); self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if not p:
            return self.send_json({'error': 'not found'}, 404)
        if p[:2] == ['api', 'remote']:
            return self.remote_api(method, p[2:])
        if p[:2] == ['api', 'push']:
            return self.push_api(method, p[2:])
        if method == 'GET' and p[0] == 'static':
            path = os.path.normpath(os.path.join(WEB, *p[1:]))
            if not path.startswith(WEB + os.sep):
                return self.send_json({}, 404)
            return self.send_static(path, immutable=bool(q.get('v')) and q.get('v') == static_ver(path))  # 版本号对得上才长期缓存
        if p[0] == 'media':
            return self.media(p[1:], q)
        if p[0] != 'api' or len(p) < 2:
            return self.send_json({'error': 'not found'}, 404)
        api = p[1:]
        if api == ['boot']:  # 很轻的一个：页面回到前台时问一下 Studio 有没有重启过；桌面应用也用它确认后台是不是自己启动的（owner 只给口令的摘要）
            return self.send_json({'boot': BOOT_ID, 'owner': OWNER_TAG, 'pid': os.getpid()})
        if api == ['status']:
            return self.send_json({'engine': engine_alive(), 'queue': sum(1 for j in list(job_queue) if getattr(j, 'space', 'n') == space()), 'remote': getattr(self, 'remote', False), **vaultkey.hint(VAULT_REC, VAULT_KEY_SHA, vault_legacy_allowed), 'rev': space_rev()})  # vk / vks：网页本地粗筛用的 2 位提示和提示盐（F08）
        if api == ['shutdown'] and method == 'POST':  # 只有启动了这个后台的桌面应用能叫（关窗口时）
            if getattr(self, 'remote', False):
                return self.send_json({'error': '仅可在电脑上关闭'}, 403)
            # 2026-11-17 审查 F04：以前谁叫都关——桌面应用误连到别人启动的 Studio 时，关窗口会把它关掉。现在要带启动时给的口令
            if not OWNER_TOKEN or not hmac.compare_digest(self.headers.get('X-Studio-Owner') or '', OWNER_TOKEN):
                return self.send_json({'error': '这个 Studio 不是由这个应用启动的，不关闭'}, 403)
            self.send_json({'ok': True})
            threading.Thread(target=shutdown_self, daemon=True).start()
            return
        if api == ['restart'] and method == 'POST':  # 设置里的“重启 Studio”：换上新代码（关掉应用窗口不会重启后台）
            b = self.jbody()
            busy = busy_work()
            if busy and not b.get('force'):
                return self.send_json({'busy': busy})
            self.send_json({'ok': True})
            threading.Thread(target=restart_self, daemon=True).start()
            return
        if api == ['activity']:
            since, tag = int(q.get('since') or 0), q.get('tag')
            return self.send_json([e for e in list(ACT) if e['seq'] > since and (not tag or e['tag'] == tag) and e.get('space', 'n') == space()])
        if api[0] == 'batch':  # 2026-11-14 批量配方（batch.py）
            return self.batch_api(method, api[1:], q)
        if api[0] == 'agent':  # 2026-11-14 给 Agent（agent_mcp.py）用：只收 / 只回代号和数字（agentapi.py）
            return self.agent_api(method, api[1:], q)
        if api[0] == 'vault':
            return self.vault_api(method, api[1:], q)
        if api[0] == 'rc':  # 遥控播放：私密空间里用电脑控制手机（手机在哪个空间都行，见 vaultrc.py）
            return self.rc_api(method, api[1:], q)
        if api[0] == 'civitai':
            return self.civitai_api(method, api[1:], q)
        if api == ['play', 'subs']:
            return self.play_api(method, api[2:], q)
        if api == ['play', 'translate']:
            return self.play_translate(method, q)
        if api and api[0] == 'cache':  # 设置页 · 存储：缓存占了多少、清掉多久以前的（只管当前空间；作品、原视频、字幕都不碰，见 cachemgr.py）
            import cachemgr
            sp = space()
            cs = cachemgr.cats(videogen.videos_dir(sp), covers_dir(), conv_dir(), VTMP if sp == 'v' else TMP)
            if api == ['cache']:
                return self.send_json({'space': sp, 'cats': cachemgr.stats(cs)})
            if api == ['cache', 'clean'] and method == 'POST':
                b = self.jbody()
                keys = [str(k) for k in (b.get('keys') or []) if str(k) in ('scrub', 'covers', 'conv', 'tmp')]
                try:
                    days = int(b.get('days') or 0)
                except (TypeError, ValueError):
                    days = -1
                if days not in (0, 30, 90, 180, 365) or not keys:
                    return self.send_json({'error': '请选择要清除的内容和时间范围'}, 400)
                with _scrub_lock:
                    busy = set(_scrub_busy)
                r = cachemgr.clean(cs, keys, days, busy)
                return self.send_json({**r, 'cats': cachemgr.stats(cs)})
        if api == ['vram']:
            if method == 'POST':  # 释放：某一个模型 / 全部
                mid = str(self.jbody().get('id', ''))
                info = vram_info()
                ids = [x['id'] for x in info['items']] if mid == 'all' else [mid]
                # 先把会冲突的都查一遍，有一个在忙就什么都不停（审查 22：以前先停了本地翻译，后面才发现在生图 / 生视频，返回失败时翻译已经被停掉）
                if 'prompt' in ids and promptgen.Engine.busy:
                    return self.send_json({'error': '提示词模型正在生成，完成后再释放'}, 409)
                if 'video' in ids and any(j.get('state') == 'running' for j in list(videogen.jobs.values())):
                    return self.send_json({'error': '正在生成视频，完成后再释放'}, 409)
                if ('video' in ids or 'imagegen' in ids) and any(j.get('state') == 'running' for j in list(imagegen.jobs.values())):
                    return self.send_json({'error': '正在生成图片，完成后再释放'}, 409)
                if 'translate' in ids:
                    translate._Local.stop(); ids.remove('translate')
                if 'prompt' in ids:
                    ids.remove('prompt')
                    if promptgen.Engine.busy:
                        return self.send_json({'error': '提示词模型正在生成，完成后再释放'}, 409)
                    promptgen.stop()
                if 'imagegen' in ids:
                    ids.remove('imagegen')
                    if not imagegen.GPU.acquire(blocking=False):
                        return self.send_json({'error': '正在生成图片，本张完成后再释放'}, 409)
                    try:
                        imagegen.Engine.stop()
                    finally:
                        imagegen.GPU.release()
                if 'video' in ids:
                    ids.remove('video')
                    if any(j.get('state') == 'running' for j in list(videogen.jobs.values())):
                        return self.send_json({'error': '正在生成视频，完成后再释放'}, 409)
                    if any(j.get('state') == 'running' and imagegen.comfy(j.get('model')) for j in list(imagegen.jobs.values())):
                        return self.send_json({'error': '正在生成图片（和视频共用引擎），完成后再释放'}, 409)  # 2026-11-16 审查：以前只看视频任务
                    videogen.Engine.free()  # 卸掉 ComfyUI 里载入的模型（引擎本身留着，下次用时重新载入）
                if ids:
                    try:
                        engine('/v1/tasks/unload_models', {'model_ids': ids})
                    except Exception as e:
                        return self.send_json({'error': str(e)}, 500)
                time.sleep(.4)
                v = vram_info()
                with _vram_lock:
                    _vram_c['t'], _vram_c['v'] = time.time(), v
                return self.send_json(v)
            return self.send_json(vram_info_cached())
        if api == ['diag'] and method == 'POST':  # 播放掉帧记录（网页发现视频掉帧时报上来，方便查“偶尔卡”的原因）
            b = self.jbody()
            if space() == 'v':
                return self.send_json({'ok': True})
            with open(DIAG_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'t': time.strftime('%Y-%m-%d %H:%M:%S'), **{k: b.get(k) for k in list(b)[:20]}}, ensure_ascii=False) + '\n')
            return self.send_json({'ok': True})
        if api == ['play', 'external']:  # 用 PotPlayer 打开（特别重的视频的退路）
            if space() == 'v':  # PotPlayer 会记下最近播放的文件名：私密空间里不用
                return self.send_json({'potplayer': False} if method == 'GET' else {'error': '私密空间中不能使用 PotPlayer 打开'}, 200 if method == 'GET' else 403)
            if method == 'GET':
                return self.send_json({'potplayer': os.path.isfile(POTPLAYER)})
            b = self.jbody()
            if not os.path.isfile(POTPLAYER):
                return self.send_json({'error': '未找到 PotPlayer'}, 400)
            try:
                audio, _ = play_subs_target(b.get('key', ''))
                t = max(0, int(float(b.get('t') or 0)))
            except (RuntimeError, ValueError, TypeError) as e:
                return self.send_json({'error': str(e) or '参数有误'}, 400)
            subprocess.Popen([POTPLAYER, longp(audio), f'/seek={t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d}'])
            return self.send_json({'ok': True})
        if api == ['play', 'translate-engines']:
            return self.send_json({'google': True, 'local': translate.local_available()})
        if api[:1] == ['play'] and api[1:] in (['library'], ['images'], ['imginfo'], ['reveal'], ['delete'], ['convert'], ['favs'], ['recent'], ['tags'], ['order'], ['subsearch']):
            return self.play_lib_api(method, api[1:], q)
        if api == ['models']:
            return self.send_json(list_models())
        if api[0] == 'voices':
            return self.voices(method, api[1:], q)
        if api[0] == 'jobs':
            return self.jobs(method, api[1:], q)
        if api == ['preview'] and method == 'POST':
            return self.preview()
        if api == ['settings']:
            if method == 'POST':
                stt.save_settings(self.jbody())
            return self.send_json(stt.public_settings())
        if api == ['tts', 'engine-opts']:
            if method == 'POST':
                busy = any(getattr(j, 'state', '') in ('running', 'queued') for j in list(jobs.values())) or \
                    any(getattr(j, 'state', '') == 'running' for j in list(stt.stt_jobs.values()))
                try:
                    changed = set_tts_engine_opts(self.jbody())
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
                restarted = False
                if changed and not busy:  # 没有任务在用引擎：马上按新参数重启（约 10 秒）
                    with engine_lock:
                        try:
                            start_engine()
                            restarted = True
                        except SystemExit as se:
                            return self.send_json({'error': str(se)}, 500)
                return self.send_json({**tts_engine_opts(), 'changed': changed, 'restarted': restarted})
            return self.send_json(tts_engine_opts())
        if api == ['templates']:  # 模板套（2026-11-09）：GET 列表 / ?id= 某一套的全文；POST 新建 / 保存 / 删除 / 设为默认
            if method == 'POST':
                try:
                    return self.send_json(tplstore.op(space(), self.jbody(), write_json))
                except (ValueError, TypeError) as e:
                    return self.send_json({'error': str(e)}, 400)
            if q.get('id'):
                x = tplstore.get(space(), str(q['id']))
                return self.send_json(x) if x['id'] == str(q['id']) else self.send_json({'error': '找不到这套模板'}, 404)
            return self.send_json(tplstore.listing(space()))
        if api[0] == 'prompt':
            return self.prompt_api(method, api[1:])
        if api[0] == 'img':
            return self.img_api(method, api[1:], q)
        if api == ['video', 'film']:  # 剪辑条上的一排小画面：?u=素材库 / 视频库里视频的地址（/media/mats/… 或 /media/video/…）&n=张数&h=高度
            from urllib.parse import unquote, urlsplit
            u = unquote(urlsplit(q.get('u') or '').path)
            path = None
            try:
                if u.startswith('/media/mats/'):
                    path = mats_path(u[len('/media/mats/'):])
                elif u.startswith('/media/video/'):
                    path = videogen.video_path(u[len('/media/video/'):], space())
            except ValueError:
                path = None
            if not path or not os.path.isfile(path):
                return self.send_json({'error': '找不到这个视频'}, 404)
            try:
                jpg = film_for(path, q.get('n') or 12, q.get('h') or 72)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)
            return self.send_file(jpg, cache=None if space() == 'v' else 'private, max-age=31536000, immutable') if jpg else self.send_json({'error': '截不出画面'}, 500)
        if api[0] == 'video':
            return self.video_api(method, api[1:], q)
        if api == ['mats', 'gallery']:  # 素材库 / gallery 的整份清单（姿势 / 衣服 / 脸 + 原站的分类）：网页里筛选、搜索，不用一层层点文件夹
            keep = ('lib', 'id', 'group', 'cat', 'pose', 'name', 'angle', 'keywords', 'hair', 'style')
            idx = mats_index(); key = (_MATS_IDX.get('key'), MATS_GEN[0])
            if _MATS_GAL.get('key') != key or time.time() - _MATS_GAL.get('t', 0) > 300:  # 几千个文件逐个查在不在要 0.4 秒：清单没变、素材库没删改时 5 分钟内直接用上次的
                _MATS_GAL.update(key=key, t=time.time(), items=[{'rel': rel, **{k: x[k] for k in keep if x.get(k)}} for rel, x in idx.items() if os.path.isfile(mats_path(rel))])
            return self.send_json({'items': _MATS_GAL['items'], 'ver': hashlib.sha1(repr(key[0]).encode()).hexdigest()[:8]})
        if api == ['mats', 'dirs']:  # 素材库里所有的文件夹（“移动到…”用；不含 gallery 和隐藏文件夹）
            root, out = os.path.abspath(MATS_DIR), []
            for top, ds, _ in os.walk(root):
                ds[:] = sorted((x for x in ds if not x.startswith('.') and not (top == root and x == 'gallery') and not mats_hid_dir(top, x)), key=str.lower)
                out += [os.path.relpath(os.path.join(top, x), root).replace('\\', '/') for x in ds]
                if len(out) > 3000:
                    break
            return self.send_json({'dirs': out})
        if api[:1] == ['mats'] and api[1:] in (['mkdir'], ['move'], ['delete']) and method == 'POST':
            MATS_GEN[0] += 1  # 素材库里删改了：gallery 清单重新查  # 素材库页面“文件夹”：新建文件夹 / 移动 / 删除（进回收站）
            b = self.jbody()
            try:
                return self.send_json(mats_edit(api[1], b))
            except (RuntimeError, ValueError, OSError) as e:
                return self.send_json({'error': str(e)}, 400)
        if api == ['mats', 'tags']:  # 素材库：这个文件夹往下所有层里文件名开头 @ 的标签（@ 到第一个 _ 之间）和各有几个文件
            try:
                d = mats_path(q.get('dir') or '')
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            kind = q.get('kind') if q.get('kind') in MATS_EXT else None
            exts = MATS_EXT[kind] if kind else tuple(x for v in MATS_EXT.values() for x in v)
            cnt, last = {}, {}
            for top, ds, fs in os.walk(d) if os.path.isdir(d) else []:
                ds[:] = [x for x in ds if not x.startswith('.') and not (q.get('skip') and top == d and x == q.get('skip')) and not mats_hid_dir(top, x)]
                if kind in (None, 'image'):  # 图集：一个文件夹算一个（标签在文件夹名上）
                    for x in [x for x in ds if os.path.isfile(os.path.join(top, x, MATS_SET_FILE))]:
                        ds.remove(x); t = mats_tag(x + '.')
                        if t:
                            k = t.lower(); cnt[k] = cnt.get(k, 0) + 1; last.setdefault(k, t)
                for n in fs:
                    t = mats_tag(n) if n.lower().endswith(exts) else None
                    if t:
                        k = t.lower(); cnt[k] = cnt.get(k, 0) + 1; last.setdefault(k, t)
            return self.send_json({'tags': sorted(({'tag': last[k], 'n': v} for k, v in cnt.items()), key=lambda x: (-x['n'], x['tag'].lower()))})
        if api == ['mats']:  # 素材库：列出一个文件夹里的子文件夹和素材（?dir=相对路径&kind=video|image|audio）
            try:
                d = mats_path(q.get('dir') or '')
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            kind = q.get('kind') if q.get('kind') in MATS_EXT else None
            exts = MATS_EXT[kind] if kind else tuple(x for v in MATS_EXT.values() for x in v)
            if not os.path.isdir(d):
                return self.send_json({'root': MATS_DIR, 'dir': '', 'dirs': [], 'files': [], 'missing': True})
            rel = os.path.relpath(d, os.path.abspath(MATS_DIR)).replace('\\', '/')
            rel = '' if rel == '.' else rel
            dirs, files = [], []
            tag = str(q.get('tag') or '')
            if tag:  # @标签筛选：这个文件夹往下所有层里，文件名开头是 @标签_ 的（不分大小写），可再加搜索词
                words_t = [w for w in str(q.get('q') or '').lower().split() if w]
                out = []
                for top, ds, fs in os.walk(d):
                    ds[:] = sorted(x for x in ds if not x.startswith('.') and not (q.get('skip') and top == d and x == q.get('skip')) and not mats_hid_dir(top, x))
                    r0 = os.path.relpath(top, os.path.abspath(MATS_DIR)).replace('\\', '/')
                    if kind in (None, 'image'):  # 图集：看文件夹名的 @标签，整个算一格，不再往里找
                        for x in list(ds):
                            rx = (r0 + '/' if r0 != '.' else '') + x
                            if os.path.isfile(os.path.join(top, x, MATS_SET_FILE)):
                                ds.remove(x)
                                if (mats_tag(x + '.') or '').lower() == tag.lower() and (not words_t or all(w in rx.lower() for w in words_t)) and (ms := mats_set(os.path.join(top, x), rx)):
                                    out.append(dict(ms, sub='' if top == d else os.path.relpath(top, d).replace(os.sep, '/')))
                    for n in sorted(fs):
                        if n.startswith('.') or not n.lower().endswith(exts) or (mats_tag(n) or '').lower() != tag.lower():
                            continue
                        r = (r0 + '/' if r0 != '.' else '') + n
                        if words_t and not all(w in r.lower() for w in words_t):
                            continue
                        try:
                            st_ = os.stat(os.path.join(top, n))
                        except OSError:
                            continue
                        ext = os.path.splitext(n)[1].lower()
                        out.append({'name': n, 'rel': r, 'label': mats_label(r), 'size': st_.st_size, 'mtime': st_.st_mtime, 'added': mats_added(st_),
                                    'kind': next(k for k, v in MATS_EXT.items() if ext in v), 'sub': '' if top == d else os.path.relpath(top, d).replace(os.sep, '/')})
                    if len(out) >= 2000:
                        break
                return self.send_json({'root': MATS_DIR, 'dir': rel, 'dirs': [], 'files': out[:2000], 'tag': tag, 'more': len(out) >= 2000})
            words = [w for w in str(q.get('q') or '').lower().split() if w]
            if words:  # 搜索：这个文件夹往下所有层，文件名 / 路径 / 素材站的名字和关键词里都有这些字的（最多 400 个）
                idx = mats_index()
                for top, ds, fs in os.walk(d):
                    ds[:] = sorted(x for x in ds if not x.startswith('.') and not (q.get('skip') and top == d and x == q.get('skip')) and not mats_hid_dir(top, x))  # skip：不搜这个子文件夹（素材库页面的“文件夹”不搜 gallery）
                    r0 =os.path.relpath(top, os.path.abspath(MATS_DIR)).replace('\\', '/')
                    for n in sorted(fs):
                        if n.startswith('.') or not n.lower().endswith(exts):
                            continue
                        r = (r0 + '/' if r0 != '.' else '') + n
                        x = idx.get(r) or {}
                        hay = ' '.join([r, str(x.get('keywords') or ''), str(x.get('id') or ''), json.dumps(x.get('ja') or {}, ensure_ascii=False)]).lower()
                        if all(w in hay for w in words):
                            files.append(r)
                    if len(files) >= 400:
                        break
                files = files[:400]
                out, seen = [], set()
                for r in files:
                    pr = r.rsplit('/', 1)[0] if '/' in r else ''
                    if pr and kind in (None, 'image') and (pr in seen or (ms := mats_set(os.path.join(MATS_DIR, pr), pr))):
                        if pr not in seen:
                            seen.add(pr); out.append(ms)
                        continue  # 图集里的图：合成那一格
                    ext = os.path.splitext(r)[1].lower()
                    out.append({'name': os.path.basename(r), 'rel': r, 'label': mats_label(r), 'kind': next(k for k, v in MATS_EXT.items() if ext in v)})
                return self.send_json({'root': MATS_DIR, 'dir': rel, 'dirs': [], 'files': out, 'search': True, 'more': len(files) >= 400})
            dadd = {}  # 子文件夹的加入时间（网页上“按加入时间”排序用）
            for e in sorted(os.scandir(d), key=lambda e: (not e.name.startswith('正面'), e.name.lower())):  # 姿势的几个角度：正面排第一
                if e.name.startswith('.'):
                    continue
                if e.is_dir():
                    if mats_hid_dir(d, e.name):  # 只在私密空间显示的文件夹
                        continue
                    if kind in (None, 'image') and (ms := mats_set(e.path, (rel + '/' if rel else '') + e.name)):
                        files.append(ms); continue  # 图集：一格（不显示成文件夹）
                    dirs.append(e.name)
                    try:
                        dadd[e.name] = mats_added(e.stat())
                    except OSError:
                        pass
                elif e.name.lower().endswith(exts):
                    ext = os.path.splitext(e.name)[1].lower()
                    st_ = e.stat()
                    r = (rel + '/' if rel else '') + e.name
                    files.append({'name': e.name, 'rel': r, 'label': mats_label(r), 'size': st_.st_size, 'mtime': st_.st_mtime, 'added': mats_added(st_),
                                  'kind': next(k for k, v in MATS_EXT.items() if ext in v)})
            if kind != 'video' and os.path.isfile(os.path.join(d, MATS_SET_FILE)):  # 打开了一个图集：实况的视频跟着同名的图（live），不单独列成一个视频（选视频时照常列出）
                stem = lambda x: os.path.splitext(x['name'])[0]
                lv = {stem(x): x['rel'] for x in files if x.get('kind') == 'video'}
                ims = {stem(x) for x in files if x.get('kind') == 'image'}
                files = [dict(x, live=lv.get(stem(x))) if x.get('kind') == 'image' and stem(x) in lv else x for x in files if not (x.get('kind') == 'video' and stem(x) in ims)]
            if files:  # 视频截图（frames.py）：图片标上来自哪个视频、第几秒；视频标上截过几张
                fb, fc = frames.by_image(), frames.counts()
                for x in files:
                    if x.get('kind') == 'image' and not x.get('set') and x.get('rel') in fb:
                        x['ft'], x['fsrc'] = fb[x['rel']][1], fb[x['rel']][2]
                    elif x.get('kind') == 'video' and fc.get('m:' + x.get('rel', '')):
                        x['nframes'] = fc['m:' + x['rel']]
            covers = {}  # 子文件夹的封面：里面放了 .cover.png / .cover.jpg（隐藏文件，不会列出来）就用它；选图片时，没有的用里面第一张图（姿势的每个文件夹就是一个姿势的几个角度）
            for n in dirs:
                try:
                    names = [e.name for e in os.scandir(os.path.join(d, n)) if e.is_file()]
                except OSError:
                    continue
                own = next((c for c in ('.cover.png', '.cover.jpg', '.cover.jpeg', '.cover.webp') if c in names), None)
                imgs = [] if own or kind not in ('image', None) else sorted(  # 不限类型（素材库页面的“文件夹”）也给封面：只用图片
                    (s for s in names if not s.startswith('.') and s.lower().endswith(MATS_EXT['image'])), key=lambda s: (not s.startswith('正面'), s.lower()))
                first = own or (imgs[0] if imgs else None)
                if first:
                    covers[n] = (rel + '/' if rel else '') + n + '/' + first
            if kind in (None, 'video'):  # 这个文件夹里的视频：后台提前做好播放副本（打开剪辑时直接放副本，不卡）
                scrub_prefetch([os.path.join(d, f['name']) for f in sorted((f for f in files if f['kind'] == 'video'), key=lambda f: -f['mtime'])][:24])  # 最新的 24 个（副本每个十几到几十 MB，不全做）
            return self.send_json({'root': MATS_DIR, 'dir': rel, 'dirs': dirs, 'files': files, 'covers': covers, 'dirs_added': dadd, 'set': os.path.isfile(os.path.join(d, MATS_SET_FILE))})  # set：这是一个图集（网页上按作品里的顺序排）
        if api[0] == 'frames':
            return self.frames_api(method, api[1:], q)
        if api[0] == 'stt':
            return self.stt_api(method, api[1:], q)
        if api[0] == 'audioedit':
            return self.audioedit_api(method, api[1:])
        if api == ['vc', 'models']:
            return self.send_json(list_vc_models())
        if api == ['vc', 'upload'] and method == 'POST':
            return self.vc_upload(q)
        if api == ['vc', 'subs']:
            return self.vc_subs(q)
        self.send_json({'error': 'not found'}, 404)

    def media(self, p, q):
        """媒体文件（<img> / <video> 带不了 X-Space 头）：带私密凭证的请求先在私密空间找，找不到再找普通空间的（普通的内容本来就公开）；
        没有私密凭证的照旧只给普通空间的（F20：别的标签页在私密空间时，普通标签页里普通的图 / 视频照样能显示）"""
        if space() != 'v':
            return self._media(p, q)
        self._probe404 = True
        try:
            return self._media(p, q)
        except _MediaMiss:
            pass
        finally:
            self._probe404 = False
        CTX.space = 'n'
        return self._media(p, q)

    def _media(self, p, q):
        if len(p) == 2 and p[0] == 'video':  # 生成的视频 / 封面：只给当前空间自己的
            path = videogen.video_path(p[1], space())
            if path and q.get('scrub') and path.lower().endswith(('.mp4', '.webm', '.mov', '.mkv')):  # 播放副本：拖动进度条时画面跟得上
                return self.send_scrub(path, q, True, None if space() == 'v' else 'private, max-age=31536000, immutable')
            return self.send_file(path, cache=None if space() == 'v' else 'private, max-age=31536000, immutable') if path else self.send_json({'error': '视频不存在'}, 404)
        if len(p) == 2 and p[0] == 'img':  # 生图的图：只给当前空间自己图库里的
            path = imagegen.image_path(p[1])
            if path and q.get('thumb'):  # 图库里的小图：用缩略图（原图每张约 2MB，图一多就卡）
                path = thumb_for(path)
            # 文件名不会重复、图也不会改：普通空间让浏览器一直缓存；私密空间不留缓存（不在硬盘上留下痕迹）
            return self.send_file(path, cache=None if space() == 'v' else 'private, max-age=31536000, immutable') if path else self.send_json({'error': '图片不存在'}, 404)
        if len(p) == 2 and p[0] == 'voice':
            name = os.path.basename(p[1]); vid, ext = os.path.splitext(name)
            lib = voice_lib_of(vid)
            if ext.lower() != '.wav' or not lib:  # 只给音色本身的音频，不给 voices.json / prompt_text 这些
                return self.send_json({'error': '音色不存在'}, 404)
            return self.send_file(os.path.join(lib, name))
        if len(p) >= 2 and p[0] == 'mats':  # 素材库里的文件（只读）
            try:
                path = mats_path('/'.join(p[1:]))
            except ValueError:
                return self.send_json({}, 404)
            if not (os.path.isfile(path) and path.lower().endswith(tuple(x for v in MATS_EXT.values() for x in v))):
                return self.send_json({}, 404)
            # 小图带了 ?v=（文件的修改时间 / 素材站清单的版本）：文件变了地址就变，浏览器可以一直缓存（2026-11-11：以前 no-store，每次进文件夹都重新下载、等解码）
            tcache = 'private, max-age=31536000, immutable' if q.get('v') and space() != 'v' else None
            if q.get('thumb') and path.lower().endswith(MATS_EXT['image']):  # 列表里的小图（原图一张几 MB，一页几十张就卡）
                return self.send_file(mats_thumb(path), cache=tcache)
            if q.get('thumb') and path.lower().endswith(MATS_EXT['video']):  # 视频的小图（2026-11-08）：以前每一格都是一个播放器，几十个 4K 视频一起解码很慢，生成视频时更是出不来
                c = cover_for(path)
                return self.send_file(c, cache=tcache) if c else self.send_json({}, 404)
            if q.get('scrub') and path.lower().endswith(MATS_EXT['video']):  # 播放副本：拖动进度条时画面跟得上
                return self.send_scrub(path, q, False, None)
            return self.send_file(path)
        if len(p) >= 2 and p[0] == 'lib':  # 音源：当前空间自己的文件夹
            root = lib_root()
            path = os.path.normpath(os.path.join(root, *p[1:]))
            return self.send_file(path) if path.startswith(root + os.sep) else self.send_json({}, 404)  # send_file 会处理超长路径
        if len(p) >= 2 and p[0] == 'thumb':  # 图片缩略图：/media/thumb/<图片相对路径>
            try:
                return self.send_file(thumb_for(lib_path('/'.join(p[1:]))))
            except RuntimeError:
                return self.send_json({'error': 'no image'}, 404)
        if len(p) == 2 and p[0] == 'conv':  # 转换好的缓存
            return self.send_file(os.path.join(conv_dir(), os.path.basename(p[1])))
        if len(p) >= 2 and p[0] == 'cover':  # 封面：/media/cover/<音源相对路径>
            try:
                jpg = cover_for(lib_path('/'.join(p[1:])))
            except RuntimeError:
                jpg = None
            if not jpg:
                return self.send_json({'error': 'no cover'}, 404)
            return self.send_file(jpg)
        if len(p) == 2 and p[0] == 'tmp':
            return self.send_file(os.path.join(tmp_dir(), os.path.basename(p[1])))
        if len(p) == 3 and p[0] == 'audioedit' and p[2] in ('output.wav', 'input.wav'):  # 改录音的结果 / 原录音（转好的 wav）：只给当前空间自己的
            j = audioedit.jobs.get(p[1])
            if not j or j.get('_space') != space():
                return self.send_json({'error': '记录不存在'}, 404)
            return self.send_file(os.path.join(j['_dir'], p[2]), (f"改录音-{p[1]}.wav" if q.get('dl') else None))
        if len(p) == 3 and p[0] == 'stt' and p[1] in stt.stt_jobs and getattr(stt.stt_jobs[p[1]], 'space', 'n') == space() and p[2] in ('transcript.txt', 'transcript.srt'):
            j = stt.stt_jobs[p[1]]
            name = os.path.splitext(j.filename)[0] + os.path.splitext(p[2])[1] if q.get('dl') else None
            return self.send_file(os.path.join(j.dir, p[2]), name)
        if len(p) >= 3 and p[0] == 'job' and job_visible(p[1]):
            j = jobs[p[1]]
            if p[2] == 'seg' and len(p) == 4:
                return self.send_file(j.seg_path(int(p[3])))
            if p[2] == 'source.wav':
                return self.send_file(os.path.join(j.dir, 'source.wav'))
            if p[2] in ('output.mp3', 'output.wav'):
                name = re.sub(r'[\\/:*?"<>|\s]', '_', j.title) + os.path.splitext(p[2])[1] if q.get('dl') else None
                return self.send_file(os.path.join(j.dir, p[2]), name)
        self.send_json({'error': 'not found'}, 404)

    def preview(self):
        """短句试听：不进任务队列。"""
        b = self.jbody()
        model = model_info(b.get('model') or 'breeze')
        text = (b.get('text') or '').strip()[:300] or DEFAULT_SAMPLE
        m = DIRECTION_RE.match(text)
        direction = ''
        if m:
            direction, text = m.group(1).strip(), text[m.end():].strip()
        voice = get_voice(b['voice']) if b.get('voice') else None
        instruct = '，'.join(x for x in ((b.get('instruct') or '').strip(), direction) if x)
        payload, mode = build_request(model, text, voice, instruct, b.get('options'), int(b.get('seed') or 0),
                                      b.get('preset'), b.get('emotion_vector'), bool(b.get('emotion_auto')))
        name = 'pv_' + uuid.uuid4().hex[:10] + '.wav'
        tag = b.get('op', 'preview')
        act(f"试听：{model['display_name']} · {mode} · {len(text)} 字", tag)
        speak(payload, os.path.join(tmp_dir(), name), tag)
        self.send_json({'url': '/media/tmp/' + name, 'mode': mode})

    def batch_api(self, method, p, q):
        """/api/batch：配方（recipes）、一次批量的新建 / 列表 / 详情 / 停下 / 重做一段 / 换一版 / 删除记录"""
        import batch
        sp = space()
        b = self.jbody() if method == 'POST' else {}
        try:
            if p == ['recipes']:
                if method == 'POST':
                    return self.send_json(batch.recipe_save(sp, b.get('recipe') or {}))
                return self.send_json({'recipes': batch.recipes(sp), 'pass': batch.PASS})
            if len(p) == 2 and p[0] == 'recipes' and method == 'DELETE':
                batch.recipe_delete(sp, p[1]); return self.send_json({'ok': True})
            if not p:
                if method == 'POST':
                    return self.send_json(batch.create(sp, b.get('recipe'), b.get('items'), b.get('instruction')))
                return self.send_json({'batches': batch.listing(sp)})
            bid = p[0]
            if len(p) == 1:
                if method == 'DELETE':
                    batch.delete(sp, bid); return self.send_json({'ok': True})
                x = batch.get(sp, bid)
                return self.send_json(x) if x else self.send_json({'error': '没有这次批量'}, 404)
            if p[1] == 'cancel' and method == 'POST':
                return self.send_json(batch.cancel(sp, bid))
            if p[1] == 'redo' and method == 'POST':
                return self.send_json(batch.redo(sp, bid, b.get('item'), b.get('seg')))
            if p[1] == 'pick' and method == 'POST':
                return self.send_json(batch.pick(sp, bid, b.get('item'), b.get('seg'), b.get('try')))
        except (ValueError, TypeError, IndexError, KeyError) as e:
            return self.send_json({'error': str(e) or '参数有误'}, 400)
        return self.send_json({'error': '没有这个接口'}, 404)

    def agent_api(self, method, p, q):
        """/api/agent/<工具>：只给这台电脑上的 Agent（手机 / 远程进来的不行）；见 agentapi.py"""
        import agentapi
        if getattr(self, 'remote', False):
            return self.send_json({'error': '只能在这台电脑上使用'}, 403)
        if not agentapi._ctx:
            submit = video_edit_submit
            agentapi.setup(key_file=os.path.join(DATA, 'agent.key'), mats_dir=MATS_DIR, mats_path=mats_path, mats_hide=mats_hide, video_ext=VIDEO_EXT, probe=lambda p: videogen._probe(p, exact=False), videogen=videogen, act=act,
                           cp_dir=lambda sp: os.path.join(VTMP if sp == 'v' else TMP, 'cutpoints'), segpref=lambda sp: SEGPREF_V if sp == 'v' else SEGPREF_N,
                           idle=lambda: not busy_work(), submit=submit, ffmpeg=ffmpeg)
        sp = space()
        b = self.jbody() if method == 'POST' else {}
        tools = {'whoami': lambda: {'space': 'private' if sp == 'v' else 'normal'},
                 'list_videos': lambda: agentapi.list_videos(sp, b.get('source') or 'materials', b.get('limit') or 50, b.get('offset') or 0),
                 'cutpoints': lambda: agentapi.cutpoints(sp, str(b.get('video') or '')),
                 'recommend_segments': lambda: agentapi.recommend(sp, str(b.get('video') or '')),
                 'edit_outfit': lambda: agentapi.edit_outfit(sp, str(b.get('video') or ''), b.get('instruction') or '', b.get('segments'), b.get('viggle'), int(b.get('seed') if b.get('seed') is not None else -1), b.get('size') or '720p'),
                 'job_status': lambda: agentapi.job_status(sp, b.get('jobs')),
                 'check_quality': lambda: agentapi.check_quality(sp, str(b.get('job') or '')),
                 'retry': lambda: agentapi.retry(sp, str(b.get('job') or ''), int(b.get('seed') if b.get('seed') is not None else -1)),
                 'list_recipes': lambda: agentapi.list_recipes(sp),
                 'run_recipe': lambda: agentapi.run_recipe(sp, b.get('videos'), str(b.get('recipe') or ''), b.get('instruction')),
                 'batch_status': lambda: agentapi.batch_status(sp, str(b.get('batch') or ''))}
        f = tools.get(p[0] if p else '')
        if not f:
            return self.send_json({'error': '没有这个工具', 'tools': list(tools)}, 404)
        try:
            return self.send_json(f())
        except (ValueError, TypeError) as e:
            return self.send_json({'error': agentapi.scrub(e)}, 400)
        except Exception as e:
            return self.send_json({'error': '出错：' + agentapi.scrub(e)}, 500)

    def vault_api(self, method, p, q):
        if p == ['status']:
            return self.send_json({'vault': space() == 'v'})
        if p == ['unlock'] and method == 'POST':
            ip, now, rem = self.client_address[0], time.time(), getattr(self, 'remote', False)
            with lock:  # 先记一次（核对通过再撤销）：同时发来的很多请求也都会被算上
                for k in list(_vfail):
                    _vfail[k] = [t for t in _vfail[k] if now - t < 600]
                mine = _vfail.setdefault(ip, [])
                remote_all = sum(len(v) for k, v in _vfail.items() if k not in ('127.0.0.1', '::1'))
                if len(mine) >= (20 if rem else 200) or (rem and remote_all >= 40):  # 10 分钟里错太多次：先停一会儿（防止被一个个试出来）
                    return self.send_json({'error': 'too many'}, 429)
                mine.append(now)
            key = str(self.jbody().get('key', ''))
            if not vault_check(key):
                return self.send_json({'error': 'no'}, 403)
            tok = secrets.token_hex(24)
            with lock:
                if now in _vfail.get(ip, []):
                    _vfail[ip].remove(now)
                for old in sorted(list(VTOKS), key=lambda k: (VTOKS.get(k) or {}).get('last', 0))[:-19]:  # 最多留 20 个
                    VTOKS.pop(old, None)
                VTOKS[tok] = {'remote': bool(getattr(self, 'remote', False)), 'last': now}
            return self.send_json({'vault': True}, headers={'Set-Cookie': f'vault={tok}; Path=/; HttpOnly; SameSite=Strict'})
        if p == ['passkey', 'begin'] and method == 'POST':  # 面容 ID 解锁第一步：给一个一次性的挑战（这台设备没开启时就是 404，和没这个功能一样）
            dev, _ = self._dev_id(); host = self._host()
            if not dev or not passkey.has(dev, host):
                return self.send_json({'error': 'not found'}, 404)
            return self.send_json(passkey.auth_options(host, dev))
        if p == ['passkey', 'unlock'] and method == 'POST':  # 第二步：核对签名，通过就和输对密钥一样进私密空间
            ip, now, rem = self.client_address[0], time.time(), getattr(self, 'remote', False)
            with lock:
                mine = _vfail.setdefault(ip, [])
                if len([t for t in mine if now - t < 600]) >= (20 if rem else 200):
                    return self.send_json({'error': 'too many'}, 429)
                mine.append(now)
            try:
                passkey.verify(self.jbody(), self._dev_id()[0] or '-')  # 只认这台设备自己登记的（审查 10）
            except Exception as e:
                return self.send_json({'error': str(e) or '验证失败'}, 403)
            tok = secrets.token_hex(24)
            with lock:
                if now in _vfail.get(ip, []):
                    _vfail[ip].remove(now)
                for old in sorted(list(VTOKS), key=lambda k: (VTOKS.get(k) or {}).get('last', 0))[:-19]:
                    VTOKS.pop(old, None)
                VTOKS[tok] = {'remote': bool(rem), 'last': now}
            return self.send_json({'vault': True}, headers={'Set-Cookie': f'vault={tok}; Path=/; HttpOnly; SameSite=Strict'})
        if p == ['lock'] and method == 'POST':
            tok = cookie_val(self.headers.get('Cookie', ''), 'vault')
            with lock:
                VTOKS.pop(tok, None)
            vaultrc.disarm_owner(vaultrc.key_of(tok))  # 遥控播放：这台电脑开着的“控制手机”一起关掉（发给手机的一次性播放地址全部作废）
            if not VTOKS:
                clean_vtmp(600)  # 退出私密空间：它的临时文件（10 分钟内还可能在用的除外）删掉
                try:  # 智能选取存着的私密原图、部件也清掉（F03）
                    imagegen.q21.sam_forget_space('v')
                except Exception:
                    pass
            return self.send_json({'vault': False}, headers={'Set-Cookie': 'vault=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
        if space() != 'v':
            return self.send_json({'error': 'not found'}, 404)
        if p[:1] == ['passkey']:  # 私密空间里：开启 / 关闭这台设备的面容 ID 解锁
            dev, name = self._dev_id(); host = self._host()
            if not dev:
                return self.send_json({'error': '此设备尚未配对'}, 401)
            if p == ['passkey', 'status']:
                return self.send_json({'on': passkey.has(dev, host), 'host': host})
            if p == ['passkey', 'reg'] and method == 'POST':
                return self.send_json(passkey.reg_options(host, dev))
            if p == ['passkey', 'save'] and method == 'POST':
                try:
                    passkey.register(self.jbody(), dev, name)
                except Exception as e:
                    return self.send_json({'error': str(e) or '开启失败'}, 400)
                return self.send_json({'on': True})
            if p == ['passkey', 'remove'] and method == 'POST':
                passkey.remove(dev, host)
                return self.send_json({'on': False})
            return self.send_json({'error': 'not found'}, 404)
        if p == ['prefs']:
            if method == 'POST':
                d = self.jbody()
                with lock:
                    write_json(VPREFS, d if isinstance(d, dict) else {})
                return self.send_json({'ok': True})
            return self.send_json(read_json(VPREFS, {}) or {})
        return self.play_lib_api(method, p, q)

    def rc_api(self, method, p, q):
        """遥控播放（见 vaultrc.py）。手机（配对过的设备，两个空间都行）：POST state 报在放什么 / GET wait 等命令 /
        POST hand 退出私密空间前把正在放的换成一次性地址 / GET m/<一次性地址> 放电脑点的私密内容。
        电脑（本机，只在私密空间里）：POST arm 开启 / 关掉控制，GET view 看手机在放什么（ctl=1 = 正在控制），GET queue 手机的播放列表，POST cmd 发命令。
        GET silence.wav：手机暂停时循环放的无声音频（让锁屏的网页保持运行、电脑还能叫醒它）"""
        sp = space()
        if p == ['silence.wav']:
            b, n = vaultrc.silence_wav(), None
            m = re.match(r'bytes=(\d*)-(\d*)$', self.headers.get('Range') or '')  # iPhone 的 Safari 放音频要先要一小段（bytes=0-1），不支持分段就不放
            if m and (m.group(1) or m.group(2)):
                a0 = int(m.group(1)) if m.group(1) else max(0, len(b) - int(m.group(2)))
                a1 = min(len(b) - 1, int(m.group(2))) if m.group(1) and m.group(2) else len(b) - 1
                n, b = len(b), b[a0:a1 + 1]
            self.send_response(206 if n else 200)
            if n:
                self.send_header('Content-Range', f'bytes {a0}-{a0 + len(b) - 1}/{n}')
            self.send_header('Content-Type', 'audio/wav'); self.send_header('Content-Length', str(len(b)))
            self.send_header('Accept-Ranges', 'bytes'); self.send_header('Cache-Control', 'private, max-age=86400'); self.end_headers()
            self.wfile.write(b)
            return
        if getattr(self, 'remote', False):  # 手机
            dev, _ = self._dev_id()
            if not dev:
                return self.send_json({'error': '此设备尚未配对'}, 401)
            if p == ['state'] and method == 'POST':
                return self.send_json(vaultrc.report(dev, self.jbody(), sp))
            if p == ['wait']:
                try:
                    since = int(q.get('since', -1))
                except ValueError:
                    since = -1
                seen = {'1': True, '0': False}.get(q.get('armed'))
                vt = cookie_val(self.headers.get('Cookie', ''), 'vault')
                return self.send_json(vaultrc.wait(dev, since, sp, seen, playing=q.get('p') == '1', vok=lambda: bool(vt) and vt in VTOKS))  # 挂着的时候退出了私密空间：按普通空间发
            if p == ['hand'] and method == 'POST' and sp == 'v':
                b = self.jbody()
                r = vaultrc.hand(dev, b.get('items'), b.get('i'))
                return self.send_json(r) if r else self.send_json({'error': '电脑未在控制'}, 409)
            if len(p) == 3 and p[0] == 'm' and method == 'GET':
                path = vaultrc.media(p[1], dev)
                if not path:
                    return self.send_json({'error': 'not found'}, 404)
                u = urllib.parse.urlparse(path)
                parts = [urllib.parse.unquote(x) for x in u.path.strip('/').split('/') if x]
                if parts[:1] != ['media'] or '..' in parts:
                    return self.send_json({'error': 'not found'}, 404)
                CTX.space = 'v'  # 电脑在私密空间里点的：按私密空间去找这个文件（只这一次请求）
                return self.media(parts[1:], dict(urllib.parse.parse_qsl(u.query)))
            return self.send_json({'error': 'not found'}, 404)
        if sp != 'v':  # 电脑：只在私密空间里有
            return self.send_json({'error': 'not found'}, 404)
        owner = vaultrc.key_of(cookie_val(self.headers.get('Cookie', ''), 'vault'))
        if p == ['arm'] and method == 'POST':
            return self.send_json(vaultrc.arm(owner, bool(self.jbody().get('on'))))
        if p == ['view']:
            return self.send_json(vaultrc.view(owner, q.get('ctl') == '1'))
        if p == ['queue']:
            return self.send_json(vaultrc.queue(owner))
        if p == ['cmd'] and method == 'POST':
            try:
                seq = vaultrc.send(owner, self.jbody())
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            if seq is None:
                return self.send_json({'error': '手机未在播放，或未开启控制'}, 409)
            return self.send_json({'seq': seq})
        return self.send_json({'error': 'not found'}, 404)

    def play_lib_api(self, method, p, q):
        if p in (['library'], ['images']):
            snap = lib_snapshot(bool(q.get('fresh')))  # 一次扫描两份列表 + 指纹（P05）
            items = snap['data'] if p == ['library'] else snap['images']
            if 'sig' not in q:
                return self.send_json(items)
            # 每 20 秒一次的“有没有新文件”：带上次的指纹来，没变就只回一句 same（以前每次都把整个音源库的列表传一遍，2026-11-08）
            sig = snap['sig'] if p == ['library'] else snap['isig']  # 扫描时算好的，不再每次请求序列化整个列表
            return self.send_json({'same': True, 'sig': sig} if q.get('sig') == sig else {'items': items, 'sig': sig})
        if p in (['reveal'], ['delete']) and method == 'POST':  # 播放页右键菜单：在资源管理器里打开 / 移到回收站（只限本机，手机上不行）
            b = self.jbody()
            try:
                path = lib_target(str(b.get('path') or ''), bool(b.get('dir')))
                if p == ['reveal']:
                    if space() == 'v':
                        raise RuntimeError('私密空间中不能在资源管理器中打开（资源管理器会记录文件夹和文件名）')
                    reveal(path, bool(b.get('dir')))
                else:
                    if path == lib_root():
                        raise RuntimeError('不能删除整个音源库')
                    if space() == 'v':
                        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
                    else:
                        to_recycle_bin(path)
                    _lib_cache.pop(lib_root(), None)
                return self.send_json({'ok': True})
            except (RuntimeError, OSError) as e:
                return self.send_json({'error': str(e)}, 400)
        if p == ['imginfo']:
            try:
                return self.send_json(image_info(lib_path(q.get('path') or '')))
            except (RuntimeError, OSError):
                return self.send_json({'error': '文件不存在'}, 404)
        if p == ['convert']:  # GET ?path= 看进度；POST {path} 开始转换
            try:
                rel = str(self.jbody().get('path', '')) if method == 'POST' else (q.get('path') or '')
                if method == 'POST':
                    conv_start(rel)
                return self.send_json(conv_status(rel))
            except RuntimeError as e:
                return self.send_json({'state': 'error', 'err': str(e), 'error': str(e)}, 404)
        if p == ['favs']:
            if method != 'POST':
                return self.send_json(read_json(favs_file(), []) or [])
            b = self.jbody(); key = str(b.get('key', ''))
            with lock:
                favs = [f for f in (read_json(favs_file(), []) or []) if f.get('key') != key]
                if b.get('on') and key:
                    favs.insert(0, {'key': key, 't': time.time()})
                write_json(favs_file(), favs)
            return self.send_json(favs)
        if p == ['recent']:
            key = str(self.jbody().get('key', '')) if method == 'POST' else ''
            if not key:
                return self.send_json(read_json(recent_file(), []) or [])
            with lock:
                rec = read_json(recent_file(), []) or []
                rec = ([{'key': key, 't': time.time()}] + [r for r in rec if r.get('key') != key])[:200]
                write_json(recent_file(), rec)
            return self.send_json(rec)
        if p == ['tags']:
            b = self.jbody() if method == 'POST' else {}
            key = str(b.get('key', ''))
            if not key:
                return self.send_json(read_json(tags_file(), {}) or {})
            t = [str(x).strip()[:24] for x in (b.get('tags') or []) if str(x).strip()]
            with lock:
                tags = read_json(tags_file(), {}) or {}
                if t:
                    tags[key] = list(dict.fromkeys(t))
                else:
                    tags.pop(key, None)
                write_json(tags_file(), tags)
            return self.send_json(tags)
        if p == ['order']:
            if method != 'POST':
                return self.send_json(read_json(order_file(), {}) or {})
            b = self.jbody(); grp = str(b.get('group', ''))[:300]
            names = [str(x)[:200] for x in (b.get('names') or [])][:2000]
            with lock:
                order = read_json(order_file(), {}) or {}
                if names:
                    order[grp] = list(dict.fromkeys(names))
                else:
                    order.pop(grp, None)
                write_json(order_file(), order)
            return self.send_json(order)
        if p == ['subsearch']:
            # 在已经生成过的字幕里找一句话：返回是哪个文件、第几秒
            q = (q.get('q') or '').strip().lower()
            out = []
            if q:
                keys = ['lib:' + x['path'] for x in scan_library()] + ['job:' + j.id for j in list(jobs.values()) if job_visible(j.id) and j.state == 'done']
                has_stt = any(getattr(j, 'space', 'n') == space() and getattr(j, 'has_subs', False) for j in stt.stt_jobs.values())
                for key in keys:
                    try:
                        audio, f = play_subs_target(key)
                    except Exception:
                        continue
                    if not os.path.isfile(f) and has_stt and key.startswith('lib:'):
                        f = stt_subs_for(audio) or f  # 播放页还没打开过、但语音转文字里转过的
                    if not os.path.isfile(f):
                        continue
                    for st in read_json(f, {}).get('sents', []):
                        if q in st.get('text', '').lower():
                            out.append({'key': key, 's': st['s'], 'text': st['text']})
                            if len(out) >= 300:
                                break
                    if len(out) >= 300:
                        break
            return self.send_json(out)
        self.send_json({'error': 'not found'}, 404)

    def play_api(self, method, p, q):
        """播放页字幕：GET 查状态 / 取字幕；POST 开始生成（后台进行，长音频要几十秒）。"""
        key = q.get('key', '')
        audio, out = play_subs_target(key)
        redo = method == 'POST' and q.get('redo') == '1'  # 重新生成（2026-11-17 用户：有些气声没转出来）：删掉现在的字幕和译文，重新识别
        if method == 'POST' and q.get('import') == '1':  # 载入字幕 / 歌词文件（2026-11-17 用户）：换掉现在的字幕，旧译文作废
            import base64, subimport
            b = self.jbody()
            try:
                raw = base64.b64decode(str(b.get('data') or ''), validate=True)
                sents = subimport.parse(str(b.get('name') or ''), raw)
            except (ValueError, TypeError) as e:
                return self.send_json({'error': str(e) or '字幕文件读不了'}, 400)
            if play_subs_state.get(out) == 'running':
                return self.send_json({'error': '正在识别字幕，完成后再载入'}, 409)
            with SUBS_LOCK:
                subs_drop_tr(out)
                write_json(out, {'sents': sents, 'language': None, 'source': 'import', 'file': os.path.basename(str(b.get('name') or ''))[:200]}, indent=0)
            play_subs_state.pop(out, None)
            act(f'播放页字幕：载入了字幕文件（{len(sents)} 句）', 'playsubs')
            return self.send_json({'state': 'done', 'sents': sents, 'language': None})
        if method == 'POST' and q.get('cancel') == '1':  # 取消：不再等这次的结果（引擎手上这一段会在后台做完，结果丢掉）
            if play_subs_state.get(out) == 'running':
                play_subs_state.pop(out, None); g = play_subs_prog.pop(out, None) or {}
                play_subs_prog[out] = {'gen': g.get('gen', 0) + 1, 'cancelled': True}
                act('播放页字幕：已取消', 'playsubs')
                return self.send_json({'state': 'none'})
            if os.path.isfile(out):  # 已经做完了（短音频几秒就好）：照实告诉前台
                d = read_json(out, {})
                return self.send_json({'state': 'done', 'sents': d.get('sents', []), 'language': d.get('language')})
            return self.send_json({'state': 'none'})
        if redo:  # 重新生成：旧字幕和译文先留着，新的做好了才换掉（以前先删，识别失败 / 取消 / 重启就什么都没了，审查 2）
            if play_subs_state.get(out) == 'running':
                return self.send_json({'state': 'running', 'p': play_subs_pct(out)})
            play_subs_state.pop(out, None)
        st0 = play_subs_state.get(out)
        if not redo and st0 == 'running':  # 正在（重新）识别：先报进度，不拿旧文件当结果
            return self.send_json({'state': 'running', 'p': play_subs_pct(out)})
        if not redo and st0 and st0.startswith('error:') and os.path.isfile(out):  # 重新识别失败了：报一次错，旧字幕还在
            play_subs_state.pop(out, None)
            return self.send_json({'state': 'error', 'error': st0[6:]})
        if key.startswith('lib:') and not redo and play_subs_state.get(out) != 'running':  # 重新生成时 / 正在识别时不拿语音转文字里的旧结果顶上
            f = stt_subs_for(audio)
            if f and (not os.path.isfile(out) or os.path.getmtime(f) > os.path.getmtime(out)):  # 没有字幕，或语音转文字里改过
                with SUBS_LOCK:  # 文字变了：旧的译文作废
                    shutil.copyfile(f, out)
                    subs_drop_tr(out)
                act('播放页字幕：使用语音转文字的结果', 'playsubs')
        if os.path.isfile(out) and not redo:
            d = read_json(out, {})
            return self.send_json({'state': 'done', 'sents': d.get('sents', []), 'language': d.get('language')})
        st = play_subs_state.get(out)
        if method == 'POST' and not (st and st == 'running'):
            play_subs_state[out] = 'running'
            sp, gen = space(), (play_subs_prog.get(out) or {}).get('gen', 0) + 1
            g = play_subs_prog[out] = {'gen': gen, 't0': time.time()}

            def work():
                CTX.space = sp
                part = out + f'.part{gen}.json'  # 先写到临时文件：取消了就丢掉，不会顶掉后来重新开始的那次
                try:
                    compute_subs(audio, part, 'playsubs', prog=g)
                    if (play_subs_prog.get(out) or {}).get('gen') == gen:
                        with SUBS_LOCK:  # 新字幕换上了：旧的译文作废
                            os.replace(part, out); subs_drop_tr(out)
                        play_subs_state.pop(out, None); play_subs_prog.pop(out, None)
                except Exception as e:
                    if (play_subs_prog.get(out) or {}).get('gen') == gen:
                        play_subs_state[out] = 'error:' + str(e); play_subs_prog.pop(out, None)
                finally:
                    try:
                        os.remove(part)
                    except OSError:
                        pass
            threading.Thread(target=work, daemon=True).start()
            return self.send_json({'state': 'running', 'p': play_subs_pct(out)})
        if st and st.startswith('error:'):
            return self.send_json({'state': 'error', 'error': st[6:]})
        return self.send_json({'state': 'running', 'p': play_subs_pct(out)} if st else {'state': 'none'})

    def play_translate(self, method, q):
        """字幕翻译：GET 查状态 / 取译文；POST 开始翻译（后台进行）。按“目标语言 + 原文语言”分别缓存。"""
        to, src, eng = q.get('to', 'zh-CN'), q.get('from', 'auto'), ('local' if q.get('engine') == 'local' else 'google')
        if eng == 'local' and not translate.local_available():
            return self.send_json({'state': 'error', 'error': '未安装本地翻译模型'})
        if not re.fullmatch(r'[A-Za-z-]{2,8}', to) or not re.fullmatch(r'[A-Za-z-]{2,8}', src):
            return self.send_json({'error': '语言代码不正确'}, 400)
        audio, out = play_subs_target(q.get('key', ''))
        if not os.path.isfile(out):
            return self.send_json({'state': 'error', 'error': '尚无字幕'})
        cache = out[:-5] + f'.tr-{to}-{src}' + ('-local' if eng == 'local' else '') + '.json'
        if os.path.isfile(cache):
            d = read_json(cache, {})
            return self.send_json({'state': 'done', 'lines': d.get('lines', []), 'src': d.get('src')})
        st = tr_state.get(cache, '')
        if method == 'POST' and not st.startswith('running'):
            tr_state[cache] = 'running:0/0'
            with SUBS_LOCK:  # 读字幕和记下是哪一版一起做
                sents = read_json(out, {}).get('sents', [])
                ver = os.path.getmtime(out)  # 这次翻译对的是哪一版字幕

            def work():
                try:
                    lines, det = translate.translate_lines([x['text'] for x in sents], to, src,
                                                           lambda a, b: tr_state.__setitem__(cache, f'running:{a}/{b}'), eng)
                    with SUBS_LOCK:  # 核对和写缓存一起做，中间字幕换不了（第二轮审查 4）
                        try:
                            same = os.path.getmtime(out) == ver
                        except OSError:
                            same = False
                        if same:  # 翻译期间字幕换过（导入 / 重新生成）：这份译文对不上了，不写（审查 3）
                            write_json(cache, {'lines': lines, 'src': det, 'to': to})
                    tr_state.pop(cache, None)
                except Exception as e:
                    tr_state[cache] = 'error:' + str(e)
            threading.Thread(target=work, daemon=True).start()
            return self.send_json({'state': 'running', 'done': 0, 'total': len(sents)})
        if st.startswith('error:'):
            tr_state.pop(cache, None)
            return self.send_json({'state': 'error', 'error': st[6:]})
        if st.startswith('running'):
            a, b = st[8:].split('/')
            return self.send_json({'state': 'running', 'done': int(a), 'total': int(b)})
        return self.send_json({'state': 'none'})

    def _dev_id(self):
        """这台设备：配对过的手机用它的 id，电脑本机是 'pc'"""
        if getattr(self, 'remote', False):
            d = remote.device_of(self.headers.get('Cookie', ''))
            return (d['id'], d.get('name') or '手机') if d else (None, None)
        return 'pc', '电脑'

    def _host(self):
        h = (self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or '').split(',')[0].strip().lower()
        return h[1:].split(']')[0] if h.startswith('[') else h.rsplit(':', 1)[0]

    def push_api(self, method, p):
        """手机推送：GET key 公钥 / GET status 这台订阅了没有 / POST subscribe / POST unsubscribe / GET last 最近一条（sw.js 收到推送后来取）"""
        dev, _ = self._dev_id()
        if p == ['key']:
            return self.send_json({'key': push.public_key()})
        if p == ['status']:
            return self.send_json({'on': bool(dev) and push.subscribed(dev)})
        if p == ['last']:
            return self.send_json(push.last())
        if not dev:
            return self.send_json({'error': '此设备尚未配对'}, 401)
        if p == ['subscribe'] and method == 'POST':
            try:
                push.subscribe(dev, self.jbody().get('sub'), self._host())
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            return self.send_json({'on': True})
        if p == ['unsubscribe'] and method == 'POST':
            push.unsubscribe(dev)
            return self.send_json({'on': False})
        if p == ['test'] and method == 'POST':
            push.SEEN.pop(dev, None)
            threading.Thread(target=push.notify, args=('Studio', '通知已开启：生成完成时会在这里提醒你', '/play'), daemon=True).start()
            return self.send_json({'ok': True})
        return self.send_json({'error': 'not found'}, 404)

    def remote_api(self, method, p):
        """手机访问的设置。配对（pair）是手机调的；其余只能在电脑上调。"""
        if p == ['pair'] and method == 'POST':
            b = self.jbody()
            tok, err = remote.pair(b.get('code', ''), b.get('name', ''))
            if not tok:
                return self.send_json({'error': err}, 400)
            act(f'手机访问：新设备“{b.get("name") or "手机"}”配对成功', 'remote', 'ok')
            return self.send_json({'ok': True}, headers={'Set-Cookie': f'dev={tok}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax'})
        if p == ['install'] and method == 'POST':  # 手机上“添加到主屏幕”
            dev = remote.device_of(self.headers.get('Cookie', '')) if getattr(self, 'remote', False) else None
            if not dev:
                return self.send_json({'error': '仅可在已配对的手机上添加到主屏幕'}, 400)
            return self.send_json({'token': remote.install_token(dev['id'])})
        if getattr(self, 'remote', False):
            return self.send_json({'error': 'not found'}, 404)
        d = remote.load()
        if method == 'POST' and not p:
            en = bool(self.jbody().get('enabled'))
            with remote.lock:  # 读-改-写拿着锁（以前不拿：同时配对 / 移除手机时会互相覆盖，2026-11-16 审查）
                d = remote.load(); d['enabled'] = en; remote.save(d)
        elif method == 'POST' and p == ['code']:
            code, ttl = remote.new_code()
            return self.send_json({'code': code, 'ttl': ttl})
        elif method == 'DELETE' and len(p) == 2 and p[0] == 'device':
            remote.remove_device(p[1]); d = remote.load()
        ts = remote.tailscale()
        ip = remote.listening()
        url = f'http://{ts["name"] or ip}:{PORT}' if ip and ts.get('name') else (f'http://{ip}:{PORT}' if ip else '')
        return self.send_json({'enabled': d['enabled'], 'listening': ip, 'url': url, 'ip_url': f'http://{ip}:{PORT}' if ip else '', 'tailscale': ts,
                               'devices': [{k: x[k] for k in ('id', 'name', 'created', 'last')} for x in d['devices']]})

    def vc_upload(self, q):
        """换声的原录音：任意音频/视频/网页录音 → 44.1kHz 单声道 16 位 WAV（引擎内部会再按模型需要重采样）。"""
        fname = urllib.parse.unquote(self.headers.get('X-Filename', 'upload.bin'))
        src = os.path.join(tmp_dir(), 'vcup_' + uuid.uuid4().hex[:10] + safe_ext(fname))
        try:
            digest = self.save_body(src)
        except RuntimeError:
            if os.path.exists(src):
                os.remove(src)
            raise
        name = 'vcsrc_' + uuid.uuid4().hex[:10] + '.wav'
        try:
            act(f'读取 {fname}，转成 44.1kHz 单声道 WAV', q.get('op', 'vc'))
            ffmpeg('-i', src, '-vn', '-ac', '1', '-ar', '44100', '-sample_fmt', 's16', os.path.join(tmp_dir(), name))
        finally:
            os.remove(src)
        sec = wav_seconds(os.path.join(tmp_dir(), name))
        if sec < 0.5:
            return self.send_json({'error': '音频过短或没有声音'}, 400)
        start_upload_subs(name, 'vcsubs', os.path.join(psubs_dir(), 'upload_' + digest + '.json'))  # 上传完就在后台生成带时间的字幕
        return self.send_json({'file': name, 'url': '/media/tmp/' + name, 'seconds': sec, 'filename': fname})

    def vc_subs(self, q):
        name = os.path.basename(q.get('file') or '')
        path = os.path.join(tmp_dir(), name + '.subs.json')
        if os.path.isfile(path):
            return self.send_json({'state': 'done', 'sents': read_json(path, {}).get('sents', [])})
        st = subs_state.get(name)
        if st and st.startswith('error:'):
            return self.send_json({'state': 'error', 'error': st[6:]})
        return self.send_json({'state': 'running' if st else 'none'})

    def prompt_api(self, method, p):
        """AI 助手：状态 / 预设（每个空间一份）/ 引擎设置 / 流式生成 / 停止引擎"""
        pf = os.path.join(DATA if space() == 'v' else PROMPT_DIR, 'prompt-presets.json')
        ef = os.path.join(PROMPT_DIR, 'prompt-engine.json')
        if len(p) == 2 and p[0] == 'traces' and method == 'GET':
            import prompttrace
            trace = prompttrace.load(os.path.join(os.path.dirname(pf), 'prompt-traces'), p[1])
            return self.send_json(trace) if trace else self.send_json({'error': '完整提示词记录不存在或已过期'}, 404)
        if p == ['status']:
            return self.send_json({'available': promptgen.available(), 'running': promptgen.Engine.running(), 'busy': promptgen.Engine.busy,
                                   'model': promptgen.MODEL_NAME, 'vision': promptgen.vision(), 'gen_defaults': promptgen.GEN_DEFAULTS, 'engine_defaults': promptgen.ENGINE_DEFAULTS,
                                   'kv_types': promptgen.KV_TYPES, 'engine': promptgen.clamp_engine(read_json(ef, {}) or {}), 'presets': promptgen.load_presets(pf),
                                   'recommended': promptgen.RECOMMENDED, 'ctx_choices': promptgen.CTX_CHOICES, 'ubatch_choices': promptgen.UBATCH_CHOICES,
                                   'default_presets': promptgen.DEFAULT_PRESETS})
        if p == ['presets'] and method == 'POST':
            try:
                return self.send_json(promptgen.save_presets(pf, self.jbody().get('presets') or [], write_json))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
        if p == ['engine'] and method == 'POST':
            cfg = promptgen.clamp_engine(self.jbody())
            write_json(ef, cfg)
            return self.send_json(cfg)
        if p == ['stop'] and method == 'POST':
            if promptgen.Engine.busy:
                return self.send_json({'error': '正在生成，完成后再停止'}, 409)
            promptgen.stop()
            return self.send_json({'ok': True})
        if p == ['preview'] and method == 'POST':
            import prompttrace
            b = self.jbody()
            presets = promptgen.load_presets(pf)
            pre = next((x for x in presets if x['id'] == b.get('preset')), None)
            system = str(b['system'])[:16000] if isinstance(b.get('system'), str) else (pre['system'] if pre else '')
            msgs = [m for m in (b.get('messages') or []) if isinstance(m, dict)]
            try:
                return self.send_json(prompttrace.chat_preview(promptgen.build_messages(msgs, system), b.get('prompt_input', '')))
            except (ValueError, TypeError, AttributeError):
                return self.send_json({'error': '请先输入需求，或检查消息格式'}, 400)
        if p == ['chat'] and method == 'POST':
            b = self.jbody()
            presets = promptgen.load_presets(pf)
            pre = next((x for x in presets if x['id'] == b.get('preset')), None)
            system = str(b['system'])[:16000] if isinstance(b.get('system'), str) else (pre['system'] if pre else '')
            msgs = [m for m in (b.get('messages') or []) if isinstance(m, dict)]
            params, cfg = promptgen.clamp_params(b.get('params')), promptgen.clamp_engine(read_json(ef, {}) or {})
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            gone = [False]
            try:
                self.connection.settimeout(60)
            except OSError:
                pass

            def out(d):
                if gone[0]:
                    return
                try:
                    self.wfile.write(('data: ' + json.dumps(d, ensure_ascii=False) + '\n\n').encode('utf-8')); self.wfile.flush()
                except OSError:
                    gone[0] = True  # 网页关了 / 不收了：停下
            gen = None
            if b.get('preset') in promptgen.PE_PRESETS:
                try:
                    last = next((m for m in reversed(msgs) if m.get('role') == 'user'), None)
                    if not last:
                        raise ValueError('请先写明您想要的内容')
                    imgs = [x for x in (last.get('images') if isinstance(last.get('images'), list) else [last.get('image')]) if isinstance(x, str) and x.startswith('data:image/')]
                    out({'type': 'start', 'loading': True})
                    out({'type': 'wait', 'v': '正在用官方增强小模型回答（单轮，不看之前的对话；首次需载入约 20~40 秒）…'})
                    t0 = time.time()
                    txt = imagegen.q21_pe_chat(promptgen.PE_PRESETS[b['preset']], system, str(last.get('content') or ''), imgs, space())
                    out({'type': 'text', 'v': imagegen.q21.parse_enhanced(txt)[0] if txt else '（小模型没有输出）'})  # 小模型多半输出 JSON：只显示其中的提示词（原文在后台记录里）
                    out({'type': 'done', 'v': {'seconds': round(time.time() - t0, 1), 'chunks': 1}})
                except Exception as e:
                    out({'type': 'error', 'v': str(e)[:500] or e.__class__.__name__})
                return
            try:
                import prompttrace
                trace = prompttrace.chat_preview(promptgen.build_messages(msgs, system), b.get('prompt_input', ''))
                try:
                    trace_id = prompttrace.save(os.path.join(os.path.dirname(pf), 'prompt-traces'), trace)
                    out({'type': 'prompt_trace', 'v': trace_id})
                except OSError:
                    act('完整提示词记录未能保存，本次生成继续', 'prompt', 'warn')
                out({'type': 'start', 'loading': not promptgen.Engine.running()})
                gen = promptgen.chat_stream(msgs, system, params, cfg, lambda: gone[0])
                for kind, val in gen:
                    out({'type': kind, 'v': val})
                    if gone[0]:
                        break
            except Exception as e:  # 模型中途退出、显存不够、参数不对……：告诉网页，不再写第二个 HTTP 响应
                msg = str(e) or e.__class__.__name__
                if isinstance(e, (ConnectionError, http.client.IncompleteRead)):
                    msg = '提示词模型中途退出（多半是显存不足），详情请见 studio/prompt-engine.log'
                out({'type': 'error', 'v': msg})
            finally:
                if gen is not None:
                    gen.close()
            return
        return self.send_json({'error': 'not found'}, 404)

    def frames_api(self, method, p, q):
        """视频截一帧 → 素材库（frames.py，2026-11-19 用户）。视频用 {mats: 素材库相对路径} 或 {gallery: 视频库 id} 指明；
        info：帧率 / 时长 / 截过的图 / 默认存放位置；grab：截一帧（save 时存进素材库，否则放临时文件夹拿来用）；save：网页自己取好的一帧；
        undo：删掉刚存的那张；src：图片 → 来源视频和秒数；thumb：缩略图条上的小图；tmp：临时文件"""
        sp = space(); tdir = os.path.join(VTMP if sp == 'v' else TMP, 'frames')
        root = os.path.abspath(MATS_DIR); rel = lambda x: os.path.relpath(x, root).replace('\\', '/')
        def src_of(b):
            if b.get('mats'):
                r = str(b['mats']).replace('\\', '/').strip('/'); path = mats_path(r)
                if not os.path.isfile(path):
                    raise ValueError('素材库中找不到这个视频')
                return {'mats': r}, path, mats_private(r), os.path.splitext(os.path.basename(path))[0]
            if b.get('gallery'):
                x = videogen.gallery_get(str(b['gallery']), sp)
                if not x:
                    raise ValueError('视频库中已找不到这段视频')
                path = videogen.vfile(sp, x['file'])
                if not os.path.isfile(path):
                    raise ValueError('这段视频的文件已经不在了')
                nm = re.sub(r'\s+', ' ', str(x.get('prompt') or '')).strip()[:30] or os.path.splitext(os.path.basename(path))[0]
                return {'gallery': str(b['gallery'])}, path, sp == 'v', nm
            raise ValueError('不知道是哪个视频')
        def dest_of(sv, priv):
            d = str((sv or {}).get('dir') or '').replace('\\', '/').strip('/')
            if not d:
                raise ValueError('请选择存放的文件夹')
            if d == 'gallery' or d.startswith('gallery/'):
                raise ValueError('不能存进 gallery（姿势 / 衣服 / 脸）')
            if priv and not mats_private(d):
                raise ValueError('这是私密的视频：截图只能存进私密文件夹')
            if mats_test_ro():
                raise ValueError('测试用的 Studio 不往真的素材库里写')
            ab = mats_path(d)
            os.makedirs(ab, exist_ok=True)
            return ab
        try:
            if p == ['info']:
                src, path, priv, name = src_of(q)
                pr = frames.probe(path); e = frames.items(frames.key_of(src)) or {}
                dest = frames.default_dest(src, sp == 'v')
                return self.send_json({'fps': pr['fps'], 'dur': pr['dur'], 'w': pr['w'], 'h': pr['h'], 'name': name, 'private': priv,
                                       'items': [x for x in e.get('items') or [] if not mats_hide(x['rel'])], 'album': e.get('album'),
                                       'dest': dest, 'dest_exists': os.path.isdir(os.path.join(root, *dest.split('/')))})
            if p == ['grab'] and method == 'POST':
                b = self.jbody(); src, path, priv, name = src_of(b.get('src') or {})
                pr = frames.probe(path); t = frames.snap(b.get('t') or 0, pr['fps'], pr['dur']); key = frames.key_of(src)
                if not b.get('save'):  # 只拿来用（生图原图、参考图……）：临时文件
                    out = os.path.join(tdir, hashlib.sha1(f'{key}|{pr["size"]}|{t}'.encode()).hexdigest()[:16] + '.png')
                    if not os.path.isfile(out):
                        frames.grab(path, t, out, pr['fps'])
                    return self.send_json({'ok': True, 't': t, 'url': '/api/frames/tmp?f=' + os.path.basename(out), 'name': f'{frames.safe_name(name, 60)}_{frames.stamp(t)}.png'})
                d0 = frames.dup(key, t, 0.5 / pr['fps'] if pr.get('fps') else 0.02)  # 半帧以内才算同一帧（审查 11）
                if d0 and not mats_hide(d0['rel']) and not b.get('force'):  # force：换位置时先存新的再撤旧的
                    return self.send_json({'ok': True, 'dup': True, 'rel': d0['rel'], 't': d0['t']})
                sv = b['save']; dab = dest_of(sv, priv); album = None
                if sv.get('album', True):
                    prev = (frames.items(key, prune=False) or {}).get('album')  # 这个视频已经有图集（可能改过名）：接着放
                    pa = mats_path(prev) if prev else None
                    dab = pa if pa and os.path.isdir(pa) and os.path.dirname(pa) == os.path.normpath(dab) else frames.album_dir(dab, name, src)
                    os.makedirs(dab, exist_ok=True); frames.write_album(dab, src, name); album = rel(dab)
                out = frames.free_path(dab, frames.safe_name(name, 60) + '_' + frames.stamp(t) + '.png')
                frames.grab(path, t, out, pr['fps'])
                r = rel(out); frames.add(src, {**pr, 'name': name}, r, t, album); MATS_GEN[0] += 1
                return self.send_json({'ok': True, 'rel': r, 't': t, 'album': album, 'n': len((frames.items(key) or {}).get('items') or [])})
            if p == ['save'] and method == 'POST':  # 网页自己取的一帧（后台读不到原文件的视频）：{data, name, dir, album}
                b = self.jbody(); data = str(b.get('data') or '')
                raw = base64.b64decode(data.split(',', 1)[1] if data.startswith('data:') else data)
                if not raw:
                    raise ValueError('没有图片')
                name = frames.safe_name(b.get('name') or '视频'); dab = dest_of(b, bool(b.get('private')) or sp == 'v')  # 私密空间里的视频：只能存进私密文件夹
                if b.get('album', True):
                    dab = frames.album_dir(dab, name); os.makedirs(dab, exist_ok=True); frames.write_album(dab, {}, name)
                out = frames.free_path(dab, name[:60] + '_' + frames.stamp(float(b.get('t') or 0)) + '.png')
                with open(out, 'wb') as f:
                    f.write(raw)
                MATS_GEN[0] += 1
                FR_LOCAL.add(rel(out))  # 网页取的帧没有进截图索引：记一下，撤销时认得（审查 13）
                return self.send_json({'ok': True, 'rel': rel(out)})
            if p == ['undo'] and method == 'POST':
                r = str(self.jbody().get('rel') or '').strip('/')
                if mats_test_ro():  # 测试 Studio 读的是真的素材库：撤销也不动（第二轮审查 3）
                    raise ValueError('测试用的 Studio 不改动真的素材库')
                if r not in frames.by_image() and r not in FR_LOCAL:
                    raise ValueError('只能撤销刚截的图')
                ab = mats_path(r); to_recycle_bin(ab); frames.remove_image(r); FR_LOCAL.discard(r); MATS_GEN[0] += 1
                d = os.path.dirname(ab)  # 图集里一张都不剩了：图集也删掉
                try:
                    if os.path.isfile(os.path.join(d, frames.POST)) and not [e for e in os.scandir(d) if e.is_file() and not e.name.startswith('.')]:
                        to_recycle_bin(d)
                except OSError:
                    pass
                return self.send_json({'ok': True})
            if p == ['src']:
                r = str(q.get('rel') or '').strip('/'); mats_path(r)  # 当前空间看不到的图：当它不存在
                hit = frames.by_image().get(r)
                if not hit:
                    return self.send_json({'src': None})
                _, t, src = hit; src = src or {}; ok = False
                try:
                    ok = os.path.isfile(mats_path(src['mats'])) if src.get('mats') else bool(src.get('gallery') and videogen.gallery_get(src['gallery'], sp))
                except ValueError:
                    ok = False
                return self.send_json({'src': src, 't': t, 'exists': ok})
            if p == ['thumb']:
                src, path, priv, _ = src_of(q); t = float(q.get('t') or 0)
                out = os.path.join(tdir, 'th', frames.thumb_key(path, t) + '.jpg')
                frames.thumb(path, t, out)
                return self.send_file(out, cache='no-store' if priv or sp == 'v' else 'public, max-age=86400')  # 私密的不让浏览器缓存（审查 14）
            if p == ['tmp']:
                f = os.path.basename(str(q.get('f') or ''))
                return self.send_file(os.path.join(tdir, f))
        except (ValueError, RuntimeError, OSError, KeyError) as e:
            return self.send_json({'error': str(e)}, 400)
        return self.send_json({'error': 'not found'}, 404)

    def civitai_api(self, method, p, q):
        """Civitai：密钥（只告诉网页有没有存）、搜索、下载、下载进度"""
        try:
            if p == ['key']:
                if method == 'POST':
                    civitai.set_key(self.jbody().get('key'))
                return self.send_json({'key': bool(civitai.key())})
            if p == ['search']:
                return self.send_json(civitai.search(q.get('q', ''), q.get('target', 'h3'), q.get('sort', 'downloads'), q.get('cursor', '')))
            if p == ['download'] and method == 'POST':
                b = self.jbody()
                return self.send_json(civitai.download(b.get('version'), b.get('target'), b.get('file'), {'model': b.get('model'), 'weight': b.get('weight'), 'creator': b.get('creator')}))
            if p == ['downloads']:
                return self.send_json(civitai.list_downloads())
            if p == ['installed']:
                return self.send_json(sorted(civitai.installed(q.get('target', 'h3'))))
            if p == ['mine']:  # 我的下载：这个模型的全部 LoRA（软件自己在用的标上用在哪，网页里收在下面）
                bi = builtin_loras()
                return self.send_json([{**r, 'builtin': bi.get(r['file'])} for r in civitai.mine(q.get('target', 'h3'))])
            if p == ['model']:  # 我的下载 → 详情
                return self.send_json(civitai.model(q.get('id'), q.get('target', 'h3'), q.get('version')))
            if p == ['identify'] and method == 'POST':  # 没有记录的 LoRA：按文件指纹去 Civitai 查
                b = self.jbody()
                try:
                    return self.send_json(civitai.identify(b.get('target'), b.get('file')))
                except urllib.error.URLError as e:
                    return self.send_json({'error': '无法连接 Civitai：' + str(getattr(e, 'reason', e))[:160]}, 502)
            if p == ['translate'] and method == 'POST':
                try:
                    return self.send_json({'texts': civitai.translate(self.jbody().get('texts'))})
                except Exception as e:
                    return self.send_json({'error': '翻译失败（无法连接 Google 翻译）：' + str(getattr(e, 'reason', e))[:160]}, 502)
        except ValueError as e:
            return self.send_json({'error': str(e)}, 400)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return self.send_json({'error': '无法连接 Civitai：' + str(getattr(e, 'reason', e))[:200]}, 502)
        return self.send_json({'error': 'not found'}, 404)

    def video_api(self, method, p, q):
        """生视频：状态 / 提交 / 进度 / 取消 / 视频库 / 打开 ComfyUI 原界面。"""
        sp = space()
        if p == ['edit-templates'] and method == 'POST':  # “填入模板”菜单：当前任务的全部模板（2026-11-08；videoedit 在文件开头已导入，这里不能再 import，否则整个函数里它都成了局部变量）
            b = self.jbody(); e = b.get('edit') if isinstance(b.get('edit'), dict) else {}
            return self.send_json({'items': videoedit.fill_templates(e, str(b.get('prompt') or '')[:4000], bool(b.get('has_ref')))})
        if p == ['orig-templates']:  # 设置页“原始提示词模板”：laowang 用的工作流自带的提示词（studio/orig_prompts.json）
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orig_prompts.json'), encoding='utf-8') as f:
                    return self.send_json({'items': json.load(f)})
            except (OSError, ValueError):
                return self.send_json({'items': []})
        if p == ['prompt-preview'] and method == 'POST':
            import prompttrace
            try:
                return self.send_json(prompttrace.video_preview(self.jbody()))
            except (ValueError, TypeError, AttributeError):
                return self.send_json({'error': '提示词选项格式有误'}, 400)
        if p == ['status']:
            smp, sch = videogen.sampler_options()
            return self.send_json({'models': [{'key': k, 'name': m['name'], 'base': m['base'], 'tag': m['tag'], 'speed': m['speed'], 'desc': m['desc'], 'fps': m['fps'],
                                               'audio': m['audio'], 'defaults': m['defaults'], 'missing': videogen.missing(k),
                                               'tune': videogen.TUNE[k], 'flf': True, 'max_seconds': videogen.MAX_SECONDS[k], 'res_step': videogen.RES_STEP[k]}
                                              for k, m in videogen.MODELS.items()], 'engine': videogen.Engine.alive(), 'sizes': list(videogen.SIZES),
                                   'samplers': smp, 'schedulers': sch, 'upscaler': videogen.upscaler_ok(), 'seedvr': videogen.seedvr_ok(), 'interp': videogen.interp_ok(), 'lora_meta': civitai.meta_for(os.path.join(videogen.MODELS_DIR, 'loras')), 'loras': videogen.lora_files(),
                                   'lora_kind': {f: videogen.lora_kind(f) for f in videogen.lora_files()}, 'edit': videoedit.status(),
                                   'official': videogen.official_ok(), 'official_steps': videogen.OFFICIAL_STEPS, 'turbo': videogen.turbo_list(), 'engines': h3methods.status(), 'h3max': h3extra.MAX,
                                   'mats': os.path.isdir(MATS_DIR)})
        if p == ['jobs']:
            if method == 'POST':
                b = self.jbody()
                try:
                    b = mats_inline(b)  # 从素材库选的素材：读成 data URL
                    if isinstance(b.get('init'), dict) and b['init'].get('gallery'):
                        b['src_id'] = str(b['init']['gallery'])
                    if b.get('edit'):  # 改视频：原视频（上传的，或视频库里的一段）+ 人物图 / 衣服图（可选）
                        v, vid = b.get('video') if isinstance(b.get('video'), dict) else {}, None
                        if v.get('gallery'):
                            x = videogen.gallery_get(str(v['gallery']), sp)
                            if not x:
                                raise ValueError('视频库中已找不到原视频')
                            b['src_vid'] = x['id']
                            with open(videogen.vfile(sp, x['file']), 'rb') as f:
                                vid = f.read()
                        elif isinstance(v.get('data'), str):
                            d = v['data'].split(',', 1)[1] if v['data'].startswith('data:') else v['data']
                            if len(d) > 96_000_000:
                                raise ValueError('原视频过大（上限约 70MB，请先剪短）')
                            vid = base64.b64decode(d)
                        img = base64.b64decode(imagegen._image_b64(b['init'], sp, '人物图')) if b.get('init') else None
                        return self.send_json(videogen.submit(b, img, ffmpeg, None, vid))
                    extra = None
                    if b.get('model') == 'h3' and isinstance(b.get('h3x'), dict):  # H3 的更多条件：关键帧、开头片段、指定声音、参考图 / 视频 / 音频
                        hx = b['h3x']
                        def vbytes(v, what):  # 视频：{gallery: 视频库 id} 或 {data: data URL}
                            v = v if isinstance(v, dict) else {}
                            if v.get('gallery'):
                                g = videogen.gallery_get(str(v['gallery']), sp)
                                if not g:
                                    raise ValueError(what + '在视频库中已找不到')
                                with open(videogen.vfile(sp, g['file']), 'rb') as f:
                                    return f.read()
                            if isinstance(v.get('data'), str):
                                d = v['data'].split(',', 1)[1] if v['data'].startswith('data:') else v['data']
                                return base64.b64decode(d)
                            return None
                        def abytes(a):  # 声音：{data: data URL}
                            d = (a or {}).get('data') if isinstance(a, dict) else None
                            return base64.b64decode(d.split(',', 1)[1] if d.startswith('data:') else d) if isinstance(d, str) and d else None
                        im = lambda x, what: base64.b64decode(imagegen._image_b64(x, sp, what))
                        extra = h3extra.parse({
                            'keys': [(k.get('t') or 0, im(k.get('img'), '关键帧')) for k in (hx.get('keys') or []) if isinstance(k, dict) and k.get('img')],
                            'clip': {**hx['clip'], 'vid': vbytes(hx['clip'].get('video'), '开头片段')} if isinstance(hx.get('clip'), dict) else None,
                            'guide': {'vid': vbytes(hx['guide'].get('video'), '引导视频'), 'audio': hx['guide'].get('audio')} if isinstance(hx.get('guide'), dict) else None,
                            'audio': {'data': abytes(hx['audio']), 'start': hx['audio'].get('start')} if isinstance(hx.get('audio'), dict) else None,
                            'refs': [im(r, '参考图') for r in (hx.get('refs') or [])[:h3extra.MAX['refs']]],
                            'rvids': [vbytes(r, '参考视频') for r in (hx.get('rvids') or [])[:h3extra.MAX['rvids']]],
                            'rvid_audio': [(r or {}).get('audio') if isinstance(r, dict) else None for r in (hx.get('rvids') or [])[:h3extra.MAX['rvids']]],
                            'raudios': [abytes(r) for r in (hx.get('raudios') or [])[:h3extra.MAX['raudios']]]})
                    if b.get('model') == 'h3' and not b.get('init'):  # H3 可以没有首帧：只按文字（和参考）生成
                        return self.send_json(videogen.submit(b, None, ffmpeg, base64.b64decode(imagegen._image_b64(b['end'], sp, '尾帧图片')) if b.get('end') else None, None, extra))
                    img = base64.b64decode(imagegen._image_b64(b.get('init'), sp, '首帧图片'))
                    end = None
                    if b.get('end'):  # 尾帧（可选）：和首帧一样，{gallery: 图库 id} 或 {data: data URL}
                        if isinstance(b['end'], dict) and b['end'].get('gallery'):
                            b['end_id'] = str(b['end']['gallery'])
                        end = base64.b64decode(imagegen._image_b64(b['end'], sp, '尾帧图片'))
                    return self.send_json(videogen.submit(b, img, ffmpeg, end, None, extra))
                except (ValueError, TypeError, OverflowError) as e:
                    return self.send_json({'error': str(e) if isinstance(e, ValueError) else '参数格式有误'}, 400)
            return self.send_json(videogen.list_jobs(sp))
        if len(p) == 2 and p[0] == 'lastframe':  # 续接：这段视频的最后一帧（当作下一段的首帧）
            try:
                return self.send_json(videogen.last_frame(p[1], sp, ffmpeg))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 404)
        if len(p) == 3 and p[0] == 'jobs' and p[2] == 'prep':  # 只准备的那一单：Qwen 换好的图 + 看图写准确的名字（2026-11-10）
            r = videogen.prep_result(p[1], sp)
            return self.send_json(r) if r else self.send_json({'error': '没有准备好的结果'}, 404)
        if len(p) == 3 and p[0] == 'jobs' and p[2] == 'cancel' and method == 'POST':
            videogen.cancel(p[1], sp)
            return self.send_json({'ok': True})
        if p == ['translate'] and method == 'POST':  # 提示词翻成英文：{text, lang} → {text, cached}；锁住的内容对不上时 {error, fallback}
            b = self.jbody(); txt = str(b.get('text') or '')[:12000]
            try:
                out, cached = ptrans.translate(txt, 'en' if b.get('lang') == 'en' else 'zh')
            except ValueError as e:
                return self.send_json({'error': str(e), 'fallback': True})
            except Exception as e:
                return self.send_json({'error': '翻译失败：' + str(e), 'fallback': True})
            return self.send_json({'text': out, 'cached': cached})
        if p == ['gallery']:
            try:  # 老的视频库先整理一次文件（辅助文件挪进 _辅助文件、重复的原视频只留一份，2026-11-06）
                videogen.ensure_layout(sp)
            except Exception as e:
                print('[视频库整理] 失败：', e, flush=True)
            try:  # 引擎做完了、但没收进视频库的成品（以前被误判失败的）：后台找回，做完下一次刷新就有（2026-11-12，见 videogen.adopt_orphans）
                videogen.adopt_orphans(sp)
            except Exception:
                pass
            try:  # 每条带上视频组 grp（同一个原视频；以前的条目第一次补算，见 videogen.ensure_groups）
                g = videogen.ensure_groups(sp)
            except Exception:
                g = videogen.gallery(sp)
            try:  # 最近 20 段：后台先做好播放副本（点开时拖动进度条就不卡）
                vf = lambda f: videogen.vfile(sp, f)
                scrub_queue([(vf(f), True) for x in g[:20] for f in (x.get('file'), x.get('src_file'))
                             if f and os.path.isfile(vf(f)) and not os.path.isfile(videogen.scrub_file(vf(f))) and not videogen.seekable(vf(f))])
                # 告诉网页哪些播放副本已经做好：没做好的直接放原文件。以前同一个 ?scrub 地址先给原文件、做好后又给副本，
                # 播放到一半后面的数据来自另一个文件，视频就卡住不往下播（2026-11-05 新拼接的视频播一半停住）
                def ok(f):
                    try:
                        a = vf(f)
                        if videogen.seekable(a):  # 本身就能流畅拖动：当作“副本已好”（网页照样用 ?scrub 地址，后台给原文件）
                            return True
                        return os.path.getmtime(videogen.scrub_file(a)) >= os.path.getmtime(a)
                    except OSError:
                        return False
                g = [{**x, 'scrub': [f for f in (x.get('file'), x.get('src_file')) if f and ok(f)]} for x in g]
            except Exception:
                pass
            return self.send_json(g)
        if p == ['gallery', 'delete'] and method == 'POST':
            ids = self.jbody().get('ids')
            if not isinstance(ids, list):
                return self.send_json({'error': '请指定要删除的视频'}, 400)
            try:
                videogen.gallery_delete({str(x) for x in ids}, sp)
            except (videogen.IndexUnreadable, RuntimeError) as e:  # 索引读不出：什么都没删；有的文件删不掉：那几条留着（第二轮审查 9）
                return self.send_json({'error': str(e)}, 409)
            return self.send_json({'ok': True})
        if p == ['lag'] and method == 'POST':  # 改视频成品比原视频早 / 晚几帧（滑动对比对齐用；没量过就现在量）
            return self.send_json({'lag': videogen.ensure_lag(str(self.jbody().get('id') or ''), sp)})
        if p == ['cut'] and method == 'POST':  # 修剪：去掉几段，剩下的接成新视频（视频库里的用 id，别的传视频内容）
            b = self.jbody()
            try:
                data = None
                if not b.get('id') and b.get('data'):
                    raw = str(b['data']); data = base64.b64decode(raw.split(',', 1)[1] if raw.startswith('data:') else raw)
                cuts = [(float(x[0]), float(x[1])) for x in (b.get('cuts') or [])][:200]
                return self.send_json(videogen.cut_video(sp, cuts, str(b.get('id') or '') or None, data, b.get('name') or ''))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            except RuntimeError as e:
                return self.send_json({'error': str(e)}, 500)
        if p == ['cutpoints', 'calm'] and method == 'POST':  # 剪辑里正在播放：后台提前分析先停一停（cutpoints.calm）
            import cutpoints
            self.jbody(); cutpoints.calm()
            return self.send_json({'ok': True})
        if p == ['cutpoints'] and method == 'POST':  # 找适合换装 / 拼接的时间点：鼓点 + 动作（只用 CPU，见 cutpoints.py）
            import cutpoints
            b = self.jbody(); v, tmp = b.get('video') if isinstance(b.get('video'), dict) else {}, None
            try:
                if v.get('gallery'):
                    x = videogen.gallery_get(str(v['gallery']), sp)
                    if not x:
                        raise ValueError('视频库中已找不到这段视频')
                    path = videogen.vfile(sp, x['file'])
                elif v.get('mats'):
                    path = mats_path(v['mats'])
                    if not os.path.isfile(path):
                        raise ValueError('素材库中找不到该文件：' + str(v['mats']))
                elif isinstance(v.get('data'), str):
                    d = v['data'].split(',', 1)[1] if v['data'].startswith('data:') else v['data']
                    tmp = path = os.path.join(VTMP if sp == 'v' else TMP, 'cp_' + uuid.uuid4().hex[:8] + '.mp4')
                    with open(tmp, 'wb') as f:
                        f.write(base64.b64decode(d))
                else:
                    raise ValueError('请先放入原视频')
                if b.get('hurry'):  # 后台正在算、用户点了按钮：让它换成全速（结果由后台那次请求带回）
                    return self.send_json({'hurry': cutpoints.hurry(path)})
                return self.send_json(cutpoints.analyze(path, videogen.FFMPEG, videogen._probe, os.path.join(VTMP if sp == 'v' else TMP, 'cutpoints'), bool(b.get('bg')), lambda: not busy_work()))  # 有生成 / 配音等任务时不用显卡
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            except Exception as e:
                return self.send_json({'error': '分析失败：' + str(e)}, 500)
            finally:
                if tmp:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        if p in (['cutpoints', 'split'], ['segpref']):  # 2026-11-14 推荐分段（segpref.split，按用户自己的选段学偏好）/ 记下这次的选段
            import cutpoints, segpref
            fn = SEGPREF_V if sp == 'v' else SEGPREF_N
            if method != 'POST':
                st = segpref.status(fn)
                return self.send_json({k: v for k, v in st.items() if k != 'model'})
            b = self.jbody(); v = b.get('video') if isinstance(b.get('video'), dict) else {}
            if v.get('gallery'):
                x = videogen.gallery_get(str(v['gallery']), sp); path = videogen.vfile(sp, x['file']) if x else ''
            elif v.get('mats'):
                path = mats_path(v['mats'])
            else:
                path = ''
            if not path or not os.path.isfile(path):
                return self.send_json({'error': '找不到这段视频（只支持素材库 / 视频库里的视频）'}, 400)
            cp = cutpoints.cached(path, os.path.join(VTMP if sp == 'v' else TMP, 'cutpoints'))
            if not cp:
                return self.send_json({'error': '请先点“找换装点”'}, 400)
            if p == ['segpref']:
                segs = [s for s in (b.get('segs') or []) if isinstance(s, (list, tuple)) and len(s) == 2]
                ok = segpref.record(fn, {**cp, '_key': cutpoints._key(path)}, [[float(a), float(c)] for a, c in segs], b.get('rec'), {'task': str(b.get('task') or '')[:20]})
                return self.send_json({'ok': ok, 'videos': segpref.status(fn).get('videos', 0)})
            st = segpref.status(fn)
            segs = segpref.split(cp, float(b.get('dur') or cp.get('dur') or 0), st.get('model') if st.get('use') == 'learned' else None)
            return self.send_json({'segs': segs, 'by': st.get('use'), **{k: st[k] for k in ('videos', 'rule', 'learned', 'need') if k in st}})
        if p == ['redo', 'prompt']:  # 重新生成前：提示词框里先放当时的提示词
            return self.send_json(videogen.redo_prompt(str(q.get('id') or ''), sp))
        if p == ['redo'] and method == 'POST':  # 重新生成：同样的原视频、片段和设置再排一次（新的随机种子）；body.prompt：改过的提示词（可选）
            try:
                jb = self.jbody()
                b, img, vid = videogen.redo_input(str(jb.get('id') or ''), sp, jb.get('prompt') if isinstance(jb.get('prompt'), str) else None, jb.get('tpl') if isinstance(jb.get('tpl'), bool) else None)
                return self.send_json(videogen.submit(b, img, ffmpeg, None, vid))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            except RuntimeError as e:
                return self.send_json({'error': str(e)}, 500)
        if p == ['splice', 'group']:  # 和这段用同一个原视频的其他成品（多段拼接时一起选）
            return self.send_json(videogen.splice_group(str(q.get('id') or ''), sp))
        if p == ['qc', 'run'] and method == 'POST':  # 2026-11-14：现在就查一条（Agent 用；按任务号或视频库编号），返回 flags + 数字小结 m
            b = self.jbody(); iid = str(b.get('id') or '')
            if not iid and b.get('job'):
                iid = next((x.get('id') for x in videogen.gallery(sp) if x.get('job') == str(b['job'])), '')
            x = videogen.gallery_get(iid, sp) if iid else None
            if not x:
                return self.send_json({'error': '视频库里找不到这条（任务还没做完？）'}, 404)
            e = x.get('edit') or {}
            r = videogen.qc_run(sp, iid)
            return self.send_json({**(r or {}), 'task': e.get('task')})
        if p == ['qc']:  # 自动质检开关（设置页；默认关）
            if method == 'POST':
                videogen.qc_set(self.jbody().get('on') is True)
            return self.send_json({'on': videogen.qc_on()})
        if p == ['post'] and method == 'POST':  # 已经生成好的视频再做超分 / 插帧（排进视频队列，存成新的一条）
            try:
                b = self.jbody()
                col = b.get('color') if isinstance(b.get('color'), dict) else None
                if col and isinstance(col.get('ref'), str):  # 参考图：data URL → 字节
                    col = {**col, 'ref': base64.b64decode(imagegen._image_b64({'data': col['ref']}, sp, '参考图'))}
                return self.send_json(videogen.submit_post(str(b.get('id') or ''), sp, b.get('up'), b.get('ix'), ffmpeg, b.get('by'), col))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
        if p == ['splice'] and method == 'POST':  # 改视频的成品拼回原视频（ids：一起拼的几段）
            try:
                b = self.jbody()
                return self.send_json(videogen.splice(str(b.get('id') or ''), sp, [str(x) for x in (b.get('ids') or [])][:20]))
            except ValueError as e:
                return self.send_json({'error': str(e)}, 400)
            except RuntimeError as e:
                return self.send_json({'error': str(e)}, 500)
        if p == ['timeline', 'export'] and method == 'POST':  # 时间线：按顺序拼成一段完整的视频
            b = self.jbody()
            try:
                ids = [str(x) for x in (b.get('ids') or [])]
                return self.send_json(videogen.export_timeline(ids, sp, ffmpeg, b.get('xfade') or 0))
            except (ValueError, TypeError) as e:
                return self.send_json({'error': str(e)}, 400)
            except RuntimeError as e:
                return self.send_json({'error': str(e)}, 500)
        if p == ['comfy'] and method == 'POST':  # 设置里“打开 ComfyUI 原界面”：只在这台电脑上
            if getattr(self, 'remote', False):
                return self.send_json({'error': 'ComfyUI 原界面只能在电脑上打开'}, 403)
            videogen.Engine.ensure()
            return self.send_json({'url': f'http://127.0.0.1:{videogen.PORT}/'})
        return self.send_json({'error': 'not found'}, 404)

    def img_api(self, method, p, q):
        sp = space()
        if p == ['by-hash']:  # 上传的图是不是图库里生成过的：是就给它的提示词（视频页“生图提示词”）
            try:
                x = imagegen.find_by_hash(int(q.get('size') or 0), str(q.get('sha') or '').lower()[:40], sp)
            except (ValueError, OSError):
                x = None
            return self.send_json({'id': x['id'], 'prompt': x.get('prompt') or ''} if x else {})
        if p == ['prompt-preview'] and method == 'POST':
            import prompttrace
            return self.send_json(prompttrace.image_preview(self.jbody()))
        if p == ['status']:
            return self.send_json({'models': [{'key': k, 'name': m['name'], 'desc': m['desc'], 'missing': imagegen.missing_files(k), 'base': m.get('base', ''), 'speed': m.get('speed', ''),
                                               'tag': m.get('tag', ''), 'gb': imagegen.model_gb(k), 'edit': bool(m.get('edit')), 'cn': imagegen.controlnet_ok(k),
                                               'comfy': imagegen.comfy(k), 'modes': m.get('modes'), 'refine': bool(m.get('refine'))} for k, m in imagegen.MODELS.items()],
                                   'refine_missing': imagegen.q21.refine_missing(),  # 二采（Krea 2 润色）缺的文件：空 = 能用
                                   # ComfyUI 跑的几个模型：每种用法的推荐设置（网页上显示成默认值，用户可以改，见 q21.apply_over）+ 能选的采样器 / 调度器
                                   'q_settings': {k: {m: {x: v for x, v in s.items() if x in ('steps', 'cfg', 'sampler', 'scheduler', 'mp')} for m, s in imagegen.q21.SETTINGS[k].items()}
                                                  for k in imagegen.q21.SETTINGS},
                                   'q_samplers': imagegen.q21.Q_SAMPLERS, 'q_schedulers': imagegen.q21.Q_SCHEDULERS,
                                   # Qwen 2.1 的官方提示词增强模型在不在（不在时网页不显示增强开关）
                                   'q21_pe': {kd: imagegen.q21.pe_ok(kd) for kd in ('i2i', 't2i')},
                                   'q21_pose': fisher.available() and imagegen.q21.pose_ok(),  # 3D 人偶摆姿势（Fisher 编辑器 + PoseStudio LoRA）
                                   'engine': imagegen.Engine.model if imagegen.Engine.running() else None, 'defaults': imagegen.DEFAULTS,
                                   'model_defaults': {k: imagegen.model_defaults(k) for k in imagegen.MODELS},
                                   'default_model': imagegen.default_model(), 'caps': imagegen.capabilities()})
        if p == ['sam'] and method == 'POST':  # 局部重画的「智能选取」：在原图上点一下，SAM3 选出那一块（2026-11-16）
            try:
                return self.send_json(imagegen.sam_select(self.jbody(), sp))
            except (ValueError, TypeError) as e:
                return self.send_json({'error': str(e)}, 400)
            except Exception as e:
                return self.send_json({'error': str(e)[:500]}, 500)
        if p == ['q21-enhance'] and method == 'POST':  # Qwen 2.1 的“先增强”：只增强，把结果交回网页填进提示词框
            try:
                return self.send_json(imagegen.q21_preview(self.jbody(), sp))
            except (ValueError, TypeError) as e:
                return self.send_json({'error': str(e)}, 400)
            except Exception as e:
                return self.send_json({'error': str(e)[:500]}, 500)
        if p == ['q21-log']:  # 提示词增强的后台记录（AI 助手页的“后台记录”）：按空间分开
            if method == 'POST':
                b = self.jbody()
                imagegen.q21.clear_log(sp, str(b.get('id') or '') or None)
                return self.send_json({'ok': True})
            return self.send_json({'items': imagegen.q21.read_log(sp)})
        if p == ['jobs']:
            if method == 'POST':
                try:
                    return self.send_json(imagegen.submit(self.jbody(), sp))
                except (ValueError, TypeError, OverflowError, AttributeError) as e:
                    return self.send_json({'error': str(e) if isinstance(e, ValueError) else '参数格式有误'}, 400)
            return self.send_json(imagegen.list_jobs(sp))
        if len(p) == 2 and p[0] == 'jobs':
            j = imagegen.jobs.get(p[1])
            if not j or j['space'] != sp:
                return self.send_json({'error': '任务不存在'}, 404)
            return self.send_json(imagegen.public(j, full=True))
        if len(p) == 3 and p[0] == 'jobs' and p[2] == 'cancel' and method == 'POST':
            r = imagegen.cancel(p[1], sp)
            return self.send_json(r) if r else self.send_json({'error': '任务不存在'}, 404)
        if p == ['gallery']:
            return self.send_json(imagegen.gallery(sp))
        if p == ['gallery', 'delete'] and method == 'POST':
            ids = self.jbody().get('ids')
            if not isinstance(ids, list):
                return self.send_json({'error': '请指定要删除的图片'}, 400)
            try:
                imagegen.gallery_delete([str(x) for x in ids], sp)
            except RuntimeError as e:  # 有的文件删不掉：那几张留在图库里（第二轮审查 9）
                return self.send_json({'error': str(e)}, 409)
            return self.send_json({'ok': True})
        if len(p) == 3 and p[0] == 'gallery' and method == 'POST':
            x = imagegen.gallery_get(p[1], sp)
            if not x:
                return self.send_json({'error': '图片不存在'}, 404)
            src = os.path.join(imagegen.images_dir(sp), x['file'])
            if p[2] == 'reveal':
                if sp == 'v':
                    return self.send_json({'error': '私密空间中不能在资源管理器中打开（资源管理器会记录文件夹和文件名）'}, 400)
                reveal(src, False)
                return self.send_json({'ok': True})
            if p[2] == 'tomats':  # 放进素材库的“提取的衣服”（2026-11-17 用户：生成的衣服图也放进来，选参考图时好找）。素材库不分空间：私密空间不行
                if sp == 'v':
                    return self.send_json({'error': '私密空间的图不能放进素材库（素材库不在私密空间里）'}, 400)
                rel, had = mats_link(src, x['file'])
                return self.send_json({'ok': True, 'rel': rel, 'existed': had})
            if p[2] == 'tolib':  # 存进音源库的“AI 生图”文件夹：播放页里就能看到（私密空间存进私密音源库）
                d = os.path.join(lib_root(), 'AI 生图')
                os.makedirs(d, exist_ok=True)
                stem = re.sub(r'[\\/:*?"<>|\s]+', ' ', x['prompt']).strip()[:24].strip() or '生图'
                name = f"{datetime.datetime.fromtimestamp(x['created']).strftime('%Y%m%d-%H%M%S')} {stem}{os.path.splitext(x['file'])[1]}"
                dst = os.path.join(d, name)
                had = os.path.isfile(dst)
                if not had:
                    shutil.copyfile(src, dst)
                _lib_cache.pop(lib_root(), None)
                return self.send_json({'ok': True, 'path': 'AI 生图/' + name, 'existed': had})
        return self.send_json({'error': 'not found'}, 404)

    def audioedit_api(self, method, p):
        """改录音：POST /api/audioedit（{audio: {data: data URL} 或 {lib: 音源相对路径}, kind, a, b, seconds?}）；GET /api/audioedit = 当前空间的任务"""
        sp = space()
        root = os.path.join(jobs_root(sp), '_audioedit')
        audioedit.load(root, sp)
        if not p and method == 'GET':
            mine = [j for j in audioedit.jobs.values() if j.get('_space') == sp]
            return self.send_json({'ok': audioedit.ok(), 'missing': audioedit.missing(), 'jobs': [audioedit.public(j) for j in sorted(mine, key=lambda x: -x['created'])][:30]})
        if not p and method == 'POST':
            b = self.jbody()
            a = b.get('audio') if isinstance(b.get('audio'), dict) else {}
            if not audioedit.ok():
                return self.send_json({'error': '改录音所需的模型尚未下载：' + '、'.join(audioedit.missing())}, 400)
            try:
                if isinstance(a.get('data'), str):
                    d = a['data'].split(',', 1)[1] if a['data'].startswith('data:') else a['data']
                    if len(d) > 70_000_000:
                        raise ValueError('录音过大（上限约 50MB）')
                    data, ext = base64.b64decode(d), (re.sub(r'[^a-z0-9]', '', str(a.get('ext') or 'wav').lower()) or 'wav')[:5]
                elif isinstance(a.get('lib'), str):
                    path = lib_path(a['lib'])
                    if os.path.getsize(path) > 200_000_000:  # 音源库里选的也有上限（审查 27：以前不限，选一个很大的视频会整份读进内存）
                        raise ValueError('录音过大（上限约 200MB），请先剪出要改的那一段')
                    with open(path, 'rb') as f:
                        data = f.read()
                    ext = os.path.splitext(path)[1].lstrip('.').lower() or 'wav'
                else:
                    raise ValueError('请先添加一段录音')
                secs = b.get('seconds')
                secs = max(0.5, min(120.0, float(secs))) if secs not in (None, '') else None
                os.makedirs(root, exist_ok=True)
                j = audioedit.submit(data, ext, str(b.get('kind') or 'replace'), str(b.get('a') or '')[:200], str(b.get('b') or '')[:200], secs, root=root)
                j['_space'] = sp
                return self.send_json(audioedit.public(j))
            except (ValueError, RuntimeError) as e:
                return self.send_json({'error': str(e)}, 400)
        if len(p) == 1 and method == 'DELETE':
            j = audioedit.jobs.get(p[0])
            if not j or j.get('_space') != sp:
                return self.send_json({'error': '记录不存在'}, 404)
            if j['state'] in ('queued', 'running'):
                return self.send_json({'error': '正在修改，完成后再删除'}, 400)
            audioedit.jobs.pop(p[0], None)
            shutil.rmtree(j['_dir'], ignore_errors=True)
            return self.send_json({'ok': True})
        return self.send_json({'error': 'not found'}, 404)

    def stt_api(self, method, p, q):
        if method == 'GET' and not p:
            return self.send_json([j.summary() for j in sorted((x for x in list(stt.stt_jobs.values()) if getattr(x, 'space', 'n') == space()), key=lambda j: -j.created)[:100]])
        if method == 'POST' and not p:
            fname = urllib.parse.unquote(self.headers.get('X-Filename', 'upload.bin'))
            src = os.path.join(tmp_dir(), 'stt_' + uuid.uuid4().hex[:10] + safe_ext(fname))
            eng = q.get('engine') if q.get('engine') in ('qwen', 'whisper') else 'qwen'
            if eng == 'whisper' and not stt.whisper_available():  # 先检查，免得白收一个大文件
                return self.send_json({'error': '未找到 Whisper（PotPlayer 里的 Faster-Whisper-XXL）'}, 400)
            try:
                self.save_body(src)
            except RuntimeError:
                if os.path.exists(src):
                    os.remove(src)
                raise
            try:
                sopts = json.loads(urllib.parse.unquote(self.headers.get('X-Stt-Opts', '') or '{}'))
            except ValueError:
                sopts = {}
            j = stt.SttJob(src, fname, eng, q.get('language', 'auto'), transcribe_stt, root=VSTT if space() == 'v' else None, space=space(), opts=sopts)
            stt.stt_jobs[j.id] = j
            return self.send_json(j.summary())
        if p == ['prompt'] and method == 'POST':
            b = self.jbody()
            return self.send_json({'prompt': stt.copy_prompt(b.get('text', ''), b.get('background', ''))})
        if not p or p[0] not in stt.stt_jobs or getattr(stt.stt_jobs[p[0]], 'space', 'n') != space():
            return self.send_json({'error': '记录不存在'}, 404)
        j = stt.stt_jobs[p[0]]
        if method == 'GET' and len(p) == 1:
            return self.send_json(j.summary(full=True))
        if method == 'PATCH' and len(p) == 1:
            b = self.jbody()
            if 'text' in b:
                if not isinstance(b['text'], str):
                    return self.send_json({'error': '文字内容有误'}, 400)
                with open(os.path.join(j.dir, 'transcript.txt'), 'w', encoding='utf-8') as f:
                    f.write(b['text'])
                j.text = b['text']
                try:
                    stt_resubs(j)  # 播放页的字幕也用改过的文字
                except Exception as e:
                    act(f'字幕对齐失败：{e}', j.id, 'warn')
            if 'corrected' in b and (b['corrected'] is None or isinstance(b['corrected'], str)):
                j.corrected = b['corrected']
            j.save()
            return self.send_json({'ok': True})
        if method == 'DELETE' and len(p) == 1:
            if j.state == 'running':
                return self.send_json({'error': '正在识别中，无法删除'}, 400)
            stt.stt_jobs.pop(j.id)
            shutil.rmtree(j.dir, ignore_errors=True)
            return self.send_json({'ok': True})
        if method == 'POST' and p[1:] == ['correct']:
            b = self.jbody()
            text = b.get('text') or j.text
            fixed = stt.correct_text(text, b.get('background', ''), b.get('op', j.id))
            j.corrected = fixed
            j.save()
            return self.send_json({'corrected': fixed, 'ops': stt.diff_ops(text, fixed)})
        self.send_json({'error': 'not found'}, 404)

    def voices(self, method, p, q):
        if method == 'GET' and not p:
            items = [{'id': k, **v, 'url': f'/media/voice/{k}.wav', **({'private': True} if lib == VLIB else {})} for lib in voice_libs() for k, v in load_meta(lib).items()]
            items.sort(key=lambda x: -x.get('created', 0))
            return self.send_json(items)

        if method == 'POST' and p == ['design']:
            b = self.jbody()
            desc = (b.get('description') or '').strip()
            if not desc:
                return self.send_json({'error': '请先描述所需的声音'}, 400)
            model = model_info(b.get('model') or 'breeze')
            text = (b.get('text') or '').strip() or DEFAULT_SAMPLE
            count = max(1, min(4, int(b.get('count') or 3)))
            base = int(b.get('seed') or (int(time.time()) % 100000))
            if not model['roles']['design']:
                raise RuntimeError(f"{model['display_name']} 不支持通过描述设计音色，请改用 Breeze 或 Qwen3-TTS")
            out = []
            with gpu_audio():
                for k in range(count):
                    name = f'cand_{uuid.uuid4().hex[:10]}.wav'
                    payload, _ = build_request(model, text, None, desc, b.get('options'), base + k * 101)
                    act(f"设计候选 {k + 1}/{count}（{model['display_name']}）", b.get('op', 'design'))
                    speak(payload, os.path.join(tmp_dir(), name), b.get('op', 'design'))
                    out.append({'file': name, 'url': '/media/tmp/' + name, 'seed': base + k * 101, 'transcript': text})
            return self.send_json(out)

        if method == 'POST' and p == ['import']:
            # 原始文件（mp3/mp4/wav/m4a/录音 webm…）作为请求体上传，截取范围放在查询串里
            fname = urllib.parse.unquote(self.headers.get('X-Filename', 'upload.bin'))
            src = os.path.join(tmp_dir(), 'src_' + uuid.uuid4().hex[:10] + safe_ext(fname))
            try:
                start = max(0.0, float(q.get('start') or 0))
                dur = max(2.0, min(30.0, float(q.get('duration') or 12)))
            except ValueError:
                raise BadRequest('起点或时长不是数字')
            try:
                self.save_body(src)
            except RuntimeError:
                if os.path.exists(src):
                    os.remove(src)
                raise
            name = f'clip_{uuid.uuid4().hex[:10]}.wav'
            clip = os.path.join(tmp_dir(), name)
            try:
                act(f'截取 {fname} 第 {start:.1f} 秒起 {dur:.1f} 秒，转成 24kHz 单声道 WAV', q.get('op', 'import'))
                ffmpeg('-ss', str(start), '-t', str(dur), '-i', src, '-vn', '-ac', '1', '-ar', '24000', '-sample_fmt', 's16', clip)
                # 同一段再留一份原始音质（44.1kHz 立体声）：之后用户点“去除背景声”时拿它来分离，效果比用 24k 单声道好
                ffmpeg('-ss', str(start), '-t', str(dur), '-i', src, '-vn', '-ac', '2', '-ar', '44100', '-sample_fmt', 's16', clip[:-4] + '_hq.wav')
            finally:
                os.remove(src)
            asr16 = clip[:-4] + '_16k.wav'
            ffmpeg('-i', clip, '-ac', '1', '-ar', '16000', asr16)
            text = transcribe(asr16, q.get('op', 'import'))
            act('识别完成：' + text[:40], q.get('op', 'import'), 'ok')
            os.remove(asr16)
            return self.send_json({'file': name, 'url': '/media/tmp/' + name, 'transcript': text, 'seconds': wav_seconds(clip)})

        if method == 'POST' and p == ['separate']:
            # 用户在截取结果里点了“去除背景声”：只处理这一小段，原来的截取结果保留，可以来回对比
            b = self.jbody()
            name = os.path.basename(b.get('file') or '')
            clip = os.path.join(tmp_dir(), name)
            if not (name.startswith('clip_') and os.path.isfile(clip)):
                return self.send_json({'error': '音频已失效，请重新截取'}, 400)
            out = separate_vocals(clip[:-4] + '_hq.wav' if os.path.isfile(clip[:-4] + '_hq.wav') else clip, b.get('op', 'import'))
            return self.send_json({'file': out, 'url': '/media/tmp/' + out, 'seconds': wav_seconds(os.path.join(tmp_dir(), out))})

        if method == 'POST' and p == ['save']:
            b = self.jbody()
            src = os.path.join(tmp_dir(), os.path.basename(b.get('file') or ''))
            if not os.path.isfile(src):
                return self.send_json({'error': '音频已失效，请重新生成'}, 400)
            name, transcript = (b.get('name') or '').strip(), (b.get('transcript') or '').strip()
            if not name:
                return self.send_json({'error': '请给音色起个名字'}, 400)
            if not transcript:
                return self.send_json({'error': '缺少参考文字稿（该段音频的内容）'}, 400)
            lib = VLIB if space() == 'v' else LIB  # 私密空间里新建的音色只存在私密库
            with lock:
                meta = load_meta(lib)
                vid = 'v' + datetime.datetime.now().strftime('%Y%m%d%H%M%S') + uuid.uuid4().hex[:4]
                shutil.copyfile(src, os.path.join(lib, vid + '.wav'))
                meta[vid] = {'name': name, 'description': b.get('description', ''), 'transcript': transcript,
                             'source': b.get('source', 'design'), 'seed': b.get('seed'), 'created': time.time()}
                save_meta(meta, lib)
            return self.send_json({'id': vid})

        if len(p) == 1 and method in ('PATCH', 'DELETE'):
            vid = p[0]
            with lock:
                lib = voice_lib_of(vid) or LIB
                meta = load_meta(lib)
                if vid not in meta:
                    return self.send_json({'error': '音色不存在'}, 404)
                if method == 'DELETE':
                    del meta[vid]
                    try:
                        os.remove(os.path.join(lib, vid + '.wav'))
                    except OSError:
                        pass
                else:
                    b = self.jbody()
                    if 'name' in b and not str(b['name']).strip():
                        return self.send_json({'error': '请给音色起个名字'}, 400)
                    if 'transcript' in b and not str(b['transcript']).strip():
                        return self.send_json({'error': '参考文字不能为空（须与音频内容一字不差）'}, 400)
                    for k in ('name', 'description', 'transcript'):
                        if k in b:
                            meta[vid][k] = str(b[k]).strip()
                save_meta(meta, lib)
            return self.send_json({'ok': True})
        self.send_json({'error': 'not found'}, 404)

    def jobs(self, method, p, q):
        if method == 'GET' and not p:
            mine = sorted((x for x in list(jobs.values()) if getattr(x, 'space', 'n') == space()), key=lambda j: -j.created)
            # 最新的 200 条 + 更早但保存成作品的（作品不能因为历史记录多了就看不到）
            return self.send_json([j.summary() for k, j in enumerate(mine) if k < 200 or getattr(j, 'saved', False)])
        if method == 'POST' and not p:
            b = self.jbody()
            if b.get('kind') == 'vc':
                if not b.get('source'):
                    return self.send_json({'error': '请先上传或录制要换声的音频'}, 400)
                if not b.get('voice'):
                    return self.send_json({'error': '请选择目标音色'}, 400)
                b['model'] = b.get('model') or 'seedvc'
                b['model_name'] = vc_model_info(b['model'])['display_name']
                b['voice_name'] = get_voice(b['voice']).get('name', '')
                j = VcJob(b)
                jobs[j.id] = j
                j.save()
                with job_cv:
                    job_queue.append(j)
                    job_cv.notify()
                return self.send_json(j.summary())
            if not norm(b.get('text', '')):
                return self.send_json({'error': '请先输入要朗读的文字'}, 400)
            b.setdefault('model', 'breeze')
            b['model_name'] = model_info(b['model'])['display_name']
            if b.get('voice'):
                b['voice_name'] = get_voice(b['voice']).get('name', '')
            elif b.get('preset'):
                b['voice_name'] = '预设 · ' + b['preset']
            elif not (b.get('instruct') or '').strip():
                return self.send_json({'error': '请选择一个音色，或在“导演”中描述所需的声音'}, 400)
            j = Job(b)
            if not j.segments:
                shutil.rmtree(j.dir, ignore_errors=True)  # 只有指令、没有正文：建好的空文件夹删掉
                return self.send_json({'error': '没有可朗读的文字'}, 400)
            jobs[j.id] = j
            j.save()
            with job_cv:
                job_queue.append(j)
                job_cv.notify()
            return self.send_json(j.summary())
        if not p or not job_visible(p[0]):
            return self.send_json({'error': '任务不存在'}, 404)
        j = jobs[p[0]]
        if method == 'GET' and len(p) == 1:
            return self.send_json(j.summary(full=True))
        if method == 'GET' and p[1:] == ['subs']:
            if not isinstance(j, VcJob):
                return self.send_json({'error': '只有换声任务有对比字幕'}, 400)
            src_j, out_j = j.subs_files()
            need_out = j.state == 'done'
            if not (os.path.isfile(src_j) and (os.path.isfile(out_j) or not need_out)):
                if getattr(j, 'subs', '') == 'running':
                    return self.send_json({'state': 'running'})
                if q.get('wait') != '1':
                    return self.send_json({'state': 'none'})
                sl = j.__dict__.setdefault('_subs_lock', threading.Lock())
                if not sl.acquire(blocking=False):
                    return self.send_json({'state': 'running'})
                try:
                    with gpu_audio():
                        j.make_subs()  # 旧任务第一次打开对比：现在补做
                finally:
                    sl.release()
                if not os.path.isfile(src_j):
                    return self.send_json({'state': 'error', 'error': getattr(j, 'subs', '')[6:] or '字幕生成失败'})
            src = read_json(src_j, {}).get('sents', [])
            out = pair_subs(src, read_json(out_j, {}).get('chars', [])) if os.path.isfile(out_j) else []
            return self.send_json({'state': 'done', 'src': src, 'out': out})
        if method == 'POST' and p[1:] == ['save']:
            # 保存到作品 / 取消保存 / 重命名
            b = self.jbody()
            if 'saved' in b:
                if b['saved'] and j.state != 'done':
                    return self.send_json({'error': '只有生成完成的音频才能保存到作品'}, 400)
                j.saved = bool(b['saved'])
            if isinstance(b.get('title'), str) and b['title'].strip():
                j.title = b['title'].strip()[:40]
            j.save()
            return self.send_json(j.summary())
        if method == 'POST' and p[1:] == ['cancel']:
            j.cancel = True
            with job_cv:
                queued = j in job_queue
                if queued:
                    job_queue.remove(j)
            if queued:
                j.state, j.message, j.finished = 'error', '已取消', time.time()
                j.log('已取消（尚未开始生成）', 'warn')
                j.save()
            elif j.state == 'running':
                j.message = '正在取消：当前这一段生成完成后即停止（引擎无法中途打断）'
                j.log('收到取消：当前这一段生成完后立即停止，不再重做、拼接和导出', 'warn')
            return self.send_json(j.summary(full=True))
        if method == 'DELETE' and len(p) == 1:
            if j.state in ('queued', 'running'):
                return self.send_json({'error': '任务进行中，不能删除'}, 400)
            rl = j.__dict__.get('_redo_lock')
            if rl and rl.locked():
                return self.send_json({'error': '正在重做其中一段，完成后再删除'}, 400)
            jobs.pop(j.id)
            shutil.rmtree(j.dir, ignore_errors=True)
            return self.send_json({'ok': True})
        if method == 'POST' and len(p) == 3 and p[1] == 'redo':
            if j.state in ('queued', 'running'):
                return self.send_json({'error': '任务仍在进行中，请待其完成后再单独重做'}, 400)
            b = self.jbody()
            if not p[2].isdigit() or int(p[2]) >= len(j.segments):
                return self.send_json({'error': '段号有误'}, 400)
            with gpu_audio(), j.__dict__.setdefault('_redo_lock', threading.Lock()):  # 同一条任务的重做一个一个来
                j.redo(int(p[2]), b.get('text'), b.get('direction'))
            return self.send_json(j.summary(full=True))
        self.send_json({'error': 'not found'}, 404)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    request_queue_size = 128  # 2026-11-23：默认只排 5 个，页面一打开同时要三十来个静态文件，Windows 会直接拒绝多出来的连接（手机测试打不开页面）
    # Windows 上 SO_REUSEADDR 会允许多个进程同时占用 7860，导致“已在运行”检测失效、请求随机落到旧进程。
    # 改为独占端口：第二次启动会失败并直接打开浏览器。
    allow_reuse_address = False

    def server_bind(self):
        import socket
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def clean_vtmp(max_age=0):
    """私密空间的临时文件：启动时全部删掉，退出私密空间时删掉 max_age 秒以前的。"""
    now = time.time()
    for f in os.listdir(VTMP):
        fp = os.path.join(VTMP, f)
        try:
            if now - os.path.getmtime(fp) > max_age:
                shutil.rmtree(fp, ignore_errors=True) if os.path.isdir(fp) else os.remove(fp)
        except OSError:
            pass


def clean_tmp(max_age=86400 * 2):
    now = time.time()
    for f in os.listdir(TMP):
        fp = os.path.join(TMP, f)
        try:  # 文件刚好被别处删掉也不报错；文件夹也清（以前 os.remove 删不掉文件夹、永远留着，2026-11-16 审查）
            if now - os.path.getmtime(fp) > max_age:
                shutil.rmtree(fp, ignore_errors=True) if os.path.isdir(fp) else os.remove(fp)
        except OSError:
            pass


def wire_modules():
    """把各模块接到这里的日志、空间、显卡调度上（正式启动和开发测试 devtest/run.py 共用）。"""
    stt.act = act
    imagegen.act, imagegen.space, imagegen.gpu_free = act, space, gpu_free_for_images
    tplstore.SPACE = space  # 模板套：按当前空间（请求 / 后台任务线程）取默认的那套
    tplstore.FILE = lambda sp: os.path.join(DATA if sp == 'v' else PROMPT_DIR, 'templates.json')  # 自己建的几套 + 默认用哪套，和 AI 助手的预设放在一起
    imagegen.set_space = lambda sp: setattr(CTX, 'space', sp)
    import editfix as _ef
    _ef.TMP = tmp_dir  # 修脸的中间图：私密空间的写在 .data 里
    translate.GPU_CTX = stt.GPU_CTX = gpu_audio
    translate.KILL_PORT = promptgen.KILL_PORT = imagegen.kill_port
    promptgen.OTHERS = lambda: imagegen._busy  # 一共几个在用显卡；promptgen 自己减掉正在写的对话
    promptgen.act, promptgen.GPU_CTX, promptgen.gpu_prepare = act, imagegen.audio_gpu, gpu_free_for_prompt
    stt.SET_SPACE = imagegen.set_space
    videogen.act, videogen.space, videogen.GPU_PREPARE = act, space, gpu_free_for_images
    # 做完一段视频要不要把显存让出来：配音 / 换声 / 识别 / 提示词正在用或排着、生图有任务排着（2026-11-11）
    videogen.OTHERS_WAITING = lambda: bool(imagegen._busy) or any(x.get('state') == 'queued' for x in list(imagegen.jobs.values())) \
        or any(getattr(x, 'state', '') in ('queued', 'running') for x in list(jobs.values()))
    imagegen.OTHER_GPU = videogen.Engine.free_idle
    imagegen.MATS_LINK = mats_link  # 提取出来的衣服：普通空间硬链接进素材库/提取的衣服（2026-11-17）
    import batch  # 批量配方（2026-11-14）：后台线程推进每一次批量
    batch.setup(submit=video_edit_submit, set_space=lambda sp: setattr(CTX, 'space', sp), videogen=videogen, mats_path=mats_path, split_for=batch_split, act=act,
                notify=lambda t, b_, u: push.notify(t, b_, u), dirs=lambda sp: (RECIPES_V, BATCH_V) if sp == 'v' else (RECIPES_N, BATCH_N))
    if not getattr(videogen, '_started', False):  # 生视频的任务线程：和生图共用显卡锁（同一时间只做一件大事）
        videogen._started = True

        def take(j):
            ok = imagegen._take_gpu(j)
            if ok:
                CTX.space = j['space']
            return ok
        threading.Thread(target=videogen.worker, args=(take, imagegen.GPU.release, imagegen.Engine.stop), daemon=True).start()


# ================================================================ 一键重启（设置里）
RESTART_CMD = None   # 重启后用什么命令再启动；None = 和现在一样（测试环境会改掉）
RESTART_LOG = os.path.join(STUDIO, 'app-server.log')
DIAG_LOG = os.path.join(ROOT, 'outputs', 'play-diag.log')


def gpu_busy():
    """现在真正在用显卡的任务（2026-11-17 审查 P02）：正在跑的配音 / 换声、生图、视频、转写、改录音、AI 助手生成。
    排队的、批量 runner 自己的推进（找换装点 / 质检 / 拼接的管理工作）不算——它们是 busy_work（重启会打断的事）"""
    st = lambda j: j.get('state') if isinstance(j, dict) else getattr(j, 'state', '')
    return (any(j.state == 'running' for j in list(jobs.values())) or any(st(j) == 'running' for j in list(imagegen.jobs.values()))
            or any(st(j) == 'running' for j in list(videogen.jobs.values())) or any(getattr(j, 'state', '') == 'running' for j in list(stt.stt_jobs.values()))
            or any(st(j) == 'running' for j in list(audioedit.jobs.values())) or bool(getattr(promptgen.Engine, 'busy', 0))
            or any((j.__dict__.get('_redo_lock') or threading.Lock()).locked() for j in list(jobs.values())))


def busy_work():
    """重启会打断的事：返回说明（空 = 可以直接重启）。私密空间的只算数量、不说是什么。"""
    tts = sum(1 for j in list(jobs.values()) if j.state in ('queued', 'running'))
    img = sum(1 for j in list(imagegen.jobs.values()) if j.get('state') in ('queued', 'running'))
    video = sum(1 for j in list(videogen.jobs.values()) if j.get('state') in ('queued', 'running'))
    asr = sum(1 for j in list(stt.stt_jobs.values()) if getattr(j, 'state', '') == 'running')
    pg = 1 if getattr(promptgen.Engine, 'busy', 0) else 0
    ae = sum(1 for j in list(audioedit.jobs.values()) if (j.get('state') if isinstance(j, dict) else getattr(j, 'state', '')) in ('queued', 'running'))  # 2026-11-14 审查：以前漏了改录音
    tts += sum(1 for j in list(jobs.values()) if (j.__dict__.get('_redo_lock') or threading.Lock()).locked())  # 单段重做（2026-11-16 审查：以前漏了）
    out = []
    if getattr(sys.modules.get('batch'), 'BUSY', [0])[0]:
        out.append('批量正在找换装点 / 质检 / 拼接')
    if ae:
        out.append(f'{ae} 个改录音任务')
    if tts:
        out.append(f'{tts} 个配音 / 换声任务')
    if img:
        out.append(f'{img} 个生图任务')
    if video:
        out.append(f'{video} 个视频任务')
    if asr:
        out.append(f'{asr} 个语音转文字')
    if pg:
        out.append('AI 助手正在生成')
    return out


def stop_all_engines():
    for stop in (lambda: imagegen.Engine.stop(), promptgen.stop, lambda: translate._Local.stop()):
        try:
            stop()
        except Exception:
            pass


def shutdown_self():
    """应用窗口关了：正在做的任务记成中断，关掉所有引擎（包括配音引擎），自己退出。"""
    time.sleep(0.3)
    for j in list(jobs.values()):
        if j.state in ('queued', 'running'):
            try:
                j.cancel = True
                j.state, j.message, j.finished = 'error', '上次未完成（程序被关闭）', time.time()
                j.save()
            except Exception:
                pass
    stop_all_engines()
    try:  # 2026-11-14 审查：应用关了视频引擎（ComfyUI）也关（以前留着继续占显存）；一键重启时不关，新的 Studio 直接接着用
        videogen.Engine.shutdown()
    except Exception:
        pass
    if not ENGINE_SHARED or ENGINE_OWNED:  # 借来的配音引擎（测试实例）不关：正式 Studio 还在用（F05）
        kill_ours('audiocpp_server.exe', port=urllib.parse.urlsplit(ENGINE).port)
    os._exit(0)


def restart_self():
    """先把回复发出去，再关掉显卡上的生图 / 提示词 / 翻译模型，起一个小进程等端口空出来后用同样的命令重新启动，自己退出。
    配音引擎（audio.cpp）不关：新启动的会直接接着用它（模型不用重新载入），引擎配置变了会自己重启它。"""
    time.sleep(0.6)
    act('正在重启 Studio……', 'system')
    for j in list(jobs.values()):
        if j.state in ('queued', 'running'):
            try:
                j.cancel = True
                j.state, j.message, j.finished = 'error', '重启 Studio 时中断（已生成的段仍保留，可单独重做）', time.time()
                j.save()
            except Exception:
                pass
    for stop in (lambda: imagegen.Engine.stop(), promptgen.stop, lambda: translate._Local.stop()):
        try:
            stop()
        except Exception:
            pass
    cmd = RESTART_CMD or [sys.executable] + (['-I'] if sys.flags.isolated else []) + [os.path.abspath(__file__)] + [a for a in sys.argv[1:]]
    if RESTART_CMD is None:
        cmd = [a for a in cmd if a != '--restarted'] + (['--no-browser'] if '--no-browser' not in cmd else []) + ['--restarted']  # 重启后不再弹浏览器；端口一时绑不上就等
    helper = '\n'.join([  # 等旧进程退出、端口空出来（最多 30 秒），再启动新的
        'import socket, subprocess, sys, time',
        'port, log, cmd = int(sys.argv[1]), sys.argv[2], sys.argv[3:]',
        'for _ in range(120):',
        '    s = socket.socket()',
        '    try:',
        '        s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)',
        '        s.bind(("127.0.0.1", port)); s.close(); break',
        '    except OSError:',
        '        s.close(); time.sleep(0.25)',
        'f = open(log, "w", encoding="utf-8", errors="replace")',
        'subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, creationflags=0x08000200)'])
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    subprocess.Popen([pyw if os.path.isfile(pyw) else sys.executable, '-I', '-c', helper, str(PORT), RESTART_LOG] + cmd,
                     cwd=ROOT, creationflags=0x08000200 | NO_WINDOW, close_fds=True)
    time.sleep(0.3)
    os._exit(0)


def main():
    wire_modules()
    testing = '--library' in sys.argv  # 开发测试用：生图的图放到测试目录旁边、用另一个引擎端口、不清理临时文件，不碰真实数据
    if testing:
        imagegen.DIRS = {k: os.path.join(os.path.dirname(LIBRARY), 'test-images-' + k) for k in 'nv'}
        imagegen.PORT += 1
        translate.LOCAL_PORT += 1
        promptgen.PORT += 2
    httpd = None
    for k in range(120 if '--restarted' in sys.argv else 1):  # 一键重启后：旧进程的连接可能还占着端口，最多等 60 秒
        try:
            httpd = Server(('127.0.0.1', PORT), Handler)
            break
        except OSError:
            time.sleep(0.5)
    if httpd is None:
        print('工作室已在运行。')
        if '--no-browser' not in sys.argv:
            webbrowser.open(f'http://127.0.0.1:{PORT}/play')
        return
    if not testing:  # 2026-11-14 审查：先确认这是唯一的 Studio（端口拿到了）再清上次没关干净的引擎——以前第二次双击启动会把正在用的引擎杀掉
        threading.Thread(target=imagegen.kill_orphan, daemon=True).start()  # 上次没关干净的生图引擎还占着显存的话，先结束掉
        threading.Thread(target=imagegen.kill_port, args=(translate.LOCAL_PORT, 'llama-server.exe'), daemon=True).start()  # 翻译模型也是
        threading.Thread(target=imagegen.kill_port, args=(promptgen.PORT, 'llama-server.exe'), daemon=True).start()  # 提示词模型也是
    remote.keep_listening(lambda addr: Server(addr, Handler), PORT, lambda m: act(m, 'remote'))  # 手机访问（开启后才会监听）
    push.watch([('配音', lambda: jobs, '/tts'), ('生图', lambda: imagegen.jobs, '/img'), ('生视频', lambda: videogen.jobs, '/video'), ('改录音', lambda: audioedit.jobs, '/audioedit')])  # 生成完成推送到手机
    print('正在启动推理引擎（audio.cpp）……')
    proc = start_engine()
    if not testing:
        clean_tmp()
        clean_vtmp()
        try:  # 上次留下的智能选取原图（记录只在内存里，重启后用不到了；可能有私密的）
            imagegen.q21.sam_purge()
        except Exception:
            pass
        try:
            os.remove(VAULT_TOKENS)  # 旧版本存在硬盘上的私密空间凭证（现在只放内存）
        except OSError:
            pass
    load_old_jobs()
    stt.load_old_stt()
    stt.load_old_stt(VSTT, 'v')
    threading.Thread(target=job_worker, daemon=True).start()
    print(f'AI 配音工作室已启动： http://127.0.0.1:{PORT}')
    print('使用完毕后直接关闭此窗口即可（将同时停止引擎并释放显卡内存）。')
    if '--no-browser' not in sys.argv:
        webbrowser.open(f'http://127.0.0.1:{PORT}/play')
    try:
        httpd.serve_forever()
    finally:
        if proc:
            proc.terminate()


if __name__ == '__main__':
    main()
