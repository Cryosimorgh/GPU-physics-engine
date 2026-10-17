@echo off
setlocal
pushd "%~dp0"
"%~dp0GPUPhysicsBilliards.exe" %*
set "BILLIARDS_EXIT=%errorlevel%"
popd
if not "%BILLIARDS_EXIT%"=="0" echo Billiards exited with error %BILLIARDS_EXIT%.
exit /b %BILLIARDS_EXIT%
