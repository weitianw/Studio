"""任务管理器里显示“Studio”而不是“Python”（2026-11-18 用户）。

做法：在 Conda 的文件夹里复制一份 pythonw.exe → Studio.exe（应用窗口）、python.exe → StudioServer.exe（后台），
用 rcedit（Electron 的开源工具，tools/rcedit/rcedit-x64.exe）改掉显示名和图标。必须放在 Conda 文件夹里：
Python 按 exe 所在的位置找 python313.dll 和标准库。

Conda 升级 Python 后复制的那份会过时：记下复制时原文件的大小和修改时间，变了就重做（正在运行的 exe 不能覆盖，
但可以改名，所以先把旧的改名成 .old 再放新的，下次启动时删掉 .old）。

用法：python -I studio/studioexe.py        （检查，过时了就重做）
      python -I studio/studioexe.py --force
"""
import json
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # 用 -I 启动时脚本所在的文件夹不在搜索路径里
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RCEDIT = config.tools('rcedit', 'rcedit-x64.exe')
ICON = os.path.join(ROOT, 'studio', 'web', 'app.ico')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
TARGETS = [('pythonw.exe', 'Studio.exe', 'Studio'), ('python.exe', 'StudioServer.exe', 'Studio 后台')]


def py_dir():
    """Conda 的文件夹：从 Studio.exe / StudioServer.exe 启动时 sys.executable 就在这里"""
    return os.path.dirname(os.path.abspath(sys.executable))


def _sig(path):
    st = os.stat(path)
    return [st.st_size, int(st.st_mtime)]


def _mark(dst):
    return dst + '.studio.json'


def stale(d=None):
    d = d or py_dir()
    out = []
    for src, dst, _ in TARGETS:
        s, t = os.path.join(d, src), os.path.join(d, dst)
        if not os.path.isfile(s):
            continue
        try:
            with open(_mark(t), encoding='utf-8') as fh:
                m = json.load(fh)
        except Exception:
            m = None
        if not os.path.isfile(t) or not m or m.get('src') != _sig(s) or m.get('icon') != _sig(ICON):
            out.append((src, dst))
    return out


def build(force=False, d=None):
    """返回做了哪些；rcedit 或图标不在就什么都不做（照旧用 python）"""
    d = d or py_dir()
    if not (os.path.isfile(RCEDIT) and os.path.isfile(ICON)):
        return []
    for _, dst, _ in TARGETS:  # 上次换下来的旧文件
        try:
            os.remove(os.path.join(d, dst + '.old'))
        except OSError:
            pass
    todo = [(s, t) for s, t, _ in TARGETS] if force else stale(d)
    done = []
    for src, dst in todo:
        name = dict((t, n) for _, t, n in TARGETS)[dst]
        s, t = os.path.join(d, src), os.path.join(d, dst)
        tmp = t + '.new'
        shutil.copy2(s, tmp)
        r = subprocess.run([RCEDIT, tmp, '--set-icon', ICON,
                            '--set-version-string', 'FileDescription', name, '--set-version-string', 'ProductName', 'Studio',
                            '--set-version-string', 'InternalName', dst, '--set-version-string', 'OriginalFilename', dst,
                            '--set-version-string', 'CompanyName', 'AI-TTS Studio'],
                           capture_output=True, timeout=60, creationflags=NO_WINDOW)
        if r.returncode:
            os.remove(tmp)
            continue
        if os.path.exists(t):
            try:
                os.remove(t)
            except OSError:  # 正在运行：改名让开
                os.replace(t, t + '.old')
        os.replace(tmp, t)
        with open(_mark(t), 'w', encoding='utf-8') as fh:
            json.dump({'src': _sig(s), 'icon': _sig(ICON)}, fh)
        done.append(dst)
    return done


def server_exe():
    """后台用哪个 exe：做好了就用 StudioServer.exe，不然 python.exe"""
    d = py_dir()
    t = os.path.join(d, 'StudioServer.exe')
    if os.path.isfile(t) and ('StudioServer.exe' not in [x[1] for x in stale(d)]):
        return t
    return os.path.join(d, 'python.exe')


if __name__ == '__main__':
    print(build(force='--force' in sys.argv) or '已是最新')
