"""Show what an edit-design call really changed.

Usage: python -I canva/probe_diff.py <previous_outline.txt> <edit_result.json> <new_outline.txt> <report.txt>
Builds the new outline from the edit result (written to <new_outline.txt>), then reports the status of every
operation and the outline lines that differ from the previous outline (full report in <report.txt>; the console
gets the summary and the path). Fails when the result reports no operations, so an empty diff cannot be mistaken
for "nothing to see".
"""
import difflib
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.outline import build_outline  # noqa: E402


def probe_diff(prev_outline: str, result: dict, new_outline: str = None) -> list:
    """Report lines for one edit result. `new_outline` defaults to the outline built from the result.
    Raises ValueError when the result has no edit_operation_results."""
    ops = result.get("edit_operation_results") if isinstance(result, dict) else None
    if not ops:
        keys = list(result) if isinstance(result, dict) else type(result).__name__
        raise ValueError(f"no edit_operation_results in the edit result: keys={keys}")
    if new_outline is None:
        new_outline = build_outline(result)
    lines = [f"status={result.get('status')} page_index={result.get('page_index')} "
             f"thumbnails={len(result.get('thumbnail_urls', []))}"]
    for i, op in enumerate(ops, 1):
        extra = {k: v for k, v in op.items() if k not in ("status", "operation_info", "validation_required")}
        lines.append(f"  op{i} {op.get('operation_info', {}).get('type')}: {op.get('status')} "
                     f"{json.dumps(extra, ensure_ascii=False)[:400] if extra else ''}".rstrip())
    a, b = prev_outline.splitlines(), new_outline.splitlines()
    changed = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]
    lines.append(f"outline lines before={len(a)} after={len(b)} changed={len(changed)}")
    lines.extend("  " + l[:420] for l in changed)
    return lines


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    try:
        prev = Path(argv[0]).read_text(encoding="utf-8")
        result = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        new = build_outline(result)
        lines = probe_diff(prev, result, new)
        Path(argv[2]).write_text(new, encoding="utf-8")
        Path(argv[3]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    print("\n".join(l for l in lines if not l.startswith("    ") and (l.startswith("status") or l.startswith("  op") or l.startswith("outline"))))
    print(f"report: {argv[3]}\nnew outline: {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
