"""Read-only prompt previews and snapshots taken at the engine boundary.

This module never rewrites prompts, starts an engine, or reads media files.
"""
import copy
import json
import os
import re
import time
import uuid


def new(raw):
    return {'input': str(raw or ''), 'stages': [], 'notes': []}


def add(trace, label, text, negative=None):
    stage = {'label': label, 'text': str(text or '')}
    if negative is not None:
        stage['negative'] = str(negative or '')
    if stage not in trace['stages']:
        trace['stages'].append(stage)


def capture_image(job, request):
    trace = job.setdefault('prompt_trace', new(job.get('prompt', '')))
    label = '图片生成' if request.get('prompt') == job.get('prompt') else '局部细化'
    add(trace, label, request.get('prompt'), request.get('negative_prompt', ''))


def capture_workflow(job, workflow):
    trace = job.setdefault('prompt_trace', new(job.get('prompt', '')))
    negative_nodes = {str(n['inputs']['negative'][0]) for n in workflow.values()
                      if isinstance((n.get('inputs') or {}).get('negative'), list) and n['inputs']['negative']}
    for key, node in workflow.items():
        inputs = node.get('inputs') or {}
        cls = node.get('class_type', '')
        if isinstance(inputs.get('prompt'), str):
            add(trace, f'视频模型 · {cls}（节点 {key}）', inputs['prompt'])
        elif 'TextEncode' in cls and isinstance(inputs.get('text'), str):
            label = '负面提示词' if str(key) in negative_nodes else '提示词'
            add(trace, f'{label} · {cls}（节点 {key}）', inputs['text'])


def image_preview(body):
    trace = new(body.get('prompt_input', body.get('prompt')))
    ptxt = str(body.get('prompt') or '').strip()[:4000]
    q = body.get('q21') if isinstance(body.get('q21'), dict) else None
    if q and q.get('mode') == 'inpaint' and not q.get('pose'):  # Qwen 2.1 局部重画：和 q21.py 生成时一样，按原话画时前面加上“重画灰色区域”那句（2026-11-11 用户：完整提示词里要看得到）
        import q21
        if (q.get('enhance') or 'off') == 'off':
            if '灰色' not in ptxt:
                ptxt = q21.INPAINT_LEAD + ptxt
        else:
            trace['notes'].append('开了提示词增强：生成时先增强，实际发送的是增强后的指令（生成后可在图片详情里查看）；增强失败、按原话生成时，前面会加上“' + q21.INPAINT_LEAD.rstrip('：') + '”。')
    add(trace, '图片生成', ptxt, str(body.get('negative') or '').strip()[:2000])
    detail = body.get('detail') if isinstance(body.get('detail'), dict) else {}
    if any(detail.get(k) for k in ('face', 'hand')):
        add(trace, '局部细化（检测到区域后使用）', str(detail.get('prompt') or '').strip()[:1000] or trace['stages'][0]['text'],
            trace['stages'][0]['negative'])
    trace['notes'].append('只预览文字，不载入模型、不提交生成；素材按当前界面的选择另行发送。')
    if len(str(body.get('prompt') or '').strip()) > 4000:
        trace['notes'].append('图片接口当前最多接收 4000 个字符；输入原文完整保留在上方。')
    return trace


def video_preview(body):
    import tplstore
    with tplstore.track() as used:
        trace = _video_preview(body)
    trace['templates'] = list(used)  # 这次用到的模板（网页“模板”里定位到正在用的那份）
    return trace


def _video_preview(body):
    import videogen
    import videoedit
    trace = new(body.get('prompt_input', body.get('prompt')))
    user = str(body.get('prompt') or '').strip()[:4000]
    edit = body.get('edit') if isinstance(body.get('edit'), dict) else None
    if edit:
        # 2026-11-14 审查：和 videoedit.parse 用同样的规则推出做法（以前动作迁移当成换人、没有作者配方 / 换头做法 / Viggle）
        task = edit.get('task') if edit.get('task') in videoedit.TASKS else 'swap'
        method = 'ref'  # 改衣只剩参考生成（保真替换 / 参考编辑随 Wan 2.2 去掉了，2026-11-06）
        by = edit.get('swap_by') or 'v11'
        st = videoedit.status()
        hb = (edit.get('head_by') if edit.get('head_by') in (st.get('head_by') or []) else ((st.get('head_by') or ['fs'])[0])) if task == 'head' else None
        e = {**edit, 'task': task, 'method': method, 'target': str(edit.get('target') or '').strip()[:200],
             'tpl': edit.get('tpl') is not False, 'ref': bool(body.get('has_ref')), 'own': task == 'outfit' and edit.get('own') is True,
             'swap_by': by if task == 'swap' else None, 'plang': 'en' if edit.get('plang') == 'en' else 'zh',
             'recipe': 'cs11' if task == 'swap' and by == 'v11' else 'motion' if task == 'motion' else None,
             'head_by': hb, 'vg': bool(task == 'outfit' and edit.get('vg') is True and st.get('vg'))}
        if task == 'outfit' and not e['own']:
            import outfit2
            desc = videoedit.edit_desc(user) if method == 'ref' else user
            ep = (outfit2.edit_prompt(desc, e['target'], e['ref'])
                  if e['tpl'] or videoedit._structured(user) else user)
            add(trace, '参考图改图', ep)
        rec = videoedit.recognize(e, user)
        if rec:
            trace['stages'].insert(0, {'label': '识别结果', 'text': rec})
        add(trace, '视频生成', videoedit._prompt({'edit': e, 'prompt': user, 'seconds': body.get('seconds')}))
    else:  # 生视频（只有 H3）
        import h3extra
        x = body.get('h3x') if isinstance(body.get('h3x'), dict) else {}
        extra = {k: x.get(k) or [] for k in ('refs', 'rvids', 'raudios')}
        extra['rvid_audio'] = [v.get('audio') or 'none' for v in extra['rvids'] if isinstance(v, dict)]
        add(trace, '视频生成', h3extra._prompt_refs(user, extra))
    if len(str(body.get('prompt') or '').strip()) > 4000:
        trace['notes'].append('视频接口当前最多接收 4000 个字符；输入原文完整保留在上方。')
    return trace


def chat_preview(messages, raw=''):
    trace = new(raw)
    roles = {'system': '系统指令', 'user': '用户', 'assistant': '助手'}
    for i, msg in enumerate(messages):
        content = msg['content']
        if isinstance(content, list):
            texts = [p.get('text', '') for p in content if p.get('type') == 'text']
            images = sum(p.get('type') == 'image_url' for p in content)
            content = '\n'.join(texts) + (f'\n[另附 {images} 张图片]' if images else '')
        # Repeated messages are significant; preserve their order and duplicates.
        trace['stages'].append({'label': f'{i + 1}. {roles.get(msg["role"], msg["role"])}', 'text': content})
    return trace


def snapshot(job):
    return copy.deepcopy(job.get('prompt_trace'))


def save(directory, trace):
    """Chat records store a small ID, keeping complete contexts out of browser storage."""
    os.makedirs(directory, exist_ok=True)
    key = uuid.uuid4().hex
    with open(os.path.join(directory, key + '.json'), 'w', encoding='utf-8') as f:
        json.dump(trace, f, ensure_ascii=False)
    cutoff = time.time() - 30 * 86400
    for name in os.listdir(directory):
        if re.fullmatch(r'[a-f0-9]{32}\.json', name):
            path = os.path.join(directory, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass
    return key


def load(directory, key):
    if not re.fullmatch(r'[a-f0-9]{32}', key):
        return None
    try:
        with open(os.path.join(directory, key + '.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
