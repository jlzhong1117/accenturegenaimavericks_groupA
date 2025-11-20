import os
import tempfile
from dotenv import load_dotenv

import streamlit as st
from src.pipeline import run_simplification_pipeline_for_streamlit

# 1) Configuration and Environment Setup
st.set_page_config(page_title="Legal Simplification System", layout="wide")

# Load environment variables from .env
load_dotenv()

# Check if the key exists in the env vars
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    st.error("🔑 GOOGLE_API_KEY not found in the environment (.env).")
    st.info("Add GOOGLE_API_KEY=your_key in the .env file at the project root.")
else:
    st.success("🔑 GOOGLE_API_KEY loaded from .env.")

# --- 2. Main Interface ---
st.title("⚖️ Legal Document Simplifier (Spanish Judicial Decisions)")

uploaded_file = st.file_uploader(
    "Upload a Spanish SJPI PDF Judgment",
    type="pdf",
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.info(f"File uploaded: **{uploaded_file.name}**. Click Simplify to begin.")

    if st.button("✨ Simplify Document"):
        # Guardar el PDF subido en un archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            pdf_path = tmp_file.name

        try:
            with st.spinner("⏳ Analyzing and simplifying the complex legal document..."):
                result = run_simplification_pipeline_for_streamlit(pdf_path)

            st.success("✅ Document Simplified Successfully!")
            st.markdown("---")

            tab1, tab2, tab3 = st.tabs([
                "Simplified Markdown Output",
                "Download PDF",
                "Download JSON",
            ])

            with tab1:
                st.subheader("Human-Readable Simplified Judgment")
                st.markdown(result["markdown"])

            with tab2:
                st.subheader("Download Simplified PDF")
                st.download_button(
                    label="⬇️ Download PDF",
                    data=result["pdf_bytes"],
                    file_name=f"clarified_{result['base_name']}.pdf",
                    mime="application/pdf",
                )

            with tab3:
                st.subheader("Download JSON (Structured Data)")
                st.download_button(
                    label="⬇️ Download JSON",
                    data=result["json_bytes"],
                    file_name=f"{result['base_name']}_resultado.json",
                    mime="application/json",
                )

        except Exception as e:
            st.error(f"An error occurred during simplification: {e}")

        finally:
            # Clean up the temporary file
            os.unlink(pdf_path)
