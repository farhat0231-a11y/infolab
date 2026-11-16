"""Gemini арқылы сабақ мазмұнын жасау (міндетті емес).

GEMINI_API_KEY орнатылса, мұғалім сабақ редакторында «AI арқылы жасау» батырмасын көреді.
Кілтті тегін алу: https://aistudio.google.com/apikey
"""
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

try:  # macOS-тағы python.org Python-да сертификаттар жоқ болуы мүмкін — certifi жинағын қолданамыз
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
FALLBACK = "gemini-3.5-flash-lite"  # негізгі модель бос емес болса

SCHEMA_HINT = """
JSON форматы (тек JSON қайтар, басқа мәтінсіз):
{
  "theory": "Markdown форматындағы теория: ## тақырыпшалар, тізімдер, кестелер, ```python код мысалдары```",
  "tasks": [
    {"type":"quiz","prompt":"сұрақ","points":1,"data":{"options":["A","B","C","D"],"answer":0,"explain":"неге дұрыс"}},
    {"type":"multi","prompt":"сұрақ (бірнеше дұрыс)","points":2,"data":{"options":["A","B","C","D"],"answer":[0,2],"explain":"..."}},
    {"type":"short","prompt":"есеп, жауабы сан не бір сөз","points":1,"data":{"answer":["24","24 бит"],"explain":"шешуі"}},
    {"type":"code","prompt":"Python есебі: не енгізіледі, не шығару керек","points":3,
     "data":{"starter":"# кодыңызды жазыңыз\\n","tests":[{"input":"5","output":"25"},{"input":"3","output":"9","hidden":true}]}},
    {"type":"open","prompt":"ойлануға арналған ашық сұрақ","points":2,
     "data":{"criteria":[{"text":"нені дұрыс айтса","points":1},{"text":"мысал келтірсе","points":1}]}},
    {"type":"file","prompt":"**Практикалық жұмыс.** Не істеу керек: 1) ... 2) ... 3) ... Файлды сақтап, жүктеңіз.","points":3,
     "data":{"accept":".xlsx,.xls","criteria":[{"text":"1-қадам орындалған","points":1},{"text":"2-қадам орындалған","points":1},{"text":"3-қадам орындалған","points":1}]}}
  ]
}
"""


def rubric_to_criteria(rubric: str, total) -> list:
    """«1 балл — ...; 1 балл — ...» түріндегі мәтінді критерийлер тізіміне айналдыру. Сәйкес келмесе — бос тізім."""
    parts = [p.strip(" .") for p in re.split(r"[;\n]", rubric or "") if p.strip(" .")]
    out = []
    for p in parts:
        m = re.match(r"^(\d+(?:[.,]\d+)?)\s*балл\w*\s*[-–—:]\s*(.+)$", p, re.I)
        if m:
            pts, text = m.group(1), m.group(2)
        else:
            m = re.match(r"^(.+?)\s*[-–—:]?\s*\(?(\d+(?:[.,]\d+)?)\s*балл\w*\)?$", p, re.I)
            if not m:
                return []
            text, pts = m.group(1), m.group(2)
        pts = float(pts.replace(",", "."))
        out.append({"text": text.strip(" -–—:"), "points": int(pts) if pts == int(pts) else pts})
    ok = out and all(c["text"] and c["points"] > 0 for c in out) and abs(sum(c["points"] for c in out) - float(total)) < 0.01
    return out if ok else []


def normalize_tasks(tasks: list) -> list:
    """open/file тапсырмаларына рубрика критерийлерін дайындау; тапсырма балы — критерийлер қосындысы."""
    for t in tasks:
        if t.get("type") not in ("open", "file"):
            continue
        d = t.setdefault("data", {})
        crit = []
        for c in d.get("criteria") or []:
            try:
                p = float(c.get("points", 0))
            except (TypeError, ValueError):
                p = 0
            if str(c.get("text", "")).strip() and p > 0:
                crit.append({"text": str(c["text"]).strip(), "points": int(p) if p == int(p) else p})
        if not crit:
            crit = rubric_to_criteria(d.get("rubric", ""), t.get("points", 1))
        if crit:
            d["criteria"] = crit
            t["points"] = sum(c["points"] for c in crit)
        else:
            d.pop("criteria", None)
    return tasks


def enabled():
    return bool(os.environ.get("GEMINI_API_KEY"))


API = "https://generativelanguage.googleapis.com"


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY орнатылмаған")
    if not key.isascii():
        raise RuntimeError("GEMINI_API_KEY қате: кілтте тек латын әріптері мен цифрлар болуы керек (үлгі сөз қалып қойған жоқ па?)")
    return key


def upload_pdf(path: str) -> str:
    """PDF-ті (сканерленген болса да) Gemini File API-ге жүктеп, file_uri қайтарады. Файл 48 сағат сақталады."""
    key, size = _key(), os.path.getsize(path)
    req = urllib.request.Request(
        f"{API}/upload/v1beta/files?key={key}", method="POST",
        data=json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
        headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(size),
                 "X-Goog-Upload-Header-Content-Type": "application/pdf", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
        upload_url = r.headers["X-Goog-Upload-URL"]
    with open(path, "rb") as f:
        req = urllib.request.Request(upload_url, data=f.read(), method="POST",
                                     headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})
    with urllib.request.urlopen(req, timeout=600, context=SSL_CTX) as r:
        info = json.loads(r.read())["file"]
    while info.get("state") == "PROCESSING":
        time.sleep(5)
        with urllib.request.urlopen(f"{API}/v1beta/{info['name']}?key={key}", timeout=60, context=SSL_CTX) as r:
            info = json.loads(r.read())
    if info.get("state") != "ACTIVE":
        raise RuntimeError(f"PDF өңделмеді: {info.get('state')}")
    return info["uri"]


def _call(prompt: str, file_uri: str = None, model: str = None) -> str:
    url = f"{API}/v1beta/models/{model or MODEL}:generateContent?key={_key()}"
    parts = [{"text": prompt}]
    if file_uri:
        parts.insert(0, {"file_data": {"mime_type": "application/pdf", "file_uri": file_uri}})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini қатесі {e.code}: {e.read().decode()[:300]}")
    return data["candidates"][0]["content"]["parts"][0]["text"]


def translate_lesson(lesson: dict, model: str = None) -> dict:
    """Дайын сабақты (title, theory, tasks) орыс тіліне аудару, құрылымы өзгермейді."""
    src = {"title": lesson["title"], "theory": lesson["theory"],
           "tasks": [{"type": t["type"], "prompt": t["prompt"], "data": t["data"]} for t in lesson["tasks"]]}
    prompt = f"""Переведи на РУССКИЙ язык учебный материал по информатике для {lesson['grade']} класса школы Казахстана.
Это урок для групп с русским языком обучения. Используй принятые в русских учебниках термины
(ячейка, формула, диаграмма, цикл, переменная и т.д.), пиши естественно, а не дословно.

Правила:
- Верни ТОЛЬКО JSON той же структуры: {{"title": ..., "theory": ..., "tasks": [{{"type", "prompt", "data"}}]}}.
- Количество и порядок заданий, их type, количество вариантов (options) и их ПОРЯДОК не меняй.
  Поля answer у quiz/multi (индексы) оставь как есть.
- У short переведи answer — это список допустимых ответов; числа оставь, слова дай по-русски
  (можно добавить синонимы).
- Markdown, код, формулы Excel (=СУММ(A1:A5) и т.п.) не меняй, переводи только текст и комментарии.
- У code tests: input не меняй; если в output есть казахские слова (например «Иә», «Жоқ», «Қош келдіңіз!»),
  переведи их на русский («Да», «Нет», «Добро пожаловать!») и используй ТЕ ЖЕ слова в условии задачи.
- ВСЁ должно быть на русском: ни одного казахского слова в prompt, options, explain не оставляй.
- Переведи explain и rubric. У open/file переведи text в criteria, количество criteria и points не меняй. У file поле accept не меняй; в prompt практической работы
  используй русские названия команд и вкладок Excel/Word (Главная, Вставка, Условное форматирование и т.д.).

ИСХОДНЫЙ УРОК (казахский):
{json.dumps(src, ensure_ascii=False)}
"""
    text = _call(prompt, model=model).strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1]
    out = json.loads(text)
    tasks = out.get("tasks", [])
    if len(tasks) != len(src["tasks"]):
        raise RuntimeError("аудармада тапсырма саны өзгерді")
    for a, b in zip(src["tasks"], tasks):
        if a["type"] != b.get("type"):
            raise RuntimeError("аудармада тапсырма түрі өзгерді")
        d, bd = a["data"], b.setdefault("data", {})
        if a["type"] in ("quiz", "multi"):
            if len(bd.get("options", [])) != len(d.get("options", [])):
                raise RuntimeError("аудармада жауап нұсқаларының саны өзгерді")
            bd["answer"] = d["answer"]
        if a["type"] in ("open", "file"):
            sc, bc = d.get("criteria") or [], bd.get("criteria") or []
            if sc:
                if len(bc) != len(sc):
                    raise RuntimeError("аудармада рубрика критерийлерінің саны өзгерді")
                bd["criteria"] = [{"text": str(y.get("text", "")), "points": x["points"]} for x, y in zip(sc, bc)]
        if a["type"] == "file":
            bd["accept"] = d.get("accept", "")
        if a["type"] == "code":
            # Енгізу мен тест саны өзгермейді, тек шығарудағы сөздер аударылуы мүмкін
            tests, rt = d.get("tests", []), bd.get("tests") or []
            same = len(rt) == len(tests) and all(str(x.get("input", "")) == str(y.get("input", "")) for x, y in zip(tests, rt))
            bd["tests"] = [dict(x, output=y.get("output", x["output"])) for x, y in zip(tests, rt)] if same else tests
    return {"title": out.get("title", ""), "theory": out.get("theory", ""),
            "tasks": [{"prompt": t["prompt"], "data": t["data"]} for t in tasks]}


def translate_theory(title: str, theory: str, grade: int, model: str = None) -> dict:
    """Тек сабақтың атауы мен теориясын орысшаға аудару (тапсырмаларға тиіспейді). Қайтарады: {"title", "theory"}."""
    prompt = f"""Переведи на РУССКИЙ язык теорию урока информатики для {grade} класса школы Казахстана (группы с русским языком обучения).
Используй принятые в русских учебниках термины, пиши естественно. Markdown, таблицы, код и формулы не меняй, переводи текст и комментарии в коде.
ВСЁ должно быть на русском: ни одного казахского слова не оставляй. Верни ТОЛЬКО JSON: {{"title": ..., "theory": ...}}.

{json.dumps({"title": title, "theory": theory}, ensure_ascii=False)}
"""
    text = _call(prompt, model=model).strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1]
    out = json.loads(text)
    return {"title": out.get("title", ""), "theory": out.get("theory", "")}


def generate_lesson(lesson: dict, source: str, what: str = "all", file_uri: str = None, model: str = None) -> dict:
    prompt = f"""Сен Қазақстандағы мектептің тәжірибелі информатика мұғалімісің.
{lesson['grade']}-сынып, {lesson['quarter']}-тоқсан. Бөлім: «{lesson['section']}». Сабақ тақырыбы: «{lesson['title']}».
Оқу мақсаттары: {lesson['objectives']}

{"Тіркелген оқулықтан (PDF) осы тақырыпқа арналған параграфты тауып, соған сүйеніп" if file_uri else "Төмендегі оқулық мәтініне сүйеніп,"} ҚАЗАҚ ТІЛІНДЕ сабақ материалын жаса:
1. Теория: толық және терең (900–1400 сөз), жас ерекшелігіне сай. Құрылымы: ## тақырыпшалар; әр жаңа ұғымға анықтама +
   өмірден ұқсастық/мысал; кемінде 2–3 толық шешілген мысал (Python тақырыбында — код пен шығысы және қадамдап түсіндірмесі);
   салыстыру кестесі (қажет болса); «Жиі кететін қателер» бөлімі; соңында «Есте сақта» қысқа тұжырымы.
2. 5–7 практикалық тапсырма: оңайдан қиынға қарай. Python тақырыптарында кемінде 2 code тапсырма
   (әрқайсысында 3–4 тест, біреуі hidden). Басқа тақырыптарда quiz, multi, short және бір open.
Python емес тақырыптарда міндетті түрде 1 file тапсырмасы (практикалық жұмыс) болсын: оқушы компьютерде
(Excel, Word, PowerPoint, браузер, Paint т.б.) өз қолымен орындайтын нақты жұмыс. Шартында бастапқы деректерді
(мысалы, кестенің мәндерін) және 3–6 нөмірленген қадамды нақты жаз, соңында қандай файл жүктеу керегін айт.
accept өрісіне файл түрлерін жаз (.xlsx,.xls / .docx,.pdf / .pptx / скриншот болса .png,.jpg).
open және file тапсырмаларына criteria (рубрика) жаз: 2–4 нақты, тексеруге болатын критерий, әрқайсысына points; points қосындысы тапсырма баллына тең болсын.
code тапсырмасын ТЕК Python бағдарламалау тақырыптарында бер. Мәтіндік процессор, электрондық кесте,
графика сияқты тақырыптарда code тапсырмасы мен ```python мысалдары болмасын — оның орнына практикалық
жағдаяттарға (формула нәтижесі, ұяшық адресі, мәзір командасы) quiz/short сұрақтар бер.
Code тапсырмаларында input() арқылы енгізу, print() арқылы дәл шығару керек — тест шығысы бірмәнді болсын.
{"Тек теорияны жаса, tasks бос тізім болсын." if what == "theory" else ""}
{"Тек тапсырмаларды жаса, theory бос жол болсын." if what == "tasks" else ""}
{SCHEMA_HINT}

ОҚУЛЫҚ МӘТІНІ:
{source[:30000] or '(мәтін берілмеді — оқу мақсаттарына сүйен)'}
"""
    if model:
        text = _call(prompt, file_uri, model).strip()
    else:
        try:
            text = _call(prompt, file_uri, MODEL).strip()
        except RuntimeError:
            text = _call(prompt, file_uri, FALLBACK).strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1]
    out = json.loads(text)
    return {"theory": out.get("theory", ""), "tasks": normalize_tasks(out.get("tasks", []))}


def suggest_grade(prompt: str, criteria: list, rubric: str, answer: str, points) -> dict:
    """Оқушының ашық жауабына баға ұсынысы: әр критерийге балл және қысқа пікір. Соңғы шешімді мұғалім қабылдайды."""
    if criteria:
        scale = "\n".join(f"{i + 1}. {c['text']} (макс. {c['points']})" for i, c in enumerate(criteria))
        fmt = '{"scores": [число для каждого критерия по порядку], "feedback": "1-2 коротких предложения"}'
    else:
        scale = rubric or "Оцени полноту и правильность ответа."
        fmt = f'{{"scores": [одно число от 0 до {points}], "feedback": "1-2 коротких предложения"}}'
    text = f"""Ты помощник учителя информатики. Оцени ответ ученика строго по критериям, не завышай оценку.
Если ответ пустой, не по теме или бессмысленный, ставь 0. Баллы могут быть дробными (шаг 0.5), не больше максимума.
Комментарий напиши на том же языке, на котором написан ответ ученика (казахский или русский), доброжелательно.

ЗАДАНИЕ: {prompt}

КРИТЕРИИ:
{scale}

ОТВЕТ УЧЕНИКА:
{answer[:4000]}

Верни ТОЛЬКО JSON: {fmt}"""
    out = json.loads(_call(text).strip().strip("`").removeprefix("json").strip())
    scores = out.get("scores") or []
    caps = [float(c["points"]) for c in criteria] if criteria else [float(points)]
    if len(scores) != len(caps):
        raise RuntimeError("AI жауабының құрылымы дұрыс емес")
    scores = [round(max(0.0, min(float(x), cap)) * 2) / 2 for x, cap in zip(scores, caps)]
    return {"scores": scores, "feedback": str(out.get("feedback", ""))[:300]}
