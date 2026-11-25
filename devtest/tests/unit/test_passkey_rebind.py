"""面容 ID（11-21 用户 iPhone“开启失败：The object is in an invalid state”）：手机重新配对后换了设备 id，
旧 id 下的通行密钥不能再挡住这台手机重新开启；移除手机时它的通行密钥一起删。只用临时文件。"""
import json, os, sys
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import passkey, remote

H = 'pc.example.ts.net'


def _setup(tmp_path, creds, devices):
    pk, rm = tmp_path / 'pk.json', tmp_path / 'remote.json'
    pk.write_text(json.dumps({'creds': creds}), encoding='utf-8')
    rm.write_text(json.dumps({'enabled': True, 'devices': devices}), encoding='utf-8')
    return patch.object(passkey, 'CONF', str(pk)), patch.object(remote, 'CONF', str(rm))


def test_exclude_only_this_device(tmp_path):
    a, b = _setup(tmp_path, [{'id': 'OLD', 'rp': H, 'dev': 'd_old'}, {'id': 'MINE', 'rp': H, 'dev': 'd_new'}, {'id': 'PC', 'rp': H, 'dev': 'pc'}],
                  [{'id': 'd_new', 'hash': 'x'}])
    with a, b:
        ex = [c['id'] for c in passkey.reg_options(H, 'd_new')['excludeCredentials']]
        assert ex == ['MINE']  # 旧 id（同一台手机重新配对前）的不排除，手机才能新建
        assert passkey.reg_options(H, 'd_other')['excludeCredentials'] == []


def test_paired_cleanup_and_remove_device(tmp_path):
    a, b = _setup(tmp_path, [{'id': 'OLD', 'rp': H, 'dev': 'd_old'}, {'id': 'PC', 'rp': H, 'dev': 'pc'}, {'id': 'N', 'rp': H, 'dev': 'd_new'}],
                  [{'id': 'd_new', 'hash': 'x'}])
    with a, b:
        assert passkey._paired('pc') and passkey._paired('d_new') and not passkey._paired('d_old')
        with patch.dict(sys.modules, {'push': Mock()}):  # 不碰真的推送订阅
            remote.remove_device('d_new')
        ids = [c['id'] for c in passkey._load()['creds']]
        assert 'N' not in ids and 'PC' in ids  # 移除手机：它的通行密钥一起删，电脑的不动
