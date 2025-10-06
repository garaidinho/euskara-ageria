@echo off
setlocal
chcp 65001 >nul
title Euskara Ageria - Sync fotos (simple)

set "BRANCH=main"
set "PHOTOS_DIR=static\photos"

echo ====================================================
echo   Euskara Ageria - Sincronizando fotos con GitHub
echo   Carpeta del script: %~dp0
echo ====================================================
echo.

cd /d "%~dp0" || (echo [ERROR] No puedo entrar en la carpeta del script & pause & exit /b 1)
where git >nul 2>&1 || (echo [ERROR] Git no esta en PATH & pause & exit /b 1)
git rev-parse --is-inside-work-tree >nul 2>&1 || (echo [ERROR] No es un repo Git & pause & exit /b 1)

REM 1) Preparar imágenes (altas/cambios/borrados)
for /r "%PHOTOS_DIR%" %%F in (*.jpg)  do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.jpeg) do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.png)  do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.webp) do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.JPG)  do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.JPEG) do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.PNG)  do git add -f "%%F" >nul 2>&1
for /r "%PHOTOS_DIR%" %%F in (*.WEBP) do git add -f "%%F" >nul 2>&1
git add -A "%PHOTOS_DIR%" >nul 2>&1

REM 2) Commit solo si hay algo staged
git diff --cached --quiet
if errorlevel 1 (
  git config --get user.name  >nul || git config user.name  "Euskara Ageria"
  git config --get user.email >nul || git config user.email "no-reply@local"
  git commit -m "Actualiza fotos" || (echo [ERROR] Commit fallido & pause & exit /b 1)
) else (
  echo [INFO] No hay cambios nuevos en %PHOTOS_DIR%.
)

REM 3) Pull (rebase) y 4) Push SIEMPRE
git pull --rebase --autostash origin "%BRANCH%" || (echo [ERROR] Pull --rebase fallo & pause & exit /b 1)
git push origin "%BRANCH%" || (echo [ERROR] Push fallido & pause & exit /b 1)

echo.
echo [OK] GitHub actualizado.
echo.
pause
