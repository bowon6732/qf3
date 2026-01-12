# qf3_api.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import requests


@dataclass
class QF3Config:
    base_url: str = "https://qf3.qfactory.biz:8000"
    language_code: str = "KO"
    company_id: int = 100
    plant_id: int = 11


class QF3Client:
    def __init__(self, config: QF3Config):
        self.config = config
        self.sess = requests.Session()
        self.sess.headers.update({
            "Accept": "*/*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://qf3.qfactory.biz",
            "Referer": "https://qf3.qfactory.biz/",
        })

    # ---------- Auth ----------
    def login(self, company_code: str, user_key: str, password: str) -> Dict[str, Any]:
        url = f"{self.config.base_url}/common/login/post-login"
        payload = {
            "companyCode": company_code,
            "userKey": user_key,
            "password": password,
            "languageCode": self.config.language_code,
        }
        r = self.sess.post(url, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"Login failed: {data}")
        return data

    # ---------- QCM ----------
    def head_list(
        self,
        inspection_date_from: str,
        inspection_date_to: str,
        item_code: str = "",
        item_name: str = "",
        job_name: str = "",
        operation_code: str = "",
        person_id: int = 0,
        check_class: str = "OPR",
        page: int = 1,
        limit: int = 20,
        start: int = 1,
    ) -> Dict[str, Any]:
        url = f"{self.config.base_url}/qcm/operation_inspection-view/head-list"
        payload = {
            "companyId": self.config.company_id,
            "plantId": self.config.plant_id,
            "inspectionDateFrom": inspection_date_from,
            "inspectionDateTo": inspection_date_to,
            "itemCode": item_code,
            "itemName": item_name,
            "jobName": job_name,
            "operationCode": operation_code,
            "personId": person_id,
            "checkClass": check_class,
            "languageCode": self.config.language_code,
            "start": start,
            "page": page,
            "limit": str(limit),
        }
        r = self.sess.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def line_list(
        self,
        mfg_inspection_id: int,
        page: int = 1,
        limit: int = 200,
        node: str = "root",
    ) -> Dict[str, Any]:
        url = f"{self.config.base_url}/qcm/operation_inspection-view/line-list"
        payload = {
            "languageCode": self.config.language_code,
            "companyId": self.config.company_id,
            "plantId": self.config.plant_id,
            "mfgInspectionId": int(mfg_inspection_id),
            "start": 1,
            "page": page,
            "limit": str(limit),
            "node": node,
        }
        r = self.sess.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    # ---------- MFG ----------
    def joborder_list(
        self,
        released_date_from: str,
        released_date_to: str,
        item_code: str = "",
        item_name: str = "",
        job_name: str = "",
        workcenter_code: str = "",
        worker_result: str = "Y",
        page: int = 1,
        limit: int = 200,
        start: int = 1,
    ) -> Dict[str, Any]:
        url = f"{self.config.base_url}/mfg/job_order_sum_view/joborder-list"
        payload = {
            "languageCode": self.config.language_code,
            "companyId": self.config.company_id,
            "plantId": self.config.plant_id,
            "releasedDateFrom": released_date_from,
            "releasedDateTo": released_date_to,
            "itemCode": item_code,
            "itemName": item_name,
            "jobName": job_name,
            "jobComent": "",
            "workcenterCode": workcenter_code,
            "workerResult": worker_result,
            "status": {
                "CANCEL": False,
                "CLOSE": True,
                "COMPLETE": True,
                "EXECUTE": True,
                "HOLDING": True,
                "RELEASED": False,
                "UNRELEASE": False,
            },
            "start": start,
            "page": page,
            "limit": str(limit),
        }
        r = self.sess.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    # ---------- Helpers ----------
    @staticmethod
    def _extract_list(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
        return (resp or {}).get("data", {}).get("list", []) or []

    @staticmethod
    def _extract_total(resp: Dict[str, Any]) -> int:
        lst = (resp or {}).get("data", {}).get("list", []) or []
        if not lst:
            return 0
        return int(lst[0].get("cnt", len(lst)) or len(lst))

    def build_job_equipment_map(
        self,
        released_date_from: str,
        released_date_to: str,
        limit: int = 500,
        max_pages: int = 999,
    ) -> Dict[str, Dict[str, Any]]:
        mp: Dict[str, Dict[str, Any]] = {}
        page = 1
        while page <= max_pages:
            resp = self.joborder_list(
                released_date_from=released_date_from,
                released_date_to=released_date_to,
                page=page,
                limit=limit,
                start=1,
            )
            rows = self._extract_list(resp)
            if not rows:
                break

            for r in rows:
                jn = r.get("jobName")
                if not jn:
                    continue
                mp[jn] = {
                    "workcenterName": r.get("workcenterName"),
                    "machineName": r.get("machineName"),
                    "resourceName": r.get("resourceName"),
                }

            total = self._extract_total(resp)
            if len(mp) >= total:
                break
            page += 1
        return mp

    def fetch_all_heads(
        self,
        inspection_date_from: str,
        inspection_date_to: str,
        item_code: str = "",
        item_name: str = "",
        job_name: str = "",
        operation_code: str = "",
        person_id: int = 0,
        check_class: str = "OPR",
        limit: int = 500,
        max_pages: int = 999,
    ) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            resp = self.head_list(
                inspection_date_from=inspection_date_from,
                inspection_date_to=inspection_date_to,
                item_code=item_code,
                item_name=item_name,
                job_name=job_name,
                operation_code=operation_code,
                person_id=person_id,
                check_class=check_class,
                page=page,
                limit=limit,
                start=1,
            )
            rows = self._extract_list(resp)
            if not rows:
                break
            all_rows.extend(rows)

            total = self._extract_total(resp)
            if len(all_rows) >= total:
                break
            page += 1
        return all_rows

    @staticmethod
    def attach_equipment_to_heads(
        heads: List[Dict[str, Any]],
        job_mp: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for h in heads:
            h2 = dict(h)
            jn = h2.get("jobName")
            eq = job_mp.get(jn, {}) if jn else {}

            h2["workcenterName"] = eq.get("workcenterName")
            h2["machineName"] = eq.get("machineName")
            h2["resourceName"] = eq.get("resourceName")

            wc = h2.get("workcenterName") or ""
            mc = h2.get("machineName") or ""
            rs = h2.get("resourceName") or ""
            h2["equipmentDisplay"] = " / ".join([x for x in [wc, mc, rs] if x])

            out.append(h2)
        return out
