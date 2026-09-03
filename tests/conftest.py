# -*- coding: utf-8 -*-
"""共享测试夹具：本机回环启动真实 Web 服务。"""
import threading
from http.server import ThreadingHTTPServer

import pytest

from yuanjisong.webapp import DataStore, ScrapeManager, make_handler


@pytest.fixture(scope="session")
def server():
    store = DataStore()
    scraper = ScrapeManager(store)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, scraper))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
