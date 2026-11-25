#!/bin/sh
# 全量检查：audit2 的所有尺寸配置依次跑（2026-11-18）
cd "$(dirname "$0")"
for p in app1920 app2560 app1600 app1440 app1366 app1280 win1200 win1199 win1024 win900 win761 win1920s app3840 web1920 light1920 ph440 ph393 ph390 ph375 ph440l phland pad768 pad1024; do
  echo "=== $p"; STUDIO_TEST_PORT=${STUDIO_TEST_PORT:-7897} timeout 900 ../.venv/Scripts/python.exe -I audit2.py $p 2>&1 | tail -4
done
