@echo off
setlocal
pushd "%~dp0"
"%~dp0GPUPhysicsBench.exe" %*
set "BENCH_EXIT=%errorlevel%"
popd
if not "%BENCH_EXIT%"=="0" echo GPU Physics Bench exited with error %BENCH_EXIT%.
exit /b %BENCH_EXIT%
