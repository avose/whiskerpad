from __future__ import annotations

import re
from typing import Callable, List, Set

__all__ = [
    "TOKEN_RE",
    "make_img_token",
    "parse_img_token_line",
    "extract_img_filenames",
    "referenced_images",
    "map_img_tokens",
]

# Block-only token, one per line:
#   {{img "FILENAME"}}
# Leading/trailing whitespace on the line is allowed.
TOKEN_RE = re.compile(r'^\s*\{\{\s*img\s+"([^"\r\n]+)"\s*\}\}\s*$', re.MULTILINE)


def make_img_token(filename: str) -> str:
    """
    Build a canonical block token from a filename.
    Rejects quotes/newlines to keep tokens simple and grep-able.
    """
    if '"' in filename or "\n" in filename or "\r" in filename:
        raise ValueError("filename may not contain quotes or newlines")
    return f'{{{{img "{filename}"}}}}'


def parse_img_token_line(line: str) -> str | None:
    """
    If `line` is an image-token line, return the filename; else None.
    """
    m = TOKEN_RE.match(line)
    return m.group(1) if m else None


def extract_img_filenames(text: str) -> List[str]:
    """
    Return all image filenames referenced by tokens in `text`.
    """
    return [m.group(1) for m in TOKEN_RE.finditer(text)]


def referenced_images(text: str) -> Set[str]:
    """
    Return a set of unique image filenames referenced in `text`.
    """
    return set(extract_img_filenames(text))


def map_img_tokens(text: str, mapper: Callable[[str], str]) -> str:
    """
    Replace each token's filename by mapper(old)->new.
    Preserves surrounding whitespace and token formatting by
    substituting only the captured filename.
    """
    def _repl(m: re.Match) -> str:
        old = m.group(1)
        new = mapper(old)
        if new == old:
            return m.group(0)
        if '"' in new or "\n" in new or "\r" in new:
            raise ValueError("mapped filename contains invalid characters")
        return m.group(0).replace(old, new)

    return TOKEN_RE.sub(_repl, text)

