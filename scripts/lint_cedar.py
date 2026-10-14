#!/usr/bin/env python3
"""Linter de politicas Cedar (plantillas) para CI. Sin AWS, sin Terraform."""

import re
import sys
from pathlib import Path

KNOWN_PLACEHOLDERS = {"target", "gateway_arn", "account_id"}
STATEMENT_RE = re.compile(r"\b(permit|forbid)\s*\((.*?)\)\s*(when\s*\{.*?\}|unless\s*\{.*?\})?\s*;", re.S)


def strip_comments(text):
    return re.sub(r"//[^\n]*", "", text)


def balanced(text):
    pairs = {")": "(", "}": "{", "]": "["}
    stack = []
    in_str = False
    for i, ch in enumerate(text):
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "({[":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack and not in_str


def lint_text(text, label="<memoria>"):
    errors = []
    code = strip_comments(text)

    if not balanced(code):
        errors.append(f"{label}: parentesis, llaves o comillas sin balancear")

    for name in re.findall(r"\$\{(\w+)\}", code):
        if name not in KNOWN_PLACEHOLDERS:
            errors.append(f"{label}: placeholder desconocido ${{{name}}}")

    statements = list(STATEMENT_RE.finditer(code))
    if not statements:
        errors.append(f"{label}: no encontre ninguna politica permit/forbid")

    for m in statements:
        kind, head, clause = m.group(1), m.group(2), m.group(3) or ""
        if kind == "permit" and not clause.startswith("when"):
            errors.append(f"{label}: permit sin clausula `when` (el servicio lo rechaza por demasiado permisivo)")
        if not re.search(r"\baction\s*==", head):
            errors.append(f"{label}: falta `action ==` concreta")
        if not re.search(r"\bresource\s*==", head):
            errors.append(f"{label}: falta `resource ==` concreto")
        if not re.search(r"\bprincipal\s+is\s+\S+", head):
            errors.append(f"{label}: falta `principal is <tipo>`")
    return errors


def lint_paths(paths):
    errors = []
    files = []
    for p in paths:
        p = Path(p)
        files.extend(sorted(p.rglob("*.cedar")) if p.is_dir() else [p])
    if not files:
        errors.append("No encontre archivos .cedar")
    for f in files:
        errors.extend(lint_text(f.read_text(encoding="utf-8"), str(f)))
    return files, errors


def main(argv):
    root = Path(__file__).resolve().parent.parent
    paths = argv or sorted(str(p) for p in (root / "examples").glob("*/policies"))
    files, errors = lint_paths(paths)
    for e in errors:
        print(f"✗ {e}")
    print(f"{len(files)} archivo(s) revisado(s), {len(errors)} problema(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
