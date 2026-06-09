@echo off
REM ===========================================================================
REM  SEAD 3 Compliance Auditor -- one-click launcher for Windows
REM  Just double-click this file. It sets everything up the first time, then
REM  starts the app and opens it in your browser.
REM ===========================================================================

REM Always run from this script's own folder, no matter where it's launched.
cd /d "%~dp0"

echo ===========================================================
echo   SEAD 3 Compliance Auditor
echo ===========================================================
echo.

REM --- 1. Is Python installed? ----------------------------------------------
py --version >nul 2>&1
if errorlevel 1 (
    echo [PROBLEM] Python isn't installed, or wasn't added to PATH.
    echo.
    echo   Fix: download it from  https://www.python.org/downloads/
    echo   During install, CHECK the box "Add python.exe to PATH".
    echo   Then double-click this file again.
    echo.
    pause
    exit /b 1
)

REM --- 2. Create the project sandbox the first time -------------------------
if not exist "venv\Scripts\activate.bat" (
    echo Setting up for the first time. This happens only once...
    py -m venv venv
)

REM --- 3. Turn the sandbox on -----------------------------------------------
call venv\Scripts\activate.bat

REM --- 4. Install libraries if they aren't there yet ------------------------
python -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing required libraries. Expect a wall of text -- that's normal.
    echo This can take a minute or two the first time...
    echo.
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    echo.
)

REM --- 5. Open the browser shortly after the server starts ------------------
REM This launches a tiny helper that waits 4 seconds, then opens your browser,
REM while the main window goes on to run the server.
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"

echo ===========================================================
echo   Starting the app...
echo   Your browser will open to:  http://127.0.0.1:8000
echo.
echo   Leave THIS window open while you use the app.
echo   To STOP the app: click this window and press  Ctrl + C
echo ===========================================================
echo.

REM --- 6. Run the server (this keeps running until you stop it) -------------
python -m uvicorn main:app --reload --port 8000

echo.
echo The app has stopped. You can close this window now.
pause
