import json

from app.bootstrap import prepare_storage
from app.logging_setup import configure_logging
from app.pipeline import run_once


def main() -> None:
    configure_logging()
    prepare_storage()
    result = run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
