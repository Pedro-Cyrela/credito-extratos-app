# Analise de Credito por Extratos Bancarios

Aplicacao Streamlit para analise de renda/credito a partir de extratos bancarios em PDF, preparada para uso local em `localhost`.

## O que o app faz

- le diferentes layouts de extrato;
- identifica titular, banco, conta e periodo;
- localiza colunas como `data`, `descricao`, `credito`, `debito` e `valor`;
- interpreta PDFs com coluna unica de valor usando sinais `+` e `-`;
- desconsidera automaticamente resgates, rendimentos, aplicacoes e investimentos;
- aceita regras manuais informadas na interface;
- gera resumo mensal e exportacao auditavel em Excel.

## Execucao local

### 1. Instale as dependencias

```bash
pip install -r requirements.txt
```

### 2. Rode o app

Opcao direta:

```bash
streamlit run app.py
```

Opcao PowerShell no Windows:

```powershell
.\run_local.ps1
```

O projeto inclui `.streamlit/config.toml`, deixando o Streamlit configurado para:

- subir em `localhost`;
- usar a porta `8501`;
- desabilitar coleta de telemetria do navegador.

Abra no navegador:

```text
http://localhost:8501
```

## Estrutura

```text
credito-extratos-app/
|-- .streamlit/
|   `-- config.toml
|-- app.py
|-- run_local.ps1
|-- requirements.txt
|-- README.md
|-- config/
|   |-- column_aliases.json
|   `-- exclusion_terms_default.json
|-- src/
`-- tests/
```

## Observacoes

- Nao ha dependencia de Streamlit Community Cloud para executar o app.
- Nao e necessario publicar em GitHub para uso local.
- O motor funciona melhor com PDFs pesquisaveis/tabulares.
- PDFs totalmente escaneados ainda podem exigir OCR em evolucao futura.
