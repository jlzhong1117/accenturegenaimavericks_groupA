# README — System for Simplifying and Validating Court Judgments into Plain Language

## 📌 Project Summary

This project implements a complete system that transforms court judgments in PDF format into a version written in clear, plain language, while guaranteeing that the legal meaning of the original text is fully preserved.

The pipeline produces:

* A plain-language rewritten judgment
* An automated validation of the legal meaning (spirit of the norm)
* A complete audit report (risk, quality score, regeneration attempts)
* Three final deliverables:

```
resultado.json     → structured data + audit log
README.md          → plain-language version of the judgment
clarified_<name>.pdf → typeset PDF version of the README
```

The goal is to make court rulings understandable for citizens and non-experts without losing legal accuracy.

# 🧩 High-Level Architecture

The project combines three major components:

0) A legal parser to convert the PDF into a structured representation
1) A RAG system to provide real legal context
2) A multi-agent LLM pipeline that rewrites, validates, and self-corrects the text

# 🔍 1. Legal Parsing of the Judgment

Before any AI processing, the PDF is converted into a structured format that reflects the internal logic of a court ruling:

* Metadata : court, date, proceeding type, ROJ number…
* Legal sections :

  * Header
  * Facts (Antecedentes de Hecho)
  * Legal Grounds (Fundamentos de Derecho)
  * Decision (Fallo)
* Subsections with legal ordinals (FIRST, SECOND, THIRD…)
* Text fragments (chunks)

This structure enables:

* Fragment-by-fragment processing
* Clear separation of legal reasoning
* Precise alignment between original and rewritten text

# 🧠 2. RAG — Retrieval Augmented Generation

### ❓ Why is RAG essential?

A standalone LLM cannot reliably replicate:

* judicial writing standards
* clarity guidelines
* typical structure of court reasoning
* terminology and style from the Spanish judiciary

RAG solves this by providing the model with authoritative external context.

## 📚 Knowledge Sources Used by the RAG

### 1) Official Judicial Plain Language Guide

Stored in `chroma_guide/`.

Provides:

* clarity and simplification principles
* typical judicial style
* common corrections (capitalization, long sentences, jargon)
* examples of best practices

### 2) Real court judgments

Stored in `chroma_judgments/`.

Provides:

* examples of correctly written judgments
* real legal structures and tone
* additional guidance for consistency

## 🔎 How the RAG Works in the Pipeline

For each fragment of the judgment:

0. A query is generated based on the original text
1. Two vectorstores retrieve relevant fragments:

  * plain-language guide excerpts
  * excerpts from real judgments
2. These are merged into a context block
3. The LLM uses this block to rewrite the fragment

  * reduces hallucinations
  * improves legal accuracy
  * ensures stylistic consistency

RAG ensures that the model does not improvise, but writes in alignment with real judicial standards.

# 🤖 3. Multi-Agent LLM System

The pipeline does not rely on a single model. Instead, it uses a two-agent system, each with a specialized role.

This mimics a real judicial workflow: a writer and an auditor.

## 🟦 Agent 1 — Plain-Language Rewriter

(The Judicial Writer)

Responsible for:

- Rewriting the text in clear, structured, accessible language
- Maintaining legal precision
- Identifying writing issues in the original text
- Providing a detailed change log

Produces:

```
{
  "simplified_text": "...",
  "incorrect_things": "...",
  "change_log": ["..."]
}
```

This is the creative agent, but guided by RAG and strict instructions.

## 🟥 Agent 2 — Validator of the Spirit of the Norm

(The Legal Auditor)

This agent compares:

+ original vs simplified text

And detects:

+ changes in meaning
+ altered parties, dates, amounts, deadlines
+ additions or omissions of legal effects
+ tone deviations that may affect interpretation

Produces:

```
{
  "spirit_respected": true/false,
  "risk_level": "low/medium/high",
  "issues": ["..."]
}
```

It is strict and conservative, and does not rewrite. Its role is pure legal safeguarding.

# 🔁 4. Self-Regeneration Mechanism (Automatic Corrections)

The system includes an intelligent self-correction loop:

0. The writer agent rewrites
1. The auditor flags risks
2. The system generates regeneration hints

  * detailed issues
  * corrections needed
  * warnings detected
3. The writer produces a new version
4. The auditor reevaluates

Up to 3 automatic attempts.

If still unsafe:

- fragment is marked HIGH RISK
- human review is required

This makes the pipeline:

- robust
- explainable
- legally cautious
- self-correcting

# 📊 5. Quality Score and Audit System

Each fragment receives a 0–100 quality score, based on:

* respect of the legal meaning
* risk level
* issues reported
* need for regenerations

A global score is also computed for the entire judgment.

The `resultado.json` file includes:

* complete trace of decisions
* fragments marked medium/high risk
* attempt counts
* model used (main or fallback)

This ensures transparency and auditability.

# 📄 6. Final Output Delivered

After running the pipeline, the system generates:

```
outputs/<JUDGMENT_ID>/
  ├── resultado.json           → full audit + structured processing results
  ├── README.md                → plain-language rewritten judgment
  └── clarified_<ID>.pdf       → typeset PDF generated from README
```

The PDF is clean, structured, and ready for publication or human review.

# 📁 7. Repository File and Directory Structure

To facilitate navigation and understanding, the repository is organized as follows:

- **Root Directory**:
  - `README.md`: This documentation file.
  - `simplify_judgment.py`: Script for running the simplification pipeline via command line.
  - `streamlit_app.py`: Script for launching the Streamlit user interface.
  - `.env`: Configuration file for API keys (e.g., GOOGLE_API_KEY; not committed to version control).

- **chroma_guide/**: Directory containing vectorized data from the official judicial plain language guide.
- **chroma_judgments/**: Directory containing vectorized real court judgments for RAG reference.
- **outputs/**: Directory for generated outputs, with subdirectories per judgment ID containing `resultado.json`, `README.md`, and `clarified_<ID>.pdf`.

Note: The `.venv/` directory is generated locally during setup and is not part of the repository.

# 📜 8. Change Log

This section tracks significant updates to the repository:

- **Initial Commit (Date Unknown)**: Project initialization with core scripts, RAG directories, and README documentation.
- **Subsequent Updates**: No detailed commit history available at this time. Future changes will be logged here, including additions to dependencies, enhancements to agents, or expansions in knowledge sources.

For the latest changes, refer to the commit history on GitHub.

# 🎯 Conclusion

This project combines:

### ✔ Legal document structuring

### ✔ RAG with authoritative external sources

### ✔ A multi-agent LLM pipeline

### ✔ Legal-meaning validation and risk detection

### ✔ Automatic self-correction

### ✔ Full auditability and transparency

The result is a reliable system capable of transforming complex court judgments into clear, accessible language without compromising legal accuracy, which is essential for real-world deployment in justice systems.

# 🧪 Running Locally with UV

## 1. Install uv

```
pip install uv
```

## 2. Create the environment

```
uv venv
```

## 3. Activate it

```
source .venv/bin/activate  # On Unix-based systems
# or
.venv\Scripts\activate  # On Windows
```

## 4. Install dependencies

```
uv sync
```

## 5. Run the simplification pipeline manually

```
uv run python simplify_judgment.py file.pdf
```

Replace `file.pdf` with your judgment.

# 🌐 Running the System from Streamlit (Recommended UI)

We provide a simple interface to upload a PDF and obtain:

* Simplified Markdown
* Downloadable clarified PDF
* Downloadable JSON

## 1. Make sure `.env` contains your API key

```
GOOGLE_API_KEY=your_key_here
```

## 2. Launch the Streamlit app

Run this command in the project root:

```
streamlit run streamlit_app.py
```

## 3. Use the interface

+ Upload a PDF judgment
+ Click “Simplify Document”
+ Download the autogenerated PDF and JSON