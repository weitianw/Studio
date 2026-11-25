"""生视频 · H3 的更多条件（都是 H3 自带的，ComfyUI 原生节点）：
- 关键帧：任意时间点放一张图（MiniMaxH3AddGuide 的 image + frame_idx），可以放好几张
- 开头片段：拿一段视频的开头 / 结尾几帧接在新视频最前面（AddGuide 的多帧 clip，17k+5 帧：22 帧 ≈ 0.9 秒、39 帧 ≈ 1.6 秒），它的声音也一起接上
- 指定声音：给一段声音，从第几秒开始对上（AddGuide 的 audio），比如让人照着这段话说
- 参考模式：参考图（人物 / 服装 / 场景 / 画风）、参考视频（动作和镜头）、参考音频（音色）——换成 MiniMaxH3ReferenceToVideo，
  首帧 / 尾帧改用 AddGuide 放在第 0 帧 / 最后一帧。要能读参考的底模（官方 Ref2VA）
网页传来的东西由 server.py 解码成字节，submit 时放进 j['_x']；_run 里拼好普通的 H3 工作流后调 apply() 加上这些。
- 参考视频的原声（2026-11-04 补齐 laowang 节点有的）：'ref' = 原声也当参考（官方节点的 ref_video_audios，它占一个 <Audio N>，排在单独的参考音频前面）；
  'lock' = 用这段原声驱动：成品的声音锁定成这段原声（AddGuide 从第 0 帧放上去，对应他节点的 lock_source），同时也当参考。
  他节点的 remix_source（原声部分重画）原生节点做不到，要等做法 ② 接进来
- 引导视频（2026-11-04：“自由修改”并进生视频）：整段原视频从第 0 帧起逐帧当引导（AddGuide 的多帧 clip，和改视频里自由修改 / 换头的接法一样），
  配合特效编辑（VFX Edit）这类 LoRA 改视频；原视频有声音时声音也一起锁上
"""
import os

import videogen as V

MAX = {'keys': 6, 'refs': 9, 'rvids': 3, 'raudios': 3}  # 参考图最多 9 张（官方 / laowang 节点的上限）
RV_AUDIO = ('none', 'ref', 'lock')
CLIP_N = (22, 39)  # 开头片段的帧数（17k+5）
AUDIO_EXT = {b'RIFF': 'wav', b'ID3': 'mp3', b'\xff\xfb': 'mp3', b'\xff\xf3': 'mp3', b'\xff\xf2': 'mp3', b'fLaC': 'flac', b'OggS': 'ogg'}


def audio_ext(data):
    if data[4:8] == b'ftyp':
        return 'm4a'
    return next((e for h, e in AUDIO_EXT.items() if data.startswith(h)), None)


def parse(x):
    """server.py 解码好的 {'keys': [(秒, 图)], 'clip': {'vid', 'part', 'n'}, 'audio': {'data', 'start'}, 'refs': [图], 'rvids': [视频], 'raudios': [音频]} → 检查过的"""
    if not isinstance(x, dict):
        return None
    out = {}
    keys = [(max(0.0, min(15.0, float(t))), b) for t, b in (x.get('keys') or [])[:MAX['keys']] if b]
    if keys:
        out['keys'] = sorted(keys, key=lambda k: k[0])
    c = x.get('clip')
    if c and c.get('vid'):
        out['clip'] = {'vid': c['vid'], 'part': 'head' if c.get('part') == 'head' else 'tail', 'n': c.get('n') if c.get('n') in CLIP_N else CLIP_N[0]}
    g = x.get('guide')
    if g and g.get('vid'):
        out['guide'] = {'vid': g['vid'], 'audio': g.get('audio') is not False}
    a = x.get('audio')
    if a and a.get('data'):
        if not audio_ext(a['data']):
            raise ValueError('声音仅支持 WAV / MP3 / M4A / FLAC / OGG')
        out['audio'] = {'data': a['data'], 'start': max(0.0, min(15.0, float(a.get('start') or 0)))}
    for k in ('refs', 'rvids'):
        L = [b for b in (x.get(k) or [])[:MAX[k]] if b]
        if L:
            out[k] = L
    if out.get('rvids'):  # 每段参考视频的原声怎么用：none / ref / lock（只能锁一段，而且和“指定声音”二选一）
        fl = [(f if f in RV_AUDIO else 'none') for f in (list(x.get('rvid_audio') or []) + ['none'] * 3)[:len(out['rvids'])]]
        if fl.count('lock') > 1:
            raise ValueError('仅可使用一段参考视频的原声进行驱动')
        if 'lock' in fl and out.get('audio'):
            raise ValueError('“指定声音”和“参考视频原声驱动”只能二选一')
        if any(f != 'none' for f in fl):
            out['rvid_audio'] = fl
            if 'lock' in fl:
                out['lock'] = fl.index('lock')
    ra = [b for b in (x.get('raudios') or [])[:MAX['raudios']] if b]
    for b in ra:
        if not audio_ext(b):
            raise ValueError('参考音频仅支持 WAV / MP3 / M4A / FLAC / OGG')
    if ra:
        out['raudios'] = ra
    return out or None


def summary(x):
    """记进视频库的（不含文件本身）"""
    if not x:
        return None
    return {k: v for k, v in {'keys': [round(t, 2) for t, _ in x.get('keys', [])], 'clip': x['clip']['part'] + str(x['clip']['n']) if x.get('clip') else None,
                              'audio': x['audio']['start'] if x.get('audio') else None, 'refs': len(x.get('refs', [])),
                              'rvids': len(x.get('rvids', [])), 'raudios': len(x.get('raudios', [])), 'rvid_audio': x.get('rvid_audio'),
                              'guide': bool(x.get('guide'))}.items() if v not in (None, 0, [], False)}


def ref_mode(x):  # 引导视频也走参考模式的节点（改视频的自由修改就是这样接的，VFX Edit LoRA 是 Ref2VA 版）
    return bool(x and (x.get('refs') or x.get('rvids') or x.get('raudios') or x.get('guide')))


def aspect_bytes(x):
    """没有首帧时用来定画面比例的图：第一张关键帧，或者第一张参考图"""
    if not x:
        return None
    return (x.get('keys') or [(0, None)])[0][1] or (x.get('refs') or [None])[0]


def clip_dims(j, work_in, tag):
    """开头片段的原始宽高（没有首帧时按它定比例）"""
    x = j.get('_x') or {}
    if not x.get('clip') and not x.get('guide'):
        return None
    raw = _raw_clip(j, work_in, tag) if x.get('clip') else _raw_guide(j, work_in, tag)
    pr = V._probe(raw)
    return (pr.get('width'), pr.get('height')) if pr.get('width') else None


def _raw_guide(j, work_in, tag):
    raw = os.path.join(work_in, f'studio_{tag}_xguide_raw.mp4')
    if not os.path.exists(raw):
        with open(raw, 'wb') as f:
            f.write(j['_x']['guide']['vid'])
    return raw


def _raw_clip(j, work_in, tag):
    raw = os.path.join(work_in, f'studio_{tag}_xclip_raw.mp4')
    if not os.path.exists(raw):
        with open(raw, 'wb') as f:
            f.write(j['_x']['clip']['vid'])
    return raw


def _prompt_refs(p, x):
    """参考模式：提示词里没提到的参考补一句（官方格式里每个参考都要点名，<Picture N> / <Video N> / <Audio N> 各自编号）"""
    add = []
    n = len(x.get('refs', []))
    miss = [i for i in range(1, n + 1) if f'<picture {i}>' not in p.lower()]
    if miss:
        add.append(tplstore.fmt(tplstore.T('VG_REF_PIC'), refs=', '.join(f'<Picture {i}>' for i in miss)))
    nv = len(x.get('rvids', []))
    mv = [i for i in range(1, nv + 1) if f'<video {i}>' not in p.lower()]
    if mv:
        add.append(tplstore.fmt(tplstore.T('VG_REF_VID'), refs=', '.join(f'<Video {i}>' for i in mv)))
    # <Audio N>：先是带原声的参考视频的原声（按视频顺序），再是单独的参考音频（官方节点就是这样编号的）
    nt = sum(1 for f in (x.get('rvid_audio') or []) if f != 'none')
    na = len(x.get('raudios', []))
    if nt:
        mt = [i for i in range(1, nt + 1) if f'<audio {i}>' not in p.lower()]
        if mt:
            add.append(tplstore.fmt(tplstore.T('VG_REF_VSND'), refs=', '.join(f'<Audio {i}>' for i in mt)))
    ma = [i for i in range(nt + 1, nt + na + 1) if f'<audio {i}>' not in p.lower()]
    if ma:
        add.append(tplstore.fmt(tplstore.T('VG_REF_AUD'), refs=', '.join(f'<Audio {i}>' for i in ma)))
    return (p.rstrip() + ' ' + ' '.join(add)).strip() if add else p


def apply(j, wf, work_in, tag, w, h, frames, fps):
    """在拼好的 H3 首帧工作流（节点 1 首帧、40 尾帧、7 MiniMaxH3ImageToVideo、11 引导）上加更多条件"""
    x = j.get('_x') or {}
    if not x:
        return
    pos, guides = ['7', 0], []
    if ref_mode(x):  # 换成参考模式：首帧 / 尾帧改用 AddGuide
        old = wf['7']['inputs']
        ci = {'clip': old['clip'], 'vae': old['vae'], 'audio_vae': ['6', 0], 'prompt': _prompt_refs(old['prompt'], x),
              'width': old['width'], 'height': old['height'], 'length': old['length'], 'ref_image_size': 'match'}
        for i, b in enumerate(x.get('refs', [])):
            n = f'studio_{tag}_xr{i}.png'
            with open(os.path.join(work_in, n), 'wb') as f:
                f.write(b)
            wf[f'x1{i}'] = {'class_type': 'LoadImage', 'inputs': {'image': n}}
            ci[f'ref_images.ref_image_{i}'] = [f'x1{i}', 0]
        fl = x.get('rvid_audio') or []
        for i, b in enumerate(x.get('rvids', [])):
            n = f'studio_{tag}_xv{i}.mp4'
            src = os.path.join(work_in, f'studio_{tag}_xv{i}_raw')
            with open(src, 'wb') as f:
                f.write(b)
            snd = (fl[i] if i < len(fl) else 'none') != 'none' and V._probe(src, exact=False).get('audio')  # 要用原声、原视频也有声音
            # 参考视频：24 fps、最长 15 秒、短边不超过 512（参考的帧每一步都要算，太大很慢）
            V._ff(j, ['-i', src, '-t', '15', '-vf', "fps=24,scale='if(lt(iw,ih),min(512,iw),-2)':'if(lt(iw,ih),-2,min(512,ih))':flags=lanczos,setsar=1",
                      '-c:v', 'libx264', '-crf', '14', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                      *(['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if snd else ['-an']), os.path.join(work_in, n)], '处理参考视频')
            wf[f'x2{i}'] = {'class_type': 'LoadVideo', 'inputs': {'file': n}}
            wf[f'x3{i}'] = {'class_type': 'GetVideoComponents', 'inputs': {'video': [f'x2{i}', 0]}}
            ci[f'ref_videos.ref_video_{i}'] = [f'x3{i}', 0]
            if snd:
                ci[f'ref_video_audios.ref_video_audio_{i}'] = [f'x3{i}', 1]  # 和同编号的参考视频配对
                if x.get('lock') == i:  # 用这段原声驱动：成品的声音锁定成它（从第 0 帧起，超出视频长度的部分截掉）
                    guides.append({'audio': [f'x3{i}', 1], 'frame_idx': 0})
            elif x.get('lock') == i:
                raise RuntimeError(f'参考视频 {i + 1} 没有声音，无法用其原声驱动')
        for i, b in enumerate(x.get('raudios', [])):
            n = f'studio_{tag}_xa{i}.{audio_ext(b)}'
            with open(os.path.join(work_in, n), 'wb') as f:
                f.write(b)
            wf[f'x4{i}'] = {'class_type': 'LoadAudio', 'inputs': {'audio': n}}
            ci[f'ref_audios.ref_audio_{i}'] = [f'x4{i}', 0]
        if old.get('first_frame'):
            guides.append({'image': old['first_frame'], 'frame_idx': 0})
        if old.get('last_frame'):
            guides.append({'image': old['last_frame'], 'frame_idx': -1})
        wf['7'] = {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': ci}
    for i, (t, b) in enumerate(x.get('keys', [])):  # 关键帧
        n = f'studio_{tag}_xk{i}.png'
        with open(os.path.join(work_in, n), 'wb') as f:
            f.write(b)
        wf[f'x5{i}'] = {'class_type': 'LoadImage', 'inputs': {'image': n}}
        guides.append({'image': [f'x5{i}', 0], 'frame_idx': max(0, min(frames - 1, round(t * fps)))})
    if x.get('clip'):  # 开头片段：处理成目标尺寸、24 fps、正好 n 帧，接在第 0 帧
        c, raw = x['clip'], _raw_clip(j, work_in, tag)
        pr = V._probe(raw)
        dur = pr.get('duration') or 0
        if dur * fps < c['n'] - 1:
            raise RuntimeError(f"开头片段过短：至少需要 {c['n'] / fps:.1f} 秒")
        n, vf = f'studio_{tag}_xclip.mp4', f'fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1'
        enc = ['-c:v', 'libx264', '-crf', '12', '-preset', 'fast', '-pix_fmt', 'yuv420p', *(['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if pr.get('audio') else ['-an'])]
        if c['part'] == 'head':
            V._ff(j, ['-i', raw, '-vf', vf, '-frames:v', str(c['n']), *enc, os.path.join(work_in, n)], '处理开头片段')
        else:  # 取最后 n 帧要正好是最后那 n 帧（续接时合成按这 n 帧交叉淡化）：先转出结尾一小段，数清帧数，再从后往前取
            tmp = os.path.join(work_in, f'studio_{tag}_xclip_t.mp4')
            V._ff(j, ['-ss', f'{max(0.0, dur - (c["n"] + 12) / fps):.3f}', '-i', raw, '-vf', vf, *enc, tmp], '处理开头片段')
            got = V._probe(tmp).get('frames') or 0
            if got < c['n']:
                raise RuntimeError(f"开头片段过短：至少需要 {c['n'] / fps:.1f} 秒")
            k = got - c['n']
            V._ff(j, ['-i', tmp, '-vf', f"select='gte(n\\,{k})',setpts=PTS-STARTPTS", *(['-af', f'atrim=start={k / fps:.5f},asetpts=PTS-STARTPTS'] if pr.get('audio') else []),
                      '-frames:v', str(c['n']), *enc, os.path.join(work_in, n)], '处理开头片段')
        wf['x60'] = {'class_type': 'LoadVideo', 'inputs': {'file': n}}
        wf['x61'] = {'class_type': 'GetVideoComponents', 'inputs': {'video': ['x60', 0]}}
        g = {'image': ['x61', 0], 'frame_idx': 0}
        if pr.get('audio') and j.get('audio', True) and V._probe(os.path.join(work_in, n), exact=False).get('audio'):
            g['audio'] = ['x61', 1]  # 开头片段的声音也接上：说话 / 音乐不会在接缝处断掉
        guides.insert(0, g)
    if x.get('guide'):  # 引导视频：整段从第 0 帧起逐帧引导（处理成目标尺寸、24 fps，最多和新视频一样长；AddGuide 自己会截到 17k+5 帧）
        raw = _raw_guide(j, work_in, tag)
        pr = V._probe(raw)
        n = f'studio_{tag}_xguide.mp4'
        keep = x['guide']['audio'] and pr.get('audio') and j.get('audio', True)
        V._ff(j, ['-i', raw, '-vf', f'fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1', '-frames:v', str(frames),
                  '-c:v', 'libx264', '-crf', '12', '-preset', 'fast', '-pix_fmt', 'yuv420p', *(['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if keep else ['-an']),
                  os.path.join(work_in, n)], '处理引导视频')
        if (V._probe(os.path.join(work_in, n)).get('frames') or 0) < 5:
            raise RuntimeError('引导视频过短')
        wf['x90'] = {'class_type': 'LoadVideo', 'inputs': {'file': n}}
        wf['x91'] = {'class_type': 'GetVideoComponents', 'inputs': {'video': ['x90', 0]}}
        g = {'image': ['x91', 0], 'frame_idx': 0}
        if keep and V._probe(os.path.join(work_in, n), exact=False).get('audio'):
            g['audio'] = ['x91', 1]  # 原视频的声音也锁上（和改视频里“保留原声”一样）
        guides.insert(0, g)
    if x.get('audio'):  # 指定声音：从第几秒开始对上
        a = x['audio']
        n = f'studio_{tag}_xaud.{audio_ext(a["data"])}'
        with open(os.path.join(work_in, n), 'wb') as f:
            f.write(a['data'])
        wf['x70'] = {'class_type': 'LoadAudio', 'inputs': {'audio': n}}
        guides.append({'audio': ['x70', 0], 'frame_idx': max(0, min(frames - 1, round(a['start'] * fps)))})
    for i, g in enumerate(guides):
        nid = f'x8{i}'
        inp = {'positive': pos, 'latent': ['7', 1], 'frame_idx': g['frame_idx']}
        if g.get('image'):
            inp.update(vae=['5', 0], image=g['image'])
        if g.get('audio'):
            inp.update(audio_vae=['6', 0], audio=g['audio'])
        wf[nid] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': inp}
        pos = [nid, 0]
    wf['11']['inputs']['conditioning'] = pos


# 2026-11-09 模板套：上面补的四句登记到 tplstore（用户可以自己改）
import tplstore
_REFS = '用到的标签（比如 <Picture 1>, <Picture 2>）'
for _k, _l, _n, _t in [('vg_pic', '参考图', 'VG_REF_PIC', 'The appearance of the people, outfits, objects and scene follows {refs}.'),
                       ('vg_vid', '参考视频', 'VG_REF_VID', 'The motion and camera movement follow {refs}.'),
                       ('vg_vsnd', '参考视频原声', 'VG_REF_VSND', 'The sound of the reference video follows {refs}.'),
                       ('vg_aud', '参考音频', 'VG_REF_AUD', 'The voice and sound follow {refs}.')]:
    tplstore.register('vgen', _k, _l, [(_n, 'en')], {'pos': {_n: _t}}, {'refs': _REFS}, '参考素材补充句')
