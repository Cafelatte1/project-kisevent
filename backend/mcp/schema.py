"""요약 스키마 v2(docs/event-page-research.md §7.3)와 에이전트용 안내문."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


class TargetV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    types: list[Literal["영업점", "뱅키스", "연금"]] = []
    text: str = ""
    conditions: list[str] = []
    exclusions: list[str] = []

    # 에이전트가 빈 값을 null로 쓰는 경우가 잦아 기본값으로 받는다.
    @field_validator("types", "text", "conditions", "exclusions", mode="before")
    @classmethod
    def _null_to_default(cls, v, info):
        return cls.model_fields[info.field_name].default if v is None else v


class CriteriaV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    products: list[Product] = []
    performance: str | None = None

    @field_validator("text", "products", mode="before")
    @classmethod
    def _null_to_default(cls, v, info):
        return cls.model_fields[info.field_name].default if v is None else v

    # 목록에 없는 상품명(CMA·발행어음 등)은 거부하지 않고 버린다 — text에 이미 원문이 있다.
    @field_validator("products", mode="before")
    @classmethod
    def _drop_unknown_products(cls, v):
        if isinstance(v, list):
            return [p for p in v if p in Product.__args__]
        return v

    @property
    def empty(self) -> bool:
        return not (self.text.strip() or self.products or self.performance)


class SummaryV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 필드 순서 = 에이전트가 쓰는 순서: 이미지 서술 → 블록 유무 판정 → 추출
    analysis: str
    block_found: bool
    target: TargetV2 = TargetV2()
    criteria: CriteriaV2 | None = None

    @model_validator(mode="after")
    def _block_requires_target(self) -> "SummaryV2":
        if self.block_found and not self.target.text.strip():
            raise ValueError(
                "block_found가 true면 target.text(참여대상 문구 원문, 예: 'BanKIS 주식계좌 보유 고객')가 필요합니다"
            )
        # 세 필드가 다 비면 기준 없음으로 본다.
        if self.criteria is not None and self.criteria.empty:
            self.criteria = None
        return self


SUMMARY_GUIDE = """[schema_version 2 요약 안내]
- 타일은 배너 상단의 정보 블록 구간(제목 아래 ~ 첫 이벤트 섹션)이다. 제목은 이미지에 없을 수 있으니 목록 title을 참고한다. 라벨은 '이벤트 기간/참가 신청/대회 기간', '참여대상/이벤트 대상/대상 고객/참가 대상' 등으로 흔들리니 라벨이 아니라 내용으로 판단한다.
- 쓰는 순서: analysis → block_found → target → criteria. 관찰을 먼저 적고, 블록 유무를 판정한 뒤, 찾았을 때만 추출한다.
- analysis: 이미지 자체를 서술한다 — 어떤 라벨과 문구(기간·대상·조건·해시태그·회색 소문)가 어디에 보이는지 2~5문장. 판단이 아니라 관찰을 적는다.
- block_found: 기간·대상 정보 블록이 보이면 true. 안 보이거나 잘려 있으면 false로 두고 target·criteria는 쓰지 않는다(추측 금지).
- target.types: 영업점|뱅키스|연금 중 해당하는 것 전부(둘 다면 둘 다). 제목과 이미지 문구만으로 판단한다('BanKIS 주식계좌 보유 고객'→뱅키스, '영업점 개인고객'→영업점, 'DC·IRP·개인연금 계좌'→연금, '영업점, BanKIS 계좌 모두 가능'→영업점+뱅키스). 판단할 문구가 없으면 빈 배열. 해시태그·회색 소문·칩은 conditions와 exclusions로 나눈다.
- criteria: 대상 상품/계좌/종목/시장·실적 인정·이미지에만 있는 부가 기간(자산유지·자격판정·대회 기간)·그 밖의 조건을 text 한 필드에 담고, products와 performance는 있을 때만 채운다. '참여조건' 라벨은 내용에 따라 자격→target.conditions, 절차·실적→criteria.performance, 상품→criteria.products. 아무것도 없으면 criteria는 null.
- 형식(키 이름·순서 그대로): {"analysis": str, "block_found": bool, "target": {"types": [...], "text": str, "conditions": [str], "exclusions": [str]}, "criteria": {"text": str, "products": [str], "performance": str|null} | null}"""
