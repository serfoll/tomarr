import json
import sys

from tomarr.app import create_app


def main() -> None:
    # create_app() does not run the lifespan, so this needs no config directory or database.
    schema = create_app().openapi()
    sys.stdout.write(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
