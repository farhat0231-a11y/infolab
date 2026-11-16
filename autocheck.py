"""Практикалық жұмыс файлдарын (.xlsx, .docx) ереже бойынша автоматты тексеру.

Тапсырманың data["auto"] өрісінде критерийлер тізімі тұрады:
    [{"points": 1, "checks": [{"t": "filled", "range": "A1:C5", "min": 12}, ...]}, ...]
Критерийдегі барлық тексеру өтсе — сол критерийдің балы беріледі.
Файлды оқу мүмкін болмаса (.xls, .ods, бүлінген файл) None қайтады — жұмыс мұғалімге жіберіледі.
Интернет қажет емес.
"""
import datetime
import re
import zipfile

try:
    import openpyxl
except ImportError:  # орнатылмаған болса — автотексеру өшірулі, барлығы мұғалімге түседі
    openpyxl = None

FUNC_ALIASES = {"СУММ": "SUM", "СРЗНАЧ": "AVERAGE", "ЕСЛИ": "IF", "КОРЕНЬ": "SQRT", "МАКС": "MAX",
                "МИН": "MIN", "ИНДЕКС": "INDEX", "ПОИСКПОЗ": "MATCH"}


def _formula(v):
    if v is None:
        return None
    text = getattr(v, "text", v)  # ArrayFormula
    return text if isinstance(text, str) and text.startswith("=") else None


def _cells(ws, rng):
    if not rng:
        return [c for row in ws.iter_rows() for c in row]
    out = ws[rng]
    if not isinstance(out, tuple):
        return [out]
    if out and not isinstance(out[0], tuple):
        return list(out)
    return [c for row in out for c in row]


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _chart_xmls(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if re.match(r"xl/charts/chart\d+\.xml$", n):
                out.append(re.sub(r"<(/?)c:", r"<\1", z.read(n).decode("utf-8", "ignore")))
    return out


class XlsxBook:
    def __init__(self, path):
        self.wb = openpyxl.load_workbook(path)  # формулалар
        self.wv = openpyxl.load_workbook(path, data_only=True)  # Excel есептеген мәндер
        # Негізгі парақ — ең көп толтырылған парақ
        self.ws = max(self.wb.worksheets, key=lambda s: sum(1 for r in s.iter_rows() for c in r if not _empty(c.value)))
        self.wsv = self.wv[self.ws.title]
        self.charts = _chart_xmls(path)

    def filled_count(self):
        return sum(1 for c in _cells(self.ws, None) if not _empty(c.value))

    def cached(self, c):
        return self.wsv[c.coordinate].value

    # ── тексеру түрлері: әрқайсысы True/False қайтарады ──
    def c_valid(self, k):
        return self.filled_count() >= k.get("min", 1)

    def c_filled(self, k):
        return sum(1 for c in _cells(self.ws, k.get("range")) if not _empty(c.value)) >= k["min"]

    def c_numeric(self, k):
        return sum(1 for c in _cells(self.ws, k.get("range")) if _num(self.cached(c))) >= k["min"]

    def c_textlen(self, k):
        return sum(1 for c in _cells(self.ws, k.get("range"))
                   if isinstance(c.value, str) and len(c.value.strip()) >= k.get("chars", 3)) >= k["min"]

    def c_rows(self, k):  # бағанда бос емес ұяшық саны
        return sum(1 for c in self.ws[k["col"]] if not _empty(c.value)) >= k["min"]

    def c_formula(self, k):  # формула мәтіні regex-ке сәйкес келетін ұяшықтар саны
        rx = re.compile(k["re"], re.I)
        return sum(1 for c in _cells(self.ws, k.get("range")) if (f := _formula(c.value)) and rx.search(f)) >= k.get("min", 1)

    def c_func(self, k):
        name = FUNC_ALIASES.get(k["name"].upper(), k["name"].upper())
        rx = re.compile(r"\b" + re.escape(name) + r"\s*\(", re.I)
        return sum(1 for c in _cells(self.ws, k.get("range")) if (f := _formula(c.value)) and rx.search(f)) >= k.get("min", 1)

    def c_formula_value(self, k):  # формула бар және (есептелген болса) нәтижесі дұрыс
        rx = re.compile(k["re"], re.I)
        found = [c for c in _cells(self.ws, None) if (f := _formula(c.value)) and rx.search(f)]
        if not found:
            return False
        got = [self.cached(c) for c in found]
        if all(v is None for v in got):  # файл Excel-де есептелмей сақталған — формуланың болуы жеткілікті
            return True
        return any(_num(v) and abs(v - k["eq"]) <= k.get("tol", 0.01) for v in got)

    def c_value(self, k):
        v = self.wsv[k["ref"]].value
        eq = k["eq"] if isinstance(k["eq"], list) else [k["eq"]]
        return _num(v) and any(abs(v - e) <= k.get("tol", 0.0001) for e in eq)

    def c_date(self, k):
        return sum(1 for c in _cells(self.ws, k.get("range"))
                   if isinstance(self.cached(c), (datetime.datetime, datetime.date))) >= k.get("min", 1)

    def c_numfmt(self, k):
        rx = re.compile(k["re"], re.I)
        return sum(1 for c in _cells(self.ws, k.get("range")) if rx.search(c.number_format or "")) >= k.get("min", 1)

    def c_sorted(self, k):
        vals = [v for v in (self.cached(c) for c in _cells(self.ws, k["range"])) if _num(v)]
        if len(vals) < k.get("min", 3):
            return False
        return vals == sorted(vals, reverse=(k.get("order") == "desc"))

    @staticmethod
    def _fmt(c, what):
        if "bold" in what and c.font and c.font.b:
            return True
        if "fill" in what and c.fill and c.fill.fill_type and c.fill.fill_type != "none":
            return True
        if "border" in what and c.border and any(getattr(c.border, s) is not None and getattr(c.border, s).style
                                                 for s in ("left", "right", "top", "bottom")):
            return True
        return False

    def c_format(self, k):  # bold/fill/border — көрсетілген түрлердің кез келгені бар ұяшықтар саны
        what = k.get("what", ["bold", "fill", "border"])
        return sum(1 for c in _cells(self.ws, k.get("range")) if self._fmt(c, what)) >= k.get("min", 1)

    def c_no_merged(self, k):
        return not self.ws.merged_cells.ranges

    def c_no_empty_rows(self, k):  # көрсетілген ауқымда толық бос жол болмауы керек
        return all(any(not _empty(c.value) for c in row) for row in self.ws[k["range"]])

    def c_text_any(self, k):  # ұяшық мәтіні немесе ескертпе (примечание) regex-ке сәйкес келеді
        rx = re.compile(k["re"], re.I)
        for c in _cells(self.ws, None):
            if isinstance(c.value, str) and rx.search(c.value):
                return True
            if c.comment and rx.search(c.comment.text or ""):
                return True
        return False

    def c_autofilter(self, k):
        ws = self.ws
        if not ((ws.auto_filter and ws.auto_filter.ref) or any(getattr(t, "autoFilter", None) for t in ws.tables.values())):
            return False
        if k.get("applied"):  # сүзгі шын мәнінде қолданылған (бағанға шарт қойылған немесе жолдар жасырылған)
            return bool(ws.auto_filter.filterColumn) or any(d.hidden for d in ws.row_dimensions.values())
        return True

    def c_condfmt(self, k):
        ops, types = set(), set()
        for cf in self.ws.conditional_formatting:
            for r in cf.rules:
                types.add(r.type)
                if r.operator:
                    ops.add(r.operator)
        return bool(ops or types) and set(k.get("ops", [])) <= ops and set(k.get("types", [])) <= types

    def c_colwidth(self, k):
        return sum(1 for d in self.ws.column_dimensions.values() if d.width and getattr(d, "customWidth", True)) >= k.get("min", 2)

    def c_chart(self, k):  # диаграмма: түрі, тақырыптар саны, regex
        for x in self.charts:
            if k.get("type") and not re.search(r"<" + k["type"] + r"Chart\b", x):
                continue
            if len(re.findall(r"<title>", x)) < k.get("titles", 0):
                continue
            if any(not re.search(r, x) for r in k.get("re", [])):
                continue
            return True
        return False


class DocxBook:
    def __init__(self, path):
        with zipfile.ZipFile(path) as z:
            self.xml = z.read("word/document.xml").decode("utf-8", "ignore")

    def c_valid(self, k):
        return len(self.xml) > 500

    def c_table(self, k):
        for t in re.findall(r"<w:tbl>.*?</w:tbl>", self.xml, re.S):
            trs = re.findall(r"<w:tr[ >].*?</w:tr>", t, re.S)
            cols = max((len(re.findall(r"<w:tc[ >]", r)) for r in trs), default=0)
            texts = sum(1 for c in re.findall(r"<w:tc[ >].*?</w:tc>", t, re.S) if re.search(r"<w:t[ >][^<]", c))
            if len(trs) >= k.get("rows", 1) and cols >= k.get("cols", 1) and texts >= k.get("filled", 0):
                return True
        return False

    def c_xml(self, k):  # XML-де regex-тер бар (біріктіру, түс, туралау, шекара)
        return len(re.findall(k["re"], self.xml)) >= k.get("min", 1)


def open_book(path, ext):
    if openpyxl is None:
        return None
    try:
        if ext == "xlsx":
            return XlsxBook(path)
        if ext == "docx":
            return DocxBook(path)
    except Exception:  # бүлінген / парольді файл
        return None
    return None


def grade(path, ext, rules, labels=None):
    """rules — data["auto"]. Қайтарады: {"score", "max", "items":[{"label","points","got","ok"}]} немесе None."""
    if not rules:
        return None
    book = open_book(path, ext.lower())
    if book is None:
        return None
    items, score, total = [], 0.0, 0.0
    for i, rule in enumerate(rules):
        ok = True
        for k in rule.get("checks", []):
            fn = getattr(book, "c_" + k["t"], None)
            try:
                if fn is None or not fn(k):
                    ok = False
                    break
            except Exception:
                ok = False
                break
        pts = float(rule["points"])
        label = labels[i] if labels and i < len(labels) else rule.get("text", "")
        items.append({"label": label, "points": pts, "got": pts if ok else 0.0, "ok": ok})
        score += pts if ok else 0
        total += pts
    return {"score": round(score, 2), "max": round(total, 2), "items": items}
