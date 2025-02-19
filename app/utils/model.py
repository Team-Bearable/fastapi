
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')


anthropic = ChatAnthropic(
    model="claude-3-5-sonnet-20240620",
    max_tokens_to_sample=6000,
    temperature=0.8, 
    api_key = ANTHROPIC_API_KEY)

gpt4o = ChatOpenAI(
    model="gpt-4o",
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY)

gpt4o_mini = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY)

perple = OpenAI(api_key = PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
perplexity_model = "llama-3.1-sonar-small-128k-online"