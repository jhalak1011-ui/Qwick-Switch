from pdf2image import convert_from_path
from io import BytesIO
import base64
import os
import anthropic
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.7, anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"))

def convert_pdf_to_images(pdf_path: str):
    images = convert_from_path(pdf_path, dpi=200, poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin")
    image_bytes_list = []

    for image in images:
        byte_stream = BytesIO()
        image.save(byte_stream, format="PNG")
        byte_stream.seek(0)
        image_bytes_list.append(byte_stream)

    return image_bytes_list

def review_resume_with_claude(image_bytes_list):
    image_data = image_bytes_list[0]
    base64_image = base64.b64encode(image_data.read()).decode("utf-8")

    prompt = (
        "You are a professional resume reviewer.\n"
        "Look at this resume visually and give:\n"
        "- Format feedback (alignment, spacing, section order)\n"
        "- Grammar / wording suggestions\n"
        "- Any missing sections or info\n"
        "- Overall improvements to make it more job-worthy."
    )

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_image
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )
    return response.content[0].text


def resume_feedback_agent(state):
    resume_path = state.get("resume_path", None)

    if not resume_path or not os.path.isfile(resume_path):
        return {
            "messages": state["messages"] + [
                AIMessage(content="No valid resume file path provided.")
            ]
        }

    try:
        images = convert_pdf_to_images(resume_path)
        feedback = review_resume_with_claude(images)
        return {
            "messages": state["messages"] + [AIMessage(content=feedback)]
        }
    except Exception as e:
        return {
            "messages": state["messages"] + [AIMessage(content=f"Error processing resume: {str(e)}")]
        }
