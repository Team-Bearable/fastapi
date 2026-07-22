
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from openai import OpenAI
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
import os

from app.utils.logger import get_logger

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"
OPENAI_MINI_MODEL = "gpt-4o-mini"
PERPLEXITY_MODEL = "sonar"

load_dotenv(os.getenv("DOTENV_PATH", ".env"))
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

_llm_log = get_logger("llm")


class _LlmRequestLogger(BaseCallbackHandler):
    """LLM 요청이 실제로 나가고 끝날 때를 콘솔에 찍는다.

    모든 LangChain 모델(anthropic/gpt4o/gpt4o_mini)에 붙여, 어떤 체인에서든
    LLM 호출이 일어나면 '요청 시작 → 완료/실패'가 로그로 남는다. 워커가 실제로
    LLM 을 때리고 있는지 눈으로 확인하는 용도.
    """

    def _model_name(self, serialized, kwargs):
        # invocation_params 에 실제 모델 id(gpt-4o-mini 등)가 들어온다. 없으면 serialized 로 폴백.
        inv = kwargs.get("invocation_params") or {}
        s = serialized or {}
        return inv.get("model") or inv.get("model_name") \
            or (s.get("kwargs") or {}).get("model") or s.get("name") or "?"

    def on_chat_model_start(self, serialized, messages, **kwargs):
        n = sum(len(m) for m in messages)  # 배치 내 총 메시지 수
        _llm_log.info("LLM 요청 시작 model=%s messages=%d", self._model_name(serialized, kwargs), n)

    def on_llm_end(self, response, **kwargs):
        usage = None
        try:
            usage = (response.llm_output or {}).get("token_usage") \
                or (response.llm_output or {}).get("usage")
        except Exception:
            pass
        _llm_log.info("LLM 요청 완료 usage=%s", usage)

    def on_llm_error(self, error, **kwargs):
        _llm_log.warning("LLM 요청 실패 error=%r", error)


_llm_logger = _LlmRequestLogger()


anthropic = ChatAnthropic(
    model=ANTHROPIC_MODEL,
    max_tokens_to_sample=6000,
    temperature=0.8,
    api_key = ANTHROPIC_API_KEY,
    callbacks=[_llm_logger])

gpt4o = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY,
    callbacks=[_llm_logger])

gpt4o_mini = ChatOpenAI(
    model=OPENAI_MINI_MODEL,
    temperature=0.8,
    openai_api_key = OPENAI_API_KEY,
    callbacks=[_llm_logger])

perple = OpenAI(api_key = PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")

anthropic_async = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)