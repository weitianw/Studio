r"""改衣的公用小工具（原来“整体重绘”的那一套，整体重绘 2026-11-04 删掉了，剩下还在用的）：
- edit_prompt：给 Qwen 指令改图的“只换衣服”指令（参考生成、保真替换、参考编辑都用）
- cloth_only：衣服图里常有模特，先用 SAM3 只抠出衣服贴在白底上
- landmarks：逐帧人脸关键点（facelmk.py，用 ComfyUI 自带的 Python 跑；参考生成挑一帧脸清楚的画面用）"""
import os, subprocess

import numpy as np
from PIL import Image

import videogen as V

LMK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'facelmk.py')
SAM = 'sam3.1_multiplex_fp16.safetensors'



# 2026-11-08 A/B：背对镜头的一帧以前被 Qwen 画成正面（有脸）、帽子和双马尾都改了，视频照着画就“背面出现脸、帽子没了”；写了这句后背面保持、帽子鞋袜都在
# 11-08 的写法（留着对照）：点名“背对镜头”“帽子、袜子和鞋”，正面近景时 Qwen 反而画成背面、加帽子和丝袜（11-09 夜测 2 个种子都这样），改成不点名的说法
KEEP_FACING_V1108 = '保持原图里每个人的身体朝向和姿势不变：背对镜头的人继续背对镜头，不要转过身来，不要画出脸。'
KEEP_POSE_V1108 = KEEP_FACING_V1108 + '帽子、发型、饰品、袜子和鞋都照原样保留（上面要求更换的除外）。'
KEEP_FACING = '身体朝向、姿势和取景都和原图完全一样，不要转身，不要改变构图。'
KEEP_POSE = KEEP_FACING + '原图里已有的配饰照原样保留（上面要求更换的除外），不要添加原图里没有的东西。'  # 换衣用


# 2026-11-09 正向写法（videoedit.POS 打开时用）：只写想要的样子，不出现“转身 / 背对 / 帽子袜子鞋 / 晒黑发黄 / 图 2 的人”这些原图里没有或想去掉的东西
KEEP_FACING_POS = '身体朝向、姿势、取景和构图都和原图完全一样，人物在画面中的大小和位置也和原图一样。'
KEEP_POSE_POS = KEEP_FACING_POS + '原图里的配饰照原样保留（上面要求更换的除外）。'


# 11-09 测试（docs/AB测试/正向提示词_1109，同一帧两个种子）：“只改变衣服，其余全部保持原图的样子：……朝向……取景范围都与原图完全相同”
# 背面那帧两张都保持背面、正面近景两张都保持正面；带“不要转身”的写法把正面近景转成了侧背面，第一版正向写法（KEEP_POSE_POS）背面那帧回头露脸
_REST_POS = '其余全部保持原图的样子：人物的姿势、身体和头的朝向、脸、发型、{acc}身材、表情、背景、光线和取景范围都与原图完全相同。'


# 2026-11-09 模板套：Qwen 改图那句的两种写法登记到 tplstore（用户可以基于内置的新建、修改），两套内置写法的文字和以前拼出来的逐字相同
_QE_POS = {
    'QE_CLOTH': '只改变图 1 里{who}的衣服：换上{look}，只使用图 2 里的衣服本身。图 1 的人还是同一个人、同样的性别。' + _REST_POS.format(acc='配饰、').replace('原图', '图 1 '),
    'QE_OUTFIT': '只改变{who}的衣服：衣服换成{user}。' + _REST_POS.format(acc='配饰、'),
}
_QE_V1108 = {
    'QE_CLOTH': '图 1 里{who}换上{look}，换掉原来的衣服。只拿图 2 的衣服，不要图 2 里的人、脸和头发。'
                '图 1 的人保持原样：同一个人、同样的性别、脸、发型、身材、姿势和表情，背景、光线和镜头都和图 1 一模一样。' + KEEP_POSE,
    'QE_OUTFIT': '把{who}的衣服换成{user}。' + KEEP_POSE + '人、脸、发型、身材、姿势、表情、背景、光线和镜头都不变，只换衣服。',
}
_QS = {'who': '要改的人（“画面里的人”或填写的目标）', 'user': '提示词框里写的衣服', 'look': '“图 2 里的那件衣服（写的描述）”'}
import tplstore
for _k, _g, _l, _n, _pg, _sl in [('qe_outfit', '换衣', 'Qwen 改图', 'QE_OUTFIT', ['vedit'], ('who', 'user')), ('qe_cloth', '换衣', 'Qwen 改图 · 衣服图', 'QE_CLOTH', ['vedit'], ('who', 'look'))]:
    tplstore.register(_pg, _k, _l, [(_n, 'zh')], {'pos': {_n: _QE_POS[_n]}, 'v1108': {_n: _QE_V1108[_n]}}, {x: _QS[x] for x in _sl}, _g)


def edit_prompt(user, target, has_cloth_img):
    """给 Qwen 指令改图的那句：按情况选一份模板（当前空间默认的那套），把占位符换掉"""
    import videoedit
    who = target or '画面里的人'
    if has_cloth_img:  # 衣服图里常常有模特：要说清楚只拿衣服（2026-11-03 测过，不说的话会把图 2 的人连长发一起换过来）
        return tplstore.fmt(tplstore.T('QE_CLOTH'), who=who, look='图 2 里的那件衣服' + (f'（{user}）' if user else ''))
    return tplstore.fmt(tplstore.T('QE_OUTFIT'), who=who, user=user)


def cloth_only(img_name, out_prefix, w, h, work_out):
    """衣服图里常常有模特：Qwen 会把那个人（连长发）也换过来。先用 SAM3 只抠出衣服、贴在白底上（视频引擎这时开着），返回 PNG 字节；抠不到就返回 None"""
    import json as _json, time as _time, uuid as _uuid
    wf = {'l': {'class_type': 'LoadImage', 'inputs': {'image': img_name}},
          's': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM}},
          't': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['s', 1], 'text': 'clothing:4, shoes:2'}},
          'd': {'class_type': 'SAM3_Detect', 'inputs': {'model': ['s', 0], 'image': ['l', 0], 'conditioning': ['t', 0], 'threshold': 0.35, 'refine_iterations': 2, 'individual_masks': False}},
          'e': {'class_type': 'EmptyImage', 'inputs': {'width': w, 'height': h, 'batch_size': 1, 'color': 0xFFFFFF}},
          'c': {'class_type': 'ImageCompositeMasked', 'inputs': {'destination': ['e', 0], 'source': ['l', 0], 'x': 0, 'y': 0, 'resize_source': False, 'mask': ['d', 0]}},
          'o': {'class_type': 'SaveImage', 'inputs': {'images': ['c', 0], 'filename_prefix': out_prefix}},
          'mi': {'class_type': 'MaskToImage', 'inputs': {'mask': ['d', 0]}},
          'mo': {'class_type': 'SaveImage', 'inputs': {'images': ['mi', 0], 'filename_prefix': out_prefix + '_m'}}}
    pid = V._submit(wf, _uuid.uuid4().hex)
    t0, hst = _time.time(), {}
    while _time.time() - t0 < 300:
        _time.sleep(1)
        h_ = V._history(pid, hst)
        if isinstance(h_, dict) and pid in h_ and (h_[pid].get('status') or {}).get('completed') is not None:
            outs = h_[pid].get('outputs') or {}
            fs = {k: [os.path.join(work_out, x.get('subfolder', ''), x['filename']) for x in (outs.get(k) or {}).get('images', [])] for k in ('o', 'mo')}
            data, area = None, 0.0
            if fs['mo']:
                area = float((np.array(Image.open(fs['mo'][0]).convert('L')) > 127).mean())
            if fs['o'] and area > 0.01:
                with open(fs['o'][0], 'rb') as fh:
                    data = fh.read()
            for f in fs['o'] + fs['mo']:
                try:
                    os.remove(f)
                except OSError:
                    pass
            return data
    V._drop(pid)  # 超时：引擎里这一单也取消（2026-11-16 审查）
    return None



def landmarks(*pairs):
    """[(视频或图片, 输出.npz), ...] → 用 ComfyUI 自带的 Python 跑 facelmk.py；返回每个的 xy（帧, 478, 2）"""
    args = [x for p in pairs for x in p]
    r = subprocess.run([V.COMFY_PY, '-I', LMK, *args], capture_output=True, text=True, creationflags=V.NO_WINDOW, timeout=900)
    if r.returncode:
        raise RuntimeError('脸部关键点检测失败：' + (r.stderr or '')[-300:])
    out = []
    for _, npz in pairs:
        d = np.load(npz)
        out.append((d['xy'], tuple(int(v) for v in d['size'])))
    return out


