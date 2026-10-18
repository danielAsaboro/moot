"""Draft the fix: the patch puts a dated 'under review' note in the ADR and applies cleanly; the body is the re-open memo."""
import subprocess

from moot.draftpr import note, patch_for

ADR = "# Use Lerna\n\n- Status: accepted\n- Date: 2020-09-25\n\n## Context\n\nLerna is good.\n"
MEMO = dict(as_of="2026-10-21", verdict="MOOT", broken=[dict(premise=dict(text="Lerna is good practice"),
                                                              evidence=dict(id="src:later", at="2024-12-17"))])


def test_the_patch_applies_and_carries_the_dated_reason(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "adr.md").write_text(ADR)
    p = patch_for(ADR, "docs/adr.md", note(MEMO))
    (tmp_path / "fix.patch").write_text(p)
    subprocess.run(["git", "apply", "fix.patch"], cwd=tmp_path, check=True)
    out = (tmp_path / "docs" / "adr.md").read_text()
    assert "- Date: 2020-09-25\n\n> Under review (2026-10-21)" in out and "src:later contradicted on 2024-12-17" in out
