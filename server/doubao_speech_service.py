from __future__ import annotations

import asyncio
import gzip
import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any


logger = logging.getLogger("doubao_speech")

DOUBAO_ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
DOUBAO_ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"
SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
CHUNK_MS = 200
CHUNK_BYTES = int(SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE * CHUNK_MS / 1000)
SEND_SLEEP_SECONDS = 0.04


class DoubaoSpeechError(RuntimeError):
    def __init__(self, message: str, *, task_id: str = "", audio_seconds: float | None = None):
        super().__init__(message)
        self.task_id = task_id
        self.audio_seconds = audio_seconds


def _is_keepalive_timeout(exc: Exception) -> bool:
    text = str(exc).lower()
    return "keepalive ping timeout" in text or "no close frame received" in text


def _ffmpeg_exe() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise DoubaoSpeechError("当前环境缺少 ffmpeg，无法从直播视频中提取音频。") from exc


def _extract_pcm_sync(input_path: Path, output_path: Path) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-f",
        "s16le",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        str(output_path),
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise DoubaoSpeechError("直播视频音频提取超时，请先裁短视频后重试。") from exc
    except (PermissionError, OSError) as exc:
        raise DoubaoSpeechError(f"ffmpeg 无法启动：{exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        message = detail[-1] if detail else "ffmpeg 未能从视频中提取音频。"
        raise DoubaoSpeechError(f"直播视频音频提取失败：{message[:240]}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise DoubaoSpeechError("直播视频里没有可识别的音频轨道。")


async def extract_pcm_audio(input_path: Path, output_path: Path) -> float:
    await asyncio.to_thread(_extract_pcm_sync, input_path, output_path)
    size = output_path.stat().st_size
    return size / float(SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE)


def _header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([
        (0x01 << 4) | 0x01,
        (message_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])


def _pack_full_client_request(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body = gzip.compress(raw)
    return _header(0x01, 0x00, 0x01, 0x01) + len(body).to_bytes(4, "big") + body


def _pack_audio_request(chunk: bytes, *, final: bool) -> bytes:
    body = gzip.compress(chunk)
    flags = 0x02 if final else 0x00
    return _header(0x02, flags, 0x00, 0x01) + len(body).to_bytes(4, "big") + body


def _unpack_response(message: bytes) -> dict[str, Any]:
    if not isinstance(message, (bytes, bytearray)):
        raise DoubaoSpeechError("豆包语音返回了非二进制 WebSocket 消息。")
    data = bytes(message)
    if len(data) < 8:
        raise DoubaoSpeechError("豆包语音返回数据过短，无法解析。")

    header_size = (data[0] & 0x0F) * 4
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = header_size

    if message_type == 0x0F:
        if len(data) < offset + 8:
            raise DoubaoSpeechError("豆包语音返回错误帧，但内容不完整。")
        error_code = int.from_bytes(data[offset:offset + 4], "big", signed=False)
        offset += 4
        payload_size = int.from_bytes(data[offset:offset + 4], "big", signed=False)
        offset += 4
        payload = data[offset:offset + payload_size]
        if compression == 0x01:
            payload = gzip.decompress(payload)
        message_text = payload.decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(message_text)
            message_text = error_payload.get("message") or error_payload.get("error") or message_text
        except Exception:
            pass
        raise DoubaoSpeechError(f"豆包语音 ASR 返回错误 {error_code}: {message_text}")

    sequence = None
    if flags in (0x01, 0x03):
        if len(data) < offset + 4:
            raise DoubaoSpeechError("豆包语音返回结果缺少 sequence。")
        sequence = int.from_bytes(data[offset:offset + 4], "big", signed=True)
        offset += 4

    if len(data) < offset + 4:
        raise DoubaoSpeechError("豆包语音返回结果缺少 payload size。")
    payload_size = int.from_bytes(data[offset:offset + 4], "big", signed=False)
    offset += 4
    payload = data[offset:offset + payload_size]
    if compression == 0x01:
        payload = gzip.decompress(payload)

    parsed: Any = payload
    if serialization == 0x01 and payload:
        parsed = json.loads(payload.decode("utf-8"))

    return {
        "message_type": message_type,
        "flags": flags,
        "sequence": sequence,
        "payload": parsed,
    }


def _utterance_key(item: dict[str, Any]) -> tuple[Any, Any, str]:
    return (item.get("start_time"), item.get("end_time"), str(item.get("text") or ""))


def _collect_payload_text(payload: Any, segment_map: dict[tuple[Any, Any, str], dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result") or {}
    if isinstance(result, list):
        texts = []
        for item in result:
            text = _collect_payload_text({"result": item}, segment_map)
            if text:
                texts.append(text)
        return "".join(texts)
    if not isinstance(result, dict):
        return ""

    utterances = result.get("utterances") or []
    if isinstance(utterances, list):
        for item in utterances:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            key = _utterance_key(item)
            segment_map[key] = {
                "text": text,
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "definite": bool(item.get("definite")),
            }

    return str(result.get("text") or "").strip()


async def transcribe_media_file(
    *,
    api_key: str,
    media_path: Path,
    language: str = "zh-CN",
    resource_id: str = DOUBAO_ASR_RESOURCE_ID,
) -> dict[str, Any]:
    api_key = (api_key or "").strip()
    if not api_key:
        raise DoubaoSpeechError("豆包语音 API Key 未配置。")
    if not media_path.exists():
        raise DoubaoSpeechError("直播视频文件不存在，请重新上传。")

    import websockets

    task_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix="wanpi_asr_") as tmp_dir:
        pcm_path = Path(tmp_dir) / "audio.pcm"
        audio_seconds = await extract_pcm_audio(media_path, pcm_path)
        if audio_seconds <= 0:
            raise DoubaoSpeechError("直播视频里没有可识别的音频内容。")

        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id or DOUBAO_ASR_RESOURCE_ID,
            "X-Api-Connect-Id": task_id,
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1",
        }
        request_payload: dict[str, Any] = {
            "user": {
                "uid": "wanpi-batch-video",
                "platform": "web",
            },
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": SAMPLE_RATE,
                "bits": 16,
                "channel": CHANNELS,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
                "show_utterances": True,
                "result_type": "full",
            },
        }
        if language:
            request_payload["audio"]["language"] = language

        responses: list[dict[str, Any]] = []
        segment_map: dict[tuple[Any, Any, str], dict[str, Any]] = {}

        async def receive_until_final(ws) -> None:
            while True:
                raw = await ws.recv()
                parsed = _unpack_response(raw)
                responses.append(parsed)
                payload_text = _collect_payload_text(parsed.get("payload"), segment_map)
                if payload_text:
                    logger.debug("Doubao ASR partial transcript length=%s", len(payload_text))
                if parsed.get("message_type") == 0x09 and parsed.get("flags") == 0x03:
                    return

        connect_timeout = 30
        response_timeout = max(120, min(1800, int(audio_seconds * 2 + 120)))
        try:
            async with websockets.connect(
                DOUBAO_ASR_WS_URL,
                additional_headers=headers,
                open_timeout=connect_timeout,
                close_timeout=10,
                max_size=32 * 1024 * 1024,
                ping_interval=None,
            ) as ws:
                receiver = asyncio.create_task(receive_until_final(ws))
                await ws.send(_pack_full_client_request(request_payload))

                sent_chunks = 0
                total_size = pcm_path.stat().st_size
                with pcm_path.open("rb") as audio_file:
                    while True:
                        chunk = await asyncio.to_thread(audio_file.read, CHUNK_BYTES)
                        if not chunk:
                            break
                        final = audio_file.tell() >= total_size
                        await ws.send(_pack_audio_request(chunk, final=final))
                        sent_chunks += 1
                        if not final:
                            await asyncio.sleep(SEND_SLEEP_SECONDS)

                if sent_chunks == 0:
                    receiver.cancel()
                    raise DoubaoSpeechError("直播视频里没有可识别的音频内容。")
                await asyncio.wait_for(receiver, timeout=response_timeout)
        except DoubaoSpeechError:
            raise
        except asyncio.TimeoutError as exc:
            raise DoubaoSpeechError("豆包语音 ASR 等待结果超时，请裁短视频或稍后重试。") from exc
        except Exception as exc:
            if _is_keepalive_timeout(exc):
                raise DoubaoSpeechError("豆包语音 ASR 长连接超时，请重试；如果仍失败，请裁短直播视频或降低上传视频时长。") from exc
            raise DoubaoSpeechError(f"豆包语音 ASR 调用失败：{exc}") from exc

    transcript = ""
    for parsed in responses:
        text = _collect_payload_text(parsed.get("payload"), segment_map)
        if text:
            transcript = text
    if not transcript and segment_map:
        transcript = "".join(item["text"] for item in sorted(
            segment_map.values(),
            key=lambda item: (item.get("start_time") is None, item.get("start_time") or 0),
        ))

    segments = sorted(
        segment_map.values(),
        key=lambda item: (item.get("start_time") is None, item.get("start_time") or 0),
    )
    if not transcript.strip():
        raise DoubaoSpeechError("豆包语音 ASR 已返回，但没有识别出文本。", task_id=task_id, audio_seconds=audio_seconds)

    return {
        "task_id": task_id,
        "transcript": transcript.strip(),
        "segments": segments,
        "audio_seconds": audio_seconds,
        "resource_id": resource_id or DOUBAO_ASR_RESOURCE_ID,
        "response_count": len(responses),
    }
