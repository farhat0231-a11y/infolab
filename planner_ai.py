"""Gemini арқылы ҚМЖ + слайд + мұғалім сөзін жасау (интернет және GEMINI_API_KEY болса ғана)."""
import json

import ai

MODELS = list(dict.fromkeys([ai.MODEL, "gemini-3.8-flash", ai.FALLBACK]))
PHASES = ("start", "middle", "end")
LANGS = {"kk": "ҚАЗАҚ", "ru": "РУССКОМ"}

SHAPE = """
Тек JSON қайтар:
{
 "aim": "сабақтың мақсаты (1–2 сөйлем: сабақ соңында оқушы не істей алады)",
 "phases": [
  {"key":"start","steps":[{"title":"қадам атауы","minutes":5,"teacher":"педагог әрекеті","student":"оқушы әрекеті","assess":"бағалау: дескриптор + кері байланыс түрі","resources":"ресурстар","tasks":[]}]},
  {"key":"middle","steps":[...]},
  {"key":"end","steps":[...]}
 ],
 "slides": [{"phase":"start|middle|end","md":"слайд мәтіні markdown-мен","notes":"осы слайдта мұғалім не айтады"}]
}
"""


def build_prompt(lesson, objectives, lang, theory, tasks, total, has_book=False):
    tl = "\n".join(f"{n}. [{t['type']}] {t['prompt'][:140]}" for n, t in enumerate(tasks, 1)) or "(тапсырма жоқ)"
    return f"""Сен Қазақстандағы мектептің тәжірибелі информатика мұғалімісің. {lesson['grade']}-сынып, {lesson['quarter']}-тоқсан.
Бөлім: «{lesson['section']}». Сабақ тақырыбы: «{lesson['title']}». Оқу мақсаты (КТЖ): {objectives}

Осы сабаққа {total} МИНУТТЫҚ қысқа мерзімді жоспар (ҚМЖ), слайдтар және мұғалімнің сөзін {LANGS[lang]} ТІЛІНДЕ жаса.
ТАЛАПТАР:
- phases: start (сабақтың басы), middle (ортасы), end (соңы). Қадамдардың minutes қосындысы ДӘЛ {total} болсын.
  Қадамдар саны барлығы 5–8.
- Саралау (дифференциация): ортаңғы кезеңде кемінде бір қадамда 3 деңгей (базалық / орта / жоғары) көрсет:
  әр деңгейге нақты тапсырма немесе қолдау түрін жаз.
- Қалыптастырушы бағалау: әр қадамның assess өрісінде нақты дескриптор («...істей алады») және кері байланыс түрі
  (ауызша, өзара бағалау, смайлик, 2 жұлдыз + 1 тілек т.б.).
- Сабақтың соңы (end) рефлексияны қамтуы тиіс (мысалы, «Бүгін не үйрендім / не қиын болды»).
- Практика қадамы төмендегі InfoLab тапсырмаларына сілтеме жасасын: tasks өрісіне тапсырма НӨМІРЛЕРІН (бүтін сандар) жаз.
- slides: 14–18 слайд, ҚМЖ кезеңдерімен үйлес (start/middle/end). Бір сабаққа бір ғана монотонды «тақырып+тізім» болмасын,
  слайд түрлерін араластыр:
  • ұғым слайды: «## ұғым» + анықтама + өмірден ұқсастық (3–6 жол);
  • мысал слайды: «## Мысал» + ```python код (≤12 жол) + «Шығысы:» немесе «Шығысы не болады?» сұрағы;
  • қадамдап орындау (trace) слайды: markdown кесте (қадам | айнымалылар | шығыс);
  • салыстыру слайды: markdown кесте (екі ұғымды қатар);
  • «Жиі кететін қате» слайды: қате код → неге қате → дұрысы;
  • сұрақ слайды: ойланту сұрағы немесе 3–4 жауап нұсқалы мини-сұрақ;
  • практикаға өту слайды: қандай InfoLab тапсырмасы және қандай нәтиже күтіледі.
  Мәтін тығыз әрі мазмұнды болсын, бірақ слайд ішіне сыйсын (ең көбі 8 жол немесе 1 код + 3 жол). Бірінші слайд — «# тақырып» және мақсат.
  notes — сол слайдта мұғалім айтатын 3–5 сөйлем: түсіндірме, қосымша мысал, оқушыға қояр сұрақ (тірі сөйлеу тілімен).
{SHAPE}
СЫНЫП ТІЛІ: {LANGS[lang]}.

{"ОҚУЛЫҚ (PDF) тіркелген: осы тақырыпқа арналған параграфты тауып, мысалдар мен терминдерді сол оқулықтан ал, оқулықтағы терминологияны қолдан." if has_book else ""}
ТЕОРИЯ (дайын материал):
{(theory or '(жоқ — оқу мақсатына сүйен)')[:12000]}

INFOLAB ТАПСЫРМАЛАРЫ (нөмірі бойынша):
{tl}
"""


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1]
    return json.loads(text)


def fix_total(stages, total):
    """Қосынды total-ға тең болмаса, айырманы ең ұзақ ортаңғы қадамға қосамыз/азайтамыз."""
    steps = [s for p in stages["phases"] for s in p["steps"]]
    if not steps:
        return stages
    diff = total - sum(s["minutes"] for s in steps)
    mid = [s for p in stages["phases"] if p["key"] == "middle" for s in p["steps"]] or steps
    tgt = max(mid, key=lambda s: s["minutes"])
    tgt["minutes"] = max(1, tgt["minutes"] + diff)
    return stages


def generate(lesson, objectives, lang, theory, tasks, total, clean_stages, call=None, file_uri=None):
    """Қайтарады: {aim, stages, slides}. tasks — [{'id','type','prompt'}]; clean_stages — planner.clean_stages."""
    prompt = build_prompt(lesson, objectives, lang, theory, tasks, total, bool(file_uri))
    err = None
    for model in MODELS:
        try:
            out = _parse((call or ai._call)(prompt, file_uri, model))
            break
        except Exception as e:  # noqa — келесі модельді байқап көреміз
            err = e
    else:
        raise RuntimeError(str(err))
    ids = {n: t["id"] for n, t in enumerate(tasks, 1)}
    for ph in out.get("phases", []):
        for s in ph.get("steps", []):
            s["tasks"] = [ids[int(x)] for x in s.get("tasks", []) if str(x).isdigit() and int(x) in ids]
    stages = fix_total(clean_stages({"phases": out.get("phases", [])}), total)
    slides = [{"phase": s.get("phase") if s.get("phase") in PHASES else "middle", "md": str(s.get("md", ""))[:6000],
               "notes": str(s.get("notes", ""))[:4000]} for s in out.get("slides", [])[:40] if str(s.get("md", "")).strip()]
    return {"aim": str(out.get("aim", ""))[:1500], "stages": stages, "slides": slides}


IMPROVE = {
    "more": "Слайдты толығырақ және терең жаса: түсіндірмені, мысалды және қосымша ақпаратты қос.",
    "example": "Слайдқа жақсы нақты мысал қос (Python тақырыбында — код пен шығысы).",
    "simple": "Слайдты қарапайым тілмен, жас оқушыға түсінікті етіп қайта жаз: ұқсастық қолдан.",
    "short": "Слайдты қысқарт: ең маңыздысын ғана қалдыр.",
}


def improve(lesson, lang, md, notes, instruction, call=None):
    """Бір слайдты (және мұғалімнің сөзін) нұсқаулық бойынша қайта жазу. Қайтарады: {md, notes}."""
    prompt = f"""Сен информатика мұғалімісің. {lesson['grade']}-сынып, тақырып: «{lesson['title']}». Тіл: {LANGS[lang]} ТІЛІ.
Төмендегі слайдты (markdown) және мұғалімнің сөзін нұсқаулыққа сай жақсарт. Слайд 16:9 экранда ірі қаріппен көрсетіледі:
ең көбі 8 жол немесе 1 код блогы (```python, ≤12 жол) + 3 жол. Кесте қажет болса markdown кестені қолдан.
NҰСҚАУЛЫҚ: {instruction}

СЛАЙД:
{md}

МҰҒАЛІМНІҢ СӨЗІ:
{notes or '(жоқ)'}

Тек JSON қайтар: {{"md":"жаңа слайд мәтіні","notes":"жаңа мұғалім сөзі (3–5 сөйлем)"}}"""
    err = None
    for model in MODELS:
        try:
            out = _parse((call or ai._call)(prompt, None, model))
            return {"md": str(out.get("md") or md)[:6000], "notes": str(out.get("notes") or notes)[:4000]}
        except Exception as e:  # noqa
            err = e
    raise RuntimeError(str(err))
