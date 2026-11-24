"""Markji's visible web workflow. No API keys or private endpoints."""

import argparse
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


HOME_URL = "https://www.markji.com/decks"
BUILTIN = re.compile(r"^(?P<kind>IMG|AUD)_[A-Za-z0-9_-]+$")
SLOT = re.compile(r"\{\{((?:IMG|AUD)_[A-Za-z0-9_-]+)\}\}")
TAG = re.compile(r"\[(Pic|Audio)#([^#\r\n]+)#[^\]\r\n]*\]")
DEFAULT_PROFILE = (Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
                        or (Path.home() / ".local" / "share"))
                   / "Memo-TXT" / "MarkjiBrowserProfile")


def web_url(url, editor=False):
    p = urlparse(url)
    path_ok = (re.fullmatch(r"/deck/editor/[A-Za-z0-9_-]+", p.path) if editor
               else p.path.rstrip("/") == "/decks")
    if p.scheme != "https" or p.netloc != "www.markji.com" or not path_ok or p.fragment:
        raise ValueError(f"请使用墨墨官网的{'具体牌组编辑' if editor else '我的牌库'}地址。")
    return url


def read_txt(path):
    return Path(path).read_text(encoding="utf-8-sig")


def new_text(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(text)


def card_blocks(text):
    return re.split(r"(?m)^[ \t]*===[ \t]*$", text)


def media_refs(export):
    refs = {}
    for block in card_blocks(export):
        lines = [x.strip() for x in block.splitlines()
                 if x.strip() and not x.startswith(("牌组名称：", "牌组简介：", "###"))]
        if not lines or not BUILTIN.fullmatch(lines[0]):
            continue
        marker = lines[0]
        tags = list(TAG.finditer(block))
        if marker in refs or len(tags) != 1:
            raise ValueError(f"{marker} 重复，或没有恰好一个媒体标签。")
        tag = tags[0]
        expected = "Pic" if marker.startswith("IMG_") else "Audio"
        ids = re.findall(r"(?:^|,)ID/([^,\s#\[\]]+)(?=,|$)", tag[2])
        if tag[1] != expected or len(ids) != 1:
            raise ValueError(f"{marker} 的媒体类别或 ID 不符合预期。")
        refs[marker] = tag[0]
    if not refs:
        raise ValueError("没有找到 IMG_ / AUD_ 中转卡和原生媒体标签。")
    return refs


def preview_text(text):
    # Header metadata is for the file, not card content. Trailing === is an
    # export convention and has appeared as visible content on TXT import.
    text = re.sub(r"\A(?:牌组(?:名称|简介)：[^\n]*\n(?:[ \t]*\n)*)+", "", text)
    text = re.sub(r"(?m)^###[ \t]*([^\n]+)$", r"### \1", text)
    text = re.sub(r"(?:\n[ \t]*===[ \t]*)\s*\Z", "", text).strip()
    blocks = card_blocks(text)
    values = [re.sub(r"(?m)^###[ \t]*[^\n]+\n?", "", b).strip() for b in blocks]
    if not text or any(not x for x in values):
        raise ValueError("有空卡片，检查章节和分卡符。")
    return text, len(values)


def fill_refs(template, refs):
    markers = SLOT.findall(template)
    if not markers:
        raise ValueError("模板未包含 {{IMG_...}} 或 {{AUD_...}}。")
    missing = sorted(set(markers) - refs.keys())
    if missing:
        raise ValueError("缺少媒体标签：" + ", ".join(missing))
    for marker in set(markers):
        if marker.startswith("IMG_"):
            slot = "{{" + marker + "}}"
            if any(slot in line and line != slot for line in template.splitlines()):
                raise ValueError(f"{slot} 必须从行首独占一行。")
    result = SLOT.sub(lambda m: refs[m[1]], template)
    if re.search(r"\{\{(?:IMG|AUD)_", result):
        raise ValueError("存在未识别的媒体占位符。")
    return result


def check_apkg(path):
    path = path.resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".apkg" or path.stat().st_size >= 80_000_000:
        raise ValueError(f"{path.name} 必须是小于 80 MB 的 APKG。")
    return path


def open_editor(ctx, url, expected=None):
    page = ctx.new_page()
    page.goto(web_url(url, editor=True), wait_until="domcontentloaded")
    heading = page.get_by_role("heading", level=1, name=expected, exact=True) if expected else page.get_by_role("heading", level=1)
    heading.wait_for()
    return page


def library(ctx, url):
    page = ctx.new_page()
    page.goto(web_url(url), wait_until="domcontentloaded")
    account = page.get_by_role("link", name="打开账号管理")
    if not account.is_visible():
        print("如网页尚未登录，请在 Playwright 打开的 Chrome 窗口手动登录。", flush=True)
    account.wait_for(timeout=120_000)
    page.get_by_role("button", name="+ 新建牌组", exact=True).wait_for()
    return page


def library_row(page, name):
    return page.locator("a:visible").and_(page.get_by_text(name, exact=True))


def open_named_editor(library_page, name, timeout=15_000):
    row = library_row(library_page, name)
    row.wait_for(timeout=timeout)
    with library_page.context.expect_page(timeout=15_000) as popup:
        row.click()
    page = popup.value
    page.get_by_role("heading", level=1, name=name, exact=True).wait_for()
    web_url(page.url, editor=True)
    return page


def upload_apkg(page, path, timeout):
    # Use the real visible file chooser. Selecting a file can start import.
    row = library_row(page, path.stem)
    ready = page.get_by_text("长按拖动可调整排序及分组", exact=True)
    ready.wait_for()
    if row.count():
        raise ValueError(f"当前列表已存在 {path.stem}；为防重复，不上传。可改用 --source-url。")
    page.get_by_role("button", name="+ 新建牌组", exact=True).click()
    with page.expect_file_chooser() as picker:
        page.get_by_role("menuitem", name=re.compile("导入 Anki 牌组")).click()
    try:
        picker.value.set_files(str(path))
        return open_named_editor(page, path.stem, timeout)
    except Exception as exc:
        raise RuntimeError(f"{path.name} 已选中，但未确认中转牌组。请先查牌库，不要直接重传。") from exc


def export_txt(page, path, selected_range=None):
    page.locator("header .icondeck_more").click()
    page.get_by_text("导出牌组", exact=True).click()
    page.get_by_text("TXT", exact=True).click()
    dialog = page.get_by_role("dialog").filter(has_text="导出 TXT")
    for name in (("范围" if selected_range else "整个牌组"), "保留语法"):
        radio = dialog.get_by_role("radio", name=name, exact=True)
        if not radio.is_checked():
            dialog.get_by_text(name, exact=True).click()
    if selected_range:
        dialog.get_by_placeholder("如 1,3,5-12").fill(selected_range)
    with page.expect_download() as pending:
        dialog.get_by_role("button", name="导出", exact=True).click()
    download = pending.value
    if not download.suggested_filename.lower().endswith(".txt"):
        raise RuntimeError("官网没有返回 TXT，停止。")
    download.save_as(str(path))


def import_preview(page, text, count):
    from playwright.sync_api import expect

    page.get_by_role("button", name=re.compile("批量制卡")).click()
    page.get_by_text("从文本导入", exact=True).click()
    for marker in ("###", "===", "---"):
        radio = page.get_by_role("radio", name=marker, exact=True)
        if not radio.is_checked():
            radio.check()
    page.locator('.ql-editor[contenteditable="true"]:visible').fill(text)
    expect(page.get_by_text(re.compile(rf"^\s*{count}\s*张卡片\s*$"))).to_be_visible(timeout=20_000)
    expect(page.get_by_role("button", name="导入", exact=True)).to_be_enabled(timeout=60_000)


def submit_titles(text):
    titles = []
    for block in card_blocks(text):
        lines = [line.strip() for line in block.splitlines()
                 if line.strip() and not line.startswith("###")]
        title = lines[0] if lines else ""
        if not title or re.search(r"[\[\]{}]", title):
            raise ValueError("自动提交要求每张卡的第一行是可核对的纯文本题面。")
        titles.append(title)
    if len(titles) != len(set(titles)):
        raise ValueError("自动提交要求本批题面唯一。")
    return titles


def count_pattern(count=None):
    wanted = r"[0-9][0-9,]*" if count is None else f"(?:{count}|{count:,})"
    return re.compile(rf"^\s*卡片数[：:]\s*({wanted})(?![0-9,])")


def title_match(page, title):
    return page.locator("main p:visible").and_(page.get_by_text(title, exact=True))


def submit_baseline(page, titles):
    counter = page.locator("header").get_by_text(count_pattern())
    counter.wait_for()
    before = int(count_pattern().search(counter.inner_text())[1].replace(",", ""))
    if any(title_match(page, title).count() for title in titles):
        raise ValueError("目标页面已发现相同的测试题面；未提交，避免重复。")
    return before


def verify_submitted(ctx, url, name, before, titles, record,
                     *, verify_range=None, verify_path=None, payload=None):
    check = open_editor(ctx, url, name)
    expected = before + len(titles)
    counter = check.locator("header").get_by_text(count_pattern(expected))
    counter.wait_for(timeout=25_000)
    record(f"独立重新打开后，牌组卡数 {before} → {expected}。")
    if verify_range:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=verify_path.parent) as folder:
            raw = Path(folder) / "verification.txt"
            export_txt(check, raw, selected_range=verify_range)
            result = read_txt(raw)
            normalized, n = preview_text(result)
            if (n != len(titles) or submit_titles(normalized) != titles
                    or [m[0] for m in TAG.finditer(normalized)] != [m[0] for m in TAG.finditer(payload)]):
                raise ValueError("独立导出的题面或媒体标签与提交文本不一致。")
            new_text(verify_path, result)
        record(f"已从第 {verify_range} 张回读核对题面与完整媒体标签。")
    else:
        for title in titles:
            title_match(check, title).first.wait_for(timeout=8_000)
            record(f"已回读卡片：{title}")
    return check


def parse():
    parser = argparse.ArgumentParser(description="墨墨 APKG / TXT 官网自动化；默认只预览。")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("login", help="打开独立 Chrome 配置，手动登录一次")
    run = commands.add_parser("run", help="上传或复用中转牌组 → 导出 → 回填 → 网页预览")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--apkg", action="append", type=Path, help="实际上传，可重复传入")
    source.add_argument("--source-url", action="append", help="复用已经导入的中转牌组，可重复传入")
    source.add_argument("--source-name", action="append", help="从当前牌库列表按准确名称查找中转牌组")
    source.add_argument("--exported-txt", action="append", type=Path, help="复用已经下载的含语法 TXT")
    run.add_argument("--library-url", default=HOME_URL, help="默认我的牌库；也可指定官网文件夹地址")
    run.add_argument("--template", type=Path, required=True)
    run.add_argument("--target-url", help="目标牌组编辑器完整 URL；不填则按名称从当前列表查找")
    run.add_argument("--target-name", required=True, help="目标牌组准确名称，用于防错")
    run.add_argument("--run-dir", type=Path, required=True, help="新建的结果目录，不能已存在")
    run.add_argument("--upload-timeout", type=int, default=300, help="每包处理等待秒数")
    run.add_argument("--commit", action="store_true", help="预览核对后真的提交一次，并独立回读")
    run.add_argument("--verify-range", help="已知新增卡的全牌组序号时，用 N-M 范围导出做独立回读")
    return parser.parse_args()


def main():
    args = parse()
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("此路线需要当前 Python 环境的 Playwright，以及本机 Chrome。离线 TXT 命令不需要。") from exc
    if args.action == "run":
        if args.target_url:
            web_url(args.target_url, editor=True)
        web_url(args.library_url)
        template = read_txt(args.template)
        range_match = re.fullmatch(r"([1-9][0-9]*)(?:-([1-9][0-9]*))?", args.verify_range or "")
        if args.verify_range and (not args.commit or not range_match):
            raise ValueError("--verify-range 必须与 --commit 一起使用，且格式为 N 或 N-M。")
        files = [check_apkg(p) for p in args.apkg or []]
        if len({p.stem.casefold() for p in files}) != len(files):
            raise ValueError("APKG 文件名（不含后缀）不可重复。")
        target_path = urlparse(args.target_url).path if args.target_url else None
        if args.target_name in (args.source_name or []):
            raise ValueError("中转牌组与目标牌组不能同名。")
        for url in args.source_url or []:
            if urlparse(web_url(url, editor=True)).path == target_path:
                raise ValueError("中转牌组与目标牌组不能相同。")
        if args.upload_timeout <= 0 or not SLOT.search(template):
            raise ValueError("超时秒数须为正，且模板须含媒体占位符。")
        args.run_dir.mkdir(parents=True, exist_ok=False)
        proof = args.run_dir / "run.log"
        def record(event):
            print(event, flush=True)
            with proof.open("a", encoding="utf-8") as f:
                f.write(event + "\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(args.profile), channel="chrome",
                                                  headless=False, accept_downloads=True)
        ctx.set_default_timeout(15_000)
        try:
            if args.action == "login":
                library(ctx, HOME_URL)
                input("检测到墨墨牌库登录。按 Enter 关闭浏览器并保留此登录状态。")
                return
            lib = library(ctx, args.library_url)
            dest = (open_editor(ctx, args.target_url, args.target_name) if args.target_url
                    else open_named_editor(lib, args.target_name))
            target_path = urlparse(dest.url).path
            record(f"已确认目标牌组 {args.target_name}：{dest.url}")
            refs = {}
            n = len(files or args.source_url or args.source_name or args.exported_txt)
            for i in range(n):
                dest_file = args.run_dir / f"export-{i+1:03}.txt"
                if args.exported_txt:
                    new_text(dest_file, read_txt(args.exported_txt[i]))
                else:
                    if files:
                        record(f"准备上传 {files[i].name}；中断后先检查官网，勿盲目重试。")
                        source = upload_apkg(lib, files[i], args.upload_timeout * 1000)
                    elif args.source_name:
                        source = open_named_editor(lib, args.source_name[i])
                    else:
                        source = open_editor(ctx, args.source_url[i])
                    if urlparse(source.url).path == target_path:
                        raise ValueError("中转与目标牌组指向同一编辑页。")
                    record(f"已确认中转牌组 {source.url}")
                    export_txt(source, dest_file)
                batch = media_refs(read_txt(dest_file))
                duplicate = refs.keys() & batch.keys()
                if duplicate:
                    raise ValueError("不同中转包出现重复编号：" + ", ".join(sorted(duplicate)))
                refs.update(batch)
                record(f"{dest_file.name}：读取 {len(batch)} 个原生标签")
            output = fill_refs(template, refs)
            payload, expected = preview_text(output)
            new_text(args.run_dir / "filled.txt", payload + "\n")
            if args.commit:
                titles = submit_titles(payload)
                before = submit_baseline(dest, titles)
                if range_match:
                    lower = int(range_match[1])
                    upper = int(range_match[2] or range_match[1])
                    if upper - lower + 1 != expected or upper > before + expected:
                        raise ValueError("回读范围须对应本批卡数，且不得超出预计总卡数。")
            dest.bring_to_front()
            import_preview(dest, payload, expected)
            if args.commit:
                record(f"提交前已确认目标为 {args.target_name}（现有 {before} 张），预览 {expected} 张；仅提交一次。")
                try:
                    dest.get_by_role("button", name="导入", exact=True).click()
                    dest.get_by_text("取消导入", exact=True).wait_for(state="hidden", timeout=25_000)
                    verify_submitted(ctx, dest.url, args.target_name, before, titles, record,
                                     verify_range=args.verify_range,
                                     verify_path=args.run_dir / "verified-cards.txt", payload=payload)
                except Exception as exc:
                    record("提交或回读未完全确认。不要重跑；先在目标牌组检查是否已产生卡片。")
                    raise RuntimeError("提交或回读结果不完整；未重试。") from exc
                record(f"已回读确认本次导入 {expected} 张卡。")
            else:
                record(f"网页预览确认 {expected} 张卡；脚本未点击最终导入。")
                input("如确认无误，请在网页点「导入」；操作完毕或要放弃后，按 Enter 关闭。")
        finally:
            ctx.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"停止：{str(error).splitlines()[0] if str(error) else type(error).__name__}", file=sys.stderr)
        sys.exit(1)
