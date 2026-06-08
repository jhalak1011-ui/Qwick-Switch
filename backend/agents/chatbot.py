from typing_extensions import TypedDict
from typing import Annotated, Optional
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain_anthropic import ChatAnthropic
from backend.agents.career_question import career_questions_agent
from backend.agents.resume_feedback_vision_agent import resume_feedback_agent
from backend.agents.job_search_tool import search_jobs
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
import os

import uuid

load_dotenv("openaiapikey.env")
memory = MemorySaver()

# ✅ Define State with resume_path
class State(TypedDict):
    messages: Annotated[list, add_messages]
    resume_path: Optional[str]
    route: Optional[str]

# Initialize model and tools
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.7, anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"))
tool_list = [search_jobs]
llm_with_tools = llm.bind_tools(tool_list)

# ✅ Chatbot function
def chatbot(state: State) -> State:
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

# ✅ Router: Decide which agent to use
def router(state: State):
    last_message = state["messages"][-1].content.lower()
    if "resume" in last_message:
        return {"route": "resume_feedback_agent"}
    elif any(word in last_message for word in ("career", "question")):
        return {"route": "ask_career_questions"}
    else:
        return {"route": "chatbot"}

# ✅ Build the LangGraph workflow
builder = StateGraph(State)
builder.add_node("router", router)
builder.add_node("ask_career_questions", career_questions_agent)
builder.add_node("resume_feedback_agent", resume_feedback_agent)
builder.add_node("tools", ToolNode(tool_list))
builder.add_node("chatbot", chatbot)

builder.set_entry_point("router")
builder.add_conditional_edges("router", lambda state: state["route"], {
    "ask_career_questions": "ask_career_questions",
    "resume_feedback_agent": "resume_feedback_agent",
    "chatbot": "chatbot"
})
builder.add_conditional_edges("chatbot", tools_condition)
builder.add_edge("tools", "chatbot")

# All end
builder.add_edge("ask_career_questions", "__end__")
builder.add_edge("resume_feedback_agent", "__end__")

graph = builder.compile(checkpointer=memory)

# ✅ Final entrypoint function
from typing import Optional  # ✅ Add this import

def career_counselor(user_query: str, thread_id: str, resume_path: Optional[str] = None):
    config = {"configurable": {"thread_id": thread_id}}
    message = {"role": "user", "content": user_query}

    # ✅ Only pass *new input*, don't overwrite memory
    input_state = {"messages": [message]}
    if resume_path:
        input_state["resume_path"] = resume_path

    response = graph.invoke(input_state, config=config)

    return response["messages"][-1].content

import uuid
from fastapi import UploadFile

# Dict to store conversation history {thread_id: [messages]}
chat_histories = {}

def chatbot_fn(text: str, thread_id: str = None, resume_file: UploadFile = None):
    """
    Chatbot logic with optional resume upload and persistent history.
    """

    if not thread_id:
        thread_id = uuid.uuid4().hex

    if thread_id not in chat_histories:
        chat_histories[thread_id] = []

    chat_histories[thread_id].append({"role": "user", "text": text})

    resume_path = None
    if resume_file:
        import os, shutil
        os.makedirs("uploads", exist_ok=True)
        resume_path = f"uploads/{uuid.uuid4().hex}_{resume_file.filename}"
        with open(resume_path, "wb") as f:
            shutil.copyfileobj(resume_file.file, f)

    response = career_counselor(text, thread_id, resume_path)

    # Store bot response
    chat_histories[thread_id].append({"role": "bot", "text": response})

    return response, thread_id, chat_histories[thread_id]
