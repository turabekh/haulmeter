"""AI-CONTEXT: Model registry for Alembic + tests (build/ops glue).

Lives OUTSIDE the `app` package on purpose: it must import every component's
models to populate Base.metadata, which the core/UI-split import-linter
contract forbids `app.core` from doing. Foundation/module components own
their own Postgres schema (schema-per-module, PRD 10). Register new model
modules here as they land.
"""

import importlib

MODEL_MODULES = [
    "app.foundation.f01_identity.domain.models",
    "app.foundation.f02_facility.domain.models",
    "app.foundation.f03_location.domain.models",
    "app.foundation.f04_evidence.domain.models",
    "app.foundation.f05_load.domain.models",
    "app.foundation.f06_documents.domain.models",
    "app.foundation.f07_ledger.domain.models",
    "app.foundation.f08_notifications.domain.models",
    "app.foundation.f09_ai_gateway.domain.models",
    "app.foundation.f10_crowd.domain.models",
    "app.foundation.f12_offline.domain.models",
    "app.foundation.f13_flags.domain.models",
    "app.foundation.f14_admin.domain.models",
    "app.foundation.f15_localization.domain.models",
    "app.modules.m02_facility_intel.domain.models",
    "app.modules.m03_detention.domain.models",
    "app.modules.m04_accessorial.domain.models",
    "app.modules.m05_protection.domain.models",
    "app.modules.m06_parking.domain.models",
    "app.modules.m07_fuel.domain.models",
    "app.modules.m09_money.domain.models",
    "app.modules.m10_community.domain.models",
    "app.modules.m12_fleet.domain.models",
    "app.modules.m13_vendor.domain.models",
    # AI-CONTEXT: M14 (PRD Extension E2, D8). Missing this is not cosmetic — it is what
    # `Base.metadata` is built from, so alembic autogenerate cannot see the module and
    # `drop_all` in the test harness cannot drop its tables. The symptom is remote from
    # the cause: `cannot drop table f01.account because other objects depend on it`,
    # every test erroring at fixture setup, on a suite that has nothing to do with M14.
    # It hid for a while because pytest COLLECTING m14's own test file imports the models
    # as a side effect — so the full suite passed and a subset failed.
    "app.modules.m14_recovery.domain.models",
]


def import_all_models() -> None:
    for path in MODEL_MODULES:
        importlib.import_module(path)
