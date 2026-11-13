import asyncio
from services.parser import fetch_schedule_from_ruz


async def main():
    print("Загружаем расписание для МЭиТ26-8...")
    try:
        # Даты берем текущие для теста
        data = await fetch_schedule_from_ruz("МЭиТ26-8", "2026.11.13", "2026.11.19")

        for les in data:
            print(
                f"{les['date']} | {les['time_start']}-{les['time_end']} | {les['subject']} | {les['room']} | {les['teacher']}")

    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())