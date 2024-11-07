import streamlit as st
import random
import time
from typing import Sequence

import fitz
import os
import uuid
from collections import defaultdict

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.llms import ChatMessage, MessageRole

from agent import messages_to_history_str, CustomRetriverQueryEngine

import base64
import logging
import sys

LOGGING = False

if LOGGING:
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))


st.set_page_config(layout="wide")


@st.cache_resource
def get_query_engine():
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    Settings.llm = Ollama(model="llama3.2:1b", request_timeout=360.0)

    # rebuild storage context
    PERSIST_DIR = "./storage"
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)

    # load index
    index = load_index_from_storage(storage_context)

    # query_engine = index.as_query_engine(streaming=True, similarity_top_k=5)
    query_engine = index.as_retriever( similarity_top_k=10)

    # kwargs = dict(streaming=True, similarity_top_k=5)
    # query_engine = CustomRetriverQueryEngine.from_args(retriever=index.as_retriever(**kwargs),
    #                                                 llm=Settings.llm,
    #                                                 **kwargs)
    
    return query_engine

query_engine = get_query_engine()

print(query_engine)
# print(query_engine.retriever)
# print(query_engine._response_synthesizer)

# exit()

import fitz  # PyMuPDF
import base64

def pdf_page_text_to_base64(pdf_path, page_number):
    # Open the PDF file
    pdf_document = fitz.open(pdf_path)
    
    # Ensure the page number is within range
    if page_number < 0 or page_number >= pdf_document.page_count:
        raise ValueError("Page number out of range")
    
    # Extract text from the specified page
    page = pdf_document[page_number]
    # text = page.get_text("text")  # Extract text content as plain text
    
    # Encode the text as base64
    text_base64 = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    
    return text_base64

os.makedirs("tmp/", exist_ok=True)

def read_and_concat_pdf(retrieved_pdf_data):
    # Create a new PDF for output
    new_document = fitz.open()

    for input_pdf_path, pages_to_extract in retrieved_pdf_data.items():
        pages_to_extract = sorted(pages_to_extract)

        # increase continuity of pages_to_extract
        # new_pages_to_extract = set()
        # margin = 1
        # for i, page_num in enumerate(pages_to_extract): 
        #     for offset in range(-margin, margin+1):
        #         if page_num + offset < 0:
        #             continue
        #         new_pages_to_extract.add(page_num + offset)        
            
        # Open the input PDF
        document = fitz.open(input_pdf_path)
        
        # Loop through the specified pages and extract them
        for page_num in pages_to_extract:
            if page_num < len(document):
                # Extract the page and append it to the new document
                new_document.insert_pdf(document, from_page=page_num, to_page=page_num)
            else:
                print(f"Page {page_num} does not exist in the document.")

        document.close()

    return new_document
    

# Streamed response emulator
def response_generator(prompt):
    hist = messages_to_history_str(st.session_state.messages)
    full_prompt = hist + "\nuser: " + prompt
    # response = query_engine.query(full_prompt)
    print("Prompt:", prompt)
    retrieved_nodes = query_engine.retrieve(prompt)

    # print(response.source_nodes)

    retrieved_pdf_data = defaultdict(set)
    for node in retrieved_nodes:
        print(node)
        print(node.metadata)
        # print("Text:", node.text)
        pdf_file_path = node.metadata['file_path'] 
        page_num = int(node.metadata['page_index'])
        retrieved_pdf_data[pdf_file_path].add(page_num)

    # Save the new PDF to the specified path
    new_document = read_and_concat_pdf(retrieved_pdf_data)

    new_document.save(f"tmp/{st.session_state['session_id']}_tmp_result.pdf")

    new_document.close()

    with col3:
        st.subheader("Retrieved content")
        pdf_file_path = f"tmp/{st.session_state['session_id']}_tmp_result.pdf" 
        # pdf_viewer(pdf_file_path)
        with open(pdf_file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="120%" height="1000" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)

    # for word in response.response_gen:
    #     yield word
    #     time.sleep(0.05)


# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

if 'session_id' not in st.session_state:
    # Generate a unique session ID
    st.session_state.session_id = str(uuid.uuid4())

# Create two columns: left for chat, right for PDF viewer
col2, col3 = st.columns([5, 5], gap='medium', )

# Sidebar (left side)
st.sidebar.title("Sidebar")
st.sidebar.write("You can put settings or information here.")

with col2:
    # st.title("Simple Chat with PDF Query Viewer")

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message.role):
            st.markdown(message.content)

    # Accept user input
    if prompt := st.chat_input("What is up?"):
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            # response = st.write_stream(response_generator(prompt))
            response_generator(prompt)
        
        # Add user message to chat history
        st.session_state.messages.append(
            ChatMessage(
                    role=MessageRole.USER,
                    content=prompt,
                )
        )
        # Add assistant response to chat history
        # st.session_state.messages.append(
        #     ChatMessage(
        #             role=MessageRole.ASSISTANT,
        #             content=response,
        #         )
        # )

def change_chatbot_style():
    # Set style of chat input so that it shows up at the bottom of the column
    chat_input_style = f"""
    <style>
        .stChatInput {{
          position: fixed;
          bottom: 3rem;
        }}
    </style>
    """
    st.markdown(chat_input_style, unsafe_allow_html=True)

change_chatbot_style()


# with col3:
#     st.subheader("Retrieved content")
#     pdf_file_path = "data/ProbML2024_Macke_05_Regression_I.pdf"  # Replace with your PDF path
#     # pdf_viewer(pdf_file_path)
#     with open(pdf_file_path, "rb") as f:
#         base64_pdf = base64.b64encode(f.read()).decode("utf-8")
#     pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="120%" height="1000" type="application/pdf"></iframe>'
#     st.markdown(pdf_display, unsafe_allow_html=True)