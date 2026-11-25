"""生成测试用的音源库（一次生成，长期保留；只有几 MB）：覆盖各种格式、命名、层级、数量、坏文件等情况。
用法：python -I devtest/make_fixtures.py          （已经有的文件不重新生成）
     python -I devtest/make_fixtures.py --force  （全部重新生成）
     python -I devtest/make_fixtures.py --out 目录 （生成到别处，比如干净检出里验证）
媒体文件（MP4 / WAV 等）不进 git（.gitignore 按扩展名排除），干净检出后跑一次这个脚本即可。
2026-11-17 审查 C04：改成确定性生成——同一个 ffmpeg 版本、同样的参数，每次生成的文件逐字节一样
（-bitexact、编码器单线程、不写时间 / 版本等元数据，坏文件的“随机字节”用固定种子）。
ffmpeg：环境变量 STUDIO_FFMPEG > 仓库里的 tools\ffmpeg\bin\ffmpeg.exe > PATH 里的 ffmpeg。验证用的是 ffmpeg 9.0.2（gyan.dev essentials build）。"""
import os, random, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FX = os.path.abspath(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else os.path.join(HERE, 'fixtures')
FF = os.environ.get('STUDIO_FFMPEG') or next((x for x in (os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe'),) if os.path.isfile(x)), None) or shutil.which('ffmpeg') or 'ffmpeg'
FORCE = '--force' in sys.argv
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
RNG = random.Random(20261117)  # 坏文件的“随机字节”：固定种子，每次一样
EXACT = ['-threads', '1', '-fflags', '+bitexact', '-flags', '+bitexact', '-map_metadata', '-1', '-map_chapters', '-1']  # 输出端：不写编码器版本 / 时间，单线程


def ff(out, *args):
    if os.path.isfile(out) and not FORCE:
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    x265 = ['-x265-params', 'pools=1:frame-threads=1:log-level=error'] if 'libx265' in args else []
    subprocess.run([FF, '-v', 'error', '-y', *args, *EXACT, *x265, out], check=True, creationflags=NO_WINDOW)


def tone(out, sec=2, f=440, *extra):
    ff(out, '-f', 'lavfi', '-i', f'sine=f={f}:d={sec}', *extra)


def video(out, sec=3, size='640x360', rate=25, vcodec=('-c:v', 'libx264', '-pix_fmt', 'yuv420p'), acodec=('-c:a', 'aac'), src='testsrc2'):
    ff(out, '-f', 'lavfi', '-i', f'{src}=s={size}:r={rate}:d={sec}', '-f', 'lavfi', '-i', f'sine=f=330:d={sec}', *vcodec, *acodec, '-shortest')


def image(out, size='640x480', src='testsrc'):
    ff(out, '-f', 'lavfi', '-i', f'{src}=s={size}:d=1', '-frames:v', '1')


def raw(out, data):
    if os.path.isfile(out) and not FORCE:
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(data)


P = lambda *a: os.path.join(FX, 'pub', *a)
V = lambda *a: os.path.join(FX, 'vault', *a)

# 各种音频格式
tone(P('音乐', '常见格式', '01 MP3.mp3'), 3, 440)
tone(P('音乐', '常见格式', '02 M4A.m4a'), 3, 494, '-c:a', 'aac')
tone(P('音乐', '常见格式', '03 FLAC.flac'), 3, 523)
tone(P('音乐', '常见格式', '04 WAV.wav'), 2, 587)
tone(P('音乐', '常见格式', '05 OGG.ogg'), 3, 659, '-c:a', 'libvorbis')
tone(P('音乐', '常见格式', '06 OPUS.opus'), 3, 698, '-c:a', 'libopus')
tone(P('音乐', '常见格式', '07 大写扩展名.MP3'), 2, 784)
tone(P('音乐', '要转换的格式', 'WMA 格式.wma'), 2, 440, '-c:a', 'wmav2')
tone(P('音乐', '要转换的格式', 'AIFF 格式.aiff'), 2, 494)
tone(P('音乐', '长音频（2 分钟）.mp3'), 120, 220, '-b:a', '32k')
# 视频：能直接放的 / 要转换的 / 竖屏 / 放不了的
video(P('视频', '能直接放', 'H264 720p.mp4'), 4, '1280x720')
video(P('视频', '能直接放', '竖屏 9比16.mp4'), 3, '360x640')
video(P('视频', '能直接放', 'WebM VP9.webm'), 3, '640x360', vcodec=('-c:v', 'libvpx-vp9', '-b:v', '200k'), acodec=('-c:a', 'libopus'))
video(P('视频', '能直接放', 'MOV.mov'), 3)
video(P('视频', '能直接放', 'MKV 容器.mkv'), 3)
video(P('视频', '要转换', 'AVI 格式.avi'), 3, vcodec=('-c:v', 'mpeg4'), acodec=('-c:a', 'mp3'))
video(P('视频', '要转换', 'TS 格式.ts'), 3)
video(P('视频', '要转换', 'H265 HEVC.mp4'), 3, vcodec=('-c:v', 'libx265', '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1'))
video(P('视频', '高帧率 60fps.mp4'), 3, '1280x720', 60)
video(P('视频', '只有画面没有声音.mp4'), 3, acodec=('-an',))
raw(P('视频', '坏文件', '随机字节.mp4'), RNG.randbytes(200_000))
raw(P('视频', '坏文件', '空文件.mp4'), b'')
raw(P('音乐', '坏文件', '空文件.mp3'), b'')
raw(P('音乐', '坏文件', '其实是文本.mp3'), '这不是音频'.encode('utf-8'))
# 图片
image(P('图片', 'PNG.png'), '800x600')
image(P('图片', 'JPG.jpg'), '1024x768', 'testsrc2')
image(P('图片', 'WebP.webp'), '640x640')
image(P('图片', '竖图.png'), '600x1200', 'testsrc2')
image(P('图片', '超大 4000x3000.jpg'), '4000x3000')
ff(P('图片', '动图.gif'), '-f', 'lavfi', '-i', 'testsrc=s=200x150:r=5:d=2')
raw(P('图片', '坏图片.png'), b'\x89PNG\r\n\x1a\nbroken')
# 剧集：多层文件夹、按数字排序（第2集 要排在 第10集 前面）
for s in (1, 2):
    for e in (1, 2, 10):
        video(P('剧集', f'第{s}季', f'第{e}集.mp4'), 2, '320x180')
# 很多文件（测试长列表、虚拟滚动、手机上滑动）
for k in range(1, 401):
    tone(P('很多文件（400 个）', f'片段 {k:03d}.mp3'), 1, 200 + k, '-b:a', '16k')
# 名字很怪的
tone(P('特殊名字', '有 空格  和  多个空格.mp3'), 1)
tone(P('特殊名字', '符号 #&%+=@!~()[]{}.mp3'), 1)
tone(P('特殊名字', 'emoji 🎵🎧✨.mp3'), 1)
tone(P('特殊名字', '日本語 にほんご.mp3'), 1)
tone(P('特殊名字', 'English Name With Caps.mp3'), 1)
tone(P('特殊名字', '超长的名字' * 12 + '.mp3'), 1)
tone(P('特殊名字', '.隐藏开头的点.mp3'), 1)
# 很深的层级、空文件夹、只有图片的文件夹
tone(P('很深', '一', '二', '三', '四', '五', '最里面.mp3'), 1)
os.makedirs(P('空文件夹'), exist_ok=True)
image(P('只有图片', '一张图.jpg'), '400x300')
# 根目录下直接放的文件（“未分类”）
tone(P('放在根目录.mp3'), 2)
# 私密空间的音源库（测试两个空间互相看不到）
video(V('私密视频', '私密 1.mp4'), 3)
tone(V('私密音频', '私密录音.mp3'), 2)
image(V('私密图片', '私密图片.png'), '640x480')
tone(V('放在私密根目录.mp3'), 1)
# 生图用的原图（图生图 / 局部重画）
image(os.path.join(FX, 'images', '原图 1024.png'), '1024x1024', 'testsrc2')
image(os.path.join(FX, 'images', '竖图 768x1344.png'), '768x1344')
size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(FX) for f in fs)
print(f'测试素材就绪：{sum(len(fs) for _, _, fs in os.walk(FX))} 个文件，共 {size / 1e6:.1f} MB')
