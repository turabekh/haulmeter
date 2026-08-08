"""AI-CONTEXT: M7 Fuel Savings Network (PRD §8.7) — the sleeper economics. The map
shows the driver's NET price after discount along the corridor; a tap issues a
pump code and the transaction settles on the F7 ledger with spread accounting.
Mudflap's model fused into the corridor view. The platform keeps a per-gallon
SPREAD baked between the merchant discount and the driver-facing discount, so the
driver sees one net price with no fees/minimums (PRD §8.7 user story). The card
charge / merchant settlement is the F7 PaymentGateway SEAM (payment partner
deferred, wired at activation — mirrors M6's Stripe seam). F7 already ships the
`fuel_clearing` account + `fuel_txn` entry type. Composes foundation publics +
m01.public (corridor). Runs behind the F13 flag m07_fuel, gated on a signed
merchant agreement + a live payment partner.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.modules.m01_map import public as m1

from .enums import FuelTxnState, PriceSource
from .models import FuelTransaction, Merchant, RegionalFuelPrice, StationPricing

FLAG_KEY = "m07_fuel"
MODULE = "m07"
GATES = ["merchant_agreement", "payment_partner"]
DEFAULT_GALLONS = 100.0  # a typical fill for corridor true-cost ranking


class NotAFuelPartner(Exception):
    pass


@dataclass
class FuelStop:
    facility_id: object
    name: str
    distance_m: float
    gross_cents_per_gal: int
    net_cents_per_gal: int
    savings_cents_per_gal: int
    true_cost_cents: int
    is_network: bool


@dataclass
class DriverFuelAnalytics:
    gallons_milli: int
    spend_cents: int
    savings_cents: int
    txn_count: int


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M7 Fuel Savings Network", default_on=True)
    for gate in GATES:
        flags.add_gate(db, FLAG_KEY, gate)
    admin.register_admin_view(db, "m07.fuel", MODULE, "Fuel Network", "/admin/m07/fuel")


# --- Merchant network + station pricing (M7-FR1) ---
def register_merchant(db: Session, name: str, settlement_terms: str = "net_15") -> Merchant:
    merchant = Merchant(name=name, settlement_terms=settlement_terms)
    db.add(merchant)
    db.flush()
    return merchant


def set_station_pricing(
    db: Session,
    facility_ref,
    gross_cents_per_gal: int,
    discount_cents_per_gal: int = 0,
    spread_cents_per_gal: int = 0,
    merchant_id=None,
    source: PriceSource = PriceSource.feed,
) -> StationPricing:
    pricing = db.scalar(select(StationPricing).where(StationPricing.facility_ref == facility_ref))
    if pricing is None:
        pricing = StationPricing(facility_ref=facility_ref)
        db.add(pricing)
    pricing.gross_cents_per_gal = gross_cents_per_gal
    pricing.discount_cents_per_gal = discount_cents_per_gal
    pricing.spread_cents_per_gal = spread_cents_per_gal
    pricing.merchant_id = merchant_id
    pricing.source = source
    db.flush()
    return pricing


def net_cents_per_gal(pricing: StationPricing) -> int:
    return pricing.gross_cents_per_gal - pricing.discount_cents_per_gal


# --- EIA regional baseline (M1-FR5): the indicative price until a real one exists ---
# EIA v2 petroleum/pri/gnd `duoarea` region code -> our PADD region code.
EIA_REGIONS = {
    "R10": "PADD1",
    "R20": "PADD2",
    "R30": "PADD3",
    "R40": "PADD4",
    "R50": "PADD5",
    "NUS": "US",
}
EIA_DIESEL_PRODUCT = "EPD2D"  # No. 2 Diesel — ignore gasoline rows in a mixed payload
EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
EIA_DUOAREAS = ["NUS", "R10", "R20", "R30", "R40", "R50"]  # US + PADD1..5


class MissingEIAKey(Exception):
    pass


def fetch_eia(api_key: str) -> dict:
    # live pull of EIA's weekly on-highway diesel by region (make-target + worker
    # only, never CI). Shared by scripts.ingest_eia and runners.run_eia.
    if not api_key:
        raise MissingEIAKey("EIA_API_KEY not set")
    import httpx

    params = [
        ("api_key", api_key),
        ("frequency", "weekly"),
        ("data[0]", "value"),
        ("facets[product][]", EIA_DIESEL_PRODUCT),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("length", "300"),
    ]
    params += [("facets[duoarea][]", area) for area in EIA_DUOAREAS]
    resp = httpx.get(EIA_URL, params=params, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def region_for(lat: float, lon: float) -> str:
    # coarse PADD partition by longitude (+ a lat split through the mountain/gulf
    # south). Deliberately approximate — this backs an INDICATIVE regional average
    # (labeled as such); a crowd report or a network feed overrides it per-station.
    if lon >= -82:
        return "PADD1"  # East Coast
    if lon >= -104:
        return "PADD3" if lat < 37 else "PADD2"  # Gulf Coast (south) vs Midwest (north)
    if lon >= -114:
        return "PADD5" if lat < 37 else "PADD4"  # desert Southwest vs Rocky Mountain
    return "PADD5"  # West Coast


def upsert_regional_price(
    db: Session, region: str, gross_cents_per_gal: int, week_of: date
) -> RegionalFuelPrice:
    row = db.get(RegionalFuelPrice, region)
    if row is None:
        row = RegionalFuelPrice(region=region)
        db.add(row)
    row.gross_cents_per_gal = gross_cents_per_gal
    row.week_of = week_of
    db.flush()
    return row


def _regional_price(db: Session, lat: float, lon: float) -> RegionalFuelPrice | None:
    return db.get(RegionalFuelPrice, region_for(lat, lon)) or db.get(RegionalFuelPrice, "US")


def parse_eia(payload: dict) -> list[tuple[str, int, date]]:
    # EIA v2 gnd response -> [(region, cents/gal, week_of)]. Rows look like
    # {"period":"2026-07-14","duoarea":"R20","value":"3.892","units":"$/GAL"}.
    out: list[tuple[str, int, date]] = []
    for row in payload.get("response", {}).get("data", []):
        region = EIA_REGIONS.get(row.get("duoarea"))
        if region is None or row.get("value") in (None, ""):
            continue
        if row.get("product") != EIA_DIESEL_PRODUCT:
            continue  # ignore gasoline rows in a mixed payload
        cents = round(float(row["value"]) * 100)
        out.append((region, cents, date.fromisoformat(row["period"])))
    return out


def ingest_eia_prices(db: Session, payload: dict) -> int:
    # EIA returns a time series; keep only the freshest week per region.
    latest: dict[str, tuple[int, date]] = {}
    for region, cents, week_of in parse_eia(payload):
        if region not in latest or week_of > latest[region][1]:
            latest[region] = (cents, week_of)
    for region, (cents, week_of) in latest.items():
        upsert_regional_price(db, region, cents, week_of)
    return len(latest)


def fuel_summary(
    db: Session, facility_ref, lat: float | None = None, lon: float | None = None
) -> dict | None:
    # backs the map's fuel badge. Priority: per-station NETWORK feed -> CROWD
    # consensus (M7-FR5, with belief freshness) -> EIA REGIONAL baseline (indicative).
    pricing = db.scalar(select(StationPricing).where(StationPricing.facility_ref == facility_ref))
    if pricing is not None:
        net = net_cents_per_gal(pricing)
        as_of, sample_size = pricing.updated_at, None
        source = "feed"
        if pricing.source == PriceSource.crowd:
            source = "crowd"
            belief = crowd.get_belief(db, facility_ref, crowd.SignalType.fuel_price)
            if belief is not None:
                as_of, sample_size = belief.freshest_at, belief.sample_size
        return {
            "gross": pricing.gross_cents_per_gal,
            "net": net,
            "savings": pricing.gross_cents_per_gal - net,
            "is_network": _is_network(pricing),
            "source": source,
            "indicative": False,
            "as_of": as_of.isoformat() if as_of else None,
            "sample_size": sample_size,
        }
    if lat is not None and lon is not None:
        row = _regional_price(db, lat, lon)
        if row is not None:
            return {
                "gross": row.gross_cents_per_gal,
                "net": row.gross_cents_per_gal,
                "savings": 0,
                "is_network": False,
                "source": "regional",
                "indicative": True,
                "region": row.region,
                "as_of": row.week_of.isoformat(),
                "sample_size": None,
            }
    return None


def _is_network(pricing: StationPricing) -> bool:
    return pricing.merchant_id is not None


# --- Crowd price confirmation keeps non-network honest (M7-FR5) ---
def confirm_price(
    db: Session, account_id, facility_ref, price_cents_per_gal: int, submitted_at: datetime
) -> int | None:
    crowd.submit(
        db,
        account_id,
        facility_ref,
        crowd.SignalType.fuel_price,
        {"price_cents": price_cents_per_gal},
        submitted_at=submitted_at,
    )
    belief = crowd.update_belief(db, facility_ref, crowd.SignalType.fuel_price, as_of=submitted_at)
    if belief is None:
        return None
    consensus = belief.value["price_cents"]
    # non-network / crowd-sourced stations track the consensus gross on the same layer
    pricing = db.scalar(select(StationPricing).where(StationPricing.facility_ref == facility_ref))
    if pricing is None:
        set_station_pricing(db, facility_ref, consensus, source=PriceSource.crowd)
    elif not _is_network(pricing):
        pricing.gross_cents_per_gal = consensus
        pricing.source = PriceSource.crowd
        db.flush()
    return consensus


# --- Net-price corridor, ranked by true cost (M7-FR2) ---
def corridor_fuel(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float,
    gallons: float = DEFAULT_GALLONS,
) -> list[FuelStop]:
    entries = m1.corridor_view(
        db, account_id, origin_lat, origin_lon, heading_deg, max_distance_m, preset=m1.Preset.fuel
    )
    refs = [e.facility_id for e in entries]
    pricing = {
        p.facility_ref: p
        for p in db.scalars(select(StationPricing).where(StationPricing.facility_ref.in_(refs)))
    }
    gallons_milli = round(gallons * 1000)
    stops: list[FuelStop] = []
    for entry in entries:
        p = pricing.get(entry.facility_id)
        if p is None:
            continue
        net = net_cents_per_gal(p)
        true_cost = round(net * gallons_milli / 1000)
        stops.append(
            FuelStop(
                facility_id=entry.facility_id,
                name=entry.name,
                distance_m=entry.distance_m,
                gross_cents_per_gal=p.gross_cents_per_gal,
                net_cents_per_gal=net,
                savings_cents_per_gal=p.discount_cents_per_gal,
                true_cost_cents=true_cost,
                is_network=_is_network(p),
            )
        )
    # AI-CONTEXT: rank by the driver's net price, then proximity — no fabricated
    # deviation-mile coefficient (design-prd §11.7, never fake precision).
    stops.sort(key=lambda s: (s.net_cents_per_gal, s.distance_m))
    return stops


# --- In-app fuel payment: pump code + spread settlement (M7-FR3) ---
def _pump_code() -> str:
    return uuid.uuid4().hex[:8].upper()


def issue_pump_code(
    db: Session, account_id, station_ref, gallons: float, gateway=None
) -> FuelTransaction:
    pricing = db.scalar(select(StationPricing).where(StationPricing.facility_ref == station_ref))
    if pricing is None or not _is_network(pricing):
        raise NotAFuelPartner(str(station_ref))
    gallons_milli = round(gallons * 1000)
    net_per_gal = net_cents_per_gal(pricing)
    gross_cents = round(pricing.gross_cents_per_gal * gallons_milli / 1000)
    net_cents = round(net_per_gal * gallons_milli / 1000)
    spread_cents = round(pricing.spread_cents_per_gal * gallons_milli / 1000)

    if gateway is not None:  # payment partner seam (deferred); ledger is the truth
        gateway.authorize_pump(net_cents, f"fuel:{station_ref}")
    txn = FuelTransaction(
        driver_account_id=account_id,
        station_ref=station_ref,
        merchant_id=pricing.merchant_id,
        gallons_milli=gallons_milli,
        gross_cents_per_gal=pricing.gross_cents_per_gal,
        net_cents_per_gal=net_per_gal,
        spread_cents_per_gal=pricing.spread_cents_per_gal,
        gross_cents=gross_cents,
        net_cents=net_cents,
        spread_cents=spread_cents,
        pump_code=_pump_code(),
        state=FuelTxnState.code_issued,
    )
    db.add(txn)
    db.flush()
    return txn


def settle(db: Session, txn: FuelTransaction) -> FuelTransaction:
    # driver pays net; platform keeps the spread; the merchant is owed the rest.
    cash = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.cash_clearing, "cash:fuel", ledger.Currency.usd
    )
    platform = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.platform_revenue, "revenue:fuel", ledger.Currency.usd
    )
    merchant = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.fuel_clearing,
        f"merchant:{txn.merchant_id}",
        ledger.Currency.usd,
    )
    entry = ledger.post_entry(
        db,
        ledger.EntryType.fuel_txn,
        [
            ledger.Posting(cash.id, ledger.Direction.debit, txn.net_cents),
            ledger.Posting(platform.id, ledger.Direction.credit, txn.spread_cents),
            ledger.Posting(merchant.id, ledger.Direction.credit, txn.net_cents - txn.spread_cents),
        ],
        description=f"fuel settlement {txn.id}",
    )
    txn.state = FuelTxnState.settled
    txn.entry_ref = entry.id
    txn.settled_at = txn.created_at
    db.flush()
    return txn


# --- Fuel spend analytics + savings-to-date (M7-FR4; IFTA export -> M9 hook) ---
def driver_analytics(db: Session, account_id) -> DriverFuelAnalytics:
    txns = list(
        db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.driver_account_id == account_id,
                FuelTransaction.state == FuelTxnState.settled,
            )
        )
    )
    gallons_milli = sum(t.gallons_milli for t in txns)
    spend = sum(t.net_cents for t in txns)
    savings = sum(t.gross_cents - t.net_cents for t in txns)
    return DriverFuelAnalytics(gallons_milli, spend, savings, len(txns))
