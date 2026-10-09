"""Data model: every claim in a report points at sources, and every source carries a LIVE/CACHED/MOCK label."""
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Kind = Literal["person", "organization"]
Mode = Literal["LIVE", "CACHED", "MOCK"]
Confidence = Literal["high", "medium", "low"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Anchor(BaseModel):
    """The one disambiguating fact the user supplies (IČO, website, city, or free text)."""
    type: Literal["ico", "url", "city", "text"]
    value: str

    @classmethod
    def parse(cls, raw: str) -> "Anchor":
        raw = raw.strip()
        low = raw.lower()
        for prefix in ("ico:", "ičo:"):
            if low.startswith(prefix):
                return cls(type="ico", value=raw[len(prefix):].strip().zfill(8))
        if raw.isdigit() and len(raw) <= 8:
            return cls(type="ico", value=raw.zfill(8))
        if low.startswith(("http://", "https://", "www.")) or low.startswith("url:"):
            value = raw[4:].strip() if low.startswith("url:") else raw
            return cls(type="url", value=value)
        if low.startswith("city:"):
            return cls(type="city", value=raw[5:].strip())
        return cls(type="text", value=raw)

    def label(self) -> str:
        return {"ico": "IČO", "url": "Website", "city": "City", "text": "Context"}[self.type] + f": {self.value}"


class Subject(BaseModel):
    name: str
    kind: Kind
    anchor: Anchor
    goal: str


class Source(BaseModel):
    id: str
    url: str
    title: str
    text: str
    origin: Literal["registry", "web"]
    publisher: str
    query: Optional[str] = None
    question_ids: list[str] = Field(default_factory=list)
    fetched_at: str = Field(default_factory=now_iso)
    mode: Mode = "LIVE"
    snippet_only: bool = False


class IdentityVerdict(BaseModel):
    source_id: str
    match: Literal["same", "possible", "different", "unassessed"]
    reason: str


class Contradiction(BaseModel):
    source_id: str
    quote: str
    note: str
    quote_verified: bool = False


class Claim(BaseModel):
    id: str
    question_id: str
    statement: str
    kind: Literal["fact", "inference"]
    source_ids: list[str]
    quotes: list[str] = Field(default_factory=list)
    quote_verified: list[bool] = Field(default_factory=list)
    relevance: str = ""
    contradicted_by: list[Contradiction] = Field(default_factory=list)
    confidence: Confidence = "low"
    confidence_reason: str = ""
    flags: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    question_id: str
    question: str
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class LookAlike(BaseModel):
    name: str
    detail: str
    reason: str


class Report(BaseModel):
    run_id: str
    generated_at: str = Field(default_factory=now_iso)
    subject: Subject
    goal_label: str
    goal_purpose: str
    resolved_entity: dict = Field(default_factory=dict)
    lookalikes: list[LookAlike] = Field(default_factory=list)
    identity: list[IdentityVerdict] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    suppressed_special_category: int = 0
    outreach_draft: Optional[str] = None
    method: dict = Field(default_factory=dict)  # "How this report was built" (R12)
    limitations: list[str] = Field(default_factory=list)
