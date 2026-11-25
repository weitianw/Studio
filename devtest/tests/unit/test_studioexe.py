"""任务管理器里显示“Studio”（studioexe.py，2026-11-18）：在临时文件夹里复制 python / pythonw 做一遍，
检查改了显示名、记下原文件、原文件变了会重做、正在用的旧文件改名让开。不碰 Conda 文件夹。"""
import os, shutil, subprocess, sys, time
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'studio'))
import studioexe as se

PYDIR = os.path.dirname(sys.executable)
pytestmark = pytest.mark.skipif(not (os.path.isfile(se.RCEDIT) and os.path.isfile(os.path.join(PYDIR, 'pythonw.exe'))), reason='没有 rcedit 或 pythonw')


def _desc(exe):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', f"(Get-Item -LiteralPath '{exe}').VersionInfo.FileDescription"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def test_build_and_rebuild(tmp_path):
    d = str(tmp_path)
    for n in ('python.exe', 'pythonw.exe'):
        shutil.copy2(os.path.join(PYDIR, n), d)
    assert set(t for _, t in se.stale(d)) == {'Studio.exe', 'StudioServer.exe'}
    assert sorted(se.build(d=d)) == ['Studio.exe', 'StudioServer.exe']
    assert _desc(os.path.join(d, 'Studio.exe')) == 'Studio'
    assert _desc(os.path.join(d, 'StudioServer.exe')) == 'Studio 后台'
    assert se.stale(d) == [] and se.build(d=d) == []  # 已是最新：不重做
    # “升级”了 pythonw：只重做 Studio.exe
    p = os.path.join(d, 'pythonw.exe'); t = time.time() + 5; os.utime(p, (t, t))
    assert [x for _, x in se.stale(d)] == ['Studio.exe']
    assert se.build(d=d) == ['Studio.exe'] and se.stale(d) == []


def test_running_exe_is_renamed_out_of_the_way(tmp_path):
    d = str(tmp_path)
    for n in ('python.exe', 'pythonw.exe'):
        shutil.copy2(os.path.join(PYDIR, n), d)
    se.build(d=d)
    run = subprocess.Popen([os.path.join(d, 'StudioServer.exe'), '-c', 'import time; time.sleep(20)'])  # 在用的那份
    try:
        time.sleep(1)
        assert se.build(force=True, d=d) == ['Studio.exe', 'StudioServer.exe']
        assert os.path.isfile(os.path.join(d, 'StudioServer.exe.old'))
    finally:
        run.kill(); run.wait()
    se.build(d=d)  # 下一次：旧文件清掉
    assert not os.path.exists(os.path.join(d, 'StudioServer.exe.old'))
