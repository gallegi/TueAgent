import streamlit as st
import random
import time
from typing import Sequence

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

def messages_to_history_str(messages: Sequence[ChatMessage]) -> str:
    """Convert messages to a history string."""
    string_messages = []
    for message in messages:
        role = message.role
        content = message.content
        string_message = f"{role.value}: {content}"

        additional_kwargs = message.additional_kwargs
        if additional_kwargs:
            string_message += f"\n{additional_kwargs}"
        string_messages.append(string_message)
    return "\n".join(string_messages)

@st.cache_resource
def get_query_engine():
    # Create a database session object that points to the URL.
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    Settings.llm = Ollama(model="llama3.2:3b", request_timeout=360.0)

    # rebuild storage context
    PERSIST_DIR = "./storage"
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)

    # load index
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine(streaming=True, similarity_top_k=5)
    
    return query_engine

query_engine = get_query_engine()

# Streamed response emulator
def response_generator(prompt):
    hist = messages_to_history_str(st.session_state.messages)
    full_prompt = hist + "\nuser: " + prompt
    response = query_engine.query(full_prompt)

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