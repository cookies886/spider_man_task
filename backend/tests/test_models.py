"""Test that all ORM models import correctly and have expected attributes."""
from app.models import (
    AlertHistory,
    AlertRule,
    Base,
    Environment,
    GitRepo,
    Project,
    ProjectDistribution,
    ProjectFile,
    Task,
    TaskDependency,
    TaskRun,
    Worker,
)


def test_all_models_importable():
    """All models should be importable from the models package."""
    models = [
        Base, Project, GitRepo, ProjectFile, ProjectDistribution, Task,
        TaskRun, TaskDependency, Worker, Environment, AlertRule, AlertHistory,
    ]
    assert all(m is not None for m in models)


def test_project_tablename():
    assert Project.__tablename__ == "projects"


def test_git_repo_tablename():
    assert GitRepo.__tablename__ == "git_repos"


def test_task_tablename():
    assert Task.__tablename__ == "tasks"


def test_task_run_tablename():
    assert TaskRun.__tablename__ == "task_runs"


def test_worker_tablename():
    assert Worker.__tablename__ == "workers"


def test_environment_tablename():
    assert Environment.__tablename__ == "environments"


def test_alert_rule_tablename():
    assert AlertRule.__tablename__ == "alert_rules"


def test_alert_history_tablename():
    assert AlertHistory.__tablename__ == "alert_history"


def test_base_has_metadata():
    assert Base.metadata is not None
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "projects", "git_repos", "project_files", "project_distributions",
        "tasks", "task_runs", "task_dependencies", "workers", "environments",
        "alert_rules", "alert_history",
    }
    assert expected.issubset(table_names)


def test_worker_has_node_id_and_api_key_hash():
    from app.models.worker import Worker
    cols = {c.name for c in Worker.__table__.columns}
    assert "node_id" in cols
    assert "api_key_hash" in cols
    assert "type" in cols
    assert "os" in cols
    assert "arch" in cols
    assert "python_version" in cols
