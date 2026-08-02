from pathlib import Path


def test_pr26_document_declares_pr25_stack() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "PR26_TILE_PERCEPTION.md").read_text(encoding="utf-8")
    assert "nasce diretamente da branch da PR25" in text
