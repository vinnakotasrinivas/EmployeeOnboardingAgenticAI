"""Generate negative test files for the ingestion pipeline.

Outputs (in docs/sample_data/):
  irrelevant/  valid formats with no onboarding content (must be rejected by the relevance gate)
  invalid/     unsupported, empty, spoofed or corrupt files (must be rejected by the validator)

Run: uv run python scripts/make_test_files.py [--oversize]
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import zipfile
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "sample_data"
SEED = 20261025
OVERSIZE_BYTES = 20 * 1024 * 1024

PASTA_RECIPE = """Classic Spaghetti Carbonara (serves 4)

Ingredients
- 400 g spaghetti
- 150 g guanciale or pancetta, cut into strips
- 4 egg yolks and 1 whole egg
- 60 g Pecorino Romano, finely grated, plus extra to serve
- Freshly ground black pepper

Method
1. Bring a large pot of salted water to the boil and cook the spaghetti until al dente.
2. Meanwhile, fry the guanciale in a dry pan over medium heat until crisp, about 8 minutes.
3. Whisk the yolks, whole egg and Pecorino with plenty of black pepper.
4. Reserve a cup of pasta water, drain the spaghetti and add it to the guanciale pan off the heat.
5. Pour in the egg mixture and toss quickly, adding pasta water a splash at a time until glossy.
6. Serve immediately with extra Pecorino and pepper.

Tip: never add cream. The sauce comes from the eggs, cheese and starchy pasta water.
"""

FOOTBALL_RULES = [
    ("Rules of Association Football: A Summary", "title"),
    ("The field and the ball", "h"),
    ("Matches are played on a rectangular grass or artificial pitch between 90 and 120 metres long. "
     "The ball is spherical with a circumference of 68 to 70 cm.", "p"),
    ("Players and duration", "h"),
    ("Each team fields eleven players, one of whom is the goalkeeper. A match lasts two halves of "
     "45 minutes with a half-time interval of no more than 15 minutes.", "p"),
    ("Offside", "h"),
    ("A player is in an offside position if any part of the head, body or feet is in the opponent's half "
     "and nearer to the opponent's goal line than both the ball and the second-last opponent.", "p"),
    ("Fouls and misconduct", "h"),
    ("Direct free kicks are awarded for careless, reckless or excessive challenges. Referees show a "
     "yellow card for a caution and a red card for a sending-off.", "p"),
    ("Scoring", "h"),
    ("A goal is scored when the whole ball passes over the goal line between the posts and under the "
     "crossbar. The team with more goals wins; competitions may use extra time and penalties.", "p"),
]


def write_irrelevant(out: Path, rng: random.Random) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "pasta_recipe.txt").write_text(PASTA_RECIPE, encoding="utf-8", newline="\n")

    with (out / "quarterly_sales.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["quarter", "region", "product", "units_sold", "revenue_usd", "gross_margin_pct"])
        for quarter in ("2026-Q1", "2026-Q2", "2026-Q3"):
            for region in ("North America", "EMEA", "APAC"):
                for product in ("Starter", "Growth", "Enterprise"):
                    units = rng.randint(40, 900)
                    price = {"Starter": 1200, "Growth": 4800, "Enterprise": 21000}[product]
                    w.writerow([quarter, region, product, units, units * price, round(rng.uniform(62, 81), 1)])

    styles = getSampleStyleSheet()
    style_for = {"title": styles["Title"], "h": styles["Heading2"], "p": styles["BodyText"]}
    doc = SimpleDocTemplate(str(out / "football_rules.pdf"), pagesize=A4, title="Football rules")
    story = []
    for text, kind in FOOTBALL_RULES:
        story += [Paragraph(text, style_for[kind]), Spacer(1, 4)]
    doc.build(story)


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (31, 58, 95)).save(buf, format="JPEG")
    return buf.getvalue()


def write_invalid(out: Path, rng: random.Random, oversize: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    jpeg = _jpeg_bytes()
    (out / "photo.jpg").write_bytes(jpeg)
    (out / "fake_pdf.pdf").write_bytes(jpeg)
    (out / "empty.txt").write_bytes(b"")
    (out / "corrupt.pdf").write_bytes(b"%PDF-1.4\n" + rng.randbytes(2048))
    (out / "slides.pptx").write_bytes(b"PK\x03\x04" + rng.randbytes(512))
    (out / "macro_book.xlsm").write_bytes(b"PK\x03\x04" + rng.randbytes(512))

    with zipfile.ZipFile(out / "archive.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("first_week_faq.txt", (OUT / "txt" / "first_week_faq.txt").read_bytes())

    oversize_path = out / "oversize.pdf"
    if oversize:
        header = b"%PDF-1.4\n% padded test file larger than the 19 MB upload limit\n"
        with oversize_path.open("wb") as f:
            f.write(header)
            f.write(b"0" * (OVERSIZE_BYTES - len(header)))
    elif oversize_path.exists():
        oversize_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--oversize", action="store_true", help="also create a 20 MB oversize.pdf")
    args = parser.parse_args()

    if not (OUT / "txt" / "first_week_faq.txt").exists():
        raise SystemExit("Run scripts/generate_sample_data.py first.")

    rng = random.Random(SEED)
    write_irrelevant(OUT / "irrelevant", rng)
    write_invalid(OUT / "invalid", rng, args.oversize)

    for f in sorted((OUT / "irrelevant").iterdir()) + sorted((OUT / "invalid").iterdir()):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
