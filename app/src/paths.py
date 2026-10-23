"""Where everything lives. Change a folder location here and nowhere else.

Tax Scanner/
  inputs/clients/          real client folders (private, never committed)
  inputs/sample_clients/   the 24 fictional test clients
  outputs/                 graded runs
  netlify_site/site/       the public demo site;  netlify_site/tax-scan-site.zip = upload file
  app/                     code, config, tests (this package lives in app/src)
"""
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent

INPUTS = ROOT / "inputs"
CLIENTS = INPUTS / "clients"
SAMPLE_CLIENTS = INPUTS / "sample_clients"
OUTPUTS = ROOT / "outputs"
WEB_RUNS = OUTPUTS / "web"

NETLIFY = ROOT / "netlify_site"
SITE = NETLIFY / "site"
SITE_ZIP = NETLIFY / "tax-scan-site.zip"

CONFIG = APP / "config" / "grader.yaml"
STARTER = APP / "starter"
