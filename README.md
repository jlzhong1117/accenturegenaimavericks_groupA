# README — Sistema de Simplificación y Validación de Sentencias en Lenguaje Claro

## 📌 Resumen del proyecto

Este proyecto implementa un sistema completo para **transformar sentencias judiciales en PDF** en una versión redactada en **lenguaje claro**, garantizando siempre que **no se altere el sentido jurídico** del texto original.

El resultado final incluye:

* Una sentencia **reescrita en lenguaje claro**.
* Una **validación automática** del espíritu de la norma.
* Un **informe de auditoría** con riesgos, calidad y trazabilidad.
* Generación de **JSON estructurado**, **README.md** y **PDF final** útil para revisión judicial.

El objetivo es acercar el contenido jurídico a ciudadanos y profesionales sin formación legal, **sin comprometer la fidelidad jurídica**.

---

# 🧩 Arquitectura conceptual del proyecto

El proyecto combina tres elementos principales:

1. **Un parser** que transforma el PDF en una estructura lógica.
2. **Un sistema RAG** que proporciona contexto jurídico real.
3. **Un sistema multi-agente de IA** encargado de reescritura, validación y autocorrección.

---

# 🔍 1. Parseo jurídico de la sentencia

Antes de procesar cualquier fragmento, la sentencia en PDF se transforma en una estructura organizada:

* **Metadatos**: órgano, fecha, procedimiento...
* **Secciones jurídicas**:

  * Encabezado
  * Antecedentes de Hecho
  * Fundamentos de Derecho
  * Fallo
* **Subsecciones** con ordinales (PRIMERO, SEGUNDO, TERCERO…)
* **Fragmentos (chunks)** de texto

Esta estructura permite:

* Procesar cada parte por separado
* Evitar mezclar razonamientos
* Combinar precisión jurídica con claridad textual

---

# 🧠 2. RAG — Retrieval Augmented Generation

### ❓ ¿Por qué es necesario?

Un modelo de lenguaje por sí solo no siempre replica criterios jurídicos oficiales ni conoce patrones reales de redacción judicial.

Para asegurar coherencia, calidad y precisión, usamos un **RAG** como memoria jurídica externa.

---

## 📚 Fuentes que utiliza el RAG

### **1) Guía de Lenguaje Claro del Poder Judicial**

Almacenada en `chroma_guide/`.

Incluye:

* Reglas de claridad
* Estilo judicial recomendado
* Correcciones frecuentes (mayusculismo, frases largas…)
* Ejemplos de buena redacción

### **2) Sentencias reales**

Almacenadas en `chroma_judgments/`.

Aporta:

* Estructuras reales
* Forma jurídica correcta
* Ejemplos prácticos de simplificación

---

## 🔎 ¿Cómo funciona el RAG?

Para cada fragmento de la sentencia:

1. Se genera una **consulta** basada en el texto original.
2. Los vector stores devuelven **los fragmentos más relevantes** de:

   * la guía de lenguaje claro
   * otras sentencias judiciales
3. Ese material se inserta como **contexto directo** en la llamada al LLM.
4. El LLM reescribe el texto siguiendo **criterios reales y documentados**, reduciendo errores y alucinaciones.

> El RAG no es opcional: es el componente que garantiza que la IA no inventa, no se desvía y redacta como lo haría un profesional del derecho en lenguaje claro.

---

# 🤖 3. Sistema de Agentes LLM

El proyecto no usa un único modelo “mágico”, sino un **sistema multi-agente**, donde cada agente tiene un rol bien definido.

Esto imita un flujo de trabajo judicial real: un redactor y un auditor.

---

## 🟦 Agente 1 — Simplificador en Lenguaje Claro

*(El Escritor Judicial)*

Este agente se encarga de:

* Reescribir el texto jurídico en versiones **claras, ordenadas y comprensibles**.
* Mantener la **precisión jurídica**.
* Identificar malas prácticas del texto original.
* Explicar los cambios (change_log).

Produce un JSON estructurado:

```json
{
  "simplified_text": "...",
  "incorrect_things": "...",
  "change_log": ["..."]
}
```

---

## 🟥 Agente 2 — Validador del Espíritu de la Norma

*(El Auditor Jurídico)*

Este agente compara:

* Texto original vs texto simplificado

Y determina:

* Si el sentido jurídico se mantiene intacto.
* Si se han cambiado datos relevantes.
* Si hay riesgo de interpretación incorrecta.

Produce:

```json
{
  "spirit_respected": true/false,
  "risk_level": "low/medium/high",
  "issues": ["..."]
}
```

Es crítico, estricto y no reescribe, solo evalúa.

---

# 🔁 4. Autoregeneración — Un sistema autocorrectivo

El pipeline incorpora un mecanismo de **auto-mejora**:

1. El LLM reescribe.
2. El auditor detecta fallos.
3. Se generan instrucciones adicionales explicando qué corregir.
4. El LLM reescribe otra versión.
5. Se vuelve a validar.

Hasta un máximo de **3 iteraciones**.

Si aun así persisten errores:

* El fragmento se marca como **HIGH RISK**.
* Se requiere revisión humana.

Este mecanismo hace al sistema:

* más robusto
* más seguro
* más fiable
* y más alineado con procesos jurídicos reales

---

# 📊 5. Auditoría y Quality Score

Cada fragmento obtiene una puntuación automática basada en:

* Respeto del espíritu de la norma
* Riesgo detectado
* Divergencias señaladas
* Nº de autocorrecciones necesarias
* Limpieza y coherencia del texto final

La media global produce un **quality score de la sentencia**.

Además, se generan logs para rastrear:

* Qué fragmentos han sido problemáticos
* Cuántos intentos se han necesitado
* Qué modelo LLM ha intervenido (principal o fallback)

Todo queda registrado en `resultado.json`.

---

# 📄 6. Resultados finales

Tras procesar una sentencia PDF, se genera:

```
outputs/<ID_SENTENCIA>/
  ├── resultado.json           → auditoría completa del pipeline
  ├── README.md                → sentencia simplificada en lenguaje claro
  └── clarified_<ID>.pdf       → versión PDF lista para entregar
```

La versión PDF se maqueta automáticamente a partir del README simplificado.

---

# 🎯 Conclusión

Este proyecto combina:

### ✔ Procesamiento jurídico estructurado

### ✔ RAG con fuentes reales

### ✔ Agentes especializados que cooperan

### ✔ Validación automática de riesgo

### ✔ Autocorrección inteligente

### ✔ Auditoría completa y trazabilidad

El resultado es un sistema sólido, fiable y explicable que transforma textos jurídicos complejos en versiones claras **sin perder precisión legal**, algo esencial en proyectos reales de IA aplicada a justicia.
