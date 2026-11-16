"""deck.src.html → infolab-qorgau.html: PT Sans Narrow қаріптерін base64 ретінде ендіреді (интернетсіз ашылуы үшін)."""
import base64, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RANGES = {
    "cyrillic-ext": "U+0460-052F,U+1C80-1C8A,U+20B4,U+2DE0-2DFF,U+A640-A69F,U+FE2E-FE2F",
    "cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
}
css = []
for sub, rng in RANGES.items():
    for w in (400, 700):
        data = base64.b64encode(open(os.path.join(HERE, "fonts", f"pt-{sub}-{w}.woff2"), "rb").read()).decode()
        css.append(f'@font-face{{font-family:"PT Sans Narrow";font-weight:{w};font-display:block;'
                   f'src:url(data:font/woff2;base64,{data}) format("woff2");unicode-range:{rng}}}')
# Әдепкі: слайдтар. Басқа файл үшін: python3 build_deck.py video/story.src.html video/story.html
src_path, out_path = (sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else ("deck.src.html", "infolab-qorgau.html")
src = open(os.path.join(HERE, src_path), encoding="utf-8").read()
open(os.path.join(HERE, out_path), "w", encoding="utf-8").write(src.replace("/*FONTS*/", "\n".join(css), 1))
print("ok", os.path.getsize(os.path.join(HERE, out_path)))
