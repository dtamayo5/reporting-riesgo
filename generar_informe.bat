@echo off
REM Uso mensual: procesa el archivo de posiciones mas reciente de la carpeta entrada.
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat goto sin_instalar
call venv\Scripts\activate.bat
python generar_reporte.py %*
if errorlevel 1 goto fallo
start "" "%~dp0salidas"
pause
exit /b 0

:sin_instalar
echo Primero ejecute instalar.bat (doble clic).
pause
exit /b 1

:fallo
echo.
echo No se genero el informe. Lea el mensaje de arriba.
pause
exit /b 1
