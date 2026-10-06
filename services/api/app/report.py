"""Human-readable report (HTML, print to PDF) rendered from the claim packet — never the other way round."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.schema.claim_packet import ClaimPacket, PriceQuote

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_report(packet: ClaimPacket, frame_base_url: str) -> str:
    currency = packet.sweep.currency

    def money(value: float | None) -> str:
        return "—" if value is None else f"{currency} {value:,.0f}"

    def dim(value: float | None, unit: str) -> str:
        return "—" if value is None else f"{value:,.2f} {unit}".strip()

    def quote(q: PriceQuote) -> str:
        if q.amount is None:
            return "—"
        parts = [f"{escape(q.currency)} {q.amount:,.0f}",
                 f'<br><a class="src" href="{escape(q.url)}">{escape(q.source)}</a>',
                 f'<br><span class="src">{escape(q.retrieved_at)}'
                 + (f" · {escape(q.condition_assumed)}" if q.condition_assumed else "") + "</span>"]
        if q.converted:
            parts.append(f'<br><span class="conv">converted from {escape(q.original_currency)} '
                         f"{q.original_amount:,.2f} @ {escape(str(q.fx_rate))}</span>")
        return Markup("".join(parts))

    def frame_url(ref: str) -> str:
        return f"{frame_base_url.rstrip('/')}/frames/{ref}"

    return _env.get_template("report.html").render(
        p=packet, t=packet.totals, r=packet.room, money=money, dim=dim, quote=quote, frame_url=frame_url
    )
