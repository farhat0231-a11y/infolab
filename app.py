"""Информатика оқыту платформасы (7–11 сыныптар).

Іске қосу:
    pip install -r requirements.txt
    python app.py
Содан кейін браузерде ашыңыз: http://localhost:5000
"""
import csv
import io
import json
import os
import secrets
import sqlite3
import string
import sys
from datetime import date, datetime, timedelta
from functools import wraps

import markdown as md
from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import ai
import autocheck
from i18n import JS_KEYS, RU
from runner import check_code, run_code

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "data", "platform.db"))
BOOKS_DIR = os.path.join(BASE, "data", "books")
UPLOADS_DIR = os.path.join(BASE, "data", "uploads")  # оқушылардың практикалық жұмыс файлдары
UPLOAD_EXT = {"xlsx", "xls", "ods", "csv", "docx", "doc", "odt", "rtf", "txt", "pptx", "ppt", "odp", "pdf",
              "png", "jpg", "jpeg", "gif", "webp", "bmp", "py", "html", "css", "sb3", "zip"}
UPLOAD_MAX = 20 * 1024 * 1024
def _teacher_code():
    """Мұғалім болып тіркелу коды: TEACHER_CODE айнымалысы, болмаса data/teacher_code файлы.
    Файл жоқ болса, кездейсоқ код жасалып сақталады (код GitHub-қа кірмейді)."""
    if os.environ.get("TEACHER_CODE"):
        return os.environ["TEACHER_CODE"]
    path = os.path.join(BASE, "data", "teacher_code")
    try:
        with open(path) as f:
            if c := f.read().strip():
                return c
    except OSError:
        pass
    c = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(c)
    return c


TEACHER_CODE = _teacher_code()

app = Flask(__name__)
def _secret_key():
    """Кілт файлда сақталады: сайт қайта қосылғанда оқушылар жүйеден шығып кетпейді."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(BASE, "data", "secret_key")
    try:
        with open(path) as f:
            if k := f.read().strip():
                return k
    except OSError:
        pass
    k = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(k)
    return k


app.config["SECRET_KEY"] = _secret_key()
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.permanent_session_lifetime = timedelta(days=30)

TASK_TYPES = {"quiz": "Тест (бір жауап)", "multi": "Тест (бірнеше жауап)", "short": "Қысқа жауап",
              "code": "Python код", "open": "Ашық жауап", "file": "Практикалық жұмыс (файл)"}
QUIZ_ATTEMPTS = 2       # тест пен қысқа жауапқа берілетін әрекет саны
XP_PER_POINT = 10
XP_LESSON_BONUS = 20
XP_STREAK_BONUS = 5
LEVELS = [(0, "Жаңадан бастаушы"), (200, "Үйренуші"), (500, "Зерттеуші"), (1000, "Программист"),
          (2000, "Шебер"), (3500, "Сарапшы"), (5000, "Информатика батыры")]


# ───────────────────────── Деректер қоры ─────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('teacher','student')), class_id INTEGER,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS classes(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, grade INTEGER NOT NULL, code TEXT UNIQUE NOT NULL,
  teacher_id INTEGER NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, grade INTEGER NOT NULL, quarter INTEGER NOT NULL,
  num INTEGER NOT NULL, section TEXT, title TEXT NOT NULL, objectives TEXT, hours INTEGER DEFAULT 1,
  bjb INTEGER DEFAULT 0, theory TEXT DEFAULT '', updated TEXT);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, lesson_id INTEGER NOT NULL, ord INTEGER NOT NULL, type TEXT NOT NULL,
  prompt TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', points INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS class_lessons(
  class_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL, opened TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(class_id, lesson_id));
CREATE TABLE IF NOT EXISTS submissions(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, task_id INTEGER NOT NULL, answer TEXT,
  score REAL DEFAULT 0, max REAL DEFAULT 0, status TEXT DEFAULT 'graded', feedback TEXT,
  attempts INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT,
  UNIQUE(user_id, task_id));
CREATE TABLE IF NOT EXISTS xp_log(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT,
  day TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS books(
  id INTEGER PRIMARY KEY, grade INTEGER NOT NULL, title TEXT NOT NULL, lang TEXT, filename TEXT NOT NULL,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS comment_bank(
  id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS away_log(
  user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL, n INTEGER DEFAULT 0, secs INTEGER DEFAULT 0,
  updated TEXT, PRIMARY KEY(user_id, lesson_id));
CREATE TABLE IF NOT EXISTS answer_log(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, task_id INTEGER NOT NULL, n INTEGER NOT NULL,
  answer TEXT, score REAL, status TEXT, created TEXT);
CREATE INDEX IF NOT EXISTS ix_alog ON answer_log(user_id, task_id);
CREATE TABLE IF NOT EXISTS presence(
  user_id INTEGER PRIMARY KEY, lesson_id INTEGER, task_no INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0, last_seen TEXT);
CREATE TABLE IF NOT EXISTS penalties(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, teacher_id INTEGER NOT NULL, lesson_id INTEGER,
  xp INTEGER DEFAULT 0, pts REAL DEFAULT 0, reason TEXT, xp_log_id INTEGER, created TEXT);
CREATE INDEX IF NOT EXISTS ix_sub_user ON submissions(user_id);
CREATE INDEX IF NOT EXISTS ix_xp_user ON xp_log(user_id);
CREATE INDEX IF NOT EXISTS ix_tasks_lesson ON tasks(lesson_id);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def q(sql, args=(), one=False):
    cur = db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    migrate(con)
    con.commit()
    if con.execute("SELECT COUNT(*) FROM lessons").fetchone()[0] == 0:
        seed_curriculum(con)
    con.close()


MIGRATIONS = [("classes", "lang", "TEXT DEFAULT 'kk'"),
              ("lessons", "title_ru", "TEXT DEFAULT ''"), ("lessons", "theory_ru", "TEXT DEFAULT ''"),
              ("tasks", "prompt_ru", "TEXT DEFAULT ''"), ("tasks", "data_ru", "TEXT DEFAULT ''"),
              ("class_lessons", "due", "TEXT DEFAULT ''"), ("class_lessons", "late_pct", "INTEGER DEFAULT 50"),
              ("submissions", "late_pct", "INTEGER DEFAULT 100"), ("submissions", "rubric_scores", "TEXT DEFAULT ''"), ("submissions", "auto", "INTEGER DEFAULT 0"),
              ("lessons", "kind", "TEXT DEFAULT 'lesson'"), ("lessons", "parent_id", "INTEGER"),
              ("away_log", "pastes", "INTEGER DEFAULT 0")]


def migrate(con):
    """Ескі деректер қорына жаңа бағандарды қосу (орыс топтарына арналған мазмұн)."""
    for table, col, typ in MIGRATIONS:
        if col not in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def save_ru(con, lesson_id, ru):
    """content/*.json ішіндегі "ru" бөлімін (title, theory, tasks[{prompt, data}]) жазу."""
    con.execute("UPDATE lessons SET title_ru=?, theory_ru=? WHERE id=?",
                (ru.get("title", ""), ru.get("theory", ""), lesson_id))
    for k, t in enumerate(ru.get("tasks", [])):
        con.execute("UPDATE tasks SET prompt_ru=?, data_ru=? WHERE lesson_id=? AND ord=?",
                    (t["prompt"], json.dumps(t.get("data", {}), ensure_ascii=False), lesson_id, k))


def seed_curriculum(con):
    """КТЖ-дан алынған тақырыптарды және дайын сабақ мазмұнын жүктеу."""
    with open(os.path.join(BASE, "data", "curriculum.json"), encoding="utf-8") as f:
        cur = json.load(f)
    for grade, lessons in cur.items():
        for i, L in enumerate(lessons, 1):
            con.execute("INSERT OR IGNORE INTO lessons(code,grade,quarter,num,section,title,objectives,hours,bjb)"
                        " VALUES(?,?,?,?,?,?,?,?,?)",
                        (L["code"], int(grade), L["quarter"], i, L["section"], L["title"], L["objectives"],
                         L["hours"], int(L["bjb"])))
    cdir = os.path.join(BASE, "content")
    for fn in sorted(os.listdir(cdir)):
        if fn.endswith(".json"):
            with open(os.path.join(cdir, fn), encoding="utf-8") as f:
                c = json.load(f)
            row = con.execute("SELECT id FROM lessons WHERE code=?", (c["code"],)).fetchone()
            if not row:
                continue
            con.execute("UPDATE lessons SET theory=?, updated=? WHERE id=?", (c["theory"], now(), row[0]))
            con.execute("DELETE FROM tasks WHERE lesson_id=?", (row[0],))
            for k, t in enumerate(c["tasks"]):
                con.execute("INSERT INTO tasks(lesson_id,ord,type,prompt,data,points) VALUES(?,?,?,?,?,?)",
                            (row[0], k, t["type"], t["prompt"], json.dumps(t.get("data", {}), ensure_ascii=False),
                             t.get("points", 1)))
            if c.get("ru"):
                save_ru(con, row[0], c["ru"])
    con.commit()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return date.today().isoformat()


def lnum(L):
    """Сабақ нөмірі; тапсырмалар блогы өз сабағының нөмірінен кейін «+» белгісімен."""
    return f"{L['num']}+" if (L["kind"] or "lesson") == "block" else str(L["num"])


def dmy(s):
    """2026-11-05 → 05.11.2026"""
    try:
        return date.fromisoformat(s).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return s or ""


def deadline_state(class_id, lesson_id):
    """Сыныпқа ашылған сабақтың мерзімі: (мерзім, кештен кейінгі ұпай %, мерзім өтті ме)."""
    r = q("SELECT due, late_pct FROM class_lessons WHERE class_id=? AND lesson_id=?", (class_id, lesson_id), one=True)
    due = (r["due"] if r else "") or ""
    pct = r["late_pct"] if r and r["late_pct"] is not None else 50
    return due, pct, bool(due and today() > due)


def sub_full(sub, points):
    """Оқушы осы тапсырмаға қолжетімді ең жоғары ұпайды алды ма (кеш тапсырғанда — азайтылған максимум)."""
    pct = sub["late_pct"] if sub["late_pct"] is not None else 100
    return sub["score"] >= points * pct / 100 - 0.005


# ───────────────────────── Авторизация ─────────────────────────
@app.before_request
def load_user():
    g.user = None
    if "uid" in session:
        g.user = q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)
        if g.user and g.user["role"] == "student" and not request.path.startswith("/static"):
            g.user_xp = total_xp(g.user["id"])


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                return redirect(url_for("login", next=request.path))
            if role and g.user["role"] != role:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def gen_code(n=6):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        c = "".join(secrets.choice(alphabet) for _ in range(n))
        if not q("SELECT 1 FROM classes WHERE code=?", (c,), one=True):
            return c


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE username=?", (request.form["username"].strip().lower(),), one=True)
        if u and check_password_hash(u["pw"], request.form["password"]):
            session.clear()
            session.permanent = True
            session["uid"] = u["id"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("home"))
        flash(tr("Логин немесе құпия сөз қате"), "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, username, pw = f["name"].strip(), f["username"].strip().lower(), f["password"]
        role = f.get("role", "student")
        code = f.get("code", "").strip().upper()
        allowed = set(string.ascii_lowercase + string.digits + "._-")
        err = None
        if len(name) < 3:
            err = tr("Аты-жөніңізді толық жазыңыз")
        elif len(username) < 3 or not set(username) <= allowed:
            err = tr("Логин кемінде 3 таңба, тек латын әріптері, сандар және . _ -")
        elif len(pw) < 6:
            err = tr("Құпия сөз кемінде 6 таңба болуы керек")
        elif q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            err = tr("Бұл логин бос емес")
        class_id = None
        if not err and role == "teacher" and code != TEACHER_CODE.upper():
            err = tr("Мұғалім коды қате")
        if not err and role == "student":
            c = q("SELECT * FROM classes WHERE code=?", (code,), one=True)
            if not c:
                err = tr("Сынып коды табылмады. Мұғаліміңізден сұраңыз")
            else:
                class_id = c["id"]
        if err:
            flash(err, "error")
            return render_template("register.html", form=f)
        cur = db().execute("INSERT INTO users(name,username,pw,role,class_id) VALUES(?,?,?,?,?)",
                           (name, username, generate_password_hash(pw), role, class_id))
        db().commit()
        session.clear()
        session.permanent = True
        session["uid"] = cur.lastrowid
        flash(tr("Тіркелу сәтті өтті! Қош келдіңіз 👋"), "ok")
        return redirect(url_for("home"))
    return render_template("register.html", form={})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/lang/<code>")
def set_lang(code):
    """Тілді ауыстыру (Қаз | Рус): таңдау осы браузерде бір жыл сақталады."""
    nxt = request.args.get("next", "")
    resp = redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("home"))
    if code in ("kk", "ru"):
        resp.set_cookie("ui_lang", code, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


@app.route("/")
def home():
    if not g.user:
        return landing()
    if g.user["role"] == "teacher":
        return redirect(url_for("teacher_home"))
    return student_home()


# ───────────────────────── Басты бет (қонаққа) ─────────────────────────
PLATE_KIND = {"code": "Python", "file": "файл", "open": "ашық жауап", "quiz": "тест", "multi": "тест", "short": "қысқа жауап"}
DEMO_TESTS = [{"input": "3", "output": "9"}, {"input": "12", "output": "144"}, {"input": "-5", "output": "25"}]
_demo_hits = {}


def landing():
    """Кірмеген қонаққа: дәліздегі сабақ кестесі тақтасы (сабақ нөмірлері, атаулары жасырын), кіру, тірі тексеру."""
    m = date.today().month
    want = 1 if m in (9, 10) else 2 if m in (11, 12) else 3 if m in (1, 2, 3) else 4
    cols, now_id = [], None
    for grade in (7, 8, 9, 10, 11):
        base = """SELECT l.* FROM lessons l WHERE l.grade=? AND COALESCE(l.kind,'lesson')='lesson'
                  AND EXISTS(SELECT 1 FROM tasks t WHERE t.lesson_id=l.id)"""
        qn = q(base.replace("SELECT l.*", "SELECT MAX(l.quarter) qn") + " AND l.quarter<=?", (grade, want), one=True)["qn"] or want
        rows = []
        for L in q(base + " AND l.quarter=? ORDER BY l.num LIMIT 4", (grade, qn)):
            types = [r["type"] for r in q("SELECT type FROM tasks WHERE lesson_id=? ORDER BY ord", (L["id"],))]
            kind = "code" if "code" in types else "file" if "file" in types else types[0]
            rows.append({"id": L["id"], "num": L["num"], "kind": tr(PLATE_KIND.get(kind, kind))})
        cols.append({"grade": grade, "quarter": qn, "rows": rows})
    ids = [r["id"] for c in cols for r in c["rows"]]
    if ids:  # «қазір»: тақтадағы сабақтардың ішінен ең соңғы ашылғаны
        last = q(f"SELECT lesson_id FROM class_lessons WHERE lesson_id IN ({','.join('?' * len(ids))}) ORDER BY opened DESC LIMIT 1",
                 ids, one=True)
        now_id = last["lesson_id"] if last else None
    return render_template("landing.html", cols=cols, now_id=now_id, quarter=want)


@app.post("/api/demo")
def api_demo():
    """Басты беттегі тірі көрсетілім: бір бекітілген есеп, нәтиже ешқайда сақталмайды."""
    ip, t = request.remote_addr or "?", datetime.now().timestamp()
    hits = [h for h in _demo_hits.get(ip, []) if t - h < 60]
    if len(hits) >= 8:
        return jsonify({"error": tr("Тым жиі. Бір минуттан кейін қайталаңыз")}), 429
    _demo_hits[ip] = hits + [t]
    code = str((request.get_json(force=True, silent=True) or {}).get("code", ""))[:2000]
    return jsonify(check_code(code, DEMO_TESTS))


# ───────────────────────── Ұпай, деңгей, баға ─────────────────────────
def total_xp(uid):
    return max(0, q("SELECT COALESCE(SUM(amount),0) s FROM xp_log WHERE user_id=?", (uid,), one=True)["s"])


def level_of(xp):
    cur, nxt = LEVELS[0], None
    for i, (need, name) in enumerate(LEVELS):
        if xp >= need:
            cur = (need, name, i + 1)
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    progress = 100 if not nxt else int((xp - cur[0]) * 100 / (nxt[0] - cur[0]))
    return {"num": cur[2], "name": cur[1], "next": nxt[0] if nxt else None, "progress": progress}


def streak(uid):
    days = {r["day"] for r in q("SELECT DISTINCT day FROM xp_log WHERE user_id=? AND amount>0", (uid,))}
    d = date.today()
    if d.isoformat() not in days:
        d -= timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


def add_xp(uid, amount, reason):
    if amount <= 0:
        return 0
    t = today()
    first_today = not q("SELECT 1 FROM xp_log WHERE user_id=? AND day=? AND amount>0", (uid, t), one=True)
    db().execute("INSERT INTO xp_log(user_id,amount,reason,day) VALUES(?,?,?,?)", (uid, amount, reason, t))
    bonus = 0
    if first_today:
        s = streak(uid)
        if s >= 2:
            bonus = XP_STREAK_BONUS * min(s, 7)
            db().execute("INSERT INTO xp_log(user_id,amount,reason,day) VALUES(?,?,?,?)",
                         (uid, bonus, f"🔥 {s} күн қатарынан", t))
    return amount + bonus


def mark10(percent):
    """Сабақ бойынша 10 балдық баға (күнделікті бағалау)."""
    if percent is None:
        return None
    return max(1, min(10, round(percent / 10)))


def mark5(percent):
    """Тоқсандық 5 балдық баға (пайыз бойынша)."""
    if percent is None:
        return None
    return 5 if percent >= 85 else 4 if percent >= 65 else 3 if percent >= 40 else 2


def lesson_result(uid, lesson_id):
    """Оқушының бір сабақ бойынша нәтижесі: (жинаған балл, максимум, тексерілмеген бар ма, тапсырған ба)."""
    r = q("""SELECT COALESCE(SUM(t.points),0) mx,
                    COALESCE(SUM(s.score),0) sc,
                    SUM(CASE WHEN s.status='pending' THEN 1 ELSE 0 END) pend,
                    COUNT(s.id) done
             FROM tasks t LEFT JOIN submissions s ON s.task_id=t.id AND s.user_id=?
             WHERE t.lesson_id=?""", (uid, lesson_id), one=True)
    pen = q("SELECT COALESCE(SUM(pts),0) p FROM penalties WHERE user_id=? AND lesson_id=?", (uid, lesson_id), one=True)["p"]
    sc = max(0, r["sc"] - pen)  # мұғалімнің айыппұлы (сабақта ойын ойнау т.б.)
    return {"score": sc, "max": r["mx"], "pending": r["pend"] or 0, "done": r["done"], "penalty": pen,
            "percent": (sc * 100 / r["mx"]) if r["mx"] and r["done"] else None}


def view_lang():
    """Тіл: ?lang= (мұғалімнің алдын ала қарауы) → өзі таңдаған тіл (cookie) → оқушыға сыныбының тілі → қазақша."""
    if "lang" not in g:
        if request.args.get("lang") in ("kk", "ru"):
            g.lang = request.args["lang"]
        elif request.cookies.get("ui_lang") in ("kk", "ru"):
            g.lang = request.cookies["ui_lang"]
        elif g.get("user") and g.user["role"] == "student":
            c = q("SELECT lang FROM classes WHERE id=?", (g.user["class_id"],), one=True)
            g.lang = (c["lang"] if c else None) or "kk"
        else:
            g.lang = "ru" if request.args.get("lang") == "ru" else "kk"
    return g.lang


def tr(s):
    """Интерфейс мәтінін орыс тобына аудару (i18n.py)."""
    return RU.get(s, s) if view_lang() == "ru" else s


def js_i18n():
    return {k: RU[k] for k in JS_KEYS if k in RU} if view_lang() == "ru" else {}


def loc_lesson(L, lang=None):
    """Орыс тобына сабақтың орысша тақырыбы мен теориясын көрсету (бар болса)."""
    L = dict(L)
    if (lang or view_lang()) == "ru":
        L["title"] = L.get("title_ru") or L["title"]
        L["theory"] = L.get("theory_ru") or L["theory"]
    return L


def loc_task(t, lang=None):
    """Тапсырманың орысша мәтіні мен деректері (бар болса). alt_data — екінші тілдегі нұсқа."""
    t = dict(t)
    t["kk_data"] = t["data"]
    t["alt_data"] = t.get("data_ru") or ""
    if (lang or view_lang()) == "ru" and t.get("prompt_ru"):
        t["alt_data"], t["prompt"], t["data"] = t["data"], t["prompt_ru"], t["data_ru"] or t["data"]
    return t


def opened_lessons(class_id, quarter=None):
    sql = """SELECT l.*, cl.opened, cl.due, cl.late_pct FROM class_lessons cl JOIN lessons l ON l.id=cl.lesson_id
             WHERE cl.class_id=?"""
    args = [class_id]
    if quarter:
        sql += " AND l.quarter=?"
        args.append(quarter)
    lang = view_lang()
    return [loc_lesson(L, lang) for L in q(sql + " ORDER BY l.quarter, l.num, (l.kind='block'), l.id", args)]


def quarter_summary(uid, class_id, quarter):
    lessons = [L for L in opened_lessons(class_id, quarter) if task_count(L["id"])]
    sc = mx = 0
    marks = []
    for L in lessons:
        r = lesson_result(uid, L["id"])
        sc += r["score"]
        mx += r["max"]
        marks.append((L, r))
    pct = sc * 100 / mx if mx and any(r["done"] for _, r in marks) else None
    return {"lessons": marks, "score": sc, "max": mx, "percent": pct, "mark5": mark5(pct)}


def task_count(lesson_id):
    return q("SELECT COUNT(*) c FROM tasks WHERE lesson_id=?", (lesson_id,), one=True)["c"]


def leaderboard(class_id, limit=50, days=None):
    sql = """SELECT u.id, u.name, COALESCE(SUM(x.amount),0) xp FROM users u
             LEFT JOIN xp_log x ON x.user_id=u.id {cond}
             WHERE u.class_id=? AND u.role='student' GROUP BY u.id ORDER BY xp DESC, u.name LIMIT ?"""
    if days:
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        return q(sql.format(cond="AND x.day>=?"), (since, class_id, limit))
    return q(sql.format(cond=""), (class_id, limit))


@app.template_filter("md")
def md_filter(text):
    return Markup(md.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists", "nl2br"]))


@app.template_filter("fromjson")
def fromjson_filter(x):
    try:
        return json.loads(x)
    except (TypeError, ValueError):
        return None


@app.template_filter("fmt")
def fmt(x):
    if x is None:
        return "—"
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


app.jinja_env.globals.update(TASK_TYPES=TASK_TYPES, mark10=mark10, mark5=mark5, tr=tr, js_i18n=js_i18n,
                             view_lang=view_lang, today=today)
app.jinja_env.filters["dmy"] = dmy
app.jinja_env.globals["lnum"] = lnum


# ───────────────────────── Оқушы беттері ─────────────────────────
def student_home():
    u = g.user
    cls = q("SELECT * FROM classes WHERE id=?", (u["class_id"],), one=True)
    xp = total_xp(u["id"])
    lessons = opened_lessons(u["class_id"]) if cls else []
    items = []
    for L in reversed(lessons):
        r = lesson_result(u["id"], L["id"])
        items.append((L, r, task_count(L["id"])))
    today_xp = q("SELECT COALESCE(SUM(amount),0) s FROM xp_log WHERE user_id=? AND day=?",
                 (u["id"], today()), one=True)["s"]
    board = leaderboard(u["class_id"], 10, days=7) if cls else []
    return render_template("student_home.html", cls=cls, xp=xp, level=level_of(xp), streak=streak(u["id"]),
                           items=items, today_xp=today_xp, board=board, penalties=penalties_of(u["id"], 14))


def can_see_lesson(lesson_id):
    if g.user["role"] == "teacher":
        return True
    return bool(q("SELECT 1 FROM class_lessons WHERE class_id=? AND lesson_id=?",
                  (g.user["class_id"], lesson_id), one=True))


def task_criteria(t):
    """Рубрика критерийлері: мәтіні оқушының тілінде (бар болса), ұпайлары — қазақша (негізгі) нұсқадан."""
    kk = json.loads(t.get("kk_data") or t["data"] or "{}").get("criteria") or []
    cur = json.loads(t["data"] or "{}").get("criteria") or []
    if len(cur) != len(kk):
        cur = kk
    return [{"text": c["text"], "points": k["points"]} for c, k in zip(cur, kk)]


def task_public(t, sub=None):
    """Тапсырманы оқушыға жіберу үшін дұрыс жауаптарсыз дайындау."""
    d = json.loads(t["data"] or "{}")
    pub = {"id": t["id"], "type": t["type"], "prompt": t["prompt"], "html": str(md_filter(t["prompt"])),
           "points": t["points"]}
    if t["type"] in ("quiz", "multi"):
        pub["options"] = d.get("options", [])
    if t["type"] == "code":
        pub["starter"] = d.get("starter", "")
        pub["examples"] = [x for x in d.get("tests", []) if not x.get("hidden")][:2]
        pub["ntests"] = len(d.get("tests", []))
    if t["type"] == "short":
        pub["placeholder"] = d.get("placeholder", "")
    if t["type"] == "file":
        pub["accept"] = d.get("accept", "")
    if t["type"] == "file":
        pub["autocheck"] = bool(json.loads(t.get("kk_data") or t["data"] or "{}").get("auto"))
    if t["type"] in ("open", "file"):
        crit = task_criteria(t)
        if crit:
            pub["criteria"] = crit
    if sub:
        full = sub_full(sub, t["points"])
        pub["sub"] = {"answer": json.loads(sub["answer"] or "null"), "score": sub["score"], "max": sub["max"],
                      "status": sub["status"], "feedback": sub["feedback"], "attempts": sub["attempts"], "auto": bool(sub["auto"]),
                      "late_pct": sub["late_pct"] if sub["late_pct"] is not None else 100, "full": full}
        rs = json.loads(sub["rubric_scores"]) if sub["rubric_scores"] else None
        if rs and pub.get("criteria") and len(rs) == len(pub["criteria"]):
            pub["sub"]["rubric"] = rs
        if t["type"] in ("quiz", "multi", "short") and (sub["attempts"] >= QUIZ_ATTEMPTS or full):
            pub["solution"] = d.get("answer")
            pub["explain"] = str(md_filter(d.get("explain", ""))) if d.get("explain") else ""
    return pub


@app.route("/lesson/<int:lid>")
@login_required()
def lesson(lid):
    L = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) or abort(404)
    if not can_see_lesson(lid):
        abort(403)
    lang = view_lang()
    L = loc_lesson(L, lang)
    tasks = [loc_task(t, lang) for t in q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))]
    subs = {}
    if g.user["role"] == "student":
        subs = {s["task_id"]: s for s in q("SELECT * FROM submissions WHERE user_id=? AND task_id IN (SELECT id FROM tasks WHERE lesson_id=?)",
                                           (g.user["id"], lid))}
    pub = [task_public(t, subs.get(t["id"])) for t in tasks]
    res = lesson_result(g.user["id"], lid) if g.user["role"] == "student" else None
    dl = None
    if g.user["role"] == "student":
        due, pct, late = deadline_state(g.user["class_id"], lid)
        if due:
            dl = {"due": due, "pct": pct, "late": late}
    is_block = (L["kind"] or "lesson") == "block"
    parent = None
    if is_block and L["parent_id"]:
        P = q("SELECT * FROM lessons WHERE id=?", (L["parent_id"],), one=True)
        if P and can_see_lesson(P["id"]):
            parent = loc_lesson(P, lang)
    return render_template("lesson.html", L=L, tasks=pub, res=res, attempts=QUIZ_ATTEMPTS, lang=lang, dl=dl,
                           is_block=is_block, parent=parent)


@app.post("/api/run")
@login_required()
def api_run():
    data = request.get_json(force=True)
    code = data.get("code", "")[:20000]
    return jsonify(run_code(code, data.get("stdin", "")[:5000]))


def grade_auto(t, answer):
    d = json.loads(t["data"] or "{}")
    pts = t["points"]
    if t["type"] == "quiz":
        return (pts if str(answer) == str(d.get("answer")) else 0), None
    if t["type"] == "multi":
        right = set(map(int, d.get("answer", [])))
        got = set(map(int, answer or []))
        if not got:
            return 0, None
        # Ішінара балл: дұрыс таңдау – қате таңдау
        good = len(got & right) - len(got - right)
        return round(max(0, good) * pts / len(right), 2), None
    if t["type"] == "short":
        norm = lambda s: " ".join(str(s).strip().lower().replace(",", ".").split())
        answers = []
        for a in (d.get("answer"), json.loads(t.get("alt_data") or "{}").get("answer")):
            answers += a if isinstance(a, list) else [a] if a else []
        return (pts if norm(answer) in {norm(a) for a in answers} else 0), None
    if t["type"] == "code":
        r = check_code(str(answer), d.get("tests", []))
        sc = round(pts * r["passed"] / r["total"], 2) if r["total"] else 0
        return sc, r
    return 0, None


@app.post("/api/away/<int:lid>")
@login_required("student")
def api_away(lid):
    """Оқушы сабақ бетінен басқа терезеге / ЖИ панеліне ауысты — мұғалімге белгі ретінде жазылады."""
    try:
        secs = int((request.get_json(force=True, silent=True) or {}).get("secs", 0))
    except (TypeError, ValueError):
        secs = 0
    secs = max(0, min(secs, 3600))
    db().execute("""INSERT INTO away_log(user_id, lesson_id, n, secs, updated) VALUES(?,?,1,?,?)
                    ON CONFLICT(user_id, lesson_id) DO UPDATE SET n=n+1, secs=secs+excluded.secs, updated=excluded.updated""",
                 (g.user["id"], lid, secs, now()))
    db().commit()
    return jsonify({"ok": True})


def answer_history(uid, tid):
    """Оқушының бір тапсырмаға берген барлық жауаптары (ескісі бірінші)."""
    return [dict(r, answer=json.loads(r["answer"]) if r["answer"] else None)
            for r in q("SELECT * FROM answer_log WHERE user_id=? AND task_id=? ORDER BY id", (uid, tid))]


def away_of(uid, lid):
    return q("SELECT n, secs, pastes FROM away_log WHERE user_id=? AND lesson_id=?", (uid, lid), one=True)


@app.post("/api/paste/<int:lid>")
@login_required("student")
def api_paste(lid):
    """Жауап өрісіне мәтін қою әрекеті (бөгелді) — мұғалімге белгі ретінде саналады."""
    db().execute("""INSERT INTO away_log(user_id, lesson_id, pastes, updated) VALUES(?,?,1,?)
                    ON CONFLICT(user_id, lesson_id) DO UPDATE SET pastes=COALESCE(pastes,0)+1, updated=excluded.updated""",
                 (g.user["id"], lid, now()))
    db().commit()
    return jsonify({"ok": True})


@app.post("/api/ping/<int:lid>")
@login_required("student")
def api_ping(lid):
    """Оқушы сабақ бетінде: қай тапсырмада тұр, бет көрініп тұр ма (сабақ режимі үшін)."""
    d = request.get_json(force=True, silent=True) or {}
    try:
        task_no = max(0, min(int(d.get("task", 0)), 999))
    except (TypeError, ValueError):
        task_no = 0
    db().execute("""INSERT INTO presence(user_id, lesson_id, task_no, hidden, last_seen) VALUES(?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET lesson_id=excluded.lesson_id, task_no=excluded.task_no,
                    hidden=excluded.hidden, last_seen=excluded.last_seen""",
                 (g.user["id"], lid, task_no, 1 if d.get("hidden") else 0, now()))
    db().commit()
    return jsonify({"ok": True})


@app.post("/api/submit/<int:tid>")
@login_required("student")
def api_submit(tid):
    t = q("SELECT * FROM tasks WHERE id=?", (tid,), one=True) or abort(404)
    if not can_see_lesson(t["lesson_id"]):
        abort(403)
    t = loc_task(t)
    uid = g.user["id"]
    # Мерзім: өтіп кетсе — ұпай азаяды (немесе тапсыру жабылады)
    _due, lpct, is_late = deadline_state(g.user["class_id"], t["lesson_id"])
    if is_late and lpct == 0:
        return jsonify({"error": tr("Мерзім өтті, тапсыру жабық")}), 400
    factor = lpct if is_late else 100
    prev = q("SELECT * FROM submissions WHERE user_id=? AND task_id=?", (uid, tid), one=True)
    if t["type"] == "file":
        answer = save_upload(uid, t, prev)
        if isinstance(answer, str):
            return jsonify({"error": answer}), 400
    else:
        answer = request.get_json(force=True).get("answer")
    if t["type"] in ("quiz", "multi", "short") and prev and (prev["attempts"] >= QUIZ_ATTEMPTS or sub_full(prev, t["points"])):
        return jsonify({"error": tr("Әрекет саны таусылды")}), 400
    before = lesson_result(uid, t["lesson_id"])
    detail = None
    auto = None
    if t["type"] == "open":
        text = str(answer or "").strip()
        if len(text) < 3:
            return jsonify({"error": tr("Жауап бос")}), 400
        score, status = (prev["score"] if prev else 0), "pending"
    elif t["type"] == "file":
        score, status = (prev["score"] if prev else 0), "pending"
        auto = auto_grade_file(t, answer)  # .xlsx/.docx ережелер бойынша; мүмкін болмаса — мұғалімге
        if auto and auto["score"] <= 0:  # 0 балл — көбіне басқа файл жүктелген: мұғалім өзі қарасын
            auto = None
        if auto:
            score, status = round(auto["score"] * factor / 100, 2), "graded"
    else:
        score, detail = grade_auto(t, answer)
        score = round(score * factor / 100, 2)
        status = "graded"
    best = max(score, prev["score"] if prev and status == "graded" else 0)
    late_new = factor
    if prev and status == "graded" and best <= prev["score"]:
        late_new = prev["late_pct"] if prev["late_pct"] is not None else 100  # ұпай жақсармады — бұрынғы жазба қалады
    ans_json = json.dumps(answer, ensure_ascii=False)
    # Автотексеру нәтижесі (пікір + критерий баллдары) тек жақсы нәтиже болса жазылады
    use_auto = bool(auto) and (not prev or prev["status"] != "graded" or score > prev["score"])
    fb, rs, is_auto = (auto_feedback(auto), auto_rubric(t, auto), 1) if use_auto else (None, None, None)
    if prev:
        db().execute("UPDATE submissions SET answer=?, score=?, max=?, status=?, attempts=attempts+1, late_pct=?, updated=?,"
                     " feedback=COALESCE(?, feedback), rubric_scores=COALESCE(?, rubric_scores), auto=COALESCE(?, CASE WHEN status='pending' THEN 0 ELSE auto END) WHERE id=?",
                     (ans_json, best, t["points"], status, late_new, now(), fb, rs, is_auto, prev["id"]))
    else:
        db().execute("INSERT INTO submissions(user_id,task_id,answer,score,max,status,attempts,late_pct,updated,feedback,rubric_scores,auto)"
                     " VALUES(?,?,?,?,?,?,1,?,?,?,?,?)",
                     (uid, tid, ans_json, best, t["points"], status, late_new, now(), fb or "", rs or "", is_auto or 0))
    # Жауаптар тарихы: әр әрекет бөлек сақталады (мұғалім алдыңғы жауаптарды көреді)
    db().execute("INSERT INTO answer_log(user_id,task_id,n,answer,score,status,created) VALUES(?,?,?,?,?,?,?)",
                 (uid, tid, (prev["attempts"] or 0) + 1 if prev else 1, ans_json,
                  score if status == "graded" else None, status, now()))
    gained = 0
    old = prev["score"] if prev else 0
    if best > old:
        gained += add_xp(uid, round((best - old) * XP_PER_POINT), f"Тапсырма: {t['prompt'][:40]}")
    after = lesson_result(uid, t["lesson_id"])
    total_tasks = task_count(t["lesson_id"])
    if after["done"] == total_tasks and before["done"] < total_tasks:
        gained += add_xp(uid, XP_LESSON_BONUS, "Сабақ толық орындалды")
    db().commit()
    sub = q("SELECT * FROM submissions WHERE user_id=? AND task_id=?", (uid, tid), one=True)
    return jsonify({"task": task_public(t, sub), "detail": detail, "score": score, "xp": gained,
                    "lesson": after, "mark": mark10(after["percent"]), "total_xp": total_xp(uid)})


def auto_grade_file(t, answer):
    """Практикалық жұмыс файлын data["auto"] ережелері бойынша тексеру. Мүмкін болмаса — None (мұғалім тексереді)."""
    rules = json.loads(t.get("kk_data") or t["data"] or "{}").get("auto")
    if not rules:
        return None
    crit = task_criteria(t)
    if crit and len(crit) != len(rules):  # мұғалім критерийлерді өзгерткен — ережелер сәйкес емес
        return None
    lang = view_lang()
    labels = [c["text"] for c in crit] if crit else [r.get("ru" if lang == "ru" else "text", r.get("text", "")) for r in rules]
    path = os.path.join(UPLOADS_DIR, os.path.basename(answer["file"]))
    return autocheck.grade(path, answer["file"].rsplit(".", 1)[-1], rules, labels)


def auto_feedback(auto):
    lines = [("✓ " if i["ok"] else "✗ ") + i["label"] for i in auto["items"]]
    return tr("Автотексеру") + f": {auto['score']:g}/{auto['max']:g}\n" + "\n".join(lines)


def auto_rubric(t, auto):
    """Критерийлер бар болса — әр критерийге алынған балл (оқушы мен журналға көрсетіледі)."""
    return json.dumps([i["got"] for i in auto["items"]]) if task_criteria(t) else None


def save_upload(uid, t, prev):
    """Практикалық жұмыс файлын сақтау. Қате болса — қате мәтінін қайтарады."""
    f = request.files.get("file")
    if not f or not f.filename:
        return tr("Файлды таңдаңыз")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in UPLOAD_EXT:
        return tr("Бұл файл түрін жүктеуге болмайды") + f" (.{ext})"
    data = f.read(UPLOAD_MAX + 1)
    if len(data) > UPLOAD_MAX:
        return tr("Файл тым үлкен (20 МБ-тан аспауы керек)")
    fn = f"{uid}_{t['id']}_{secrets.token_hex(4)}.{ext}"
    with open(os.path.join(UPLOADS_DIR, fn), "wb") as out:
        out.write(data)
    old = json.loads(prev["answer"] or "null") if prev else None
    if isinstance(old, dict) and old.get("file"):
        try:
            os.remove(os.path.join(UPLOADS_DIR, os.path.basename(old["file"])))
        except OSError:
            pass
    return {"file": fn, "name": f.filename[-120:], "size": len(data)}


@app.route("/files/<fn>")
@login_required()
def upload_file(fn):
    """Практикалық жұмыс файлы: тек оның иесі мен сол сыныптың мұғаліміне."""
    fn = os.path.basename(fn)
    s = q("""SELECT s.answer, s.user_id, c.teacher_id FROM submissions s JOIN users u ON u.id=s.user_id
             LEFT JOIN classes c ON c.id=u.class_id WHERE s.answer LIKE ?""", (f'%"file": "{fn}"%',), one=True) or abort(404)
    if g.user["id"] not in (s["user_id"], s["teacher_id"]):
        abort(403)
    name = json.loads(s["answer"]).get("name") or fn
    return send_from_directory(UPLOADS_DIR, fn, download_name=name,
                               as_attachment=not fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp", "pdf"))


@app.route("/grades")
@login_required("student")
def my_grades():
    quarters = {qn: quarter_summary(g.user["id"], g.user["class_id"], qn) for qn in (1, 2, 3, 4)}
    return render_template("grades.html", quarters=quarters, student=g.user)


@app.route("/leaderboard")
@login_required()
def leaderboard_page():
    if g.user["role"] == "teacher":
        cid = request.args.get("class_id", type=int)
        cls = q("SELECT * FROM classes WHERE id=? AND teacher_id=?", (cid, g.user["id"]), one=True) or abort(404)
    else:
        cls = q("SELECT * FROM classes WHERE id=?", (g.user["class_id"],), one=True)
    period = request.args.get("p", "all")
    days = {"day": 1, "week": 7}.get(period)
    rows = leaderboard(cls["id"], 100, days)
    return render_template("leaderboard.html", rows=rows, cls=cls, period=period)


@app.route("/books")
@login_required()
def books():
    if g.user["role"] == "teacher":
        rows = q("SELECT * FROM books ORDER BY grade, title")
    else:
        grade = q("SELECT grade FROM classes WHERE id=?", (g.user["class_id"],), one=True)["grade"]
        rows = q("SELECT * FROM books WHERE grade=? ORDER BY title", (grade,))
    return render_template("books.html", rows=rows)


@app.route("/books/file/<int:bid>")
@login_required()
def book_file(bid):
    b = q("SELECT * FROM books WHERE id=?", (bid,), one=True) or abort(404)
    return send_from_directory(BOOKS_DIR, b["filename"])


# ───────────────────────── Мұғалім беттері ─────────────────────────
def my_class(cid):
    return q("SELECT * FROM classes WHERE id=? AND teacher_id=?", (cid, g.user["id"]), one=True) or abort(404)


@app.route("/teacher")
@login_required("teacher")
def teacher_home():
    classes = q("""SELECT c.*, (SELECT COUNT(*) FROM users u WHERE u.class_id=c.id) n,
                   (SELECT COUNT(*) FROM class_lessons cl WHERE cl.class_id=c.id) nl
                   FROM classes c WHERE teacher_id=? ORDER BY grade, name""", (g.user["id"],))
    pending = q("""SELECT COUNT(*) c FROM submissions s JOIN users u ON u.id=s.user_id
                   JOIN classes c ON c.id=u.class_id WHERE s.status='pending' AND c.teacher_id=?""",
                (g.user["id"],), one=True)["c"]
    filled = q("SELECT grade, COUNT(*) total, SUM(CASE WHEN EXISTS(SELECT 1 FROM tasks t WHERE t.lesson_id=l.id) THEN 1 ELSE 0 END) ready FROM lessons l WHERE COALESCE(l.kind,'lesson')='lesson' GROUP BY grade")
    return render_template("teacher_home.html", classes=classes, pending=pending, filled=filled)


@app.post("/teacher/class/new")
@login_required("teacher")
def class_new():
    name = request.form["name"].strip()
    grade = int(request.form["grade"])
    lang = "ru" if request.form.get("lang") == "ru" else "kk"
    if not name or grade not in range(7, 12):
        flash("Сынып атауы мен сыныбын дұрыс толтырыңыз", "error")
        return redirect(url_for("teacher_home"))
    db().execute("INSERT INTO classes(name,grade,code,teacher_id,lang) VALUES(?,?,?,?,?)",
                 (name, grade, gen_code(), g.user["id"], lang))
    db().commit()
    flash(f"«{name}» сыныбы құрылды", "ok")
    return redirect(url_for("teacher_home"))


@app.route("/teacher/class/<int:cid>")
@login_required("teacher")
def class_page(cid):
    cls = my_class(cid)
    students = q("""SELECT u.*, COALESCE((SELECT SUM(amount) FROM xp_log x WHERE x.user_id=u.id),0) xp
                    FROM users u WHERE class_id=? ORDER BY name""", (cid,))
    lessons = q("""SELECT l.*, cl.opened, cl.due, cl.late_pct, (SELECT COUNT(*) FROM tasks t WHERE t.lesson_id=l.id) nt
                   FROM lessons l LEFT JOIN class_lessons cl ON cl.lesson_id=l.id AND cl.class_id=?
                   WHERE l.grade=? ORDER BY quarter, num, (l.kind='block'), l.id""", (cid, cls["grade"]))
    return render_template("class_page.html", cls=cls, students=students, lessons=lessons)


@app.post("/teacher/class/<int:cid>/lang")
@login_required("teacher")
def class_lang(cid):
    my_class(cid)
    lang = "ru" if request.form.get("lang") == "ru" else "kk"
    db().execute("UPDATE classes SET lang=? WHERE id=?", (lang, cid))
    db().commit()
    flash("Сабақ тілі: " + ("орысша" if lang == "ru" else "қазақша"), "ok")
    return redirect(url_for("class_page", cid=cid))


@app.post("/teacher/class/<int:cid>/toggle/<int:lid>")
@login_required("teacher")
def toggle_lesson(cid, lid):
    my_class(cid)
    if q("SELECT 1 FROM class_lessons WHERE class_id=? AND lesson_id=?", (cid, lid), one=True):
        db().execute("DELETE FROM class_lessons WHERE class_id=? AND lesson_id=?", (cid, lid))
    else:
        db().execute("INSERT INTO class_lessons(class_id,lesson_id,opened) VALUES(?,?,?)", (cid, lid, now()))
    db().commit()
    return redirect(url_for("class_page", cid=cid) + f"#l{lid}")


def _local(nxt):
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else ""


@app.post("/teacher/lesson/<int:lid>/block/new")
@login_required("teacher")
def block_new(lid):
    """Сабаққа теориясыз, тек тапсырмалардан тұратын блок қосу (бос немесе сабақ тапсырмаларының көшірмесімен)."""
    P = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) or abort(404)
    if (P["kind"] or "lesson") == "block":  # блоктың блогы болмайды — ата сабаққа қосамыз
        P = q("SELECT * FROM lessons WHERE id=?", (P["parent_id"],), one=True) or abort(404)
    n = q("SELECT COUNT(*) c FROM lessons WHERE parent_id=?", (P["id"],), one=True)["c"] + 1
    while q("SELECT 1 FROM lessons WHERE code=?", (f"{P['code']}-b{n}",), one=True):
        n += 1
    title = f"{P['title']} — тапсырмалар блогы" + (f" ({n})" if n > 1 else "")
    title_ru = (f"{P['title_ru']} — блок заданий" + (f" ({n})" if n > 1 else "")) if P["title_ru"] else ""
    cur = db().execute("""INSERT INTO lessons(code,grade,quarter,num,section,title,objectives,hours,bjb,theory,updated,kind,parent_id,title_ru)
                          VALUES(?,?,?,?,?,?,?,0,0,'',?,'block',?,?)""",
                       (f"{P['code']}-b{n}", P["grade"], P["quarter"], P["num"], P["section"], title, P["objectives"],
                        now(), P["id"], title_ru))
    bid = cur.lastrowid
    copied = 0
    if request.form.get("mode") == "copy":
        for r in q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (P["id"],)):
            db().execute("INSERT INTO tasks(lesson_id,ord,type,prompt,data,points,prompt_ru,data_ru) VALUES(?,?,?,?,?,?,?,?)",
                         (bid, r["ord"], r["type"], r["prompt"], r["data"], r["points"], r["prompt_ru"], r["data_ru"]))
            copied += 1
    db().commit()
    nxt = _local(request.form.get("next", ""))
    if copied and nxt:
        flash(f"Блок құрылды: {copied} тапсырма көшірілді ✓", "ok")
        return redirect(nxt + f"#l{bid}")
    flash("Блок құрылды. Тапсырмаларды қосыңыз ✓", "ok")
    return redirect(url_for("lesson_edit", lid=bid))


@app.post("/teacher/block/<int:bid>/delete")
@login_required("teacher")
def block_delete(bid):
    B = q("SELECT * FROM lessons WHERE id=? AND kind='block'", (bid,), one=True) or abort(404)
    back = _local(request.form.get("next", "")) or url_for("lessons_admin", grade=B["grade"])
    if q("SELECT 1 FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE t.lesson_id=? LIMIT 1", (bid,), one=True):
        flash("Блокта оқушы жауаптары бар — өшіруге болмайды", "error")
        return redirect(back)
    db().execute("DELETE FROM tasks WHERE lesson_id=?", (bid,))
    db().execute("DELETE FROM class_lessons WHERE lesson_id=?", (bid,))
    db().execute("DELETE FROM lessons WHERE id=?", (bid,))
    db().commit()
    flash("Блок өшірілді", "ok")
    return redirect(back)


@app.post("/teacher/class/<int:cid>/due/<int:lid>")
@login_required("teacher")
def class_due(cid, lid):
    """Сабаққа мерзім және кеш тапсыру ережесін қою (мерзімді тазалау үшін күнді бос қалдырыңыз)."""
    my_class(cid)
    due = request.form.get("due", "").strip()
    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            flash("Күн дұрыс емес", "error")
            return redirect(url_for("class_page", cid=cid) + f"#l{lid}")
    late = request.form.get("late", "50")
    late = int(late) if late in ("0", "50", "75", "100") else 50
    db().execute("UPDATE class_lessons SET due=?, late_pct=? WHERE class_id=? AND lesson_id=?", (due, late, cid, lid))
    db().commit()
    flash("Мерзім сақталды ✓" if due else "Мерзім алынды", "ok")
    return redirect(url_for("class_page", cid=cid) + f"#l{lid}")


@app.post("/teacher/class/<int:cid>/reset/<int:uid>")
@login_required("teacher")
def reset_password(cid, uid):
    my_class(cid)
    u = q("SELECT * FROM users WHERE id=? AND class_id=?", (uid, cid), one=True) or abort(404)
    pw = "".join(secrets.choice("23456789") for _ in range(6))
    db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(pw), uid))
    db().commit()
    flash(f"{u['name']} — жаңа құпия сөз: {pw}", "ok")
    return redirect(url_for("class_page", cid=cid))


@app.post("/teacher/class/<int:cid>/penalty/<int:uid>")
@login_required("teacher")
def penalize_student(cid, uid):
    """Айыппұл: оқушыдан XP және (таңдалса) бір сабақтың балын алу. Оқушы себебін өз бетінде көреді."""
    my_class(cid)
    u = q("SELECT * FROM users WHERE id=? AND class_id=? AND role='student'", (uid, cid), one=True) or abort(404)
    try:
        xp = max(0, min(int(request.form.get("xp", "0") or 0), 10000))
        pts = max(0.0, min(float(str(request.form.get("pts", "0") or 0).replace(",", ".")), 100.0))
    except ValueError:
        flash("Санды дұрыс жазыңыз", "error")
        return redirect(url_for("class_page", cid=cid))
    lid = request.form.get("lesson", type=int)
    if lid and not q("SELECT 1 FROM class_lessons WHERE class_id=? AND lesson_id=?", (cid, lid), one=True):
        lid = None
    if not lid:
        pts = 0.0
    if not xp and not pts:
        flash("XP немесе балл мөлшерін көрсетіңіз", "error")
        return redirect(url_for("class_page", cid=cid))
    reason = " ".join(request.form.get("reason", "").split())[:120] or "Сабақта ойын ойнады"
    log_id = None
    if xp:
        log_id = db().execute("INSERT INTO xp_log(user_id,amount,reason,day) VALUES(?,?,?,?)",
                              (uid, -xp, "Айыппұл: " + reason, today())).lastrowid
    db().execute("INSERT INTO penalties(user_id,teacher_id,lesson_id,xp,pts,reason,xp_log_id,created) VALUES(?,?,?,?,?,?,?,?)",
                 (uid, g.user["id"], lid, xp, pts, reason, log_id, now()))
    db().commit()
    parts = ([f"−{xp} XP"] if xp else []) + ([f"−{pts:g} балл"] if pts else [])
    flash(f"{u['name']}: {', '.join(parts)} ({reason})", "ok")
    return redirect(url_for("class_page", cid=cid))


@app.post("/teacher/penalty/<int:pid>/cancel")
@login_required("teacher")
def cancel_penalty(pid):
    """Қате қойылған айыппұлды қайтару: XP мен балл орнына келеді."""
    p = q("""SELECT p.* FROM penalties p JOIN users u ON u.id=p.user_id JOIN classes c ON c.id=u.class_id
             WHERE p.id=? AND c.teacher_id=?""", (pid, g.user["id"]), one=True) or abort(404)
    if p["xp_log_id"]:
        db().execute("DELETE FROM xp_log WHERE id=?", (p["xp_log_id"],))
    db().execute("DELETE FROM penalties WHERE id=?", (pid,))
    db().commit()
    flash("Айыппұл алынып тасталды", "ok")
    return redirect(request.referrer or url_for("student_detail", uid=p["user_id"]))


def penalties_of(uid, days=None):
    cond = " AND p.created >= ?" if days else ""
    args = (uid, (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")) if days else (uid,)
    return q(f"""SELECT p.*, l.title, l.title_ru FROM penalties p LEFT JOIN lessons l ON l.id=p.lesson_id
                 WHERE p.user_id=?{cond} ORDER BY p.id DESC""", args)


@app.post("/teacher/class/<int:cid>/rename/<int:uid>")
@login_required("teacher")
def rename_student(cid, uid):
    """Оқушының аты-жөнін тек мұғалім түзетеді (оқушыда мұндай мүмкіндік жоқ)."""
    my_class(cid)
    u = q("SELECT * FROM users WHERE id=? AND class_id=? AND role='student'", (uid, cid), one=True) or abort(404)
    name = " ".join(request.form.get("name", "").split())[:80]
    if len(name) < 3:
        flash("Аты-жөнін толық жазыңыз", "error")
    elif name != u["name"]:
        db().execute("UPDATE users SET name=? WHERE id=?", (name, uid))
        db().commit()
        flash(f"Аты-жөні түзетілді: {u['name']} → {name}", "ok")
    return redirect(url_for("class_page", cid=cid))


@app.post("/teacher/class/<int:cid>/remove/<int:uid>")
@login_required("teacher")
def remove_student(cid, uid):
    my_class(cid)
    db().execute("UPDATE users SET class_id=NULL WHERE id=? AND class_id=?", (uid, cid))
    db().commit()
    flash("Оқушы сыныптан шығарылды", "ok")
    return redirect(url_for("class_page", cid=cid))


@app.post("/teacher/class/<int:cid>/delete")
@login_required("teacher")
def class_delete(cid):
    cls = my_class(cid)
    d = db()
    d.execute("UPDATE users SET class_id=NULL WHERE class_id=? AND role='student'", (cid,))
    d.execute("DELETE FROM class_lessons WHERE class_id=?", (cid,))
    d.execute("DELETE FROM classes WHERE id=?", (cid,))
    d.commit()
    flash(f"Сынып «{cls['name']}» өшірілді", "ok")
    return redirect(url_for("teacher_home"))


def journal_data(cls, quarter):
    lessons = [L for L in opened_lessons(cls["id"], quarter) if task_count(L["id"])]
    students = q("SELECT * FROM users WHERE class_id=? AND role='student' ORDER BY name", (cls["id"],))
    rows = []
    for s in students:
        cells, sc, mx = [], 0, 0
        for L in lessons:
            r = dict(lesson_result(s["id"], L["id"]), away=away_of(s["id"], L["id"]))
            cells.append(r)
            sc += r["score"]
            mx += r["max"]
        pct = sc * 100 / mx if mx and any(c["done"] for c in cells) else None
        rows.append({"s": s, "cells": cells, "percent": pct, "mark5": mark5(pct)})
    return lessons, rows


ONLINE_SECS = 45  # соңғы белгіден бері осыдан аз уақыт өтсе — оқушы сабақ бетінде


def live_data(cls, lid):
    """Сабақ режимі: әр оқушының қазіргі күйі және таңдалған сабақ бойынша прогресі."""
    tasks = q("SELECT id, type FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))
    nt = len(tasks)
    limit = (datetime.now() - timedelta(seconds=ONLINE_SECS)).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for s in q("SELECT id, name FROM users WHERE class_id=? AND role='student' ORDER BY name", (cls["id"],)):
        p = q("SELECT * FROM presence WHERE user_id=?", (s["id"],), one=True)
        r = lesson_result(s["id"], lid)
        a = away_of(s["id"], lid)
        if p and p["last_seen"] >= limit:
            state = "away" if p["hidden"] else ("here" if p["lesson_id"] == lid else "other")
        else:
            state = "off"
        rows.append({"id": s["id"], "name": s["name"], "state": state,
                     "task": p["task_no"] if p and state == "here" else None,
                     "other": p["lesson_id"] if p and state == "other" else None,
                     "done": r["done"], "nt": nt, "pending": r["pending"],
                     "percent": round(r["percent"]) if r["percent"] is not None else None,
                     "away_n": a["n"] if a else 0, "away_secs": a["secs"] if a else 0,
                     "pastes": (a["pastes"] or 0) if a else 0})
    order = {"here": 0, "away": 1, "other": 2, "off": 3}
    rows.sort(key=lambda x: (order[x["state"]], x["name"]))
    return rows


@app.route("/teacher/class/<int:cid>/live")
@login_required("teacher")
def class_live(cid):
    cls = my_class(cid)
    lessons = [L for L in opened_lessons(cls["id"]) if task_count(L["id"])]
    lessons.sort(key=lambda L: L["opened"] or "", reverse=True)
    lid = request.args.get("lesson", type=int)
    if not lid:  # әдепкіде — оқушылардың көбі қазір отырған сабақ, болмаса соңғы ашылған сабақ
        limit = (datetime.now() - timedelta(seconds=ONLINE_SECS)).strftime("%Y-%m-%d %H:%M:%S")
        busy = q("""SELECT p.lesson_id, COUNT(*) c FROM presence p JOIN users u ON u.id=p.user_id
                    WHERE u.class_id=? AND p.last_seen>=? GROUP BY p.lesson_id ORDER BY c DESC""", (cid, limit))
        ids = {L["id"] for L in lessons}
        lid = next((b["lesson_id"] for b in busy if b["lesson_id"] in ids), None) or (lessons[0]["id"] if lessons else None)
    L = next((x for x in lessons if x["id"] == lid), None)
    rows = live_data(cls, L["id"]) if L else []
    if request.args.get("format") == "json":
        return jsonify({"rows": rows, "time": datetime.now().strftime("%H:%M:%S")})
    return render_template("live.html", cls=cls, lessons=lessons, L=L, rows=rows)


@app.route("/teacher/class/<int:cid>/journal")
@login_required("teacher")
def journal(cid):
    cls = my_class(cid)
    quarter = request.args.get("q", 1, type=int)
    lessons, rows = journal_data(cls, quarter)
    return render_template("journal.html", cls=cls, quarter=quarter, lessons=lessons, rows=rows)


@app.route("/teacher/class/<int:cid>/journal.csv")
@login_required("teacher")
def journal_csv(cid):
    cls = my_class(cid)
    quarter = request.args.get("q", 1, type=int)
    lessons, rows = journal_data(cls, quarter)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Оқушы"] + [f"{L['num']}. {L['title']}" for L in lessons] + ["Пайыз", "Тоқсандық баға"])
    for r in rows:
        w.writerow([r["s"]["name"]] + [mark10(c["percent"]) or "" for c in r["cells"]] +
                   [f"{r['percent']:.0f}%" if r["percent"] is not None else "", r["mark5"] or ""])
    data = "﻿" + buf.getvalue()  # Excel кириллицаны дұрыс ашуы үшін BOM
    fn = f"journal_{cls['name']}_{quarter}toqsan.csv"
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{secure_filename(fn) or 'journal.csv'}"})


@app.route("/teacher/student/<int:uid>")
@login_required("teacher")
def student_detail(uid):
    s = q("""SELECT u.* FROM users u JOIN classes c ON c.id=u.class_id
             WHERE u.id=? AND c.teacher_id=?""", (uid, g.user["id"]), one=True) or abort(404)
    lid = request.args.get("lesson", type=int)
    subs = []
    if lid:
        subs = q("""SELECT t.*, s.answer, s.score, s.status, s.feedback, s.attempts, s.updated
                    FROM tasks t LEFT JOIN submissions s ON s.task_id=t.id AND s.user_id=?
                    WHERE t.lesson_id=? ORDER BY t.ord""", (uid, lid))
        subs = [dict(x, answer=json.loads(x["answer"]) if x["answer"] else None, data=json.loads(x["data"]),
                     hist=answer_history(uid, x["id"])) for x in subs]
    quarters = {qn: quarter_summary(uid, s["class_id"], qn) for qn in (1, 2, 3, 4)}
    xp = total_xp(uid)
    L = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) if lid else None
    away = away_of(uid, lid) if lid else None
    return render_template("student_detail.html", s=s, quarters=quarters, subs=subs, L=L, xp=xp, away=away,
                           penalties=penalties_of(uid),
                           level=level_of(xp), streak=streak(uid))


@app.post("/teacher/student/<int:uid>/retake/<int:lid>")
@login_required("teacher")
def student_retake(uid, lid):
    """Оқушыға сабақты басынан қайта тапсыруға рұқсат: жауаптары өшеді, тарихы (answer_log) сақталады,
    бұрын алған XP шегеріледі (қайта орындағанда екі рет жиналмасын)."""
    s = q("""SELECT u.* FROM users u JOIN classes c ON c.id=u.class_id
             WHERE u.id=? AND c.teacher_id=?""", (uid, g.user["id"]), one=True) or abort(404)
    L = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) or abort(404)
    r = lesson_result(uid, lid)
    if not r["done"]:
        flash("Бұл сабақта өшіретін жауап жоқ", "error")
        return redirect(url_for("student_detail", uid=uid, lesson=lid))
    nt = task_count(lid)
    refund = round(r["score"] * XP_PER_POINT) + (XP_LESSON_BONUS if nt and r["done"] == nt else 0)
    if refund > 0:
        db().execute("INSERT INTO xp_log(user_id,amount,reason,day) VALUES(?,?,?,?)",
                     (uid, -refund, f"Қайта тапсыру: {L['title'][:40]}", today()))
    db().execute("DELETE FROM submissions WHERE user_id=? AND task_id IN (SELECT id FROM tasks WHERE lesson_id=?)", (uid, lid))
    db().commit()
    flash(f"{s['name']}: «{L['title']}» сабағын басынан қайта тапсыра алады ✓ (жауаптар тарихы сақталды)", "ok")
    return redirect(url_for("student_detail", uid=uid, lesson=lid))


DEFAULT_COMMENTS = [
    "Жарайсың! Дұрыс орындалған.", "Тапсырма толық орындалмаған — барлық қадамды тексер.",
    "Формуланы немесе ұяшық адресін тексеріп, қайта жібер.", "Файл ашылмады — қайта жүктеп көр.",
    "Өз сөзіңмен, мысал келтіріп түсіндір.",
    "Молодец! Выполнено верно.", "Задание выполнено не полностью — проверь все шаги.",
    "Проверь формулу или адреса ячеек и отправь снова.", "Файл не открывается — загрузи ещё раз.",
    "Объясни своими словами и приведи пример.",
]


def comment_bank(tid):
    """Мұғалімнің дайын пікірлері. Бос болса, әдепкі пікірлер (қазақша және орысша) қосылады."""
    rows = q("SELECT * FROM comment_bank WHERE teacher_id=? ORDER BY id", (tid,))
    if not rows:
        for text in DEFAULT_COMMENTS:
            db().execute("INSERT INTO comment_bank(teacher_id,text) VALUES(?,?)", (tid, text))
        db().commit()
        rows = q("SELECT * FROM comment_bank WHERE teacher_id=? ORDER BY id", (tid,))
    return rows


@app.post("/teacher/comments/add")
@login_required("teacher")
def comment_add():
    text = str((request.get_json(force=True) or {}).get("text", "")).strip()[:300]
    if not text:
        return jsonify({"error": "Пікір бос"}), 400
    dup = q("SELECT id FROM comment_bank WHERE teacher_id=? AND text=?", (g.user["id"], text), one=True)
    if dup:
        return jsonify({"id": dup["id"], "text": text, "dup": True})
    cur = db().execute("INSERT INTO comment_bank(teacher_id,text) VALUES(?,?)", (g.user["id"], text))
    db().commit()
    return jsonify({"id": cur.lastrowid, "text": text})


@app.post("/teacher/comments/<int:cid>/delete")
@login_required("teacher")
def comment_delete(cid):
    db().execute("DELETE FROM comment_bank WHERE id=? AND teacher_id=?", (cid, g.user["id"]))
    db().commit()
    return jsonify({"ok": True})


@app.route("/teacher/review", methods=["GET", "POST"])
@login_required("teacher")
def review():
    if request.method == "POST":
        sid = int(request.form["sid"])
        s = q("""SELECT s.*, t.points, t.prompt, t.data FROM submissions s JOIN tasks t ON t.id=s.task_id
                 JOIN users u ON u.id=s.user_id JOIN classes c ON c.id=u.class_id
                 WHERE s.id=? AND c.teacher_id=?""", (sid, g.user["id"]), one=True) or abort(404)
        crit = json.loads(s["data"] or "{}").get("criteria") or []
        rubric_json = ""
        if "final" in request.form:  # автоматты бағаны мұғалім түзетеді: енгізілген балл сол күйі сақталады
            try:
                fin = float(request.form["final"].replace(",", "."))
            except ValueError:
                fin = 0.0
            fin = round(max(0.0, min(fin, float(s["points"]))), 2)
            fb = request.form.get("feedback", "").strip()
            old_fb = q("SELECT feedback FROM submissions WHERE id=?", (sid,), one=True)["feedback"]
            db().execute("UPDATE submissions SET score=?, status='graded', feedback=?, rubric_scores='', auto=0, updated=? WHERE id=?",
                         (fin, fb or old_fb, now(), sid))
            db().commit()
            flash("Бағаланды ✓", "ok")
            return redirect(url_for("review", c=request.form.get("c") or None))
        if crit and "crit0" in request.form:  # рубрика бойынша: әр критерийге балл, қосындысын сервер өзі есептейді
            got = []
            for i, c in enumerate(crit):
                try:
                    v = float(request.form.get(f"crit{i}", "0").replace(",", "."))
                except ValueError:
                    v = 0.0
                got.append(round(max(0.0, min(v, float(c["points"]))), 2))
            raw = sum(got)
            rubric_json = json.dumps(got)
        else:
            raw = float(request.form["score"].replace(",", "."))
        pct = s["late_pct"] if s["late_pct"] is not None else 100
        score = round(max(0.0, min(raw, s["points"])) * pct / 100, 2)  # кеш тапсырса, ұпай азаяды
        db().execute("UPDATE submissions SET score=?, status='graded', feedback=?, rubric_scores=?, auto=0, updated=? WHERE id=?",
                     (score, request.form.get("feedback", "").strip(), rubric_json, now(), sid))
        if score > s["score"]:
            add_xp(s["user_id"], round((score - s["score"]) * XP_PER_POINT), f"Ашық жауап: {s['prompt'][:40]}")
        db().commit()
        flash("Бағаланды ✓", "ok")
        return redirect(url_for("review", c=request.form.get("c") or None))
    rows = q("""SELECT s.*, t.type ttype, t.prompt, t.points, t.data, u.name, c.id cid, c.name cname, l.title, l.grade
                FROM submissions s JOIN tasks t ON t.id=s.task_id JOIN lessons l ON l.id=t.lesson_id
                JOIN users u ON u.id=s.user_id JOIN classes c ON c.id=u.class_id
                WHERE s.status='pending' AND c.teacher_id=? ORDER BY c.grade, c.name, c.id, s.updated""", (g.user["id"],))
    rows = [dict(r, answer=json.loads(r["answer"]), data=json.loads(r["data"]),
                 hist=answer_history(r["user_id"], r["task_id"])) for r in rows]
    # Сыныптар бойынша топтау: әр сыныптың күтіп тұрған жұмыстары бөлек блокта
    classes = []
    for r in rows:
        if not classes or classes[-1]["id"] != r["cid"]:
            classes.append({"id": r["cid"], "name": r["cname"], "rows": []})
        classes[-1]["rows"].append(r)
    sel = request.args.get("c", type=int)
    shown = [c for c in classes if sel in (None, c["id"])]
    # Сайт өзі бағалаған жұмыстар (мұғалім қаласа түзетеді)
    arows = q("""SELECT s.*, t.prompt, t.points, u.name, c.id cid, c.name cname, l.title
                 FROM submissions s JOIN tasks t ON t.id=s.task_id JOIN lessons l ON l.id=t.lesson_id
                 JOIN users u ON u.id=s.user_id JOIN classes c ON c.id=u.class_id
                 WHERE s.auto=1 AND s.status='graded' AND c.teacher_id=? ORDER BY c.grade, c.name, c.id, s.updated DESC
                 LIMIT 300""", (g.user["id"],))
    agroups = []
    for r in arows:
        if sel not in (None, r["cid"]):
            continue
        if not agroups or agroups[-1]["id"] != r["cid"]:
            agroups.append({"id": r["cid"], "name": r["cname"], "rows": []})
        agroups[-1]["rows"].append(r)
    return render_template("review.html", rows=rows, classes=classes, shown=shown, sel=sel, agroups=agroups,
                           bank=comment_bank(g.user["id"]), ai_on=ai.enabled())


@app.post("/teacher/review/<int:sid>/suggest")
@login_required("teacher")
def review_suggest(sid):
    """Ашық жауапқа Gemini баға ұсынысы (мұғалім растайды). Интернет пен GEMINI_API_KEY керек."""
    if not ai.enabled():
        return jsonify({"error": "GEMINI_API_KEY орнатылмаған"}), 400
    s = q("""SELECT s.answer, t.prompt, t.points, t.data, t.type FROM submissions s JOIN tasks t ON t.id=s.task_id
             JOIN users u ON u.id=s.user_id JOIN classes c ON c.id=u.class_id
             WHERE s.id=? AND c.teacher_id=?""", (sid, g.user["id"]), one=True) or abort(404)
    answer = json.loads(s["answer"] or "null")
    if s["type"] != "open" or not isinstance(answer, str):
        return jsonify({"error": "Тек ашық жауапқа"}), 400
    d = json.loads(s["data"] or "{}")
    try:
        return jsonify(ai.suggest_grade(s["prompt"], d.get("criteria") or [], d.get("rubric") or "", answer, s["points"]))
    except Exception as e:  # noqa
        return jsonify({"error": f"AI қатесі: {str(e)[:150]}"}), 502


# ── Сабақ мазмұнын басқару ──
@app.route("/teacher/lessons")
@login_required("teacher")
def lessons_admin():
    grade = request.args.get("grade", 7, type=int)
    rows = q("""SELECT l.*, (SELECT COUNT(*) FROM tasks t WHERE t.lesson_id=l.id) nt
                FROM lessons l WHERE grade=? ORDER BY quarter, num, (kind='block'), id""", (grade,))
    return render_template("lessons_admin.html", rows=rows, grade=grade)


def validate_tasks(tasks):
    clean = []
    for i, t in enumerate(tasks, 1):
        typ = t.get("type")
        if typ not in TASK_TYPES:
            raise ValueError(f"{i}-тапсырма: түрі белгісіз")
        prompt = str(t.get("prompt", "")).strip()
        if not prompt:
            raise ValueError(f"{i}-тапсырма: сұрақ мәтіні бос")
        d = t.get("data") or {}
        pts = int(t.get("points") or 1)
        if typ in ("quiz", "multi"):
            opts = [str(o).strip() for o in d.get("options", []) if str(o).strip()]
            if len(opts) < 2:
                raise ValueError(f"{i}-тапсырма: кемінде 2 жауап нұсқасы керек")
            d["options"] = opts
            if typ == "quiz":
                a = int(d.get("answer", -1))
                if not 0 <= a < len(opts):
                    raise ValueError(f"{i}-тапсырма: дұрыс жауапты белгілеңіз")
                d["answer"] = a
            else:
                a = sorted({int(x) for x in d.get("answer", []) if 0 <= int(x) < len(opts)})
                if not a:
                    raise ValueError(f"{i}-тапсырма: кемінде бір дұрыс жауапты белгілеңіз")
                d["answer"] = a
        if typ in ("open", "file"):
            crit = []
            for c in d.get("criteria") or []:
                text = str(c.get("text", "")).strip()
                try:
                    p = round(float(c.get("points", 0)), 2)
                except (TypeError, ValueError):
                    p = 0
                if text and p > 0:
                    crit.append({"text": text, "points": int(p) if p == int(p) else p})
            if crit:
                d["criteria"] = crit
                pts = sum(c["points"] for c in crit)  # тапсырма балы — критерийлер қосындысы
            else:
                d.pop("criteria", None)
        if typ == "short":
            ans = d.get("answer")
            ans = ans if isinstance(ans, list) else [x.strip() for x in str(ans or "").split("|")]
            ans = [x for x in ans if str(x).strip()]
            if not ans:
                raise ValueError(f"{i}-тапсырма: дұрыс жауап жазылмаған")
            d["answer"] = ans
        if typ == "code":
            tests = [x for x in d.get("tests", []) if str(x.get("output", "")).strip()]
            if not tests:
                raise ValueError(f"{i}-тапсырма: кемінде бір тест (күтілетін нәтиже) керек")
            d["tests"] = tests
        clean.append({"type": typ, "prompt": prompt, "data": d, "points": max(1, pts)})
    return clean


@app.route("/teacher/lesson/<int:lid>/edit", methods=["GET", "POST"])
@login_required("teacher")
def lesson_edit(lid):
    L = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) or abort(404)
    if request.args.get("lang") == "ru":
        return lesson_edit_ru(L)
    if request.method == "POST":
        try:
            tasks = validate_tasks(json.loads(request.form.get("tasks_json") or "[]"))
        except (ValueError, json.JSONDecodeError) as e:
            flash(f"Сақталмады: {e}", "error")
            return render_template("lesson_edit.html", L=dict(L, theory=request.form.get("theory", "")),
                                   tasks=_safe_json(request.form.get("tasks_json")), ai_on=ai.enabled())
        db().execute("UPDATE lessons SET title=?, theory=?, updated=? WHERE id=?",
                     (request.form["title"].strip() or L["title"], request.form.get("theory", ""), now(), lid))
        old = {r["ord"]: r for r in q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))}
        # Бар тапсырмаларды жаңарту (оқушы жауаптары сақталуы үшін), артығын өшіру
        for k, t in enumerate(tasks):
            if t["type"] == "file" and k in old and "auto" not in t["data"]:  # автотексеру ережелерін жоғалтпау
                oa = json.loads(old[k]["data"] or "{}").get("auto")
                if oa:
                    t["data"]["auto"] = oa
            data = json.dumps(t["data"], ensure_ascii=False)
            if k in old:
                db().execute("UPDATE tasks SET type=?, prompt=?, data=?, points=? WHERE id=?",
                             (t["type"], t["prompt"], data, t["points"], old[k]["id"]))
            else:
                db().execute("INSERT INTO tasks(lesson_id,ord,type,prompt,data,points) VALUES(?,?,?,?,?,?)",
                             (lid, k, t["type"], t["prompt"], data, t["points"]))
        for k, r in old.items():
            if k >= len(tasks):
                db().execute("DELETE FROM submissions WHERE task_id=?", (r["id"],))
                db().execute("DELETE FROM tasks WHERE id=?", (r["id"],))
        db().commit()
        flash("Сабақ сақталды ✓", "ok")
        for r in q("SELECT data, data_ru FROM tasks WHERE lesson_id=? AND data_ru != ''", (lid,)):
            kk_n = len(json.loads(r["data"] or "{}").get("criteria") or [])
            ru_n = len(json.loads(r["data_ru"] or "{}").get("criteria") or [])
            if kk_n and ru_n and kk_n != ru_n:
                flash("Ескерту: рубрика критерийлерінің саны өзгерді. «Орысша» қойындысында орысша критерийлерді жаңартыңыз, әйтпесе орыс тобы қазақша критерийлерді көреді.", "error")
                break
        return redirect(url_for("lesson_edit", lid=lid))
    tasks = [{"type": t["type"], "prompt": t["prompt"], "data": json.loads(t["data"]), "points": t["points"]}
             for t in q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))]
    return render_template("lesson_edit.html", L=L, tasks=tasks, ai_on=ai.enabled())


def lesson_edit_ru(L):
    """Сабақтың орысша нұсқасын өңдеу. Тапсырмалардың саны, түрі және балы қазақша нұсқамен бірдей болады."""
    lid = L["id"]
    rows = q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))
    if request.method == "POST":
        try:
            tasks = validate_tasks(json.loads(request.form.get("tasks_json") or "[]"))
            if [t["type"] for t in tasks] != [r["type"] for r in rows]:
                raise ValueError("орысша нұсқада тапсырмалардың саны мен түрі қазақша нұсқамен бірдей болуы керек")
            for t, r in zip(tasks, rows):
                kk_n = len(json.loads(r["data"] or "{}").get("criteria") or [])
                if kk_n and len(t["data"].get("criteria") or []) != kk_n:
                    raise ValueError("орысша нұсқада рубрика критерийлерінің саны қазақшамен бірдей болуы керек")
        except (ValueError, json.JSONDecodeError) as e:
            flash(f"Сақталмады: {e}", "error")
            return render_template("lesson_edit.html", L=dict(L, title=request.form.get("title", ""), theory=request.form.get("theory", "")),
                                   tasks=_safe_json(request.form.get("tasks_json")), ai_on=False, lang="ru")
        db().execute("UPDATE lessons SET title_ru=?, theory_ru=?, updated=? WHERE id=?",
                     (request.form.get("title", "").strip(), request.form.get("theory", ""), now(), lid))
        for t, r in zip(tasks, rows):
            db().execute("UPDATE tasks SET prompt_ru=?, data_ru=? WHERE id=?",
                         (t["prompt"], json.dumps(t["data"], ensure_ascii=False), r["id"]))
        db().commit()
        flash("Орысша нұсқа сақталды ✓", "ok")
        return redirect(url_for("lesson_edit", lid=lid, lang="ru"))
    tasks = []
    for r in rows:
        d = json.loads(r["data_ru"] or r["data"])
        kk_crit = json.loads(r["data"] or "{}").get("criteria")
        if kk_crit and not d.get("criteria"):
            d["criteria"] = kk_crit  # аудару үшін қазақша критерийлерден бастаймыз
        tasks.append({"type": r["type"], "prompt": r["prompt_ru"] or r["prompt"], "data": d, "points": r["points"]})
    return render_template("lesson_edit.html", L=dict(L, title=L["title_ru"] or L["title"], theory=L["theory_ru"]),
                           tasks=tasks, ai_on=False, lang="ru")


def _safe_json(s):
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


@app.post("/teacher/lesson/<int:lid>/ai")
@login_required("teacher")
def lesson_ai(lid):
    L = q("SELECT * FROM lessons WHERE id=?", (lid,), one=True) or abort(404)
    body = request.get_json(force=True)
    info, src, what = dict(L), body.get("source", ""), body.get("what", "all")
    if (L["kind"] or "lesson") == "block":  # блок: ата сабақтың тақырыбы мен теориясына сүйеніп, тек тапсырмалар
        P = q("SELECT * FROM lessons WHERE id=?", (L["parent_id"],), one=True)
        if P:
            info.update(title=P["title"], section=P["section"], objectives=P["objectives"])
            src = src or P["theory"]
        what = "tasks"
    try:
        out = ai.generate_lesson(info, src, what)
        return jsonify(out)
    except Exception as e:  # noqa
        return jsonify({"error": str(e)}), 400


@app.post("/teacher/preview")
@login_required("teacher")
def preview_md():
    return jsonify({"html": str(md_filter(request.get_json(force=True).get("md", "")))})


@app.post("/teacher/test-code")
@login_required("teacher")
def teacher_test_code():
    d = request.get_json(force=True)
    return jsonify(check_code(d.get("code", ""), d.get("tests", [])))


@app.route("/teacher/books", methods=["POST"])
@login_required("teacher")
def book_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        flash("PDF файл таңдаңыз", "error")
        return redirect(url_for("books"))
    fn = f"{secrets.token_hex(6)}.pdf"
    f.save(os.path.join(BOOKS_DIR, fn))
    db().execute("INSERT INTO books(grade,title,lang,filename) VALUES(?,?,?,?)",
                 (int(request.form["grade"]), request.form["title"].strip() or f.filename,
                  request.form.get("lang", "kk"), fn))
    db().commit()
    flash("Оқулық жүктелді ✓", "ok")
    return redirect(url_for("books"))


@app.post("/teacher/books/<int:bid>/delete")
@login_required("teacher")
def book_delete(bid):
    b = q("SELECT * FROM books WHERE id=?", (bid,), one=True) or abort(404)
    try:
        os.remove(os.path.join(BOOKS_DIR, b["filename"]))
    except OSError:
        pass
    db().execute("DELETE FROM books WHERE id=?", (bid,))
    db().commit()
    return redirect(url_for("books"))


@app.errorhandler(403)
def e403(_e):
    return render_template("error.html", msg=tr("Бұл бетке кіруге рұқсат жоқ")), 403


@app.errorhandler(404)
def e404(_e):
    return render_template("error.html", msg=tr("Бет табылмады")), 404


init_db()
import planner  # «Сабаққа дайындық» модулі (мұғалімге)
planner.register(app, DB_PATH, db, login_required)

if __name__ == "__main__":
    import socket

    def free(p):
        """Порт бос па және оны ашуға рұқсат бар ма (80-ші порт кейде бос емес не жабық болады)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
            try:
                sk.bind(("0.0.0.0", p))
                return True
            except OSError:
                return False

    # 80-ші порт: мекенжай портсыз жазылады (http://infolab.local); болмаса 8080
    port = int(os.environ["PORT"]) if os.environ.get("PORT") else (80 if free(80) else 8080)
    url = "http://localhost" + ("" if port == 80 else f":{port}")
    print(f"\n  Платформа іске қосылды: {url}\n  Мұғалім коды: {TEACHER_CODE}\n")
    if sys.platform == "darwin":  # сайт қосулы тұрғанда Mac бос тұрып ұйықтап қалмасын
        import subprocess
        try:
            subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        except OSError:
            pass
    app.run(host="0.0.0.0", port=port, threaded=True, debug=os.environ.get("DEBUG") == "1")
