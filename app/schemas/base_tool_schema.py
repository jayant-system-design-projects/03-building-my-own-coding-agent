from typing import Callable, Literal
from pydantic import BaseModel, Field, model_validator


class Properties(BaseModel):
    property_type: str = Field(alias="type", default="object")
    description: str


class Parameters(BaseModel):
    parameter_type: str = Field(alias="type", default="object")
    properties: dict[str, Properties] = Field(default_factory=dict)


class Function(BaseModel):
    name: str
    description: str
    parameters: Parameters
    required: list[str]

    @model_validator(mode="after")
    def validate_required(self):
        missing = self.required - self.parameters.properties.keys()

        if missing:
            raise ValueError(f"Required properties not defined: {sorted(missing)}")

        return self


class ToolBase(BaseModel):
    tool_type: str = Field(alias="type", default="function")
    function: Function


class Tool(BaseModel):
    tool_schema: ToolBase = Field(alias="schema")
    function: Callable


class Mode(BaseModel):
    mode: Literal["low", "medium", "high"]
