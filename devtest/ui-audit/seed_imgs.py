"""测试 Studio（devtest/states/gpu，run.py --profile gpu / chk）的普通空间图库里放几张假图：竖图 / 横图 / 方图、长提示词、LoRA，给全面检查用（只动测试数据）"""
import os, json, time, random
from PIL import Image, ImageDraw
D = os.path.join(os.environ.get('STUDIO_TEST_STATE') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'states', 'gpu'), 'outputs', 'images')
os.makedirs(D, exist_ok=True)
P = os.path.join(D, 'index.json')
old = json.load(open(P, encoding='utf-8')) if os.path.exists(P) else []
old = [x for x in old if not x.get('id', '').startswith('seed')]
now = time.time(); recs = []
sizes = [(832, 1216), (1216, 832), (1024, 1024), (720, 1280), (1280, 720), (896, 1152), (1152, 896), (768, 1344), (1344, 768), (1024, 1024)]
prompts = ['一位穿白色连衣裙的女孩站在海边，夕阳，电影感', 'A cozy cabin in snowy mountains at night, warm window light, ultra detailed, 8k, cinematic composition, volumetric fog, ' * 3,
           '赛博朋克城市街道，霓虹灯，雨夜', '', '咖啡馆里看书的男生，柔和自然光', '超长提示词测试' * 40, '猫', '山水画风格的城市', 'portrait of an old man', '室内人像，窗边']
random.seed(7)
for i, (w, h) in enumerate(sizes):
    im = Image.new('RGB', (w, h)); dr = ImageDraw.Draw(im)
    c1, c2 = [random.randint(30, 220) for _ in range(3)], [random.randint(30, 220) for _ in range(3)]
    for y in range(h):
        t = y / h; dr.line([(0, y), (w, y)], fill=tuple(int(c1[k] * (1 - t) + c2[k] * t) for k in range(3)))
    dr.ellipse([w * .3, h * .2, w * .7, h * .2 + w * .4], fill=(240, 220, 200)); dr.rectangle([w * .25, h * .55, w * .75, h * .95], fill=(60, 80, 140))
    dr.text((20, 20), f'seed {i} {w}x{h}', fill=(255, 255, 255))
    name = f'seed-{i:02d}.png'; im.save(os.path.join(D, name))
    recs.append({'id': f'seed{i:02d}', 'file': name, 'prompt': prompts[i], 'model': 'q21' if i % 3 else 'zit', 'model_name': 'Qwen-Image 2.1' if i % 3 else 'Z-Image Turbo', 'job': f'seedjob{i}',
                 'created': now - i * 3600 * (5 if i > 6 else 1), 'size': os.path.getsize(os.path.join(D, name)), 'seed': 1000 + i, 'width': w, 'height': h, 'seconds': 12.5 + i, 'steps': 8,
                 'mode': 'edit' if i in (2, 5) else 'gen', 'loras': [{'name': 'detail_tweaker.safetensors', 'weight': 0.8}] if i % 2 else []})
json.dump(recs + old, open(P, 'w', encoding='utf-8'), ensure_ascii=False)
print(len(recs), 'seeded ->', D)
