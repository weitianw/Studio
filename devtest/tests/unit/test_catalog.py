"""开源泛化 ②：模型目录（studio/catalog.py）。
- 没有用户模型时，q21 的表和以前写死的一样（另有 test：工作流也一样）
- user-models.json 可以加模型（选已有的 family、给文件）、改已有模型的几项、藏起来
- 通用 Checkpoint（SD 1.5 / SDXL）走 ComfyUI 默认的文生图工作流；LoRA 同时接模型和文本编码器
- imagegen.reload_models() 之后网页上就有新模型（不用重启）"""
import json, os, sys
import pytest

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)
import catalog, q21, imagegen  # noqa: E402

BUILTIN = ['q21-fast', 'q21', 'moss', 'moss-photo', 'krea2', 'h3img', 'zit-official', 'zit-diving']


@pytest.fixture
def user_file(tmp_path, monkeypatch):
    p = tmp_path / 'user-models.json'
    monkeypatch.setattr(catalog, 'USER_FILE', str(p))
    yield p
    monkeypatch.undo()
    imagegen.reload_models()


def test_builtin_catalog_order_and_tables():
    c = catalog.load('image')
    assert [k for k, m in c['models'].items() if m['source'] == 'builtin'][:8] == BUILTIN
    assert 'ckpt' in c['families'] and c['families']['ckpt']['loader'] == 'checkpoint'
    assert q21.FAMILY['moss-photo'] == 'moss' and q21.SETTINGS['moss-photo']['txt']['slg'] == ('22', 0.0, 0.5)
    assert q21.MODELS['moss-photo']['fixed_loras'][0] == ('MOSS\\feverdream-epoch-07.safetensors', 0.45)


def test_user_models_add_override_hide(user_file):
    user_file.write_text(json.dumps({'image': [
        {'id': 'u-sdxl', 'name': 'My SDXL', 'family': 'ckpt', 'unet': 'sdxl\\juggernaut.safetensors'},
        {'id': 'u-zit', 'name': 'My Z-Image finetune', 'family': 'zimg', 'unet': 'Z_Image\\mine.safetensors', 'vae': 'Z_Image\\my_vae.safetensors'},
        {'id': 'krea2', 'tag': 'renamed tag'},
        {'id': 'zit-diving', 'hidden': True},
        {'id': 'u-bad', 'name': 'no family', 'family': 'nope', 'unet': 'x.safetensors'},
    ]}), encoding='utf-8')
    n = imagegen.reload_models()
    assert 'u-sdxl' in imagegen.MODELS and 'u-zit' in imagegen.MODELS and 'u-bad' not in imagegen.MODELS
    assert 'zit-diving' not in imagegen.MODELS and q21.MODELS['krea2']['tag'] == 'renamed tag'
    assert q21.MODELS['u-sdxl']['source'] == 'user' and q21.MODELS['u-sdxl']['modes'] == ['txt']
    assert q21.SETTINGS['u-sdxl']['txt']['sampler'] == 'dpmpp_2m'            # family 的默认设置
    assert q21.SETTINGS['u-zit']['txt'] == q21.SETTINGS['zit-official']['txt']  # 同 family 第一个模型的设置
    assert q21.txt_files('u-zit')['vae'] == 'Z_Image\\my_vae.safetensors' and q21.txt_files('u-zit')['type'] == 'lumina2'
    assert n == len(q21.MODELS)


def test_checkpoint_workflow(user_file):
    user_file.write_text(json.dumps({'image': [{'id': 'u-sd', 'name': 'SD', 'family': 'ckpt', 'unet': 'sd15.safetensors'}]}), encoding='utf-8')
    imagegen.reload_models()
    st = dict(q21.SETTINGS['u-sd']['txt'], negative='blurry')
    wf = q21.wf_ckpt('u-sd', 'a cat', 5, 768, 512, st, 'p', [('style.safetensors', 0.7)])
    assert wf['ck']['inputs']['ckpt_name'] == 'sd15.safetensors'
    assert wf['lo0']['class_type'] == 'LoraLoader' and wf['lo0']['inputs']['clip'] == ['ck', 1]
    assert wf['k']['inputs']['model'] == ['lo0', 0] and wf['p']['inputs']['clip'] == ['lo0', 1]
    assert wf['n']['inputs']['text'] == 'blurry' and wf['d']['inputs']['vae'] == ['ck', 2]
    assert wf['lat']['inputs']['width'] == 768 and q21.lora_sub('u-sd') == ''
    assert any('checkpoints' in x for x in q21.missing('u-sd'))


def test_no_user_file_means_builtin_only(user_file):
    imagegen.reload_models()
    assert [k for k in q21.MODELS] == BUILTIN
