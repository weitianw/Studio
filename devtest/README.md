# devtest：测试用的东西都在这里（2026-11-14 从各次会话的临时文件夹搬进来）

| 文件夹 / 文件 | 用途 |
|---|---|
| `run.py` | 测试 Studio，和真实数据完全隔开；按用途选 `--profile`（见下表） |
| `state/` | dev 的测试数据（原来就在这里） |
| `states/gpu/` | gpu / chk / dy 的测试数据（原来在临时文件夹 st_state，2.9 GB） |
| `states/ui/` | ui 的测试数据（原来的 st_ui，1.1 GB） |
| `fixtures/` | 新建测试数据时复制的初始音源库 |
| `gpu-tests/` | 显卡 A/B 测试脚本（公开版不含） |
| `agent/` | Agent 接口测试：`post.py`（直接调 `/api/...`）、`mcp_client_test.py` / `mcp_qc_test.py`（用官方 MCP 客户端测 `studio/agent_mcp.py`）、`a1test.py`（音乐段落） |
| `tools/` | `proxy_ui.py`（预览用的转发）、`scan_shadow.py`（后台改完查“函数里 import 执行前就用了”；退出码 0 没发现 / 1 发现 / 2 读不了，可直接接进脚本）、`probe.py`（测试 Studio 起来后的快速自检）、`bench_p01.py`～`bench_p06.py`、`bench_p08.py`（2026-11-17 审查各性能项的前后测量，合成数据） |
| `ui-audit/` | 界面全面检查；`bench_p07.py` / `bench_p09.py` 播放列表重绘、按键保存的测量，`queue_regress.py` / `persist_space.py` 对应的回归 |

## run.py 的 profile

| profile | 用途 | 电脑 / 手机 | ComfyUI | 测试数据 | 素材库 |
|---|---|---|---|---|---|
| dev（默认） | 日常开发 | 7865 / 7866 | 8189 | `state` | 真实素材库 |
| gpu | 显卡 A/B 测试 | 7897 / 7898 | 8199 | `states/gpu` | 真实素材库 |
| chk | 全面检查 | 7897 / 7898 | 8199 | `states/gpu` | 测试数据里的 `mats`（隔开） |
| ui | 界面预览 | 7899 / 7900 | 8299 | `states/ui` | 真实素材库 |

- 改端口：`--port`、`--phone-port`、`--comfy-port`，或环境变量 `STUDIO_TEST_PORT`、`STUDIO_TEST_PHONE_PORT`、`STUDIO_TEST_COMFY_PORT`（命令行优先）。
  - 只改 `--port` 时，其余端口跟着挪同样多。
  - 例：`--profile gpu --port 7917` → 手机 7918、ComfyUI 8219、生图 / 翻译 / 提示词 8125 / 8126 / 8128。
- 改测试数据目录：`--state 目录` 或 `STUDIO_TEST_STATE`。
- `gpu-tests`、`agent`、`ui-audit` 里的脚本都看 `STUDIO_TEST_PORT` / `STUDIO_TEST_COMFY_PORT` / `STUDIO_TEST_STATE`，默认 7897 / 8199 / `states/gpu`。

## 几个会话同时测试
每个会话用不同的 `--port`，并且各用一份测试数据（`--state`），因为同一份数据被两个 Studio 同时写会乱。例：

```
set STUDIO_TEST_PORT=7917
set STUDIO_TEST_STATE=D:\AI-TTS\devtest\states\gpu2
python -I devtest\run.py --profile gpu
```

- 新目录第一次用时会从 `fixtures` 建一份空的测试数据。
- 显卡只有一张：两个会话同时跑生成会抢显存。可以同时测界面和后台；生成最好一个一个来。

## 测试素材（fixtures）
`fixtures/` 里的图片进 git；视频、音频（MP4 / WAV / MP3……）按扩展名不进 git。干净检出后跑一次：

```
python -I devtest\make_fixtures.py
```

- 同一个 ffmpeg、同样的参数，生成的文件逐字节一样（2026-11-17 审查 C04：两次生成 453 个文件哈希全同）；已有的文件不重新生成，`--force` 全部重做，`--out 目录` 生成到别处。
- ffmpeg：`STUDIO_FFMPEG` 环境变量 > 仓库里的 `tools\ffmpeg\bin\ffmpeg.exe` > PATH。验证用 ffmpeg 9.0.2（gyan.dev essentials build），要有 libx264 / libx265 / libvpx-vp9 / libopus / libvorbis。
- 只用合成的测试图、正弦音、彩条视频，没有任何用户素材。

## 测试用的新版 ComfyUI（comfy_new，不进 git）
H3-Image 等新节点要比 Studio 自带的便携版更新的 ComfyUI。`comfy_new_boot.py` 用便携版的 Python 启动一份独立的副本，只在这个进程里把副本和新版 comfy-kitchen 放到搜索路径最前面，不改原来的 Python。

准备步骤（审查时本机的版本）：
1. `git clone https://github.com/Comfy-Org/ComfyUI devtest\comfy_new`，`git -C devtest\comfy_new checkout e9afbccc2669677076feb08e52658f129cd8c12b`（ComfyUI 0.45.0）。
2. 新版 comfy-kitchen 装到单独的文件夹：`tools\ComfyUI_windows_portable\python_embeded\python.exe -m pip install comfy-kitchen==0.2.41 --target devtest\comfy_new_pydeps`（便携版自己的 comfy-kitchen 是 0.2.40，见 `comfy_update_1116_before.txt`）。
3. 模型共用便携版的：在 `devtest\comfy_new\extra_model_paths.yaml` 里写 `main:` → `base_path: D:/AI-TTS/tools/ComfyUI_windows_portable/ComfyUI/`、`is_default: true`，再列出 checkpoints / diffusion_models / text_encoders / clip / vae / loras / upscale_models 各自的 `models/...` 子目录。
4. 启动：`python_embeded\python.exe -s devtest\comfy_new_boot.py --listen 127.0.0.1 --port <测试端口> --extra-model-paths-config devtest\comfy_new\extra_model_paths.yaml --input-directory ... --output-directory ...`（`gpu-tests/img_ab/run.py` 里 `AB_NEW=1` 时就是这样起的）。只用测试端口，不碰 8188。
