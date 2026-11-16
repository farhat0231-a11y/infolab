"""content/ папкасындағы JSON сабақтарды деректер қорына жүктеу (жаңарту).

    python load_content.py            # тек бос сабақтарға жүктейді
    python load_content.py --force    # бар сабақтарды да қайта жазады (оқушы жауаптары өшеді!)
"""
import json
import os
import sqlite3
import sys

import app as platform

force = "--force" in sys.argv
con = sqlite3.connect(platform.DB_PATH)
platform.migrate(con)
cdir = os.path.join(platform.BASE, "content")
n = 0
for fn in sorted(os.listdir(cdir)):
    if not fn.endswith(".json"):
        continue
    c = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
    row = con.execute("SELECT id FROM lessons WHERE code=?", (c["code"],)).fetchone()
    if not row:
        print("Табылмады:", c["code"]); continue
    lid = row[0]
    has = con.execute("SELECT COUNT(*) FROM tasks WHERE lesson_id=?", (lid,)).fetchone()[0]
    if has and not force:
        continue
    con.execute("DELETE FROM submissions WHERE task_id IN (SELECT id FROM tasks WHERE lesson_id=?)", (lid,))
    con.execute("DELETE FROM tasks WHERE lesson_id=?", (lid,))
    con.execute("UPDATE lessons SET theory=? WHERE id=?", (c["theory"], lid))
    for k, t in enumerate(c["tasks"]):
        con.execute("INSERT INTO tasks(lesson_id,ord,type,prompt,data,points) VALUES(?,?,?,?,?,?)",
                    (lid, k, t["type"], t["prompt"], json.dumps(t.get("data", {}), ensure_ascii=False), t.get("points", 1)))
    if c.get("ru"):
        platform.save_ru(con, lid, c["ru"])
    n += 1
con.commit()
print(f"{n} сабақ жүктелді.")
