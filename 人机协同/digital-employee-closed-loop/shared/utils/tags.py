from __future__ import annotations


def normalize_tag_list(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    for tag in tags:
        clean = str(tag).strip()
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized
