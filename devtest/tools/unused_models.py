"""列出“可能没在用”的大模型文件（只读，不删）：models/ 和 ComfyUI/models/ 里大于 2 GB、文件名在 Studio 代码 / 工作流 / 配置里一次都没出现的。
LoRA 文件夹不算（那是用户自己下载的）。用法：python -I devtest/tools/unused_models.py [输出.md]"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIRS = [os.path.join(ROOT, 'models'), os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'models')]
text = []
for a, ds, fs in os.walk(os.path.join(ROOT, 'studio')):
    ds[:] = [d for d in ds if d not in ('app-data', 'pylib', 'tmp', '__pycache__')]
    for f in fs:
        if f.endswith(('.py', '.js', '.json', '.txt', '.html')):
            try:
                text.append(open(os.path.join(a, f), encoding='utf-8', errors='ignore').read())
            except OSError:
                pass
for f in ('server.json',):
    text.append(open(os.path.join(ROOT, f), encoding='utf-8', errors='ignore').read())
blob = '\n'.join(text).replace('\\\\', '/').replace('\\', '/')
rows, total = [], 0
for d in DIRS:
    for a, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x.lower() not in ('loras', 'lora')]
        for f in fs:
            p = os.path.join(a, f)
            try:
                n = os.path.getsize(p)
            except OSError:
                continue
            if n < 2 << 30:
                continue
            stem = os.path.splitext(f)[0]
            used = f in blob or stem in blob or os.path.basename(a) in blob and os.path.basename(a) not in ('checkpoints', 'diffusion_models', 'text_encoders', 'vae', 'unet', 'clip')
            if not used:
                rows.append((n, os.path.relpath(p, ROOT))); total += n
rows.sort(reverse=True)
out = ['| 大小 | 文件 |', '|---|---|'] + [f'| {n / 2 ** 30:.1f} GB | `{r}` |' for n, r in rows] + [f'\n共 {len(rows)} 个，{total / 2 ** 30:.1f} GB']
print('\n'.join(out))
if len(sys.argv) > 1:
    open(sys.argv[1], 'w', encoding='utf-8').write('\n'.join(out) + '\n')
