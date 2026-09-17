"""요약 스키마 v2(docs/event-page-research.md §7.3)와 에이전트용 안내문."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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
