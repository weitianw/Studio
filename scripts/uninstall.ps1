# 一键卸载：停止服务、删除 D:\AI-TTS 里的程序/模型/生成的临时文件和桌面快捷方式。不改动系统其他任何地方。
# 个人资料默认保留：隐藏文件夹 .data（私密空间）、“音源库”（播放页的音源）、“素材库”（改视频 / 生视频用的素材）、outputs（生成的作品）、voice-library（录制 / 克隆 / 设计的音色），只有明确输入 DELETE 才会删除。
# 2026-11-17 审查 C06（用户定）：voice-library 以前不在保留名单里，会被一起删掉
# 2026-11-14 审查：以前“素材库”和 outputs 不在保留名单里，会被一起删掉
param([string]$Root)

$Root = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
# 安全检查：只删除本工具自己的文件夹
if (-not (Test-Path -LiteralPath (Join-Path $Root 'scripts\uninstall.ps1'))) { Write-Host "$Root 不是 AI-TTS 安装目录，已停止。" -ForegroundColor Red; Read-Host; exit 1 }

$ans = Read-Host "将删除 $Root 里的程序和模型（.data、“音源库”、“素材库”、outputs、voice-library（音色库）这几个个人资料文件夹会保留）。确定请输入 Y"
if ($ans -ne 'Y' -and $ans -ne 'y') { Write-Host '已取消。'; exit 0 }
$Data = Join-Path $Root '.data'
$Pub = Join-Path $Root '音源库'
$keepNames = @('.data', '音源库', '素材库', 'outputs', 'voice-library')
$keepData = $true
if (($keepNames | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_) })) {
  $d = Read-Host "“.data”（私密空间）、“音源库”、“素材库”、outputs、voice-library（音色库）里是你的个人资料，默认保留。要连它们一起删除，请输入 DELETE；直接回车保留"
  if ($d -ceq 'DELETE') { $keepData = $false }
}

# 只结束本项目里的音频引擎（按完整路径，不按名字全杀）
Get-Process audiocpp_server -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root\*" } | Stop-Process -Force
# 审查 8：进程按这份安装目录（$Root\studio）认，不再用写死的 *AI-TTS*studio* 模糊匹配（别的目录里的同名项目也会被结束）
$StudioDir = ((Join-Path $Root 'studio') + '\').ToLower()
$Ours = { param($c, $k) $c -and $c.ToLower().Contains($StudioDir) -and $c.ToLower().Contains($k) }
# 停止网页工作室（python studio\server.py）
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { & $Ours $_.CommandLine 'server.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# 停止应用版（pythonw studio\app.py）
Get-CimInstance Win32_Process -Filter "Name like 'pythonw%'" | Where-Object { & $Ours $_.CommandLine 'app.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# 应用版也可能是 Studio.exe / StudioServer.exe（Conda 里改了名字的 python，studio\studioexe.py）
Get-CimInstance Win32_Process -Filter "Name = 'Studio.exe' or Name = 'StudioServer.exe'" | Where-Object { & $Ours $_.CommandLine '' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$Desktop = [Environment]::GetFolderPath('Desktop')
Remove-Item -LiteralPath (Join-Path $Desktop 'AI配音 (Breeze TTS).lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $Desktop 'Studio.lnk') -Force -ErrorAction SilentlyContinue
foreach ($n in 'Studio.exe', 'StudioServer.exe') { foreach ($f in $n, "$n.studio.json", "$n.old") { Remove-Item -LiteralPath (Join-Path 'D:\App\Conda' $f) -Force -ErrorAction SilentlyContinue } }
if ($keepData -and ($keepNames | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_) })) {
  # 只删除个人资料文件夹以外的东西
  Get-ChildItem -LiteralPath $Root -Force | Where-Object { $keepNames -notcontains $_.Name } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  $left = Get-ChildItem -LiteralPath $Root -Force | Where-Object { $keepNames -notcontains $_.Name }
  if ($left) { Write-Host "有文件没删掉（可能被占用），请重启电脑后手动删除（个人资料文件夹除外）" -ForegroundColor Yellow }
  else { Write-Host "卸载完成。个人资料保留在 $Root 的 .data（隐藏）、“音源库”、“素材库”、outputs、voice-library（音色库）里。" -ForegroundColor Green }
} else {
  Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $Root) { Write-Host "有文件没删掉（可能被占用），请重启电脑后手动删除 $Root" -ForegroundColor Yellow }
  else { Write-Host '卸载完成，已全部删除。' -ForegroundColor Green }
}
Read-Host '按回车关闭'
