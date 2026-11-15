"""回归验证分页补采、条文清洗和修订冲突。"""

import json
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
from playwright.sync_api import sync_playwright

from collect import _attempt, _navigate, collect
from convert import clean_markdown, convert_batch
from ingest import upload
from storage import store_file, write_json


@contextmanager
def source_server():
    """通过真实浏览器访问受控栏目和详情页。"""
    detail = """
        <meta name="ArticleTitle" content="示例条例">
        <meta name="PubDate" content="2025-05-20 12:00">
        <div class="body"><p>（2025年5月10日公布 自2025年6月1日起施行）</p>
        <p>第一条　示例规则。</p></div>
        <a onclick="downloadFj('条例.docx','/rule.docx')">下载</a>
    """.encode()
    routes = {
        "/robots.txt": b"User-agent: *\nDisallow: /private\n",
        "/list": b'<article><a href="/law/1">one</a><a id="next" href="/page2">next</a></article>',
        "/page2": b'<article><a href="/law/1">duplicate</a><a href="/law/2">two</a></article>',
        "/law/1": detail,
        "/law/2": detail.replace(b"/rule.docx", b"/unavailable.docx"),
        "/rule.docx": b"PK\x03\x04dummy",
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            value = routes.get(self.path)
            self.send_response(200 if value is not None else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if value:
                self.wfile.write(value)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", routes
        finally:
            server.shutdown()
            thread.join()


class CorpusTests(unittest.TestCase):
    def test_browser_retries_transient_connection_reset(self):
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            page = browser.new_page()
            calls = []

            def respond(route):
                calls.append(route.request.url)
                if len(calls) == 1:
                    route.abort("connectionreset")
                else:
                    route.fulfill(status=200, body="recovered")

            page.route("https://example.test/source", respond)
            _attempt(2, 0, _navigate, page, "https://example.test/source")
            self.assertEqual(len(calls), 2)
            self.assertEqual(page.locator("body").inner_text(), "recovered")

    def test_multiple_pages_keep_stable_identity_and_retry_failed_detail(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            source_server() as (origin, routes),
            sync_playwright() as playwright,
            playwright.chromium.launch() as browser,
        ):
            root = Path(temp)
            source = {
                "namespace": "test",
                "list_url": origin + "/list",
                "links": "article a[href^='/law/']",
                "next": "#next",
                "body": ".body",
                "id_pattern": r"/law/(\d+)$",
                "doc_type": "regulation",
            }
            first = collect(browser, source, root, max_pages=2, max_items=10, delay=0, attempts=1)
            self.assertEqual(first["counts"], {"saved": 1, "skipped": 0, "failed": 1})
            records = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["records"]
            self.assertEqual(records["1"]["metadata"]["effective_date"], "2025-06-01")
            self.assertEqual(records["1"]["metadata"]["published_date"], "2025-05-10")
            self.assertIsNone(records["1"]["metadata"]["abolished_date"])
            self.assertEqual(records["1"]["attachments"][0]["format"], "docx")
            self.assertEqual(records["2"]["status"], "failed")
            self.assertTrue((root / records["2"]["body"]["path"]).is_file())
            self.assertIn("HTTP 404", records["2"]["error"])
            routes["/unavailable.docx"] = routes["/rule.docx"]
            retry = collect(browser, source, root, max_pages=2, max_items=10, delay=0, only_id="2")
            self.assertEqual(retry["counts"]["saved"], 1)
            rerun = collect(browser, source, root, max_pages=2, max_items=10, delay=0)
            self.assertEqual(rerun["counts"], {"saved": 0, "skipped": 2, "failed": 0})
            self.assertEqual({row["id"] for row in rerun["results"]}, {"1", "2"})

    def test_article_markers_and_tables_survive_markdown_cleanup(self):
        text = "## 第一章　总则\n\n**第一条**　应遵守规定。\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n- 1 -"
        self.assertEqual(
            clean_markdown(text),
            "## 第一章 总则\n\n### 第一条\n\n应遵守规定。\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
        )

    def test_empty_html_records_conversion_failure_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            html = b"<html><body><nav>navigation</nav></body></html>"
            asset = store_file(root, html, "html")
            write_json(
                root / "manifest.json",
                {"records": {"1": {"status": "saved", "body": asset, "attachments": []}}},
            )
            results = convert_batch(root, fmt="html", models=None)
            self.assertEqual(results[0]["status"], "failed")
            self.assertEqual((root / asset["path"]).read_bytes(), html)
            self.assertFalse((root / "markdown").exists())

    def test_import_reuses_document_and_stops_on_remote_edit(self):
        remote = {}
        methods = []
        conflict_next = False

        def respond(request):
            nonlocal conflict_next
            methods.append(request.method)
            if request.method == "POST":
                self.assertTrue(request.headers["Idempotency-Key"].startswith("legal-corpus-"))
                remote.update(json.loads(request.content), id="1234567890123456789", revision=1)
            if request.method == "PATCH":
                if conflict_next:
                    remote.update(title="人工编辑", revision=3)
                    return httpx.Response(409, json={"code": 40901, "message": "冲突"})
                body = json.loads(request.content)
                self.assertEqual(body.pop("revision"), remote["revision"])
                remote.update(body, revision=2)
            return httpx.Response(200, json={"code": 0, "data": remote})

        with (
            tempfile.TemporaryDirectory() as temp,
            httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond)) as client,
        ):
            state = Path(temp) / "state.json"
            payload = {"content": "第一条 规则", "title": "条例", "metadata": {"source_document_id": "1"}}
            self.assertEqual(
                upload(client, "/api/knowledge-bases/1/documents", state, "s:1", payload)[0], "created"
            )
            self.assertEqual(
                upload(client, "/api/knowledge-bases/1/documents", state, "s:1", payload)[0], "skipped"
            )
            payload = {**payload, "content": "第一条 新规则"}
            self.assertEqual(
                upload(client, "/api/knowledge-bases/1/documents", state, "s:1", payload)[0], "updated"
            )
            conflict_next = True
            with self.assertRaisesRegex(ValueError, "修订冲突"):
                upload(
                    client, "/api/knowledge-bases/1/documents", state, "s:1", {**payload, "title": "再次更新"}
                )
            self.assertEqual(remote["title"], "人工编辑")
            self.assertEqual(methods, ["POST", "GET", "GET", "PATCH", "GET", "PATCH", "GET"])
