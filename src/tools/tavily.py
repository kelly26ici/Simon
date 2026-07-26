from tavily import AsyncTavilyClient
from pydantic import BaseModel, Field
from typing import Literal
from src.configs.settings import TAVILY_API_KEY
from src.tools.registry import registry


client=AsyncTavilyClient(api_key=TAVILY_API_KEY)

class TavilyInput(BaseModel):
  
  query: str
  search_depth: Literal["basic", "advanced"] = Field(
      default="basic",
      description="'advanced' for deeper, more relevant results on complex/current-events queries. Costs more."
    )
  topic: Literal["general", "news"] = Field(
      default="general",
      description="Use 'news' for recent events, breaking news, or time-sensitive queries."
    )
  max_results: int = Field(default=5, ge=1, le=20)
  include_answer: bool = Field(
      default=True,
      description="Include Tavily's synthesized answer")
  include_domains: list[str] = Field(
      default_factory=list,
      description="Restrict search to these domains")
     
  exclude_domains: list[str] = Field(
      default_factory=list)
      
  days: int | None = Field(
        default=None,
        description="For topic='news', limit results to the last N days")
  
  

async def tavily_search(input: TavilyInput) -> dict:
  
  params=input.model_dump(
      exclude_none=True,
      exclude_defaults=False
      )
  
  params={key: value for key, value in params.items() if value not in (None, [])}
  
  try:
    
    response=client.search(**params)
  
  except Exception as e:
    print(f"Failed to search: {e}")
  
  return response