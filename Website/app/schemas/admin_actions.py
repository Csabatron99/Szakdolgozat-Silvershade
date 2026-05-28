from pydantic import BaseModel, Field


class CreateAdminActionRequest(BaseModel):
    type: str = Field(pattern="^(ban|kick|give_role|remove_role)$")
    playerId: str = Field(min_length=1, max_length=100)
    data: dict


class ConfirmAdminActionRequest(BaseModel):
    actionId: str
    status: str = Field(default="completed", pattern="^(pending|completed)$")
