"""音乐段落（2026-11-14）：All-In-One 音乐结构分析（mir-aidj/all-in-one 的 openmirlab/all-in-one-infer 版，不要 NATTEN、能在 Windows / CPU 上跑），
单独一个进程跑完就退出（模型 + 分离人声伴奏的 Demucs 约 1 GB 内存，不留在 Studio 里）。被 cutpoints.sections 调用。
用法：python allin1_run.py <音频> <输出.json> <线程数> <临时目录>
输出：{"sections": [[开始, 结束, 标签], …], "act": [段落切换的可能性，每秒 50 个], "fps": 50}
代码 MIT；模型权重 CC-BY-NC-SA-4.0（只能非商业用），放在 models/allin1。"""
import json, os, sys
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # 用 -I 启动时脚本所在的文件夹不在搜索路径里
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['TORCH_HOME'] = config.models('allin1')
sys.path.append(config.tools('allin1_lib'))
src, out, thr, tmp = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
import numpy as np, torch  # noqa: E402
torch.set_num_threads(max(1, thr))
from allin1_infer import analyze  # noqa: E402
r = analyze(src, device='cpu', multiprocess=False, include_activations=True, demix_dir=os.path.join(tmp, 'demix'), spec_dir=os.path.join(tmp, 'spec'), keep_byproducts=False)
seg = np.asarray(r.activations['segment'], dtype=np.float32).reshape(-1)  # 每秒 100 个
n = seg.size // 2 * 2
act = seg[:n].reshape(-1, 2).max(1) if n else seg
with open(out, 'w', encoding='utf-8') as f:
    json.dump({'sections': [[round(float(s.start), 3), round(float(s.end), 3), s.label] for s in r.segments], 'act': [round(float(v), 4) for v in act], 'fps': 50}, f)
