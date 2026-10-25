"""Read PDFs into pages of positioned words.

Text PDFs are read with pdfplumber. A page with (almost) no text is treated as a
scan: it is rendered with Poppler, straightened, cleaned up, and read with
Tesseract. Either way every page comes back as a list of Word objects in PDF
points (1/72 inch, origin top-left), so the extractors don't care which path
was used.

Everything runs locally. Nothing is sent anywhere.
"""
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pdfplumber
from PIL import Image, ImageFilter

OCR_DPI = 400
MIN_TEXT_CHARS = 25          # fewer characters than this on a page -> OCR it


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def mid_y(self):
        return (self.top + self.bottom) / 2


@dataclass
class Page:
    doc: str                  # file name
    number: int               # 1-based
    words: list
    ocr: bool = False
    width: float = 612
    height: float = 792
    image: object = None      # cleaned binary image (OCR pages only), for checkbox checks
    scale: float = 1.0        # image pixels per PDF point
    lazy_path: str = None     # set when an OCR page came from the cache (image not kept)

    @property
    def text(self):
        return "\n".join(" ".join(w.text for w in row) for row in rows(self.words))


def rows(words, tol=4.0):
    """Group words into visual rows (sorted top to bottom, then left to right)."""
    out = []
    for w in sorted(words, key=lambda w: w.mid_y):
        if out and abs(w.mid_y - out[-1][0]) <= tol:
            out[-1][1].append(w)
            n = len(out[-1][1])
            out[-1][0] = (out[-1][0] * (n - 1) + w.mid_y) / n
        else:
            out.append([w.mid_y, [w]])
    return [sorted(r, key=lambda w: w.x0) for _, r in out]


# ---------------------------------------------------------------------
# Tool locations (Windows installs put these outside PATH)
# ---------------------------------------------------------------------
def find_poppler():
    if os.environ.get("POPPLER_PATH"):
        return os.environ["POPPLER_PATH"]
    exe = shutil.which("pdftoppm")
    if exe:
        return str(Path(exe).parent)
    for base in [Path.home() / "AppData/Local/Microsoft/WinGet/Packages", Path("C:/Program Files")]:
        for hit in base.glob("*oppler*/**/pdftoppm.exe"):
            return str(hit.parent)
    return None


def find_tesseract():
    if os.environ.get("TESSERACT_CMD"):
        return os.environ["TESSERACT_CMD"]
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for p in [Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
              Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe"]:
        if p.exists():
            return str(p)
    return None


# ---------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------
def read_pdf(path, cache_dir=None):
    """Return a list of Page objects for one PDF."""
    path = Path(path)
    cached = _cache_load(path, cache_dir)
    if cached is not None:
        return cached
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages, 1):
            if len(pg.chars) >= MIN_TEXT_CHARS:
                # Diagonal watermarks ("SAMPLE", "DRAFT", "COPY") are drawn as rotated characters and
                # would otherwise glue stray letters onto real words; keep upright text only.
                upright = pg.filter(lambda o: o.get("object_type") != "char" or (
                    abs(o["matrix"][1]) < 1e-3 and abs(o["matrix"][2]) < 1e-3))
                words = [Word(w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                         for w in upright.extract_words(x_tolerance=1.5, y_tolerance=2)]
                pages.append(Page(path.name, i, words, False, float(pg.width), float(pg.height)))
            else:
                pages.append(ocr_page(path, i, float(pg.width), float(pg.height)))
    _cache_save(path, cache_dir, pages)
    return pages


def tesseract():
    """pytesseract, pointed at the local Tesseract install."""
    import pytesseract
    tess = find_tesseract()
    if not tess:
        raise RuntimeError("Tesseract is not installed; it is needed for scanned pages. See README.")
    pytesseract.pytesseract.tesseract_cmd = tess
    return pytesseract


def ocr_page(path, number, width, height):
    from pdf2image import convert_from_path

    pytesseract = tesseract()
    img = convert_from_path(str(path), dpi=OCR_DPI, first_page=number, last_page=number,
                            grayscale=True, poppler_path=find_poppler())[0]
    img = clean_scan(img.convert("L"))
    scale = img.width / width
    # Two passes, merged: psm 4 (column of variable-size text) keeps every form row; psm 6
    # (uniform block) sometimes reads values psm 4 misses. Words from the second pass are
    # added only where the first pass found nothing.
    words = _tess_words(pytesseract, img, scale, 4)
    for w in _tess_words(pytesseract, img, scale, 6):
        if not any(_overlap(w, v) for v in words):
            words.append(w)
    return Page(Path(path).name, number, words, True, width, height, image=img, scale=scale)


def _tess_words(pytesseract, img, scale, psm):
    data = pytesseract.image_to_data(img, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    out = []
    for t, x, y, w, h, conf in zip(data["text"], data["left"], data["top"], data["width"], data["height"], data["conf"]):
        t = t.strip()
        if t and float(conf) >= 0:
            out.append(Word(t, x / scale, y / scale, (x + w) / scale, (y + h) / scale))
    return out


def _overlap(a, b):
    ix = min(a.x1, b.x1) - max(a.x0, b.x0)
    iy = min(a.bottom, b.bottom) - max(a.top, b.top)
    if ix <= 0 or iy <= 0:
        return False
    return ix * iy >= 0.3 * min((a.x1 - a.x0) * (a.bottom - a.top), (b.x1 - b.x0) * (b.bottom - b.top))


def clean_scan(img):
    """Straighten a slightly rotated scan, make it black-on-white, and erase form rules.

    Box borders and long ruled lines confuse Tesseract (amounts inside boxes get
    dropped or merged with the border), so runs of ink longer than ~1/5 inch in
    either direction are removed. Letters and digits are much shorter than that.
    """
    img = img.filter(ImageFilter.MedianFilter(3))
    img = img.rotate(skew_angle(img), resample=Image.BICUBIC, expand=False, fillcolor=255)
    a = np.asarray(img).astype(np.float32)
    ink = a < 165
    dpi = img.width / 8.5
    rules = _long_runs(ink, int(dpi * 0.2), axis=1) | _long_runs(ink, int(dpi * 0.2), axis=0)
    a[_grow(rules, 2)] = 255
    # stretch contrast (paper -> white, ink -> black) but keep gray edges for Tesseract
    a = np.clip((a - 60) * 255.0 / (225 - 60), 0, 255)
    return Image.fromarray(a.astype(np.uint8))


def _long_runs(mask, k, axis):
    """Pixels that belong to a straight run of >= k ink pixels along `axis`."""
    m = mask if axis == 1 else mask.T
    cs = np.concatenate([np.zeros((m.shape[0], 1), np.int32), np.cumsum(m, axis=1, dtype=np.int32)], axis=1)
    full = (cs[:, k:] - cs[:, :-k]) == k                     # window starting at i is all ink
    starts = np.concatenate([np.zeros((m.shape[0], 1), np.int32), np.cumsum(full, axis=1, dtype=np.int32)], axis=1)
    out = np.zeros_like(m)
    n = m.shape[1]
    # pixel j is covered if any full window starts in [j-k+1, j]
    hi = np.minimum(np.arange(n) + 1, full.shape[1])
    lo = np.clip(np.arange(n) - k + 1, 0, full.shape[1])
    out = (starts[:, hi] - starts[:, lo]) > 0
    return out if axis == 1 else out.T


def _grow(mask, r):
    """Dilate a boolean mask by r pixels (so the anti-aliased edges of rules go too)."""
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def skew_angle(img, limit=2.5, step=0.1):
    """Angle (degrees) that makes text rows most horizontal (projection-profile method)."""
    small = img.resize((img.width // 4, img.height // 4))
    best, best_score = 0.0, -1.0
    for ang in np.arange(-limit, limit + 1e-9, step):
        r = small.rotate(float(ang), resample=Image.BILINEAR, fillcolor=255)
        dark = (np.asarray(r) < 140).sum(axis=1).astype(np.float64)
        score = float(np.var(dark))
        if score > best_score:
            best, best_score = float(ang), score
    return best


# ---------------------------------------------------------------------
# Optional on-disk cache of OCR results (off by default; tests turn it on).
# It holds extracted text, so only point it at a local, private folder.
# ---------------------------------------------------------------------
CACHE_VERSION = 2          # bump when reading logic changes so cached pages are re-read


def _key(path):
    return f"v{CACHE_VERSION}_" + hashlib.sha256(Path(path).read_bytes()).hexdigest()[:32]


def _cache_load(path, cache_dir):
    if not cache_dir:
        return None
    f = Path(cache_dir) / f"{_key(path)}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    # Checkbox detection on scans needs the image; page_image() re-renders it on demand.
    return [Page(Path(path).name, p["number"], [Word(*w) for w in p["words"]], p["ocr"], p["width"], p["height"],
                 lazy_path=str(path) if p["ocr"] else None) for p in data]


def _cache_save(path, cache_dir, pages):
    if not cache_dir:
        return
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    data = [{"number": p.number, "ocr": p.ocr, "width": p.width, "height": p.height,
             "words": [[w.text, w.x0, w.top, w.x1, w.bottom] for w in p.words]} for p in pages]
    (Path(cache_dir) / f"{_key(path)}.json").write_text(json.dumps(data), encoding="utf-8")


def page_image(page):
    """Cleaned image for an OCR page (re-rendered if the page came from the cache)."""
    if page.image is None and page.lazy_path:
        from pdf2image import convert_from_path
        img = convert_from_path(page.lazy_path, dpi=OCR_DPI, first_page=page.number, last_page=page.number,
                                grayscale=True, poppler_path=find_poppler())[0]
        page.image = clean_scan(img.convert("L"))
        page.scale = page.image.width / page.width
    return page.image
