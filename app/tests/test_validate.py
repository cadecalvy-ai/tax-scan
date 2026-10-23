"""Validation: mismatches become warnings, and the best-supported value is used."""
from src.extract import Fact
from src.record import new_year
from src.validate import analyze_year


def F(v, ref):
    return Fact(v, "test.pdf", 1, ref)


def test_ocr_misread_agi_is_outvoted_and_reported():
    yr = new_year()
    yr["f1040"] = {"9": F(131160, "Form 1040 line 9"), "10": F(0, "Form 1040 line 10"),
                   "11a": F(134160, "Form 1040 line 11a"), "11b": F(131160, "Form 1040 line 11b")}
    figs = analyze_year(2025, yr)
    assert figs.get("agi") == 131160
    assert any("AGI" in w and "134,160" in w for w in figs.warnings)


def test_source_documents_disagree_with_1040():
    yr = new_year()
    yr["f1040"] = {"1a": F(186500, "Form 1040 line 1a"), "1z": F(186500, "Form 1040 line 1z")}
    yr["sources"]["W-2"].append({"doc": "w2.pdf", "box1": F(186000, "W-2 box 1"), "box2": F(0, "W-2 box 2")})
    figs = analyze_year(2025, yr)
    assert any("Wages" in w and "186,000" in w and "186,500" in w for w in figs.warnings)


def test_missing_1040_lines_are_reported():
    yr = new_year()
    yr["f1040"] = {"1a": F(50000, "Form 1040 line 1a")}
    figs = analyze_year(2025, yr)
    assert any("not found" in w for w in figs.warnings)
