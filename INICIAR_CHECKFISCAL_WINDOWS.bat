@echo off
setlocal
cd /d "%~dp0"
title CheckFiscal 1.41

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON=py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON=python"
  ) else (
    echo.
    echo O Python nao foi encontrado neste computador.
    echo Instale o Python 3.11 ou superior e marque "Add Python to PATH".
    echo.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparando o CheckFiscal pela primeira vez...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :erro
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.checkfiscal-deps-1.41" (
  echo Instalando os componentes da versao 1.41...
  python -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 goto :erro
  type nul > ".venv\.checkfiscal-deps-1.41"
)

if not exist "%LOCALAPPDATA%\CheckFiscal" mkdir "%LOCALAPPDATA%\CheckFiscal"
set "CHECKFISCAL_DATA_DIR=%LOCALAPPDATA%\CheckFiscal"

if exist "checkfiscal_local.db" if not exist "%CHECKFISCAL_DATA_DIR%\checkfiscal.db" (
  echo Migrando o banco local da versao anterior...
  copy /Y "checkfiscal_local.db" "%CHECKFISCAL_DATA_DIR%\checkfiscal.db" >nul
)

echo.
echo CheckFiscal 1.41 iniciado em http://127.0.0.1:8141
echo Os dados ficam em: %CHECKFISCAL_DATA_DIR%
echo Para encerrar, feche esta janela.
echo.

start "" http://127.0.0.1:8141
python -m uvicorn app:app --host 127.0.0.1 --port 8141 --no-access-log
exit /b 0

:erro
echo.
echo Nao foi possivel iniciar o CheckFiscal.
echo Confira a conexao com a internet e a instalacao do Python.
echo.
pause
exit /b 1
