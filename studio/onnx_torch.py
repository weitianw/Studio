"""在显卡上跑 ONNX 模型（2026-11-05，找换装点用）：把 .onnx 里的计算图逐个节点用 PyTorch 算。
只实现了 models/detect 里 YOLOX-L（找人）和 DWPose（关键点）用到的算子（opset 11）；和 onnxruntime 的结果对过。
在 ComfyUI 自带的 Python 里用（那里有显卡版的 torch 和 onnx 读取库），Studio 自己的 Python 只有 CPU 版 torch。"""
import numpy as np
import torch
import torch.nn.functional as F


def _attrs(n):
    import onnx
    return {a.name: onnx.helper.get_attribute_value(a) for a in n.attribute}


class Session:
    """和 onnxruntime.InferenceSession 一样的用法：run(None, {输入名: 数组}) → [输出数组, …]"""

    def __init__(self, path, device='cuda', half=False):
        import onnx
        from onnx import numpy_helper
        m = onnx.load(path)
        self.dev, self.half = torch.device(device), half
        self.w = {}
        for t in m.graph.initializer:
            a = numpy_helper.to_array(t)
            self.w[t.name] = torch.from_numpy(a.copy()).to(self.dev) if a.dtype.kind == 'f' else torch.from_numpy(a.astype(np.int64))  # 整数（形状、下标）留在 CPU
        self.nodes = [(n.op_type, list(n.input), list(n.output), _attrs(n)) for n in m.graph.node]
        self.inputs = [i.name for i in m.graph.input if i.name not in self.w]
        self.outputs = [o.name for o in m.graph.output]

    @torch.inference_mode()
    def run(self, names, feeds):
        v = dict(self.w)
        for k, a in feeds.items():
            v[k] = torch.from_numpy(np.ascontiguousarray(a)).to(self.dev)
        for op, ins, outs, at in self.nodes:
            x = [v[i] if i else None for i in ins]
            r = getattr(self, '_' + op)(x, {**at, '_n': len(outs)})
            if not isinstance(r, (list, tuple)):
                r = [r]
            for o, t in zip(outs, r):
                v[o] = t
        return [v[o].float().cpu().numpy() for o in (names or self.outputs)]

    # ---- 算子
    @staticmethod
    def _ints(t):
        return [int(i) for i in (t.tolist() if torch.is_tensor(t) else t)]

    def _Conv(self, x, a):
        X, W, B = x[0], x[1], x[2] if len(x) > 2 else None
        p = a.get('pads', [0, 0, 0, 0]); s = a.get('strides', [1, 1]); d = a.get('dilations', [1, 1]); g = a.get('group', 1)
        if p[0] == p[2] and p[1] == p[3]:
            return F.conv2d(X, W, B, s, (p[0], p[1]), d, g)
        return F.conv2d(F.pad(X, (p[1], p[3], p[0], p[2])), W, B, s, 0, d, g)

    def _Sigmoid(self, x, a): return torch.sigmoid(x[0])
    def _Relu(self, x, a): return torch.relu(x[0])
    def _Mul(self, x, a): return x[0] * x[1]
    def _Add(self, x, a): return x[0] + x[1]
    def _Div(self, x, a): return x[0] / x[1]
    def _Sqrt(self, x, a): return torch.sqrt(x[0])
    def _Identity(self, x, a): return x[0]
    def _MatMul(self, x, a): return torch.matmul(x[0], x[1])

    def _HardSigmoid(self, x, a):
        return torch.clamp(a.get('alpha', 0.2) * x[0] + a.get('beta', 0.5), 0, 1)

    def _Clip(self, x, a):
        lo = x[1] if len(x) > 1 and x[1] is not None else a.get('min'); hi = x[2] if len(x) > 2 and x[2] is not None else a.get('max')
        lo = float(lo) if lo is not None else None; hi = float(hi) if hi is not None else None
        return torch.clamp(x[0], lo, hi)

    def _Concat(self, x, a):
        ax = a['axis']
        if all(not t.is_floating_point() for t in x):
            return torch.cat([t.cpu().reshape(-1) if t.dim() == 0 else t.cpu() for t in x], ax)
        return torch.cat(x, ax)

    def _MaxPool(self, x, a):
        k = a['kernel_shape']; s = a.get('strides', [1, 1]); p = a.get('pads', [0, 0, 0, 0])
        if p[0] == p[2] and p[1] == p[3]:
            return F.max_pool2d(x[0], k, s, (p[0], p[1]), ceil_mode=bool(a.get('ceil_mode', 0)))
        return F.max_pool2d(F.pad(x[0], (p[1], p[3], p[0], p[2]), value=float('-inf')), k, s, 0, ceil_mode=bool(a.get('ceil_mode', 0)))

    def _GlobalAveragePool(self, x, a): return x[0].mean((2, 3), keepdim=True)

    def _Resize(self, x, a):
        mode = a.get('mode', b'nearest'); mode = mode.decode() if isinstance(mode, bytes) else mode
        sizes = x[3] if len(x) > 3 and x[3] is not None and x[3].numel() else None
        if mode != 'nearest':
            raise NotImplementedError('Resize ' + mode)
        if sizes is not None:
            return F.interpolate(x[0], size=self._ints(sizes)[2:], mode='nearest')
        sc = [float(t) for t in x[2].tolist()][2:]
        return F.interpolate(x[0], scale_factor=sc, mode='nearest')

    def _Slice(self, x, a):
        d = x[0]; st, en = self._ints(x[1]), self._ints(x[2])
        ax = self._ints(x[3]) if len(x) > 3 and x[3] is not None else list(range(len(st)))
        sp = self._ints(x[4]) if len(x) > 4 and x[4] is not None else [1] * len(st)
        idx = [slice(None)] * d.dim()
        for s0, e0, a0, p0 in zip(st, en, ax, sp):
            n = d.shape[a0]; e0 = min(e0, n) if e0 >= 0 else e0; s0 = min(s0, n) if s0 >= 0 else s0
            if p0 < 0:
                raise NotImplementedError('Slice step < 0')
            idx[a0] = slice(s0, e0, p0)
        return d[tuple(idx)]

    def _Reshape(self, x, a):
        sh = self._ints(x[1]); sh = [x[0].shape[i] if v == 0 else v for i, v in enumerate(sh)]
        return x[0].reshape(sh)

    def _Transpose(self, x, a): return x[0].permute(*a['perm'])
    def _Shape(self, x, a): return torch.tensor(list(x[0].shape), dtype=torch.int64)

    def _Constant(self, x, a):
        from onnx import numpy_helper
        arr = numpy_helper.to_array(a['value'])
        return torch.from_numpy(arr.copy()).to(self.dev) if arr.dtype.kind == 'f' else torch.from_numpy(arr.astype(np.int64))

    def _ReduceSum(self, x, a):
        ax = a.get('axes'); kd = bool(a.get('keepdims', 1))
        return x[0].sum(dim=tuple(ax), keepdim=kd) if ax else x[0].sum()

    def _Split(self, x, a):
        ax = a.get('axis', 0); sp = a.get('split')
        if sp:
            return list(torch.split(x[0], list(sp), ax))
        return list(torch.chunk(x[0], a['_n'], ax))  # 没写大小：平均分

    def _Unsqueeze(self, x, a):
        t = x[0]
        for ax in sorted(a['axes']):
            t = t.unsqueeze(ax)
        return t

    def _Squeeze(self, x, a):
        t = x[0]
        for ax in sorted(a.get('axes', []), reverse=True):
            t = t.squeeze(ax)
        return t
