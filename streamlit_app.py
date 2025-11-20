import streamlit as st
import os
import tempfile
# Assuming your core RAG function is in this file:
from simplify_judgment import run_simplification_pipeline 

# --- 1. Configuration and API Key Check ---
st.set_page_config(page_title="Legal Simplification System", layout="wide")

# Use Streamlit secrets for secure key management
if "GEMINI_API_KEY" not in st.secrets:
    st.error("🔑 Gemini API Key not found in Streamlit secrets.")
    st.info("Please add your key under [secrets] in the .streamlit/secrets.toml file.")
else:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# --- 2. Main Application Interface ---
st.title("⚖️ Legal Document Simplifier (Spanish Judicial Decisions)")

uploaded_file = st.file_uploader(
    "Upload a Spanish SJPI PDF Judgment",
    type="pdf",
    accept_multiple_files=False
)

if uploaded_file is not None and os.getenv("GEMINI_API_KEY"):
    st.info(f"File uploaded: **{uploaded_file.name}**. Click Simplify to begin.")

    if st.button("✨ Simplify Document"):
        # Create a temporary file to save the uploaded PDF
        # This is necessary because the RAG pipeline likely expects a file path, not a Streamlit object
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            pdf_path = tmp_file.name
        
        # --- Run the RAG Pipeline ---
        with st.spinner("⏳ Analyzing and simplifying the complex legal document..."):
            try:
                # Call the function from your core script
                simplified_output = run_simplification_pipeline(pdf_path)

                st.success("✅ Document Simplified Successfully!")
                st.markdown("---")
                
                # --- 3. Display Results ---
                
                tab1, tab2 = st.tabs(["Simplified Markdown Output", "Structured JSON Data"])
                
                with tab1:
                    st.subheader("Human-Readable Simplified Judgment")
                    # Assuming your function returns a dictionary with a 'markdown' key
                    st.markdown(simplified_output.get('markdown', 'No simplified text found.'))

                with tab2:
                    st.subheader("Structured Data Output")
                    # Assuming your function returns a dictionary with a 'json' key
                    st.json(simplified_output.get('json', {}))

            except Exception as e:
                st.error(f"An error occurred during simplification: {e}")
            
            finally:
                # Clean up the temporary file
                os.unlink(pdf_path)
