@echo off
rem Crea (o reemplaza) las dos tareas de Windows del PC puente:
rem   1. Cada 30 minutos, de 5:00 a 12:00: subir respuestas nuevas a la nube y, si hubo, pedir los
rem      consejos de la IA para los casos nuevos (automatico, sin boton).
rem   2. Reporte diario por correo de lunes a sabado a la hora elegida (reutiliza los consejos ya guardados).
rem El equipo debe estar encendido y con la sesion iniciada (OneDrive debe estar sincronizando).
set /p HORA="Hora del reporte diario (HH:MM, Enter = 11:00): "
if "%HORA%"=="" set HORA=11:00
schtasks /Create /F /TN "Calidad NUBE - subir datos" /SC DAILY /ST 05:00 /RI 30 /DU 07:00 /TR "cmd /c \"%~dp0SUBIR_DATOS.cmd\" /auto"
schtasks /Create /F /TN "Calidad NUBE - reporte diario" /SC WEEKLY /D MON,TUE,WED,THU,FRI,SAT /ST %HORA% /TR "cmd /c \"%~dp0ENVIAR_REPORTE_HOY.cmd\" /auto"
rem Windows crea las tareas con "no iniciar con bateria": en un portatil sin cargador las rechaza (error 0x800710E0).
rem Se permite la bateria y, si el equipo estaba apagado a la hora, la tarea corre apenas se encienda.
powershell -NoProfile -Command "foreach ($n in 'Calidad NUBE - subir datos','Calidad NUBE - reporte diario') { Set-ScheduledTask -TaskName $n -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew) | Out-Null }"
echo.
echo Para quitarlas:
echo   schtasks /Delete /TN "Calidad NUBE - subir datos" /F
echo   schtasks /Delete /TN "Calidad NUBE - reporte diario" /F
pause
