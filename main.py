import shutil
import os
import time
from typing import List

from llama_index.core import SimpleDirectoryReader
from pydantic import BaseModel
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.responses import FileResponse

from llama_index.core.llms import ChatMessage, MessageRole

from fastapi.middleware.cors import CORSMiddleware

from agent import RAGAgent, ChatHistories

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

agent = RAGAgent(PERSIST_DIR, UPLOAD_DIRECTORY, TMP_DIR)

chat_histories = ChatHistories()

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), category: str = Form(...)):
    print("File category:", category)
    folder_location = f"{UPLOAD_DIRECTORY}/{category}"
    if not os.path.exists(folder_location):
        os.makedirs(folder_location)
    
    for file in files:
        print("Uploading: ", file.filename)
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
    user_id = chat_message.user_id
    chat_history = chat_histories.get_history(user_id)
    print(f"User message: {user_message}")
    generator = await agent.run(query_str=user_message, user_id=user_id, chat_history=chat_history)
    return StreamingResponse(generator, media_type="text/plain")

@app.post("/update_chat_history")
async def update_chat_history(chat_message: ChatMessage):
    user_id = chat_message.user_id
    message = chat_message.message
    chat_histories.add_message(user_id, message, MessageRole.ASSISTANT)
    print("Chat history:", chat_histories.get_history(user_id))
    return {"message": "Chat history updated successfully"}

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