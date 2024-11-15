import asyncio
import time
import os
from typing import List
from collections import defaultdict

from llama_index.readers.web import BeautifulSoupWebReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.schema import NodeRelationship, NodeWithScore, QueryBundle
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.core.workflow import Context
from llama_index.postprocessor.colbert_rerank import ColbertRerank
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core import Document

from llama_index.core.workflow import Event, StartEvent, StopEvent, Workflow, step

from utils import read_and_concat_pdf, convert_message_list_to_str

class CondenseQueryEvent(Event):
    condensed_query_str: str

class RetrievalEvent(Event):
    nodes: List[NodeWithScore]


class RAGAgent(Workflow):
    SUMMARY_TEMPLATE = (
        "Given the chat history:\n"
        "'''{chat_history_str}'''\n\n"
        "And the user asked the following question:{query_str}\n"
        "Rewrite to a standalone question:\n"
    )

    CONTEXT_PROMPT_TEMPLATE = (
        "Information that might help:\n"
        "-----\n"
        "{node_context}\n"
        "-----\n"
        "Please write a response to the following question, using the above information if relevant:\n"
        "{query_str}\n"
    ) 

    def __init__(self, index_persisted_dir, data_dir, tmp_dir, timeout: int = 60, verbose: bool = False):
        super().__init__(timeout=timeout, verbose=verbose)
        self.index_persisted_dir = index_persisted_dir
        self.data_dir = data_dir
        self.tmp_dir = tmp_dir
        self.k = 5

        self.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
        Settings.embed_model = self.embed_model
        self.search_index = self._load_or_create_index()
        self.retriever = self.search_index.as_retriever(similarity_top_k=self.k)
        self.reranker = ColbertRerank(top_n=5)
        self.node_processor = SimilarityPostprocessor(similarity_cutoff=0.6)
        self.llm = Ollama(model="llama3.2:1b", request_timeout=60.0)
        Settings.llm = self.llm
        

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
            search_index = VectorStoreIndex.from_documents(documents, embed_model=self.embed_model)
            # store it for later
            search_index.storage_context.persist(persist_dir=self.index_persisted_dir)

        return search_index

    @step
    async def condense_history_to_query(self, ctx: Context, ev: StartEvent) -> CondenseQueryEvent:
        query_str = ev.query_str
        chat_history = ev.chat_history
        user_id = ev.user_id
        await ctx.set("query_str", query_str)
        await ctx.set("chat_history", chat_history)
        await ctx.set("user_id", user_id)
        formated_query = ""
        if len(chat_history) > 0:
            chat_history_str = convert_message_list_to_str(chat_history)
            formated_query = self.SUMMARY_TEMPLATE.format(chat_history_str=chat_history_str, query_str=query_str)
            # print('Formated Query:', formated_query)
            history_summary = await self.llm.acomplete(formated_query)
            condensed_query = "Context:\n" + history_summary.text + "\nQuestion: " + query_str
        else:
            condensed_query = query_str
        # print("Condense query:", condensed_query)
        return CondenseQueryEvent(condensed_query_str=condensed_query)
    
    @step
    async def retrieve(self, ctx: Context, ev: CondenseQueryEvent) -> RetrievalEvent:
        # retrieve from context
        # query_str = await ctx.get("query_str")
        condensed_query_str = ev.condensed_query_str
        nodes = await self.retriever.aretrieve(condensed_query_str)
        # rerank the nodes
        nodes = self.reranker.postprocess_nodes(nodes=nodes, query_str=condensed_query_str)
        # for node in nodes:
        #     print(node)
        nodes = self.node_processor.postprocess_nodes(nodes)
        user_id = await ctx.get("user_id")
        print("user_id:", user_id)
        self.save_retrieved_pdf_data(nodes, user_id)
        return RetrievalEvent(nodes=nodes)
    
    def _prepare_query_with_context(
        self,
        query_str: str,
        nodes: List[NodeWithScore],
    ) -> str:
        node_context = ""

        if len(nodes) == 0:
            return query_str
        
        for idx, node in enumerate(nodes):
            node_text = node.get_content(metadata_mode="llm")
            node_context += f"\n{node_text}\n\n"

        formatted_query = self.CONTEXT_PROMPT_TEMPLATE.format(
            node_context=node_context, query_str=query_str
        )
        
        return formatted_query

    @step
    async def llm_response(self,  ctx: Context, retrieval_ev: RetrievalEvent) -> StopEvent:
        nodes = retrieval_ev.nodes
        query_str = await ctx.get("query_str")
        query_with_ctx = self._prepare_query_with_context(query_str, nodes)
        chat_history = await ctx.get("chat_history")
        response = await self.llm.astream_chat(chat_history + [ChatMessage(role=MessageRole.USER, content=query_with_ctx)])
        
        async def response_gen():
            async for chunk in response:
                yield chunk.delta
                
        chat_history.append(ChatMessage(role=MessageRole.USER, content=query_str))
        
        return StopEvent(result=response_gen())
    
    def save_retrieved_pdf_data(self, retrieved_nodes, user_id):
        if len(retrieved_nodes) == 0:
            print("No relevant documents found.")
            return
        retrieved_pdf_data = defaultdict(list)
        for node in retrieved_nodes:
            # print(node)
            pdf_file_path = node.metadata['file_path'] 
            page_num = int(node.metadata['page_index'])
            retrieved_pdf_data[pdf_file_path].append(page_num)

        # Save the new PDF to the specified path
        new_document = read_and_concat_pdf(retrieved_pdf_data)

        new_document.save(f"{self.tmp_dir}/{user_id}_tmp_result.pdf")

        new_document.close()

    def append_index(self, documents: List[Document]):
        page_num_tracker = defaultdict(int)
        for doc in documents:
            # Add new doc to the index
            key = doc.metadata['file_path']
            doc.metadata['page_index'] = page_num_tracker[key]
            self.search_index.insert(doc) # Add the new document to the index
            page_num_tracker[key] += 1  
    
        # Store the updated index ascynchronously
        self.search_index.storage_context.persist(persist_dir=self.index_persisted_dir)


class ChatHistories:
    def __init__(self):
        self.histories = {}
    
    def get_history(self, user_id):
        if user_id not in self.histories:
            self.histories[user_id] = []
        return self.histories[user_id]
    
    def add_message(self, user_id, message, role):
        self.histories[user_id].append(ChatMessage(role=role, content=message))
