"""数据库模型的静态元数据约束。"""

from app.models.memory import Memory


def test_memory_index_names_are_unique():
    index_names = [index.name for index in Memory.__table__.indexes]

    assert len(index_names) == len(set(index_names))
