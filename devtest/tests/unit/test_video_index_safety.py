"""F01（2026-11-17 审查）：视频库索引读不出 / 列不出文件夹时，不能把展示用的（过滤后的）列表写回去覆盖整个视频库。
全部在临时目录里，不碰真实视频库。跑：cd devtest && python -m pytest tests/unit/test_video_index_safety.py"""
import json, os, sys
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import videogen as vg


@pytest.fixture
def lib(tmp_path, monkeypatch):
    d = tmp_path / 'videos'; d.mkdir()
    monkeypatch.setitem(vg.DIRS, 'n', str(d))
    monkeypatch.setattr(vg, 'act', lambda *a, **k: None)
    return d


def media(d, name):
    (d / name).write_bytes(b'fake mp4')
    return name


def idx(d):
    return json.loads((d / 'index.json').read_text(encoding='utf-8'))


def test_first_save_creates_index(lib):
    vg._gallery_add('n', {'id': 'a', 'file': media(lib, 'a.mp4')})
    assert [x['id'] for x in idx(lib)] == ['a']


def test_corrupt_index_is_kept_and_new_item_recoverable(lib):
    media(lib, 'old.mp4')
    (lib / 'index.json').write_text('[{"id": "old", "file": "old.mp4"}, BROKEN', encoding='utf-8')
    before = (lib / 'index.json').read_bytes()
    with pytest.raises(vg.IndexUnreadable):
        vg._gallery_add('n', {'id': 'new', 'file': media(lib, 'new.mp4')})
    assert (lib / 'index.json').read_bytes() == before  # 原索引一个字节都没动
    assert (lib / 'new.mp4').exists() and (lib / 'old.mp4').exists()  # 媒体都在
    assert [x['id'] for x in vg.gallery('n')] == ['new']  # 界面能看到新成品（待并回）
    with pytest.raises(vg.IndexUnreadable):  # 删除也不写
        vg.gallery_delete({'old'}, 'n')
    assert (lib / 'old.mp4').exists() and (lib / 'index.json').read_bytes() == before
    # 修好索引后再存一条：待并回的、新的、原来的都在，待并回文件清掉
    (lib / 'index.json').write_text(json.dumps([{'id': 'old', 'file': 'old.mp4'}]), encoding='utf-8')
    vg._gallery_add('n', {'id': 'n2', 'file': media(lib, 'n2.mp4')})
    assert [x['id'] for x in idx(lib)] == ['n2', 'new', 'old']
    assert not (lib / 'index.pending.jsonl').exists()


def test_transient_read_error_does_not_overwrite(lib):
    vg._gallery_add('n', {'id': 'a', 'file': media(lib, 'a.mp4')})
    real = open

    def flaky(p, *a, **k):
        if str(p).endswith('index.json') and (not a or 'r' in a[0]) and 'w' not in (a[0] if a else k.get('mode', 'r')):
            raise PermissionError('临时读不出')
        return real(p, *a, **k)
    with patch('builtins.open', flaky):
        with pytest.raises(vg.IndexUnreadable):
            vg._gallery_add('n', {'id': 'b', 'file': media(lib, 'b.mp4')})
    assert [x['id'] for x in idx(lib)] == ['a']


def test_scandir_error_and_missing_media_do_not_drop_records(lib):
    # 有一条的视频文件暂时不在（比如外接盘没插）：界面不显示，但索引里必须保留
    (lib / 'index.json').write_text(json.dumps([{'id': 'gone', 'file': 'gone.mp4'}, {'id': 'a', 'file': media(lib, 'a.mp4')}]), encoding='utf-8')
    real = os.scandir
    with patch.object(vg.os, 'scandir', side_effect=lambda p=None: (_ for _ in ()).throw(OSError('列不出')) if os.path.samefile(p, lib) else real(p)):
        assert [x['id'] for x in vg.gallery('n')] == ['a']  # 列不出文件夹时逐条看，不是“都不在”
        vg._gallery_add('n', {'id': 'b', 'file': media(lib, 'b.mp4')})
    assert [x['id'] for x in idx(lib)] == ['b', 'gone', 'a']


def test_delete_keeps_shared_files_and_other_records(lib):
    src = media(lib, 'src.mp4')
    (lib / 'index.json').write_text(json.dumps([
        {'id': 'x', 'file': media(lib, 'x.mp4'), 'src_file': src},
        {'id': 'y', 'file': media(lib, 'y.mp4'), 'src_file': src},
        {'id': 'gone', 'file': 'gone.mp4'}]), encoding='utf-8')
    vg.gallery_delete({'x'}, 'n')
    assert [x['id'] for x in idx(lib)] == ['y', 'gone']  # 文件暂时不在的那条也没被顺手删掉
    assert not (lib / 'x.mp4').exists() and (lib / 'src.mp4').exists()


def test_non_list_index_refused(lib):
    (lib / 'index.json').write_text('{"oops": 1}', encoding='utf-8')
    with pytest.raises(vg.IndexUnreadable):
        vg._gallery_add('n', {'id': 'a', 'file': media(lib, 'a.mp4')})
    assert json.loads((lib / 'index.json').read_text()) == {'oops': 1}
