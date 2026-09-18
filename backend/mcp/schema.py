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
                "target.text is required when block_found is true"
                " (the eligible-customer wording as printed, e.g. 'BanKIS 주식계좌 보유 고객')"
            )
        # 세 필드가 다 비면 기준 없음으로 본다.
        if self.criteria is not None and self.criteria.empty:
            self.criteria = None
        return self


SUMMARY_GUIDE = """[Summary guide, schema_version 2]
- The image is the info-block region of the banner (below the title, above the first event section). The title may be absent from the image; use the list title. Labels vary ('이벤트 기간/참가 신청/대회 기간', '참여대상/이벤트 대상/대상 고객/참가 대상' ...), so judge by content, not by label.
- Write in this order: analysis → block_found → target → criteria. Observe first, decide whether the block is there, and extract only if it is.
- analysis: describe the image itself — which labels and phrases (period, eligibility, conditions, hashtags, small grey print) appear and where, in 2–5 sentences. Observation, not judgement.
- block_found: true if the period/eligibility info block is visible. If it is missing or cut off, set false and do not write target or criteria (never guess).
- target.types: every applicable group among 영업점 (branch), 뱅키스 (BanKIS online), 연금 (pension) — both if both. Judge from the title and the image wording only ('BanKIS 주식계좌 보유 고객' → 뱅키스, '영업점 개인고객' → 영업점, 'DC·IRP·개인연금 계좌' → 연금, '영업점, BanKIS 계좌 모두 가능' → 영업점 + 뱅키스). Empty array if nothing decides it. Split hashtags, grey print and chips into conditions and exclusions. Keep target.text and the list items in Korean as printed.
- criteria: put target products/accounts/instruments/markets, performance criteria, extra periods that exist only in the image (asset-holding, qualification, contest periods) and any other condition into text; fill products and performance only when present. A '참여조건' label goes by content: eligibility → target.conditions, procedure/performance → criteria.performance, product → criteria.products. criteria is null when there is nothing.
- Format (keys and order exactly): {"analysis": str, "block_found": bool, "target": {"types": [...], "text": str, "conditions": [str], "exclusions": [str]}, "criteria": {"text": str, "products": [str], "performance": str|null} | null}"""
