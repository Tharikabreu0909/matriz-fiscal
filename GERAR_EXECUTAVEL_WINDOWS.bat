@echo off
setlocal
cd /d "%~dp0"

echo Este script deve ser executado em um computador Windows com Python.
where py >nul 2>nul || goto :sem_python

py -m venv .build-venv
call .build-venv\Scripts\activate.bat
python -m pip install -q -r requirements-build.txt
pyinstaller --noconfirm checkfiscal.spec

echo.
echo Executavel gerado na pasta dist\CheckFiscal.
pause
exit /b 0

:sem_python
echo Python nao encontrado.
pause
exit /b 1
