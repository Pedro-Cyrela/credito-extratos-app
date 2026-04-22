# Análise de Crédito por Extratos Bancários

Aplicação Streamlit para análise de renda/crédito a partir de extratos bancários em PDF, com foco em:

- leitura flexível de diferentes layouts;
- identificação de titular, banco e conta;
- localização de colunas como **data**, **descrição**, **crédito**, **débito** e **valor**;
- interpretação de PDFs com **coluna única de valor** usando sinais `+` / `-`;
- exclusão automática de **resgates, rendimentos, aplicações e investimentos**;
- regras personalizadas informadas pelo usuário;
- painel de resumo mensal sem foco em gráficos;
- exportação auditável em **Excel**.

## Como executar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy no Streamlit Community Cloud

1. Suba este projeto para um repositório no GitHub.
2. Acesse o Streamlit Community Cloud.
3. Crie um novo app apontando para o repositório.
4. Defina `app.py` como arquivo principal.

## Estrutura

```text
credito-extratos-app/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── config/
│   ├── column_aliases.json
│   └── exclusion_terms_default.json
├── src/
│   ├── __init__.py
│   ├── analysis_engine.py
│   ├── credit_classifier.py
│   ├── exclusion_rules.py
│   ├── export_excel.py
│   ├── header_parser.py
│   ├── monthly_summary.py
│   ├── pdf_reader.py
│   ├── table_extractor.py
│   ├── transaction_parser.py
│   └── utils.py
└── tests/
    ├── test_classifier.py
    ├── test_parser.py
    └── test_rules.py
```

## Observações importantes

- O motor tenta extrair dados de PDFs pesquisáveis / tabulares.
- PDFs totalmente escaneados podem exigir OCR em uma evolução futura.
- O app foi desenhado para ser **útil mesmo em cenários imperfeitos**: quando a classificação não for suficiente, o usuário consegue baixar o Excel detalhado com `data`, `descrição`, `origem identificada`, `valor`, `status`, `motivo`, `titular` e `conta`.

## Próximas evoluções recomendadas

- OCR para PDFs escaneados;
- regras específicas por banco;
- armazenamento de perfis de restrições;
- revisão assistida por nível de confiança;
- relatório PDF institucional.
