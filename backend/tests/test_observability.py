from app.utils.observability import search_log_entries


def test_correlation_id_propagates_and_logs_are_searchable(client):
    response = client.post(
        "/api/prompts/preview",
        json={
            "base_prompt": "Hello {{user_context}}",
            "variables": {
                "user_context": "email alice@example.com api_key=supersecret",
                "memory_summary": "previous",
                "guardrail_rules": "none",
            },
        },
        headers={"X-Correlation-ID": "corr-test-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-test-123"

    search = client.get("/api/logs/search", params={"correlation_id": "corr-test-123"})
    assert search.status_code == 200
    body = search.json()
    assert body["correlation_id"] == "corr-test-123"
    assert body["entries"]
    serialized = str(body["entries"])
    assert "alice@example.com" not in serialized
    assert "supersecret" not in serialized

    assert search_log_entries("corr-test-123")
