"""Validated Python representation of the public True or Not result contract."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from schemas import ModelId
from scoring import ScoreBand, default_fact_score, score_band, score_label


VerdictCode = Literal[
    "mostly_supported",
    "partially_supported",
    "missing_context",
    "conflicting_sources",
    "insufficient_evidence",
    "not_checkable",
    "contradicted",
]

EvidenceRelation = Literal["supports", "contradicts", "context"]
ClaimKind = Literal["fact", "opinion", "prediction", "unclear"]
ClaimTone = Literal["positive", "negative", "neutral"]
AccessStatus = Literal["verified", "unavailable"]
Reasoning = Literal["max", "high"]


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FactSource(_ContractModel):
    id: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=300)
    publishedAt: str | None
    retrievedAt: str = Field(min_length=1, max_length=100)
    accessStatus: AccessStatus
    sourceType: str = Field(min_length=1, max_length=100)
    originGroupId: str | None
    searchProvider: Literal["openai_web_search", "gemini_google_search", "tavily_search"] | None = None
    searchQuery: str | None = Field(default=None, max_length=300)
    candidateOrder: int | None = Field(default=None, ge=1, le=1000)
    youtubeTitle: str | None = Field(default=None, max_length=300)
    youtubeChannelTitle: str | None = Field(default=None, max_length=300)
    youtubePublishedAt: str | None = Field(
        default=None,
        max_length=50,
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$",
    )
    youtubeViewCount: str | None = Field(default=None, pattern=r"^\d{1,30}$")
    youtubeComments: list[Annotated[str, Field(max_length=10_000)]] = Field(
        default_factory=list,
        max_length=10,
    )
    youtubeDataStatus: Literal[
        "not_applicable", "not_configured", "collected", "unavailable",
    ] = "not_applicable"


class FactCheckProgressSource(_ContractModel):
    """Small, non-sensitive source projection used while verification is running."""

    id: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=300)
    accessStatus: Literal["candidate", "verified", "unavailable"]
    sourceType: str = Field(min_length=1, max_length=100)


class FactCheckProgressCitation(_ContractModel):
    sourceId: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2_000)


class FactCheckProgressClaim(_ContractModel):
    id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=12_000)
    summary: str = Field(min_length=1, max_length=2_000)
    verdict: str = Field(min_length=1, max_length=100)
    citations: list[FactCheckProgressCitation] = Field(max_length=3)


class MarketCandle(_ContractModel):
    time: int = Field(ge=0)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class MarketContext(_ContractModel):
    source: Literal["finnhub", "krx"] = "finnhub"
    symbol: str = Field(min_length=1, max_length=16)
    displayName: str | None = Field(default=None, max_length=100)
    current: float | None = None
    previousClose: float | None = None
    changePercent: float | None = None
    dataAsOf: str | None = Field(default=None, max_length=100)
    candles: list[MarketCandle] = Field(max_length=90)


class FactEvidence(_ContractModel):
    id: str = Field(min_length=1, max_length=100)
    claimId: str = Field(min_length=1, max_length=100)
    sourceId: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2_000)
    quoteTranslation: str | None = Field(default=None, max_length=2_000)
    quoteVerified: Literal[True]
    relation: EvidenceRelation
    sectionTitle: str | None = Field(default=None, min_length=1, max_length=300)
    sectionText: str | None = Field(default=None, min_length=1, max_length=8_000)
    sectionTruncated: bool = False

    @model_validator(mode="after")
    def validate_section_details(self):
        if (self.sectionTitle is None) != (self.sectionText is None):
            raise ValueError("Section title and text must be provided together")
        if self.sectionTruncated and self.sectionText is None:
            raise ValueError("Truncated section details need section text")
        return self


class FactClaim(_ContractModel):
    id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=12_000)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    kind: ClaimKind
    factScore: int = Field(ge=0, le=100)
    scoreBand: ScoreBand
    scoreLabel: str = Field(min_length=1, max_length=100)
    verdictCode: VerdictCode
    verdict: str = Field(min_length=1, max_length=100)
    tone: ClaimTone
    summary: str = Field(min_length=1, max_length=2_000)
    confirmed: list[str] = Field(max_length=5)
    unresolved: list[str] = Field(max_length=5)
    warnings: list[str] = Field(max_length=5)
    evidenceIds: list[str] = Field(max_length=6)

    @model_validator(mode="before")
    @classmethod
    def fill_score_defaults(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "factScore" not in normalized:
            normalized["factScore"] = default_fact_score(str(normalized.get("verdictCode", "")))
        raw_score = normalized.get("factScore")
        if isinstance(raw_score, int) and not isinstance(raw_score, bool):
            normalized.setdefault("scoreBand", score_band(raw_score))
            normalized.setdefault("scoreLabel", score_label(raw_score))
        return normalized

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.end < self.start:
            raise ValueError("Claim end offset must not precede start offset")
        if score_band(self.factScore) != self.scoreBand or score_label(self.factScore) != self.scoreLabel:
            raise ValueError("Fact score label does not match score")
        return self


class AnswerCitation(_ContractModel):
    sourceId: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2_000)


class AnswerBlock(_ContractModel):
    text: str = Field(min_length=1, max_length=1_200)
    citations: list[AnswerCitation] = Field(max_length=3)


class AnswerSection(_ContractModel):
    kind: Literal["supporting", "counter", "uncertainty", "context"]
    title: str = Field(min_length=1, max_length=120)
    items: list[AnswerBlock] = Field(min_length=1, max_length=3)


class FactCheckAnswer(_ContractModel):
    status: Literal["grounded", "partial", "insufficient_evidence", "synthesis_failed", "judgment_only"]
    overview: AnswerBlock | None
    sections: list[AnswerSection] = Field(max_length=4)
    conclusion: AnswerBlock | None
    model: str | None = Field(max_length=100)
    reasoning: Reasoning | None

    @model_validator(mode="after")
    def validate_answer_blocks(self):
        blocks = [block for block in (self.overview, self.conclusion) if block]
        blocks.extend(item for section in self.sections for item in section.items)

        if self.status == "judgment_only" and (blocks or self.model is not None or self.reasoning is not None):
            raise ValueError("Judgment-only results cannot include generated blocks or model metadata")

        if self.status in {"grounded", "partial"} and (
            self.overview is None
            or self.conclusion is None
            or any(not block.citations for block in blocks)
        ):
            raise ValueError("Grounded answers need cited overview and conclusion")
        if self.status in {"insufficient_evidence", "synthesis_failed"} and self.sections:
            raise ValueError("Unusable answers cannot assert evidence sections")
        return self


class FactCheckResult(_ContractModel):
    text: str = Field(min_length=1, max_length=12_000)
    focus: str = Field(max_length=500)
    demo: Literal[False]
    model: str = Field(min_length=1, max_length=100)
    reasoning: Reasoning
    checkedAt: str = Field(min_length=1, max_length=100)
    claims: list[FactClaim] = Field(max_length=3)
    sources: list[FactSource] = Field(max_length=6)
    evidence: list[FactEvidence] = Field(max_length=18)
    warnings: list[str] = Field(max_length=8)
    market: MarketContext | None = None
    answer: FactCheckAnswer = Field(default_factory=lambda: FactCheckAnswer(
        status="insufficient_evidence",
        overview=None,
        sections=[],
        conclusion=None,
        model=None,
        reasoning=None,
    ))

    @model_validator(mode="after")
    def validate_cross_references(self):
        claims = {claim.id: claim for claim in self.claims}
        sources = {source.id: source for source in self.sources}
        evidence_by_id: dict[str, FactEvidence] = {}
        text_bytes = self.text.encode("utf-16-le", errors="surrogatepass")
        text_units = len(text_bytes) // 2

        if len(claims) != len(self.claims) or len(sources) != len(self.sources):
            raise ValueError("Duplicate claim or source id")

        for claim in self.claims:
            if claim.kind in {"opinion", "prediction"} and claim.verdictCode != "not_checkable":
                raise ValueError("Opinion and prediction claims must be not_checkable")
            if claim.end > text_units:
                raise ValueError("Claim offset exceeds input text")
            quoted = text_bytes[claim.start * 2:claim.end * 2].decode(
                "utf-16-le", errors="surrogatepass"
            )
            if quoted != claim.quote:
                raise ValueError("Claim quote does not match its offsets")

        for evidence in self.evidence:
            if evidence.id in evidence_by_id:
                raise ValueError("Duplicate evidence id")
            source = sources.get(evidence.sourceId)
            if evidence.claimId not in claims or source is None:
                raise ValueError("Evidence references an unknown claim or source")
            if source.accessStatus != "verified":
                raise ValueError("Evidence references an unavailable source")
            evidence_by_id[evidence.id] = evidence

        for claim in self.claims:
            if len(set(claim.evidenceIds)) != len(claim.evidenceIds):
                raise ValueError("Duplicate evidence link")
            for evidence_id in claim.evidenceIds:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None or evidence.claimId != claim.id:
                    raise ValueError("Claim evidence link is inconsistent")

        linked_ids = {evidence_id for claim in self.claims for evidence_id in claim.evidenceIds}
        if linked_ids != set(evidence_by_id):
            raise ValueError("Unlinked evidence is not allowed")

        answer_blocks = [block for block in (self.answer.overview, self.answer.conclusion) if block]
        answer_blocks.extend(item for section in self.answer.sections for item in section.items)
        for block in answer_blocks:
            for citation in block.citations:
                source = sources.get(citation.sourceId)
                if (
                    source is None
                    or source.accessStatus != "verified"
                    or source.sourceType == "유튜브"
                ):
                    raise ValueError("Answer citation references an ineligible source")
        return self


class FactCheckResponse(_ContractModel):
    result: FactCheckResult


class ContentSummary(_ContractModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2_000)
    points: list[str] = Field(max_length=5)
    sourceName: str | None = Field(default=None, max_length=100)
    sourceUrl: str | None = Field(default=None, max_length=2048)
    warnings: list[str] = Field(max_length=3)
    model: str | None = Field(default=None, max_length=100)
    reasoning: Reasoning | None = None


class SummaryResponse(_ContractModel):
    result: ContentSummary


class ModelOption(_ContractModel):
    id: ModelId
    label: str = Field(min_length=1, max_length=50)
    configured: bool


class AgentStatus(_ContractModel):
    configured: bool
    jevConfigured: bool
    workflowReady: bool
    engine: Literal["langgraph"] = "langgraph"
    model: str | None
    reasoning: Reasoning | None
    webSearch: bool
    modelOptions: list[ModelOption]
    phase: Literal["api-foundation", "workflow-ready"]
