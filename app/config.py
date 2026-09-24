import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # These are api key,model name and base url for llm you can use you own
    API_KEY = os.getenv("OPENROUTER_API_KEY")
    BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    MODEL_NAME = os.getenv(
        "OPENROUTER_MODEL_NAME", "nvidia/nemotron-3-ultra-550b-a55b:free"
    )
