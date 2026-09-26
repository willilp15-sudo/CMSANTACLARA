@echo off
setlocal
cd /d "%~dp0"
set ERR=0
for %%F in (nextsys.exe administracion.pbd configuracion_inicial.pbd consultas.pbd contabilidad.pbd facturas.pbd fondo_fijo.pbd importadora.pbd informes.pbd informes_base.pbd modelos.pbd notificaciones.pbd punto_venta.pbd restaurant.pbd sanatorio.pbd transp.pbd Sifen.dll bd.ini) do (
  if not exist "%%F" (
    echo [FALTA] %%F
    set ERR=1
  ) else (
    echo [OK] %%F
  )
)
if not exist "sifen\santaclara.cer" echo [AVISO] No se encuentra sifen\santaclara.cer
if not exist "imagen\SANTACLARA.jpg" echo [AVISO] No se encuentra imagen\SANTACLARA.jpg
if "%ERR%"=="0" (echo. & echo ESTRUCTURA PRINCIPAL: OK) else (echo. & echo ESTRUCTURA PRINCIPAL: INCOMPLETA)
pause
exit /b %ERR%
