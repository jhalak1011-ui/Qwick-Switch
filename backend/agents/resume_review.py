from fastapi import UploadFile
from pdf2image import convert_from_path
from io import BytesIO
import base64
import anthropic
import os
from dotenv import load_dotenv

load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def convert_pdf_to_images(pdf_path: str):
    images = convert_from_path(
        pdf_path,
        dpi=200,
        poppler_path=r"C:\poppler\poppler-24.08.0\Library\bin"
    )
    image_bytes_list = []

    for image in images:
        byte_stream = BytesIO()
        image.save(byte_stream, format="PNG")
        byte_stream.seek(0)
        image_bytes_list.append(byte_stream)

    return image_bytes_list


def review_resume_with_claude(image_bytes_list):
    image_data = image_bytes_list[0]

    prompt = (
        "You are a professional resume reviewer.\n"
        "Look at this resume visually and give:\n"
        "- Format feedback (alignment, spacing, section order)\n"
        "- Grammar / wording suggestions\n"
        "- Any missing sections or info\n"
        "- Overall improvements to make it more job-worthy."
    )

    base64_image = base64.b64encode(image_data.read()).decode("utf-8")
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


async def review_resume(resume: UploadFile):
    try:
        temp_path = f"temp_{resume.filename}"
        with open(temp_path, "wb") as f:
            f.write(await resume.read())

        images = convert_pdf_to_images(temp_path)
        feedback = review_resume_with_claude(images)

        os.remove(temp_path)
        return {"feedback": feedback}

    except Exception as e:
        return {"error": str(e)}
