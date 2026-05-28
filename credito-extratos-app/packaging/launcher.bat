@echo off
REM ============================================================================
REM  Analise de Credito por Extratos - Launcher
REM ----------------------------------------------------------------------------
REM  Roda 100%% local. Nao envia dados para a Internet
REM  (a unica chamada externa e a cotacao PTAX do BCB).
REM
REM  Como funciona:
REM    1) Usa o Python embutido na subpasta python\
REM    2) Sobe o Streamlit em http://localhost:8501
REM    3) Abre o navegador padrao na pagina
REM
REM  Logs ficam em logs\app-<data>.log
REM ============================================================================
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM -- Diretorio do launcher (com barra final) ---------------------------------
set "HERE=%~dp0"
cd /d "%HERE%"

REM -- Caminhos ----------------------------------------------------------------
set "PYTHON=%HERE%python\python.exe"
set "APP=%HERE%app\app.py"
set "LOGDIR=%HERE%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM Timestamp YYYY-MM-DD_HH-MM para o nome do log
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value ^| find "="') do set "DT=%%I"
set "STAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%-%DT:~10,2%"
set "LOGFILE=%LOGDIR%\app-%STAMP%.log"

REM -- Sanity check ------------------------------------------------------------
if not exist "%PYTHON%" (
    echo.
    echo [ERRO] Python embarcado nao encontrado em:
    echo        %PYTHON%
    echo.
    echo Provavelmente o ZIP foi extraido errado. Extraia novamente
    echo mantendo a estrutura de pastas e tente outra vez.
    pause
    exit /b 1
)
if not exist "%APP%" (
    echo.
    echo [ERRO] Arquivo do app nao encontrado em:
    echo        %APP%
    pause
    exit /b 1
)

REM -- Banner ------------------------------------------------------------------
echo.
echo ============================================================
echo   Analise de Credito por Extratos
echo   Iniciando localmente em http://localhost:8501
echo ============================================================
echo.
echo   Para encerrar: feche esta janela ou pressione Ctrl+C.
echo   Logs: %LOGFILE%
echo.

REM -- Abre o navegador apos um pequeno delay (em background) ------------------
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:8501"

REM -- Sobe o Streamlit usando o python embarcado ------------------------------
REM  Tee manual: stderr no console + tudo no arquivo de log
"%PYTHON%" -m streamlit run "%APP%" ^
    --server.address localhost ^
    --server.port 8501 ^
    --server.headless true ^
    --browser.gatherUsageStats false ^
    1>>"%LOGFILE%" 2>&1

set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [ERRO] O Streamlit terminou com codigo %RC%. Detalhes em:
    echo        %LOGFILE%
    pause
)

endlocal
