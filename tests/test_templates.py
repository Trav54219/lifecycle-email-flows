import pytest

from lifecycle.templates import MissingVariable, TemplateError, render, render_email, template_names


def test_variables_default_and_escape():
    s = {"c": {"name": "<b>Al</b>"}}
    assert render("Hi {{ c.name }}", s) == "Hi &lt;b&gt;Al&lt;/b&gt;"
    assert render("Hi {{ c.nick | default: 'there' }}", s) == "Hi there"
    assert render("{{ c.name | raw }}", s) == "<b>Al</b>"


def test_filters():
    assert render("{{ x | money }}", {"x": 1234.5}) == "$1,234.50"
    assert render("{{ x | upcase }}", {"x": "ab"}) == "AB"


def test_if_else_and_comparisons():
    t = "{% if n > 100 %}big{% else %}small{% endif %}"
    assert render(t, {"n": 150}) == "big"
    assert render(t, {"n": 5}) == "small"
    assert render("{% if not a %}no{% endif %}", {"a": ""}) == "no"
    assert render("{% if s == 'x' %}y{% endif %}", {"s": "x"}) == "y"


def test_for_loop():
    out = render("{% for i in items %}{{ forloop.index }}:{{ i.n }};{% endfor %}", {"items": [{"n": "a"}, {"n": "b"}]})
    assert out == "1:a;2:b;"


def test_strict_mode_and_errors():
    with pytest.raises(MissingVariable):
        render("{{ nope }}", {}, strict=True)
    assert render("{{ nope | default: 'ok' }}", {}, strict=True) == "ok"
    with pytest.raises(TemplateError):
        render("{% if a %}x", {"a": 1})
    with pytest.raises(TemplateError):
        render("{% bogus %}", {})


def test_every_template_renders_strict_with_sample_data():
    scope = {
        "brand": {"name": "B", "address": "A"}, "customer": {"first_name": "Pat", "email": "p@example.com"},
        "cart": {"items": [{"name": "Lamp", "price": 62, "qty": 1}], "total": 62},
        "order": {"count": 2, "last_value": 50}, "offer": {"discount_code": "X", "discount_pct": 5},
        "unsubscribe_url": "https://example.com/u",
    }
    names = template_names()
    assert len(names) >= 13
    for n in names:
        html = render_email(n, scope, strict=True)
        assert "{{" not in html and "{%" not in html, n
        assert "https://example.com/u" in html, f"{n} lacks unsubscribe link"
