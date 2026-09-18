import json


def test_basic_math_is_stable():
    assert 2 + 2 == 4


def test_json_round_trip_is_stable():
    payload = {"topic": "CrewAI", "enabled": True, "count": 3}

    encoded = json.dumps(payload, sort_keys=True)

    assert json.loads(encoded) == payload
