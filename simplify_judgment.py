import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()  # Carga variables de entorno desde .env

from pypdf import PdfReader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import google.generativeai as genai

from parse_sentence import parse_sentence_text


GUIDE_DB_DIR = "./chroma_guide"
JUDG_DB_DIR = "./chroma_judgments"
OUTPUT_DIR = "./outputs"


def load_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def init_rag():
    embeddings = HuggingFaceEmbeddings(
        model_name="intfloat/multilingual-e5-large"
    )
    guide_vs = Chroma(
        embedding_function=embeddings,
        persist_directory=GUIDE_DB_DIR
    )
    judgments_vs = Chroma(
        embedding_function=embeddings,
        persist_directory=JUDG_DB_DIR
    )

    guide_ret = guide_vs.as_retriever(search_kwargs={"k": 4})
    judgments_ret = judgments_vs.as_retriever(search_kwargs={"k": 2})
    return guide_ret, judgments_ret


def build_context(guide_ret, judgments_ret, chunk_text: str) -> Dict[str, str]:
    query = "cómo redactar en lenguaje judicial claro este fragmento: " + chunk_text[:500]
    guide_docs = guide_ret.invoke(query)
    judg_docs = judgments_ret.invoke(chunk_text[:500])
    return {
        "guide": "\n\n".join(d.page_content for d in guide_docs),
        "judgments": "\n\n".join(d.page_content for d in judg_docs)
    }


def init_model():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY no está definida en .env")
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-2.5-flash")


def parse_json_response(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {"simplified_text": "", "summary_original": "", "change_log": []}

    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        json_str = raw_text[start:end + 1] if start != -1 and end != -1 else raw_text
        data = json.loads(json_str)

        return {
            "simplified_text": data.get("simplified_text", "").strip(),
            "summary_original": data.get("summary_original", "").strip(),
            "change_log": data.get("change_log", []) or []
        }
    except Exception:
        return {"simplified_text": raw_text.strip(), "summary_original": "", "change_log": []}


def simplify_chunk(model, contexts, original_text):
    original_text = (original_text or "").strip()
    if not original_text:
        return {"simplified_text": "", "summary_original": "", "change_log": []}

    prompt = f"""
Eres un juez que debe reescribir un fragmento de sentencia en LENGUAJE CLARO. No debes omitir información relevante ni cambiar el sentido del texto original.
No digas quien eres ni nada personal, lo único que debes hacer es reescribir el texto en lenguaje claro siguiendo las indicaciones de la guía y los ejemplos de otras sentencias.

=== CONTEXTO GUÍA ===
{contexts["guide"]}

=== CONTEXTO OTRAS SENTENCIAS ===
{contexts["judgments"]}

=== TEXTO ORIGINAL ===
{original_text}

=== TAREA ===
Devuelve SOLO este JSON:

{{
  "simplified_text": "texto reescrito en lenguaje claro",
  "summary_original": "resumen corto del texto original",
  "change_log": [
    "cambio importante 1",
    "cambio importante 2"
  ]
}}
"""

    response = model.generate_content(prompt)
    raw_text = getattr(response, "text", None)

    if raw_text is None:
        try:
            parts = response.candidates[0].content.parts
            raw_text = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            raw_text = ""

    return parse_json_response(raw_text or "")


def simplify_sentence_struct(model, guide_ret, judgments_ret, doc_struct):
    result = {
        "metadata": doc_struct.get("metadata", {}),
        "sections": []
    }

    for section in doc_struct.get("sections", []):
        if "subsections" in section:
            processed = []
            for sub in section["subsections"]:
                raw = sub.get("raw_text", "").strip()
                chunks = sub.get("chunks", [])

                original_text = (
                    "\n\n".join(ch["text"].strip() for ch in chunks if ch.get("text"))
                    if chunks else raw
                ).strip()

                if not original_text:
                    processed.append({
                        "ordinal": sub.get("ordinal"),
                        "heading": sub.get("heading"),
                        "original_text": "",
                        "simplified_text": "",
                        "summary_original": "",
                        "change_log": []
                    })
                    continue

                ctx = build_context(guide_ret, judgments_ret, original_text)
                info = simplify_chunk(model, ctx, original_text)

                processed.append({
                    "ordinal": sub.get("ordinal"),
                    "heading": sub.get("heading"),
                    "original_text": original_text,
                    "simplified_text": info["simplified_text"],
                    "summary_original": info["summary_original"],
                    "change_log": info["change_log"]
                })

            result["sections"].append({
                "id": section.get("id"),
                "type": section.get("type"),
                "title": section.get("title"),
                "subsections": processed
            })

        else:
            original_text = (section.get("text") or "").strip()
            if original_text:
                ctx = build_context(guide_ret, judgments_ret, original_text)
                info = simplify_chunk(model, ctx, original_text)
            else:
                info = {"simplified_text": "", "summary_original": "", "change_log": []}

            result["sections"].append({
                "id": section.get("id"),
                "type": section.get("type"),
                "title": section.get("title"),
                "original_text": original_text,
                "simplified_text": info["simplified_text"],
                "summary_original": info["summary_original"],
                "change_log": info["change_log"]
            })

    return result


def build_readme(result):
    meta = result["metadata"]
    title = meta.get("roj", meta.get("doc_id", "Sentencia"))
    lines = [f"# {title}\n"]

    if meta.get("organo"):
        lines.append(f"- **Órgano:** {meta['organo']}")
    if meta.get("fecha"):
        lines.append(f"- **Fecha:** {meta['fecha']}")
    if meta.get("procedimiento"):
        lines.append(f"- **Procedimiento:** {meta['procedimiento']}")
    lines.append("\n")

    for section in result["sections"]:
        lines.append(f"## {section['title']}\n")
        if "subsections" in section:
            for sub in section["subsections"]:
                header = ""
                if sub.get("ordinal"):
                    header += sub["ordinal"]
                if sub.get("heading"):
                    header += f". {sub['heading']}"
                if header:
                    lines.append(f"### {header}\n")
                lines.append(sub["simplified_text"] + "\n")

        else:
            lines.append(section["simplified_text"] + "\n")

    return "\n".join(lines)


def save_outputs(base_name: str, json_data: dict, readme_text: str):
    folder = Path(OUTPUT_DIR) / base_name
    folder.mkdir(parents=True, exist_ok=True)

    # Save JSON
    with open(folder / "resultado.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Save README
    with open(folder / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_text)

    print(f"\n💾 Archivos guardados en: {folder.absolute()}")


def main():
    if len(sys.argv) < 2:
        print("Uso: uv run python simplify_judgment.py archivo.pdf")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"No existe: {pdf_path}")
        sys.exit(1)

    base_name = pdf_path.stem

    print(f"📄 Leyendo PDF: {pdf_path.name}")
    text = load_pdf_text(pdf_path)

    print("🔎 Parseando sentencia...")
    struct = parse_sentence_text(text, doc_id=base_name, source=str(pdf_path))

    print("🧠 Inicializando RAG...")
    guide_ret, judgments_ret = init_rag()

    print("🤖 Cargando Gemini...")
    model = init_model()

    print("✍️ Simplificando sentencia...")
    result_json = simplify_sentence_struct(model, guide_ret, judgments_ret, struct)

    print("📄 Construyendo README...")
    readme_md = build_readme(result_json)

    print("💾 Guardando archivos...")
    save_outputs(base_name, result_json, readme_md)

    print("\n🎉 Proceso completado correctamente.")


if __name__ == "__main__":
    main()
