"""改视频：拿一段已有的视频换人、换头、改衣（MiniMax H3 的参考模式）。

- 换人：新版 = Alissonerdx Character Swap v1.1 作者配方；审美优先 = 参考生成（原视频当 <Video 1>、人物图当 <Picture 1>，秋叶写法，官方完整版）；
- 换头：UntMods 换脸 LoRA（官方精简 Ref2VA + 原视频当参考视频）。
- 改衣：参考生成（这里拼）。保真替换（Wan 2.2 Animate）、参考编辑（Bernini-R）2026-11-06 随 Wan 2.2 一起去掉了。
（2026-11-04 删掉：改衣的整体重绘 / 局部重绘、去人去物、单独的“自由修改”任务——自由修改现在是生视频里加特效编辑 LoRA + 引导视频）
工作流在这里拼好（ComfyUI API 格式），占位符（__SEED__ 等）和节点编号跟 h3_i2v.json 一样，videogen._run 照常处理采样参数、自选 LoRA、插帧、超分和保存。
"""
import json, math, os, re, subprocess, uuid

import videogen as V

FILES = {
    'vfx': 'loras/minimax_h3_vfx_edit_v1.0_r128.safetensors',
    # 2026-11-12：换人 · 新做法（Alissonerdx Character Swap v1.1）和动作迁移（同作者 Motion Transfer v1.0）的作者配方：
    # 官方精简 Ref2VA + 做法 LoRA 1.0 + DMD 8 步加速（drbaph）+ 原视频走 AddGuide（第 0 帧起）+ 人物图当 <Picture 1> + 作者的提示词模板
    'cs11': 'loras/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors',
    'motion': 'loras/minimax_h3_motion_transfer_v1.0_ref2va.safetensors',
    'dmd': 'loras/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors',
    # 2026-11-13 用户定：换头默认改用 UntMods 换脸 LoRA（夜测和参考脸相似度 0.48）：官方精简 Ref2VA + 原视频当参考视频 + 头像 + 触发词 Faceswap + 官方加速 8 步
    'faceswap': 'loras/SS_FaceSwap_MiniMax_H3_REF2VA.safetensors',
}
# 改衣 · Viggle 重拍（2026-11-13 接入，默认关）：Viggle 官方 Remake edit（H3 首帧版 + edit LoRA 合并的 int8）+ 它的节点包：
# Qwen 改好的那一帧钉在原来那一帧上，整段照着重拍；夜测光照最接近原视频（脸亮度差 0.7、背景 0.1；参考生成差 5.7 / 3.5）
VG_FILE = 'diffusion_models/viggle_remake_edit_pruned_int8_convrot.safetensors'
VG_NODES = 'ComfyUI-Viggle-Remake'
VG_SIGMAS = '1.0, 0.983607, 0.96, 0.923077, 0.857143, 0.705882, 0.0'  # 官方 edit 的 6 步
VG_MIN_FRAMES, VG_MAX_FRAMES = 90, 345  # 节点只接 17n+5、90~345 帧（约 3.8~14.4 秒）
HEAD_BY = ('fs',)  # 换头的做法：fs = UntMods 换脸 LoRA
FS_TPL = 'Faceswap'  # UntMods 模型页：单个触发词 Faceswap
# Viggle Remake 的六段式提示词（PROMPTING.md：写成目标视频的样子；retention_analysis 照字面执行）。{desc} = 提示词框里写的
VG_TPL = ('subject_definitions:\n<Video 1> is the source video for the target video edit.\n'
          '<Picture 1> is a frame of the target video, exactly as the target video shows it at that moment.\n'
          '<Subject 1> is {who} in <Video 1>.\n'
          '<Subject 2> is the look of <Subject 1> from the neck down in the target video: {desc}, exactly as shown in <Picture 1>.\n\n'
          'summary:\n[video editing] The target video is an edited version of <Video 1>. <Subject 1> moves exactly as in <Video 1>, with the same face, hair, expression, gestures, '
          'camera, framing and light, and looks like <Subject 2> in every frame.\n\n'
          'retention_analysis:\n<Video 1> (source video editing): fully_preserved - the framing, the camera motion, the background, the lighting, and the face, hair, expression, '
          'gestures and motion of <Subject 1> are copied frame for frame.\n'
          '{pinline}'
          '<Subject 1> (appears in [Shot 1]): fully_preserved - face, identity, hair, skin tone, makeup and every movement are retained.\n'
          '<Subject 2> (appears in [Shot 1]): replaced - in every frame and from every angle <Subject 1> looks exactly as in <Picture 1> from the neck down.\n\n'
          'detailed_description:\nThe target video keeps the look of <Video 1>: the same light, colors and sharpness. [Shot 1] From 00:00.000 to {end}, <Subject 1> moves exactly as in '
          '<Video 1> and looks like <Subject 2>.{pinat} Fabric and hair move naturally with every motion.\n\n'
          'overall_soundscape:\nThe soundtrack of <Video 1>, unchanged.\n\nnon_diegetic_music:\nN/A')
VG_PIN_LINE = '<Picture 1> (target keyframe): fully_preserved - the target video passes through this exact frame.\n'
RMBG = 'background_removal/BiRefNet-HR-matting.safetensors'  # 换人 · 新做法：人物图先去背景（作者 v1.1 工作流里的 BiRefNet 那一步；不去背景时模型会把人物图里的房间搬进视频）
DMD_TURBO = {'lora': os.path.basename(FILES['dmd']), 'steps': 8, 'shift': 12.0, 'ashift': 3.0}  # 作者示例：DMD 8 步、euler / simple、偏移 12 / 3
RMBG_GRAY = 235  # 去背景后填的纯色（浅灰）
# 作者的 body_swap 模板（docs/character-swap.md 原文，一行）；{details} = 人物图里这个人从头到脚的样子（看图自动写，英文逗号分隔，以性别开头）
CS11_TPL = ('body_swap: subject_definitions: <Subject 1> is the {pdetails} shown in <Picture 1>, whose identity, face, head, hair or fur, skin, body shape, proportions and clothing define the character in the target video. '
            'The guide video provides the scene and the performance: its background, environment, lighting, camera, framing, body pose, hand and arm movement, head rotation, gaze direction, lip movement and facial expression, frame by frame; '
            'only the main subject of the guide video is replaced: its face, hair, body and clothing become <Subject 1>.  summary: [video generation + reference] Replace the guide subject with <Subject 1>, keeping the scene, camera and the complete motion and performance of the guide video.  '
            'detailed_description: [Shot 1] <Subject 1> takes the exact place of the guide subject and moves with the same timing, body pose, gestures, head motion, gaze, speech and facial expressions, while keeping the complete identity from <Picture 1>: '
            'facial structure, hair or fur, skin, body shape and clothing stay stable in every frame. The background, lighting, colors and camera of the guide video are preserved. Prevent identity drift, clothing changes, texture crawling and flicker.')
# 作者的 motion_transfer 手写模板（工作流里的 Manual prompt）；{details} = 人物图里的人，{setting} = 场景那句（人物图里有真实场景就用它，否则沿用原视频的）
MOTION_TPL = '''motion_transfer:
subject_definitions:
<Subject 1> is the subject in <Picture 1>: {pdetails}; preserve its visible identity, face, hair or fur, body proportions and outfit.
{setting}
summary:
[video generation + reference] Transfer the source performance to <Subject 1>, preserving the action order, timing and camera of the guide.
retention_analysis:
<Subject 1>: preserve the reference identity and appearance throughout the clip.
detailed_description:
[Shot 1] <Subject 1> follows the guide's motion, poses, gestures, head movement and expression in order and at matching times. Keep identity stable during occlusion, turns and back views. Do not turn a back view into a front view. Do not copy the reference picture's still pose as the motion.
overall_soundscape:
Keep the source soundtrack when connected; do not invent dialogue.
non_diegetic_music:
No additional music requested.'''
MOTION_SETTING_PIC = '<Picture 1> also gives the target environment: {env}. The whole guide environment is replaced by this environment; the guide only gives motion, timing and camera.'
MOTION_SETTING_GUIDE = 'Keep the guide setting.'
OFFICIAL_STEPS = 20  # 官方底模没合并加速：默认 20 步（ComfyUI 官方模板的值）；官方精简版 2026-11-04 去掉
# 官方完整版 Ref2VA（34GB，int8）+ int8 文字编码器：laowang A/B 第 2 轮 C1 证明多参考 + 动作靠它追上了他的效果；“参考生成”默认用它
FULL = V.H3_FULL['ref2va']
FULL_TE = V.H3_TE['int8']
# 官方精简（2026-11-09 夜测 M4）：精简版 Ref2VA（21GB）+ nvfp4 文字编码器，少占约 15GB 内存、略快；高级参数里可选，默认不用
LITE = 'diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors'
LITE_TE = V.H3_TE['nvfp4']
TASKS = ('swap', 'outfit', 'head', 'motion')  # motion = 动作迁移（2026-11-12）
# 换人：ref = 审美优先（参考生成：原视频当 <Video 1>、人物图当 <Picture 1>，结构化提示词，不加 LoRA——laowang A3 的做法）
SWAP_BY = ('v11', 'ref')  # v11 = 新做法（2026-11-12 用户定默认）：Alissonerdx v1.1 作者配方 + 人物图去背景
MAX_SECONDS = 10   # 拖动条的上限：换人 LoRA 在 4~5 秒最稳，超过 10 秒容易走样（数字框可以填到下面的硬上限）
MAX_SECONDS_REF = 15  # 参考生成拖动条的上限：H3 官方建议参考视频 2~15 秒
# 每种做法本身能做的最长时长（节点 / 模型的硬限制，2026-11-04 用户要求数字框能填到这里）：
# H3 的条件节点（原生 MiniMaxH3* 和秋叶 T8）length 最多 3600 帧 = 150 秒（24 fps；训练范围约 124~362 帧，更长没测过）；
HARD_SECONDS = {'h3': 150}


def max_seconds(e):
    """这次改视频最长能做几秒（硬上限）"""
    if e.get('vg'):  # Viggle 重拍：节点最多 345 帧
        return 14
    return HARD_SECONDS.get(e.get('method') if e.get('task') == 'outfit' else '', HARD_SECONDS['h3'])
MIN_FRAMES = 22    # H3 的帧数是 17k+5：至少 22 帧（约 1 秒）
FPS = 24
VIDEO_EXT = {b'ftyp': 'mp4', b'\x1aE\xdf\xa3': 'webm'}


def qedit_ok():
    try:
        import imagegen
        return not imagegen.missing_files('qedit')
    except Exception:
        return False




def is_ref(e):
    """这次是不是“参考生成”（换人的审美优先 / 改衣的参考生成）"""
    return (e.get('task') == 'swap' and e.get('swap_by') == 'ref') or (e.get('task') == 'outfit' and e.get('method') == 'ref')


def full_ok():
    return V._have(FULL) and V._have(FULL_TE)


def lite_ok():
    return V._have(LITE) and V._have(LITE_TE)


def fs_ok():
    """换头 · 换脸 LoRA（UntMods）要的：官方精简 + 这个 LoRA"""
    return lite_ok() and full_ok() and V._have(FILES['faceswap'])


def vg_ok():
    """改衣 · Viggle 重拍要的：Viggle 的 int8 合并版底模 + 它的节点包（custom_nodes/ComfyUI-Viggle-Remake）"""
    return V._have(VG_FILE) and os.path.isdir(os.path.join(V.COMFY_DIR, 'ComfyUI', 'custom_nodes', VG_NODES))


def recipe_ok(k):
    """作者配方（换人 · 新做法 k='cs11' / 动作迁移 k='motion'）要的文件都在吗"""
    return lite_ok() and full_ok() and V._have(FILES[k]) and V._have(FILES['dmd']) and (k != 'cs11' or V._have(RMBG))


def shared_ok():
    """不管用哪个底模都要的：ComfyUI 和 H3 的视频 / 声音 VAE"""
    return os.path.isfile(V.COMFY_PY) and all(V._have(f) for f in V.MODELS['h3']['files'] if f.startswith('vae/'))


def official_ok():
    """官方完整版这条路（Ref2VA int8 + int8 文字编码器 + VAE）"""
    return shared_ok() and full_ok()


def status():
    """每个任务 / 做法按它真正要的文件判断"""
    have = {k: V._have(f) for k, f in FILES.items()}
    off = official_ok()
    by = [k for k in SWAP_BY if (off if k == 'ref' else shared_ok() and recipe_ok('cs11'))]  # 参考生成不用 LoRA
    o5 = off and qedit_ok()  # 改衣：H3 参考模式（官方完整版）+ Qwen 改图
    hb = [k for k in HEAD_BY if shared_ok() and fs_ok()]
    tasks = {'swap': bool(by), 'outfit': o5, 'head': bool(hb), 'motion': shared_ok() and recipe_ok('motion')}
    ok = any(tasks.values())
    return {'ok': ok, 'tasks': tasks, 'official': off, 'vfx': have['vfx'], 'templates': templates(),
            'head_by': hb, 'vg': o5 and vg_ok(),
            'outfit_ref': o5, 'swap_by': by, 'official_steps': OFFICIAL_STEPS,
            'full': full_ok(), 'full_file': os.path.basename(FULL), 'lite': full_ok() and lite_ok(), 'pose': pose_ok(), 'loc': loc_ok(), 'max_seconds': MAX_SECONDS, 'max_seconds_ref': MAX_SECONDS_REF, 'hard_seconds': HARD_SECONDS,
            'missing': [os.path.basename(f) for k, f in FILES.items() if not have[k]] + ([] if off else ['H3 官方 Ref2VA 完整版'])}


def video_kind(data):
    head = data[:16]
    if head[4:8] == b'ftyp':
        return 'mp4'
    if head[:4] == b'\x1aE\xdf\xa3':
        return 'webm'
    if head[:4] == b'RIFF' and head[8:12] == b'AVI ':
        return 'avi'
    return None


def parse(b, video_bytes, ref_bytes):
    """网页传来的“改视频”设置 → 检查过的 dict（不对就报错，提示看得懂的话）。"""
    e = b.get('edit') if isinstance(b.get('edit'), dict) else {}
    st = status()
    if not st['ok']:
        raise RuntimeError('改视频需要的底模还没下载（H3 官方 Ref2VA 完整版）')
    if e.get('task') in ('remove', 'free'):
        raise ValueError('去人去物、自由修改已移除（自由修改请在生成视频中添加特效编辑 LoRA 和引导视频）')
    task = e.get('task') if e.get('task') in TASKS else 'swap'
    if not st['tasks'][task]:
        raise RuntimeError('该功能所需的文件尚未下载：' + '、'.join(st['missing']))
    if not video_bytes or len(video_bytes) < 1000:
        raise ValueError('请先放入原视频')
    if not video_kind(video_bytes):
        raise ValueError('原视频仅支持 MP4 / MOV / WebM / AVI')
    if task == 'head' and not ref_bytes:
        raise ValueError('换头需要放入一张头像（新的那张脸，最好是清晰的正脸）')
    if task == 'swap' and not ref_bytes:
        raise ValueError('换人需要放入一张人物图（要换成的那个人）')
    if task == 'motion' and not ref_bytes:
        raise ValueError('动作迁移需要放入一张人物图（要做动作的那个人；图里的场景也会用上）')
    by = e.get('swap_by') if e.get('swap_by') in st['swap_by'] else (st['swap_by'] or ['v11'])[0]
    audio = e.get('audio') if e.get('audio') in ('keep', 'gen', 'none') else 'keep'
    try:
        start = max(0.0, min(3600.0, float(e.get('start') or 0)))
    except (TypeError, ValueError):
        start = 0.0
    base0 = e.get('base') if e.get('base') in ('official', 'full', 'lite') else 'auto'  # auto = 跟着做法走（2026-11-04 起网页默认）
    lite = (base0 == 'lite' or (base0 == 'full' and e.get('lite') is True)) and st.get('lite')  # 官方精简：其余都按官方，只换底模和文字编码器文件
    if base0 == 'lite':
        base0 = 'full'
    if base0 == 'official':  # 官方精简版已去掉（2026-11-04）：以前存的设置、重跑旧任务都按官方完整版
        base0 = 'full'
    tpl = e.get('tpl') is not False  # 用不用内置的提示词模板（默认用；关掉就把提示词框里的原样发给模型）
    # 改衣的做法只剩参考生成（ref）：保真替换 / 参考编辑（Wan 2.2）2026-11-06 去掉了。旧记录里存的 animate / bernini 重新生成时也按参考生成（迁移，2026-11-17 审查 C02）
    method = None
    if task == 'outfit':
        method = 'ref'
        if not st['outfit_ref']:
            raise RuntimeError('参考生成所需的文件尚未下载：Qwen 指令改图')
    # 改衣：上传的图直接当参考图（已经换好衣服的人物图，比如在改图里改好的），跳过 Qwen 改图
    own = task == 'outfit' and e.get('own') is True
    # 底模：官方完整版（参考生成）；作者配方 / 换脸 LoRA 固定官方精简；“高级”里可以选官方精简
    ref = is_ref({'task': task, 'swap_by': by, 'method': method})
    if e.get('base') == 'lite' and not ref and e.get('xbase') != 'lite':  # 网页默认是“精简”：它只对参考生成有意义
        base0, lite = 'auto', False
    # 测试（2026-11-12）：xbase = 'lite' 时换人 / 换头也用官方精简（作者的 LoRA 都是在官方 Ref2VA 上训练的）；xlora 换掉做法自带的 LoRA（换头那条接法 = AddGuide 原视频 + 参考图 + LoRA）
    xlora = os.path.basename(str(e.get('xlora') or '')) if e.get('xlora') and V._have('loras/' + os.path.basename(str(e.get('xlora')))) else None
    base = 'full'
    if not st['full']:
        raise RuntimeError('改视频需要 H3 官方 Ref2VA 完整版，尚未下载')
    # 作者配方（换人 · 新做法、动作迁移）：固定官方精简（作者的 LoRA 都在官方 Ref2VA 上训练，示例全用精简版）
    recipe = 'cs11' if task == 'swap' and by == 'v11' else 'motion' if task == 'motion' else None
    if recipe:
        if not recipe_ok(recipe):
            raise RuntimeError('该做法所需的文件尚未下载')
        base, lite = 'full', True
    hb = (e.get('head_by') if e.get('head_by') in st['head_by'] else (st['head_by'] or ['fs'])[0]) if task == 'head' else None
    if hb == 'fs':  # 换头 · 换脸 LoRA：固定官方精简（夜测 N3 就是这一套）
        base, lite = 'full', True
    # 改衣 · Viggle 重拍（默认关）：要一张改好的图（Qwen 改的，或自己放的“已经换好衣服的图”）；不叠局部修改 / 动作跟随（Viggle 底模是首帧版，没测过这两样）
    vg = task == 'outfit' and method == 'ref' and e.get('vg') is True and st.get('vg')
    if vg and own and not ref_bytes:
        raise ValueError('Viggle 重拍需要一张改好的图：放入参考图，或关掉“直接用作参考图”让 Qwen 改')
    # 动作跟随（2026-11-10）：官方只出了配精简版底模的 Fun ControlNet（adaln 是曲线基，宽 8；完整版是 2688，接上就报
    # “controlnet adaln width 8 does not match”）。所以开了动作跟随时这一单用官方精简（精简版 + nvfp4，测过的就是这一套），别的底模不接
    # 局部修改（2026-11-12 夜测，网页开关，默认关）：只重画衣服那块（SAM3 逐帧找衣服），其余贴回原视频——脸和色调和原视频一样、看不出接缝。
    # 测过的就是这一套：Fun ControlNet 2.0 · 强度 1.0（和动作骨架同一层）+ 不给参考视频 + 参考图（Qwen 或自己的）+ 贴回。所以开了就带动作跟随（2.0）、用官方精简
    loc = None
    if task == 'outfit' and method == 'ref' and base == 'full' and st.get('lite') and loc_ok() and not vg:
        loc = _loc_in(e.get('loc')) if isinstance(e.get('loc'), dict) else (_loc_in(dict(LOC_Q.get(str(e.get('locq')), LOC_Q['cloth']))) if e.get('locon') is True else None)
    # 动作跟随只用 2.0 · 1.0（2026-11-12 用户定，第一版删了：三个种子 2.0 = 0.054 / 0.054 / 0.053，第一版 0.6 有一个种子跑偏到 0.099）
    pv = '2'
    pose = not recipe and not vg and hb != 'fs' and (e.get('pose') is True or (bool(loc) and not loc.get('nopose'))) and base == 'full' and bool(st.get('lite')) and pose_ok()  # 作者配方不叠动作跟随（作者示例没有，没测过）
    if pose or loc:
        lite = True
    return {'task': task, 'base': base, 'lite': bool(lite) and base == 'full', 'tpl': tpl, 'method': method, 'own': own,
            'swap_by': by if task == 'swap' else None, 'target': str(e.get('target') or '').strip()[:200],
            'audio': audio, 'start': round(start, 2), 'ref': bool(ref_bytes),
            'plang': 'en' if e.get('plang') == 'en' else 'zh',
            'cmatch': e.get('cmatch') is True and task != 'motion',  # 动作迁移是人物图的场景，不往原视频的颜色调；2026-11-10：生成后自动把亮度和肤色调回原视频（colorfix 照原视频；默认关）
            'pose': pose, 'pose_w': max(0.2, min(2.0, float(e.get('pose_w') or POSE_W))) if isinstance(e.get('pose_w'), (int, float)) else (LOC_W if loc else POSE_W),  # 动作跟随（2026-11-10，默认关）：原视频的全身骨架逐帧约束
            'ffguide': task == 'outfit' and e.get('ffguide') is True,
            'ff_own': task == 'outfit' and own and e.get('ff_own') is True,
            'ref_max': e.get('ref_max') is True,  # 夜间测试（2026-11-11，默认关）：参考图按最大尺寸送进去（短边最多 2048），细节更多
            # 只准备（2026-11-10 用户）：看图描述 + Qwen 生图做完就停，图和写准确的名字交回网页，填进参考图和提示词框，用户检查后再点生成
            'prep': task == 'outfit' and method == 'ref' and not own and e.get('prep') is True,
            # 改动写进每一段（2026-11-11 用户定默认开，网页上的开关）：写的改动除了开头也写进每一段
            'emph': task == 'outfit' and e.get('emph') is True,
            'splice': e.get('splice') is True and task != 'motion',  # 选了一段并选择拼接：留一份完整原视频，成品可以拼回去（动作迁移是另一个人、另一个场景，拼回去没有意义）
            # 多段改衣共用一张 Qwen 换好衣服的图（2026-11-06）：同一批的几段带同一个 qshare，第一段生成、后面几段直接用
            'qshare': (re.sub(r'[^0-9A-Za-z_-]', '', str(e.get('qshare') or ''))[:40] or None) if task == 'outfit' and method == 'ref' and not own else None,
            'pose_v': pv,  # 动作跟随用哪一版 ControlNet（见上面 pv）
            'loc': loc, 'xlora': xlora, 'recipe': recipe,
            'xt': e.get('xt') if isinstance(e.get('xt'), dict) else None,
            'head_by': hb, 'vg': bool(vg)}  # 夜测（2026-11-12）：x2 两段式、gray 去背景底色；网页不发


def _loc_in(x):
    """局部生成的设置（测试用）：q = SAM3 按什么找（'person' = 整个人，锁背景）；grow 外扩几像素；protect 扣掉脸 / 头发 / 手；
    w 强度；sep 和动作骨架分两层（各自的强度）；paste 解码后 mask 外贴回原视频；clean 贴回前去毛边；feather 贴回时边缘柔化；
    noref 不再把原视频当参考视频（默认）；dump 存一份 mask 视频（分析用）；end 分两层时局部那层只在前面这部分步数起作用（测试）"""
    if not isinstance(x, dict) or not str(x.get('q') or '').strip():
        return None
    f = lambda k, lo, hi, d: max(lo, min(hi, float(x[k]))) if isinstance(x.get(k), (int, float)) else d
    return {'q': str(x['q']).strip()[:80], 'grow': int(f('grow', 0, 128, LOC_GROW)), 'protect': x.get('protect') is not False, 'w': f('w', 0.1, 3.0, 1.0),
            'sep': x.get('sep') is True, 'paste': x.get('paste') is not False, 'clean': x.get('clean') is not False, 'feather': int(f('feather', 0, 32, LOC_FEATHER)),
            'noref': x.get('noref') is not False, 'dump': x.get('dump') is True, 'thr': f('thr', 0.1, 0.9, 0.4), 'end': f('end', 0.1, 1.0, 1.0),
            'native': x.get('native') is True,
            'nopose': x.get('nopose') is True,
            'pq': str(x.get('pq') or '').strip()[:60] or None,
            'pgrow': int(f('pgrow', 0, 48, 4)), 'pqout': x.get('pqout') is True}  # 夜测：保护范围外扩几像素；只保护衣服范围外的手（手压在要改的衣服上时一起重画）  # 测试：保护（不重画）的部分，默认 face, hair, hand  # 测试：局部修改不带动作跟随（官方 inpaint 例子就没有控制视频）  # 测试：H3 自己的局部重画（latent 噪声 mask），只在 ② 上


# 局部修改的默认值（2026-11-12 夜测，docs/AB测试/ControlNet2_1112）：外扩 32 像素 + 贴回时边缘柔化 6 接缝最平；2.0 · 强度 1.0
LOC_GROW, LOC_FEATHER, LOC_W = 32, 6, 1.0
# 网页上的“改哪里”：SAM3 用英文找。cloth = 全部衣服（默认）；person = 整个人（扣掉脸、头发、手），外扩 96
# 2026-11-12 下午起网页开关走 H3 原生局部重画（native：原视频 latent + 噪声 mask，mask 外当干净原画面）+ 不贴回：
# 昨晚的 ControlNet 灰洞 + 贴回在衣服边上有线 / 残影（贴回范围压在衣服边上）；原生不贴回没有线，脸 0.92、亮度 −0.7。
# 720p 中途会变回原来的衣服（11-12 在查）；用户不接受 480p，所以不再固定分辨率（LOC_SIZE = None）
# 保护（不重画）只留脸和手，头发不保护（11-12 下午）：头发搭在衣服上会在 mask 里挖出一条条缝，720p 下模型透过缝看到原来衣服的碎片，
# 就把原来的衣服（女仆的蝴蝶结）中途补回来；头发不保护后 720p 逐帧一致（C6h）
# 手也不保护（11-13 夜测 K1）：手划过要改的地方时，保护住的手会把原来的衣服（白蝴蝶结）一起留下、成了白块；不保护手后逐帧一致，手在衣服外的部分本来就不在 mask 里
LOC_Q = {'cloth': {'q': 'clothing', 'native': True, 'paste': False, 'pq': 'face'},
         'person': {'q': 'person', 'grow': 96, 'native': True, 'paste': False, 'pq': 'face'}}
LOC_SIZE = None  # 要固定局部修改的分辨率时填 '480p' 之类


def loc_ok():
    return pose_ok('2') and V._have('checkpoints/' + SAM_FILE)


def _vprobe(path):
    """原视频：宽高（已按手机竖拍的旋转换好）、时长、有没有声音。"""
    try:
        r = subprocess.run([V.FFPROBE, '-v', 'error', '-show_entries', 'stream=codec_type,width,height,start_time:stream_tags=rotate:stream_side_data=rotation:format=duration,start_time',
                            '-of', 'json', path], capture_output=True, timeout=60, creationflags=V.NO_WINDOW)
        d = json.loads(r.stdout or b'{}')
    except Exception:
        return {}
    ss = d.get('streams') or []
    v = next((s for s in ss if s.get('codec_type') == 'video'), {})
    rot = 0
    try:
        rot = int(float((v.get('tags') or {}).get('rotate') or next((x.get('rotation') for x in v.get('side_data_list') or [] if 'rotation' in x), 0) or 0))
    except (TypeError, ValueError):
        rot = 0
    w, h = v.get('width') or 0, v.get('height') or 0
    if abs(rot) % 180 == 90:
        w, h = h, w
    try:
        dur = float((d.get('format') or {}).get('duration') or 0)
    except (TypeError, ValueError):
        dur = 0.0
    try:
        st0 = float(v.get('start_time') or (d.get('format') or {}).get('start_time') or 0)  # 画面流自己的起点（声音可能更早开始）
    except (TypeError, ValueError):
        st0 = 0.0
    return {'width': w, 'height': h, 'duration': dur, 'start': st0, 'audio': any(s.get('codec_type') == 'audio' for s in ss)}


def _grid(n):  # 不超过 n 的最大 17k+5
    return ((n - 5) // 17) * 17 + 5 if n >= MIN_FRAMES else 0


def prepare(j, work_in, tag):
    """把原视频裁成要的那一段：24 fps、目标尺寸（按原比例，32 的倍数，居中裁掉多出来的一点）、正好 17k+5 帧。
    返回 (宽, 高, 帧数, 处理好的文件名, 有没有声音)。"""
    e = j['edit']
    raw = os.path.join(work_in, f"studio_{tag}_raw.{video_kind(j['_vid']) or 'mp4'}")
    with open(raw, 'wb') as f:
        f.write(j['_vid'])
    pr = _vprobe(raw)
    if not pr.get('width') or not pr.get('duration'):
        raise RuntimeError('无法读取原视频（文件可能已损坏，或编码不受支持）')
    T = pr['duration'] - 0.5 / FPS  # 最后一帧开始的地方（再往后就没有画面了）
    if e['start'] > T - 0.2:
        raise RuntimeError(f"原视频从第 {e['start']:g} 秒起已经没有画面了")
    # 2026-11-05 用户定：选多长就生成多长，每一帧都是生成的。模型只能做 17k+5 帧（每档约 0.71 秒），所以生成一个比选段稍长的“窗口”，
    # 做完再按成品和原视频的帧差裁成正好选的那一段（exact_trim）。窗口：开头多留 3 帧（成品通常早 2 帧），长度往上取一档；
    # 结尾不够就把窗口往前挪；整个原视频都不够长就在开头 / 结尾补几帧定格（这些都在裁掉的部分里）
    s0 = e['start']; want = max(0.2, min(float(e.get('want') or j['seconds']), pr['duration'] - s0))
    pre = 3 / FPS
    k = -(-((pre + want) * FPS - 5 - 1e-6) // 17)
    frames = max(VG_MIN_FRAMES if e.get('vg') else MIN_FRAMES, int(k) * 17 + 5)  # Viggle 重拍：节点至少 90 帧（多出来的在裁成选段时裁掉）
    ws = s0 - pre
    if ws + frames / FPS > pr['duration']:
        ws = pr['duration'] - frames / FPS
    ws = math.floor(ws * FPS + 1e-6) / FPS  # 窗口起点对齐到 24 fps 的格子上（下面按原视频自己的时间轴转 24 fps 再按帧取，处理好的第 k 帧正好是 ws + k/24）
    pad0 = max(0.0, -ws)  # 开头补定格（窗口从 0 秒之前开始）
    pad1 = max(0.0, ws + frames / FPS - pr['duration'])  # 结尾补定格
    e['win'], e['want'] = round(ws, 4), round(want, 4)
    res = j.get('res')
    if res and res[0] == 'wh':
        w, h = res[1], res[2]
    else:
        short = res[1] if res else V.SIZES.get(j['size'], 480)
        if e.get('vg'):  # Viggle 重拍：节点只认短边 480 / 736（不是的话它会自己裁成 16:9 的画布，拼回原视频就对不上）
            short = 736 if short > 600 else 480
        k = short / min(pr['width'], pr['height'])
        w, h = (max(256, int(round(x * k / 32)) * 32) for x in (pr['width'], pr['height']))
        if e.get('vg'):
            w, h = (short, h) if w <= h else (w, short)  # 短边正好是 480 / 736（四舍五入到 32 会差一点）
    name = f'studio_{tag}_src.mp4'
    out = os.path.join(work_in, name)
    j['message'] = '正在处理原视频…'
    tp = (f',tpad=start_mode=clone:start_duration={pad0:.4f}' if pad0 > 0 else '') + (f',tpad=stop_mode=clone:stop_duration={pad1 + 0.2:.4f}' if pad1 > 0 else '')
    af = (f'adelay=delays={round(pad0 * 1000)}:all=1,' if pad0 > 0 else '') + f'apad=whole_dur={frames / FPS:.4f},atrim=end={frames / FPS:.4f}'
    # 2026-11-06：以前是先跳到 ws 再转 24 fps——30 fps 的原视频跳过去落在下一帧上、转的时候又取最近的一帧，整段晚约 1 帧（对比、拼接都差一点）。
    # 现在保留原视频的时间戳（-copyts），先在原视频自己的时间轴上转 24 fps（第 n 帧在 n/24 秒），再从 ws 起按帧取
    t00 = pr.get('start') or 0.0  # 画面时间戳的起点（多数是 0；有的视频不是）：先减掉，24 fps 的格子从画面第一帧算起
    ss0, wa = max(0.0, ws - 2.0), max(0.0, ws)
    V._ff(j, ['-ss', f'{ss0:.4f}', '-copyts', '-i', raw,
              '-vf', f'setpts=PTS-{t00:.6f}/TB,fps={FPS},trim=start={wa - 0.25 / FPS:.5f},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1{tp}',
              '-frames:v', str(frames), '-c:v', 'libx264', '-crf', '12', '-preset', 'fast', '-pix_fmt', 'yuv420p',
              *(['-af', f'asetpts=PTS-{t00:.6f}/TB,atrim=start={wa:.5f},asetpts=PTS-STARTPTS,' + af, '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if pr['audio'] else ['-an']), out], '处理原视频')
    got = V._probe(out).get('frames') or frames
    if got < frames:  # 万一还是少了几帧：按实际帧数往下取一档（裁的时候按实际长度）
        frames = _grid(got)
        if not frames:
            raise RuntimeError('原视频过短（至少需要 1 秒）')
    try:
        os.remove(raw)
    except OSError:
        pass
    return w, h, frames, name, pr['audio'] and V._probe(out).get('audio', False)


# 参考生成（换人的审美优先 / 改衣的参考生成）：H3 官方结构化写法，照 laowang A/B 第 3、4 段（A3 / A4）的写法改成通用的；{desc} = 提示词框里写的
REF_SWAP_TPL = '''subject_definitions:
<Subject 1> 是来自 <Picture 1> 的人物{desc}。
<Picture 1> 是提供 <Subject 1> 外观的人物参考图。
<Video 1> 是原视频，提供场景、机位、构图、光线和人物的全部动作。

summary:
[video editing] 把 <Video 1> 里的{who}完全换成 <Subject 1>：脸、发型、身材和穿着都来自 <Picture 1>，动作、机位、场景和光线与 <Video 1> 逐帧一致。

retention_analysis:
<Subject 1>（出现在 [Shot 1]）：fully_preserved - 脸、发型、肤色、身材和穿着与 <Picture 1> 完全一致。
<Picture 1>：fully_preserved - 作为 <Subject 1> 的唯一外观来源。
<Video 1>（原视频）：attribute_transfer - 保留 <Video 1> 的场景、机位、构图、光线和人物的全部动作、身体朝向与节奏；原来的{who}被 <Subject 1> 完全替换，画面里不再出现原来的人。

detailed_description:
写实风格，与 <Video 1> 相同的镜头、景别和光线，画面清晰锐利。
[Shot 1] <Subject 1> 出现在原来那个人的位置上，逐帧做出与 <Video 1> 完全相同的动作、表情和口型；头发和衣服随动作自然摆动。脸始终清晰，与 <Picture 1> 一致。

overall_soundscape:
与 <Video 1> 一致的环境声和动作声。

non_diegetic_music:
N/A'''
# 2026-11-08 新写法（旧的留作 _V1）：加朝向 / 帽子饰品 / 人数 / 节奏。B1 → B3（背面一帧被画成正面的参考图）：背面不再画脸、帽子更多帧保住，动作差 0.195 → 0.171；正面视频 A4 ≈ A5
REF_OUTFIT_TPL_V1 = '''subject_definitions:
<Subject 1> 是 <Video 1> 里的{who}，也就是 <Picture 1> 里的同一个人{desc}。
<Picture 1> 是 <Subject 1> 换好衣服后的样子，提供新衣服的外观。
<Video 1> 是原视频，提供人物的脸、发型、身材、全部动作，以及场景、机位和光线。

summary:
[video editing] 保持 <Video 1> 的同一个人、同样的动作和同一个场景，只把衣服换成 <Picture 1> 里的样子。

retention_analysis:
<Subject 1>（出现在 [Shot 1]）：partially_preserved - 脸、表情、发型、肤色、身材和全部动作与 <Video 1> 逐帧一致；衣服换成 <Picture 1> 里的样子。
<Picture 1>：fully_preserved - 作为新衣服的外观来源。
<Video 1>（原视频）：attribute_transfer - 保留 <Video 1> 的人物身份、动作、机位、构图和场景；只改变衣服。

detailed_description:
写实风格，与 <Video 1> 相同的镜头、景别和光线，画面清晰锐利。
[Shot 1] <Subject 1> 逐帧做出与 <Video 1> 完全相同的动作。衣服和 <Picture 1> 一致，正面、背面和袖子都一样，布料随动作自然摆动。脸、表情和发型都与 <Video 1> 一致，脸始终清晰；身材与原视频一致，没有变胖或变瘦。

overall_soundscape:
与 <Video 1> 一致的环境声和动作声。

non_diegetic_music:
N/A'''
REF_OUTFIT_TPL = '''subject_definitions:
<Subject 1> 是 <Video 1> 里的{who}，也就是 <Picture 1> 里的同一个人{desc}。
<Picture 1> 是 <Subject 1> 换好衣服后的样子，提供新衣服的外观。
<Video 1> 是原视频，提供人物的脸、发型、帽子和饰品、身材、全部动作和身体朝向，以及场景、机位和光线。

summary:
[video editing] 保持 <Video 1> 的同一个人、同样的动作和同一个场景，只把衣服换成 <Picture 1> 里的样子。画面里的人数和每个人的位置与 <Video 1> 逐帧一致。

retention_analysis:
<Subject 1>（出现在 [Shot 1]）：partially_preserved - 脸、表情、发型、帽子和饰品、肤色、身材、全部动作和身体朝向与 <Video 1> 逐帧一致；衣服换成 <Picture 1> 里的样子。
<Picture 1>：fully_preserved - 作为新衣服的外观来源。
<Video 1>（原视频）：attribute_transfer - 保留 <Video 1> 的人物身份、人数、动作、身体朝向、机位、构图和场景；只改变衣服。

detailed_description:
写实风格，与 <Video 1> 相同的镜头、景别和光线，画面清晰锐利。
[Shot 1] <Subject 1> 逐帧做出与 <Video 1> 完全相同的动作，节奏和快慢一致，不提前也不落后。身体和头的朝向始终与 <Video 1> 的同一帧完全一致（面向镜头、侧身还是背对镜头都一样），看不到脸的画面里不要画出脸。衣服和 <Picture 1> 一致，正面、背面和袖子都一样，布料随动作自然摆动。帽子、发型和饰品与 <Video 1> 一致。看得到脸的时候，脸和表情与 <Video 1> 一致，清晰不模糊；身材与原视频一致，没有变胖或变瘦。

overall_soundscape:
与 <Video 1> 一致的环境声和动作声。

non_diegetic_music:
N/A'''


# 提示词语言 = 英文时用的英文版（占位和中文版一样；用户写的那一小段由网页先翻成英文，见 ptrans.py）
EN_REF_SWAP_TPL = "subject_definitions:\n<Subject 1> is the person from <Picture 1>{desc}.\n<Picture 1> is the character reference image that provides the appearance of <Subject 1>.\n<Video 1> is the source video, providing the scene, camera position, framing, lighting, and every movement of the person.\n\nsummary:\n[video editing] The target video is an edited version of <Video 1>. The {who} in <Video 1> is completely replaced by <Subject 1>: face, hair, body, and outfit all come from <Picture 1>, while the movement, camera, scene, and lighting match <Video 1> frame by frame.\n\nretention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - face, hairstyle, skin tone, body shape, and outfit exactly match <Picture 1>.\n<Picture 1>: fully_preserved - the only source of the appearance of <Subject 1>.\n<Video 1> (source video): attribute_transfer - the scene, camera position, framing, lighting, and all of the person's movements, body orientation, and rhythm are kept; the original {who} is fully replaced by <Subject 1> and no longer appears in the frame.\n\ndetailed_description:\nLive-action, photorealistic, with the same shots, framing, and lighting as <Video 1>; the image stays sharp and clear.\n[Shot 1] <Subject 1> appears in the original person's position and performs exactly the same movements, expressions, and lip movements as <Video 1>, frame by frame; hair and clothing move naturally with the motion. The face stays sharp throughout and matches <Picture 1>.\n\noverall_soundscape:\nThe same ambience and movement sounds as <Video 1>.\n\nnon_diegetic_music:\nN/A"
EN_REF_OUTFIT_TPL_V1 = "subject_definitions:\n<Subject 1> is the {who} in <Video 1>, the same person shown in <Picture 1>{desc}.\n<Picture 1> shows <Subject 1> after the outfit change and provides the appearance of the new clothes.\n<Video 1> is the source video, providing the person's face, hair, body, every movement, and the scene, camera position, and lighting.\n\nsummary:\n[video editing] The target video is an edited version of <Video 1>. The same person, the same movements, and the same scene as <Video 1> are kept; only the clothes are changed to match <Picture 1>.\n\nretention_analysis:\n<Subject 1> (appears in [Shot 1]): partially_preserved - face, expression, hairstyle, skin tone, body shape, and every movement match <Video 1> frame by frame; the clothes are changed to match <Picture 1>.\n<Picture 1>: fully_preserved - the source of the new clothes' appearance.\n<Video 1> (source video): attribute_transfer - the person's identity, movements, camera position, framing, and scene are kept; only the clothes change.\n\ndetailed_description:\nLive-action, photorealistic, with the same shots, framing, and lighting as <Video 1>; the image stays sharp and clear.\n[Shot 1] <Subject 1> performs exactly the same movements as <Video 1>, frame by frame. The clothes match <Picture 1> on the front, the back, and the sleeves, and the fabric moves naturally with the motion. Face, expression, and hairstyle match <Video 1>; the face stays sharp throughout, and the body shape matches the source video with no change in weight.\n\noverall_soundscape:\nThe same ambience and movement sounds as <Video 1>.\n\nnon_diegetic_music:\nN/A"
EN_REF_OUTFIT_TPL = "subject_definitions:\n<Subject 1> is the {who} in <Video 1>, the same person shown in <Picture 1>{desc}.\n<Picture 1> shows <Subject 1> after the outfit change and provides the appearance of the new clothes.\n<Video 1> is the source video, providing the person's face, hair, hat and accessories, body, every movement and body orientation, and the scene, camera position, and lighting.\n\nsummary:\n[video editing] The target video is an edited version of <Video 1>. The same person, the same movements, and the same scene as <Video 1> are kept; only the clothes are changed to match <Picture 1>. The number of people and each person's position match <Video 1> frame by frame.\n\nretention_analysis:\n<Subject 1> (appears in [Shot 1]): partially_preserved - face, expression, hairstyle, hat and accessories, skin tone, body shape, every movement, and body orientation match <Video 1> frame by frame; the clothes are changed to match <Picture 1>.\n<Picture 1>: fully_preserved - the source of the new clothes' appearance.\n<Video 1> (source video): attribute_transfer - the person's identity, the number of people, movements, body orientation, camera position, framing, and scene are kept; only the clothes change.\n\ndetailed_description:\nLive-action, photorealistic, with the same shots, framing, and lighting as <Video 1>; the image stays sharp and clear.\n[Shot 1] <Subject 1> performs exactly the same movements as <Video 1>, frame by frame, at the same pace, never ahead or behind. Her body and head always face exactly the same way as in the same frame of <Video 1> (facing the camera, sideways, or with her back to it); in frames where her face is not visible, no face is drawn. The clothes match <Picture 1> on the front, the back, and the sleeves, and the fabric moves naturally with the motion. Her hat, hairstyle, and accessories match <Video 1>. Whenever her face is visible, it and her expression match <Video 1> and stay sharp; the body shape matches the source video with no change in weight.\n\noverall_soundscape:\nThe same ambience and movement sounds as <Video 1>.\n\nnon_diegetic_music:\nN/A"
# 2026-11-09：模板里点名“帽子”，原视频没戴帽子时 H3 会给人加一顶（夜测换衣：正面近景成品戴上了黑色棒球帽，Qwen 图里没有）。11-08 的写法留作 _V1108，改成只说“饰品”、没有的不要加
REF_OUTFIT_TPL_V1108, EN_REF_OUTFIT_TPL_V1108 = REF_OUTFIT_TPL, EN_REF_OUTFIT_TPL
REF_OUTFIT_TPL = REF_OUTFIT_TPL_V1108.replace('帽子和饰品', '饰品').replace('帽子、发型和饰品与 <Video 1> 一致。', '发型和饰品与 <Video 1> 一致，<Video 1> 里没有的东西不要加。')
EN_REF_OUTFIT_TPL = EN_REF_OUTFIT_TPL_V1108.replace('hat and accessories', 'accessories').replace('Her hat, hairstyle, and accessories match <Video 1>.', 'Her hairstyle and accessories match <Video 1>; do not add anything that is not in <Video 1>.')


# ===== 2026-11-09 正向写法（POS）：提示词里只写想要的样子，不出现原视频里没有、或者想去掉的东西 =====
# 用户 11-09：大模型对提到的东西都会加注意力，“不要转身”会让人更容易转身，“背面时……”会让正面视频出现背面，“帽子袜子鞋也去掉”会让它们更容易留着。
# 所以：朝向只说“和 <Video 1> 同一帧相同”，不列举正面 / 侧面 / 背面；去掉的东西不点名；不写“不要 / 没有 / 不提前不落后 / 没有变胖变瘦”。
# 上面的 11-08 写法（REF_*_TPL）保留不动；POS = True 时 _prompt / outfit2 用这里的写法
POS = False
_ORIENT_POS_ZH = '逐帧做出与 <Video 1> 完全相同的动作，动作节奏与 <Video 1> 同步。她的身体和头部朝向在每一帧都与 <Video 1> 的同一帧相同。'
_ORIENT_POS_EN = "performs exactly the same movements as <Video 1>, frame by frame, in sync with its rhythm. In every frame her body and head point the same way as in the same frame of <Video 1>. "
_FRAME_ZH = '写实风格，与 <Video 1> 相同的镜头、景别和光线，人物在画面中的大小和位置与 <Video 1> 的同一帧相同，一镜到底，画面清晰锐利。'
_FRAME_EN = "Live-action, photorealistic, with the same shots, framing, and lighting as <Video 1>; the person has the same size and position in the frame as in the same frame of <Video 1>; one continuous shot, sharp and clear."
REF_OUTFIT_TPL_POS = ('subject_definitions:\n<Subject 1> 是 <Video 1> 里的{who}，也就是 <Picture 1> 里的同一个人{desc}。\n'
    '<Picture 1> 是 <Subject 1> 换好衣服后的样子，只提供新衣服的外观。\n'
    '<Video 1> 是原视频，提供人物的长相、发型、饰品、身材、全部动作和身体朝向，以及场景、机位、构图和光线。\n\n'
    'summary:\n[video editing] 保持 <Video 1> 的同一个人、同样的动作、同样的构图和同一个场景，只把衣服换成 <Picture 1> 里的样子。画面里的人数和每个人的位置与 <Video 1> 逐帧相同。\n\n'
    'retention_analysis:\n<Subject 1>（出现在 [Shot 1]）：partially_preserved - 长相、表情、发型、饰品、肤色、身材、全部动作和身体朝向与 <Video 1> 逐帧相同；衣服换成 <Picture 1> 里的样子。\n'
    '<Picture 1>：fully_preserved - 作为新衣服的外观来源。\n'
    '<Video 1>（原视频）：attribute_transfer - 保留 <Video 1> 的人物身份、人数、动作、身体朝向、机位、构图和场景；只改变衣服。\n\n'
    'detailed_description:\n' + _FRAME_ZH + '\n'
    '[Shot 1] <Subject 1> ' + _ORIENT_POS_ZH + '衣服与 <Picture 1> 完全相同，布料随动作自然摆动。发型和饰品与 <Video 1> 完全相同。她的长相、表情和身材与 <Video 1> 完全相同。\n\n'
    'overall_soundscape:\n与 <Video 1> 一致的环境声和动作声。\n\nnon_diegetic_music:\nN/A')
EN_REF_OUTFIT_TPL_POS = ("subject_definitions:\n<Subject 1> is the {who} in <Video 1>, the same person shown in <Picture 1>{desc}.\n"
    "<Picture 1> shows <Subject 1> after the outfit change and provides only the appearance of the new clothes.\n"
    "<Video 1> is the source video, providing the person's looks, hair, accessories, body, every movement and body orientation, and the scene, camera position, framing, and lighting.\n\n"
    "summary:\n[video editing] The target video is an edited version of <Video 1>. The same person, the same movements, the same framing, and the same scene as <Video 1> are kept; only the clothes are changed to match <Picture 1>. The number of people and each person's position match <Video 1> frame by frame.\n\n"
    "retention_analysis:\n<Subject 1> (appears in [Shot 1]): partially_preserved - looks, expression, hairstyle, accessories, skin tone, body shape, every movement, and body orientation match <Video 1> frame by frame; the clothes are changed to match <Picture 1>.\n"
    "<Picture 1>: fully_preserved - the source of the new clothes' appearance.\n"
    "<Video 1> (source video): attribute_transfer - the person's identity, the number of people, movements, body orientation, camera position, framing, and scene are kept; only the clothes change.\n\n"
    "detailed_description:\n" + _FRAME_EN + "\n"
    "[Shot 1] <Subject 1> " + _ORIENT_POS_EN + "The clothes match <Picture 1> exactly, and the fabric moves naturally with the motion. Her hairstyle and accessories match <Video 1> exactly. Her looks, expression, and body shape match <Video 1> exactly.\n\n"
    "overall_soundscape:\nThe same ambience and movement sounds as <Video 1>.\n\nnon_diegetic_music:\nN/A")
# 换人：去掉“画面里不再出现原来的人”“脸始终清晰”（后者会让背面画面也去画脸）
REF_SWAP_TPL_POS = None  # 在下面按 REF_SWAP_TPL 替换生成


# 2026-11-04：改衣 · 参考生成打开“直接用作参考图”但没放图 = 跳过 Qwen 改图，只有原视频（<Video 1>）+ 提示词。
# 模板里所有提到 <Picture 1> 的地方改成“按描述”，提到它的整行去掉（H3 收到的素材里没有图，标签不能悬空）
_NOPIC_SUBS = [
    ('，也就是 <Picture 1> 里的同一个人', ''), (', the same person shown in <Picture 1>', ''),
    ('只把衣服换成 <Picture 1> 里的样子', '只按描述更换衣服'), ('衣服换成 <Picture 1> 里的样子', '衣服按描述更换'),
    ('衣服和 <Picture 1> 一致，正面、背面和袖子都一样，布料随动作自然摆动', '衣服按描述更换，布料随动作自然摆动'),
    ('衣服与 <Picture 1> 完全相同，布料随动作自然摆动', '衣服按描述更换，布料随动作自然摆动'),  # 正向写法（POS）
    ('The clothes match <Picture 1> exactly, and the fabric moves', 'The clothes are changed as described, and the fabric moves'),
    ('only the clothes are changed to match <Picture 1>', 'only the clothes are changed as described'),
    ('the clothes are changed to match <Picture 1>', 'the clothes are changed as described'),
    ('The clothes match <Picture 1> on the front, the back, and the sleeves, and the fabric moves', 'The clothes are changed as described, and the fabric moves'),
    ('，与 <Picture 1> 一致', ''),
    (', matching <Picture 1>', ''),
]


def _nsub(text):
    """只做 _NOPIC_SUBS 里的替换（一小段文字用；不删行、不兜底）"""
    for a, b in _NOPIC_SUBS:
        text = text.replace(a, b)
    return text


def _TT(name, nopic):
    """没放图时用“无参考图”那一份模板（名字后面加 _NP）"""
    return _T(name + '_NP' if nopic else name)


def _nopic(text):
    for a, b in _NOPIC_SUBS:
        text = text.replace(a, b)
    text = '\n'.join(l for l in text.split('\n') if not l.lstrip().startswith('<Picture 1>'))
    if '<Picture' in text:  # 兜底：还有没替换到的说法（比如用户自己的补充里写了），把标签换成文字，不留悬空的标签
        text = text.replace('<Picture 1>', '描述' if re.search(r'[一-鿿]', text) else 'the description')
    return text


_NOT_KEEP = re.compile(r'衣服|衣物|原样|原来|不变|段|秒|开头|结尾|之前|之后|人物|部位|clothes|clothing|outfit|original|half|second|same'
                       r'|动作|表情|姿势|姿态|长相|五官|发型|身材|体型|肤色|背景|场景|样子|镜头|机位|光线|^(?:脸|脸部|头发|身体|皮肤|人)$'  # 2026-11-10：去掉“人物的”前缀以后，“保留人物的动作 / 脸”别被当成衣物
                       r'|\b(?:pose|motion|movements?|expression|face|hair(?:style)?|body|background|scene|camera|lighting)$', re.I)
# 衣物（区分衣服和饰品：换衣写了“保留 X”时，衣服写“穿着”、饰品写“戴着”）
_GARMENT = re.compile(r'衣|衫|外套|夹克|西装|针织|背心|吊带|裙|裤|T恤|披肩|袍|校服|制服|马甲|胸罩|文胸|比基尼|肚兜|bra\b|bikini|lingerie|underwear|panties|thong|jacket|coat|blazer|shirt|blouse|cardigan|sweater|hoodie|vest|skirt|dress|pants|trousers|shorts|jeans|robe|top\b', re.I)


def _wear_zh(keep):
    """“大衣外套、白色长袜、脖子上的饰品” → “穿着大衣外套和白色长袜，戴着脖子上的饰品”（2026-11-09：以前对饰品也写“穿着”）"""
    xs = [x for x in (keep or '').split('、') if x]
    g = [x for x in xs if _GARMENT.search(x) or re.search(r'袜|鞋|靴|丝', x)]
    a = [x for x in xs if x not in g]
    j = lambda v: v[0] if len(v) == 1 else '、'.join(v[:-1]) + '和' + v[-1]
    return '，'.join((['穿着' + j(g)] if g else []) + (['戴着' + j(a)] if a else []))


# 2026-11-10 用户：“保留人物上面的深藏青色短款圆领外套”没认出来——整句带“人物”，被 _NOT_KEEP 当成“保留前半段人物衣服”那类句子丢掉了。
# 先去掉开头“谁的 / 身上的”这种前缀（人物上面的、她身上的、原视频里人物的），再判断；“头上的 / 脖子上的”这类位置留着（是在说哪一件）
_KEEP_PRE = re.compile(r'^(?:原视频|视频|画面)?(?:里|中)?的?(?:人物|她|他|女生|女孩|女人|主角)?的?(?:身上|上面|上身)?的')


# 2026-11-11 用户：“保留外面的深色外套、领带和裙子不变”只认出外套和领带——最后一样带着“不变”，整样被当成“保留原来的不变”那类话丢掉了。
# 先去掉末尾的“（都 / 也）（保持）不变 / 原样 / 照旧”再判断；“原来的衣服不变”去掉以后还是“原来的衣服”，照样不算
_KEEP_TAIL_ZH = re.compile(r'(?:都|也|均|仍然|依然)?(?:保持)?(?:不变|原样|照旧|不动)$')
_KEEP_TAIL_EN = re.compile(r'\s+(?:unchanged|as is|as-is|intact)$', re.I)


def _keep_clean(x, en):
    return _KEEP_TAIL_EN.sub('', x).strip() if en else _KEEP_TAIL_ZH.sub('', _KEEP_PRE.sub('', x, count=1).strip()).strip()



# 2026-11-09 换衣也认“保留 X”：旧写法只在开头写一次“现在穿着保留灰色外套，里面换成……”，后面三处都是“只改变衣服”，
# 只用文字（不走 Qwen）时外套整件丢了。所以认出保留的东西、每一段都写一遍，外套就保得住。
# 换衣里“穿着 / 戴着 / 只…”常是在描述新衣服（“穿着红色比基尼”），所以只认 保留 / 留着 / 留下 / X 不变
_KEEP_OUT_ZH = re.compile(r'(?:只|仅)?(?:保留|留着|留下)(?:原来的|原本的|原视频里?的|她的|身上的)?([^，,。.；;]{1,20})|([^，,。.；;、]{1,12}?)(?:保持不变|不变|不换)')
_KEEP_OUT_EN = re.compile(r'\b(?:keep(?:ing)?|leav(?:e|ing))\s+(?:on\s+)?(?:her\s+|the\s+)?(?:original\s+)?([a-z][a-z \-]{1,30}?)(?:\s+(?:on|as is|unchanged|the same))?(?=[,.;]|$)'
                          r'|\b(?:her\s+|the\s+)?([a-z][a-z \-]{1,20}?)\s+(?:stays?|remains?)\s+(?:the same|unchanged|as is)\b', re.I)


def _keep_out(text, en):
    """换衣时要保留的衣物 / 配饰，和去掉“保留……”那句以后剩下的要求。返回 (keep, rest)；没写保留就是 ('', 原话)"""
    got, spans = [], []
    for m in (_KEEP_OUT_EN if en else _KEEP_OUT_ZH).finditer(text or ''):
        k = re.sub(r'[（(][^）)]*[）)]?', '', next(g for g in m.groups() if g)).strip()
        ok = False
        for x in re.split(r'\s*(?:、|和|及|以及|与|,|\band\b)\s*', k):
            x = _keep_clean(x.strip(), en)
            # “外面不变、里面换成……”里的“外面”只是位置、不算一件衣服；“外面的深色外套”“里面的白色背心”是在说哪一件，要算（2026-11-11 用户：以前带“外面 / 里面”的整样丢掉）
            if x and not _NOT_KEEP.search(x) and not re.search(r'脱|去掉|换|不要|其余|其他|全部|别的|\b(?:rest|other|everything|off|change)\b', x, re.I) \
                    and not re.fullmatch(r'(?:最)?(?:外面|里面|里边|外边|外层|内层|里层)(?:的|那件|这件|那层|一层)?(?:衣服|衣物)?', x):
                ok = True
                if x not in got:
                    got.append(x)
        if ok:
            spans.append(m.span())
    rest = text or ''
    for a, b in reversed(spans):
        rest = rest[:a] + rest[b:]
    rest = re.sub(r'[，,；;、]\s*[，,；;、]', '，' if not en else ',', rest)
    rest = re.sub(r'([。.!?！？])\s*[，,；;、]+\s*', r'\1', rest)  # 去掉“保留……”那句后：“一致。，领带……”→“一致。领带……”（2026-11-11）
    rest = re.sub(r'^[\s，,。.；;、]+|[\s，,。.；;、]+$', '', rest)
    return ('、' if not en else ', ').join(got), rest


def _outfit_keep(t, keep, rest, en, nopic):
    """换衣模板（正向写法）里每一段都写上：{keep} 与 <Video 1> 完全相同、始终在身上；其余衣服按描述 / <Picture 1> 更换"""
    if en:
        subs = [('\x00.\n', f'. Her {keep} matches <Video 1> exactly and stays on her the whole time' + (f'; {rest}' if rest else '') + '.\n'),
                ('every movement and body orientation, and the scene', f'every movement and body orientation, the {keep}, and the scene'),
                ('only the clothes are changed to match <Picture 1>', f'the {keep} matches <Video 1> exactly and stays on her the whole time, and the rest of the clothes are changed to match <Picture 1>'),
                ('; the clothes are changed to match <Picture 1>.', f'; the {keep} match <Video 1> exactly (color, style, size, where they sit on her body, and how they move); the rest of the clothes are changed to match <Picture 1>.'),
                ('and scene are kept; only the clothes change.', f'scene, and the {keep} are kept; only the clothes besides the {keep} change.'),
                ('The clothes match <Picture 1> exactly, and the fabric moves',
                 f'She wears the {keep} the whole time, exactly as in <Video 1>; ' + ((rest or 'the rest of her clothes are changed as described') if nopic else 'the rest of her clothes match <Picture 1> exactly') + ', and the fabric moves')]
    else:
        wear = _wear_zh(keep)
        subs = [('\x00。\n', f'。{keep}与 <Video 1> 完全相同，她始终{wear}' + (f'；{rest}' if rest else '') + '。\n'),
                ('全部动作和身体朝向，以及场景', f'全部动作和身体朝向、{keep}，以及场景'),
                ('只把衣服换成 <Picture 1> 里的样子', f'{keep}与 <Video 1> 完全相同、始终在她身上，其余衣服换成 <Picture 1> 里的样子'),
                ('；衣服换成 <Picture 1> 里的样子。', f'；{keep}与 <Video 1> 完全相同（颜色、款式、大小、在身上的位置和随动作的摆动都相同）；其余衣服换成 <Picture 1> 里的样子。'),
                ('构图和场景；只改变衣服。', f'构图、场景和{keep}；只改变{keep}以外的衣服。'),
                ('衣服与 <Picture 1> 完全相同，布料随动作自然摆动',
                 f'她始终{wear}，{keep}与 <Video 1> 完全相同；' + ((rest or '其余衣服按描述更换') if nopic else '其余衣服与 <Picture 1> 完全相同') + '，布料随动作自然摆动')]
    if nopic:  # 没放图：模板是“无参考图”那一份（2026-11-09），要找的那几句和换上去的也照 _NOPIC_SUBS 改成“按描述”
        subs = [(_nsub(a), _nsub(b)) for a, b in subs]
    if any(t.count(a) != 1 for a, _ in subs):  # 模板改过、这里没跟上：退回普通换衣写法（调用的地方处理），不要悄悄少写几段
        return None
    for a, b in subs:
        t = t.replace(a, b)
    return _nopic(t) if nopic else t


def _structured(p):
    """提示词框里写的已经是一整段结构化提示词（AI 助手写的 / 自己按结构写的）：原样用，不再套模板"""
    return bool(re.search(r'subject_definitions\s*:|<Subject \d+>', p or ''))


def _prompt(j):
    if j.get('space') in ('n', 'v'):
        _tl.sp = j['space']
    e, user = j['edit'], j['prompt'].strip()
    tgt = e['target']
    if not e.get('tpl', True):  # 关了模板：完全按提示词框里写的
        return user
    if e.get('recipe'):  # 作者配方：人物的样子看图自动写（videogen.ref_describe → ref_desc），提示词框里写的接在后面
        if _structured(user) or re.match(r'^\s*(body_swap|motion_transfer)\s*:', user):  # 已经是整段（“填入模板”填的）：原样用，‹…› 占位换成看图写的
            return re.sub(r'‹人物图里的场景[^›]*›', e.get('ref_env') or 'the guide setting', re.sub(r'‹人物图中的人[^›]*›', e.get('ref_desc') or 'person', user))
        d = ', '.join(x for x in (e.get('ref_desc') or '', user.rstrip('。.')) if x) or 'person'
        if e['recipe'] == 'cs11':
            return _fmt(_T('CS11_TPL'), pdetails=d)
        env = (e.get('ref_env') or '').strip().rstrip('.')
        return _fmt(_T('MOTION_TPL'), pdetails=d, setting=_fmt(_T('MOTION_SETTING_PIC'), env=env) if env else MOTION_SETTING_GUIDE)
    if e.get('vg'):  # 改衣 · Viggle 重拍：六段式（写了整段结构化的就原样用）
        if _structured(user):
            return user
        return vg_prompt(e, user, j.get('_frames'))
    if e['task'] == 'head' and e.get('head_by') == 'fs':  # 换头 · 换脸 LoRA：作者说只要触发词
        return _T('FS_TPL')
    if is_ref(e):  # 参考生成：结构化模板；写了整段结构化提示词就原样用
        if _structured(user):
            return user
        d, en = user.rstrip('。.'), e.get('plang') == 'en'
        if e['task'] == 'swap':
            if en:
                return _fmt(_T('EN_REF_SWAP_TPL'), desc=(': ' + d) if d else '', who=tgt or 'main person')
            return _fmt(_T('REF_SWAP_TPL'), desc=('：' + d) if d else '', who=tgt or '主要人物')
        nopic = e.get('own') and not e.get('ref')  # 直接用作参考图但没放图：跳过 Qwen，只按提示词改
        keep, rest = _keep_out(user, en) if _pos() else ('', '')
        if keep:  # 换衣写了“保留 X”：每一段都写上 X 与原视频相同（2026-11-09）
            t = _outfit_keep(_fmt(_TT('EN_REF_OUTFIT_TPL' if en else 'REF_OUTFIT_TPL', nopic), desc='\x00', who=tgt or ('person' if en else '人物')), keep, rest.rstrip('。.'), en, nopic)
            if t:
                return t
        if nopic:  # 没有图：描述写成“现在穿着……”
            if en:
                return _nopic(_fmt(_T('EN_REF_OUTFIT_TPL_NP'), desc=(', now wearing ' + d) if d else '', who=tgt or 'person'))
            return _nopic(_fmt(_T('REF_OUTFIT_TPL_NP'), desc=('，现在穿着' + d) if d else '', who=tgt or '人物'))
        if en:
            return _fmt(_T('EN_REF_OUTFIT_TPL'), desc=((', now wearing ' + d) if d and not e.get('own') else (': ' + d) if d else ''), who=tgt or 'person')
        t = _fmt(_T('REF_OUTFIT_TPL'), desc=(('，现在穿着' + d) if d and not e.get('own') else ('：' + d) if d else ''), who=tgt or '人物')
        if e.get('emph') and d:  # 2026-11-10：写的描述以前只在开头出现一次，后面三段只写“换成 <Picture 1> 里的样子”——小改动（肩带滑落）被原视频拉回去。每一段都写上
            t = (t.replace('只把衣服换成 <Picture 1> 里的样子。', f'只把衣服换成 <Picture 1> 里的样子：{d}。', 1)
                  .replace('；衣服换成 <Picture 1> 里的样子。', f'；衣服换成 <Picture 1> 里的样子：{d}。', 1)
                  .replace('衣服与 <Picture 1> 完全相同，布料随动作自然摆动。', f'衣服与 <Picture 1> 完全相同：{d}，布料随动作自然摆动。', 1))
        return t
    return user  # 别的做法（保真替换、参考编辑）不用这里的模板


def _ts(sec):
    m, x = divmod(max(0.0, sec), 60)
    return f'{int(m):02d}:{x:06.3f}'


def vg_prompt(e, user, frames=None):
    """Viggle 重拍的六段式：{desc} = 提示词框里写的；Qwen 改的那一帧钉在原来那一帧上时写明“那一刻和 <Picture 1> 一样”"""
    d = user.rstrip('。.')
    m = re.search(r'(?:换成|改成|变成|换上|穿上)(.+)$', d)  # “A 换成 B”只留 B：写成目标视频的样子（Viggle 的写法），也不写要去掉的那件（正向提示词原则）
    d = (m.group(1).strip('，, ') if m else d) or 'the new outfit'
    end = _ts(((frames or 124) - 1) / FPS)
    pin = vg_pin(e)
    return _fmt(_T('VG_TPL'), who=e.get('target') or 'the main person', desc=d, end=end, pinline=VG_PIN_LINE if pin is not None else '',
                pinat=f' At {_ts(pin / FPS)} the scene matches <Picture 1>.' if pin is not None else '')


def vg_pin(e):
    """Qwen 改的是窗口里的第几帧（钉在这一帧上）；自己放的图不知道对应哪一帧：不钉，只当参考"""
    return e.get('pick_idx') if e.get('qwen_done') and isinstance(e.get('pick_idx'), int) else None


def templates():
    """网页上给人看的提示词模板（不能改）：‹…› 是会被换掉的部分"""
    U, T = '‹提示词框里写的›', '‹要换掉的人›'
    out = {}
    out['ref_swap'] = _fmt(_T('REF_SWAP_TPL'), desc='：‹提示词框里写的（可选）›', who='‹要换掉的人›')
    out['v11'] = _fmt(_T('CS11_TPL'), pdetails='‹人物图中的人（看图自动写）›, ‹提示词框里写的（可选）›')
    out['motion'] = _fmt(_T('MOTION_TPL'), pdetails='‹人物图中的人（看图自动写）›, ‹提示词框里写的（可选）›', setting=_fmt(_T('MOTION_SETTING_PIC'), env='‹人物图里的场景（看图自动写；图里没有场景时沿用原视频的）›'))
    out['faceswap'] = _T('FS_TPL')
    out['vg'] = _fmt(_T('VG_TPL'), who='‹要改衣的人›', desc='‹提示词框里写的›', end='‹结尾时间›', pinline=VG_PIN_LINE, pinat=' At ‹Qwen 改的那一帧的时间› the scene matches <Picture 1>.')
    out['ref_outfit'] = _fmt(_T('REF_OUTFIT_TPL'), desc='，现在穿着‹提示词框里写的（可选）›', who='‹要改衣的人›')
    try:  # 改衣“参考生成”：给人物改图的那句（Qwen 指令改图）
        import outfit2
        out['outfit_edit'] = outfit2.edit_prompt(U, '‹要改衣的人›', False)
        out['outfit_edit_img'] = outfit2.edit_prompt(U, '‹要改衣的人›', True)
    except Exception:
        pass
    return out


def build(j, w, h, frames, src_name, has_audio, ref_name):
    """拼工作流。节点编号：2 底模、17 采样偏移（自选 LoRA 接在它前面）、4 文字模型、5/6 视频 / 声音 VAE、7 条件、8~16 采样到保存（同 h3_i2v.json）。"""
    e = j['edit']
    j['_frames'] = frames  # Viggle 重拍的提示词要写结尾时间
    ptxt = _prompt(j)
    if (e.get('loc') or {}).get('noref'):  # 局部生成不给参考视频时（测试）：模板里的 <Video 1> 换成文字，H3 才不报“<Video 1> 没接上”
        ptxt = ptxt.replace('<Video 1>', '原视频')
    try:  # 生成记录里的“查看生成时的完整提示词”：记下真正发给 H3 的那段（以前只记了 Qwen 改图那句）
        import prompttrace
        if isinstance(j.get('prompt_trace'), dict) and not any(x.get('label') == '视频生成' for x in j['prompt_trace'].get('stages') or []):
            prompttrace.add(j['prompt_trace'], '视频生成', ptxt)
    except Exception:
        pass
    wf = {
        '2': {'class_type': 'UNETLoader', 'inputs': {'unet_name': '__H3DIFF__', 'weight_dtype': 'default'}},
        '4': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', 'type': 'minimax', 'device': 'default'}},
        '5': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'minimax_h3_video_vae_fp16.safetensors'}},
        '6': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'minimax_h3_audio_vae_fp32.safetensors'}},
        'e1': {'class_type': 'LoadVideo', 'inputs': {'file': src_name}},
        'e2': {'class_type': 'GetVideoComponents', 'inputs': {'video': ['e1', 0]}},
        '7': {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': {'clip': ['4', 0], 'vae': ['5', 0], 'audio_vae': ['6', 0], 'prompt': ptxt,
                                                                 'width': w, 'height': h, 'length': frames, 'ref_image_size': 'match'}},
        '17': {'class_type': 'MiniMaxH3SigmaShift', 'inputs': {'model': ['2', 0], 'shift_video': '__SHIFT__', 'shift_audio': '__ASHIFT__'}},
        '8': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': '__SEED__'}},
        '9': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': '__SAMPLER__'}},
        '10': {'class_type': 'BasicScheduler', 'inputs': {'model': ['17', 0], 'scheduler': '__SCHEDULER__', 'steps': '__STEPS__', 'denoise': 1.0}},
        '11': {'class_type': 'BasicGuider', 'inputs': {'model': ['17', 0], 'conditioning': ['7', 0]}},
        '12': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['8', 0], 'guider': ['11', 0], 'sampler': ['9', 0], 'sigmas': ['10', 0], 'latent_image': ['7', 1]}},
        '13': {'class_type': 'VAEDecode', 'inputs': {'samples': ['12', 0], 'vae': ['5', 0]}},
        '14': {'class_type': 'VAEDecodeAudio', 'inputs': {'samples': ['12', 0], 'vae': ['6', 0]}},
        '15': {'class_type': 'CreateVideo', 'inputs': {'images': ['13', 0], 'audio': ['14', 0], 'fps': '__FPS__'}},
        '16': {'class_type': 'SaveVideo', 'inputs': {'video': ['15', 0], 'filename_prefix': '__PREFIX__', 'format': 'mp4', 'codec': 'h264'}},
    }
    if e.get('base') == 'full':  # 官方完整版 + int8 文字编码器（和 C1 一样：没合并加速，不加加速 LoRA）
        wf['2']['inputs']['unet_name'] = os.path.basename(LITE if e.get('lite') else FULL)
        wf['4']['inputs']['clip_name'] = os.path.basename(LITE_TE if e.get('lite') else FULL_TE)
    ci = wf['7']['inputs']
    if ref_name:
        wf['1'] = {'class_type': 'LoadImage', 'inputs': {'image': ref_name}}
        ci['ref_images.ref_image_0'] = ['1', 0]
        if e.get('ref_max'):
            ci['ref_image_size'] = 'max'
    model = ['2', 0]

    def lora(nid, f, wt):
        nonlocal model
        wf[nid] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': model, 'lora_name': os.path.basename(f), 'strength_model': wt}}
        model = [nid, 0]
    guide = False
    if e.get('recipe'):  # 作者配方（换人 · 新做法 / 动作迁移）：做法 LoRA 1.0 + 原视频走 AddGuide + 人物图当 <Picture 1>；DMD 加速在 videogen 里接（_turbo）
        lora('e31', FILES[e['recipe']], 1.0); guide = True
        if e['recipe'] == 'cs11' and ref_name:  # 换人：人物图先去背景，换成纯浅灰（作者 v1.1 工作流里 BiRefNet 那一步；不去背景时人物图里的房间会被搬进视频）
            gv = int((e.get('xt') or {}).get('gray') or RMBG_GRAY)
            g = gv * 65536 + gv * 256 + gv
            wf['rb1'] = {'class_type': 'LoadBackgroundRemovalModel', 'inputs': {'bg_removal_name': os.path.basename(RMBG)}}
            wf['rb2'] = {'class_type': 'RemoveBackground', 'inputs': {'bg_removal_model': ['rb1', 0], 'image': ['1', 0]}}
            wf['rb3'] = {'class_type': 'GetImageSize', 'inputs': {'image': ['1', 0]}}
            wf['rb4'] = {'class_type': 'EmptyImage', 'inputs': {'width': ['rb3', 0], 'height': ['rb3', 1], 'batch_size': 1, 'color': g}}
            wf['rb5'] = {'class_type': 'ImageCompositeMasked', 'inputs': {'destination': ['rb4', 0], 'source': ['1', 0], 'x': 0, 'y': 0, 'resize_source': False, 'mask': ['rb2', 0]}}
            ci['ref_images.ref_image_0'] = ['rb5', 0]
    elif is_ref(e):  # 参考生成：原视频当 <Video 1>（要新生成声音时把原声也带上），人物图 / 换好衣服的图当 <Picture 1>；不加 LoRA
        if not (e.get('loc') or {}).get('noref'):
            ci['ref_videos.ref_video_0'] = ['e2', 0]
        if e.get('ffguide') and ref_name and ((e.get('pick_idx') == 0 and e.get('qwen_done')) or e.get('ff_own')):  # 首帧锁定（实验，2026-11-06，默认关）：参考生成开头动作会慢半拍，
            # 把 Qwen 换好衣服的那一帧（就是窗口第 0 帧）当首帧引导，开头就钉在原视频的姿势上（AddGuide 自己缩放；② 只认第 0 帧、直接来自 LoadImage 的图）
            wf['e5'] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': ['7', 0], 'vae': ['5', 0], 'latent': ['7', 1], 'image': ['1', 0], 'frame_idx': 0}}
            wf['11']['inputs']['conditioning'] = ['e5', 0]
        if has_audio and e['audio'] == 'gen':
            ci['ref_video_audios.ref_video_audio_0'] = ['e2', 1]
    elif e['task'] == 'head' and e.get('head_by') == 'fs':  # 换头 · 换脸 LoRA（UntMods）：原视频当参考视频、头像当参考图（作者工作流 R2V 模式）
        lora('e31', FILES['faceswap'], 1.0)
        ci['ref_videos.ref_video_0'] = ['e2', 0]
        if has_audio and e['audio'] == 'gen':
            ci['ref_video_audios.ref_video_audio_0'] = ['e2', 1]
    l2 = (e.get('xt') or {}).get('lora2')  # 夜测：再叠一个 LoRA（换头 + 换人 v1.1 一起，作者说可以试）
    if l2 and guide:
        lora('x31', 'loras/' + os.path.basename(str(l2[0])), float(l2[1]))
    if guide:
        wf['e3'] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': ['7', 0], 'vae': ['5', 0], 'latent': ['7', 1], 'image': ['e2', 0], 'frame_idx': 0}}
        wf['11']['inputs']['conditioning'] = ['e3', 0]
    if e.get('pose') and pose_ok():  # 动作跟随（2026-11-10）：原视频的全身骨架（身体、手、脸、脚）逐帧约束生成——H3 官方 Fun ControlNet Union 的接法
        wf['pp0'] = {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': POSE_FILES['sdpose']}}
        wf['pp1'] = {'class_type': 'UNETLoader', 'inputs': {'unet_name': POSE_FILES['detr'], 'weight_dtype': 'default'}}
        wf['pp3'] = {'class_type': 'RTDETR_detect', 'inputs': {'model': ['pp1', 0], 'image': ['e2', 0], 'threshold': 0.5, 'class_name': 'person', 'max_detections': 2}}
        wf['pp4'] = {'class_type': 'SDPoseKeypointExtractor', 'inputs': {'model': ['pp0', 0], 'vae': ['pp0', 2], 'image': ['e2', 0], 'batch_size': 16, 'bboxes': ['pp3', 0]}}
        wf['pp5'] = {'class_type': 'SDPoseDrawKeypoints', 'inputs': {'keypoints': ['pp4', 0], 'draw_body': True, 'draw_hands': True, 'draw_face': True, 'draw_feet': True,
                                                                     'stick_width': 4, 'face_point_size': 2, 'score_threshold': 0.5, 'draw_head': True}}
        wf['pp6'] = {'class_type': 'ModelPatchLoader', 'inputs': {'name': POSE_FILES['patch2']}}
        wf['pp7'] = {'class_type': 'MiniMaxH3FunControlNetApply', 'inputs': {'model': model, 'model_patch': ['pp6', 0], 'vae': ['5', 0], 'strength': float(e.get('pose_w') or POSE_W),
                                                                            'start_percent': 0.0, 'end_percent': 1.0, 'control_video': ['pp5', 0]}}
        model = ['pp7', 0]
    L = e.get('loc')
    if L and e['task'] == 'outfit':  # 局部生成（测试用，见 _loc_in）：只重画 mask 里的，其余照原视频
        model = _loc_build(wf, e, L, model)
    wf['17']['inputs']['model'] = model
    if e.get('vg'):  # 改衣 · Viggle 重拍：换成 Viggle 官方的接法（自选 LoRA 照样接在 17 前面）
        _vg_build(wf, e, ptxt, ref_name, frames, w, h, has_audio)
        return wf
    x2 = (e.get('xt') or {}).get('x2')
    if x2:  # 夜测：作者原版两段式——先按小尺寸生成，H3 latent 放大（LBH-123-AI，作者的 LMS 版权重），再加 LMS LoRA 用 3 步细化到目标尺寸
        _x2_build(wf, e, x2, w, h)
    return wf


def _vg_build(wf, e, ptxt, ref_name, frames, w, h, has_audio):
    """Viggle Remake · edit（官方 remake_edit_api.json 的接法）：int8 合并版底模 → KeyframeUntil 0.9 → BasicGuider；
    RemakeConditioning（原视频 = <Video 1>、改好的图 = <Picture 1>，钉在 Qwen 改的那一帧）+ RemakeNoise；6 步 ManualSigmas。原声当干净的目标声音"""
    model = wf['17']['inputs']['model']  # 前面接的自选 LoRA（如果有）
    if '1' not in wf:
        raise RuntimeError('Viggle 重拍需要一张改好的图')
    keep = {model[0]} if isinstance(model, list) else set()  # 自选 LoRA 的节点要留着：以前按前缀 'e3' 一起删了，工作流接到不存在的节点（2026-11-15 审查）
    for k in [k for k in wf if k.startswith(('pp', 'lm', 'ln', 'e3', 'e5', 'rb')) and k not in keep and not (k.startswith('e3') and len(k) > 2 and wf[k].get('class_type', '').startswith('Lora'))]:
        wf.pop(k, None)  # 动作跟随 / 局部 / 引导这些都不用
    wf['2']['inputs']['unet_name'] = os.path.basename(VG_FILE)
    wf['4']['inputs']['clip_name'] = os.path.basename(LITE_TE)
    pin = vg_pin(e)
    wf['vg1'] = {'class_type': 'RemakeConditioning', 'inputs': {'clip': ['4', 0], 'vae': ['5', 0], 'audio_vae': ['6', 0], 'source': ['e2', 0], 'prompt': ptxt,
                                                               'ref_1': ['1', 0], 'pins': '' if pin is None else str(min(pin, frames - 1)), 'frames': frames,
                                                               'short_edge': min(w, h)}}
    if has_audio:
        wf['vg1']['inputs']['audio'] = ['e2', 1]
    wf['vg2'] = {'class_type': 'RemakeNoise', 'inputs': {'positive': ['vg1', 0], 'seed': '__SEED__'}}
    wf['vg3'] = {'class_type': 'RemakeKeyframeUntil', 'inputs': {'model': ['17', 0], 'keyframe_until': 0.9}}
    wf['vg4'] = {'class_type': 'ManualSigmas', 'inputs': {'sigmas': VG_SIGMAS}}
    wf['9']['inputs']['sampler_name'] = 'euler'
    wf['11'] = {'class_type': 'BasicGuider', 'inputs': {'model': ['vg3', 0], 'conditioning': ['vg1', 0]}}
    wf['12'] = {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['vg2', 0], 'guider': ['11', 0], 'sampler': ['9', 0], 'sigmas': ['vg4', 0], 'latent_image': ['vg1', 1]}}
    for k in ('7', '8', '10'):
        wf.pop(k, None)
    wf['17']['inputs']['model'] = model


def _x2_build(wf, e, x2, w, h):
    k = float(x2.get('k') or 2.25)  # 第一遍 = 目标 ÷ k（作者默认 0.3 MP ≈ 720p 的 1/2.25）
    w1, h1 = (max(256, int(round(v / k / 32)) * 32) for v in (w, h))
    wf['7']['inputs'].update(width=w1, height=h1)
    c2 = dict(wf['7']['inputs']); c2['prompt'] = c2['prompt'] + '\nEnhance this video with sharp, crisp details while preserving a natural photorealistic appearance.'
    wf['x24'] = {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': c2}
    wf['x21'] = {'class_type': 'LTXVSeparateAVLatent', 'inputs': {'av_latent': ['12', 1]}}  # 第一遍去噪后的结果（作者接的 denoised）
    wf['x22'] = {'class_type': 'MinimaxH3LatentUpscaler3D', 'inputs': {'latent': ['x21', 0], 'model_name': x2.get('up') or 'h3_upscaler_lms_v0.1.safetensors', 'mode': 'target dimensions',
                                                                       'mode.width': w, 'mode.height': h, 'align': 32, 'enable_temporal_chunking': True, 'force_unload': True,
                                                                       'device': 'cuda', 'precision': 'fp16'}}
    wf['x23'] = {'class_type': 'LTXVConcatAVLatent', 'inputs': {'video_latent': ['x22', 0], 'audio_latent': ['x21', 1]}}
    pos = ['x24', 0]
    if 'e3' in wf:  # 第二遍也用原视频逐帧引导
        wf['x25'] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': ['x24', 0], 'vae': ['5', 0], 'latent': ['x23', 0], 'image': ['e2', 0], 'frame_idx': 0}}
        pos = ['x25', 0]
    m = wf['17']['inputs']['model']
    lw = float(x2.get('lms', 0.7))
    if lw > 0:
        wf['x26'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['17', 0], 'lora_name': 'minimax_h3_lms_v1.0_r64.safetensors', 'strength_model': lw}}
        m = ['x26', 0]
    else:
        m = ['17', 0]
    wf['x27'] = {'class_type': 'BasicGuider', 'inputs': {'model': m, 'conditioning': pos}}
    wf['x28'] = {'class_type': 'ManualSigmas', 'inputs': {'sigmas': x2.get('sig') or '0.9035, 0.6316, 0.3158, 0.0000'}}
    wf['x29'] = {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['8', 0], 'guider': ['x27', 0], 'sampler': ['9', 0], 'sigmas': ['x28', 0], 'latent_image': ['x23', 0]}}
    wf['13']['inputs']['samples'] = ['x29', 0]
    wf['14']['inputs']['samples'] = ['x29', 0]


def _loc_build(wf, e, L, model):
    """SAM3 逐帧跟踪 → mask（外扩、扣掉脸 / 头发 / 手）→ ControlNet 的 mask + source_video；解码后 mask 外贴回原视频（去毛边、边缘柔化）"""
    wf['lm0'] = {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM_FILE}}
    wf['lm1'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['lm0', 1], 'text': L['q']}}
    wf['lm2'] = {'class_type': 'SAM3_VideoTrack', 'inputs': {'images': ['e2', 0], 'model': ['lm0', 0], 'conditioning': ['lm1', 0], 'detection_threshold': L['thr'],
                                                             'max_objects': 8, 'detect_interval': 1}}
    wf['lm3'] = {'class_type': 'SAM3_TrackToMask', 'inputs': {'track_data': ['lm2', 0], 'object_indices': ''}}
    cloth = mask = ['lm3', 0]
    if L['grow']:
        wf['lm4'] = {'class_type': 'GrowMask', 'inputs': {'mask': mask, 'expand': L['grow'], 'tapered_corners': True}}
        mask = ['lm4', 0]
    if L['protect']:
        wf['lm5'] = {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['lm0', 1], 'text': L.get('pq') or 'face, hair, hand'}}
        wf['lm6'] = {'class_type': 'SAM3_VideoTrack', 'inputs': {'images': ['e2', 0], 'model': ['lm0', 0], 'conditioning': ['lm5', 0], 'detection_threshold': 0.4,
                                                                 'max_objects': 8, 'detect_interval': 1}}
        wf['lm7'] = {'class_type': 'SAM3_TrackToMask', 'inputs': {'track_data': ['lm6', 0], 'object_indices': ''}}
        wf['lm8'] = {'class_type': 'GrowMask', 'inputs': {'mask': ['lm7', 0], 'expand': L.get('pgrow', 4), 'tapered_corners': True}}
        prot = ['lm8', 0]
        if L.get('pqout'):  # 只保护衣服外面的部分：压在衣服上的手跟着一起重画
            wf['lmA'] = {'class_type': 'MaskComposite', 'inputs': {'destination': ['lm8', 0], 'source': cloth, 'x': 0, 'y': 0, 'operation': 'subtract'}}
            prot = ['lmA', 0]
        wf['lm9'] = {'class_type': 'MaskComposite', 'inputs': {'destination': mask, 'source': prot, 'x': 0, 'y': 0, 'operation': 'subtract'}}
        mask = ['lm9', 0]
    if L.get('native'):  # 11-12 测试：H3 自己的局部重画——原视频编码成 latent，mask 外的 token 当干净的原画面，只有 mask 里生成（不走 ControlNet 的灰洞）
        wf['ln0'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['e2', 0], 'vae': ['5', 0]}}
        wf['ln1'] = {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': ['ln0', 0], 'mask': mask}}
        # audio_latent 在 h3methods.to_t8 里接到 T8 条件的 av_latent；声音整段重新生成（收尾时换回原声）
        wf['ln2'] = {'class_type': 'MiniMaxH3SourceAVPrepareT8', 'inputs': {'video_latent': ['ln1', 0], 'audio_latent': ['ln1', 0], 'video_mode': 'remix', 'video_denoise_strength': 1.0,
                                                                           'audio_mode': 'regenerate', 'audio_denoise_strength': 1.0, 'audio_fit_policy': 'fit_to_video_generate_tail',
                                                                           'dtype_device_policy': 'match_video'}}
    elif 'pp7' in wf and not L['sep']:  # 和动作骨架同一层（同一个强度）
        wf['pp7']['inputs'].update(mask=mask, source_video=['e2', 0])
        if isinstance(L.get('w'), float) and L['w'] != 1.0:
            pass  # 同一层时强度就是动作跟随的那个（pose_w）
    else:  # 单独一层：自己的强度（和动作那层叠着）
        if 'pp6' not in wf:
            wf['pp6'] = {'class_type': 'ModelPatchLoader', 'inputs': {'name': POSE_FILES['patch2']}}
        wf['lmc'] = {'class_type': 'MiniMaxH3FunControlNetApply', 'inputs': {'model': model, 'model_patch': ['pp6', 0], 'vae': ['5', 0], 'strength': L['w'],
                                                                            'start_percent': 0.0, 'end_percent': L.get('end', 1.0), 'mask': mask, 'source_video': ['e2', 0]}}
        model = ['lmc', 0]
    if L['dump']:  # 分析用：mask 也存成视频（videogen 收尾时另存一份 <任务>_mask.mp4）
        wf['lmd0'] = {'class_type': 'MaskToImage', 'inputs': {'mask': mask}}
        wf['lmd1'] = {'class_type': 'CreateVideo', 'inputs': {'images': ['lmd0', 0], 'fps': FPS}}
        wf['lmd2'] = {'class_type': 'SaveVideo', 'inputs': {'video': ['lmd1', 0], 'filename_prefix': '__PREFIX___mask', 'format': 'mp4', 'codec': 'h264'}}
        # 11-12 测接缝：贴回之前的生成画面、原视频的衣服 / 脸手 mask 也各存一份（<任务>_mask_raw / _cloth / _prot / _gcloth）
        for k, src, is_mask in (('raw', ['13', 0], False), ('cloth', cloth, True), ('prot', ['lm8', 0] if L['protect'] else None, True)):
            if src is None:
                continue
            if is_mask:
                wf[f'lmd_{k}0'] = {'class_type': 'MaskToImage', 'inputs': {'mask': src}}
                src = [f'lmd_{k}0', 0]
            wf[f'lmd_{k}1'] = {'class_type': 'CreateVideo', 'inputs': {'images': src, 'fps': FPS}}
            wf[f'lmd_{k}2'] = {'class_type': 'SaveVideo', 'inputs': {'video': [f'lmd_{k}1', 0], 'filename_prefix': f'__PREFIX___mask_{k}', 'format': 'mp4', 'codec': 'h264'}}
    if L['paste']:
        paste = mask
        if L['clean']:  # 去毛边（11-03）：在生成的画面上再找一次衣服，只贴回（新衣服外扩 3 像素 ∪ 原来的衣服）∩ 生成用的 mask
            wf['lp0'] = {'class_type': 'SAM3_VideoTrack', 'inputs': {'images': ['13', 0], 'model': ['lm0', 0], 'conditioning': ['lm1', 0], 'detection_threshold': L['thr'],
                                                                     'max_objects': 8, 'detect_interval': 1}}
            wf['lp1'] = {'class_type': 'SAM3_TrackToMask', 'inputs': {'track_data': ['lp0', 0], 'object_indices': ''}}
            wf['lp2'] = {'class_type': 'GrowMask', 'inputs': {'mask': ['lp1', 0], 'expand': 3, 'tapered_corners': True}}
            wf['lp3'] = {'class_type': 'MaskComposite', 'inputs': {'destination': ['lp2', 0], 'source': cloth, 'x': 0, 'y': 0, 'operation': 'or'}}
            wf['lp4'] = {'class_type': 'MaskComposite', 'inputs': {'destination': ['lp3', 0], 'source': mask, 'x': 0, 'y': 0, 'operation': 'and'}}
            paste = ['lp4', 0]
            if L['dump']:
                wf['lmd_g0'] = {'class_type': 'MaskToImage', 'inputs': {'mask': ['lp1', 0]}}
                wf['lmd_g1'] = {'class_type': 'CreateVideo', 'inputs': {'images': ['lmd_g0', 0], 'fps': FPS}}
                wf['lmd_g2'] = {'class_type': 'SaveVideo', 'inputs': {'video': ['lmd_g1', 0], 'filename_prefix': '__PREFIX___mask_gcloth', 'format': 'mp4', 'codec': 'h264'}}
        wf['lp5'] = {'class_type': 'MaskToImage', 'inputs': {'mask': paste}}
        fr = max(1, L['feather'])
        wf['lp6'] = {'class_type': 'ImageBlur', 'inputs': {'image': ['lp5', 0], 'blur_radius': fr, 'sigma': fr / 2}}
        wf['lp7'] = {'class_type': 'ImageToMask', 'inputs': {'image': ['lp6', 0], 'channel': 'red'}}
        wf['lp8'] = {'class_type': 'ImageCompositeMasked', 'inputs': {'destination': ['e2', 0], 'source': ['13', 0], 'x': 0, 'y': 0, 'resize_source': False, 'mask': ['lp7', 0]}}
        wf['15']['inputs']['images'] = ['lp8', 0]
    return model


# 动作跟随（2026-11-10）：H3 Fun ControlNet Union（alibaba-pai，Comfy-Org 打包的 int8）+ SDPose 全身姿态 + RT-DETR 找人；三个文件都在才可用
# 强度 11-10 测过（docs/AB测试/正向提示词_1109 图 12；0~7 秒、种子 1234、480p）：不开 0.135，1.0 = 0.072 但大衣和颈饰没了，0.6 = 0.043 且大衣、颈饰、长袜都在
# 2.0（2026-11-12 起，第一版已删）：官方推荐 1.0；测过 0.6 = 0.063，比 1.0（0.054）和第一版 0.6（0.059）都差；1.0 外套也在（第一版开到 1.0 会抹掉外套）
POSE_W = 1.0
POSE_FILES = {'sdpose': 'sdpose_wholebody_fp16.safetensors', 'detr': 'rt_detr_v4-x-hgnet_fp16.safetensors',
              'patch2': 'minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors'}  # 2.0（2026-11-12 起唯一的一版）
SAM_FILE = 'sam3.1_multiplex_fp16.safetensors'  # 局部生成找衣服 / 人（checkpoints）


def pose_ok(v='2'):  # v：以前分第一版 / 2.0，现在只有 2.0
    return all(V._have(f) for f in ('model_patches/' + POSE_FILES['patch2'], 'checkpoints/' + POSE_FILES['sdpose'], 'diffusion_models/' + POSE_FILES['detr']))


def exact_trim(j, dst, src):
    """把成品（和对比用的原视频）裁成正好选的那一段，按成品和原视频的帧差对齐（成品通常早 2 帧）。
    窗口见 prepare。返回 (帧差, 把握)；裁不了时返回 None（保持原样）。"""
    e = j['edit']; ws = e.get('win')
    if ws is None:
        return None
    s0, want = float(e['start']), float(e.get('want') or 0)
    pg, ps = V._probe(dst), V._probe(src)
    gd = pg.get('duration') or 0
    try:
        lag, conf = V.motion_lag(dst, src)
    except Exception:
        lag, conf = None, 0.0
    if lag is None:
        lag = V.H3_LAG
    F = FPS; fo = round((s0 - ws) * F)  # 按整帧算（处理好的原视频是 24 fps，从窗口起点开始）
    lf = round(lag * F)
    if fo - lf < 0:  # 成品比原视频晚太多（很少见）：从成品开头起，选段起点往后挪几帧
        fo = lf
    n = min(round((e['start'] + want - ws) * F) - fo, int(gd * F + 1e-6) - (fo - lf), int((ps.get('duration') or 0) * F + 1e-6) - fo)
    if n < 5:
        return None
    s0 = ws + fo / F
    t0, so, dur = (fo - lf) / F, fo / F, n / F  # 成品里从 t0 起、原视频里从 so 起，各取 n 帧
    keep = e.get('audio') == 'keep' and ps.get('audio')
    h = 0.5 / F  # 起点往前半帧：正好从那一帧开始（时间戳的小误差不影响）
    gfps = pg.get('fps') or F  # 插帧过的成品帧率更高：按时间裁，长度一样
    fc = f'[0:v]setpts=PTS-STARTPTS,trim=start={max(0, t0 - 0.5 / gfps):.5f}:duration={dur:.5f},setpts=PTS-STARTPTS[v]'
    if keep:
        fc += f';[1:a]asetpts=PTS-STARTPTS,atrim=start={so:.5f}:duration={dur:.5f},asetpts=PTS-STARTPTS[a]'
    elif pg.get('audio'):
        fc += f';[0:a]asetpts=PTS-STARTPTS,atrim=start={t0:.5f}:duration={dur:.5f},asetpts=PTS-STARTPTS[a]'
    has_a = keep or pg.get('audio')
    tmp, tmp2 = dst + '.cut.mp4', src + '.cut.mp4'
    try:
        V._ff(j, ['-i', dst, '-i', src, '-filter_complex', fc, '-map', '[v]', *(['-map', '[a]', '-c:a', 'aac', '-b:a', '192k'] if has_a else []),
                  '-c:v', 'libx264', *V.GOP, '-crf', '16', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp], '裁成选的那一段')
        V._ff(j, ['-i', src, '-vf', f'setpts=PTS-STARTPTS,trim=start={max(0, so - h):.5f}:duration={dur:.5f},setpts=PTS-STARTPTS',
                  *(['-af', f'asetpts=PTS-STARTPTS,atrim=start={so:.5f}:duration={dur:.5f},asetpts=PTS-STARTPTS', '-c:a', 'aac', '-b:a', '192k'] if ps.get('audio') else ['-an']),
                  '-c:v', 'libx264', *V.GOP, '-crf', '12', '-preset', 'fast', '-pix_fmt', 'yuv420p', tmp2], '裁对比用的原视频')
        os.replace(tmp, dst); os.replace(tmp2, src)
    except BaseException:
        for t in (tmp, tmp2):
            try:
                os.remove(t)
            except OSError:
                pass
        raise
    e['start'], e['want'] = round(s0, 4), round(dur, 4)
    e['trim'] = {'gen_frames': round(gd * F), 'src_frames': round((ps.get('duration') or 0) * F), 'fo': fo, 'lag_frames': lf, 'conf': round(float(conf or 0), 4), 'n': n, 'want_frames': round(want * F)}  # 裁剪时的数字（查问题用）
    return lag, conf


def mux_audio(j, dst, src):
    """保留原声：把处理好的原视频里的声音放进成品（画面不重新编码）。"""
    tmp = dst + '.au.mp4'
    try:
        vd = (V._probe(dst).get('duration') or 0)  # 以画面长度为准（2026-11-06：以前用 -shortest，声音结尾按块对齐、短一点，成品最后 1~3 帧被截掉，拼接时结尾又变回原视频）
        af = ['-af', f'apad=whole_dur={vd:.5f},atrim=end={vd:.5f}'] if vd else ['-shortest']
        V._ff(j, ['-i', dst, '-i', src, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', *af, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', tmp], '放回原声')
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def recognize(e, user):
    """换衣时程序从提示词里认出了什么（完整提示词窗口里显示，方便确认写的有没有被认出来）"""
    u = (user or '').strip(); en = e.get('plang') == 'en'
    if not e.get('tpl', True):
        return '未使用模板：提示词框里的内容原样发送'
    if _structured(u):
        return '提示词框里是整段结构化提示词：原样发送，没有套模板'
    if not (e.get('task') == 'outfit' and is_ref(e)):
        return ''
    k = _keep_out(u, en)[0] if _pos() and u else ''
    return '换衣：' + (f'保留{k}（每一段都写明与原视频相同），其余衣服按描述更换；' if k else '') + '原视频里的饰品、袜子和鞋照原样保留'


# “填入模板”菜单（2026-11-08）：当前任务能用的模板全部列出来，按现在的设置和提示词框里写的拼好；没写的地方用 ‹…› 举例，自己改
FILL_KINDS = {'outfit': [('outfit', '换衣')],
              'swap_ref': [('swap_ref', '换人 · 审美优先')]}


def fill_templates(e, user, has_ref):
    u = '' if _structured(user) else (user or '').strip()
    if e.get('task') == 'motion' or (e.get('task') in (None, 'swap') and e.get('swap_by') == 'v11'):  # 作者配方：人物（和动作迁移的场景）是生成时看人物图写的，这里用 ‹…› 占位
        mo = e.get('task') == 'motion'
        ed = {'task': 'motion' if mo else 'swap', 'swap_by': None if mo else 'v11', 'recipe': 'motion' if mo else 'cs11', 'tpl': True, 'target': '',
              'ref_desc': '‹人物图中的人（生成时看图自动写）›', 'ref_env': '‹人物图里的场景（生成时看图自动写；没有场景就沿用原视频）›' if mo else None}
        return [{'key': 'motion' if mo else 'v11', 'label': '动作迁移' if mo else '换人 · 新版', 'text': _prompt({'edit': ed, 'prompt': u})}]
    task = e.get('task') if e.get('task') in ('swap', 'head', 'outfit') else 'swap'
    base = {**e, 'task': task, 'tpl': True, 'method': 'ref' if task == 'outfit' else e.get('method'), 'target': str(e.get('target') or '').strip()[:200],
            'plang': 'en' if e.get('plang') == 'en' else 'zh', 'ref': bool(has_ref)}
    out = []
    if task == 'swap':
        ed = {**base, 'swap_by': 'ref'}
        for k, label in FILL_KINDS['swap_ref']:
            out.append({'key': k, 'label': label, 'text': _prompt({'edit': ed, 'prompt': u or '‹人物的样子：发型、肤色、身材、穿着（可不写）›'})})
        return out
    if task == 'head':
        return [{'key': 'faceswap', 'label': '换头 · 换脸 LoRA', 'text': _T('FS_TPL')}]
    if e.get('vg') is True:  # 改衣 · Viggle 重拍：六段式，结尾时间按 5 秒写（生成时按实际长度）
        ed = {**base, 'vg': True, 'qwen_done': True, 'pick_idx': 0}
        return [{'key': 'vg', 'label': '改衣 · Viggle 重拍', 'text': vg_prompt(ed, u or '‹新衣服的样子›')}]
    ed = {**base, 'own': bool(e.get('own'))}
    return [{'key': 'outfit', 'label': '换衣', 'text': _prompt({'edit': ed, 'prompt': u or '‹新衣服的样子›', 'seconds': None}), 'own': None}]


# 看图写描述（作者配方看人物图写人物的样子）：由 server.py 接上 DESCRIBE / DESCRIBE_RELEASE
DESCRIBE = None  # (system, user, [dataURL]) -> 回答
DESCRIBE_RELEASE = None
DESCRIBE_OK = lambda: False


def _no_neg(s):
    """只留看得见的（正向提示词原则）：看图模型常补“no pockets, no visible tattoos, scars, or wrinkles”——去掉否定的那一项和紧跟着的短尾巴"""
    out = []
    for grp in s.split(';'):
        keep, drop = [], False
        for p in (x.strip() for x in grp.split(',')):
            if not p:
                continue
            if re.match(r'^(no|not|without|none)\b', p, re.I):
                drop = True; continue
            if drop and (re.match(r'^(or|and|nor)\b', p, re.I) or len(p.split()) <= 2):
                continue
            drop = False; keep.append(p)
        if keep:
            out.append(', '.join(keep))
    return ', '.join(out)


def describe_ref(img, scene=False):
    """（2026-11-12）作者配方用：看人物图写这个人从头到脚的样子（作者 Shot Planner 的描述指令，英文逗号分隔、以性别开头）；
    scene = True（动作迁移）时再写图里的场景（纯色 / 棚拍背景算没有场景）。返回 (人物, 场景或 None)；不可用 / 没写好时 (None, None)"""
    if not (img and DESCRIBE and DESCRIBE_OK()):
        return None, None
    import base64, io
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert('RGB'); k = min(1.0, 1024 / max(im.size))
    im = im.resize((round(im.width * k), round(im.height * k))); b = io.BytesIO(); im.save(b, 'JPEG', quality=90)
    url = 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
    system = 'You describe a reference picture for a video model. Answer in English only.'
    user = ('Describe the character in this reference picture as one comma-separated English attribute list, from head to toe, in this order: gender, apparent height, body type, physique, '
            'shoulders, waist and proportions; head and face shape, jawline, skin tone, eye color, distinctive facial features; hair color, style, length, texture and facial hair; '
            'upper-body clothing (garments, exact colors, fit, fabric, collars, sleeves, buttons, zippers, pockets, logos, patterns, layers); lower-body clothing (garments, colors, materials, fit, details); '
            'footwear (type, colors, materials, style); visible accessories (hats, glasses, earrings, necklaces, chains, watches, bracelets, rings, belts, bags, scarves, piercings); tattoos, scars, wrinkles, makeup. '
            'Only what is clearly visible; skip what cannot be seen. Never the background, camera, lighting or pose. Start with the gender ("Male, ..." or "Female, ..."), no article, no full stop.\n'
            'Write it on the first line, starting with "PERSON: ".')
    if scene:
        user += ('\nOn the second line, starting with "SCENE: ", describe the place shown in the picture in one short sentence (room or location, main objects, colors, light). '
                 'If the background is plain, white, grey, a studio backdrop or not a real place, write "SCENE: NONE".')
    try:
        out = (DESCRIBE(system, user, [url]) or '').strip()
    finally:
        if DESCRIBE_RELEASE:
            try:
                DESCRIBE_RELEASE()  # 写完让出显存，再跑视频
            except Exception:
                pass
    grab = lambda tag: next((re.sub(r'^\W*' + tag + r'\s*[:：]\s*', '', x, flags=re.I).strip().rstrip('.。') for x in out.splitlines() if re.match(r'^\W*' + tag + r'\s*[:：]', x.strip(), re.I)), '')
    who, env = grab('PERSON'), grab('SCENE')
    if who:
        who = _no_neg(who)
    if not who or len(who) > 900 or not re.match(r'^(fe)?male\b|^(woman|man|girl|boy)\b', who, re.I):  # 没按格式写：不用（模板里就只写 person）
        who = None
    if not env or env.upper().startswith('NONE') or len(env) > 400:
        env = None
    return who, env


def edit_desc(user):
    """给 Qwen 改图的衣服描述：写的是整段结构化提示词时，取 summary 那一段（不然改图模型看不懂）"""
    if not _structured(user):
        return user
    w = re.search(r'(?:现在穿着|now wearing )([^。\n]+)', user)
    if w and not re.search(r'[‹›]', w.group(1)):
        return w.group(1).strip()[:300]
    m = re.search(r'summary\s*:\s*(.+?)(?:\n\s*\n|\n\w+\s*:|$)', user, re.S)
    return re.sub(r'\[[^\]]*\]\s*', '', m.group(1)).strip()[:300] if m else ''


def pick_frame(src_path, dst, pre, j=None, work_in=None, tag=None):
    """改衣“参考生成”给 Qwen 改图的那一帧：认得出脸的帧里挑脸最大的（脸越大，Qwen 改完越像本人）；都认不出就用第一帧。
    2026-11-04：用户反映改出来的脸不像——以前取的是缩到输出尺寸（默认 480p）的帧、而且只要“脸不太小”的第一帧。
    现在给了 j / work_in / tag 时，从上传的原视频里按原分辨率取这一帧（长边最多 1280，裁成和输出一样的比例），返回 (帧号, 宽, 高)。"""
    import numpy as np, outfit2
    idx = 0
    try:
        (xy, (H, W)), = outfit2.landmarks((src_path, pre + '_pf.npz'))
        ok = ~np.isnan(xy[:, :, 0]).any(1)
        span = np.where(ok, np.nanmax(xy[:, :, 0], 1) - np.nanmin(xy[:, :, 0], 1), 0) / max(1, W)
        # 和 laowang A/B 测试一样尽量靠前（测试用的是第 0 帧）：从头往后第一帧认得出脸、脸不太小的；参考图和视频开头的姿势对得上，H3 不会照着中间某一帧去画
        good = np.nonzero(ok & (span >= 0.04))[0]
        idx = int(good[0]) if len(good) else (int(np.nonzero(ok)[0][0]) if ok.any() else 0)
    except Exception:
        idx = 0
    xp = ((j or {}).get('edit') or {}).get('xt') or {}
    if isinstance(xp.get('pick'), int):  # 夜测：手动指定 Qwen 改哪一帧（窗口内第几帧）
        idx = max(0, xp['pick'])
    pr = V._probe(src_path)
    w, h = pr.get('width') or 0, pr.get('height') or 0
    if j is not None and j.get('_vid') and w and h:  # 原视频原分辨率：和 prepare 一样的起点、比例和裁切，只是尺寸更大
        try:
            raw = os.path.join(work_in, f"studio_{tag}_raw_pf.{video_kind(j['_vid']) or 'mp4'}")
            with open(raw, 'wb') as f:
                f.write(j['_vid'])
            rp = _vprobe(raw)
            k = min(1280 / max(w, h), max(rp['width'] / w, rp['height'] / h))  # 不超过原视频本身的清晰度
            qw, qh = (max(256, int(x * max(1.0, k)) // 16 * 16) for x in (w, h))
            t = max(0.0, j['edit'].get('win', j['edit']['start'])) + idx / FPS  # 处理好的原视频从窗口起点开始
            subprocess.run([V.FFMPEG, '-v', 'error', '-y', '-ss', f'{t:.3f}', '-i', raw, '-frames:v', '1',
                            '-vf', f'scale={qw}:{qh}:force_original_aspect_ratio=increase:flags=lanczos,crop={qw}:{qh},setsar=1', dst],
                           check=True, capture_output=True, creationflags=V.NO_WINDOW)
            os.remove(raw)
            return idx, qw, qh
        except Exception:
            pass
    subprocess.run([V.FFMPEG, '-v', 'error', '-y', '-i', src_path, '-vf', f'select=eq(n\\,{idx})', '-frames:v', '1', dst], check=True, capture_output=True, creationflags=V.NO_WINDOW)
    return idx, w, h



def _pos_swap(zh, en):
    zh = zh.replace('原来的{who}被 <Subject 1> 完全替换，画面里不再出现原来的人。', '原来{who}的位置上是 <Subject 1>。').replace(
        '脸始终清晰，与 <Picture 1> 一致。', '她的长相与 <Picture 1> 完全相同；身体和头部朝向在每一帧都与 <Video 1> 的同一帧相同。')
    en = en.replace('the original {who} is fully replaced by <Subject 1> and no longer appears in the frame.', "<Subject 1> takes the original {who}'s place.").replace(
        'The face stays sharp throughout and matches <Picture 1>.', 'Her looks match <Picture 1> exactly; in every frame her body and head point the same way as in the same frame of <Video 1>.')
    return zh, en


_OLD = {}


def use_pos(on=True):
    """切换正向写法（2026-11-09）：把下面这些模板换成 *_POS（旧的存在 _OLD 里，关掉时换回来）"""
    global POS
    names = ['REF_OUTFIT_TPL', 'EN_REF_OUTFIT_TPL', 'REF_SWAP_TPL', 'EN_REF_SWAP_TPL']
    g = globals()
    if not _OLD:
        _OLD.update({n: g[n] for n in names})
    if on:
        sz, se = _pos_swap(_OLD['REF_SWAP_TPL'], _OLD['EN_REF_SWAP_TPL'])
        g.update(REF_OUTFIT_TPL=REF_OUTFIT_TPL_POS, EN_REF_OUTFIT_TPL=EN_REF_OUTFIT_TPL_POS, REF_SWAP_TPL=sz, EN_REF_SWAP_TPL=se)
    else:
        g.update(_OLD)
    POS = bool(on)


# 2026-11-09：正向写法测试通过（docs/AB测试/正向提示词_1109/报告.md，5 个场景都不比 11-08 写法差，换衣两项明显更好），设为默认。
# 要回到 11-08 的写法：把下面这行改成 use_pos(False)
use_pos(True)



# ===== 2026-11-09 模板管理（用户）：改视频用的模板登记到 tplstore，按当前空间默认的那套取 =====
# 内置两套只读：正向写法（现在的默认，上面 use_pos(True) 之后的样子）和 11-08 写法（_OLD）。
# 改过的模板可能对不上程序里按原文找位置的几处（换衣认出“保留”、没放图时去掉 <Picture 1>），对不上时退回普通写法，不会出错。
import tplstore
_tl = tplstore._tl
_fmt = tplstore.fmt
_T = tplstore.T


def _pos():
    return bool(tplstore.flag('pos'))


_S = {'who': '要改的人（“人物”或填写的目标）', 'desc': '提示词框里写的描述', 'details': '新头像的脸部描述',
      'end': '结尾时间（MM:SS.mmm）', 'pinline': '“<Picture 1> 是目标视频里的一帧”那一行（钉帧时才有）', 'pinat': '“某一刻和 <Picture 1> 一样”那一句（钉帧时才有）',
      'pdetails': '人物图中的人（看图自动写，加上提示词框里写的）', 'setting': '场景那一句（人物图里有场景时用它，否则沿用原视频）', 'env': '人物图里的场景（看图自动写）'}
for _k, _g, _l, _z, _e, _sl in [('ve_outfit', '换衣', '视频 · 参考生成（默认）', 'REF_OUTFIT_TPL', 'EN_REF_OUTFIT_TPL', ('who', 'desc')),
                                ('ve_swap', '换人', '视频 · 审美优先', 'REF_SWAP_TPL', 'EN_REF_SWAP_TPL', ('who', 'desc')),
                                ('ve_swap11', '换人', '视频 · 新版（默认）', 'CS11_TPL', None, ('pdetails',)),
                                ('ve_motion', '动作迁移', '视频', 'MOTION_TPL', None, ('pdetails', 'setting')),
                                ('ve_motion_env', '动作迁移', '场景那一句', 'MOTION_SETTING_PIC', None, ('env',)),
                                ('ve_faceswap', '换头', '视频 · 换脸 LoRA（默认）', 'FS_TPL', None, ()),
                                ('ve_vg', '换衣', '视频 · Viggle 重拍', 'VG_TPL', None, ('who', 'desc', 'end', 'pinline', 'pinat'))]:
    _np = _k == 've_outfit'  # 换衣可以不放参考图（跳过 Qwen）：多一份“无参考图”的写法
    _ns = [(_z, 'zh', True)] + ([(_e, 'en', True)] if _e else []) + ([(_z + '_NP', 'zh', False), (_e + '_NP', 'en', False)] if _np else [])
    _b = {sid: {n: src.get(n, globals()[n]) for n in (_z, _e) if n} for sid, src in (('pos', globals()), ('v1108', _OLD))}
    for _sid in _b:
        if _np:
            _b[_sid].update({n + '_NP': _nopic(_b[_sid][n]) for n in (_z, _e)})
    tplstore.register('vedit', _k, _l, [x if _np else x[:2] for x in _ns], _b, {x: _S[x] for x in _sl}, _g)
