@echo off
setlocal
pushd "%~dp0"
"%~dp0GPUPhysicsPlayground.exe" %*
set "PLAY_EXIT=%errorlevel%"
popd
if not "%PLAY_EXIT%"=="0" echo Playground exited with error %PLAY_EXIT%.
exit /b %PLAY_EXIT%
