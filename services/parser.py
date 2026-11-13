import httpx

BASE_URL = "https://ruz.fa.ru/api"


async def get_group_id(group_name: str) -> int | None:
    url = f"{BASE_URL}/search"
    params = {"term": group_name, "type": "group"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0]["id"]
    return None


async def fetch_schedule_from_ruz(group_name: str, start_date: str, end_date: str) -> list[dict]:
    group_id = await get_group_id(group_name)
    if not group_id:
        raise Exception(f"Группа '{group_name}' не найдена на сайте.")

    url = f"{BASE_URL}/schedule/group/{group_id}"
    params = {"start": start_date, "finish": end_date, "lng": 1}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            raw_data = response.json()
            # Очищаем данные, оставляя только нужные поля
            clean_data = []
            for item in raw_data:
                clean_data.append({
                    "date": item.get("date"),
                    "time_start": item.get("beginLesson"),
                    "time_end": item.get("endLesson"),
                    "subject": item.get("discipline"),
                    "type": item.get("kindOfWork"),
                    "teacher": item.get("lecturer"),
                    "room": item.get("auditorium")
                })
            return clean_data
        else:
            raise Exception(f"Ошибка API: статус {response.status_code}")