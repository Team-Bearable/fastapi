import re, json

def json_format(json_str: str) -> dict:
    """
    json_str 문자열에서 "introduction", "body", "conclusion"에 해당하는
    key와 value만 추출하여 딕셔너리로 반환합니다.
    
    이 방법은 전체 문자열의 불필요한 \n 등의 제어문자에 신경쓰지 않고,
    key-value 구조가 고정되어 있다는 가정 하에 효율적으로 원하는 부분만 추출합니다.
    """
    pattern = re.compile(
        r'"(introduction|body|conclusion)"\s*:\s*"((?:\\.|[^"\\])*)"'
    )
    matches = pattern.findall(json_str)
    
    if len(matches) != 3:
        raise ValueError(f"Expected exactly 3 key-value pairs, but found {len(matches)}.")
    
    data = {key: value for key, value in matches}
    return data
def perple_json_format(response):
    response = response.replace("json", '')
    response = response.replace("```", '').strip()
    response = re.sub(r'[\n\\]+(?="?\})', '', response)
    response = json.loads(response)
    return response

def perple_process_result(result):
    """
    에러 대비 JSON 처리 로직
    """
    try:
        return perple_json_format(result)
    except Exception as e:
        print(repr(result))
        raise ValueError(f"오류: {e}")