from typing import Any, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateExecutionRequest(BaseModel):
    workflow_type: str  # new_partner | new_partner_user


class ManualInputRequest(BaseModel):
    model_config = {"extra": "allow"}

    # Common manual fields — all optional since different steps need different things
    organization_name: Optional[str] = None
    organization_id: Optional[str] = None
    studio_company_name_test: Optional[str] = None
    studio_company_id_test: Optional[str] = None
    studio_company_name_prod: Optional[str] = None
    studio_company_id_prod: Optional[str] = None
    keycloak_cluster: Optional[str] = None
    keycloak_confirmed: Optional[bool] = None
    scopes: Optional[str] = None
    lms_confirmed: Optional[bool] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    languages: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    roles: Optional[list[str]] = None
    selected_studio_company_ids: Optional[list[str]] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
