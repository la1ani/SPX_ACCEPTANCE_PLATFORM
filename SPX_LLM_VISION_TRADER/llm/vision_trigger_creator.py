from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from pydantic import ValidationError

from .llm_client import LLMClient
from .prompts import TRIGGER_CREATOR_PROMPT, JSON_REPAIR_PROMPT
from storage.models import TriggerPlan


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class VisionTriggerCreator:
    def __init__(self, client: LLMClient):
        self.client = client

    def create_trigger_plan(self, screenshot_path: str | Path) -> tuple[TriggerPlan, str]:
        raw = self.client.send_vision_request(TRIGGER_CREATOR_PROMPT, screenshot_path)
        try:
            data = extract_json_object(raw)
            plan = TriggerPlan.model_validate(data)
            return plan, raw
        except (json.JSONDecodeError, ValidationError):
            repaired_raw = self.client.send_vision_request(JSON_REPAIR_PROMPT + "\n\nBROKEN RESPONSE:\n" + raw, screenshot_path)
            data = extract_json_object(repaired_raw)
            plan = TriggerPlan.model_validate(data)
            return plan, repaired_raw
