## Django django-project parser template
### Why tho?
This template contains generic code for all parsers. Models, settings, posting function, management commands

### Installation
`django-admin startproject --template=https://github.com/WinterCitizen/parser-template/archive/master.zip parser-name`

`pip install -r requirements.pip`


### Settings you might need to change
`LANGUAGE_ID = 1`

`CELERY_BROKER_URL = 'redis://localhost:6379'`

`TIME_ZONE = 'UTC'`
