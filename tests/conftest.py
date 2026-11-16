"""Isolamento obrigatório da suíte de testes (Fase 0, T01).

Este arquivo é carregado pelo pytest antes de qualquer módulo de teste e,
portanto, antes de ``app``, ``database`` e ``services.*``. Ele garante que
nenhum teste consiga ler ou alterar os dados reais do operador.

Camadas de proteção, na ordem em que são aplicadas:

1. Captura dos locais reais de dados (``%LOCALAPPDATA%\\CheckFiscal``,
   ``checkfiscal_data/`` do Docker, banco legado, ``exports/``) e snapshot
   desses arquivos antes de qualquer outra ação.
2. Diretório temporário exclusivo da sessão, configurado por variável de
   ambiente antes dos imports: ``services.runtime_paths`` resolve todos os
   caminhos a partir dele. Não depende de ``monkeypatch`` aplicado depois.
3. Audit hook (``sys.addaudithook``): bloqueia, antes da chamada ao sistema
   operacional, qualquer abertura de arquivo, conexão SQLite, listagem,
   cópia, renomeação ou remoção dentro dos locais reais. Também bloqueia
   rede externa e criação de subprocessos sem marcação explícita.
4. Verificação preventiva dos caminhos resolvidos: a sessão é abortada se
   algum caminho de persistência apontar para fora do diretório temporário.
5. Banco temporário recriado a cada teste, para que o resultado não dependa
   da ordem de execução.
6. Ao final, comparação do snapshot e falha da sessão se algum acesso aos
   dados reais tiver sido tentado.

Exceções de rede ou subprocesso exigem marcação com justificativa:
``@pytest.mark.allow_network(reason="...")`` (apenas loopback é liberado
por padrão) e ``@pytest.mark.allow_subprocess(reason="...")``.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import gc
import hashlib
import ipaddress
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from urllib.parse import unquote, urlsplit

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

APPLICATION_MODULES = (
    "app",
    "database",
    "services.runtime_paths",
    "services.backup_service",
    "services.support_bundle",
    "services.file_storage",
    "services.app_logging",
)

# Se algum módulo da aplicação já foi importado, os caminhos foram
# resolvidos antes deste isolamento e podem apontar para dados reais.
_already_loaded = [name for name in APPLICATION_MODULES if name in sys.modules]
if _already_loaded:
    pytest.exit(
        "Isolamento abortado: módulos da aplicação carregados antes do "
        f"conftest ({', '.join(_already_loaded)}).",
        returncode=3,
    )


def _normalize(value: object) -> str | None:
    if isinstance(value, int) or value is None:
        return None
    try:
        if isinstance(value, bytes):
            value = os.fsdecode(value)
        text = os.fspath(value)
    except TypeError:
        return None
    if not text or text == ":memory:" or text.startswith("file::memory:"):
        return None
    if text.startswith("file:"):
        # URI do SQLite (file:C:\x.db?mode=ro, file:///C:/x.db): extrai o caminho.
        parsed = urlsplit(text)
        if "mode=memory" in parsed.query:
            return None
        text = unquote(parsed.netloc + parsed.path)
        if len(text) > 2 and text[0] == "/" and text[2] == ":":
            text = text[1:]
        if not text:
            return None
    return os.path.normcase(os.path.abspath(text))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _primary_checkout() -> Path | None:
    """Checkout principal quando REPO_ROOT é um worktree git.

    O Docker monta o checkout principal; sem isso, ``checkfiscal_data/`` real
    sairia da lista protegida ao rodar a suíte de dentro de um worktree. Lê o
    arquivo ``.git`` (``gitdir: <principal>/.git/worktrees/<nome>``), sem subprocesso.
    """
    marker = REPO_ROOT / ".git"
    if not marker.is_file():
        return None
    text = marker.read_text(encoding="utf-8", errors="replace")
    if "gitdir:" not in text:
        return None
    gitdir = Path(text.split("gitdir:", 1)[1].strip())
    for parent in gitdir.parents:
        if parent.name == ".git":
            return parent.parent
    return None


def _real_data_roots() -> list[str]:
    """Todos os locais onde o CheckFiscal guarda dados reais."""
    candidates: list[object] = [
        REPO_ROOT / "checkfiscal_data",
        REPO_ROOT / "checkfiscal_local.db",
        REPO_ROOT / "exports",
        Path.home() / ".checkfiscal",
    ]
    primary = _primary_checkout()
    if primary is not None and primary.resolve() != REPO_ROOT:
        candidates += [
            primary / "checkfiscal_data",
            primary / "checkfiscal_local.db",
            primary / "exports",
        ]
    # Caminhos absolutos extras (ex.: backups frios), separados por os.pathsep.
    for extra in os.environ.get("CHECKFISCAL_PROTECTED_ROOTS", "").split(os.pathsep):
        if extra.strip():
            candidates.append(Path(extra.strip()))
    for variable in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "CheckFiscal")
    # Configuração explícita do operador, se existir neste ambiente.
    for variable in ("CHECKFISCAL_DATA_DIR", "CHECKFISCAL_DB_PATH"):
        configured = os.environ.get(variable)
        if configured:
            candidates.append(Path(configured).expanduser())
    roots = {_normalize(candidate) for candidate in candidates}
    return sorted(root for root in roots if root)


PROTECTED_ROOTS = _real_data_roots()


def _snapshot(roots: list[str]) -> dict[str, dict[str, object]]:
    """Fotografia de tamanho, data e hash dos arquivos reais (somente leitura)."""
    result: dict[str, dict[str, object]] = {}
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for file in files:
            stat = file.stat()
            entry: dict[str, object] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            if stat.st_size <= 50 * 1024 * 1024:
                entry["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            result[str(file)] = entry
    return result


# 1. Snapshot antes de instalar o bloqueio (é a única leitura permitida).
SNAPSHOT_BEFORE = _snapshot(PROTECTED_ROOTS)

# 2. Diretório exclusivo da sessão, fora de qualquer local real.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="checkfiscal-test-")).resolve()
TEST_DATA_DIR = TEST_ROOT / "data"
TEST_DB_PATH = TEST_DATA_DIR / "checkfiscal.db"
_test_root_normalized = _normalize(TEST_ROOT)
for _root in PROTECTED_ROOTS:
    if _inside(_test_root_normalized, _root) or _inside(_root, _test_root_normalized):
        pytest.exit(
            f"Isolamento abortado: diretório de teste {TEST_ROOT} sobrepõe {_root}.",
            returncode=3,
        )

os.environ["CHECKFISCAL_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["CHECKFISCAL_DB_PATH"] = str(TEST_DB_PATH)
# Fallbacks de runtime_paths e de subprocessos também caem no diretório de teste.
os.environ["LOCALAPPDATA"] = str(TEST_ROOT / "localappdata")
os.environ["APPDATA"] = str(TEST_ROOT / "appdata")

# 3. Audit hook: bloqueio antes do acesso.
_FILE_EVENTS = {
    "open",
    "sqlite3.connect",
    "os.listdir",
    "os.scandir",
    "os.remove",
    "os.rename",
    "os.rmdir",
    "os.mkdir",
    "os.chmod",
    "os.utime",
    "os.truncate",
    "os.link",
    "os.symlink",
    "shutil.copyfile",
    "shutil.copymode",
    "shutil.copystat",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
    "shutil.make_archive",
    "shutil.unpack_archive",
    "glob.glob",
    "glob.glob/2",
}
_PROCESS_EVENTS = {
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.startfile",
}
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", ""}

_state = {
    "network_allowed": False,
    "subprocess_allowed": False,
    "expected_probe": False,
    "bypass": False,
}
VIOLATIONS: list[dict[str, str]] = []
PROBES_BLOCKED: list[dict[str, str]] = []
NETWORK_BLOCKED: list[dict[str, str]] = []
PROCESSES_BLOCKED: list[dict[str, str]] = []


def _current_test() -> str:
    return os.environ.get("PYTEST_CURRENT_TEST", "(fora de teste)")


def _is_loopback(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    text = str(host).strip("[]").split("%")[0]
    if text.lower() in _LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _audit(event: str, args: tuple) -> None:
    if _state["bypass"]:
        return

    if event in _FILE_EVENTS:
        for argument in args:
            path = _normalize(argument) if isinstance(argument, (str, bytes, os.PathLike)) else None
            if path and any(_inside(path, root) for root in PROTECTED_ROOTS):
                record = {"event": event, "path": path, "test": _current_test()}
                if _state["expected_probe"]:
                    PROBES_BLOCKED.append(record)
                else:
                    VIOLATIONS.append(record)
                raise PermissionError(
                    f"[isolamento de testes] acesso bloqueado a dado real: {event} {path}"
                )
        return

    if event == "socket.getaddrinfo" and not _state["network_allowed"]:
        host = args[0] if args else None
        if not _is_loopback(host):
            NETWORK_BLOCKED.append({"event": event, "target": str(host), "test": _current_test()})
            raise OSError(f"[isolamento de testes] rede externa bloqueada: {host}")
        return

    if event == "socket.connect" and not _state["network_allowed"]:
        address = args[1] if len(args) > 1 else None
        host = address[0] if isinstance(address, tuple) and address else None
        if isinstance(address, tuple) and not _is_loopback(host):
            NETWORK_BLOCKED.append({"event": event, "target": str(address), "test": _current_test()})
            raise OSError(f"[isolamento de testes] rede externa bloqueada: {address}")
        return

    if event in _PROCESS_EVENTS and not _state["subprocess_allowed"]:
        PROCESSES_BLOCKED.append({"event": event, "target": repr(args[:2]), "test": _current_test()})
        raise PermissionError(
            f"[isolamento de testes] subprocesso bloqueado ({event}); "
            "use @pytest.mark.allow_subprocess(reason=...)"
        )


sys.addaudithook(_audit)


@contextmanager
def _bypass_audit():
    """Uso exclusivo deste conftest para o snapshot final (somente leitura)."""
    _state["bypass"] = True
    try:
        yield
    finally:
        _state["bypass"] = False


# 4. Verificação preventiva dos caminhos, antes de qualquer teste importar
# ``database`` (cujo import executa ``init_db()``).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import services.runtime_paths as runtime_paths  # noqa: E402  (precisa vir após o ambiente)


def persistence_paths() -> dict[str, Path]:
    """Todos os caminhos de persistência resolvidos pelos módulos carregados."""
    paths: dict[str, Path] = {
        "runtime_paths.DATA_DIR": runtime_paths.DATA_DIR,
        "runtime_paths.DB_PATH": runtime_paths.DB_PATH,
        "runtime_paths.DOCUMENTS_DIR": runtime_paths.DOCUMENTS_DIR,
        "runtime_paths.BACKUPS_DIR": runtime_paths.BACKUPS_DIR,
        "runtime_paths.LOGS_DIR": runtime_paths.LOGS_DIR,
        "runtime_paths.SUPPORT_DIR": runtime_paths.SUPPORT_DIR,
    }
    module_attributes = {
        "database": ("DB_PATH",),
        "services.backup_service": ("DB_PATH", "DOCUMENTS_DIR", "BACKUPS_DIR"),
        "services.support_bundle": ("DB_PATH", "SUPPORT_DIR", "LOG_PATH"),
        "services.file_storage": ("DOCUMENTS_DIR",),
        "services.app_logging": ("LOG_PATH",),
        "app": ("DATA_DIR", "DOCUMENTS_DIR"),
    }
    for module_name, attributes in module_attributes.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attribute in attributes:
            if hasattr(module, attribute):
                paths[f"{module_name}.{attribute}"] = Path(getattr(module, attribute))
    return paths


def assert_isolated(paths: dict[str, Path]) -> list[str]:
    problems = []
    for label, path in paths.items():
        normalized = _normalize(path)
        if not normalized or not _inside(normalized, _test_root_normalized):
            problems.append(f"{label} = {path}")
    return problems


_problems = assert_isolated(persistence_paths())
if _problems:
    pytest.exit(
        "Isolamento abortado: caminhos de persistência fora do ambiente de teste: "
        + "; ".join(_problems),
        returncode=3,
    )


# 5. Integração com o pytest.

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "allow_network(reason): libera rede externa para um teste de integração justificado.",
    )
    config.addinivalue_line(
        "markers",
        "allow_subprocess(reason): libera criação de subprocesso para um teste justificado.",
    )


def _marker_reason(item: pytest.Item, name: str) -> str | None:
    marker = item.get_closest_marker(name)
    if marker is None:
        return None
    reason = marker.kwargs.get("reason") or (marker.args[0] if marker.args else "")
    if not str(reason).strip():
        pytest.fail(f"@pytest.mark.{name} exige reason= com a justificativa.")
    return str(reason)


@pytest.fixture(autouse=True)
def _isolation_policy(request: pytest.FixtureRequest):
    """Aplica as exceções marcadas e recria o banco temporário a cada teste."""
    _state["network_allowed"] = _marker_reason(request.node, "allow_network") is not None
    _state["subprocess_allowed"] = _marker_reason(request.node, "allow_subprocess") is not None

    # Os caminhos continuam isolados mesmo depois de imports feitos pelos testes.
    problems = assert_isolated(persistence_paths())
    if problems:
        pytest.exit(
            "Isolamento abortado durante a execução: " + "; ".join(problems),
            returncode=3,
        )

    _reset_test_data()
    import database

    database.init_db()
    try:
        yield
    finally:
        _state["network_allowed"] = False
        _state["subprocess_allowed"] = False


def _reset_test_data() -> None:
    """Esvazia o banco e as pastas do diretório temporário da sessão."""
    gc.collect()
    db_path = runtime_paths.DB_PATH
    if db_path.exists():
        connection = sqlite3.connect(db_path, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
            for table in tables:
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
            connection.execute("PRAGMA user_version = 0")
            connection.commit()
        finally:
            connection.close()
    for directory in (
        runtime_paths.DOCUMENTS_DIR,
        runtime_paths.BACKUPS_DIR,
        runtime_paths.SUPPORT_DIR,
    ):
        if directory.exists():
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()


class IsolationGuard:
    """Acesso dos testes de isolamento ao estado desta proteção."""

    test_root = TEST_ROOT
    protected_roots = PROTECTED_ROOTS
    violations = VIOLATIONS
    probes_blocked = PROBES_BLOCKED
    network_blocked = NETWORK_BLOCKED
    processes_blocked = PROCESSES_BLOCKED

    @staticmethod
    def persistence_paths() -> dict[str, Path]:
        return persistence_paths()

    @staticmethod
    def problems() -> list[str]:
        return assert_isolated(persistence_paths())

    @staticmethod
    @contextmanager
    def expect_blocked():
        """Sonda intencional: o acesso deve ser bloqueado e não conta como violação."""
        _state["expected_probe"] = True
        try:
            yield
        finally:
            _state["expected_probe"] = False


@pytest.fixture
def isolation_guard() -> IsolationGuard:
    return IsolationGuard()


def _snapshot_differences() -> list[str]:
    with _bypass_audit():
        after = _snapshot(PROTECTED_ROOTS)
    differences = []
    for path in sorted(set(SNAPSHOT_BEFORE) | set(after)):
        if SNAPSHOT_BEFORE.get(path) != after.get(path):
            differences.append(path)
    return differences


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    differences = _snapshot_differences()
    session.config._checkfiscal_isolation = {  # type: ignore[attr-defined]
        "test_root": str(TEST_ROOT),
        "protected_roots": PROTECTED_ROOTS,
        "protected_files_checked": len(SNAPSHOT_BEFORE),
        "protected_files_changed": differences,
        "violations": VIOLATIONS,
        "probes_blocked": len(PROBES_BLOCKED),
        "network_blocked": NETWORK_BLOCKED,
        "processes_blocked": PROCESSES_BLOCKED,
    }
    evidence_path = os.environ.get("CHECKFISCAL_TEST_EVIDENCE")
    if evidence_path:
        with _bypass_audit():
            Path(evidence_path).write_text(
                json.dumps(session.config._checkfiscal_isolation, ensure_ascii=False, indent=2),  # type: ignore[attr-defined]
                encoding="utf-8",
            )
    if VIOLATIONS:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED

    for handler in list(logging.getLogger("checkfiscal").handlers):
        handler.close()
    # Conexões abertas por database.connect() só são liberadas pelo coletor
    # de lixo; sem isso o Windows mantém o banco temporário travado.
    gc.collect()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    evidence = getattr(config, "_checkfiscal_isolation", None)
    if not evidence:
        return
    write = terminalreporter.write_line
    terminalreporter.section("Isolamento CheckFiscal")
    write(f"Diretório de teste: {evidence['test_root']}")
    write(f"Locais reais protegidos: {len(evidence['protected_roots'])}")
    for root in evidence["protected_roots"]:
        write(f"  - {root}")
    write(f"Arquivos reais verificados: {evidence['protected_files_checked']}")
    write(f"Arquivos reais alterados durante a sessão: {len(evidence['protected_files_changed'])}")
    for path in evidence["protected_files_changed"]:
        write(f"  ! {path} (nenhum acesso do processo de teste registrado: origem externa)"
              if not evidence["violations"] else f"  ! {path}")
    write(f"Tentativas de acesso a dados reais (violações): {len(evidence['violations'])}")
    for violation in evidence["violations"]:
        write(f"  X {violation['event']} {violation['path']} em {violation['test']}")
    write(f"Sondas intencionais bloqueadas: {evidence['probes_blocked']}")
    write(f"Conexões de rede bloqueadas: {len(evidence['network_blocked'])}")
    write(f"Subprocessos bloqueados: {len(evidence['processes_blocked'])}")
