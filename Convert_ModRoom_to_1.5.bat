@echo off
setlocal enabledelayedexpansion

title ModRoom to WB 1.5 Mod Converter v1.0
cd /d "%~dp0"

echo ======================================================================
echo                MODROOM TO WB 1.5 MOD CONVERTER v1.0
echo ======================================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto :no_python
goto :run_tool

:no_python
echo [ERROR] Python was not found in your system PATH.
echo Please install Python 3.8 or higher from python.org and check
echo the box "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:run_tool
if "%~1"=="" goto :run_default
python "ModRoom_to_WB_1.5.py" %*
goto :finish

:run_default
python "ModRoom_to_WB_1.5.py"
goto :finish

:finish
echo.
echo Press any key to exit...
pause >nul
exit /b 0
