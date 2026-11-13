"""
Seed Authentication Data

Creates initial users for development and testing:
- admin / admin123 (ADMIN role)
- developer / dev123 (ANALYST role)  
- user / user123 (USER role)
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

from api.models.user import Base, User, Role, Permission

# Password hashing
def get_password_hash(password: str) -> str:
    """Hash a password using the maintained bcrypt package directly."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp without deprecated APIs."""
    return datetime.now(timezone.utc)


async def seed_users():
    """Create initial test users"""

    db_host = os.getenv("MAHOUN_DB_HOST", "localhost")
    db_port = os.getenv("MAHOUN_DB_PORT", "5432")
    db_name = os.getenv("MAHOUN_DB_NAME", "mahoun")
    db_user = os.getenv("MAHOUN_DB_USER", "mahoun")
    db_pass = os.getenv("MAHOUN_DB_PASSWORD")
    if not db_pass:
        raise RuntimeError("MAHOUN_DB_PASSWORD must be set to seed authentication data")

    # URL encode password to handle special characters
    db_pass_encoded = quote_plus(db_pass)

    database_url = f"postgresql+asyncpg://{db_user}:{db_pass_encoded}@{db_host}:{db_port}/{db_name}"

    print(f"🔌 Connecting to database: {db_host}:{db_port}/{db_name}")
    
    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Get roles
            from sqlalchemy import select
            
            result = await session.execute(select(Role).where(Role.name == "ADMIN"))
            admin_role = result.scalar_one_or_none()
            
            result = await session.execute(select(Role).where(Role.name == "ANALYST"))
            analyst_role = result.scalar_one_or_none()
            
            result = await session.execute(select(Role).where(Role.name == "USER"))
            user_role = result.scalar_one_or_none()
            
            if not all([admin_role, analyst_role, user_role]):
                print("❌ Roles not found. Please run migrations first: alembic upgrade head")
                return
            
            # Create admin user
            result = await session.execute(select(User).where(User.username == "admin"))
            admin_user = result.scalar_one_or_none()
            
            if not admin_user:
                admin_user = User(
                    username="admin",
                    email="admin@mahoun.ai",
                    full_name="System Administrator",
                    hashed_password=get_password_hash("admin123"),
                    is_active=True,
                    is_superuser=True,
                    is_verified=True,
                    created_at=utc_now(),
                    updated_at=utc_now()
                )
                admin_user.roles.append(admin_role)
                session.add(admin_user)
                print("✅ Created admin user: admin / admin123")
            else:
                print("⚠️  Admin user already exists")
            
            # Create developer user
            result = await session.execute(select(User).where(User.username == "developer"))
            dev_user = result.scalar_one_or_none()
            
            if not dev_user:
                dev_user = User(
                    username="developer",
                    email="dev@mahoun.ai",
                    full_name="Developer User",
                    hashed_password=get_password_hash("dev123"),
                    is_active=True,
                    is_superuser=False,
                    is_verified=True,
                    created_at=utc_now(),
                    updated_at=utc_now()
                )
                dev_user.roles.append(analyst_role)
                session.add(dev_user)
                print("✅ Created developer user: developer / dev123")
            else:
                print("⚠️  Developer user already exists")
            
            # Create regular user
            result = await session.execute(select(User).where(User.username == "user"))
            regular_user = result.scalar_one_or_none()
            
            if not regular_user:
                regular_user = User(
                    username="user",
                    email="user@mahoun.ai",
                    full_name="Regular User",
                    hashed_password=get_password_hash("user123"),
                    is_active=True,
                    is_superuser=False,
                    is_verified=True,
                    created_at=utc_now(),
                    updated_at=utc_now()
                )
                regular_user.roles.append(user_role)
                session.add(regular_user)
                print("✅ Created regular user: user / user123")
            else:
                print("⚠️  Regular user already exists")
            
            # Commit changes
            await session.commit()
            print("\n✅ Seed data created successfully!")
            print("\n📋 Test Users:")
            print("  • admin / admin123 (Full access)")
            print("  • developer / dev123 (Analyst access)")
            print("  • user / user123 (Read-only access)")
            
        except Exception as e:
            print(f"❌ Error seeding data: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("🌱 Seeding authentication data...\n")
    asyncio.run(seed_users())
