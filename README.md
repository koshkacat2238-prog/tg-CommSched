# tg-CommSched
source code for our reply to Chamberlen
schedule_bot/
├── bot.py                  🔒 я
├── config.py               🔒 я
├── database.py             🔒 я
├── middlewares.py          🔒 я
├── Dockerfile              🔒 я
├── docker-compose.yml      🔒 я
├── requirements.txt        🔒 я
│
├── services/               🔒 я (контракт, Дам Босс только читает)
│   ├── __init__.py
│   ├── users.py
│   ├── bans.py
│   ├── schedule.py
│   ├── homework.py
│   └── audit.py
│
├── handlers/               ⚠️ Дам Босс (по шаблону)
│   ├── __init__.py
│   ├── states.py           🔒 я (общий файл, не трогать)
│   ├── common.py           ⚠️ Дам Босс
│   ├── user.py             ⚠️ Дам Босс
│   ├── teacher.py          ⚠️ Дам Босс
│   └── admin.py            🔒 я (слишком опасно)
│
└── ui/                     ✅ Дам Босс (полная свобода)
    ├── __init__.py
    ├── texts.py            ✅ Дам Босс
    ├── formatters.py       ✅ Дам Босс
    ├── keyboards.py        ✅ Дам Босс
    └── emoji.py            ✅ Дам Босс (константы эмодзи)
