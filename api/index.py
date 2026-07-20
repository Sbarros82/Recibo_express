import os
import sys

# Garante que o Flask encontre app.py, templates/ e static/ na raiz do projeto.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)

from app import app  # noqa: E402
