@echo off
setlocal
pushd "%~dp0"
set "BILLIARDS_EXE=%~dp0GPUPhysicsBilliards.exe"
if not exist "%BILLIARDS_EXE%" set "BILLIARDS_EXE=%~dp0zig-out\bin\GPUPhysicsBilliards.exe"
if not exist "%BILLIARDS_EXE%" (
  echo Billiards executable missing. Build with python build_billiards.py or extract the complete portable ZIP.
  popd
  exit /b 2
)
"%BILLIARDS_EXE%" %*
set "BILLIARDS_EXIT=%errorlevel%"
popd
if not "%BILLIARDS_EXIT%"=="0" echo Billiards exited with error %BILLIARDS_EXIT%.
exit /b %BILLIARDS_EXIT%
