import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python main.py file.pdf")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Does not exist: {pdf_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
