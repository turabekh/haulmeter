import os
import sys

EXTENSIONS = (".py", ".vue", ".yml", ".yaml", ".txt", ".md", ".example")

SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "alembic",
    "alembic_bluelake",
    "alembic_raw",
    "htmlcov",
    "venv",
    "env",
    ".venv",
    "docs",
    "pytest_cache",
    ".pytest_cache",
    "node_modules",
    ".nuxt",
    ".output",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
}


def collect_files(folder_name, output_file=None):
    if not os.path.exists(folder_name):
        print(f"Error: Folder '{folder_name}' does not exist.")
        return
    if not os.path.isdir(folder_name):
        print(f"Error: '{folder_name}' is not a directory.")
        return

    collected = []
    for root, dirs, files in os.walk(folder_name):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if filename.endswith(EXTENSIONS):
                collected.append(os.path.join(root, filename))

    if not collected:
        print(f"No matching files found in '{folder_name}'")
        return

    collected.sort()

    output = []
    for filepath in collected:
        output.append(f"# {filepath}\n")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                output.append(f.read())
            output.append("\n\n")
        except Exception as e:
            output.append(f"Error reading file: {e}\n\n")

    result = "".join(output)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Output written to {output_file}")
    else:
        print(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <folder_name> [output_file]")
        sys.exit(1)
    folder_name = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    collect_files(folder_name, output_file)