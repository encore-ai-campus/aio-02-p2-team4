"""First-use consent UI regression; all API and non-local traffic is intercepted."""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import Error, sync_playwright, expect

BASE = os.environ.get("CONSENT_TEST_URL", "http://127.0.0.1:3018")
LONG_TEXT = "합성 시험 원문의 사실 여부를 확인해 주세요. " * 10


with sync_playwright() as runtime:
    browser = runtime.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    posts = []

    def intercept(route):
        request = route.request
        if not request.url.startswith(BASE + "/"):
            route.abort()
            return
        path = urlparse(request.url).path
        if not path.startswith("/api/"):
            route.continue_()
            return
        if request.method == "GET":
            value = {"items": [], "nextCursor": None} if path.startswith("/api/conversations") else {
                "configured": True, "jevConfigured": True, "model": "gpt-6-luna",
                "modelOptions": [{"id": model, "configured": True} for model in
                                 ["deepseek-v4.1-flash", "gpt-6-luna", "gemini-3.8-flash", "gemini-3.7-flash"]],
            }
        else:
            body = request.post_data_json
            posts.append((path, body))
            assert body.get("consent") is True, "No fabricated or missing consent may reach an API"
            if path == "/api/intent":
                value = {"action": "reply", "reply": "모의 응답입니다.", "focus": None}
            elif path == "/api/summarize":
                value = {"result": {"title": "합성 요약", "summary": "모의 요약입니다.", "points": [],
                                    "sourceName": None, "sourceUrl": None, "warnings": [],
                                    "model": "gpt-6-luna", "reasoning": "max"}}
            else:
                value = {"text": body["text"], "focus": body["focus"], "demo": False,
                         "model": "typesafe-ai/jev" if path.endswith("/jev") else "gpt-6-luna",
                         "reasoning": "max", "checkedAt": "2026-10-05T00:00:00Z",
                         "claims": [], "sources": [], "evidence": [], "warnings": [], "market": None,
                         "answer": {"status": "insufficient_evidence", "overview": None,
                                    "sections": [], "conclusion": None, "model": None, "reasoning": None}}
                if path == "/api/fact-check":
                    route.fulfill(content_type="application/x-ndjson", body=json.dumps({"type": "result", "result": value}) + "\n")
                    return
        route.fulfill(content_type="application/json", body=json.dumps(value))

    context.route("**/*", intercept)
    page = context.new_page()
    cancelled = []
    page.on("requestfailed", lambda request: cancelled.append(request.url) if request.url.endswith("/api/intent") else None)

    def send(text):
        page.get_by_label("확인할 원문", exact=True).fill(text)
        page.get_by_role("button", name="팩트 검증 시작", exact=True).click()

    try:
        page.goto(BASE, wait_until="networkidle")
        page.get_by_role("combobox", name="답변 모델 선택").click()
        for model in ["DeepSeek V4.1 Flash Max", "GPT-6 Luna Max", "Gemini 3.8 Flash", "Gemini 3.7 Flash"]:
            expect(page.get_by_role("option").filter(has_text=model)).to_be_visible()
        page.get_by_role("option").filter(has_text="DeepSeek V4.1 Flash Max").click()
        expect(page.get_by_role("combobox", name="답변 모델 선택")).to_contain_text("DeepSeek V4.1 Flash Max")
        page.get_by_role("combobox", name="답변 모델 선택").click()
        page.get_by_role("option").filter(has_text="Auto").click()
        expect(page.locator(".sidebar").get_by_label("이 브라우저에서 대화 저장")).to_have_count(0)
        send(LONG_TEXT)
        dialog = page.get_by_role("dialog", name="외부 서비스 전송 동의", exact=True)
        expect(dialog).to_be_visible()
        expect(dialog.get_by_label("이 브라우저에서 대화 저장")).not_to_be_checked()
        assert posts == []
        expect(page.get_by_label("확인할 원문", exact=True)).to_have_value(LONG_TEXT)
        dialog.get_by_role("button", name="동의하지 않음", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert posts == []
        send(LONG_TEXT)
        dialog.get_by_role("button", name="동의하고 시작", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(page.get_by_role("button", name="팩트 검증 시작", exact=True)).to_be_visible()
        assert [path for path, _ in posts] == ["/api/fact-check"]
        page.locator(".page-footer").get_by_role("button", name="대화 저장 설정", exact=True).click()
        storage_dialog = page.get_by_role("dialog", name="대화 저장 설정", exact=True)
        expect(storage_dialog.get_by_label("이 브라우저에서 대화 저장")).not_to_be_checked()
        storage_dialog.get_by_role("button", name="취소", exact=True).click()
        send("안녕하세요")
        expect(page.locator(".chat-thread")).to_contain_text("모의 응답입니다.")
        assert posts[-1][0] == "/api/intent"
        expect(dialog).not_to_be_visible()
        page.reload(wait_until="networkidle")
        send("새로고침 후 인사")
        expect(page.locator(".chat-thread")).to_contain_text("모의 응답입니다.")
        expect(dialog).not_to_be_visible()
        send("https://example.test/article 요약해줘")
        expect(page.locator(".chat-thread")).to_contain_text("모의 요약입니다.")
        assert posts[-1][0] == "/api/summarize"
        page.get_by_role("button", name="JEV 모드", exact=True).click()
        send(LONG_TEXT)
        expect(page.get_by_role("button", name="팩트 검증 시작", exact=True)).to_be_visible()
        assert posts[-1][0] == "/api/fact-check/jev"
        page.get_by_role("button", name="외부 전송 동의 철회", exact=True).click()
        before = len(posts)
        send("철회 후 인사")
        expect(dialog).to_be_visible()
        assert len(posts) == before
        dialog.get_by_role("button", name="동의하고 시작", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(page.locator(".chat-thread")).to_contain_text("모의 응답입니다.")
        other = context.new_page()
        other.goto(BASE, wait_until="networkidle")
        page.get_by_role("button", name="외부 전송 동의 철회", exact=True).click()
        other.get_by_label("확인할 원문", exact=True).fill("다른 탭에서 인사")
        other.get_by_role("button", name="팩트 검증 시작", exact=True).click()
        expect(other.get_by_role("dialog", name="외부 서비스 전송 동의", exact=True)).to_be_visible()
        other.close()
        page.get_by_role("button", name="외부 전송 안내", exact=True).click()
        dialog.get_by_role("button", name="동의하고 시작", exact=True).click()
        before = len(posts)
        # This same-page removal emits no storage event: a stale in-memory true is insufficient.
        page.evaluate("localStorage.removeItem('ton_external_consent')")
        send("동의 기록 삭제 후 인사")
        expect(dialog).to_be_visible()
        assert len(posts) == before
        dialog.get_by_role("button", name="동의하지 않음", exact=True).click()

        def grant():
            page.get_by_role("button", name="외부 전송 안내", exact=True).click()
            dialog.get_by_role("button", name="동의하고 시작", exact=True).click()

        held = []

        def hold(route):
            posts.append(("/api/intent", route.request.post_data_json))
            held.append(route)

        def wait_for_held():
            for _ in range(100):
                if held:
                    return
                page.wait_for_timeout(20)
            raise AssertionError("Intent request did not start")

        grant()
        page.route("**/api/intent", hold)
        send("1969년에 인류는 달에 갔나?")
        wait_for_held()
        before = len(posts)
        page.evaluate("localStorage.removeItem('ton_external_consent')")
        held.pop().fulfill(content_type="application/json", body=json.dumps({"action": "verify", "reply": None, "focus": ""}))
        expect(page.locator(".chat-loader-row")).not_to_be_visible()
        assert len(posts) == before, "Revocation without a storage event must block follow-up POST"
        expect(page.locator(".chat-thread")).not_to_contain_text("늦은 응답")
        page.unroute("**/api/intent", hold)

        for cross_tab in [False, True]:
            grant()
            actor = context.new_page() if cross_tab else page
            if cross_tab:
                actor.goto(BASE, wait_until="networkidle")
            page.route("**/api/intent", hold)
            send("취소할 의도 분석")
            wait_for_held()
            before = len(posts)
            cancelled_before = len(cancelled)
            actor.get_by_role("button", name="외부 전송 동의 철회", exact=True).click()
            expect(page.locator(".chat-loader-row")).not_to_be_visible()
            try:
                held.pop().fulfill(content_type="application/json", body=json.dumps({"action": "reply", "reply": "늦은 응답", "focus": None}))
            except Error:
                pass  # A cancelled browser interception cannot always be fulfilled.
            for _ in range(100):
                if len(cancelled) > cancelled_before:
                    break
                page.wait_for_timeout(20)
            assert len(cancelled) > cancelled_before, "Revocation must abort the pending browser request"
            assert len(posts) == before
            expect(page.locator(".chat-thread")).not_to_contain_text("늦은 응답")
            page.unroute("**/api/intent", hold)
            if cross_tab:
                actor.close()
        page.evaluate("localStorage.setItem('ton_external_consent', 'old-policy')")
        page.reload(wait_until="networkidle")
        send("정책 변경 후 인사")
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="동의하지 않음", exact=True).click()
        page.set_viewport_size({"width": 390, "height": 844})
        send("모바일 인사")
        expect(dialog).to_be_visible()
        assert dialog.evaluate("element => {const box = element.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth && element.scrollWidth <= element.clientWidth;}")
        dialog.get_by_role("button", name="동의하지 않음", exact=True).click()
        page.set_viewport_size({"width": 1400, "height": 1000})
        page.evaluate("() => {localStorage.setItem('ton_external_consent', '2026-10-05-v1'); localStorage.setItem('ton_storage_consent', '2026-10-05-v1');}")
        page.reload(wait_until="networkidle")
        before = len(posts)
        send("새 게이트웨이 안내 재확인")
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text("하이브")
        expect(dialog.get_by_label("이 브라우저에서 대화 저장")).to_be_checked()
        assert len(posts) == before
        dialog.get_by_role("button", name="동의하지 않음", exact=True).click()
        page.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('blocked', 'SecurityError');}})")
        page.reload(wait_until="networkidle")
        before = len(posts)
        send("저장 차단 환경의 최초 확인")
        expect(dialog).to_be_visible()
        assert len(posts) == before
        dialog.get_by_role("button", name="동의하고 시작", exact=True).click()
        expect(page.locator(".chat-thread")).to_contain_text("모의 응답입니다.")
        send("저장 차단 후 다음 질문")
        expect(dialog).not_to_be_visible()
        page.reload(wait_until="networkidle")
        send("저장 차단 후 새로고침")
        expect(dialog).to_be_visible()
        print({"browserPassed": True, "mockedPosts": len(posts), "realProviderCalls": 0,
               "checks": ["reject preserves input", "all four paths", "reload", "storage separate",
                          "revoke", "cross-tab revoke", "policy change", "mobile dialog", "blocked storage",
                          "stale memory", "follow-up consent check", "pending cancel", "late reply ignored",
                          "four models preserved", "gateway consent revision preserves storage choice"]})
    finally:
        context.close()
        browser.close()
