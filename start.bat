@echo off
REM AdaptiBoard - one-command start for the BOARD laptop (Windows).
cd /d "%~dp0"
if not exist .venv (
  echo Creating Python environment...
  py -3 -m venv .venv
)
.venv\Scripts\pip install -q -r server\requirements.txt
if not exist web\dist\index.html (
  echo Building the web app - first run only...
  pushd web
  call npm install --no-audit --no-fund
  call npm run build
  popd
)
.venv\Scripts\python -u server\main.py %*
