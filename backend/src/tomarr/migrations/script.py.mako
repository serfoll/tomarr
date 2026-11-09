"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
<%
    # Kept so a generated revision passes ruff unedited: double quotes, and sa and op are
    # imported only when the generated body uses them.
    body = (upgrades or "") + (downgrades or "")
    uses_sa = "sa." in body
    uses_op = "op." in body
    def quoted(value):
        return repr(value).replace("'", '"')
%>\

from collections.abc import Sequence
% if uses_sa or uses_op or imports:

% endif
% if uses_sa:
import sqlalchemy as sa
% endif
% if uses_op:
from alembic import op
% endif
% if imports:
${imports}
% endif

revision: str = ${quoted(up_revision)}
down_revision: str | Sequence[str] | None = ${quoted(down_revision)}
branch_labels: str | Sequence[str] | None = ${quoted(branch_labels)}
depends_on: str | Sequence[str] | None = ${quoted(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
