from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ImportError:
    def retry(*_args, **_kwargs):
        def deco(func):
            return func
        return deco
    def stop_after_attempt(*_args, **_kwargs):
        return None
    def wait_exponential(*_args, **_kwargs):
        return None


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider.strip().lower()
        self.model = model
        self.api_key = api_key

    def _image_data_url(self, image_path: str | Path) -> str:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Screenshot not found: {path}")
        mime = "image/png"
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=12))
    def send_vision_request(self, prompt: str, image_path: str | Path, extra_text: Optional[str] = None) -> str:
        if self.provider in {"openai", "openrouter"}:
            return self._send_openai_compatible(prompt, image_path, extra_text)
        raise NotImplementedError(f"Provider {self.provider!r} is not implemented yet. Use openai or openrouter.")

    def _send_openai_compatible(self, prompt: str, image_path: str | Path, extra_text: Optional[str]) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai package: pip install openai") from exc
        base_url = "https://openrouter.ai/api/v1" if self.provider == "openrouter" else None
        client = OpenAI(api_key=self.api_key, base_url=base_url)
        image_url = self._image_data_url(image_path)
        text = prompt if not extra_text else f"{prompt}\n\nADDITIONAL DATA:\n{extra_text}"
        try:
            response = client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": image_url}]}],
            )
            return getattr(response, "output_text", "") or str(response)
        except Exception:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": image_url}}]}],
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
