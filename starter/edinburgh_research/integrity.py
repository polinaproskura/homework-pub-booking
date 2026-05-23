"""Ex5 — reference solution for integrity.py.

verify_dataflow's job: for every concrete fact in the flyer, confirm
that some tool call in the session actually produced that value. If
a fact exists in the flyer but not in any tool output, it's fabrication.

Two competing failure modes to balance:
  - Too lenient → misses fabrications (grader plants £9999; must catch it)
  - Too strict → rejects legitimate flyers (fails the "accepts real flyer" test)

This implementation leans slightly strict but uses the scalar-matching
`fact_appears_in_log` helper provided in the starter to tolerate common
variations (leading £, trailing C, case differences).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    output: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


_TOOL_CALL_LOG: list[ToolCallRecord] = []


def record_tool_call(tool_name: str, arguments: dict, output: dict) -> None:
    _TOOL_CALL_LOG.append(
        ToolCallRecord(tool_name=tool_name, arguments=dict(arguments), output=dict(output))
    )


def clear_log() -> None:
    _TOOL_CALL_LOG.clear()


@dataclass
class IntegrityResult:
    ok: bool
    unverified_facts: list[str] = field(default_factory=list)
    verified_facts: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "unverified_facts": self.unverified_facts,
            "verified_facts": self.verified_facts,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_money_facts(text: str) -> list[str]:
    """Find all £<number> occurrences, HTML tags stripped or not."""
    # Strip HTML tags first so e.g. <dd>£540</dd> matches cleanly.
    stripped = re.sub(r"<[^>]+>", " ", text)
    return re.findall(r"£\d+(?:\.\d+)?", stripped)


_TEMPERATURE_LABEL_WORDS = {"temperature", "temp"}


def extract_temperature_facts(text: str) -> list[str]:
    """Find temperature mentions (number followed by °C or C).

    When the number is preceded by a non-label adjective ("scorching 35C"),
    the full phrase is returned so a planted fabrication shows up verbatim
    in unverified_facts. Label words like "Temperature" in the HTML flyer
    are skipped so the legit reading still returns just the digit.
    """
    stripped = re.sub(r"<[^>]+>", " ", text)
    results: set[str] = set()
    for m in re.finditer(r"(?:(\w+)\s+)?(\d+)\s*°?\s*[Cc]\b", stripped):
        prefix = m.group(1)
        if prefix and prefix.lower() not in _TEMPERATURE_LABEL_WORDS:
            results.add(m.group(0).strip())
        else:
            results.add(m.group(2))
    return list(results)


def extract_condition_facts(text: str) -> list[str]:
    """Find weather condition keywords."""
    stripped = re.sub(r"<[^>]+>", " ", text)
    tl = stripped.lower()
    known = ("sunny", "rainy", "cloudy", "partly_cloudy", "partly cloudy")
    return [c for c in known if c in tl]


_VENUE_NAME_SUFFIXES = {
    "inn",
    "tap",
    "bar",
    "pub",
    "tavern",
    "house",
    "hall",
    "cafe",
    "restaurant",
    "hotel",
    "lodge",
    "arms",
    "oak",
    "heid",
    "club",
    "royal",
}


def extract_venue_facts(text: str) -> list[str]:
    """Extract venue name references from a flyer.

    Three sources, combined into one deduped list:

      1. HTML data-testid="venue" — structured form used by the
         reference flyer.
      2. Markdown "Venue: <name>" lines.
      3. Any capitalised proper-noun phrase (>=2 words, e.g.
         "Castle Royal Grand Inn") whose last word matches a venue
         suffix like "Inn", "Tap", "Bar". The suffix filter avoids
         false-positives on HTML labels such as "Party Size" or
         "Total Cost" that survive tag stripping.

    The third source is what catches the dataflow_probe's
    "Castle Royal Grand Inn" plant when it appears outside a "Venue:"
    line.
    """
    venues: set[str] = set()

    testids = extract_testid_facts(text)
    if "venue" in testids:
        venues.add(testids["venue"].strip())

    stripped = re.sub(r"<[^>]+>", " ", text)

    for m in re.finditer(r"Venue:?\s*([^\n.]+?)(?:\.\s|\n|$)", stripped):
        venue = m.group(1).strip()
        if venue:
            venues.add(venue)

    for m in re.finditer(r"(?:[A-Z][\w']+\s+)+[A-Z][\w']+", stripped):
        phrase = m.group(0).strip()
        last_word = phrase.split()[-1].lower()
        if last_word in _VENUE_NAME_SUFFIXES:
            venues.add(phrase)

    return list(venues)


def extract_testid_facts(text: str) -> dict[str, str]:
    """For HTML flyers that use data-testid, extract {testid: value} pairs.

    This is the preferred path for HTML — it gives us structured facts
    (e.g. {'total': '£540', 'deposit': '£0'}) instead of loose regex
    matches. The solution flyer ships with data-testid on every fact.
    """
    pattern = re.compile(
        r'<[^>]+data-testid="([^"]+)"[^>]*>([^<]+)</[^>]+>',
        re.IGNORECASE,
    )
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(text)}


def fact_appears_in_log(fact: Any, log: list[ToolCallRecord] | None = None) -> bool:
    records = log if log is not None else _TOOL_CALL_LOG
    target = str(fact).lower().strip("£°c ")

    def _scan(obj: Any) -> bool:
        if isinstance(obj, (str, int, float)):
            return str(obj).lower().strip("£°c ") == target
        if isinstance(obj, dict):
            return any(_scan(v) for v in obj.values())
        if isinstance(obj, (list, tuple, set)):
            return any(_scan(v) for v in obj)
        return False

    return any(_scan(r.output) or _scan(r.arguments) for r in records)


# ---------------------------------------------------------------------------
# verify_dataflow — the main check
# ---------------------------------------------------------------------------
def verify_dataflow(flyer_content: str) -> IntegrityResult:
    if not flyer_content or not flyer_content.strip():
        return IntegrityResult(ok=True, summary="no facts to verify (empty flyer)")

    facts_to_check: list[str] = []
    facts_to_check.extend(extract_money_facts(flyer_content))
    facts_to_check.extend(extract_temperature_facts(flyer_content))
    facts_to_check.extend(extract_condition_facts(flyer_content))
    facts_to_check.extend(extract_venue_facts(flyer_content))

    # De-dupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for f in facts_to_check:
        key = f.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    if not deduped:
        return IntegrityResult(
            ok=True, summary="no extractable facts in flyer (verified vacuously)"
        )

    verified: list[str] = []
    unverified: list[str] = []
    for fact in deduped:
        if fact_appears_in_log(fact):
            verified.append(fact)
        else:
            unverified.append(fact)

    if unverified:
        return IntegrityResult(
            ok=False,
            unverified_facts=unverified,
            verified_facts=verified,
            summary=(
                f"dataflow FAIL: {len(unverified)} unverified fact(s): "
                f"{unverified[:5]}" + ("..." if len(unverified) > 5 else "")
            ),
        )

    return IntegrityResult(
        ok=True,
        verified_facts=verified,
        summary=f"dataflow OK: verified {len(verified)} fact(s) against tool outputs",
    )


__all__ = [
    "IntegrityResult",
    "ToolCallRecord",
    "_TOOL_CALL_LOG",
    "clear_log",
    "extract_condition_facts",
    "extract_money_facts",
    "extract_temperature_facts",
    "extract_testid_facts",
    "extract_venue_facts",
    "fact_appears_in_log",
    "record_tool_call",
    "verify_dataflow",
]
