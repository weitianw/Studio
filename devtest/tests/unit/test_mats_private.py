"""素材库里只在私密空间显示的文件夹（server.MATS_PRIVATE，例如 视频截图/私密空间）。
用临时目录当素材库，不碰真实文件：普通空间里这些路径取不到、子路径也取不到；私密空间照常；大小写、反斜杠、..（会被丢掉、不往上走）绕不过去；
别的同名前缀（视频截图 本身、私密空间2）不受影响；后台线程用 any_space=True 照常能取。"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server

P = '视频截图/私密空间'


@pytest.fixture
def mats(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'MATS_DIR', str(tmp_path))
    yield tmp_path
    server.CTX.space = 'n'


@pytest.mark.parametrize('rel', [P, P + '/a.png', P + '/x/01.jpg', '视频截图\\私密空间\\a.png'])
def test_hidden_in_normal_space(mats, rel):
    server.CTX.space = 'n'
    with pytest.raises(ValueError):
        server.mats_path(rel)
    server.CTX.space = 'v'
    assert server.mats_path(rel).startswith(str(mats))


@pytest.mark.parametrize('rel', ['', '视频截图', '视频截图/a.png', '视频截图/私密空间2', '视频截图/其他/私密空间', '测试视频/私密空间.mp4'])
def test_others_visible(mats, rel):
    server.CTX.space = 'n'
    assert server.mats_path(rel).startswith(str(mats))


def test_any_space_and_walk_filter(mats):
    server.CTX.space = 'n'
    assert server.mats_path(P + '/a.png', any_space=True).endswith('a.png')  # 后台线程
    assert server.mats_hid_dir(str(mats / '视频截图'), '私密空间')
    assert not server.mats_hid_dir(str(mats), '视频截图') and not server.mats_hid_dir(str(mats / '视频截图'), '别的')
    assert server.mats_hide(P + '/a', 'v') is False and server.mats_hide(P + '/a', 'n') is True
    server.CTX.space = 'v'
    assert not server.mats_hid_dir(str(mats / '视频截图'), '私密空间')


def test_dotdot_cannot_reach_private(mats):
    """.. 会被直接丢掉（不往上走）：x/../视频截图/私密空间 进不到真正的私密文件夹"""
    server.CTX.space = 'n'
    for rel in ('x/../视频截图/私密空间/a.png', '../视频截图/私密空间/a.png', '视频截图/x/../私密空间/a.png'):
        try:
            p = server.mats_path(rel)
        except ValueError:
            continue
        assert not p.startswith(str(mats / '视频截图' / '私密空间') + os.sep), p
