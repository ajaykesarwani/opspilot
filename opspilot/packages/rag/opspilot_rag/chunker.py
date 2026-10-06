"""Structure-aware chunking for markdown-like text."""

import hashlib
import re

_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


def generate_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DocumentChunker:
    """Splits text at markdown headings first, then packs paragraphs up to `chunk_size`.

    Keeping a heading together with its body means a retrieved chunk is self-describing
    ("## Billing Disputes ...") and unrelated policies never share a chunk. Only a single
    paragraph longer than `chunk_size` is split, on word boundaries, with `chunk_overlap`
    characters of overlap.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_overlap must satisfy 0 <= chunk_overlap < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        chunks: list[str] = []
        for section in self._sections(text):
            if len(section) <= self.chunk_size:
                chunks.append(section)
            else:
                chunks.extend(self._split_long_section(section))
        return chunks

    @staticmethod
    def _sections(text: str) -> list[str]:
        starts = [m.start() for m in _HEADING.finditer(text)]
        if not starts or starts[0] != 0:
            starts.insert(0, 0)
        bounds = [*starts, len(text)]
        sections = (text[a:b].strip() for a, b in zip(bounds, bounds[1:], strict=False))
        return [s for s in sections if s]

    def _split_long_section(self, section: str) -> list[str]:
        out: list[str] = []
        current = ""
        for paragraph in re.split(r"\n\s*\n", section):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) > self.chunk_size:
                if current:
                    out.append(current)
                    current = ""
                out.extend(self._split_words(paragraph))
            elif current and len(current) + 2 + len(paragraph) > self.chunk_size:
                out.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            out.append(current)
        return out

    def _split_words(self, text: str) -> list[str]:
        words = text.split()
        pieces: list[str] = []
        start = 0
        while start < len(words):
            end, length = start, 0
            while end < len(words) and length + len(words[end]) + (1 if length else 0) <= (
                self.chunk_size
            ):
                length += len(words[end]) + (1 if length else 0)
                end += 1
            end = max(end, start + 1)  # always make progress, even for one giant "word"
            pieces.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            # Step back far enough to carry ~chunk_overlap characters into the next piece.
            back, carried = end, 0
            while back > start + 1 and carried + len(words[back - 1]) + 1 <= self.chunk_overlap:
                back -= 1
                carried += len(words[back]) + 1
            start = back
        return pieces
