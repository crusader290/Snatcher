@echo off
rem Snatcher static recompilation: fetch dependencies, build segarecomp, compile the game.
rem
rem   build.bat                       fetch dependencies and build the segarecomp CLI only
rem   build.bat DISC.cue BIOS.bin     ...then compile Snatcher into work\game (about an hour)
rem
rem Options (environment variables):
rem   MSYS2_ROOT       MSYS2 install folder (default C:\msys64; installed with winget if missing)
rem   SNATCHER_BUDGET  build-pass instruction budget (default 10000000000)
rem   SNATCHER_JOBS    parallel compile jobs (default: number of processors)
rem   SNATCHER_ROUTE   input route that drives the build pass (default routes\act1-chief.route)
rem
rem Nothing from the game or the BIOS is copied into the repository; everything derived goes to work\.
setlocal EnableExtensions
cd /d "%~dp0"

if "%MSYS2_ROOT%"=="" set "MSYS2_ROOT=C:\msys64"
if "%SNATCHER_BUDGET%"=="" set "SNATCHER_BUDGET=10000000000"
if "%SNATCHER_JOBS%"=="" set "SNATCHER_JOBS=%NUMBER_OF_PROCESSORS%"
if "%SNATCHER_ROUTE%"=="" set "SNATCHER_ROUTE=routes\act1-chief.route"
set "UCRT=%MSYS2_ROOT%\ucrt64"
set "CUE=%~f1"
set "BIOS=%~f2"

echo == [1/6] Host tools: Git, Python 3.10+, MSYS2
where git >nul 2>nul || call :winget Git.Git Git || goto :fail
call :find_python || goto :fail
if not exist "%MSYS2_ROOT%\usr\bin\bash.exe" call :winget MSYS2.MSYS2 MSYS2 || goto :fail
if not exist "%MSYS2_ROOT%\usr\bin\bash.exe" (echo MSYS2 not found at %MSYS2_ROOT%; set MSYS2_ROOT to its folder.& goto :fail)

echo == [2/6] MSYS2 UCRT64 packages: gcc, cmake, ninja, SDL3
"%MSYS2_ROOT%\usr\bin\bash.exe" -lc "pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-sdl3"
if errorlevel 1 (echo pacman failed. Update MSYS2 once with: %MSYS2_ROOT%\usr\bin\bash.exe -lc "pacman -Syu" & goto :fail)
set "PATH=%UCRT%\bin;%PATH%"

echo == [3/6] Submodules
git submodule update --init external/segagenesisrecomp external/z80-frontend external/segarecomp || goto :fail
git -C external/segagenesisrecomp submodule update --init external/m68k-recomp-core external/z80-recomp-core || goto :fail

echo == [4/6] Local patches
"%PY%" tools\apply_patches.py || goto :fail

echo == [5/6] segarecomp CLI
if not exist build\segarecomp-ucrt\CMakeCache.txt (
  cmake -S external/segarecomp -B build/segarecomp-ucrt -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ || goto :fail
)
cmake --build build/segarecomp-ucrt --target segarecomp -j %SNATCHER_JOBS% || goto :fail
set "SEGARECOMP=%CD%\build\segarecomp-ucrt\apps\segarecomp\segarecomp.exe"
if not exist "%SEGARECOMP%" (echo segarecomp.exe was not produced.& goto :fail)

if "%~2"=="" (
  echo.
  echo Dependencies are ready. To compile the game, run:
  echo   build.bat "path\to\Snatcher.cue" "path\to\US v1.10 Sega CD BIOS.bin"
  exit /b 0
)

echo == [6/6] Compile Snatcher
if not exist "%CUE%" (echo CUE not found: "%CUE%"& goto :fail)
if not exist "%BIOS%" (echo BIOS not found: "%BIOS%"& goto :fail)
"%PY%" -c "import hashlib,sys;h=hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest();ok=h=='807384678ef259494d943eddb6954dfc7069693d0dde0c424e2028488d88e81a';print('BIOS ok' if ok else 'BIOS SHA-256 '+h+' is not the US Model 1 v1.10 BIOS');sys.exit(0 if ok else 1)" "%BIOS%" || goto :fail
set "CUE_FIXED="
for /f "usebackq delims=" %%C in (`call "%PY%" tools\fix_cue.py "%CUE%"`) do set "CUE_FIXED=%%C"
if not defined CUE_FIXED goto :fail
for %%D in ("%CUE_FIXED%") do set "DISC_DIR=%%~dpD"
set "DISC_DIR=%DISC_DIR:~0,-1%"
if not exist work mkdir work
if not exist work\save mkdir work\save
"%PY%" tools\make_bram.py work\bram-formatted.bin || goto :fail
"%PY%" tools\route.py "%SNATCHER_ROUTE%" work\input-route.txt || goto :fail

"%SEGARECOMP%" sega-cd build --cue "%CUE_FIXED%" --bios "%BIOS%" --output work\game --runtime-dir external\segarecomp ^
  --cc "%UCRT%\bin\gcc.exe" --cxx "%UCRT%\bin\g++.exe" --cache-dir work\cache --jobs %SNATCHER_JOBS% ^
  --backup-ram work\bram-formatted.bin --input-script work\input-route.txt --budget %SNATCHER_BUDGET% --pass-timeout 14400 ^
  --link-arg -Wl,--stack,8388608 --emit-arg --disc-image --emit-arg main:31488:16769280:1280 --file-first structural ^
  --viewer 1 --sdl3-include "%UCRT%\include" --sdl3-lib "%UCRT%\lib"
if errorlevel 1 (echo segarecomp build failed; see work\game\status.json& goto :fail)
copy /y "%UCRT%\bin\SDL3.dll" work\game\ >nul || goto :fail

rem play.bat reads these
> work\play-config.bat echo set "BIOS=%BIOS%"
>> work\play-config.bat echo set "DISC_DIR=%DISC_DIR%"
echo.
echo Built work\game\program-viewer.exe. Run play.bat to play.
exit /b 0

:find_python
set "PY="
for /f "delims=" %%P in ('python -c "import sys;print(sys.executable) if sys.version_info>=(3,10) else None" 2^>nul') do set "PY=%%P"
if defined PY exit /b 0
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable) if sys.version_info>=(3,10) else None" 2^>nul') do set "PY=%%P"
if defined PY exit /b 0
call :winget Python.Python.3.12 Python || exit /b 1
echo Python was installed; open a new terminal so it is on PATH, then run build.bat again.
exit /b 1

:winget
echo %2 is missing; installing it with winget (%1)...
where winget >nul 2>nul || (echo winget is not available; install %2 yourself and re-run.& exit /b 1)
winget install --exact --id %1 --silent --accept-source-agreements --accept-package-agreements || (echo winget could not install %2.& exit /b 1)
exit /b 0

:fail
echo.
echo build.bat failed.
exit /b 1
