# Contexto do produto

Nome operacional: **Matriz Fiscal** (repositório e dados locais: CheckFiscal).

## Por que existe

Escritórios de contabilidade recebem a malha fiscal do Simples Nacional e precisam decidir, competência a competência, o que é obrigação acessória (SPED/LFE) e o que é exposição tributária no PGDAS. O trabalho manual mistura os dois avisos, soma divergências que não podem ser somadas e projeta imposto sem receita real.

O Matriz Fiscal lê os PDFs, separa os cruzamentos, pede só os PGDAS necessários e entrega uma estimativa conservadora para o contador mostrar ao cliente.

## Problemas que resolve

- Identificar Tipo 01 e Tipo 17 sem somar as divergências.
- Planejar, de uma vez, quais PGDAS conferem a malha e quais cobrem reflexos da RBT12.
- Simular a exposição se o valor considerado pelo Fisco prevalecer, sem tratar isso como retificação definitiva.
- Separar o estudo contábil (valor que realmente deve ser retificado) da exposição conservadora.
- Estimar DAS, multa e juros só com receitas reais já vencidas.
- Guardar malha, PGDAS, histórico e backups na máquina do escritório.

## Como deve funcionar

Jornada em cinco etapas, sem virar sistema de tarefas:

1. **Malha** — upload do PDF, identificação da empresa e divergências por competência.
2. **Documentos** — PGDAS pedidos pelo planejador, um a um ou em lote.
3. **Análise** — uma linha por competência; Tipos 01 e 17 só aparecem expandidos e nunca somados.
4. **Cálculo** — estimativa de DAS, reflexos na RBT12, multa e juros.
5. **Relatório** — texto para o cliente, sem JSON, status internos, fórmula ou memória técnica.

A empresa tem um processo principal. Nova malha entra nesse processo; o histórico registra os marcos técnicos.

## Limite de produto verificado no código

- Aplicação local, um operador por instalação, sem login e sem nuvem.
- Resultado é estimativa. O relatório precisa deixar isso explícito.
- Períodos de 2027 em diante ficam bloqueados (transição tributária).
- O cálculo ligado à API usa um único anexo para a receita integral. Segregação, Fator R e colunas por anexo existem como motores, mas não são o cálculo do endpoint principal.
- Receita futura não é preenchida com zero nem com projeção.

## O que o contador precisa ver primeiro

Em poucos segundos: o que aconteceu, quanto está envolvido, quais competências pedem ação e quais pedem estudo contábil. O código do tipo permanece visível, sempre com a explicação humana do cruzamento.
