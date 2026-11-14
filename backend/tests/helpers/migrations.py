from alembic.config import Config
from alembic.script import ScriptDirectory

from tomarr.core.migrations import SCRIPT_LOCATION


def head_revision() -> str | None:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    return ScriptDirectory.from_config(config).get_current_head()
