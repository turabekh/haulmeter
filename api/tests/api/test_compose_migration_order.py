"""AI-CONTEXT: N-03 — nothing may query the schema before the migration has written it.

Found on the 113→121 deploy, by reading the worker's log rather than assuming. Migrations
rode inside the api's command (`alembic upgrade head && uvicorn`) and the worker waited only
on postgres being healthy, so it booted against the OLD schema and every one of its seven
jobs failed:

    worker: detention_clock failed (1x): column feature_flag.default_on does not exist
    worker: outbound_retry  failed (1x): relation "f14.job_schedule" does not exist

`detention_clock` is M3's P0 — the alert that a driver's free time has expired. It recovered
on the failure backoff, but that backoff is up to 3600 s for four of the jobs, so every
migration-carrying deploy quietly cost the wedge feature its clock and the ingest jobs an
hour, and nothing said so.

WHY THIS IS A TEST AND NOT JUST A FIX. The bug was not that someone wrote the wrong
ordering; it was that the ordering was IMPLICIT — a reader had to know the api's command
happened to migrate first, and the worker's `depends_on` block looked complete on its own
terms. A third consumer of the schema added later would have looked equally complete and
been equally wrong. So the invariant is asserted rather than commented:

  · exactly one service runs `alembic upgrade`, and it is `migrate`
  · every service that talks to the database waits for it to COMPLETE
  · `migrate` does not restart, because a one-shot under `unless-stopped` loops forever

Both compose files, because CLAUDE.md's "dev = CI parity" rule means the ordering a deploy
relies on must be the ordering `make up` exercises — and because the local stack had the
identical race for exactly as long.
"""

from pathlib import Path

import pytest
import yaml

# AI-CONTEXT: mounted read-only into the api container at /repo/infra (see the api service
# in docker-compose.yml). The repo-relative path is the fallback for a run outside the
# container. It ASSERTS rather than skips when neither exists — the Makefile and i18n mounts
# beside it carry the same note for the same reason: a check that skips reports nothing while
# looking green.
_MOUNTED = Path("/repo/infra")
_LOCAL = Path(__file__).resolve().parents[3] / "infra"
INFRA = _MOUNTED if (_MOUNTED / "docker-compose.yml").exists() else _LOCAL
COMPOSE_FILES = ["docker-compose.yml", "docker-compose.deploy.yml"]

# the services that read or write application tables. `ui` builds the SPA, `caddy` serves
# files, `minio`/`redis`/`postgres` are the infrastructure itself.
DB_CONSUMERS = ("api", "worker")


def _compose(name: str) -> dict:
    path = INFRA / name
    assert path.exists(), f"{path} is missing — this test is the wrong shape, not the stack"
    return yaml.safe_load(path.read_text())


def _command_text(service: dict) -> str:
    cmd = service.get("command") or []
    return " ".join(cmd) if isinstance(cmd, list) else str(cmd)


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_exactly_one_service_applies_migrations(compose_file):
    """`alembic upgrade` in two places is two racing writers of the same schema."""
    services = _compose(compose_file)["services"]
    appliers = [n for n, s in services.items() if "alembic upgrade" in _command_text(s)]
    assert appliers == ["migrate"], (
        f"{compose_file}: expected only `migrate` to run alembic, found {appliers}. "
        "Migrations riding inside a long-running service's command is N-03."
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_every_database_consumer_waits_for_the_migration_to_complete(compose_file):
    """`service_started` or a bare list would not be enough: the schema is not ready when
    the container starts, it is ready when the process EXITS 0."""
    services = _compose(compose_file)["services"]
    for name in DB_CONSUMERS:
        assert name in services, f"{compose_file}: no `{name}` service"
        depends = services[name].get("depends_on") or {}
        assert isinstance(depends, dict), (
            f"{compose_file}: {name}'s depends_on is a plain list, which cannot express a "
            "completion condition — N-03 needs `service_completed_successfully`"
        )
        assert "migrate" in depends, (
            f"{compose_file}: {name} does not wait for `migrate`. This is N-03 exactly: "
            f"{name} queries the schema the migration writes."
        )
        assert depends["migrate"].get("condition") == "service_completed_successfully", (
            f"{compose_file}: {name} waits for `migrate` but not for it to SUCCEED "
            f"(condition={depends['migrate'].get('condition')!r})"
        )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_the_migration_step_does_not_restart(compose_file):
    """A one-shot service inheriting the stack's `unless-stopped` would re-run alembic in a
    loop forever, and the loop would look like a healthy service."""
    migrate = _compose(compose_file)["services"]["migrate"]
    assert str(migrate.get("restart", "")) in {"no", "No", "false"}, (
        f"{compose_file}: migrate has restart={migrate.get('restart')!r}; a one-shot must "
        "not restart"
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_the_migration_step_still_waits_for_its_database(compose_file):
    """It is the first thing to touch postgres, so it is the one that must not race it."""
    depends = _compose(compose_file)["services"]["migrate"].get("depends_on") or {}
    assert depends.get("postgres", {}).get("condition") == "service_healthy", (
        f"{compose_file}: migrate must wait for postgres to be healthy, got {depends}"
    )
