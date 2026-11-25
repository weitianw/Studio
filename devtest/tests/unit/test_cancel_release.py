"""P06（2026-11-17 审查）：排队时取消的任务也放掉大的输入（生视频原视频 / 图，生图原图 / 遮罩）；共享的原视频快照别的段照样能用。
不起 worker、不用显卡：只把任务放进队列再取消。"""
import gc, os, sys, weakref
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import videogen, imagegen


class Big:  # 代表一大块输入；bytes 不能弱引用，用普通对象
    def __init__(self, b): self.b = b


def test_video_queued_cancel_releases():
    src = Big(b'v' * 1000)
    ref = weakref.ref(src)
    a = {'id': 'a', 'space': 'n', 'state': 'queued', 'model': 'm', '_vid': src, '_img': b'i', '_redo': ({}, src, b'i')}
    b = {'id': 'b', 'space': 'n', 'state': 'queued', 'model': 'm', '_vid': src}
    with patch.object(videogen, 'jobs', {'a': a, 'b': b}), patch.object(videogen, '_q', [a, b]):
        videogen.cancel('a', 'n')
        assert a['state'] == 'cancelled' and a['finished'] and videogen._q == [b]
        assert not any(k in a for k in ('_vid', '_img', '_redo'))
        del src; gc.collect()
        assert ref() is not None and b['_vid'] is ref()  # 另一段还在用这份快照
        videogen.cancel('b', 'n')
        gc.collect()
        assert ref() is None


def test_video_release_same_keys_as_worker():
    j = {k: 1 for k in ('_img', '_end', '_vid', '_x', '_ffmpeg', '_redo', '_cref')}
    videogen.release(j)
    assert j == {}


def test_image_queued_cancel_releases():
    init = Big(b'p' * 1000)
    ref = weakref.ref(init)
    j = {'id': 'g', 'space': 'n', 'state': 'queued', 'done': 0, '_init': init, '_mask': b'm', '_ctl': b'c', '_refs': [b'r']}
    del init
    with patch.object(imagegen, 'jobs', {'g': j}), patch.object(imagegen, 'queue', ['g']):
        imagegen.cancel('g', 'n')
        assert j['state'] == 'cancelled' and imagegen.queue == []
    assert not any(k in j for k in ('_init', '_mask', '_ctl', '_refs'))
    gc.collect()
    assert ref() is None
