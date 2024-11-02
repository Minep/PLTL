from openai import OpenAI
from pydantic import BaseModel
import os

class LatinEntry(BaseModel):
    expression: str
    explain_grammar: str
    explain_semantic: str
    explain_nuances: str

class LatinResponse(BaseModel):
    entries: list[LatinEntry]

class Explaination:
    def __init__(self, client: OpenAI, words):
        self.__client = client
        response = self.__get_response(words)
        self.__refusal = response.refusal
        
        if self.is_refused():
            return
        
        self.entries = response.parsed.entries
    

    def is_refused(self):
        return self.__refusal is not None
    
    def refused_message(self):
        return self.__refusal

    def __create_prompt(self, words):
        return [
            {
                "role": "system", 
                "content": """
You are a helpful tutor on Classical Latin.
The input is a list of Latin expressions separated by pipe, |.
Each expression could be a word, a phrase or a sentence.
If an expression is word and it's approximated grammar property may supplied in parenthesis for disambiguation.
For each expression you will provide an explaination.
Your explaination must meet the following requirements:
    1. the grammatical role of that expression.
    2. the semantic of that expression.
    3. the nuances of that expression.
Your explaination must signify the difference of that expression from others.
Your explaination should: organised naturally, avoid listing, short and concise
If the expression is not a valid Classical Latin, explain why.
""".strip()
            },
            {
                "role": "user", 
                "content": "|".join(words)
            }
        ]
    
    def __get_response(self, words):
        return self.__client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=self.__create_prompt(words),
            response_format=LatinResponse,
        ).choices[0].message
    
class Explainer:
    def __init__(self, api_key_file="apikey"):
        self.__en = True

        if not os.path.exists(api_key_file):
            print("No ApiKey to OpenAI is detected, disabled explainer.")
            self.__client = None
            self.__en = False
            return
        

        with open(api_key_file, 'r') as f: 
            self.__client = OpenAI(api_key=f.read())

    def set_enabled(self, val):
        if self.__client:
            self.__en = val

    def explain(self, words):
        if not self.__en:
            return None
        return Explaination(self.__client, words)


explainer = Explainer()