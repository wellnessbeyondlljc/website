"""Behavioral checks for the public reorg structure."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_new_public_surfaces_exist():
    """The new public top-level structure exists."""
    expected_dirs = [
        REPO_ROOT / "docs",
        REPO_ROOT / "shared" / "codebase" / "skills",
        REPO_ROOT / "shared" / "teachings",
        REPO_ROOT / "spoke" / "codebase" / "templates" / "spoke",
        REPO_ROOT / "spoke" / "codebase" / "templates" / "commands",
        REPO_ROOT / "hub" / "codebase" / "skills",
        REPO_ROOT / "hub" / "teachings",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in expected_dirs if not path.is_dir()]
    assert missing == [], f"Missing expected public structure: {missing}"


def test_key_reorganized_assets_exist():
    """A few representative assets are present in the new public locations."""
    expected_files = [
        REPO_ROOT / "docs" / "setup" / "installation.md",
        REPO_ROOT / "shared" / "codebase" / "skills" / "help.yaml",
        REPO_ROOT / "shared" / "teachings" / "skill-system-v1.md.teaching",
        REPO_ROOT / "spoke" / "codebase" / "templates" / "spoke" / "WAI-State.json",
        REPO_ROOT / "spoke" / "codebase" / "templates" / "commands" / "wai.md",
        REPO_ROOT / "hub" / "codebase" / "skills" / "wai" / "wai.md",
        REPO_ROOT / "hub" / "teachings" / "skill-wai-chain-load-v1.md.teaching",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in expected_files if not path.is_file()]
    assert missing == [], f"Missing expected reorganized assets: {missing}"
