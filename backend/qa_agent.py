import os
import httpx
from pydantic import BaseModel

class QAQuery(BaseModel):
    question: str
    stats_context: str

class QAAgent:
    def __init__(self, ollama_host: str = "http://localhost:11434", ollama_model: str = "qwen2.5:latest"):
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model
        self.client = httpx.Client(timeout=120.0)

    def ask(self, query: str, context: str) -> str:
        prompt = f"""You are a highly capable Settlement Q&A assistant for the AI Finance Controller.
You have access to the following context regarding the most recent reconciliation run:

{context}

The user asks: {query}

Answer concisely and professionally based on the context. If you don't know, say so."""

        try:
            resp = self.client.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "Sorry, I couldn't generate a response.")
        except httpx.ConnectError:
            return "Error connecting to Ollama. Is the Ollama service running on localhost:11434?"
        except Exception as e:
            return f"Error from Ollama: {str(e)}"
