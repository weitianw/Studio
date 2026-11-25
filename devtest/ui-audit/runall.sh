#!/bin/bash
# 3 个一组并行跑
cd "$(dirname "$0")"
PY="${PW_PY:-../.venv/Scripts/python.exe}"  # devtest/.venv（requirements-ui.txt：playwright 1.64.1，浏览器用已下载的 chromium_headless_shell-1217）
run() { for p in "$@"; do $PY audit2.py $p > aud_$p.log 2>&1; done; }
run app1920 app1920t app2560 app3840 web1920 light1920 &
run app1600 app1440 app1366 app1280 win1920s &
run win1200 win1199 win1024 win900 win761 &
run ph440 ph393 ph390 ph375 ph440l phland pad768 pad1024 &
wait
tail -q -n1 aud_*.log
