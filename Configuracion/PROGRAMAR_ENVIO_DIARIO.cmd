@echo off
rem Crea (o reemplaza) las dos tareas de Windows del PC puente:
rem   1. Subir respuestas nuevas a la nube cada 15 minutos, de 5:00 a 20:00.
rem   2. Reporte diario con IA de lunes a sabado a la hora elegida.
rem El equipo debe estar encendido y con la sesion iniciada (OneDrive debe estar sincronizando).
set /p HORA="Hora del reporte diario (HH:MM, Enter = 11:00): "
if "%HORA%"=="" set HORA=11:00
schtasks /Create /F /TN "Calidad NUBE - subir datos" /SC DAILY /ST 05:00 /RI 15 /DU 15:00 /TR "cmd /c \"%~dp0SUBIR_DATOS.cmd\" /auto"
schtasks /Create /F /TN "Calidad NUBE - reporte diario" /SC WEEKLY /D MON,TUE,WED,THU,FRI,SAT /ST %HORA% /TR "cmd /c \"%~dp0ENVIAR_REPORTE_HOY.cmd\" /auto"
echo.
echo Para quitarlas:
echo   schtasks /Delete /TN "Calidad NUBE - subir datos" /F
echo   schtasks /Delete /TN "Calidad NUBE - reporte diario" /F
pause
