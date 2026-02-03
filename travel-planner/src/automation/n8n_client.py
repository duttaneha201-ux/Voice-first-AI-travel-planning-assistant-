"""
n8n webhook client for PDF generation and email automation.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from src.utils.config import n8n_webhook_url
from src.utils.logger import get_logger

logger = get_logger()

_MAX_DEBUG_BODY_CHARS = 4000


def _redact_url(url: str) -> str:
    # Avoid leaking tokens if user ever pastes one into the URL.
    if not url:
        return url
    for marker in ("token=", "api_key=", "apikey="):
        if marker in url.lower():
            return url.split("?", 1)[0] + "?REDACTED=1"
    return url


def _is_test_webhook(url: str) -> bool:
    return "/webhook-test/" in (url or "")


def _suggest_production_webhook(url: str) -> str | None:
    if not url:
        return None
    if "/webhook-test/" in url:
        return url.replace("/webhook-test/", "/webhook/")
    return None


def send_itinerary_to_n8n(
    itinerary: dict[str, Any],
    email: str | None = None,
    generate_pdf: bool = True,
    send_email: bool = False,
) -> dict[str, Any]:
    """
    Send itinerary data to n8n webhook for PDF generation and/or email sending.
    
    Args:
        itinerary: Itinerary dict with "days" and "metadata" keys.
        email: Optional email address to send the itinerary to.
        generate_pdf: Whether to generate a PDF (default True).
        send_email: Whether to send email (default False, requires email).
    
    Returns:
        Dict with "success" (bool), "message" (str), and optional "pdf_url" or "error".
    
    Example:
        >>> it = {"days": [...], "metadata": {...}}
        >>> result = send_itinerary_to_n8n(it, email="user@example.com", send_email=True)
        >>> result["success"]
        True
    """
    webhook_url = n8n_webhook_url()
    if not webhook_url:
        return {
            "success": False,
            "message": "n8n webhook URL not configured",
            "error": "N8N_WEBHOOK_URL not set in .env. Add it to enable PDF/email export.",
        }
    webhook_url = webhook_url.strip()
    
    # Prepare payload for n8n
    payload = {
        "itinerary": itinerary,
        "options": {
            "generate_pdf": generate_pdf,
            "send_email": send_email,
        },
    }
    
    if email:
        payload["email"] = email
    
    try:
        logger.info("Sending POST request to n8n webhook: %s", _redact_url(webhook_url))
        logger.debug("Payload keys: %s", list(payload.keys()))
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        logger.info("n8n webhook responded with status: %s", getattr(response, "status_code", None))
        status_code = getattr(response, "status_code", None)
        content_type = (response.headers.get("Content-Type") or "").lower()
        body_text = ""
        try:
            body_text = response.text or ""
        except Exception:
            body_text = ""

        # Success path: binary PDF response
        if status_code and 200 <= status_code < 300 and ("application/pdf" in content_type):
            pdf_bytes = response.content or b""
            return {
                "success": True,
                "message": "PDF generated successfully",
                "pdf_bytes": pdf_bytes,
                "content_type": content_type,
                "status_code": status_code,
                "debug": {
                    "webhook_url": _redact_url(webhook_url),
                    "is_test_webhook": _is_test_webhook(webhook_url),
                    "suggested_production_url": _suggest_production_webhook(webhook_url),
                    "response_headers": {"content-type": content_type},
                    "response_body_preview": (body_text[:_MAX_DEBUG_BODY_CHARS] if body_text else ""),
                },
            }

        # Normal JSON response
        response.raise_for_status()
        parsed: dict[str, Any] = {}
        if response.content:
            try:
                parsed = response.json()
            except Exception:
                parsed = {"raw": (body_text[:_MAX_DEBUG_BODY_CHARS] if body_text else "")}

        out: dict[str, Any] = {
            "success": True,
            "message": parsed.get("message") or "Itinerary sent to n8n successfully",
            "pdf_url": parsed.get("pdf_url"),
            "email_sent": bool(parsed.get("email_sent", False)),
            "n8n_response": parsed,
            "status_code": status_code,
            "debug": {
                "webhook_url": _redact_url(webhook_url),
                "is_test_webhook": _is_test_webhook(webhook_url),
                "suggested_production_url": _suggest_production_webhook(webhook_url),
                "response_headers": {"content-type": content_type},
                "response_body_preview": (body_text[:_MAX_DEBUG_BODY_CHARS] if body_text else ""),
            },
        }

        # If workflow doesn't return pdf_url, surface an actionable hint.
        if generate_pdf and not out.get("pdf_url") and not out.get("pdf_bytes"):
            out["hint"] = (
                "n8n responded successfully, but did not include `pdf_url`. "
                "Update your n8n workflow to either (a) return a `pdf_url` in the Respond to Webhook node, "
                "or (b) respond with the PDF bytes (Content-Type: application/pdf) so the app can offer a download."
            )
        if send_email and email and not out.get("email_sent"):
            out["hint"] = (
                (out.get("hint") + " " if out.get("hint") else "")
                + "n8n did not confirm `email_sent=true`. Check SMTP credentials and the IF: Send Email? node conditions."
            )
        return out
    except requests.exceptions.RequestException as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.exception("n8n webhook request failed: %s (%s)", error_msg, error_type)
        
        # Provide more specific error messages
        if isinstance(e, requests.exceptions.ConnectionError):
            detailed_error = f"Connection failed: Could not reach n8n at {_redact_url(webhook_url)}. Check if the URL is correct and n8n is accessible."
        elif isinstance(e, requests.exceptions.Timeout):
            detailed_error = f"Request timed out after 30 seconds. n8n may be slow or unresponsive."
        elif isinstance(e, requests.exceptions.HTTPError):
            detailed_error = f"HTTP error: {error_msg}"
        else:
            detailed_error = f"{error_type}: {error_msg}"
        
        url_hint = ""
        if _is_test_webhook(webhook_url):
            prod = _suggest_production_webhook(webhook_url)
            url_hint = (
                "You are using an n8n Test URL (`/webhook-test/`). "
                "Test URLs only work when the workflow is in 'listening/test' mode. "
                + (f"Prefer switching to the Production URL: {prod}" if prod else "Prefer switching to the Production URL (`/webhook/...`).")
            )
        return {
            "success": False,
            "message": f"Failed to send to n8n: {detailed_error}",
            "error": detailed_error,
            "error_type": error_type,
            "hint": url_hint or None,
            "debug": {
                "webhook_url": _redact_url(webhook_url),
                "is_test_webhook": _is_test_webhook(webhook_url),
                "suggested_production_url": _suggest_production_webhook(webhook_url),
                "error_type": error_type,
            },
        }
    except Exception as e:
        logger.exception("Unexpected error sending to n8n: %s", e)
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "error": str(e),
        }


def format_itinerary_for_pdf(itinerary: dict[str, Any]) -> str:
    """
    Format itinerary as HTML for PDF generation.
    
    Args:
        itinerary: Itinerary dict with "days" and "metadata".
    
    Returns:
        HTML string suitable for PDF conversion.
    """
    days = itinerary.get("days", [])
    meta = itinerary.get("metadata", {})
    
    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='UTF-8'>",
        "<title>Udaipur Travel Itinerary</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 20px; }",
        "h1 { color: #2c3e50; }",
        "h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }",
        "h3 { color: #7f8c8d; }",
        ".day { margin-bottom: 30px; }",
        ".activity { margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 3px solid #3498db; }",
        ".time { font-weight: bold; color: #2980b9; }",
        ".cost { color: #27ae60; }",
        ".summary { background: #ecf0f1; padding: 15px; border-radius: 5px; margin-top: 20px; }",
        "</style></head><body>",
        "<h1>🗺️ Udaipur Travel Itinerary</h1>",
    ]
    
    # Add metadata summary
    if meta:
        total_cost = meta.get("total_cost_inr", 0)
        duration = meta.get("duration_days", len(days))
        pace = meta.get("pace", "moderate")
        
        html_parts.append("<div class='summary'>")
        html_parts.append(f"<p><strong>Duration:</strong> {duration} day(s)</p>")
        html_parts.append(f"<p><strong>Pace:</strong> {pace.title()}</p>")
        if total_cost:
            html_parts.append(f"<p><strong>Estimated Total Cost:</strong> ₹{total_cost}</p>")
        html_parts.append("</div>")
    
    # Add days
    for day in days:
        day_num = day.get("day_number", 0)
        activities = day.get("activities", [])
        date = day.get("date", "")
        
        html_parts.append(f"<div class='day'>")
        html_parts.append(f"<h2>Day {day_num}</h2>")
        if date:
            html_parts.append(f"<p><em>{date}</em></p>")
        
        # Group by time blocks
        time_blocks = {"Morning": [], "Afternoon": [], "Evening": [], "Other": []}
        for act in activities:
            time_str = act.get("time", "")
            poi = act.get("poi", {})
            poi_name = poi.get("name", "") or "Activity"
            
            # Determine time block
            block = "Other"
            if time_str:
                hour_match = time_str.split(":")[0] if ":" in time_str else ""
                try:
                    hour = int(hour_match)
                    if "PM" in time_str.upper() and hour != 12:
                        hour += 12
                    if 5 <= hour < 12:
                        block = "Morning"
                    elif 12 <= hour < 17:
                        block = "Afternoon"
                    elif 17 <= hour < 22:
                        block = "Evening"
                except (ValueError, AttributeError):
                    pass
            
            time_blocks[block].append((time_str, act, poi))
        
        # Render time blocks
        for block_name in ["Morning", "Afternoon", "Evening", "Other"]:
            if time_blocks[block_name]:
                html_parts.append(f"<h3>{block_name}</h3>")
                for time_str, act, poi in time_blocks[block_name]:
                    poi_name = poi.get("name", "") or "Activity"
                    duration = poi.get("duration_hours", 0) or act.get("duration_hours", 0)
                    cost = poi.get("cost_inr", 0) or 0
                    travel_time = act.get("travel_time_from_previous", 0)
                    
                    html_parts.append("<div class='activity'>")
                    html_parts.append(f"<span class='time'>{time_str}</span> - <strong>{poi_name}</strong>")
                    if duration:
                        html_parts.append(f" <em>({duration}h)</em>")
                    if travel_time:
                        html_parts.append(f" <small>(Travel: {travel_time} min)</small>")
                    if cost:
                        html_parts.append(f" <span class='cost'>₹{cost}</span>")
                    else:
                        html_parts.append(" <span class='cost'>Free</span>")
                    html_parts.append("</div>")
        
        html_parts.append("</div>")
    
    # Add sources if available
    sources = itinerary.get("sources")
    if sources:
        html_parts.append("<h2>📚 Sources & References</h2>")
        pois = sources.get("pois", [])
        if pois:
            html_parts.append("<p><strong>Places referenced:</strong></p><ul>")
            for poi in pois[:10]:
                poi_name = poi.get("name", "")
                if poi_name:
                    links = poi.get("links", {})
                    link_texts = []
                    if "google_maps" in links:
                        link_texts.append(f"<a href='{links['google_maps']}'>Maps</a>")
                    if "wikipedia" in links:
                        link_texts.append(f"<a href='{links['wikipedia']}'>Wiki</a>")
                    if link_texts:
                        html_parts.append(f"<li>{poi_name} ({', '.join(link_texts)})</li>")
                    else:
                        html_parts.append(f"<li>{poi_name}</li>")
            html_parts.append("</ul>")
    
    html_parts.append("</body></html>")
    return "\n".join(html_parts)
