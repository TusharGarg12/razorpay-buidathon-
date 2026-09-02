import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from llm_agent import OllamaAgent
import httpx
import config

@pytest.fixture(autouse=True)
def disable_gemini(monkeypatch):
    monkeypatch.setattr("llm_agent._gemini_is_blocked", lambda: True)

@patch("llm_agent.httpx.Client")
def test_ollama_agent_malformed_json(mock_client_class):
    """
    Tests that a malformed JSON response from the LLM immediately triggers the fallback logic.
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    # return malformed JSON string directly since raw_text uses response.json().get('response')
    # wait, response.json() will fail if the overall response isn't JSON.
    # Ollama returns valid JSON with a "response" field containing the malformed string.
    mock_response.json.return_value = {"response": '{"decision": "match", "confi'}
    mock_client.post.return_value = mock_response
    
    agent = OllamaAgent()
    agent.client = mock_client
    
    bank_rec = {'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    candidate = {'txn_id': 'L1', 'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    
    # Resolve should fallback to heuristic
    result = agent.resolve(bank_rec, [candidate])
    
    # In heuristic fallback for exact match, conf is 1.0 > 0.6 => match
    assert result["is_fallback"] is True
    assert result["confidence"] == 1.0
    assert result["decision"] == "match"
    assert result["ledger_id"] == "L1"

@patch("llm_agent.httpx.Client")
def test_ollama_agent_missing_fields(mock_client_class):
    """
    Tests that a JSON response missing 'decision' or 'confidence' triggers the fallback.
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": '{"decision": "match", "reason": "Looks good"}'}
    mock_client.post.return_value = mock_response
    
    agent = OllamaAgent()
    agent.client = mock_client
    
    bank_rec = {'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    candidate = {'txn_id': 'L1', 'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    
    result = agent.resolve(bank_rec, [candidate])
    
    assert result["is_fallback"] is True
    assert result["decision"] == "match"

@patch("llm_agent.httpx.Client")
def test_ollama_agent_connection_error(mock_client_class):
    """
    Tests that Connection Errors (or timeouts) trigger retry/fallback.
    """
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_client.post.side_effect = httpx.ConnectError("Connection Failed")
    
    agent = OllamaAgent()
    agent.client = mock_client
    
    bank_rec = {'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    candidate = {'txn_id': 'L1', 'amount': 100, 'date': '2023-01-01', 'description': 'test'}
    
    result = agent.resolve(bank_rec, [candidate])
    
    assert result["is_fallback"] is True
