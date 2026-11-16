"""Сынап көру үшін демо деректер: 1 мұғалім, 2 сынып, бірнеше оқушы.

    python seed_demo.py

Мұғалім:  логин mugalim / құпия сөз mugalim123
Оқушылар: aruzhan, nurlan, dana, timur / құпия сөз 123456
"""
import sqlite3

from werkzeug.security import generate_password_hash

import app as platform

con = sqlite3.connect(platform.DB_PATH)
con.row_factory = sqlite3.Row
if con.execute("SELECT 1 FROM users WHERE username='mugalim'").fetchone():
    print("Демо деректер бұрыннан бар.")
    raise SystemExit
cur = con.execute("INSERT INTO users(name,username,pw,role) VALUES(?,?,?,?)",
                  ("Төленді Фархат", "mugalim", generate_password_hash("mugalim123"), "teacher"))
tid = cur.lastrowid
classes = {}
for name, grade, code in [("8А", 8, "INFO8A"), ("10Ә", 10, "INFO10"), ("7Б", 7, "INFO7B")]:
    classes[name] = con.execute("INSERT INTO classes(name,grade,code,teacher_id) VALUES(?,?,?,?)",
                                (name, grade, code, tid)).lastrowid
students = [("Әлиева Аружан", "aruzhan", "8А"), ("Серікұлы Нұрлан", "nurlan", "8А"),
            ("Қайратқызы Дана", "dana", "8А"), ("Болатов Тимур", "timur", "10Ә")]
for name, user, cls in students:
    con.execute("INSERT INTO users(name,username,pw,role,class_id) VALUES(?,?,?,?,?)",
                (name, user, generate_password_hash("123456"), "student", classes[cls]))
# Мазмұны бар сабақтарды сыныптарға ашу
for cname, cid in classes.items():
    grade = int("".join(ch for ch in cname if ch.isdigit()))
    for r in con.execute("""SELECT id FROM lessons l WHERE grade=? AND
                            EXISTS(SELECT 1 FROM tasks t WHERE t.lesson_id=l.id)""", (grade,)):
        con.execute("INSERT OR IGNORE INTO class_lessons(class_id,lesson_id) VALUES(?,?)", (cid, r["id"]))
con.commit()
print("Демо деректер қосылды.\n  Мұғалім: mugalim / mugalim123\n  Оқушы:   aruzhan / 123456 (8А)")
