from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.issues import service
from app.issues.schemas import RoadIssueOut

router = APIRouter(prefix="/api/v1/issues", tags=["issues"])


@router.get("", response_model=list[RoadIssueOut])
def list_issues(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    issues = service.list_issues_for_user(db, current_user.id)
    return [RoadIssueOut.model_validate(i) for i in issues]
