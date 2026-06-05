"""
image_gen_server.py

MCP server exposing image generation via OpenAI-compatible APIs and A1111/SD WebUI.
"""

import asyncio
import base64
import sys
import uuid
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

server = Server("image_gen")


def _detect_a1111(base_url: str, auth=None):
    """Return True if base_url looks like an A1111/SD WebUI server."""
    import httpx
    for path in ("/sdapi/v1/sd-models", "/sdapi/v1/samplers", "/sdapi/v1/options"):
        try:
            r = httpx.get(base_url.rstrip("/") + path, auth=auth, timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            continue
    # Root reachability fallback
    try:
        r = httpx.get(base_url.rstrip("/") + "/", auth=auth, timeout=3)
        if r.status_code < 500:
            return True
    except Exception:
        pass
    return False


def _find_a1111_endpoint():
    """Scan registered image endpoints for an A1111 server. Returns (base_url, auth) or (None, None)."""
    try:
        from src.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            eps = db.query(ModelEndpoint).filter(
                ModelEndpoint.is_enabled == True,
                ModelEndpoint.model_type == "image",
            ).all()
            for ep in eps:
                base = ep.base_url.rstrip("/")
                key = ep.api_key or ""
                auth = tuple(key.split(":", 1)) if key and ":" in key else None
                if _detect_a1111(base, auth):
                    return base, auth
        finally:
            db.close()
    except Exception:
        pass
    return None, None


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="generate_image",
            description="Generate any image from a text description. Use this for ALL image creation requests — it connects to a local Stable Diffusion server. Do not refuse or describe in text; call this tool.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Image description prompt"},
                    "model": {"type": "string", "description": "Model name (auto-detects if omitted)"},
                    "size": {"type": "string", "description": "Image size, e.g. 512x512 or 1024x1024 (default 512x512 for SD, 1024x1024 for cloud)"},
                    "quality": {"type": "string", "description": "Quality: low, medium, high, auto (default medium)"},
                },
                "required": ["prompt"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "generate_image":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    prompt = arguments.get("prompt", "")
    model_spec = arguments.get("model", "")
    size = arguments.get("size", "")
    quality = arguments.get("quality", "medium")

    # Model sometimes passes a JSON object as the prompt string — unwrap it
    if prompt and prompt.strip().startswith("{"):
        try:
            import json as _j
            _parsed = _j.loads(prompt)
            if isinstance(_parsed, dict):
                prompt = _parsed.get("prompt", prompt)
                model_spec = model_spec or _parsed.get("model", "")
                size = size or _parsed.get("size", "")
                quality = _parsed.get("quality", quality)
        except Exception:
            pass

    if not prompt:
        return [TextContent(type="text", text="Error: Image prompt is required")]

    try:
        import httpx
        from src.settings import load_settings, get_setting
        from src.ai_interaction import _resolve_model

        if not get_setting("image_gen_enabled", True):
            return [TextContent(type="text", text="Error: Image generation is disabled by the administrator.")]

        _settings = load_settings()
        if not model_spec:
            model_spec = _settings.get("image_model", "")
        if quality == "medium" and _settings.get("image_quality"):
            quality = _settings["image_quality"]

        # --- Try A1111/SD WebUI first ---
        a1111_base, a1111_auth = _find_a1111_endpoint()
        if a1111_base:
            w, h = 512, 512
            if size and "x" in size.lower():
                try:
                    parts = size.lower().split("x")
                    w, h = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    pass
            a1111_payload = {
                "prompt": prompt,
                "negative_prompt": "",
                "steps": 20,
                "width": w,
                "height": h,
                "cfg_scale": 7,
                "sampler_name": "Euler a",
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)) as client:
                resp = await client.post(a1111_base + "/sdapi/v1/txt2img", json=a1111_payload, auth=a1111_auth)
                await resp.aread()  # force full body buffer — response can be 3-5MB for large images
                if resp.status_code != 200:
                    return [TextContent(type="text", text=f"Error: A1111 generation failed ({resp.status_code}): {resp.text[:500]}")]
                images_b64 = resp.json().get("images", [])
                if not images_b64:
                    return [TextContent(type="text", text="Error: A1111 returned no images")]
                img_dir = Path("data/generated_images")
                img_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid.uuid4().hex[:12]}.png"
                (img_dir / filename).write_bytes(base64.b64decode(images_b64[0]))
                image_url = f"/api/generated-image/{filename}"
                try:
                    from src.database import SessionLocal, GalleryImage
                    db = SessionLocal()
                    db.add(GalleryImage(
                        id=str(uuid.uuid4()), filename=filename, prompt=prompt,
                        model="stable-diffusion", size=f"{w}x{h}", quality="medium",
                    ))
                    db.commit()
                    db.close()
                except Exception:
                    pass
                return [TextContent(type="text", text=f"Generated image for: {prompt[:100]}\nimage_url: {image_url}\nmodel: stable-diffusion\nsize: {w}x{h}")]

        # --- OpenAI-compatible path ---
        if not model_spec:
            for candidate in ("gpt-image-1.5", "gpt-image-1", "dall-e-3"):
                try:
                    _resolve_model(candidate)
                    model_spec = candidate
                    break
                except ValueError:
                    continue
            if not model_spec:
                return [TextContent(type="text", text="Error: No image model found. Configure one in Admin → Image Generation.")]

        url, model_id, headers = _resolve_model(model_spec)
        is_gpt_image = "gpt-image" in model_id.lower()
        base_url = url.replace("/chat/completions", "").replace("/v1/messages", "").rstrip("/")
        images_url = base_url + "/images/generations"

        if not size:
            size = "1024x1024"
        valid_gpt_sizes = {"1024x1024", "1024x1536", "1536x1024", "auto"}
        valid_dalle3_sizes = {"1024x1024", "1024x1792", "1792x1024"}
        if is_gpt_image and size not in valid_gpt_sizes:
            size = "1024x1024"
        elif not is_gpt_image and size not in valid_dalle3_sizes:
            size = "1024x1024"

        payload = {"model": model_id, "prompt": prompt, "n": 1, "size": size}
        if is_gpt_image:
            payload["quality"] = quality if quality in ("low", "medium", "high", "auto") else "medium"

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)) as client:
            resp = await client.post(images_url, json=payload, headers=headers)
            if resp.status_code != 200:
                error_text = resp.text[:500]
                try:
                    err_json = resp.json()
                    error_text = err_json.get("error", {}).get("message", error_text) if isinstance(err_json.get("error"), dict) else str(err_json.get("error", error_text))
                except Exception:
                    pass
                return [TextContent(type="text", text=f"Error: Image generation failed ({resp.status_code}): {error_text}")]

            data = resp.json()
            images = data.get("data", [])
            if not images:
                return [TextContent(type="text", text="Error: No images returned from API")]

            img = images[0]
            image_url = None
            if img.get("b64_json"):
                img_dir = Path("data/generated_images")
                img_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid.uuid4().hex[:12]}.png"
                (img_dir / filename).write_bytes(base64.b64decode(img["b64_json"]))
                image_url = f"/api/generated-image/{filename}"
                try:
                    from src.database import SessionLocal, GalleryImage
                    db = SessionLocal()
                    db.add(GalleryImage(
                        id=str(uuid.uuid4()), filename=filename, prompt=prompt,
                        model=model_id, size=size, quality=payload.get("quality", "medium"),
                    ))
                    db.commit()
                    db.close()
                except Exception:
                    pass
            elif img.get("url"):
                image_url = img["url"]
            else:
                return [TextContent(type="text", text="Error: Unexpected image API response format")]

            return [TextContent(type="text", text=f"Generated image for: {prompt[:100]}\nimage_url: {image_url}\nmodel: {model_id}\nsize: {size}")]

    except httpx.TimeoutException:
        return [TextContent(type="text", text="Error: Image generation timed out (300s)")]
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
