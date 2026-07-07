import streamlit as st
import os

# Import the core logic directly, bypassing the command-line reader
from main import run_pipeline 

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
        temp_input = "temp_input.pdf"
        temp_output = "layout_preserved_output.pdf"
        
        # Save the uploaded file into a temporary layout space
        with open(temp_input, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        try:
            st.info("⚡ Pipeline Active. Running Engine (OCR -> Inpaint -> Render)...")
            
            # Choose backend based on the API key presence
            backend_choice = "openai" if api_key else "echo"
            
            # Execute the core engineering pipeline directly using your variables!
            run_pipeline(
                input_pdf=temp_input,
                output_pdf=temp_output,
                dpi=150,                     # 150 DPI saves precious RAM on Streamlit Cloud
                backend=backend_choice,
                api_key=api_key if api_key else None,
                model=None,
                erase_mode="fill",           # 'fill' is lightning fast and robust for web apps
                min_confidence=40,
                align="left"
            )
            
            # Verify and construct the dynamic download button
            if os.path.exists(temp_output):
                with open(temp_output, "rb") as file_bytes:
                    st.download_button(
                        label="📥 Download Translated PDF",
                        data=file_bytes,
                        file_name="Roman_Urdu_Layout_Preserved.pdf",
                        mime="application/pdf"
                    )
                st.success("🎉 Process Complete! Click above to download.")
            else:
                st.error("Engine completed but no output canvas was saved.")
                
        except Exception as e:
            st.error(f"Pipeline Execution Fault: {e}")
            
        finally:
            # Clean up residual file streams from the server
            if os.path.exists(temp_input): os.remove(temp_input)
            if os.path.exists(temp_output): os.remove(temp_output)


