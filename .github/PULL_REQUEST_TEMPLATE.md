## 📋 Summary
<!-- Brief description of the changes introduced by this PR -->

## 🧪 Quality & Testing Checklist
- [ ] `python3 -m py_compile custom_components/smart_zone_heating/*.py` passes
- [ ] `ruff check` passes with 0 warnings/errors
- [ ] Automated test suite (`docker compose -f .dev-tools/docker-compose.test.yml run --rm test-runner`) passes (`16/16`)
- [ ] Documentation (`README.md`, `docs/IT.md`, `docs/EN.md`, `CHANGELOG.md`) updated if applicable
