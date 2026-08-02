#!/usr/bin/env python3
"""
Generate a wiki-ready list of every book in the game, showing what skill/martial
art it trains and what crafting recipes it teaches.

Produces books_wiki.txt - finished MediaWiki source. Paste this directly into
the wiki page's "Edit source" box (NOT a third-party "paste text, get a
table" tool - it's already complete wikitext with headings and {| |} tables,
a plain text-splitter will mangle it).

Usage:
    python book_recipe_wiki.py [--game-dir PATH] [output_file.txt]

Reads the game's own data/json tree, so the output always matches whatever
version of the game/mod you run it against - just rerun this after an
update. When the output already exists, the new result is compared with the
last run and a unified diff is printed before the output is updated. By
default it looks for a data/json folder next to this script, in its parent,
in its grandparent (the game root when this lives under tools/), and in the
current directory; if none of those exist, point it at your install with
--game-dir, e.g.:

    python book_recipe_wiki.py --game-dir "C:\\Path\\To\\Cataclysm-TLG"
"""
import argparse
import difflib
import json
import sys
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent


def find_data_json(game_dir_arg):
    if game_dir_arg:
        candidate = Path(game_dir_arg) / "data" / "json"
        if candidate.is_dir():
            return candidate
        sys.exit(f"No data/json folder found under --game-dir: {game_dir_arg}")

    for candidate in (
        SCRIPT_DIR / "data" / "json",
        SCRIPT_DIR.parent / "data" / "json",
        SCRIPT_DIR.parent.parent / "data" / "json",
        Path.cwd() / "data" / "json",
    ):
        if candidate.is_dir():
            return candidate

    sys.exit(
        "Couldn't find a data/json folder automatically.\n"
        "Point this at your game install with --game-dir, e.g.:\n"
        '  python book_recipe_wiki.py --game-dir "C:\\Path\\To\\Cataclysm-TLG"'
    )


def load_all_objects(root):
    """Return list of (obj, path) for every JSON dict under root."""
    objs = []
    for path in root.rglob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ! skipping {path}: {e}", file=sys.stderr)
            continue
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            continue
        for obj in items:
            if isinstance(obj, dict):
                objs.append((obj, path))
    return objs


def obj_key(obj):
    return obj.get("id") or obj.get("abstract")


def as_display_name(name_field, fallback):
    if isinstance(name_field, dict):
        return name_field.get("str") or name_field.get("str_sp") or fallback
    if isinstance(name_field, str):
        return name_field
    return fallback


def build_indices(all_objs):
    by_id = {}
    for obj, _path in all_objs:
        key = obj_key(obj)
        if key is None:
            continue
        keys = key if isinstance(key, list) else [key]
        for k in keys:
            if isinstance(k, str):
                by_id[k] = obj
    return by_id


def resolve_field(by_id, start_id, field, depth=0):
    """Walk the copy-from chain until `field` is found on some ancestor."""
    if depth > 25 or start_id is None:
        return None
    obj = by_id.get(start_id)
    if obj is None:
        return None
    if field in obj:
        return obj[field]
    parent = obj.get("copy-from")
    if parent:
        return resolve_field(by_id, parent, field, depth + 1)
    return None


def resolve_name(by_id, start_id, depth=0):
    if depth > 25 or start_id is None:
        return start_id
    obj = by_id.get(start_id)
    if obj is None:
        return start_id
    if "name" in obj:
        return as_display_name(obj["name"], start_id)
    if obj.get("type") == "MIGRATION" and obj.get("replace"):
        return resolve_name(by_id, obj["replace"], depth + 1)
    parent = obj.get("copy-from")
    if parent:
        return resolve_name(by_id, parent, depth + 1)
    return start_id


def parse_book_learn(raw):
    """Normalize every book_learn shape into a list of (book_id, level_or_None)."""
    entries = []
    if raw is None:
        return entries
    if isinstance(raw, dict):
        for book_id, val in raw.items():
            level = None
            if isinstance(val, dict):
                level = val.get("skill_level")
            elif isinstance(val, (int, float)):
                level = val
            entries.append((book_id, level))
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                entries.append((entry, None))
            elif isinstance(entry, list):
                book_id = entry[0]
                level = entry[1] if len(entry) > 1 else None
                entries.append((book_id, level))
            elif isinstance(entry, dict):
                book_id = entry.get("name") or entry.get("id")
                level = entry.get("skill_level")
                if book_id:
                    entries.append((book_id, level))
    return entries


def is_book(obj):
    if not isinstance(obj.get("id"), str):
        return False  # abstract/template/multi-id def, not a plain real item
    if obj.get("type") == "BOOK":
        return True
    subtypes = obj.get("subtypes")
    if isinstance(subtypes, list) and "BOOK" in subtypes:
        return True
    return False


def wiki_escape(text):
    return str(text).replace("|", "&#124;")


ALWAYS_VISIBLE = 5
COLLAPSE_THRESHOLD = 10


def format_list_cell(items, noun):
    """Render a list of strings for a table cell. Up to COLLAPSE_THRESHOLD items
    are shown inline in full. Beyond that, the first ALWAYS_VISIBLE items stay
    visible and the rest collapse into a click-to-expand box, so rows stay a
    reasonable height even for books that teach dozens of recipes (MediaWiki's
    built-in mw-collapsible, no extension required)."""
    if not items:
        return "&mdash;"
    if len(items) <= COLLAPSE_THRESHOLD:
        return "<br>".join(items)
    visible, hidden = items[:ALWAYS_VISIBLE], items[ALWAYS_VISIBLE:]
    return (
        "<br>".join(visible) + "<br>"
        '<div class="mw-collapsible mw-collapsed">'
        f"+{len(hidden)} more {noun}"
        '<div class="mw-collapsible-content">' + "<br>".join(hidden) + "</div></div>"
    )


def report_changes(out_path, new_text):
    """Print the changes from the previous generated output, if one exists."""
    if not out_path.exists():
        print(f"No previous output found at {out_path}; this is the first run.")
        return

    try:
        old_text = out_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Couldn't compare with previous output {out_path}: {e}", file=sys.stderr)
        return

    if old_text == new_text:
        print("No changes since the last run.")
        return

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{out_path} (last run)",
        tofile=f"{out_path} (current run)",
    ))
    additions = sum(line.startswith("+") and not line.startswith("+++") for line in diff)
    deletions = sum(line.startswith("-") and not line.startswith("---") for line in diff)
    print(f"Changes since the last run: {additions} additions, {deletions} deletions")
    print("".join(diff), end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", nargs="?", help="output .txt path (default: books_wiki.txt beside this script)")
    parser.add_argument("--game-dir", help="path to the game install (the folder containing data/json)")
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else SCRIPT_DIR / "books_wiki.txt"
    data_json = find_data_json(args.game_dir)

    print(f"Reading JSON from: {data_json}")
    all_objs = load_all_objects(data_json)
    print(f"  loaded {len(all_objs)} JSON objects")

    by_id = build_indices(all_objs)

    skill_names = {
        obj["id"]: as_display_name(obj.get("name"), obj["id"]).title()
        for obj, _p in all_objs
        if obj.get("type") == "skill" and isinstance(obj.get("id"), str)
    }
    ma_names = {
        obj["id"]: as_display_name(obj.get("name"), obj["id"])
        for obj, _p in all_objs
        if obj.get("type") == "martial_art" and isinstance(obj.get("id"), str)
    }
    prof_names = {
        obj["id"]: as_display_name(obj.get("name"), obj["id"])
        for obj, _p in all_objs
        if obj.get("type") == "proficiency" and isinstance(obj.get("id"), str)
    }

    # book_id -> list of (result_item_id, level_or_None)
    book_recipes = defaultdict(list)
    for obj, _path in all_objs:
        if obj.get("type") != "recipe":
            continue
        bl = obj.get("book_learn")
        if not bl:
            continue
        result = obj.get("result")
        if not result:
            continue
        for book_id, level in parse_book_learn(bl):
            book_recipes[book_id].append((result, level))

    books = [obj for obj, _path in all_objs if is_book(obj)]
    print(f"  found {len(books)} book items, {len(book_recipes)} books with taught recipes")

    rows = []
    for obj in books:
        book_id = obj["id"]
        name = resolve_name(by_id, book_id)
        skill_id = resolve_field(by_id, book_id, "read_skill")
        martial_art_id = resolve_field(by_id, book_id, "martial_art")
        max_level = resolve_field(by_id, book_id, "max_level")
        required_level = resolve_field(by_id, book_id, "required_level") or 0
        proficiencies_raw = resolve_field(by_id, book_id, "proficiencies") or []

        skill_display = skill_names.get(skill_id, skill_id.title() if skill_id else None)
        martial_display = ma_names.get(martial_art_id, martial_art_id) if martial_art_id else None

        if skill_display and max_level is not None:
            level_range = f"{required_level}-{max_level}"
        elif skill_display:
            level_range = f"{required_level}+"
        else:
            level_range = ""

        prof_list = []
        for p in proficiencies_raw:
            pid = p.get("proficiency") if isinstance(p, dict) else p
            if pid:
                prof_list.append(prof_names.get(pid, pid))

        recipe_entries = book_recipes.get(book_id, [])
        recipe_set = set()
        for result_id, level in recipe_entries:
            recipe_name = resolve_name(by_id, result_id)
            recipe_set.add((recipe_name, level))
        recipe_list = sorted(recipe_set, key=lambda t: (t[0].lower(), t[1] if t[1] is not None else -1))

        rows.append({
            "id": book_id,
            "name": name,
            "skill": skill_display,
            "level_range": level_range,
            "martial_art": martial_display,
            "proficiencies": sorted(set(prof_list)),
            "recipes": recipe_list,
        })

    # Only keep books that actually teach something (skill, martial art, or recipes)
    # so we don't fill the wiki page with pure fiction/fluff reading material.
    rows = [r for r in rows if r["skill"] or r["martial_art"] or r["recipes"]]

    def group_key(r):
        if r["martial_art"]:
            return "Martial Arts Manuals"
        if r["skill"]:
            return r["skill"]
        return "Other"

    groups = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)
    for g in groups.values():
        g.sort(key=lambda r: r["name"].lower())

    lines = []
    lines.append("== List of Books ==")
    lines.append("")
    lines.append("'''How to read this list:'''")
    lines.append("")
    lines.append(
        "* '''Level Range''' &mdash; the two numbers are the skill level you need "
        "to already have before the book teaches you anything, and the highest "
        "level it can train that skill up to just from reading it."
    )
    lines.append(
        "* '''Recipes Taught''' &mdash; crafting recipes you unlock by reading the "
        "book. The number after a recipe is the skill level you need to be at "
        "before that specific recipe unlocks &mdash; owning the book isn't always "
        "enough on its own, you may need to train the skill up first."
    )
    lines.append(
        "* '''Proficiencies''' &mdash; proficiencies the book helps with while "
        "crafting, reducing the time/failure penalty for not having learned "
        "them yet (it does not teach the proficiency outright)."
    )
    lines.append("")

    for group_name in sorted(groups.keys(), key=lambda s: (s == "Martial Arts Manuals", s == "Other", s.lower())):
        group_rows = groups[group_name]
        lines.append(f"=== {group_name} ===")
        lines.append('{| class="wikitable sortable"')
        if group_name == "Martial Arts Manuals":
            lines.append("! Book !! Style Taught")
            for r in group_rows:
                lines.append("|-")
                lines.append(f"| {wiki_escape(r['name'])}")
                lines.append(f"| {wiki_escape(r['martial_art'])}")
        else:
            lines.append("! Book !! Level Range !! Recipes Taught !! Proficiencies")
            for r in group_rows:
                lines.append("|-")
                lines.append(f"| {wiki_escape(r['name'])}")
                level_col = r["level_range"] if r["skill"] else "&mdash;"
                lines.append(f"| {level_col}")
                recipe_bits = []
                for rname, lvl in r["recipes"]:
                    if lvl is not None:
                        recipe_bits.append(f"{wiki_escape(rname)} ({lvl})")
                    else:
                        recipe_bits.append(wiki_escape(rname))
                lines.append(f"| {format_list_cell(recipe_bits, 'recipes')}")
                prof_bits = [wiki_escape(p) for p in r["proficiencies"]]
                lines.append(f"| {format_list_cell(prof_bits, 'proficiencies')}")
        lines.append("|}")
        lines.append("")

    output_text = "\n".join(lines)
    report_changes(out_path, output_text)
    out_path.write_text(output_text, encoding="utf-8")
    print(f"Wrote {len(rows)} books across {len(groups)} groups to: {out_path}")


if __name__ == "__main__":
    main()
