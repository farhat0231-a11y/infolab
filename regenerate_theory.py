"""Бар сабақтардың ТЕОРИЯСЫН оқулықтан жаңа (толық) промтпен қайта жасау. Тапсырмаларға және оқушы жауаптарына тиіспейді.

    GEMINI_API_KEY=... python regenerate_theory.py 8 2              # 8-сынып, 2-тоқсан (қысқа теориялар ғана)
    GEMINI_API_KEY=... python regenerate_theory.py 8 2 --all        # ұзын теорияларды да қайта жасау
    GEMINI_API_KEY=... python regenerate_theory.py 8 g8-05 g8-06    # нақты сабақтар

Қазақша теория жаңарған соң орысша теория да аударылады (title_ru, theory_ru). Нәтиже content/<код>.json-ға жазылады.
"""
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ai
import app as platform

MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
WORKERS = 2
MIN_WORDS = 800  # осыдан қысқа теориялар ғана қайта жасалады (--all болмаса)
STRANGE = re.compile(r"[^\u0000-ɏЀ-ӿ -⯿\U0001F300-\U0001FAFF️]")
KAZAKH = re.compile(r"\S*[әғқңөұүһіӘҒҚҢӨҰҮҺІ]\S*")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
force_all = "--all" in sys.argv
grade = int(args[0])
codes = [a for a in args[1:] if a.startswith("g")]
quarter = int(args[1]) if len(args) > 1 and not args[1].startswith("g") else None

con = sqlite3.connect(platform.DB_PATH, check_same_thread=False, timeout=60)
con.row_factory = sqlite3.Row
book = con.execute("SELECT * FROM books WHERE grade=? ORDER BY lang='kk' DESC, id DESC", (grade,)).fetchone()
if not book:
    print(f"{grade}-сыныптың оқулығы жоқ: бар теория негізінде кеңейтіледі.", flush=True)
where, params = "grade=? AND COALESCE(kind,'lesson')='lesson'", [grade]
if quarter:
    where += " AND quarter=?"
    params.append(quarter)
if codes:
    where += " AND code IN (%s)" % ",".join("?" * len(codes))
    params += codes
lessons = [dict(r) for r in con.execute(f"SELECT * FROM lessons WHERE {where} ORDER BY quarter, num", params)]
if not force_all and not codes:
    lessons = [L for L in lessons if len((L["theory"] or "").split()) < MIN_WORDS]
if not lessons:
    sys.exit("Қайта жасайтын сабақ жоқ.")
print(f"{grade}-сынып: {len(lessons)} сабақ.", flush=True)
uri = None
if book:
    print(f"Оқулық жүктелуде: {book['title']}", flush=True)
    uri = ai.upload_pdf(os.path.join(platform.BOOKS_DIR, book["filename"]))


def run(L):
    for model in MODELS:
        t = time.time()
        try:
            out = ai.generate_lesson(L, "" if uri else L["theory"], "theory", uri, model=model)
            if len(out["theory"].split()) < 700:  # жеңіл модель жиі қысқа береді: келесі модельді байқаймыз
                raise RuntimeError(f"теория тым қысқа ({len(out['theory'].split())} сөз)")
            return L, out["theory"], f"{model}, {time.time() - t:.0f} с"
        except Exception as e:  # noqa
            print(f"  {L['code']}: {model} — {str(e)[:80]}", flush=True)
    return L, None, None


def translate(L, theory):
    for model in MODELS:
        try:
            ru = ai.translate_theory(L["title"], theory, L["grade"], model=model)
            js = json.dumps(ru, ensure_ascii=False)
            if STRANGE.search(js):
                raise RuntimeError("бөгде таңбалар")
            if len(KAZAKH.findall(js)) > 3:
                raise RuntimeError("қазақша сөздер қалды")
            return ru
        except Exception as e:  # noqa
            print(f"  {L['code']} RU: {model} — {str(e)[:80]}", flush=True)
    return None


def process(L):
    L, theory, info = run(L)
    if not theory:
        return L, None, None, "теория жасалмады"
    return L, theory, translate(L, theory), info


done = 0
with ThreadPoolExecutor(WORKERS) as ex:
    for L, theory, ru, info in ex.map(process, lessons):
        if not theory:
            print(f"✗ {L['code']} {L['title']}: {info}", flush=True)
            continue
        con.execute("UPDATE lessons SET theory=?, updated=datetime('now') WHERE id=?", (theory, L["id"]))
        path = os.path.join(platform.BASE, "content", f"{L['code']}.json")
        c = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"code": L["code"], "tasks": []}
        c["theory"] = theory
        if ru:
            con.execute("UPDATE lessons SET theory_ru=?, title_ru=COALESCE(NULLIF(title_ru,''),?) WHERE id=?",
                        (ru["theory"], ru["title"], L["id"]))
            c.setdefault("ru", {"title": ru["title"], "tasks": []})["theory"] = ru["theory"]
        else:
            con.execute("UPDATE lessons SET theory_ru='' WHERE id=?", (L["id"],))  # ескі орысша теория қазақшаға сай емес
            c.get("ru", {}).pop("theory", None)
        con.commit()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        done += 1
        print(f"✓ {L['code']} {L['title']}: {len(theory.split())} сөз{'' if ru else ', орысшасы жасалмады'} ({info})", flush=True)
print(f"{grade}-сынып: {done}/{len(lessons)} сабақ жаңартылды.")
