import datetime as dt
import os
import sqlite3

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from db import close_db, get_db, init_db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"
    app.config["DATABASE"] = os.path.join(app.root_path, "dreams.db")

    @app.teardown_appcontext
    def teardown_db(exception):
        close_db(exception)

    with app.app_context():
        init_db()

    def normalize_tags(tag_string):
        tags = []
        for raw in tag_string.split(","):
            name = raw.strip()
            if name and name not in tags:
                tags.append(name)
        return tags

    def parse_int(value, min_value=None, max_value=None):
        if value is None or value == "":
            return None
        try:
            number = int(value)
        except ValueError:
            return None
        if min_value is not None and number < min_value:
            return None
        if max_value is not None and number > max_value:
            return None
        return number

    def get_dream(dream_id):
        db = get_db()
        dream = db.execute(
            "SELECT * FROM dreams WHERE dream_id = ?",
            (dream_id,),
        ).fetchone()
        if dream is None:
            abort(404)
        tags = db.execute(
            """
            SELECT t.name
            FROM tags t
            JOIN dream_tags dt ON dt.tag_id = t.tag_id
            WHERE dt.dream_id = ?
            ORDER BY t.name
            """,
            (dream_id,),
        ).fetchall()
        tag_names = ", ".join([row["name"] for row in tags])
        return dream, tag_names

    def save_tags(dream_id, tags):
        db = get_db()
        for tag in tags:
            db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tag_id = db.execute(
                "SELECT tag_id FROM tags WHERE name = ?",
                (tag,),
            ).fetchone()["tag_id"]
            db.execute(
                "INSERT OR IGNORE INTO dream_tags (dream_id, tag_id) VALUES (?, ?)",
                (dream_id, tag_id),
            )

    @app.route("/")
    @app.route("/dreams")
    @app.route("/search")
    def index():
        q = request.args.get("q", "").strip()
        date_from = request.args.get("from", "").strip()
        date_to = request.args.get("to", "").strip()
        tag = request.args.get("tag", "").strip()

        conditions = []
        params = []

        if q:
            conditions.append("(d.title LIKE ? OR d.body LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])
        if date_from:
            conditions.append("d.date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("d.date <= ?")
            params.append(date_to)
        if tag:
            conditions.append(
                "EXISTS (SELECT 1 FROM dream_tags dt2 JOIN tags t2 ON t2.tag_id = dt2.tag_id "
                "WHERE dt2.dream_id = d.dream_id AND t2.name = ?)"
            )
            params.append(tag)

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        db = get_db()
        dreams = db.execute(
            f"""
            SELECT d.*, COALESCE(group_concat(t.name, ', '), '') AS tags
            FROM dreams d
            LEFT JOIN dream_tags dt ON dt.dream_id = d.dream_id
            LEFT JOIN tags t ON t.tag_id = dt.tag_id
            {where_sql}
            GROUP BY d.dream_id
            ORDER BY d.date DESC, d.created_at DESC
            """,
            params,
        ).fetchall()

        return render_template(
            "index.html",
            dreams=dreams,
            q=q,
            date_from=date_from,
            date_to=date_to,
            tag=tag,
        )

    @app.route("/dreams/new", methods=["GET", "POST"])
    def new_dream():
        if request.method == "POST":
            form = request.form
            title = form.get("title", "").strip()
            body = form.get("body", "").strip()
            date_str = form.get("date", "").strip() or dt.date.today().isoformat()
            mood = parse_int(form.get("mood"), -2, 2)
            vividness = parse_int(form.get("vividness"), 1, 5)
            tag_input = form.get("tags", "")

            errors = []
            if not title:
                errors.append("Title is required.")
            if not body:
                errors.append("Body is required.")
            if form.get("mood") and mood is None:
                errors.append("Mood must be an integer between -2 and 2.")
            if form.get("vividness") and vividness is None:
                errors.append("Vividness must be an integer between 1 and 5.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template(
                    "new.html",
                    form=form,
                )

            now = dt.datetime.now().isoformat(timespec="seconds")
            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO dreams (date, title, body, mood, vividness, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (date_str, title, body, mood, vividness, now, now),
            )
            dream_id = cursor.lastrowid
            tags = normalize_tags(tag_input)
            save_tags(dream_id, tags)
            db.commit()

            return redirect(url_for("detail", dream_id=dream_id))

        return render_template("new.html", form={})

    @app.route("/dreams/<int:dream_id>")
    def detail(dream_id):
        dream, tag_names = get_dream(dream_id)
        return render_template("detail.html", dream=dream, tags=tag_names)

    @app.route("/dreams/<int:dream_id>/edit", methods=["GET", "POST"])
    def edit_dream(dream_id):
        dream, tag_names = get_dream(dream_id)

        if request.method == "POST":
            form = request.form
            title = form.get("title", "").strip()
            body = form.get("body", "").strip()
            date_str = form.get("date", "").strip() or dt.date.today().isoformat()
            mood = parse_int(form.get("mood"), -2, 2)
            vividness = parse_int(form.get("vividness"), 1, 5)
            tag_input = form.get("tags", "")

            errors = []
            if not title:
                errors.append("Title is required.")
            if not body:
                errors.append("Body is required.")
            if form.get("mood") and mood is None:
                errors.append("Mood must be an integer between -2 and 2.")
            if form.get("vividness") and vividness is None:
                errors.append("Vividness must be an integer between 1 and 5.")

            if errors:
                for err in errors:
                    flash(err, "error")
                dream_data = dict(dream)
                dream_data["date"] = date_str
                dream_data["title"] = title
                dream_data["body"] = body
                dream_data["mood"] = form.get("mood", "")
                dream_data["vividness"] = form.get("vividness", "")
                return render_template(
                    "edit.html",
                    dream=dream_data,
                    tags=tag_input,
                )

            now = dt.datetime.now().isoformat(timespec="seconds")
            db = get_db()
            db.execute(
                """
                UPDATE dreams
                SET date = ?, title = ?, body = ?, mood = ?, vividness = ?, updated_at = ?
                WHERE dream_id = ?
                """,
                (date_str, title, body, mood, vividness, now, dream_id),
            )
            db.execute("DELETE FROM dream_tags WHERE dream_id = ?", (dream_id,))
            tags = normalize_tags(tag_input)
            save_tags(dream_id, tags)
            db.commit()

            return redirect(url_for("detail", dream_id=dream_id))

        return render_template("edit.html", dream=dream, tags=tag_names)

    @app.route("/dreams/<int:dream_id>/delete", methods=["POST"])
    def delete_dream(dream_id):
        db = get_db()
        db.execute("DELETE FROM dreams WHERE dream_id = ?", (dream_id,))
        db.commit()
        return redirect(url_for("index"))

    @app.route("/stats")
    def stats():
        date_from = request.args.get("from", "").strip()
        date_to = request.args.get("to", "").strip()
        conditions = []
        params = []
        if date_from:
            conditions.append("d.date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("d.date <= ?")
            params.append(date_to)
        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        db = get_db()
        tag_rows = db.execute(
            f"""
            SELECT t.name, COUNT(*) AS count
            FROM dream_tags dt
            JOIN tags t ON t.tag_id = dt.tag_id
            JOIN dreams d ON d.dream_id = dt.dream_id
            {where_sql}
            GROUP BY t.tag_id
            ORDER BY count DESC, t.name ASC
            LIMIT 10
            """,
            params,
        ).fetchall()

        mood_row = db.execute(
            f"""
            SELECT AVG(d.mood) AS avg_mood
            FROM dreams d
            {where_sql}
            """,
            params,
        ).fetchone()

        avg_mood = None
        if mood_row and mood_row["avg_mood"] is not None:
            avg_mood = round(mood_row["avg_mood"], 2)

        return render_template(
            "stats.html",
            tags=tag_rows,
            avg_mood=avg_mood,
            date_from=date_from,
            date_to=date_to,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
