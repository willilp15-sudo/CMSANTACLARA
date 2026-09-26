@echo off
setlocal
cd /d "%~dp0"
title Santa Clara ERP - Centro Medico Santa Clara / Grupo Santa Clara S.A.
if not exist "nextsys.exe" (
  echo ERROR: No se encuentra nextsys.exe en %CD%
  pause
  exit /b 1
)
start "Santa Clara ERP" /D "%CD%" "nextsys.exe"
endlocal
