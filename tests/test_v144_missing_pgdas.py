from pathlib import Path
from unittest.mock import patch

import database
from app import app
from fastapi.testclient import TestClient


def test_marking_missing_declarations_and_partial_report(tmp_path):
    with patch.object(database, 'DB_PATH', tmp_path / 'fresh.sqlite'):
        database.init_db()
        malha = {
            'contributor': {'legal_name': 'Teste Fiscal', 'cfdf': '123'},
            'source_document': {'file_name': 'malha.pdf'},
            'work_months': [
                {'competence': '12/2025', 'notices': [
                    {'type_code': '17', 'informed_cents': 25258859,
                     'considered_cents': 50836920, 'divergence_cents': 25578061}]},
                {'competence': '06/2026', 'notices': [
                    {'type_code': '17', 'informed_cents': 0,
                     'considered_cents': 1773600, 'divergence_cents': 1773600}]},
            ],
        }
        plan = {'required_pgdas': [
            {'requested_competence': '06/2026'},
            {'requested_competence': '09/2026'},
        ]}
        pid = database.create_process(malha, plan, '000')
        client = TestClient(app)
        response = client.post(f'/api/process/{pid}/pgdas-situation', json={
            'competence': '06/2026', 'status': 'NOT_DECLARED'})
        assert response.status_code == 200, response.text
        assert database.list_pgdas_missing_status(pid) == {'06/2026': 'NOT_DECLARED'}
        report = client.get(f'/api/process/{pid}/partial-report')
        assert report.status_code == 200
        assert '255.780,61' in report.text
        assert '12/2025' in report.text and '06/2026' in report.text
        assert 'Não declarado' in report.text
        invalid = client.post(f'/api/process/{pid}/pgdas-situation', json={
            'competence': '12/2025', 'status': 'NOT_DECLARED'})
        assert invalid.status_code == 400
