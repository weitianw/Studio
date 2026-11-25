"""遥控播放（studio/vaultrc.py：私密空间里电脑控制手机，手机在哪个空间都行）的中转规则。
跑：cd devtest && python -m pytest tests/unit/test_vaultrc.py"""
import io, os, sys, threading, time, wave

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)
import vaultrc  # noqa: E402

PC, PC2 = vaultrc.key_of('pc-vault-tok'), vaultrc.key_of('pc2-vault-tok')
PH, PH2 = 'dev-phone', 'dev-phone-2'
ITEMS = [{'key': 'lib:私密/a.mp3', 'title': '私密 A', 'sub': '私密', 'cover': '/media/cover/私密/a.mp3', 'url': '/media/lib/私密/a.mp3', 'pos': '私密/a.mp3', 'video': True},
         {'key': 'lib:私密/b.avi', 'title': '要转换的', 'url': '/media/lib/私密/b.avi', 'conv': True},
         {'key': 'job:1', 'title': '作品', 'url': '/media/job/1/output.mp3?t=5'}]


def setup_function(_):
    vaultrc.drop()


def _queue_for(dev, space):
    s = vaultrc.wait(dev, -1, space)['seq']
    assert vaultrc.send(PC, {'c': 'queue', 'items': ITEMS, 'i': 2})
    return vaultrc.wait(dev, s, space, timeout=0.2)['cmds']


def test_commands_need_arm():
    vaultrc.report(PH, {'title': 'x'}, 'v')
    assert vaultrc.send(PC, {'c': 'pause'}) is None  # 电脑没开启控制：命令不收
    vaultrc.arm(PC, True)
    assert vaultrc.send(PC2, {'c': 'pause'}) is None  # 别的电脑（另一个私密空间凭证）不能发
    assert vaultrc.send(PC, {'c': 'pause'})


def test_normal_space_phone_only_reports_when_armed():
    assert vaultrc.report(PH, {'title': '普通空间的歌'}, 'n')['armed'] is False
    assert vaultrc.view(PC)['phone'] is None  # 没开启控制：普通空间里放什么后台不记
    vaultrc.arm(PC, True)
    vaultrc.report(PH, {'title': '空白音频', 't': 1}, 'n')
    v = vaultrc.view(PC)
    assert v['armed'] and v['phone']['title'] == '空白音频' and v['phone']['space'] == 'n'


def test_vault_phone_reports_without_arm_and_state_cleaned():
    vaultrc.report(PH, {'title': '一首', 't': 12.5, 'd': 'NaN', 'paused': 0, 'evil': 'x', 'n': '3'}, 'v')
    v = vaultrc.view(PC)['phone']
    assert v['title'] == '一首' and v['t'] == 12.5 and v['paused'] is False and v['n'] == 3 and 'd' not in v and 'evil' not in v


def test_wait_wakes_on_command_and_on_arm_change():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    s = vaultrc.wait(PH, -1, 'n')['seq']
    got = {}

    def w(since):
        t0 = time.time(); got['r'] = vaultrc.wait(PH, since, 'n', True, timeout=5); got['dt'] = time.time() - t0
    th = threading.Thread(target=w, args=(s,)); th.start(); time.sleep(0.2)
    vaultrc.send(PC, {'c': 'seek', 'v': 30}); th.join(3)
    assert got['r']['cmds'] == [{'c': 'seek', 'v': 30.0, 'seq': s + 1}] and got['dt'] < 1.5
    th = threading.Thread(target=w, args=(s + 1,)); th.start(); time.sleep(0.2)
    vaultrc.arm(PC, False); th.join(3)  # 电脑关掉控制：等着的手机马上知道
    assert got['r']['armed'] is False and got['dt'] < 1.5


def test_normal_space_queue_is_tokenized_and_anonymous():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    c = _queue_for(PH, 'n')[0]
    assert [x['title'] for x in c['items']] == [vaultrc.RC_TITLE] * 2 and c['i'] == 1  # 要转换的那首跳过，点的那首位置跟着挪
    blob = repr(c)
    assert '私密' not in blob and 'lib:' not in blob and 'cover' not in blob and 'pos' not in blob and "'video': True" not in blob
    u = c['items'][0]['url']
    assert u.startswith('/api/rc/m/') and u.endswith('/a.mp3')
    tok = u.split('/')[4]
    assert vaultrc.media(tok, PH) == '/media/lib/私密/a.mp3'
    assert vaultrc.media(tok, PH2) is None  # 只给这台手机
    assert vaultrc.media(c['items'][1]['url'].split('/')[4], PH) == '/media/job/1/output.mp3?t=5'
    vaultrc.arm(PC, False)
    assert vaultrc.media(tok, PH) is None  # 电脑关掉控制：全部作废


def test_vault_space_queue_keeps_real_items():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'v')
    c = _queue_for(PH, 'v')[0]
    assert c['items'][0]['title'] == '私密 A' and c['items'][0]['url'] == '/media/lib/私密/a.mp3' and c['i'] == 2


def test_hand_off_when_leaving_vault():
    assert vaultrc.hand(PH, ITEMS, 0) is None  # 电脑没开着控制：不给
    vaultrc.arm(PC, True)
    r = vaultrc.hand(PH, ITEMS, 2)
    assert len(r['items']) == 2 and r['i'] == 1 and '私密' not in repr(r)


def test_arm_expires_and_disarm_on_vault_exit(monkeypatch):
    vaultrc.arm(PC, True)
    assert vaultrc.view(PC)['armed']
    real = time.time
    monkeypatch.setattr(vaultrc.time, 'time', lambda: real() + vaultrc.ARM_TTL + 1)
    assert not vaultrc.view(PC)['armed']  # 电脑页面关了、很久没来问：当成关掉了
    monkeypatch.setattr(vaultrc.time, 'time', real)
    vaultrc.arm(PC, True); vaultrc.disarm_owner(PC2)
    assert vaultrc.view(PC)['armed']  # 别的电脑退出私密空间不影响
    vaultrc.disarm_owner(PC)
    assert not vaultrc.view(PC)['armed']


def test_old_commands_dropped_and_other_phone_gets_nothing(monkeypatch):
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'v')
    s = vaultrc.wait(PH, -1, 'v')['seq']
    vaultrc.send(PC, {'c': 'next'})
    assert vaultrc.wait(PH2, s, 'v', timeout=0.1)['cmds'] == []
    real = time.time
    monkeypatch.setattr(vaultrc.time, 'time', lambda: real() + vaultrc.CMD_TTL + 1)
    assert vaultrc.wait(PH, s, 'v', timeout=0.1)['cmds'] == []


def test_normal_space_gets_no_commands_after_disarm():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    s = vaultrc.wait(PH, -1, 'n')['seq']
    vaultrc.send(PC, {'c': 'next'})
    vaultrc.arm(PC, False)
    assert vaultrc.wait(PH, s, 'n', timeout=0.1)['cmds'] == []


def test_bad_commands_and_foreign_urls_rejected():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'v')
    for bad in ({'c': 'rm'}, {'c': 'seek'}, {'c': 'seek', 'v': 'nan'}, {'c': 'queue', 'items': []},
                {'c': 'queue', 'items': [{'url': 'https://evil.example/a.mp3'}, {'url': '//evil/b'}]}):
        try:
            vaultrc.send(PC, bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert vaultrc._mint('/api/settings', PH) is None and vaultrc._mint('/media/lib/../x', PH) is None  # 一次性地址只能指向播放文件


def test_silence_is_valid_wav():
    with wave.open(io.BytesIO(vaultrc.silence_wav())) as w:
        assert w.getnchannels() == 1 and w.getframerate() == 8000 and w.getnframes() == 80000
        assert set(w.readframes(100)) == {0x80}


def test_pc_sees_names_of_tokenized_items():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    c = _queue_for(PH, 'n')[0]
    vaultrc.report(PH, {'rc': True, 'i': c['i'], 't': 3}, 'n')
    v = vaultrc.view(PC)['phone']
    assert v['title'] == '作品' and v['t'] == 3  # 电脑上显示真名（手机那边只有“电脑控制播放”）
    assert vaultrc.view(PC2)['phone'].get('title') is None  # 别的电脑看不到名字


def test_queue_for_pc_and_jump():
    vaultrc.arm(PC, True)
    vaultrc.report(PH, {'title': 'a', 'qv': 1, 'subsKey': 'lib:私密/a.mp3'}, 'v')
    vaultrc.report(PH, {'title': 'a', 'qv': 1, 'queue': [{'title': '一', 'sub': 's', 'url': '/x'}, {'title': '二'}]}, 'v')
    assert vaultrc.queue(PC) == {'items': [{'title': '一', 'sub': 's'}, {'title': '二'}]}  # 只留名字
    assert vaultrc.queue(PC2) == {'items': []}  # 别的电脑看不到
    s = vaultrc.wait(PH, -1, 'v')['seq']
    vaultrc.send(PC, {'c': 'jump', 'v': 1})
    assert vaultrc.wait(PH, s, 'v', timeout=0.1)['cmds'][0] == {'c': 'jump', 'v': 1, 'seq': s + 1}
    for bad in ({'c': 'jump'}, {'c': 'jump', 'v': -1}):
        try:
            vaultrc.send(PC, bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_queue_names_when_phone_in_normal_space():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    c = _queue_for(PH, 'n')[0]
    vaultrc.report(PH, {'rc': True, 'i': 0, 'queue': [{'title': vaultrc.RC_TITLE}] * 2}, 'n')
    assert [x['title'] for x in vaultrc.queue(PC)['items']] == ['私密 A', '作品']  # 电脑上是真名
    v = vaultrc.view(PC)['phone']
    assert v['key'] == 'lib:私密/a.mp3' and 'subsKey' not in v  # 收藏用的 key 有；这首没给字幕标识
    assert '私密' not in repr(c)  # 手机那边还是什么都没有


def test_arm_clears_long_gone_phone(monkeypatch):
    vaultrc.report(PH, {'title': 'a'}, 'v')
    real = time.time
    monkeypatch.setattr(vaultrc.time, 'time', lambda: real() + vaultrc.FRESH * 4 + 1)
    vaultrc.arm(PC, True)
    assert vaultrc.view(PC)['phone'] is None  # 上一次的手机早就没动静：当成还没有手机（显示“等待手机播放”）


def test_disarm_drops_rc_state():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'rc': True, 'i': 0}, 'n')
    vaultrc.arm(PC, False); vaultrc.arm(PC, True)
    assert vaultrc.view(PC)['phone'] is None  # 关掉控制时手机上电脑发去的就停了：重新开启后不再显示它


def test_near_when_a_phone_is_playing_without_details(monkeypatch):
    assert vaultrc.view(PC)['near'] is False
    vaultrc.wait(PH, -1, 'n', playing=True)  # 普通空间的手机在放、来等命令
    v = vaultrc.view(PC)
    assert v['near'] is True and v['phone'] is None  # 只知道“有手机在放”，不知道放的是什么
    vaultrc.wait(PH2, -1, 'n', playing=False)
    assert vaultrc.view(PC)['near'] is True  # 没在放的那台不算，前一台还在
    real = time.time
    monkeypatch.setattr(vaultrc.time, 'time', lambda: real() + vaultrc.WAIT + 6)
    assert vaultrc.view(PC)['near'] is False


def test_keep_error_reaches_pc():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a', 'paused': True, 'kerr': 'NotAllowedError'}, 'v')
    assert vaultrc.view(PC)['phone']['kerr'] == 'NotAllowedError'  # 手机暂停时无声音频没放出来：电脑能看到原因


def test_resume_passes_through_as_number_only():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'n')
    s = vaultrc.wait(PH, -1, 'n')['seq']
    vaultrc.send(PC, {'c': 'queue', 'i': 0, 'items': [{'key': 'lib:私密/a.mp3', 'url': '/media/lib/私密/a.mp3', 'resume': 42},
                                                    {'key': 'lib:私密/b.mp3', 'url': '/media/lib/私密/b.mp3', 'resume': '/evil'},
                                                    {'key': 'lib:私密/c.mp3', 'url': '/media/lib/私密/c.mp3', 'resume': True}]})
    items = vaultrc.wait(PH, s, 'n', timeout=0.1)['cmds'][0]['items']
    assert items[0]['resume'] == 42 and 'resume' not in items[1] and 'resume' not in items[2]  # 只带秒数；别的都丢掉


def test_wait_started_in_vault_but_left_gets_tokens():
    vaultrc.arm(PC, True); vaultrc.report(PH, {'title': 'a'}, 'v')
    s = vaultrc.wait(PH, -1, 'v')['seq']
    still = {'v': True}
    got = {}
    th = threading.Thread(target=lambda: got.setdefault('r', vaultrc.wait(PH, s, 'v', True, timeout=5, vok=lambda: still['v'])))
    th.start(); time.sleep(0.2)
    still['v'] = False  # 请求挂着的时候手机退出了私密空间
    vaultrc.send(PC, {'c': 'queue', 'items': ITEMS, 'i': 0}); th.join(3)
    c = got['r']['cmds'][0]
    assert c['items'][0]['url'].startswith('/api/rc/m/') and '私密' not in repr(c)  # 按普通空间发：一次性地址，不带名字
