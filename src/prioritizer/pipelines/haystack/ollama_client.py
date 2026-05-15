from haystack import component
import requests
import csv

@component
class OllamaGenerator:
    def __init__(self, seed_number: int, model="gpt-oss:120b-cloud", url="http://localhost:11434/api/generate",  full_prompt_file: str = None):
        self.model = model
        self.url = url
        self.full_prompt_file = full_prompt_file
        self.seed_number = seed_number

    def run(self, prompt: str):
        if self.full_prompt_file is not None:
            with open(self.full_prompt_file, "w", newline="", encoding="utf-8") as f: 
                writer = csv.writer(f)
                writer.writerow([prompt])

        response = requests.post(self.url, json={
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 1.0,
                "seed": self.seed_number,
                "top_p": 0,
            }
        })

        result = response.json()

        return {"response": result["response"]}