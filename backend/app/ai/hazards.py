"""Hazard detection: deterministic keyword rules first, LLM second.

final_is_hazard = rules_hit OR llm.is_hazard. The LLM can add a hazard but can never remove a
rule-triggered one, so safety never depends on the model alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app import taxonomy


@dataclass
class RuleHit:
    hazard_type: str
    phrase: str
    match: str

    def as_dict(self) -> dict:
        return {"hazard_type": self.hazard_type, "phrase": self.phrase, "match": self.match}


@dataclass
class HazardDecision:
    is_hazard: bool
    hazard_type: str | None
    rule_hits: list[RuleHit] = field(default_factory=list)
    llm_flagged: bool = False
    llm_hazard_type: str | None = None
    rationale: str = ""

    @property
    def rules_triggered(self) -> bool:
        return bool(self.rule_hits)

    @property
    def sources(self) -> list[str]:
        out = []
        if self.rule_hits:
            out.append("rules")
        if self.llm_flagged:
            out.append("llm")
        return out

    def as_payload(self) -> dict:
        return {
            "is_hazard": self.is_hazard,
            "hazard_type": self.hazard_type,
            "rule_hits": [h.as_dict() for h in self.rule_hits],
            "llm_flagged": self.llm_flagged,
            "llm_hazard_type": self.llm_hazard_type,
            "sources": self.sources,
        }


def rule_hazards(*texts: str | None) -> list[RuleHit]:
    """Run every keyword rule over the given texts. Order follows HAZARD_PRIORITY_ORDER."""
    blob = "  ".join(t for t in texts if t)
    if not blob.strip():
        return []
    hits: list[RuleHit] = []
    seen: set[tuple[str, str]] = set()
    for rule in taxonomy.HAZARD_RULES:
        m = rule.regex.search(blob)
        if m and (rule.hazard_type, m.group(0).lower()) not in seen:
            seen.add((rule.hazard_type, m.group(0).lower()))
            hits.append(RuleHit(rule.hazard_type, rule.source, m.group(0)))
    order = {h: i for i, h in enumerate(taxonomy.HAZARD_PRIORITY_ORDER)}
    hits.sort(key=lambda h: order.get(h.hazard_type, 99))
    return hits


def decide(rule_hits: list[RuleHit], llm_is_hazard: bool = False, llm_hazard_type: str | None = None) -> HazardDecision:
    llm_type = llm_hazard_type if llm_hazard_type in taxonomy.HAZARD_TYPES else None
    if rule_hits:
        primary = rule_hits[0].hazard_type
        phrases = ", ".join(sorted({f"'{h.match.lower()}'" for h in rule_hits}))
        rationale = f"Deterministic hazard rule matched {phrases} -> {taxonomy.HAZARD_LABELS[primary]}."
        if llm_is_hazard:
            rationale += f" The model also flagged a hazard ({llm_type or 'unspecified'})."
        return HazardDecision(True, primary, rule_hits, llm_is_hazard, llm_type, rationale)
    if llm_is_hazard:
        htype = llm_type or "slip_trip"
        return HazardDecision(True, htype, [], True, llm_type,
                              f"No keyword rule fired; the model flagged a {taxonomy.HAZARD_LABELS[htype]} hazard.")
    return HazardDecision(False, None, [], False, None, "No hazard rule matched and the model did not flag a hazard.")


def safety_text(hazard_type: str | None, emergency_text: str) -> str:
    specific = taxonomy.SAFETY_TEXT.get(hazard_type or "", "")
    return f"{specific} {emergency_text}".strip() if specific else emergency_text
