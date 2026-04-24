from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=255)


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


from datetime import datetime


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    full_name: str | None
    cohort_code: str | None
    created_at: datetime

    model_config = {'from_attributes': True}
