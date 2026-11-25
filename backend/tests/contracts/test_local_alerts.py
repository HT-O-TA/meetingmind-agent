from pathlib import Path


def test_alert_rules_trigger_hold_and_recover(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    from check_local_alerts import transitions

    def sample(ready, dead):
        return {"queues": {
            "document_process": {"ready": ready},
            "document_process.dead": {"ready": dead},
        }}

    baseline = sample(0, 2)
    route = "GET /example"
    failing = {route: {
        "requests": 20, "status_counts": {"500": 2, "200": 18}, "p95_ms": 2500,
    }}
    initial = transitions(failing, baseline, [sample(12, 3), sample(12, 3)], set())
    expected = {
        f"http_errors:{route}", f"http_latency:{route}",
        "queue_backlog:document_process", "new_dead_letter:document_process.dead",
    }
    assert set(initial["triggered"]) == expected
    undersampled = transitions({}, baseline, [sample(12, 3)], expected)
    assert set(undersampled["active"]) == expected
    assert undersampled["recovered"] == []

    healthy = {route: {
        "requests": 20, "status_counts": {"200": 20}, "p95_ms": 100,
    }}
    resolved = transitions(healthy, baseline, [sample(0, 2), sample(0, 2)], expected)
    assert resolved["active"] == []
    assert set(resolved["recovered"]) == expected
