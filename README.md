# Analise de Credito por Extratos Bancarios

Aplicacao Streamlit para analise de renda e credito a partir de extratos
bancarios em PDF. O projeto foi pensado para uso interno/local, com processamento
em `localhost`, exportacao auditavel em Excel e apoio a revisao manual do
analista.

## O que o app faz

- Le extratos bancarios em PDF e extrai movimentacoes de credito/debito.
- Identifica dados de cabecalho como titular, banco, conta e periodo quando o
  layout permite.
- Usa parsers especificos para bancos conhecidos e fallbacks genericos para
  layouts tabulares ou textuais.
- Desconsidera automaticamente movimentacoes que nao representam renda, como
  resgates, rendimentos, aplicacoes e investimentos.
- Permite ajustes manuais de classificacao diretamente na interface.
- Calcula resumo mensal e metricas globais de renda.
- Suporta extratos estrangeiros com conversao por PTAX quando o analista informa
  a moeda.
- Exporta uma planilha Excel com dados, resumo, cabecalho, regras aplicadas e
  erros por arquivo.
- Gera relatorio em PDF quando a dependencia `fpdf2` esta disponivel.

## Stack principal

- Python 3.11+
- Streamlit
- pandas
- pdfplumber
- PyMuPDF
- rapidocr-onnxruntime
- openpyxl
- rapidfuzz
- fpdf2
- pytest
- ruff

## Estrutura do repositorio

```text
.
|-- README.md
|-- requirements.txt              # aponta para credito-extratos-app/requirements.txt
|-- runtime.txt                   # runtime usado por ambientes tipo Streamlit Cloud
|-- packages.txt                  # pacotes Linux necessarios para OCR/PyMuPDF
|-- .devcontainer/
`-- credito-extratos-app/
    |-- app.py                    # entrada Streamlit
    |-- run_local.ps1             # launcher local para Windows
    |-- Executar Aplicativo.py     # launcher alternativo
    |-- pyproject.toml             # metadados, pytest e ruff
    |-- requirements.txt           # dependencias minimas
    |-- requirements-lock.txt      # dependencias travadas com hashes
    |-- README.md                  # README legado da subpasta do app
    |-- SECURITY.md                # notas de seguranca e LGPD
    |-- CHANGELOG.md
    |-- .streamlit/config.toml
    |-- config/
    |   |-- banks.json
    |   |-- column_aliases.json
    |   `-- exclusion_terms_default.json
    |-- src/
    |   |-- analysis_engine.py
    |   |-- export_excel.py
    |   |-- fx_processing.py
    |   |-- fx_ptax.py
    |   |-- manual_overrides.py
    |   |-- parsers/
    |   `-- ...
    `-- tests/
```

## Bancos e layouts

O motor tem parsers dedicados para:

- Wise
- Bradesco
- Banco do Brasil
- Eagle
- Inter
- Nubank
- C6 Bank
- Bank of America
- Santander

Alem disso, existem parsers genericos para extratos em tabela ou texto. O
catalogo em `credito-extratos-app/config/banks.json` tambem lista aliases de
outros bancos para ajudar na identificacao de cabecalho.

## Como rodar localmente

### 1. Criar e ativar ambiente virtual

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Instalar dependencias

Para desenvolvimento:

```powershell
pip install -r requirements.txt
pip install -e ".\credito-extratos-app[dev]"
```

Para uma instalacao mais reprodutivel, usando o lockfile do app:

```powershell
cd credito-extratos-app
pip install --require-hashes -r requirements-lock.txt
```

### 3. Executar o Streamlit

Opcao recomendada no Windows:

```powershell
cd credito-extratos-app
.\run_local.ps1
```

Opcao direta:

```powershell
cd credito-extratos-app
streamlit run app.py
```

Depois acesse:

```text
http://localhost:8501
```

## Fluxo de uso

1. Abra o app em `localhost`.
2. Envie um ou mais PDFs de extratos bancarios.
3. Revise os dados de cabecalho e as movimentacoes extraidas.
4. Informe a moeda quando o app detectar ou quando o analista marcar que o
   extrato e estrangeiro.
5. Ajuste manualmente linhas ambiguas ou classificacoes incorretas.
6. Baixe o Excel de auditoria e, se necessario, o relatorio PDF.
7. Ao terminar, use a opcao de encerrar analise/limpar sessao na sidebar.

## Testes e qualidade

Execute a partir da pasta do app:

```powershell
cd credito-extratos-app
pytest -q
ruff check .
```

O `pyproject.toml` configura:

- `pytest` com `tests/` como suite principal.
- `ruff` para lint, imports, pyupgrade e regras especificas do projeto.
- Python alvo `3.11`.

## Configuracoes importantes

- `.streamlit/config.toml`: define execucao headless, `localhost`, porta `8501`
  e desativa telemetria do navegador.
- `config/banks.json`: aliases e nomes exibidos para bancos.
- `config/column_aliases.json`: variacoes de nomes de colunas reconhecidas.
- `config/exclusion_terms_default.json`: termos padrao para exclusao de
  movimentacoes que nao devem contar como renda.
- `requirements-lock.txt`: dependencias travadas para instalacao reprodutivel.

## Seguranca e LGPD

O app manipula extratos com dados pessoais e financeiros. Pontos principais:

- PDFs enviados ficam em memoria durante a sessao Streamlit.
- O app nao usa banco de dados.
- A chamada externa usada para PTAX consulta apenas moeda e data na API do BCB,
  sem enviar dados do titular ou transacoes.
- Arquivos Excel/PDF exportados passam a ser responsabilidade do analista e
  devem seguir a politica interna de retencao e descarte.
- Mais detalhes estao em `credito-extratos-app/SECURITY.md`.

## Manutencao

Para adicionar suporte a um novo banco:

1. Criar ou ajustar parser em `credito-extratos-app/src/parsers/`.
2. Registrar o parser em `credito-extratos-app/src/parsers/__init__.py`.
3. Atualizar aliases em `credito-extratos-app/config/banks.json`, se aplicavel.
4. Adicionar testes cobrindo deteccao, cabecalho e transacoes.
5. Rodar `pytest -q` e `ruff check .`.

Para atualizar dependencias:

```powershell
cd credito-extratos-app
pip install pip-tools
pip-compile --generate-hashes -o requirements-lock.txt pyproject.toml
```

## Observacoes

- O app funciona melhor com PDFs pesquisaveis ou com tabelas bem estruturadas.
- PDFs escaneados acionam OCR como fallback; os resultados devem ser revisados
  com mais cuidado.
- O projeto atual esta organizado com a raiz do repositorio fora da pasta do app;
  por isso a maioria dos comandos de desenvolvimento roda dentro de
  `credito-extratos-app`.
