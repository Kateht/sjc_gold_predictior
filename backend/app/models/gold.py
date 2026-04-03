from pydantic import BaseModel

class GoldQuery(BaseModel):
    question: str

class GoldResponse(BaseModel):
    answer: str