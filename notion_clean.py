#!/usr/bin/env python3
"""
notion_clean.py — Strip Notion UUIDs from exported zip archives.

Notion appends a 32-character hex ID to every file and folder name on export,
which causes path-length issues and generally clutters the archive. This tool
rewrites the zip with clean names.

Usage:
    python notion_clean.py export.zip
    python notion_clean.py export.zip -o cleaned.zip
    python notion_clean.py export.zip --dry-run
"""

import argparse
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path


# Matches a space followed by a 32-char hex ID, just before an extension or
# path separator. Also handles Notion's "_all" suffix variant.
_ID_PATTERN = re.compile(
    r" ([0-9a-f]{32})(_all)?(?=(\.[^/]*)?(/|$))"
)


def clean_name(name: str) -> str:
    """Remove Notion UUID suffixes from every segment of a zip entry path."""
    def _replace(m: re.Match) -> str:
        # Keep the "_all" suffix if present, drop the UUID
        return m.group(2) or ""

    return _ID_PATTERN.sub(_replace, name)


def deduplicate(name_map: dict[str, str]) -> dict[str, str]:
    """
    If multiple originals map to the same cleaned name, append (1), (2), …
    before the extension so no files are silently clobbered.
    """
    # Count how many originals share each cleaned name
    freq: dict[str, int] = defaultdict(int)
    for cleaned in name_map.values():
        freq[cleaned] += 1

    counter: dict[str, int] = defaultdict(int)
    final: dict[str, str] = {}

    for orig, cleaned in name_map.items():
        if freq[cleaned] > 1:
            counter[cleaned] += 1
            # Insert counter before the last extension, respecting subdirs
            head, sep, ext = cleaned.rpartition(".")
            if sep and "/" not in ext:
                final[orig] = f"{head} ({counter[cleaned]}).{ext}"
            else:
                final[orig] = f"{cleaned} ({counter[cleaned]})"
        else:
            final[orig] = cleaned

    return final


def process(src: Path, dst: Path, dry_run: bool = False) -> None:
    with zipfile.ZipFile(src, "r") as zin:
        entries = zin.infolist()
        raw_map = {e.filename: clean_name(e.filename) for e in entries}
        final_map = deduplicate(raw_map)

        changed = [(o, n) for o, n in final_map.items() if o != n]
        unchanged = [o for o, n in final_map.items() if o == n]

        # --- Report ---
        print(f"\n📦  Source : {src}")
        if not dry_run:
            print(f"📦  Output : {dst}")
        print(f"\n{'DRY RUN — no file written' if dry_run else 'Writing cleaned archive...'}")
        print(f"\n  {len(changed):>3} file(s) renamed")
        print(f"  {len(unchanged):>3} file(s) unchanged\n")

        col = max((len(o) for o, _ in changed), default=0)
        for orig, new in sorted(changed):
            print(f"  {orig:<{col}}  →  {new}")

        if dry_run:
            print("\n(No output written — remove --dry-run to apply.)\n")
            return

        # --- Write ---
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in entries:
                data = zin.read(item.filename)
                info = zipfile.ZipInfo(final_map[item.filename])
                info.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(info, data)

        print(f"\n✅  Done → {dst}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strip Notion UUIDs from a Notion export zip.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("src", type=Path, help="Path to the Notion export .zip")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output path (default: <src>-cleaned.zip)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing anything",
    )
    args = parser.parse_args()

    src: Path = args.src
    if not src.exists():
        print(f"Error: {src} not found.", file=sys.stderr)
        sys.exit(1)
    if not zipfile.is_zipfile(src):
        print(f"Error: {src} does not look like a zip file.", file=sys.stderr)
        sys.exit(1)

    # If the zip contains a single inner zip (Notion's double-wrap), unwrap it.
    with zipfile.ZipFile(src) as z:
        inner = [n for n in z.namelist() if n.endswith(".zip")]
        if len(z.namelist()) == 1 and inner:
            print(f"ℹ️  Detected double-wrapped Notion export; unwrapping inner zip.")
            inner_bytes = z.read(inner[0])
            import io
            actual_src = zipfile.ZipFile(io.BytesIO(inner_bytes))
            # Write temp zip to work with it
            tmp = Path("/tmp") / (src.stem + ".inner.zip")
            with open(tmp, "wb") as f:
                f.write(inner_bytes)
            src = tmp

    dst: Path = args.output or src.parent / (
        src.stem.replace(".inner", "") + "-cleaned.zip"
    )

    process(src, dst, dry_run=args.dry_run)

    # Clean up temp inner zip if we created one
    if src.name.endswith(".inner.zip"):
        src.unlink()


if __name__ == "__main__":
    main()
