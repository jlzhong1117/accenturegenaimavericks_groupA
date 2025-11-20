import streamlit as st
import os
from simplify_judgment import run_simplification_pipeline

#1. PREPARING THE STREAMLIT UI

#1a.SET UP & API KEY
if "GEMINI_API_KEY" not in os.environ:
  os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

st.title("CLAWRIFAI")

#1b. FILE UPLOADER
uploaded_file = st.file_uploader("Upload a Spanish SJPI PDF", type="pdf")

if uploaded_file is not None:
    # Save the uploaded file temporarily
    with open("uploaded_judgment.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    if st.button("Simplify Document"):
        with st.spinner("Processing and simplifying the judgment..."):
            # Call the core function
            simplified_output = run_simplification_pipeline("uploaded_judgment.pdf") 

            # Display the results
            st.subheader("✅ Simplified Judgment")
            st.markdown(simplified_output['markdown']) # Assuming your function returns a dictionary

            st.subheader("📝 Structured JSON Output")
            st.json(simplified_output['json'])

#2. HANDLE RAG & CHROMADB ACCESS
# Example snippet for loading in simplify_judgment.py
from chromadb import PersistentClient

# Use the path where the database directories are stored
client = PersistentClient(path="./chroma_judgments_dir") 
judgments_db = client.get_collection("judgments_collection")
# ... then initialize the LangChain vector store wrappers
