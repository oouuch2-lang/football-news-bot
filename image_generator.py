"""
Генерация изображений через один из бесплатных ИИ-провайдеров.
Если провайдер недоступен или вернул ошибку — функция возвращает None,
и пост публикуется без картинки. Это штатная ситуация, а не сбой бота.
"""
import base64
import time

import requests

import config


def generate_image(prompt: str) -> bytes | None:
    """Генерирует картинку способом, выбранным в config.IMAGE_PROVIDER."""
    if config.IMAGE_PROVIDER == "none":
        return None

    generators = {
        "pollinations": _generate_pollinations,
        "huggingface": _generate_huggingface,
        "cloudflare": _generate_cloudflare,
    }
    generator = generators.get(config.IMAGE_PROVIDER)
    if generator is None:
        print(f"Неизвестный IMAGE_PROVIDER: {config.IMAGE_PROVIDER!r}, картинка не создаётся")
        return None

    try:
        return generator(prompt)
    except Exception as e:
        print(f"Генерация изображения не удалась ({config.IMAGE_PROVIDER}): {e}")
        return None


def _generate_pollinations(prompt: str) -> bytes:
    """Pollinations AI — бесплатно и без ключа, обычный GET-запрос с промптом в URL."""
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    response = requests.get(url, params={"width": 1024, "height": 1024, "nologo": "true"}, timeout=60)
    response.raise_for_status()
    return response.content


def _generate_huggingface(prompt: str) -> bytes:
    """Hugging Face Inference API. Бесплатный тариф, но модель может 'просыпаться' —
    тогда сервер отвечает 503, и мы один раз ждём и пробуем снова."""
    url = f"https://api-inference.huggingface.co/models/{config.HUGGINGFACE_MODEL}"
    headers = {"Authorization": f"Bearer {config.HUGGINGFACE_API_KEY}"}

    response = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=60)
    if response.status_code == 503:
        wait_seconds = min(response.json().get("estimated_time", 20), 30)
        time.sleep(wait_seconds)
        response = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=60)

    response.raise_for_status()
    return response.content


def _generate_cloudflare(prompt: str) -> bytes:
    """Cloudflare Workers AI (FLUX). Бесплатный тариф, ответ приходит как base64-картинка в JSON."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{config.CLOUDFLARE_MODEL}"
    )
    headers = {"Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}"}
    response = requests.post(url, headers=headers, json={"prompt": prompt}, timeout=60)
    response.raise_for_status()

    image_b64 = response.json()["result"]["image"]
    return base64.b64decode(image_b64)
