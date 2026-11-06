@echo off
rem Abre la pagina web interna (reporte del dia, tablero, historial y guia).
pushd "%~dp0"
".venv\Scripts\python.exe" -m calidad web --abrir
popd
