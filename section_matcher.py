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
# In PDF text a heading owns its line: "8.2.5.1. Malignancies....... 94".
_PDF_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z].*?)\s*$")
_DOT_LEADER_RE = re.compile(r"\.{3,}\s*\d*\s*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")
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

    @property
    def sort_key(self) -> tuple[int, ...]:
        """Position in the numbering, so 2.10 follows 2.9."""
        return tuple(int(part) for part in self.number.split(".") if part.isdigit())


@dataclass
class BlockResult:
    heading: str
    status: str                 # MATCH | PARTIAL | MISMATCH | MISSING_IN_PDF | MISSING_IN_UI
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


def parse_pdf_blocks(text: str) -> list[Block]:
    """
    Split PDF text into heading-anchored blocks.

    PDF text keeps its line breaks, so headings sit on their own line. Table of
    contents entries look identical to real headings apart from their dot
    leaders and empty body, so a heading that occurs twice keeps the occurrence
    that actually carries text.
    """
    lines = (text or "").splitlines()
    candidates: list[tuple[int, str, str]] = []
    contents: dict[str, str] = {}
    for i, line in enumerate(lines):
        m = _PDF_HEADING_RE.match(line)
        if not m:
            continue
        number, title = m.group(1), m.group(2)
        if _DOT_LEADER_RE.search(title):
            contents.setdefault(number, _compact(_DOT_LEADER_RE.sub("", title)))
        candidates.append((i, number, _DOT_LEADER_RE.sub("", title).strip()))

    # Table rows and footnotes ('3 Moderate', '4 Relative risk, 95% CI...') are
    # shaped exactly like headings; the table of contents says which number and
    # title pairs are real. A wrapped contents entry only lists the title's
    # first line, so the two are compared by prefix.
    found = [
        c for c in candidates if _matches_contents(c[1], c[2], contents)
    ] if contents else candidates

    blocks: list[Block] = []
    for pos, (line_no, number, title) in enumerate(found):
        end = found[pos + 1][0] if pos + 1 < len(found) else len(lines)
        if not title:
            continue
        body = "\n".join(
            line for line in lines[line_no + 1:end] if not _DOT_LEADER_RE.search(line)
        ).strip()
        blocks.append(Block(number=number, title=title, body=body))

    # The contents listing comes before the body, so the last occurrence of a
    # heading is the one that carries the section's text.
    last: dict[str, Block] = {block.number: block for block in blocks}
    return [b for b in blocks if last[b.number] is b]


def _in_document_order(
    anchors: list[tuple[int, int, tuple[int, ...], Block]]
) -> list[tuple[int, int, tuple[int, ...], Block]]:
    """
    Keep the longest run of anchors whose numbering ascends.

    A section that merely cites a heading from elsewhere in the document
    ('see 7.1 Table of Clinical Studies') would otherwise anchor there and
    swallow the rest of the section.
    """
    if not anchors:
        return []

    best_length = [1] * len(anchors)
    previous = [-1] * len(anchors)
    for i in range(len(anchors)):
        for j in range(i):
            if anchors[j][2] < anchors[i][2] and best_length[j] + 1 > best_length[i]:
                best_length[i] = best_length[j] + 1
                previous[i] = j

    end = max(range(len(anchors)), key=lambda i: best_length[i])
    kept = []
    while end != -1:
        kept.append(anchors[end])
        end = previous[end]
    return list(reversed(kept))


def _matches_contents(number: str, title: str, contents: dict[str, str]) -> bool:
    listed = contents.get(number)
    if listed is None:
        return False
    seen = _compact(title)
    if not seen or not listed:
        return False
    shortest = min(len(seen), len(listed))
    return seen[:shortest] == listed[:shortest]


def locate_ui_blocks(ui_text: str, pdf_blocks: list[Block]) -> list[Block]:
    """
    Split a UI section into blocks using the PDF's headings as anchors.

    The UI collapses a section onto one line and often loses the spaces around
    a heading entirely ("...Executive Summary1.1. Product IntroductionThe
    Applicant..."), so headings are located on a whitespace-stripped copy of
    the text and mapped back to the original offsets.
    """
    if not ui_text:
        return []

    compact, offsets = _compact_with_offsets(ui_text)
    anchors: list[tuple[int, int, tuple[int, ...], Block]] = []
    for pdf_block in pdf_blocks:
        needle = _compact(pdf_block.heading)
        if not needle:
            continue
        at = compact.find(needle)
        if at == -1:
            continue
        anchors.append((at, at + len(needle), pdf_block.sort_key, pdf_block))

    anchors.sort(key=lambda anchor: anchor[0])
    anchors = _in_document_order(anchors)
    ui_blocks: list[Block] = []
    for i, (_, body_start, _order, pdf_block) in enumerate(anchors):
        body_end = anchors[i + 1][0] if i + 1 < len(anchors) else len(compact)
        body = ui_text[
            _offset_at(offsets, body_start, len(ui_text)):
            _offset_at(offsets, body_end, len(ui_text))
        ]
        ui_blocks.append(
            Block(number=pdf_block.number, title=pdf_block.title, body=body.strip())
        )
    return ui_blocks


def _compact(value: str) -> str:
    """Lowercase, with punctuation and whitespace removed."""
    return _NON_ALNUM_RE.sub("", (value or "").lower())


def _compact_with_offsets(value: str) -> tuple[str, list[int]]:
    """`_compact(value)` plus, per compacted character, its index in `value`."""
    chars: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(value.lower()):
        if ch.isalnum():
            chars.append(ch)
            offsets.append(i)
    return "".join(chars), offsets


def _offset_at(offsets: list[int], index: int, fallback: int) -> int:
    return offsets[index] if index < len(offsets) else fallback


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
    # Compared without whitespace: the UI drops spaces around headings and the
    # PDF wraps the same sentence across lines, so only the characters count.
    u, p = _compact(ui_text), _compact(pdf_text)
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
        self._cache: dict[int, object] = {}

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
            # A document's candidate lines are reused for every UI field, so
            # they are embedded once per document rather than once per field.
            key = hash(tuple(candidates))
            if key not in self._cache:
                self._cache[key] = model.encode(
                    [canonical(c) for c in candidates], normalize_embeddings=True
                )
            candidate_embeddings = self._cache[key]
            query = model.encode([canonical(ui_text)], normalize_embeddings=True)[0]
            scored = [
                (c, float(max(0.0, min(1.0, query @ candidate_embeddings[i]))))
                for i, c in enumerate(candidates)
            ]
        return max(scored, key=lambda pair: pair[1])


def _candidates(text: str) -> list[str]:
    """Non-empty lines of a text blob, used as semantic comparison units."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def _status(score: float, threshold: float, partial_threshold: float) -> str:
    """MATCH, or PARTIAL when only some of the UI text was found."""
    if score >= threshold:
        return "MATCH"
    return "PARTIAL" if score >= partial_threshold else "MISMATCH"


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
    partial_threshold: float = 0.6,
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
                    status=_status(score, threshold, partial_threshold),
                    ui_text=line,
                    pdf_text=best,
                    similarity=score,
                    semantic=True,
                )
            )
        return result

    ui_blocks = locate_ui_blocks(ui_text, pdf_blocks)
    if not ui_blocks:
        # No heading in the section — fall back to locating the text anywhere.
        score = text_similarity(ui_text, pdf_raw)
        result.blocks.append(
            BlockResult(
                heading=section,
                status=(
                    _status(score, threshold, partial_threshold)
                    if score >= partial_threshold else "MISSING_IN_PDF"
                ),
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

        if not ui_block.body.strip() and not pdf_block.body.strip():
            # A parent heading whose text lives entirely in its subsections.
            result.blocks.append(
                BlockResult(
                    heading=ui_block.heading,
                    status="MATCH",
                    ui_text="",
                    pdf_text="",
                    similarity=1.0,
                )
            )
            continue

        pdf_body = pdf_block.body
        if not pdf_body.strip():
            # The heading survived only in the contents listing, so its text
            # sits under a heading PDF extraction lost; look for the UI text
            # anywhere in the document instead.
            pdf_body = pdf_raw

        heading_score = text_similarity(ui_block.title, pdf_block.title)
        body_score = text_similarity(ui_block.body, pdf_body)
        score = min(heading_score, body_score)
        if not ui_block.body.strip() and pdf_block.body.strip():
            status = "MISSING_IN_UI"
        elif not pdf_block.body.strip() and score < partial_threshold:
            status = "MISSING_IN_PDF"
        else:
            status = _status(score, threshold, partial_threshold)
        result.blocks.append(
            BlockResult(
                heading=ui_block.heading,
                status=status,
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
    return [b for b in pdf_blocks if b.number not in seen and b.body.strip()]
