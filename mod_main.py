import os
import threading
import traceback
import urllib.parse

from flask import Response, jsonify, render_template, request, stream_with_context
from plugin import PluginModuleBase, default_route_socketio_module

from .logic_misskon import LogicMissKon


class ModuleMain(PluginModuleBase):
    template_prefix = "ff_misskon"

    def __init__(self, P):
        super(ModuleMain, self).__init__(P, name="main")
        self.db_default = {
            "misskon_url": LogicMissKon.BASE_URL,
            "proxy_url": "",
            "proxy_enabled": "True",
            "download_path": os.path.join(os.getcwd(), "downloads", "ff_misskon"),
        }
        self.menu = {
            "main": "최신",
            "top3": "인기 (3일)",
            "top7": "인기 (7일)",
            "top30": "인기 (30일)",
            "top60": "인기 (60일)",
            "search": "검색",
            "setting": "설정",
            "log": "로그",
        }
        self.download_status = {}
        default_route_socketio_module(self)

    def process_menu(self, sub, req):
        arg = self.P.ModelSetting.to_dict()
        arg["package_name"] = self.P.package_name
        menu_map = {
            "main": {"title": "최신", "category": ""},
            "top3": {"title": "인기 (3일)", "category": "top3"},
            "top7": {"title": "인기 (7일)", "category": "top7"},
            "top30": {"title": "인기 (30일)", "category": "top30"},
            "top60": {"title": "인기 (60일)", "category": "top60"},
            "search": {"title": "검색"},
            "setting": {"title": "설정"},
            "log": {"title": "로그"},
        }

        if sub in ["main", "top3", "top7", "top30", "top60"]:
            arg["title"] = menu_map[sub]["title"]
            arg["category"] = menu_map[sub]["category"]
            return render_template(f"{self.template_prefix}_main.html", arg=arg)
        if sub == "search":
            arg["title"] = "Search"
            arg["category"] = ""
            return render_template(f"{self.template_prefix}_search.html", arg=arg)
        if sub == "setting":
            arg["title"] = "Setting"
            return render_template(f"{self.template_prefix}_setting.html", arg=arg)
        if sub == "log":
            return render_template("log.html", package=self.P.package_name)
        return render_template("sample.html", title=f"MissKon - {sub}")

    def process_ajax(self, sub, req):
        try:
            if sub == "setting_save":
                ret = self.P.ModelSetting.setting_save(self._setting_request_with_defaults(req))
                return jsonify(ret)

            if sub == "discover_url":
                discovered_url = LogicMissKon.discover_url()
                self._set_setting("misskon_url", discovered_url)
                return jsonify({"ret": "success", "url": discovered_url})

            if sub == "list":
                page = int(req.form.get("page", 1))
                search = req.form.get("search", "")
                category = req.form.get("category", "")
                base_url = self._get_effective_base_url()
                data = LogicMissKon.get_list(
                    base_url=base_url, page=page, search=search, category=category
                )
                if self.P.ModelSetting.get_bool("proxy_enabled"):
                    for item in data:
                        if item.get("thumbnail"):
                            item["thumbnail"] = self._make_proxy_url(item["thumbnail"])
                return jsonify({"ret": "success", "data": data})

            if sub == "detail":
                url = req.form.get("url")
                data = LogicMissKon.get_detail(url)
                if data:
                    if self.P.ModelSetting.get_bool("proxy_enabled"):
                        data["proxy_images"] = [
                            self._make_proxy_url(img) for img in data["images"]
                        ]
                    return jsonify({"ret": "success", "data": data})
                return jsonify({"ret": "error", "log": "상세 정보를 가져올 수 없습니다."})

            if sub == "download":
                url = req.form.get("url")
                force = req.form.get("force") == "true"
                target_path = self.P.ModelSetting.get("download_path")

                if not force:
                    data = LogicMissKon.get_detail(url)
                    if data:
                        safe_title = self._safe_filename(data["title"])
                        zip_file_path = os.path.join(target_path, f"{safe_title}.zip")
                        if os.path.exists(zip_file_path):
                            return jsonify(
                                {"ret": "exists", "msg": "이미 다운로드된 파일이 있습니다. 다시 받으시겠습니까?"}
                            )

                if not os.path.exists(target_path):
                    os.makedirs(target_path)

                self.download_status[url] = {"current": 0, "total": 0, "status": "starting"}
                threading.Thread(
                    target=self.download_thread, args=(url, target_path), daemon=True
                ).start()
                return jsonify({"ret": "success", "msg": "다운로드를 시작합니다. 버튼에서 진행률을 확인하세요."})

            if sub == "download_status":
                url = req.form.get("url")
                return jsonify(self.download_status.get(url, {"status": "none"}))
        except Exception as e:
            self.P.logger.error(f"Exception:{str(e)}")
            self.P.logger.error(traceback.format_exc())
            return jsonify({"ret": "error", "log": str(e)})

    def download_thread(self, url, target_path):
        try:
            import shutil
            import zipfile
            from io import BytesIO

            try:
                from PIL import Image
            except Exception:
                Image = None

            self.P.logger.info(f"[MissKon] Download Task Started: {url}")
            data = LogicMissKon.get_detail(url)
            if not data:
                self.download_status[url] = {"status": "error", "msg": "상세 정보 로딩 실패"}
                return

            safe_title = self._safe_filename(data["title"])
            temp_folder = os.path.join(target_path, f"temp_{safe_title}")
            zip_file_path = os.path.join(target_path, f"{safe_title}.zip")

            if not os.path.exists(temp_folder):
                os.makedirs(temp_folder)

            session = LogicMissKon.get_session()
            total = len(data["images"])
            self.download_status[url] = {"current": 0, "total": total, "status": "downloading"}
            downloaded_files = []

            for idx, img_url in enumerate(data["images"]):
                try:
                    res = session.get(img_url, headers=LogicMissKon.HEADERS, timeout=30)
                    if res.status_code == 200:
                        file_path = os.path.join(temp_folder, f"{idx + 1:03d}.jpg")
                        if Image and not img_url.lower().endswith(".gif"):
                            img = Image.open(BytesIO(res.content))
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.save(file_path, "JPEG", quality=95, subsampling=0)
                        else:
                            with open(file_path, "wb") as f:
                                f.write(res.content)
                        downloaded_files.append(file_path)
                    self.download_status[url]["current"] = idx + 1
                except Exception:
                    pass

            if downloaded_files:
                self.download_status[url]["status"] = "zipping"
                with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in downloaded_files:
                        zipf.write(file_path, os.path.basename(file_path))
                shutil.rmtree(temp_folder)
                self.download_status[url]["status"] = "completed"
                self.P.logger.info(f"[MissKon] Download & Zip Completed: {zip_file_path}")
            else:
                self.download_status[url]["status"] = "error"
                if os.path.exists(temp_folder):
                    shutil.rmtree(temp_folder)
        except Exception as e:
            self.download_status[url] = {"status": "error", "msg": str(e)}
            self.P.logger.error(f"[MissKon] Download thread failed: {e}")
            self.P.logger.error(traceback.format_exc())

    def process_normal(self, sub, req):
        if sub == "proxy":
            return self._proxy(req)
        return "Not Found", 404

    def _make_proxy_url(self, target):
        return f"/{self.P.package_name}/normal/proxy?url={urllib.parse.quote(target)}"

    def _get_effective_base_url(self):
        base_url = self.P.ModelSetting.get("misskon_url") or LogicMissKon.BASE_URL
        if not LogicMissKon.is_supported_base_url(base_url):
            discovered_url = LogicMissKon.discover_url()
            self._set_setting("misskon_url", discovered_url)
            return discovered_url
        return base_url.rstrip("/")

    def _setting_request_with_defaults(self, req):
        if "proxy_enabled" in req.form:
            return req

        from werkzeug.datastructures import MultiDict

        class RequestProxy:
            def __init__(self, original, form):
                self._original = original
                self.form = form

            def __getattr__(self, name):
                return getattr(self._original, name)

        form = MultiDict(req.form)
        form["proxy_enabled"] = "False"
        return RequestProxy(req, form)

    def _set_setting(self, key, value):
        if hasattr(self.P.ModelSetting, "set"):
            return self.P.ModelSetting.set(key, value)

        from werkzeug.datastructures import MultiDict

        class SettingRequest:
            method = "POST"

            def __init__(self, form):
                self.form = form

        form = MultiDict(self.P.ModelSetting.to_dict())
        form[key] = value
        return self.P.ModelSetting.setting_save(SettingRequest(form))

    def _proxy(self, req):
        target_url = req.args.get("url")
        if not target_url:
            return "No URL", 400
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": self.P.ModelSetting.get("misskon_url") or LogicMissKon.BASE_URL,
        }

        try:
            session = LogicMissKon.get_session()
            res = session.get(target_url, headers=headers, stream=True, timeout=10)
            if not res or res.status_code >= 400:
                return "Target Error", res.status_code if res else 500

            def generate():
                try:
                    for chunk in res.iter_content(chunk_size=1024 * 64):
                        yield chunk
                finally:
                    res.close()

            response = Response(
                stream_with_context(generate()),
                status=res.status_code,
                content_type=res.headers.get("Content-Type"),
            )
            response.headers["Cache-Control"] = "public, max-age=604800"
            return response
        except Exception as e:
            self.P.logger.error(f"[MissKon] Image Proxy Exception: {e} ({target_url})")
            return str(e), 500

    def _safe_filename(self, name):
        return "".join(c for c in name if c.isalnum() or c in (" ", ".", "_", "-")).strip()

    def plugin_load(self):
        pass

    def plugin_unload(self):
        pass
