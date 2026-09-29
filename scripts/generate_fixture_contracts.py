"""Generate the two Task-Set-F fixture contracts.

Both contracts carry a Definitions section with capitalized defined terms
(e.g. "Cause", "Notice Period") that the Termination clause references
without restating their meaning. Answering a termination question about
either contract therefore requires a second lookup (get_definitions) after
the first clause search -- the defined-term-chase pattern Task Set F asks
the race to cover. Run once: `python scripts/generate_fixture_contracts.py`.
"""

from pathlib import Path

from fpdf import FPDF

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"


def make_pdf(filename: str, title: str, sections: list[tuple[str, str]]) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 10, title)
    pdf.ln(2)

    for heading, body in sections:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 8, heading)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, body)
        pdf.ln(2)

    out_path = CONTRACTS_DIR / filename
    pdf.output(str(out_path))
    print(f"Wrote {out_path}")


MSA_SECTIONS = [
    ("Parties", "Vendor: Orion Analytics Inc. Client: Delta Retail Group LLC."),
    (
        "Effective Date",
        'This Agreement is effective as of 1 April 2025 (the "Effective Date").',
    ),
    (
        "Definitions",
        '"Cause" means a material breach of this Agreement that the breaching '
        "party fails to cure within fifteen (15) days after receiving written "
        'notice describing the breach. "Notice Period" means thirty (30) days. '
        '"Renewal Term" means successive periods of twelve (12) months '
        "following the first anniversary of the Effective Date.",
    ),
    (
        "Termination",
        'Either party may terminate this Agreement for Cause, effective '
        "immediately upon expiry of the cure period described in the "
        "definition of Cause if the breach remains uncured. Either party "
        "may also terminate this Agreement for convenience by giving the "
        "other party the Notice Period in advance, in writing.",
    ),
    (
        "Governing Law",
        "This Agreement is governed by the laws of the State of Delaware.",
    ),
]

SLA_SECTIONS = [
    ("Parties", "Licensor: NovaCloud Systems Inc. Licensee: Harborview Logistics Ltd."),
    (
        "Effective Date",
        'This Agreement is effective as of 15 September 2025 (the "Effective Date").',
    ),
    (
        "Definitions",
        '"Initial Term" means the period of twelve (12) months beginning on '
        'the Effective Date. "Termination Notice Period" means forty-five '
        '(45) days. "Renewal Date" means the day immediately following the '
        "last day of the Initial Term.",
    ),
    (
        "Termination",
        "This Agreement automatically renews for successive Renewal Terms "
        "unless either party provides written notice of non-renewal at "
        "least the Termination Notice Period before the Renewal Date. "
        "Either party may also terminate this Agreement for material "
        "breach that remains uncured for thirty (30) days after written "
        "notice.",
    ),
    (
        "Governing Law",
        "This Agreement is governed by the laws of the State of New York.",
    ),
]


def main() -> None:
    make_pdf("Master_Service_Agreement.pdf", "Master Services Agreement", MSA_SECTIONS)
    make_pdf("Software_License_Agreement.pdf", "Software License Agreement", SLA_SECTIONS)


if __name__ == "__main__":
    main()
