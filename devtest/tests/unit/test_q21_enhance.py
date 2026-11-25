"""Qwen 2.1 提示词增强：小模型输出的解析、增强用哪个模型、AI 助手写提示词。
跑：cd devtest && python -m pytest"""
import os, sys

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)

P = '将输入图片中的女生上衣换成白色吊带，保留脸和发型，光影不变，背景不变，构图不变，其余保持一致。'


def test_parse_enhanced_unwraps_any_json_key():
    import q21
    for raw in ('{"rewritten_prompt": "%s", "x": "y"}' % P,  # 官方
                '{"rewritten_instruction": "%s"}' % P,      # 偶尔换键
                '{"output": "%s"}' % P,
                '{"答案": "%s"}' % P,
                '{"output": "%s' % P,                         # 没写完的 JSON
                P):
        assert q21.parse_enhanced(raw) == (P, '')


def test_parse_enhanced_still_flags_refusal():
    import q21
    assert q21.parse_enhanced('我不能执行这条编辑指令，因为涉及真实人物。')[1] == 'refused'


def test_pe_set_official_only():
    import q21
    assert q21.pe_set({'enhance': 'pe'}) == 'official'
    assert q21.pe_set({'enhance': 'pe', 'pe_model': 'bogus'}) == 'official'
    assert q21.pe_set({'enhance': 'ai'}) == 'official'  # 助手直接写不用增强模型（这里返回什么都不跑）
    assert q21.ENHANCE == ('off', 'pe', 'ai') and set(q21.WITH_AI) == {'ai'} and list(q21.PE_SETS) == ['official']


def _fake_run(monkeypatch, tmp_path, enh, pe_raw='', mode='edit', mask=False, reply=None):
    """跑一次 prepare_prompt：增强模型和 AI 助手都换成假的，返回 (结果, 增强被调用的次数, AI 助手收到的消息)"""
    import q21
    from PIL import Image
    Image.new('RGB', (64, 64), 'white').save(tmp_path / 'src.png')
    calls, got = {'pe': 0}, {}

    def fake_enhance(*a, **k):
        calls['pe'] += 1
        return pe_raw
    monkeypatch.setattr(q21, '_enhance', fake_enhance)
    monkeypatch.setattr(q21, 'CHAT', lambda system, msg, imgs: got.update(msg=msg, n=len(imgs), system=system, imgs=imgs) or (reply if reply is not None else '在<image1>上，' + P))
    monkeypatch.setattr(q21, 'RELEASE', None)
    monkeypatch.setattr(q21.V.Engine, 'free', classmethod(lambda cls, keep_ram=False: None))
    monkeypatch.setattr(q21, 'LOG_DIR', None)
    j = {'prompt': '换成白色连衣裙', 'enhance': enh, 'seed': 1, 'space': 'pub', 'message': ''}
    if mask:  # 局部重画的遮罩：左半边涂了
        m = Image.new('L', (64, 64), 0); m.paste(255, (0, 0, 32, 64)); m.save(tmp_path / 'mask.png'); j['_mask_path'] = str(tmp_path / 'mask.png')
    hooks = {'release': lambda: None, 'take': lambda: True}
    out = q21.prepare_prompt(j, 'i2i', mode, ['src.png'], str(tmp_path), hooks, '测试')
    return out, calls['pe'], got


def test_ai_mode_skips_enhancer(monkeypatch, tmp_path):
    import q21
    (prompt, note, enh_text), n_pe, got = _fake_run(monkeypatch, tmp_path, 'ai')
    assert n_pe == 0                                  # 不跑增强模型
    assert got['n'] == 1 and '白色连衣裙' in got['msg']  # 看图、照原话写
    assert got['system'].startswith(q21._system('i2i')[:200])  # 用官方增强的整份写法
    assert prompt.startswith('在<image1>上') and note == ''


def test_official_refusal_note_names_enhancer(monkeypatch, tmp_path):
    (prompt, note, _e), n_pe, got = _fake_run(monkeypatch, tmp_path, 'pe', '我不能执行这条编辑指令。')
    assert n_pe == 1 and '官方增强拒绝了' in note and prompt == '换成白色连衣裙' and not got  # 拒绝时按原话生成，不用 AI 助手


def test_inpaint_ai_uses_own_system(monkeypatch, tmp_path):
    import q21
    (prompt, note, _e), n_pe, got = _fake_run(monkeypatch, tmp_path, 'ai', mode='inpaint', mask=True, reply='一件白色蕾丝吊带，贴身，肤色与周围一致')
    assert got['system'].startswith(q21.AI_INPAINT[:60]) and '<image1>' not in got['system']  # 局部重画单独一套，不用官方改图（会写保持项）的那份
    assert '红线' in got['msg'] and '白色连衣裙' in got['msg']
    assert prompt.startswith(q21.INPAINT_LEAD)  # 助手没写“灰色区域”时补上，否则模型照抄灰色
    import base64, io
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(got['imgs'][0].split(',', 1)[1]))).convert('RGB')
    l, r, edge = im.getpixel((8, 32)), im.getpixel((56, 32)), im.getpixel((31, 32))
    assert min(l) > 240  # 涂抹的左半边里面还是原图的颜色（2026-11-16：整块盖红色时助手把衣服当成粉色）
    assert edge[0] - edge[1] > 60  # 涂抹范围的边上是一圈红线
    assert min(r) > 240  # 没涂的右半边还是原图（白）


def test_inpaint_preview_outline_on_photo(tmp_path):
    import q21, base64, io
    from PIL import Image
    Image.new('RGB', (1280, 960), (230, 120, 160)).save(tmp_path / 'src.png')  # 粉色衣服：里面保持粉色，红线外侧有白边
    m = Image.new('L', (1280, 960), 0); m.paste(255, (400, 300, 900, 700)); m.save(tmp_path / 'mask.png')
    im = Image.open(io.BytesIO(base64.b64decode(q21._mask_preview(str(tmp_path / 'src.png'), str(tmp_path / 'mask.png')).split(',', 1)[1]))).convert('RGB')
    inside, red, white, far = im.getpixel((650, 500)), im.getpixel((400, 500)), im.getpixel((395, 500)), im.getpixel((100, 100))
    assert all(abs(a - b) < 12 for a, b in zip(inside, (230, 120, 160))) and all(abs(a - b) < 12 for a, b in zip(far, (230, 120, 160)))
    assert red[0] > 200 and red[1] < 80 and min(white) > 230


def test_inpaint_keeps_written_grey_lead(monkeypatch, tmp_path):
    (prompt, _n, _e), _p, got = _fake_run(monkeypatch, tmp_path, 'ai', mode='inpaint', reply='将图1中的灰色区域重画为一件白色蕾丝吊带')
    assert prompt == '将图1中的灰色区域重画为一件白色蕾丝吊带'  # 写了就不再加


def test_sam_select_flow(monkeypatch, tmp_path):
    """智能选取（不用显卡）：图没传过 → NeedImage；第一次点先找部件（存着），取包含这一点的最小一块；同一处 level+1 = 大一圈（点选整个物体，和已有的差不多就不另算）"""
    import base64, io, json, q21
    from PIL import Image
    (tmp_path / 'in').mkdir(); (tmp_path / 'out').mkdir()
    monkeypatch.setitem(q21.V.WORK, 'n', str(tmp_path))
    for f in ('ensure', 'cancel_later', 'free_later'):
        monkeypatch.setattr(q21.V.Engine, f, classmethod(lambda cls: None))
    runs = []

    def mask(box, name):
        m = Image.new('L', (1536, 768), 0); m.paste(255, box); m.save(tmp_path / 'out' / name); return {'filename': name, 'subfolder': ''}

    def fake_submit(wf, cid):
        runs.append(wf)
        if 't' in wf:  # 找部件：左上一块（“衣服”）、整个左半边（“人”）
            runs[-1]['_out'] = [mask((0, 0, 384, 384), 'p1.png'), mask((0, 0, 768, 768), 'p2.png')]
        else:  # 点选：整个画面（比部件都大）
            runs[-1]['_out'] = [mask((0, 0, 1536, 768), 'pt.png')]
        return 'pid%d' % len(runs)
    monkeypatch.setattr(q21.V, '_submit', fake_submit)
    monkeypatch.setattr(q21.V, '_history', lambda pid, hst: {pid: {'status': {'completed': True}, 'outputs': {'mo': {'images': runs[int(pid[3:]) - 1]['_out']}}}})
    with __import__('pytest').raises(q21.NeedImage):
        q21.sam_select('pub:x', .5, .5)
    b = io.BytesIO(); Image.new('RGB', (4000, 2000), 'white').save(b, 'PNG')
    r0 = q21.sam_select('pub:x', .1, .1, base64.b64encode(b.getvalue()).decode())
    assert len(runs) == 1 and 'SAM3_Detect' == runs[0]['d']['class_type'] and runs[0]['d']['inputs']['individual_masks'] is True
    assert abs(r0['area'] - .125) < .01 and r0['level'] == 0 and r0['levels'] == 3  # 还没点选过：多算一级（可能还有整个物体）； 最小的那块（左上）
    r1 = q21.sam_select('pub:x', .1, .1, level=1); assert abs(r1['area'] - .5) < .01 and len(runs) == 1  # 大一圈：部件里有，不用再跑
    r2 = q21.sam_select('pub:x', .1, .1, level=2); assert r2['area'] > .99 and r2['levels'] == 3 and len(runs) == 2  # 部件用完：点选整个物体
    pts = json.loads(runs[1]['p']['inputs']['value']); assert pts == [{'x': int(.1 * 1535), 'y': int(.1 * 767)}]  # 图先缩到最长边 1536
    r3 = q21.sam_select('pub:x', .9, .9); assert r3['area'] > .99  # 部件都不含这一点：直接点选
    assert not list((tmp_path / 'out').glob('*.png'))  # 用完的输出都删掉


def test_t2i_ai_default_official(monkeypatch, tmp_path):
    """文生图「助手直接写」默认照官方写法（11-16 用户：官方的更有美感）"""
    import q21
    monkeypatch.setattr(q21, '_enhance', lambda *a, **k: '')
    got = {}
    monkeypatch.setattr(q21, 'CHAT', lambda system, msg, imgs: got.update(system=system, msg=msg) or 'A photo of a woman.')
    monkeypatch.setattr(q21, 'RELEASE', None)
    monkeypatch.setattr(q21.V.Engine, 'free', classmethod(lambda cls, keep_ram=False: None))
    monkeypatch.setattr(q21, 'LOG_DIR', None)
    j = {'prompt': '前置自拍', 'enhance': 'ai', 'seed': 1, 'space': 'pub', 'message': ''}
    q21.prepare_prompt(j, 't2i', 'txt', [], str(tmp_path), {'release': lambda: None, 'take': lambda: True}, '测试')
    assert got['system'] == q21._system('t2i') and 'enh_ver' not in j


def test_t2i_ai_uses_action_breakdown(monkeypatch, tmp_path):
    """系统指令「文生图 · 助手直接写」选了版本「动作拆开写」：用 AI_T2I（夜测 W6）；详情里记下版本"""
    import q21, tplstore
    monkeypatch.setattr(tplstore, 'store', lambda sp: {'default': 'pos', 'sets': [], 'pick': {'img_ai_t2i': 'act'}})
    monkeypatch.setattr(q21, '_enhance', lambda *a, **k: '')
    got = {}
    monkeypatch.setattr(q21, 'CHAT', lambda system, msg, imgs: got.update(system=system, msg=msg) or '旁人拍摄的照片，一位二十岁出头的中国女生……')
    monkeypatch.setattr(q21, 'RELEASE', None)
    monkeypatch.setattr(q21.V.Engine, 'free', classmethod(lambda cls, keep_ram=False: None))
    monkeypatch.setattr(q21, 'LOG_DIR', None)
    j = {'prompt': '前置自拍', 'enhance': 'ai', 'seed': 1, 'space': 'pub', 'message': ''}
    p, note, _e = q21.prepare_prompt(j, 't2i', 'txt', [], str(tmp_path), {'release': lambda: None, 'take': lambda: True}, '测试')
    assert got['system'] == q21.AI_T2I and got['msg'].endswith('前置自拍') and p.startswith('旁人拍摄') and j['enh_ver'] == '动作拆开写'


def test_tpl_versions_and_own_edits(monkeypatch, tmp_path):
    """系统指令的版本：pick 存在空间里；自己建的套照抄的内置 / 旧内置 / 别的版本文字不算改过，真改过的优先"""
    import json, q21, tplstore
    f = tmp_path / 'templates.json'
    monkeypatch.setattr(tplstore, 'FILE', lambda sp: str(f))
    w = lambda p, d, indent=1: open(p, 'w', encoding='utf-8').write(json.dumps(d))
    off = q21._system('t2i')
    assert tplstore.get('n')['t']['IMG_AI_T2I'] == off and tplstore.get('n')['vers']['img_ai_t2i']['id'] == ''
    tplstore.op('n', {'op': 'pick', 'key': 'img_ai_t2i', 'ver': 'act'}, w)
    g = tplstore.get('n'); assert g['t']['IMG_AI_T2I'] == q21.AI_T2I and g['vers']['img_ai_t2i']['label'] == '动作拆开写'
    assert tplstore.listing('n')['pick'] == {'img_ai_t2i': 'act'}
    r = tplstore.op('n', {'op': 'create', 'base': 'pos', 'name': '我的'}, w); sid = r['id']
    tplstore.op('n', {'op': 'default', 'id': sid}, w)
    assert tplstore.get('n')['t']['IMG_AI_T2I'] == q21.AI_T2I and not tplstore.get('n')['vers']['img_ai_t2i']['own']  # 照抄的版本文字：跟着选的版本
    tplstore.op('n', {'op': 'pick', 'key': 'img_ai_t2i', 'ver': ''}, w)
    assert tplstore.get('n')['t']['IMG_AI_T2I'] == off and 'img_ai_t2i' not in tplstore.listing('n')['pick']
    tplstore.op('n', {'op': 'save', 'id': sid, 't': {'IMG_AI_T2I': ''}}, w)
    assert tplstore.get('n')['t']['IMG_AI_T2I'] == off  # 旧内置（空）不算改过
    tplstore.op('n', {'op': 'save', 'id': sid, 't': {'IMG_AI_T2I': '我自己的'}}, w)
    g = tplstore.get('n'); assert g['t']['IMG_AI_T2I'] == '我自己的' and g['vers']['img_ai_t2i']['own']
    import pytest
    with pytest.raises(ValueError):
        tplstore.op('n', {'op': 'pick', 'key': 'img_ai_t2i', 'ver': 'nope'}, w)
    k = next(k for k in tplstore.listing('n')['kinds'] if k['key'] == 'img_ai_t2i'); assert k['sys'] and [v['id'] for v in k['versions']] == ['', 'act']
