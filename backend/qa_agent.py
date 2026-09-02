import os
import httpx
from pydantic import BaseModel

class QAQuery(BaseModel):
    question: str
    stats_context: str

class QAAgent:
    def __init__(self, ollama_host: str = None, ollama_model: str = "qwen2.5:latest"):
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = ollama_model
        self.client = httpx.Client(timeout=120.0)
        
        self.gemini_client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
            except Exception as e:
                print(f"[QAAgent] Failed to init Gemini: {e}")

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
            if self.gemini_client:
                try:
                    response = self.gemini_client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt,
                    )
                    return response.text
                except Exception as e:
                    return f"Error connecting to Ollama, and Gemini fallback failed: {str(e)}"
            return "Error connecting to Ollama, and no GEMINI_API_KEY provided for fallback."
        except Exception as e:
            return f"Error from Ollama: {str(e)}"
