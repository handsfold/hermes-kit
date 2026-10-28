---
name: groq_whisperer
description: Transcribe audio files using Groq's high-performance Whisper implementation.
---

# Groq Whisperer (groq_whisperer)

## Description
Transcribe audio files using Groq's high-performance Whisper implementation. Perfect for low-latency transcription of voice messages or audio files.

## Python Reference
```python
import os
from openai import OpenAI

def transcribe(file_path, api_key):
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key
    )
    with open(file_path, "rb") as file:
        return client.audio.transcriptions.create(
            file=file,
            model="whisper-large-v3-turbo",
            response_format="text"
        )
```