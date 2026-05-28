# Análise de Extratos Bancários em PDF

## O que esse projeto faz
 le diferentes layouts de extrato;
- identifica titular, banco, conta e periodo;
- localiza colunas como `data`, `descricao`, `credito`, `debito` e `valor`;
- interpreta PDFs com coluna unica de valor usando sinais `+` e `-`;
- desconsidera automaticamente resgates, rendimentos, aplicacoes e investimentos;
- aceita regras manuais informadas na interface;
- gera resumo mensal e exportacao auditavel em Excel.

## Stack
streamlit>=1.43.0
pdfplumber>=0.11.0
pandas>=2.2.0
openpyxl>=3.1.0
rapidfuzz>=3.9.0
Unidecode>=1.3.8
python-dateutil>=2.9.0
numpy>=2.0.0
fpdf2>=2.7.9

## Comandos

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

## Arquivos de entrada esperados
Documento PDF

## Convenções

## Cuidados
-Criando novas funções não apagar existentes que funcionam em outros bancos ou situações.

## O que está em andamento
-Aplicativo consegue ler extratos de vários bancos que fui cadastrando durante os testes
-Tenta ler quando não identifica o banco identificando a estrutura de tabelas