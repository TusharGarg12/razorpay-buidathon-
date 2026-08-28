#!/bin/bash

echo "Setting up dependencies..."
pip install -r backend/requirements.txt

echo "Warming up Ollama..."
curl -s -o /dev/null -X POST http://localhost:11434/api/generate -d '{"model": "qwen2.5:latest", "prompt": "warmup", "stream": false}' || echo "Warning: Ollama might not be running"

echo "Setup complete."
