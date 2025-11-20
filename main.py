import sys
from pathlib import Path

from src.pipeline import simplify_document

def main():

    if len(sys.argv) < 2:
        print("Usage: uv run python main.py file.pdf")
        sys.exit(1)
    
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")
    
    _ = simplify_document(pdf_path)


if __name__ == "__main__":
    main()
