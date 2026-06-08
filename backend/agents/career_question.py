import os
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv("openaiapikey.env")
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.7, anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"))


def career_questions_agent(state):
    system_prompt = (
        "You're a friendly career coach.\n"
        "Start the conversation by asking these questions to understand the user's background:\n"
        "1. What are your strengths?\n"
        "2. What topics interest you?\n"
        "3. Do you prefer working in teams or alone?\n"
        "4. What's your dream job?\n"
        "Keep it short, encouraging, and conversational."
    )

    messages = [AIMessage(role="system", content=system_prompt)] + state["messages"]
    response = llm.invoke(messages)

    # ✅ Append new AI response to existing message history
    return {
        "messages": state["messages"] + [AIMessage(content=response.content)]
    }
