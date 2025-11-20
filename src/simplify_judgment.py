import os
import json
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

from pypdf import PdfReader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions  # <<< CHANGE
from types import SimpleNamespace  # <<< CHANGE

# To generate the PDF without wkhtmltopdf
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors

import re

from src.config import OUTPUT_DIR, PRIMARY_MODEL_NAME, CURRENT_MODEL_NAME, FALLBACK_MODEL_NAME, GUIDE_DB_DIR, JUDG_DB_DIR


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
    query = "cómo redactar en lenguaje judicial claro este fragmento: " + chunk_text[:800]
    guide_docs = guide_ret.invoke(query)
    judg_docs = judgments_ret.invoke(chunk_text[:800])
    return {
        "guide": "\n\n".join(d.page_content for d in guide_docs),
        "judgments": "\n\n".join(d.page_content for d in judg_docs)
    }


def init_model():
    """
    Initializes Gemini with the primary model.
    The fallback is handled in generate_with_fallback.
    """
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY no está definida en .env")
    genai.configure(api_key=key)

    global CURRENT_MODEL_NAME
    CURRENT_MODEL_NAME = PRIMARY_MODEL_NAME

    # We use the primary model; quota retries are handled separately
    return genai.GenerativeModel(PRIMARY_MODEL_NAME)


# <<< CHANGE: helper to use the fallback model if there is a quota error
def generate_with_fallback(model, prompt: str):
    """
    Calls model.generate_content(prompt). If there is a quota error (ResourceExhausted)
    or a timeout (DeadlineExceeded), it retries with the fallback model.
    If the fallback also fails, it returns an empty response so that the
    pipeline does not crash and the fragment is marked as high risk.
    """
    global CURRENT_MODEL_NAME

    try:
        # 1st attempt: primary model
        response = model.generate_content(prompt)
        CURRENT_MODEL_NAME = PRIMARY_MODEL_NAME
        return response

    except (google_exceptions.ResourceExhausted,
            google_exceptions.DeadlineExceeded) as e:
        print(f"⚠️ Error with {PRIMARY_MODEL_NAME} ({e.__class__.__name__}): {e}")
        print(f"   Trying fallback model {FALLBACK_MODEL_NAME}...")

        fallback_model = genai.GenerativeModel(FALLBACK_MODEL_NAME)
        try:
            response = fallback_model.generate_content(prompt)
            CURRENT_MODEL_NAME = FALLBACK_MODEL_NAME
            return response

        except (google_exceptions.ResourceExhausted,
                google_exceptions.DeadlineExceeded) as e2:
            print(f"❌ Fallback model {FALLBACK_MODEL_NAME} also failed ({e2.__class__.__name__}).")
            print("   Continuing without LLM response; this fragment will be marked as high risk.")
            CURRENT_MODEL_NAME = "none"
            # Minimal object compatible with the rest of the code (has a .text attribute)
            return SimpleNamespace(text="")


def parse_json_response(raw_text: str) -> Dict[str, Any]:
    """
    Parser for the SIMPLIFICATION RESPONSE.
    Expects a JSON with:
    {
      "simplified_text": "...",
      "incorrect_things": "...",
      "change_log": [...]
    }
    """
    if not raw_text:
        return {
            "simplified_text": "",
            "incorrect_things": "",
            "change_log": []
        }

    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        json_str = raw_text[start:end + 1] if start != -1 and end != -1 else raw_text
        data = json.loads(json_str)

        return {
            "simplified_text": data.get("simplified_text", "").strip(),
            "incorrect_things": data.get("incorrect_things", "").strip(),
            "change_log": data.get("change_log", []) or []
        }
    except Exception:
        return {
            "simplified_text": raw_text.strip(),
            "incorrect_things": "",
            "change_log": []
        }


def parse_validation_response(raw_text: str) -> Dict[str, Any]:
    """
    Parser for the VALIDATION RESPONSE OF THE SPIRIT OF THE LAW.
    Expects a JSON with:
    {
      "spirit_respected": true/false,
      "risk_level": "low"/"medium"/"high"/"unknown",
      "issues": ["...", "..."]
    }
    """
    if not raw_text:
        return {
            "spirit_respected": False,
            "risk_level": "unknown",
            "issues": ["Respuesta vacía del validador. Revisar manualmente."]
        }

    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        json_str = raw_text[start:end + 1] if start != -1 and end != -1 else raw_text
        data = json.loads(json_str)

        return {
            "spirit_respected": bool(data.get("spirit_respected", False)),
            "risk_level": (data.get("risk_level") or "unknown").strip(),
            "issues": data.get("issues", []) or []
        }
    except Exception:
        return {
            "spirit_respected": False,
            "risk_level": "unknown",
            "issues": [
                "No se pudo interpretar la respuesta del validador LLM. Revisar manualmente."
            ]
        }


def simplify_chunk(model, contexts, original_text: str, regen_hint: str | None = None) -> Dict[str, Any]:
    """
    First LLM step: rewriting into plain language + listing drafting issues + change_log.
    regen_hint: additional text for retries (Mode C: intelligent autoregeneration).
    """
    original_text = (original_text or "").strip()
    if not original_text:
        return {
            "simplified_text": "",
            "incorrect_things": "",
            "change_log": []
        }

    extra_block = ""
    if regen_hint:
        extra_block = f"""

=== INSTRUCCIONES ADICIONALES PARA CORREGIR ERRORES DETECTADOS ===
{regen_hint}
Debes corregir estrictamente estos problemas en esta nueva versión simplificada.
No cambies las partes, plazos, cantidades ni efectos jurídicos respecto al original.
"""

    prompt = f"""
Eres un juez que debe reescribir un fragmento de sentencia en LENGUAJE CLARO. No debes omitir información relevante ni cambiar el sentido del texto original.
No digas quién eres ni nada personal, lo único que debes hacer es reescribir el texto en lenguaje claro siguiendo las indicaciones de la guía y los ejemplos de otras sentencias.

Además, debes detectar y etiquetar los principales problemas de redacción del texto original (por ejemplo, mayusculismo, frases demasiado largas, tecnicismos innecesarios, falta de orden lógico, etc.), de acuerdo con la guía de lenguaje judicial claro.
{extra_block}

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
  "incorrect_things": "lista breve (en texto libre) de los principales errores o malas prácticas del original, usando etiquetas como 'mayusculismo', 'frases farragosas', 'tecnicismos sin explicación', etc.",
  "change_log": [
    "cambio importante 1",
    "cambio importante 2"
  ]
}}
"""

    # <<< CHANGE: use generate_with_fallback
    response = generate_with_fallback(model, prompt)
    raw_text = getattr(response, "text", None)

    if raw_text is None:
        try:
            parts = response.candidates[0].content.parts
            raw_text = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            raw_text = ""

    return parse_json_response(raw_text or "")


def validate_spirit(model, original_text: str, simplified_text: str) -> Dict[str, Any]:
    """
    Second LLM step: validation of the "spirit of the law".
    Compares original vs simplified and returns a JSON with risk flags.
    """
    original_text = (original_text or "").strip()
    simplified_text = (simplified_text or "").strip()

    if not original_text or not simplified_text:
        return {
            "spirit_respected": False,
            "risk_level": "not_applicable",
            "issues": ["No hay texto suficiente para validar el espíritu de la norma."]
        }

    prompt = f"""
Actúas como un juez auditor que comprueba si una versión en lenguaje claro de un fragmento de sentencia mantiene el MISMO sentido jurídico y el espíritu de la norma que el texto original.

Debes fijarte especialmente en:
- Que no cambien las partes (quién demanda, quién es demandado).
- Que no cambien el fallo ni el sentido de la decisión.
- Que no se alteren plazos, importes, intereses, fechas clave ni advertencias legales.
- Que no se añadan nuevos efectos jurídicos ni se eliminen efectos relevantes.
- Que el tono no banalice obligaciones o responsabilidades importantes.

=== TEXTO ORIGINAL (JURÍDICO) ===
{original_text}

=== TEXTO SIMPLIFICADO (LENGUAJE CLARO) ===
{simplified_text}

=== TAREA ===
Devuelve SOLO un JSON con este formato:

{{
  "spirit_respected": true/false,
  "risk_level": "low" | "medium" | "high" | "unknown",
  "issues": [
    "breve explicación de posibles divergencias relevantes entre original y simplificado",
    "otra posible divergencia"
  ]
}}
- "spirit_respected" debe ser false si hay cualquier duda razonable sobre cambios en fallo, plazos, importes, sujetos o efectos.
- Si todo está correcto, usa:
  "spirit_respected": true,
  "risk_level": "low",
  "issues": []
"""

    # <<< CHANGE: use generate_with_fallback
    response = generate_with_fallback(model, prompt)
    raw_text = getattr(response, "text", None)

    if raw_text is None:
        try:
            parts = response.candidates[0].content.parts
            raw_text = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            raw_text = ""

    return parse_validation_response(raw_text or "")


def compute_quality_score(simplified_text: str, validation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes a quality score 0-100 based on:
    - Respect for the spirit of the law.
    - Risk level.
    - Existence of issues.
    """
    base = 100

    spirit = validation.get("spirit_respected", False)
    risk = (validation.get("risk_level") or "unknown").lower()
    issues = validation.get("issues", []) or []

    if not spirit:
        base -= 40

    if risk == "medium":
        base -= 15
    elif risk == "high":
        base -= 35
    elif risk == "unknown":
        base -= 10

    if issues:
        # Small penalty for non-empty issues
        base -= 5

    # Smoothing and bounds
    score = max(0, min(100, base))

    if score >= 90:
        label = "excellent"
    elif score >= 80:
        label = "good"
    elif score >= 60:
        label = "acceptable"
    else:
        label = "risky"

    return {
        "quality_score": score,
        "quality_label": label
    }


def simplify_and_validate_with_regen(
    model,
    guide_ret,
    judgments_ret,
    original_text: str,
    max_attempts: int = 3
) -> Dict[str, Any]:
    """
    Mode C: intelligent autoregeneration.
    - Tries simplify + validate.
    - If spirit validation fails or risk is medium/high, regenerates using hints.
    - Returns full info for the fragment, including attempts and auto_regenerated.
    """
    original_text = (original_text or "").strip()
    if not original_text:
        empty_validation = {
            "spirit_respected": False,
            "risk_level": "not_applicable",
            "issues": ["Sin texto que validar."]
        }
        quality = compute_quality_score("", empty_validation)
        return {
            "original_text": "",
            "simplified_text": "",
            "incorrect_things": "",
            "change_log": [],
            "validation": empty_validation,
            "quality": quality,
            "attempts": 0,
            "auto_regenerated": False
        }

    contexts = build_context(guide_ret, judgments_ret, original_text)

    last_info = None
    last_validation = None
    auto_regenerated = False

    for attempt in range(1, max_attempts + 1):
        regen_hint = None

        # From the second attempt onward, generate hints using the previous validation
        if attempt > 1 and last_validation is not None:
            issues = last_validation.get("issues", [])
            risk = last_validation.get("risk_level", "unknown")
            regen_hint_lines = [
                f"- Riesgo detectado: {risk}",
                "- Corrige específicamente las divergencias identificadas por el validador.",
            ]
            regen_hint_lines.extend([f"- {i}" for i in issues])
            regen_hint = "\n".join(regen_hint_lines)
            auto_regenerated = True

        info = simplify_chunk(model, contexts, original_text, regen_hint=regen_hint)
        simplified_text = info.get("simplified_text", "").strip()

        validation = validate_spirit(model, original_text, simplified_text)

        last_info = info
        last_validation = validation

        spirit_ok = validation.get("spirit_respected", False)
        risk = (validation.get("risk_level") or "unknown").lower()
        issues = validation.get("issues", []) or []

        # Strict success condition
        if spirit_ok and risk == "low" and not issues:
            break

    # If after all attempts the spirit is still not clearly respected, escalate risk
    if last_validation is None:
        last_validation = {
            "spirit_respected": False,
            "risk_level": "unknown",
            "issues": ["No se obtuvo respuesta de validación."]
        }

    if (not last_validation.get("spirit_respected", False)) or \
       (last_validation.get("risk_level", "").lower() in ["medium", "high", "unknown"] and auto_regenerated):
        # Mark as high risk if it could not be cleaned after several attempts
        if last_validation.get("risk_level", "").lower() != "high":
            last_validation["risk_level"] = "high"
        issues = last_validation.get("issues", []) or []
        issues.append("Auto-regeneración agotada; requiere revisión humana.")
        last_validation["issues"] = issues

    quality = compute_quality_score(last_info.get("simplified_text", ""), last_validation)

    return {
        "original_text": original_text,
        "simplified_text": last_info.get("simplified_text", ""),
        "incorrect_things": last_info.get("incorrect_things", ""),
        "change_log": last_info.get("change_log", []),
        "validation": last_validation,
        "quality": quality,
        "attempts": attempt,
        "auto_regenerated": auto_regenerated
    }


def simplify_sentence_struct(model, guide_ret, judgments_ret, doc_struct):
    result: Dict[str, Any] = {
        "metadata": doc_struct.get("metadata", {}),
        "sections": [],
        "audit_log": {}  # will be filled at the end
    }

    total_sections = 0
    total_subsections = 0
    auto_regen_count = 0
    high_risk_fragments: List[Dict[str, Any]] = []
    medium_risk_fragments: List[Dict[str, Any]] = []
    fragment_scores: List[float] = []
    fragment_audit_entries: List[Dict[str, Any]] = []

    for section in doc_struct.get("sections", []):
        total_sections += 1

        if "subsections" in section:
            processed = []
            for sub in section["subsections"]:
                total_subsections += 1

                raw = sub.get("raw_text", "").strip()
                chunks = sub.get("chunks", [])

                original_text = (
                    "\n\n".join(ch["text"].strip() for ch in chunks if ch.get("text"))
                    if chunks else raw
                ).strip()

                if not original_text:
                    empty_validation = {
                        "spirit_respected": False,
                        "risk_level": "not_applicable",
                        "issues": ["Sin texto que validar."]
                    }
                    empty_quality = compute_quality_score("", empty_validation)
                    fragment_data = {
                        "ordinal": sub.get("ordinal"),
                        "heading": sub.get("heading"),
                        "original_text": "",
                        "simplified_text": "",
                        "incorrect_things": "",
                        "change_log": [],
                        "validation": empty_validation,
                        "quality": empty_quality,
                        "attempts": 0,
                        "auto_regenerated": False
                    }
                else:
                    fragment_data = simplify_and_validate_with_regen(
                        model, guide_ret, judgments_ret, original_text
                    )
                    fragment_data["ordinal"] = sub.get("ordinal")
                    fragment_data["heading"] = sub.get("heading")

                processed.append(fragment_data)

                # Audit info per fragment
                val = fragment_data["validation"]
                q = fragment_data["quality"]
                risk = (val.get("risk_level") or "unknown").lower()

                if isinstance(q.get("quality_score"), (int, float)):
                    fragment_scores.append(q["quality_score"])

                if fragment_data.get("auto_regenerated"):
                    auto_regen_count += 1

                frag_id = {
                    "section_id": section.get("id"),
                    "section_title": section.get("title"),
                    "ordinal": fragment_data.get("ordinal"),
                    "heading": fragment_data.get("heading")
                }

                if risk == "high":
                    high_risk_fragments.append(frag_id)
                elif risk == "medium":
                    medium_risk_fragments.append(frag_id)

                fragment_audit_entries.append({
                    **frag_id,
                    "risk_level": risk,
                    "spirit_respected": val.get("spirit_respected", False),
                    "quality_score": q.get("quality_score"),
                    "quality_label": q.get("quality_label"),
                    "attempts": fragment_data.get("attempts", 0),
                    "auto_regenerated": fragment_data.get("auto_regenerated", False)
                })

            result["sections"].append({
                "id": section.get("id"),
                "type": section.get("type"),
                "title": section.get("title"),
                "subsections": processed
            })

        else:
            original_text = (section.get("text") or "").strip()
            if not original_text:
                empty_validation = {
                    "spirit_respected": False,
                    "risk_level": "not_applicable",
                    "issues": ["Sin texto que validar."]
                }
                empty_quality = compute_quality_score("", empty_validation)
                fragment_data = {
                    "original_text": "",
                    "simplified_text": "",
                    "incorrect_things": "",
                    "change_log": [],
                    "validation": empty_validation,
                    "quality": empty_quality,
                    "attempts": 0,
                    "auto_regenerated": False
                }
            else:
                fragment_data = simplify_and_validate_with_regen(
                    model, guide_ret, judgments_ret, original_text
                )

            result["sections"].append({
                "id": section.get("id"),
                "type": section.get("type"),
                "title": section.get("title"),
                **fragment_data
            })

            # Audit info for simple section
            val = fragment_data["validation"]
            q = fragment_data["quality"]
            risk = (val.get("risk_level") or "unknown").lower()

            if isinstance(q.get("quality_score"), (int, float)):
                fragment_scores.append(q["quality_score"])

            if fragment_data.get("auto_regenerated"):
                auto_regen_count += 1

            frag_id = {
                "section_id": section.get("id"),
                "section_title": section.get("title"),
                "ordinal": None,
                "heading": None
            }

            if risk == "high":
                high_risk_fragments.append(frag_id)
            elif risk == "medium":
                medium_risk_fragments.append(frag_id)

            fragment_audit_entries.append({
                **frag_id,
                "risk_level": risk,
                "spirit_respected": val.get("spirit_respected", False),
                "quality_score": q.get("quality_score"),
                "quality_label": q.get("quality_label"),
                "attempts": fragment_data.get("attempts", 0),
                "auto_regenerated": fragment_data.get("auto_regenerated", False)
            })

    # Global quality of the document
    if fragment_scores:
        global_quality = sum(fragment_scores) / len(fragment_scores)
    else:
        global_quality = 0.0

    from datetime import datetime as _dt  # just in case

    result["audit_log"] = {
        "summary": {
            "total_sections": total_sections,
            "total_subsections": total_subsections,
            "auto_regenerations": auto_regen_count,
            "high_risk_fragments": len(high_risk_fragments),
            "medium_risk_fragments": len(medium_risk_fragments),
            "global_quality_score": round(global_quality, 2),
            "timestamp": _dt.utcnow().isoformat() + "Z",
            # <<< CHANGE: use the model that was actually used
            "model_used": CURRENT_MODEL_NAME
        },
        "high_risk_fragments": high_risk_fragments,
        "medium_risk_fragments": medium_risk_fragments,
        "fragments": fragment_audit_entries
    }

    return result


def sanitize_md_body(text: str) -> str:
    """
    Cleans the LLM text so it does not introduce weird Markdown formatting in the README.
    - Escapes asterisks and underscores so they do not become bold/italic.
    - Keeps the content as is, only without formatting.
    """
    if not text:
        return ""
    # Prevent **something** or *something* from becoming bold/italic in the README
    text = text.replace("*", r"\*")
    text = text.replace("_", r"\_")
    return text


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

    # Quick summary info from audit log
    audit = result.get("audit_log", {}).get("summary", {})
    if audit:
        lines.append(f"- **Quality global:** {audit.get('global_quality_score', 0)} / 100")
        lines.append(f"- **Auto-regeneraciones:** {audit.get('auto_regenerations', 0)}")
        lines.append(f"- **Fragmentos high risk:** {audit.get('high_risk_fragments', 0)}")
        lines.append(f"- **Modelo usado:** {audit.get('model_used', '')}")
    lines.append("\n")

    for section in result["sections"]:
        # Section title as is (SENTENCIA Nº, ANTECEDENTES..., FUNDAMENTOS..., FALLO...)
        lines.append(f"## {section['title']}\n")

        if "subsections" in section:
            # For ANTECEDENTES and FUNDAMENTOS we do NOT add anything else
            # (no extra "Hechos", "RAZONAMIENTOS LEGALES", etc.)
            for sub in section["subsections"]:
                header = ""

                # Use ONLY the ordinal as title (PRIMERO., SEGUNDO., TERCERO., etc.)
                if sub.get("ordinal"):
                    header = f"{sub['ordinal']}."

                # If there is no ordinal but there is a heading, we could use it as title
                # but to avoid weird cases we leave it blank.
                # If you want to use it:
                # elif sub.get("heading"):
                #     header = sub["heading"]

                if header:
                    lines.append(f"### {header}\n")

                body = sanitize_md_body(sub.get("simplified_text", ""))
                lines.append(body + "\n")

        else:
            # Sections without subsections (intro, fallo, warnings, etc.)
            body = sanitize_md_body(section.get("simplified_text", ""))
            lines.append(body + "\n")

    return "\n".join(lines)


def escape_md_inline(text: str) -> str:
    """
    Converts Markdown **bold** and *italic* into <b>/<i>,
    but avoids making entire paragraphs bold when they start
    with legal ordinal headings like 'TERCERO.'.
    """

    if not text:
        return ""

    # 1) Detect legal ordinals at the beginning ("TERCERO.", "PRIMERO.", etc.)
    ordinal_match = re.match(
        r'^(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|SEPTIMO|OCTAVO|NOVENO|DÉCIMO|DECIMO)\.\s+(.*)$',
        text,
        flags=re.IGNORECASE
    )

    if ordinal_match:
        ordinal = ordinal_match.group(1)
        rest = ordinal_match.group(2)

        # Apply bold ONLY to the ordinal and not to the rest
        text = f"<b>{ordinal}.</b> {rest}"

        # Escape to avoid problems with < > & except for the tags above
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
        return text

    # 2) If it is not a legal ordinal, apply normal transformation

    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic *text*
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)

    # Escape dangerous characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Restore valid tags
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")

    return text


def build_pdf_from_markdown(base_name: str, readme_text: str) -> None:
    """
    Generates a PDF from the Markdown README using ReportLab.
    Respects titles, basic bold text and lists with a simple layout.
    Does not require wkhtmltopdf or external binaries.
    """
    folder = Path(OUTPUT_DIR) / base_name
    folder.mkdir(parents=True, exist_ok=True)

    pdf_path = folder / f"clarified_{base_name}.pdf"

    # Base styles
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1f3b6f"),
        spaceAfter=12,
    )

    style_h1 = ParagraphStyle(
        "Heading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1f3b6f"),
        spaceBefore=12,
        spaceAfter=6,
    )

    style_h2 = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1f3b6f"),
        leftIndent=6,
        spaceBefore=10,
        spaceAfter=4,
    )

    style_h3 = ParagraphStyle(
        "Heading3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1f3b6f"),
        leftIndent=12,
        spaceBefore=8,
        spaceAfter=4,
    )

    style_body = ParagraphStyle(
        "BodyText",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    style_bullet = ParagraphStyle(
        "Bullet",
        parent=style_body,
        leftIndent=18,
        bulletIndent=9,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=60,
        bottomMargin=60,
    )

    elements = []

    lines = readme_text.splitlines()
    bullet_buffer: list[str] = []

    def flush_bullets():
        nonlocal bullet_buffer
        if not bullet_buffer:
            return
        items = []
        for item in bullet_buffer:
            txt = escape_md_inline(item.strip())
            items.append(ListItem(Paragraph(txt, style_bullet)))
        elements.append(ListFlowable(items, bulletType="bullet", start="•"))
        elements.append(Spacer(1, 4))
        bullet_buffer = []

    for idx, raw_line in enumerate(lines):
        line = raw_line.rstrip("\n")

        # Blank line
        if not line.strip():
            flush_bullets()
            elements.append(Spacer(1, 6))
            continue

        # Lists "- " or "* "
        if line.lstrip().startswith("- ") or line.lstrip().startswith("* "):
            content = line.lstrip()[2:]
            bullet_buffer.append(content)
            continue
        else:
            flush_bullets()

        # Markdown headings
        if line.startswith("# "):
            text = escape_md_inline(line[2:].strip())
            if idx == 0:
                elements.append(Paragraph(text, style_title))
            else:
                elements.append(Paragraph(text, style_h1))
        elif line.startswith("## "):
            text = escape_md_inline(line[3:].strip())
            elements.append(Paragraph(text, style_h1))
        elif line.startswith("### "):
            text = escape_md_inline(line[4:].strip())
            elements.append(Paragraph(text, style_h2))
        elif line.startswith("#### "):
            text = escape_md_inline(line[5:].strip())
            elements.append(Paragraph(text, style_h3))
        else:
            # Normal paragraph
            text = escape_md_inline(line.strip())
            elements.append(Paragraph(text, style_body))

    # If there are remaining bullets at the end, flush them
    flush_bullets()

    doc.build(elements)
    print(f"📄 PDF generated from README (ReportLab): {pdf_path}")


def save_outputs(base_name: str, json_data: dict, readme_text: str):
    folder = Path(OUTPUT_DIR) / base_name
    folder.mkdir(parents=True, exist_ok=True)

    # Save JSON
    with open(folder / "resultado.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Save README (markdown)
    readme_path = folder / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_text)

    # Generate PDF from README using ReportLab
    build_pdf_from_markdown(base_name, readme_text)

    print(f"\n💾 Files saved in: {folder.absolute()}")