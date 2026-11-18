"""Minimal Liquid/Handlebars-style renderer (no dependencies).

Supported:
  {{ customer.first_name | default: "there" }}   dotted paths, filters
  filters: default, upcase, downcase, capitalize, money, raw
  {% if a.b %}..{% else %}..{% endif %}           also `not x`, `x == "s"`, `x != "s"`, `x > 3`, `x < 3`
  {% for item in cart.items %}..{% endfor %}      loop var plus `forloop.index`
Output of {{ }} is HTML-escaped unless the `raw` filter is applied.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

TOKEN = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)


class TemplateError(Exception):
    pass


class MissingVariable(TemplateError):
    pass


_MISSING = object()


def _lookup(path: str, scope: dict):
    cur = scope
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def _literal(tok: str, scope: dict):
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    try:
        return float(tok) if "." in tok else int(tok)
    except ValueError:
        v = _lookup(tok, scope)
        return None if v is _MISSING else v


def _parse(tokens: list[str], i: int, stop: tuple[str, ...]):
    nodes = []
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("{{"):
            nodes.append(("var", t[2:-2].strip()))
        elif t.startswith("{%"):
            tag = t[2:-2].strip()
            word = tag.split()[0] if tag else ""
            if word in stop:
                return nodes, i, word
            if word == "if":
                body, i, end = _parse(tokens, i + 1, ("else", "endif"))
                other = []
                if end == "else":
                    other, i, end = _parse(tokens, i + 1, ("endif",))
                if end != "endif":
                    raise TemplateError("unclosed {% if %}")
                nodes.append(("if", tag[2:].strip(), body, other))
            elif word == "for":
                m = re.fullmatch(r"for\s+(\w+)\s+in\s+([\w.]+)", tag)
                if not m:
                    raise TemplateError(f"bad for tag: {tag}")
                body, i, end = _parse(tokens, i + 1, ("endfor",))
                if end != "endfor":
                    raise TemplateError("unclosed {% for %}")
                nodes.append(("for", m.group(1), m.group(2), body))
            else:
                raise TemplateError(f"unknown tag: {tag}")
        else:
            nodes.append(("text", t))
        i += 1
    if stop:
        raise TemplateError(f"missing {stop[-1]}")
    return nodes, i, None


def _truthy(v) -> bool:
    return v is not _MISSING and bool(v)


def _eval_cond(expr: str, scope: dict) -> bool:
    expr = expr.strip()
    if expr.startswith("not "):
        return not _eval_cond(expr[4:], scope)
    m = re.fullmatch(r"(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+)", expr)
    if m:
        a, op, b = _literal(m.group(1), scope), m.group(2), _literal(m.group(3), scope)
        try:
            return {"==": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]
        except TypeError:
            return False
    return _truthy(_lookup(expr, scope))


def _split_filters(expr: str):
    parts, buf, q = [], "", None
    for ch in expr:
        if q:
            buf += ch
            q = None if ch == q else q
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch == "|":
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return parts


def _render_var(expr: str, scope: dict, strict: bool) -> str:
    base, *filters = _split_filters(expr)
    val = _lookup(base, scope) if not base[:1] in "\"'" else base[1:-1]
    raw = False
    has_default = False
    for f in filters:
        name, _, arg = f.partition(":")
        name = name.strip()
        if name == "default":
            has_default = True
            if val is _MISSING or val in (None, "", [], 0):
                val = _literal(arg, scope)
        elif name == "raw":
            raw = True
        elif val is _MISSING:
            continue
        elif name == "upcase":
            val = str(val).upper()
        elif name == "downcase":
            val = str(val).lower()
        elif name == "capitalize":
            val = str(val).capitalize()
        elif name == "money":
            val = f"${float(val):,.2f}"
        else:
            raise TemplateError(f"unknown filter: {name}")
    if val is _MISSING:
        if strict and not has_default:
            raise MissingVariable(base)
        return ""
    s = "" if val is None else str(val)
    return s if raw else html.escape(s)


def _render(nodes, scope: dict, strict: bool) -> str:
    out = []
    for n in nodes:
        if n[0] == "text":
            out.append(n[1])
        elif n[0] == "var":
            out.append(_render_var(n[1], scope, strict))
        elif n[0] == "if":
            out.append(_render(n[2] if _eval_cond(n[1], scope) else n[3], scope, strict))
        elif n[0] == "for":
            seq = _lookup(n[2], scope)
            if seq is _MISSING or not isinstance(seq, list):
                if strict:
                    raise MissingVariable(n[2])
                continue
            for idx, item in enumerate(seq, 1):
                out.append(_render(n[3], {**scope, n[1]: item, "forloop": {"index": idx}}, strict))
    return "".join(out)


def render(template: str, scope: dict, strict: bool = False) -> str:
    nodes, _, _ = _parse(TOKEN.split(template), 0, ())
    return _render(nodes, scope, strict)


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def load_template(name: str, directory: Path = TEMPLATE_DIR) -> str:
    return (directory / f"{name}.html").read_text()


def template_names(directory: Path = TEMPLATE_DIR) -> set[str]:
    return {p.stem for p in directory.glob("*.html") if not p.stem.startswith("_")}


def render_email(name: str, scope: dict, strict: bool = False, directory: Path = TEMPLATE_DIR) -> str:
    body = render(load_template(name, directory), scope, strict)
    layout = (directory / "_layout.html").read_text()
    return render(layout, {**scope, "content": body}, strict)
