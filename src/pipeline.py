from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()  # Load environment variables from .env

from src.parse_sentence import parse_sentence_text
from src.simplify_judgment import load_pdf_text, init_rag, init_model, simplify_sentence_struct, build_readme, save_outputs
from src.config import OUTPUT_DIR

def simplify_document(pdf_path: Path):

    base_name = pdf_path.stem

    # 1) Read the PDF
    print(f"📄 Reading PDF: {pdf_path.name}")
    text = load_pdf_text(pdf_path)

    # 2) Parse judgment
    print("🔎 Parsing judgment...")
    struct = parse_sentence_text(text, doc_id=base_name, source=str(pdf_path))

    # 3) Initialize RAG
    print("🧠 Initializing RAG...")
    guide_ret, judgments_ret = init_rag()

    # 4) Load Gemini model
    print("🤖 Loading Model...")
    model = init_model()

    # 5) Simplify and validate
    print("✍️ Simplifying and validating judgment (with autoregeneration)...")
    result_json = simplify_sentence_struct(model, guide_ret, judgments_ret, struct)

    # 6) Build README markdown
    print("📄 Building README...")
    readme_md = build_readme(result_json)

    # 7) Save to disk (use your existing logic)
    print("💾 Saving files...")
    save_outputs(base_name, result_json, readme_md)

    return base_name, readme_md, result_json

def run_simplification_pipeline_for_streamlit(pdf_path: str) -> Dict[str, Any]:
    """
    Pensada para ser llamada desde Streamlit.

    - Recibe la ruta a un PDF (str).
    - Ejecuta TODO el pipeline de simplificación.
    - Genera los archivos en ./outputs/<base_name>/:
        - resultado.json
        - clarified_<base_name>.pdf
    - Devuelve:
        {
          "base_name": str,
          "markdown": str,        # README simplificado
          "json_struct": dict,    # datos estructurados
          "pdf_bytes": bytes,     # para st.download_button
          "json_bytes": bytes,    # para st.download_button
        }
    """

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")
    
    base_name, readme_md, result_json = simplify_document(pdf_path)

    # 8) Read PDF and JSON as bytes for Streamlit
    folder = Path(OUTPUT_DIR) / base_name
    pdf_file = folder / f"clarified_{base_name}.pdf"
    json_file = folder / "resultado.json"

    with open(pdf_file, "rb") as f:
        pdf_bytes = f.read()

    with open(json_file, "rb") as f:
        json_bytes = f.read()

    return {
        "base_name": base_name,
        "markdown": readme_md,
        "json_struct": result_json,
        "pdf_bytes": pdf_bytes,
        "json_bytes": json_bytes,
    }