# Changelog

## Unreleased

Безопасность (hardening):

- **Allowlist команд**: только точные имена `git`/`docker`/`docker-compose`;
  суффикс `.exe` допускается только на Windows. Ранее по совпадению stem
  пропускались `git.sh`, `git.com`, `docker-compose.sh` и т.п.
- **Поиск исполняемых файлов**: исключаются PATH-записи не только внутри
  `--project`, но и внутри текущей директории; результаты `shutil.which`
  дополнительно фильтруются по суффиксу (только `.exe`/без суффикса —
  PATHEXT мог вернуть `.com`/`.bat`).
- **Явный путь исполняемого файла**: проверка, что это обычный файл
  (symlink/директория отклоняются).
- **TOCTOU при чтении**: логи, `.env` и `.devreport.toml` открываются
  атомарно через `O_NOFOLLOW` (POSIX) + `fstat` — подмена файла symlink'ом
  между проверкой и открытием больше не работает.
- **Redaction**: расширен словарь ключей (`key`, `auth`, `session`, `cookie`,
  `pwd`, `passphrase`, `signature`, `csrf`, `jwt`, `phpsessid` и составные),
  составные ключи с любым числом сегментов (`X-Amz-Signature`,
  `AWS_ACCESS_KEY_ID`); маскируются `Authorization:`/`Proxy-Authorization:`
  любых схем, `Cookie:`/`Set-Cookie:`, PEM-блоки приватных ключей
  (включая обрезанный хвост без END), single-quoted JSON `'key': 'v'`,
  многословные значения `KEY=v` до конца строки; добавлены префиксы
  токенов (`sk-ant-`, `sk-proj-`, `AKIA`, `ASIA`, `AIza`, `ya29.`,
  `glpat-`, `xapp-`, `npm_`, `pypi-`, `dop_v1_`, `dapi`, `hf_`, `sbp_`,
  `shp*_`, `sq0*`, `SG.`).
- **`--log` на `.env*`**: значения всех ключей маскируются на границе
  рендера (`mask_dotenv_text`), независимо от имени ключа.
- **Markdown**: HTML-метасимволы и `[]`/`[` экранируются в полях из
  внешних источников (stdout команд, детали проверок).
- **CI**: триггер на все ветки (ранее push в `feature/*` не запускал CI);
  actions закреплены по SHA; диапазоны версий dev-зависимостей и
  `build`; добавлен Dependabot для pip и github-actions.
- Удалён мёртвый код (`_normalize_cmd_name`) и недостижимая ветка
  в `Report.to_dict`.

## 0.1.0

Первый MVP DevReport:

- CLI `devreport collect` (Typer + Rich);
- сбор ОС/Python, git/docker/compose, файлов проекта;
- сравнение ключей `.env` / `.env.example`;
- проверка TCP-порта на 127.0.0.1;
- явное добавление хвоста лога с redaction;
- Markdown и JSON отчёты;
- конфигурация `.devreport.toml`;
- тесты, Ruff, mypy, GitHub Actions (Windows/Linux).
