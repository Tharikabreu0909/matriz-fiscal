from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from services.pgdas_planner import normalize_malha_data


def brl(cents: int | None) -> str:
    value = int(cents or 0)
    whole, decimal = divmod(abs(value), 100)
    formatted = f"{whole:,}".replace(",", ".")
    sign = "-" if value < 0 else ""
    return f"{sign}R$ {formatted},{decimal:02d}"


def format_cnpj(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())

    if len(digits) != 14:
        return value

    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def format_iso_date(value: str | None) -> str:
    if not value:
        return "Não informada"

    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime(
            "%d/%m/%Y"
        )
    except ValueError:
        return value


def effective_analyses(
    analysis_result: dict[str, Any],
    stored_confirmations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reviewed = {
        item["competence"]: item["analysis"]
        for item in stored_confirmations
        if item.get("decision") == "CONFIRMED"
    }

    return [
        reviewed.get(item["competence"], item)
        for item in analysis_result.get("analyses", [])
    ]


def action_rows(
    analyses: list[dict[str, Any]],
    legal_charges: dict[str, Any],
) -> list[dict[str, Any]]:
    charge_by_competence = {
        row["competence"]: row
        for row in legal_charges.get("rows", [])
    }
    rows: list[dict[str, Any]] = []

    for analysis in analyses:
        segregation = analysis.get("segregation", {})
        type_01 = segregation.get("type_01", {})
        type_17 = segregation.get("type_17", {})
        consolidated = segregation.get("consolidated", {})
        study = segregation.get("accounting_study", {})
        regularization = analysis.get(
            "regularization",
            {},
        )
        actions: list[str] = []

        if (
            type_01.get("present")
            and type_01.get("minimum_gap_cents", 0) > 0
        ):
            validated_sped = regularization.get(
                "validated_sped_lfe_revenue_cents"
            )
            if validated_sped is not None:
                actions.append(
                    "A conferência registrada indicou que o SPED/LFE deve "
                    "refletir "
                    + brl(validated_sped)
                    + "."
                )
            else:
                actions.append(
                    "Conferir e reconstruir o SPED/LFE. "
                    "O cruzamento detectou movimentação mínima de "
                    + brl(type_01.get("minimum_detected_cents"))
                    + ", mas esse valor não define sozinho a "
                    "escrituração correta."
                )

        if (
            type_17.get("present")
            and type_17.get("simulation_increment_cents", 0) > 0
        ):
            validated_pgdas = regularization.get(
                "validated_pgdas_revenue_cents"
            )
            if validated_pgdas is not None:
                actions.append(
                    "A conferência registrada indicou receita de "
                    + brl(validated_pgdas)
                    + " para o PGDAS."
                )
            else:
                actions.append(
                    "Exposição simulada considerando receita de "
                    + brl(type_17.get("simulation_target_cents"))
                    + ". Validar a composição dos documentos antes "
                    "de retificar definitivamente o PGDAS."
                )

        if type_17.get("present") and type_17.get("simulation_target_cents") is None:
            actions.append(
                "Tipo 17: divergência de faturamento apontada na malha: "
                + brl(type_17.get("document_divergence_cents"))
                + ". Cálculo do imposto pendente de conferência do PGDAS."
            )
        if not actions:
            actions.append(
                "Nenhuma exposição tributária adicional identificada."
            )

        charge = charge_by_competence.get(
            analysis["competence"],
            {},
        )

        rows.append({
            "competence": analysis["competence"],
            "actions": actions,
            "minimum_sped_detected_cents": (
                type_01.get("minimum_detected_cents")
            ),
            "simulation_pgdas_target_cents": (
                type_17.get("simulation_target_cents")
            ),
            "regularization_status": regularization.get(
                "status",
                study.get(
                    "status",
                    "NOT_REQUIRED",
                ),
            ),
            "tax_increment_cents": consolidated.get(
                "simulation_tax_base_increment_cents",
                consolidated.get(
                    "tax_base_increment_cents",
                    0,
                ),
            ),
            "principal_cents": charge.get(
                "principal_cents",
                0,
            ),
            "fine_cents": charge.get("fine_cents", 0),
            "interest_cents": charge.get(
                "interest_cents",
                0,
            ),
            "updated_total_cents": charge.get(
                "total_cents",
                0,
            ),
        })

    return rows


def build_report_model(
    process: dict[str, Any],
    analysis_result: dict[str, Any],
    stored_confirmations: list[dict[str, Any]],
    tax_result: dict[str, Any],
    legal_charges: dict[str, Any],
) -> dict[str, Any]:
    analyses = effective_analyses(
        analysis_result,
        stored_confirmations,
    )
    rows = action_rows(analyses, legal_charges)
    # A tabela do relatório deve espelhar TODAS as competências originais da malha,
    # mesmo as que não tiveram PGDAS importado ou cálculo tributário concluído.
    normalized_malha = normalize_malha_data(process.get("malha") or {})
    analyses_by_competence = {row["competence"]: row for row in rows}
    for month in normalized_malha.get("work_months", []):
        competence = month["competence"]
        if competence in analyses_by_competence:
            continue
        notices = month.get("notices") or []
        type_01 = next((n for n in notices if n.get("type_code") == "01"), None)
        type_17 = next((n for n in notices if n.get("type_code") == "17"), None)
        actions = ["Competência identificada na malha; análise documental pendente."]
        if type_17:
            actions.append(
                "Tipo 17: diferença de faturamento informada na malha: "
                + brl(type_17.get("divergence_cents"))
                + ". Conferir PGDAS e calcular eventual imposto, sem presumir pagamento devido."
            )
        elif type_01:
            actions.append("Tipo 01: conferir LFE/EFD e PGDAS; não gera imposto automaticamente.")
        analyses_by_competence[competence] = {
            "competence": competence, "actions": actions,
            "minimum_sped_detected_cents": type_01.get("considered_cents") if type_01 else None,
            "simulation_pgdas_target_cents": None,
            "tax_increment_cents": 0, "updated_total_cents": 0,
        }
    rows = sorted(
        analyses_by_competence.values(),
        key=lambda row: (int(row["competence"][3:]), int(row["competence"][:2])),
    )
    tax_summary = tax_result.get("summary", {})
    charge_summary = legal_charges.get("summary", {})
    update_date = (
        legal_charges.get("source", {}).get("update_date")
    )

    relevant_rows = rows  # Nenhuma competência da malha pode ser ocultada.

    return {
        "company": {
            "name": process.get("company_name", ""),
            "cnpj": format_cnpj(
                process.get("company_cnpj", "")
            ),
            "cfdf": process.get(
                "company_identifier",
                "",
            ),
        },
        "generated_at": datetime.now().strftime(
            "%d/%m/%Y às %H:%M"
        ),
        "scenario": tax_result.get(
            "configuration",
            {},
        ).get(
            "scenario",
            "CONSERVATIVE_FISCAL_EXPOSURE",
        ),
        "update_date": format_iso_date(update_date),
        "annex": tax_result.get(
            "configuration",
            {},
        ).get("annex", ""),
        "summary": {
            "direct_tax_cents": tax_summary.get(
                "corrected_competence_total_cents",
                0,
            ),
            "reflection_tax_cents": tax_summary.get(
                "reflection_total_cents",
                0,
            ),
            "principal_cents": charge_summary.get(
                "principal_cents",
                0,
            ),
            "fine_cents": charge_summary.get(
                "fine_cents",
                0,
            ),
            "interest_cents": charge_summary.get(
                "interest_cents",
                0,
            ),
            "updated_total_cents": charge_summary.get(
                "total_cents",
                0,
            ),
            "impacted_month_count": tax_summary.get(
                "impacted_month_count",
                0,
            ),
            "calculation_end_competence": tax_summary.get(
                "calculation_end_competence"
            ),
            "full_reflection_end_competence": tax_summary.get(
                "full_reflection_end_competence"
            ),
            "future_pending_count": tax_summary.get(
                "future_pending_count",
                0,
            ),
            "is_partial": tax_summary.get(
                "is_partial",
                False,
            ),
        },
        "competence_rows": relevant_rows,
        "malha_competence_count": len(normalized_malha.get("work_months", [])),
        "reflection_rows": tax_result.get(
            "visible_impacts",
            [],
        ),
        "warnings": [
            *tax_result.get("warnings", []),
            *legal_charges.get("warnings", []),
        ],
    }


def competence_table_rows(
    rows: list[dict[str, Any]],
) -> str:
    rendered: list[str] = []

    for row in rows:
        actions = "".join(
            f"<li>{escape(action)}</li>"
            for action in row["actions"]
        )
        rendered.append(
            f"""
            <tr>
              <td class="competence">{escape(row["competence"])}</td>
              <td><ul>{actions}</ul></td>
              <td class="money">{brl(row["tax_increment_cents"])}</td>
              <td class="money">{brl(row["updated_total_cents"])}</td>
            </tr>
            """
        )

    if not rendered:
        return """
        <tr>
          <td colspan="4" class="empty">
            Nenhuma providência financeira foi identificada.
          </td>
        </tr>
        """

    return "".join(rendered)


def reflection_table_rows(
    rows: list[dict[str, Any]],
) -> str:
    rendered: list[str] = []

    for row in rows:
        if row.get("difference_cents", 0) == 0:
            continue

        classification = row.get("classification", "")
        label = {
            "CORRECTED_COMPETENCE": "Competência corrigida",
            "RBT12_REFLECTION": "Reflexo posterior",
            "CORRECTED_AND_REFLECTION": (
                "Competência corrigida e reflexo"
            ),
        }.get(classification, "Impacto calculado")

        rendered.append(
            f"""
            <tr>
              <td class="competence">{escape(row["competence"])}</td>
              <td>{escape(label)}</td>
              <td class="money">{brl(row["difference_cents"])}</td>
            </tr>
            """
        )

    if not rendered:
        return """
        <tr>
          <td colspan="3" class="empty">
            Não foram encontrados reflexos financeiros posteriores.
          </td>
        </tr>
        """

    return "".join(rendered)


def render_client_report(model: dict[str, Any]) -> str:
    company = model["company"]
    summary = model["summary"]
    competence_rows = competence_table_rows(
        model["competence_rows"]
    )
    reflection_rows = reflection_table_rows(
        model["reflection_rows"]
    )
    company_name = escape(
        company["name"] or "Empresa analisada"
    )
    cnpj = escape(company["cnpj"])
    cfdf = escape(company["cfdf"])
    annex = escape(model["annex"] or "Não identificado")
    scenario = model.get(
        "scenario",
        "CONSERVATIVE_FISCAL_EXPOSURE",
    )
    validated = scenario == "VALIDATED_REGULARIZATION"
    report_title = (
        "Relatório de regularização validada"
        if validated
        else "Relatório de exposição fiscal"
    )
    report_description = (
        "Resultado recalculado com os valores concluídos no estudo contábil."
        if validated
        else (
            "Estimativa conservadora da exposição indicada pela malha "
            "fiscal e pelas apurações do Simples Nacional."
        )
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(report_title)} — {company_name}</title>
<style>
:root {{
  --ink:#172033;
  --muted:#667085;
  --line:#dbe3ee;
  --soft:#f5f8fc;
  --brand:#225bd6;
  --brand-soft:#edf3ff;
  --green:#067647;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  background:#eef2f7;
  color:var(--ink);
  font-family:Segoe UI,Arial,sans-serif;
  font-size:14px;
  line-height:1.5;
}}
.page {{
  width:min(1040px,calc(100% - 32px));
  margin:28px auto;
  background:#fff;
  border:1px solid var(--line);
  border-radius:18px;
  box-shadow:0 14px 45px rgba(16,24,40,.08);
  overflow:hidden;
}}
.toolbar {{
  display:flex;
  justify-content:flex-end;
  padding:12px 22px;
  background:#101828;
}}
.toolbar button {{
  border:0;
  border-radius:9px;
  background:#fff;
  color:#172033;
  padding:10px 14px;
  font-weight:750;
  cursor:pointer;
}}
.header {{
  padding:34px 40px 30px;
  background:linear-gradient(135deg,#173e96,#2969ef);
  color:#fff;
}}
.brand {{
  font-size:13px;
  font-weight:850;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.header h1 {{
  margin:12px 0 7px;
  font-size:31px;
  line-height:1.15;
}}
.header p {{
  margin:0;
  opacity:.9;
}}
.badge {{
  display:inline-flex;
  margin-top:18px;
  padding:7px 11px;
  border-radius:999px;
  background:rgba(255,255,255,.16);
  font-size:12px;
  font-weight:750;
}}
.content {{
  padding:30px 40px 42px;
}}
.company {{
  display:grid;
  grid-template-columns:2fr 1fr 1fr;
  gap:12px;
  margin-bottom:22px;
}}
.info {{
  border:1px solid var(--line);
  border-radius:12px;
  padding:14px;
  background:#fff;
}}
.info span,.metric span {{
  display:block;
  color:var(--muted);
  font-size:11px;
}}
.info strong {{
  display:block;
  margin-top:5px;
}}
.metrics {{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:12px;
  margin:14px 0 28px;
}}
.metric {{
  border:1px solid var(--line);
  border-radius:13px;
  padding:16px;
  background:var(--soft);
}}
.metric.primary {{
  background:var(--brand-soft);
  border-color:#b9cef9;
}}
.metric strong {{
  display:block;
  margin-top:7px;
  font-size:20px;
}}
section {{
  margin-top:28px;
}}
h2 {{
  margin:0 0 6px;
  font-size:20px;
}}
.lead {{
  color:var(--muted);
  margin:0 0 13px;
}}
table {{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  border:1px solid var(--line);
  border-radius:12px;
  overflow:hidden;
}}
th {{
  text-align:left;
  background:#f3f6fa;
  color:#475467;
  font-size:11px;
  padding:11px 12px;
}}
td {{
  border-top:1px solid var(--line);
  padding:12px;
  vertical-align:top;
}}
td ul {{
  margin:0;
  padding-left:18px;
}}
.competence {{
  font-weight:800;
  white-space:nowrap;
}}
.money {{
  text-align:right;
  font-weight:750;
  white-space:nowrap;
}}
.empty {{
  text-align:center;
  color:var(--muted);
  padding:24px;
}}
.conclusion {{
  margin-top:28px;
  padding:18px;
  border-left:5px solid var(--green);
  border-radius:0 12px 12px 0;
  background:#ecfdf3;
}}
.conclusion strong {{
  display:block;
  font-size:17px;
  margin-bottom:5px;
}}
.notes {{
  color:var(--muted);
  font-size:12px;
  padding:16px;
  background:#f8fafc;
  border:1px solid var(--line);
  border-radius:11px;
}}
.footer {{
  display:flex;
  justify-content:space-between;
  gap:16px;
  color:var(--muted);
  font-size:11px;
  margin-top:30px;
  padding-top:18px;
  border-top:1px solid var(--line);
}}
@media(max-width:760px) {{
  .content,.header {{ padding-left:20px;padding-right:20px; }}
  .company,.metrics {{ grid-template-columns:1fr; }}
  table {{ display:block;overflow-x:auto; }}
}}
@media print {{
  @page {{ size:A4; margin:13mm; }}
  body {{ background:#fff;font-size:11px; }}
  .page {{
    width:100%;
    margin:0;
    border:0;
    box-shadow:none;
    border-radius:0;
  }}
  .toolbar {{ display:none; }}
  .header {{
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
  }}
  .content {{ padding:22px 0 0; }}
  .header {{ padding:25px 28px; }}
  .metrics {{ grid-template-columns:repeat(4,1fr); }}
  section {{ break-inside:avoid; }}
  tr {{ break-inside:avoid; }}
}}
</style>
</head>
<body>
<main class="page">
  <div class="toolbar">
    <button onclick="window.print()">
      Imprimir ou salvar em PDF
    </button>
  </div>

  <header class="header">
    <div class="brand">CheckFiscal</div>
    <h1>{escape(report_title)}</h1>
    <p>
      Estimativa conservadora da exposição indicada pela malha fiscal e pelas apurações do Simples Nacional.
    </p>
    <span class="badge">
      Estimativa atualizada até {escape(model["update_date"])}
    </span>
  </header>

  <div class="content">
    <section class="company">
      <div class="info">
        <span>Empresa</span>
        <strong>{company_name}</strong>
      </div>
      <div class="info">
        <span>CNPJ</span>
        <strong>{cnpj}</strong>
      </div>
      <div class="info">
        <span>CFDF</span>
        <strong>{cfdf or "Não informado"}</strong>
      </div>
    </section>

    <section>
      <h2>Resumo financeiro</h2>
      <p class="lead">
        Valores estimados considerando o cenário fiscal apontado,
        os reflexos posteriores, a multa e os juros.
      </p>
      <div class="metrics">
        <div class="metric">
          <span>Diferença de imposto</span>
          <strong>{brl(summary["principal_cents"])}</strong>
        </div>
        <div class="metric">
          <span>Multa estimada</span>
          <strong>{brl(summary["fine_cents"])}</strong>
        </div>
        <div class="metric">
          <span>Juros estimados</span>
          <strong>{brl(summary["interest_cents"])}</strong>
        </div>
        <div class="metric primary">
          <span>Total atualizado</span>
          <strong>{brl(summary["updated_total_cents"])}</strong>
        </div>
      </div>
    </section>

    {
      f"""<div class="partial">
        <strong>Resultado parcial até {escape(summary["calculation_end_competence"] or "")}</strong>
        Existem {summary["future_pending_count"]} competência(s) futura(s)
        até {escape(summary["full_reflection_end_competence"] or "")}.
        O relatório deverá ser atualizado quando os respectivos PGDAS forem
        transmitidos.
      </div>"""
      if summary["is_partial"]
      else ""
    }

    <section>
      <h2>Pontos de atenção</h2>
      <p class="lead">
        O SPED/LFE e o PGDAS são analisados separadamente. A simulação não transforma automaticamente os valores do cruzamento em ordens de retificação.
      </p>
      <table>
        <thead>
          <tr>
            <th>Competência</th>
            <th>Diagnóstico e próximo passo</th>
            <th class="money">Acréscimo considerado na simulação</th>
            <th class="money">Total atualizado</th>
          </tr>
        </thead>
        <tbody>{competence_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Competências consideradas na exposição</h2>
      <p class="lead">
        Inclui a competência de origem e os meses posteriores que sofreram alteração estimada no DAS dentro do cenário conservador.
      </p>
      <table>
        <thead>
          <tr>
            <th>Competência</th>
            <th>Origem do impacto</th>
            <th class="money">Diferença de DAS</th>
          </tr>
        </thead>
        <tbody>{reflection_rows}</tbody>
      </table>
    </section>

    <div class="conclusion">
      <strong>Exposição total estimada: {brl(summary["updated_total_cents"])}</strong>
      O valor reúne a diferença principal, os reflexos posteriores,
      a multa e os juros calculados até
      {escape(model["update_date"])}.
    </div>

    <section>
      <h2>Observações</h2>
      <div class="notes">
        Este documento apresenta uma estimativa conservadora produzida a partir dos arquivos analisados e das regras configuradas no CheckFiscal. Não constitui ordem automática de retificação.
        A composição dos documentos fiscais deve ser conferida antes de qualquer retificação definitiva. A emissão definitiva das guias e das retificações deve ser realizada nos sistemas oficiais. O cálculo atual pressupõe
        receita integralmente tributada pelo Anexo {annex}, sem
        segregações especiais, substituição tributária, tributação
        monofásica, isenções ou mistura de anexos.
      </div>
    </section>

    <footer class="footer">
      <span>Emitido em {escape(model["generated_at"])}</span>
      <span>CheckFiscal · Auditoria inteligente do Simples Nacional</span>
    </footer>
  </div>
</main>
</body>
</html>"""
