import os
from google import genai
from pydantic import BaseModel

class QAQuery(BaseModel):
    question: str
    stats_context: str

class QAAgent:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def ask(self, query: str, context: str) -> str:
        if not self.client:
            return "QA Agent is currently in fallback mode (no API key). I cannot answer questions right now."
            
        prompt = f"""
        You are a highly capable Settlement Q&A assistant for the AI Finance Controller.
        You have access to the following context regarding the most recent reconciliation run:
        
        {context}
        
        The user asks: {query}
        
        Answer concisely and professionally based on the context. If you don't know, say so.
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Error connecting to Gemini: {str(e)}"
