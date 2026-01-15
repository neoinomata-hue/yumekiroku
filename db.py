import os
import sqlite3
from flask import current_app, g


def get_db():
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db_path = current_app.config["DATABASE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON;")
        schema_path = os.path.join(current_app.root_path, "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            db.executescript(f.read())
        ensure_dream_columns(db)
        normalize_image_paths(db)


def ensure_dream_columns(db):
    cursor = db.execute("PRAGMA table_info(dreams)")
    existing = {row[1] for row in cursor.fetchall()}
    desired = {
        "location": "TEXT",
        "people": "TEXT",
        "thing": "TEXT",
        "sound": "INTEGER",
        "color": "TEXT",
        "smell": "TEXT",
        "fatigue": "INTEGER",
        "sleep_start": "TEXT",
        "sleep_end": "TEXT",
        "sleep_minutes": "INTEGER",
        "image_path": "TEXT",
    }
    for column, col_type in desired.items():
        if column not in existing:
            db.execute(f"ALTER TABLE dreams ADD COLUMN {column} {col_type}")


def normalize_image_paths(db):
    db.execute(
        """
        UPDATE dreams
        SET image_path = REPLACE(image_path, '\\\\', '/')
        WHERE image_path LIKE '%\\\\%'
        """
    )
