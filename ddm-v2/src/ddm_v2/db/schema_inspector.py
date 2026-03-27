"""Schema inspector: extracts a compact DDL summary of the core manufacturing tables
for injection into the LLM system prompt.

The summary is built *statically* from SQLAlchemy ``Base.metadata`` — no database
connection is required at import time.  It is safe to call at module load in any
environment (test, dev, production).
"""

from __future__ import annotations

# Tables exposed to the BI agent.  We INTENTIONALLY exclude session/auth-sensitive
# tables (users, most_workspaces) from the LLM context to minimise data-leakage risk.
_BI_TABLE_NAMES: frozenset[str] = frozenset({
    "projects",
    "sop_versions",
    "sop_actions",
    "video_uploads",
    "syntax_library",
    "component_library",
    "object_library",
    "tool_library",
    "precaution_rules",
    "stations",
    "employees",
    "level_entries",
    "simulation_results",
})

# Human-readable type aliases (keeps the prompt compact)
_TYPE_LABEL: dict[str, str] = {
    "VARCHAR": "TEXT",
    "CHARACTER VARYING": "TEXT",
}


def _friendly_type(col_type: str) -> str:
    upper = col_type.upper()
    for src, dst in _TYPE_LABEL.items():
        upper = upper.replace(src, dst)
    # strip length qualifiers like TEXT(64) → TEXT
    import re
    upper = re.sub(r"\(\d+\)", "", upper)
    return upper.strip()


def get_bi_schema_ddl() -> str:
    """Return a compact, human-readable schema summary for all BI-relevant tables.

    Import models first so ``Base.metadata`` is fully populated.  We do the
    import here (not at module level) to avoid circular-import issues.

    Returns a string such as::

        TABLE: sop_actions
          id            TEXT            PK
          sop_version_id TEXT           FK → sop_versions.id
          description   TEXT
          tmu           INTEGER
          ...

        TABLE: stations
          ...
    """
    import ddm_v2.models.domain  # noqa: F401 — populate Base.metadata

    from ddm_v2.db.database import Base

    sections: list[str] = []

    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        if table.name not in _BI_TABLE_NAMES:
            continue

        lines: list[str] = [f"TABLE: {table.name}"]
        for col in table.columns:
            col_type = _friendly_type(str(col.type))
            flags: list[str] = []
            if col.primary_key:
                flags.append("PK")
            for fk in col.foreign_keys:
                flags.append(f"FK → {fk.target_fullname}")
            if not col.nullable and not col.primary_key:
                flags.append("NOT NULL")
            flag_str = "  [" + ", ".join(flags) + "]" if flags else ""
            lines.append(f"  {col.name:<28} {col_type:<16}{flag_str}")

        sections.append("\n".join(lines))

    if not sections:
        return "(schema not available)"

    header = (
        "-- DDM v2 Manufacturing Database Schema (read-only BI context)\n"
        "-- Use these exact table and column names in your SQL queries.\n\n"
    )
    return header + "\n\n".join(sections)
