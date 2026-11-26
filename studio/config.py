"""路径配置（2026-11-26 开源泛化 ①）：程序、模型、引擎、工具都从这里取，别的模块不再自己拼 ROOT/tools/... 这类路径。

每一项的查找顺序：环境变量 → studio/settings.json 里的 "paths" → 自动查找（PATH 等）→ 默认位置（和以前一样，在程序文件夹里）。
所以装在别的位置、或者模型放在另一块盘上的电脑，只要设一个环境变量或者在 settings.json 里写一行；不设时和以前完全一样。

  环境变量                settings.json 的 paths 键   默认
  STUDIO_MODELS_DIR       models                      <程序>/models
  STUDIO_TOOLS_DIR        tools                       <程序>/tools
  STUDIO_COMFY_DIR        comfyui                     <tools>/ComfyUI_windows_portable（便携版的根目录，里面有 ComfyUI/ 和 python_embeded/）
  STUDIO_FFMPEG           ffmpeg                      <tools>/ffmpeg/bin/ffmpeg.exe，没有就用 PATH 上的 ffmpeg
  STUDIO_LLAMA_DIR        llama_cpp                   <程序>/llama.cpp
  STUDIO_AUDIOCPP_DIR     audio_cpp                   <程序>/audio.cpp
  STUDIO_SD_DIR           sd_cpp                      <tools>/sd.cpp
  STUDIO_POTPLAYER        potplayer                   常见安装位置里第一个存在的
"""
import json, os, shutil

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
EXE = '.exe' if os.name == 'nt' else ''


def _settings_paths():
    try:
        with open(os.path.join(STUDIO, 'settings.json'), encoding='utf-8') as f:
            p = json.load(f).get('paths')
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


_SP = _settings_paths()


def _pick(env, key, default):
    v = os.environ.get(env) or _SP.get(key)
    return os.path.normpath(os.path.expanduser(str(v))) if v else default


def _first(*cands):
    """候选里第一个存在的；都不存在就返回第一个（报错时能看出它在找哪里）"""
    cands = [c for c in cands if c]
    return next((c for c in cands if os.path.exists(c)), cands[0] if cands else '')


MODELS_DIR = _pick('STUDIO_MODELS_DIR', 'models', os.path.join(ROOT, 'models'))
TOOLS_DIR = _pick('STUDIO_TOOLS_DIR', 'tools', os.path.join(ROOT, 'tools'))
COMFY_PORTABLE = _pick('STUDIO_COMFY_DIR', 'comfyui', os.path.join(TOOLS_DIR, 'ComfyUI_windows_portable'))
COMFY_DIR = os.path.join(COMFY_PORTABLE, 'ComfyUI')
COMFY_MODELS = os.path.join(COMFY_DIR, 'models')
COMFY_PY = _first(os.path.join(COMFY_PORTABLE, 'python_embeded', 'python' + EXE), os.path.join(COMFY_PORTABLE, 'python_embedded', 'python' + EXE))
LLAMA_DIR = _pick('STUDIO_LLAMA_DIR', 'llama_cpp', os.path.join(ROOT, 'llama.cpp'))
LLAMA_SERVER = os.path.join(LLAMA_DIR, 'llama-server' + EXE)
AUDIOCPP_DIR = _pick('STUDIO_AUDIOCPP_DIR', 'audio_cpp', os.path.join(ROOT, 'audio.cpp'))
SD_DIR = _pick('STUDIO_SD_DIR', 'sd_cpp', os.path.join(TOOLS_DIR, 'sd.cpp'))


def _tool(env, key, local, name):
    v = _pick(env, key, None)
    if v:
        return v
    return local if os.path.isfile(local) else (shutil.which(name) or local)


FFMPEG = _tool('STUDIO_FFMPEG', 'ffmpeg', os.path.join(TOOLS_DIR, 'ffmpeg', 'bin', 'ffmpeg' + EXE), 'ffmpeg')
FFPROBE = _tool('STUDIO_FFPROBE', 'ffprobe', os.path.join(os.path.dirname(FFMPEG), 'ffprobe' + EXE), 'ffprobe')
POTPLAYER = _pick('STUDIO_POTPLAYER', 'potplayer', None) or _first(
    r'D:\App\PotPlayer\PotPlayerMini64.exe', r'C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe',
    r'C:\Program Files\PotPlayer\PotPlayerMini64.exe', r'C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini.exe')


def _defaults():
    try:
        with open(os.path.join(STUDIO, 'defaults.json'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _settings_value(key):
    try:
        with open(os.path.join(STUDIO, 'settings.json'), encoding='utf-8') as f:
            return json.load(f).get(key)
    except (OSError, ValueError, AttributeError):
        return None


# 界面默认语言（开源泛化 ④）：环境变量 STUDIO_UI_LANG → settings.json 的 ui_lang → studio/defaults.json → 中文。页面上的切换存在浏览器里，优先于这个
UI_LANG = next((v for v in (os.environ.get('STUDIO_UI_LANG'), _settings_value('ui_lang'), _defaults().get('ui_lang')) if v in ('zh', 'en')), 'zh')


def models(*p):
    return os.path.join(MODELS_DIR, *p)


def tools(*p):
    return os.path.join(TOOLS_DIR, *p)


def comfy(*p):
    """ComfyUI 便携版里的路径（comfy('ComfyUI', 'models', 'loras') 这样用）"""
    return os.path.join(COMFY_PORTABLE, *p)


def audiocpp(*p):
    return os.path.join(AUDIOCPP_DIR, *p)


def resolve(p):
    """配置文件里写的相对路径（相对程序文件夹，例如 models/<文件夹>/<文件>.gguf）展开成完整路径；已经是完整路径的原样返回。
    models/ 开头的跟着 MODELS_DIR 走（模型放在别的盘时 server.json 不用改）"""
    if not isinstance(p, str) or not p or os.path.isabs(p):
        return p
    q = p.replace('\\', '/')
    if q.startswith('models/'):
        return os.path.join(MODELS_DIR, *q[7:].split('/'))
    return os.path.join(ROOT, *q.split('/'))


def summary():
    """设置页 / 模型页显示用：每一项现在指向哪里、在不在"""
    items = {'models': MODELS_DIR, 'tools': TOOLS_DIR, 'comfyui': COMFY_PORTABLE, 'ffmpeg': FFMPEG, 'llama_cpp': LLAMA_DIR,
             'audio_cpp': AUDIOCPP_DIR, 'sd_cpp': SD_DIR, 'potplayer': POTPLAYER}
    return {k: {'path': v, 'exists': bool(v) and os.path.exists(v)} for k, v in items.items()}
