"""XMLTV generator (DESIGN.md §9)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..planner.expander import EpgProgramme
from ..planner.model import ChannelSpec
from ..schemas import XMLTV_GENERATOR_NAME, XMLTV_SOURCE_NAME


def _xmltv_time(dt) -> str:
    """XMLTV time: `YYYYMMDDHHMMSS ±HHMM`."""
    off = dt.utcoffset()
    total_min = int(off.total_seconds() // 60) if off else 0
    sign = "-" if total_min < 0 else "+"
    abs_min = abs(total_min)
    hh, mm = divmod(abs_min, 60)
    return dt.strftime("%Y%m%d%H%M%S") + f" {sign}{hh:02d}{mm:02d}"


def render_channel_xmltv(
    channel: ChannelSpec,
    programmes: list[EpgProgramme],
    *,
    icon_url: str | None = None,
) -> bytes:
    root = etree.Element(
        "tv",
        attrib={
            "generator-info-name": XMLTV_GENERATOR_NAME,
            "source-info-name": XMLTV_SOURCE_NAME,
        },
    )
    ch = etree.SubElement(root, "channel", id=channel.tuning)
    disp = etree.SubElement(ch, "display-name", lang=channel.language or "en")
    disp.text = channel.name
    if icon_url or channel.icon:
        etree.SubElement(ch, "icon", src=icon_url or channel.icon or "")

    for p in programmes:
        pe = etree.SubElement(
            root,
            "programme",
            attrib={
                "start": _xmltv_time(p.start),
                "stop": _xmltv_time(p.finish),
                "channel": channel.tuning,
            },
        )
        title = etree.SubElement(pe, "title", lang=channel.language or "en")
        title.text = p.title
        if p.description:
            desc = etree.SubElement(pe, "desc", lang=channel.language or "en")
            desc.text = p.description
        if p.category:
            cat = etree.SubElement(pe, "category", lang=channel.language or "en")
            cat.text = p.category

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype='<!DOCTYPE tv SYSTEM "xmltv.dtd">',
    )


def merge_xmltv_files(paths: list[str | Path], output_path: str | Path) -> Path:
    """Concatenate per-channel XMLTV files into a single document."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    root = etree.Element(
        "tv",
        attrib={
            "generator-info-name": XMLTV_GENERATOR_NAME,
            "source-info-name": XMLTV_SOURCE_NAME,
        },
    )
    for p in paths:
        p_path = Path(p)
        if not p_path.exists():
            continue
        doc = etree.parse(str(p_path))
        for node in doc.getroot():
            root.append(node)
    data = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype='<!DOCTYPE tv SYSTEM "xmltv.dtd">',
    )
    out.write_bytes(data)
    return out


__all__ = ["merge_xmltv_files", "render_channel_xmltv"]
