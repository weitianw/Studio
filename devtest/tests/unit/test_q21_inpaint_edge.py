"""Qwen 2.1 局部重画的边缘处理和“参考图先提取衣服”（2026-11-16 A/B：docs/AB测试/局部重画边缘_1116）。不用显卡。
跑：cd devtest && python -m pytest"""
import os, sys, io

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)


def _mask(path, size, box):
    from PIL import Image
    m = Image.new('L', size, 0); m.paste(255, box); m.save(path)
    return str(path)


def test_auto_grow_follows_latent_cell_size(tmp_path):
    """外扩 ≈ 2.2 格潜空间格子：涂抹范围大（裁剪缩小）外扩多，范围小（裁剪放大）外扩少；最少 4、最多 96"""
    import q21
    st = q21.SETTINGS['q21']['inpaint']
    big = q21.auto_grow(_mask(tmp_path / 'b.png', (3584, 4779), (1360, 2230, 2216, 4101)), st)  # 和 A/B 那张一样大的整件泳衣
    assert 28 <= big <= 36  # A/B 里最好的是 32
    small = q21.auto_grow(_mask(tmp_path / 's.png', (3584, 4779), (1600, 2300, 2100, 2700)), st)
    assert 4 <= small < big
    assert q21.auto_grow(_mask(tmp_path / 't.png', (512, 512), (10, 10, 20, 20)), st) == 4
    assert q21.auto_grow(_mask(tmp_path / 'e.png', (512, 512), (0, 0, 0, 0)), st) == 0  # 没涂


def test_wf_local_edge_options():
    """hard：灰色只盖涂抹处（ThresholdMask）；dd：采样前接 Differential Diffusion；grow：裁剪节点先外扩"""
    import q21
    st = q21.SETTINGS['q21']['inpaint']
    old = q21.wf_local('q21', 'src.png', 'm.png', [], 'p', 1, st, 'pre')
    assert old['gm']['inputs']['mask'] == ['cr', 2] and 'dd' not in old and old['cr']['inputs']['mask_expand_pixels'] == 0 and 'gw' not in old
    new = q21.wf_local('q21', 'src.png', 'm.png', [], 'p', 1, st, 'pre', edge=('hard', 'dd', 'grow'), grow=32)
    assert new['hm']['class_type'] == 'ThresholdMask' and new['gm']['inputs']['mask'] == ['hm', 0]
    assert new['dd']['class_type'] == 'DifferentialDiffusion' and new['k']['inputs']['model'] == ['dd', 0]
    assert new['gw']['class_type'] == 'GrowMask' and new['gw']['inputs']['expand'] == 32 and new['cr']['inputs']['mask'] == ['gw', 0]
    assert new['cr']['inputs']['mask_expand_pixels'] == 0 and new['cr']['inputs']['mask_blend_pixels'] == 32  # 裁剪节点的 expand 不是真像素数，别用


def test_extract_refs_caches_and_overwrites(monkeypatch, tmp_path):
    """参考图先提取衣服：图 2 换成提取结果（铺白底），同一张图第二次不再跑"""
    import q21
    from PIL import Image
    (tmp_path / 'in').mkdir(); (tmp_path / 'out').mkdir()
    monkeypatch.setitem(q21.V.WORK, 'n', str(tmp_path))
    monkeypatch.setattr(q21, '_XCACHE', {})
    saved = []
    monkeypatch.setattr(q21, 'FIND_EXTRACT', lambda j, key, sha1: None)
    monkeypatch.setattr(q21, 'SAVE_EXTRACT', lambda j, png, meta: saved.append(meta))
    Image.new('RGB', (300, 500), (200, 120, 100)).save(tmp_path / 'in' / 'ref2.png')
    calls = []

    def fake_submit(j, wf, label):
        calls.append(wf)
        assert wf['e']['inputs']['prompt'] == q21.X_PROMPT and '衣服' in label
        im = Image.new('RGBA', (320, 512), (10, 20, 30, 0)); im.paste((240, 230, 220, 255), (100, 100, 220, 400))
        im.save(tmp_path / 'out' / 'x.png')
        return {'o': {'images': [{'filename': 'x.png', 'subfolder': ''}]}}
    monkeypatch.setattr(q21, '_submit', fake_submit)
    j = {'cancel': False}
    q21.extract_refs(j, 'q21', ['src.png', 'ref2.png'], str(tmp_path / 'in'))
    out = Image.open(tmp_path / 'in' / 'ref2.png').convert('RGB')
    assert out.size == (320, 512) and out.getpixel((5, 5)) == (255, 255, 255) and out.getpixel((150, 200)) == (240, 230, 220)  # 透明处铺白
    assert len(calls) == 1 and j['ref_extracted'] == 1 and not list((tmp_path / 'out').glob('*.png'))
    Image.new('RGB', (300, 500), (200, 120, 100)).save(tmp_path / 'in' / 'ref2.png')  # 同一张参考图再来一次
    q21.extract_refs(j, 'q21', ['src.png', 'ref2.png'], str(tmp_path / 'in'))
    assert len(calls) == 1 and Image.open(tmp_path / 'in' / 'ref2.png').size == (320, 512)
    assert len(saved) == 1 and saved[0]['w'] == 320 and len(saved[0]['sha1']) == 40  # 提取出来的存进图库，只存一次


def test_default_edge_on_for_q21_inpaint():
    """网页的请求不带 inp_edge：局部重画默认 hard + dd + grow；测试请求带 [] 时是旧做法"""
    import q21
    assert set(q21.EDGE_DEFAULT) == {'hard', 'dd', 'grow'}
    src = open(os.path.join(STUDIO, 'imagegen.py'), encoding='utf-8').read()
    assert "if isinstance(b.get('inp_edge'), list) else list(q21.EDGE_DEFAULT)" in src


def test_extract_saved_to_gallery_and_reused(monkeypatch, tmp_path):
    """提取出来的衣服进这个空间的图库（kind = extract），普通空间再放进素材库；图库里有就直接用（重启后也不再提取）；私密空间不进素材库"""
    import imagegen, q21
    monkeypatch.setattr(imagegen, 'DIRS', {'n': str(tmp_path / 'n'), 'v': str(tmp_path / 'v')})
    links = []
    monkeypatch.setattr(imagegen, 'MATS_LINK', lambda src, name: links.append((src, name)))
    monkeypatch.setattr(imagegen, 'act', lambda *a, **k: None)
    png = b'PNG fake bytes'
    for sp in ('pub', 'v'):
        j = {'space': sp, 'model': 'q21', 'model_name': 'Qwen 2.1', 'id': 'job1'}
        rec = imagegen.save_extract(j, png, {'sha1': 'a' * 40, 'w': 10, 'h': 20, 'sec': 1.0})
        assert rec['kind'] == 'extract' and any(x['id'] == rec['id'] for x in imagegen.gallery(sp))
        assert imagegen.find_extract(j, 'q21', 'a' * 40) == png and imagegen.find_extract(j, 'q21-fast', 'a' * 40) is None
    assert len(links) == 1 and links[0][1].endswith('.png')  # 只有普通空间放进素材库
    assert q21.SAVE_EXTRACT is imagegen.save_extract and q21.FIND_EXTRACT is imagegen.find_extract
