from src.credit_classifier import classify_by_score, score_transaction


def test_positive_credit_score():
    score = score_transaction(
        description="PIX RECEBIDO DE JOAO",
        amount=1200.0,
        detected_as_credit=True,
        detected_as_debit=False,
        has_plus_sign=False,
        has_minus_sign=False,
    )
    result = classify_by_score(score)
    assert result.status == "considerado"
