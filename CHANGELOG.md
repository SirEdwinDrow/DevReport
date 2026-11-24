# Changelog

## Unreleased

Безопасность (selective hardening, на базе идей closed PR #1):

- **Allowlist команд**: только точные имена `git`/`docker`/`docker-compose`;
  суффикс `.exe` допускается только на Windows. Ранее по совпадению stem
  пропускались `git.sh`, `git.com`, `docker-compose.sh` и т.п.
- **Поиск исполняемых файлов**: исключаются PATH-записи внутри `--project` и
  cwd; результаты `shutil.which` фильтруются по суффиксу (только `.exe`/без
  суффикса); **symlink-executable отклоняется** (обычный файл обязателен).
- **Явный путь исполняемого файла**: проверка, что это обычный файл
  (symlink/директория отклоняются).
- **TOCTOU при чтении**: логи, `.env` и `.devreport.toml` открываются
  атомарно через `O_NOFOLLOW` (POSIX) + `fstat`; на Windows — pre/post
  `is_symlink` best-effort без прав администратора.
- **Redaction (смягчённый словарь)**: passphrase/pwd/credentials/access_key/
  private_key/csrf/jwt/bearer + составные любой глубины; Authorization/
  Proxy-Authorization любых схем, Cookie/Set-Cookie, PEM private key,
  single-quoted JSON, расширенные префиксы токенов (AKIA/ASIA, sk-ant-,
  sk-proj-, glpat-, AIza, hf_, npm_, pypi-, …). Голые `key`/`session`/
  `signature`/`pass`/`cookie` **не** добавлены (меньше false positives).
  EOL-маскирование значений — только для secret-like ключей и dotenv-границы.
- **`--log` на `.env*`**: значения всех ключей маскируются на границе
  рендера (`mask_dotenv_text`); задокументировано в limitations/SECURITY.
- **Markdown**: HTML-метасимволы и `[]` экранируются во внешних полях.
- **CI**: push на все ветки; actions закреплены по SHA; верхние границы
  dev-deps; Dependabot (pip + github-actions).
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
