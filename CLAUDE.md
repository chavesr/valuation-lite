# Valuation Lite — regras de trabalho

## Ler TUDO o que a empresa mandou (regra inegociável, 11/11/2026)

Antes de triar, avaliar ou gerar qualquer relatório, leia **por inteiro** cada documento que a empresa enviou —
no Drive (pasta original do case, incluindo subpastas) e na cópia local:

- todas as páginas de todos os PDFs (inclusive os de dentro de .rar/.zip); se o texto vier embaralhado ou curto
  demais para o número de páginas, renderize as páginas e leia como imagem;
- todas as abas de todas as planilhas, de cima a baixo;
- Word, apresentações, imagens (fotos de WhatsApp, organogramas) e os relatórios gerenciais de anos anteriores;
- DREs e balanços contábeis **sempre** entram no relatório (histórico, DRE simplificado, balanço), mesmo quando o
  valuation usa o gerencial — nunca escreva "não informado" para algo que está na pasta.

Registre cada leitura em `_valuation/leitura.json` (formato em `tarantino/leitura.py`): o resumo do que o documento
traz e onde entra no relatório. `python -m tarantino relatorio` **recusa** gerar o relatório enquanto houver
documento sem leitura registrada. Não contorne a trava: se um arquivo não puder ser lido, registre por quê em
`sem_conteudo` e avise o usuário.

Antes de entregar, cruze o relatório com a leitura: cada "não informado", cada número e a finalidade (venda total,
entrada de sócio ou valuation independente) precisam bater com o que os documentos dizem.

**Por quê:** IBRATE (10/11) e Emunah (11/11) saíram com DRE, equipe, concorrentes, ativos e a própria finalidade
errados porque parte da pasta não foi lida — o usuário teve de apontar os erros antes de reuniões com o chefe.

## Ambiente

- Python do projeto: `C:\Users\ruhmk\.venvs\valuation_lite\Scripts\python.exe` (o Python do sistema não tem pydantic).
- Testes: `PYTHONDONTWRITEBYTECODE=1 <venv python> -m pytest -q -p no:cacheprovider`.
- Nunca rodar o tarantino direto na pasta do cliente no Drive: copiar para o scratchpad.
- Links de arquivo para o usuário: caminho sem espaços.
