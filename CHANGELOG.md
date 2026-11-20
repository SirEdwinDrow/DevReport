# Changelog

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
