# CheckFiscal 1.45 — PGDAS para todas as competências da malha

**Versão operacional: 1.45.0** · **Porta local: `http://127.0.0.1:8145`**

## Instalação no Windows
1. Extraia o ZIP em uma pasta nova.
2. Execute `INICIAR_CHECKFISCAL_WINDOWS.bat`.
3. Confirme a versão 1.45 e a porta 8145 no navegador.

## Python compatível
Esta versão utiliza Python 3.11, 3.12 ou 3.13 de 64 bits. O Python 3.15 não é usado por esta versão, porque dependências binárias ainda podem não ter rodas compatíveis. O instalador escolhe automaticamente 3.13, 3.12 ou 3.11, quando instalado. Se o computador tiver apenas Python 3.15, instale Python 3.13 pelo site oficial: https://www.python.org/downloads/windows/ . Marque “Add Python to PATH”. Você pode manter as duas versões instaladas.

O pacote não usa o extra `uvicorn[standard]`, que estava acionando a compilação de PyYAML desnecessariamente; o aplicativo não utiliza essa funcionalidade extra.

## Dados
O banco de dados local é mantido em `%LOCALAPPDATA%\CheckFiscal`. Não apague essa pasta ao atualizar o programa.

## Mudanças desta versão
- Evita a instalação do extra opcional que acionava a compilação de PyYAML.
- Seleciona apenas versões compatíveis do Python e explica claramente como instalar uma versão suportada.
- Recria apenas o ambiente virtual descartável se ele tiver sido criado com uma versão incompatível.
- Mantém a regra de solicitar PGDAS para conferência também nas competências que aparecem apenas com Tipo 01.
