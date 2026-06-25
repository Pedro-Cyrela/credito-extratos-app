# Análise de Crédito por Extratos Bancários

Aplicação para análise de renda e crédito a partir de extratos bancários em PDF.

## O que o sistema faz

- Processa um ou vários extratos bancários em PDF.
- Identifica banco, titular, agência, conta e período quando essas informações estão disponíveis.
- Extrai datas, descrições, créditos, débitos, valores e saldos de diferentes layouts.
- Usa parsers específicos para bancos conhecidos e alternativas genéricas para outros formatos.
- Aplica OCR em documentos sem texto ou tabela selecionável suficiente.
- Detecta extratos em moeda estrangeira e permite conversão pela cotação PTAX.
- Classifica movimentações como consideradas, desconsideradas ou pendentes de revisão.
- Permite corrigir manualmente classificações e dados extraídos.
- Desconsidera aplicações, resgates, rendimentos e outras movimentações que não representam renda.
- Consolida os créditos considerados em um resumo mensal.
- Calcula métricas gerais para apoiar a análise de crédito.
- Exporta uma planilha Excel auditável com movimentações, resumo, regras e erros.
- Gera um relatório final em PDF.

## Bancos com tratamento específico

- Banco do Brasil
- Bank of America
- Bradesco
- C6 Bank
- Eagle
- Inter
- Nubank
- Santander
- Wise

Outros layouts podem ser processados pelos mecanismos genéricos de leitura de tabelas e texto.

## Execução e deploy

- Use Python 3.11 ou 3.12. O pacote `rapidocr-onnxruntime`, usado no OCR, ainda não é compatível com Python 3.13.
- No Streamlit Community Cloud, mantenha a versão do Python do app em 3.12 ou 3.11 nas configurações avançadas do deploy.

## Tratamento dos dados

- Os documentos são processados durante a sessão.
- O sistema não utiliza banco de dados para armazenar os extratos.
- A consulta externa de PTAX envia somente moeda e data, sem dados do titular ou das transações.
- Os resultados devem ser revisados pelo analista, principalmente quando houver uso de OCR ou indicação de pendência.

Consulte `SECURITY.md` para as regras de segurança e tratamento de dados.
