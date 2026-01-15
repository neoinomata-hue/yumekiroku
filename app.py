import calendar as cal
import datetime as dt
import os
import sqlite3
import uuid

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename
from db import close_db, get_db, init_db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"
    app.config["DATABASE"] = os.path.join(app.root_path, "dreams.db")
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    @app.teardown_appcontext
    def teardown_db(exception):
        close_db(exception)

    with app.app_context():
        init_db()

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

    def normalize_items(value):
        if value is None:
            return ""
        items = []
        for raw in value.split(","):
            item = raw.strip()
            if item and item not in items:
                items.append(item)
        return ", ".join(items)

    def split_items(value):
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def parse_time(value):
        if not value:
            return None
        try:
            return dt.time.fromisoformat(value)
        except ValueError:
            return None

    def compute_sleep_minutes(start_time, end_time):
        if not start_time or not end_time:
            return None
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        if end_minutes < start_minutes:
            end_minutes += 24 * 60
        return end_minutes - start_minutes

    def format_sleep_minutes(minutes):
        if minutes is None:
            return "-"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}時間{mins:02d}分"

    def allowed_file(filename):
        if "." not in filename:
            return False
        ext = filename.rsplit(".", 1)[1].lower()
        return ext in {"png", "jpg", "jpeg", "gif"}

    def save_image(file_storage):
        if not file_storage or file_storage.filename == "":
            return None
        if not allowed_file(file_storage.filename):
            return None
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
        rel_path = f"uploads/{filename}"
        abs_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file_storage.save(abs_path)
        return rel_path

    def month_bounds(year, month):
        first_day = dt.date(year, month, 1)
        last_day = dt.date(year, month, cal.monthrange(year, month)[1])
        return first_day, last_day

    def build_tag_counts(rows, field):
        counts = {}
        for row in rows:
            for item in split_items(row[field]):
                counts[item] = counts.get(item, 0) + 1
        return [{"name": name, "count": counts[name]} for name in sorted(counts, key=counts.get, reverse=True)]

    def build_tag_list(rows, field):
        items = set()
        for row in rows:
            items.update(split_items(row[field]))
        return [{"name": name} for name in sorted(items)]

    def mood_class(mood):
        classes = {
            -2: "mood--2",
            -1: "mood--1",
            0: "mood-0",
            1: "mood-1",
            2: "mood-2",
        }
        return classes.get(mood, "mood-none")

    def get_dream(dream_id):
        db = get_db()
        dream = db.execute(
            "SELECT * FROM dreams WHERE dream_id = ?",
            (dream_id,),
        ).fetchone()
        if dream is None:
            abort(404)
        return dream

    @app.route("/")
    def home():
        return redirect(url_for("new_dream"))

    @app.route("/dreams")
    def calendar_view():
        ym = request.args.get("ym", "").strip()
        today = dt.date.today()
        if ym:
            try:
                year, month = map(int, ym.split("-"))
                current = dt.date(year, month, 1)
            except ValueError:
                current = dt.date(today.year, today.month, 1)
        else:
            current = dt.date(today.year, today.month, 1)

        first_day, last_day = month_bounds(current.year, current.month)
        db = get_db()
        rows = db.execute(
            """
            SELECT dream_id, date, title, mood, vividness, sleep_minutes, image_path
            FROM dreams
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC, created_at ASC
            """,
            (first_day.isoformat(), last_day.isoformat()),
        ).fetchall()

        dreams_by_date = {}
        counts = {}
        for row in rows:
            date_key = row["date"]
            counts[date_key] = counts.get(date_key, 0) + 1
            if date_key not in dreams_by_date:
                item = dict(row)
                item["sleep_display"] = format_sleep_minutes(row["sleep_minutes"])
                dreams_by_date[date_key] = item

        cal_obj = cal.Calendar(firstweekday=6)
        weeks = cal_obj.monthdatescalendar(current.year, current.month)
        prev_month = (current.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        next_month = (current.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

        return render_template(
            "calendar.html",
            weeks=weeks,
            year=current.year,
            month=current.month,
            today=today.isoformat(),
            dreams_by_date=dreams_by_date,
            counts=counts,
            mood_class=mood_class,
            prev_ym=prev_month.strftime("%Y-%m"),
            next_ym=next_month.strftime("%Y-%m"),
        )

    @app.route("/search")
    def search():
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
            term_clauses = []
            for term in split_items(tag):
                term_clauses.append(
                    "("
                    "d.location LIKE ? OR d.people LIKE ? OR d.thing LIKE ? "
                    "OR d.color LIKE ? OR d.smell LIKE ?"
                    ")"
                )
                like = f"%{term}%"
                params.extend([like, like, like, like, like])
            if term_clauses:
                conditions.append("(" + " OR ".join(term_clauses) + ")")

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        db = get_db()
        dreams = db.execute(
            f"""
            SELECT d.*
            FROM dreams d
            {where_sql}
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
        default_date = request.args.get("date", "").strip() or dt.date.today().isoformat()
        if request.method == "POST":
            form = request.form
            title = form.get("title", "").strip()
            location = normalize_items(form.get("location", ""))
            people = normalize_items(form.get("people", ""))
            thing = normalize_items(form.get("thing", ""))
            sound = parse_int(form.get("sound"), 0, 5)
            color = normalize_items(form.get("color", ""))
            smell = normalize_items(form.get("smell", ""))
            body = form.get("body", "").strip()
            date_str = form.get("date", "").strip() or dt.date.today().isoformat()
            mood = parse_int(form.get("mood"), -2, 2)
            vividness = parse_int(form.get("vividness"), 1, 5)
            fatigue = parse_int(form.get("fatigue"), 0, 5)
            sleep_start_str = form.get("sleep_start", "").strip()
            sleep_end_str = form.get("sleep_end", "").strip()
            sleep_start = parse_time(sleep_start_str)
            sleep_end = parse_time(sleep_end_str)
            sleep_minutes = compute_sleep_minutes(sleep_start, sleep_end)
            image = request.files.get("image")
            image_path = None

            errors = []
            if not title:
                errors.append("タイトルは必須です。")
            if not body:
                errors.append("本文は必須です。")
            if form.get("sound") and sound is None:
                errors.append("音は 0 から 5 の整数で入力してください。")
            if form.get("mood") and mood is None:
                errors.append("感情は -2 から 2 の整数で入力してください。")
            if form.get("vividness") and vividness is None:
                errors.append("鮮明度は 1 から 5 の整数で入力してください。")
            if form.get("fatigue") and fatigue is None:
                errors.append("疲労度は 0 から 5 の整数で入力してください。")
            if (sleep_start_str and sleep_start is None) or (sleep_end_str and sleep_end is None):
                errors.append("寝た時間は HH:MM 形式で入力してください。")
            if (sleep_start and not sleep_end) or (sleep_end and not sleep_start):
                errors.append("寝た時間は開始と終了を両方入力してください。")
            if image and image.filename and not allowed_file(image.filename):
                errors.append("画像は png/jpg/jpeg/gif のみ対応しています。")

            if errors:
                for err in errors:
                    flash(err, "error")
                form_data = dict(form)
                form_data["date"] = date_str
                form_data["sleep_duration"] = (
                    format_sleep_minutes(sleep_minutes) if sleep_minutes is not None else ""
                )
                return render_template(
                    "new.html",
                    form=form_data,
                )

            if image and image.filename:
                image_path = save_image(image)

            now = dt.datetime.now().isoformat(timespec="seconds")
            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO dreams (
                    date, title, location, people, thing, sound, color, smell, body,
                    mood, vividness, fatigue, sleep_start, sleep_end, sleep_minutes,
                    image_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_str,
                    title,
                    location,
                    people,
                    thing,
                    sound,
                    color,
                    smell,
                    body,
                    mood,
                    vividness,
                    fatigue,
                    sleep_start_str or None,
                    sleep_end_str or None,
                    sleep_minutes,
                    image_path,
                    now,
                    now,
                ),
            )
            dream_id = cursor.lastrowid
            db.commit()

            return redirect(url_for("detail", dream_id=dream_id))

        return render_template("new.html", form={"date": default_date})

    @app.route("/dreams/<int:dream_id>")
    def detail(dream_id):
        dream = get_dream(dream_id)
        sleep_display = format_sleep_minutes(dream["sleep_minutes"])
        return render_template(
            "detail.html",
            dream=dream,
            sleep_display=sleep_display,
        )

    @app.route("/dreams/<int:dream_id>/edit", methods=["GET", "POST"])
    def edit_dream(dream_id):
        dream = get_dream(dream_id)

        if request.method == "POST":
            form = request.form
            title = form.get("title", "").strip()
            location = normalize_items(form.get("location", ""))
            people = normalize_items(form.get("people", ""))
            thing = normalize_items(form.get("thing", ""))
            sound = parse_int(form.get("sound"), 0, 5)
            color = normalize_items(form.get("color", ""))
            smell = normalize_items(form.get("smell", ""))
            body = form.get("body", "").strip()
            date_str = form.get("date", "").strip() or dt.date.today().isoformat()
            mood = parse_int(form.get("mood"), -2, 2)
            vividness = parse_int(form.get("vividness"), 1, 5)
            fatigue = parse_int(form.get("fatigue"), 0, 5)
            sleep_start_str = form.get("sleep_start", "").strip()
            sleep_end_str = form.get("sleep_end", "").strip()
            sleep_start = parse_time(sleep_start_str)
            sleep_end = parse_time(sleep_end_str)
            sleep_minutes = compute_sleep_minutes(sleep_start, sleep_end)
            image = request.files.get("image")
            image_path = dream["image_path"]

            errors = []
            if not title:
                errors.append("タイトルは必須です。")
            if not body:
                errors.append("本文は必須です。")
            if form.get("sound") and sound is None:
                errors.append("音は 0 から 5 の整数で入力してください。")
            if form.get("mood") and mood is None:
                errors.append("感情は -2 から 2 の整数で入力してください。")
            if form.get("vividness") and vividness is None:
                errors.append("鮮明度は 1 から 5 の整数で入力してください。")
            if form.get("fatigue") and fatigue is None:
                errors.append("疲労度は 0 から 5 の整数で入力してください。")
            if (sleep_start_str and sleep_start is None) or (sleep_end_str and sleep_end is None):
                errors.append("寝た時間は HH:MM 形式で入力してください。")
            if (sleep_start and not sleep_end) or (sleep_end and not sleep_start):
                errors.append("寝た時間は開始と終了を両方入力してください。")
            if image and image.filename and not allowed_file(image.filename):
                errors.append("画像は png/jpg/jpeg/gif のみ対応しています。")

            if errors:
                for err in errors:
                    flash(err, "error")
                dream_data = dict(dream)
                dream_data["date"] = date_str
                dream_data["title"] = title
                dream_data["location"] = location
                dream_data["people"] = people
                dream_data["thing"] = thing
                dream_data["sound"] = form.get("sound", "")
                dream_data["color"] = color
                dream_data["smell"] = smell
                dream_data["body"] = body
                dream_data["mood"] = form.get("mood", "")
                dream_data["vividness"] = form.get("vividness", "")
                dream_data["fatigue"] = form.get("fatigue", "")
                dream_data["sleep_start"] = sleep_start_str
                dream_data["sleep_end"] = sleep_end_str
                dream_data["sleep_duration"] = (
                    format_sleep_minutes(sleep_minutes) if sleep_minutes is not None else ""
                )
                return render_template(
                    "edit.html",
                    dream=dream_data,
                )

            if image and image.filename:
                image_path = save_image(image)

            now = dt.datetime.now().isoformat(timespec="seconds")
            db = get_db()
            db.execute(
                """
                UPDATE dreams
                SET date = ?, title = ?, location = ?, people = ?, thing = ?, sound = ?, color = ?, smell = ?,
                    body = ?, mood = ?, vividness = ?, fatigue = ?, sleep_start = ?, sleep_end = ?,
                    sleep_minutes = ?, image_path = ?, updated_at = ?
                WHERE dream_id = ?
                """,
                (
                    date_str,
                    title,
                    location,
                    people,
                    thing,
                    sound,
                    color,
                    smell,
                    body,
                    mood,
                    vividness,
                    fatigue,
                    sleep_start_str or None,
                    sleep_end_str or None,
                    sleep_minutes,
                    image_path,
                    now,
                    dream_id,
                ),
            )
            db.commit()

            return redirect(url_for("detail", dream_id=dream_id))

        dream_data = dict(dream)
        dream_data["sleep_duration"] = (
            format_sleep_minutes(dream["sleep_minutes"])
            if dream["sleep_minutes"] is not None
            else ""
        )
        return render_template("edit.html", dream=dream_data)

    @app.route("/dreams/<int:dream_id>/delete", methods=["POST"])
    def delete_dream(dream_id):
        db = get_db()
        db.execute("DELETE FROM dreams WHERE dream_id = ?", (dream_id,))
        db.commit()
        return redirect(url_for("calendar_view"))

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
        base_where = ""
        if conditions:
            base_where = "WHERE " + " AND ".join(conditions)

        db = get_db()
        tag_rows = db.execute(
            f"""
            SELECT d.location, d.people, d.thing, d.color, d.smell
            FROM dreams d
            {base_where}
            """,
            params,
        ).fetchall()

        location_rows = build_tag_counts(tag_rows, "location")[:10]
        thing_rows = build_tag_counts(tag_rows, "thing")[:10]
        people_rows = build_tag_counts(tag_rows, "people")[:10]
        color_rows = build_tag_counts(tag_rows, "color")[:10]
        smell_rows = build_tag_counts(tag_rows, "smell")[:10]

        mood_row = db.execute(
            f"""
            SELECT AVG(d.mood) AS avg_mood
            FROM dreams d
            {base_where}
            """,
            params,
        ).fetchone()

        avg_mood = None
        if mood_row and mood_row["avg_mood"] is not None:
            avg_mood = round(mood_row["avg_mood"], 2)

        fatigue_row = db.execute(
            f"""
            SELECT AVG(d.fatigue) AS avg_fatigue
            FROM dreams d
            {base_where}
            """,
            params,
        ).fetchone()
        avg_fatigue = None
        if fatigue_row and fatigue_row["avg_fatigue"] is not None:
            avg_fatigue = round(fatigue_row["avg_fatigue"], 2)

        sleep_row = db.execute(
            f"""
            SELECT AVG(d.sleep_minutes) AS avg_sleep
            FROM dreams d
            {base_where}
            """,
            params,
        ).fetchone()
        avg_sleep = None
        if sleep_row and sleep_row["avg_sleep"] is not None:
            avg_sleep = format_sleep_minutes(int(round(sleep_row["avg_sleep"])))

        return render_template(
            "stats.html",
            location_rows=location_rows,
            thing_rows=thing_rows,
            people_rows=people_rows,
            color_rows=color_rows,
            smell_rows=smell_rows,
            avg_mood=avg_mood,
            avg_fatigue=avg_fatigue,
            avg_sleep=avg_sleep,
            date_from=date_from,
            date_to=date_to,
        )

    @app.route("/tags")
    def tag_list():
        db = get_db()
        tag_rows = db.execute(
            """
            SELECT location, people, thing, color, smell
            FROM dreams
            """
        ).fetchall()
        locations = build_tag_list(tag_rows, "location")
        things = build_tag_list(tag_rows, "thing")
        people = build_tag_list(tag_rows, "people")
        colors = build_tag_list(tag_rows, "color")
        smells = build_tag_list(tag_rows, "smell")

        return render_template(
            "tags.html",
            locations=locations,
            things=things,
            people=people,
            colors=colors,
            smells=smells,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)




