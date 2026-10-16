from pathlib import Path

from drfast.cli import startapp, startproject


def test_startproject_creates_runnable_layout(tmp_path: Path) -> None:
	startproject("demo", str(tmp_path))
	root = tmp_path / "demo"
	assert (root / "pyproject.toml").exists()
	assert (root / "demo" / "main.py").exists()
	assert (root / "demo" / "users" / "auth.py").exists()
	assert (root / "demo" / "apps" / "todo" / "views.py").exists()


def test_startapp_creates_conventional_modules(tmp_path: Path) -> None:
	startproject("demo", str(tmp_path))
	project = tmp_path / "demo"
	startapp("billing", str(project))
	root = project / "apps" / "billing"
	assert {path.name for path in root.iterdir()} == {
		"__init__.py",
		"models.py",
		"serializers.py",
		"views.py",
		"tests.py",
	}
	assert '"demo.apps.billing.models"' in (project / "demo" / "settings.py").read_text()

