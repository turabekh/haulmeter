

def test_the_application_configures_logging_so_its_own_logs_are_not_a_void():
    """AI-CONTEXT: every `log.info` in this codebase went nowhere until 2026-08-18.

    uvicorn configures `uvicorn.*` and leaves the root logger alone, so three modules
    doing `logging.getLogger(__name__)` emitted into nothing — including a diagnostic
    added to settle a live "copilot not working" report, which produced no output on
    production because it was itself wired to nothing.
    """
    import logging

    from app.main import _configure_logging

    _configure_logging()
    assert logging.getLogger("app.api.m11_voice").isEnabledFor(logging.INFO)
    assert logging.getLogger().handlers, "root logger has nowhere to write"
