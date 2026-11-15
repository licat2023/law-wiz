"""用 Playwright 遍历公开栏目，在允许的站点内保存正文和附件。"""

import re
import time
from contextlib import suppress
from datetime import date
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from playwright.sync_api import TimeoutError as BrowserTimeout

from storage import read_json, store_file, write_json

USER_AGENT = "LawWizCorpus/1.0"
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
ATTACHMENTS = {".pdf": "pdf", ".docx": "docx"}
DATE = r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2})"
ATTACHMENT_LINK = re.compile(r"""downloadFj\(\s*['"][^'"]*['"]\s*,\s*['"]([^'"]+)['"]""")


def _date_metadata(body, page_date):
    front = re.split(r"(?m)^\s*第\s*(?:一|1)\s*条", body, maxsplit=1)[0][:2200]
    patterns = {
        "published_date": (front, DATE + r"(?:(?!\d{4}\s*年|\d{4}-)[^，。；\n]){0,45}(?:公布|发布)"),
        "effective_date": (front, r"自\s*" + DATE + r"\s*(?:起)?\s*(?:施行|实施|生效)"),
        "abolished_date": (
            body,
            r"本(?:条例|规定|办法|规则|决定)\s*自\s*" + DATE + r"\s*(?:起)?\s*(?:废止|失效)",
        ),
    }
    values = {}
    original = {"site_published_date": page_date}
    for field, (text, pattern) in patterns.items():
        matches = re.findall(pattern, text)
        if field == "effective_date" and not matches:
            matches = re.findall(r"本(?:条例|规定|办法|规则|决定)\s*" + pattern, body)
        raw = matches[-1] if matches else None
        original[field] = raw
        values[field] = None
        if raw:
            with suppress(ValueError):
                values[field] = date(*(int(value) for value in re.findall(r"\d+", raw))).isoformat()
    return values | {"source_dates": original}


def _source_url(base, value):
    result = urlsplit(urljoin(base, value))
    origin = urlsplit(base)
    if (result.scheme, result.netloc) != (origin.scheme, origin.netloc):
        raise ValueError("链接指向来源站点之外")
    if result.username or result.password or result.scheme not in ("http", "https"):
        raise ValueError("来源 URL 必须是普通 HTTP(S) 链接")
    return urlunsplit(result._replace(fragment=""))


class TemporarySourceError(Exception):
    """可在有限次数内重试的远端故障。"""


def _check_status(status):
    if status in (408, 429) or 500 <= status <= 599:
        raise TemporarySourceError(f"HTTP {status}")
    if not 200 <= status < 300:
        raise ValueError(f"HTTP {status}")


def _attempt(attempts, delay, action, *args):
    for number in range(attempts):
        time.sleep(delay if number == 0 else max(delay, 1) * 2 ** (number - 1))
        try:
            return action(*args)
        except BrowserTimeout, TemporarySourceError, httpx.TransportError:
            if number + 1 == attempts:
                raise


def _robots(client, entry):
    robots_url = urljoin(entry, "/robots.txt")
    response = client.get(robots_url)
    parser = RobotFileParser(robots_url)
    if response.status_code not in (404, 410):
        _check_status(response.status_code)
        parser.parse(response.text.splitlines())
    else:
        parser.parse([])
    return parser


def _require_allowed(robots, url):
    if not robots.can_fetch(USER_AGENT, url):
        raise ValueError("robots.txt 拒绝访问")


def _download(client, url):
    with client.stream("GET", url) as response:
        _check_status(response.status_code)
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_ATTACHMENT_BYTES:
                raise ValueError("附件超过 20 MiB 上限")
        return bytes(body)


def _navigate(page, url):
    response = page.goto(url, wait_until="domcontentloaded")
    if response is None:
        raise ValueError("页面没有 HTTP 响应")
    _check_status(response.status)


def _discover(page, sources, max_pages, max_items, run):
    candidates = {}
    for source in sources:
        current = source["list_url"]
        visited = set()
        while current and current not in visited and len(visited) < max_pages:
            visited.add(current)
            run(_navigate, page, current)
            links = page.locator(source["links"])
            links.first.wait_for(state="attached")
            for link in links.all():
                href = link.get_attribute("href")
                if not href:
                    continue
                try:
                    url = _source_url(current, href)
                except ValueError:
                    continue
                match = re.search(source["id_pattern"], urlsplit(url).path)
                if match:
                    candidates.setdefault(
                        match[1], {"id": match[1], "source_url": url, "doc_type": source["doc_type"]}
                    )
            link = page.locator(source["next"]).first
            href = link.get_attribute("href") if link.count() else None
            current = _source_url(current, href) if href else None
    return list(candidates.values())[:max_items]


def _detail(page, client, robots, source, item, root, run):
    url = item["source_url"]
    run(_navigate, page, url)
    box = page.locator(source["body"]).first
    body = box.inner_text().strip()
    if not body:
        raise ValueError("详情页缺少正文")
    title = page.locator('meta[name="ArticleTitle" i]').first
    title = title.get_attribute("content") if title.count() else page.title()
    if not title or not title.strip():
        raise ValueError("详情页缺少标题")
    published = page.locator('meta[name="PubDate" i]').first
    page_date = published.get_attribute("content") if published.count() else None
    fragment = box.evaluate("""element => {
        const copy = element.cloneNode(true);
        copy.querySelectorAll('script, style, header, footer, nav, iframe, object, img')
            .forEach(child => child.remove());
        return copy.outerHTML;
    }""")
    html = '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><body>' + fragment + "</body></html>"
    metadata = {
        "source_namespace": source["namespace"],
        "source_document_id": item["id"],
        "source_url": url,
        "law_name": title.strip(),
        "document_profile": "legal_article",
        "doc_type": item["doc_type"],
    } | _date_metadata(body, page_date)
    record = item | {
        "title": title.strip(),
        "metadata": metadata,
        "body": store_file(root, html.encode(), "html"),
        "attachments": [],
        "status": "saved",
    }
    attachments = {}
    for link in page.locator("a[href], a[onclick]").all():
        onclick = link.get_attribute("onclick") or ""
        match = ATTACHMENT_LINK.search(onclick)
        href = match[1] if match else link.get_attribute("href")
        if not href or (format_suffix := urlsplit(href).path.lower().rsplit(".", 1)[-1]) not in (
            "pdf",
            "docx",
        ):
            continue
        try:
            asset_url = _source_url(url, href)
        except ValueError:
            continue
        fmt = ATTACHMENTS["." + format_suffix]
        attachments.setdefault(asset_url, (fmt, link.inner_text().strip()))
    for asset_url, (fmt, label) in attachments.items():
        try:
            _require_allowed(robots, asset_url)
            content = run(_download, client, asset_url)
            expected = b"%PDF-" if fmt == "pdf" else b"PK\x03\x04"
            if not content.startswith(expected):
                raise ValueError(f"下载内容不是有效的 {fmt} 文件")
            record["attachments"].append({"url": asset_url, "label": label} | store_file(root, content, fmt))
        except (ValueError, TemporarySourceError, httpx.TransportError) as exc:
            return record | {"status": "failed", "error": f"附件 {asset_url}，{exc}"}
    return record


def collect(browser, source, root, *, max_pages, max_items, delay=1, attempts=3, only_id=None, refresh=False):
    """保存同源清单和本次结果。已成功的原件默认复用，待补采项可按 ID 重试。"""
    if not 1 <= max_pages <= 10 or not 1 <= max_items <= 100 or not 1 <= attempts <= 3 or delay < 0:
        raise ValueError("采集上限无效")
    path = root / "manifest.json"
    manifest = read_json(path, {"namespace": source["namespace"], "records": {}})
    if manifest["namespace"] != source["namespace"]:
        raise ValueError("输出目录已经用于另一来源")
    records = manifest["records"]
    results, responses = [], []
    counts = dict.fromkeys(("saved", "skipped", "failed"), 0)
    sections = [source | section for section in source.get("sections", [{}])]
    entry = sections[0]["list_url"]
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=False) as client:
        robots = _attempt(attempts, delay, _robots, client, entry)
        pause = max(delay, robots.crawl_delay(USER_AGENT) or 0)

        def run(action, *args):
            return _attempt(attempts, pause, action, *args)

        context = browser.new_context(user_agent=USER_AGENT)
        try:
            page = context.new_page()
            page.set_default_timeout(15_000)

            def route_request(route):
                try:
                    _require_allowed(robots, _source_url(entry, route.request.url))
                except ValueError:
                    route.abort()
                    return
                if route.request.resource_type in {"document", "script", "xhr", "fetch"}:
                    route.continue_()
                else:
                    route.abort()

            def observe(response):
                if response.request.resource_type in {"document", "xhr", "fetch"}:
                    responses.append({"url": response.url, "status": response.status})

            context.route("**/*", route_request)
            page.on("response", observe)
            if only_id:
                if only_id not in records:
                    raise ValueError("待补采来源 ID 不在已有清单中")
                candidates = [{key: records[only_id][key] for key in ("id", "source_url", "doc_type")}]
            else:
                candidates = _discover(page, sections, max_pages, max_items, run)
            for item in candidates:
                previous = records.get(item["id"], {})
                expected = (
                    [previous["body"], *previous["attachments"]] if previous.get("status") == "saved" else []
                )
                if not refresh and expected and all((root / asset["path"]).is_file() for asset in expected):
                    status = "skipped"
                    result = item | {"status": status}
                else:
                    try:
                        result = _detail(page, client, robots, source, item, root, run)
                    except (ValueError, BrowserTimeout, TemporarySourceError, httpx.TransportError) as exc:
                        result = item | {"status": "failed", "error": str(exc)}
                    status = result["status"]
                    records[item["id"]] = result
                    write_json(path, manifest)
                results.append(result)
                counts[status] += 1
        finally:
            context.close()
    report = {"counts": counts, "results": results, "responses": responses}
    write_json(root / "collection-run.json", report)
    return report
