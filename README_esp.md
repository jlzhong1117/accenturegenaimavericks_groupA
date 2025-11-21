# README — Sistema para Simplificar y Validar Sentencias Judiciales en Lenguaje Claro

## 📌 Resumen del Proyecto

Este proyecto implementa un sistema completo que transforma sentencias judiciales en formato PDF a una versión redactada en lenguaje claro y accesible, garantizando que el significado jurídico del texto original se preserve al 100 %.

El pipeline genera automáticamente:

- Una sentencia reescrita en lenguaje llano  
- Una validación automática del espíritu de la norma  
- Un informe completo de auditoría (riesgo, puntuación de calidad, intentos de regeneración)  
- Tres entregables finales:

```
resultado.json               → datos estructurados + registro de auditoría
README.md                    → versión en lenguaje claro de la sentencia
clarified_<nombre>.pdf       → PDF maquetado y listo para publicar
```

El objetivo es que las resoluciones judiciales sean comprensibles para la ciudadanía y personas no expertas sin perder rigor jurídico.

# 🧩 Arquitectura de Alto Nivel

El proyecto combina tres grandes componentes:

1. Un parser jurídico que convierte el PDF en una representación estructurada  
2. Un sistema RAG que aporta contexto jurídico real  
3. Un pipeline multi-agente con LLM que reescribe, valida y se autocorrige

# 🔍 1. Parseo Jurídico de la Sentencia

Antes de cualquier procesamiento de IA, el PDF se convierte en un formato estructurado que refleja la lógica interna de una resolución judicial:

- Metadatos: tribunal, fecha, tipo de procedimiento, número ROJ…  
- Secciones legales:  
  - Encabezamiento  
  - Antecedentes de Hecho  
  - Fundamentos de Derecho  
  - Fallo  
- Subsecciones con ordinales jurídicos (PRIMERO, SEGUNDO, TERCERO…)  
- Fragmentos de texto (chunks)

Esta estructura permite el procesamiento fragmento por fragmento y una alineación precisa entre original y versión simplificada.

# 🧠 2. RAG — Generación Aumentada por Recuperación

### ❓ ¿Por qué es esencial el RAG?

Un LLM aislado no puede reproducir de forma fiable:
- estándares de redacción judicial
- criterios de claridad
- estructura típica del razonamiento judicial
- terminología y estilo del poder judicial español

El RAG lo soluciona aportando contexto externo autorizado.

## 📚 Fuentes de Conocimiento del RAG

### 1) Guía Oficial de Lenguaje Claro Judicial
Almacenada en `chroma_guide/`

Aporta:
- principios de claridad y simplificación
- estilo judicial correcto
- correcciones habituales (mayúsculas, frases largas, jerga)
- ejemplos de buenas prácticas

### 2) Sentencias judiciales reales
Almacenadas en `chroma_judgments/`

Aportan:
- ejemplos de sentencias bien redactadas
- estructuras y tono reales
- guía adicional de coherencia

## 🔎 Funcionamiento del RAG en el Pipeline

Para cada fragmento de la sentencia:
1. Se genera una consulta a partir del texto original  
2. Dos bases vectoriales recuperan fragmentos relevantes:  
   - extractos de la guía de lenguaje claro  
   - extractos de sentencias reales  
3. Se combinan en un bloque de contexto  
4. El LLM reescribe el fragmento utilizando ese contexto

→ Reduce alucinaciones  
→ Mejora la precisión jurídica  
→ Garantiza coherencia estilística

# 🤖 3. Sistema Multi-Agente con LLM

El pipeline no usa un único modelo, sino dos agentes especializados que simulan el flujo real de un juzgado: un redactor y un auditor.

## 🟦 Agente 1 — Redactor en Lenguaje Claro (El Redactor Judicial)

Responsable de:
- Reescribir en lenguaje claro, estructurado y accesible
- Mantener la precisión jurídica
- Identificar problemas de redacción del original
- Generar un registro detallado de cambios

Salida:
```json
{
  "simplified_text": "...",
  "incorrect_things": "...",
  "change_log": ["..."]
}
```

## 🟥 Agente 2 — Validador del Espíritu de la Norma (El Auditor Jurídico)

Compara original ↔ simplificado y detecta:
- cambios de significado
- alteración de partes, fechas, cuantías, plazos
- adiciones u omisiones de efectos jurídicos
- desviaciones de tono que afecten la interpretación

Salida:
```json
{
  "spirit_respected": true/false,
  "risk_level": "low/medium/high",
  "issues": ["..."]
}
```

Es estrictamente conservador y solo valida, nunca reescribe.

# 🔁 4. Mecanismo de Autorregeneración (Correcciones Automáticas)

El sistema incluye un bucle inteligente de autocorrección:
1. El redactor genera una versión  
2. El auditor detecta riesgos  
3. Se generan pistas de regeneración detalladas  
4. El redactor produce una nueva versión  
5. El auditor reevalúa

Hasta 3 intentos automáticos.

Si sigue sin ser seguro → el fragmento se marca ALTO RIESGO y requiere revisión humana.

# 📊 5. Puntuación de Calidad y Sistema de Auditoría

Cada fragmento recibe una puntuación de 0–100 según:
- respeto del significado jurídico
- nivel de riesgo
- problemas detectados
- número de regeneraciones necesarias

Se calcula también una puntuación global de la sentencia.

El archivo `resultado.json` contiene trazabilidad completa:
- decisiones tomadas
- fragmentos de riesgo medio/alto
- número de intentos
- modelo utilizado (principal o fallback)

# 📄 6. Entregables Finales

Tras ejecutar el pipeline se genera:

```
outputs/<ID_SENTENCIA>/
  ├── resultado.json           → auditoría completa + resultados estructurados
  ├── README.md                → sentencia reescrita en lenguaje claro
  └── clarified_<ID>.pdf       → PDF maquetado generado a partir del README
```

# 📁 7. Estructura del Repositorio

- **Raíz**:
  - `README.md` – esta documentación
  - `simplify_judgment.py` – ejecución por línea de comandos
  - `streamlit_app.py` – interfaz gráfica con Streamlit
  - `.env` – claves API (no versionado)

- `chroma_guide/` – base vectorial de la guía oficial de lenguaje claro
- `chroma_judgments/` – base vectorial de sentencias reales
- `outputs/` – carpeta con resultados (una subcarpeta por sentencia procesada)

# 🎯 Conclusión

Este proyecto combina:
- Estructuración avanzada de documentos jurídicos
- RAG con fuentes autorizadas reales
- Pipeline multi-agente con LLM
- Validación del espíritu de la norma y detección de riesgo
- Autocorrección automática
- Auditoría y trazabilidad completas

El resultado es un sistema fiable y auditable capaz de convertir sentencias judiciales complejas en textos claros y accesibles sin comprometer la precisión jurídica, listo para despliegues reales en la Administración de Justicia.

# 🧪 Ejecución Local con UV

1. Instalar uv: `pip install uv`
2. Crear entorno: `uv venv`
3. Activar:
   - Unix: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`
4. Instalar dependencias: `uv sync`
5. Ejecutar: `uv run python simplify_judgment.py archivo.pdf`

# 🌐 Ejecución con Interfaz Streamlit (Recomendado)

1. Añadir tu clave en `.env`:
   ```
   GOOGLE_API_KEY=tu_clave_aquí
   ```
2. Lanzar la interfaz:
   ```
   streamlit run streamlit_app.py
   ```
3. Subir PDF → “Simplificar Documento” → Descargar PDF y JSON generados

¡Listo! El sistema procesará automáticamente la sentencia y entregará los tres archivos finales.