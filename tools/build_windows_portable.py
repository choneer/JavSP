"""Build a standalone Windows directory in a new, empty destination."""
from argparse import ArgumentParser
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--site-packages', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copytree(args.runtime, dest / 'runtime', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    site = dest / 'runtime' / 'Lib' / 'site-packages'
    shutil.copytree(args.site_packages, site, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'javsp.pth', 'pytest*', '_pytest', 'pip*'))
    for directory in ('javsp', 'data', 'image'):
        shutil.copytree(ROOT / directory, dest / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(args.config, dest / 'config.yml')
    for file in ('LICENSE',):
        shutil.copy2(ROOT / file, dest / file)
    shutil.copy2(ROOT / 'README.md', dest / 'UPSTREAM-README.md')
    shutil.copy2(ROOT / 'docs' / 'WINDOWS_WEBUI.md', dest / '使用说明.md')
    (dest / 'Start-WebUI.cmd').write_text(
        '@echo off\r\ncd /d "%~dp0"\r\n'
        'echo Starting JavSP WebUI on http://127.0.0.1:8765\r\n'
        '"%~dp0runtime\\python.exe" -m javsp.server --open-browser\r\n'
        'echo WebUI stopped.\r\npause\r\n', encoding='ascii', newline='')
    print(dest)


if __name__ == '__main__':
    main()
