#!/bin/sh
# 全量检查：devtest/ui-audit 里现有的检查脚本依次跑一遍（2026-11-18），每个只留最后几行和退出码
cd "$(dirname "$0")"
FAILED=""; MISS=""; mkdir -p suite_logs
PY=../.venv/Scripts/python.exe
for t in t_validate states t_imgflow t_lay t_layer t_sound_reset u_check ui_review_fix queue_regress pl_hover_scroll lib_watch_cache persist_space now_art \
         np_check2 np_desk np_ext_audio np_look np_morph np_queue_glide np_regen np_subs_import np_subs_layout np_vol \
         t_vault_rc t_vault_rc_resume t_iphone_all ip_chips ip_drag ip_headh ip_heads ip_headtop ip_kb ip_lyrics ip_lyrics_long ip_mats ip_np ip_play ip_play2 \
         ip_plback ip_pltree ip_scroll ip_seek ip_sheets ip_sound ip_tiles ip_viewer ip_xchip ip_xgal ip_xref ip_play_drill ip_np_theater ip_sheets_pull t_qset play_full t_click; do
  [ -f "$t.py" ] || { echo "=== $t（缺这个脚本）"; MISS="$MISS $t"; continue; }
  arg=""; [ "$t" = states ] && arg="app1440"  # states.py 要一个尺寸配置
  echo "=== $t"; STUDIO_TEST_PORT=${STUDIO_TEST_PORT:-7897} timeout 900 $PY -I $t.py $arg > "suite_logs/$t.log" 2>&1; rc=$?; echo "exit=$rc"
  [ $rc -ne 0 ] && FAILED="$FAILED $t"
  grep -E "失败|✗|FAIL|Traceback|Error|通过|ok|OK" "suite_logs/$t.log" | tail -4 | cut -c1-260
done
# 2026-11-23 第二轮审查 11：汇总，有失败 / 缺脚本就以 1 退出（以前只打印各项，外面看不出这次没过）
echo "=== 汇总"; echo "没过：${FAILED:-无}"; echo "缺脚本：${MISS:-无}"
[ -z "$FAILED$MISS" ] || exit 1
