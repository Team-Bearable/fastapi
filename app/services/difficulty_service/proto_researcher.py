from app.utils.difficulty_prompt import protoResearcher_prompt
from app.utils.model import anthropic, perple, PERPLEXITY_MODEL, gpt4o


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
                model = PERPLEXITY_MODEL,
                messages = perple_messages
            )
    case_result = response.choices[0].message.content

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

