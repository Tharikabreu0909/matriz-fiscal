@echo off
setlocal
cd /d "%~dp0"
title CheckFiscal 1.45

rem Prefer a supported Python version. Python 3.14+ is not currently used for this build.
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.13 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3.13"
  if not defined PYTHON_CMD (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.12"
  )
  if not defined PYTHON_CMD (
    py -3.11 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
  )
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  echo.
  echo O CheckFiscal 1.45 precisa do Python 3.11, 3.12 ou 3.13 de 64 bits.
  echo Python 3.14/3.15 nao e usado nesta versao porque algumas dependencias ainda podem falhar nessas versoes.
  echo Instale o Python 3.13 em: https://www.python.org/downloads/windows/
  echo Durante a instalacao, marque "Add Python to PATH".
  echo Voce pode manter o Python 3.15 instalado; os dois podem coexistir.
  echo Depois execute este arquivo novamente.
  echo.
  pause
  exit /b 1
)

rem Recreate only the disposable virtual environment if it was made with an unsupported Python.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo O ambiente virtual anterior usa uma versao de Python incompatível.
    echo Recriando apenas o ambiente virtual; seus dados ficam em %%LOCALAPPDATA%%\CheckFiscal.
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparando o ambiente do CheckFiscal 1.45...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :erro
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :erro

if not exist ".venv\.checkfiscal-deps-1.45" (
  echo Instalando os componentes da versao 1.45...
  python -m pip install --upgrade pip
  if errorlevel 1 goto :erro
  python -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :erro
  type nul > ".venv\.checkfiscal-deps-1.45"
)

if not exist "%LOCALAPPDATA%\CheckFiscal" mkdir "%LOCALAPPDATA%\CheckFiscal"
set "CHECKFISCAL_DATA_DIR=%LOCALAPPDATA%\CheckFiscal"

if exist "checkfiscal_local.db" if not exist "%CHECKFISCAL_DATA_DIR%\checkfiscal.db" (
  echo Migrando o banco local da versao anterior...
  copy /Y "checkfiscal_local.db" "%CHECKFISCAL_DATA_DIR%\checkfiscal.db" >nul
)

echo.
echo CheckFiscal 1.45 iniciado em http://127.0.0.1:8145
echo Os dados ficam em: %CHECKFISCAL_DATA_DIR%
echo Para encerrar, feche esta janela.
echo.

start "" http://127.0.0.1:8145
python -m uvicorn app:app --host 127.0.0.1 --port 8145 --no-access-log
exit /b 0

:erro
echo.
echo Nao foi possivel iniciar o CheckFiscal 1.45.
echo Veja a mensagem de erro acima. Se o Python nao for compativel, instale o Python 3.13 de 64 bits.
echo Seus dados locais ficam em %%LOCALAPPDATA%%\CheckFiscal e nao devem ser apagados.
echo.
pause
exit /b 1
