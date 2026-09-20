"""文件切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.api import CurrentUserId, RequestId, get_db
from app.core.errors import ApiResponse
from app.slices.files import service
from app.slices.files.schemas import FileData, UploadFileData

router = APIRouter(tags=["文件"])

DbSession = Annotated[Session, Depends(get_db)]


# ⚠️ 必须是 `async def`：读取上传内容用的是 `await upload.read()`。
# 写成同步 `def`（FastAPI 会放进线程池执行）会导致读取失败。
@router.post(
    "/files",
    response_model=ApiResponse[UploadFileData],
    status_code=status.HTTP_201_CREATED,
    summary="B-01 上传文件",
)
async def upload_file(
    file: Annotated[UploadFile, File(description="合同文件（PDF / DOCX / JPG / PNG，≤20 MB）")],
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
) -> ApiResponse[UploadFileData]:
    data = await service.read_upload(file)
    result = service.save_upload(
        db,
        user_id=user_id,
        original_name=file.filename,
        data=data,
    )
    db.commit()
    return ApiResponse.ok(result, request_id=rid)


@router.get(
    "/files/{file_id}",
    response_model=ApiResponse[FileData],
    summary="B-02 获取文件元数据",
)
def get_file(
    file_id: int,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
) -> ApiResponse[FileData]:
    return ApiResponse.ok(service.get_file_meta(db, user_id=user_id, file_id=file_id), request_id=rid)
