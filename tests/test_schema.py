"""리서치 §7.3 예시가 스키마 v2를 통과하고, 통제 어휘 밖 값은 막히는지 확인한다."""

import pytest
from pydantic import ValidationError

from backend.mcp.schema import SummaryV2

SUMMARY_EXAMPLE = {
    "analysis": (
        "히어로 아래 정보 블록에 '이벤트 기간 2026.9.1~10.30'과 '참여대상 BanKIS 주식계좌(01) 보유 고객'이 있다."
        " 대상 줄 밑 회색 소문에 '#영업점 계좌 제외'가 붙어 있어 대상은 뱅키스로 판단했다."
        " 같은 블록의 '대상 종목'과 '실적 인정' 칸에 국내주식 범위와 순입고 산식이 적혀 있고,"
        " 자산유지 기한 11/30은 기간 줄 옆 괄호에 있다."
    ),
    "target": {
        "types": ["뱅키스"],
        "text": "BanKIS 주식계좌(01) 보유 고객",
        "conditions": ["이벤트 신청", "마케팅 동의 필수"],
        "exclusions": ["영업점 계좌"],
    },
    "criteria": {
        "text": (
            "대상 종목 국내주식(KOSPI·KOSDAQ·K-OTC·코넥스, ETF·ETN·ELW 제외)"
            " / 순입고금액 = 기간 내 총입고-총출고, 순출금 감액 / 2026-11-30까지 자산유지"
        ),
        "products": ["국내주식"],
        "performance": "1천만원 이상 타사대체 순입고 + 1천만원 이상 거래 + 11/30까지 자산유지",
    },
    "block_found": True,
}


def test_summary_example_validates():
    summary = SummaryV2.model_validate(SUMMARY_EXAMPLE)

    assert summary.target.types == ["뱅키스"]
    assert summary.criteria.products == ["국내주식"]
    assert summary.block_found is True


def test_block_found_requires_target_text():
    payload = {**SUMMARY_EXAMPLE, "target": {"types": ["뱅키스"], "text": ""}}

    with pytest.raises(ValidationError):
        SummaryV2.model_validate(payload)


def test_summary_without_block_allows_empty_target():
    summary = SummaryV2.model_validate({"analysis": "블록을 찾지 못했다", "block_found": False})

    assert summary.target.types == []
    assert summary.criteria is None


def test_target_type_vocabulary():
    payload = {**SUMMARY_EXAMPLE, "target": {**SUMMARY_EXAMPLE["target"], "types": ["온라인"]}}

    with pytest.raises(ValidationError):
        SummaryV2.model_validate(payload)
