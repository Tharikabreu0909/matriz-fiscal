from readers.pgdas_reader import (
    detect_document_type,
    parse_destinations_and_payment,
)


def test_document_classifier():
    assert detect_document_type(
        "Extrato do Simples Nacional"
    ) == "PGDAS_EXTRACT"

    assert detect_document_type(
        "Programa Gerador do Documento de Arrecadação\n"
        "do Simples Nacional - Declaratório"
    ) == "PGDAS_DECLARATION"


def test_split_destination_and_payment_tables():
    tables = [
        [
            [
                "Tributo",
                None,
                "Valor",
                None,
                None,
                "Ente Federativo de Destino",
            ],
            [
                "IRPJ",
                None,
                "143,32",
                None,
                None,
                "União",
            ],
            [
                "CSLL",
                None,
                "91,20",
                None,
                None,
                "União",
            ],
        ],
        [
            ["COFINS", "331,97", "União"],
            [
                "6.2) Informações da Arrecadação "
                "do DAS gerado nesta apuração",
                "",
                "",
            ],
            [
                "Data de Pagamento",
                "Banco/Agência de Arrecadação",
                "Valor Pago",
            ],
            [
                "20/07/2026",
                "341/1498",
                "2.605,74",
            ],
        ],
    ]

    destinations, payment = (
        parse_destinations_and_payment(tables)
    )

    assert len(destinations) == 3
    assert destinations[2]["tribute"] == "COFINS"
    assert payment["payment_date"] == "20/07/2026"
    assert payment["paid_cents"] == 260_574
