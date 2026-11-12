@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Epsilon desktop pet

rem ================================================== 1) already installed here?
if exist "._python\pythonw.exe" goto :run

rem ================================================== 2) system Python with the libs?
where pythonw >nul 2>nul && pythonw -c "import PyQt6.QtWidgets, PyQt6.QtGui, PIL" >nul 2>nul && (start "" /min pythonw epsilon.py & exit /b 0)
where python >nul 2>nul && python -c "import PyQt6.QtWidgets, PyQt6.QtGui, PIL" >nul 2>nul && (start "" /min python epsilon.py & exit /b 0)

rem ================================================== first run: portable Python + libs (internet)
echo --------------------------------------------------------------
echo  Epsilon desktop pet: first run on this machine...
echo  Downloading portable Python and libraries (about 130 MB)
echo  Needs INTERNET. First run only; it is kept in ._python
echo --------------------------------------------------------------
set "PYV=3.12.10"
if not exist "._python" mkdir "._python"

call :dl "https://www.python.org/ftp/python/%PYV%/python-%PYV%-embed-amd64.zip" "python-embed.zip" || goto :no_net
tar -xf "python-embed.zip" -C "._python" || goto :tar_fail
del "python-embed.zip"

rem the portable Python blocks external packages: allow them
> "._python\python312._pth" (
  echo python312.zip
  echo .
  echo Lib\site-packages
  echo import site
)

call :dl "https://bootstrap.pypa.io/get-pip.py" "get-pip.py" || goto :no_net
"._python\python.exe" get-pip.py >nul 2>nul
del "get-pip.py"

echo Installing PyQt6 and Pillow, this may take a minute...
"._python\python.exe" -m pip install --only-binary=:all: PyQt6 Pillow
if errorlevel 1 goto :pip_fail

"._python\python.exe" -c "import PyQt6.QtWidgets, PyQt6.QtGui, PIL" >nul 2>nul
if errorlevel 1 goto :pip_fail

:run
start "" /min "._python\pythonw.exe" epsilon.py
exit /b 0

rem ================================================== download with curl, then PowerShell as fallback
:dl
curl -L -sS -o "%~2" "%~1" >nul 2>nul
if exist "%~2" exit /b 0
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%~1' -OutFile '%~2'" >nul 2>nul
if exist "%~2" exit /b 0
exit /b 1

:no_net
echo.
echo  [ERROR] Could not download Python. Check your internet connection
echo  (or the work/proxy network) and run start.bat again.
pause
exit /b 1

:tar_fail
echo.
echo  [ERROR] Could not extract the downloaded Python. This machine
echo  needs Windows 10 1803 or newer, or extract python-embed.zip
echo  manually into .\_python and repeat the step.
pause
exit /b 1

:pip_fail
echo.
echo  [ERROR] PyQt6/Pillow could not be installed. Common causes:
echo   - Antivirus/proxy blocking pip.
echo   - Missing "Microsoft Visual C++ Redistributable x64":
echo     https://aka.ms/vs/17/release/vc_redist.x64.exe
echo Install it and run start.bat again.
pause
exit /b 1
