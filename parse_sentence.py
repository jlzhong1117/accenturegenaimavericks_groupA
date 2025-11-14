import re
import json
from typing import List, Dict, Any


ORDINAL_REGEX = re.compile(
    r'^(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|SEPTIMO|OCTAVO|NOVENO|DÉCIMO|DECIMO)\-\.?(.*)$',
    re.IGNORECASE
)

def clean_line(line: str) -> str:
    return line.strip().replace("\xa0", " ")


def parse_metadata(lines: List[str]) -> Dict[str, Any]:
    meta = {}
    for line in lines:
        line = clean_line(line)
        if line.startswith("Roj:"):
            meta["roj"] = line.replace("Roj:", "").strip()
        elif line.startswith("ECLI:"):
            meta["ecli"] = line.replace("ECLI:", "").strip()
        elif line.startswith("Id Cendoj:"):
            meta["id_cendoj"] = line.replace("Id Cendoj:", "").strip()
        elif line.startswith("Órgano:") or line.startswith("Organo:"):
            meta["organo"] = line.split(":", 1)[1].strip()
        elif line.startswith("Sede:"):
            meta["sede"] = line.split(":", 1)[1].strip()
        elif line.startswith("Sección:") or line.startswith("Seccion:"):
            meta["seccion"] = line.split(":", 1)[1].strip()
        elif line.startswith("Fecha:"):
            meta["fecha"] = line.split(":", 1)[1].strip()
        elif line.startswith("Nº de Recurso:") or line.startswith("Nº de recurso:"):
            meta["num_recurso"] = line.split(":", 1)[1].strip()
        elif line.startswith("Nº de Resolución:") or line.startswith("Nº de resolución:"):
            meta["num_resolucion"] = line.split(":", 1)[1].strip()
        elif line.startswith("Procedimiento:"):
            # puede aparecer dos veces, nos quedamos con la primera si no existe
            if "procedimiento" not in meta:
                meta["procedimiento"] = line.split(":", 1)[1].strip()
        elif line.startswith("Materia:"):
            meta["materia"] = line.split(":", 1)[1].strip()
        elif line.startswith("Ponente:"):
            meta["ponente"] = line.split(":", 1)[1].strip()
        elif line.startswith("Demandante:"):
            meta["demandante"] = line.replace("Demandante:", "").strip()
        elif line.startswith("Demandado:"):
            meta["demandado"] = line.replace("Demandado:", "").strip()
        elif "Tipo de Resolución:" in line:
            meta["tipo_resolucion"] = line.split(":", 1)[1].strip()
    return meta


def split_into_sections(lines: List[str]) -> Dict[str, List[str]]:
    """
    Devuelve un dict con listas de líneas por sección lógica:
    intro, antecedentes, fundamentos, fallo, recursos, proteccion_datos.
    """
    sections = {
        "intro": [],
        "antecedentes": [],
        "fundamentos": [],
        "fallo": [],
        "recursos": [],
        "proteccion_datos": []
    }

    current = None
    saw_sentencia = False

    for raw_line in lines:
        line = clean_line(raw_line)
        if not line:
            continue

        # cambio de sección principal
        if re.fullmatch(r"ANTECEDENTES DE HECHO", line, re.IGNORECASE):
            current = "antecedentes"
            continue
        elif re.fullmatch(r"FUNDAMENTOS DE DERECHO", line, re.IGNORECASE):
            current = "fundamentos"
            continue
        elif re.fullmatch(r"FALLO", line, re.IGNORECASE):
            current = "fallo"
            continue

        # detección de sub-secciones dentro del final
        if line.startswith("Contra la presente resolución"):
            current = "recursos"
        elif line.startswith("La difusión del texto de esta resolución") or \
             line.startswith("Los datos personales incluidos en esta resolución"):
            current = "proteccion_datos"

        # Intro: desde la primera línea "SENTENCIA" hasta "ANTECEDENTES..."
        if not saw_sentencia and line.startswith("SENTENCIA"):
            saw_sentencia = True
            current = "intro"

        # si aún no hemos visto SENTENCIA, estamos en cabecera (metadata), no se añade a sections
        if not saw_sentencia:
            continue

        # añadimos la línea a la sección actual
        if current is not None and current in sections:
            sections[current].append(line)

    return sections


def split_subsections_from_section_lines(section_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Para secciones como ANTECEDENTES o FUNDAMENTOS:
    detecta ordinales (PRIMERO, SEGUNDO...) y agrupa texto.
    """
    subsections: List[Dict[str, Any]] = []
    current_sub = None
    buffer_lines: List[str] = []

    def flush_current():
        nonlocal current_sub, buffer_lines
        if current_sub is not None:
            text = " ".join(buffer_lines).strip()
            current_sub["raw_text"] = text
            current_sub["chunks"] = chunk_long_text(text)
            subsections.append(current_sub)
        current_sub = None
        buffer_lines = []

    for line in section_lines:
        m = ORDINAL_REGEX.match(line)
        if m:
            # nuevo ordinal: volcamos el anterior si existe
            flush_current()
            ordinal = m.group(1).upper()
            heading_tail = m.group(2).strip()
            heading = heading_tail.strip(" .-") if heading_tail else None
            current_sub = {
                "ordinal": ordinal,
                "heading": heading,
                "raw_text": "",
                "chunks": []
            }
        else:
            # seguimos acumulando texto en el subapartado actual
            if current_sub is None:
                # texto antes del primer ordinal: lo ignoramos o lo acumulamos en un "sin_ordinal"
                current_sub = {
                    "ordinal": None,
                    "heading": None,
                    "raw_text": "",
                    "chunks": []
                }
            buffer_lines.append(line)

    # flush final
    flush_current()
    return subsections


def chunk_long_text(text: str, max_chars: int = 1200) -> List[Dict[str, Any]]:
    """
    Divide el texto de un fundamento en chunks más pequeños:
    - primero por párrafos (doble salto)
    - si alguno sigue siendo muy largo, por puntos.
    Devuelve lista de dicts con chunk_id (que luego puedes completar) y text.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[Dict[str, Any]] = []

    for p in paragraphs:
        if len(p) <= max_chars:
            chunks.append({"text": p})
        else:
            # dividir por frases aproximadas
            sentences = re.split(r"(?<=[\.\?\!])\s+", p)
            current = ""
            for s in sentences:
                # garantiza espacio entre frases
                candidate = (current + " " + s).strip()
                if len(candidate) > max_chars and current:
                    chunks.append({"text": current})
                    current = s
                else:
                    current = candidate
            if current:
                chunks.append({"text": current})

    # asignamos ids secuenciales dentro del fundamento
    for i, ch in enumerate(chunks, start=1):
        ch["chunk_id"] = f"chunk_{i}"

    return chunks


def join_lines(lines: List[str]) -> str:
    return " ".join(lines).strip()


def parse_sentence_text(text: str, doc_id: str = None, source: str = None) -> Dict[str, Any]:
    """
    Función principal:
    - recibe el texto completo de la sentencia (string)
    - devuelve un dict estructurado (lista de secciones, subsecciones, chunks, etc.)
    """
    lines = [clean_line(l) for l in text.splitlines()]

    # cabecera: hasta la primera línea "SENTENCIA"
    header_lines = []
    body_start_index = 0
    for i, line in enumerate(lines):
        if line.startswith("SENTENCIA"):
            body_start_index = i
            break
        header_lines.append(line)

    metadata = parse_metadata(header_lines)
    if doc_id:
        metadata["doc_id"] = doc_id
    if source:
        metadata["source"] = source

    body_lines = lines[body_start_index:]
    sections_lines = split_into_sections(body_lines)

    # Intro
    sections: List[Dict[str, Any]] = []
    if sections_lines["intro"]:
        sections.append({
            "id": "intro",
            "type": "intro",
            "title": sections_lines["intro"][0] if sections_lines["intro"] else "INTRODUCCIÓN",
            "text": join_lines(sections_lines["intro"]),
            "metadata": {"role": "intro_procesal"}
        })

    # Antecedentes
    if sections_lines["antecedentes"]:
        antecedentes_subs = split_subsections_from_section_lines(sections_lines["antecedentes"])
        sections.append({
            "id": "antecedentes",
            "type": "facts",
            "title": "ANTECEDENTES DE HECHO",
            "subsections": antecedentes_subs
        })

    # Fundamentos
    if sections_lines["fundamentos"]:
        fundamentos_subs = split_subsections_from_section_lines(sections_lines["fundamentos"])
        sections.append({
            "id": "fundamentos",
            "type": "legal_reasoning",
            "title": "FUNDAMENTOS DE DERECHO",
            "subsections": fundamentos_subs
        })

    # Fallo
    if sections_lines["fallo"]:
        sections.append({
            "id": "fallo",
            "type": "decision",
            "title": "FALLO",
            "text": join_lines(sections_lines["fallo"]),
            "metadata": {}
        })

    # Recursos
    if sections_lines["recursos"]:
        sections.append({
            "id": "recursos",
            "type": "recursos",
            "title": "RÉGIMEN DE RECURSOS",
            "text": join_lines(sections_lines["recursos"]),
            "metadata": {}
        })

    # Protección de datos
    if sections_lines["proteccion_datos"]:
        sections.append({
            "id": "proteccion_datos",
            "type": "disposiciones_finales",
            "title": "ADVERTENCIAS SOBRE DIFUSIÓN Y DATOS PERSONALES",
            "text": join_lines(sections_lines["proteccion_datos"]),
            "metadata": {}
        })

    result = {
        "metadata": metadata,
        "sections": sections
    }
    return result


# Ejemplo de uso independiente:
if __name__ == "__main__":
    # Aquí pondrías el texto que ya has extraído del PDF (p.ej. con pypdf)
    # from pypdf import PdfReader
    #
    # reader = PdfReader("SJPI_281_2025.pdf")
    # full_text = ""
    # for page in reader.pages:
    #     full_text += page.extract_text() + "\n"
    #
    # parsed = parse_sentence_text(full_text, doc_id="SJPI_281/2025", source="SJPI_281_2025.pdf")
    # print(json.dumps(parsed, ensure_ascii=False, indent=2))

    # Para probar rápido, pega aquí un fragmento de texto:
    sample_text = """Roj: SJPI 281/2025 - ECLI:ES:JPI:2025:281
Órgano:Juzgado de Primera Instancia
Sede:Madrid
Fecha:07/02/2025
SENTENCIA Nº 432/2025
En Madrid, a 7 de febrero de 2025...
ANTECEDENTES DE HECHO
PRIMERO-. Por turno de reparto correspondió...
SEGUNDO-. Admitida a trámite la demanda...
FUNDAMENTOS DE DERECHO
PRIMERO-. Pretensiones de las partes.
Por la parte actora se ejercita acción...
FALLO
Se estima la demanda...
Contra la presente resolución cabe interponer recurso de APELACIÓN...
La difusión del texto de esta resolución a partes no interesadas..."""

    parsed = parse_sentence_text(sample_text, doc_id="SJPI_281/2025", source="SJPI_281_2025.txt")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
