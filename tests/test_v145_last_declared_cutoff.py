from datetime import date
from pathlib import Path

import database
from readers.malha_reader import read_malha_pdf
from services.pgdas_planner import calculate_required_pgdas, adapt_plan_to_last_transmitted


def test_cutoff_replaces_future_document_requests_and_preserves_2026_notices():
    malha = read_malha_pdf(Path('/mnt/data/MALHA FISCAL RF(1).pdf'))
    base = calculate_required_pgdas(malha, as_of_date=date(2026, 10, 21))
    plan = adapt_plan_to_last_transmitted(base, '02/2026')
    assert all(int(row['requested_competence'][3:]) * 12 + int(row['requested_competence'][:2]) <= 2026 * 12 + 2 for row in plan['required_pgdas'])
    assert '06/2026' in plan['assumed_not_declared_competences']
    assert '01/2026' not in plan['assumed_not_declared_competences']
    assert any(r['requested_competence'] == '02/2026' for r in plan['required_pgdas'])
    assert plan['declared_zero_hypothesis_only'] is True
    assert plan['summary']['type_17_month_count'] == 4
    assert plan['validation']['status'] == 'VALID'


def test_year_range_and_process_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'cutoff.db')
    database.init_db()
    company = database.create_company(cnpj='39588299000182', legal_name='Teste último PGDAS')
    malha = read_malha_pdf(Path('/mnt/data/MALHA FISCAL RF(1).pdf'))
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 10, 21))
    pid = database.create_process(malha=malha, pgdas_plan=plan, company_cnpj='39588299000182',company_id=company)
    database.set_last_transmitted_pgdas(pid, '02/2026')
    assert database.get_last_transmitted_pgdas(pid) == '02/2026'
    database.init_db()  # migration must also work after reinitialization
    assert database.get_last_transmitted_pgdas(pid) == '02/2026'
    database.set_last_transmitted_pgdas(pid, None)
    assert database.get_last_transmitted_pgdas(pid) is None
