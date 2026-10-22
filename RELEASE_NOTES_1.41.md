# Matriz Fiscal 1.41.0

## Regra PGDAS atualizada

- O PGDAS é solicitado para toda competência identificada na malha, mesmo quando há apenas Tipo 01.
- O Tipo 01 gera uma solicitação de conferência declaratória e mantém a revisão SPED/LFE; não aciona sozinho cálculo de imposto.
- O Tipo 17 continua acionando análise de exposição fiscal e reflexos potencialmente aplicáveis.
- Solicitações são consolidadas usando a janela histórica do PGDAS, preservando a cobertura de cada competência.
- O status de documentos e as validações da API exigem todos os PGDAS iniciais, inclusive pedidos de conferência Tipo 01.
- A interface deixa de marcar automaticamente uma malha com competências como “Não se aplica”.
- Versão operacional e porta local atualizadas para 1.41 / 8141.
