from pathlib import Path
import importlib.util
import tempfile
import unittest
import sys

import web_media as m

TEMPLATE = """### 默认章节

图片测试
---
{{IMG_001}}

===

音频测试
---
{{AUD_001}}
"""

EXPORT = """牌组名称：probe

牌组简介：

### 默认章节

IMG_001
---

[Pic#ID/abcAz#]

===

AUD_001
---

[Audio#ID/defZz#]

===
"""
SOURCE = "https://www.markji.com/deck/editor/mock-source"
TARGET = "https://www.markji.com/deck/editor/mock-target"
LIBRARY = """<a href="/setting" aria-label="打开账号管理">账号</a>
<p>长按拖动可调整排序及分组</p>
<button onclick="document.querySelector('[role=menuitem]').hidden=false">+ 新建牌组</button>
<button role=menuitem hidden onclick="document.querySelector('input').click()">导入 Anki 牌组</button>
<input type=file hidden onchange="document.querySelector('#row').hidden=false">
<a id=row hidden href='""" + SOURCE + """' target=_blank>probe</a>"""
SOURCE_PAGE = """<header><h1>probe</h1><button class=icondeck_more onclick="out.hidden=false">…</button></header>
<button id=out hidden onclick="txt.hidden=false">导出牌组</button>
<button id=txt hidden onclick="dlg.showModal()">TXT</button>
<dialog id=dlg>导出 TXT
<label><input type=radio checked>整个牌组</label>
<label><input type=radio checked>保留语法</label>
<button onclick="location.href='/mock-export'">导出</button></dialog>"""
DEST_PAGE = """<h1>target</h1><button onclick="mode.hidden=false">批量制卡</button>
<button id=mode hidden onclick="pane.hidden=false">从文本导入</button>
<section id=pane hidden>
<label><input type=radio checked>###</label>
<label><input type=radio checked>===</label>
<label><input type=radio checked>---</label>
<div class=ql-editor contenteditable=true oninput="result.textContent='2 张卡片'; go.disabled=false"></div>
<span id=result>0 张卡片</span><button id=go disabled onclick="document.body.dataset.committed='yes'">导入</button></section>"""


class ProbeTests(unittest.TestCase):
    def test_reference_mapping_and_boundaries(self):
        refs = m.media_refs(EXPORT)
        self.assertEqual(refs, {"IMG_001": "[Pic#ID/abcAz#]", "AUD_001": "[Audio#ID/defZz#]"})
        template = TEMPLATE
        payload, count = m.preview_text(m.fill_refs(template, refs) + "\n===\n")
        self.assertEqual(count, 2)
        self.assertFalse(payload.endswith("==="))
        self.assertEqual(payload.splitlines().count("==="), 1)
        self.assertEqual(m.preview_text(EXPORT)[1], 2)
        for bad in ("x {{IMG_001}}", "{{IMG_MISSING}}"):
            with self.assertRaises(ValueError):
                m.fill_refs(bad, refs)
        with self.assertRaises(ValueError):
            m.media_refs(EXPORT.replace("[Pic#", "[Audio#"))
        with self.assertRaises(ValueError):
            m.web_url("https://www.markji.com.evil.invalid/deck/editor/a", editor=True)

    @unittest.skipUnless(importlib.util.find_spec("playwright"), "optional Playwright not installed")
    def test_browser_workflow_without_real_site(self):
        from playwright.sync_api import Error, sync_playwright

        with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome")
            except Error as exc:
                if "not found" in str(exc).lower():
                    self.skipTest("optional Chrome channel not installed")
                raise
            ctx = browser.new_context(accept_downloads=True)
            ctx.set_default_timeout(8000)
            def route(r):
                if r.request.url == "https://www.markji.com/mock-export":
                    return r.fulfill(status=200, content_type="text/plain; charset=utf-8",
                                     headers={"Content-Disposition": "attachment; filename=probe.txt"},
                                     body=EXPORT)
                return r.fulfill(status=200, content_type="text/html; charset=utf-8",
                    body={m.HOME_URL: LIBRARY, SOURCE: SOURCE_PAGE, TARGET: DEST_PAGE}.get(r.request.url, ""))
            ctx.route("**/*", route)
            lib = m.library(ctx, m.HOME_URL)
            dest = m.open_editor(ctx, TARGET, "target")
            package = Path(temp) / "probe.apkg"
            package.touch()
            source = m.upload_apkg(lib, package, 3000)
            with self.assertRaises(ValueError):
                m.upload_apkg(lib, package, 3000)
            saved = Path(temp) / "raw.txt"
            m.export_txt(source, saved)
            template = TEMPLATE
            payload, count = m.preview_text(m.fill_refs(template, m.media_refs(m.read_txt(saved))))
            m.import_preview(dest, payload, count)
            self.assertIn("[Audio#ID/defZz#]", dest.locator(".ql-editor").inner_text())
            self.assertIsNone(dest.locator("body").get_attribute("data-committed"))
            browser.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
