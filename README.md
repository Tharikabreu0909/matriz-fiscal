# Matriz Fiscal 1.41 — PGDAS para todas as competências da malha

**Versão operacional: 1.41.0** · **Porta local: `http://127.0.0.1:8141`**

## Correção desta versão

- Toda competência identificada na malha gera cobertura PGDAS, inclusive quando contém somente Tipo 01.
- Tipo 01 solicita PGDAS para conferir o que foi declarado; continua sem gerar imposto, multa ou reflexo tributário automaticamente.
- Tipo 17 mantém a análise de exposição fiscal e a cobertura de reflexos aplicável.
- O planejador agrupa competências cobertas pelo histórico do mesmo PGDAS, evitando solicitações redundantes.
- Se uma competência da malha ficar sem cobertura, o sistema informa falha no planejamento em vez de marcar a etapa como desnecessária.
- Processos existentes atualizam o plano ao serem abertos, por causa da nova versão do planejador.

## Abrir no Windows

1. Extraia o ZIP em uma pasta nova.
2. Execute `INICIAR_CHECKFISCAL_WINDOWS.bat`.
3. Confirme a versão `1.41` e o endereço `http://127.0.0.1:8141`.
4. Para testar o fluxo, siga `COMO_TESTAR.html`.

O banco local permanece em `%LOCALAPPDATA%\CheckFiscal`. Não o exclua para aplicar esta atualização.

## Fluxo fiscal

**Tipo 01:** conferir PGDAS + revisar SPED/LFE. O valor considerado na malha permanece movimento mínimo detectado, não alvo automático de retificação.

**Tipo 17:** conferir PGDAS e avaliar exposição tributária conservadora. Os reflexos na RBT12 dependem de receitas reais e nunca são preenchidos por projeções automáticas.
