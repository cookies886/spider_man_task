import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.alert import AlertHistory, AlertRule
from app.schemas.alert import AlertHistoryRead, AlertRuleCreate, AlertRuleRead, AlertRuleUpdate
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


@router.get("/rules", response_model=PaginatedResponse)
async def list_alert_rules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    project_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(AlertRule)
    count_query = select(func.count(AlertRule.id))
    if project_id:
        query = query.where(AlertRule.project_id == project_id)
        count_query = count_query.where(AlertRule.project_id == project_id)

    total = (await session.execute(count_query)).scalar() or 0
    skip = (page - 1) * page_size
    result = await session.execute(
        query.order_by(AlertRule.created_at.desc()).offset(skip).limit(page_size)
    )
    items = [AlertRuleRead.model_validate(r) for r in result.scalars().all()]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("/rules", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    session: AsyncSession = Depends(get_session),
):
    rule = AlertRule(**body.model_dump())
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    await session.commit()
    return AlertRuleRead.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=AlertRuleRead)
async def update_alert_rule(
    rule_id: uuid.UUID,
    body: AlertRuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    await session.flush()
    await session.refresh(rule)
    await session.commit()
    return AlertRuleRead.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await session.delete(rule)
    await session.commit()


@router.get("/history", response_model=PaginatedResponse)
async def list_alert_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    rule_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(AlertHistory)
    count_query = select(func.count(AlertHistory.id))
    if rule_id:
        query = query.where(AlertHistory.rule_id == rule_id)
        count_query = count_query.where(AlertHistory.rule_id == rule_id)

    total = (await session.execute(count_query)).scalar() or 0
    skip = (page - 1) * page_size
    result = await session.execute(
        query.order_by(AlertHistory.sent_at.desc()).offset(skip).limit(page_size)
    )
    items = [AlertHistoryRead.model_validate(h) for h in result.scalars().all()]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )
