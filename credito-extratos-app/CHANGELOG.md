# Changelog

## v1.0.0 — Profissionalização + distribuição standalone

### Refatoração técnica

- **Parsers por banco**: `transaction_parser.py` (1778 linhas) virou fachada
  de 36 linhas; lógica vive em `src/parsers/<banco>.py` (BB, Bradesco,
  Inter, Wise, Eagle, C6, Nubank, BoA, genéricos). Cada parser implementa
  `BankParser` Protocol e é tentado por um registry ordenado em
  `src/parsers/__init__.py`.
- **Logging estruturado** via `src/logging_config.py` em todos os módulos.
  Zero PII nos logs: só parser, contagens, status, exceções.
- **Tratamento de erro por arquivo**: `analyze_uploaded_files` envolve
  leitura/cabeçalho/transações em try/except separados. Erros viram aba
  `Erros` no Excel + warning na UI; demais arquivos seguem.
- **Versionamento** (`src/__init__.py`): `__version__ = "1.0.0"` +
  `get_git_commit()` (lê `.git/HEAD` sem precisar do `git` instalado).
  Estampado no topbar, Excel (`Cabecalho`) e rodapé do PDF.
- **LGPD**: `SECURITY.md` documenta retenção; botão "Encerrar análise /
  limpar sessão" na sidebar zera `st.session_state`.
- **Conflito de parsers**: registry agora roda **todos** os detectores e
  loga warning quando >1 casa com o mesmo PDF (primeiro continua ganhando).
- **Catálogo de bancos** em `config/banks.json` (16 bancos, aliases com e
  sem acento, ordenados por tamanho para evitar prefixos curtos vencerem
  nomes completos).
- **Split `app.py`**: FX/BRL → `src/fx_processing.py` (testável). +7 testes
  novos. Total: **43/43 passing**.
- **Qualidade**: `pyproject.toml` + `ruff` (47 issues → 0). Lockfile com
  SHA256. CI em `.github/workflows/ci.yml` (pytest + ruff em 3.11 e 3.13).

### Distribuição standalone

- **`packaging/build_standalone.ps1`** gera `dist\Analise_Extratos_v<ver>.zip`
  (~109 MB compactado, ~319 MB descompactado) com Python 3.11 embeddable +
  deps pré-instaladas. Analista descompacta e clica em `Executar.bat` —
  zero instalação, zero admin.
- **`packaging/launcher.bat`** abre `http://localhost:8501` no navegador,
  loga em `logs\app-<timestamp>.log`.
- **`packaging/LEIA-ME.txt`** guia do analista (LGPD, antivírus,
  troubleshooting).

## Como testar antes de distribuir

1. **Suíte**: `python -m pytest -q` (esperado: 43 passed) e `ruff check .`
   (esperado: All checks passed).
2. **Build limpo**: `.\packaging\build_standalone.ps1` (ou `-SkipDownload`
   se já tem cache em `dist\_cache\`).
3. **Smoke no embedded**:
   `dist\Analise_Extratos_v1.0.0\python\python.exe -c "import streamlit, pandas, pdfplumber, openpyxl, rapidfuzz; print('ok')"`.
4. **Teste em máquina limpa** (sem Python instalado): copie o ZIP para
   um colega ou VM, extraia, clique em `Executar.bat`, processe um PDF
   de cada banco que você já validou no plantão. Confirme que o Excel
   tem a aba `Cabecalho` com `versao_app` preenchido.
5. **SHA256 para o TI**:
   `Get-FileHash dist\Analise_Extratos_v1.0.0.zip -Algorithm SHA256`.

## Próximos passos

- **Curto prazo**: pedir whitelist do Defender por SHA256; distribuir o
  ZIP via SharePoint corporativo (não email — gateway pode bloquear .bat
  dentro do ZIP); lembrar analistas de "Desbloquear" o ZIP nas
  Propriedades antes de extrair (mark-of-the-web).
- **Médio prazo**: regerar o lockfile com `python3.11 -m piptools compile`
  (o atual saiu com 3.10 disponível); criar `tests/parsers/` com casos
  específicos por banco; expandir o catálogo `banks.json` conforme novos
  layouts aparecem nos plantões.
- **Longo prazo (Fase 2 plena)**: hospedar em servidor interno com SSO
  Entra ID para destravar atualização centralizada e auditoria de uso;
  considerar OCR opcional (`ocrmypdf`) para PDFs escaneados.
