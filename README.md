# Dream Journal (Flask + SQLite)

A local web app to record, search, edit, and analyze your dreams.

## Features
- Create, read, update, delete (CRUD) dreams
- Tagging (comma-separated input)
- Search by keyword, date range, and tag
- Simple stats (top tags and average mood)

## Requirements
- Python 3.10+

## Setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:5000

## Project Structure
```
dream_journal/
  app.py
  db.py
  schema.sql
  templates/
    base.html
    index.html
    new.html
    detail.html
    edit.html
    stats.html
  static/
    style.css
  README.md
  requirements.txt
```

## Notes
- The SQLite database file (`dreams.db`) is created automatically on first run using `schema.sql`.
- Foreign keys are enabled via `PRAGMA foreign_keys = ON`.
- Title and body are required fields.
- Tag input is split by commas, trimmed, and de-duplicated.
- Tag duplicates are handled with `INSERT OR IGNORE` and a UNIQUE constraint on `tags.name`.

## Representative SQL
Keyword + date search:
```sql
SELECT d.*
FROM dreams d
WHERE (d.title LIKE ? OR d.body LIKE ?)
  AND d.date >= ?
  AND d.date <= ?
ORDER BY d.date DESC;
```

Tag join (many-to-many):
```sql
SELECT d.*, t.name
FROM dreams d
JOIN dream_tags dt ON dt.dream_id = d.dream_id
JOIN tags t ON t.tag_id = dt.tag_id
WHERE t.name = ?;
```

Tag frequency ranking:
```sql
SELECT t.name, COUNT(*) AS count
FROM dream_tags dt
JOIN tags t ON t.tag_id = dt.tag_id
GROUP BY t.tag_id
ORDER BY count DESC
LIMIT 10;
```
