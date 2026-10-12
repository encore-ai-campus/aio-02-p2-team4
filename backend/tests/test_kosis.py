import httpx

from kosis import fetch_nationwide_monthly_cpi, is_cpi_claim


def test_cpi_claim_detection_is_limited_to_cpi_mentions():
    assert is_cpi_claim([{"quote": "소비자물가가 전월보다 올랐다"}])
    assert is_cpi_claim([{"statement": "CPI increased"}])
    assert not is_cpi_claim([{"quote": "실업률이 올랐다"}])


async def test_fetch_nationwide_total_index_filters_out_regional_rows():
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("statisticsSearch.do"):
            payload = [{"ORG_ID": "101", "TBL_ID": "DT_1J22003", "TBL_NM": "소비자물가지수(2020=100)"}]
        elif request.url.params.get("type") == "ITM":
            payload = [{"ITM_ID": "T", "ITM_NM": "소비자물가지수(총지수)"}]
        else:
            payload = [
                {"PRD_DE": "202609", "PRD_SE": "M", "DT": "120.01", "C1_NM": "서울특별시"},
                {"PRD_DE": "202609", "PRD_SE": "M", "DT": "119.88", "C1_NM": "전국", "TBL_NM": "소비자물가지수(2020=100)", "ITM_NM": "소비자물가지수(총지수)", "UNIT_NM": "2020=100"},
            ]
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_nationwide_monthly_cpi(api_key="server-secret", client=client)

    assert result is not None
    source, text = result
    assert "시점 2026-09 소비자물가지수 119.88 (2020=100)" in text
    assert "120.01" not in text
    assert source["url"].endswith("tblId=DT_1J22003")
    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "statisticsSearch.do", "statisticsData.do", "statisticsParameterData.do",
    ]
