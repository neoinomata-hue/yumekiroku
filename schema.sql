PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dreams (
    dream_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    title TEXT NOT NULL,
    location TEXT,
    people TEXT,
    thing TEXT,
    sound INTEGER,
    color TEXT,
    smell TEXT,
    body TEXT NOT NULL,
    mood INTEGER,
    vividness INTEGER,
    fatigue INTEGER,
    sleep_start TEXT,
    sleep_end TEXT,
    sleep_minutes INTEGER,
    image_path TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dream_tags (
    dream_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (dream_id, tag_id),
    FOREIGN KEY (dream_id) REFERENCES dreams(dream_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
);
