
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from openai import OpenAI
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
import os

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"
OPENAI_MINI_MODEL = "gpt-4o-mini"
PERPLEXITY_MODEL = "sonar"

load_dotenv(os.getenv("DOTENV_PATH", ".env"))
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')


anthropic = ChatAnthropic(
    model=ANTHROPIC_MODEL,
    max_tokens_to_sample=6000,
    temperature=0.8, 
    api_key = ANTHROPIC_API_KEY)

gpt4o = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY)

gpt4o_mini = ChatOpenAI(
    model=OPENAI_MINI_MODEL,
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY)

perple = OpenAI(api_key = PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")

anthropic_async = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)