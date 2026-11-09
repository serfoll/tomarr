from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL

# A package resource, not a folder path, so the scripts are found from any working directory.
SCRIPT_LOCATION = "tomarr:migrations"


def upgrade_to_head(path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    # Passed as a URL object, not a main option: main options go through ConfigParser, which
    # rejects a "%" in the path, and a URL string would read a "?" in the path as a query.
    config.attributes["url"] = URL.create("sqlite", database=str(path))
    command.upgrade(config, "head")
