"""Decipher a Dayforce charge string such as

    101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis

Segments are separated by '>'. The PRJ segment is 'PRJ<digits> - <project name>' and the PT segment is
'PT<digits>: <task name>'. Anything else (department prefix, 'General', ...) is kept as-is.
The raw string is what gets stored and copied back out, so parsing is deliberately forgiving.
"""
import re
from dataclasses import dataclass

_PRJ = re.compile(r"^(PRJ\d+)\s*(?:[-–—:]\s*(.*))?$", re.IGNORECASE)
_PT = re.compile(r"^(PT\d+)\s*(?:[-–—:]\s*(.*))?$", re.IGNORECASE)


@dataclass(frozen=True)
class ChargeString:
    raw: str
    prj_code: str
    prj_name: str
    pt_code: str
    pt_name: str
    other_segments: tuple[str, ...]

    @property
    def suggested_name(self) -> str:
        parts = [p for p in (self.prj_name or self.prj_code, self.pt_name or self.pt_code) if p]
        return " / ".join(parts) or self.raw


def normalize(raw: str) -> str:
    """Trim the ends and collapse line breaks; never touch the characters inside."""
    return " ".join((raw or "").split())


def parse_charge_string(raw: str) -> ChargeString:
    text = normalize(raw)
    if not text:
        raise ValueError("The charge string is empty.")
    prj_code = prj_name = pt_code = pt_name = ""
    others = []
    for segment in (s.strip() for s in text.split(">")):
        prj, pt = _PRJ.match(segment), _PT.match(segment)
        if prj and not prj_code:
            prj_code, prj_name = prj.group(1).upper(), (prj.group(2) or "").strip()
        elif pt and not pt_code:
            pt_code, pt_name = pt.group(1).upper(), (pt.group(2) or "").strip()
        elif segment:
            others.append(segment)
    return ChargeString(text, prj_code, prj_name, pt_code, pt_name, tuple(others))
