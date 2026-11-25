"""F08（2026-11-17 审查）：私密空间密钥改成每个安装独立的带盐记录。只用测试自己编的密钥，临时目录。"""
import hashlib, json, os, sys
from unittest.mock import patch, Mock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import vaultkey as vk

OLD = 'abc123'  # 测试用的“旧密钥”（不是真的）
OLD_SHA = hashlib.sha256(OLD.encode()).hexdigest()


def test_new_install_needs_local_setup(tmp_path):
    rec = tmp_path / 'vault-key.json'
    assert not vk.check(str(rec), OLD, OLD_SHA, lambda: False)  # 没有私密数据的新安装：源码里的旧哈希不认
    assert vk.hint(str(rec), OLD_SHA, lambda: False)['vk'] is None
    vk.save(str(rec), vk.make('zx98qw'))  # 在这台电脑上设置（vaultkey.py 命令行做的事）
    assert vk.check(str(rec), 'zx98qw') and not vk.check(str(rec), 'zx98qe')
    h = vk.hint(str(rec))
    assert h['vk'] == hashlib.sha256((h['vks'] + 'zx98qw').encode()).hexdigest()[:2]
    data = json.loads(rec.read_text())
    assert 'zx98qw' not in rec.read_text() and data['kdf'] == 'scrypt' and len(data['salt']) > 10


def test_two_installs_have_different_records(tmp_path):
    a, b = vk.make('zx98qw'), vk.make('zx98qw')
    assert a['salt'] != b['salt'] and a['hash'] != b['hash'] and a['hint_salt'] != b['hint_salt']


def test_old_install_migrates_on_first_unlock_then_legacy_retires(tmp_path):
    rec = tmp_path / 'vault-key.json'
    logs = []
    assert vk.hint(str(rec), OLD_SHA, lambda: True)['vk'] == OLD_SHA[:2]
    assert vk.check(str(rec), OLD, OLD_SHA, lambda: True, logs.append)  # 老用户：旧密钥能解锁
    assert rec.exists() and any('迁移' in m for m in logs)
    assert vk.check(str(rec), OLD, OLD_SHA, lambda: True)  # 之后用本机记录核对
    vk.save(str(rec), vk.make('newkey'))  # 换了密钥以后：旧密钥 + 旧哈希不再被接受
    assert not vk.check(str(rec), OLD, OLD_SHA, lambda: True)
    assert vk.check(str(rec), 'newkey', OLD_SHA, lambda: True)


def test_interrupted_migration_retries(tmp_path):
    rec = tmp_path / 'vault-key.json'
    with patch.object(vk.os, 'replace', side_effect=OSError('断电')):
        assert vk.check(str(rec), OLD, OLD_SHA, lambda: True)  # 这次照样放行
    assert not rec.exists() and not list(tmp_path.glob('*.json'))  # 没有半个记录
    assert vk.check(str(rec), OLD, OLD_SHA, lambda: True) and rec.exists()  # 下次再迁，成功


def test_broken_record_refuses_everything(tmp_path):
    rec = tmp_path / 'vault-key.json'
    rec.write_text('{broken', encoding='utf-8')
    assert not vk.check(str(rec), OLD, OLD_SHA, lambda: True)  # 不退回旧方式
    assert vk.hint(str(rec), OLD_SHA, lambda: True)['vk'] is None
    rec.write_text(json.dumps({'kdf': 'md5'}), encoding='utf-8')
    assert not vk.check(str(rec), OLD, OLD_SHA, lambda: True)


def test_server_unlock_uses_local_record(tmp_path):
    import server
    rec = tmp_path / 'vault-key.json'
    vk.save(str(rec), vk.make('qq11ww'))

    def unlock(key):
        h = object.__new__(server.Handler)
        h.remote, h.client_address = False, ('127.0.0.1', 1)
        h.headers = {}
        h.jbody = lambda: {'key': key}
        h.send_json = Mock(side_effect=lambda d, *a, **k: (d, a[0] if a else 200, k))
        with patch.object(server, 'VAULT_REC', str(rec)), patch.object(server, 'VAULT_KEY_SHA', OLD_SHA), patch.object(server, 'VTOKS', {}), \
                patch.object(server, '_vfail', {}), patch.object(server, 'act', lambda *a, **k: None):
            return h.vault_api('POST', ['unlock'], {})
    ok = unlock('qq11ww')
    assert ok[0] == {'vault': True} and 'vault=' in ok[2]['headers']['Set-Cookie']
    assert unlock(OLD)[1] == 403  # 有了本机记录：源码里的旧哈希对应的密钥不认
    assert unlock('qq11wx')[1] == 403
