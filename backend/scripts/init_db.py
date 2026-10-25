"""Create the schema (idempotent). Usage: python -m scripts.init_db"""
from app.database import models  # noqa: F401
from app.database.models import Base
from app.database.session import engine


def main() -> None:
    Base.metadata.create_all(engine)
    print("Schema ready on", engine.url.render_as_string(hide_password=True))


if __name__ == "__main__":
    main()
