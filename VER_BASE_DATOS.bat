@echo off
setlocal
if defined SANTA_CLARA_DATA_DIR (
  set "DATOS=%SANTA_CLARA_DATA_DIR%"
) else (
  set "DATOS=%LOCALAPPDATA%\SantaClaraERP\data"
)
echo Base de datos persistente:
echo %DATOS%\santa_clara_v8.db
echo.
echo Copias de seguridad:
echo %DATOS%\backups
if exist "%DATOS%" explorer "%DATOS%"
pause
