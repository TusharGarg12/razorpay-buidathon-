Write-Output "Setting up dependencies..."
pip install -r backend/requirements.txt

Write-Output "Warming up Ollama..."
try {
    $body = @{
        model = "qwen2.5:latest"
        prompt = "warmup"
        stream = $false
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/generate" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
    Write-Output "Ollama warmed up successfully."
} catch {
    Write-Output "Warning: Ollama might not be running or the model is missing."
}

Write-Output "Setup complete."
