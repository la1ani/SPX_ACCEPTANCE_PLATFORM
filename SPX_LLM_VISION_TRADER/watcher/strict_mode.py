from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import io
import tokenize


@dataclass
class StrictModeFinding:
    file_path: str
    line: int
    term: str
    text: str


class StrictModeScanner:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.skip_parts = {".git", "__pycache__", "outputs", "tradingview_profile"}
        self.allowed_files = {
            "llm/prompts.py",
            "storage/models.py",
            "storage/database.py",
            "watcher/strict_mode.py",
            "sheets/google_sheet_reader.py",
        }
        self.forbidden_terms = ["bullish", "bearish", "weak_side", "strong_side", "support_broken", "resistance_failed", "winner", "trade_direction", "trade_grade", "full_hand", "light_hand", "no_trade_reason", "rejection_confirmed", "velocity_after_failure", "support_hold", "support_break", "volume_imbalance", "power_transfer"]

    def _should_scan(self, path: Path) -> bool:
        if path.suffix != ".py":
            return False
        if any(part in self.skip_parts for part in path.parts):
            return False
        rel = path.relative_to(self.root_dir).as_posix()
        return rel not in self.allowed_files

    def scan(self) -> list[StrictModeFinding]:
        findings: list[StrictModeFinding] = []
        for path in self.root_dir.rglob("*.py"):
            if not self._should_scan(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            try:
                tokens = tokenize.generate_tokens(io.StringIO(text).readline)
                for token in tokens:
                    if token.type != tokenize.NAME:
                        continue
                    token_text = token.string.lower()
                    for term in self.forbidden_terms:
                        if token_text == term:
                            findings.append(StrictModeFinding(str(path.relative_to(self.root_dir)), token.start[0], term, token.line.strip()))
            except tokenize.TokenError:
                findings.append(StrictModeFinding(str(path.relative_to(self.root_dir)), 1, "TOKENIZE_ERROR", "Could not tokenize file"))
        return findings

    def print_report(self, block: bool = False) -> None:
        findings = self.scan()
        if not findings:
            print("[strict-mode] OK: no forbidden trading-intelligence terms found in restricted Python files.")
            return
        print("[strict-mode] WARNING: Python may be creating trading intelligence. Move this logic into LLM prompts or LLM response schema.")
        for item in findings:
            print(f"  - {item.file_path}:{item.line} term={item.term} :: {item.text}")
        if block:
            raise RuntimeError("STRICT_MODE_BLOCK=true and strict mode found violations.")
