"""
Database Schemas for AptLearn – 15-Day Interview Preparation Portal

Each Pydantic model represents a collection in MongoDB. The collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")

class Module(BaseModel):
    key: str = Field(..., description="Unique key e.g., aptitude, technical, hr")
    title: str
    order: int

class Day(BaseModel):
    day_number: int = Field(..., ge=1, le=15)
    module_key: str = Field(..., description="Module key this day belongs to")
    title: str
    video_url: str
    notes: str

class Question(BaseModel):
    day_number: int
    prompt: str
    options: List[str]
    answer_index: int = Field(..., ge=0)

class Attempt(BaseModel):
    user_id: str
    day_number: int
    answers: List[int]
    score: int
    total: int
    flagged: bool = False
    violations: int = 0

class Progress(BaseModel):
    user_id: str
    completed_days: List[int] = []

class Certificate(BaseModel):
    user_id: str
    name: str
    issued_at: str
    svg: str
