"""리서치 §6.3 예시가 스키마 v1을 통과하고, 통제 어휘 밖 값은 막히는지 확인한다."""

import pytest
from pydantic import ValidationError

from backend.mcp.schema import AnalysisV1

EXAMPLE = {
    "title": "국내주식 자산입고 이벤트 한투로 가져오기",
    "tagline": "최대 421만원 혜택 *조건 충족시",
    "periods": [
        {"type": "신청", "start": "2026-09-01", "end": "2026-10-30"},
        {"type": "자산유지", "start": None, "end": "2026-11-30"},
    ],
    "targets": {
        "account_types": ["뱅키스"],
        "customer_types": ["전체"],
        "conditions": ["타사에서 국내주식 입고", "이벤트 기간 내 1천만원 이상 거래"],
    },
    "max_benefit_krw": 4210000,
    "benefits": [
        {
            "name": "순입고 리워드",
            "reward_type": "현금",
            "reward": "순입고 1천만원당 4만원",
            "reward_amount_krw": 4000000,
            "conditions": [
                "순입고 = 총 타사입고 - 총 타사출고 - 당사 타명의계좌출고",
                "이벤트 기간 내 1천만원 이상 거래 필수",
                "잔고 유지 필수",
            ],
            "cap": "최대 400만원",
            "lottery": None,
            "caveats": ["뱅키스계좌 외 영업점계좌 이체도 감액 대상", "매도 후 출금 시 순출금액만큼 차감"],
            "examples": ["순입고 1,250만원 + 거래 1천만원 이상 → 4만원"],
        },
        {
            "name": "추첨 경품",
            "reward_type": "추첨",
            "reward": "50명 추첨 (총 100명 대상)",
            "reward_amount_krw": None,
            "conditions": [],
            "cap": None,
            "lottery": {"winners": 100, "note": "50명 × 2회"},
            "caveats": [],
            "examples": [],
        },
    ],
    "participation": {
        "requires_application": True,
        "auto_enroll": False,
        "channels": ["한국투자앱 → 혜택"],
        "steps": ["뱅키스 계좌 준비(미보유 시 비대면 개설)", "거래 증권사에 출고 요청", "뱅키스로 거래"],
        "consents": ["개인정보 수집·이용·제공 동의"],
    },
    "products": ["국내주식"],
    "payout": {"timing": None, "method": None},
    "exclusions": ["IRP·개인연금 계좌 내 가입분"],
    "tax_note": "총 수령금액 5만원 초과 시 제세공과금(22%) 당사 부담, 기타소득 귀속",
    "notes": ["ETF 거래비용 별도", "정상수수료 0.0130527%~0.0140527%"],
    "compliance": {
        "number": "제2026-1704호",
        "valid_from": "2026-09-01",
        "valid_to": "2026-10-30",
    },
    "contact": "1544-5000",
    "confidence": {"overall": 0.9, "unreadable": []},
}


def test_research_example_validates():
    analysis = AnalysisV1.model_validate(EXAMPLE)

    assert analysis.targets.account_types == ["뱅키스"]
    assert analysis.benefits[1].lottery.winners == 100
    assert analysis.max_benefit_krw == 4210000


def test_targets_required():
    payload = {key: value for key, value in EXAMPLE.items() if key != "targets"}

    with pytest.raises(ValidationError):
        AnalysisV1.model_validate(payload)


def test_reward_type_vocabulary():
    payload = {**EXAMPLE, "benefits": [{**EXAMPLE["benefits"][0], "reward_type": "포인트"}]}

    with pytest.raises(ValidationError):
        AnalysisV1.model_validate(payload)
