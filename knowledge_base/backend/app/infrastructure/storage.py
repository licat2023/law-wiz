"""保存知识库上传原文件。"""

import asyncio

from app.infrastructure.database import new_id


async def write_file(state, body):
    """用生成的存储键写入原文件，返回可存入修订记录的键。"""
    key = new_id()
    target = state.settings.data_root / "files" / key
    await asyncio.to_thread(target.write_bytes, body)
    return key
