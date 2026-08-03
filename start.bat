@echo off
REM ============================================================
REM  Video -> Animation : one-click launcher (Windows)
REM  Double-click this file to start the app and open the tool.
REM ============================================================

REM Move to the folder this file lives in (so paths work anywhere).
cd /d "%~dp0"

echo.
echo   Starting the Video to Animation app...
echo   Keep this window open while you use the tool.
echo   Close it (or press Ctrl+C) when you are done.
echo.

REM Open the tool in the default browser a few seconds after start,
REM so the server has time to come up.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:5000/animator"

REM Prefer the Python 3.11 launcher; fall back to plain python.
py -3.11 app.py
if errorlevel 1 (
    echo.
    echo   'py -3.11' did not work, trying 'python'...
    python app.py
)

echo.
echo   The app has stopped.
pause
