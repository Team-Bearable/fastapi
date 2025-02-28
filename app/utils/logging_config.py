import logging

# 애플리케이션 로거 생성 및 설정
logger = logging.getLogger("llm_logger")
logger.setLevel(logging.DEBUG)

# 콘솔 핸들러 추가 (필요시 파일 핸들러도 추가 가능)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)