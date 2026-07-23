from typing import Any, Optional

from pydantic import BaseModel, Field


class ProofNode(BaseModel):
    type: str
    goal: Optional[str] = None
    body: Optional[str] = None
    subproof: Optional["ProofNode"] = None
    left: Optional["ProofNode"] = None
    right: Optional["ProofNode"] = None


class Solution(BaseModel):
    substitutions: dict[str, Any] = Field(default_factory=dict)
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
    version: Optional[str] = None


# ── Diagnosis models ──


class DiagnosisFinding(BaseModel):
    """A single finding from diagnosis: a missing fact, a blocking rule, etc."""
    type: str  # "missing_fact", "missing_rule", "blocking_condition", "satisfied"
    predicate: str
    detail: str = ""


class DiagnosisResult(BaseModel):
    """Result from diagnose(): explains why a query succeeds or fails."""
    query: str = ""
    mode: str = ""  # "why", "why_not", "what_needs"
    holds: bool = False  # whether the query is true or false
    findings: list[DiagnosisFinding] = Field(default_factory=list)
    proof: Optional[ProofNode] = None
    solutions: list[Solution] = Field(default_factory=list)
    conclusion: str = ""
    elapsed_ms: float = 0.0
    error: Optional[str] = None


# ── What-if models ──


class WhatIfResult(BaseModel):
    """Result from what_if(): shows impact of knowledge modifications."""
    query: str = ""
    modifications: str = ""
    before_count: int = 0  # solutions before modification
    after_count: int = 0  # solutions after modification
    delta: str = ""  # "more", "less", "same", "new", "lost"
    solutions_before: list[Solution] = Field(default_factory=list)
    solutions_after: list[Solution] = Field(default_factory=list)
    conclusion: str = ""
    elapsed_ms: float = 0.0
    error: Optional[str] = None


# ── KB check models ──


class KBError(BaseModel):
    """A single issue found in the knowledge base."""
    type: str  # "syntax_error", "undefined_predicate", "circular_rule", etc.
    message: str
    predicate: Optional[str] = None
    line: Optional[int] = None


class KBCheckResult(BaseModel):
    """Result from check_kb(): KB consistency and health report."""
    valid: bool = True
    errors: list[KBError] = Field(default_factory=list)
    warnings: list[KBError] = Field(default_factory=list)
    facts_count: int = 0
    rules_count: int = 0
    predicates_count: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None
