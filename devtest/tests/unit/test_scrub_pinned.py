"""F15（2026-11-17 审查）：播放副本用固定版本的地址——一次播放里所有 Range 请求都来自同一个文件。临时文件，假的请求。"""
import io, os, sys, time
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server


class Req:
    """记下回应：状态码、头、正文"""
    def __init__(self, path, rng=''):
        h = object.__new__(server.Handler)
        h.path, h.headers, h.wfile = path, {'Range': rng} if rng else {}, io.BytesIO()
        self.h, self.status, self.hdr = h, None, {}
        h.send_response = lambda code, *a: setattr(self, 'status', code)
        h.send_header = lambda k, v: self.hdr.__setitem__(k, v)
        h.end_headers = lambda: None
        h.send_json = lambda d, code=200, **k: setattr(self, 'status', code)
        h.command = 'GET'

    def body(self):
        return self.h.wfile.getvalue()


@pytest.fixture
def files(tmp_path):
    orig, copy = tmp_path / 'v.mp4', tmp_path / 'v.scrub.mp4'
    orig.write_bytes(b'ORIGINAL' * 100)
    return orig, copy


def get(path, files, q, rng=''):
    orig, copy = files
    r = Req(path, rng)
    with patch.object(server, 'scrub_path', lambda p, beside: str(copy)), patch.object(server, 'scrub_queue', lambda *a, **k: None):
        r.h.send_scrub(str(orig), q, False, None)
    return r


def test_pinned_versions(files):
    orig, copy = files
    r = get('/media/mats/v.mp4?scrub=1', files, {'scrub': '1'})  # 副本还没好
    assert r.status == 302 and r.hdr['Cache-Control'] == 'no-store'
    loc = r.hdr['Location']; assert 'sv=o' in loc
    sv_o = loc.split('sv=')[1]
    copy.write_bytes(b'COPYCOPY' * 100)  # 播放期间副本做好了
    os.utime(copy, (time.time() + 5, time.time() + 5))
    r = get(loc, files, {'scrub': '1', 'sv': sv_o}, 'bytes=8-15')  # 同一次播放接着要后面的数据（拖动）：还是原片
    assert r.body() == b'ORIGINAL' and r.status == 206
    r = get('/media/mats/v.mp4?scrub=1', files, {'scrub': '1'})  # 新的一次播放：用做好的副本
    loc2 = r.hdr['Location']; assert r.status == 302 and 'sv=c' in loc2
    r = get(loc2, files, {'scrub': '1', 'sv': loc2.split('sv=')[1]}, 'bytes=0-7')
    assert r.body() == b'COPYCOPY'
    r = get(loc2, files, {'scrub': '1', 'sv': loc2.split('sv=')[1]}, 'bytes=800-')  # 续读到结尾
    assert r.body() == b''  or r.status in (206, 416)


def test_stale_copy_version_falls_back_to_original(files):
    orig, copy = files
    copy.write_bytes(b'COPYCOPY' * 100)
    r = get('/x?scrub=1&sv=c1', files, {'scrub': '1', 'sv': 'c1'}, 'bytes=0-7')  # 版本对不上（副本换过）：给原片，不会混
    assert r.body() == b'ORIGINAL'
