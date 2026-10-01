"""Dependency-free protocol shared by the desktop and the save service."""

from __future__ import annotations

Rule = tuple[str, str, str]


def rule_key(text: str) -> str:
    text = text.strip().upper().replace("\u00a0", " ").replace("\r", "").replace("\n", "")
    text = text.replace("Ö", "O").replace("Ä", "A").replace("Ü", "U").replace("ß", "SS")
    for dash in "\u2010\u2011\u2012\u2013\u2014\u2212":
        text = text.replace(dash, "-")
    for char in "- ,;./\\:_()":
        text = text.replace(char, "")
    return text


def validate_rules(raw: object, *, allow_empty: bool = False) -> tuple[Rule, ...]:
    if not isinstance(raw, list) or len(raw) > 2000:
        raise ValueError("Érvénytelen szabálykészlet.")
    result: list[Rule] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Érvénytelen szabály.")
        values = (item.get("from"), item.get("to"), item.get("partner", ""))
        if any(not isinstance(value, str) or len(value) > 300 for value in values):
            raise ValueError("A szabály mezői hibásak vagy túl hosszúak.")
        rule = tuple(value.strip() for value in values)
        key = rule_key(rule[0])
        if not key or not rule[1] or key in seen:
            raise ValueError("Üres vagy ismétlődő szabály.")
        if any(any(ord(char) < 32 for char in value) for value in rule):
            raise ValueError("A szabály nem tartalmazhat vezérlőkaraktert.")
        seen.add(key)
        result.append(rule)
    if not result and not allow_empty:
        raise ValueError("A közös szabálykészlet nem lehet üres.")
    return tuple(result)


def rule_objects(rules: tuple[Rule, ...]) -> list[dict[str, str]]:
    return [{"from": p, "to": r, "partner": partner} for p, r, partner in rules]


class RuleConflict(ValueError):
    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns
        super().__init__("Más is módosította ezeket a szabályokat: " + ", ".join(patterns))


def merge_rules(base: tuple[Rule, ...], desired: tuple[Rule, ...], current: tuple[Rule, ...], *, overwrite_conflicts: bool = False) -> tuple[Rule, ...]:
    """Apply only the client's changes, refusing concurrent conflicting edits."""
    before = {rule_key(r[0]): r for r in base}
    after = {rule_key(r[0]): r for r in desired}
    latest = {rule_key(r[0]): r for r in current}
    changes = [key for key in dict.fromkeys([*before, *after]) if before.get(key) != after.get(key)]
    conflicts = [
        (after.get(key) or before[key])[0] for key in changes
        if latest.get(key) != before.get(key) and latest.get(key) != after.get(key)
    ]
    if conflicts and not overwrite_conflicts:
        raise RuleConflict(conflicts)
    for key in changes:
        if key in after:
            latest[key] = after[key]
        else:
            latest.pop(key, None)
    if not latest:
        raise ValueError("Az összes közös szabály nem törölhető.")
    return tuple(latest.values())
