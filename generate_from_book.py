"""Сайтқа жүктелген оқулықтан (PDF, сканер болса да) бос сабақтарды Gemini арқылы толтыру.

    GEMINI_API_KEY=... python generate_from_book.py 7          # 7-сыныптың барлық бос сабақтары
    GEMINI_API_KEY=... python generate_from_book.py 7 2        # тек 2-тоқсан
    GEMINI_API_KEY=... python generate_from_book.py 9 --replace g9-07 g9-08   # бар мазмұнды оқулықтан қайта жасау

Әдепкіде тек бос сабақтар толтырылады. --replace үшін сабақ кодтарын көрсету керек: олардың
мазмұны ауыстырылады, бірақ оқушы жауабы бар сабаққа тиіспейді. Нәтиже content/<код>.json файлына да жазылады.
"""
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ai
import app as platform

MODELS = ["gemini-3.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]  # бос емес болса, келесісі
WORKERS = 3

args = [a for a in sys.argv[1:] if not a.startswith("--")]
replace = "--replace" in sys.argv
codes = [a for a in args if a.startswith("g")]
nums = [a for a in args if not a.startswith("g")]
grade = int(nums[0])
quarter = int(nums[1]) if len(nums) > 1 else None
if replace and not codes:
    sys.exit("--replace үшін сабақ кодтарын көрсетіңіз, мысалы: g9-07 g9-08")

con = sqlite3.connect(platform.DB_PATH, check_same_thread=False)
con.row_factory = sqlite3.Row
book = con.execute("SELECT * FROM books WHERE grade=? ORDER BY lang='kk' DESC, id DESC", (grade,)).fetchone()
if not book:
    sys.exit(f"{grade}-сыныптың оқулығы жүктелмеген (Мұғалім → Оқулықтар)")
where, params = "grade=? AND COALESCE(kind,'lesson')='lesson' AND (? IS NULL OR quarter=?)", [grade, quarter, quarter]
if codes:
    where += " AND code IN (%s)" % ",".join("?" * len(codes))
    params += codes
if replace:  # оқушы жауабы бар сабақтың мазмұнын ауыстырмаймыз
    where += " AND id NOT IN (SELECT t.lesson_id FROM tasks t JOIN submissions s ON s.task_id=t.id)"
else:
    where += " AND id NOT IN (SELECT lesson_id FROM tasks)"
lessons = [dict(r) for r in con.execute(f"SELECT * FROM lessons WHERE {where} ORDER BY quarter, num", params)]
skipped = sorted(set(codes) - {L["code"] for L in lessons})
if skipped:
    print("Өткізілді (жауабы бар немесе табылмады):", ", ".join(skipped), flush=True)
if not lessons:
    sys.exit("Жасайтын сабақ жоқ.")

print(f"Оқулық: {book['title']} — Gemini-ге жүктелуде...", flush=True)
uri = ai.upload_pdf(os.path.join(platform.BOOKS_DIR, book["filename"]))
print(f"{len(lessons)} сабақ жасалады.", flush=True)


def generate(L):
    for model in MODELS:
        t = time.time()
        try:
            out = ai.generate_lesson(L, "", "all", uri, model=model)
            if out["theory"] and out["tasks"]:
                return L, out, f"{model}, {time.time() - t:.0f} с"
        except Exception as e:  # noqa
            print(f"  {L['code']}: {model} — {str(e)[:80]}", flush=True)
    return L, None, "жасалмады"


done = 0
with ThreadPoolExecutor(WORKERS) as ex:
    for L, out, info in ex.map(generate, lessons):
        if not out:
            print(f"✗ {L['code']} {L['title']}: {info}", flush=True)
            continue
        c = {"code": L["code"], "theory": out["theory"], "tasks": out["tasks"]}
        with open(os.path.join(platform.BASE, "content", f"{L['code']}.json"), "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        if replace:  # ескі тапсырмалар мен орысша нұсқаны өшіру (жаңа мазмұн қазақша)
            con.execute("DELETE FROM tasks WHERE lesson_id=?", (L["id"],))
            con.execute("UPDATE lessons SET title_ru='', theory_ru='' WHERE id=?", (L["id"],))
        con.execute("UPDATE lessons SET theory=? WHERE id=?", (c["theory"], L["id"]))
        for k, t in enumerate(c["tasks"]):
            con.execute("INSERT INTO tasks(lesson_id,ord,type,prompt,data,points) VALUES(?,?,?,?,?,?)",
                        (L["id"], k, t["type"], t["prompt"], json.dumps(t.get("data", {}), ensure_ascii=False), t.get("points", 1)))
        con.commit()
        done += 1
        print(f"✓ {L['code']} {L['title']}: {len(c['tasks'])} тапсырма ({info})", flush=True)
print(f"{done}/{len(lessons)} сабақ толтырылды.")
