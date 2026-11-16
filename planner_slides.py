"""Слайдтарды markdown-нан HTML-ға айналдыру (Python коды түсті, интернетсіз) және теориядан слайд жасау."""
import html
import keyword
import re

import markdown as md

KW = set(keyword.kwlist) - {"True", "False", "None"}
BUILTINS = {"print", "input", "range", "len", "int", "str", "float", "list", "dict", "set", "tuple", "bool",
            "sum", "min", "max", "abs", "round", "sorted", "enumerate", "zip", "open", "type"}
TOKEN = re.compile(r'''(?P<com>\#[^\n]*)|(?P<str>[rbfRBF]{0,2}(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\n]*"|'[^'\n]*'))'''
                   r'''|(?P<num>\b\d+(?:\.\d+)?\b)|(?P<id>[A-Za-z_]\w*)''')


def highlight_python(code):
    """Python кодының түсті жарығы: <span class="tk-..."> (CDN-сіз, regex арқылы)."""
    out, pos = [], 0
    for m in TOKEN.finditer(code):
        out.append(html.escape(code[pos:m.start()]))
        text, kind = html.escape(m.group()), m.lastgroup
        if kind == "id":
            w = m.group()
            kind = "kw" if w in KW else "bi" if w in BUILTINS else "lit" if w in ("True", "False", "None") else None
        out.append(f'<span class="tk-{kind}">{text}</span>' if kind else text)
        pos = m.end()
    out.append(html.escape(code[pos:]))
    return "".join(out)


_PRE = re.compile(r'<pre><code(?: class="language-([\w+-]+)")?>([\s\S]*?)</code></pre>')


def render(text):
    """Markdown → HTML: тақырып, тізім, кесте, код (Python түсті), сурет."""
    h = md.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists"])

    def sub(m):
        lang = (m.group(1) or "python").lower()
        code = html.unescape(m.group(2))
        body = highlight_python(code) if lang in ("python", "py") else html.escape(code)
        return f'<pre class="code"><code>{body}</code></pre>'
    return _PRE.sub(sub, h)


def _blocks(text):
    """Мәтінді бос жолдар бойынша блоктарға бөлу (``` ішіндегі бос жолдар бөлмейді)."""
    blocks, cur, fence = [], [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        if not line.strip() and not fence:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


REFLECT = {"kk": ("Рефлексия", "- Бүгін не үйрендім?\n- Не қиын болды?\n- Келесі сабаққа не білгім келеді?"),
           "ru": ("Рефлексия", "- Что я узнал сегодня?\n- Что было трудным?\n- Что хочу узнать дальше?")}


def from_theory(title, objectives, theory, lang="kk", limit=650):
    """Теория бөлімдерін (## тақырыпшалар) слайдтарға айналдыру: титул → бөлімдер → рефлексия."""
    slides = [{"phase": "start", "md": f"# {title}\n\n{objectives or ''}".strip(), "notes": ""}]
    parts = re.split(r"(?m)^##\s+", theory or "")
    intro, sections = parts[0].strip(), parts[1:]
    if intro and not sections:
        sections, intro = [f"{title}\n{intro}"], ""
    for sec in sections:
        head, _, body = sec.partition("\n")
        chunks, cur = [], ""
        for b in _blocks(body.strip()):
            if cur and len(cur) + len(b) > limit:
                chunks.append(cur)
                cur = b
            else:
                cur = f"{cur}\n\n{b}" if cur else b
        chunks.append(cur)
        for i, c in enumerate(chunks):
            suffix = f" ({i + 1}/{len(chunks)})" if len(chunks) > 1 else ""
            slides.append({"phase": "middle", "md": f"## {head.strip()}{suffix}\n\n{c}".strip(), "notes": ""})
    rt, rb = REFLECT[lang]
    slides.append({"phase": "end", "md": f"## {rt}\n\n{rb}", "notes": ""})
    return slides
