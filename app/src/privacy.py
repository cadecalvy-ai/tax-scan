"""Privacy helpers: SSN masking and the IRC 7216 consent check."""
import re
from pathlib import Path

import yaml

SSN_ANY = re.compile(r"\b\d{3}[-– ]?\d{2}[-– ]?(\d{4})\b")


def mask_ssn(text):
    """Replace every SSN-shaped number with ***-**-1234."""
    return SSN_ANY.sub(lambda m: f"***-**-{m.group(1)}", str(text))


def consent_from_file(folder):
    """Read consent_7216 from client.yaml in the client folder.

    Returns (True/False, explanation) or (None, explanation) when no file exists.
    """
    for name in ("client.yaml", "client.yml"):
        f = Path(folder) / name
        if f.exists():
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            val = data.get("consent_7216")
            if isinstance(val, bool):
                return val, f"{name}: consent_7216 = {str(val).lower()}"
            return False, f"{name}: consent_7216 missing or not true/false"
    return None, "no client.yaml"
