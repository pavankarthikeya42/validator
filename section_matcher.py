"""
section_matcher.py — Heading-anchored section validation

The UI hands over one blob of text per accordion section. The first heading in
that blob (e.g. "1. Executive Summary") is the anchor: the same heading exists
in the PDF, and everything under it in the PDF must match everything under it in
the UI. A single UI section may carry several numbered headings (e.g. a nested
"2.3 Executive Summary"); each one is anchored and compared as its own block.

Sections whose values are short key/value style text (Metadata, Indication) are
compared semantically instead of literally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

# "1 Title", "1. Title", "2.3) Title" — the number, an optional separator, then
# a title that starts with a capital letter. The UI collapses a whole section
# onto one line, so the title is bounded by word shape rather than by a newline.
_TITLE_WORD = r"(?:[A-Z][\w()/&,'\u2019-]*|and|of|the|for|in|to|with|on|a|an)"
_HEADING_RE = re.compile(
    rf"(?<![\w.])(\d+(?:\.\d+)*)[.)]?\s+({_TITLE_WORD}(?:[ \t]+{_TITLE_WORD}){{0,15}})"
)
_CONNECTORS = {"and", "of", "the", "for", "in", "to", "with", "on", "a", "an"}
_SENTENCE_START_RE = re.compile(r"^[ \t]+[a-z]")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


@dataclass
class Block:
    """A heading and the text that belongs to it."""
    number: str
    title: str
    body: str

    @property
    def heading(self) -> str:
        return f"{self.number} {self.title}".strip()

    @property
    def level(self) -> int:
        return self.number.count(".") + 1


@dataclass
class BlockResult:
    heading: str
    status: str                 # MATCH | MISMATCH | MISSING_IN_PDF | MISSING_IN_UI
    ui_text: str
    pdf_text: str
    similarity: float = 0.0
    semantic: bool = False


@dataclass
class SectionResult:
    section: str
    blocks: list[BlockResult] = field(default_factory=list)


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def parse_blocks(text: str) -> list[Block]:
    """Split free text into heading-anchored blocks, in document order."""
    if not text:
        return []

    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return []

    blocks: list[Block] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title_end = _trim_title_end(text, m.start(2), m.end(2))
        body = text[title_end:end].strip()
        blocks.append(
            Block(number=m.group(1), title=text[m.start(2):title_end].strip(), body=body)
        )
    return blocks


def _trim_title_end(text: str, start: int, end: int) -> int:
    """
    Give back trailing words that belong to the body.

    "1. Executive Summary The product demonstrated ..." — the title swallows
    "The" because it is capitalised, but the lowercase word after it shows the
    sentence has already begun.
    """
    while end > start:
        tail = text[end:]
        last_space = text.rfind(" ", start, end)
        last_word = text[last_space + 1:end].lower() if last_space > start else ""
        if _SENTENCE_START_RE.match(tail) or last_word in _CONNECTORS:
            if last_space <= start:
                break
            end = last_space
            continue
        break
    return end


def leading_text(text: str) -> str:
    """Text that appears before the first heading, if any."""
    if not text:
        return ""
    m = _HEADING_RE.search(text)
    return (text[:m.start()] if m else text).strip()


# ----------------------------------------------------------------------
# Similarity
# ----------------------------------------------------------------------

def canonical(value: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", (value or "").lower())).strip()


def text_similarity(ui_text: str, pdf_text: str) -> float:
    """
    Ratio in [0, 1] of how much of the UI text is present in the PDF text.

    Chunking the UI text keeps page headers and footers injected into the PDF
    from dragging an otherwise identical block below the threshold.
    """
    u, p = canonical(ui_text), canonical(pdf_text)
    if not u and not p:
        return 1.0
    if not u or not p:
        return 0.0
    if u in p or p in u:
        return 1.0

    chunk_size = 50
    if len(u) > chunk_size:
        chunks = [u[i:i + chunk_size] for i in range(0, len(u), chunk_size)]
        hits = sum(1 for c in chunks if c in p)
        return max(hits / len(chunks), SequenceMatcher(None, u, p).ratio())
    return SequenceMatcher(None, u, p).ratio()


class SemanticMatcher:
    """
    Cosine similarity over sentence-transformer embeddings, with a lexical
    fallback so validation still runs when the model is unavailable offline.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None
        self._unavailable = False

    @property
    def model(self):
        if self._model is None and not self._unavailable:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception:
                self._unavailable = True
        return self._model

    def similarity(self, ui_text: str, pdf_text: str) -> float:
        u, p = canonical(ui_text), canonical(pdf_text)
        if not u or not p:
            return 0.0
        model = self.model
        if model is None:
            return text_similarity(ui_text, pdf_text)
        emb = model.encode([u, p], normalize_embeddings=True)
        return float(max(0.0, min(1.0, emb[0] @ emb[1])))

    def best_match(self, ui_text: str, candidates: list[str]) -> tuple[str, float]:
        """The candidate closest in meaning to `ui_text`, and its score."""
        if not candidates or not canonical(ui_text):
            return "", 0.0
        model = self.model
        if model is None:
            scored = [(c, text_similarity(ui_text, c)) for c in candidates]
        else:
            embeddings = model.encode(
                [canonical(ui_text)] + [canonical(c) for c in candidates],
                normalize_embeddings=True,
            )
            scored = [
                (c, float(max(0.0, min(1.0, embeddings[0] @ embeddings[i + 1]))))
                for i, c in enumerate(candidates)
            ]
        return max(scored, key=lambda pair: pair[1])


def _candidates(text: str) -> list[str]:
    """Non-empty lines of a text blob, used as semantic comparison units."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def _find_pdf_block(ui_block: Block, pdf_blocks: list[Block]) -> Optional[Block]:
    """Anchor on the heading number first, then on the heading title."""
    for pdf_block in pdf_blocks:
        if pdf_block.number == ui_block.number:
            return pdf_block
    ui_title = canonical(ui_block.title)
    for pdf_block in pdf_blocks:
        if canonical(pdf_block.title) == ui_title:
            return pdf_block
    return None


def validate_section(
    section: str,
    ui_text: str,
    pdf_blocks: list[Block],
    pdf_raw: str,
    threshold: float,
    semantic: bool = False,
    matcher: Optional[SemanticMatcher] = None,
) -> SectionResult:
    """Compare one UI section against the PDF, block by block."""
    result = SectionResult(section=section)

    if semantic:
        matcher = matcher or SemanticMatcher()
        candidates = _candidates(pdf_raw)
        for line in _candidates(ui_text):
            best, score = matcher.best_match(line, candidates)
            result.blocks.append(
                BlockResult(
                    heading=section,
                    status="MATCH" if score >= threshold else "MISMATCH",
                    ui_text=line,
                    pdf_text=best,
                    similarity=score,
                    semantic=True,
                )
            )
        return result

    ui_blocks = parse_blocks(ui_text)
    if not ui_blocks:
        # No heading in the section — fall back to locating the text anywhere.
        score = text_similarity(ui_text, pdf_raw)
        result.blocks.append(
            BlockResult(
                heading=section,
                status="MATCH" if score >= threshold else "MISSING_IN_PDF",
                ui_text=ui_text,
                pdf_text="",
                similarity=score,
            )
        )
        return result

    for ui_block in ui_blocks:
        pdf_block = _find_pdf_block(ui_block, pdf_blocks)
        if pdf_block is None:
            result.blocks.append(
                BlockResult(
                    heading=ui_block.heading,
                    status="MISSING_IN_PDF",
                    ui_text=ui_block.body,
                    pdf_text="",
                )
            )
            continue

        heading_score = text_similarity(ui_block.title, pdf_block.title)
        body_score = text_similarity(ui_block.body, pdf_block.body)
        score = min(heading_score, body_score)
        result.blocks.append(
            BlockResult(
                heading=ui_block.heading,
                status="MATCH" if score >= threshold else "MISMATCH",
                ui_text=ui_block.body,
                pdf_text=pdf_block.body,
                similarity=score,
            )
        )

    return result


def unmatched_pdf_blocks(
    pdf_blocks: list[Block], section_results: list[SectionResult]
) -> list[Block]:
    """PDF headings that no UI section claimed."""
    seen = {
        block.heading.split(" ", 1)[0]
        for res in section_results
        for block in res.blocks
        if not block.semantic
    }
    return [b for b in pdf_blocks if b.number not in seen]
