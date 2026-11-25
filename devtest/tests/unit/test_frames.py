"""视频截一帧 → 素材库（studio/frames.py，2026-11-19 用户）。用临时目录当素材库，不碰真实文件：
对齐到帧、默认存放位置（成对的图片文件夹 / 生成的视频 / 私密空间）、记录增删、重复判断、移动后同步、文件没了自动清掉、私密文件夹清单和网页一致。"""
import json, os, re, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'studio'))
import frames


@pytest.fixture
def root(tmp_path):
    frames.init(str(tmp_path), 'ffmpeg', 'ffprobe')
    yield tmp_path


def touch(root, rel):
    p = os.path.join(str(root), *rel.split('/')); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(b'x'); return p


@pytest.mark.parametrize('t,fps,want', [(1.234, 30, 37 / 30), (0, 30, 0), (1.0, 30, 1.0), (0.999, 30, 29 / 30), (2.5, 0, 2.5), (5.0, 25, 4.96)])
def test_snap_to_frame(t, fps, want):
    assert abs(frames.snap(t, fps, 5.0) - want) < 1e-5  # 11-23 起保留 6 位小数（再对齐一次还是同一帧）


def test_default_dest():
    assert frames.default_dest({'mats': 'clips/a.mp4'}, False) == 'clips image'
    assert frames.default_dest({'mats': 'trip/x/b.mp4'}, False) == 'trip/x image'
    assert frames.default_dest({'mats': 'root.mp4'}, False) == '视频截图'
    assert frames.default_dest({'gallery': 'abc'}, False) == '视频截图/生成的视频'
    assert frames.default_dest({'gallery': 'abc'}, True) == '视频截图/私密空间'


def test_index_add_dup_remove(root):
    src = {'mats': 'v/a.mp4'}
    touch(root, 'v image/a/a_0m01.00s.png'); touch(root, 'v image/a/a_0m02.00s.png')
    frames.add(src, {'size': 1, 'dur': 3, 'fps': 30, 'name': 'a'}, 'v image/a/a_0m01.00s.png', 1.0, 'v image/a')
    frames.add(src, {'size': 1, 'dur': 3, 'fps': 30, 'name': 'a'}, 'v image/a/a_0m02.00s.png', 2.0, 'v image/a')
    e = frames.items('m:v/a.mp4')
    assert [x['t'] for x in e['items']] == [1.0, 2.0] and e['album'] == 'v image/a'
    assert frames.dup('m:v/a.mp4', 1.05)['rel'].endswith('01.00s.png')
    assert frames.dup('m:v/a.mp4', 1.2) is None
    assert frames.counts() == {'m:v/a.mp4': 2}
    assert frames.by_image()['v image/a/a_0m02.00s.png'][1] == 2.0
    assert frames.remove_image('v image/a/a_0m01.00s.png')
    assert len(frames.items('m:v/a.mp4')['items']) == 1


def test_missing_files_pruned(root):
    src = {'mats': 'v/a.mp4'}
    p = touch(root, 'v image/a/x.png')
    frames.add(src, {}, 'v image/a/x.png', 1.0, 'v image/a')
    os.remove(p)
    assert frames.items('m:v/a.mp4') is None
    assert 'm:v/a.mp4' not in frames.load()['videos']


def test_on_move_updates_video_album_items(root):
    src = {'mats': 'v/a.mp4'}
    touch(root, 'v image/a/x.png'); os.makedirs(os.path.join(str(root), 'v image', 'a'), exist_ok=True)
    frames.write_album(os.path.join(str(root), 'v image', 'a'), src, 'a')
    frames.add(src, {}, 'v image/a/x.png', 1.0, 'v image/a')
    os.makedirs(os.path.join(str(root), 'w image', 'sub'), exist_ok=True)
    os.replace(os.path.join(str(root), 'v image', 'a'), os.path.join(str(root), 'w image', 'sub', 'a'))
    frames.on_move('v image/a', 'w image/sub/a')
    e = frames.items('m:v/a.mp4')
    assert e['album'] == 'w image/sub/a' and e['items'][0]['rel'] == 'w image/sub/a/x.png'
    touch(root, 'z/a.mp4'); frames.on_move('v/a.mp4', 'z/a.mp4')  # 视频本身挪了
    assert frames.items('m:z/a.mp4')['items'][0]['rel'] == 'w image/sub/a/x.png'
    info = json.load(open(os.path.join(str(root), 'w image', 'sub', 'a', frames.POST), encoding='utf-8'))
    assert info['video'] == {'mats': 'z/a.mp4'} and info['kind'] == 'frames'


def test_album_dir_avoids_other_sets(root):
    """和视频同名的另一个图集已经在了：截图另起「… 截图」，不混进去、不改它的说明"""
    par = os.path.join(str(root), 'clips image'); d = os.path.join(par, 'post'); os.makedirs(d)
    json.dump({'desc': '别的图集', 'id': '1'}, open(os.path.join(d, frames.POST), 'w', encoding='utf-8'))
    ad = frames.album_dir(par, 'post')
    assert os.path.basename(ad) == 'post 截图'
    frames.write_album(d, {'mats': 'clips/a.mp4'}, 'post')
    assert json.load(open(os.path.join(d, frames.POST), encoding='utf-8')) == {'desc': '别的图集', 'id': '1'}
    os.makedirs(ad); frames.write_album(ad, {'mats': 'clips/a.mp4'}, 'post')
    assert frames.album_dir(par, 'post') == ad  # 第二次：就是这个截图图集
    assert os.path.basename(frames.album_dir(par, 'new')) == 'new'


def test_names():
    assert frames.stamp(72.5) == '1m12.50s' and frames.stamp(3) == '0m03.00s'
    assert frames.safe_name('a/b:c*?') == 'a b c' and frames.safe_name('   ') == '视频'
    assert frames.key_of({'mats': 'a\\b.mp4'}) == 'm:a/b.mp4' and frames.key_of({'gallery': 'x'}) == 'g:x'


def test_private_list_matches_web():
    """网页（frames.js 的 FR_PRIV）和后台（server.MATS_PRIVATE）的私密文件夹清单一样：不一样时网页会让人选到后台不让存的文件夹"""
    js = open(os.path.join(HERE, '..', '..', '..', 'studio', 'web', 'frames.js'), encoding='utf-8').read()
    web = re.search(r"const FR_PRIV = \[([^\]]+)\]", js).group(1)
    web = [x.strip().strip("'") for x in web.split(',')]
    py = open(os.path.join(HERE, '..', '..', '..', 'studio', 'server.py'), encoding='utf-8').read()
    srv = re.search(r"MATS_PRIVATE = \(([^)]+)\)", py).group(1)
    srv = [x.strip().strip("'") for x in srv.split(',') if x.strip()]
    assert web == srv
