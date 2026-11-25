"""Fisher Pose（3D 真人人偶摆姿势，ComfyUI-Fisher-Pose 插件的编辑器）嵌进生图页：编辑器是插件里的一个独立网页
（web/editor/freepose.html?embedded=1），在 iframe 里打开，通过 postMessage 和生图页来回传姿势。它要的几个接口
原本由 ComfyUI 提供，这里由 Studio 自己提供（不用先开 ComfyUI）：
  /extensions/ComfyUI-Fisher-Pose/…        编辑器的网页、脚本、人偶数据（插件 web 文件夹里的文件，只读）
  /fisher_pose/env、/fisher_pose/body_pack  环境检查、MakeHuman 人偶数据
  /fisher_pose/builtin_poses[/名字]         内置的 209 张 OpenPose 骨架图（插件的 FISHER小彩蛋 文件夹）
  /fisher_pose/openpose_library[/clear]、/upload/image、/view   “我的图库”：自己上传的骨架图
  /fisher_pose/saved_poses[/名字[/delete]]  “我的姿势”：摆好的姿势（JSON）
“我的图库”“我的姿势”按空间分开存（私密空间的存在私密空间里）。
出图不在这里：生图页拿到人偶图后，当图 1 交给 Qwen 2.1（加 VNCCS PoseStudio LoRA），见 q21.py。"""
import json, os, re, time
from email.parser import BytesParser
from email.policy import default as email_default

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'custom_nodes', 'ComfyUI-Fisher-Pose')
WEB = os.path.join(PLUGIN, 'web')
BUILTIN = os.path.join(PLUGIN, 'FISHER小彩蛋')
DATA_ROOT = None  # 由 server.py 设：DATA_ROOT(sp) → 这个空间的数据文件夹（普通空间 outputs，私密空间 .data），下面再建 fisher 子文件夹
LIB_SUB = 'fisher_openpose'
IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp')
BAD = set('\\/:*?"<>|')


def available():
    return os.path.isfile(os.path.join(WEB, 'editor', 'freepose.html')) and os.path.isfile(os.path.join(WEB, 'vnccs', 'assets', 'pose_studio_makehuman.v2.bin'))


def _dir(sp, *sub):
    d = os.path.join(DATA_ROOT(sp), 'fisher', *sub)
    os.makedirs(d, exist_ok=True)
    return d


def _inside(base, path):
    base, path = os.path.realpath(base), os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def _builtin():
    if not os.path.isdir(BUILTIN):
        return []
    names = [n for n in os.listdir(BUILTIN) if n.lower().endswith(IMG_EXT)]
    return sorted(names, key=lambda n: (int(os.path.splitext(n)[0]) if os.path.splitext(n)[0].isdigit() else float('inf'), n))


def _safe_name(name):
    if not isinstance(name, str):
        return None
    name = ' '.join(name.split())
    if not name or len(name) > 60 or name.strip('.') == '' or name.startswith('.') or any(c in BAD or ord(c) < 32 for c in name):
        return None
    return name


def handle(h, method, p, q, sp):
    """h：server 的请求处理对象（send_json / send_file / body）。处理了返回 True"""
    if p[:2] == ['extensions', 'ComfyUI-Fisher-Pose'] and method == 'GET':
        fp = os.path.join(WEB, *p[2:])
        if not _inside(WEB, fp) or not os.path.isfile(fp):
            h.send_json({'error': 'not found'}, 404)
        else:
            h.send_file(fp, cache='no-cache')
        return True
    if p == ['view'] and method == 'GET':  # “我的图库”的骨架图
        if q.get('subfolder') != LIB_SUB:
            h.send_json({'error': 'not found'}, 404); return True
        d = _dir(sp, LIB_SUB); fp = os.path.join(d, q.get('filename', ''))
        if not _inside(d, fp) or not os.path.isfile(fp):
            h.send_json({'error': 'not found'}, 404)
        else:
            h.send_file(fp)
        return True
    if p == ['upload', 'image'] and method == 'POST':  # 只收“我的图库”的骨架图（识别骨骼要 DWPose，这里没有）
        ctype = h.headers.get('Content-Type', '')
        msg = BytesParser(policy=email_default).parsebytes(b'Content-Type: ' + ctype.encode() + b'\r\n\r\n' + h.body())
        fields, img, fname = {}, None, ''
        for part in msg.iter_parts():
            name = part.get_param('name', header='content-disposition')
            if name == 'image':
                img, fname = part.get_payload(decode=True), part.get_filename() or 'pose.png'
            elif name:
                fields[name] = part.get_content().strip() if part.get_content_maintype() == 'text' else ''
        if fields.get('subfolder') != LIB_SUB or not img:
            h.send_json({'error': '这里只能上传“我的图库”的骨架图（识别照片骨骼需要 ComfyUI 里的 DWPose，应用中没有）'}, 400); return True
        base = re.sub(r'[^\w\-.()一-鿿]', '_', os.path.basename(fname))[:80] or 'pose.png'
        if not base.lower().endswith(IMG_EXT):
            base += '.png'
        d = _dir(sp, LIB_SUB)
        with open(os.path.join(d, base), 'wb') as f:
            f.write(img)
        h.send_json({'name': base, 'subfolder': LIB_SUB, 'type': 'input'}); return True
    if p[:1] != ['fisher_pose']:
        return False
    if p == ['fisher_pose', 'env']:
        h.send_json({'version': 'studio', 'minVersion': '0.36.0', 'qwen21': True, 'splat': False, 'updateHint': '', 'freePoseBindingVersion': 2})
    elif p == ['fisher_pose', 'body_pack']:
        fp = os.path.join(WEB, 'vnccs', 'assets', 'pose_studio_makehuman.v2.bin')
        if not os.path.isfile(fp):
            h.send_json({'error': '人体数据文件缺失，请重新安装完整的 Fisher Pose 插件'}, 404)
        else:
            h.send_file(fp, cache='no-cache')
    elif p == ['fisher_pose', 'builtin_poses']:
        h.send_json({'files': _builtin()})
    elif p[:2] == ['fisher_pose', 'builtin_poses'] and len(p) == 3:
        if p[2] not in _builtin():
            h.send_json({'error': 'not found'}, 404)
        else:
            h.send_file(os.path.join(BUILTIN, p[2]))
    elif p == ['fisher_pose', 'openpose_library']:
        d = _dir(sp, LIB_SUB)
        h.send_json({'subfolder': LIB_SUB, 'files': sorted(n for n in os.listdir(d) if n.lower().endswith(IMG_EXT))})
    elif p == ['fisher_pose', 'openpose_library', 'clear'] and method == 'POST':
        d, n = _dir(sp, LIB_SUB), 0
        for f in os.listdir(d):
            if f.lower().endswith(IMG_EXT):
                os.remove(os.path.join(d, f)); n += 1
        h.send_json({'removed': n})
    elif p[:2] == ['fisher_pose', 'saved_poses']:
        d = _dir(sp, 'poses')
        if len(p) == 2 and method == 'GET':
            out = []
            for f in os.listdir(d):
                if f.endswith('.json') and _safe_name(f[:-5]) == f[:-5]:
                    try:
                        with open(os.path.join(d, f), encoding='utf-8') as fh:
                            r = json.load(fh)
                        out.append({'name': f[:-5], 'savedAt': r.get('savedAt', 0), 'thumbnail': r.get('thumbnail', '')})
                    except (OSError, ValueError):
                        pass
            h.send_json({'poses': sorted(out, key=lambda x: x['savedAt'], reverse=True)})
        elif len(p) == 2 and method == 'POST':
            try:
                b = json.loads(h.body() or b'{}')
            except ValueError:
                h.send_json({'error': '请求格式错误'}, 400); return True
            name, rec = _safe_name(b.get('name')), b.get('record')
            if not name:
                h.send_json({'error': '名字不能为空、不能超过 60 个字，也不能包含 \\ / : * ? " < > |'}, 400); return True
            if not isinstance(rec, dict) or not isinstance(rec.get('doc'), dict):
                h.send_json({'error': '姿势数据不完整'}, 400); return True
            fp = os.path.join(d, name + '.json')
            if os.path.exists(fp) and not b.get('overwrite'):
                h.send_json({'error': '已有同名姿势'}, 409); return True
            text = json.dumps({**rec, 'kind': 'fisher-saved-pose', 'name': name, 'savedAt': int(time.time() * 1000)}, ensure_ascii=False)
            if len(text.encode('utf-8')) > 8 << 20:
                h.send_json({'error': '姿势数据过大'}, 400); return True
            with open(fp + '.tmp', 'w', encoding='utf-8') as fh:
                fh.write(text)
            os.replace(fp + '.tmp', fp)
            h.send_json({'name': name})
        elif len(p) == 3 and method == 'GET':
            name = _safe_name(p[2]); fp = name and os.path.join(d, name + '.json')
            if not fp or not os.path.isfile(fp):
                h.send_json({'error': 'not found'}, 404)
            else:
                with open(fp, encoding='utf-8') as fh:
                    h.send_json(json.load(fh))
        elif len(p) == 4 and p[3] == 'delete' and method == 'POST':
            name = _safe_name(p[2]); fp = name and os.path.join(d, name + '.json')
            ok = bool(fp and os.path.isfile(fp))
            if ok:
                os.remove(fp)
            h.send_json({'removed': ok})
        else:
            h.send_json({'error': 'not found'}, 404)
    else:
        h.send_json({'error': 'not found'}, 404)
    return True
