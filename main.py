import logging
from fastapi import FastAPI
import inngest
#from inngest.fastapi import serve
import inngest.fast_api
#from inngest.experimental import ai 
from dotenv import load_dotenv
import uuid
import os
import datetime
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc, RAGQueryResult, RAGSearchResult, RAGUpsertResult


import json

load_dotenv()

inngest_client = inngest.Inngest(
  app_id="RAGaiAgent",
  logger = logging.getLogger("uvicorn"),
  is_production=False,
  #serializer=inngest.PydanticSerializer()
)

#decorator
@inngest_client.create_function( 
  fn_id="RAG: Ingest PDF",
  trigger=inngest.TriggerEvent(event="rag/ingest_pdf")
)
async def rag_ingest_pdf(ctx: inngest.Context, **kwargs):
  def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
    pdf_path = ctx.event.data["pdf_path"]
    source_id = ctx.event.data.get("source_id", pdf_path)
    chunks = load_and_chunk_pdf(pdf_path)

    # Make sure everything is a string
    chunks = [str(c) for c in chunks]

    # Test serialization
    try:
      json.dumps(chunks)  # Try dumping as JSON
      print("✅ Chunks are JSON-serializable")
    except Exception as e:
      print("❌ Serialization failed:", e)
    #print(type(chunks), chunks[:2])


    return RAGChunkAndSrc(chunks=chunks, source_id=source_id).model_dump()
    #chunks_and_src = RAGChunkAndSrc(chunks=chunks, source_id=source_id)
    #print("Debug _load output", chunks_and_src)
    #return chunks_and_src.model_dump()

  def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
    chunks_and_src = RAGChunkAndSrc(**chunks_and_src)
    chunks = chunks_and_src.chunks
    source_id = chunks_and_src.source_id
    vecs = embed_texts(chunks)
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}: {i}")) for i in range(len(chunks))]
    payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
    QdrantStorage().upsert(ids, vecs, payloads)

    return RAGUpsertResult(ingested=len(chunks)).model_dump()
    #result = RAGUpsertResult(ingested=len(chunks))
    #print("Debug _upsert output:", result)
    #return result.model_dump()

  chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc)
  ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)

  ingested = RAGUpsertResult(**ingested)
  return ingested.model_dump()
  

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf])
