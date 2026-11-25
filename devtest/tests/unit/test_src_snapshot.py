"""P01（2026-11-17 审查）：同一原视频排进多段时共用一份快照；排队期间文件被替换，已排上的用旧快照、新排的用新的；没人用的快照会放掉。临时文件。"""
import gc, os, sys, time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server


def test_shared_replaced_and_released(tmp_path):
    p = tmp_path / 'a.mp4'
    p.write_bytes(b'OLD' * 1000)
    server._SRC_SNAP.clear()
    jobs = [server.src_snapshot(str(p)) for _ in range(4)]
    assert all(j is jobs[0] for j in jobs)  # 4 段共用一份
    p.write_bytes(b'NEW' * 1000); os.utime(p, (time.time() + 5, time.time() + 5))  # 排队期间素材被替换
    new = server.src_snapshot(str(p))
    assert new is not jobs[0] and new[:3] == b'NEW' and jobs[0][:3] == b'OLD'  # 已排上的不受影响
    jobs.pop()  # 取消一段：其余照样拿着
    assert jobs[0][:3] == b'OLD'
    jobs.clear(); gc.collect()  # 旧快照没有任务在用了
    later = time.time() + 10 ** 6
    with patch.object(server.time, 'time', lambda: later):
        server.src_snapshot(str(p))
    assert len(server._SRC_SNAP) == 1  # 只剩新的那份


def test_submit_keeps_only_path_in_request(tmp_path):
    p = tmp_path / 's.mp4'; p.write_bytes(b'\x00\x00\x00\x18ftypmp42' + b'x' * 5000)
    got = []
    with patch.object(server, 'mats_path', lambda r: str(p)), patch.object(server.videogen, 'submit', lambda b, i, f, e, v: got.append((b, v)) or {'id': '1'}):
        server.video_edit_submit({'video': {'mats': 's.mp4'}, 'edit': {'task': 'outfit'}}, 'n')
        server.video_edit_submit({'video': {'mats': 's.mp4'}, 'edit': {'task': 'outfit'}}, 'n')
    assert got[0][0]['video'] == {'mats': 's.mp4'} and got[0][1] is got[1][1]
