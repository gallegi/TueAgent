import shutil
import os
import time
from typing import List
from collections import defaultdict

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse
from fastapi import UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from fastapi.responses import FileResponse

from fastapi.middleware.cors import CORSMiddleware

from llama_index.core import Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core import StorageContext, load_index_from_storage, get_response_synthesizer
from llama_index.core.llms import ChatMessage, MessageRole

from utils import read_and_concat_pdf

app = FastAPI()

# Allow CORS for all origins (you can restrict this later)
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# Directory to save uploaded files
UPLOAD_DIRECTORY = "data"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

PERSIST_DIR = "./search_index_storage"

TMP_DIR = "tmp" # Directory to save temporary files (retrieved PDFs)
os.makedirs(TMP_DIR, exist_ok=True)

SESSION_COOKIE_NAME = "session_id"

class RAGAgent:
    def __init__(self, index_persisted_dir, data_dir, tmp_dir) -> None:
        self.index_persisted_dir = index_persisted_dir
        self.data_dir = data_dir
        self.tmp_dir = tmp_dir

        Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
        Settings.llm = Ollama(model="llama3.1", request_timeout=360.0)

        self.search_index = self._load_or_create_index()

        # Load the query engine to retrieve relevant documents
        self.search_engine = self.search_index.as_retriever( similarity_top_k=10)

        self.response_synthesizer = get_response_synthesizer(response_mode="compact", streaming=True)

    def _load_or_create_index(self):
        # indexing if needed
        if os.path.exists(os.path.join(self.index_persisted_dir,  'index_store.json')):
            print("Loading index from storage...")
            storage_context = StorageContext.from_defaults(persist_dir=self.index_persisted_dir)
            # load index
            search_index = load_index_from_storage(storage_context)
        else:
            # Create
            print("Indexing documents...")
            documents = SimpleDirectoryReader(self.data_dir, recursive=True).load_data(show_progress=True, num_workers=1)
            # create a page index for each document (cannot rely on 'page_label' as it is not unique)
            page_num_tracker = defaultdict(int)
            for doc in documents:
                key = doc.metadata['file_path']
                doc.metadata['page_index'] = page_num_tracker[key]
                page_num_tracker[key] += 1  
            search_index = VectorStoreIndex.from_documents(documents)
            # store it for later
            search_index.storage_context.persist(persist_dir=self.index_persisted_dir)

        return search_index
    
    def retrieve(self, prompt):
        retrieved_nodes = self.search_engine.retrieve(prompt)
        return retrieved_nodes
    
    def generate_response(self, prompt, retrieved_nodes):
        response = self.response_synthesizer.synthesize(prompt, nodes=retrieved_nodes)
        return response
    
    def chat(self, user_message, session_id):
        # Retrieve relevant documents
        retrieved_nodes = self.retrieve(user_message)

        self.save_retrieved_pdf_data(retrieved_nodes, session_id)

        # Generate response
        response = self.generate_response(user_message, retrieved_nodes)

        for chunk in response.response_gen:
            yield chunk
            time.sleep(0.05)
    
    def save_retrieved_pdf_data(self, retrieved_nodes, session_id):
        retrieved_pdf_data = defaultdict(set)
        for node in retrieved_nodes:
            # print(node)
            # print(node.metadata)
            # print("Text:", node.text)
            pdf_file_path = node.metadata['file_path'] 
            page_num = int(node.metadata['page_index'])
            retrieved_pdf_data[pdf_file_path].add(page_num)

        # Save the new PDF to the specified path
        new_document = read_and_concat_pdf(retrieved_pdf_data)

        new_document.save(f"{self.tmp_dir}/{session_id}_tmp_result.pdf")

        new_document.close()

    def append_index(self, documents: List[Document]):
        page_num_tracker = defaultdict(int)
        for doc in documents:
            # Add new doc to the index
            key = doc.metadata['file_path']
            doc.metadata['page_index'] = page_num_tracker[key]
            self.search_index.insert(doc) # Add the new document to the index
            page_num_tracker[key] += 1  
        
        # Re-initialize the search engine
        self.search_engine = self.search_index.as_retriever( similarity_top_k=10)

        # Store the updated index ascynchronously
        self.search_index.storage_context.persist(persist_dir=self.index_persisted_dir)


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), category: str = Form(...)):
    print("File category:", category)
    folder_location = f"{UPLOAD_DIRECTORY}/{category}"
    if not os.path.exists(folder_location):
        os.makedirs(folder_location)
    
    for file in files:
        print(file.filename)
        file_location = f"{folder_location}/{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        new_documents = SimpleDirectoryReader(input_files=[file_location]).load_data(show_progress=True)
        
        agent.append_index(new_documents)

    return JSONResponse(content={"message": "Files uploaded successfully"}, status_code=200)

class ChatMessage(BaseModel):
    message: str
    user_id: str

@app.post("/chat_reply")
async def chat_reply(chat_message: ChatMessage):
    user_message = chat_message.message
    print(f"User message: {user_message}")  # Print user message to the backend
    # Here you can add your logic to generate a response based on the user_message

    return StreamingResponse(agent.chat(user_message, chat_message.user_id), media_type="text/plain")

@app.get("/categories")
async def get_categories():
    try:
        directory_structure = {}
        # Read the directories and files in UPLOAD_DIRECTORY
        for category in os.listdir(UPLOAD_DIRECTORY):
            category_path = os.path.join(UPLOAD_DIRECTORY, category)
            if os.path.isdir(category_path):
                # List files in the category directory
                files = os.listdir(category_path)
                directory_structure[category] = files
        return {"directory_structure": directory_structure}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/pdf/{folder}/{pdf_filename}")
async def get_pdf(folder: str, pdf_filename: str):
    file_path = os.path.join(UPLOAD_DIRECTORY, folder, pdf_filename)
    return FileResponse(file_path, media_type="application/pdf")

@app.get("/pdf_tmp/{pdf_filename}")
async def get_pdf(pdf_filename: str):
    file_path = os.path.join(TMP_DIR, pdf_filename)
    return FileResponse(file_path, media_type="application/pdf")

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    with open("index.html", "r") as file:
        return HTMLResponse(content=file.read())

if __name__ == "__main__":
    import uvicorn
    agent = RAGAgent(PERSIST_DIR, UPLOAD_DIRECTORY, TMP_DIR)
    uvicorn.run(app, host="localhost", port=8000) 