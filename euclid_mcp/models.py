from pydantic import BaseModel, Field
from typing import Optional


class ProofNode(BaseModel):
    type: str
    goal: Optional[str] = None
    body: Optional[str] = None
    subproof: Optional["ProofNode"] = None
    left: Optional["ProofNode"] = None
    right: Optional["ProofNode"] = None


class Solution(BaseModel):
    substitutions: dict[str, str] = Field(default_factory=dict)
    proof: ProofNode


class ReasonResult(BaseModel):
    solutions: list[Solution] = Field(default_factory=list)
    query: str = ""
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class KB(BaseModel):
    facts: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    query: Optional[str] = None
