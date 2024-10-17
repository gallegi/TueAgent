import streamlit as st
import random
import time

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core import PromptTemplate
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.chat_engine import CondenseQuestionChatEngine 
from llama_index.core import StorageContext, load_index_from_storage

import logging
import sys

LOGGING = False

if LOGGING:
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

custom_prompt = PromptTemplate(
    """
<Chat History>
{chat_history}

<Current Question>
{question}

Summarize into a single command or question:
<Stand-alone Question>
"""
)

@st.cache_resource
def get_query_engine():
    # Create a database session object that points to the URL.
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    Settings.llm = Ollama(model="llama3.2:1b", request_timeout=360.0)

    # rebuild storage context
    PERSIST_DIR = "./storage"
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)

    # load index
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine(streaming=True, similarity_top_k=5)

    chat_engine = CondenseQuestionChatEngine.from_defaults(
            query_engine=query_engine,
            condense_question_prompt=custom_prompt,
            # chat_history=st.session_state.messages,
            verbose=True,
        )
    
    return chat_engine

chat_engine = get_query_engine()


# Streamed response emulator
def response_generator(prompt):
    # response = query_engine.query(prompt)
    response = chat_engine.stream_chat(prompt, 
                                       chat_history=st.session_state.messages)

    for word in response.response_gen:
        yield word
        time.sleep(0.05)


st.title("Simple chat")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

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
        response = st.write_stream(response_generator(prompt))
    
    # Add user message to chat history
    st.session_state.messages.append(
        ChatMessage(
                role=MessageRole.USER,
                content=prompt,
            )
    )
    # Add assistant response to chat history
    st.session_state.messages.append(
        ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response,
            )
    )