from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

from src.parse_sentence import parse_sentence_text
from src.simplify_judgment import load_pdf_text, init_rag, init_model, simplify_sentence_struct, build_readme, save_outputs


def simplify_document(pdf_path: Path):

    base_name = pdf_path.stem

    print(f"📄 Reading PDF: {pdf_path.name}")
    text = load_pdf_text(pdf_path)

    print("🔎 Parsing judgment...")
    struct = parse_sentence_text(text, doc_id=base_name, source=str(pdf_path))

    print("🧠 Initializing RAG...")
    guide_ret, judgments_ret = init_rag()

    print("🤖 Loading Gemini...")
    model = init_model()

    print("✍️ Simplifying and validating judgment (with autoregeneration)...")
    result_json = simplify_sentence_struct(model, guide_ret, judgments_ret, struct)

    print("📄 Building README...")
    readme_md = build_readme(result_json)

    print("💾 Saving files...")
    save_outputs(base_name, result_json, readme_md)

    print("\n🎉 Process completed successfully.")