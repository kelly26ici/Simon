import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import (
    UnexpectedResponse,
    ResponseHandlingException,
)
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

from src.configs.settings import QDRANT_URL, QDRANT_API_KEY
from loguru import logger

PROPERTIES_COLLECTION = "properties"

_qdrant_clients_by_loop: dict[asyncio.AbstractEventLoop | None, AsyncQdrantClient] = {}


def get_qdrant_client() -> AsyncQdrantClient:
    """Return an AsyncQdrantClient scoped to the current running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    client = _qdrant_clients_by_loop.get(loop)
    if client is None:
        client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        )
        _qdrant_clients_by_loop[loop] = client
    return client


class _QdrantClientProxy:
    """Proxy object ensuring calls delegate to the current event loop's client."""
    def __getattr__(self, name: str):
        actual = get_qdrant_client()
        return getattr(actual, name)


client = _QdrantClientProxy()


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
    """Ensure the Qdrant collection exists and has appropriate vector and payload schema."""
    try:
        exists = await check_if_collection_exists(collection_name)
        if not exists:
            logger.info("Creating Qdrant collection '{}'...", collection_name)
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                ),
            )

        # Create payload indices for fast filtered vector searches (idempotent in Qdrant)
        for field, p_type in [
            ("price", PayloadSchemaType.FLOAT),
            ("bedrooms", PayloadSchemaType.INTEGER),
            ("city", PayloadSchemaType.KEYWORD),
            ("location", PayloadSchemaType.KEYWORD),
            ("property_type", PayloadSchemaType.KEYWORD),
            ("property_subtype", PayloadSchemaType.KEYWORD),
            ("price_period", PayloadSchemaType.KEYWORD),
            ("listing_type", PayloadSchemaType.KEYWORD),
            ("town", PayloadSchemaType.KEYWORD),
            ("country", PayloadSchemaType.KEYWORD),
            ("agent_id", PayloadSchemaType.KEYWORD),
            ("status", PayloadSchemaType.KEYWORD),
        ]:
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=p_type,
                )
            except Exception as idx_err:
                logger.debug("Payload index creation for {} notice: {}", field, idx_err)

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

