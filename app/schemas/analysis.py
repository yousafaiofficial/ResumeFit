from pydantic import BaseModel, ConfigDict, Field


class AnalysisRewrite(BaseModel):
    original: str
    suggested: str
    source: str = "rules"


class AnalysisResponse(BaseModel):
    id: int
    job_title: str
    score: float
    semantic_score: float
    skill_score: float | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    sections: dict[str, bool] = Field(default_factory=dict)
    word_count: int
    suggestions: list[str] = Field(default_factory=list)
    rewrites: list[AnalysisRewrite] = Field(default_factory=list)
    engine: str
    cached: bool = False
    created_at: str | None = None


class AnalysisItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_title: str
    score: float
    created_at: str


class PaginatedAnalysisHistory(BaseModel):
    items: list[AnalysisItemSummary]
    limit: int
    next_cursor: int | None = None
    has_more: bool
