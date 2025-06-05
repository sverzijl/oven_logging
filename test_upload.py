"""Test script to debug file upload issue"""

import streamlit as st
import pandas as pd
import io
from src.data.loader import ThermalProfileLoader

st.title("File Upload Debug Test")

uploaded_file = st.file_uploader("Upload CSV", type=['csv'])

if uploaded_file is not None:
    st.write(f"File name: {uploaded_file.name}")
    st.write(f"File type: {type(uploaded_file)}")
    
    try:
        # First, let's examine the file structure
        st.subheader("File Structure Analysis")
        
        # Read file content
        content = uploaded_file.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        uploaded_file.seek(0)  # Reset
        
        # Show first 15 lines
        lines = content.split('\n')[:15]
        st.write("First 15 lines of the file:")
        for i, line in enumerate(lines):
            st.text(f"Line {i}: {line[:100]}...")  # Show first 100 chars
        
        # Method 1: Read without skipping rows
        st.subheader("Method 1: Read all rows")
        df_all = pd.read_csv(uploaded_file)
        st.write(f"Shape: {df_all.shape}")
        st.write(f"Columns: {list(df_all.columns)}")
        st.write("First few rows:")
        st.dataframe(df_all.head())
        uploaded_file.seek(0)  # Reset
        
        # Method 2: Read with skiprows
        st.subheader("Method 2: Read with skiprows=10")
        df_skip = pd.read_csv(uploaded_file, skiprows=10)
        st.write(f"Shape: {df_skip.shape}")
        st.write(f"Columns: {list(df_skip.columns)}")
        st.write("First few rows:")
        st.dataframe(df_skip.head())
        uploaded_file.seek(0)  # Reset
        
        # Method 3: Using our loader (with error handling)
        st.subheader("Method 3: Using ThermalProfileLoader")
        try:
            loader = ThermalProfileLoader()
            data, metadata = loader.load_csv(file_buffer=uploaded_file)
            st.write(f"✅ Success! Shape: {data.shape}")
            st.write(f"Metadata: {list(metadata.keys())}")
        except Exception as e:
            st.error(f"Loader error: {type(e).__name__}: {str(e)}")
            
            # Try to identify the issue
            uploaded_file.seek(0)
            test_df = pd.read_csv(uploaded_file, skiprows=10)
            st.write("Available columns after skiprows=10:")
            st.write(list(test_df.columns))
            
            # Check if any column contains 'time' (case insensitive)
            time_cols = [col for col in test_df.columns if 'time' in col.lower()]
            st.write(f"Columns containing 'time': {time_cols}")
        
    except Exception as e:
        st.error(f"Error: {type(e).__name__}: {str(e)}")
        import traceback
        st.code(traceback.format_exc())