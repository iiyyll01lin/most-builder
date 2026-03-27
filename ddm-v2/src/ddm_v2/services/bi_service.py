"""Generative BI service — Text-to-SQL pipeline with secure execution.

Architecture (defense-in-depth):
  Layer 1 — Static structure check  : SQL must start with SELECT / WITH…SELECT.
  Layer 2 — Keyword blacklist scan  : DML / DDL keywords rejected after string-
                                      literal stripping (prevents data-hiding attacks).
  Layer 3 — DB read-only transaction: PostgreSQL itself enforces read-only; any write
                                      attempt that slips past layers 1-2 is rejected
                                      by the database engine.
  Row-cap guard                     : LIMIT 1000 is injected automatically when absent,
                                      preventing resource-exhaustion.

Public API:
    result = await generate_bi_report(natural_language_query, session)
    # result: BIReportPayload dict  ← returned directly to the frontend
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Type aliases ─────────────────────────────────────────────────────────────

ChartType = Literal["BarChart", "LineChart", "PieChart", "Table", "MetricCard"]

# ─── SQL Security Sandbox ─────────────────────────────────────────────────────

# Compiled once at import time.
_STRIP_SINGLE_QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'", re.DOTALL)
_STRIP_DOUBLE_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)
_STRIP_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRIP_LINE_COMMENT = re.compile(r"--[^\n]*")

# Structural: the first real token must be WITH or SELECT.
_ALLOWED_START = re.compile(r"^\s*(?:with|select)\b", re.IGNORECASE)

# DML / DDL keyword blacklist (whole-word match against de-stringified SQL).
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(?:"
    r"INSERT|UPDATE|DELETE|DROP|TRUNCATE|CREATE|ALTER|REPLACE|MERGE|"
    r"EXECUTE|EXEC|CALL|GRANT|REVOKE|COPY|VACUUM|ANALYZE|DO|"
    r"LOCK|COMMENT|SECURITY|REINDEX|CLUSTER|PREPARE|DEALLOCATE|"
    r"BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE"
    r")\b",
    re.IGNORECASE,
)

# Row-cap: append LIMIT when missing.
_HAS_LIMIT = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_ROW_CAP = 1_000


def _normalise_sql(raw: str) -> str:
    """Strip comments and string literals, return collapsed whitespace."""
    sql = _STRIP_BLOCK_COMMENT.sub(" ", raw)
    sql = _STRIP_LINE_COMMENT.sub(" ", sql)
    sql = _STRIP_SINGLE_QUOTED.sub("''", sql)
    sql = _STRIP_DOUBLE_QUOTED.sub('""', sql)
    return " ".join(sql.split())


def validate_select_only(sql: str) -> None:
    """Raise ``ValueError`` if *sql* is not a pure SELECT statement.

    Implements all three static layers of the sandbox.  The caller is still
    responsible for executing inside a read-only transaction (Layer 3).
    """
    if not sql or not sql.strip():
        raise ValueError("Empty SQL query.")

    normalised = _normalise_sql(sql)

    # Layer 1 — structural check
    if not _ALLOWED_START.match(normalised):
        raise ValueError(
            f"Query rejected: must start with SELECT or WITH. "
            f"Got: {normalised[:80]!r}"
        )

    # Layer 2 — keyword blacklist
    match = _DANGEROUS_KEYWORDS.search(normalised)
    if match:
        raise ValueError(
            f"Query rejected: forbidden keyword '{match.group().upper()}' detected."
        )


def _apply_row_cap(sql: str) -> str:
    """Append LIMIT {_ROW_CAP} to *sql* if no LIMIT clause is present."""
    clean = _normalise_sql(sql)
    if _HAS_LIMIT.search(clean):
        return sql.rstrip().rstrip(";")
    return f"{sql.rstrip().rstrip(';')} LIMIT {_ROW_CAP}"


# ─── Read-Only SQL Executor ───────────────────────────────────────────────────


class ReadOnlySQLExecutor:
    """Wraps an ``AsyncSession`` and executes only validated SELECT queries.

    Usage::

        executor = ReadOnlySQLExecutor(session)
        rows, columns = await executor.execute("SELECT station_id, SUM(tmu) ...")
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(self, sql: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Validate, cap, and execute *sql* in a read-only transaction.

        Returns:
            (rows, columns) where *rows* is a list of dicts and *columns* is the
            ordered list of column names.

        Raises:
            ValueError: if the SQL fails validation (layers 1 or 2).
            sqlalchemy.exc.SQLAlchemyError: for any database-level error.
        """
        validate_select_only(sql)
        capped_sql = _apply_row_cap(sql)

        # Layer 3 — enforce read-only at the PostgreSQL server level.
        # We use a raw connection so we can issue SET TRANSACTION before the query.
        conn = await self._session.connection()

        # For SQLite (used in tests) SET TRANSACTION READ ONLY is unsupported;
        # skip it silently — layers 1 & 2 are still active.
        dialect_name = conn.dialect.name
        if dialect_name != "sqlite":
            await conn.execute(text("SET TRANSACTION READ ONLY"))

        result = await conn.execute(text(capped_sql))
        columns: list[str] = list(result.keys())
        rows: list[dict[str, Any]] = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows, columns


# ─── LLM Integration ──────────────────────────────────────────────────────────

# JSON schema sent to the LLM (OpenAI function-calling / structured output).
_BI_TOOL_SCHEMA: dict[str, Any] = {
    "name": "render_bi_report",
    "description": "Generate a BI report from a natural-language factory question.",
    "parameters": {
        "type": "object",
        "properties": {
            "sql_query": {
                "type": "string",
                "description": (
                    "A PostgreSQL SELECT query that answers the user's question. "
                    "Use only the tables and columns listed in the schema context. "
                    "Must start with SELECT or WITH."
                ),
            },
            "chart_type": {
                "type": "string",
                "enum": ["BarChart", "LineChart", "PieChart", "Table", "MetricCard"],
                "description": "The most appropriate chart type for visualising the result.",
            },
            "insight": {
                "type": "string",
                "description": "A concise 1-2 sentence explanation of what the data shows.",
            },
        },
        "required": ["sql_query", "chart_type", "insight"],
        "additionalProperties": False,
    },
}


def _build_bi_system_prompt(schema_ddl: str) -> str:
    return f"""You are a Generative BI assistant for a smart manufacturing factory.
Your role: translate the user's natural language question into a valid PostgreSQL SELECT query,
choose the best chart type, and write a brief analytical insight.

## Database Schema
{schema_ddl}

## Rules
1. Only generate SELECT statements. Never use INSERT, UPDATE, DELETE, DROP, or any DML/DDL.
2. Use exact table and column names from the schema above.
3. For time-series questions, use a LineChart.  For comparisons, use BarChart.
   For proportional data, use PieChart.  For multi-column results, use Table.
   For a single KPI number, use MetricCard.
4. Keep the SQL readable and efficient — avoid SELECT *.
5. Always call the render_bi_report function with your answer.
"""


# ─── Mock LLM (test / offline mode) ──────────────────────────────────────────

def _mock_llm_bi_response(query: str) -> dict[str, str]:
    """Deterministic mock that returns a syntactically correct response for offline tests."""
    q = query.lower()
    if "station" in q and ("tmu" in q or "time" in q):
        return {
            "sql_query": (
                "SELECT sa.station_id, SUM(sa.tmu) AS total_tmu "
                "FROM sop_actions sa "
                "WHERE sa.station_id IS NOT NULL "
                "GROUP BY sa.station_id "
                "ORDER BY total_tmu DESC"
            ),
            "chart_type": "BarChart",
            "insight": "Shows total TMU workload aggregated per station.",
        }
    if "project" in q or "sop" in q:
        return {
            "sql_query": (
                "SELECT p.name AS project, COUNT(sv.id) AS sop_count "
                "FROM projects p "
                "LEFT JOIN sop_versions sv ON sv.project_id = p.id "
                "GROUP BY p.name "
                "ORDER BY sop_count DESC"
            ),
            "chart_type": "BarChart",
            "insight": "Shows the number of SOP versions per project.",
        }
    if "ctq" in q or "critical" in q:
        return {
            "sql_query": (
                "SELECT "
                "  SUM(CASE WHEN is_ctq THEN 1 ELSE 0 END) AS ctq_actions, "
                "  SUM(CASE WHEN NOT is_ctq THEN 1 ELSE 0 END) AS non_ctq_actions "
                "FROM sop_actions"
            ),
            "chart_type": "PieChart",
            "insight": "Proportion of CTQ (Critical-to-Quality) vs. standard actions.",
        }
    # Generic fallback
    return {
        "sql_query": (
            "SELECT p.name AS project, p.sku, p.process_type "
            "FROM projects p "
            "ORDER BY p.name"
        ),
        "chart_type": "Table",
        "insight": "Lists all projects in the system.",
    }


def _call_llm(query: str, schema_ddl: str) -> dict[str, str]:
    """Call the OpenAI API (tool-calling mode) or fall back to the mock.

    Returns a dict with keys: sql_query, chart_type, insight.
    """
    api_key = os.environ.get("DDM_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _mock_llm_bi_response(query)

    try:
        import openai  # type: ignore[import-untyped]

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.environ.get("DDM_BI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _build_bi_system_prompt(schema_ddl)},
                {"role": "user", "content": query},
            ],
            tools=[{"type": "function", "function": _BI_TOOL_SCHEMA}],
            tool_choice={"type": "function", "function": {"name": "render_bi_report"}},
            temperature=0,
            max_tokens=512,
        )
        tool_call = response.choices[0].message.tool_calls[0]
        return json.loads(tool_call.function.arguments)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"LLM call failed: {exc}") from exc


# ─── Public API ───────────────────────────────────────────────────────────────

async def generate_bi_report(
    query: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Translate *query* to SQL, execute it, and return a structured BI payload.

    The returned payload is directly serialisable to JSON and consumed by the
    ``DynamicChartRenderer`` component on the frontend::

        {
            "type":    "BarChart",           # chart component to mount
            "data":    [{"station_id": "S1", "total_tmu": 840}, ...],
            "columns": ["station_id", "total_tmu"],
            "xAxis":   "station_id",         # first non-numeric column
            "yAxis":   "total_tmu",          # first numeric column
            "insight": "Shows total TMU workload per station.",
            "sql_query": "SELECT ...",       # echoed for debugging / transparency
        }

    Raises:
        ValueError: if the generated SQL is destructive.
        RuntimeError: if the LLM call fails.
    """
    from ddm_v2.db.schema_inspector import get_bi_schema_ddl

    schema_ddl = get_bi_schema_ddl()
    llm_result = _call_llm(query, schema_ddl)

    sql_query: str = llm_result.get("sql_query", "")
    chart_type: str = llm_result.get("chart_type", "Table")
    insight: str = llm_result.get("insight", "")

    executor = ReadOnlySQLExecutor(session)
    rows, columns = await executor.execute(sql_query)

    # Heuristic: pick xAxis (first TEXT column) and yAxis (first numeric column).
    x_axis: str | None = None
    y_axis: str | None = None
    if rows:
        for col in columns:
            val = rows[0].get(col)
            if x_axis is None and isinstance(val, str):
                x_axis = col
            if y_axis is None and isinstance(val, (int, float)):
                y_axis = col

    # Serialise non-JSON-native types (e.g. Decimal from PostgreSQL aggregates).
    serialisable_rows: list[dict[str, Any]] = []
    for row in rows:
        serialisable_rows.append(
            {k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, bool, type(None))) else v)
             for k, v in row.items()}
        )

    return {
        "type": chart_type,
        "data": serialisable_rows,
        "columns": columns,
        "xAxis": x_axis or (columns[0] if columns else None),
        "yAxis": y_axis or (columns[1] if len(columns) > 1 else None),
        "insight": insight,
        "sql_query": sql_query,
    }
