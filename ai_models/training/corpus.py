"""Synthetic training corpus — SYNTHETIC DATA, no real TBO ticket text.

Two disjoint template families exist per intent:

* ``TRAIN_TEMPLATES`` — used to fit the model.
* ``HOLDOUT_TEMPLATES`` — never seen during training; used for the reported
  evaluation metrics in ``ai_models/evaluation/metrics.json``.

Because the split is template-disjoint the reported accuracy is an honest
out-of-distribution estimate for unseen phrasings, not a memorisation score.
"""
from __future__ import annotations

import random

INTENTS = [
    "REFUND_DELAY",
    "CANCELLATION_LCD_WAIVER",
    "VOUCHER_CONFIRMATION_ISSUE",
    "AMENDMENT_NAME_DATE",
    "INVENTORY_RATE_SYNC_BUG",
    "SPECIAL_REQUEST",
    "SUPPLIER_OVERBOOKING_RELOCATION",
    "BILLING_INVOICE_DISPUTE",
]

TRAIN_TEMPLATES: dict[str, list[str]] = {
    "REFUND_DELAY": [
        "Refund of {currency} {amount} for cancelled {hotel} has not been credited after {days} days.",
        "Client is still waiting for the refund on booking {tboh}; supplier says it is pending with finance.",
        "We cancelled {hotel} within the deadline and the refund credit note was never issued.",
        "Third follow up on refund {tboh}; money has not reached the agency account yet.",
        "Refund not received for cancelled stay at {hotel}. Please chase {supplier} for a credit date.",
        "The refund is overdue by {days} days and the passenger keeps calling us.",
        "Cancelled booking {tboh}, refund still pending with the supplier and no credit note reference.",
        "Where is our refund? {currency} {amount} deducted for {hotel} and nothing credited.",
        "Supplier confirmed cancellation but the refund has not been processed on their side.",
        "Refund delay on {hotel}: {days} days since cancellation, no money back to the client.",
        "Please escalate the refund for {tboh}; the agency ledger still shows a debit.",
        "Refund pending for {days} days after cancellation of the {hotel} booking.",
    ],
    "CANCELLATION_LCD_WAIVER": [
        "Guest must cancel but we are past the last cancellation date; requesting a penalty waiver.",
        "LCD has already closed for {hotel} and the client wants a free cancellation due to hospitalisation.",
        "We need to cancel after the cancellation deadline and ask {supplier} to waive the charge.",
        "Request a waiver of the cancellation penalty for {tboh}; the guest cannot travel.",
        "Cancellation is after LCD, please request goodwill waiving of the one night penalty.",
        "Client requests cancellation outside the free cancellation window; can we waive the fee?",
        "Airline strike forced a cancellation past the last cancellation date; asking for a waiver.",
        "Late cancellation request for {hotel}: LCD closed yesterday, please negotiate a waiver.",
        "We missed the LCD by hours because of a medical emergency; request penalty waiver from supplier.",
        "Cancellation after the last cancellation date, requesting a courtesy waiver of charges.",
        "Please raise a cancellation waiver request for {tboh} as the penalty is extremely high.",
        "Cancellation fee waiver needed: the booking is past its free cancellation period.",
    ],
    "VOUCHER_CONFIRMATION_ISSUE": [
        "Hotel has no confirmation and the guest checks in tomorrow; voucher not received.",
        "Voucher for {hotel} is missing from the booking {tboh}, guest arrives in 48 hours.",
        "Supplier has not confirmed the reservation, we need the voucher urgently for check-in.",
        "The hotel cannot find our reservation; please resend the confirmation voucher.",
        "Guest at reception and the property says the booking is not confirmed on their system.",
        "Voucher not received for {hotel}, arrival is today and the client is waiting at the desk.",
        "Reconfirmation needed: the hotel denies having a confirmed reservation for {tboh}.",
        "We never received the voucher for the group block at {hotel}; check-in is imminent.",
        "Confirmation voucher pending from {supplier}; the guest is travelling tomorrow morning.",
        "Property has no record of the booking and refuses check-in without a voucher.",
        "Please issue the missing voucher for {hotel}; the client is already at the airport.",
        "Reservation is unconfirmed on the supplier side and the guest arrives tonight.",
    ],
    "AMENDMENT_NAME_DATE": [
        "Please amend the guest name on the booking to the passport spelling.",
        "Client needs a date change for {hotel}: move check-in by {days} days.",
        "Name correction required on {tboh}; the surname was typed with a spelling mistake.",
        "Requesting an amendment to the travel dates for the {hotel} reservation.",
        "Passport shows a different middle name, please amend the booking name accordingly.",
        "Change of check-in date requested by the guest for {hotel}, subject to availability.",
        "We need to correct the guest name and date of birth on the reservation {tboh}.",
        "Amendment request: shift the stay at {hotel} by {days} days and update the guest name.",
        "Spelling error in the passenger name must be corrected before the voucher is issued.",
        "Guest wants to extend the stay and amend the departure date at {hotel}.",
        "Please modify the booking to the correct passport name, the client was denied boarding paperwork.",
        "Date amendment needed for {tboh}, the client's flight moved by {days} days.",
    ],
    "INVENTORY_RATE_SYNC_BUG": [
        "Supplier API returned a rate mismatch error between search and book on {hotel}.",
        "Availability shown in search disappears at booking; looks like a caching bug in the {supplier} API.",
        "Price changed at book step on {tboh}; the search rate is not syncing with the supplier inventory.",
        "Inventory sync issue: room shows available but the API rejects the booking with error code 402.",
        "Rate cache mismatch between search and book on {hotel}, the API returns a different amount.",
        "We are seeing a supplier API bug where availability is stale by several minutes.",
        "Booking fails with a rate error even though the search response showed the room available.",
        "Sync defect on {supplier}: the rate pushed to us does not match the rate in their system.",
        "Search returns availability but the book call fails with an inventory error code.",
        "Caching issue on the {supplier} API is producing wrong rates for {hotel}.",
        "The rate we display does not match the API response at confirmation; suspected sync bug.",
        "Repeat API error 409 on {supplier} inventory; the room is available but booking is rejected.",
    ],
    "SPECIAL_REQUEST": [
        "Please arrange honeymoon decoration and a cake at the hotel.",
        "Guest requests a high floor room away from the lift for the {hotel} stay.",
        "Requesting an early check-in and a baby cot for the {hotel} reservation.",
        "Client asked for airport pickup and a vegetarian breakfast during the stay.",
        "Please note a special request for a quiet room and a late check-out at {hotel}.",
        "Anniversary stay: the guest would like flowers and a fruit basket in the room.",
        "Add a request for connecting rooms for the family at {hotel}.",
        "The guest needs a wheelchair accessible room and help with luggage.",
        "Special occasion: birthday cake and a card in the room for the {hotel} booking.",
        "Please request a sea view room and an extra bed for the child at {hotel}.",
        "Traveller would like a smoking-free floor and gluten free breakfast.",
        "Kindly add a honeymoon note and champagne on arrival for {tboh}.",
    ],
    "SUPPLIER_OVERBOOKING_RELOCATION": [
        "The hotel is overbooked and cannot honour the booking; the guest needs relocation.",
        "{supplier} overbooked {hotel} and walked the guest to another property, we need a refund or upgrade.",
        "Property is sold out and denies the confirmed reservation; arrange relocation for the client.",
        "Overbooking situation at {hotel}: our guest has no room tonight and is waiting in reception.",
        "Supplier moved our client because of overbooking, please arrange alternative accommodation.",
        "Hotel walked the guest due to overbooking and offered an inferior property; request relocation compensation.",
        "Guest arrived to find the hotel oversold; need urgent relocation for {tboh}.",
        "Overbooked property, client stranded at midnight; please relocate to a comparable hotel.",
        "Relocation required: the hotel is overbooked and refuses to honour the confirmed stay.",
        "Supplier reports the hotel is sold out and our booking cannot be accommodated; relocate the guest.",
        "Walked guest scenario at {hotel}, the family is waiting for an alternative room.",
        "The property is oversold and the client has been denied check-in, requesting relocation support.",
    ],
    "BILLING_INVOICE_DISPUTE": [
        "The invoice shows a different amount; please issue a credit note for the duplicate charge.",
        "We were billed twice for {tboh} and need a corrected invoice.",
        "Invoice dispute: the commission shown on the invoice does not match the agreed rate.",
        "Please reissue the tax invoice with the correct billing entity name.",
        "The invoice total does not match the booking value, please send a credit note.",
        "Duplicate charge on the {supplier} invoice for {currency} {amount}; request a refund of the difference.",
        "Billing query: the invoice carries the wrong GST number and needs correction.",
        "We have not received the invoice for {tboh}; accounts cannot process the payment without it.",
        "The credit note for the cancelled booking was never issued, accounts is chasing it.",
        "Invoice amount is higher than the confirmed rate, please reconcile and raise a credit note.",
        "Wrong billing currency on the invoice; please correct it to {currency}.",
        "Dispute on the final invoice: extra supplier charges were added without approval.",
    ],
}

HOLDOUT_TEMPLATES: dict[str, list[str]] = {
    # Deliberately harder than the training set: different phrasing, and
    # several templates share vocabulary with a neighbouring intent so the
    # reported accuracy is not flattered by easy lexical separation.
    "REFUND_DELAY": [
        "It has been {days} days since we cancelled {hotel} and our client has still not been paid back.",
        "No money has come back for {tboh}; the agency is out of pocket and the traveller is chasing daily.",
        "We are chasing the outstanding amount of {currency} {amount} from {supplier} for a cancelled stay.",
        "Refund still outstanding after cancellation of the {hotel} booking, please advise the credit date.",
        "Client cancelled and the amount remains unreturned for {days} days; escalate to {supplier}.",
        "Our traveller is asking where the money is — the cancellation was weeks ago and nothing arrived.",
        "Supplier keeps promising the credit but the agency account still shows the full debit.",
        "Cancellation completed, yet the reversal of {currency} {amount} never appeared on the statement.",
        "Payment went out for {tboh} and after cancelling we have had no reversal at all.",
    ],
    "CANCELLATION_LCD_WAIVER": [
        "The free cancellation window has closed and the guest now needs to cancel for medical reasons.",
        "We are beyond the last cancellation date and ask that the penalty be waived as a goodwill gesture.",
        "Please request the supplier to waive cancellation charges, the LCD expired a few hours ago.",
        "Late cancellation needed past the deadline; the family has a bereavement and cannot travel.",
        "Can the cancellation penalty be waived? We are outside the allowed cancellation period.",
        "Client wants to cancel today but the booking is inside the penalty period; is there any flexibility?",
        "The supplier will charge one night because we are past the cut-off; please ask them to release it.",
        "Cancellation after the cut-off time — request the property to drop the charge on compassionate grounds.",
        "Guest cannot travel and we are outside the permitted cancellation window; seek a fee reduction.",
    ],
    "VOUCHER_CONFIRMATION_ISSUE": [
        "Our guest is standing at the front desk and the property has no booking on file for them.",
        "Nothing has been received to confirm the reservation and the arrival is in a few hours.",
        "The hotel denies the reservation exists; please obtain written confirmation immediately.",
        "We are missing the confirmation document for {hotel} and check-in is this evening.",
        "Supplier has still not sent the confirmation and the client is due to arrive soon.",
        "There is a problem with the booking at the property: they cannot see our confirmation number.",
        "Guest was refused at check-in because the reservation was never lodged by the supplier.",
        "Reconfirmation from {supplier} is still pending and the client travels in the morning.",
        "The property insists the reservation is not guaranteed; please send the voucher again.",
    ],
    "AMENDMENT_NAME_DATE": [
        "The traveller's name is misspelled on the reservation and must be corrected to match the passport.",
        "Please move the stay forward by {days} days and update the departure date accordingly.",
        "We need to change the guest details and the dates on booking {tboh}.",
        "A date change is required at {hotel} because the flight schedule was revised.",
        "Correct the passenger name on the booking, the middle name is missing.",
        "The client's surname changed after marriage and the reservation must reflect the new name.",
        "Can we shift the check-in by a day? The guest is arriving on a later flight.",
        "Update the occupancy and the guest name for the {hotel} reservation.",
        "The ticket was issued for the wrong date and the hotel booking must follow the new dates.",
    ],
    "INVENTORY_RATE_SYNC_BUG": [
        "Booking fails with a supplier API error although the room appeared available in search results.",
        "There is a mismatch between the cached rate and the live supplier rate at the book step.",
        "Inventory on {supplier} is out of sync: the room is sellable in search but rejected on confirmation.",
        "We keep receiving error codes from the {supplier} API for rooms that show as available.",
        "Price displayed at search differs from the confirmed rate, suggesting a cache refresh defect.",
        "Availability flips to sold out the moment we confirm, which looks like a technical defect.",
        "The {supplier} response returns a different rate than the one we quoted, twice today.",
        "Two agents got different prices seconds apart for the same room and date.",
        "Something is broken in the supplier connection: results are stale and booking throws an error.",
    ],
    "SPECIAL_REQUEST": [
        "The guest would like a room with a view and a cake for their anniversary.",
        "Please pass on a request for a cot and early access to the room.",
        "Client asks for flowers and a fruit platter on arrival at {hotel}.",
        "Kindly request connecting rooms and a late checkout for the family stay.",
        "Traveller requests a quiet room, away from the lifts, for a work trip.",
        "Add a note asking the property to prepare a surprise for the couple on arrival.",
        "The family needs two rooms next to each other and a highchair in the restaurant.",
        "Guest is celebrating a milestone and asked whether the hotel can arrange something special.",
        "Please ask the hotel for a room on a higher floor and a corner unit if possible.",
    ],
    "SUPPLIER_OVERBOOKING_RELOCATION": [
        "The property is oversold and our client has been denied the room they paid for.",
        "Guest has been walked to another hotel because the original one is overbooked; need relocation.",
        "Property cannot accommodate the booking due to overbooking and our client is stranded.",
        "The hotel has no room for our guest tonight and asks us to find an alternative.",
        "Overbooked situation at the property, we need urgent alternative accommodation for the family.",
        "The property says they cannot host our guest despite a confirmed reservation; arrange a move.",
        "Our client is sitting in reception while staff look for a different hotel for the night.",
        "Hotel is full and suggests another property; we need the new booking and any cost covered.",
        "Confirmed reservation not honoured because the house is full; relocate the guest immediately.",
    ],
    "BILLING_INVOICE_DISPUTE": [
        "The tax invoice needs to be corrected because the billing entity is wrong.",
        "We have been invoiced twice for the same stay and need a credit note.",
        "The amount on the invoice does not agree with the confirmed booking value.",
        "Please send a corrected invoice and a credit note for the difference.",
        "Accounts cannot reconcile the invoice because the commission is calculated incorrectly.",
        "The statement shows an extra line for this booking that nobody can explain.",
        "Our finance team is querying the charge of {currency} {amount} on the monthly statement.",
        "The invoice for {tboh} is addressed to the wrong company and must be reissued.",
        "We were charged the wrong currency and need the difference adjusted on the account.",
    ],
}

FILLERS = {
    "hotel": ["Atlantis The Palm", "Hilton Paris Opera", "Marina Bay Sands", "Ibis Styles Bali",
              "Novotel Bangkok Sukhumvit", "Rotana Downtown Dubai", "Raffles Dubai",
              "Sofitel Dubai The Palm", "Mandarin Oriental Bangkok", "Kempinski Bali"],
    "supplier": ["Hotelbeds", "Accor", "Marriott", "Hilton", "Rotana", "Agoda", "WebBeds"],
    "currency": ["USD", "EUR", "GBP", "AED", "SGD"],
    "amount": ["450", "1,450", "2,140", "780", "3,200", "690"],
    "days": ["3", "5", "7", "10", "14", "20", "26"],
    "tboh": ["TBOH-778899", "TBOH-554411", "TBOH-301332", "TBOH-410551", "TBOH-640017"],
}

PREFIXES = ["", "Urgent: ", "Please advise: ", "Client escalation — ", "Follow up: ", "Action needed: "]
SUFFIXES = ["", " Please advise.", " Client is waiting.", " Thanks.", " This is time critical."]


def render(template: str, rng: random.Random) -> str:
    slots = {key: rng.choice(values) for key, values in FILLERS.items()}
    return template.format(**slots)


def build_dataset(
    *, per_template: int = 6, seed: int = 7, holdout: bool = False
) -> tuple[list[str], list[str]]:
    rng = random.Random(seed + (1 if holdout else 0))
    templates = HOLDOUT_TEMPLATES if holdout else TRAIN_TEMPLATES
    texts: list[str] = []
    labels: list[str] = []
    for intent in INTENTS:
        for template in templates[intent]:
            for _ in range(per_template):
                body = render(template, rng)
                texts.append(f"{rng.choice(PREFIXES)}{body}{rng.choice(SUFFIXES)}")
                labels.append(intent)
    return texts, labels
