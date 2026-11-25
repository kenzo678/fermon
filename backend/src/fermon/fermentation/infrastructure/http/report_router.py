import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response

from fermon.fermentation.infrastructure.http.dependencies import BuildBatchReportDep
from fermon.fermentation.infrastructure.http.schemas import ErrorResponse
from fermon.fermentation.infrastructure.reporting import render_csv, render_pdf, report_filename

router = APIRouter()

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/batches/{batch_id}/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, **_ERRORS},
)
async def download_pdf_report(batch_id: UUID, use_case: BuildBatchReportDep) -> Response:
    """The batch report as a PDF. Active batches give a partial report; planned ones are 409."""
    report = await use_case.execute(batch_id)
    # WeasyPrint is synchronous and CPU-bound: keep it off the event loop.
    pdf = await asyncio.to_thread(render_pdf, report)
    return _attachment(pdf, "application/pdf", report_filename(report, "pdf"))


@router.get(
    "/batches/{batch_id}/report.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, **_ERRORS},
)
async def download_csv_report(batch_id: UUID, use_case: BuildBatchReportDep) -> Response:
    """The batch summary and per-measurement statistics as CSV (same rules as the PDF)."""
    report = await use_case.execute(batch_id)
    return _attachment(
        render_csv(report), "text/csv; charset=utf-8", report_filename(report, "csv")
    )
