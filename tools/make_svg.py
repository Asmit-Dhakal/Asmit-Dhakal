"""
Generates dark_mode.svg and light_mode.svg.

    python tools/make_svg.py                  # placeholder "AD" art
    python tools/make_svg.py --image me.jpg   # ASCII-fy your own photo
    python tools/make_svg.py --image me.jpg --invert   # if the subject looks inverted

Edit the PROFILE section below to change the static text. Dynamic fields
(ids ending in _data / _add / _del) are rewritten by today.py on every run.
Each dynamic <tspan> carries data-width so today.py knows how many dots to
draw; the layout math below keeps every line exactly LINE_W characters wide.
"""
import argparse
import os
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- PROFILE ---
HANDLE = "asmit@dhakal"

# (key, value) static rows. Section headers are plain strings.
PROFILE = [
    ("OS", "Ubuntu Linux"),
    ("Uptime", None),  # dynamic: age, from the BIRTHDAY env var
    ("Role", "Backend Developer, Computer Engineer"),
    ("Location", "Nepal"),
    ("Shell", "fish"),
    "",
    ("Languages", "Python, C, C++, Java, SQL, Bash"),
    ("Frontend", "HTML, CSS, Tailwind, JavaScript"),
    ("Backend", "Django, DRF, Celery, Flask"),
    ("Data", "PostgreSQL, MySQL, Redis, MongoDB"),
    ("Infra", "Docker, Linux, Git, uv"),
    ("ML", "PyTorch, TensorFlow, scikit-learn"),
    "",
    "- Contact",
    ("Email", "asmitdhakal123@gmail.com"),
    ("LinkedIn", "asmitdhakal"),
    ("Website", "asmitdhakal.com.np"),
    "",
    "- GitHub Stats",
]
# ------------------------------------------------------------------------ #

LINE_W = 58          # characters per right-hand line (budgeted for ~10px/char fallback fonts)
CHAR_W = 9.6         # px per char at 16px monospace
LINE_H = 20          # px between right-hand lines
RIGHT_X = 380
ART_FONT = 10                      # px; monospace cell is ~0.6em wide
CELL_W = ART_FONT * 0.602
ART_X, ART_STEP, ART_COLS, ART_ROWS = 15, 12, 57, 40
WIDTH, HEIGHT = 1000, 530

THEMES = {
    "dark_mode": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                      add="#3fb950", dele="#f85149", cc="#616e7f", art="#8b949e"),
    "light_mode": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                       add="#1a7f37", dele="#cf222e", cc="#8c959f", art="#6e7781"),
}

RAMP = " .,:;-=+*#%@"


def crop_to_art(img: Image.Image, focus=0.5, vfocus=0.5, zoom=1.0) -> Image.Image:
    """Crop to the art area's aspect ratio (cells are CELL_W x ART_STEP px).
    focus = horizontal centre of the crop as a fraction of image width."""
    target = (ART_COLS * CELL_W) / (ART_ROWS * ART_STEP)
    w, h = img.size
    # largest box with the target aspect, shrunk by zoom (<1 = tighter), centred on (focus, vfocus)
    bw, bh = (h * target, h) if w / h > target else (w, w / target)
    bw, bh = bw * zoom, bh * zoom
    x = min(max(w * focus - bw / 2, 0), w - bw)
    y = min(max(h * vfocus - bh / 2, 0), h - bh)
    return img.crop((int(x), int(y), int(x + bw), int(y + bh)))


def to_ascii(img: Image.Image, invert=False, gamma=1.0, equalize=False, floor=0) -> list[str]:
    img = img.convert("L")
    img = ImageOps.equalize(img) if equalize else ImageOps.autocontrast(img, cutoff=2)
    if invert:
        img = ImageOps.invert(img)
    if gamma != 1.0:
        img = img.point(lambda p: int(255 * (p / 255) ** gamma))
    img = img.resize((ART_COLS * 4, ART_ROWS * 4), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=6, percent=180, threshold=2))
    img = img.resize((ART_COLS, ART_ROWS), Image.LANCZOS)
    if floor:  # blank out faint background specks
        img = img.point(lambda p: 0 if p < floor else p)
    px = img.load()
    rows = []
    for y in range(ART_ROWS):
        row = "".join(RAMP[px[x, y] * (len(RAMP) - 1) // 255] for x in range(ART_COLS))
        rows.append(row.rstrip())
    return rows


def placeholder_art() -> list[str]:
    # char cells are ~1:2, so render at 2x width ratio before squashing
    w, h = 1000, int(1000 * ART_ROWS * ART_STEP / (ART_COLS * CELL_W))
    img = Image.new("L", (w, h), 0)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 520)
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), "AD", font=font)
    d.text(((w - (box[2] - box[0])) / 2 - box[0], (h - (box[3] - box[1])) / 2 - box[1]),
           "AD", fill=255, font=font)
    return to_ascii(img)


def tspan(text, cls=None, **attrs):
    a = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    c = f' class="{cls}"' if cls else ""
    return f"<tspan{c}{a}>{escape(text)}</tspan>"


def dots(n):
    return " " + "." * n + " " if n > 2 else {0: "", 1: " ", 2: ". "}[n]


def fill(n):
    """Exactly n characters of leader."""
    return " " * n if n <= 2 else " " + "." * (n - 2) + " "


def static_row(key, value, prefix=". "):
    n = LINE_W - len(prefix) - len(key) - 1 - len(value)
    return (tspan(prefix) + tspan(key + ":", "key") + tspan(fill(n), "cc")
            + tspan(value, "value"))


def dyn(id_, width, cls="value", init="0", minus=None):
    """Dotted dynamic field: dots tspan + value tspan.
    today.py draws (width - len(value)) dots; `minus` lists other element ids whose
    text length is subtracted from width, which keeps the line's right edge fixed."""
    extra = {"data_minus": minus} if minus else {}
    return (tspan(dots(width - len(init)), "cc", id=f"{id_}_dots")
            + tspan(init, cls, id=id_, data_width=width, **extra))


def build_rows():
    rows = []
    rows.append(tspan(HANDLE, "key") + tspan(" " + "-" * (LINE_W - len(HANDLE) - 1), "cc"))
    for item in PROFILE:
        if item == "":
            rows.append("")
        elif isinstance(item, str):
            rows.append(tspan(item + " ", None) + tspan("-" * (LINE_W - len(item) - 1), "cc"))
        else:
            key, value = item
            if value is None:  # Uptime
                prefix = ". "
                w = LINE_W - len(prefix) - len(key) - 1 - 2
                rows.append(tspan(prefix) + tspan(key + ":", "key")
                            + tspan(dots(w - len("0 years")), "cc", id="age_data_dots")
                            + tspan("0 years", "value", id="age_data", data_width=w))
            else:
                rows.append(static_row(key, value))

    # Stats block. Pipes are aligned: contributed field is padded to 3 chars.
    # A: ". Repos:" + (L1+2) + " {Contributed: " + 3 + "}" + " | Stars:" + (L3+2)
    # B: ". Commits:" + (L2+2) + " " + " | Followers:" + (L4+2)
    b_pre = len(". Commits:")
    L1 = 8
    pipe_col = len(". Repos:") + L1 + 2 + len(" {Contributed: ") + 3 + len("}")  # contributed budgeted at 3 chars
    L2 = pipe_col - b_pre - 2
    L3 = LINE_W - (pipe_col + len(" | Stars:")) - 2
    L4 = LINE_W - (pipe_col + len(" | Followers:")) - 2

    rows.append(tspan(". ") + tspan("Repos:", "key") + dyn("repo_data", L1 + 3, minus="contrib_data")
                + tspan(" {") + tspan("Contributed", "key") + tspan(": ")
                + tspan("0", "value", id="contrib_data") + tspan("}")
                + tspan(" | ") + tspan("Stars:", "key") + dyn("star_data", L3))
    rows.append(tspan(". ") + tspan("Commits:", "key") + dyn("commit_data", L2)
                + tspan(" " * 0) + tspan(" | ") + tspan("Followers:", "key")
                + dyn("follower_data", L4))
    # LOC line: ". Lines of Code on GitHub: ..... 0 ( 0++, 0-- )"
    pre = ". Lines of Code:"
    tail_fixed = len(" ( ") + len("++, ") + len("--") + len(" )")
    add_w, del_w = 9, 8
    loc_w = LINE_W - len(pre) - 2 - tail_fixed - add_w - del_w - 2
    rows.append(tspan(". ") + tspan("Lines of Code:", "key")
                + dyn("loc_data", loc_w + add_w + del_w, minus="loc_add,loc_del")
                + tspan(" ( ") + tspan("0", "addColor", id="loc_add")
                + tspan("++", "addColor") + tspan(", ") + tspan("0", "delColor", id="loc_del")
                + tspan("--", "delColor") + tspan(" )"))
    return rows


def render(theme_name, art_lines, rows):
    t = THEMES[theme_name]
    out = [f'<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" font-family="Consolas, \'DejaVu Sans Mono\', \'Liberation Mono\', \'Courier New\', monospace" '
           f'width="{WIDTH}px" height="{HEIGHT}px" font-size="16px">',
           "<style>",
           f".key {{fill: {t['key']};}}",
           f".value {{fill: {t['value']};}}",
           f".addColor {{fill: {t['add']};}}",
           f".delColor {{fill: {t['dele']};}}",
           f".cc {{fill: {t['cc']};}}",
           f"text, tspan {{white-space: pre;}}",
           "</style>",
           f'<rect width="{WIDTH}px" height="{HEIGHT}px" fill="{t["bg"]}" rx="15"/>']
    out.append(f'<text x="{ART_X}" y="30" fill="{t["art"]}" font-size="{ART_FONT}px" xml:space="preserve">')
    for i, line in enumerate(art_lines):
        out.append(f'<tspan x="{ART_X}" y="{30 + i * ART_STEP}">{escape(line)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{RIGHT_X}" y="30" fill="{t["text"]}" xml:space="preserve">')
    for i, row in enumerate(rows):
        out.append(f'<tspan x="{RIGHT_X}" y="{30 + i * LINE_H}">{row}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--focus", type=float, default=0.5, help="horizontal crop centre, 0-1")
    ap.add_argument("--vfocus", type=float, default=0.5, help="vertical crop centre, 0-1")
    ap.add_argument("--zoom", type=float, default=1.0, help="<1 crops tighter (face close-up)")
    ap.add_argument("--equalize", action="store_true", help="histogram-equalize for faint faces")
    ap.add_argument("--floor", type=int, default=0, help="0-255; pixels below this become blank")
    ap.add_argument("--gamma", type=float, default=1.0, help=">1 darkens midtones")
    args = ap.parse_args()
    art = (to_ascii(crop_to_art(Image.open(args.image), args.focus, args.vfocus, args.zoom),
              args.invert, args.gamma, args.equalize, args.floor)
           if args.image else placeholder_art())
    rows = build_rows()
    for name in THEMES:
        path = os.path.join(ROOT, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(name, art, rows))
        print("wrote", path)
