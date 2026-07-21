"""Loads the athlete's self-reported context: goals, training split,
injuries, motivation. Static, hand-edited JSON — this bot has no onboarding
chat that fills it in automatically. Edit athlete_profile.json once.
"""
import storage

PROFILE_NAME = "athlete_profile.json"


def load_profile() -> dict:
    return storage.read_json(PROFILE_NAME, {})
