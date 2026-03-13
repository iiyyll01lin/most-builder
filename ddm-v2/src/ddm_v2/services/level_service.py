from __future__ import annotations

from collections import defaultdict


def validate_level_tags(tags: list[str]) -> list[str]:
    errors: list[str] = []
    seen_main = False
    for index, tag in enumerate(tags, start=1):
        if not tag:
            continue
        normalized = tag.lower()
        if normalized.startswith("main"):
            seen_main = True
        if normalized.startswith("sub") and not seen_main:
            errors.append(f"Row {index}: sub tag cannot appear before main tag.")
        if normalized.startswith("cub") and "." in normalized:
            errors.append(f"Row {index}: cub tag must not contain hierarchical separators.")
    return errors


def build_level_entries(project_id: str, sop_actions: list[dict], existing_entries: list[dict] | None = None) -> list[dict]:
    existing_map = {entry["action_id"]: entry for entry in existing_entries or []}
    result: list[dict] = []
    for index, action in enumerate(sop_actions):
        current = existing_map.get(action["id"], {})
        difficulty_factor = current.get("difficulty_factor", 1.0)
        adjusted_ct = round(action.get("seconds", 0) * difficulty_factor, 2)
        machine_count = current.get("machine_count", 1)
        operator_count = current.get("operator_count", 1)
        cub_group = current.get("cub_group")
        divisor = max(machine_count, operator_count)
        effective_cub_ct = round(adjusted_ct / divisor, 2) if cub_group else None
        sort_order = current.get("sort_order")
        if sort_order is None:
            sort_order = index
        result.append(
            {
                "id": current.get("id", f"lvl-{project_id}-{action['id']}"),
                "action_id": action["id"],
                "row_no": index + 1,
                "description": action["description"],
                "ct_seconds": action.get("seconds", 0),
                "frequency": action.get("frequency", 1),
                "difficulty_factor": difficulty_factor,
                "adjusted_ct": adjusted_ct,
                "number_tag": current.get("number_tag"),
                "number_count": current.get("number_count"),
                "main_seq": current.get("main_seq"),
                "order_seq": current.get("order_seq"),
                "cub_group": cub_group,
                "machine_count": machine_count,
                "operator_count": operator_count,
                "status_label": current.get("status_label"),
                "effective_cub_ct": effective_cub_ct,
                "sort_order": sort_order,
            }
        )
    result.sort(key=lambda entry: entry["sort_order"])
    for index, entry in enumerate(result, start=1):
        entry["row_no"] = index
        entry["sort_order"] = index - 1
    return result


def build_precedence_graph(level_entries: list[dict]) -> dict:
    nodes = []
    precedence_edges = []
    cub_groups: dict[str, list[str]] = defaultdict(list)
    number_constraints: dict[str, dict] = {}
    main_order = []

    for entry in level_entries:
        nodes.append(
            {
                "id": entry["action_id"],
                "description": entry["description"],
                "original_ct": entry["ct_seconds"],
                "difficulty_factor": entry["difficulty_factor"],
                "adjusted_ct": entry["adjusted_ct"],
                "effective_ct": entry["effective_cub_ct"] or entry["adjusted_ct"],
                "main_seq": entry.get("main_seq"),
                "order_seq": entry.get("order_seq"),
                "cub_group": entry.get("cub_group"),
                "number_tag": entry.get("number_tag"),
                "number_count": entry.get("number_count"),
                "machine_count": entry.get("machine_count"),
                "operator_count": entry.get("operator_count"),
                "status_label": entry.get("status_label"),
            }
        )
        if entry.get("main_seq"):
            main_order.append((entry["main_seq"], entry["action_id"]))
        if entry.get("cub_group"):
            cub_groups[entry["cub_group"]].append(entry["action_id"])
        if entry.get("number_tag"):
            number_constraints.setdefault(
                entry["number_tag"],
                {"limit": entry.get("number_count") or 1, "actions": []},
            )["actions"].append(entry["action_id"])

    main_order.sort(key=lambda value: value[0])
    for left, right in zip(main_order, main_order[1:]):
        precedence_edges.append({"from": left[1], "to": right[1], "type": "main"})

    return {
        "nodes": nodes,
        "precedence_edges": precedence_edges,
        "cub_groups": dict(cub_groups),
        "number_constraints": number_constraints,
        "total_adjusted_ct": round(sum(node["adjusted_ct"] for node in nodes), 2),
        "total_effective_ct": round(sum(node["effective_ct"] for node in nodes), 2),
    }
