@echo off
rem Puente: lee el Excel del flujo de Power Automate y sube a la nube solo las respuestas nuevas o cambiadas.
rem Si hubo respuestas nuevas, pide en el mismo momento los consejos de la IA para los casos nuevos (--ia).
rem Si el Excel no cambio, no se conecta a la nube. La tarea programada lo ejecuta cada 30 minutos con /auto.
if not exist "%USERPROFILE%\CalidadKaravansayNube" mkdir "%USERPROFILE%\CalidadKaravansayNube"
set REGISTRO=%USERPROFILE%\CalidadKaravansayNube\registro.txt
pushd "%~dp0.."
echo ===== %DATE% %TIME% subida >> "%REGISTRO%"
".venv\Scripts\python.exe" -m calidad sincronizar --ia >> "%REGISTRO%" 2>&1
popd
if /i not "%~1"=="/auto" (
  echo Listo. El detalle queda en %REGISTRO%
  pause
)
