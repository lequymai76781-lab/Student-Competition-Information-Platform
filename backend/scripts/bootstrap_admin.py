"""V1.0.1 admin bootstrap from environment variables (no fixed default password).

Requires ADMIN_EMAIL and ADMIN_PASSWORD env vars. Refuses obvious defaults.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import User


def main() -> None:
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not email or not password:
        raise SystemExit("需要环境变量 ADMIN_EMAIL 与 ADMIN_PASSWORD")
    if password in {"test123456", "admin123", "password", "123456"} or len(password) < 12:
        raise SystemExit("拒绝使用常见/过短密码作为管理员凭据")
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if admin is None:
            admin = User(
                email=email,
                username="admin",
                hashed_password=hash_password(password),
                is_admin=True,
            )
            db.add(admin)
        else:
            admin.email = email
            admin.hashed_password = hash_password(password)
            admin.is_admin = True
        db.commit()
    print(f"管理员已创建/更新：{email}（密码未回显）")


if __name__ == "__main__":
    main()
