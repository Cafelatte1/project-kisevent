"""구조화 스키마 v1(docs/event-page-research.md §6.3)·요약 스키마 v2(§7.3)와 에이전트용 안내문."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 2

Product = Literal[
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
    products: list[Product]
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
- targets.account_types: 영업점|뱅키스|연금 — 제목과 이미지 문구만으로 판단한다(요약 v2의 target.types와 같은 기준). 이미지가 더 좁히면('관리점이 영업점인 계좌만') 그 문장을 targets.conditions에 넣는다.
- benefits[]: [혜택 n] 블록마다 하나. reward_type: 현금|쿠폰|상품권|경품|수수료할인|추첨|축하금. 금액 필드는 원 단위 정수, '약 97만원 상당' 같은 환산치는 reward 문장에만 두고 숫자는 null. 빨간 글씨 감액·제외 조건은 caveats.
- participation: 별도 신청 없이 자동 참여면 auto_enroll=true, requires_application=false. channels에는 이미지의 신청 경로와 list_actions(HTML 버튼 텍스트)를 합친다.
- products: 국내주식|해외주식|선물옵션|ELS·ELB|펀드|채권|RP|ISA|연금|계좌개설|OpenAPI 중 해당하는 것 전부.
- notes: 유의사항 중 답변에 쓸 핵심 5개 이내(세금·지급 시기·잔고 유지·경품 변경 등). 전문은 전사문에 남아 있다.
- compliance: '준법감시인 심사필 제YYYY-NNNN호(기간)'에서 추출.
- confidence.overall 0~1, 읽지 못한 구간은 unreadable에 문장으로.
- summary: 대상 + 핵심 혜택 + 신청 기간을 담은 200자 이내 한 문장. list_events에 그대로 실린다."""


class TargetV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    types: list[Literal["영업점", "뱅키스", "연금"]] = []
    text: str = ""
    conditions: list[str] = []
    exclusions: list[str] = []


class CriteriaV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    products: list[Product] = []
    performance: str | None = None


class SummaryV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    analysis: str
    target: TargetV2 = TargetV2()
    criteria: CriteriaV2 | None = None
    block_found: bool

    @model_validator(mode="after")
    def _block_requires_target(self) -> "SummaryV2":
        if self.block_found and not self.target.text.strip():
            raise ValueError("block_found가 true면 target.text가 필요합니다")
        return self


SUMMARY_GUIDE = """[schema_version 2 요약 안내]
- 타일은 배너 상단의 정보 블록 구간(제목 아래 ~ 첫 이벤트 섹션)이다. 제목은 이미지에 없을 수 있으니 목록 title을 참고한다. 라벨은 '이벤트 기간/참가 신청/대회 기간', '참여대상/이벤트 대상/대상 고객/참가 대상' 등으로 흔들리니 라벨이 아니라 내용으로 판단한다.
- analysis: 어떤 문구를 보고 기간·대상·기준을 판단했는지 2~5문장. 이 필드를 먼저 쓴다.
- target.types: 영업점|뱅키스|연금 중 해당하는 것 전부(둘 다면 둘 다). 제목과 이미지 문구만으로 판단한다('BanKIS 주식계좌 보유 고객'→뱅키스, '영업점 개인고객'→영업점, 'DC·IRP·개인연금 계좌'→연금, '영업점, BanKIS 계좌 모두 가능'→영업점+뱅키스). 판단할 문구가 없으면 빈 배열. 해시태그·회색 소문·칩은 conditions와 exclusions로 나눈다.
- criteria: 대상 상품/계좌/종목/시장·실적 인정·이미지에만 있는 부가 기간(자산유지·자격판정·대회 기간)·그 밖의 조건을 text 한 필드에 담고, products와 performance는 있을 때만 채운다. '참여조건' 라벨은 내용에 따라 자격→target.conditions, 절차·실적→criteria.performance, 상품→criteria.products. 아무것도 없으면 criteria는 null.
- block_found: 기간·대상 블록을 찾았으면 true. 못 찾았으면 false로 저장하고 멈춘다."""
