"""Initialize a new HWK Stock SQLite database.

The application intentionally does not support legacy schema migration.
Delete the old HWK Stock database when this schema changes.
"""

from database.schema import create_tables


def init_database(db) -> None:
    create_tables(db)
    db.commit()
