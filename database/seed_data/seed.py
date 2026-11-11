"""Deterministic synthetic seed data.

    python -m database.seed_data.seed            # reset + seed
    python -m database.seed_data.seed --reset    # reset only

ALL DATA IS SYNTHETIC. No real TBO customer, agency, booking or passenger data
is used anywhere in OpsDesk. Fixtures are positioned relative to ``now`` so the
SLA demonstration (LCD in ~54 minutes, check-in in ~90 minutes) is reproducible
whenever the seed runs.
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import delete, func, select

from backend.database import SessionLocal, init_db
from backend.models import (
    ActivityTimeline,
    AgentRun,
    Agency,
    Booking,
    EscalationRecord,
    ExportJob,
    Message,
    ProductBug,
    RoutingAudit,
    SideConversation,
    SideMessage,
    ThemeTag,
    Ticket,
    TicketLink,
    TicketTransfer,
    User,
)
from backend.models.base import utcnow
from backend.security import hash_password
from backend.services import assignment, sla as sla_service
from backend.services.classifier import get_classifier
from backend.services.linking import build_case_links

DEMO_PASSWORD = "OpsDesk#2026"

# --------------------------------------------------------------------- fixtures

AGENCY_SPECS = [
    {"code": "AG-WLT", "name": "Wanderlust Travels", "tier": "GOLD", "region": "MEA",
     "contact_email": "ops@wanderlust-travels.com"},
    {"code": "AG-AGH", "name": "Apex Global Holidays", "tier": "SILVER", "region": "APAC",
     "contact_email": "desk@apexglobalholidays.com"},
    {"code": "AG-EWB", "name": "EuroWings B2B", "tier": "SILVER", "region": "EU",
     "contact_email": "groups@eurowings-b2b.com"},
    {"code": "AG-SKY", "name": "Skyline Corporate Travel", "tier": "BRONZE", "region": "APAC",
     "contact_email": "travel@skylinecorp.com"},
]

USER_SPECS = [
    # agency requesters
    {"email": "maya.requester@wanderlust-travels.com", "full_name": "Maya Al Farsi",
     "role": "AGENCY_REQUESTER", "region": "MEA", "tz": "Asia/Dubai", "shift": ("00:00", "23:59"),
     "skill": 2, "cap": 20, "online": True, "agency": "AG-WLT"},
    {"email": "kai.requester@apexglobalholidays.com", "full_name": "Kai Tanaka",
     "role": "AGENCY_REQUESTER", "region": "APAC", "tz": "Asia/Singapore", "shift": ("00:00", "23:59"),
     "skill": 2, "cap": 20, "online": True, "agency": "AG-AGH"},
    {"email": "lena.requester@eurowings-b2b.com", "full_name": "Lena Fischer",
     "role": "AGENCY_REQUESTER", "region": "EU", "tz": "Europe/Paris", "shift": ("00:00", "23:59"),
     "skill": 2, "cap": 20, "online": True, "agency": "AG-EWB"},
    {"email": "andre.requester@skylinecorp.com", "full_name": "Andre Silva",
     "role": "AGENCY_REQUESTER", "region": "APAC", "tz": "Asia/Singapore", "shift": ("00:00", "23:59"),
     "skill": 2, "cap": 20, "online": True, "agency": "AG-SKY"},
    # operations agents
    {"email": "ananya.sharma@tbo.com", "full_name": "Ananya Sharma", "role": "OPS_AGENT",
     "region": "APAC", "tz": "Asia/Singapore", "shift": ("00:00", "23:59"), "skill": 5, "cap": 8,
     "online": True},
    {"email": "daniel.okafor@tbo.com", "full_name": "Daniel Okafor", "role": "OPS_AGENT",
     "region": "AMER", "tz": "America/New_York", "shift": ("00:00", "23:59"), "skill": 4, "cap": 6,
     "online": True},
    {"email": "mei.chen@tbo.com", "full_name": "Mei Chen", "role": "OPS_AGENT",
     "region": "APAC", "tz": "Asia/Singapore", "shift": ("00:00", "23:59"), "skill": 3, "cap": 8,
     "online": True},
    {"email": "rahul.mehta@tbo.com", "full_name": "Rahul Mehta", "role": "OPS_AGENT",
     "region": "APAC", "tz": "Asia/Kolkata", "shift": ("00:00", "23:59"), "skill": 5, "cap": 8,
     "online": True},
    {"email": "sofia.lindqvist@tbo.com", "full_name": "Sofia Lindqvist", "role": "OPS_AGENT",
     "region": "EU", "tz": "Europe/Paris", "shift": ("00:00", "23:59"), "skill": 4, "cap": 8,
     "online": True},
    {"email": "omar.haddad@tbo.com", "full_name": "Omar Haddad", "role": "OPS_AGENT",
     "region": "MEA", "tz": "Asia/Dubai", "shift": ("00:00", "23:59"), "skill": 4, "cap": 8,
     "online": True},
    {"email": "lucas.moreau@tbo.com", "full_name": "Lucas Moreau", "role": "OPS_AGENT",
     "region": "EU", "tz": "Europe/Paris", "shift": ("22:00", "06:00"), "skill": 5, "cap": 8,
     "online": True},
    {"email": "ethan.blake@tbo.com", "full_name": "Ethan Blake", "role": "OPS_AGENT",
     "region": "EU", "tz": "Europe/London", "shift": ("00:00", "00:00"), "skill": 5, "cap": 8,
     "online": True},
    {"email": "priya.nair@tbo.com", "full_name": "Priya Nair", "role": "OPS_AGENT",
     "region": "MEA", "tz": "Asia/Kolkata", "shift": ("05:00", "23:00"), "skill": 5, "cap": 8,
     "online": False},
    # escalation managers
    {"email": "elena.rossi@tbo.com", "full_name": "Elena Rossi", "role": "ESCALATION_MANAGER",
     "region": "EU", "tz": "Europe/Paris", "shift": ("00:00", "23:59"), "skill": 5, "cap": 12,
     "online": True},
    {"email": "vikram.rao@tbo.com", "full_name": "Vikram Rao", "role": "ESCALATION_MANAGER",
     "region": "APAC", "tz": "Asia/Kolkata", "shift": ("00:00", "23:59"), "skill": 5, "cap": 12,
     "online": True},
    # operations lead
    {"email": "nisha.verma@tbo.com", "full_name": "Nisha Verma", "role": "OPS_LEAD",
     "region": "MEA", "tz": "Asia/Kolkata", "shift": ("00:00", "23:59"), "skill": 5, "cap": 20,
     "online": True},
]

BOOKING_SPECS = [
    # key, tboh, agency, supplier, hotel, city, country, region, tz, check_in_h, lcd_h,
    # status, amount, currency, passenger
    {"key": "A", "tboh_id": "TBOH-778899", "agency": "AG-WLT", "supplier": "Hotelbeds",
     "supplier_email": "reservations@hotelbeds.com", "hotel": "Atlantis The Palm",
     "city": "Dubai", "country": "United Arab Emirates", "region": "MEA", "tz": "Asia/Dubai",
     "check_in_h": 120, "lcd_h": -72, "status": "REFUND_PENDING", "amount": 1450, "currency": "USD",
     "passenger": "Rashid Al Nuaimi"},
    {"key": "B", "tboh_id": "TBOH-554411", "agency": "AG-AGH", "supplier": "Agoda",
     "supplier_email": "partners@agoda.com", "hotel": "Marina Bay Sands",
     "city": "Singapore", "country": "Singapore", "region": "APAC", "tz": "Asia/Singapore",
     "check_in_h": 44, "lcd_h": 720, "status": "CONFIRMED", "amount": 2380, "currency": "SGD",
     "passenger": "Wei Ling Tan"},
    {"key": "C", "tboh_id": "TBOH-301332", "agency": "AG-EWB", "supplier": "Hilton",
     "supplier_email": "groups@hilton-paris.com", "hotel": "Hilton Paris Opera",
     "city": "Paris", "country": "France", "region": "EU", "tz": "Europe/Paris",
     "check_in_h": 42, "lcd_h": 22, "status": "CONFIRMED", "amount": 1860, "currency": "EUR",
     "passenger": "Claire Dubois"},
    {"key": "D1", "tboh_id": "TBOH-410551", "agency": "AG-EWB", "supplier": "Hilton",
     "supplier_email": "ops@hilton-paris.com", "hotel": "Hilton Paris Opera",
     "city": "Paris", "country": "France", "region": "EU", "tz": "Europe/Paris",
     "check_in_h": 50, "lcd_h": 2.9, "status": "CONFIRMED", "amount": 2140, "currency": "EUR",
     "passenger": "Marc Lefevre"},
    {"key": "D2", "tboh_id": "TBOH-410552", "agency": "AG-AGH", "supplier": "Agoda",
     "supplier_email": "partners@agoda.com", "hotel": "Marina Bay Sands",
     "city": "Singapore", "country": "Singapore", "region": "APAC", "tz": "Asia/Singapore",
     "check_in_h": 1.5, "lcd_h": 48, "status": "CONFIRMED", "amount": 1320, "currency": "SGD",
     "passenger": "Hiroshi Sato"},
    {"key": "E1", "tboh_id": "TBOH-640017", "agency": "AG-SKY", "supplier": "Accor",
     "supplier_email": "api-support@accor.com", "hotel": "Novotel Bangkok Sukhumvit",
     "city": "Bangkok", "country": "Thailand", "region": "APAC", "tz": "Asia/Bangkok",
     "check_in_h": 600, "lcd_h": 400, "status": "CONFIRMED", "amount": 940, "currency": "USD",
     "passenger": "Somsak Chaiyaporn"},
    {"key": "E2", "tboh_id": "TBOH-118820", "agency": "AG-WLT", "supplier": "Rotana",
     "supplier_email": "reservations@rotana.com", "hotel": "Rotana Downtown Dubai",
     "city": "Dubai", "country": "United Arab Emirates", "region": "MEA", "tz": "Asia/Dubai",
     "check_in_h": 500, "lcd_h": 300, "status": "CONFIRMED", "amount": 780, "currency": "USD",
     "passenger": "Yusuf Karim"},
    {"key": "E3", "tboh_id": "TBOH-461021", "agency": "AG-EWB", "supplier": "Accor",
     "supplier_email": "api-support@accor.com", "hotel": "Ibis Styles Bali",
     "city": "Bali", "country": "Indonesia", "region": "APAC", "tz": "Asia/Makassar",
     "check_in_h": 460, "lcd_h": 260, "status": "CONFIRMED", "amount": 690, "currency": "EUR",
     "passenger": "Nina Kovač"},
    {"key": "E4", "tboh_id": "TBOH-903114", "agency": "AG-WLT", "supplier": "Hotelbeds",
     "supplier_email": "reservations@hotelbeds.com", "hotel": "Fairmont The Palm",
     "city": "Dubai", "country": "United Arab Emirates", "region": "MEA", "tz": "Asia/Dubai",
     "check_in_h": 380, "lcd_h": 200, "status": "CONFIRMED", "amount": 1980, "currency": "USD",
     "passenger": "Aisha Rahman"},
    {"key": "E5", "tboh_id": "TBOH-552208", "agency": "AG-AGH", "supplier": "Marriott",
     "supplier_email": "connect@marriott.com", "hotel": "Marriott Marquis",
     "city": "Bangkok", "country": "Thailand", "region": "APAC", "tz": "Asia/Bangkok",
     "check_in_h": 320, "lcd_h": 150, "status": "CONFIRMED", "amount": 1560, "currency": "SGD",
     "passenger": "Daniel Wong"},
    {"key": "E6", "tboh_id": "TBOH-771204", "agency": "AG-SKY", "supplier": "WebBeds",
     "supplier_email": "support@webbeds.com", "hotel": "Kempinski Bali",
     "city": "Bali", "country": "Indonesia", "region": "APAC", "tz": "Asia/Makassar",
     "check_in_h": 260, "lcd_h": 120, "status": "CONFIRMED", "amount": 1120, "currency": "USD",
     "passenger": "Grace Lim"},
    {"key": "E7", "tboh_id": "TBOH-228640", "agency": "AG-EWB", "supplier": "Hilton",
     "supplier_email": "groups@hilton-paris.com", "hotel": "DoubleTree by Hilton London",
     "city": "London", "country": "United Kingdom", "region": "EU", "tz": "Europe/London",
     "check_in_h": 200, "lcd_h": 90, "status": "CONFIRMED", "amount": 1340, "currency": "GBP",
     "passenger": "Oliver Grant"},
]

# ---------------------------------------------------------------- named tickets
# age_h = hours since creation; res_h = hours after creation the ticket was resolved
TICKET_SPECS = [
    {"number": "TCK-101", "booking": "A", "title": "Refund not received for cancelled Atlantis stay",
     "description": ("We cancelled the stay for our client at Atlantis The Palm and the refund of "
                     "USD 1,450 has still not been credited. Booking TBOH-778899."),
     "intent": "REFUND_DELAY", "priority": "HIGH", "status": "IN_PROGRESS", "queue": "MEA-SUPPORT",
     "agent": "Omar Haddad", "age_h": 480},
    {"number": "TCK-104", "booking": "A", "title": "Follow up on USD 1,450 refund (TBOH-778899)",
     "description": ("Second chase on the same refund. Supplier says the credit is pending with their "
                     "finance team. Passenger is asking daily."),
     "intent": "REFUND_DELAY", "priority": "HIGH", "status": "PENDING_SUPPLIER",
     "queue": "MEA-SUPPORT", "agent": "Omar Haddad", "age_h": 288},
    {"number": "TCK-109", "booking": "A", "title": "Refund credit note still not issued",
     "description": ("Third contact on TBOH-778899. Cancellation was completed within the LCD. "
                     "Requesting a credit note reference for USD 1,450."),
     "intent": "REFUND_DELAY", "priority": "MEDIUM", "status": "OPEN", "queue": "MEA-SUPPORT",
     "agent": None, "age_h": 168},
    {"number": "TCK-201", "booking": "B", "title": "Voucher confirmation required before arrival",
     "description": ("Marina Bay Sands has no confirmation on file for TBOH-554411 and the guest "
                     "arrives in under 48 hours. Please send the voucher urgently."),
     "intent": "VOUCHER_CONFIRMATION_ISSUE", "priority": "HIGH", "status": "IN_PROGRESS",
     "queue": "APAC-SUPPORT", "agent": "Ananya Sharma", "age_h": 18},
    {"number": "TCK-205", "booking": "B", "title": "Refund of deposit not received",
     "description": ("The deposit charged for the Marina Bay Sands booking was cancelled and the "
                     "refund has not been credited after 12 days."),
     "intent": "REFUND_DELAY", "priority": "MEDIUM", "status": "OPEN", "queue": "APAC-SUPPORT",
     "agent": "Rahul Mehta", "age_h": 96},
    {"number": "TCK-301", "booking": "C", "title": "Group allocation confirmation for Hilton Paris Opera",
     "description": ("We need written confirmation of the 12-room group allocation and the group rate "
                     "for TBOH-301332 ahead of arrival."),
     "intent": "VOUCHER_CONFIRMATION_ISSUE", "priority": "MEDIUM", "status": "PENDING_SUPPLIER",
     "queue": "EU-TRIAGE", "agent": "Sofia Lindqvist", "age_h": 18,
     "side_conversation": {
         "channel": "SUPPLIER", "subject": "12-room group allocation & rate confirmation",
         "counterparty": "Hilton Paris Opera", "recipients": ["groups@hilton-paris.com"],
         "messages": [
             ("reservations@eurowings-b2b.com", "groups@hilton-paris.com",
              "Please confirm the 12-room group block and the agreed group rate for TBOH-301332.", "OUTBOUND"),
             ("groups@hilton-paris.com", "reservations@eurowings-b2b.com",
              "We have the block on hold; written confirmation will follow once the rate is revalidated.", "INBOUND"),
             ("reservations@eurowings-b2b.com", "groups@hilton-paris.com",
              "Thank you — our guest arrives in two days, we need the confirmation today.", "OUTBOUND"),
         ],
     }},
    {"number": "TCK-401", "booking": "D1", "title": "Cancellation waiver required before LCD",
     "description": ("Agency requests a cancellation waiver for TBOH-410551. The LCD closes within "
                     "three hours and the guest is hospitalised. Regional holiday operating window "
                     "applies."),
     "intent": "CANCELLATION_LCD_WAIVER", "priority": "HIGH", "status": "IN_PROGRESS",
     "queue": "EU-TRIAGE", "agent": "Sofia Lindqvist", "age_h": 3, "holiday": True},
    {"number": "TCK-402", "booking": "D2", "title": "Guest check-in in 90 minutes — no confirmation",
     "description": ("The guest is checking in within 90 minutes and the supplier still has no "
                     "confirmation on file. We need an immediate confirmation or a relocation."),
     "intent": "VOUCHER_CONFIRMATION_ISSUE", "priority": "CRITICAL", "status": "IN_PROGRESS",
     "queue": "APAC-SUPPORT", "agent": "Rahul Mehta", "age_h": 3},
    {"number": "TCK-403", "booking": "E1", "title": "Overbooking relocation at Rotana Downtown",
     "description": ("Supplier reports the property is overbooked and our guest must be relocated "
                     "tonight. Pre-escalated to the Escalation Manager on duty."),
     "intent": "SUPPLIER_OVERBOOKING_RELOCATION", "priority": "CRITICAL", "status": "ESCALATED",
     "queue": "ESCALATION_MANAGER", "agent": "Elena Rossi", "age_h": 9, "escalated": "Elena Rossi"},
    {"number": "TCK-404", "booking": "E6", "title": "Rate cache mismatch escalated by agency",
     "description": ("The agency reports repeated rate mismatches on the same property and asks for "
                     "an escalation after three failed bookings."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "HIGH", "status": "ESCALATED",
     "queue": "ESCALATION_MANAGER", "agent": "Vikram Rao", "age_h": 26, "escalated": "Vikram Rao"},
    {"number": "TCK-501", "booking": "E1", "title": "Rate mismatch on Hotelbeds API for Ibis Styles Bali",
     "description": ("Supplier API returned a rate mismatch error code 402 between search and book "
                     "for Ibis Styles Bali; looks like a cache bug."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "MEDIUM", "status": "OPEN",
     "queue": "APAC-SUPPORT", "agent": None, "age_h": 30},
    {"number": "TCK-502", "booking": "E3", "title": "Rate mismatch on Hotelbeds API for Ibis Styles Bali",
     "description": ("Second report of the same rate mismatch: availability shows in search but the "
                     "book call returns a different rate for Ibis Styles Bali."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "MEDIUM", "status": "OPEN",
     "queue": "APAC-SUPPORT", "agent": "Rahul Mehta", "age_h": 54},
    {"number": "TCK-503", "booking": "E6", "title": "Inventory sync failure on WebBeds availability",
     "description": ("Availability is stale for Kempinski Bali on the WebBeds API and bookings fail "
                     "with an inventory error."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "HIGH", "status": "IN_PROGRESS",
     "queue": "APAC-SUPPORT", "agent": "Mei Chen", "age_h": 72},
    {"number": "TCK-504", "booking": "E5", "title": "Marriott cache bug rejected our booking",
     "description": ("Marriott API rejected the booking with a cache error although the room showed "
                     "as available in search results."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "MEDIUM", "status": "OPEN",
     "queue": "APAC-SUPPORT", "agent": None, "age_h": 26},
    {"number": "TCK-505", "booking": "E2", "title": "Rotana rate mismatch between search and book",
     "description": ("Rate mismatch reported by the agency on Rotana Downtown Dubai: the search rate "
                     "does not match the API response at confirmation."),
     "intent": "INVENTORY_RATE_SYNC_BUG", "priority": "MEDIUM", "status": "RESOLVED",
     "queue": "MEA-SUPPORT", "agent": "Omar Haddad", "age_h": 120, "res_h": 88},
    {"number": "TCK-506", "booking": "E4", "title": "Honeymoon setup for Fairmont The Palm stay",
     "description": ("Client requests honeymoon decoration, flowers and a cake in the room for the "
                     "Fairmont The Palm stay."),
     "intent": "SPECIAL_REQUEST", "priority": "LOW", "status": "OPEN", "queue": "MEA-SUPPORT",
     "agent": "Omar Haddad", "age_h": 40},
    {"number": "TCK-507", "booking": "E7", "title": "Special request for the DoubleTree stay",
     "description": ("Guest requests connecting rooms and an early check-in for the family at "
                     "DoubleTree by Hilton London."),
     "intent": "SPECIAL_REQUEST", "priority": "LOW", "status": "IN_PROGRESS",
     "queue": "EU-TRIAGE", "agent": "Sofia Lindqvist", "age_h": 62},
    {"number": "TCK-508", "booking": "E6", "title": "Invoice dispute for the Bali booking",
     "description": ("The invoice shows a different amount than the confirmed rate; please issue a "
                     "credit note for the difference."),
     "intent": "BILLING_INVOICE_DISPUTE", "priority": "MEDIUM", "status": "OPEN",
     "queue": "APAC-SUPPORT", "agent": None, "age_h": 34},
    {"number": "TCK-509", "booking": "E4", "title": "Name correction on the Fairmont booking",
     "description": ("Please amend the guest name to the passport spelling for TBOH-903114."),
     "intent": "AMENDMENT_NAME_DATE", "priority": "LOW", "status": "RESOLVED",
     "queue": "MEA-SUPPORT", "agent": "Omar Haddad", "age_h": 168, "res_h": 140},
    {"number": "TCK-510", "booking": "E3", "title": "Date change requested for Ibis Styles Bali",
     "description": ("Client needs to move the check-in date by three days because the flight was "
                     "rescheduled."),
     "intent": "AMENDMENT_NAME_DATE", "priority": "MEDIUM", "status": "IN_PROGRESS",
     "queue": "APAC-SUPPORT", "agent": "Mei Chen", "age_h": 52},
    {"number": "TCK-511", "booking": "E2", "title": "Refund delay for cancelled Rotana stay",
     "description": ("The client cancelled the Rotana Downtown Dubai stay and the refund has not been "
                     "credited after 10 days."),
     "intent": "REFUND_DELAY", "priority": "HIGH", "status": "OPEN", "queue": "MEA-SUPPORT",
     "agent": "Omar Haddad", "age_h": 46},
    {"number": "TCK-512", "booking": "E5", "title": "Refund delay for cancelled Marriott stay",
     "description": ("Refund for the cancelled Marriott Marquis booking is overdue; supplier says it "
                     "is pending."),
     "intent": "REFUND_DELAY", "priority": "MEDIUM", "status": "OPEN", "queue": "APAC-SUPPORT",
     "agent": "Rahul Mehta", "age_h": 38},
    {"number": "TCK-513", "booking": "E7", "title": "Late cancellation waiver request for London",
     "description": ("The guest must cancel inside the penalty window; requesting the supplier waive "
                     "the one-night charge."),
     "intent": "CANCELLATION_LCD_WAIVER", "priority": "MEDIUM", "status": "OPEN",
     "queue": "EU-TRIAGE", "agent": "Sofia Lindqvist", "age_h": 44},
    {"number": "TCK-514", "booking": "A", "title": "Refund escalation for Atlantis The Palm",
     "description": ("Fourth contact on the Atlantis refund. The agency asks for an escalation and a "
                     "written credit date."),
     "intent": "REFUND_DELAY", "priority": "HIGH", "status": "OPEN", "queue": "MEA-SUPPORT",
     "agent": "Omar Haddad", "age_h": 20},
]

BACKGROUND_TEMPLATES = [
    ("INVENTORY_RATE_SYNC_BUG", "HIGH",
     "Rate mismatch on {supplier} API for {hotel}",
     "Supplier API returned a rate mismatch error code between search and book for {hotel}; "
     "looks like a cache bug on the availability response."),
    ("INVENTORY_RATE_SYNC_BUG", "MEDIUM",
     "Inventory sync issue on {supplier} availability",
     "Availability is stale on the {supplier} API for {hotel} and the booking call fails with an "
     "inventory error code."),
    ("REFUND_DELAY", "HIGH",
     "Refund not received for cancelled {hotel} stay",
     "The client cancelled the {hotel} stay and the refund has still not been credited after "
     "several days of chasing."),
    ("REFUND_DELAY", "MEDIUM",
     "Refund delay on {supplier} booking",
     "Refund is pending with the supplier finance team and the agency account still shows the debit "
     "for {hotel}."),
    ("SPECIAL_REQUEST", "LOW",
     "Special request for the {hotel} arrival",
     "Guest requests a high floor room with a view and an early check-in for the {hotel} stay."),
]

MESSAGES = [
    ("TCK-101", "Maya Al Farsi", "AGENCY_REQUESTER", "PUBLIC_REPLY",
     "Any update on the refund? Our client is asking for a date."),
    ("TCK-101", "Omar Haddad", "OPS_AGENT", "PUBLIC_REPLY",
     "Chased the supplier today; the credit is with their finance team. I will update you by "
     "tomorrow morning."),
    ("TCK-101", "Omar Haddad", "OPS_AGENT", "INTERNAL_NOTE",
     "Supplier confirmed the cancellation was within LCD, so this is purely a payment backlog."),
    ("TCK-201", "Ananya Sharma", "OPS_AGENT", "PUBLIC_REPLY",
     "Voucher has been requested from Agoda; awaiting the confirmation document."),
    ("TCK-301", "Sofia Lindqvist", "OPS_AGENT", "INTERNAL_NOTE",
     "Group block is on hold; hotel needs the rate revalidated before they confirm in writing."),
    ("TCK-402", "Rahul Mehta", "OPS_AGENT", "INTERNAL_NOTE",
     "Guest arrives in 90 minutes. Calling the property directly — escalation may be required."),
    ("TCK-401", "Sofia Lindqvist", "OPS_AGENT", "PUBLIC_REPLY",
     "Waiver request submitted to the supplier; the LCD is closing so we are treating this as urgent."),
    ("TCK-511", "Omar Haddad", "OPS_AGENT", "PUBLIC_REPLY",
     "Following up with Rotana on the refund status and will confirm the credit date."),
]


def reset_database() -> dict:
    """Delete every row in FK-safe order. Returns per-table counts removed."""
    init_db()
    db = SessionLocal()
    counts: dict[str, int] = {}
    try:
        for model in (
            AgentRun, SideMessage, SideConversation, Message, ActivityTimeline, RoutingAudit,
            EscalationRecord, TicketTransfer, TicketLink, ProductBug, ThemeTag,
            ExportJob, Ticket, Booking, User, Agency,
        ):
            counts[model.__tablename__] = int(db.scalar(select(func.count()).select_from(model)) or 0)
            db.execute(delete(model))
        db.commit()
    finally:
        db.close()
    return counts


_CLASSIFIER = None


def _model_evidence(title: str, description: str, tboh_id: str) -> tuple[float, list[str], dict]:
    """Run the shipped model on a fixture description.

    Returns (probability of the label, reasoning bullets, score map). Confidence
    is the model's own calibrated probability for the fixture label — never a
    hardcoded number.
    """
    global _CLASSIFIER
    if _CLASSIFIER is None:
        _CLASSIFIER = get_classifier()
    prediction = _CLASSIFIER.classify(
        title=title, description=description, tboh_id=tboh_id, extraction_source="FIELD"
    )
    scores = dict(prediction.scores)
    return prediction.confidence, list(prediction.reasoning), scores


def seed_database(*, reset: bool = True, now=None) -> dict:
    now = (now or utcnow()).replace(second=0, microsecond=0)
    if reset:
        reset_database()
    init_db()
    db = SessionLocal()
    summary: dict = {}
    try:
        pwd = hash_password(DEMO_PASSWORD)

        agencies: dict[str, Agency] = {}
        for spec in AGENCY_SPECS:
            agency = Agency(
                code=spec["code"], name=spec["name"], tier=spec["tier"], region=spec["region"],
                contact_email=spec["contact_email"], created_at=now,
            )
            db.add(agency)
            agencies[spec["code"]] = agency
        db.flush()

        users: dict[str, User] = {}
        for spec in USER_SPECS:
            user = User(
                email=spec["email"], full_name=spec["full_name"], hashed_password=pwd,
                role=spec["role"], region=spec["region"], timezone=spec["tz"],
                shift_start=spec["shift"][0], shift_end=spec["shift"][1],
                skill_rank=spec["skill"], max_capacity=spec["cap"], is_online=spec["online"],
                agency_id=agencies[spec["agency"]].id if spec.get("agency") else None,
                created_at=now,
            )
            db.add(user)
            users[spec["full_name"]] = user
        db.flush()

        bookings: dict[str, Booking] = {}
        for spec in BOOKING_SPECS:
            booking = Booking(
                tboh_id=spec["tboh_id"], agency_id=agencies[spec["agency"]].id,
                supplier_name=spec["supplier"], supplier_email=spec["supplier_email"],
                hotel_name=spec["hotel"], destination_city=spec["city"],
                destination_country=spec["country"], region=spec["region"], timezone=spec["tz"],
                check_in=now + timedelta(hours=spec["check_in_h"]),
                check_out=now + timedelta(hours=spec["check_in_h"] + 72),
                lcd=now + timedelta(hours=spec["lcd_h"]),
                booking_status=spec["status"], amount=spec["amount"], currency=spec["currency"],
                passenger_name=spec["passenger"], created_at=now - timedelta(days=21),
            )
            db.add(booking)
            bookings[spec["key"]] = booking
        db.flush()

        def create_ticket(
            *, number: str, booking: Booking, title: str, description: str, intent: str,
            priority: str, status: str, queue: str, agent: str | None, age_h: float,
            holiday: bool = False, res_h: float | None = None,
        ) -> Ticket:
            created = now - timedelta(hours=age_h)
            resolved = created + timedelta(hours=res_h) if res_h is not None else None
            confidence, reasoning, scores = _model_evidence(title, description, booking.tboh_id)
            ticket = Ticket(
                ticket_number=number, booking_id=booking.id, agency_id=booking.agency_id,
                assigned_user_id=users[agent].id if agent else None,
                region=booking.region, title=title, description=description,
                intent=intent, intent_confidence=confidence,
                intent_reasoning=reasoning, intent_scores=scores, intent_source="ML",
                extracted_tboh=booking.tboh_id, extraction_source="FIELD",
                priority=priority, status="RESOLVED" if resolved else status, queue=queue,
                regional_holiday_flag=holiday,
                created_by_id=users["Maya Al Farsi"].id if booking.agency_id == agencies["AG-WLT"].id
                else users["Nisha Verma"].id,
                created_at=created, updated_at=resolved or created, resolved_at=resolved,
            )
            db.add(ticket)
            db.flush()

            computed = sla_service.compute_sla(
                created_at=created, priority=priority, lcd=booking.lcd, check_in=booking.check_in,
                regional_holiday_flag=holiday, now=now, status=ticket.status,
            )
            ticket.priority_due_at = computed.priority_due_at
            ticket.effective_sla_due_at = computed.effective_due_at
            ticket.sla_rule = computed.governing_rule
            ticket.at_risk_threshold = computed.at_risk_threshold
            db.add(ActivityTimeline(
                ticket_id=ticket.id, event_type="TICKET_CREATED", actor_name="Seeded fixture",
                description=f"Ticket created and classified as {intent} ({confidence:.0%})",
                metadata_json={"intent": intent, "confidence": round(confidence, 4),
                               "source": "ML", "seed": True},
                created_at=created,
            ))
            return ticket

        tickets: dict[str, Ticket] = {}
        for spec in TICKET_SPECS:
            ticket = create_ticket(
                number=spec["number"], booking=bookings[spec["booking"]], title=spec["title"],
                description=spec["description"], intent=spec["intent"], priority=spec["priority"],
                status=spec["status"], queue=spec["queue"], agent=spec["agent"],
                age_h=spec["age_h"], holiday=spec.get("holiday", False), res_h=spec.get("res_h"),
            )
            tickets[spec["number"]] = ticket

            if spec.get("escalated"):
                manager = users[spec["escalated"]]
                previous_owner = users[spec["agent"]].id if spec["agent"] else None
                ticket.escalated = True
                ticket.escalated_at = ticket.created_at + timedelta(hours=1)
                ticket.escalated_by_id = users["Nisha Verma"].id
                db.add(EscalationRecord(
                    ticket_id=ticket.id, escalated_by_id=users["Nisha Verma"].id,
                    assigned_em_id=manager.id, previous_owner_id=previous_owner,
                    previous_status="IN_PROGRESS", previous_queue=f"{ticket.region}-SUPPORT",
                    reason="Pre-escalated fixture: travel deadline imminent and supplier unresponsive",
                    escalated_at=ticket.escalated_at,
                ))
                db.add(ActivityTimeline(
                    ticket_id=ticket.id, event_type="ESCALATED", actor_name="Nisha Verma",
                    description=f"Escalated to {manager.full_name} (Escalation Manager)",
                    metadata_json={"assigned_em": manager.full_name, "seed": True},
                    created_at=ticket.escalated_at,
                ))

            side = spec.get("side_conversation")
            if side:
                conversation = SideConversation(
                    ticket_id=ticket.id, channel_type=side["channel"], subject=side["subject"],
                    counterparty_name=side["counterparty"],
                    explicit_recipients=side["recipients"], created_by_group=spec["queue"],
                    status="OPEN", created_at=ticket.created_at + timedelta(minutes=30),
                )
                db.add(conversation)
                db.flush()
                for offset, (sender, recipient, content, direction) in enumerate(side["messages"]):
                    db.add(SideMessage(
                        side_conversation_id=conversation.id, sender_email=sender,
                        recipient_email=recipient, content=content, direction=direction,
                        status="SENT" if direction == "OUTBOUND" else "RECEIVED",
                        created_at=ticket.created_at + timedelta(minutes=30 + offset * 25),
                    ))

        # ------------------------------------------------ background volume
        background_ticket_count = 0
        booking_cycle = list(bookings.values())
        # Deliberate load shape: Omar is pushed to capacity (full → excluded),
        # Ananya keeps exactly one active ticket so Journey B starts at 1/8.
        agents_cycle = ["Omar Haddad", "Omar Haddad", "Omar Haddad", "Rahul Mehta",
                        "Mei Chen", "Daniel Okafor", "Sofia Lindqvist", "Rahul Mehta"]
        state_plan = ["HEALTHY", "HEALTHY", "AT_RISK", "RESOLVED", "BREACHED",
                      "HEALTHY", "AT_RISK", "HEALTHY", "RESOLVED", "AT_RISK"]
        suppliers = {"Accor", "Marriott", "Rotana", "Hilton", "WebBeds"}

        for seq in range(25):
            spec = BACKGROUND_TEMPLATES[seq % len(BACKGROUND_TEMPLATES)]
            intent, priority = spec[0], spec[1]
            booking = booking_cycle[seq % len(booking_cycle)]
            template_title, template_desc = spec[2], spec[3]
            title = template_title.format(supplier=booking.supplier_name, hotel=booking.hotel_name)
            description = template_desc.format(supplier=booking.supplier_name, hotel=booking.hotel_name)

            target_state = state_plan[seq % len(state_plan)]
            sla_hours = sla_service.PRIORITY_SLA_HOURS[priority]
            ratio = {"HEALTHY": 0.30, "AT_RISK": 0.82, "BREACHED": 1.45, "RESOLVED": 0.55}[target_state]
            age_h = sla_hours * ratio + (seq % 5) * 0.1
            number = f"TCK-{600 + seq}"
            ticket = create_ticket(
                number=number, booking=booking, title=title, description=description,
                intent=intent, priority=priority, status="OPEN" if target_state != "RESOLVED"
                else "RESOLVED", queue=f"{booking.region}-SUPPORT",
                agent=agents_cycle[seq % len(agents_cycle)], age_h=age_h,
                res_h=(sla_hours * 0.55) if target_state == "RESOLVED" else None,
            )
            tickets[number] = ticket
            background_ticket_count += 1

        # ------------------------------------------------------- messages
        for number, sender, role, message_type, content in MESSAGES:
            ticket = tickets.get(number)
            if ticket is None:
                continue
            db.add(Message(
                ticket_id=ticket.id, sender_id=users.get(sender).id if sender in users else None,
                sender_name=sender, sender_role=role, message_type=message_type, content=content,
                created_at=ticket.created_at + timedelta(hours=2),
            ))

        db.commit()

        # ------------------------------------------------- case graph + audits
        link_counts: dict[str, int] = {}
        for ticket in tickets.values():
            created = build_case_links(db, ticket)
            link_counts[ticket.ticket_number] = len(created)
        db.commit()

        # A few recorded routing decisions so the audit view is not empty on first load.
        for number in ("TCK-101", "TCK-201", "TCK-301"):
            ticket = tickets[number]
            decision = assignment.build_decision(db, ticket)
            db.add(RoutingAudit(
                ticket_id=ticket.id,
                candidate_scores_json=decision["candidates"],
                excluded_json=decision["excluded"],
                eligible_count=len(decision["candidates"]),
                selected_agent_id=ticket.assigned_user_id,
                selected_score=(decision["candidates"][0]["total_score"]
                                if decision["candidates"] else None),
                decision_reason=assignment.explain(ticket, decision),
                tie_break_applied=decision["tie_break_applied"],
                triggered_by="AUTO",
                created_at=ticket.created_at + timedelta(minutes=2),
            ))
        db.commit()

        summary = {
            "seeded_at": now.isoformat(),
            "agencies": len(AGENCY_SPECS),
            "users": len(USER_SPECS),
            "bookings": len(BOOKING_SPECS),
            "tickets": int(db.scalar(select(func.count()).select_from(Ticket)) or 0),
            "background_tickets": background_ticket_count,
            "link_counts": link_counts,
            "journey_fixtures": {
                "A": {"agency": "Wanderlust Travels", "booking": "TBOH-778899",
                      "existing_tickets": ["TCK-101", "TCK-104", "TCK-109"]},
                "B": {"agency": "Apex Global Holidays", "booking": "TBOH-554411",
                      "ticket": "TCK-201", "expected_agent": "Ananya Sharma"},
                "C": {"agency": "EuroWings B2B", "ticket": "TCK-301",
                      "supplier": "Hilton Paris Opera",
                      "recipients": ["groups@hilton-paris.com"], "queue": "EU-TRIAGE"},
                "D": {"tickets": ["TCK-401", "TCK-402"], "em_queue": ["TCK-403", "TCK-404"]},
                "E": {"background_tickets": background_ticket_count},
            },
            "data_notice": "ALL seeded operational data is SYNTHETIC.",
        }
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpsDesk synthetic seed")
    parser.add_argument("--reset", action="store_true", help="reset only, do not seed")
    args = parser.parse_args()
    if args.reset:
        print("Reset:", reset_database())
    else:
        print("Seeded:", seed_database(reset=True))
