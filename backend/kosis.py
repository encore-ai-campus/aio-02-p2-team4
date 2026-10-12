"""KOSIS consumer price index adapter for nationwide monthly total-index data."""

import re
import unicodedata

import httpx


_BASE_URL = "https://kosis.kr/openapi"
_CPI_TABLE = "소비자물가지수(2020=100)"
_MAX_TABLE_CANDIDATES = 5


def _normalized(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def is_cpi_claim(claims: list[dict], focus: str = "") -> bool:
    target = _normalized(" ".join([
        focus,
        *(claim.get("statement") or claim.get("quote", "") for claim in claims),
    ]))
    return "소비자물가" in target or re.search(r"(?<![a-z])cpi(?![a-z])", target) is not None


async def _get_json(client: httpx.AsyncClient, path: str, params: dict) -> list[dict] | None:
    response = await client.get(f"{_BASE_URL}/{path}", params=params)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) and all(isinstance(row, dict) for row in payload) else None


async def fetch_nationwide_monthly_cpi(
    *, api_key: str, client: httpx.AsyncClient
) -> tuple[dict, str] | None:
    """Find the official CPI table and return its nationwide total-index series."""
    if not api_key.strip():
        return None

    search = await _get_json(client, "statisticsSearch.do", {
        "method": "getList", "apiKey": api_key, "searchNm": _CPI_TABLE,
        "orgId": "101", "sort": "DATE", "startCount": "1",
        "resultCount": "30", "format": "json",
    })
    if not search:
        return None

    table_candidates = [
        row for row in search
        if str(row.get("ORG_ID", "101")) == "101"
        and _normalized(row.get("TBL_NM") or row.get("LIST_NM")) == _normalized(_CPI_TABLE)
        and isinstance(row.get("TBL_ID"), str)
    ][: _MAX_TABLE_CANDIDATES]

    for table in table_candidates:
        table_id = table["TBL_ID"]
        metadata = await _get_json(client, "statisticsData.do", {
            "method": "getMeta", "type": "ITM", "apiKey": api_key,
            "orgId": "101", "tblId": table_id, "format": "json",
        })
        if not metadata:
            continue
        total_items = [
            row for row in metadata
            if isinstance(row.get("ITM_ID"), str)
            and "총지수" in _normalized(row.get("ITM_NM"))
        ]
        for item in total_items:
            rows = await _get_json(client, "Param/statisticsParameterData.do", {
                "method": "getList", "apiKey": api_key, "orgId": "101",
                "tblId": table_id, "objL1": "ALL", "itmId": item["ITM_ID"],
                "prdSe": "M", "newEstPrdCnt": "24", "format": "json",
            })
            if not rows:
                continue
            nationwide = [
                row for row in rows
                if any(_normalized(row.get(f"C{index}_NM")) == _normalized("전국")
                       for index in range(1, 9))
                or not any(f"C{index}_NM" in row for index in range(1, 9))
            ]
            nationwide = [
                row for row in nationwide
                if row.get("PRD_SE") == "M"
                and re.fullmatch(r"\d{6}", str(row.get("PRD_DE", "")))
                and re.fullmatch(r"-?\d+(?:\.\d+)?", str(row.get("DT", "")))
            ]
            if not nationwide:
                continue
            nationwide.sort(key=lambda row: row["PRD_DE"])
            latest = nationwide[-24:]
            title = str(latest[-1].get("TBL_NM") or table.get("TBL_NM") or _CPI_TABLE)
            unit = str(latest[-1].get("UNIT_NM") or "2020=100")
            item_name = str(latest[-1].get("ITM_NM") or item.get("ITM_NM") or "총지수")
            lines = [
                f"통계표: {title}",
                "작성기관: 국가데이터처, 소비자물가조사",
                f"항목: {item_name} (전국)",
                f"단위: {unit}",
            ]
            lines.extend(
                f"시점 {row['PRD_DE'][:4]}-{row['PRD_DE'][4:]} 소비자물가지수 {row['DT']} ({unit})"
                for row in latest
            )
            table_url = f"https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId={table_id}"
            return ({
                "url": table_url,
                "title": title,
                "publisher": "국가데이터처(KOSIS)",
                "sourceType": "공공 통계",
                "originGroupId": "kosis",
                "searchProvider": None,
                "searchQuery": "KOSIS 전국 월별 소비자물가지수 총지수",
                "candidateOrder": 1,
                "accessStatus": "pending",
                "inlineText": "\n".join(lines),
                "publishedAt": None,
            }, "\n".join(lines))
    return None
