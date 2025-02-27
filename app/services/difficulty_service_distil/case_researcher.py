
from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from utils.difficulty_prompt_distil import  material_organizer, perplexity_prompt
from utils.model import anthropic, perple, perplexity_model, gpt4o
from utils.utils import perple_process_result


def llm_material_organizer(major, topic, context, model, state):

    tp_cs = material_organizer()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain  = {"major": RunnablePassthrough(), "topic": RunnablePassthrough(), 'context':RunnablePassthrough() }|topic_prompt | gpt4o | StrOutputParser()
    result = chain.invoke({'major': major, 'topic':topic, 'context': context})
    return result



def perplexity(state):
    print('perplexity 진입')
    # 테스트용 기본 응답 데이터 생성
    major = state['major']
    topic = state['topic']
    
    prompt = perplexity_prompt(topic)
    perple_messages = [
        {"role": "system",
         "content": (prompt.system)},
        {"role": "user",
         "content": (prompt.user)}
    ]
    
    try:
        response = perple.chat.completions.create(
            model = perplexity_model,
            messages = perple_messages
        )
        case_result = response.choices[0].message.content
        citations = response.citations
    except Exception as e:
        print('perplexity 오류:', e)
    json_case = ""
    case = ""
    while True:
        try:
            case = llm_material_organizer(major, topic, case_result, gpt4o, state
) 
            json_case = perple_process_result(case)
            break
        except Exception as e:
            print('perple json 오류:', e)
            print('이거보세요', case)
            break
    case_study = list(filter(lambda x: x['host']!='no', json_case))
    applied_study = list(filter(lambda x: x['host']=='no', json_case))
    reference_news = []
    case_study_str = "<<<관련 사례>>>\n"
    if len(case_study) > 0:
        for i in case_study:
            print('펄플i', i)
            case_study_str +=f"""
    * 사례: {i['topic']}
    * 내용: {i['content']}
    * 진행 기관: {i['host']}
    * 관련 자료 링크: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({'title': i['topic'],
                                   'institute': i['host'],
                                   'url': [citations[ii-1] for ii in eval(i['src'])][0],
                                   'date':None})
    else:
        case_study_str = ""

    applied_study_str = "<<<응용 탐구>>>\n"
    if len(applied_study) > 0:
        for i in applied_study:
            applied_study_str +=f"""
    * 주제: {i['topic']}
    * 내용: {i['content']}
    * 관련 자료: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({'title': i['topic'],
                                   'institute': '응용탐구',
                                   'url': [citations[ii-1] for ii in eval(i['src'])][0],
                                   'date':None})
    else:
        applied_study_str = ""

    return {'case_result': applied_study_str + "\n" + case_study_str, 'reference_news': reference_news}
