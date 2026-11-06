@echo off
rem Prepara el PC puente. Requiere Python 3.12 o superior instalado.
rem Este archivo vive en Configuracion\; el proyecto es la carpeta de arriba.
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Siguientes pasos (ver README):
echo   .venv\Scripts\python.exe -m calidad clave-bd     (direccion de Neon)
echo   .venv\Scripts\python.exe -m calidad clave-ia     (clave de Gemini)
echo   .venv\Scripts\python.exe -m calidad probar-bd
popd
pause
