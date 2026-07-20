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
]


def import_all_models() -> None:
    for path in MODEL_MODULES:
        importlib.import_module(path)
