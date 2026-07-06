from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import ValidationError

from .llm_client import LLMClient
from .prompts import BATTLE_ANALYZER_PROMPT, JSON_REPAIR_PROMPT
from .vision_trigger_creator import extract_json_object
from storage.models import BattleDecision


class BattleAnalyzer:
    def __init__(self, client: LLMClient):
        self.client = client

    def analyze(self, screenshot_path: str | Path, trigger_plan: dict[str, Any], call_rows: list[dict[str, Any]], put_rows: list[dict[str, Any]], memory: list[dict[str, Any]], previous_grading: list[dict[str, Any]]) -> tuple[BattleDecision, str]:
        extra = json.dumps({"original_trigger_plan": trigger_plan, "call_sheet_rows": call_rows, "put_sheet_rows": put_rows, "battle_memory": memory, "previous_grading": previous_grading}, ensure_ascii=False, default=str)
        raw = self.client.send_vision_request(BATTLE_ANALYZER_PROMPT, screenshot_path, extra_text=extra)
        try:
            data = extract_json_object(raw)
            decision = BattleDecision.model_validate(data)
            return decision, raw
        except (json.JSONDecodeError, ValidationError):
            repaired_raw = self.client.send_vision_request(JSON_REPAIR_PROMPT + "\n\nBROKEN RESPONSE:\n" + raw, screenshot_path, extra_text=extra)
            data = extract_json_object(repaired_raw)
            decision = BattleDecision.model_validate(data)
            return decision, repaired_raw
