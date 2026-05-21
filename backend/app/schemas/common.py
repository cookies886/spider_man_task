from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_projects: int = 0
    total_tasks_today: int = 0
    running_tasks: int = 0
    failed_tasks_today: int = 0
    active_workers: int = 0
    success_rate: float = 0.0


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int
