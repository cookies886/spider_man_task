import base64
import hashlib
import uuid

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.env_var import EnvVar
from app.schemas.common import PaginatedResponse
from app.schemas.env_var import EnvVarCreate, EnvVarRead, EnvVarUpdate

router = APIRouter(
    prefix="/env-vars", tags=["env-vars"], dependencies=[Depends(get_current_user)]
)


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application secret_key."""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def _encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext value for storage."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def _decrypt_value(ciphertext: str) -> str:
    """Decrypt a stored ciphertext value."""
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode()).decode()


@router.get("", response_model=PaginatedResponse)
async def list_env_vars(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List environment variables for a project (secrets are masked)."""
    query = select(EnvVar).where(EnvVar.project_id == project_id)
    count_query = select(func.count(EnvVar.id)).where(EnvVar.project_id == project_id)

    total = (await session.execute(count_query)).scalar() or 0
    skip = (page - 1) * page_size
    result = await session.execute(
        query.order_by(EnvVar.created_at.desc()).offset(skip).limit(page_size)
    )
    env_vars = result.scalars().all()

    items = []
    for ev in env_vars:
        decrypted_value = _decrypt_value(ev.value)
        # Temporarily set plaintext for schema conversion, then mask
        ev_read = EnvVarRead(
            id=ev.id,
            project_id=ev.project_id,
            key=ev.key,
            value="***" if ev.is_secret else decrypted_value,
            description=ev.description,
            is_secret=ev.is_secret,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )
        items.append(ev_read)

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=EnvVarRead, status_code=status.HTTP_201_CREATED)
async def create_env_var(
    body: EnvVarCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new environment variable (value is encrypted at rest)."""
    encrypted_value = _encrypt_value(body.value)
    env_var = EnvVar(
        project_id=body.project_id,
        key=body.key,
        value=encrypted_value,
        description=body.description,
        is_secret=body.is_secret,
    )
    session.add(env_var)
    await session.flush()
    await session.refresh(env_var)
    await session.commit()

    return EnvVarRead(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value="***" if env_var.is_secret else body.value,
        description=env_var.description,
        is_secret=env_var.is_secret,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


@router.patch("/{env_var_id}", response_model=EnvVarRead)
async def update_env_var(
    env_var_id: uuid.UUID,
    body: EnvVarUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an environment variable."""
    result = await session.execute(select(EnvVar).where(EnvVar.id == env_var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Environment variable not found")

    update_data = body.model_dump(exclude_unset=True)
    if "value" in update_data and update_data["value"] is not None:
        update_data["value"] = _encrypt_value(update_data["value"])

    for key, value in update_data.items():
        setattr(env_var, key, value)

    await session.flush()
    await session.refresh(env_var)
    await session.commit()

    is_secret = env_var.is_secret
    decrypted_value = _decrypt_value(env_var.value)
    return EnvVarRead(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value="***" if is_secret else decrypted_value,
        description=env_var.description,
        is_secret=is_secret,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


@router.delete("/{env_var_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_env_var(
    env_var_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete an environment variable."""
    result = await session.execute(select(EnvVar).where(EnvVar.id == env_var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    await session.delete(env_var)
    await session.commit()


@router.get("/{env_var_id}/reveal", response_model=EnvVarRead)
async def reveal_env_var(
    env_var_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Reveal the actual value of an environment variable (authorized users only)."""
    result = await session.execute(select(EnvVar).where(EnvVar.id == env_var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Environment variable not found")

    decrypted_value = _decrypt_value(env_var.value)
    return EnvVarRead(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value=decrypted_value,
        description=env_var.description,
        is_secret=env_var.is_secret,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )
