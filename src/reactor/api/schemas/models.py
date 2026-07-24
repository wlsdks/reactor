from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ModelInfoResponse(BaseModel):
    name: str
    is_default: bool = Field(alias="isDefault")


class ModelsResponse(BaseModel):
    models: list[ModelInfoResponse]
    default_model: str = Field(alias="defaultModel")


class AdminModelResponse(BaseModel):
    name: str
    provider: str
    input_price_per_million_tokens: Decimal = Field(alias="inputPricePerMillionTokens")
    output_price_per_million_tokens: Decimal = Field(alias="outputPricePerMillionTokens")
    is_default: bool = Field(alias="isDefault")
