# Regras de negócio

Regra vigente é a que está no código da versão **1.41.0** / planejador **2.4.0**. Onde um markdown antigo discorda, vale o código. Onde uma nota 1.43–1.45 discorda, a nota ainda não é comportamento.

Base legal usada pelo motor: Lei Complementar 123/2006, art. 18, anexos na redação vigente desde 01/01/2018. Isto é estimativa do escritório, não apuração oficial do PGDAS.

## 1. Empresa, carteira e processo

- O CNPJ identifica a empresa. O CFDF/IE complementa o confronto com a malha.
- A carteira mostra situação, exposição estimada e a ação principal.
- Cada empresa mantém um processo principal. Competências novas entram na malha já gravada (`merge_malhas`), sem abrir outro processo.
- Marcos técnicos vão para o histórico do processo. O histórico não é lista de tarefas.
- Divergência de identidade (IE diferente, ou nome abaixo de 0,78 sem IE comparável) exige confirmação explícita e fica registrada. Sem essa confirmação a importação responde 409.
- PGDAS só é aceito se a raiz do CNPJ (8 dígitos) for a da empresa e a competência extraída for a esperada.

## 2. Tipo 01 e Tipo 17 não se somam

Cada aviso é um cruzamento independente.

**Tipo 01** — SPED/LFE informado comparado ao valor considerado na malha.

- Providência de obrigação acessória: revisar e reconstruir SPED/LFE.
- Ação de plano: `REVIEW_SPED_LFE` e `VERIFY_PGDAS_DECLARATION`.
- O valor considerado é movimento mínimo detectado, não faturamento final nem alvo automático de retificação.
- Acréscimo mínimo = max(0, considerado − informado).
- `generates_tax` é falso. Tipo 01 sozinho não gera imposto, multa nem reflexo.

**Tipo 17** — receita informada na malha para o PGDAS comparada ao valor considerado, e depois ao PGDAS importado.

- Providência: avaliar exposição no PGDAS.
- Ações: importar PGDAS, avaliar tributo, avaliar reflexos de RBT12.
- O motor tributário recebe somente o acréscimo do Tipo 17.

Proibido calcular `divergência Tipo 01 + divergência Tipo 17`. O consolidado zera `combined_divergence_cents` e usa `tax_source = TYPE_17_ONLY`.

Se os dois tipos existem na mesma competência, o sistema só informa se o valor considerado é o mesmo (`SAME_CONSIDERED_VALUE` ou `DIFFERENT_CONSIDERED_VALUES`). Isso não soma base.

Mais de um aviso do mesmo tipo com valores diferentes gera aviso e empurra a competência para revisão. Duplicata idêntica é ignorada.

## 3. Planejador de PGDAS (2.4.0)

Entrada: malha normalizada (`work_months` reconciliado com `raw_rows`). Códigos `1` e `01` viram `01`. Competência aceita `MM/AAAA`, data ou `AAAA-MM`.

Saída: plano `UPFRONT_COMPLETE_PLAN`.

1. Toda competência identificada na malha entra na cobertura, inclusive mês só com Tipo 01.
2. O algoritmo pega sempre a competência ainda não coberta mais recente e pede o PGDAS daquele PA.
3. Esse arquivo cobre competências da malha anteriores dentro de **24 meses** (`HISTORY_MONTHS`), inclusive o próprio mês.
4. Repete até não sobrar competência da malha.
5. Janela só com Tipo 17, ou mista: pedido `ANALYSIS` (ou `ANALYSIS_AND_REFLECTION` se também cobrir reflexo).
6. Janela só com Tipo 01: pedido `VERIFICATION`. Confere o que foi declarado. Não presume omissão nem imposto.
7. Para cada Tipo 17, os 12 meses seguintes até o último PA já vencido são tratados como reflexo potencial. O que o plano da malha ainda não cobre vira pedido `REFLECTION`, também agrupado pela janela de 24 meses.
8. Um PGDAS posterior não substitui o PGDAS da própria competência quando os dois foram pedidos. O histórico confirma receita; não substitui a apuração daquele PA com a mesma segurança.
9. O plano não projeta receita futura. Meses entre o último PA vencido e o fim da janela de 12 meses ficam em `future_pending_competences`.

Último PA normalmente vencido: o mais recente cujo dia 20 do mês seguinte (avançando sábado e domingo para segunda) já passou na data de referência.

O plano fica `ERROR` se sobrar competência sem cobertura, linha sem competência, ou tipo no resumo sem mês correspondente. A interface não pode tratar lista vazia como “PGDAS desnecessário” quando a malha tem competência. Mensagem de falha bloqueia a análise.

Depois da leitura real, `reflection_coverage` valida a linha do tempo. Se uma correção confirmada não tiver receita dos meses posteriores já vencidos, pede PGDAS complementar e o cálculo responde 409. Competência antiga pode gerar pedido que o plano inicial não previu.

Documento `regra-planejador-pgdas.md` está superado no ponto em que dispensa PGDAS do Tipo 01.

## 4. Análise automática por exceção

Para Tipo 17 com PGDAS da competência:

- alvo de simulação = max(receita declarada importada, valor considerado na malha);
- acréscimo = max(0, alvo − receita declarada);
- acréscimo > 0 liga cálculo direto e reflexos de RBT12.

Receita importada diferente da receita informada na malha gera aviso (`DIFFERENT_FROM_MALHA`): pode ser retificação posterior ou outro arquivo. Isso pede revisão humana daquela competência, não das outras.

Status:

| Status | Quando |
| --- | --- |
| `AWAITING_PGDAS` | Há Tipo 17 e ainda não há receita declarada da competência |
| `REVIEW_REQUIRED` | Há avisos (fonte divergente ou avisos duplicados) |
| `AUTO_ANALYZED` | Há ação e não há aviso. Confiança alta para exposição |
| `NO_ACTION_REQUIRED` | Sem ação e sem aviso |

Decisão automática nasce do motor. Revisão salva com `CONFIRMED` substitui só aquela competência. Análise original, divergência e ajuste humano ficam separados.

O estudo contábil não bloqueia a simulação de exposição. Bloqueia a instrução de regularização definitiva enquanto estiver pendente.

## 5. Estudo contábil e dois cenários

Estudo é obrigatório quando ocorre ao menos um destes fatos:

- SPED/LFE informado igual a zero;
- SPED/LFE abaixo do mínimo detectado;
- valor considerado do Tipo 17 acima do PGDAS (acréscimo de simulação > 0);
- Tipo 01 e Tipo 17 com valores considerados diferentes.

Perguntas do estudo: se os documentos pertencem à competência; se há nota extemporânea, complementar, cancelada, devolução, duplicidade ou documento de outro período; se o cartão já está nas vendas documentadas; qual receita deve ficar no PGDAS e na escrituração.

Conclusão exige motivo da lista (`CARD_SALE_WITHOUT_INVOICE`, `DOCUMENT_NOT_IMPORTED`, `PGDAS_ENTRY_ERROR`, `SPED_NOT_SENT_OR_ZERO`, `REVENUE_WRONG_COMPETENCE`, `CANCELLED_RETURNED_OR_DUPLICATE`, `CARD_ALREADY_INCLUDED`, `MIXED_CAUSES`, `OTHER`, mais códigos antigos de compatibilidade). `OTHER` exige texto. Valor validado não pode ser negativo. Se o tipo está presente, o valor validado correspondente é obrigatório.

Cenários:

- `CONSERVATIVE_FISCAL_EXPOSURE` — mantém o valor considerado pelo Fisco. Responde quanto custaria se a malha prevalecer.
- `VALIDATED_REGULARIZATION` — usa o valor concluído pela contabilidade. Responde o que deve ser retificado.

A conclusão não altera malha, PGDAS importado nem a memória do cenário conservador. Cada cálculo é gravado no próprio cenário.

O cenário validado só segue se o estudo exigido estiver concluído (`AccountingStudyError` vira HTTP 409).

## 6. Motor tributário ligado à API

Perfil confirmado antes do cálculo. Anexo obrigatório entre I e V. Sem essa confirmação o motor recusa.

Alíquota efetiva:

`(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12`

RBT12 zero usa a alíquota nominal da primeira faixa. Alíquota negativa vira zero. RBT12 acima de R$ 4.800.000,00 (480.000.000 centavos) é erro. Dinheiro × alíquota arredonda half-up para centavo.

Faixas em centavos, desde 01/01/2018, anexos I, II, III, IV e V, seis faixas cada uma, teto 4.800.000,00. O markdown `motor-tributario-v1.md` omite o Anexo V; a tabela em `tax_engine.py` inclui.

Linha do tempo: histórico de receitas dos extratos preenche meses; a receita do próprio PA substitui o histórico daquele mês.

Uma correção entra na RBT12 dos doze períodos seguintes. O imposto recalculado não volta como receita.

Para cada mês da janela o motor exige o próprio mês e os 12 anteriores na linha do tempo. Mês faltante entra em `missing_months` e não é inventado. Ano >= 2027 entra em `unsupported_months` e fica de fora.

Classificação do mês: `CORRECTED_COMPETENCE`, `RBT12_REFLECTION`, `CORRECTED_AND_REFLECTION` ou `NO_EFFECT`. Diferença de DAS diferente de zero aparece em `visible_impacts`. Total = efeito direto da competência corrigida + reflexos.

O cálculo da API só roda se:

- todos os PGDAS de análise e de conferência do plano inicial foram aceitos;
- competências em `REVIEW_REQUIRED` foram confirmadas;
- meses de reflexo já vencidos estão cobertos por receita real.

Resultado com meses futuros pendentes é parcial (`is_partial`). O aviso diz até qual competência o número vale.

Premissa explícita do perfil padrão: receita integral no anexo escolhido, sem segregação. O aviso do resultado repete isso.

## 7. Motores presentes e ainda fora do cálculo principal

Não usar estes números como se já saíssem de `/api/calculate-tax`.

- Fator R: folha de 12 meses ÷ RBT12. Limiar **0,28**. Igual ou acima -> Anexo III; abaixo -> Anexo V. RBT12 zerada ou folha ausente recusam o cálculo nesta versão.
- Linhas de receita: atividades I, II, III, IV, V e `FACTOR_R`; tratamentos `PIS_MONOPHASIC`, `COFINS_MONOPHASIC`, `ICMS_ST`.
- Colunas por anexo reaproveitam o cálculo de linhas.

## 8. Cobertura dos reflexos

Correção em um PA afeta a RBT12 dos 12 meses seguintes.

Exemplo usado nos docs, com data de referência 22/07/2026 e malha em 11/2025:

- efeito cheio: 12/2025 a 11/2026;
- último PA normalmente vencido: 06/2026;
- cálculo real até 06/2026;
- 07/2026 a 11/2026 ficam pendentes até o PGDAS existir.

Zero e projeção não entram como receita futura. Declaração e extrato servem para competência, histórico e meses posteriores. Sem extrato, o vencimento dos encargos usa a regra padrão e o aviso de conferência.

## 9. Multa e juros

Multa: `min(dias de atraso × 0,33%, 20%) × principal`. Atraso zero ou negativo -> multa zero. Implementação: `dias × 0,0033`, teto `0,20`.

Juros:

- zero no próprio mês do vencimento e se a atualização não passou do vencimento;
- Selic mensal (SGS 4390) do mês seguinte ao vencimento até o mês anterior à atualização;
- mais 1% no mês da atualização;
- mês ausente na série interrompe o cálculo com a lista dos meses faltantes.

Vencimento:

1. data extraída do DAS do PGDAS, quando houver;
2. senão, dia 20 do mês seguinte à competência;
3. sábado ou domingo avança para segunda;
4. feriado bancário e prorrogação extraordinária não estão na regra automática e precisam de fonte oficial ou do vencimento do PGDAS.

## 10. O que a tela mostra

Divulgação por camadas: indicadores, competência fechada (divergência principal, próxima ação, situação), cruzamentos do mês, análise técnica, memória de cálculo (RBT12, multa, juros). Tipos 01 e 17 só dentro da expansão. Observação livre é opcional; motivo padronizado é o caminho normal.

Relatório do cliente leva identificação, data, resumo financeiro, providências por competência, meses com impacto de DAS, total atualizado e a frase de que é estimativa.

Ficam de fora do cliente: JSON, status internos, confiança, origem das fontes, fórmula, RBT12 mês a mês e alerta de implementação. Isso permanece na tela do contador.

## 11. Dados e beta comercial

Beta descrita em `docs/blindagem-comercial-v1.md`: local, um operador, estimativa conservadora, períodos até 12/2026, onboarding assistido.

Backup completo = banco + PDF. Guardar em local restrito. Não enviar por canal inseguro. Suporte recebe o pacote de diagnóstico, não o banco. Backup pelo menos semanal e sempre antes de trocar versão. Conferir o cálculo com documento oficial antes de retificar.

Não há login, vários escritórios, nuvem nem atualização automática.

## 12. Regras escritas para 1.44 e 1.45, ainda não implementadas

Registrar como intenção, não como regra ativa:

- Cada PGDAS pedido pode ser marcado disponível, não declarado ou não localizado, e a análise documental parcial pode avançar quando todo pedido tiver arquivo ou marcação.
- Ausência de PGDAS não vira receita zero. Cálculo integral continua bloqueado sem documentação suficiente.
- O usuário informa o último PGDAS efetivamente transmitido (mês e ano, faixa citada 1990–2100), gravado por processo.
- Pedidos de documento posteriores a esse corte deixam de ser exigidos. Competências de malha posteriores permanecem visíveis como presunção de não transmissão.
- O PGDAS desse último PA pode cobrir histórico anterior no lugar de solicitações posteriores.
- Receita declarada hipotética de R$ 0,00 não é receita real e não preenche lacuna de RBT12.
- Relatório parcial separa competências com presunção de não declaração.
- Competência antiga sem cobertura continua sendo erro do planejador.
- Simulação tributária completa só com receitas reais suficientes. Hipótese zero não alimenta o DAS.

Implementar isso exige funções que os testes já nomeiam e o código ainda não contém: `adapt_plan_to_last_transmitted` e a persistência do último PGDAS / status de ausência.
