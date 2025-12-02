@echo off
REM Windows batch script to set up .env file easily
REM This script should be run from the project root directory

cd /d "%~dp0.."

echo ============================================================
echo          OpenAI API Key Setup for Windows
echo ============================================================
echo.

REM Check if .env already exists
if exist .env (
    echo [!] .env file already exists!
    echo.
    set /p OVERWRITE="Do you want to overwrite it? (y/n): "
    if /i not "%OVERWRITE%"=="y" (
        echo Setup cancelled.
        pause
        exit /b
    )
)

REM Check if env.template exists
if not exist env.template (
    echo [ERROR] env.template not found!
    echo Please make sure you're running this from the project root directory.
    echo Current directory: %CD%
    pause
    exit /b 1
)

REM Copy template to .env
echo [1/3] Creating .env file...
copy env.template .env >nul
echo       Done!
echo.

REM Prompt for API key
echo [2/3] Please enter your OpenAI API key:
echo       (Get it from: https://platform.openai.com/api-keys)
echo.
set /p API_KEY="      API Key: "

if "%API_KEY%"=="" (
    echo.
    echo [WARNING] No API key entered. You'll need to edit .env manually.
    echo           Open .env and add: OPENAI_API_KEY=your-key-here
) else (
    echo.
    echo [3/3] Saving API key to .env...
    echo OPENAI_API_KEY=%API_KEY%>.env
    echo       Done!
)

echo.
echo ============================================================
echo                    Setup Complete!
echo ============================================================
echo.
echo Your .env file has been created.
echo.
echo Next steps:
echo   1. Install dependencies: pip install -r requirements.txt
echo   2. Test your setup:      python test_api_key.py
echo   3. Run the pipeline:     python main.py
echo.
echo IMPORTANT: Never commit .env to git! (it's already in .gitignore)
echo.
pause

