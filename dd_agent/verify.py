"""Deterministic checks applied after the LLM.

1. Every quote the LLM cites must actually appear in the cited source text; otherwise the claim is
   flagged UNSUPPORTED (likely hallucination) and gets low confidence.
2. Confidence is computed by rules here, never taken from the LLM:
     high   = verified fact from an official registry, or from 2+ independent publishers
     medium = verified fact from a single publisher, or any verified inference
     low    = unsupported, contradicted, or the source may be about a different entity
"""
import re
import unicodedata
from difflib import SequenceMatcher

from .models import Claim, IdentityVerdict, Source

_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "„": '"',
                        "–": "-", "—": "-", " ": " "})


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT).lower()
    text = re.sub(r"[*_#`>|\[\]()]", " ", text)
    return " ".join(text.split())


def quote_found(quote: str, text: str) -> bool:
    q, t = _norm(quote), _norm(text)
    if not q:
        return False
    if q in t:
        return True
    if len(q) < 12:
        return False
    m = SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
    return m.size / len(q) >= 0.85


def score_claim(claim: Claim, sources: dict[str, Source], identity: dict[str, IdentityVerdict]) -> Claim:
    claim.quote_verified = [
        sid in sources and quote_found(q, sources[sid].text)
        for sid, q in zip(claim.source_ids, claim.quotes)
    ]
    for c in claim.contradicted_by:
        c.quote_verified = c.source_id in sources and quote_found(c.quote, sources[c.source_id].text)

    supporting = [sid for sid, ok in zip(claim.source_ids, claim.quote_verified)
                  if ok and identity.get(sid, _same(sid)).match != "different"]
    flags = []

    if not supporting:
        claim.confidence = "low"
        claim.confidence_reason = "No cited quote could be found in its source"
        flags.append("UNSUPPORTED")
        claim.flags = flags
        return claim

    publishers = {sources[sid].publisher for sid in supporting}
    official = any(sources[sid].origin == "registry" for sid in supporting)
    certain = [sid for sid in supporting if identity.get(sid, _same(sid)).match == "same"]

    if official and claim.kind == "fact":
        level, reason = "high", "Official registry record"
    elif len(publishers) >= 2:
        level, reason = "high", f"Confirmed by {len(publishers)} independent publishers"
    else:
        level, reason = "medium", "Single publisher"

    if claim.kind == "inference":
        flags.append("INFERENCE")
        if level == "high":
            level, reason = "medium", reason + "; interpretation, not a stated fact"
    if not certain:
        level, reason = "low", reason + "; sources may refer to a different entity"
        flags.append("IDENTITY UNCERTAIN")
    if all(sources[sid].snippet_only for sid in supporting) and level == "high":
        level, reason = "medium", reason + "; search snippets only"
    if any(c.quote_verified for c in claim.contradicted_by):
        level, reason = "low", reason + "; contradicted by another source"
        flags.append("CONTRADICTED")

    claim.confidence = level
    claim.confidence_reason = reason
    claim.flags = flags
    return claim


def _same(sid: str) -> IdentityVerdict:
    if sid.startswith("R"):
        return IdentityVerdict(source_id=sid, match="same", reason="Official registry record for the resolved entity")
    return IdentityVerdict(source_id=sid, match="unassessed", reason="Identity check did not run")
