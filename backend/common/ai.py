"""Thin wrapper around the Gemini API (free tier available in Google AI Studio)."""
import json
import os
import re
import time

import requests


DEFAULT_TIMEOUT = 120


class AIError(Exception):
    pass


class AINotConfigured(AIError):
    pass


def is_configured():
    return bool(os.getenv("GEMINI_API_KEY"))


def generate_json(prompt, timeout=None):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise AINotConfigured("Aucune clé GEMINI_API_KEY n'est configurée sur le serveur.")
    timeout = timeout if timeout is not None else float(os.getenv("GEMINI_TIMEOUT", DEFAULT_TIMEOUT))
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
    }
    for attempt in range(2):
        try:
            response = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=timeout)
            break
        except requests.exceptions.ReadTimeout as exc:
            if attempt == 1:
                raise AIError(
                    "Gemini met trop de temps à répondre après deux tentatives. "
                    "Réessayez dans quelques instants ou augmentez GEMINI_TIMEOUT."
                ) from exc
            time.sleep(1)
        except requests.RequestException as exc:
            raise AIError(f"Le service d'IA a échoué : {exc}") from exc
    if not response.ok:
        try:
            detail = response.json().get("error", {}).get("message")
        except ValueError:
            detail = response.text[:500]
        message = detail or response.reason
        raise AIError(f"Le service d'IA a renvoyé HTTP {response.status_code} : {message}")
    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        return json.loads(text)
    except (KeyError, IndexError, ValueError) as exc:
        raise AIError(f"Le service d'IA a échoué : {exc}") from exc
