# Segurança e LGPD — Análise de Crédito por Extratos

Este documento descreve onde dados pessoais e financeiros transitam quando o
aplicativo é executado, por quanto tempo ficam acessíveis e quais são as
responsabilidades do analista que opera a ferramenta.

## Resumo

| Item                          | Onde fica                                  | Persistência                    |
|-------------------------------|--------------------------------------------|---------------------------------|
| PDF enviado pelo analista     | Memória do processo Streamlit              | Até o navegador fechar/limpar   |
| Texto extraído + transações   | `st.session_state` (RAM)                   | Até "Encerrar análise" ou reload |
| Excel exportado               | Pasta Downloads do analista                | Conforme política do analista   |
| PDF exportado                 | Pasta Downloads do analista                | Conforme política do analista   |
| Cotação PTAX (cache)          | Cache em memória do Streamlit              | TTL de 6h ou até reload         |
| Logs do app                   | stderr do processo (terminal/Windows Event)| Conforme rotação do host        |

## O que **não** acontece

- **Nenhum PDF é salvo em disco** pelo app. O upload é mantido apenas como
  bytes em memória, processado por `pdfplumber.open(io.BytesIO(...))` e
  descartado quando a sessão expira.
- **Não há banco de dados.** Nada é gravado em SQLite, Postgres, Redis ou
  qualquer outro armazenamento persistente.
- **Não há chamada externa com PII.** A única chamada de rede do app é à API
  PTAX do BCB (`olinda.bcb.gov.br`) para buscar cotação de moeda — não envia
  nenhum dado de transação ou titular, apenas código de moeda e data.
- **Não há telemetria.** `.streamlit/config.toml` desabilita
  `gatherUsageStats`.
- **Não é publicado.** O app foi configurado para rodar em `localhost` ou em
  servidor interno da organização, nunca em provedor público.

## O que os logs registram

A versão atual loga em stderr **sem PII**:

- Nome do arquivo enviado (escolhido pelo analista — equivale a metadado).
- Nome do parser que reconheceu o extrato (ex.: `bradesco`, `nubank`).
- Contagens (páginas, tabelas, linhas extraídas, consideradas, descartadas).
- Status PTAX (moeda, data, taxa) — informação pública.
- Exceções por arquivo, com `type(exc).__name__: mensagem`.

**Nunca são logados:** descrição de transação, valor, nome do titular, conta,
agência, CPF/CNPJ, conteúdo bruto do PDF.

## Responsabilidades do analista

1. **O Excel/PDF exportado contém PII.** Trate como documento confidencial:
   salve em pasta protegida, evite OneDrive pessoal, descarte conforme
   política interna de retenção (ex.: deletar após o caso ser arquivado).
2. **Encerre a sessão** ao terminar a análise — botão "Encerrar análise /
   limpar sessão" na sidebar limpa todas as transações da memória.
3. **Não compartilhe a URL** quando rodando em servidor interno; quem abrir o
   link vê os mesmos PDFs/dados que você (Streamlit não tem login nativo).
4. **Se a máquina é compartilhada**, feche o navegador e o terminal do
   Streamlit ao final do plantão para invalidar a sessão.

## Operação em servidor interno (opcional)

Quando o app passar a rodar num servidor da organização em vez de em
`localhost`, recomenda-se:

- Reverse proxy com SSO (Azure AD / Entra ID) na frente do Streamlit.
- HTTPS interno via certificado da PKI corporativa.
- Logs do processo ingestados pela rotina central de logs (ex.: Sentinel),
  com retenção alinhada à política de LGPD.

## Contato

Dúvidas ou incidentes: **Pedro.Lopes@rjzcyrela.com.br**.
