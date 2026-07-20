"""AI-CONTEXT: Payment-gateway seam for F7 (PRD §7.7).

Stripe + Stripe Connect handle card processing and owner/driver payouts,
deliberately structured so the platform never takes custody in a way that
triggers money-transmitter licensing. The double-entry ledger is the source of
truth and is fully functional without a live gateway; this protocol is where
the real Stripe adapter plugs in (wired at M6/M7 activation). StubPaymentGateway
fails loudly so nothing silently pretends to move real money.
"""

from typing import Protocol


class PaymentGateway(Protocol):
    def create_payment_intent(self, amount_cents: int, external_ref: str) -> dict: ...

    def create_payout(self, amount_cents: int, destination_ref: str) -> dict: ...

    def create_transfer(self, amount_cents: int, destination_ref: str) -> dict: ...


class StubPaymentGateway:
    def create_payment_intent(self, amount_cents: int, external_ref: str) -> dict:
        raise NotImplementedError("Stripe adapter is a seam; wired at M6/M7 activation")

    def create_payout(self, amount_cents: int, destination_ref: str) -> dict:
        raise NotImplementedError("Stripe Connect payout is a seam; wired at M6/M7 activation")

    def create_transfer(self, amount_cents: int, destination_ref: str) -> dict:
        raise NotImplementedError("Stripe Connect transfer is a seam; wired at M6/M7 activation")
