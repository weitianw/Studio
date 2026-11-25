"""拼图：python -I sheet.py out.png cols tile_w file1 file2 ...（每张下面写文件名）"""
import sys, os
from PIL import Image, ImageDraw, ImageFont
out, cols, tw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); fs = [f for f in sys.argv[4:] if os.path.exists(f)]
ims = []
for f in fs:
    im = Image.open(f).convert('RGB'); k = tw / im.width; ims.append((os.path.basename(os.path.dirname(f)) + '/' + os.path.basename(f), im.resize((tw, max(1, int(im.height * k))))))
rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
try: font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 14)
except Exception: font = None
hs = [max(im.height for _, im in r) + 20 for r in rows]
S = Image.new('RGB', (cols * (tw + 6), sum(hs) + 4), (60, 60, 60)); y = 2
for r, h in zip(rows, hs):
    for i, (n, im) in enumerate(r):
        S.paste(im, (i * (tw + 6) + 3, y)); ImageDraw.Draw(S).text((i * (tw + 6) + 6, y + im.height + 2), n, fill=(255, 255, 0), font=font)
    y += h
S.save(out); print(out, S.size)
