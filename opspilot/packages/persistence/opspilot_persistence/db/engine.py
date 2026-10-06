from sqlalchemy import Engine, create_engine


def create_db_engine(url: str) -> Engine:
    """Engine creation is lazy: no connection is made until first use."""
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
