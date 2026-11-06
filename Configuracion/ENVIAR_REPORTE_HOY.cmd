@echo off
rem Sube las respuestas nuevas a la nube, pide los consejos a la IA, genera el reporte de hoy y lo deja para
rem enviar por correo (una sola vez por dia). La tarea programada lo ejecuta con /auto para no esperar una tecla.
if not exist "%USERPROFILE%\CalidadKaravansayNube" mkdir "%USERPROFILE%\CalidadKaravansayNube"
set REGISTRO=%USERPROFILE%\CalidadKaravansayNube\registro.txt
rem Este archivo vive en Configuracion\; el proyecto es la carpeta de arriba.
pushd "%~dp0.."
echo ===== %DATE% %TIME% reporte >> "%REGISTRO%"
".venv\Scripts\python.exe" -m calidad diario --enviar >> "%REGISTRO%" 2>&1
popd
if /i not "%~1"=="/auto" (
  echo Listo. El detalle queda en %REGISTRO%
  pause
)
