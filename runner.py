"""Оқушы жазған Python кодын қауіпсіз (шектеулі) ортада іске қосу.

Код бөлек процесте орындалады:
  * уақыт шегі (әдепкі 3 секунд);
  * жад, файл өлшемі және процесс саны шектеледі (Linux/macOS);
  * уақытша бос папкада жұмыс істейді;
  * audit hook арқылы желіге шығу, жаңа процесс ашу, папкадан тыс файлдарға жазу тыйым салынады.

Бұл мектеп ішіндегі платформа үшін жеткілікті қорғаныс, бірақ толық "құмсалғыш" (sandbox) емес.
Сайтты интернетке ашық қоятын болсаңыз, серверді бөлек виртуалды машинада ұстаған дұрыс.
"""
import os
import subprocess
import sys
import tempfile

TIME_LIMIT = float(os.environ.get("CODE_TIME_LIMIT", "3"))
MAX_OUTPUT = 20_000

GUARD = r'''
import sys, os
_root = os.path.realpath(os.getcwd())
_lib = tuple({os.path.realpath(p) for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(os.__file__))})
_BAD_MODULES = {"sqlite3", "_sqlite3", "ctypes", "_ctypes", "_posixsubprocess", "_posixshmem", "multiprocessing",
                "_multiprocessing", "_xxsubinterpreters", "_interpreters", "_testcapi", "_testinternalcapi", "dbm", "_dbm", "_gdbm"}
def _hook(event, args):
    if event == "import" and args and isinstance(args[0], str) and args[0].split(".")[0] in _BAD_MODULES:
        raise ImportError("Бұл модульге рұқсат жоқ: " + args[0])
    if event.startswith("sqlite3.") or event.startswith("ctypes."):
        raise PermissionError("Бұл әрекетке рұқсат жоқ: " + event)
    if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                 "os.kill", "os.forkpty", "pty.spawn", "ctypes.dlopen", "os.startfile"):
        raise PermissionError("Бұл әрекетке рұқсат жоқ: " + event)
    if event.startswith("socket."):
        raise PermissionError("Желіге шығуға рұқсат жоқ")
    if event in ("os.remove", "os.rmdir", "os.rename", "shutil.rmtree", "os.chmod", "os.chdir"):
        p = args[0] if args else ""
        if isinstance(p, (str, bytes)) and not os.path.realpath(p if isinstance(p, str) else p.decode()).startswith(_root):
            raise PermissionError("Бұл файлға рұқсат жоқ")
    if event in ("os.listdir", "os.scandir") and args and isinstance(args[0], (str, bytes)):
        p = os.path.realpath(args[0] if isinstance(args[0], str) else args[0].decode())
        if not (p.startswith(_root) or p.startswith(_lib)):
            raise PermissionError("Бұл папкаға рұқсат жоқ")
    if event == "open":
        path, mode = args[0], args[1]
        if isinstance(path, int):
            return
        if isinstance(path, bytes):
            path = path.decode(errors="ignore")
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        writing = any(c in str(mode or "r") for c in "wax+") or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND))
        real = os.path.realpath(str(path))
        if writing:
            if not real.startswith(_root):
                raise PermissionError("Тек өз папкаңызға жазуға болады")
        elif not (real.startswith(_root) or real.startswith(_lib) or real in ("/dev/null", "/dev/urandom")):
            # сайттың файлдарын (дерекқор, кілт) оқуға болмайды: тек өз папкасы және Python кітапханалары
            raise PermissionError("Бұл файлды оқуға рұқсат жоқ")
sys.addaudithook(_hook)
del _hook
_src = open("main.py", encoding="utf-8").read()
exec(compile(_src, "main.py", "exec"), {"__name__": "__main__", "__builtins__": __builtins__})
'''


def _limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (int(TIME_LIMIT) + 1, int(TIME_LIMIT) + 2))
    except Exception:
        pass


# macOS: ядро деңгейіндегі екінші қорғаныс қабаты (audit hook-ты айналып өтсе де жұмыс істейді).
# Желі жабық, Python-нан басқа бағдарлама іске қосылмайды, тек өз уақытша папкасына жазады,
# /Users ішінен (сайттың дерекқоры, кілт, мұғалімнің файлдары) тек Python орнатылған папканы оқи алады.
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SANDBOX_PROFILE = r'''
(version 1)
(allow default)
(deny network*)
(deny process-exec)
(allow process-exec (literal (param "PY")) (subpath (param "BASE")))
(deny file-write*)
(allow file-write* (subpath (param "RUN")) (literal "/dev/null") (literal "/dev/tty"))
(deny file-read-data (subpath "/Users") (subpath "/Volumes") (subpath (param "TMP")))
(allow file-read-data (subpath (param "RUN")) (subpath (param "VENV")) (subpath (param "BASE")))
'''


def _sandbox_cmd(run_dir: str) -> list:
    py = sys.executable
    cmd = [py, "-I", "_guard.py"]
    if sys.platform != "darwin" or not os.path.exists(SANDBOX_EXEC) or os.environ.get("CODE_SANDBOX") == "off":
        return cmd
    run = os.path.realpath(run_dir)
    params = {"PY": py, "RUN": run, "TMP": os.path.dirname(run),
              "VENV": os.path.realpath(sys.prefix), "BASE": os.path.realpath(sys.base_prefix)}
    return [SANDBOX_EXEC, "-p", SANDBOX_PROFILE] + [a for k, v in params.items() for a in ("-D", f"{k}={v}")] + cmd


def run_code(code: str, stdin: str = "", files: dict | None = None) -> dict:
    """Кодты іске қосып, нәтижесін қайтарады: {ok, stdout, stderr, timeout}."""
    with tempfile.TemporaryDirectory(prefix="run_") as d:
        with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(d, "_guard.py"), "w", encoding="utf-8") as f:
            f.write(GUARD)
        for name, content in (files or {}).items():
            safe = os.path.basename(name)
            with open(os.path.join(d, safe), "w", encoding="utf-8") as f:
                f.write(content)
        env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "PATH": os.environ.get("PATH", "")}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        try:
            p = subprocess.run(
                _sandbox_cmd(d),
                input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIME_LIMIT, cwd=d, env=env,
                preexec_fn=_limits if os.name != "nt" else None,
            )
            err = _clean_trace(p.stderr)
            return {"ok": p.returncode == 0, "stdout": p.stdout[:MAX_OUTPUT], "stderr": err[:MAX_OUTPUT], "timeout": False}
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return {"ok": False, "stdout": out[:MAX_OUTPUT],
                    "stderr": f"Уақыт шегі асып кетті ({TIME_LIMIT:g} с). Шексіз цикл жоқ па?", "timeout": True}


def _clean_trace(err: str) -> str:
    """Traceback-тен қызметтік жолдарды алып тастап, оқушыға тек өз кодын көрсету."""
    if not err:
        return ""
    out = []
    seen_main = False
    for ln in err.splitlines():
        if set(ln.strip()) <= set("~^ ") and ln.strip():
            continue  # ~~~^^^ белгілері
        if ln.startswith("Traceback"):
            out.append("Қате (Traceback):")
            continue
        if 'File "main.py"' in ln:
            seen_main = True
        if ln.startswith("  ") and not seen_main:
            continue  # _guard.py ішкі жолдары
        out.append(ln.replace('File "main.py", line', "Жол").replace(", in <module>", ""))
    return "\n".join(out)


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip().splitlines())


def check_code(code: str, tests: list, files: dict | None = None) -> dict:
    """Тест-кейстер бойынша тексеру. tests = [{"input": "...", "output": "..."}]"""
    results = []
    passed = 0
    for i, t in enumerate(tests):
        r = run_code(code, t.get("input", ""), files)
        ok = r["ok"] and _norm(r["stdout"]) == _norm(t.get("output", ""))
        passed += ok
        hidden = t.get("hidden", False)
        results.append({
            "n": i + 1, "ok": ok, "hidden": hidden,
            "input": None if hidden else t.get("input", ""),
            "expected": None if hidden else t.get("output", ""),
            "got": None if hidden else r["stdout"][:2000],
            "error": r["stderr"][-1500:] if r["stderr"] else "",
        })
        if r.get("timeout"):
            # қалған тесттерді де уақыт шегі деп белгілеу (уақыт үнемдеу)
            for j in range(i + 1, len(tests)):
                results.append({"n": j + 1, "ok": False, "hidden": tests[j].get("hidden", False),
                                "input": None, "expected": None, "got": None, "error": "Орындалмады"})
            break
    return {"passed": passed, "total": len(tests), "results": results}
