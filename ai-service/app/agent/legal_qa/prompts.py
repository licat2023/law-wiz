from langchain_core.prompts import ChatPromptTemplate

LEGAL_QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "你是法律问答助手；仅依据提供的法条片段回答。"),
        ("human", "问题：{question}\n依据：{sources}"),
    ]
)
