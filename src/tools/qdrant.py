from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import (
    UnexpectedResponse,
    ResponseHandlingException,
)
from qdrant_client.models import VectorParams, Distance

from src.configs.settings import QDRANT_URL, QDRANT_API_KEY
from loguru import logger

client = AsyncQdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)


class QdrantCollectionCheckError(Exception):
    pass


class QdrantCollectionCreateError(Exception):
    pass


async def check_if_collection_exists(collection_name: str) -> bool:
    try:
        collections = (await client.get_collections()).collections
        return any(collection.name == collection_name for collection in collections)
    except UnexpectedResponse as exc:
        status = getattr(exc, "status_code", None)
        body = (getattr(exc, "content", b"") or b"").decode("utf-8", "ignore").strip()
        logger.error(
            "Qdrant unexpected response checking collections: status={} body={}",
            status,
            body or "(empty)",
        )
        raise QdrantCollectionCheckError(
            f"Qdrant collection check failed with status {status}"
        ) from exc
    except ResponseHandlingException as exc:
        logger.error("Qdrant response error while checking collections: {}", exc)
        raise QdrantCollectionCheckError("Qdrant response error during collection check") from exc
    except Exception as exc:
        logger.exception("Unexpected error while checking Qdrant collections")
        raise QdrantCollectionCheckError("Unexpected error checking Qdrant collections") from exc


async def make_collection(collection_name: str) -> bool:
    try:
        if not await check_if_collection_exists(collection_name):
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                ),
            )
        return True
    except QdrantCollectionCheckError:
        raise
    except UnexpectedResponse as exc:
        status = getattr(exc, "status_code", None)
        body = (getattr(exc, "content", b"") or b"").decode("utf-8", "ignore").strip()
        logger.error(
            "Qdrant unexpected response creating collection: status={} body={}",
            status,
            body or "(empty)",
        )
        raise QdrantCollectionCreateError(
            f"Qdrant collection create failed with status {status}"
        ) from exc
    except ResponseHandlingException as exc:
        logger.error("Qdrant response error while creating collection: {}", exc)
        raise QdrantCollectionCreateError("Qdrant response error during collection create") from exc
    except Exception as exc:
        logger.exception("Unexpected error while creating Qdrant collection")
        raise QdrantCollectionCreateError("Unexpected error creating Qdrant collection") from exc
