schedule_bot/
├── bot.py                  я
├── config.py               я
├── database.py             я
├── middlewares.py          я
├── Dockerfile              Я
├── docker-compose.yml      я
├── requirements.txt        я
│
├── services/               я(Dam Boss read-only)
│   ├── __init__.py
│   ├── users.py
│   ├── bans.py
│   ├── schedule.py
│   ├── homework.py
│   └── audit.py
│
├── handlers/               Dam Boss
│   ├── __init__.py
│   ├── states.py           я (общий файл, не трогать)
│   ├── common.py           Dam Boss
│   ├── user.py             Dam Boss
│   ├── teacher.py          Dam Boss
│   └── admin.py            я (слишком опасно)
│
└── ui/                     Dam Boss (полная свобода)
    ├── __init__.py
    ├── texts.py            
    ├── formatters.py       
    ├── keyboards.py        
    └── emoji.py            (константы эмодзи)
