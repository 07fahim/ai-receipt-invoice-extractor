import os
import time
import uuid

os.environ['APP_SCHEMA'] = 'test_' + uuid.uuid4().hex[:8]

import providers

os.environ['GROQ_API_KEY'] = 'test-groq'
os.environ['OPENROUTER_API_KEY'] = 'test-or'


def chat_fallback():
    real, seen = providers.post, []

    def fake(url, headers, body, retries=3, timeout=60):
        seen.append((url, body['model'], retries, timeout))
        if 'groq' in url:
            raise RuntimeError('HTTP 429: rate limit')
        return {'choices': [{'message': {'role': 'assistant', 'content': 'hi'}}], 'usage': {'total_tokens': 7}}, 1

    providers.post = fake
    try:
        msg, usage = providers.chat([{'role': 'user', 'content': 'x'}], [])
        assert msg['content'] == 'hi' and usage == {'total_tokens': 7}
        assert [s[1] for s in seen] == ['qwen/qwen3.8-27b', 'qwen/qwen3.8-27b:free'], seen
        assert all(s[2] == 0 and s[3] == 20 for s in seen)  # no waiting retries: the fallback is the retry

        def down(*a, **k):
            raise RuntimeError('HTTP 503')
        providers.post = down
        try:
            providers.chat([{'role': 'user', 'content': 'x'}], [])
            raise AssertionError('expected RuntimeError')
        except RuntimeError as e:
            assert 'qwen/qwen3.8-27b' in str(e)
    finally:
        providers.post = real


chat_fallback()
print('ok')
