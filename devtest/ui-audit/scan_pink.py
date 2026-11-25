import sys, glob, os
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
tot = 0
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
    im = Image.open(f).convert("RGB"); px = im.load(); n = 0
    for y in range(0, im.height, 2):
        for x in range(0, im.width, 2):
            r, g, b = px[x, y]
            if r > 170 and g < 90 and b > 170: n += 1
    tot += n; print(os.path.basename(f), n)
print("合计", tot)
