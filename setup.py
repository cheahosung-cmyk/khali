"""Setup script for Khali package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="khali",
    version="0.1.0",
    author="cheahosung-cmyk",
    author_email="cheahosung@gmail.com",
    description="AI Agent Management System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cheahosung-cmyk/khali",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "sqlalchemy>=2.0.23",
        "alembic>=1.12.1",
        "aiohttp>=3.9.1",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "black>=23.12.0",
            "flake8>=6.1.0",
            "isort>=5.13.2",
            "mypy>=1.7.1",
        ],
        "docs": [
            "mkdocs>=1.5.3",
            "mkdocs-material>=9.4.14",
        ],
        "excel": [
            "openpyxl>=3.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "khali=src.main:main",
        ],
    },
)
