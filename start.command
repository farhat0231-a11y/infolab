#!/bin/bash
# InfoLab — macOS-та екі рет басып іске қосу
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 табылмады. https://www.python.org/downloads/ сайтынан орнатыңыз да, қайта ашыңыз."
  read -p "Жабу үшін Enter басыңыз..."; exit 1
fi
if [ ! -d .venv ]; then
  echo "Алғашқы іске қосу: кітапханалар орнатылуда (интернет керек)..."
  python3 -m venv .venv || { read -p "venv құрылмады. Enter..."; exit 1; }
  .venv/bin/pip install -q -r requirements.txt || { read -p "Орнату сәтсіз. Интернетті тексеріңіз. Enter..."; exit 1; }
  .venv/bin/python seed_demo.py
fi
IP=$(ipconfig getifaddr en0 2>/dev/null)
HOST=$(scutil --get LocalHostName 2>/dev/null)
# 80-ші порт бос болса, мекенжай портсыз болады; бос болмаса app.py өзі 8080-ге ауысады
if lsof -nP -iTCP:80 -sTCP:LISTEN >/dev/null 2>&1; then P=":8080"; else P=""; fi
echo ""
echo "  Сайт ашылуда: http://localhost$P"
[ -n "$HOST" ] && echo "  Оқушылар үшін (тұрақты атау): http://$HOST.local$P"
[ -n "$IP" ] && echo "  Немесе IP арқылы: http://$IP$P"
echo "  Тоқтату үшін осы терезені жабыңыз."
echo ""
(sleep 2; open "http://localhost$P") &
.venv/bin/python app.py
