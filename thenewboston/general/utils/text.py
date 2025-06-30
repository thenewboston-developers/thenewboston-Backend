def truncate_text(text: str, max_length: int = 100) -> str:
    if not text:
        return ''

    if len(text) <= max_length:
        return text

    return text[:max_length] + '...'
