"""启动时播种超级管理员账号。"""
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.db.base import SessionLocal
from app.models.user import User, UserRole


def seed_admin() -> None:
    db: Session = SessionLocal()
    try:
        exists = (
            db.query(User)
            .filter(User.username == settings.admin_username)
            .first()
        )
        if exists:
            return
        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"[seed] 已创建超级管理员: {settings.admin_username}")
    finally:
        db.close()
