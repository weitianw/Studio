"""P08（2026-11-17 审查）：改录音只解码一次原录音；run() 看到已经准备好的两份就不再转；转换失败照样报错。不跑 AuK。"""
import os, subprocess, sys
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import audioedit


def test_prep_once_then_run_reuses(tmp_path):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        if args[0] == audioedit.FFMPEG:
            for a in args:
                if str(a).endswith('.wav'):
                    open(a, 'wb').close()
            return subprocess.CompletedProcess(args, 0, '', '')
        open(args[args.index('--out') + 1], 'wb').close()  # 假装 AuK 出了结果
        return subprocess.CompletedProcess(args, 0, '', '')
    with patch.object(audioedit.subprocess, 'run', fake_run), patch.object(audioedit, 'splice', lambda a, g, o: (False, 0, 0)):
        audioedit.prep(str(tmp_path), 'src.mp3')
        audioedit.run(str(tmp_path), 'src.mp3', '把A改成B', 3)
    ff = [c for c in calls if c[0] == audioedit.FFMPEG]
    assert len(ff) == 1 and ff[0].count('-i') == 1  # 只解码一次，一次写两份
    assert any(a.endswith('input.wav') for a in ff[0]) and any(a.endswith('input16.wav') for a in ff[0])


def test_prep_failure_raises(tmp_path):
    def bad(args, **kw):
        raise subprocess.CalledProcessError(1, args)
    with patch.object(audioedit.subprocess, 'run', bad), pytest.raises(subprocess.CalledProcessError):
        audioedit.prep(str(tmp_path), 'broken.mp3')
