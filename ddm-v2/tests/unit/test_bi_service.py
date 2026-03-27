"""Unit tests for the BI service — SQL sandbox security and text-to-SQL flow.

Test coverage:
  1. test_bi_service_rejects_destructive_sql  — Proves the sandbox blocks all DML/DDL.
  2. test_bi_service_allows_valid_select      — Healthy path: pure SELECT passes validation.
  3. test_bi_service_rejects_empty_query      — Edge case: empty input is rejected.
  4. test_bi_service_row_cap_injected         — LIMIT is auto-appended when absent.
  5. test_bi_service_existing_limit_preserved — Existing LIMIT is honoured unchanged.
  6. test_bi_service_rejects_cte_with_dml     — WITH ... DELETE inside a CTE is rejected.
  7. test_bi_service_text_to_sql_generation   — End-to-end flow with mocked LLM + SQLite.
"""

from __future__ import annotations

import pytest
import pytest_asyncio  # noqa: F401  (keeps asyncio plugin happy)

from ddm_v2.services.bi_service import (
    _apply_row_cap,
    _mock_llm_bi_response,
    validate_select_only,
    ReadOnlySQLExecutor,
    generate_bi_report,
)

# ─── Parametric security suite ────────────────────────────────────────────────

_DESTRUCTIVE_CASES = [
    # Plain DML
    ("INSERT INTO users VALUES (1, 'x')", "INSERT"),
    ("UPDATE stations SET name='hack' WHERE 1=1", "UPDATE"),
    ("DELETE FROM sop_actions", "DELETE"),
    # DDL
    ("DROP TABLE sop_actions", "DROP"),
    ("TRUNCATE TABLE sop_versions", "TRUNCATE"),
    ("CREATE TABLE evil (id int)", "CREATE"),
    ("ALTER TABLE users ADD COLUMN backdoor TEXT", "ALTER"),
    # Tricky: SELECT wrapper hiding a DML statement
    ("SELECT 1; DROP TABLE users;", "DROP"),
    # Tricky: DML keyword hidden inside CTE wrapper
    ("WITH x AS (SELECT 1) DELETE FROM projects", "DELETE"),
    # Uppercase variations
    ("drop table projects", "drop"),
    # DML with leading whitespace / newlines
    ("\n\n   UPDATE users SET role='admin'", "UPDATE"),
    # COPY (PostgreSQL data-exfil)
    ("COPY users TO '/tmp/dump.csv'", "COPY"),
    # DO (anonymous PL/pgSQL block)
    ("DO $$ BEGIN RAISE NOTICE 'x'; END $$", "DO"),
    # EXECUTE (dynamic SQL)
    ("EXECUTE 'DROP TABLE users'", "EXECUTE"),
]


@pytest.mark.unit
@pytest.mark.parametrize("sql, label", _DESTRUCTIVE_CASES)
def test_bi_service_rejects_destructive_sql(sql: str, label: str) -> None:
    """The sandbox MUST raise ValueError for any destructive statement."""
    with pytest.raises(ValueError, match=r"(?i)(forbidden|rejected|must start)"):
        validate_select_only(sql)


# ─── Allowed path ─────────────────────────────────────────────────────────────

_SAFE_CASES = [
    "SELECT * FROM projects",
    "select id, name from stations",
    "SELECT sa.tmu, sa.station_id FROM sop_actions sa WHERE sa.is_ctq = true",
    # CTE that is purely SELECT
    "WITH summary AS (SELECT station_id, SUM(tmu) AS t FROM sop_actions GROUP BY station_id) SELECT * FROM summary",
    # Leading whitespace
    "   SELECT 1",
]


@pytest.mark.unit
@pytest.mark.parametrize("sql", _SAFE_CASES)
def test_bi_service_allows_valid_select(sql: str) -> None:
    """Pure SELECT queries must pass validation without raising."""
    validate_select_only(sql)  # should not raise


# ─── Edge cases ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_bi_service_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="Empty"):
        validate_select_only("")


@pytest.mark.unit
def test_bi_service_rejects_whitespace_only_query() -> None:
    with pytest.raises(ValueError):
        validate_select_only("   \n\t  ")


# ─── Row-cap guard ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_bi_service_row_cap_injected() -> None:
    """LIMIT 1000 must be appended to queries that lack a LIMIT clause."""
    capped = _apply_row_cap("SELECT * FROM projects")
    assert "LIMIT 1000" in capped


@pytest.mark.unit
def test_bi_service_existing_limit_preserved() -> None:
    """A query already containing LIMIT must not have another LIMIT appended."""
    original = "SELECT * FROM projects LIMIT 5"
    capped = _apply_row_cap(original)
    # Should not gain a second LIMIT
    assert capped.upper().count("LIMIT") == 1
    assert "5" in capped


# ─── CTE with embedded DML ───────────────────────────────────────────────────

@pytest.mark.unit
def test_bi_service_rejects_cte_with_dml() -> None:
    """A WITH clause that wraps a DELETE must be rejected (Layer 2 blacklist)."""
    malicious = "WITH x AS (SELECT 1) DELETE FROM sop_versions WHERE 1=1"
    with pytest.raises(ValueError, match=r"(?i)forbidden"):
        validate_select_only(malicious)


# ─── Mock LLM smoke test ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_mock_llm_bi_response_station_query() -> None:
    result = _mock_llm_bi_response("Show TMU per station")
    assert "sql_query" in result
    assert result["chart_type"] in {"BarChart", "LineChart", "PieChart", "Table", "MetricCard"}
    assert result["insight"]
    # The generated SQL must itself pass validation
    validate_select_only(result["sql_query"])


@pytest.mark.unit
def test_mock_llm_bi_response_project_query() -> None:
    result = _mock_llm_bi_response("How many SOP versions per project?")
    validate_select_only(result["sql_query"])


@pytest.mark.unit
def test_mock_llm_bi_response_ctq_query() -> None:
    result = _mock_llm_bi_response("What proportion of actions are CTQ?")
    assert result["chart_type"] == "PieChart"
    validate_select_only(result["sql_query"])


# ─── End-to-end flow (mock LLM + SQLite) ─────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_bi_service_text_to_sql_generation(tmp_path) -> None:
    """Full pipeline test: schema injection → mock LLM → SQL execution → structured payload.

    Uses an in-process SQLite database so no external services are needed.
    The mock LLM bypasses the OpenAI call (DDM_OPENAI_API_KEY is not set).
    """
    import os

    # Ensure LLM mock path is taken.
    os.environ.pop("DDM_OPENAI_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)

    db_url = f"sqlite+aiosqlite:///{tmp_path}/bi_test.db"

    import ddm_v2.models.domain  # noqa: F401
    from ddm_v2.db.database import init_db, get_engine, get_session_factory
    from ddm_v2.models.domain import Base

    init_db(db_url)
    engine = get_engine()
    # Create all tables in the test SQLite DB.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory()
    async with session_factory() as session:
        payload = await generate_bi_report("Show total TMU by station", session)

    # Structural checks on the returned payload.
    assert "type" in payload
    assert payload["type"] in {"BarChart", "LineChart", "PieChart", "Table", "MetricCard"}
    assert isinstance(payload["data"], list)
    assert isinstance(payload["columns"], list)
    assert isinstance(payload["insight"], str) and payload["insight"]
    assert isinstance(payload["sql_query"], str)
    # The echoed SQL must itself be safe.
    validate_select_only(payload["sql_query"])
