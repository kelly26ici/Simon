from openai import OpenAI
from ..src.configs.settings import OPENAI_API_KEY
client = OpenAI(
    api_key="OPENAI_API_KEY",
    base_url="https://api.groq.com/openai/v1",
)

for model in client.models.list().data:
    print(model.id)