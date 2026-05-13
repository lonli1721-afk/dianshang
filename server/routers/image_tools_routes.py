from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Request, UploadFile

import deps
from image_tools_service import (
    DeriveRequest,
    GenerateNineRequest,
    ImageToolTaskRequest,
    MultimodalAnalysisRequest,
    PromptPolishRequest,
    ReversePromptsRequest,
    ReverseStylePromptRequest,
    RoleSuggestionRequest,
    SplitGridRequest,
    WatermarkRequest,
    apply_watermark_batch,
    cancel_image_tool_task,
    create_image_tool_task,
    delete_image_tool_task,
    derive_image_batch,
    generate_nine_images,
    get_image_tool_task,
    list_image_tool_tasks,
    list_multimodal_analysis_models,
    list_watermark_fonts,
    multimodal_analysis,
    polish_generation_prompt,
    prepare_derive_request,
    prepare_generate_nine_request,
    prepare_reverse_request,
    prepare_split_grid_request,
    prepare_watermark_request,
    reverse_prompt_batch,
    reverse_style_prompt,
    suggest_role_items,
    save_watermark_font_upload,
    split_grid_batch,
)
from image_tools_service import _read_image_bytes  # re-exported for focused safety tests

IMAGE_TOOLBOX_TESTER_USERNAMES = {"zhouyanqing", "caipeiling", "huanglin", "huangye"}


def _admin_only(request: Request):
    user = getattr(request.state, "user", None) or {}
    if user.get("role") == "admin" or user.get("username") in IMAGE_TOOLBOX_TESTER_USERNAMES:
        return
    deps.require_admin(request)


router = APIRouter(dependencies=[Depends(_admin_only)])


@router.post("/watermark")
async def watermark(req: WatermarkRequest):
    prepared = prepare_watermark_request(req)

    async def _do():
        return await apply_watermark_batch(prepared)

    return deps.keepalive_response(_do)


@router.post("/split-grid")
async def split_grid(req: SplitGridRequest):
    prepared = prepare_split_grid_request(req)

    async def _do():
        return await split_grid_batch(prepared)

    return deps.keepalive_response(_do)


@router.post("/fonts/upload")
async def upload_font(file: UploadFile = File(...)):
    return await save_watermark_font_upload(file)


@router.get("/fonts")
async def list_fonts(preview_text: str = "火锅消除小游戏"):
    return await asyncio.to_thread(list_watermark_fonts, preview_text)


@router.post("/generate-nine")
async def generate_nine(req: GenerateNineRequest):
    prepared = prepare_generate_nine_request(req)

    async def _do():
        return await generate_nine_images(prepared)

    return deps.keepalive_response(_do)


@router.post("/tasks")
async def create_task(req: ImageToolTaskRequest):
    return await create_image_tool_task(req)


@router.get("/tasks")
async def list_tasks(limit: int = 50, status: str = ""):
    return await list_image_tool_tasks(limit=limit, status=status)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    return await get_image_tool_task(task_id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    return await cancel_image_tool_task(task_id)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    return await delete_image_tool_task(task_id)


@router.post("/reverse-style")
async def reverse_style(req: ReverseStylePromptRequest):
    async def _do():
        return await reverse_style_prompt(req)

    return deps.keepalive_response(_do)


@router.post("/prompt-polish")
async def prompt_polish(req: PromptPolishRequest):
    async def _do():
        return await polish_generation_prompt(req)

    return deps.keepalive_response(_do)


@router.post("/role-suggestions")
async def role_suggestions(req: RoleSuggestionRequest):
    async def _do():
        return await suggest_role_items(req)

    return deps.keepalive_response(_do)


@router.post("/derive")
async def derive(req: DeriveRequest):
    prepared = prepare_derive_request(req)

    async def _do():
        return await derive_image_batch(prepared)

    return deps.keepalive_response(_do)


@router.post("/reverse-prompts")
async def reverse_prompts(req: ReversePromptsRequest):
    prepared = prepare_reverse_request(req)

    async def _do():
        return await reverse_prompt_batch(prepared)

    return deps.keepalive_response(_do)


@router.get("/multimodal-analysis/models")
async def multimodal_analysis_models():
    return list_multimodal_analysis_models()


@router.post("/multimodal-analysis")
async def analyze_multimodal(req: MultimodalAnalysisRequest):
    async def _do():
        return await multimodal_analysis(req)

    return deps.keepalive_response(_do)
