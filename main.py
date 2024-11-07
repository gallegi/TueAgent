import shutil
import os
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi import UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.responses import FileResponse

from fastapi.middleware.cors import CORSMiddleware

from llama_index.core import Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.llms import ChatMessage, MessageRole

from agent import messages_to_history_str, CustomRetriverQueryEngine

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

Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")

# indexing if needed
if os.path.exists(os.path.join(PERSIST_DIR,  'index_store.json')):
    print("Loading index from storage...")
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    # load index
    search_index = load_index_from_storage(storage_context)
else:
    # Create
    print("Indexing documents...")
    documents = SimpleDirectoryReader(UPLOAD_DIRECTORY, recursive=True).load_data(show_progress=True, num_workers=1)
    search_index = VectorStoreIndex.from_documents(documents)
    # store it for later
    search_index.storage_context.persist(persist_dir=PERSIST_DIR)

# Load the query engine to retrieve relevant documents
query_engine = search_index.as_retriever( similarity_top_k=10)


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
        for doc in new_documents:
            # Add new document(s) to the index
            search_index.insert(doc)
   
    return JSONResponse(content={"message": "Files uploaded successfully"}, status_code=200)
    

class ChatMessage(BaseModel):
    message: str

@app.post("/chat_reply")
async def chat_reply(chat_message: ChatMessage):
    user_message = chat_message.message
    print(f"User message: {user_message}")  # Print user message to the backend
    # Here you can add your logic to generate a response based on the user_message
    
    # print("Prompt:", prompt)
    # prompt = user_message
    # retrieved_nodes = query_engine.retrieve(prompt)

    # # print(response.source_nodes)

    # retrieved_pdf_data = defaultdict(set)
    # for node in retrieved_nodes:
    #     print(node)
    #     print(node.metadata)
    #     # print("Text:", node.text)
    #     pdf_file_path = node.metadata['file_path'] 
    #     page_num = int(node.metadata['page_index'])
    #     retrieved_pdf_data[pdf_file_path].add(page_num)

    # # Save the new PDF to the specified path
    # new_document = read_and_concat_pdf(retrieved_pdf_data)

    # new_document.save(f"tmp/{st.session_state['session_id']}_tmp_result.pdf")


    bot_response = f"User said: {user_message}"  # Example response
    return {"message": bot_response}

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

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    with open("index.html", "r") as file:
        return HTMLResponse(content=file.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000) 