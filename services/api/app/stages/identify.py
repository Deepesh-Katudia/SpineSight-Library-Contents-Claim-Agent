"""Stage 5: resolve a spine read to a catalogue work (and edition only when evidence supports it).

A title is filled only when (a) the spine was legible enough and (b) a catalogue record matches
the transcribed text closely. Otherwise the book stays ``unidentified`` — blanks beat wrong answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz

from app.sources.catalog import CatalogCandidate
from app.stages.observations import SpineObs

PUBLISHER_MATCH = 80
AMBIGUITY_MARGIN = 0.04


class CatalogSearch(Protocol):
    async def __call__(self, title: str, author: str) -> list[CatalogCandidate]: ...


@dataclass(frozen=True)
class Identification:
    status: str  # identified | unidentified
    confidence: float = 0.0
    title: str = ""
    author: str = ""
    publisher: str = ""
    edition: str = ""
    isbn: str = ""
    year: str = ""
    catalog_source: str = ""
    catalog_url: str = ""
    candidate: CatalogCandidate | None = None
    reason: str = ""


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("&", "and").split())


def candidate_score(read: SpineObs, cand: CatalogCandidate) -> float:
    """0..1 agreement between what the spine says and a catalogue record."""
    title_src = read.title or read.text
    title = fuzz.token_set_ratio(_norm(title_src), _norm(cand.title)) / 100
    if read.author and cand.authors:
        author = max(fuzz.token_set_ratio(_norm(read.author), _norm(a)) for a in cand.authors) / 100
        return 0.7 * title + 0.3 * author
    # No author on the spine: title alone, capped so it needs a near-exact title.
    return 0.92 * title


def publisher_supported(read: SpineObs, cand: CatalogCandidate) -> bool:
    return bool(
        read.publisher
        and cand.publisher
        and fuzz.token_set_ratio(_norm(read.publisher), _norm(cand.publisher)) >= PUBLISHER_MATCH
    )


def choose(read: SpineObs, candidates: list[CatalogCandidate], min_match: float) -> Identification:
    if not candidates:
        return Identification("unidentified", reason="no catalogue record found for the spine text")
    scored = sorted(((candidate_score(read, c), c) for c in candidates), key=lambda x: x[0], reverse=True)
    top_score, top = scored[0]
    if top_score < min_match:
        return Identification("unidentified", top_score, reason=f"best catalogue match {top_score:.2f} below {min_match}")
    rivals = [c for s, c in scored[1:] if top_score - s < AMBIGUITY_MARGIN and _norm(c.title) != _norm(top.title)]
    if rivals:
        return Identification("unidentified", top_score, reason=f"ambiguous between '{top.title}' and '{rivals[0].title}'")

    edition_ok = publisher_supported(read, top)
    return Identification(
        status="identified",
        confidence=round(top_score * (1.0 if edition_ok else 0.97), 3),
        title=top.title,
        author=", ".join(top.authors),
        publisher=top.publisher if edition_ok else read.publisher,
        edition=f"{top.publisher} {top.year}".strip() if edition_ok else "",
        isbn=top.isbn if edition_ok else "",
        year=top.year,
        catalog_source=top.source,
        catalog_url=top.url,
        candidate=top,
    )


async def identify(
    read: SpineObs, search: CatalogSearch, min_legibility: float, min_match: float
) -> Identification:
    query_title = read.title or ""
    if read.legibility < min_legibility or not query_title:
        return Identification(
            "unidentified", reason=f"spine legibility {read.legibility:.2f}; no readable title — not guessed"
        )
    candidates = await search(query_title, read.author)
    return choose(read, candidates, min_match)
