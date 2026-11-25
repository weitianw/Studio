"""接口冒烟测试：对正在运行的测试 Studio（devtest/run.py，默认 --profile gpu，端口 STUDIO_TEST_PORT=7897）。不用显卡、不生成。
跑：python -I devtest/run.py --profile gpu（另一个窗口）→ cd devtest && python -m pytest tests/api"""
import json, os, re, urllib.error, urllib.request
import pytest

pytestmark = pytest.mark.api
B = 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897')
_op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {},
                               method='POST' if body is not None else 'GET')
    try:
        return json.loads(_op.open(r, timeout=60).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {'_code': e.code, **json.loads(e.read().decode('utf-8') or '{}')}
    except urllib.error.URLError:
        pytest.skip(f'测试 Studio 没开（{B}）')


def test_video_status():
    st = call('/api/video/status')
    assert st['edit']['ok'] and 'motion' in st['edit']['tasks']


def preview(edit, prompt='衣服换成白色连衣裙'):
    return call('/api/video/prompt-preview', {'model': 'h3', 'prompt': prompt, 'prompt_input': prompt, 'has_ref': True, 'seconds': 5, 'edit': edit})


def test_preview_motion_is_not_swap():
    t = preview({'task': 'motion', 'tpl': True})
    assert 'body_swap' not in t['stages'][-1]['text']  # 以前动作迁移的预览当成换人


def test_preview_head_default_is_faceswap():
    t = preview({'task': 'head', 'tpl': True})
    assert t['stages'][-1]['text'].strip() == 'Faceswap'


def test_preview_outfit_viggle():
    t = preview({'task': 'outfit', 'method': 'ref', 'tpl': True, 'vg': True, 'own': False}, '衣服换成红色连衣裙')
    assert [s['label'] for s in t['stages']][-2:] == ['参考图改图', '视频生成'] and '红色连衣裙' in t['stages'][-1]['text']


def test_vram_panel_lists_items():
    v = call('/api/vram')
    assert 'items' in v


def test_segpref_status():
    s = call('/api/video/segpref')
    assert s['use'] in ('rule', 'learned') and 'videos' in s


def test_agent_list_has_no_names():
    r = call('/api/agent/list_videos', {'source': 'materials', 'limit': 20})
    txt = json.dumps(r, ensure_ascii=False)
    assert r['videos'] and all(re.fullmatch(r'v_[0-9a-f]{10}', v['id']) for v in r['videos'])
    assert '.mp4' not in txt and '@' not in txt


def test_agent_unknown_handle():
    r = call('/api/agent/cutpoints', {'video': 'v_0000000000'})
    assert r.get('_code') == 400 and '代号' in r['error']


def test_batch_recipes_listed():
    r = call('/api/batch/recipes')
    if r.get('_code') == 404:
        pytest.skip('批量配方还没有')
    assert isinstance(r.get('recipes'), list) and r['recipes']
