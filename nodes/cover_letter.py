from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
llm = ChatAnthropic(model="claude-sonnet-4-20250514")

def generate_cover_letter(cv: str, job_description: str,
                           company: str, language: str = "German"):
    prompt = f"""
    You are an expert job application writer.

    Write a professional, tailored cover letter.

    Candidate CV:
    {cv}

    Job Description:
    {job_description}

    Company: {company}
    Language: {language}

    Rules:
    - Max 250 words
    - Highlight only relevant skills from the CV
    - Match the tone to the company
    - Sound human, not robotic
    - End with a confident closing line
    """
    response = llm.invoke(prompt)
    return response.content