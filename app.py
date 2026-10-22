from __future__ import annotations

from pathlib import Path
import asyncio
from io import BytesIO
import json
import zipfile
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from database import (
    create_process,
    create_company,
    update_company,
    delete_company,
    get_company,
    list_companies,
    list_recent_process_events,
    get_company_active_process,
    update_process_malha,
    update_process_pgdas_plan,
    invalidate_process_analysis,
    accepted_pgdas_periods,
    append_process_event,
    list_process_events,
    get_process,
    list_accepted_pgdas,
    save_diagnostics,
    save_pgdas_document,
    save_analysis_confirmation,
    list_analysis_confirmations,
    save_tax_calculation,
    latest_tax_calculation,
    save_legal_charge_calculation,
    latest_legal_charge_calculation,
    save_client_report,
    latest_client_report,
    list_accounting_study_conclusions,
    latest_tax_calculations,
    latest_legal_charge_calculations,
    save_tax_profile,
    list_tax_profiles,
    update_process_status,
    register_stored_document,
    list_stored_documents,
    get_stored_document,
    database_status,
)
from readers.malha_reader import read_malha_pdf
from readers.pgdas_reader import read_pgdas_pdf
from services.cross_engine import validate_pgdas_identity
from services.analysis_engine import analyze_process
from services.tax_engine import (
    TaxEngineError,
    calculate_hidden_reflections,
)
from services.tax_revenue_lines import (
    RevenueLinesError,
    build_tax_setup,
)
from services.malha_merge import merge_malhas, malha_already_imported
from services.legal_charges import (
    LegalChargesError,
    calculate_legal_charges,
)
from services.client_report import (
    build_report_model,
    render_client_report,
)
from services.pgdas_planner import (
    calculate_required_pgdas,
    normalize_malha_data,
)
from services.reflection_coverage import (
    calculate_reflection_coverage,
)
from services.process_summary import (
    build_process_summary,
)
from services.accounting_study import (
    AccountingStudyError,
    EXPOSURE_SCENARIO,
    VALIDATED_SCENARIO,
    apply_study_conclusions,
    build_scenario_confirmations,
    validate_conclusion,
)
from services.security import (
    validate_cnpj,
    validate_malha_identity,
)
from services.file_storage import (
    delete_company_documents,
    resolve_document_path,
    store_document,
)
from services.backup_service import (
    create_backup,
    restore_backup,
    validate_backup_bytes,
)
from services.support_bundle import create_support_bundle
from services.app_logging import logger
from services.runtime_paths import DATA_DIR, DOCUMENTS_DIR


BASE_DIR = Path(__file__).resolve().parent
APP_VERSION = "1.41.0"
MAX_FILE_SIZE = 20 * 1024 * 1024
PROFILE_CODE = "SINGLE_ANNEX_ESTIMATE_V1"


def ensure_current_pgdas_plan(
    process: dict[str, Any],
) -> dict[str, Any]:
    """Atualiza planos antigos sem exigir novo upload da malha."""
    normalized_malha = normalize_malha_data(process.get("malha", {}))
    current = process.get("pgdas_plan", {})
    refreshed = calculate_required_pgdas(normalized_malha)

    current_version = current.get("planner", {}).get("version")
    refreshed_version = refreshed.get("planner", {}).get("version")
    current_periods = [
        item.get("requested_competence")
        for item in current.get("required_pgdas", [])
    ]
    refreshed_periods = [
        item.get("requested_competence")
        for item in refreshed.get("required_pgdas", [])
    ]
    current_due = current.get("summary", {}).get(
        "latest_normally_due_competence"
    )
    refreshed_due = refreshed.get("summary", {}).get(
        "latest_normally_due_competence"
    )
    current_validation = current.get("validation", {}).get("status")
    refreshed_validation = refreshed.get("validation", {}).get("status")
    current_type_17_count = current.get("summary", {}).get("type_17_month_count")
    refreshed_type_17_count = refreshed.get("summary", {}).get("type_17_month_count")

    if (
        current_version != refreshed_version
        or current_periods != refreshed_periods
        or current_due != refreshed_due
        or current_validation != refreshed_validation
        or current_type_17_count != refreshed_type_17_count
    ):
        update_process_pgdas_plan(process["id"], refreshed)
        return {**process, "malha": normalized_malha, "pgdas_plan": refreshed}

    return {**process, "malha": normalized_malha, "pgdas_plan": current}



def build_effective_confirmations(
    analysis_result: dict,
    stored_confirmations: list[dict],
) -> list[dict]:
    """
    Decisões automáticas são usadas diretamente.
    Uma revisão salva substitui a decisão automática da mesma competência.
    """
    stored_by_competence = {
        item["competence"]: item
        for item in stored_confirmations
        if item.get("decision") == "CONFIRMED"
    }
    effective: list[dict] = []

    for analysis in analysis_result["analyses"]:
        competence = analysis["competence"]

        if competence in stored_by_competence:
            effective.append(stored_by_competence[competence])
            continue

        if analysis["status"] in {
            "AUTO_ANALYZED",
            "NO_ACTION_REQUIRED",
        }:
            effective.append({
                "competence": competence,
                "decision": "AUTO_APPROVED",
                "analysis": analysis,
            })

    return effective


def calculate_initial_plan_status(
    process: dict,
    accepted_pgdas: list[dict],
) -> dict:
    accepted_periods = {
        pgdas.get("assessment", {}).get("period", "")
        for pgdas in accepted_pgdas
    }
    requests = process.get("pgdas_plan", {}).get("required_pgdas", [])

    # Todos os PGDAS iniciais são obrigatórios: os de análise Tipo 17 e os
    # de conferência declaratória Tipo 01. Só os pedidos exclusivamente
    # posteriores são separados da etapa inicial.
    initial_periods = {
        request["requested_competence"]
        for request in requests
        if request.get("request_kind") != "REFLECTION"
    }
    reflection_periods = {
        request["requested_competence"]
        for request in requests
        if request.get("request_kind") in {
            "REFLECTION",
            "ANALYSIS_AND_REFLECTION",
            "VERIFICATION_AND_REFLECTION",
        }
    }

    missing_initial = sorted(initial_periods - accepted_periods)
    missing_reflection = sorted(reflection_periods - accepted_periods)

    return {
        "accepted_periods": sorted(accepted_periods),
        "analysis_requests_complete": len(missing_initial) == 0,
        "initial_documents_complete": len(missing_initial) == 0,
        "reflection_requests_complete": len(missing_reflection) == 0,
        # Campo legado mantido para compatibilidade com as telas/rotas antigas.
        "missing_analysis_competences": missing_initial,
        "missing_initial_documents": missing_initial,
        "missing_reflection_competences": missing_reflection,
    }


def build_analysis_context(
    process_id: int,
    process: dict,
    accepted_pgdas: list[dict],
) -> dict:
    analysis_result = analyze_process(
        process["malha"],
        accepted_pgdas,
    )
    confirmations = list_analysis_confirmations(
        process_id
    )
    conclusions = list_accounting_study_conclusions(
        process_id
    )
    regularization_result = apply_study_conclusions(
        analysis_result,
        confirmations,
        conclusions,
    )
    tax_results = latest_tax_calculations(
        process_id
    )
    charge_results = latest_legal_charge_calculations(
        process_id
    )
    analysis_summary = build_process_summary(
        analysis_result=analysis_result,
        stored_confirmations=confirmations,
        regularization_result=regularization_result,
        tax_result=tax_results.get(
            EXPOSURE_SCENARIO
        ),
        legal_charges=charge_results.get(
            EXPOSURE_SCENARIO
        ),
        validated_tax_result=tax_results.get(
            VALIDATED_SCENARIO
        ),
        validated_legal_charges=charge_results.get(
            VALIDATED_SCENARIO
        ),
    )

    return {
        "analysis_result": analysis_result,
        "confirmations": confirmations,
        "conclusions": conclusions,
        "regularization_result": regularization_result,
        "tax_results": tax_results,
        "charge_results": charge_results,
        "analysis_summary": analysis_summary,
    }


class TaxCalculationRequest(BaseModel):
    process_id: int
    annex: str
    scenario: str = EXPOSURE_SCENARIO
    standard_profile_confirmed: bool = True


class CompanyCreateRequest(BaseModel):
    cnpj: str
    legal_name: str
    trade_name: str = ""
    state_registration: str = ""
    city: str = ""
    state: str = ""
    default_annex: str = "I"
    notes: str = ""


class CompanyUpdateRequest(BaseModel):
    legal_name: str | None = None
    trade_name: str | None = None
    state_registration: str | None = None
    city: str | None = None
    state: str | None = None
    default_annex: str | None = None
    notes: str | None = None



app = FastAPI(
    title="Matriz Fiscal - Malha, PGDAS e Diagnóstico",
    version=APP_VERSION,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
    except Exception:
        logger.exception(
            "Erro não tratado em %s %s",
            request.method,
            request.url.path,
        )
        raise


_STATIC_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8"),
        headers=_STATIC_CACHE,
    )


@app.get("/static/app.css")
def app_stylesheet() -> FileResponse:
    return FileResponse(
        BASE_DIR / "static" / "app.css",
        media_type="text/css; charset=utf-8",
        headers=_STATIC_CACHE,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "pipeline": "commercial-hardening-local-beta",
        "version": APP_VERSION,
    }



@app.get("/api/companies")
def companies_index() -> JSONResponse:
    return JSONResponse({"companies": list_companies()})


@app.get("/api/events")
def events_index(limit: int = 50) -> JSONResponse:
    return JSONResponse({"events": list_recent_process_events(limit)})


@app.post("/api/companies")
def companies_create(request: CompanyCreateRequest) -> JSONResponse:
    try:
        company_id = create_company(**request.model_dump())
        company = get_company(company_id)
        return JSONResponse({"company": company}, status_code=201)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/companies/{company_id}")
def companies_show(company_id: int) -> JSONResponse:
    try:
        company = get_company(company_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    process = get_company_active_process(company_id)
    if process:
        process = ensure_current_pgdas_plan(process)
    return JSONResponse({
        "company": company,
        "active_process": process,
        "events": list_process_events(process["id"]) if process else [],
    })


@app.patch("/api/companies/{company_id}")
def companies_update(
    company_id: int,
    request: CompanyUpdateRequest,
) -> JSONResponse:
    try:
        update_company(
            company_id,
            **request.model_dump(exclude_none=True),
        )
        return JSONResponse({"company": get_company(company_id)})
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/companies/{company_id}")
def companies_delete(company_id: int) -> JSONResponse:
    try:
        get_company(company_id)
        delete_company_documents(company_id)
        delete_company(company_id)
        logger.info("Empresa %s excluída com seus documentos.", company_id)
        return JSONResponse({"status": "DELETED", "company_id": company_id})
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/analyze-malha")
async def analyze_malha(
    file: UploadFile = File(...),
    company_id: int | None = None,
    company_cnpj: str | None = None,
    confirm_identity_mismatch: bool = False,
) -> JSONResponse:
    file_name = file.filename or "malha.pdf"

    company = None
    if company_id is not None:
        try:
            company = get_company(company_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        normalized_cnpj = company["cnpj"]
    else:
        try:
            normalized_cnpj = validate_cnpj(company_cnpj)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

    try:
        normalized_cnpj = validate_cnpj(normalized_cnpj)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Selecione uma empresa cadastrada com CNPJ válido.",
        ) from error

    if Path(file_name).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo PDF da malha fiscal.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="O arquivo está vazio.",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="O arquivo ultrapassa o limite de 20 MB.",
        )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
        ) as temp:
            temp.write(content)
            temporary_path = Path(temp.name)

        malha = normalize_malha_data(read_malha_pdf(temporary_path))
        malha["source_document"]["file_name"] = file_name

        identity_validation = None
        if company is not None:
            identity_validation = validate_malha_identity(
                company,
                malha,
            )
            if (
                not identity_validation["match"]
                and not confirm_identity_mismatch
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "MALHA_IDENTITY_MISMATCH",
                        "message": (
                            "A empresa encontrada na malha não corresponde "
                            "ao cadastro selecionado."
                        ),
                        "identity": identity_validation,
                    },
                )

        active_process = (
            get_company_active_process(company_id)
            if company_id is not None
            else None
        )
        if active_process:
            active_process = ensure_current_pgdas_plan(active_process)
        duplicate_ignored = False
        if active_process:
            process_id = active_process["id"]
            if malha_already_imported(active_process["malha"], malha):
                duplicate_ignored = True
                malha = normalize_malha_data(active_process["malha"])
                pgdas_plan = active_process["pgdas_plan"]
                event_title = "Arquivo de malha repetido ignorado"
            else:
                malha = normalize_malha_data(
                    merge_malhas(active_process["malha"], malha)
                )
                pgdas_plan = calculate_required_pgdas(malha)
                update_process_malha(
                    process_id,
                    malha,
                    pgdas_plan,
                    malha.get("contributor", {}).get("legal_name", "")
                    or (company or {}).get("legal_name", ""),
                    malha.get("contributor", {}).get("cfdf", ""),
                    file_name,
                )
                invalidate_process_analysis(process_id)
                event_title = "Nova malha adicionada ao processo"
        else:
            pgdas_plan = calculate_required_pgdas(malha)
            process_id = create_process(
                malha,
                pgdas_plan,
                normalized_cnpj,
                company_id=company_id,
            )
            event_title = "Malha fiscal incluída"

        if not duplicate_ignored and company_id is not None:
            stored = store_document(
                content=content,
                company_id=company_id,
                process_id=process_id,
                kind="MALHA",
                original_name=file_name,
            )
            register_stored_document(
                company_id=company_id,
                process_id=process_id,
                kind=stored["kind"],
                competence=stored["competence"],
                original_name=stored["original_name"],
                stored_path=stored["stored_path"],
                sha256=stored["sha256"],
                size_bytes=stored["size_bytes"],
            )

        append_process_event(
            process_id,
            "MALHA_INCLUDED",
            event_title,
            {
                "file_name": file_name,
                "competences": [
                    month["competence"]
                    for month in malha.get("work_months", [])
                ],
                "duplicate_ignored": duplicate_ignored,
                "identity_status": (
                    identity_validation.get("status")
                    if identity_validation
                    else "NOT_CHECKED"
                ),
                "identity_override": bool(
                    identity_validation
                    and not identity_validation["match"]
                    and confirm_identity_mismatch
                ),
            },
        )

        return JSONResponse({
            "process_id": process_id,
            "company": company,
            "malha": malha,
            "pgdas_plan": pgdas_plan,
            "duplicate_ignored": duplicate_ignored,
            "identity_validation": identity_validation,
        })
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Não foi possível interpretar a malha: {error}",
        ) from error
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


@app.post("/api/upload-pgdas")
async def upload_pgdas(
    process_id: int,
    competence: str,
    file: UploadFile = File(...),
) -> JSONResponse:
    file_name = file.filename or "pgdas.pdf"

    if Path(file_name).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail=("Envie o Extrato ou a Declaração ""do PGDAS-D em PDF."),
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="O arquivo está vazio.",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="O arquivo ultrapassa o limite de 20 MB.",
        )

    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    process = ensure_current_pgdas_plan(process)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
        ) as temp:
            temp.write(content)
            temporary_path = Path(temp.name)

        pgdas = read_pgdas_pdf(temporary_path)
        pgdas["source_document"]["file_name"] = file_name

        identity = validate_pgdas_identity(
            process["company_cnpj"],
            pgdas,
        )
        extracted_period = pgdas["assessment"]["period"]
        competence_match = competence == extracted_period
        accepted = identity["match"] and competence_match

        save_pgdas_document(
            process_id=process_id,
            requested_competence=competence,
            pgdas=pgdas,
            identity_status=identity["status"],
            competence_status=(
                "MATCH"
                if competence_match
                else "MISMATCH"
            ),
            accepted=accepted,
        )
        if accepted:
            if process.get("company_id"):
                stored = store_document(
                    content=content,
                    company_id=int(process["company_id"]),
                    process_id=process_id,
                    kind="PGDAS",
                    competence=extracted_period,
                    original_name=file_name,
                )
                register_stored_document(
                    company_id=int(process["company_id"]),
                    process_id=process_id,
                    kind=stored["kind"],
                    competence=stored["competence"],
                    original_name=stored["original_name"],
                    stored_path=stored["stored_path"],
                    sha256=stored["sha256"],
                    size_bytes=stored["size_bytes"],
                )
            append_process_event(
                process_id,
                "PGDAS_UPLOADED",
                f"PGDAS {competence} importado",
                {"file_name": file_name},
            )

        accepted_pgdas = list_accepted_pgdas(process_id)
        analysis_result = analyze_process(
            process["malha"],
            accepted_pgdas,
        )
        save_diagnostics(
            process_id,
            analysis_result["analyses"],
        )

        confirmations = list_analysis_confirmations(
            process_id
        )
        effective_confirmations = build_effective_confirmations(
            analysis_result,
            confirmations,
        )
        reflection_coverage = calculate_reflection_coverage(
            accepted_pgdas,
            effective_confirmations,
        )
        initial_plan_status = calculate_initial_plan_status(
            process,
            accepted_pgdas,
        )

        tax_engine_ready = (
            initial_plan_status["analysis_requests_complete"]
            and analysis_result["summary"]["awaiting_pgdas_count"] == 0
            and analysis_result["summary"]["review_required_count"] == 0
            and reflection_coverage["closed_months_complete"]
        )

        conclusions = list_accounting_study_conclusions(
            process_id
        )
        regularization_result = apply_study_conclusions(
            analysis_result,
            confirmations,
            conclusions,
        )
        tax_results = latest_tax_calculations(
            process_id
        )
        charge_results = latest_legal_charge_calculations(
            process_id
        )
        analysis_summary = build_process_summary(
            analysis_result=analysis_result,
            stored_confirmations=confirmations,
            regularization_result=regularization_result,
            tax_result=tax_results.get(
                EXPOSURE_SCENARIO
            ),
            legal_charges=charge_results.get(
                EXPOSURE_SCENARIO
            ),
            validated_tax_result=tax_results.get(
                VALIDATED_SCENARIO
            ),
            validated_legal_charges=charge_results.get(
                VALIDATED_SCENARIO
            ),
        )

        if tax_engine_ready:
            update_process_status(
                process_id,
                "READY_FOR_TAX_ENGINE",
            )
        elif not initial_plan_status[
            "analysis_requests_complete"
        ]:
            update_process_status(
                process_id,
                "AWAITING_ANALYSIS_PGDAS",
            )
        elif (
            analysis_result["summary"]["awaiting_pgdas_count"] == 0
            and analysis_result["summary"]["review_required_count"] > 0
        ):
            update_process_status(
                process_id,
                "AWAITING_EXCEPTION_REVIEW",
            )
        elif reflection_coverage["supplemental_requests"]:
            update_process_status(
                process_id,
                "AWAITING_REFLECTION_PGDAS",
            )

        return JSONResponse({
            "status": (
                "ACCEPTED"
                if accepted
                else "REJECTED"
            ),
            "process_id": process_id,
            "requested_competence": competence,
            "extracted_period": extracted_period,
            "competence_match": competence_match,
            "identity": identity,
            "accepted": accepted,
            "pgdas": pgdas,
            "analysis_result": analysis_result,
            "regularization_result": regularization_result,
            "accounting_study_conclusions": conclusions,
            "analysis_summary": analysis_summary,
            "reflection_coverage": reflection_coverage,
            "initial_plan_status": initial_plan_status,
            "tax_engine_ready": tax_engine_ready,
        })
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=(f"Não foi possível ler o Extrato ou "f"a Declaração do PGDAS-D: {error}"),
        ) from error
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _read_pgdas_content(
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            suffix=".pdf",
            delete=False,
        ) as temp:
            temp.write(content)
            temporary_path = Path(temp.name)

        pgdas = read_pgdas_pdf(temporary_path)
        pgdas["source_document"]["file_name"] = file_name
        period = pgdas.get("assessment", {}).get("period")

        if not period:
            raise ValueError("PA não identificado no PGDAS-D.")

        return {
            "file_name": file_name,
            "period": period,
            "pgdas": pgdas,
            "content": content,
            "status": "PARSED",
        }
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _refresh_process_after_pgdas_batch(
    process_id: int,
    process: dict[str, Any],
) -> None:
    accepted_pgdas = list_accepted_pgdas(process_id)
    analysis_result = analyze_process(
        process["malha"],
        accepted_pgdas,
    )
    save_diagnostics(
        process_id,
        analysis_result["analyses"],
    )

    confirmations = list_analysis_confirmations(
        process_id
    )
    effective_confirmations = build_effective_confirmations(
        analysis_result,
        confirmations,
    )
    reflection_coverage = calculate_reflection_coverage(
        accepted_pgdas,
        effective_confirmations,
    )
    initial_plan_status = calculate_initial_plan_status(
        process,
        accepted_pgdas,
    )

    tax_engine_ready = (
        initial_plan_status["analysis_requests_complete"]
        and analysis_result["summary"]["awaiting_pgdas_count"] == 0
        and analysis_result["summary"]["review_required_count"] == 0
        and reflection_coverage["closed_months_complete"]
    )

    if tax_engine_ready:
        update_process_status(
            process_id,
            "READY_FOR_TAX_ENGINE",
        )
    elif not initial_plan_status[
        "analysis_requests_complete"
    ]:
        update_process_status(
            process_id,
            "AWAITING_ANALYSIS_PGDAS",
        )
    elif (
        analysis_result["summary"]["awaiting_pgdas_count"] == 0
        and analysis_result["summary"]["review_required_count"] > 0
    ):
        update_process_status(
            process_id,
            "AWAITING_EXCEPTION_REVIEW",
        )
    elif reflection_coverage["supplemental_requests"]:
        update_process_status(
            process_id,
            "AWAITING_REFLECTION_PGDAS",
        )


@app.post("/api/upload-pgdas-auto")
async def upload_pgdas_auto(
    process_id: int,
    files: list[UploadFile] = File(...),
) -> JSONResponse:
    """Lê vários PGDAS em lote e associa cada PDF ao PA solicitado."""
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    process = ensure_current_pgdas_plan(process)

    if not files:
        raise HTTPException(
            status_code=400,
            detail="Arraste pelo menos um arquivo PGDAS-D.",
        )

    completed: list[dict[str, Any]] = []
    parse_candidates: list[tuple[str, bytes]] = []

    for upload in files:
        file_name = upload.filename or "pgdas.pdf"
        content = await upload.read()

        if Path(file_name).suffix.lower() != ".pdf":
            completed.append({
                "file_name": file_name,
                "status": "REJECTED",
                "detail": "O arquivo não é PDF.",
            })
            continue

        if not content:
            completed.append({
                "file_name": file_name,
                "status": "REJECTED",
                "detail": "O arquivo está vazio.",
            })
            continue

        if len(content) > MAX_FILE_SIZE:
            completed.append({
                "file_name": file_name,
                "status": "REJECTED",
                "detail": "O arquivo ultrapassa 20 MB.",
            })
            continue

        parse_candidates.append(
            (file_name, content)
        )

    parsed_results = await asyncio.gather(
        *[
            asyncio.to_thread(
                _read_pgdas_content,
                file_name,
                content,
            )
            for file_name, content in parse_candidates
        ],
        return_exceptions=True,
    )

    pending: list[dict[str, Any]] = []

    for candidate, result in zip(
        parse_candidates,
        parsed_results,
    ):
        file_name, _ = candidate

        if isinstance(result, Exception):
            completed.append({
                "file_name": file_name,
                "status": "REJECTED",
                "detail": (
                    "Não foi possível ler o PGDAS-D: "
                    f"{result}"
                ),
            })
            continue

        pending.append(result)

    while pending:
        accepted_pgdas = list_accepted_pgdas(process_id)
        analysis_result = analyze_process(
            process["malha"],
            accepted_pgdas,
        )
        confirmations = list_analysis_confirmations(
            process_id
        )
        effective = build_effective_confirmations(
            analysis_result,
            confirmations,
        )
        coverage = calculate_reflection_coverage(
            accepted_pgdas,
            effective,
        )

        requested = {
            item["requested_competence"]
            for item in process.get(
                "pgdas_plan",
                {},
            ).get("required_pgdas", [])
        }
        # O planejador inicial já contém a cobertura potencial completa.
        # Não são criadas novas solicitações durante o envio dos arquivos.

        accepted_periods = {
            item.get("assessment", {}).get("period")
            for item in accepted_pgdas
        }

        progress = False
        remaining: list[dict[str, Any]] = []

        for item in pending:
            period = item["period"]

            if period in accepted_periods:
                completed.append({
                    "file_name": item["file_name"],
                    "period": period,
                    "status": "ALREADY_RECEIVED",
                    "detail": "Este PA já estava concluído.",
                })
                progress = True
                continue

            if period not in requested:
                remaining.append(item)
                continue

            pgdas = item["pgdas"]
            identity = validate_pgdas_identity(
                process["company_cnpj"],
                pgdas,
            )
            accepted = identity["match"]

            save_pgdas_document(
                process_id=process_id,
                requested_competence=period,
                pgdas=pgdas,
                identity_status=identity["status"],
                competence_status="MATCH",
                accepted=accepted,
            )

            if accepted:
                if process.get("company_id"):
                    stored = store_document(
                        content=item["content"],
                        company_id=int(process["company_id"]),
                        process_id=process_id,
                        kind="PGDAS",
                        competence=period,
                        original_name=item["file_name"],
                    )
                    register_stored_document(
                        company_id=int(process["company_id"]),
                        process_id=process_id,
                        kind=stored["kind"],
                        competence=stored["competence"],
                        original_name=stored["original_name"],
                        stored_path=stored["stored_path"],
                        sha256=stored["sha256"],
                        size_bytes=stored["size_bytes"],
                    )
                append_process_event(
                    process_id,
                    "PGDAS_UPLOADED",
                    f"PGDAS {period} importado",
                    {"file_name": item["file_name"]},
                )

            completed.append({
                "file_name": item["file_name"],
                "period": period,
                "status": (
                    "ACCEPTED"
                    if accepted
                    else "REJECTED"
                ),
                "detail": (
                    "Documento identificado e associado automaticamente."
                    if accepted
                    else "O CNPJ não corresponde ao processo."
                ),
            })
            progress = True

        if not progress:
            for item in remaining:
                completed.append({
                    "file_name": item["file_name"],
                    "period": item["period"],
                    "status": "NOT_REQUESTED",
                    "detail": (
                        "O PA foi lido, mas não é um dos documentos "
                        "solicitados neste momento."
                    ),
                })
            break

        pending = remaining

    _refresh_process_after_pgdas_batch(
        process_id,
        process,
    )

    accepted_statuses = {
        "ACCEPTED",
        "ALREADY_RECEIVED",
    }
    accepted_count = sum(
        1
        for item in completed
        if item["status"] in accepted_statuses
    )

    return JSONResponse({
        "status": "PROCESSED",
        "results": completed,
        "accepted_count": accepted_count,
        "rejected_count": (
            len(completed) - accepted_count
        ),
    })


@app.get("/api/process/{process_id}/documents")
def process_documents(process_id: int) -> JSONResponse:
    try:
        get_process(process_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    documents = list_stored_documents(process_id)
    return JSONResponse({
        "documents": [
            {
                "id": item["id"],
                "kind": item["kind"],
                "competence": item["competence"],
                "original_name": item["original_name"],
                "created_at": item["created_at"],
                "size_bytes": item["size_bytes"],
                "status": item["status"],
                "download_url": f'/api/documents/{item["id"]}/download',
            }
            for item in documents
        ]
    })


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: int) -> FileResponse:
    try:
        document = get_stored_document(document_id)
        path = resolve_document_path(document["stored_path"])
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="O arquivo original não foi encontrado no armazenamento.",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document["original_name"],
    )


@app.get("/api/system/status")
def system_status() -> JSONResponse:
    return JSONResponse({
        "version": APP_VERSION,
        "database": database_status(),
        "data_directory": str(DATA_DIR),
        "documents_directory": str(DOCUMENTS_DIR),
    })


@app.get("/api/system/backup")
def system_backup() -> FileResponse:
    path = create_backup(APP_VERSION)
    logger.info("Backup criado em %s", path)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )


@app.post("/api/system/restore")
async def system_restore(
    file: UploadFile = File(...),
) -> JSONResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="O backup está vazio.")
    if len(content) > 1_000_000_000:
        raise HTTPException(
            status_code=413,
            detail="O backup ultrapassa o limite de 1 GB.",
        )
    try:
        manifest = validate_backup_bytes(content)
        result = restore_backup(content, APP_VERSION)
    except (ValueError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    logger.warning(
        "Backup restaurado. Origem: %s",
        manifest.get("created_at", "não informada"),
    )
    return JSONResponse({
        "status": "RESTORED",
        **result,
    })


@app.get("/api/system/support-bundle")
def system_support_bundle() -> FileResponse:
    path = create_support_bundle(APP_VERSION)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )


@app.get("/api/process/{process_id}")
def process_status(process_id: int) -> JSONResponse:
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    process = ensure_current_pgdas_plan(process)
    accepted_pgdas = list_accepted_pgdas(process_id)
    context = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )
    effective_confirmations = build_effective_confirmations(
        context["analysis_result"],
        context["confirmations"],
    )
    reflection_coverage = calculate_reflection_coverage(
        accepted_pgdas,
        effective_confirmations,
    )
    initial_plan_status = calculate_initial_plan_status(
        process,
        accepted_pgdas,
    )

    return JSONResponse({
        "process": process,
        "company": (
            get_company(process["company_id"])
            if process.get("company_id")
            else None
        ),
        "events": list_process_events(process_id),
        "accepted_pgdas": [
            {
                "period": item.get("assessment", {}).get("period"),
                "file_name": item.get("source_document", {}).get("file_name"),
                "document_type": item.get("source_document", {}).get("document_type"),
            }
            for item in accepted_pgdas
        ],
        "accepted_pgdas_count": len(
            accepted_pgdas_periods(process_id)
            & {
                item.get("requested_competence", "")
                for item in process.get("pgdas_plan", {}).get(
                    "required_pgdas", []
                )
            }
        ),
        "analysis_result": context["analysis_result"],
        "regularization_result": context[
            "regularization_result"
        ],
        "analysis_summary": context["analysis_summary"],
        "reflection_coverage": reflection_coverage,
        "initial_plan_status": initial_plan_status,
        "confirmations": context["confirmations"],
        "accounting_study_conclusions": context[
            "conclusions"
        ],
        "tax_calculations": context["tax_results"],
        "tax_profiles": list_tax_profiles(process_id),
        "legal_charge_calculations": context[
            "charge_results"
        ],
        "latest_client_report": latest_client_report(
            process_id
        ),
    })


@app.post("/api/confirm-analysis")
def confirm_analysis(
    process_id: int,
    competence: str,
    decision: str = "CONFIRMED",
    corrected_pgdas_revenue_cents: int | None = None,
) -> JSONResponse:
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    accepted_pgdas = list_accepted_pgdas(process_id)
    analysis_result = analyze_process(
        process["malha"],
        accepted_pgdas,
    )

    analysis = next(
        (
            item
            for item in analysis_result["analyses"]
            if item["competence"] == competence
        ),
        None,
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Competência não encontrada no processo.",
        )

    if analysis["status"] == "AWAITING_PGDAS":
        raise HTTPException(
            status_code=409,
            detail="Ainda falta PGDAS para esta competência.",
        )

    if analysis["status"] != "REVIEW_REQUIRED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Esta competência já foi analisada automaticamente "
                "e não exige intervenção."
            ),
        )

    if (
        corrected_pgdas_revenue_cents is not None
        and analysis.get("evidence", {}).get("pgdas_imported")
    ):
        if corrected_pgdas_revenue_cents < 0:
            raise HTTPException(
                status_code=400,
                detail="A receita confirmada não pode ser negativa.",
            )

        imported_revenue = (
            analysis["evidence"]["pgdas_imported"]
            ["declared_revenue_cents"]
        )
        increment = max(
            0,
            corrected_pgdas_revenue_cents - imported_revenue,
        )

        analysis["recommendation"][
            "simulation_pgdas_revenue_cents"
        ] = corrected_pgdas_revenue_cents
        analysis["recommendation"][
            "simulation_pgdas_increment_cents"
        ] = increment

        # Aliases mantidos para compatibilidade.
        analysis["recommendation"][
            "corrected_pgdas_revenue_cents"
        ] = corrected_pgdas_revenue_cents
        analysis["recommendation"][
            "pgdas_increment_cents"
        ] = increment
        analysis["recommendation"][
            "calculate_direct_tax"
        ] = increment > 0
        analysis["recommendation"][
            "calculate_rbt12_reflections"
        ] = increment > 0

        analysis["actions"] = [
            action
            for action in analysis.get("actions", [])
            if action["action"] not in {
                "RECTIFY_PGDAS",
                "SIMULATE_PGDAS_EXPOSURE",
                "CALCULATE_DIRECT_TAX",
                "CALCULATE_RBT12_REFLECTIONS",
                "VALIDATE_DOCUMENTS_BEFORE_REGULARIZATION",
            }
        ]

        if increment > 0:
            analysis["actions"].extend([
                {
                    "action": "SIMULATE_PGDAS_EXPOSURE",
                    "amount_cents": increment,
                    "simulation_target_cents": (
                        corrected_pgdas_revenue_cents
                    ),
                },
                {"action": "CALCULATE_DIRECT_TAX"},
                {"action": "CALCULATE_RBT12_REFLECTIONS"},
                {
                    "action": (
                        "VALIDATE_DOCUMENTS_BEFORE_"
                        "REGULARIZATION"
                    ),
                },
            ])

        analysis["simulation_override"] = {
            "simulation_pgdas_revenue_cents": (
                corrected_pgdas_revenue_cents
            ),
            "simulation_pgdas_increment_cents": (
                increment
            ),
            "description": (
                "Valor definido após resolver conflito entre "
                "as fontes. Não representa automaticamente a "
                "regularização definitiva."
            ),
        }

        segregation = analysis.get("segregation", {})
        type_17 = segregation.get("type_17", {})
        consolidated = segregation.get(
            "consolidated",
            {},
        )
        type_17[
            "simulation_target_cents"
        ] = corrected_pgdas_revenue_cents
        type_17[
            "simulation_increment_cents"
        ] = increment
        type_17[
            "recommended_increment_cents"
        ] = increment
        consolidated[
            "simulation_revenue_cents"
        ] = corrected_pgdas_revenue_cents
        consolidated[
            "simulation_tax_base_increment_cents"
        ] = increment
        consolidated[
            "tax_base_increment_cents"
        ] = increment

    save_analysis_confirmation(
        process_id=process_id,
        competence=competence,
        decision=decision,
        analysis=analysis,
    )

    confirmations = list_analysis_confirmations(process_id)
    required = {
        item["competence"]
        for item in analysis_result["analyses"]
        if item["requires_review"]
    }
    confirmed = {
        item["competence"]
        for item in confirmations
        if item["decision"] == "CONFIRMED"
    }

    effective_confirmations = build_effective_confirmations(
        analysis_result,
        confirmations,
    )
    reflection_coverage = calculate_reflection_coverage(
        accepted_pgdas,
        effective_confirmations,
    )
    initial_plan_status = calculate_initial_plan_status(
        process,
        accepted_pgdas,
    )
    reviews_resolved = required.issubset(confirmed)
    tax_engine_ready = (
        initial_plan_status["analysis_requests_complete"]
        and reviews_resolved
        and reflection_coverage["closed_months_complete"]
    )

    if tax_engine_ready:
        update_process_status(
            process_id,
            "READY_FOR_TAX_ENGINE",
        )
    elif reflection_coverage["supplemental_requests"]:
        update_process_status(
            process_id,
            "AWAITING_REFLECTION_PGDAS",
        )

    conclusions = list_accounting_study_conclusions(
        process_id
    )
    regularization_result = apply_study_conclusions(
        analysis_result,
        confirmations,
        conclusions,
    )
    tax_results = latest_tax_calculations(
        process_id
    )
    charge_results = latest_legal_charge_calculations(
        process_id
    )
    analysis_summary = build_process_summary(
        analysis_result=analysis_result,
        stored_confirmations=confirmations,
        regularization_result=regularization_result,
        tax_result=tax_results.get(
            EXPOSURE_SCENARIO
        ),
        legal_charges=charge_results.get(
            EXPOSURE_SCENARIO
        ),
        validated_tax_result=tax_results.get(
            VALIDATED_SCENARIO
        ),
        validated_legal_charges=charge_results.get(
            VALIDATED_SCENARIO
        ),
    )

    return JSONResponse({
        "status": "REVIEW_RESOLVED",
        "analysis_summary": analysis_summary,
        "regularization_result": regularization_result,
        "competence": competence,
        "decision": decision,
        "resolved_count": len(confirmed),
        "required_count": len(required),
        "all_reviews_resolved": reviews_resolved,
        "all_required_confirmed": reviews_resolved,
        "reflection_coverage": reflection_coverage,
        "initial_plan_status": initial_plan_status,
        "tax_engine_ready": tax_engine_ready,
    })



@app.get("/api/accounting-study")
def accounting_study_disabled() -> JSONResponse:
    return JSONResponse(
        {
            "status": "DISABLED",
            "detail": "O estudo contábil não faz parte da beta comercial atual.",
        },
        status_code=410,
    )


@app.get("/api/tax-setup")
def tax_setup(
    process_id: int,
    scenario: str = EXPOSURE_SCENARIO,
) -> JSONResponse:
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    if scenario not in {
        EXPOSURE_SCENARIO,
        VALIDATED_SCENARIO,
    }:
        raise HTTPException(
            status_code=400,
            detail="Cenário tributário inválido.",
        )

    accepted_pgdas = list_accepted_pgdas(
        process_id
    )
    context = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )

    try:
        scenario_confirmations = (
            build_scenario_confirmations(
                context["regularization_result"],
                scenario,
            )
        )
    except AccountingStudyError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    reflection_coverage = (
        calculate_reflection_coverage(
            accepted_pgdas,
            scenario_confirmations,
        )
    )
    profiles = list_tax_profiles(process_id)

    setup = build_tax_setup(
        pgdas_documents=accepted_pgdas,
        confirmations=scenario_confirmations,
        calculation_end_competence=(
            reflection_coverage[
                "actual_calculation_end"
            ]
        ),
        full_reflection_end_competence=(
            reflection_coverage[
                "full_reflection_end"
            ]
        ),
        future_pending_competences=(
            reflection_coverage[
                "future_pending_competences"
            ]
        ),
        scenario=scenario,
        saved_profile=None,
    )
    saved_profile = profiles.get(scenario)
    setup["saved_profile"] = (
        saved_profile
        if saved_profile
        and saved_profile.get("version") == PROFILE_CODE
        else None
    )

    return JSONResponse({
        **setup,
        "reflection_coverage": reflection_coverage,
    })


@app.post("/api/calculate-tax")
def calculate_tax(
    request: TaxCalculationRequest,
) -> JSONResponse:
    process_id = request.process_id
    scenario = request.scenario
    annex = request.annex

    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    if scenario not in {
        EXPOSURE_SCENARIO,
        VALIDATED_SCENARIO,
    }:
        raise HTTPException(
            status_code=400,
            detail="Cenário tributário inválido.",
        )

    accepted_pgdas = list_accepted_pgdas(process_id)
    initial_plan_status = calculate_initial_plan_status(
        process,
        accepted_pgdas,
    )

    if not initial_plan_status["analysis_requests_complete"]:
        missing = ", ".join(
            initial_plan_status[
                "missing_analysis_competences"
            ]
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Envie os PGDAS solicitados para análise ou conferência "
                f"das competências: {missing}."
            ),
        )

    context = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )
    analysis_result = context["analysis_result"]

    required = {
        item["competence"]
        for item in analysis_result["analyses"]
        if item["requires_review"]
    }
    confirmed = {
        item["competence"]
        for item in context["confirmations"]
        if item["decision"] == "CONFIRMED"
    }

    if required and not required.issubset(confirmed):
        raise HTTPException(
            status_code=409,
            detail=(
                "Resolva as divergências de fontes antes do "
                "cálculo tributário."
            ),
        )

    try:
        scenario_confirmations = build_scenario_confirmations(
            context["regularization_result"],
            scenario,
        )
    except AccountingStudyError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    reflection_coverage = calculate_reflection_coverage(
        accepted_pgdas,
        scenario_confirmations,
    )

    if not reflection_coverage["closed_months_complete"]:
        requested = ", ".join(
            item["requested_competence"]
            for item in reflection_coverage[
                "supplemental_requests"
            ]
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Envie o PGDAS complementar "
                f"{requested} para calcular os reflexos dos "
                "meses já vencidos."
            ),
        )

    try:
        result = calculate_hidden_reflections(
            pgdas_documents=accepted_pgdas,
            confirmations=scenario_confirmations,
            annex=annex,
            standard_profile_confirmed=(
                request.standard_profile_confirmed
            ),
            calculation_end_competence=(
                reflection_coverage[
                    "actual_calculation_end"
                ]
            ),
            full_reflection_end_competence=(
                reflection_coverage[
                    "full_reflection_end"
                ]
            ),
            future_pending_competences=(
                reflection_coverage[
                    "future_pending_competences"
                ]
            ),
            scenario=scenario,
        )
    except TaxEngineError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    save_tax_profile(
        process_id=process_id,
        scenario=scenario,
        profile={"version": "SINGLE_ANNEX_ESTIMATE_V1", "annex": annex},
    )
    calculation_id = save_tax_calculation(
        process_id=process_id,
        annex=annex,
        profile="STANDARD_FULL_REVENUE",
        calculation=result,
        scenario=scenario,
    )

    update_process_status(
        process_id,
        (
            "VALIDATED_TAX_CALCULATED"
            if scenario == VALIDATED_SCENARIO
            else "EXPOSURE_TAX_CALCULATED"
        ),
    )
    append_process_event(
        process_id,
        "TAX_CALCULATED",
        f"Estimativa calculada pelo Anexo {annex}",
        {
            "scenario": scenario,
            "estimated_total_cents": result.get("summary", {}).get("estimated_total_cents", 0),
        },
    )

    refreshed = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )

    return JSONResponse({
        "status": "CALCULATED",
        "scenario": scenario,
        "calculation_id": calculation_id,
        "tax_result": result,
        "tax_profile": {"version": "SINGLE_ANNEX_ESTIMATE_V1", "annex": annex},
        "analysis_summary": refreshed[
            "analysis_summary"
        ],
        "regularization_result": refreshed[
            "regularization_result"
        ],
    })


@app.post("/api/calculate-legal-charges")
def calculate_legal_charges_endpoint(
    process_id: int,
    update_date: str,
    scenario: str = EXPOSURE_SCENARIO,
) -> JSONResponse:
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    if scenario not in {
        EXPOSURE_SCENARIO,
        VALIDATED_SCENARIO,
    }:
        raise HTTPException(
            status_code=400,
            detail="Cenário tributário inválido.",
        )

    tax_result = latest_tax_calculation(
        process_id,
        scenario,
    )

    if tax_result is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Calcule primeiro o imposto e os reflexos "
                "deste cenário."
            ),
        )

    accepted_pgdas = list_accepted_pgdas(process_id)

    try:
        result = calculate_legal_charges(
            tax_result=tax_result,
            pgdas_documents=accepted_pgdas,
            update_date_text=update_date,
        )
    except LegalChargesError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    result.setdefault("source", {})[
        "scenario"
    ] = scenario

    calculation_id = save_legal_charge_calculation(
        process_id=process_id,
        update_date=update_date,
        calculation=result,
        scenario=scenario,
    )

    update_process_status(
        process_id,
        (
            "VALIDATED_LEGAL_CHARGES_CALCULATED"
            if scenario == VALIDATED_SCENARIO
            else "EXPOSURE_LEGAL_CHARGES_CALCULATED"
        ),
    )
    append_process_event(
        process_id,
        "LEGAL_CHARGES_CALCULATED",
        "Multa e juros atualizados",
        {"update_date": update_date, "scenario": scenario},
    )

    refreshed = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )

    return JSONResponse({
        "status": "CALCULATED",
        "scenario": scenario,
        "calculation_id": calculation_id,
        "legal_charges": result,
        "analysis_summary": refreshed[
            "analysis_summary"
        ],
    })


@app.get(
    "/api/client-report",
    response_class=HTMLResponse,
)
def client_report(
    process_id: int,
    scenario: str = "AUTO",
) -> HTMLResponse:
    try:
        process = get_process(process_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    if scenario == "AUTO":
        validated_tax = latest_tax_calculation(
            process_id,
            VALIDATED_SCENARIO,
        )
        validated_charges = (
            latest_legal_charge_calculation(
                process_id,
                VALIDATED_SCENARIO,
            )
        )
        selected_scenario = (
            VALIDATED_SCENARIO
            if validated_tax is not None
            and validated_charges is not None
            else EXPOSURE_SCENARIO
        )
    else:
        selected_scenario = scenario

    if selected_scenario not in {
        EXPOSURE_SCENARIO,
        VALIDATED_SCENARIO,
    }:
        raise HTTPException(
            status_code=400,
            detail="Cenário de relatório inválido.",
        )

    tax_result = latest_tax_calculation(
        process_id,
        selected_scenario,
    )
    legal_charges = latest_legal_charge_calculation(
        process_id,
        selected_scenario,
    )

    if tax_result is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Calcule primeiro o imposto e os reflexos "
                "do cenário selecionado."
            ),
        )

    if legal_charges is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Calcule primeiro a multa e os juros "
                "do cenário selecionado."
            ),
        )

    accepted_pgdas = list_accepted_pgdas(process_id)
    context = build_analysis_context(
        process_id,
        process,
        accepted_pgdas,
    )

    analysis_for_report = {
        "summary": context["analysis_result"]["summary"],
        "analyses": context[
            "regularization_result"
        ]["analyses"],
    }

    model = build_report_model(
        process=process,
        analysis_result=analysis_for_report,
        stored_confirmations=[],
        tax_result=tax_result,
        legal_charges=legal_charges,
    )
    model["scenario"] = selected_scenario

    save_client_report(
        process_id=process_id,
        update_date=(
            legal_charges.get("source", {})
            .get("update_date", "")
        ),
        report=model,
    )

    update_process_status(
        process_id,
        "CLIENT_REPORT_GENERATED",
    )
    append_process_event(
        process_id,
        "CLIENT_REPORT_GENERATED",
        "Relatório do cliente gerado",
        {"scenario": scenario},
    )

    return HTMLResponse(
        render_client_report(model),
        headers={
            "Cache-Control": "no-store",
        },
    )

