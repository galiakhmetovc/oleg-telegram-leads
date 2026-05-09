from app.application.evaluation.review_eval import ReviewEvalRow
from app.application.evaluation.review_eval import build_review_eval_report, expected_lead_from_verdict


def test_expected_lead_from_verdict_maps_review_ground_truth() -> None:
    assert expected_lead_from_verdict("lead") is True
    assert expected_lead_from_verdict("not_lead") is False
    assert expected_lead_from_verdict("noise") is False
    assert expected_lead_from_verdict("uncertain") is None
    assert expected_lead_from_verdict(None) is None


def test_build_review_eval_report_counts_confusion_matrix_and_examples() -> None:
    report = build_review_eval_report(
        [
            ReviewEvalRow(
                source_message_id="tp",
                telegram_message_id=1,
                source_chat_title="Designers",
                verdict="lead",
                predicted_is_lead=True,
                score=90,
                temperature="hot",
                review_lane="direct_pur_lead",
                text="Нужен умный дом",
            ),
            ReviewEvalRow(
                source_message_id="fn",
                telegram_message_id=2,
                source_chat_title="Designers",
                verdict="lead",
                predicted_is_lead=False,
                score=10,
                temperature="cold",
                review_lane="other_candidate",
                text="Нужен подрядчик на видеонаблюдение",
            ),
            ReviewEvalRow(
                source_message_id="fp",
                telegram_message_id=3,
                source_chat_title="Support",
                verdict="noise",
                predicted_is_lead=True,
                score=80,
                temperature="hot",
                review_lane="direct_pur_lead",
                text="Продам камеру",
            ),
            ReviewEvalRow(
                source_message_id="tn",
                telegram_message_id=4,
                source_chat_title="Support",
                verdict="not_lead",
                predicted_is_lead=False,
                score=0,
                temperature="none",
                review_lane="noise",
                text="Обычный бытовой вопрос",
            ),
            ReviewEvalRow(
                source_message_id="skip",
                telegram_message_id=5,
                source_chat_title="Support",
                verdict="uncertain",
                predicted_is_lead=True,
                score=40,
                temperature="warm",
                review_lane="research_warm",
                text="Сомнительно",
            ),
        ]
    )

    assert report.reviewed == 5
    assert report.evaluated == 4
    assert report.skipped_uncertain == 1
    assert report.true_positive == 1
    assert report.false_negative == 1
    assert report.false_positive == 1
    assert report.true_negative == 1
    assert report.precision == 0.5
    assert report.recall == 0.5
    assert report.specificity == 0.5
    assert report.accuracy == 0.5
    assert report.f1 == 0.5
    assert report.by_verdict == {"lead": 2, "noise": 1, "not_lead": 1, "uncertain": 1}
    assert report.false_positives[0]["source_message_id"] == "fp"
    assert report.false_negatives[0]["source_message_id"] == "fn"
