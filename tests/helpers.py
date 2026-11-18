import hashlib
import hmac
import json

SECRET = "secreto-de-prueba"
ALLOWED = "573001112233"


def text_payload(sender: str = ALLOWED, msg_id: str = "wamid.1", body: str = "Hola") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": sender,
                                    "id": msg_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


def media_payload(
    kind: str = "document",
    media_id: str = "media-1",
    mime: str = "application/pdf",
    msg_id: str = "wamid.doc",
    sender: str = ALLOWED,
) -> dict:
    payload = text_payload(sender=sender, msg_id=msg_id)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    del message["text"]
    message["type"] = kind
    message[kind] = {"id": media_id, "mime_type": mime, "filename": "hv.pdf"}
    return payload
