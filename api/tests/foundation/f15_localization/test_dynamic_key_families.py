"""U-03's other half — the dynamic key families, checked from the side that owns them.

`locale-completeness.test.js` proves the six catalogues AGREE with each other and that
every static `t("literal")` has a key. Neither can see this defect: a key assembled at
runtime from a PYTHON vocabulary, missing from all six locales at once. Six identical
holes are perfect parity, and `resolve()` returns the raw key in production — so
`money.state.acknowledged` reached the Money tab as literal text, for every driver, in
every language. `load.doc.cargo_condition` (session 115) was the same defect.

This test is the audit's "stronger version": enumerate the vocabulary in Python, assert the
catalogue has a label for every value. It found four families broken when it was written —
13 keys in total, including all nine `facility.type.*`.

WHAT THIS DELIBERATELY DOES NOT DO: it does not check that the label is a good translation,
only that one exists in every launch locale. Parity and quality are different questions and
the JS test owns the first one.

ADDING A FAMILY costs one row in FAMILIES. A vocabulary that gains a value and not a label
fails here, which is the whole point — the blind spot this closes is a list that rots.
"""

import json
import os

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f07_ledger import public as ledger
from app.foundation.f15_localization import public as localization

CATALOGUE_DIR = "/repo/ui-i18n"


def _values(enum_cls) -> list[str]:
    return sorted(member.value for member in enum_cls)


# (key prefix, the vocabulary that produces the suffix, where a driver meets it)
FAMILIES: list[tuple[str, list[str], str]] = [
    ("facility.type.", _values(facility.FacilityType), "vendor week picker"),
    ("facility.service.", sorted(facility.SERVICE_KINDS), "facility card service row"),
    ("money.kind.", _values(ledger.ReceivableKind), "Money tab"),
    ("money.state.", _values(ledger.ReceivableState), "Money tab state pill"),
    ("docs.type.", _values(documents.DocType), "document capture sheet"),
    ("load.stop.", _values(loads.StopType), "Load tab"),
    ("auth.authority.", _values(identity.AuthorityType), "onboarding"),
]


def _catalogue(locale: str) -> dict:
    path = os.path.join(CATALOGUE_DIR, f"{locale}.json")
    # NOT a skip. The mount is part of the check; a missing mount that skipped would
    # report nothing while looking green, which is the failure this file exists to stop.
    assert os.path.exists(path), (
        f"{path} is missing — the ui i18n catalogues are not mounted into this container. "
        "See the api service's volumes in infra/docker-compose.yml."
    )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("prefix,vocabulary,surface", FAMILIES, ids=[f[0] for f in FAMILIES])
def test_every_vocabulary_value_has_a_label_in_every_launch_locale(prefix, vocabulary, surface):
    assert vocabulary, f"{prefix} vocabulary is empty — the enum moved"
    for locale in localization.LAUNCH_LOCALES:
        catalogue = _catalogue(locale)
        missing = [value for value in vocabulary if prefix + value not in catalogue]
        assert not missing, (
            f"{locale}: no label for {[prefix + m for m in missing]} — "
            f"a driver reads the raw key on the {surface}"
        )


@pytest.mark.parametrize("prefix,vocabulary,surface", FAMILIES, ids=[f[0] for f in FAMILIES])
def test_no_label_is_empty(prefix, vocabulary, surface):
    # a blank string satisfies "the key exists" and renders as nothing at all
    for locale in localization.LAUNCH_LOCALES:
        catalogue = _catalogue(locale)
        for value in vocabulary:
            text = catalogue.get(prefix + value, "")
            assert text.strip(), f"{locale}:{prefix}{value} is empty"


def test_the_catalogues_are_the_six_launch_locales():
    present = sorted(
        name[:-5] for name in os.listdir(CATALOGUE_DIR) if name.endswith(".json")
    )
    assert present == sorted(localization.LAUNCH_LOCALES)
