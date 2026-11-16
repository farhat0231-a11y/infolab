"""Толтырылған сабақтардың орысша нұсқасын Gemini арқылы жасау (орыс топтарына).

    GEMINI_API_KEY=... python translate_ru.py          # орысшасы жоқ барлық сабақ
    GEMINI_API_KEY=... python translate_ru.py 7        # тек 7-сынып
    GEMINI_API_KEY=... python translate_ru.py g7-08 g7-09   # нақты сабақтар (бар аударманы қайта жазады)

Нәтиже деректер қорына және content/<код>.json файлының "ru" бөліміне жазылады.
"""
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import ai
import app as platform

# Бір модельдің күндік тегін шегі біткенде келесісіне ауысады
MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
WORKERS = 3
# Кирилл, латын, тыныс белгілері, нұсқамалар мен эмодзиден басқа таңба болса — аударма бұзылған
STRANGE = re.compile(r"[^\u0000-\u024F\u0400-\u04FF\u2000-\u2BFF\U0001F300-\U0001FAFF\uFE0F]")
# Аудармада қазақша сөз қалмауы керек (Қазақстан сияқты бірлі-жарым атаулардан басқа)
KAZAKH = re.compile(r"\S*[әғқңөұүһіӘҒҚҢӨҰҮҺІ]\S*")

codes = sys.argv[1:]
arg = codes[0] if codes else ""
con = sqlite3.connect(platform.DB_PATH, check_same_thread=False)
con.row_factory = sqlite3.Row
platform.migrate(con)
if arg.startswith("g"):
    where, args = f"code IN ({','.join('?' * len(codes))})", tuple(codes)
else:
    where, args = "((COALESCE(kind,'lesson')='block' AND title_ru='') OR (COALESCE(kind,'lesson')='lesson' AND theory_ru='')) AND (?='' OR grade=?)", (arg, arg)
lessons = []
for L in con.execute(f"SELECT * FROM lessons WHERE {where} AND id IN (SELECT lesson_id FROM tasks) ORDER BY grade, quarter, num", args):
    L = dict(L)
    L["tasks"] = [dict(t, data=json.loads(t["data"])) for t in con.execute("SELECT * FROM tasks WHERE lesson_id=? ORDER BY ord", (L["id"],))]
    lessons.append(L)
print(f"{len(lessons)} сабақ аударылады.", flush=True)


def translate(L):
    for model in MODELS:
        try:
            ru = ai.translate_lesson(L, model=model)
            bad = set(STRANGE.findall(json.dumps(ru, ensure_ascii=False)))
            if bad:
                raise RuntimeError("бөгде таңбалар: " + "".join(bad))
            kk = KAZAKH.findall(json.dumps(ru, ensure_ascii=False))
            if len(kk) > 3:
                raise RuntimeError("қазақша сөздер қалды: " + " ".join(kk[:5]))
            return L, ru, model
        except Exception as e:  # noqa
            print(f"  {L['code']}: {model} — {str(e)[:90]}", flush=True)
    return L, None, None


done = 0
with ThreadPoolExecutor(WORKERS) as ex:
    for L, ru, model in ex.map(translate, lessons):
        if not ru:
            print(f"✗ {L['code']} {L['title']}: аударылмады", flush=True)
            continue
        platform.save_ru(con, L["id"], ru)
        con.commit()
        path = os.path.join(platform.BASE, "content", f"{L['code']}.json")
        c = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {
            "code": L["code"], "theory": L["theory"],
            "tasks": [{"type": t["type"], "prompt": t["prompt"], "points": t["points"], "data": t["data"]} for t in L["tasks"]]}
        c["ru"] = ru
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        done += 1
        print(f"✓ {L['code']} {ru['title']} ({model})", flush=True)
print(f"{done}/{len(lessons)} сабақ аударылды.")
