# CTLG Book/Recipe Wiki Generator

A small Python script for [Cataclysm: The Last Generation](https://github.com/Cataclysm-TLG/Cataclysm-TLG)
(a fork of [Cataclysm: Dark Days Ahead](https://github.com/CleverRaven/Cataclysm-DDA)) that scans the
game's own `data/json` files and produces a wiki-ready list of every book in the game: what
skill (or martial art) it trains, what crafting recipes it teaches, and what proficiencies it
helps with.

Since it reads straight from the game's JSON data, it can be rerun any time the game updates and
the output will always match the current version - nobody has to hand-maintain the wiki page.

## Usage

Requires Python 3.8+. No third-party dependencies.

```bash
python book_recipe_wiki.py --game-dir "C:\Path\To\Cataclysm-TLG"
```

If you run it from inside the game's own `tools/` folder (or its data/json is in the current
directory), you can drop `--game-dir` entirely - it'll find it automatically.

This produces two files:

- **`books_wiki.txt`** - finished MediaWiki source (headings + sortable tables). Paste this
  directly into the wiki page's **"Edit source"** box. It's already complete wikitext - don't run
  it through a third-party "paste text, get a table" tool, those expect raw data, not markup, and
  will mangle it.
- **`books_wiki_table.tsv`** - flat, markup-free tab-separated data (Category / Book / Level Range
  or Style / Recipes / Proficiencies). Paste this into a spreadsheet, or into an online table
  generator that builds wikitext *from* raw data.

A sample of both, generated against one snapshot of the game, is checked into
[`sample_output/`](sample_output) so you can see what to expect without running anything.

## How the numbers work

- **Level Range** - the skill level you need to already have before the book teaches you
  anything, and the highest level it can train that skill up to just from reading it.
- **Recipes Taught** - the number after a recipe is the skill level you need to be at before that
  specific recipe unlocks. Owning the book isn't always enough on its own - you may need to train
  the skill up first. Lists longer than 10 recipes collapse into a click-to-expand box (the first
  5 stay visible) so table rows don't become absurdly tall.
- **Proficiencies** - proficiencies the book helps with while crafting, reducing the time/failure
  penalty for not having learned them yet. It does not teach the proficiency outright.

## Maintenance

This was built as a one-off for a fast-moving mod/fork where nobody wants to hand-maintain a wiki
page forever. It's just a script sitting here for whoever finds it useful - feel free to fork it,
rerun it, or send a PR if the game's JSON schema changes underneath it.
