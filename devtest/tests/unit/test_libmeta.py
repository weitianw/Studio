"""播放页歌曲表的时长 / 作者（libmeta.py，2026-11-17）：ffprobe 读时长和 artist 标签、缓存命中、文件改了重读。
用 ffmpeg 现场生成的 1 秒静音音频，不碰任何用户文件。"""
import os, subprocess, sys, threading
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'studio'))
import libmeta

FF = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin')
FFMPEG, FFPROBE = os.path.join(FF, 'ffmpeg.exe'), os.path.join(FF, 'ffprobe.exe')
pytestmark = pytest.mark.skipif(not (os.path.isfile(FFMPEG) and os.path.isfile(FFPROBE)), reason='没有 tools/ffmpeg')


def _make(path, artist=None, secs=1):
    cmd = [FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', str(secs)]
    if artist:
        cmd += ['-metadata', f'artist={artist}']
    subprocess.run(cmd + [path], check=True, capture_output=True)


def _item(root, rel):
    st = os.stat(os.path.join(root, rel))
    return {'path': rel, 'size': st.st_size, 'mtime': st.st_mtime}


def _fill_wait(items, root, cache):
    done = threading.Event()
    n = libmeta.fill(items, root, cache, FFPROBE, on_done=done.set)
    if n:
        assert done.wait(30)
    return n


def test_probe_reads_duration_and_artist(tmp_path):
    a = tmp_path / 'a.mp3'
    _make(str(a), artist='测试歌手', secs=2)
    dur, artist = libmeta.probe(FFPROBE, str(a))
    assert dur is not None and abs(dur - 2) < .2
    assert artist == '测试歌手'


def test_probe_bad_file_no_error(tmp_path):
    b = tmp_path / 'bad.mp3'
    b.write_bytes(b'not audio')
    assert libmeta.probe(FFPROBE, str(b)) == (None, '')


def test_fill_caches_and_refreshes_on_change(tmp_path):
    root, cache = str(tmp_path / 'lib'), str(tmp_path / 'cache' / 'libmeta.json')
    os.makedirs(os.path.join(root, 'd'))
    _make(os.path.join(root, 'd', 'x.mp3'), artist='甲')
    _make(os.path.join(root, 'y.mp3'))
    items = [_item(root, 'd/x.mp3'), _item(root, 'y.mp3')]
    assert _fill_wait(items, root, cache) == 2  # 第一次：都要后台读，这次不填
    assert 'dur' not in items[0]
    items = [_item(root, 'd/x.mp3'), _item(root, 'y.mp3')]
    assert libmeta.fill(items, root, cache, FFPROBE) == 0  # 第二次：全部命中缓存
    assert items[0]['artist'] == '甲' and abs(items[0]['dur'] - 1) < .2 and 'artist' not in items[1]
    assert os.path.isfile(cache)
    libmeta._stores.clear()  # 重启后从文件读回来
    items = [_item(root, 'd/x.mp3')]
    assert libmeta.fill(items, root, cache, FFPROBE) == 0 and items[0]['artist'] == '甲'
    _make(os.path.join(root, 'd', 'x.mp3'), artist='乙', secs=3)  # 文件换了：大小 / 时间变了就重读
    items = [_item(root, 'd/x.mp3')]
    assert _fill_wait(items, root, cache) == 1
    items = [_item(root, 'd/x.mp3')]
    libmeta.fill(items, root, cache, FFPROBE)
    assert items[0]['artist'] == '乙' and abs(items[0]['dur'] - 3) < .2
