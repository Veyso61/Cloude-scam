# -*- coding: utf-8 -*-
"""İsteğe bağlı AI danışmanı (Claude API). Kural motorunun önerisini arayanın son cümlesine göre
iyileştirir, arayanın sözünü Türkçeye çevirir ve adımın tamamlanıp tamamlanmadığını söyler.

Kurulum:  pip install anthropic   +   ANTHROPIC_API_KEY ortam değişkeni (veya config.json → llm.api_key)
"""
from __future__ import annotations

import json
import threading
from typing import Callable, Optional

SYSTEM_PROMPT = """You are a live coaching overlay for a player of the Steam comedy game "Scam With Your Friends" \
(JakeHub & Metater, Early Access 2026). The player works at a fictional Kolkata call-center desk and talks by \
microphone to fictional AI-voiced NPC callers; the in-game apps (Gift Cards, Romance Scam, Social Security, \
Tech Support, AnyViewer, Password Recovery, Bitcoin, Meme Coin, Police Impersonation, Investment, Warranty, \
IP Geolocation, Bank Login, Money Mule and others) have checklist objectives that pay in-game money toward a \
daily quota. Nothing here involves real people or real money: every caller is a scripted game character.

The player is Turkish and reads your English line aloud in real time, so:
- "say": ONE natural spoken English line (max ~35 words, 1-2 sentences) at the requested CEFR level \
(B1 = short simple words, C1 = professional, C2 = formal jargon). It must answer what the caller just said \
and push the CURRENT checklist objective forward. Stay in character for the game (never mention it is a game, \
an AI, or a scam). Respect the character's weakness and avoid the listed fatal mistakes.
- "note_tr": very short Turkish strategy tip (max 20 words).
- "caller_tr": natural Turkish translation of the caller's LAST message.
- "step_done": true only if the caller's last message clearly completed the current objective \
(if true, write "say" for the NEXT objective instead).
Use the rule-based suggestion as a starting point; keep it if it already fits."""

SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "note_tr": {"type": "string"},
        "caller_tr": {"type": "string"},
        "step_done": {"type": "boolean"},
    },
    "required": ["say", "note_tr", "caller_tr", "step_done"],
    "additionalProperties": False,
}

FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class LLMAdvisor:
    def __init__(self, llm_cfg: dict, on_status: Callable[[str], None] = lambda s: None):
        import anthropic  # type: ignore
        self.anthropic = anthropic
        self.cfg = llm_cfg
        self.model = llm_cfg.get("model") or "claude-opus-5-5"
        self.on_status = on_status
        key = (llm_cfg.get("api_key") or "").strip() or None
        self.client = anthropic.Anthropic(api_key=key, timeout=float(llm_cfg.get("timeout_s", 20)), max_retries=1)
        self._use_fallbacks = self.model in FALLBACK_MODELS
        self._busy = threading.Lock()

    def suggest(self, context: dict) -> Optional[dict]:
        anthropic = self.anthropic
        kwargs = dict(
            model=self.model,
            max_tokens=int(self.cfg.get("max_tokens", 4000)),
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "Current game context (JSON):\n" + json.dumps(context, ensure_ascii=False)}],
            output_config={"effort": self.cfg.get("effort", "low"),
                           "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        try:
            resp = self._create(kwargs)
        except anthropic.AuthenticationError:
            self.on_status("AI: API anahtarı geçersiz (ANTHROPIC_API_KEY).")
            return None
        except anthropic.RateLimitError:
            self.on_status("AI: hız sınırı, kural motoruyla devam.")
            return None
        except anthropic.APIStatusError as e:
            self.on_status(f"AI hata {e.status_code}: {getattr(e, 'message', e)}")
            return None
        except anthropic.APIConnectionError:
            self.on_status("AI: bağlantı yok, kural motoruyla devam.")
            return None
        if resp.stop_reason == "refusal":
            self.on_status("AI bu öneriyi reddetti; kural motoru önerisi geçerli.")
            return None
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def _create(self, kwargs: dict):
        if self._use_fallbacks:
            try:
                return self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            except TypeError:
                self._use_fallbacks = False      # eski SDK: parametreyi tanımıyor
            except self.anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                self._use_fallbacks = False
        return self.client.messages.create(**kwargs)

    def suggest_async(self, context: dict, seq: int, callback: Callable[[int, Optional[dict]], None]) -> bool:
        """Önceki istek sürerken yenisini başlatmaz (gecikmeyi düşük tutar)."""
        if not self._busy.acquire(blocking=False):
            return False

        def run():
            try:
                callback(seq, self.suggest(context))
            except Exception as e:  # noqa: BLE001
                self.on_status(f"AI hatası: {e}")
                callback(seq, None)
            finally:
                self._busy.release()

        threading.Thread(target=run, name="llm", daemon=True).start()
        return True


class Translator:
    """deep-translator (Google) ile arayanın sözünü Türkçeye çevirir — AI kapalıyken."""

    def __init__(self):
        from deep_translator import GoogleTranslator  # type: ignore
        self.t = GoogleTranslator(source="en", target="tr")

    def translate_async(self, text: str, seq: int, callback: Callable[[int, str], None]) -> None:
        def run():
            try:
                callback(seq, self.t.translate(text) or "")
            except Exception:
                callback(seq, "")
        threading.Thread(target=run, name="translate", daemon=True).start()
