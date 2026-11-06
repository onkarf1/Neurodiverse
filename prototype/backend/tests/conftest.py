import os

# Tests never call a real model, even when the developer's .env holds a key.
os.environ["STRIVETRACK_AI_API_KEY"] = ""
