from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance
from src.configs.settings import QDRANT_URL, QDRANT_API_KEY

client=AsyncQdrantClient(
  url=QDRANT_URL,
  api_key=QDRANT_API_KEY
  )
  
async def check_if_collection_exists(collection_name) -> bool:
  collections= (await client.get_collections()).collections
  
  return any(collection.name == collection_name for collection in collections)

async def make_collection(collection_name):
  if not await check_if_collection_exists(collection_name):
    await client.create_collection(
      collection_name=collection_name,
      vectors_config=VectorParams(
      size=1024,
      distance=Distance.COSINE,))
  
  return True
 
