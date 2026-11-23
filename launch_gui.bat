@echo off
setlocal

set "PYTHONW="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    goto :launch
)
if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" (
    set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
    goto :launch
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" (
    set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    goto :launch
)

for /f "delims=" %%I in ('where pyw 2^>nul') do (
    set "PYTHONW=%%I"
    goto :launch
)

for /f "delims=" %%I in ('where pythonw 2^>nul') do (
    echo "%%I" | findstr /i /c:"WindowsApps" >nul
    if errorlevel 1 (
        set "PYTHONW=%%I"
        goto :launch
    )
)

echo Python 3 (pythonw.exe) not found.
echo Please install Python 3 and Pillow (pip install pillow).
pause
exit /b 1

:launch
start "" "%PYTHONW%" "%~dp0gui.py"
