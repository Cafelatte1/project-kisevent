"""구조화 스키마 v1(docs/event-page-research.md §6.3)과 에이전트용 안내문."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 1


class Period(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["신청", "거래", "자산유지", "지급", "추첨", "공모"]
    start: str | None = None
    end: str | None = None
    note: str | None = None


class Targets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    account_types: list[Literal["영업점", "뱅키스", "연금"]]
    customer_types: list[Literal["전체", "신규", "휴면", "기존", "미성년"]]
    conditions: list[str] = []


class Lottery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    winners: int | None = None
    note: str | None = None


class Benefit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    reward_type: Literal["현금", "쿠폰", "상품권", "경품", "수수료할인", "추첨", "축하금"]
    reward: str
    reward_amount_krw: int | None = None
    conditions: list[str] = []
    cap: str | None = None
    lottery: Lottery | None = None
    caveats: list[str] = []
    examples: list[str] = []


class Participation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requires_application: bool
    auto_enroll: bool
    channels: list[str] = []
    steps: list[str] = []
    consents: list[str] = []


class Payout(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timing: str | None = None
    method: str | None = None


class Compliance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


class Confidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overall: float
    unreadable: list[str] = []


class AnalysisV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    tagline: str | None = None
    periods: list[Period]
    targets: Targets
    max_benefit_krw: int | None = None
    benefits: list[Benefit]
    participation: Participation
    products: list[
        Literal[
            "국내주식",
            "해외주식",
            "선물옵션",
            "ELS·ELB",
            "펀드",
            "채권",
            "RP",
            "ISA",
            "연금",
            "계좌개설",
            "OpenAPI",
        ]
    ]
    payout: Payout = Payout()
    exclusions: list[str] = []
    tax_note: str | None = None
    notes: list[str] = []
    compliance: Compliance = Compliance()
    contact: str | None = None
    confidence: Confidence


SCHEMA_GUIDE = """[schema_version 1 구조화 안내]
- 전사문을 읽고 아래 필드를 채운 JSON을 save_analysis(image_id, analysis, summary)로 저장한다.
- periods[].type: 신청|거래|자산유지|지급|추첨|공모. 목록의 기간은 '신청'이며, 이미지에만 있는 자산유지·지급 기간을 추가한다. 날짜는 YYYY-MM-DD, 연도가 없으면 목록 기간의 연도를 쓴다.
- targets.account_types: 영업점|뱅키스|연금 — 목록 탭(list_targets)이 1차 진실이고, 이미지가 더 좁히면('관리점이 영업점인 계좌만') 그 문장을 targets.conditions에 넣는다. customer_types: 전체|신규|휴면|기존|미성년.
- benefits[]: [혜택 n] 블록마다 하나. reward_type: 현금|쿠폰|상품권|경품|수수료할인|추첨|축하금. 금액 필드는 원 단위 정수, '약 97만원 상당' 같은 환산치는 reward 문장에만 두고 숫자는 null. 빨간 글씨 감액·제외 조건은 caveats.
- participation: 별도 신청 없이 자동 참여면 auto_enroll=true, requires_application=false. channels에는 이미지의 신청 경로와 list_actions(HTML 버튼 텍스트)를 합친다.
- products: 국내주식|해외주식|선물옵션|ELS·ELB|펀드|채권|RP|ISA|연금|계좌개설|OpenAPI 중 해당하는 것 전부.
- notes: 유의사항 중 답변에 쓸 핵심 5개 이내(세금·지급 시기·잔고 유지·경품 변경 등). 전문은 전사문에 남아 있다.
- compliance: '준법감시인 심사필 제YYYY-NNNN호(기간)'에서 추출.
- confidence.overall 0~1, 읽지 못한 구간은 unreadable에 문장으로.
- summary: 대상 + 핵심 혜택 + 신청 기간을 담은 200자 이내 한 문장. list_events에 그대로 실린다."""
