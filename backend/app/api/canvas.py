from dataclasses import asdict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/canvas")


@router.get("/courses")
async def courses(request: Request):
    return [asdict(c) for c in await request.app.state.canvas.courses()]


@router.get("/courses/{course_id}/assignments")
async def assignments(course_id: str, request: Request):
    return [{**asdict(a), "supported": a.supported} for a in await request.app.state.canvas.assignments(course_id)]
