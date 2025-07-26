# 🤝 Contributing Guidelines for HR & Payroll Management System

We warmly welcome contributions to the HR & Payroll Management System! Please follow these guidelines to ensure smooth, consistent, and high-quality collaboration.

## 🚀 Getting Started

- Fork the repository and clone it to your local machine.
- Install dependencies using Poetry and Docker.
- Run the test suite:
    ```
    docker compose exec django pytest
    ```
- Run pre-commit hooks:
    ```
    pre-commit run --all-files
    ```

## 🌱 Branching Strategy

Use the following branch naming conventions:

- `feature/<your-feature>` – for new features
- `bugfix/<your-fix>` – for bug fixes
- `docs/<section>` – for documentation updates
- `chore/<task>` – for internal tooling/maintenance

**💡 Example:** `feature/payroll-tax-engine`

## 📥 Making a Pull Request (PR)

- Ensure your branch is up to date with `main`.
- Write a clear PR title and a detailed description.
- Reference related issues using: `Closes #<issue_number>`
- Apply relevant labels and assign reviewers.
- Your PR must pass:
    - ✅ Continuous Integration (CI)
    - ✅ Pre-commit checks
    - ✅ Code review

## 🧪 Testing & Coverage

- All new code must be tested using `pytest`, `coverage`, and `factory_boy`.
- Run tests:
    ```
    docker compose exec django coverage run -m pytest
    docker compose exec django coverage report
    ```
- ✅ Aim for high test coverage and test edge cases.

## 📄 Documentation Requirements

- Add docstrings to all models, views, and serializers.
- Update Sphinx documentation in the `docs/` folder.
- Link new modules in `.rst` files.
- Preview documentation locally:
    ```
    docker compose -f docker-compose.docs.yml up
    ```

**📚 Docs will be available at [http://localhost:9000](http://localhost:9000).**

## 🎯 Before You Commit

Run the following command:
```
pre-commit run --all-files
```

This ensures your code passes:

- `black` – Code formatter
- `ruff` – Linter
- `isort` – Import sorter
- `trailing-whitespace`, `end-of-file-fixer`, and other checks

🧼 Always commit clean and consistent code.

## 🧱 Respect Project Architecture

- Follow Cookiecutter Django best practices.
- Keep each app modular and domain-specific.
- Avoid tight coupling between unrelated components.
- Reuse logic through utility functions, mixins, and base classes.
- ⚠️ Avoid adding unrelated logic to shared apps or config folders.

---

❤️ **Thanks for Contributing!**
We value your time and effort. If you’re stuck or have questions, open a GitHub Discussion or ask in the Issues section.
🤝 Let’s build this project together, the right way!
