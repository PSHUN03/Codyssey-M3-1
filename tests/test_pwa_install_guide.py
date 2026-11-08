"""PWA guide remains one shared header action with platform-specific dialog content."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_install_action_and_both_guides_exist_on_public_and_member_pages(client):
    pages = [client.get('/').text, client.get('/login').text]
    client.post('/demo')
    pages.extend(client.get(route).text for route in ['/home', '/plan', '/settings'])
    for html in pages:
        assert html.count('id="pwa-install-button"') == 1
        assert html.count('id="pwa-install-dialog"') == 1
        assert 'data-pwa-guide="android" hidden' in html
        assert 'data-pwa-guide="ios"' in html
        assert '설치 및 바로가기 만들기' in html
        assert 'Safari에서 간단히 추가해요.' in html
        assert '홈 화면에 아이콘이 생겨요.' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is needed for PWA event regressions')
def test_install_event_regressions():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([shutil.which('node'), '--test', 'tests/frontend/pwa-install.test.cjs'],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
