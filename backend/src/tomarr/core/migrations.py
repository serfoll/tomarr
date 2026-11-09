from pathlib import Path

from alembic import command
from alembic.config import Config

# A package resource, not a folder path, so the scripts are found from any working directory.
SCRIPT_LOCATION = "tomarr:migrations"


def upgrade_to_head(path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(config, "head")
