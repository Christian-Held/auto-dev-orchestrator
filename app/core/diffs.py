from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Iterable, Tuple

from .logging import get_logger

logger = get_logger(__name__)

HUNK_RE = re.compile(r"@@ -(?P<old_start>\d+)(?:,(?P<old_len>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@")


def generate_unified_diff(original: str, updated: str, filename: str) -> str:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def apply_unified_diff(base_path: Path, diff_text: str) -> Iterable[Tuple[Path, str]]:
    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old_path = line[4:].strip()
            i += 1
            if i >= len(lines):
                break
            new_line = lines[i]
            if not new_line.startswith("+++ "):
                raise ValueError("Invalid diff: missing '+++' line")
            new_path = new_line[4:].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            target_path = base_path / new_path
            if old_path == "/dev/null":
                original_content = ""
            else:
                source_path = old_path[2:] if old_path.startswith("a/") else old_path
                full_source = base_path / source_path
                original_content = full_source.read_text(encoding="utf-8") if full_source.exists() else ""
            source_lines = original_content.splitlines()
            rebuilt: list[str] = []
            cursor = 0
            i += 1

            # Ensure at least one valid hunk exists
            found_valid_hunk = False

            while i < len(lines) and lines[i].startswith("@@ "):
                header = lines[i]
                match = HUNK_RE.match(header)
                if not match:
                    raise ValueError(f"Invalid hunk header: {header!r}. Expected format: @@ -old_start,old_len +new_start,new_len @@")
                found_valid_hunk = True
                old_start = int(match.group("old_start")) - 1
                if old_start > len(source_lines):
                    old_start = len(source_lines)
                rebuilt.extend(source_lines[cursor:old_start])
                cursor = old_start
                i += 1
                while i < len(lines) and not lines[i].startswith("@@ ") and not lines[i].startswith("--- "):
                    hunk_line = lines[i]
                    if hunk_line.startswith(" "):
                        if cursor < len(source_lines):
                            rebuilt.append(source_lines[cursor])
                        else:
                            rebuilt.append(hunk_line[1:])
                        cursor += 1
                    elif hunk_line.startswith("-"):
                        cursor += 1
                    elif hunk_line.startswith("+"):
                        rebuilt.append(hunk_line[1:])
                    else:
                        logger.warning("unknown_diff_line", line=hunk_line)
                    i += 1
                # continue to next hunk without increment to skip header reprocessing

            # Validate that we found at least one hunk
            if not found_valid_hunk:
                raise ValueError(
                    f"No valid hunks found in diff for {new_path}. "
                    f"Diff may be malformed or missing hunk headers like '@@ -0,0 +1,10 @@'"
                )

            rebuilt.extend(source_lines[cursor:])
            new_content = "\n".join(rebuilt)
            if original_content.endswith("\n") or diff_text.endswith("\n"):
                new_content += "\n"
            logger.info("diff_applied", path=str(target_path), lines=len(rebuilt))
            yield target_path, new_content
        else:
            i += 1


def safe_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("file_written", path=str(path))
