import streamlit as st
import os

# Import the core engine functions from your generated files
from main import process_document  # Replace with the actual function name inside your main.py
import models
import translator

st.set_page_config(page_title="Layout Preserving Translator", layout="centered")
st.title("📚 Layout-Preserving Roman Urdu Translator")
st.caption("Advanced Computer Vision Engine (OCR + Inpainting + Text Injection)")

# UI Inputs
api_key = st.text_input("Gemini API Key (Optional)", type="password")
uploaded_file = st.file_uploader("Upload your scanned English PDF", type=["pdf"])

if st.button("🚀 Start Precision Translation", type="primary"):
    if not uploaded_file:
        st.error("Please upload a PDF file.")
    else:
        # 1. Save uploaded file temporarily so your backend can read it
        temp_input = "temp_input.pdf"
        temp_output = "layout_preserved_output.pdf"
        
        with open(temp_input, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        try:
            # 2. Run your multi-file backend engine
            st.info("⚡ Initializing pipeline modules (OCR -> Inpaint -> Render)...")
            
            # Adjust this line to match how your main.py executes
            process_document(input_path=temp_input, output_path=temp_output, api_key=api_key)
            
            # 3. Provide the final PDF download button
            if os.path.exists(temp_output):
                with open(temp_output, "rb") as file_bytes:
                    st.download_button(
                        label="📥 Download Translated PDF",
                        data=file_bytes,
                        file_name="Roman_Urdu_Layout_Preserved.pdf",
                        mime="application/pdf"
                    )
                st.success("🎉 Done! Layout preserved perfectly.")
            else:
                st.error("Pipeline finished but no output file was generated.")
                
        except Exception as e:
            st.error(f"Pipeline Error: {e}")
            
        finally:
            # Cleanup files on the server
            if os.path.exists(temp_input): os.remove(temp_input)
            if os.path.exists(temp_output): os.remove(temp_output)
