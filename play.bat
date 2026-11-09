@echo off
rem Play the recompiled Snatcher built by build.bat (SDL3 viewer: arrows, Z/X/C = A/B/C, Return = Start, Esc = menu).
rem Saves live in work\save\backup-ram.bin. Extra arguments are passed to the viewer.
setlocal EnableExtensions
cd /d "%~dp0"
if not exist work\game\program-viewer.exe (
  echo The game is not built yet: work\game\program-viewer.exe is missing.
  echo Run:  build.bat "path\to\Snatcher.cue" "path\to\US v1.10 Sega CD BIOS.bin"
  echo If build.bat is still running, wait for it to print "Run play.bat to play."
  goto :hold
)
if not exist work\play-config.bat (
  echo work\play-config.bat is missing; re-run build.bat with the CUE and BIOS.
  goto :hold
)
call work\play-config.bat
if not exist work\save mkdir work\save
if not exist work\save\backup-ram.bin copy /y work\bram-formatted.bin work\save\backup-ram.bin >nul
work\game\program-viewer.exe --disc-dir "%DISC_DIR%" --bios "%BIOS%" --instruction-budget 18000000000000000000 ^
  --backup-ram work\save\backup-ram.bin --backup-ram-out work\save\backup-ram.new %*
set RC=%ERRORLEVEL%
if exist work\save\backup-ram.new move /y work\save\backup-ram.new work\save\backup-ram.bin >nul
if %RC%==0 exit /b 0
echo.
if %RC%==10 (
  echo The game reached code the build did not compile ^(a typed stop^).
  echo Extending routes\ and rebuilding covers more of the game.
) else (
  echo The viewer exited with code %RC%. Codes: 2 usage, 20 disc refused, 22 backup RAM refused, 24 host/SDL failure.
)
:hold
echo.
pause
exit /b 1
