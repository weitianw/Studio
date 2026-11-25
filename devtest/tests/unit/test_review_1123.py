"""11-23 审查修复 + 生图设置放开的单元测试（只用临时文件，不起服务、不用显卡）"""
import json, os, sys, time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import frames, q21, batch, remote, passkey


def test_album_dir_per_video(tmp_path):
    """同名的两个视频不共用一个截图图集（审查 12）；同一个视频接着用自己的"""
    a = frames.album_dir(str(tmp_path), '同名视频', {'mats': 'x/同名视频.mp4'})
    os.makedirs(a); frames.write_album(a, {'mats': 'x/同名视频.mp4'}, '同名视频')
    assert frames.album_dir(str(tmp_path), '同名视频', {'mats': 'x/同名视频.mp4'}) == a
    b = frames.album_dir(str(tmp_path), '同名视频', {'mats': 'y/同名视频.mp4'})
    assert b != a and os.path.basename(b).startswith('同名视频') and '截图' in os.path.basename(b)
    # 网页取帧（来源空）不盖掉原来的来源
    frames.write_album(a, {}, '同名视频')
    assert json.load(open(os.path.join(a, frames.POST), encoding='utf-8'))['video'] == {'mats': 'x/同名视频.mp4'}


def test_clean_over():
    """生图设置：只留合法的；局部重画不改像素；page = 按所选尺寸（只文生图）"""
    o = q21.clean_over({'steps': '999', 'cfg': '3.5', 'sampler': 'er_sde', 'scheduler': 'bogus', 'mp': '2'}, 'txt')
    assert o == {'steps': 100, 'cfg': 3.5, 'sampler': 'er_sde', 'mp': 2.0}
    assert q21.clean_over({'mp': 'page'}, 'txt') == {'mp': 'page'}
    assert q21.clean_over({'mp': 'page', 'steps': 20}, 'edit') == {'steps': 20}
    assert q21.clean_over({'mp': 3, 'steps': 0}, 'inpaint') == {'steps': 1}
    assert q21.clean_over('x', 'txt') == {}


def test_item_outcome_counts_cancelled_as_missing():
    """取消掉、没出成品的段也算缺（审查 18）"""
    it = {'state': 'run', 'segs': [{'a': 0, 'b': 3, 'state': 'done', 'best': 0, 'tries': [{'ok': True, 'result': 'r'}]},
                                   {'a': 3, 'b': 6, 'state': 'cancelled', 'best': None, 'tries': []}]}
    o = batch.item_outcome(it)
    assert o['state'] == 'partial' and o['missing'] == [[3, 6]]


def test_redeem_keeps_older_logins(tmp_path):
    """主屏幕安装令牌换了几次，之前换到的登录令牌照样能用（审查 24）"""
    with patch.object(remote, 'CONF', str(tmp_path / 'remote.json')):
        remote.save({'enabled': True, 'devices': [{'id': 'd1', 'hash': remote._h('main'), 'name': '手机', 'created': time.time(), 'last': time.time()}]})
        it = remote.install_token('d1')
        t1, t2 = remote.redeem(it), remote.redeem(it)
        ck = lambda t: remote.device_of(f'dev={t}')
        assert ck(t1) and ck(t2) and ck('main') and not ck('nope')


def test_passkey_auth_only_this_device(tmp_path):
    """面容 ID 解锁只列这台设备登记的通行密钥（审查 10）"""
    p = tmp_path / 'pk.json'
    p.write_text(json.dumps({'creds': [{'id': 'A', 'rp': 'h', 'dev': 'd1'}, {'id': 'B', 'rp': 'h', 'dev': 'd2'}]}), encoding='utf-8')
    with patch.object(passkey, 'CONF', str(p)):
        assert [c['id'] for c in passkey.auth_options('h', 'd1')['allowCredentials']] == ['A']
        try:
            passkey.verify({'id': 'B', 'clientDataJSON': '', 'authenticatorData': '', 'signature': ''}, 'd1')
            assert False
        except ValueError as e:
            assert '还没有开启' in str(e)


def test_size_alignment_16():
    """ComfyUI 生图按 16 对齐（审查 17）"""
    w, h = q21.size_for(1.0, 1040, 1040, 16)
    assert w % 16 == 0 and h % 16 == 0
