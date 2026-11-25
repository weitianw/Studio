r"""逐帧人脸关键点（ComfyUI 自带的 MediaPipe Face Landmarker，478 点）。用 ComfyUI 自带的 Python 跑（outfit2.py 调用）：
python_embeded\python.exe -I facelmk.py [--multi] 视频或图片 输出.npz [视频或图片 输出.npz ...]
输出 npz：xy（帧, 478, 2，没认出脸的帧是 nan）、size（高, 宽）；--multi：每帧最多 4 张脸，xy（帧, 4, 478, 2）"""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI')
sys.path.insert(0, COMFY)
import numpy as np, torch  # noqa: E402
import comfy.utils  # noqa: E402
from comfy_extras.nodes_mediapipe import FaceLandmarkerModel  # noqa: E402
FF = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
MODEL = os.path.join(COMFY, 'models', 'detection', 'mediapipe_face_fp32.safetensors')


def frames_of(path):
    pr = json.loads(subprocess.run([FF.replace('ffmpeg.exe', 'ffprobe.exe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', path],
                                   capture_output=True, text=True).stdout)['streams'][0]
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, pr['height'], pr['width'], 3)


torch.set_grad_enabled(False)
m = FaceLandmarkerModel(comfy.utils.load_torch_file(MODEL, safe_load=True))
args = sys.argv[1:]
multi = bool(args) and args[0] == '--multi'
args = args[1:] if multi else args
for src, dst in zip(args[0::2], args[1::2]):
    fr = frames_of(src)
    nf = 4 if multi else 1
    out = np.full((len(fr), nf, 478, 2), np.nan, np.float32)
    for i in range(0, len(fr), 16):
        res = m.detect_batch([fr[k] for k in range(i, min(i + 16, len(fr)))], num_faces=nf, score_thresh=0.3, variant='full')
        for k, faces in enumerate(res):
            for q, f in enumerate(faces[:nf]):
                out[i + k, q] = np.asarray(f['landmarks_xy'], np.float32)[:478, :2]
    out = out if multi else out[:, 0]
    np.savez_compressed(dst, xy=out, size=np.array(fr.shape[1:3]))
