from pathlib import Path
import hashlib
import re


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_workspace_uses_one_visual_system_for_the_three_bands():
    assert "--workspace-radius:14px" in HTML
    assert "--workspace-cell-height:82px" in HTML
    assert (
        "#companyWorkspace .company-context,\n"
        "#companyWorkspace .journey-stepper,\n"
        "#companyWorkspace .work-summary"
    ) in HTML


def test_summary_metrics_are_one_unified_module():
    assert (
        "#companyWorkspace .work-summary{\n"
        "  min-height:var(--workspace-cell-height);"
    ) in HTML
    assert "gap:0!important" in HTML
    assert "border-radius:0!important" in HTML
    assert "background:transparent!important" in HTML


def test_step_buttons_have_equal_height_and_flexible_width():
    assert "flex:1 1 0" in HTML
    assert "min-height:58px" in HTML
    assert "width:32px" in HTML
    assert "height:32px" in HTML


def test_existing_javascript_was_not_rewritten_for_visual_change():
    scripts = re.findall(
        r"<script>(.*?)</script>",
        HTML,
        flags=re.S,
    )
    assert scripts
    assert "function updateGuidedJourney()" in scripts[-1]
    assert "async function sendBulkPgdas(files)" in scripts[-1]
