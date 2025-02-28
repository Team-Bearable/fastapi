from utils.difficulty_prompt_distil2 import protoResearcher_prompt
from utils.model import anthropic, perple, perplexity_model, gpt4o
from utils.logging_config import logger 


def protoResearcher(state):
    major = state['major']
    keyword = state['keyword']
    topic = state['topic']
    phase = state['phase']
    search_keyword = state['search_keywords'][phase]
    prompt = protoResearcher_prompt(major, keyword, topic, search_keyword)
    perple_messages = [
        {"role": "system",
        "content": (prompt.system)},
    {"role": "user",
        "content": (prompt.user)}
    ]
    response = perple.chat.completions.create(
                model = perplexity_model,
                messages = perple_messages
            )
    try: 
        case_result = response.choices[0].message.content
    except Exception as e:
        logger.exception("Error during protoResearcher extraction: %s", e)
    return {"information": [case_result]}

def protoResearchDataset(state):
    """
    entrypoint setting을 위한 작업
    """


def protoResearchCollector(state):
    """
    Research 취합
    """
    information = '\n'.join(state['information'])
    return {'additional_info': information}

