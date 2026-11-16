"""«Сабаққа дайындық» модулі: ҚМЖ (қысқа мерзімді жоспар), слайдтар, мұғалімнің сөзі.

app.py-ға тек тіркеу қосылған: planner.register(app, DB_PATH, db, login_required).
Бөлім тек мұғалімге ашық. Кестелер CREATE TABLE IF NOT EXISTS арқылы қосылады.
"""
import json
import sqlite3
from datetime import date

import io
import time
import zipfile
from urllib.parse import quote

import ai
from flask import Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

bp = Blueprint("planner", __name__, url_prefix="/teacher/planner")
LESSON_MIN = 40  # сабақтың ұзақтығы, минут

SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_plans(
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL,
  date TEXT DEFAULT '', absent INTEGER DEFAULT 0, objectives TEXT DEFAULT '', aim TEXT DEFAULT '',
  stages TEXT DEFAULT '', updated TEXT, UNIQUE(class_id, lesson_id));
CREATE TABLE IF NOT EXISTS slides(
  id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, ord INTEGER NOT NULL, phase TEXT DEFAULT '',
  md TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_slides_plan ON slides(plan_id);
CREATE TABLE IF NOT EXISTS book_files(
  book_id INTEGER PRIMARY KEY, uri TEXT NOT NULL, uploaded INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS present_state(
  plan_id INTEGER PRIMARY KEY, idx INTEGER DEFAULT 0, black INTEGER DEFAULT 0, started INTEGER DEFAULT 0, v INTEGER DEFAULT 0);
"""

PHASES = ("start", "middle", "end")
# ҚМЖ тілі сыныптың тіліне қарай таңдалады: құжат мәтіндері осы жерде (интерфейс емес)
DOC = {
    "kk": {
        "phase": {"start": "Сабақтың басы", "middle": "Сабақтың ортасы", "end": "Сабақтың соңы"},
        "steps": {
            "start": [("Ұйымдастыру және мотивация", 2, "Оқушылармен амандасады, сабақтың тақырыбы мен мақсатын таныстырады.",
                       "Сабаққа дайындалады, мақсатпен танысады.", "Бақылау", "Слайд"),
                      ("Үй тапсырмасын пысықтау", 5, "Өткен тақырып бойынша сұрақ қояды.",
                       "Сұрақтарға жауап береді.", "Ауызша кері байланыс", "Слайд, карточка")],
            "middle": [("Жаңа тақырыпты түсіндіру", 13, "Жаңа материалды мысалдармен түсіндіреді.",
                        "Тыңдайды, дәптерге жазады, сұрақ қояды.", "Сұрақ-жауап", "Слайд, оқулық"),
                       ("Практикалық жұмыс", 15, "Тапсырма береді, жұмысты бақылайды, қолдау көрсетеді.",
                        "Тапсырманы компьютерде орындайды.", "Дескриптор бойынша бағалау", "InfoLab тапсырмалары")],
            "end": [("Рефлексия", 5, "Сабақты қорытады, рефлексия ұйымдастырады.",
                     "Сабақтан не үйренгенін айтады.", "Өзін-өзі бағалау", "Рефлексия парағы")],
        },
    },
    "ru": {
        "phase": {"start": "Начало урока", "middle": "Середина урока", "end": "Конец урока"},
        "steps": {
            "start": [("Организационный момент и мотивация", 2, "Приветствует учащихся, объявляет тему и цель урока.",
                       "Готовятся к уроку, знакомятся с целью.", "Наблюдение", "Слайд"),
                      ("Проверка домашнего задания", 5, "Задаёт вопросы по пройденной теме.",
                       "Отвечают на вопросы.", "Устная обратная связь", "Слайд, карточки")],
            "middle": [("Объяснение новой темы", 13, "Объясняет новый материал на примерах.",
                        "Слушают, записывают в тетрадь, задают вопросы.", "Вопрос-ответ", "Слайд, учебник"),
                       ("Практическая работа", 15, "Выдаёт задание, наблюдает за работой, поддерживает.",
                        "Выполняют задание на компьютере.", "Оценивание по дескрипторам", "Задания InfoLab")],
            "end": [("Рефлексия", 5, "Подводит итоги урока, организует рефлексию.",
                     "Говорят, чему научились на уроке.", "Самооценивание", "Лист рефлексии")],
        },
    },
}

_state = {}


def register(app, db_path, db, login_required):
    """Blueprint тіркеу және кестелерді жасау (app.py-дан шақырылады)."""
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    _state.update(db=db, login_required=login_required)
    app.register_blueprint(bp)
    app.jinja_env.globals["planner_links"] = planner_links


def T(s):
    """Интерфейс мәтінін аудару (app.py-дағы tr)."""
    return current_app.jinja_env.globals["tr"](s)


def planner_links(lesson):
    """Сабақ бетіндегі мұғалімге арналған батырмалар үшін: сол сыныптағы (параллель) сыныптар мен жоспар күйі."""
    if not g.get("user") or g.user["role"] != "teacher":
        return []
    return _q("""SELECT c.id, c.name, (SELECT 1 FROM lesson_plans p WHERE p.class_id=c.id AND p.lesson_id=?) has_plan
                 FROM classes c WHERE c.teacher_id=? AND c.grade=? ORDER BY c.name""",
              (lesson["id"], g.user["id"], lesson["grade"]))


def _book_uri(grade, lang):
    """Сынып пен тілге сай оқулықты Gemini-ге жүктеу (file_uri 48 сағат жарамды: 40 сағатқа кэштейміз)."""
    import os
    books = _q("SELECT * FROM books WHERE grade=? ORDER BY (lang=?) DESC, id LIMIT 1", (grade, lang))
    if not books:
        return None
    b = books[0]
    row = _q("SELECT * FROM book_files WHERE book_id=?", (b["id"],), one=True)
    if row and time.time() - row["uploaded"] < 40 * 3600:
        return row["uri"]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "books", b["filename"])
    if not os.path.exists(path):
        return None
    uri = ai.upload_pdf(path)
    _db().execute("INSERT OR REPLACE INTO book_files(book_id,uri,uploaded) VALUES(?,?,?)", (b["id"], uri, int(time.time())))
    _db().commit()
    return uri


def _db():
    return _state["db"]()


def _q(sql, args=(), one=False):
    rows = _db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def teacher_only(fn):
    """Тек мұғалім: оқушыға 403."""
    def wrapper(*a, **kw):
        return _state["login_required"]("teacher")(fn)(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


def _class(cid):
    return _q("SELECT * FROM classes WHERE id=? AND teacher_id=?", (cid, g.user["id"]), one=True) or abort(404)


def _lesson(cls, lid):
    L = _q("SELECT * FROM lessons WHERE id=? AND grade=?", (lid, cls["grade"]), one=True)
    return L or abort(404)


def default_stages(lang):
    d = DOC[lang]
    return {"phases": [{"key": p, "steps": [
        {"title": t, "minutes": m, "teacher": a, "student": s, "assess": b, "resources": r, "tasks": []}
        for t, m, a, s, b, r in d["steps"][p]]} for p in PHASES]}


def clean_stages(raw):
    """Клиенттен келген кезеңдерді тексеру және тазалау."""
    out = []
    byk = {p.get("key"): p for p in (raw or {}).get("phases", []) if isinstance(p, dict)}
    for k in PHASES:
        steps = []
        for s in (byk.get(k) or {}).get("steps", [])[:30]:
            try:
                mins = max(0, min(int(float(s.get("minutes") or 0)), 240))
            except (TypeError, ValueError):
                mins = 0
            tasks = [int(x) for x in s.get("tasks", []) if str(x).isdigit()]
            steps.append({"title": str(s.get("title", ""))[:200], "minutes": mins, "tasks": tasks,
                          **{f: str(s.get(f, ""))[:4000] for f in ("teacher", "student", "assess", "resources")}})
        out.append({"key": k, "steps": steps})
    return {"phases": out}


def total_minutes(stages):
    return sum(s["minutes"] for p in stages["phases"] for s in p["steps"])


def _plan(cid, lid):
    return _q("SELECT * FROM lesson_plans WHERE class_id=? AND lesson_id=?", (cid, lid), one=True)


@bp.route("/")
@teacher_only
def index():
    classes = _q("""SELECT c.*, (SELECT COUNT(*) FROM lesson_plans p WHERE p.class_id=c.id) plans,
                    (SELECT COUNT(*) FROM users u WHERE u.class_id=c.id AND u.role='student') n
                    FROM classes c WHERE teacher_id=? ORDER BY grade, name""", (g.user["id"],))
    return render_template("planner/index.html", classes=classes)


@bp.route("/c/<int:cid>")
@teacher_only
def klass(cid):
    cls = _class(cid)
    quarter = request.args.get("q", type=int) or 1
    lessons = _q("""SELECT l.*, p.id plan_id, p.stages, p.updated plan_updated FROM lessons l
                    LEFT JOIN lesson_plans p ON p.lesson_id=l.id AND p.class_id=?
                    WHERE l.grade=? AND l.quarter=? AND l.kind!='block' ORDER BY l.num""",
                 (cid, cls["grade"], quarter))
    mins = {}
    for L in lessons:
        if L["stages"]:
            mins[L["id"]] = total_minutes(json.loads(L["stages"]))
    return render_template("planner/klass.html", cls=cls, quarter=quarter, lessons=lessons, mins=mins,
                           total=LESSON_MIN)


@bp.route("/c/<int:cid>/l/<int:lid>")
@teacher_only
def edit(cid, lid):
    cls = _class(cid)
    L = _lesson(cls, lid)
    lang = "ru" if cls["lang"] == "ru" else "kk"
    plan = _plan(cid, lid)
    stages = json.loads(plan["stages"]) if plan and plan["stages"] else default_stages(lang)
    info = {
        "date": (plan["date"] if plan else "") or date.today().isoformat(),
        "absent": plan["absent"] if plan else 0,
        "objectives": plan["objectives"] if plan else (L["objectives"] or ""),
        "aim": plan["aim"] if plan else "",
    }
    students = _q("SELECT COUNT(*) FROM users WHERE class_id=? AND role='student'", (cid,), one=True)[0]
    tasks = _q("SELECT id, ord, type, prompt FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))
    task_list = [{"id": t["id"], "label": f"{t['ord'] + 1}. {t['type']}: " + (t["prompt"] or "").replace("\n", " ")[:60]}
                 for t in tasks]
    others = _q("SELECT id, name FROM classes WHERE teacher_id=? AND grade=? AND id!=? ORDER BY name",
                (g.user["id"], cls["grade"], cid))
    return render_template("planner/edit.html", cls=cls, L=L, plan=plan, info=info, stages=stages,
                           students=students, task_list=task_list, others=others, lang=lang, ai_on=ai.enabled(),
                           phase_names=DOC[lang]["phase"], total=LESSON_MIN)


@bp.post("/c/<int:cid>/l/<int:lid>/save")
@teacher_only
def save(cid, lid):
    cls = _class(cid)
    _lesson(cls, lid)
    d = request.get_json(silent=True) or {}
    stages = clean_stages(d.get("stages"))
    day = str(d.get("date", ""))[:10]
    try:
        absent = max(0, int(d.get("absent") or 0))
    except (TypeError, ValueError):
        absent = 0
    _db().execute("""INSERT INTO lesson_plans(class_id,lesson_id,date,absent,objectives,aim,stages,updated)
                     VALUES(?,?,?,?,?,?,?,datetime('now'))
                     ON CONFLICT(class_id,lesson_id) DO UPDATE SET date=excluded.date, absent=excluded.absent,
                     objectives=excluded.objectives, aim=excluded.aim, stages=excluded.stages, updated=excluded.updated""",
                  (cid, lid, day, absent, str(d.get("objectives", ""))[:2000], str(d.get("aim", ""))[:2000],
                   json.dumps(stages, ensure_ascii=False)))
    _db().commit()
    return jsonify(ok=True, total=total_minutes(stages))


@bp.post("/c/<int:cid>/l/<int:lid>/copy")
@teacher_only
def copy(cid, lid):
    """Жоспарды (слайдтарымен) сол сыныптағы басқа параллельге көшіру."""
    cls = _class(cid)
    _lesson(cls, lid)
    to = _class(request.form.get("to", type=int) or 0)
    if to["grade"] != cls["grade"] or to["id"] == cid:
        abort(400)
    src = _plan(cid, lid) or abort(404)
    d = _db()
    d.execute("""INSERT INTO lesson_plans(class_id,lesson_id,date,absent,objectives,aim,stages,updated)
                 VALUES(?,?,?,?,?,?,?,datetime('now'))
                 ON CONFLICT(class_id,lesson_id) DO UPDATE SET objectives=excluded.objectives, aim=excluded.aim,
                 stages=excluded.stages, updated=excluded.updated""",
              (to["id"], lid, "", 0, src["objectives"], src["aim"], src["stages"]))
    new = _plan(to["id"], lid)
    d.execute("DELETE FROM slides WHERE plan_id=?", (new["id"],))
    d.execute("INSERT INTO slides(plan_id,ord,phase,md,notes) SELECT ?,ord,phase,md,notes FROM slides WHERE plan_id=?",
              (new["id"], src["id"]))
    d.commit()
    flash(T("Жоспар көшірілді") + f": {to['name']}", "ok")
    return redirect(url_for("planner.edit", cid=to["id"], lid=lid))


def _docx_for(cls, L, plan):
    from planner_docx import build
    n = _q("SELECT COUNT(*) FROM users WHERE class_id=? AND role='student'", (cls["id"],), one=True)[0]
    nums = {t["id"]: t["ord"] + 1 for t in _q("SELECT id, ord FROM tasks WHERE lesson_id=?", (L["id"],))}
    return build(plan, L, cls, g.user["name"], n, nums)


def _download(data, name, mime):
    return Response(data, mimetype=mime, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)})


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@bp.route("/c/<int:cid>/l/<int:lid>/export.docx")
@teacher_only
def export_docx(cid, lid):
    from planner_docx import safe_name
    cls = _class(cid)
    L = _lesson(cls, lid)
    plan = _plan(cid, lid) or abort(404)
    return _download(_docx_for(cls, L, plan), f"KMZh_{cls['name']}_{safe_name(L['title'])}.docx", DOCX)


@bp.route("/c/<int:cid>/q/<int:quarter>.zip")
@teacher_only
def export_zip(cid, quarter):
    """Сыныптың бір тоқсандағы барлық ҚМЖ-сы бір ZIP файлда."""
    from planner_docx import safe_name
    cls = _class(cid)
    rows = _q("""SELECT l.* FROM lessons l JOIN lesson_plans p ON p.lesson_id=l.id AND p.class_id=?
                 WHERE l.grade=? AND l.quarter=? AND l.kind!='block' ORDER BY l.num""", (cid, cls["grade"], quarter))
    if not rows:
        flash(T("Бұл тоқсанда дайын ҚМЖ жоқ"), "error")
        return redirect(url_for("planner.klass", cid=cid, q=quarter))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, L in enumerate(rows, 1):
            z.writestr(f"{i:02d}_{safe_name(L['title'])}.docx", _docx_for(cls, L, _plan(cid, L["id"])))
    return _download(buf.getvalue(), f"KMZh_{cls['name']}_{quarter}.zip", "application/zip")


@bp.post("/c/<int:cid>/l/<int:lid>/delete")
@teacher_only
def remove(cid, lid):
    cls = _class(cid)
    _lesson(cls, lid)
    p = _plan(cid, lid)
    if p:
        _db().execute("DELETE FROM slides WHERE plan_id=?", (p["id"],))
        _db().execute("DELETE FROM lesson_plans WHERE id=?", (p["id"],))
        _db().commit()
    flash(T("Жоспар өшірілді"), "ok")
    return redirect(url_for("planner.klass", cid=cid, q=_lesson(cls, lid)["quarter"]))


# ───────────────────────── Слайдтар ─────────────────────────
def _plan_or_create(cls, L):
    """Слайд қосу үшін жоспар жолы қажет: жоқ болса, әдепкі кезеңдермен жасаймыз."""
    p = _plan(cls["id"], L["id"])
    if p:
        return p
    lang = "ru" if cls["lang"] == "ru" else "kk"
    _db().execute("INSERT INTO lesson_plans(class_id,lesson_id,date,objectives,stages,updated) VALUES(?,?,?,?,?,datetime('now'))",
                  (cls["id"], L["id"], date.today().isoformat(), L["objectives"] or "",
                   json.dumps(default_stages(lang), ensure_ascii=False)))
    _db().commit()
    return _plan(cls["id"], L["id"])


def _slides(plan_id):
    return [dict(phase=r["phase"], md=r["md"], notes=r["notes"])
            for r in _q("SELECT phase, md, notes FROM slides WHERE plan_id=? ORDER BY ord", (plan_id,))]


def _ctx(cid, lid):
    cls = _class(cid)
    L = _lesson(cls, lid)
    return cls, L, _plan_or_create(cls, L)


def _library(code):
    """Қолмен дайындалған слайд кітапханасы: content/slides/<код>.json ({kk: [...], ru: [...]})."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "slides", f"{code}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@bp.post("/c/<int:cid>/l/<int:lid>/slides/library")
@teacher_only
def slides_library(cid, lid):
    cls = _class(cid)
    L = _lesson(cls, lid)
    lib = _library(L["code"])
    sl = (lib or {}).get("ru" if cls["lang"] == "ru" else "kk")
    if not sl:
        abort(404)
    return jsonify(slides=[{"phase": s["phase"] if s.get("phase") in PHASES else "middle", "md": s["md"], "notes": s.get("notes", "")} for s in sl])


@bp.route("/c/<int:cid>/l/<int:lid>/slides")
@teacher_only
def slides_edit(cid, lid):
    cls, L, plan = _ctx(cid, lid)
    return render_template("planner/slides.html", cls=cls, L=L, plan=plan, slides=_slides(plan["id"]), ai_on=ai.enabled(),
                           has_lib=bool((_library(L["code"]) or {}).get("ru" if cls["lang"] == "ru" else "kk")),
                           phase_names=DOC["ru" if cls["lang"] == "ru" else "kk"]["phase"])


@bp.post("/c/<int:cid>/l/<int:lid>/slides/save")
@teacher_only
def slides_save(cid, lid):
    cls, L, plan = _ctx(cid, lid)
    items = (request.get_json(silent=True) or {}).get("slides", [])[:200]
    d = _db()
    d.execute("DELETE FROM slides WHERE plan_id=?", (plan["id"],))
    for i, s in enumerate(items):
        ph = s.get("phase") if s.get("phase") in PHASES else "middle"
        d.execute("INSERT INTO slides(plan_id,ord,phase,md,notes) VALUES(?,?,?,?,?)",
                  (plan["id"], i, ph, str(s.get("md", ""))[:20000], str(s.get("notes", ""))[:20000]))
    d.execute("UPDATE lesson_plans SET updated=datetime('now') WHERE id=?", (plan["id"],))
    d.commit()
    return jsonify(ok=True, n=len(items))


@bp.post("/preview")
@teacher_only
def preview():
    import planner_slides as ps
    return jsonify(html=ps.render((request.get_json(silent=True) or {}).get("md", "")))


@bp.post("/c/<int:cid>/l/<int:lid>/slides/from-theory")
@teacher_only
def slides_from_theory(cid, lid):
    import planner_slides as ps
    cls, L, plan = _ctx(cid, lid)
    ru = cls["lang"] == "ru"
    title = (L["title_ru"] if ru and L["title_ru"] else L["title"])
    theory = (L["theory_ru"] if ru and L["theory_ru"] else L["theory"]) or ""
    return jsonify(slides=ps.from_theory(title, plan["objectives"] or L["objectives"], theory, "ru" if ru else "kk"))


def _phase_ends(stages):
    """Әр кезеңнің сабақ басынан есептегендегі аяқталу минуты (таймер үшін)."""
    t, out = 0, {}
    for ph in stages["phases"]:
        t += sum(s["minutes"] for s in ph["steps"])
        out[ph["key"]] = t
    return out


def _present_data(cid, lid):
    import planner_slides as ps
    cls, L, plan = _ctx(cid, lid)
    stages = json.loads(plan["stages"]) if plan["stages"] else default_stages("kk")
    sl = _slides(plan["id"]) or [{"phase": "start", "md": "# " + L["title"], "notes": ""}]
    lang = "ru" if cls["lang"] == "ru" else "kk"
    return cls, L, plan, {
        "plan": plan["id"], "ends": _phase_ends(stages), "total": LESSON_MIN, "lang": lang,
        "phaseNames": DOC[lang]["phase"],
        "slides": [{"html": ps.render(s["md"]), "notes": s["notes"], "phase": s["phase"]} for s in sl],
        "urls": {"state": url_for("planner.state", cid=cid, lid=lid), "open": url_for("planner.open_tasks", cid=cid, lid=lid),
                 "screen": url_for("planner.present", cid=cid, lid=lid),
                 "teacher": url_for("planner.present_teacher", cid=cid, lid=lid),
                 "back": url_for("planner.slides_edit", cid=cid, lid=lid)},
        "opened": bool(_q("SELECT 1 FROM class_lessons WHERE class_id=? AND lesson_id=?", (cid, lid), one=True)),
    }


@bp.route("/c/<int:cid>/l/<int:lid>/present")
@teacher_only
def present(cid, lid):
    cls, L, plan, data = _present_data(cid, lid)
    return render_template("planner/present.html", L=L, data=data, mode="screen")


@bp.route("/c/<int:cid>/l/<int:lid>/present/teacher")
@teacher_only
def present_teacher(cid, lid):
    cls, L, plan, data = _present_data(cid, lid)
    return render_template("planner/present.html", L=L, data=data, mode="teacher", cls=cls)


@bp.route("/c/<int:cid>/l/<int:lid>/print")
@teacher_only
def print_slides(cid, lid):
    cls, L, plan, data = _present_data(cid, lid)
    return render_template("planner/print.html", L=L, slides=data["slides"], cls=cls)


@bp.route("/c/<int:cid>/l/<int:lid>/state", methods=["GET", "POST"])
@teacher_only
def state(cid, lid):
    """Көрсету күйі (слайд нөмірі, қара экран, таймер): проектор мен мұғалім терезесі осы арқылы үйлеседі."""
    cls, L, plan = _ctx(cid, lid)
    pid = plan["id"]
    _db().execute("INSERT OR IGNORE INTO present_state(plan_id) VALUES(?)", (pid,))
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        n = _q("SELECT COUNT(*) FROM slides WHERE plan_id=?", (pid,), one=True)[0] or 1
        row = _q("SELECT * FROM present_state WHERE plan_id=?", (pid,), one=True)
        idx = max(0, min(int(d.get("i", row["idx"])), n - 1))
        black = int(bool(d.get("black", row["black"])))
        started = row["started"]
        if d.get("timer") == "start" and not started:
            started = int(time.time() * 1000)
        elif d.get("timer") == "reset":
            started = 0
        _db().execute("UPDATE present_state SET idx=?, black=?, started=?, v=v+1 WHERE plan_id=?", (idx, black, started, pid))
        _db().commit()
    r = _q("SELECT * FROM present_state WHERE plan_id=?", (pid,), one=True)
    _db().commit()
    return jsonify(i=r["idx"], black=r["black"], started=r["started"], v=r["v"], now=int(time.time() * 1000))


@bp.post("/c/<int:cid>/l/<int:lid>/open")
@teacher_only
def open_tasks(cid, lid):
    """Тапсырмаларды сыныпқа ашу (class_lessons): бұрын ашылған болса, өзгермейді."""
    cls = _class(cid)
    _lesson(cls, lid)
    _db().execute("INSERT OR IGNORE INTO class_lessons(class_id,lesson_id,opened) VALUES(?,?,datetime('now'))", (cid, lid))
    _db().commit()
    return jsonify(ok=True)


@bp.post("/c/<int:cid>/l/<int:lid>/ai")
@teacher_only
def ai_generate(cid, lid):
    """AI арқылы ҚМЖ + слайд + сөз жасау. Нәтиже қайтарылады, редакторда түзетіп сақтайсыз."""
    import planner_ai
    if not ai.enabled():
        return jsonify(error=T("AI қосылмаған: GEMINI_API_KEY орнатылмаған")), 400
    cls = _class(cid)
    L = _lesson(cls, lid)
    ru = cls["lang"] == "ru"
    plan = _plan(cid, lid)
    theory = (L["theory_ru"] if ru and L["theory_ru"] else L["theory"]) or ""
    tasks = [{"id": t["id"], "type": t["type"], "prompt": (t["prompt_ru"] if ru and t["prompt_ru"] else t["prompt"]) or ""}
             for t in _q("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (lid,))]
    info = dict(L)
    if ru and L["title_ru"]:
        info["title"] = L["title_ru"]
    uri = None
    if (request.get_json(silent=True) or {}).get("book", True):
        try:
            uri = _book_uri(cls["grade"], "ru" if ru else "kk")
        except Exception:  # noqa — оқулықсыз да жалғастырамыз
            uri = None
    try:
        out = planner_ai.generate(info, (plan["objectives"] if plan else "") or L["objectives"], "ru" if ru else "kk",
                                  theory, tasks, LESSON_MIN, clean_stages, file_uri=uri)
        out["book"] = bool(uri)
    except Exception as e:  # noqa — желі жоқ, квота, JSON қатесі
        return jsonify(error=str(e)[:300]), 400
    return jsonify(out)


@bp.post("/c/<int:cid>/l/<int:lid>/slides/improve")
@teacher_only
def slide_improve(cid, lid):
    """Бір слайдты нұсқаулық бойынша AI-мен жақсарту (толығырақ, мысал қос, қарапайым, қысқарт, еркін мәтін)."""
    import planner_ai
    if not ai.enabled():
        return jsonify(error=T("AI қосылмаған: GEMINI_API_KEY орнатылмаған")), 400
    cls = _class(cid)
    L = _lesson(cls, lid)
    d = request.get_json(silent=True) or {}
    instr = planner_ai.IMPROVE.get(d.get("preset")) or str(d.get("instruction", ""))[:500]
    if not instr.strip():
        return jsonify(error=T("Нұсқаулық жазыңыз")), 400
    ru = cls["lang"] == "ru"
    info = dict(L)
    if ru and L["title_ru"]:
        info["title"] = L["title_ru"]
    try:
        return jsonify(planner_ai.improve(info, "ru" if ru else "kk", str(d.get("md", ""))[:6000], str(d.get("notes", ""))[:4000], instr))
    except Exception as e:  # noqa
        return jsonify(error=str(e)[:300]), 400
