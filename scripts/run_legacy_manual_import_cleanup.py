from __future__ import annotations

import re

import remove_legacy_manual_import as cleanup


def remove_named_js_function(source: str, name: str, label: str) -> str:
    pattern = re.compile(rf"(?m)^  (?:async )?function {re.escape(name)}\(")
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise cleanup.CleanupError(f"{label}: expected one function named {name}, found {len(matches)}")

    start = matches[0].start()
    body_match = re.search(r"\)\s*\{", source[matches[0].end():])
    if body_match is None:
        raise cleanup.CleanupError(f"{label}: function body opening was not found")
    opening = matches[0].end() + body_match.end() - 1
    end = cleanup.matching_brace(source, opening) + 1

    while end < len(source) and source[end] in " \t":
        end += 1
    newline_count = 0
    while end < len(source) and source[end] in "\r\n" and newline_count < 4:
        if source[end] == "\n":
            newline_count += 1
        end += 1
    return source[:start] + source[end:]


cleanup.remove_named_js_function = remove_named_js_function
cleanup.main()
