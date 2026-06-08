from langchain.tools import tool
from dotenv import load_dotenv

import requests

#@tool
def search_jobs(skill: str, location: str = "India") -> str:
    """
    Searches for jobs based on a given skill and location using the JSearch API.
    """
    
    url = "https://jsearch.p.rapidapi.com/search"
    
    querystring = {
    "query": f"{skill} jobs in {location}",
    "page": "1",
    "num_pages": "1",
    "country": "India",
    "date_posted": "all"
    }    
    headers = {
    	"x-rapidapi-key": "9fe97cb47emshb1f0b54fe226cc3p1ffa2fjsnb1956fa0e501",
    	"x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    
    response = requests.get(url, headers=headers, params=querystring)

    data = response.json()

    jobs = data.get("data", [])
    
    if not jobs:
        print("DEBUG: No jobs returned. Full response:")
        print(data)
        return "No jobs found for that skill."

    results = []
    for job in jobs[:3]:  # limit to top 3 jobs
        results.append(
            f"- {job['job_title']} at {job['employer_name']} ({job['job_city']})\n  {job['job_apply_link']}"
        )
    return "\n".join(results)

