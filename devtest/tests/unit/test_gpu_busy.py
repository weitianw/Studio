"""P02（2026-11-17 审查）：批量找换装点时，显卡空不空只看真正在用显卡的任务——批量 runner 自己在推进（BUSY）不算；有推理任务在跑时避让。
不跑分析（cutpoints 换成记录调用的假函数）。"""
import os, sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server, batch


def idle_seen(video_jobs):
    seen = {}

    def fake_analyze(path, ff, probe, cd, bg, studio_idle):
        seen['idle'] = studio_idle()
        return {'dur': 10, 'points': [], 'dev': 'gpu' if seen['idle'] else 'cpu'}
    with patch.object(server, 'jobs', {}), patch.object(server.imagegen, 'jobs', {}), patch.object(server.videogen, 'jobs', video_jobs), \
            patch.object(server.stt, 'stt_jobs', {}), patch.object(server.audioedit, 'jobs', {}), patch.object(server.promptgen.Engine, 'busy', 0), \
            patch('cutpoints.cached', lambda p, cd: None), patch('cutpoints.analyze', fake_analyze), patch('segpref.status', lambda f: {}), \
            patch('segpref.split', lambda cp, dur, model: [[0, dur]]), patch.object(batch, 'BUSY', [1]):  # runner 正在推进这一条
        server.batch_split('x.mp4', 'n', 10)
        restart = server.busy_work()
    return seen['idle'], restart


def test_runner_itself_does_not_block_gpu():
    idle, restart = idle_seen({})
    assert idle is True  # 以前：批量自己 BUSY → 判成显卡忙 → 落到 CPU
    assert any('批量' in x for x in restart)  # 重启前的忙碌检查照样算上批量


def test_yields_when_inference_running():
    idle, _ = idle_seen({'v1': {'state': 'running', 'space': 'n'}})
    assert idle is False
    idle, _ = idle_seen({'v1': {'state': 'queued', 'space': 'n'}})  # 只是排队：不算正在用显卡
    assert idle is True
