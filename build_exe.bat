@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "MizushioDesktopPet" ^
    --icon "assets\pet.ico" ^
    --add-data "assets\character_spritesheet.png;assets" ^
    --add-data "assets\character_spritesheet_dark_green.png;assets" ^
    --add-data "assets\sprite_manifest.json;assets" ^
    main.py
if errorlevel 1 goto :error

if exist "desktop_pet.private.json" (
    copy /Y "desktop_pet.private.json" "dist\desktop_pet.private.json" >nul
)
if exist "dist\plugins" rmdir /S /Q "dist\plugins"
if exist "dist\THIRD_PARTY_NOTICES.md" del /Q "dist\THIRD_PARTY_NOTICES.md"
echo.
echo 打包完成：dist\MizushioDesktopPet.exe
pause
exit /b 0

:error
echo.
echo 打包失败。请查看上方错误信息。
pause
exit /b 1
