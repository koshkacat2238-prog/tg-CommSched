import httpx

BASE_URL = "https://ruz.fa.ru/api"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_group_id_cache: dict[str, int] = {}


async def get_group_id(client: httpx.AsyncClient, group_name: str) -> int | None:
    if group_name in _group_id_cache:
        return _group_id_cache[group_name]

    url = f"{BASE_URL}/search"
    params = {"term": group_name, "type": "group"}
    response = await client.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data:
            for item in data:
                if str(item.get("label", "")).strip().lower() == group_name.strip().lower():
                    _group_id_cache[group_name] = item["id"]
                    return item["id"]
            _group_id_cache[group_name] = data[0]["id"]
            return data[0]["id"]
    return None


async def fetch_schedule_from_ruz(group_name: str, start_date: str, end_date: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
        group_id = await get_group_id(client, group_name)
        if not group_id:
            raise ValueError(f"Группа '{group_name}' не найдена на сайте.")

        url = f"{BASE_URL}/schedule/group/{group_id}"
        params = {"start": start_date, "finish": end_date, "lng": 1}

        response = await client.get(url, params=params)
        if response.status_code != 200:
            raise RuntimeError(f"Ошибка API: статус {response.status_code}")

        raw_data = response.json()
        return [
            {
                "date": item.get("date"),
                "time_start": item.get("beginLesson"),
                "time_end": item.get("endLesson"),
                "subject": item.get("discipline") or "",
                "type": item.get("kindOfWork") or "",
                "teacher": item.get("lecturer") or "",
                "room": item.get("auditorium") or "",
            }
            for item in raw_data
        ]