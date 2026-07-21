"""Loads the athlete's self-reported context: goals, training split,
injuries, motivation. Static, hand-edited JSON — this bot is push-only
(GitHub Actions cron, no live listener), so there's no onboarding chat to
collect this automatically. Fill in data/athlete_profile.json once.
"""
import json
import os

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "athlete_profile.json")


def load_profile() -> dict:
    if not os.path.exists(PROFILE_PATH):
        return {}
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
