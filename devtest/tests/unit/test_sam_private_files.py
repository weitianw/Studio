"""F03（2026-11-17 审查）：智能选取的原图——私密的不留在普通空间的 ComfyUI 输入文件夹；同键替换、淘汰、锁定、重启都清理；
正在用的文件用完再删。合成图片 + 临时目录，假的 SAM（不启动 ComfyUI）。"""
import base64, io, os, sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import q21


def b64img(color):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (64, 48), color).save(b, 'PNG')
    return base64.b64encode(b.getvalue()).decode()


@pytest.fixture
def work(tmp_path, monkeypatch):
    n, v = tmp_path / 'n', tmp_path / 'v'
    monkeypatch.setitem(q21.V.WORK, 'n', str(n)); monkeypatch.setitem(q21.V.WORK, 'v', str(v))
    monkeypatch.setattr(q21, '_SAM_IMG', {}); monkeypatch.setattr(q21, '_SAM_PART', {})
    monkeypatch.setattr(q21, '_SAM_BUSY', {}); monkeypatch.setattr(q21, '_SAM_DROP', set())
    monkeypatch.setattr(q21.V.Engine, 'ensure', classmethod(lambda c: None))
    monkeypatch.setattr(q21.V.Engine, 'cancel_later', classmethod(lambda c: None), raising=False)
    monkeypatch.setattr(q21.V.Engine, 'free_later', classmethod(lambda c: None), raising=False)
    return n / 'in', v / 'sam'


def files(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def test_private_original_not_in_normal_input(work):
    win, vsam = work
    q21.sam_put('v:img1', b64img('red'))
    assert files(win) == [] and len(files(vsam)) == 1
    seen = {}

    def fake_run(wf, prefix):  # 跑 SAM 时：ComfyUI 输入文件夹里有一份临时副本
        seen['name'] = wf['l']['inputs']['image']
        seen['there'] = os.path.isfile(os.path.join(win, seen['name']))
        return [np.ones((48, 64), bool)]
    q21._sam_run, real = fake_run, q21._sam_run
    try:
        r = q21.sam_prep('v:img1')
    finally:
        q21._sam_run = real
    assert r['parts'] == 1 and seen['there'] and seen['name'].startswith('studio_samv_')
    assert files(win) == []  # 用完立刻删了


def test_normal_space_lookup_cannot_see_private(work):
    q21.sam_put('v:same', b64img('red'))
    with pytest.raises(q21.NeedImage):
        q21.sam_prep('n:same')


def test_same_key_replacement_deletes_old_file(work):
    win, vsam = work
    q21.sam_put('n:a', b64img('red')); first = files(win)
    q21.sam_put('n:a', b64img('blue'))
    assert len(files(win)) == 1 and files(win) != first
    q21.sam_put('v:b', b64img('red')); q21.sam_put('v:b', b64img('green'))
    assert len(files(vsam)) == 1


def test_eviction_deletes_but_waits_for_running_use(work):
    win, vsam = work
    q21.sam_put('n:k0', b64img('red'))
    ent = q21._SAM_IMG['n:k0']
    with q21._sam_staged(ent) as name:  # 一个 SAM 正在读 k0
        for k in range(1, 6):
            q21.sam_put(f'n:k{k}', b64img((k * 40, 0, 0)))
        assert 'n:k0' not in q21._SAM_IMG
        assert os.path.isfile(os.path.join(win, name))  # 被淘汰了，但还在用：先不删
    assert not os.path.isfile(ent[3])  # 用完删掉
    assert len(files(win)) == q21.SAM_KEEP


def test_lock_and_restart_clean_up(work):
    win, vsam = work
    q21.sam_put('v:a', b64img('red')); q21.sam_put('n:b', b64img('red'))
    q21._SAM_PART['v:a'] = [np.ones((48, 64), bool)]
    q21.sam_forget_space('v')  # 私密空间退出
    assert files(vsam) == [] and 'v:a' not in q21._SAM_IMG and 'v:a' not in q21._SAM_PART
    assert len(files(win)) == 1 and 'n:b' in q21._SAM_IMG
    # 异常重启：内存记录没了，文件还在 → 启动时清掉
    q21.sam_put('v:c', b64img('red'))
    q21._SAM_IMG.clear()
    (win / 'studio_samv_left.png').write_bytes(b'x')
    q21.sam_purge()
    assert files(win) == [] and files(vsam) == []
