# src/tools/tavily.py

from pydantic import BaseModel, Field
from typing import Literal
from loguru import logger

from tavily import AsyncTavilyClient
from src.configs.settings import TAVILY_API_KEY
from src.tools.registry import registry

def _get_tavily_client() -> AsyncTavilyClient | None:
    if not TAVILY_API_KEY:
        return None
    return AsyncTavilyClient(api_key=TAVILY_API_KEY)


class TavilySearchSchema(BaseModel):
    """Input for the web_search tool."""

    query: str = Field(..., description="The search query")
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description="'advanced' for deeper, more relevant results on complex queries. Costs more.",
    )
    topic: Literal["general", "news"] = Field(
        default="general",
        description="Use 'news' for recent events or time-sensitive queries.",
    )
    max_results: int = Field(default=5, ge=1, le=20)
    include_answer: bool = Field(
        default=True,
        description="Include Tavily's synthesized answer",
    )


@registry.register("web_search", TavilySearchSchema)
async def web_search(payload: TavilySearchSchema) -> dict:
    """Search the web for current information about a topic.

    Use this when a customer asks about something that requires up-to-date
    information you don't have, such as current market prices, news, or
    specific factual queries.
    """
    client = _get_tavily_client()
    if not client:
        return {"error": "Web search is currently unavailable (API key not configured)."}

    params = payload.model_dump(exclude_none=True)
    # Strip empty lists / None values so Tavily doesn't choke
    params = {k: v for k, v in params.items() if v not in (None, [])}

    try:
        response = await client.search(**params)
    except Exception:
        logger.exception("Tavily search failed for query: {}", payload.query)
        return {"error": "Web search failed. Try again later."}

    return response