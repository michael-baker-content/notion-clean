# notion_clean

Strip Notion's auto-appended UUIDs from exported zip archives.

When you export a workspace from Notion, every file and folder gets a 32-character hex ID tacked onto its name:

```
Algebra 1/Factoring c3abd99c1aa846fda6770b32e35c5c8a.md
Algebra 1/Functions 09aa97f658fe4fa386f1590e47d8ac5b.md
```

Nested folders compound the problem, pushing paths past OS limits. This script rewrites the zip with clean names:

```
Algebra 1/Factoring.md
Algebra 1/Functions.md
```

## Requirements

Python 3.9+, standard library only — no `pip install` needed.

## Usage

```bash
# Preview changes without writing anything
python notion_clean.py export.zip --dry-run

# Clean the archive (writes export-cleaned.zip alongside the original)
python notion_clean.py export.zip

# Specify a custom output path
python notion_clean.py export.zip -o my-notes.zip
```

### Arguments

| Argument | Description |
|---|---|
| `src` | Path to the Notion export `.zip` |
| `-o, --output` | Output path (default: `<src>-cleaned.zip`) |
| `--dry-run` | Print the rename plan without writing any files |

## What it handles

**Standard UUID suffixes** — Notion appends a space and 32 hex characters before the extension on every file and folder name. These are stripped from every path segment.

**The `_all.csv` variant** — Database exports produce two CSVs: one standard and one with an `_all` suffix (containing all properties). The suffix is preserved, only the UUID is removed.

```
Algebra 1 6c5f1925a44d4ede89ed79cdef2eca66.csv     → Algebra 1.csv
Algebra 1 6c5f1925a44d4ede89ed79cdef2eca66_all.csv → Algebra 1_all.csv
```

**Double-wrapped zips** — Notion sometimes wraps the real archive inside an outer zip (the outer zip's name carries its own UUID). The script detects this automatically and processes the inner archive.

**Duplicate names** — If two files have different UUIDs but the same base name (i.e. genuinely distinct Notion pages with the same title), stripping the IDs would cause a collision. These are disambiguated with a counter suffix rather than silently clobbering one:

```
📋 Learning Content Outline 4b6e...bb.md → 📋 Learning Content Outline (1).md
📋 Learning Content Outline 4d96...bf.md → 📋 Learning Content Outline (2).md
```

## How it works

The core logic is a single regular expression applied to every entry path in the zip:

```python
_ID_PATTERN = re.compile(
    r" ([0-9a-f]{32})(_all)?(?=(\.[^/]*)?(/|$))"
)
```

This matches:
- a literal space (Notion always separates the name from the ID with a space)
- exactly 32 lowercase hex characters
- optionally `_all` (database export suffix)
- followed by either a file extension + path boundary, or a path separator / end of string (lookahead, not consumed)

The replacement keeps `_all` if it was present and drops everything else.

## Adapting for edge cases

### Notion changes its ID format

If Notion switches to a different ID length or format (e.g. hyphenated UUIDs like `550e8400-e29b-41d4-a716-446655440000`), update `_ID_PATTERN`. The key structural assumption is that the separator before the ID is a space and the ID appears at the end of each path segment.

Hyphenated UUID variant:
```python
_ID_PATTERN = re.compile(
    r" [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(_all)?(?=(\.[^/]*)?(/|$))"
)
```

To match either format at once:
```python
_ID_PATTERN = re.compile(
    r" (?:[0-9a-f]{32}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})(_all)?(?=(\.[^/]*)?(/|$))"
)
```

### Files have no space before the ID

If Notion ever drops the space separator, change the leading ` ` in the pattern to ` ?` (zero or one space). Be cautious — making the space optional increases the risk of matching hex strings that appear legitimately in a filename.

### The archive isn't zipped (extracted directory)

The script only operates on zip files. To run it on an already-extracted folder, re-zip it first:

```bash
cd /path/to/notion-export
zip -r export.zip .
python notion_clean.py export.zip
```

Or adapt `process()` to walk a directory with `os.walk` / `pathlib.Path.rglob` and `os.rename` instead.

### Multiple inner zips (large workspace exports)

Notion splits very large exports into multiple `Part-N.zip` files inside the outer wrapper. The current script only processes a single inner zip. To handle all parts in one pass:

```python
# In main(), replace the single-inner-zip block with:
inner = [n for n in z.namelist() if n.endswith(".zip")]
if inner:
    for inner_name in inner:
        inner_bytes = z.read(inner_name)
        tmp = Path("/tmp") / Path(inner_name).name
        tmp.write_bytes(inner_bytes)
        part_dst = dst.parent / (tmp.stem + "-cleaned.zip")
        process(tmp, part_dst, dry_run=args.dry_run)
        tmp.unlink()
    return  # skip the single-file path below
```

### Keeping a rename log

Add a `--log` flag to write the full rename mapping to a CSV for auditing:

```python
# After final_map is built in process(), before writing:
if log_path:
    import csv
    with open(log_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["original", "cleaned"])
        w.writerows(sorted(final_map.items()))
```

### Truncated filenames

Notion sometimes truncates very long page titles mid-word before appending the ID (visible in the archive as a name ending abruptly). The script strips the ID regardless of truncation, but the truncated base name is kept as-is. There's no reliable way to recover the full original title from the zip alone — you'd need to cross-reference the exported markdown content, which includes the full page title in its first heading.
