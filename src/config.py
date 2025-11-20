GUIDE_DB_DIR = "./chroma_guide"
JUDG_DB_DIR = "./chroma_judgments"
OUTPUT_DIR = "./outputs"

# <<< CHANGE: configuration for primary and fallback models
PRIMARY_MODEL_NAME = "gemini-2.5-flash-lite"
FALLBACK_MODEL_NAME = "gemini-2.0-flash-lite"
CURRENT_MODEL_NAME = PRIMARY_MODEL_NAME  # will be updated at runtime