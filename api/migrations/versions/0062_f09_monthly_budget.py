"""AI-CONTEXT: F9's spend cap becomes a MONTHLY one, and says so (audit F-17 + F-18).

F-17: `_check_budget` returned silently for a module with no `ModuleBudget` row, and
nothing in the product ever created one — `set_module_budget` had no caller outside the
tests. The cost control had never governed a single call.

F-18: `budget_used` summed every call ever made, so the cap was a lifetime ceiling with
no reset. Nothing said which it was, and "budget" everywhere else in this codebase means
a recurring allowance.

The two had to move together. Seeding budgets while the sum was still lifetime would have
turned an inert guard into a time bomb: each module going permanently dark the first time
it crossed its number, on a box with no monitoring, looking exactly like a broken feature.

Rows are seeded at boot by `module_registry.register_all`, not here — that keeps one
source of truth for the default and makes it idempotent for every future module.
"""

from alembic import op

revision = "0062_f09_monthly_budget"
down_revision = "0061_f01_login_attempt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # a rename rather than a new column: the stored numbers keep their meaning as a
    # ceiling, only the PERIOD they are measured over changes, and every existing row
    # (there are none in practice — nothing ever wrote one) stays valid
    op.alter_column(
        "module_budget",
        "budget_micros",
        new_column_name="monthly_budget_micros",
        schema="f09",
    )
    # the budget read is now "spend since the start of the month", so the index carries
    # the time. The single-column index on `module` becomes a redundant prefix of it.
    op.create_index(
        "ix_ai_call_module_time",
        "ai_call",
        ["module", "created_at"],
        schema="f09",
    )
    op.drop_index("ix_ai_call_module", table_name="ai_call", schema="f09")


def downgrade() -> None:
    op.create_index("ix_ai_call_module", "ai_call", ["module"], schema="f09")
    op.drop_index("ix_ai_call_module_time", table_name="ai_call", schema="f09")
    op.alter_column(
        "module_budget",
        "monthly_budget_micros",
        new_column_name="budget_micros",
        schema="f09",
    )
