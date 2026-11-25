"""生图后端的实际测试（对 devtest/run.py 起的测试 Studio）：文生图、图生图、局部重画、高清修复、采样参数、放大、按批删除、参数检查。
用法：先起 devtest/run.py，再 python -I devtest/test_imagegen.py
注意：公开版去掉了 sd.cpp 的文生图模型，默认模型是 ComfyUI 上的 Z-Image Turbo 官方原版（只做文生图），图生图 / 局部重画那几项会失败"""
import base64, json, os, struct, sys, time, urllib.error, urllib.request, zlib

B = 'http://127.0.0.1:7865'
HERE = os.path.dirname(os.path.abspath(__file__))
OK, BAD = [], []


def req(path, body=None, method=None, timeout=120):
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, {'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, json.loads(x.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def check(name, cond, info=''):
    (OK if cond else BAD).append(name)
    print(('  通过  ' if cond else '  失败  ') + name + (f'  ({info})' if info else ''), flush=True)


def wait(jid, limit=400):
    t0 = time.time()
    while time.time() - t0 < limit:
        s, j = req('/api/img/jobs/' + jid)
        if j.get('state') in ('done', 'error', 'cancelled'):
            return j
        time.sleep(1)
    return {'state': 'timeout'}


def png_mask(w, h, box):
    """黑底、box 区域白色的灰度 PNG（白色 = 要重画）"""
    x0, y0, x1, y1 = box
    rows = b''.join(b'\x00' + bytes(255 if (x0 <= x < x1 and y0 <= y < y1) else 0 for x in range(w)) for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


s, st = req('/api/img/status')
print('模型：', [(m['key'], m['name'], m['missing']) for m in st['models']], '默认：', st.get('default_model'))
check('默认模型是 Z-Image Turbo 官方原版', st.get('default_model') == 'zit-official')
check('原版模型已经不在列表里', all(m['key'] != 'zit' for m in st['models']))
base = {'model': 'zit-official', 'prompt': '一只橘猫坐在木桌上，窗边自然光，写实摄影', 'width': 768, 'height': 768, 'steps': 8, 'seed': 12345}

# 1 文生图（带全部采样参数）
s, j = req('/api/img/jobs', {**base, 'count': 2, 'sampler': 'res_multistep', 'scheduler': 'simple', 'cfg': 1.0, 'format': 'webp', 'quality': 90})
check('文生图提交', s == 200, j.get('error'))
j = wait(j['id'])
check('文生图 2 张完成', j.get('state') == 'done' and len(j.get('images', [])) == 2, j.get('error') or j.get('state'))
s, gal = req('/api/img/gallery')
batch = [x for x in gal if x.get('job') == j.get('id')]
check('两张图记着同一个批次、格式是 webp', len(batch) == 2 and all(x['file'].endswith('.webp') for x in batch))
check('图库记下了采样参数', batch and batch[0].get('sampler') == 'res_multistep' and batch[0].get('scheduler') == 'simple')
first = batch[0] if batch else None

# 2 能力列表（引擎开着时是引擎报的）
s, st = req('/api/img/status')
caps = st['caps']
check('引擎在时采样器列表来自引擎', caps.get('live') and 'euler' in caps['samplers'], f"{len(caps['samplers'])} 个采样器, upscale={caps.get('upscale')}")

# 3 图生图：用图库里的图
if first:
    s, j2 = req('/api/img/jobs', {**base, 'mode': 'img', 'init': {'gallery': first['id']}, 'strength': 0.5, 'prompt': '一只黑猫坐在木桌上，窗边自然光'})
    check('图生图提交', s == 200, j2.get('error'))
    j2 = wait(j2['id'])
    check('图生图完成', j2.get('state') == 'done', j2.get('error'))
# 4 图生图：上传的图（data URL）
src = open(os.path.join(HERE, '..', '..', 'fixtures', 'images', '原图 1024.png'), 'rb').read()
s, j3 = req('/api/img/jobs', {**base, 'width': 1024, 'height': 1024, 'mode': 'img', 'init': {'data': 'data:image/png;base64,' + base64.b64encode(src).decode()}, 'strength': 0.7})
check('上传原图的图生图提交', s == 200, j3.get('error'))
j3 = wait(j3['id'])
check('上传原图的图生图完成', j3.get('state') == 'done', j3.get('error'))
check('任务列表里不带原图（不会把大图发给网页）', '_init' not in json.dumps(req('/api/img/jobs')[1]))
# 5 局部重画
mask = png_mask(1024, 1024, (300, 300, 724, 724))
s, j4 = req('/api/img/jobs', {**base, 'width': 1024, 'height': 1024, 'mode': 'inpaint', 'prompt': '一朵红色的花', 'strength': 0.9,
                               'init': {'data': base64.b64encode(src).decode()}, 'mask': {'data': base64.b64encode(mask).decode()}})
check('局部重画提交', s == 200, j4.get('error'))
j4 = wait(j4['id'])
check('局部重画完成', j4.get('state') == 'done', j4.get('error'))
# 6 高清修复 + 加速缓存 + VAE 分块
s, j5 = req('/api/img/jobs', {**base, 'width': 512, 'height': 512, 'hires': {'enabled': True, 'upscaler': 'Latent', 'scale': 1.5, 'steps': 6, 'denoise': 0.45},
                               'vae_tiling': True, 'cache_mode': 'easycache'})
check('高清修复提交', s == 200, j5.get('error'))
j5 = wait(j5['id'])
g5 = next((x for x in req('/api/img/gallery')[1] if x.get('job') == j5.get('id')), {})
check('高清修复完成、图变大了', j5.get('state') == 'done' and g5.get('width') == 768, f"{j5.get('error') or ''} {g5.get('width')}x{g5.get('height')}")
# 7 放大
if first:
    s, j6 = req('/api/img/jobs', {'kind': 'upscale', 'id': first['id']})
    check('放大提交', s == 200, j6.get('error'))
    j6 = wait(j6['id'])
    g6 = next((x for x in req('/api/img/gallery')[1] if x.get('job') == j6.get('id')), {})
    check('放大完成（×4）', j6.get('state') == 'done' and g6.get('width') == first['width'] * 4, f"{j6.get('error') or ''} {g6.get('width')}")
# 8 参数检查：乱填的值不会出事
s, j7 = req('/api/img/jobs', {**base, 'steps': 9999, 'cfg': -5, 'width': 99999, 'sampler': 'rm -rf', 'cache_option': 'a;b', 'count': 50})
check('非法的加速缓存参数被拒绝', s == 400, j7.get('error'))
s, j8 = req('/api/img/jobs', {**base, 'steps': 9999, 'cfg': -5, 'width': 99999, 'sampler': 'rm -rf', 'count': 50, 'format': 'exe'})
check('超范围的数值被夹到合理范围', s == 200 and j8.get('steps') == 60 and j8.get('cfg') == 0.0 and j8.get('width') == 2048 and j8.get('sampler') == '' and j8.get('count') == 4 and j8.get('format') == 'png', str({k: j8.get(k) for k in ('steps', 'cfg', 'width', 'sampler', 'count', 'format')}))
req(f"/api/img/jobs/{j8.get('id')}/cancel", {})
s, j9 = req('/api/img/jobs', {**base, 'mode': 'img', 'init': {'data': base64.b64encode(b'not an image at all').decode()}})
check('不是图片的“原图”被拒绝', s == 400, j9.get('error'))
s, j10 = req('/api/img/jobs', {**base, 'mode': 'img', 'init': {'gallery': 'nope'}})
check('图库里没有的原图被拒绝', s == 400, j10.get('error'))
# 9 按批删除
if batch:
    s, _ = req('/api/img/gallery/delete', {'ids': [x['id'] for x in batch]})
    left = [x for x in req('/api/img/gallery')[1] if x.get('job') == j.get('id')]
    check('按批删除', s == 200 and not left)
print(f'\n通过 {len(OK)} 项，失败 {len(BAD)} 项' + (('：' + '、'.join(BAD)) if BAD else ''))
sys.exit(1 if BAD else 0)
