"""Small reportlab helpers for drawing tax-form-like pages.

Every page gets the fictional-data footer. Amounts are whole dollars.
"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

FOOTER = "SAMPLE — FICTIONAL TEST DATA — NOT A REAL RETURN"
W, H = letter
LEFT, RIGHT = 36, W - 36
BOX_W = 88                    # amount column width on 1040-style pages
BOX_X = RIGHT - BOX_W
NUM_W = 20                    # line-number cell left of the amount column


def money(v, show_zero=False):
    if v is None or (round(v) == 0 and not show_zero):
        return ""
    v = round(v)
    return f"({-v:,})" if v < 0 else f"{v:,}"


class Pdf:
    def __init__(self, path, title):
        self.c = canvas.Canvas(str(path), pagesize=letter)
        self.c.setTitle(title)
        self.c.setAuthor("Tax Scanner test-data generator (fictional)")
        self.page_no = 0
        self.y = H - 40
        self.open = False

    # -- pages ---------------------------------------------------------
    def new_page(self):
        if self.open:
            self._finish()
        self.page_no += 1
        self.open = True
        self.y = H - 40

    def _finish(self):
        c = self.c
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(W / 2, 20, FOOTER)
        c.setFont("Helvetica", 6.5)
        c.drawRightString(RIGHT, 20, f"Page {self.page_no}")
        c.showPage()
        self.open = False

    def save(self):
        if self.open:
            self._finish()
        self.c.save()

    def need(self, height, header=None):
        """Start a continuation page if fewer than `height` points remain."""
        if self.y - height < 50:
            self.new_page()
            if header:
                header()

    # -- text ----------------------------------------------------------
    def text(self, x, y, s, size=8, bold=False, align="left"):
        c = self.c
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "right":
            c.drawRightString(x, y, s)
        elif align == "center":
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def hline(self, y, x0=LEFT, x1=RIGHT, width=0.6):
        self.c.setLineWidth(width)
        self.c.line(x0, y, x1, y)

    def checkbox(self, x, y, checked, label="", size=7):
        c = self.c
        c.setLineWidth(0.6)
        c.rect(x, y - 1, 7, 7)
        if checked:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 1.2, y, "X")
        if label:
            self.text(x + 10, y, label, size)

    # -- form header ---------------------------------------------------
    def form_header(self, form, title, year, sub="Department of the Treasury—Internal Revenue Service",
                    omb="OMB No. 1545-0074", extra=None):
        """Classic IRS header: form number box | title | year box."""
        c, top = self.c, self.y + 8
        c.setLineWidth(1.2)
        c.line(LEFT, top - 44, RIGHT, top - 44)
        is_sched = form.startswith("SCHEDULE")
        if not is_sched and not form.startswith("Form"):
            self.text(LEFT, top - 14, "Form", 7)
        self.text(LEFT, top - 30, form, 15 if len(form) < 12 else 11, bold=True)
        if is_sched:
            self.text(LEFT, top - 40, "(Form 1040)", 7)
        self.text(W / 2, top - 14, title, 11, bold=True, align="center")
        self.text(W / 2, top - 25, sub, 7, align="center")
        if extra:
            self.text(W / 2, top - 35, extra, 6.5, align="center")
        self.text(RIGHT, top - 16, omb, 6.5, align="right")
        self.text(RIGHT, top - 34, str(year), 16, bold=True, align="right")
        self.y = top - 58

    def names_row(self, names, ssn):
        self.text(LEFT, self.y + 8, "Name(s) shown on return", 6)
        self.text(LEFT, self.y - 2, names, 9)
        self.text(RIGHT - 120, self.y + 8, "Your social security number", 6)
        self.text(RIGHT - 120, self.y - 2, ssn, 9)
        self.hline(self.y - 6)
        self.y -= 20

    def section(self, title):
        self.need(30)
        self.c.setFillGray(0.85)
        self.c.rect(LEFT, self.y - 3, RIGHT - LEFT, 12, stroke=0, fill=1)
        self.c.setFillGray(0)
        self.text(LEFT + 3, self.y, title, 8, bold=True)
        self.y -= 16

    # -- 1040-style line ----------------------------------------------
    def line(self, num, label, amount=None, show_zero=False, note="", indent=0, size=7.5, bold=False):
        """One numbered line: num | label ...... | num | amount."""
        self.need(14)
        c, y = self.c, self.y
        self.text(LEFT, y, num, size, bold=True)
        lx = LEFT + 24 + indent
        self.text(lx, y, label, size, bold=bold)
        end = lx + stringWidth(label, "Helvetica-Bold" if bold else "Helvetica", size) + 4
        if note:
            self.text(end, y, note, size - 0.5, bold=True)
            end += stringWidth(note, "Helvetica-Bold", size - 0.5) + 4
        c.setFont("Helvetica", size)
        dots_end = BOX_X - NUM_W - 4
        if end < dots_end:
            n = int((dots_end - end) / stringWidth(". ", "Helvetica", size))
            c.drawString(end, y, ". " * n)
        c.setLineWidth(0.5)
        c.rect(BOX_X - NUM_W, y - 3, NUM_W, 12)
        c.rect(BOX_X, y - 3, BOX_W, 12)
        self.text(BOX_X - NUM_W + 2, y, num, 7, bold=True)
        self.text(RIGHT - 3, y, money(amount, show_zero), 8.5, align="right")
        self.y -= 13

    def pair(self, na, la, va, nb, lb, vb, size=7.5, note=""):
        """Two-column line used for 2a/2b, 3a/3b, 4a/4b, 5a/5b, 6a/6b."""
        self.need(14)
        c, y = self.c, self.y
        mid = 290
        self.text(LEFT, y, na, size, bold=True)
        self.text(LEFT + 24, y, la, size)
        c.setLineWidth(0.5)
        c.rect(mid - NUM_W, y - 3, NUM_W, 12)
        c.rect(mid, y - 3, 74, 12)
        self.text(mid - NUM_W + 2, y, na, 7, bold=True)
        self.text(mid + 71, y, money(va), 8.5, align="right")
        self.text(mid + 80, y, "b", size, bold=True)
        if note:
            lb = lb.replace("Taxable amount", "Taxable amt")
        self.text(mid + 88, y, lb, size)
        if note:
            self.text(mid + 92 + stringWidth(lb, "Helvetica", size), y, note, 6.5, bold=True)
        c.rect(BOX_X - NUM_W, y - 3, NUM_W, 12)
        c.rect(BOX_X, y - 3, BOX_W, 12)
        self.text(BOX_X - NUM_W + 2, y, nb, 7, bold=True)
        self.text(RIGHT - 3, y, money(vb), 8.5, align="right")
        self.y -= 13

    # -- information-return cells -------------------------------------
    def cell(self, x, y, w, h, label, value="", vsize=9, lsize=5.8, align="left", shade=False):
        """A labelled box as on a W-2 or 1099. (x, y) is the top-left corner."""
        c = self.c
        if shade:
            c.setFillGray(0.92)
            c.rect(x, y - h, w, h, stroke=0, fill=1)
            c.setFillGray(0)
        c.setLineWidth(0.6)
        c.rect(x, y - h, w, h)
        lines = label.split("\n")
        for i, ln in enumerate(lines):
            self.text(x + 2, y - 7 - i * 6.5, ln, lsize)
        if value != "":
            vy = y - h + 4
            if align == "right":
                self.text(x + w - 4, vy, str(value), vsize, align="right")
            else:
                self.text(x + 4, vy, str(value), vsize)

    def multiline_cell(self, x, y, w, h, label, lines, vsize=8.5):
        self.cell(x, y, w, h, label)
        for i, ln in enumerate(lines):
            self.text(x + 4, y - 18 - i * 10, ln, vsize)
