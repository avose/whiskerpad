from __future__ import annotations
from typing import List, Dict, Any, Tuple

def flatten_ops(ops: List[Dict[str, Any]] | None) -> str:
    """Concatenate Quill-like ops into a single string; normalize CR to LF-only.
    No exceptions: ignore non-dict items; coerce non-str inserts via str().
    """
    if not ops:
        return ""
    parts: List[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        val = op.get("insert", "")
        if not isinstance(val, str):
            val = str(val)
        parts.append(val)
    return "".join(parts).replace("\r", "")
def text_from_entry(entry: Dict[str, Any]) -> str:
    """Prefer entry['ops']; fall back to title (no forced newline)."""
    txt = flatten_ops(entry.get("ops"))
    if txt:
        return txt
    title = (entry.get("title") or "")
    return title.replace("\r", "")

def wrap_lines(para: str, maxw: int, dc, out: List[str]) -> None:
    """Greedy word-wrap with char fallback for long tokens."""
    if para == "":
        out.append("")
        return
    words = para.split(" ")
    space_w = dc.GetTextExtent(" ")[0]
    cur = ""
    cur_w = 0
    for w in words:
        tw = dc.GetTextExtent(w)[0]
        if not cur:
            if tw <= maxw:
                cur, cur_w = w, tw
            else:
                for ch in w:
                    cw = dc.GetTextExtent(ch)[0]
                    if cur and cur_w + cw > maxw:
                        out.append(cur); cur = ""; cur_w = 0
                    cur += ch; cur_w += cw
        else:
            if cur_w + space_w + tw <= maxw:
                cur += " " + w; cur_w += space_w + tw
            else:
                out.append(cur)
                if tw <= maxw:
                    cur, cur_w = w, tw
                else:
                    cur = ""; cur_w = 0
                    for ch in w:
                        cw = dc.GetTextExtent(ch)[0]
                        if cur and cur_w + cw > maxw:
                            out.append(cur); cur = ""; cur_w = 0
                        cur += ch; cur_w += cw
    if cur:
        out.append(cur)

def measure_wrapped(text: str, maxw: int, dc, font, padding: int) -> Tuple[List[str], int, int]:
    """
    Returns (lines, line_height, total_height_with_padding).

    We trim exactly one trailing '\n' for measurement to avoid a phantom blank line
    (useful for brand-new nodes that may save/emit a trailing newline).
    """
    t = (text or "").replace("\r", "")
    if t.endswith("\n"):
        t = t[:-1]

    dc.SetFont(font)
    lh = dc.GetTextExtent("Ag")[1]
    lines: List[str] = []
    for para in t.split("\n"):
        wrap_lines(para, maxw, dc, lines)
    if not lines:
        lines = [""]
    total_h = len(lines) * lh + 2 * padding
    return lines, lh, total_h
