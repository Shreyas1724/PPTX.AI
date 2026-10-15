"""Validated presentation-design intermediate representation.

Legacy title/body/notes slides remain valid. All additional fields are optional;
no external assets or executable content enter the renderer.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Layout = Literal[
    'title', 'section', 'summary', 'bullets', 'two_column', 'three_column',
    'problem_solution', 'quote', 'kpi', 'chart', 'process', 'timeline',
    'architecture', 'comparison', 'table', 'evidence', 'roadmap', 'conclusion',
    'references', 'methodology', 'case_study', 'formula', 'pros_cons', 'feature_grid',
]

class DataPoint(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label: str=Field(min_length=1,max_length=45)
    value: float=Field(ge=-1e12,le=1e12,allow_inf_nan=False)

class ChartSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['bar','line','pie']
    points: list[DataPoint]=Field(min_length=2,max_length=12)
    unit: str=Field(default='',max_length=20)
    title: str=Field(default='',max_length=100)
    @model_validator(mode='after')
    def valid_pie(self):
        if self.kind=='pie' and (any(p.value<0 for p in self.points) or sum(p.value for p in self.points)==0):
            raise ValueError('Pie charts need nonnegative values and a positive total.')
        return self

class MetricSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label: str=Field(min_length=1,max_length=75)
    value: str=Field(min_length=1,max_length=35)
    context: str=Field(default='',max_length=100)

class SlideSpec(BaseModel):
    """A slide with the legacy API shape and strictly bounded design metadata."""
    model_config=ConfigDict(extra='forbid')
    title: str=Field(min_length=1,max_length=110)
    body: list[str]=Field(default_factory=list,max_length=6)
    notes: str=Field(default='',max_length=1200)
    layout: Layout|None=None
    subtitle: str=Field(default='',max_length=180)
    key_message: str=Field(default='',max_length=240)
    chart: ChartSpec|None=None
    metrics: list[MetricSpec]=Field(default_factory=list,max_length=4)
    steps: list[str]=Field(default_factory=list,max_length=8)
    sources: list[str]=Field(default_factory=list,max_length=5)
    @model_validator(mode='after')
    def check(self):
        if any(not isinstance(b,str) or not 0<len(b.strip())<=240 for b in self.body):
            raise ValueError('Slide body entries must be 1–240 characters long.')
        if any(not 0<len(x.strip())<=150 for x in self.steps):
            raise ValueError('Process steps must be 1–150 characters long.')
        if any(not 0<len(x.strip())<=230 for x in self.sources):
            raise ValueError('Sources must be 1–230 characters long.')
        return self

def validate_slide(item: dict) -> SlideSpec:
    """Require real, bounded fields; do not silently drop unfamiliar AI metadata."""
    return SlideSpec.model_validate(item)

def validate_deck(items: list[dict]) -> list[SlideSpec]:
    if not isinstance(items,list) or not 1<=len(items)<=20:
        raise ValueError('A presentation must contain between 1 and 20 slides.')
    return [validate_slide(item) for item in items]
