"""Fixed Fountainhead boilerplate (terms, payment conditions, notes,
cancellation, dispute clause) plus the one part of the schedule bullets that
*is* computed: the production/graphics/handover lead-time offsets, which are
a fixed number of days before the show's opening date.

None of this text comes from the uploaded spec PDF -- it is the company's
standard quotation language, reproduced verbatim from the reference BOQ.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Lead-time offsets, in days before the show's opening day, taken from the
# reference BOQ (show opened 8 Oct 2024): technical drawing due 1 Aug (-68d),
# graphics due 5 Aug (-64d), production start 12 Aug (-57d), handover the
# evening before opening (-1d).
TECHNICAL_DRAWING_OFFSET_DAYS = 68
GRAPHICS_OFFSET_DAYS = 64
PRODUCTION_START_OFFSET_DAYS = 57
HANDOVER_OFFSET_DAYS = 1
HANDOVER_TIME = "6 pm"


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _fmt(d: date) -> str:
    return f"{_ordinal(d.day)} {d.strftime('%B')} {d.year}"


@dataclass
class ScheduleDates:
    technical_drawing: date
    graphics: date
    production_start: date
    handover: date
    show_opening: date


def compute_schedule(show_start: date) -> ScheduleDates:
    return ScheduleDates(
        technical_drawing=show_start - timedelta(days=TECHNICAL_DRAWING_OFFSET_DAYS),
        graphics=show_start - timedelta(days=GRAPHICS_OFFSET_DAYS),
        production_start=show_start - timedelta(days=PRODUCTION_START_OFFSET_DAYS),
        handover=show_start - timedelta(days=HANDOVER_OFFSET_DAYS),
        show_opening=show_start,
    )


def schedule_bullets(show_start: date | None) -> list[str]:
    bullets = ["The quotation is valid till 3 working days."]
    if show_start:
        s = compute_schedule(show_start)
        bullets += [
            f"Technical drawing must be finalized by {_fmt(s.technical_drawing)}",
            f"Graphics required {_fmt(s.graphics)}",
            f"Start production at the warehouse {_fmt(s.production_start)}",
            "Build-up - as per construction site available",
            f"Intended date of handing over the stand {_fmt(s.handover)} by {HANDOVER_TIME}.",
            f"Show Opening {_fmt(s.show_opening)}",
            "Dismantling Post show",
        ]
    else:
        bullets += [
            "Technical drawing must be finalized by [pending show date]",
            "Graphics required [pending show date]",
            "Start production at the warehouse [pending show date]",
            "Build-up - as per construction site available",
            "Intended date of handing over the stand [pending show date] by 6 pm.",
            "Show Opening [pending show date]",
            "Dismantling Post show",
        ]
    return bullets


NOT_INCLUDED_INTRO = (
    "Unless stated otherwise, all local- and third-party costs related to the "
    "exhibition are not included in the quotation. One should take into "
    "account the following potential costs:"
)

NOT_INCLUDED_BULLETS = [
    "Main power connection and usage of electricity, water connection, usage "
    "of water, drainage connection and WIFI/Internet connection.",
    "Storage of goods during the exhibition, including equipment and "
    "materials of client.",
    "Waste containers for goods during & after the exhibition including "
    "waste of client.",
    "Fountainhead will not be responsible for any delay caused due to any "
    "services provided by organizer or the third party.",
    "Drayage, rigging and usage of forklifts, scissor lift, transport and "
    "genie support, by the exhibition organization.",
    "Cleaning of the stand during the exhibition.",
    "Static Calculations",
    "Quadro/Truss system",
]

PAYMENT_CONDITIONS = [
    "80% to be paid at the date of order",
    "20% to be paid on 1st day of installation via Bank Transfer or cash.",
    "Advance payment must be credited within a week after receiving the invoice.",
]

NOTES = [
    "Unless stated otherwise, the stand is on a rental base.",
    "Graphic files need to be sent one month before the expo. Further delay, "
    "Fountainhead will not take responsibility of the printing.",
    "Due to the usage of different materials and fabrics, a difference in "
    "color might occur. Fountainhead approaches the specified colors PMS / "
    "RAL / CMYK / NCS in the booth as close as possible. Please let us know "
    "if you have strict guidelines regarding color usage.",
    "Unless stated otherwise, this quotation excludes all local costs such "
    "as suspension, forklift (unloading/loading), rigging, drayage, "
    "electricity, gas and water connection, storage of Fountainhead and "
    "customer equipment during and at the exhibition, all other costs "
    "imposed by the exhibition organization or any other costs by third "
    "parties Fountainhead is obliged to work with. Fountainhead provides "
    "these services at a mark-up of 12.5 %.",
    "The quotation and the subsequent technical drawing are leading for the "
    "actual realization of this project. The visualization is intended as "
    "impression of the design and is only indicative.",
    "Delay in order placing to organizer for rigging, electricity or any "
    "other services. Fountainhead is not responsible for same.",
    "If the technical drawings were not finalized 45 days before the show, "
    "then fountainhead will not be responsible for the changes in the stand "
    "elements/furniture/ av -video due to time frame and late delivery of "
    "the stand.",
    "For each day of delay in payment, the Contractor will be able to "
    "charge, statutory interest.",
    "Dismantling post show will continue only when there are no dues left "
    "from client.",
    "If required, Fountainhead can take help of subcontractors for the job.",
    "In case of delay in getting the possession to work on site because of "
    "organizer or services provided by him, Fountainhead is not responsible "
    "for delay in handover or late delivery and even will charge 10%- 20% "
    "of total invoice for the extra hours of work.",
    "This quotation is only valid, if the design of the booth is approved "
    "by the exhibition organization.",
    "This design is and will remain the intellectual property of "
    "Fountainhead. Only after written approval it can be used by third "
    "parties.",
    "Availability of rental items in this quotation are subject to "
    "availability. When certain rental items are not available, "
    "Fountainhead will offer the best alternative product available.",
    "Rental items are not insured for loss, theft or damages. All costs are "
    "invoiced after the exhibition client must take care to prevent theft "
    "of Audio-Visual equipment during the exhibition.",
    "LED TV, Coffee Machine provided to client, it is client responsibility "
    "to lock coffee machine in the storage room and keep the keys in info "
    "desk counter or handover to the dismantling team. If coffee machine or "
    "LED TV will be stolen, client must be charged for it.",
    "Fountainhead is not responsible for loss, damage or theft of goods "
    "that are not property of Fountainhead during transport, installing and "
    "dismantling.",
    "The stand is wipe-clean at the delivery date.",
    "In case of non - receipt of graphic files and payment as per the "
    "scheduled agreed above, this contract is considered as void",
    "In the case of non-payment of the second/final payment, delivery of "
    "the stand can be stopped or Fountainhead has the right to dismantle "
    "the stand.",
    "The pricing for the booth is determined under the assumption that a "
    "minimum of three to four consecutive days will be allocated for "
    "construction, in accordance with the standard duration required for "
    "unloading and buildup.",
    "All the stand construction will be finished apart from fascia LOGO, "
    "that will be done in the last on receipt of balance payments.",
]

CANCELLATION_TEXT = (
    "In case of cancellation of the contract by the client, Fountainhead "
    "shall be entitled to compensation amounting to 20-40% advance payment "
    "on account and to claim damages in the amount corresponding to the "
    "costs incurred and loss of profits by the Fountainhead does not exceed "
    "the total amount of remuneration, if Fountainhead cancels the contract "
    "for any reasons, Fountainhead will refund the amount."
)

DISPUTE_TEXT = (
    "Any disputes that may arise on the background of this Agreement, the "
    "Parties shall endeavor to settle amicably through negotiations or it "
    "will be taken to Amsterdam court for legal proceedings. In the absence "
    "of agreement, the Parties shall submit the outcome to the competent "
    "Court faculty popular for the seat of the Contractor."
)

# Fixed line items -- these are Fountainhead-standard placeholders, always
# quoted at 0 (priced separately), never derived from the spec PDF.
INSTALLATION_SECTION = [
    ("0,0", "Preparation, Installation, Dismantling"),
    ("0,0", "Transportation of material"),
    ("0,0", "Transport staff"),
    ("0,0", "Scaffolding, lifts & stairs"),
]
