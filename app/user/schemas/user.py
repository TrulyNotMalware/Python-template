from pydantic import BaseModel, ConfigDict, Field


class GetUserListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID")
    email: str = Field(..., description="Email")
    nickname: str = Field(..., description="Nickname")


class CreateUserRequestSchema(BaseModel):
    email: str = Field(..., description="Email")
    password1: str = Field(..., description="Password1")
    password2: str = Field(..., description="Password2")
    nickname: str = Field(..., description="Nickname")


class CreateUserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str = Field(..., description="Email")
    nickname: str = Field(..., description="Nickname")
