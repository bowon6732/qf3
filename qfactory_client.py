import os
import pickle
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class DebugTrace:
    method: str = ""
    url: str = ""
    request_headers: Dict[str, Any] = None
    request_payload: Any = None
    status_code: int = 0
    response_headers: Dict[str, Any] = None
    response_text_head: str = ""


class QFactoryClient:
    ITEM_LIST_ENDPOINT = "/base/item/list"

    def __init__(self, base_url: str, cookie_path: str = "qf_cookies.pkl"):
        self.base_url = base_url.rstrip("/")
        self.sess = requests.Session()
        self.cookie_path = cookie_path
        self.last_trace: DebugTrace = DebugTrace(request_headers={}, response_headers={})

        origin = self.base_url.replace(":8000", "")
        self.default_headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin,
            "Referer": origin + "/",
        }

    def save_cookies(self) -> None:
        with open(self.cookie_path, "wb") as f:
            pickle.dump(self.sess.cookies, f)

    def load_cookies(self) -> bool:
        if not os.path.exists(self.cookie_path):
            return False
        try:
            with open(self.cookie_path, "rb") as f:
                self.sess.cookies = pickle.load(f)
            return True
        except Exception:
            return False

    def clear_cookies(self) -> None:
        self.sess.cookies.clear()
        if os.path.exists(self.cookie_path):
            os.remove(self.cookie_path)

    def _trace(self, method: str, url: str, headers: Dict[str, Any], payload: Any, resp: requests.Response):
        text = resp.text if resp.text else ""
        self.last_trace = DebugTrace(
            method=method,
            url=url,
            request_headers=dict(headers),
            request_payload=payload,
            status_code=resp.status_code,
            response_headers=dict(resp.headers),
            response_text_head=text[:2000],
        )

    def post_json(self, path: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 60) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        h = dict(self.default_headers)
        if headers:
            h.update(headers)

        resp = self.sess.post(url, headers=h, json=payload, timeout=timeout)
        self._trace("POST", url, h, payload, resp)
        resp.raise_for_status()
        return resp.json()

    def login(self, company_code: str, user_key: str, password: str, language_code: str = "KO") -> Dict[str, Any]:
        payload = {
            "companyCode": company_code,
            "userKey": user_key,
            "password": password,
            "languageCode": language_code,
        }
        return self.post_json("/common/login/post-login", payload)

    def list_items_page(
        self,
        *,
        language_code: str,
        company_id: int,
        status: str,
        item_plant: int,
        item_code: str,
        item_name: str,
        item_type: str,
        product_group: str,
        buy_make: str,
        control_lot: str,
        page: int,
        limit: int,
    ) -> Dict[str, Any]:
        start = (page - 1) * limit + 1
        payload = {
            "languageCode": language_code,
            "companyId": company_id,
            "status": status,
            "itemPlant": item_plant,
            "itemCode": item_code or "",
            "itemName": item_name or "",
            "itemType": item_type or "",
            "productGroup": product_group or "",
            "buyMake": buy_make or "",
            "controlLot": control_lot or "",
            "start": start,
            "page": page,
            "limit": limit,
        }
        return self.post_json(self.ITEM_LIST_ENDPOINT, payload)

    @staticmethod
    def extract_rows(resp_json: Any) -> List[Dict[str, Any]]:
        if resp_json is None:
            return []
        if isinstance(resp_json, list):
            return resp_json
        if not isinstance(resp_json, dict):
            return []

        for path in [
            ("data", "list"),
            ("data", "rows"),
            ("data", "items"),
            ("result", "list"),
            ("result", "rows"),
            ("list",),
            ("rows",),
            ("items",),
        ]:
            cur = resp_json
            ok = True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, list):
                return cur

        for v in resp_json.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v

        return []

    @staticmethod
    def extract_total(resp_json: Any) -> Optional[int]:
        if isinstance(resp_json, dict):
            for k in ["total", "count", "recordsTotal", "totalCount"]:
                v = resp_json.get(k)
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
            data = resp_json.get("data")
            if isinstance(data, dict):
                v = data.get("total")
                if isinstance(v, int):
                    return v
        return None

    def list_items_all(
        self,
        *,
        language_code: str,
        company_id: int,
        status: str,
        item_plant: int,
        item_code: str,
        item_name: str,
        item_type: str,
        product_group: str,
        buy_make: str,
        control_lot: str,
        limit: int = 500,
        max_pages: int = 9999,
        progress_cb=None,
    ) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        page = 1
        total = None

        while page <= max_pages:
            resp = self.list_items_page(
                language_code=language_code,
                company_id=company_id,
                status=status,
                item_plant=item_plant,
                item_code=item_code,
                item_name=item_name,
                item_type=item_type,
                product_group=product_group,
                buy_make=buy_make,
                control_lot=control_lot,
                page=page,
                limit=limit,
            )

            if total is None:
                total = self.extract_total(resp)

            rows = self.extract_rows(resp)
            all_rows.extend(rows)

            if progress_cb:
                progress_cb(page=page, got=len(rows), total=total, acc=len(all_rows))

            if total is not None and len(all_rows) >= total:
                break
            if len(rows) < limit:
                break

            page += 1

        return all_rows
