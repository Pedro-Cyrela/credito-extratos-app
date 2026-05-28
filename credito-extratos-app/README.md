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

Para uso em producao (versoes travadas com hashes):

```bash
pip install --require-hashes -r requirements-lock.txt
```

Para desenvolvimento (versoes minimas, sem hash):

```bash
pip install -r requirements.txt
```

Para regenerar o lock apos atualizar `pyproject.toml`:

```bash
pip install pip-tools
pip-compile --generate-hashes -o requirements-lock.txt pyproject.toml
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

## Build standalone (distribuir sem Python instalado)

Para gerar um pacote `.zip` que rode em qualquer maquina Windows sem
Python pre-instalado:

```powershell
.\packaging\build_standalone.ps1
```

O script:

1. baixa Python 3.11 embeddable do python.org (cache em `dist\_cache\`);
2. instala todas as dependencias do `requirements.txt` dentro do embed;
3. copia `app.py`, `src\`, `config\`, `.streamlit\` para a pasta de build;
4. gera `dist\Analise_Extratos_v<versao>.zip`.

Distribuicao: o analista descompacta o ZIP e clica em `Executar.bat`.
Veja `packaging\LEIA-ME.txt` para o guia que vai dentro do ZIP.

Tamanho aproximado: ~80 MB compactado, ~250 MB descompactado.

## Observacoes

- Nao ha dependencia de Streamlit Community Cloud para executar o app.
- Nao e necessario publicar em GitHub para uso local.
- O motor funciona melhor com PDFs pesquisaveis/tabulares.
- PDFs totalmente escaneados ainda podem exigir OCR em evolucao futura.
