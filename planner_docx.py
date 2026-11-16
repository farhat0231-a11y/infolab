"""ҚМЖ-ны .docx-ке шығару (python-docx): ресми кесте құрылымы, Times New Roman 12."""
import io
import json
import re

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

LABELS = {
    "kk": {"title": "Қысқа мерзімді жоспар", "section": "Бөлім", "teacher": "Педагогтің аты-жөні", "date": "Күні",
           "class": "Сынып", "present": "Қатысушылар саны", "absent": "Қатыспағандар саны", "topic": "Сабақтың тақырыбы",
           "obj": "Оқу бағдарламасына сәйкес оқу мақсаттары", "aim": "Сабақтың мақсаты",
           "h_stage": "Сабақтың кезеңі / уақыт", "h_t": "Педагогтің әрекеті", "h_s": "Оқушының әрекеті",
           "h_a": "Бағалау", "h_r": "Ресурстар", "min": "мин", "task": "InfoLab тапсырмасы"},
    "ru": {"title": "Краткосрочный план", "section": "Раздел", "teacher": "ФИО педагога", "date": "Дата",
           "class": "Класс", "present": "Количество присутствующих", "absent": "Количество отсутствующих",
           "topic": "Тема урока", "obj": "Цели обучения в соответствии с учебной программой", "aim": "Цель урока",
           "h_stage": "Этап урока / время", "h_t": "Деятельность педагога", "h_s": "Деятельность ученика",
           "h_a": "Оценивание", "h_r": "Ресурсы", "min": "мин", "task": "Задание InfoLab"},
}
PHASE = {"kk": {"start": "Сабақтың басы", "middle": "Сабақтың ортасы", "end": "Сабақтың соңы"},
         "ru": {"start": "Начало урока", "middle": "Середина урока", "end": "Конец урока"}}


def _font(run, bold=False, size=12):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold


def _cell(cell, text, bold=False, center=False):
    """Ұяшыққа мәтін жазу: жол үзілімдері абзацқа бөлінеді."""
    cell.text = ""
    lines = str(text or "").split("\n")
    for i, line in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _font(p.add_run(line), bold)


def _shade(cell, color="E8EEEC"):
    tcPr = cell._element.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), color)
    tcPr.append(sh)


def build(plan, lesson, cls, teacher_name, students, task_nums):
    """plan, lesson, cls — sqlite3.Row; task_nums — {task_id: реттік нөмір}. Қайтарады: .docx байттары."""
    lang = "ru" if cls["lang"] == "ru" else "kk"
    L = LABELS[lang]
    st = json.loads(plan["stages"]) if plan["stages"] else {"phases": []}
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(1.5))
    base = doc.styles["Normal"]
    base.font.name = "Times New Roman"
    base.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    base.font.size = Pt(12)

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(h.add_run(L["title"]), True, 14)

    topic = (lesson["title_ru"] if lang == "ru" and lesson["title_ru"] else lesson["title"])
    try:
        d = plan["date"]
        day = f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) == 10 else d
    except Exception:
        day = plan["date"] or ""
    rows = [("section", lesson["section"]), ("teacher", teacher_name), ("date", day), ("class", cls["name"]),
            ("present", max(students - (plan["absent"] or 0), 0)), ("absent", plan["absent"] or 0),
            ("topic", topic), ("obj", plan["objectives"]), ("aim", plan["aim"])]
    t1 = doc.add_table(rows=0, cols=2)
    t1.style = "Table Grid"
    for k, v in rows:
        r = t1.add_row().cells
        _cell(r[0], L[k], True)
        _shade(r[0])
        _cell(r[1], v)
    for r in t1.rows:
        r.cells[0].width, r.cells[1].width = Cm(8), Cm(18.7)

    doc.add_paragraph()
    t2 = doc.add_table(rows=1, cols=5)
    t2.style = "Table Grid"
    widths = [Cm(4.2), Cm(7), Cm(6.2), Cm(4.5), Cm(4.8)]
    for c, key, w in zip(t2.rows[0].cells, ("h_stage", "h_t", "h_s", "h_a", "h_r"), widths):
        _cell(c, L[key], True, True)
        _shade(c)
        c.width = w
    # Кесте тақырыбы келесі бетке де қайталанады
    trPr = t2.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)
    for ph in st["phases"]:
        steps = ph["steps"]
        if not steps:
            continue
        tot = sum(s["minutes"] for s in steps)
        row = t2.add_row().cells
        m = row[0].merge(row[4])
        _cell(m, f"{PHASE[lang][ph['key']]} ({tot} {L['min']})", True)
        _shade(m, "F4F7F5")
        for s in steps:
            c = t2.add_row().cells
            _cell(c[0], f"{s['title']}\n({s['minutes']} {L['min']})")
            _cell(c[1], s["teacher"])
            _cell(c[2], s["student"])
            _cell(c[3], s["assess"])
            res = s["resources"]
            links = [f"{L['task']} №{task_nums[i]}" for i in s.get("tasks", []) if i in task_nums]
            _cell(c[4], "\n".join(x for x in [res, ", ".join(links)] if x))
            for cell, w in zip(c, widths):
                cell.width = w
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def safe_name(s):
    return re.sub(r"[^\w\-. ]+", "", s, flags=re.U).strip().replace(" ", "_")[:60] or "plan"
